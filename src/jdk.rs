//! Offline java.base input extraction. None of this module is a game runtime.
use crate::{
    bytecode::ClassOrigin,
    files,
    lock::InputLock,
    tools::{self, RuntimeFile},
};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::Command,
};

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct JdkBase {
    pub schema: u32,
    pub input_fingerprint: String,
    pub image: RuntimeFile,
    pub extractor: RuntimeFile,
    pub classes: BTreeMap<String, ClassOrigin>,
    pub fingerprint: String,
}

pub(crate) fn plain_file(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path)?;
    ensure!(
        !metadata.file_type().is_symlink(),
        "JDK cache contains a symbolic link"
    );
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        ensure!(
            metadata.file_attributes() & 0x400 == 0,
            "JDK cache contains a reparse point"
        );
    }
    Ok(())
}

pub(crate) fn plain_chain(path: &Path) -> Result<()> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    let mut parent = Some(absolute.as_path());
    while let Some(current) = parent {
        plain_file(current)?;
        parent = current.parent();
    }
    Ok(())
}

fn class_path(root: &Path, origin: &ClassOrigin) -> Result<PathBuf> {
    ensure!(
        origin.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "Invalid java.base class origin"
    );
    let expected = format!("java.base/{}.class", origin.binary_name.replace('.', "/"));
    ensure!(origin.jar_entry == expected, "JDK entry/name mismatch");
    plain_chain(root)?;
    let root = files::absolute(root)?;
    let path = files::safe_join(&root.join("image"), &expected)?;
    // Reject links in every traversed directory, including a moved cache root.
    plain_chain(&path)?;
    Ok(path)
}

impl JdkBase {
    fn identity(&self) -> Result<String> {
        let identity = serde_json::json!({"schema":self.schema,"input":self.input_fingerprint,"image":self.image.digest,"extractor":self.extractor.digest,"classes":self.classes});
        Ok(format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&identity)?)
        ))
    }
    pub fn read(manifest: &Path, inputs: &InputLock) -> Result<Self> {
        let base: Self = serde_json::from_slice(&fs::read(manifest)?)?;
        ensure!(
            base.schema == 1 && base.fingerprint == base.identity()?,
            "JDK cache identity mismatch"
        );
        ensure!(
            base.input_fingerprint == inputs.fingerprint,
            "JDK cache belongs to a different input lock"
        );
        ensure!(
            inputs
                .java
                .runtime_files
                .iter()
                .any(|file| file.path == base.image.path && file.digest == base.image.digest),
            "JDK image is not a locked runtime input"
        );
        ensure!(
            base.image.path == inputs.java.home.join("lib/modules"),
            "Unexpected JDK image"
        );
        ensure!(
            files::digest(&base.image.path)? == base.image.digest,
            "Locked JDK image changed"
        );
        ensure!(
            !base.classes.is_empty() && base.classes.len() <= 32768,
            "Invalid java.base class count"
        );
        for (name, origin) in &base.classes {
            ensure!(
                origin.generated.is_none(),
                "Raw JDK cache cannot declare compiler-generated classes"
            );
            ensure!(*name == origin.binary_name, "JDK class table name mismatch");
            files::validate_hash(&origin.sha256, 64)?;
        }
        Ok(base)
    }
    pub fn read_class(&self, manifest: &Path, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
        let origin = self
            .classes
            .get(&name.replace('/', "."))
            .with_context(|| format!("Class {name} is not in java.base"))?;
        let root = manifest
            .parent()
            .context("JDK cache manifest has no directory")?;
        let path = class_path(root, origin)?;
        ensure!(
            fs::metadata(&path)?.len() <= 16 * 1024 * 1024,
            "Oversized cached JDK class"
        );
        use std::io::Read;
        let mut bytes = Vec::new();
        fs::File::open(&path)?
            .take(16 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
        ensure!(
            bytes.len() <= 16 * 1024 * 1024 && files::digest_bytes(&bytes).sha256 == origin.sha256,
            "Cached JDK class changed: {name}"
        );
        Ok((bytes, origin.clone()))
    }
}

