use std::{
    fs,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result, ensure};
use clap::ValueEnum;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::{
    files::{self, FileDigest},
    metadata::{Target, VersionMetadata},
    tools::JavaIdentity,
};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, ValueEnum, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Side {
    Client,
    Server,
}

impl Side {
    pub fn name(self) -> &'static str {
        match self {
            Self::Client => "client",
            Self::Server => "server",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LockedFile {
    pub id: String,
    pub role: String,
    pub path: PathBuf,
    pub digest: FileDigest,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InputLock {
    pub schema: u32,
    pub tool_version: String,
    pub game_version: String,
    pub side: Side,
    pub target: Target,
    pub java: JavaIdentity,
    pub files: Vec<LockedFile>,
    pub classpath: Vec<String>,
    pub main_class: String,
    pub assets_root: Option<PathBuf>,
    pub natives_directory: Option<PathBuf>,
    pub fingerprint: String,
}

impl InputLock {
    pub fn add(&mut self, id: impl Into<String>, role: &str, path: &Path) -> Result<()> {
        let id = id.into();
        ensure!(
            !self.files.iter().any(|file| file.id == id),
            "Duplicate input id: {id}"
        );
        self.files.push(LockedFile {
            id,
            role: role.into(),
            path: files::absolute(path)?,
            digest: files::digest(path)?,
        });
        Ok(())
    }

    pub fn file(&self, id: &str) -> Result<&LockedFile> {
        self.files
            .iter()
            .find(|file| file.id == id)
            .with_context(|| format!("Missing locked input: {id}"))
    }

    pub fn classpath_paths(&self) -> Result<Vec<PathBuf>> {
        self.classpath
            .iter()
            .map(|id| Ok(self.file(id)?.path.clone()))
            .collect()
    }

    pub fn identity(&self) -> Result<String> {
        // Content identity deliberately excludes absolute paths and timestamps.
        let mut files: Vec<_> = self
            .files
            .iter()
            .map(|file| (&file.id, &file.role, &file.digest))
            .collect();
        files.sort_by(|a, b| a.0.cmp(b.0));
        let runtime: Vec<_> = self
            .java
            .runtime_files
            .iter()
            .map(|file| &file.digest)
            .collect();
        let identity = serde_json::json!({"schema":self.schema,"tool":self.tool_version,"game":self.game_version,"side":self.side,"target":self.target,"java_major":self.java.major,"java_version":self.java.version,"java_runtime":runtime,"files":files,"classpath":self.classpath,"main_class":self.main_class});
        Ok(format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&identity)?)
        ))
    }

    pub fn save(&mut self, destination: &Path) -> Result<()> {
        self.files.sort_by(|a, b| a.id.cmp(&b.id));
        self.fingerprint = self.identity()?;
        files::write_atomic(destination, &serde_json::to_vec_pretty(self)?)
    }

    pub fn read(path: &Path) -> Result<Self> {
        let lock: Self = serde_json::from_slice(
            &fs::read(path).with_context(|| format!("Cannot read lock {}", path.display()))?,
        )?;
        ensure!(lock.schema == 1, "Unsupported lock schema: {}", lock.schema);
        ensure!(
            lock.game_version == crate::GAME_VERSION && lock.java.major == crate::JAVA_MAJOR,
            "Lock targets an unsupported game or Java version"
        );
        ensure!(
            lock.target.os == "windows" && lock.target.arch == "x86_64",
            "Only windows-x64 locks are supported"
        );
        ensure!(
            lock.fingerprint == lock.identity()?,
            "Lock identity was modified; prepare inputs again"
        );
        ensure!(
            lock.files
                .iter()
                .map(|f| &f.id)
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                == lock.files.len(),
            "Duplicate locked input ids"
        );
        for id in &lock.classpath {
            lock.file(id)?;
        }
        Ok(lock)
    }

    pub fn verify(&self) -> Result<()> {
        ensure!(
            self.fingerprint == self.identity()?,
            "Lock identity mismatch"
        );
        ensure!(
            self.java
                .runtime_files
                .iter()
                .any(|file| file.path == self.java.executable),
            "Selected Java executable is not a locked runtime input"
        );
        for file in &self.files {
            ensure!(
                files::digest(&file.path)? == file.digest,
                "Locked input changed: {} ({})",
                file.id,
                file.path.display()
            );
        }
        for file in &self.java.runtime_files {
            ensure!(
                files::digest(&file.path)? == file.digest,
                "Java runtime changed: {}",
                file.path.display()
            );
        }
        let metadata = self.file("version-metadata")?;
        ensure!(
            metadata.digest.sha1 == crate::METADATA_SHA1,
            "Lock does not use pinned vanilla metadata"
        );
        let version: VersionMetadata = serde_json::from_slice(&fs::read(&metadata.path)?)?;
        version.validate()?;
        let expected_main = match self.side {
            Side::Client => "net.minecraft.client.main.Main",
            Side::Server => "net.minecraft.server.Main",
        };
        ensure!(
            self.main_class == expected_main,
            "Unexpected vanilla entry point"
        );
        let game_id = match self.side {
            Side::Client => "client-game",
            Side::Server => "server-bundle",
        };
        let expected_game = version
            .downloads
            .get(self.side.name())
            .context("Missing official game descriptor")?;
        let game = self.file(game_id)?;
        ensure!(
            game.digest.sha1 == expected_game.sha1 && game.digest.size == expected_game.size,
            "Game input differs from official 1.21.1 metadata"
        );
        if self.side == Side::Client {
            let assets = self
                .assets_root
                .as_ref()
                .context("Missing locked assets root")?;
            ensure!(
                self.file("asset-index")?.path
                    == assets
                        .join("indexes")
                        .join(format!("{}.json", version.asset_index.id)),
                "Asset index is outside the locked assets root"
            );
            let natives = self
                .natives_directory
                .as_ref()
                .context("Missing locked natives directory")?;
            for file in &self.files {
                if file.role == "asset" {
                    let hash = &file.digest.sha1;
                    files::validate_hash(hash, 40)?;
                    ensure!(
                        file.path == assets.join("objects").join(&hash[..2]).join(hash),
                        "Asset path differs from locked root"
                    );
                }
                if file.role == "native" {
                    ensure!(
                        file.path.parent() == Some(natives.as_path()),
                        "Native file is outside the locked native directory"
                    );
                }
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unknown_schemas_before_execution() {
        let file = tempfile::NamedTempFile::new().unwrap();
        fs::write(file.path(), b"{}").unwrap();
        assert!(InputLock::read(file.path()).is_err());
    }
}
