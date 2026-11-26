use std::{
    cell::RefCell,
    collections::BTreeMap,
    fs::File,
    io::Read,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use zip::ZipArchive;

use crate::lock::InputLock;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ClassOrigin {
    pub loader: String,
    pub binary_name: String,
    pub source_id: String,
    pub jar_entry: String,
    pub java_class_major: u16,
    pub sha256: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub generated: Option<Box<GeneratedOrigin>>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GeneratedOrigin {
    pub generator: String,
    pub abi: u32,
    pub host_loader: String,
    pub host_class: String,
    pub host_source_id: String,
    pub host_sha256: String,
    pub site: u16,
}

#[derive(Debug, Serialize)]
pub struct ClassSet {
    pub input_fingerprint: String,
    pub classes: BTreeMap<String, ClassOrigin>,
    pub shadowed: Vec<ClassOrigin>,
}

/// Future mod providers must expose classes after their loader's transformations.
pub trait BytecodeProvider {
    fn snapshot(&self) -> Result<ClassSet>;
}

pub struct VanillaBytecodeProvider<'a> {
    pub inputs: &'a InputLock,
}

/// Translation-local archive indexes. Every read still verifies the locked
/// class digest; this caches ZIP directories, never unchecked class bytes.
#[derive(Default)]
pub(crate) struct ClassArchives {
    readers: RefCell<BTreeMap<PathBuf, ZipArchive<File>>>,
}
impl ClassArchives {
    pub(crate) fn read(&self, path: &Path, origin: &ClassOrigin) -> Result<Vec<u8>> {
        let mut readers = self.readers.borrow_mut();
        if let std::collections::btree_map::Entry::Vacant(entry) = readers.entry(path.to_path_buf())
        {
            entry.insert(ZipArchive::new(File::open(path)?)?);
        }
        origin.read_from(readers.get_mut(path).expect("Archive was inserted"))
    }
}

impl BytecodeProvider for VanillaBytecodeProvider<'_> {
    fn snapshot(&self) -> Result<ClassSet> {
        self.inputs.verify()?;
        let mut set = ClassSet {
            input_fingerprint: self.inputs.fingerprint.clone(),
            classes: BTreeMap::new(),
            shadowed: Vec::new(),
        };
        for id in &self.inputs.classpath {
            scan_jar(&self.inputs.file(id)?.path, id, &mut set)?;
        }
        ensure!(
            set.classes.contains_key(&self.inputs.main_class),
            "Entry point is missing from the prepared class set"
        );
        Ok(set)
    }
}

pub(crate) fn main_manifest_attributes(text: &str) -> BTreeMap<String, String> {
    let mut logical = Vec::<String>::new();
    for line in text.lines() {
        if line.is_empty() {
            break;
        }
        if let Some(continued) = line.strip_prefix(' ') {
            if let Some(previous) = logical.last_mut() {
                previous.push_str(continued);
            }
        } else {
            logical.push(line.to_owned());
        }
    }
    logical
        .iter()
        .filter_map(|line| line.split_once(": "))
        .map(|(key, value)| (key.to_ascii_lowercase(), value.to_owned()))
        .collect()
}

fn scan_jar(path: &Path, source_id: &str, set: &mut ClassSet) -> Result<()> {
    let mut archive = ZipArchive::new(File::open(path)?)?;
    let multi_release = match archive.by_name("META-INF/MANIFEST.MF") {
        Ok(entry) => {
            let mut manifest = String::new();
            entry.take(1024 * 1024).read_to_string(&mut manifest)?;
            main_manifest_attributes(&manifest)
                .get("multi-release")
                .is_some_and(|value| value.eq_ignore_ascii_case("true"))
        }
        Err(zip::result::ZipError::FileNotFound) => false,
        Err(error) => return Err(error.into()),
    };
    let mut selected: BTreeMap<String, (u32, String)> = BTreeMap::new();
    for index in 0..archive.len() {
        let entry = archive.by_index(index)?;
        let name = entry.name()?.into_owned();
        if !name.ends_with(".class") {
            continue;
        }
        let (release, class) = if let Some(versioned) = name.strip_prefix("META-INF/versions/") {
            if !multi_release {
                continue;
            }
            let Some((version, class)) = versioned.split_once('/') else {
                continue;
            };
            let Ok(release) = version.parse::<u32>() else {
                continue;
            };
            if !(9..=crate::JAVA_MAJOR).contains(&release) {
                continue;
            }
            (release, class)
        } else if name.starts_with("META-INF/") {
            continue;
        } else {
            (0, name.as_str())
        };
        if class == "module-info.class" {
            continue;
        }
        crate::files::safe_join(Path::new("class-set"), class)?;
        let binary_name = class.strip_suffix(".class").unwrap().replace('/', ".");
        if selected
            .get(&binary_name)
            .is_none_or(|(current, _)| release > *current)
        {
            selected.insert(binary_name, (release, name));
        }
    }
    for (binary_name, (_, entry_name)) in selected {
        let entry = archive.by_name(&entry_name)?;
        ensure!(
            entry.size() <= 16 * 1024 * 1024,
            "Oversized class: {binary_name}"
        );
        let mut bytes = Vec::new();
        entry.take(16 * 1024 * 1024 + 1).read_to_end(&mut bytes)?;
        ensure!(
            bytes.len() >= 8 && bytes[..4] == [0xca, 0xfe, 0xba, 0xbe],
            "Invalid class header: {binary_name}"
        );
        let minor = u16::from_be_bytes([bytes[4], bytes[5]]);
        let major = u16::from_be_bytes([bytes[6], bytes[7]]);
        ensure!(
            (45..=65).contains(&major) && minor != 65535,
            "Unsupported class version {major}.{minor}: {binary_name}"
        );
        let origin = ClassOrigin {
            generated: None,
            loader: "vanilla-application".into(),
            binary_name: binary_name.clone(),
            source_id: source_id.into(),
            jar_entry: entry_name,
            java_class_major: major,
            sha256: format!("{:x}", Sha256::digest(&bytes)),
        };
        if let std::collections::btree_map::Entry::Vacant(entry) = set.classes.entry(binary_name) {
            entry.insert(origin);
        } else {
            set.shadowed.push(origin);
        }
    }
    Ok(())
}