pub fn prepare(inputs: &InputLock, output: &Path) -> Result<JdkBase> {
    inputs.verify()?;
    let image = inputs
        .java
        .runtime_files
        .iter()
        .find(|file| file.path == inputs.java.home.join("lib/modules"))
        .context("Locked JDK image missing")?
        .clone();
    let extractor_path = inputs.java.home.join(if cfg!(windows) {
        "bin/jimage.exe"
    } else {
        "bin/jimage"
    });
    let extractor = RuntimeFile {
        path: files::absolute(&extractor_path)?,
        digest: files::digest(&extractor_path)?,
    };
    if output.exists() {
        plain_file(output)?;
        ensure!(
            output.is_dir() && fs::read_dir(output)?.next().is_none(),
            "JDK output must be a new or empty directory"
        );
    } else {
        fs::create_dir_all(output)?;
    }
    plain_chain(output)?;
    let output = files::absolute(output)?;
    plain_file(&output)?;
    let destination = output.join("image");
    fs::create_dir(&destination)?;
    let mut command = Command::new(&extractor.path);
    tools::clean_java_environment(&mut command);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let result = command
        .args(["extract", "--include", "glob:/java.base/**", "--dir"])
        .arg(&destination)
        .arg(&image.path)
        .output()
        .context("Cannot extract locked JDK java.base inputs")?;
    ensure!(
        result.status.success(),
        "jimage extraction failed: {}",
        String::from_utf8_lossy(&result.stderr)
    );
    ensure!(
        files::digest(&image.path)? == image.digest
            && files::digest(&extractor.path)? == extractor.digest,
        "JDK image/extractor changed during extraction"
    );
    let mut base = JdkBase {
        schema: 1,
        input_fingerprint: inputs.fingerprint.clone(),
        image,
        extractor,
        classes: BTreeMap::new(),
        fingerprint: String::new(),
    };
    let mut pending = vec![destination.clone()];
    let mut total = 0u64;
    let mut entries = 0usize;
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(directory)? {
            let entry = entry?;
            let path = entry.path();
            plain_file(&path)?;
            entries += 1;
            ensure!(entries <= 65536, "JDK extraction exceeds entry budget");
            if entry.file_type()?.is_dir() {
                pending.push(path);
                continue;
            }
            ensure!(entry.file_type()?.is_file(), "Non-regular JDK cache entry");
            total = total
                .checked_add(entry.metadata()?.len())
                .context("JDK byte budget overflow")?;
            ensure!(total <= 256 * 1024 * 1024, "JDK extraction exceeds 256 MiB");
            let relative = path
                .strip_prefix(&destination)?
                .to_string_lossy()
                .replace('\\', "/");
            let Some(class) = relative
                .strip_prefix("java.base/")
                .and_then(|name| name.strip_suffix(".class"))
            else {
                continue;
            };
            if class == "module-info" {
                continue;
            }
            ensure!(
                entry.metadata()?.len() <= 16 * 1024 * 1024,
                "Oversized JDK class"
            );
            let bytes = fs::read(&path)?;
            let parsed = crate::compiler::classfile::ClassFile::parse(&bytes)?;
            ensure!(parsed.name == class, "JDK class entry/name mismatch");
            let name = class.replace('/', ".");
            let origin = ClassOrigin {
                generated: None,
                loader: "bootstrap".into(),
                binary_name: name.clone(),
                source_id: "jdk:java.base".into(),
                jar_entry: relative,
                java_class_major: parsed.major,
                sha256: files::digest_bytes(&bytes).sha256,
            };
            ensure!(
                base.classes.insert(name, origin).is_none(),
                "Duplicate JDK class"
            );
        }
    }
    ensure!(
        base.classes.contains_key("java.lang.Object")
            && base.classes.contains_key("java.lang.String"),
        "java.base extraction is incomplete"
    );
    base.fingerprint = base.identity()?;
    files::write_atomic(
        &output.join("jdk-base.json"),
        &serde_json::to_vec_pretty(&base)?,
    )?;
    Ok(base)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cache_rejects_path_name_and_loader_confusion() {
        let origin = ClassOrigin {
            generated: None,
            loader: "bootstrap".into(),
            binary_name: "java.lang.String".into(),
            source_id: "jdk:java.base".into(),
            jar_entry: "../outside.class".into(),
            java_class_major: 65,
            sha256: String::new(),
        };
        assert!(class_path(Path::new("cache"), &origin).is_err());
        let mut other = origin;
        other.jar_entry = "java.base/java/lang/String.class".into();
        other.loader = "vanilla-application".into();
        assert!(class_path(Path::new("cache"), &other).is_err());
    }
}
