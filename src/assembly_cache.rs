//! Cache only the mechanical MASM -> COFF step. Source generation and all
//! independent source/layout/link checks still run, even on a cache hit.
use crate::{files, tools};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{fs, io::Write, path::Path};

const MAGIC: &[u8; 8] = b"BMCACHE1";
const MAX_METADATA: usize = 1024 * 1024;
const MAX_OBJECT: usize = 128 * 1024 * 1024;
const OPTIONS: &str = "AMD64:/nologo:/c:ML-environment-removed:no-debug";

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Identity {
    schema: u32,
    assembler_sha256: String,
    assembly_sha256: String,
    options: String,
}

impl Identity {
    fn new(assembly: &[u8], assembler_sha256: String) -> Self {
        Self {
            schema: 1,
            assembler_sha256,
            assembly_sha256: files::digest_bytes(assembly).sha256,
            options: OPTIONS.into(),
        }
    }

    fn key(&self) -> Result<String> {
        Ok(files::digest_bytes(&serde_json::to_vec(self)?).sha256)
    }
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Entry {
    identity: Identity,
    object: files::FileDigest,
    assembler_log: String,
}

#[derive(Debug, Serialize)]
pub struct CacheRecord {
    pub schema: u32,
    pub status: String,
    pub key: Option<String>,
    pub assembly_sha256: String,
    pub assembler_sha256: String,
    pub reason: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct AssemblyResult {
    pub success: bool,
    pub exit_code: Option<i32>,
    pub cache: CacheRecord,
}

/// Generated modules normally have all include_str! content expanded. Be
/// conservative for developer-supplied input with external or path/time inputs.
fn self_contained(source: &[u8]) -> bool {
    let Ok(text) = std::str::from_utf8(source) else {
        return false;
    };
    let upper = text.to_ascii_uppercase();
    ![
        "INCLUDE",
        "INCBIN",
        "ENVIRON",
        "@FILENAME",
        "@DATE",
        "@TIME",
        "__FILE__",
        "__DATE__",
        "__TIME__",
    ]
    .iter()
    .any(|word| upper.contains(word))
        && !upper.lines().any(|line| line.trim_start().starts_with('%'))
}

fn check_coff(object: &[u8]) -> Result<()> {
    ensure!(
        object.len() >= 60 && object.len() <= MAX_OBJECT,
        "Invalid cached COFF size"
    );
    ensure!(
        u16::from_le_bytes([object[0], object[1]]) == 0x8664,
        "Expected AMD64 COFF"
    );
    let sections = usize::from(u16::from_le_bytes([object[2], object[3]]));
    ensure!(
        sections > 0 && object.len() >= 20 + sections * 40,
        "Truncated COFF sections"
    );
    ensure!(
        object[16..18] == [0, 0],
        "Expected relocatable COFF, not PE"
    );
    Ok(())
}

fn encode(identity: &Identity, object: &[u8], log: &str) -> Result<Vec<u8>> {
    check_coff(object)?;
    let header = serde_json::to_vec(&Entry {
        identity: identity.clone(),
        object: files::digest_bytes(object),
        assembler_log: log.into(),
    })?;
    ensure!(
        header.len() <= MAX_METADATA,
        "Cache metadata exceeds budget"
    );
    let mut bytes = Vec::with_capacity(12 + header.len() + object.len());
    bytes.extend_from_slice(MAGIC);
    bytes.extend_from_slice(&(header.len() as u32).to_le_bytes());
    bytes.extend_from_slice(&header);
    bytes.extend_from_slice(object);
    Ok(bytes)
}

fn decode<'a>(bytes: &'a [u8], identity: &Identity) -> Result<(&'a [u8], String)> {
    ensure!(
        bytes.get(..8) == Some(MAGIC),
        "Invalid assembly cache header"
    );
    let length = u32::from_le_bytes(
        bytes
            .get(8..12)
            .context("Truncated assembly cache")?
            .try_into()?,
    ) as usize;
    ensure!(length <= MAX_METADATA, "Cache metadata exceeds budget");
    let entry: Entry = serde_json::from_slice(
        bytes
            .get(12..12 + length)
            .context("Truncated cache metadata")?,
    )?;
    ensure!(
        entry.identity == *identity,
        "Assembly cache identity differs"
    );
    let object = bytes
        .get(12 + length..)
        .context("Truncated cached object")?;
    check_coff(object)?;
    ensure!(
        files::digest_bytes(object) == entry.object,
        "Cached object digest differs"
    );
    Ok((object, entry.assembler_log))
}

fn restore(path: &Path, identity: &Identity, object: &Path, log: &Path) -> Result<()> {
    ensure!(
        fs::metadata(path)?.len() <= (MAX_METADATA + MAX_OBJECT + 12) as u64,
        "Assembly cache exceeds budget"
    );
    let bytes = fs::read(path)?;
    let (data, previous_log) = decode(&bytes, identity)?;
    files::write_atomic(object, data)?;
    files::write_atomic(
        log,
        format!("Verified MASM object cache hit.\n{previous_log}").as_bytes(),
    )?;
    ensure!(
        files::digest(object)? == files::digest_bytes(data),
        "Restored object digest differs"
    );
    Ok(())
}

fn publish(path: &Path, identity: &Identity, object: &[u8], log: &str) -> Result<()> {
    let bytes = encode(identity, object, log)?;
    let parent = path.parent().context("Cache entry has no parent")?;
    fs::create_dir_all(parent)?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    temporary.write_all(&bytes)?;
    temporary.as_file().sync_all()?;
    match temporary.persist_noclobber(path) {
        Ok(_) => Ok(()),
        Err(error) if path.exists() => {
            // Concurrent producers may publish different COFF timestamps for
            // the same assembly. Retain either fully verified object.
            if fs::read(path)
                .ok()
                .is_some_and(|data| decode(&data, identity).is_ok())
            {
                Ok(())
            } else {
                files::write_atomic(path, &bytes).with_context(|| error.to_string())
            }
        }
        Err(error) => Err(error.error.into()),
    }
}

fn destination(path: &Path) -> Result<std::path::PathBuf> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    if path.exists() {
        files::absolute(path)
    } else {
        Ok(files::absolute(parent)?.join(path.file_name().context("Missing output filename")?))
    }
}

