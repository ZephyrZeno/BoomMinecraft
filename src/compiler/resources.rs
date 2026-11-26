//! Frozen, source-identified class resources. Preparation is a build operation;
//! lookup, file IO and allocation during guest execution are handwritten MASM.
use super::{classfile::ClassFile, numeric, types};
use crate::{boot_modules, files, jdk::JdkBase, lock::InputLock, tools};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fmt::Write as _,
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::Command,
};

pub const DESCRIPTOR: &str = "(Ljava/lang/String;)Ljava/io/InputStream;";
const LIMIT: u64 = 2 * 1024 * 1024 * 1024;
const ENTRY_LIMIT: u64 = 64 * 1024 * 1024;
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub id: usize,
    pub caller: String,
    pub caller_loader: String,
    pub caller_java_base: bool,
    pub origin: crate::bytecode::ClassOrigin,
}

#[cfg(test)]
mod tests {
    use super::*;
    fn zip(path: &Path, rows: &[(&str, &[u8])]) {
        let mut z = zip::ZipWriter::new(fs::File::create(path).unwrap());
        for (n, b) in rows {
            z.start_file(*n, zip::write::SimpleFileOptions::default())
                .unwrap();
            z.write_all(b).unwrap();
        }
        z.finish().unwrap();
    }
    #[test]
    fn multirelease_resource_aliases_preserve_physical_names_and_meta_inf_rules() {
        let dir = tempfile::tempdir().unwrap();
        let input = dir.path().join("source.jar");
        zip(
            &input,
            &[
                (
                    "META-INF/MANIFEST.MF",
                    b"Manifest-Version: 1.0\r\nMulti-Relea\r\n se: true\r\n\r\n",
                ),
                ("a", b"base"),
                ("META-INF/versions/9/a", b"nine"),
                ("META-INF/versions/21/a", b"current"),
                ("META-INF/versions/22/a", b"future"),
                ("META-INF/services/p.X", b"ordinary"),
                (
                    "META-INF/versions/21/META-INF/services/p.X",
                    b"invalid-alias",
                ),
            ],
        );
        let mut f = fs::File::create(dir.path().join("pack")).unwrap();
        f.write_all(&[0; 64]).unwrap();
        let mut pos = 64;
        let p = jar(
            &mut f,
            &mut pos,
            &input,
            "fixture",
            &files::digest(&input).unwrap(),
        )
        .unwrap();
        assert_eq!(
            p.entries
                .iter()
                .find(|e| e.name == "a")
                .unwrap()
                .source_entry,
            "META-INF/versions/21/a"
        );
        assert_eq!(
            p.entries
                .iter()
                .find(|e| e.name == "META-INF/services/p.X")
                .unwrap()
                .sha256,
            files::digest_bytes(b"ordinary").sha256
        );
        assert!(p.entries.iter().any(|e| e.name == "META-INF/versions/22/a"));
    }
    #[test]
    fn resource_rows_use_utf16_order_and_empty_entries_have_real_content_identity() {
        let dir = tempfile::tempdir().unwrap();
        let input = dir.path().join("source.jar");
        zip(
            &input,
            &[
                ("\u{e000}", b"bmp"),
                ("\u{10000}", b"supplementary"),
                ("empty/", b""),
            ],
        );
        let mut f = fs::File::create(dir.path().join("pack")).unwrap();
        f.write_all(&[0; 64]).unwrap();
        let mut pos = 64;
        let p = jar(
            &mut f,
            &mut pos,
            &input,
            "fixture",
            &files::digest(&input).unwrap(),
        )
        .unwrap();
        assert_eq!(
            p.entries
                .iter()
                .map(|e| e.name.as_str())
                .collect::<Vec<_>>(),
            vec!["empty/", "\u{10000}", "\u{e000}"]
        );
        let empty = &p.entries[0];
        assert_eq!(empty.length, 0);
        assert_eq!(empty.sha256, files::digest_bytes(b"").sha256);
    }
    #[test]
    fn cache_validation_checks_header_even_after_rehash_and_rejects_bad_ranges() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("resources.pack");
        let key = "12".repeat(32);
        fs::write(&path, header(&key, 64).unwrap()).unwrap();
        let mut p = Pack {
            abi: 1,
            key,
            boot_fingerprint: "34".repeat(32),
            providers: Vec::new(),
            file: files::digest(&path).unwrap(),
        };
        assert!(validate_pack(&p, &path).is_ok());
        let mut data = fs::read(&path).unwrap();
        data[0] = 0;
        fs::write(&path, &data).unwrap();
        p.file = files::digest(&path).unwrap();
        assert!(validate_pack(&p, &path).is_err());
        fs::write(&path, header(&p.key, 64).unwrap()).unwrap();
        p.file = files::digest(&path).unwrap();
        p.providers.push(Provider {
            name: "fixture".into(),
            module: false,
            source_sha256: "00".repeat(32),
            entries: vec![Entry {
                name: "x".into(),
                source_entry: "x".into(),
                offset: 63,
                length: 1,
                sha256: files::digest_bytes(b"x").sha256,
            }],
        });
        assert!(validate_pack(&p, &path).is_err());
    }
}
#[derive(Debug, Clone)]
pub(super) struct Link {
    pub signature: numeric::Signature,
    pub class_id: usize,
    pub constructor: usize,
    pub caller: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Entry {
    pub name: String,
    pub source_entry: String,
    pub offset: u64,
    pub length: u64,
    pub sha256: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Provider {
    pub name: String,
    pub module: bool,
    pub source_sha256: String,
    pub entries: Vec<Entry>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Pack {
    pub abi: u32,
    pub key: String,
    pub boot_fingerprint: String,
    pub providers: Vec<Provider>,
    pub file: files::FileDigest,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Anchor {
    pub prefix: Vec<u16>,
    pub domain: u32,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub pack: Pack,
    pub file: PathBuf,
    pub anchors: Vec<Anchor>,
    pub callers: Vec<Binding>,
}

pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    loader: &str,
    id: usize,
) -> Result<Binding> {
    let class = registry.class("bootstrap", "java/lang/Class")?;
    let types::Type::Class {
        key,
        origin,
        access,
        ..
    } = &registry.types[class]
    else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none()
            && access & 0x211 == 0x11,
        "Class resources require the pinned final java.base Class"
    );
    let method = registry
        .definition(class)
        .unwrap()
        .method("getResourceAsStream", Some(DESCRIPTOR))?;
    ensure!(
        method.access & (1 | 8 | 0x20 | 0x100 | 0x400) == 1 && method.code.is_some(),
        "Class resource member contract changed"
    );
    let origin = origin.as_ref().clone();
    // This profile preserves the pinned JDK's Jar URL decoder behavior, including
    // its failure for supplementary resource names. A changed implementation
    // must be reviewed instead of silently inheriting that compatibility rule.
    let policy = registry.class("bootstrap", "sun/net/www/ParseUtil")?;
    ensure!(
        matches!(&registry.types[policy],types::Type::Class{key,origin,..}
        if key.loader=="bootstrap" && origin.sha256=="ee919a5d8c4bd78e60aad97dee0dd3b4cd5bc06b957c9cda66eba17e5471a585"),
        "Jar URL encoding implementation changed; resource policy needs verification"
    );
    let current = registry.class(loader, &caller.name)?;
    let types::Type::Class {
        key,
        origin: creator,
        ..
    } = &registry.types[current]
    else {
        unreachable!()
    };
    let caller_java_base = key.loader == "bootstrap"
        && (creator.source_id == "jdk:java.base"
            || creator
                .generated
                .as_ref()
                .is_some_and(|g| g.host_source_id == "jdk:java.base"));
    ensure!(
        caller_java_base || key.loader != "bootstrap",
        "Other named caller module providers are not implemented"
    );
    Ok(Binding {
        id,
        caller: caller.name.clone(),
        caller_loader: key.loader.clone(),
        caller_java_base,
        origin,
    })
}
fn plain(path: &Path) -> Result<()> {
    let m = fs::symlink_metadata(path)?;
    ensure!(
        !m.file_type().is_symlink(),
        "Resource input/cache contains a symbolic link"
    );
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        ensure!(
            m.file_attributes() & 0x400 == 0,
            "Resource input/cache contains a reparse point"
        );
    }
    Ok(())
}
fn name_valid(name: &str) -> Result<()> {
    ensure!(
        !name.is_empty() && !name.contains('\0') && name.encode_utf16().count() <= 32767,
        "Unsupported resource name length or NUL"
    );
    Ok(())
}
fn header(key: &str, bytes: u64) -> Result<Vec<u8>> {
    files::validate_hash(key, 64)?;
    let mut h = Vec::from(*b"BOOMRES1");
    h.extend(1u32.to_le_bytes());
    h.extend(64u32.to_le_bytes());
    h.extend(bytes.to_le_bytes());
    for pair in key.as_bytes().as_chunks::<2>().0.iter() {
        h.push(u8::from_str_radix(std::str::from_utf8(pair)?, 16)?);
    }
    h.extend([0u8; 8]);
    Ok(h)
}
fn append(
    file: &mut fs::File,
    position: &mut u64,
    name: &str,
    source: &str,
    bytes: &[u8],
) -> Result<Entry> {
    name_valid(name)?;
    ensure!(
        bytes.len() as u64 <= ENTRY_LIMIT,
        "Resource exceeds 64 MiB: {name}"
    );
    let end = position
        .checked_add(bytes.len() as u64)
        .context("Resource pack overflow")?;
    ensure!(end <= LIMIT, "Resource pack exceeds 2 GiB");
    let e = Entry {
        name: name.into(),
        source_entry: source.into(),
        offset: *position,
        length: bytes.len() as u64,
        sha256: files::digest_bytes(bytes).sha256,
    };
    file.write_all(bytes)?;
    *position = end;
    Ok(e)
}
fn sorted(entries: &mut [Entry]) {
    entries.sort_by(|a, b| a.name.encode_utf16().cmp(b.name.encode_utf16()));
}
fn jar(
    file: &mut fs::File,
    pos: &mut u64,
    path: &Path,
    name: &str,
    expected: &files::FileDigest,
) -> Result<Provider> {
    plain(path)?;
    ensure!(files::digest(path)? == *expected, "Resource JAR changed");
    let mut archive = zip::ZipArchive::new(fs::File::open(path)?)?;
    let multi = match archive.by_name("META-INF/MANIFEST.MF") {
        Ok(e) => {
            let mut s = String::new();
            e.take(1024 * 1024).read_to_string(&mut s)?;
            crate::bytecode::main_manifest_attributes(&s)
                .get("multi-release")
                .is_some_and(|v| v.eq_ignore_ascii_case("true"))
        }
        Err(zip::result::ZipError::FileNotFound) => false,
        Err(e) => return Err(e.into()),
    };
    ensure!(archive.len() <= 262144, "Resource JAR exceeds entry budget");
    let mut physical = BTreeMap::new();
    for i in 0..archive.len() {
        let e = archive.by_index(i)?;
        let n = e.name()?.into_owned();
        ensure!(
            !physical.contains_key(&n),
            "Duplicate resource entry in one JAR: {n}"
        );
        ensure!(e.size() <= ENTRY_LIMIT, "Oversized resource: {n}");
        let mut b = Vec::new();
        e.take(ENTRY_LIMIT + 1).read_to_end(&mut b)?;
        let row = append(file, pos, &n, &n, &b)?;
        physical.insert(n, row);
    }
    let mut selected = physical.clone();
    let mut versions = BTreeMap::<String, u32>::new();
    if multi {
        for (name, row) in &physical {
            if let Some((version, logical)) = name
                .strip_prefix("META-INF/versions/")
                .and_then(|s| s.split_once('/'))
                && let Ok(v) = version.parse::<u32>()
                && (9..=crate::JAVA_MAJOR).contains(&v)
                && !logical.is_empty()
                && !logical.starts_with("META-INF/")
                && versions.get(logical).is_none_or(|old| v > *old)
            {
                let mut alias = row.clone();
                alias.name = logical.into();
                selected.insert(logical.into(), alias);
                versions.insert(logical.into(), v);
            }
        }
    }
    let mut entries: Vec<_> = selected.into_values().collect();
    sorted(&mut entries);
    ensure!(
        files::digest(path)? == *expected,
        "Resource JAR changed during preparation"
    );
    Ok(Provider {
        name: name.into(),
        module: false,
        source_sha256: expected.sha256.clone(),
        entries,
    })
}
fn tree(root: &Path) -> Result<Vec<PathBuf>> {
    let mut todo = vec![root.to_owned()];
    let mut result = Vec::new();
    while let Some(dir) = todo.pop() {
        plain(&dir)?;
        for e in fs::read_dir(dir)? {
            let e = e?;
            let p = e.path();
            plain(&p)?;
            if e.file_type()?.is_dir() {
                todo.push(p)
            } else {
                ensure!(e.file_type()?.is_file(), "Nonregular resource entry");
                result.push(p);
            }
            ensure!(
                result.len() + todo.len() <= 262144,
                "Resource tree entry budget exceeded"
            );
        }
    }
    result.sort();
    Ok(result)
}

pub(super) fn prepare(
    inputs: &InputLock,
    base: &Path,
    snapshot: &boot_modules::Snapshot,
    extra: &[PathBuf],
    explicit: bool,
) -> Result<(Pack, PathBuf)> {
    inputs.verify()?;
    let jdk = JdkBase::read(base, inputs)?;
    ensure!(
        jdk.image.digest == snapshot.image.digest
            && jdk.extractor.digest == snapshot.extractor.digest,
        "Resource and module metadata must use the same pinned JDK image/extractor"
    );
    ensure!(
        !explicit || !extra.is_empty(),
        "Explicit class resources require --resource-jar to define their frozen resource classpath"
    );
    let mut jars = Vec::new();
    for (i, p) in extra.iter().enumerate() {
        let p = files::absolute(p)?;
        jars.push((
            format!("explicit-resource-{i}"),
            p.clone(),
            files::digest(&p)?,
        ));
    }
    for id in &inputs.classpath {
        let f = inputs.file(id)?;
        jars.push((id.clone(), f.path.clone(), f.digest.clone()));
    }
    let key = files::digest_bytes(&serde_json::to_vec(&(
        1u32,
        &inputs.fingerprint,
        &jdk.image.digest,
        &jdk.extractor.digest,
        &snapshot.fingerprint,
        jars.iter().map(|(id, _, d)| (id, d)).collect::<Vec<_>>(),
    ))?)
    .sha256;
    let mut names: Vec<_> = snapshot.graph.resolved.keys().collect();
    names.sort_by_key(|n| {
        let l = snapshot.graph.resolved[*n].loader;
        (
            match l {
                boot_modules::Loader::Bootstrap => 0,
                boot_modules::Loader::Platform => 1,
                boot_modules::Loader::Application => 2,
            },
            *n,
        )
    });
    let cache_parent = std::env::current_dir()?.join(".boom/resource-cache");
    for parent in cache_parent.ancestors() {
        if parent.exists() {
            plain(parent)?;
        }
    }
    fs::create_dir_all(&cache_parent)?;
    plain(&cache_parent)?;
    let cache = cache_parent.join(&key);
    if cache.exists() {
        plain(&cache)?;
        let pack: Pack = serde_json::from_slice(&fs::read(cache.join("resources.json"))?)?;
        ensure!(
            pack.abi == 1 && pack.key == key && pack.boot_fingerprint == snapshot.fingerprint,
            "Resource cache belongs to different inputs"
        );
        let expected = names
            .iter()
            .map(|n| ((*n).clone(), true, jdk.image.digest.sha256.clone()))
            .chain(
                jars.iter()
                    .map(|(n, _, d)| (n.clone(), false, d.sha256.clone())),
            )
            .collect::<Vec<_>>();
        ensure!(
            pack.providers
                .iter()
                .map(|p| (p.name.clone(), p.module, p.source_sha256.clone()))
                .eq(expected),
            "Resource provider order/source changed"
        );
        validate_pack(&pack, &cache.join("resources.pack"))?;
        return Ok((pack, cache.join("resources.pack")));
    }
    let temp = tempfile::Builder::new()
        .prefix("resource-")
        .tempdir_in(&cache_parent)?;
    ensure!(
        temp.path().is_absolute() && temp.path().starts_with(&cache_parent),
        "Resource staging escaped its workspace"
    );
    let image = temp.path().join("image");
    fs::create_dir(&image)?;
    ensure!(
        files::digest(&jdk.extractor.path)? == jdk.extractor.digest,
        "Resource extractor changed"
    );
    let mut cmd = Command::new(&jdk.extractor.path);
    tools::clean_java_environment(&mut cmd);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let result = cmd
        .args(["extract", "--dir"])
        .arg(&image)
        .arg(&jdk.image.path)
        .output()?;
    ensure!(
        result.status.success(),
        "Resource image extraction failed: {}",
        String::from_utf8_lossy(&result.stderr)
    );
    ensure!(
        files::digest(&jdk.image.path)? == jdk.image.digest
            && files::digest(&jdk.extractor.path)? == jdk.extractor.digest,
        "Resource image/extractor changed during extraction"
    );
    let pack_path = temp.path().join("resources.pack");
    let mut file = fs::File::create(&pack_path)?;
    file.write_all(&[0u8; 64])?;
    let mut pos = 64;
    let mut providers = Vec::new();
    // Built-in delegation order, then a deterministic order within each loader.
    for name in names {
        let module_root = image.join(name);
        let mut entries = Vec::new();
        for path in tree(&module_root)? {
            let logical = path
                .strip_prefix(&module_root)?
                .to_string_lossy()
                .replace('\\', "/");
            let bytes = fs::read(&path)?;
            if name == "java.base"
                && let Some(class) = logical.strip_suffix(".class")
                && class != "module-info"
            {
                let origin = jdk
                    .classes
                    .get(&class.replace('/', "."))
                    .context("Resource class absent from pinned java.base")?;
                ensure!(
                    files::digest_bytes(&bytes).sha256 == origin.sha256,
                    "Resource class differs from executable JDK definition"
                );
            }
            entries.push(append(
                &mut file,
                &mut pos,
                &logical,
                &format!("{name}/{logical}"),
                &bytes,
            )?);
        }
        sorted(&mut entries);
        providers.push(Provider {
            name: name.clone(),
            module: true,
            source_sha256: jdk.image.digest.sha256.clone(),
            entries,
        });
    }
    for (name, path, digest) in &jars {
        providers.push(jar(&mut file, &mut pos, path, name, digest)?);
    }
    use std::io::{Seek, SeekFrom};
    file.seek(SeekFrom::Start(0))?;
    file.write_all(&header(&key, pos)?)?;
    file.sync_all()?;
    drop(file);
    let pack = Pack {
        abi: 1,
        key,
        boot_fingerprint: snapshot.fingerprint.clone(),
        providers,
        file: files::digest(&pack_path)?,
    };
    validate_pack(&pack, &pack_path)?;
    let publish = temp.path().join("publish");
    ensure!(
        publish.starts_with(&cache_parent) && cache.starts_with(&cache_parent),
        "Resource publication escaped its workspace"
    );
    fs::create_dir(&publish)?;
    files::write_atomic(
        &publish.join("resources.json"),
        &serde_json::to_vec_pretty(&pack)?,
    )?;
    fs::rename(&pack_path, publish.join("resources.pack"))?;
    if let Err(error) = fs::rename(&publish, &cache) {
        if !cache.exists() {
            return Err(error.into());
        }
        let winner: Pack = serde_json::from_slice(&fs::read(cache.join("resources.json"))?)?;
        ensure!(
            serde_json::to_value(&winner)? == serde_json::to_value(&pack)?,
            "Concurrent resource preparation disagreed"
        );
        validate_pack(&winner, &cache.join("resources.pack"))?;
    }
    Ok((pack, cache.join("resources.pack")))
}
fn validate_pack(pack: &Pack, path: &Path) -> Result<()> {
    plain(path)?;
    ensure!(
        pack.file.size >= 64 && pack.file.size <= LIMIT && files::digest(path)? == pack.file,
        "Resource pack content changed"
    );
    let mut actual = [0u8; 64];
    fs::File::open(path)?.read_exact(&mut actual)?;
    ensure!(
        actual.as_slice() == header(&pack.key, pack.file.size)?,
        "Resource pack header identity changed"
    );
    ensure!(
        pack.providers.len() <= 4096,
        "Resource provider budget exceeded"
    );
    let mut total = 0;
    for p in &pack.providers {
        ensure!(
            p.entries.len() <= 262144,
            "Resource provider entry budget exceeded"
        );
        let mut previous: Option<&str> = None;
        for e in &p.entries {
            name_valid(&e.name)?;
            ensure!(
                previous.is_none_or(|n| n.encode_utf16().cmp(e.name.encode_utf16()).is_lt()),
                "Resource entries are not strictly UTF-16 sorted"
            );
            previous = Some(&e.name);
            ensure!(
                e.offset >= 64
                    && e.length <= ENTRY_LIMIT
                    && e.offset
                        .checked_add(e.length)
                        .is_some_and(|end| end <= pack.file.size),
                "Resource entry outside pack"
            );
            files::validate_hash(&e.sha256, 64)?;
            total += 1;
            ensure!(total <= 262144, "Combined resource entry budget exceeded");
        }
    }
    Ok(())
}

impl Plan {
    pub(super) fn verify_definitions(&self, sources: &[super::program::Source]) -> Result<()> {
        for s in sources {
            if s.origin
                .as_ref()
                .is_some_and(|o| o.loader == "bootstrap" || o.generated.is_some())
            {
                continue;
            }
            let name = format!("{}.class", s.class_name);
            let entry = self.pack.providers.iter().find_map(|p| {
                p.entries
                    .binary_search_by(|e| e.name.encode_utf16().cmp(name.encode_utf16()))
                    .ok()
                    .map(|i| &p.entries[i])
            });
            ensure!(
                entry.is_some_and(|e| e.sha256 == s.digest.sha256),
                "Raw executable class disagrees with its frozen resource classpath: {}",
                s.class_name
            );
        }
        Ok(())
    }
    pub(super) fn new(
        pack: Pack,
        file: PathBuf,
        types: &[types::Type],
        callers: Vec<Binding>,
    ) -> Result<Self> {
        fn anchor(types: &[types::Type], id: usize, base: u32, depth: usize) -> Result<Anchor> {
            ensure!(depth < 256, "Resource anchor component cycle");
            Ok(match &types[id] {
                types::Type::Array { component } => anchor(types, *component, base, depth + 1)?,
                types::Type::Primitive { .. } => Anchor {
                    prefix: "java/lang/".encode_utf16().collect(),
                    domain: base,
                },
                types::Type::Class { key, origin, .. } => {
                    let domain = if key.loader == "bootstrap" {
                        ensure!(
                            origin.source_id == "jdk:java.base"
                                || origin
                                    .generated
                                    .as_ref()
                                    .is_some_and(|g| g.host_source_id == "jdk:java.base"),
                            "Other named resource anchor class providers are not implemented"
                        );
                        base
                    } else {
                        0
                    };
                    Anchor {
                        prefix: key.name.rsplit_once('/').map_or(Vec::new(), |(p, _)| {
                            format!("{p}/").encode_utf16().collect()
                        }),
                        domain,
                    }
                }
            })
        }
        let base = (pack
            .providers
            .iter()
            .position(|p| p.module && p.name == "java.base")
            .context("Missing java.base resource provider")?
            + 1) as u32;
        let anchors = (0..types.len())
            .map(|id| anchor(types, id, base, 0))
            .collect::<Result<_>>()?;
        Ok(Self {
            pack,
            file,
            anchors,
            callers,
        })
    }
    pub(super) fn publish(&self, source: &Path) -> Result<()> {
        if self.file.exists() {
            plain(&self.file)?;
            ensure!(
                files::digest(&self.file)? == self.pack.file,
                "Existing resource sidecar differs"
            );
            return Ok(());
        }
        if fs::hard_link(source, &self.file).is_err() {
            fs::copy(source, &self.file)?;
        }
        ensure!(
            files::digest(&self.file)? == self.pack.file,
            "Resource sidecar copy changed"
        );
        Ok(())
    }
    pub(super) fn emit(
        &self,
        assembly: &mut String,
        snapshot: &boot_modules::Snapshot,
    ) -> Result<()> {
        fn words(s: &mut String, label: &str, value: &[u16]) -> Result<()> {
            writeln!(s, "ALIGN 2\n{label} LABEL WORD")?;
            if value.is_empty() {
                writeln!(s, "    WORD 0")?;
            } else {
                for chunk in value.chunks(16) {
                    writeln!(
                        s,
                        "    WORD {}",
                        chunk
                            .iter()
                            .map(|v| format!("0{v:04X}h"))
                            .collect::<Vec<_>>()
                            .join(",")
                    )?;
                }
            }
            Ok(())
        }
        assembly.push_str(
            "EXTERN boom_resource_bytes:PROC\n.const\nALIGN 8\nboom_resource_pack_id LABEL BYTE\n",
        );
        writeln!(
            assembly,
            "    BYTE {}",
            self.pack
                .key
                .as_bytes()
                .as_chunks::<2>()
                .0
                .iter()
                .map(|b| u8::from_str_radix(std::str::from_utf8(b).unwrap(), 16)
                    .unwrap()
                    .to_string())
                .collect::<Vec<_>>()
                .join(",")
        )?;
        let base = (self
            .pack
            .providers
            .iter()
            .position(|p| p.module && p.name == "java.base")
            .unwrap()
            + 1) as u32;
        for (pi, p) in self.pack.providers.iter().enumerate() {
            for (i, e) in p.entries.iter().enumerate() {
                words(
                    assembly,
                    &format!("boom_resource_name_{pi}_{i}"),
                    &e.name.encode_utf16().collect::<Vec<_>>(),
                )?;
                writeln!(
                    assembly,
                    "boom_resource_sha_{pi}_{i} BYTE {}",
                    e.sha256
                        .as_bytes()
                        .as_chunks::<2>()
                        .0
                        .iter()
                        .map(|b| u8::from_str_radix(std::str::from_utf8(b).unwrap(), 16)
                            .unwrap()
                            .to_string())
                        .collect::<Vec<_>>()
                        .join(",")
                )?;
            }
            writeln!(assembly, "ALIGN 8\nboom_resource_entries_{pi} LABEL BYTE")?;
            if p.entries.is_empty() {
                writeln!(assembly, "    QWORD 0,0,0,0,0")?;
            }
            for (i, e) in p.entries.iter().enumerate() {
                writeln!(
                    assembly,
                    "    QWORD OFFSET boom_resource_name_{pi}_{i}\n    DWORD {},0\n    QWORD {},{}\n    QWORD OFFSET boom_resource_sha_{pi}_{i}",
                    e.name.encode_utf16().count(),
                    e.offset,
                    e.length
                )?;
            }
            if p.module {
                let d = &snapshot.modules[&p.name].descriptor;
                let mut packages = d.packages.clone();
                packages.sort_by(|a, b| a.encode_utf16().cmp(b.encode_utf16()));
                for (i, n) in packages.iter().enumerate() {
                    words(
                        assembly,
                        &format!("boom_resource_package_{pi}_{i}"),
                        &n.encode_utf16().collect::<Vec<_>>(),
                    )?;
                }
                writeln!(assembly, "ALIGN 8\nboom_resource_packages_{pi} LABEL BYTE")?;
                if packages.is_empty() {
                    writeln!(assembly, "    QWORD 0,0")?;
                }
                for (i, n) in packages.iter().enumerate() {
                    let open = d.flags & 0x20 != 0;
                    let row = d.opens.iter().find(|o| o.package == *n);
                    let bits = if open || row.is_some_and(|o| o.targets.is_empty()) {
                        1
                    } else if row.is_some_and(|o| o.targets.iter().any(|t| t == "java.base")) {
                        2
                    } else {
                        0
                    };
                    writeln!(
                        assembly,
                        "    QWORD OFFSET boom_resource_package_{pi}_{i}\n    DWORD {},{}",
                        n.encode_utf16().count(),
                        bits
                    )?;
                }
            }
        }
        writeln!(assembly, "ALIGN 8\nboom_resource_providers LABEL BYTE")?;
        for (pi, p) in self.pack.providers.iter().enumerate() {
            writeln!(
                assembly,
                "    DWORD {},0,{},0\n    QWORD OFFSET boom_resource_entries_{pi}",
                u32::from(p.module),
                p.entries.len()
            )?;
            if p.module {
                writeln!(
                    assembly,
                    "    QWORD OFFSET boom_resource_packages_{pi}\n    DWORD {},0",
                    snapshot.modules[&p.name].descriptor.packages.len()
                )?;
            } else {
                writeln!(assembly, "    QWORD 0\n    DWORD 0,0")?;
            }
        }
        for (i, a) in self.anchors.iter().enumerate() {
            words(assembly, &format!("boom_resource_prefix_{i}"), &a.prefix)?;
        }
        writeln!(assembly, "ALIGN 8\nboom_resource_anchors LABEL BYTE")?;
        for (i, a) in self.anchors.iter().enumerate() {
            writeln!(
                assembly,
                "    QWORD OFFSET boom_resource_prefix_{i}\n    DWORD {},{}",
                a.prefix.len(),
                a.domain
            )?;
        }
        writeln!(assembly, "ALIGN 4\nboom_resource_callers LABEL DWORD")?;
        for c in &self.callers {
            writeln!(
                assembly,
                "    DWORD {}",
                if c.caller_java_base { base } else { 0 }
            )?;
        }
        assembly.push_str(".data\nALIGN 16\nboom_resource_path WORD 32768 DUP(0)\nALIGN 8\nboom_resource_pool DWORD 052455350h,1,0,");
        writeln!(
            assembly,
            "{}\n    QWORD OFFSET boom_resource_providers,OFFSET boom_resource_anchors\n    DWORD {},{}\n    QWORD OFFSET boom_resource_callers,OFFSET boom_resource_pack_id,{}\n    QWORD OFFSET boom_mirror_pool,OFFSET boom_resource_path\n.code",
            self.pack.providers.len(),
            self.anchors.len(),
            self.callers.len(),
            self.pack.file.size
        )?;
        Ok(())
    }
}