impl ClassOrigin {
    pub fn read(&self, inputs: &InputLock) -> Result<Vec<u8>> {
        ensure!(
            self.generated.is_none(),
            "Compiler-generated class is not a raw locked archive input"
        );
        let path = &inputs.file(&self.source_id)?.path;
        let mut archive = ZipArchive::new(File::open(path)?)?;
        self.read_from(&mut archive)
    }

    /// Reuse a worker-local archive index when compiling many classes in one JAR.
    pub fn read_from(&self, archive: &mut ZipArchive<File>) -> Result<Vec<u8>> {
        ensure!(
            self.generated.is_none(),
            "Compiler-generated class is not a raw archive input"
        );
        let mut bytes = Vec::new();
        archive
            .by_name(&self.jar_entry)
            .context("Class entry disappeared")?
            .take(16 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
        ensure!(
            format!("{:x}", Sha256::digest(&bytes)) == self.sha256,
            "Class bytes changed: {}",
            self.binary_name
        );
        Ok(bytes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use zip::{ZipWriter, write::SimpleFileOptions};

    fn jar(path: &Path, marker: u8) {
        let mut writer = ZipWriter::new(File::create(path).unwrap());
        writer
            .start_file("META-INF/MANIFEST.MF", SimpleFileOptions::default())
            .unwrap();
        writer
            .write_all(b"Manifest-Version: 1.0\r\nMulti-Release: tr\r\n ue\r\n\r\n")
            .unwrap();
        for (name, major) in [
            ("example/Test.class", 52),
            ("META-INF/versions/21/example/Test.class", 65),
            ("META-INF/versions/25/example/Test.class", 69),
        ] {
            writer
                .start_file(name, SimpleFileOptions::default())
                .unwrap();
            writer
                .write_all(&[0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, major, marker])
                .unwrap();
        }
        writer.finish().unwrap();
    }

    #[test]
    fn selects_java_21_multirelease_class_and_preserves_first_jar_precedence() {
        let directory = tempfile::tempdir().unwrap();
        let first = directory.path().join("first.jar");
        let second = directory.path().join("second.jar");
        jar(&first, 1);
        jar(&second, 2);
        let mut set = ClassSet {
            input_fingerprint: String::new(),
            classes: BTreeMap::new(),
            shadowed: Vec::new(),
        };
        scan_jar(&first, "first", &mut set).unwrap();
        scan_jar(&second, "second", &mut set).unwrap();
        assert_eq!(set.classes.len(), 1);
        let class = &set.classes["example.Test"];
        assert_eq!(class.source_id, "first");
        assert_eq!(class.java_class_major, 65);
        assert!(class.jar_entry.starts_with("META-INF/versions/21/"));
        assert_eq!(set.shadowed.len(), 1);
    }

    #[test]
    fn reused_archive_indexes_preserve_multirelease_selection_and_digest_checks() {
        let directory = tempfile::tempdir().unwrap();
        let first = directory.path().join("first.jar");
        let second = directory.path().join("second.jar");
        jar(&first, 1);
        jar(&second, 2);
        let mut a = ClassSet {
            input_fingerprint: String::new(),
            classes: BTreeMap::new(),
            shadowed: vec![],
        };
        let mut b = ClassSet {
            input_fingerprint: String::new(),
            classes: BTreeMap::new(),
            shadowed: vec![],
        };
        scan_jar(&first, "first", &mut a).unwrap();
        scan_jar(&second, "second", &mut b).unwrap();
        let one = &a.classes["example.Test"];
        let two = &b.classes["example.Test"];
        let archives = ClassArchives::default();
        for _ in 0..3 {
            let bytes = archives.read(&first, one).unwrap();
            assert_eq!(&bytes[6..], &[0, 65, 1]);
            assert_eq!(archives.read(&second, two).unwrap().last(), Some(&2));
        }
        assert_eq!(archives.readers.borrow().len(), 2);
        let mut wrong = one.clone();
        wrong.sha256.clone_from(&two.sha256);
        assert!(
            archives
                .read(&first, &wrong)
                .unwrap_err()
                .to_string()
                .contains("Class bytes changed")
        );
        wrong.jar_entry = "missing.class".into();
        assert!(archives.read(&first, &wrong).is_err());
    }
}