/// The cache key deliberately excludes the Rust compiler and the source path:
/// freshly generated identical MASM with the same assembler/options has the
/// same relocatable semantics. Link/runtime/ABI checks are separate consumers.
pub fn assemble(
    source: &Path,
    object: &Path,
    log: &Path,
    cache: Option<&Path>,
) -> Result<AssemblyResult> {
    let source = files::absolute(source)?;
    let object_path = destination(object)?;
    let log_path = destination(log)?;
    let object = object_path.as_path();
    let log = log_path.as_path();
    ensure!(
        object != source && log != source,
        "Assembly output would overwrite source"
    );
    ensure!(object != log, "Object and assembler log paths must differ");
    let assembly = fs::read(&source)?;
    let mut command = tools::msvc_command("ml64.exe")?;
    // ML supplies implicit command line switches. No hidden switch may change
    // the result without changing the recorded identity.
    command.env_remove("ML");
    let assembler = files::absolute(Path::new(command.get_program()))?;
    let assembler_digest = files::digest(&assembler)?;
    let identity = Identity::new(&assembly, assembler_digest.sha256.clone());
    let eligible = self_contained(&assembly);
    let mut record = CacheRecord {
        schema: 1,
        status: if cache.is_none() {
            "disabled"
        } else if eligible {
            "miss"
        } else {
            "bypassed"
        }
        .into(),
        key: None,
        assembly_sha256: identity.assembly_sha256.clone(),
        assembler_sha256: identity.assembler_sha256.clone(),
        reason: (!eligible)
            .then(|| "External, environment, path or time sensitive assembly".into()),
    };
    let entry_path = if eligible {
        if let Some(root) = cache {
            let key = identity.key()?;
            let entry = root.join(&key[..2]).join(format!("{key}.cache"));
            record.key = Some(key);
            if entry.exists() {
                match restore(&entry, &identity, object, log) {
                    Ok(()) => {
                        ensure!(
                            fs::read(&source)? == assembly,
                            "Assembly source changed during cache restore"
                        );
                        ensure!(
                            files::digest(&assembler)? == assembler_digest,
                            "Assembler changed during cache restore"
                        );
                        record.status = "hit".into();
                        return Ok(AssemblyResult {
                            success: true,
                            exit_code: Some(0),
                            cache: record,
                        });
                    }
                    Err(error) => {
                        record.reason = Some(format!("Rejected cached object; rebuilt: {error:#}"))
                    }
                }
            }
            Some(entry)
        } else {
            None
        }
    } else {
        None
    };
    let parent = object
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    let temporary = tempfile::NamedTempFile::new_in(parent)?;
    let run = command
        .arg("/nologo")
        .arg("/c")
        .arg(format!("/Fo{}", temporary.path().display()))
        .arg(&source)
        .output()?;
    let assembler_log = [run.stdout.as_slice(), run.stderr.as_slice()].concat();
    files::write_atomic(log, &assembler_log)?;
    ensure!(
        fs::read(&source)? == assembly,
        "Assembly source changed during assembly"
    );
    ensure!(
        files::digest(&assembler)? == assembler_digest,
        "Assembler changed during assembly"
    );
    if run.status.success() {
        let bytes = fs::read(temporary.path())?;
        check_coff(&bytes)?;
        files::write_atomic(object, &bytes)?;
        if let Some(entry) = entry_path
            && let Err(error) = publish(
                &entry,
                &identity,
                &bytes,
                &String::from_utf8_lossy(&assembler_log),
            )
        {
            record.reason = Some(format!(
                "Assembly succeeded; cache publication failed: {error:#}"
            ));
        }
    }
    Ok(AssemblyResult {
        success: run.status.success(),
        exit_code: run.status.code(),
        cache: record,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn object() -> Vec<u8> {
        let mut data = vec![0; 60];
        data[..4].copy_from_slice(&[0x64, 0x86, 1, 0]);
        data
    }

    #[test]
    fn key_changes_with_source_tool_and_options() {
        let identity = Identity::new(b"mov eax,42", "tool-a".into());
        assert_ne!(
            identity.key().unwrap(),
            Identity::new(b"mov eax,43", "tool-a".into()).key().unwrap()
        );
        assert_ne!(
            identity.key().unwrap(),
            Identity::new(b"mov eax,42", "tool-b".into()).key().unwrap()
        );
        let mut changed = identity.clone();
        changed.options.push_str(":debug");
        assert_ne!(identity.key().unwrap(), changed.key().unwrap());
        assert_eq!(identity.key().unwrap(), identity.clone().key().unwrap());
    }

    #[test]
    fn corrupted_and_truncated_objects_do_not_hit() {
        let identity = Identity::new(b"source", "tool".into());
        let bytes = encode(&identity, &object(), "ok").unwrap();
        assert_eq!(decode(&bytes, &identity).unwrap().0, object());
        let mut corrupt = bytes.clone();
        *corrupt.last_mut().unwrap() ^= 1;
        assert!(decode(&corrupt, &identity).is_err());
        for length in [0, 8, 11, bytes.len() - 1] {
            assert!(decode(&bytes[..length], &identity).is_err());
        }
    }

    #[test]
    fn embedded_identity_must_match_key_request() {
        let identity = Identity::new(b"source", "tool".into());
        let bytes = encode(&identity, &object(), "ok").unwrap();
        let other = Identity::new(b"different", "tool".into());
        assert!(decode(&bytes, &other).is_err());
    }

    #[test]
    fn only_self_contained_source_is_reused() {
        assert!(self_contained(
            b"option casemap:none\n.code\nmov eax,42\nEND"
        ));
        for text in [
            "include other.inc",
            "INCLUDELIB os.lib",
            "db @Environ(X)",
            "db @FileName",
            "db @Time",
            "% expand",
            "incbin data.bin",
        ] {
            assert!(!self_contained(text.as_bytes()), "{text}");
        }
    }

    #[test]
    fn other_architectures_and_executables_are_rejected() {
        let mut data = object();
        data[0] = 0x4c;
        data[1] = 1;
        assert!(check_coff(&data).is_err());
        data = object();
        data[16] = 1;
        assert!(check_coff(&data).is_err());
        data = object();
        data[2] = 2;
        assert!(check_coff(&data).is_err());
    }

    #[test]
    fn restore_checks_object_and_publishes_independent_copy() {
        let root = tempfile::tempdir().unwrap();
        let identity = Identity::new(b"source", "tool".into());
        let entry = root.path().join("key.cache");
        files::write_atomic(&entry, &encode(&identity, &object(), "original").unwrap()).unwrap();
        let output = root.path().join("relocated/new.obj");
        let log = root.path().join("new.log");
        restore(&entry, &identity, &output, &log).unwrap();
        assert_eq!(fs::read(&output).unwrap(), object());
        files::write_atomic(&output, b"local mutation").unwrap();
        restore(&entry, &identity, &output, &log).unwrap();
        assert_eq!(fs::read(&output).unwrap(), object());
    }

    #[test]
    fn concurrent_publications_remain_complete() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("key.cache");
        let identity = Identity::new(b"source", "tool".into());
        std::thread::scope(|scope| {
            for _ in 0..8 {
                let path = &path;
                let identity = &identity;
                scope.spawn(move || publish(path, identity, &object(), "ok").unwrap());
            }
        });
        assert_eq!(
            decode(&fs::read(path).unwrap(), &identity).unwrap().0,
            object()
        );
    }
}
