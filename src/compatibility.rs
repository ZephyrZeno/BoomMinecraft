use std::{
    fs::{self, File},
    io::{Read, Write},
    path::Path,
    process::Command,
};

use anyhow::{Context, Result, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};
use zip::{ZipArchive, ZipWriter, write::SimpleFileOptions};

use crate::{files, lock::InputLock, tools};

const TARGET_CLASS: &str = "org/apache/logging/log4j/util/ServiceLoaderUtil.class";
const TARGET_SHA256: &str = "f17a1b460774ba05b90fb62651f2e220ede4873968ba3a2c298695d5ac0f64d1";
const SOURCE: &str = include_str!("../java/compat/dev/boom/nativeimage/Log4jServices.java");
const PROBE: &str = include_str!("../java/tests/dev/boom/nativeimage/Log4jServicesProbe.java");
const RESOURCES: &str = include_str!("../native-config/1.21.1/resource-config.json");

#[derive(Debug, Serialize)]
pub struct CompatibilityReceipt {
    pub profile: &'static str,
    pub target_class_sha256: String,
    pub source_sha256: String,
    pub resources_sha256: String,
    pub artifact: files::FileDigest,
    pub jvm_probe_cases_per_runtime: usize,
}

fn verify_target(bytes: &[u8]) -> Result<String> {
    let actual = format!("{:x}", Sha256::digest(bytes));
    ensure!(
        actual == TARGET_SHA256,
        "Log4j compatibility target changed: expected {TARGET_SHA256}, got {actual}; refusing to apply the adapter"
    );
    Ok(actual)
}

/// Compile and check a native-only adapter without modifying any input JAR.
pub fn prepare(
    lock: &InputLock,
    native_image: &Path,
    artifact: &Path,
) -> Result<CompatibilityReceipt> {
    let target = lock
        .files
        .iter()
        .find(|file| {
            file.id
                .ends_with("org/apache/logging/log4j/log4j-api/2.22.1/log4j-api-2.22.1.jar")
        })
        .context("Pinned Log4j 2.22.1 input is missing")?;
    let mut archive = ZipArchive::new(File::open(&target.path)?)?;
    let mut bytes = Vec::new();
    archive
        .by_name(TARGET_CLASS)?
        .take(1024 * 1024)
        .read_to_end(&mut bytes)?;
    let target_class_sha256 = verify_target(&bytes)?;
    let home = native_image
        .parent()
        .and_then(Path::parent)
        .context("Cannot locate GraalVM JDK")?;
    let javac = home.join("bin/javac.exe");
    let svm = home.join("lib/svm/builder/svm.jar");
    ensure!(
        javac.is_file() && svm.is_file(),
        "GraalVM compiler or substitution annotations are missing"
    );
    let root = artifact
        .parent()
        .context("Compatibility JAR has no parent")?;
    fs::create_dir_all(root)?;
    files::write_atomic(
        &root.join("metadata/resource-config.json"),
        RESOURCES.as_bytes(),
    )?;
    let sources = root.join("sources/dev/boom/nativeimage");
    fs::create_dir_all(&sources)?;
    let source = sources.join("Log4jServices.java");
    let probe = sources.join("Log4jServicesProbe.java");
    files::write_atomic(&source, SOURCE.as_bytes())?;
    files::write_atomic(&probe, PROBE.as_bytes())?;
    // Fresh classes prevent stale helper classes entering a new artifact.
    let classes = tempfile::tempdir_in(root)?;
    let mut cp = lock.classpath_paths()?;
    cp.push(svm.clone());
    let cp = std::env::join_paths(&cp)?;
    let mut compiler = Command::new(&javac);
    tools::clean_java_environment(&mut compiler);
    let output = compiler
        .args([
            "-J-Duser.language=en",
            "-J-Duser.country=US",
            "-proc:none",
            "-encoding",
            "UTF-8",
            "-source",
            "21",
            "-target",
            "21",
            "--add-modules",
            "org.graalvm.nativeimage",
            "-cp",
        ])
        .arg(&cp)
        .arg("-d")
        .arg(classes.path())
        .arg(&source)
        .arg(&probe)
        .output()?;
    ensure!(
        output.status.success(),
        "Compatibility compilation failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let services = classes.path().join("META-INF/services");
    fs::create_dir_all(&services)?;
    fs::write(services.join("dev.boom.nativeimage.Log4jServicesProbe$Greeting"),b"dev.boom.nativeimage.Log4jServicesProbe$First\ndev.boom.nativeimage.Log4jServicesProbe$Second\n")?;
    let mut probe_cp = vec![classes.path().to_owned()];
    probe_cp.extend(lock.classpath_paths()?);
    probe_cp.push(svm);
    let probe_cp = std::env::join_paths(probe_cp)?;
    for java in [&lock.java.executable, &home.join("bin/java.exe")] {
        let mut command = Command::new(java);
        tools::clean_java_environment(&mut command);
        let output = command
            .arg("-cp")
            .arg(&probe_cp)
            .arg("dev.boom.nativeimage.Log4jServicesProbe")
            .output()?;
        ensure!(
            output.status.success(),
            "Service discovery differential probe failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        let result: serde_json::Value = serde_json::from_slice(&output.stdout)
            .context("Invalid service discovery probe output")?;
        ensure!(
            result["passed"] == true && result["service_discovery_cases"] == 5,
            "Service discovery probe did not pass all cases"
        );
    }
    let mut temporary = tempfile::NamedTempFile::new_in(root)?;
    {
        let mut jar = ZipWriter::new(temporary.as_file_mut());
        jar.start_file(
            "dev/boom/nativeimage/Log4jServices.class",
            SimpleFileOptions::default(),
        )?;
        jar.write_all(&fs::read(
            classes
                .path()
                .join("dev/boom/nativeimage/Log4jServices.class"),
        )?)?;
        jar.finish()?;
    }
    temporary.flush()?;
    temporary.persist(artifact).map_err(|error| error.error)?;
    let receipt = CompatibilityReceipt {
        profile: "vanilla-1.21.1-log4j-2.22.1",
        target_class_sha256,
        source_sha256: format!("{:x}", Sha256::digest(SOURCE.as_bytes())),
        resources_sha256: format!("{:x}", Sha256::digest(RESOURCES.as_bytes())),
        artifact: files::digest(artifact)?,
        jvm_probe_cases_per_runtime: 5,
    };
    files::write_atomic(
        &root.join("compatibility.json"),
        &serde_json::to_vec_pretty(&receipt)?,
    )?;
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn changed_class_cannot_silently_receive_vanilla_adapter() {
        assert!(verify_target(b"a different Log4j build").is_err());
    }
}
