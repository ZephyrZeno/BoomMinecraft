//! Locked system class inputs and built-in package routing; compiler tooling only.
use crate::{
    boot_modules::{Loader, Snapshot},
    bytecode::ClassOrigin,
    compiler::classfile::ClassFile,
    files,
    jdk::{self, JdkBase},
    lock::InputLock,
    tools::{self, RuntimeFile},
};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs,
    io::Read,
    path::{Path, PathBuf},
    process::Command,
};

pub fn loader_name(loader: Loader) -> &'static str {
    match loader {
        Loader::Bootstrap => "bootstrap",
        Loader::Platform => "platform",
        Loader::Application => "vanilla-application",
    }
}
pub fn is_system(origin: &ClassOrigin) -> bool {
    origin.source_id.starts_with("jdk:")
}
fn valid_module(module: &str) -> bool {
    !module.is_empty()
        && module.split('.').all(|part| {
            !part.is_empty()
                && !part.as_bytes()[0].is_ascii_digit()
                && part.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
        })
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PackageOwner {
    pub module: String,
    pub loader: String,
}
pub type Packages = BTreeMap<String, PackageOwner>;

pub fn add_package(packages: &mut Packages, package: String, owner: PackageOwner) -> Result<()> {
    if let Some(previous) = packages.insert(package.clone(), owner.clone()) {
        ensure!(
            previous == owner,
            "Resolved system package has conflicting owners: {package}"
        );
    }
    Ok(())
}
pub fn inferred_packages<'a>(
    origins: impl IntoIterator<Item = &'a ClassOrigin>,
) -> Result<Packages> {
    let mut packages = Packages::new();
    for origin in origins {
        if let Some(module) = origin.source_id.strip_prefix("jdk:") {
            ensure!(valid_module(module), "Invalid system class module identity");
            let name = origin.binary_name.replace('.', "/");
            let (package, _) = name
                .rsplit_once('/')
                .context("System class has no package")?;
            add_package(
                &mut packages,
                package.into(),
                PackageOwner {
                    module: module.into(),
                    loader: origin.loader.clone(),
                },
            )?;
        }
    }
    Ok(packages)
}
/// The package-to-module table is consulted before parent delegation, including
/// delegation across built-in loaders. A missing class in an owned package must
/// not fall through to the application class path (BuiltinClassLoader semantics).
pub fn lookup<T>(
    packages: &Packages,
    initiator: &str,
    name: &str,
    mut find: impl FnMut(&str, &str) -> Option<T>,
) -> Option<T> {
    if let Some((package, _)) = name.rsplit_once('/')
        && let Some(owner) = packages.get(package)
    {
        return find(&owner.loader, name);
    }
    if let Some(found) = find("bootstrap", name) {
        return Some(found);
    }
    if matches!(initiator, "platform" | "vanilla-application")
        && let Some(found) = find("platform", name)
    {
        return Some(found);
    }
    find(initiator, name)
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SystemClasses {
    pub schema: u32,
    pub mode: String,
    pub input_fingerprint: String,
    pub image: RuntimeFile,
    pub extractor: RuntimeFile,
    pub module_snapshot: RuntimeFile,
    pub module_snapshot_fingerprint: String,
    pub packages: Packages,
    pub classes: BTreeMap<String, ClassOrigin>,
    pub fingerprint: String,
}
fn packages(snapshot: &Snapshot) -> Result<Packages> {
    let mut packages = Packages::new();
    for (name, resolved) in &snapshot.graph.resolved {
        for package in &snapshot.modules[name].descriptor.packages {
            add_package(
                &mut packages,
                package.clone(),
                PackageOwner {
                    module: name.clone(),
                    loader: loader_name(resolved.loader).into(),
                },
            )?;
        }
    }
    Ok(packages)
}
fn expected_entry(origin: &ClassOrigin, owners: &Packages) -> Result<String> {
    ensure!(
        origin.generated.is_none(),
        "Raw system class cannot be generated"
    );
    let module = origin
        .source_id
        .strip_prefix("jdk:")
        .context("Expected system class origin")?;
    ensure!(valid_module(module), "Invalid system class module");
    let name = origin.binary_name.replace('.', "/");
    let (package, leaf) = name
        .rsplit_once('/')
        .context("System class has no package")?;
    ensure!(!leaf.is_empty(), "Empty system class name");
    let owner = owners
        .get(package)
        .context("System class package is not resolved")?;
    ensure!(
        owner.module == module && owner.loader == origin.loader,
        "System class defining loader or module differs from resolution"
    );
    let expected = format!("{module}/{name}.class");
    ensure!(
        origin.jar_entry == expected,
        "System class entry/name mismatch"
    );
    Ok(expected)
}
fn system_path(root: &Path, origin: &ClassOrigin, owners: &Packages) -> Result<PathBuf> {
    let expected = expected_entry(origin, owners)?;
    jdk::plain_chain(root)?;
    let path = files::safe_join(&root.join("image"), &expected)?;
    jdk::plain_chain(&path)?;
    Ok(path)
}
impl SystemClasses {
    fn identity(&self) -> Result<String> {
        Ok(files::digest_bytes(&serde_json::to_vec(&(
            self.schema,
            &self.mode,
            &self.input_fingerprint,
            &self.image.digest,
            &self.extractor.digest,
            &self.module_snapshot.digest,
            &self.module_snapshot_fingerprint,
            &self.packages,
            &self.classes,
        ))?)
        .sha256)
    }
    pub fn read(manifest: &Path, inputs: &InputLock) -> Result<Self> {
        jdk::plain_chain(manifest)?;
        ensure!(
            fs::metadata(manifest)?.len() <= 64 * 1024 * 1024,
            "Oversized system class manifest"
        );
        let catalog: Self = serde_json::from_slice(&fs::read(manifest)?)?;
        ensure!(
            catalog.schema == 1
                && catalog.mode == "resolved_system_classes"
                && catalog.input_fingerprint == inputs.fingerprint
                && catalog.fingerprint == catalog.identity()?,
            "System class catalog identity mismatch"
        );
        ensure!(
            files::digest(&catalog.module_snapshot.path)? == catalog.module_snapshot.digest,
            "System module snapshot changed"
        );
        let snapshot = Snapshot::read(&catalog.module_snapshot.path, inputs)?;
        ensure!(
            snapshot.fingerprint == catalog.module_snapshot_fingerprint
                && snapshot.image.path == catalog.image.path
                && snapshot.image.digest == catalog.image.digest
                && snapshot.extractor.path == catalog.extractor.path
                && snapshot.extractor.digest == catalog.extractor.digest
                && packages(&snapshot)? == catalog.packages,
            "System class module metadata changed"
        );
        ensure!(
            !catalog.classes.is_empty() && catalog.classes.len() <= 65_536,
            "System class catalog exceeds budget"
        );
        for (name, origin) in &catalog.classes {
            ensure!(
                name == &origin.binary_name,
                "System class table name differs"
            );
            files::validate_hash(&origin.sha256, 64)?;
            expected_entry(origin, &catalog.packages)?;
        }
        ensure!(
            catalog.classes.contains_key("java.lang.Object")
                && catalog.classes.contains_key("java.lang.String"),
            "Incomplete system class catalog"
        );
        Ok(catalog)
    }
    pub fn read_class(&self, manifest: &Path, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
        let origin = self
            .classes
            .get(&name.replace('/', "."))
            .with_context(|| format!("Class {name} is not in resolved system inputs"))?;
        let root = manifest
            .parent()
            .context("System class manifest has no directory")?;
        let path = system_path(root, origin, &self.packages)?;
        ensure!(
            fs::metadata(&path)?.len() <= 16 * 1024 * 1024,
            "Oversized system class"
        );
        let mut bytes = Vec::new();
        fs::File::open(path)?
            .take(16 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
        ensure!(
            bytes.len() <= 16 * 1024 * 1024 && files::digest_bytes(&bytes).sha256 == origin.sha256,
            "Cached system class changed: {name}"
        );
        Ok((bytes, origin.clone()))
    }
}

/// Batch pipeline input provider. The legacy runtime linker stays java.base-only
/// until its separate VM layout and system bootstrap contracts are migrated.
pub enum ClassInputs {
    Base(JdkBase),
    System(SystemClasses),
}
impl ClassInputs {
    pub fn read(manifest: &Path, inputs: &InputLock) -> Result<Self> {
        let raw: serde_json::Value = serde_json::from_slice(&fs::read(manifest)?)?;
        match raw.get("mode").and_then(|v| v.as_str()) {
            Some("resolved_system_classes") => {
                Ok(Self::System(SystemClasses::read(manifest, inputs)?))
            }
            None => Ok(Self::Base(JdkBase::read(manifest, inputs)?)),
            _ => bail!("Unknown JDK class input provider"),
        }
    }
    pub fn classes(&self) -> &BTreeMap<String, ClassOrigin> {
        match self {
            Self::Base(v) => &v.classes,
            Self::System(v) => &v.classes,
        }
    }
    pub fn fingerprint(&self) -> &str {
        match self {
            Self::Base(v) => &v.fingerprint,
            Self::System(v) => &v.fingerprint,
        }
    }
    pub fn packages(&self) -> Result<Packages> {
        match self {
            Self::Base(v) => inferred_packages(v.classes.values()),
            Self::System(v) => Ok(v.packages.clone()),
        }
    }
    pub fn read_class(&self, manifest: &Path, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
        match self {
            Self::Base(v) => v.read_class(manifest, name),
            Self::System(v) => v.read_class(manifest, name),
        }
    }
}

pub fn prepare(inputs: &InputLock, module_manifest: &Path, output: &Path) -> Result<SystemClasses> {
    inputs.verify()?;
    let snapshot = Snapshot::read(module_manifest, inputs)?;
    if output.exists() {
        ensure!(
            output.is_dir() && fs::read_dir(output)?.next().is_none(),
            "System class output must be new or empty"
        );
    } else {
        fs::create_dir_all(output)?;
    }
    jdk::plain_chain(output)?;
    let output = files::absolute(output)?;
    let image_root = output.join("image");
    fs::create_dir(&image_root)?;
    let include = snapshot
        .graph
        .resolved
        .keys()
        .map(|name| format!("glob:/{name}/**"))
        .collect::<Vec<_>>()
        .join(",");
    eprintln!(
        "Extracting {} resolved system modules",
        snapshot.graph.resolved.len()
    );
    let mut command = Command::new(&snapshot.extractor.path);
    tools::clean_java_environment(&mut command);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let run = command
        .args(["extract", "--include", &include, "--dir"])
        .arg(&image_root)
        .arg(&snapshot.image.path)
        .output()?;
    ensure!(
        run.status.success(),
        "System class extraction failed: {}",
        String::from_utf8_lossy(&run.stderr)
    );
    ensure!(
        files::digest(&snapshot.image.path)? == snapshot.image.digest
            && files::digest(&snapshot.extractor.path)? == snapshot.extractor.digest,
        "Locked JDK inputs changed during extraction"
    );
    let owners = packages(&snapshot)?;
    eprintln!("Indexing source-verified system class declarations");
    let mut classes = BTreeMap::new();
    let mut pending = vec![image_root.clone()];
    let (mut total, mut entries) = (0u64, 0usize);
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(directory)? {
            let entry = entry?;
            let path = entry.path();
            // The new root and each directory entry are checked once while
            // walking. Class reads retain full path-chain and digest checks.
            jdk::plain_file(&path)?;
            entries += 1;
            ensure!(
                entries <= 200_000,
                "System class extraction exceeds entry budget"
            );
            if entry.file_type()?.is_dir() {
                pending.push(path);
                continue;
            }
            ensure!(
                entry.file_type()?.is_file(),
                "Non-regular system class input"
            );
            total = total
                .checked_add(entry.metadata()?.len())
                .context("System class byte budget overflow")?;
            ensure!(
                total <= 512 * 1024 * 1024,
                "System class extraction exceeds 512 MiB"
            );
            let relative = path
                .strip_prefix(&image_root)?
                .to_string_lossy()
                .replace('\\', "/");
            let (module, name) = relative
                .split_once('/')
                .context("Invalid system image entry")?;
            let resolved = snapshot
                .graph
                .resolved
                .get(module)
                .context("Unresolved module in extraction")?;
            let Some(class) = name.strip_suffix(".class") else {
                continue;
            };
            if class == "module-info" {
                continue;
            }
            ensure!(
                entry.metadata()?.len() <= 16 * 1024 * 1024,
                "Oversized system class"
            );
            let bytes = fs::read(&path)?;
            let parsed = ClassFile::parse(&bytes)?;
            ensure!(parsed.name == class, "System class entry/name differs");
            let binary_name = class.replace('/', ".");
            let origin = ClassOrigin {
                loader: loader_name(resolved.loader).into(),
                binary_name: binary_name.clone(),
                source_id: format!("jdk:{module}"),
                jar_entry: relative,
                java_class_major: parsed.major,
                sha256: files::digest_bytes(&bytes).sha256,
                generated: None,
            };
            expected_entry(&origin, &owners)?;
            ensure!(
                classes.insert(binary_name, origin).is_none(),
                "Duplicate resolved system class"
            );
            ensure!(classes.len() <= 65_536, "Too many system classes");
            if classes.len().is_multiple_of(4096) {
                eprintln!("System classes indexed: {}", classes.len());
            }
        }
    }
    let mut catalog = SystemClasses {
        schema: 1,
        mode: "resolved_system_classes".into(),
        input_fingerprint: inputs.fingerprint.clone(),
        image: snapshot.image,
        extractor: snapshot.extractor,
        module_snapshot: RuntimeFile {
            path: files::absolute(module_manifest)?,
            digest: files::digest(module_manifest)?,
        },
        module_snapshot_fingerprint: snapshot.fingerprint,
        packages: owners,
        classes,
        fingerprint: String::new(),
    };
    catalog.fingerprint = catalog.identity()?;
    files::write_atomic(
        &output.join("jdk-classes.json"),
        &serde_json::to_vec_pretty(&catalog)?,
    )?;
    Ok(catalog)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn package_routing_preserves_defining_loader_and_blocks_classpath_fallback() {
        let packages = Packages::from([(
            "p".into(),
            PackageOwner {
                module: "java.example".into(),
                loader: "platform".into(),
            },
        )]);
        let index = BTreeMap::from([
            (("platform", "p/C"), 1),
            (("vanilla-application", "p/C"), 2),
            (("vanilla-application", "p/Missing"), 3),
            (("vanilla-application", "q/App"), 4),
            (("bootstrap", "java/lang/Object"), 5),
        ]);
        let find = |loader: &str, name: &str| index.get(&(loader, name)).copied();
        assert_eq!(lookup(&packages, "bootstrap", "p/C", find), Some(1));
        assert_eq!(
            lookup(&packages, "vanilla-application", "p/C", find),
            Some(1)
        );
        assert_eq!(
            lookup(&packages, "vanilla-application", "p/Missing", find),
            None
        );
        assert_eq!(lookup(&packages, "platform", "q/App", find), None);
        assert_eq!(
            lookup(&packages, "vanilla-application", "q/App", find),
            Some(4)
        );
        assert_eq!(
            lookup(&packages, "platform", "java/lang/Object", find),
            Some(5)
        );
    }
    #[test]
    fn conflicting_resolved_packages_are_rejected() {
        let mut packages = Packages::new();
        let owner = PackageOwner {
            module: "java.example".into(),
            loader: "platform".into(),
        };
        add_package(&mut packages, "p".into(), owner.clone()).unwrap();
        add_package(&mut packages, "p".into(), owner).unwrap();
        assert!(
            add_package(
                &mut packages,
                "p".into(),
                PackageOwner {
                    module: "java.other".into(),
                    loader: "platform".into()
                }
            )
            .is_err()
        );
    }
    #[test]
    fn system_cache_rejects_wrong_module_loader_and_entry_path() {
        let packages = Packages::from([(
            "p".into(),
            PackageOwner {
                module: "java.example".into(),
                loader: "platform".into(),
            },
        )]);
        let mut origin = ClassOrigin {
            loader: "bootstrap".into(),
            binary_name: "p.C".into(),
            source_id: "jdk:java.example".into(),
            jar_entry: "java.example/p/C.class".into(),
            java_class_major: 65,
            sha256: "a".repeat(64),
            generated: None,
        };
        assert!(system_path(Path::new("cache"), &origin, &packages).is_err());
        origin.loader = "platform".into();
        origin.source_id = "jdk:java.other".into();
        assert!(system_path(Path::new("cache"), &origin, &packages).is_err());
        origin.source_id = "jdk:java.example".into();
        origin.jar_entry = "../outside.class".into();
        assert!(system_path(Path::new("cache"), &origin, &packages).is_err());
    }
}
