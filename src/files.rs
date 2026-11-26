use std::{
    fs::{self, File},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
};

use anyhow::{Context, Result, bail, ensure};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use sha1::{Digest, Sha1};
use sha2::Sha256;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct FileDigest {
    pub size: u64,
    pub sha1: String,
    pub sha256: String,
}

pub fn digest(path: &Path) -> Result<FileDigest> {
    let mut file = File::open(path).with_context(|| format!("Cannot read {}", path.display()))?;
    let mut sha1 = Sha1::new();
    let mut sha256 = Sha256::new();
    let mut size = 0;
    let mut buffer = [0_u8; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        sha1.update(&buffer[..count]);
        sha256.update(&buffer[..count]);
        size += count as u64;
    }
    Ok(FileDigest {
        size,
        sha1: format!("{:x}", sha1.finalize()),
        sha256: format!("{:x}", sha256.finalize()),
    })
}

pub fn digest_bytes(bytes: &[u8]) -> FileDigest {
    FileDigest {
        size: bytes.len() as u64,
        sha1: format!("{:x}", Sha1::digest(bytes)),
        sha256: format!("{:x}", Sha256::digest(bytes)),
    }
}

pub fn verify_expected(path: &Path, sha1: &str, size: Option<u64>) -> Result<FileDigest> {
    validate_hash(sha1, 40)?;
    let actual = digest(path)?;
    ensure!(
        actual.sha1.eq_ignore_ascii_case(sha1),
        "SHA-1 mismatch for {}: expected {}, got {}",
        path.display(),
        sha1,
        actual.sha1
    );
    if let Some(size) = size {
        ensure!(actual.size == size, "Size mismatch for {}", path.display());
    }
    Ok(actual)
}

pub fn validate_hash(value: &str, length: usize) -> Result<()> {
    ensure!(
        value.len() == length && value.bytes().all(|c| c.is_ascii_hexdigit()),
        "Invalid {length}-character digest"
    );
    Ok(())
}

/// Read the PE COFF machine field; this is not a full executable validator.
pub fn pe_machine(bytes: &[u8]) -> Result<u16> {
    ensure!(
        bytes.get(..2) == Some(b"MZ"),
        "Native DLL has no DOS header"
    );
    let offset = bytes.get(0x3c..0x40).context("Truncated DOS header")?;
    let offset = u32::from_le_bytes(offset.try_into()?) as usize;
    let end = offset.checked_add(6).context("PE offset overflow")?;
    let pe = bytes.get(offset..end).context("PE header is outside DLL")?;
    ensure!(&pe[..4] == b"PE\0\0", "Invalid PE signature");
    Ok(u16::from_le_bytes([pe[4], pe[5]]))
}

pub fn safe_join(root: &Path, relative: &str) -> Result<PathBuf> {
    ensure!(
        !relative.is_empty() && !relative.contains(['\\', ':', '\0']),
        "Unsafe relative path: {relative:?}"
    );
    let path = Path::new(relative);
    ensure!(
        path.components().all(|c| matches!(c, Component::Normal(_))),
        "Unsafe relative path: {relative:?}"
    );
    Ok(root.join(path))
}

pub fn absolute(path: &Path) -> Result<PathBuf> {
    let path =
        fs::canonicalize(path).with_context(|| format!("Cannot resolve {}", path.display()))?;
    // Java does not consistently accept Windows verbatim path prefixes in classpaths.
    #[cfg(windows)]
    {
        let text = path.to_string_lossy();
        if let Some(rest) = text.strip_prefix(r"\\?\UNC\") {
            return Ok(PathBuf::from(format!(r"\\{rest}")));
        }
        if let Some(rest) = text.strip_prefix(r"\\?\") {
            return Ok(PathBuf::from(rest));
        }
    }
    Ok(path)
}

pub fn write_atomic(path: &Path, content: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    temporary.write_all(content)?;
    temporary.as_file().sync_all()?;
    temporary
        .persist(path)
        .map_err(|e| e.error)
        .with_context(|| format!("Cannot publish {}", path.display()))?;
    Ok(())
}

pub fn fetch(
    client: &Client,
    url: &str,
    destination: &Path,
    sha1: &str,
    size: Option<u64>,
) -> Result<PathBuf> {
    if destination.exists() {
        verify_expected(destination, sha1, size)
            .context("Cached file is invalid; remove that file and retry")?;
        return absolute(destination);
    }
    ensure!(
        url.starts_with("https://"),
        "Only HTTPS downloads are supported"
    );
    validate_hash(sha1, 40)?;
    let parent = destination
        .parent()
        .context("Download destination has no parent")?;
    fs::create_dir_all(parent)?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    let response = client
        .get(url)
        .send()
        .with_context(|| format!("Download failed: {url}"))?
        .error_for_status()?;
    let limit = size.unwrap_or(4 * 1024 * 1024);
    let copied = std::io::copy(&mut response.take(limit + 1), &mut temporary)?;
    ensure!(copied <= limit, "Download exceeds expected size: {url}");
    temporary.flush()?;
    verify_expected(temporary.path(), sha1, size)?;
    temporary.as_file().sync_all()?;
    // A concurrent preparer may have published the same content while this request ran.
    if destination.exists() {
        verify_expected(destination, sha1, size)?;
    } else {
        match temporary.persist_noclobber(destination) {
            Ok(_) => (),
            Err(error) if destination.exists() => {
                verify_expected(destination, sha1, size).with_context(|| error.to_string())?;
            }
            Err(error) => bail!("Cannot publish download: {error}"),
        }
    }
    absolute(destination)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_architecture_is_read_from_bounded_pe_header() {
        let mut bytes = vec![0; 70];
        bytes[..2].copy_from_slice(b"MZ");
        bytes[0x3c..0x40].copy_from_slice(&64u32.to_le_bytes());
        bytes[64..68].copy_from_slice(b"PE\0\0");
        for machine in [0x8664u16, 0xaa64, 0x14c] {
            bytes[68..70].copy_from_slice(&machine.to_le_bytes());
            assert_eq!(pe_machine(&bytes).unwrap(), machine);
        }
        bytes[0x3c..0x40].copy_from_slice(&u32::MAX.to_le_bytes());
        assert!(pe_machine(&bytes).is_err());
        assert!(pe_machine(b"MZ").is_err());
    }

    #[test]
    fn rejects_cross_platform_path_traversal() {
        for name in [
            "../escape",
            "/absolute",
            "C:/escape",
            "a\\..\\escape",
            "a/../../escape",
            "",
        ] {
            assert!(safe_join(Path::new("cache"), name).is_err(), "{name}");
        }
        assert_eq!(
            safe_join(Path::new("cache"), "org/test/file.jar").unwrap(),
            Path::new("cache/org/test/file.jar")
        );
    }

    #[test]
    fn detects_corrupted_input_and_atomic_replacement() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("input");
        write_atomic(&path, b"abc").unwrap();
        verify_expected(&path, "a9993e364706816aba3e25717850c26c9cd0d89d", Some(3)).unwrap();
        write_atomic(&path, b"changed").unwrap();
        assert!(
            verify_expected(&path, "a9993e364706816aba3e25717850c26c9cd0d89d", Some(3)).is_err()
        );
    }
}
