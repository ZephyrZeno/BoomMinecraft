use std::{
    collections::BTreeMap,
    env,
    path::{Path, PathBuf},
    process::Command,
};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

use crate::files::{self, FileDigest};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeFile {
    pub path: PathBuf,
    pub digest: FileDigest,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct JavaIdentity {
    pub executable: PathBuf,
    pub home: PathBuf,
    pub major: u32,
    pub version: String,
    pub runtime_files: Vec<RuntimeFile>,
}

pub fn clean_java_environment(command: &mut Command) {
    for key in [
        "JAVA_TOOL_OPTIONS",
        "_JAVA_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "CLASSPATH",
    ] {
        command.env_remove(key);
    }
}

pub fn find_tool(name: &str) -> Option<PathBuf> {
    let extensions: &[&str] = if cfg!(windows) {
        &[".exe", ".cmd", ".bat", ""]
    } else {
        &[""]
    };
    for directory in env::split_paths(&env::var_os("PATH").unwrap_or_default()) {
        for extension in extensions {
            let candidate = directory.join(format!("{name}{extension}"));
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

pub fn find_java(explicit: Option<&Path>) -> Result<PathBuf> {
    if let Some(path) = explicit {
        return files::absolute(path);
    }
    if let Some(home) = env::var_os("JAVA_HOME") {
        let candidate =
            PathBuf::from(home)
                .join("bin")
                .join(if cfg!(windows) { "java.exe" } else { "java" });
        if candidate.is_file() {
            return files::absolute(&candidate);
        }
    }
    if let Some(path) = configured_tool("java")? {
        return files::absolute(&path);
    }
    if let Some(path) = find_tool("java") {
        return files::absolute(&path);
    }
    if let Some(appdata) = env::var_os("APPDATA") {
        for suffix in [
            ".minecraft/runtime/java-runtime-delta/bin/java.exe",
            ".minecraft/runtime/java-runtime-delta/windows-x64/java-runtime-delta/bin/java.exe",
        ] {
            let candidate = PathBuf::from(&appdata).join(suffix);
            if candidate.is_file() {
                return files::absolute(&candidate);
            }
        }
    }
    anyhow::bail!("Java 21 was not found. Pass --java <path-to-java> or set JAVA_HOME.")
}

pub fn probe_java(path: &Path) -> Result<JavaIdentity> {
    let executable = files::absolute(path)?;
    let mut command = Command::new(&executable);
    clean_java_environment(&mut command);
    let output = command
        .args(["-XshowSettings:properties", "-version"])
        .output()
        .context("Cannot execute Java")?;
    ensure!(output.status.success(), "Java version probe failed");
    let text = format!(
        "{}\n{}",
        String::from_utf8_lossy(&output.stderr),
        String::from_utf8_lossy(&output.stdout)
    );
    let property = |name: &str| -> Result<String> {
        text.lines()
            .find_map(|line| {
                line.trim()
                    .strip_prefix(&format!("{name} = "))
                    .map(str::to_owned)
            })
            .with_context(|| format!("Missing Java property: {name}"))
    };
    let version = property("java.version")?;
    let major = property("java.specification.version")?
        .parse::<u32>()
        .context("Unsupported Java version format")?;
    ensure!(
        major == crate::JAVA_MAJOR,
        "Minecraft {} baseline requires Java {}, found {major}",
        crate::GAME_VERSION,
        crate::JAVA_MAJOR
    );
    let home = files::absolute(Path::new(&property("java.home")?))?;
    let mut runtime_files = Vec::new();
    let jvm = if cfg!(windows) {
        "bin/server/jvm.dll"
    } else if cfg!(target_os = "macos") {
        "lib/server/libjvm.dylib"
    } else {
        "lib/server/libjvm.so"
    };
    for file in [
        executable.clone(),
        home.join("release"),
        home.join("lib/modules"),
        home.join(jvm),
    ] {
        runtime_files.push(RuntimeFile {
            path: files::absolute(&file)?,
            digest: files::digest(&file)?,
        });
    }
    Ok(JavaIdentity {
        executable,
        home,
        major,
        version,
        runtime_files,
    })
}

pub fn native_image(explicit: Option<&Path>) -> Result<PathBuf> {
    if let Some(path) = explicit {
        return files::absolute(path);
    }
    if let Some(home) = env::var_os("GRAALVM_HOME") {
        for filename in ["native-image.exe", "native-image.cmd", "native-image"] {
            let path = PathBuf::from(&home).join("bin").join(filename);
            if path.is_file() {
                return files::absolute(&path);
            }
        }
    }
    if let Some(path) = configured_tool("native_image")? {
        return files::absolute(&path);
    }
    find_tool("native-image").context("Native Image was not found. Set GRAALVM_HOME or pass --native-image; no JVM fallback will be used.")
}

fn configured_tool(key: &str) -> Result<Option<PathBuf>> {
    let path = Path::new(".boom/toolchain.json");
    if !path.is_file() {
        return Ok(None);
    }
    let bytes = std::fs::read(path)?;
    let bytes = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(&bytes);
    let value: serde_json::Value =
        serde_json::from_slice(bytes).context("Invalid .boom/toolchain.json")?;
    match value.get(key) {
        Some(value) => Ok(Some(PathBuf::from(
            value.as_str().context("Tool path must be a string")?,
        ))),
        None => Ok(None),
    }
}

/// Initialize compiler variables only for the build child, never the user's
/// global environment. GraalVM's automatic lookup misses some custom VS paths.
pub fn configure_msvc(command: &mut Command) -> Result<()> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        if env::var("VSCMD_ARG_TGT_ARCH").is_ok_and(|arch| arch == "x64") {
            return Ok(());
        }
        let program_files =
            env::var_os("ProgramFiles(x86)").context("Cannot locate Visual Studio Installer")?;
        let vswhere =
            PathBuf::from(program_files).join("Microsoft Visual Studio/Installer/vswhere.exe");
        let output = Command::new(&vswhere)
            .args([
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ])
            .output()
            .context("Cannot query Visual Studio C++ tools")?;
        ensure!(output.status.success(), "Visual Studio discovery failed");
        let installation = String::from_utf8(output.stdout)?.trim().to_owned();
        ensure!(!installation.is_empty(), "MSVC x64 tools were not found");
        let script = Path::new(&installation).join("VC/Auxiliary/Build/vcvarsall.bat");
        ensure!(
            script.is_file(),
            "MSVC environment script is missing: {}",
            script.display()
        );
        let script_text = script.to_string_lossy();
        ensure!(
            !script_text.contains(['"', '&', '|', '<', '>', '^', '%', '\r', '\n']),
            "Unsupported character in MSVC installation path"
        );
        let output = Command::new("cmd.exe")
            .args(["/d", "/s", "/c"])
            .raw_arg(format!(
                "\"chcp 65001 >nul && call \"{}\" x64 >nul && set\"",
                script.display()
            ))
            .output()
            .context("Cannot initialize MSVC environment")?;
        ensure!(
            output.status.success(),
            "MSVC environment initialization failed"
        );
        let text =
            String::from_utf8(output.stdout).context("MSVC environment output is not UTF-8")?;
        command.envs(compiler_environment(&text));
    }
    #[cfg(not(windows))]
    let _ = command;
    Ok(())
}

pub fn msvc_command(tool: &str) -> Result<Command> {
    ensure!(
        ["ml64.exe", "link.exe", "cl.exe"].contains(&tool),
        "Unsupported MSVC tool"
    );
    type Variables = Vec<(std::ffi::OsString, std::ffi::OsString)>;
    static ENVIRONMENT: std::sync::OnceLock<std::result::Result<Variables, String>> =
        std::sync::OnceLock::new();
    let variables = ENVIRONMENT
        .get_or_init(|| {
            let mut environment = Command::new("unused");
            configure_msvc(&mut environment).map_err(|error| format!("{error:#}"))?;
            Ok(environment
                .get_envs()
                .filter_map(|(key, value)| value.map(|value| (key.to_owned(), value.to_owned())))
                .collect())
        })
        .as_ref()
        .map_err(|error| anyhow::anyhow!("{error}"))?;
    let root = variables
        .iter()
        .find(|(key, _)| key.eq_ignore_ascii_case("VCToolsInstallDir"))
        .map(|(_, value)| value.clone())
        .or_else(|| env::var_os("VCToolsInstallDir"))
        .context("MSVC tool directory was not discovered")?;
    let path = PathBuf::from(root).join("bin/Hostx64/x64").join(tool);
    ensure!(path.is_file(), "MSVC tool is missing: {}", path.display());
    let mut command = Command::new(path);
    command.envs(variables.iter().map(|(key, value)| (key, value)));
    Ok(command)
}

fn compiler_environment(text: &str) -> BTreeMap<String, String> {
    const KEYS: &[&str] = &[
        "PATH",
        "INCLUDE",
        "LIB",
        "LIBPATH",
        "VSINSTALLDIR",
        "VCINSTALLDIR",
        "VCTOOLSINSTALLDIR",
        "VCTOOLSVERSION",
        "WINDOWSSDKDIR",
        "WINDOWSSDKVERSION",
        "WINDOWSSDKBINPATH",
        "WINDOWSSDKVERBINPATH",
        "UNIVERSALCRTSDKDIR",
        "UCRTVERSION",
        "VSCMD_ARG_TGT_ARCH",
        "VSCMD_ARG_HOST_ARCH",
        "VSCMD_VER",
        "DEVENVDIR",
    ];
    text.lines()
        .filter_map(|line| line.split_once('='))
        .filter(|(key, _)| KEYS.contains(&key.to_ascii_uppercase().as_str()))
        .map(|(key, value)| (key.to_owned(), value.to_owned()))
        .collect()
}

pub fn doctor(java: Option<&Path>, native: Option<&Path>) -> serde_json::Value {
    let java = find_java(java).and_then(|path| probe_java(&path));
    let native = native_image(native).and_then(|path| {
        let output = Command::new(&path).arg("--version").output()?;
        ensure!(output.status.success(), "Native Image version probe failed");
        Ok(serde_json::json!({"path": path, "version": String::from_utf8_lossy(&output.stdout).trim()}))
    });
    serde_json::json!({
        "game_version": crate::GAME_VERSION,
        "host": {"os": env::consts::OS, "arch": env::consts::ARCH},
        "java": match java { Ok(value) => serde_json::json!({"available":true,"identity":value}), Err(error) => serde_json::json!({"available":false,"error":format!("{error:#}")}) },
        "native_image": match native { Ok(value) => serde_json::json!({"available":true,"identity":value}), Err(error) => serde_json::json!({"available":false,"error":format!("{error:#}")}) }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compiler_environment_does_not_capture_unrelated_secrets() {
        let vars = compiler_environment("Path=C:\\tools\nINCLUDE=C:\\sdk\nPRIVATE_TOKEN=secret\n");
        assert_eq!(vars.len(), 2);
        assert!(!vars.contains_key("PRIVATE_TOKEN"));
    }
}
