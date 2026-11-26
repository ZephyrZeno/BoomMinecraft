use std::{
    collections::BTreeMap,
    fs::{self, File},
    path::{Path, PathBuf},
    process::{Command, Stdio},
};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

use crate::{
    files,
    lock::{InputLock, Side},
    metadata::{VersionMetadata, expand_arguments},
    tools,
};

#[derive(Debug, Clone, Serialize)]
pub struct CommandPlan {
    pub kind: String,
    pub input_fingerprint: String,
    pub executable: PathBuf,
    pub arguments: Vec<String>,
    pub working_directory: PathBuf,
    pub compatibility_jar: Option<PathBuf>,
}

impl CommandPlan {
    pub fn redacted(&self) -> Self {
        let mut plan = self.clone();
        for index in 1..plan.arguments.len() {
            if matches!(
                plan.arguments[index - 1].as_str(),
                "--accessToken" | "--clientId" | "--xuid"
            ) {
                plan.arguments[index] = "<redacted>".into();
            }
        }
        plan
    }

    pub fn command(&self) -> Command {
        let mut command = Command::new(&self.executable);
        command
            .args(&self.arguments)
            .current_dir(&self.working_directory);
        tools::clean_java_environment(&mut command);
        command
    }

    pub fn run_reference(&self) -> Result<i32> {
        fs::create_dir_all(&self.working_directory)?;
        let status = self
            .command()
            .status()
            .context("Cannot start reference JVM")?;
        Ok(status.code().unwrap_or(1))
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuthSession {
    pub player_name: String,
    pub uuid: String,
    pub access_token: String,
    pub client_id: String,
    pub xuid: String,
}

fn classpath(lock: &InputLock) -> Result<String> {
    // Target locks are Windows x64; refuse executing them on another host.
    ensure!(
        cfg!(windows) && cfg!(target_arch = "x86_64"),
        "Execution currently requires Windows x86-64"
    );
    let paths = lock.classpath_paths()?;
    let joined = std::env::join_paths(paths).context("Invalid classpath path")?;
    joined
        .into_string()
        .map_err(|_| anyhow::anyhow!("Classpath is not valid Unicode"))
}

pub fn substitute(value: &str, variables: &BTreeMap<String, String>) -> Result<String> {
    // Scan the template once: data values are never interpreted as new placeholders.
    let mut remaining = value;
    let mut output = String::new();
    while let Some(start) = remaining.find("${") {
        output.push_str(&remaining[..start]);
        let rest = &remaining[start + 2..];
        let end = rest
            .find('}')
            .context("Unterminated metadata placeholder")?;
        let key = &rest[..end];
        output.push_str(
            variables
                .get(key)
                .with_context(|| format!("Unsupported metadata placeholder: {key}"))?,
        );
        remaining = &rest[end + 1..];
    }
    output.push_str(remaining);
    Ok(output)
}

pub fn reference_plan(
    lock: &InputLock,
    game_dir: &Path,
    auth_file: Option<&Path>,
    extra_jvm: &[String],
) -> Result<CommandPlan> {
    lock.verify()?;
    let working_directory = std::path::absolute(game_dir)?;
    let cp = classpath(lock)?;
    let mut args = vec!["-Xms512M".into(), "-Xmx2G".into()];
    args.extend_from_slice(extra_jvm);
    match lock.side {
        Side::Server => args.extend(["-cp".into(), cp, lock.main_class.clone(), "nogui".into()]),
        Side::Client => {
            let auth_file = auth_file.context("Client reference launch requires --auth-file <session.json>; authentication is not bypassed")?;
            let auth: AuthSession = serde_json::from_slice(
                &fs::read(auth_file).context("Cannot read authentication session")?,
            )
            .context("Invalid authentication session JSON")?;
            ensure!(
                !auth.player_name.is_empty()
                    && !auth.access_token.is_empty()
                    && auth.access_token != "0",
                "A valid authenticated session is required"
            );
            let uuid = auth.uuid.replace('-', "");
            ensure!(
                uuid.len() == 32 && uuid.bytes().all(|c| c.is_ascii_hexdigit()),
                "Invalid player UUID"
            );
            let metadata: VersionMetadata =
                serde_json::from_slice(&fs::read(&lock.file("version-metadata")?.path)?)?;
            let mut variables = BTreeMap::from([
                ("classpath".into(), cp),
                (
                    "natives_directory".into(),
                    lock.natives_directory
                        .as_ref()
                        .context("Missing natives directory")?
                        .to_string_lossy()
                        .into_owned(),
                ),
                ("launcher_name".into(), "BoomMinecraft-reference".into()),
                ("launcher_version".into(), env!("CARGO_PKG_VERSION").into()),
                ("auth_player_name".into(), auth.player_name),
                ("version_name".into(), lock.game_version.clone()),
                (
                    "game_directory".into(),
                    working_directory.to_string_lossy().into_owned(),
                ),
                (
                    "assets_root".into(),
                    lock.assets_root
                        .as_ref()
                        .context("Missing assets root")?
                        .to_string_lossy()
                        .into_owned(),
                ),
                ("assets_index_name".into(), metadata.asset_index.id.clone()),
                ("auth_uuid".into(), uuid),
                ("auth_access_token".into(), auth.access_token),
                ("clientid".into(), auth.client_id),
                ("auth_xuid".into(), auth.xuid),
                ("user_type".into(), "msa".into()),
                ("version_type".into(), metadata.version_type.clone()),
            ]);
            let features = BTreeMap::new();
            for arg in expand_arguments(&metadata.arguments.jvm, &lock.target, &features)? {
                args.push(substitute(&arg, &variables)?);
            }
            if let Some(logging) = metadata.logging.get("client") {
                variables.insert(
                    "path".into(),
                    lock.file("logging-config")?
                        .path
                        .to_string_lossy()
                        .into_owned(),
                );
                args.push(substitute(&logging.argument, &variables)?);
            }
            args.push(lock.main_class.clone());
            for arg in expand_arguments(&metadata.arguments.game, &lock.target, &features)? {
                args.push(substitute(&arg, &variables)?);
            }
        }
    }
    Ok(CommandPlan {
        kind: "reference-jvm".into(),
        input_fingerprint: lock.fingerprint.clone(),
        executable: lock.java.executable.clone(),
        arguments: args,
        working_directory,
        compatibility_jar: None,
    })
}

pub fn native_plan(
    lock: &InputLock,
    executable: &Path,
    output: &Path,
    metadata_dir: Option<&Path>,
    jobs: u16,
    build_heap_gib: u16,
) -> Result<CommandPlan> {
    ensure!(
        jobs > 0 && build_heap_gib > 0,
        "Build budgets must be positive"
    );
    lock.verify()?;
    let output = std::path::absolute(output)?;
    // Native Image appends .exe on Windows, even when -o already ends in .exe.
    let output = if output
        .extension()
        .is_some_and(|extension| extension.eq_ignore_ascii_case("exe"))
    {
        output.with_extension("")
    } else {
        output
    };
    let parent = output
        .parent()
        .context("Native output has no parent")?
        .to_owned();
    let compatibility_jar = parent.join("compatibility/vanilla-compat.jar");
    let mut classpath_paths = lock.classpath_paths()?;
    classpath_paths.push(compatibility_jar.clone());
    let native_classpath = std::env::join_paths(classpath_paths)?
        .into_string()
        .map_err(|_| anyhow::anyhow!("Classpath is not valid Unicode"))?;
    let mut args = vec![
        "--no-fallback".into(),
        "--enable-url-protocols=http,https".into(),
        "--enable-monitoring=jfr".into(),
        "-H:+AddAllCharsets".into(),
        "-march=compatibility".into(),
        format!("--parallelism={jobs}"),
        format!("-J-Xmx{build_heap_gib}g"),
        "--verbose".into(),
        "-H:+ReportExceptionStackTraces".into(),
        "-cp".into(),
        native_classpath,
        "-o".into(),
        output.to_string_lossy().into_owned(),
    ];
    let mut metadata_directories = vec![parent.join("compatibility/metadata")];
    if let Some(metadata_dir) = metadata_dir {
        metadata_directories.push(files::absolute(metadata_dir)?);
    }
    let metadata_directories = metadata_directories
        .iter()
        .map(|path| {
            path.to_str()
                .context("Metadata directory is not valid Unicode")
        })
        .collect::<Result<Vec<_>>>()?;
    ensure!(
        metadata_directories.iter().all(|path| !path.contains(',')),
        "Metadata directories cannot contain commas"
    );
    args.push(format!(
        "-H:ConfigurationFileDirectories={}",
        metadata_directories.join(",")
    ));
    args.push(lock.main_class.clone());
    Ok(CommandPlan {
        kind: "native-image-build".into(),
        input_fingerprint: lock.fingerprint.clone(),
        executable: executable.to_owned(),
        arguments: args,
        working_directory: parent,
        compatibility_jar: Some(compatibility_jar),
    })
}

pub fn build_native(plan: &CommandPlan, inputs: &InputLock) -> Result<()> {
    ensure!(
        plan.executable.is_file(),
        "Native Image is missing; use doctor or pass --native-image. No JVM fallback will be used."
    );
    let version = Command::new(&plan.executable).arg("--version").output()?;
    ensure!(version.status.success(), "Cannot identify Native Image");
    let version_text = format!(
        "{}\n{}",
        String::from_utf8_lossy(&version.stdout),
        String::from_utf8_lossy(&version.stderr)
    );
    let major = regex::Regex::new(r"(?m)(?:native-image|GraalVM)\s+(?:version\s+)?(\d+)")?
        .captures(&version_text)
        .and_then(|c| c.get(1))
        .map(|m| m.as_str().parse::<u32>())
        .transpose()?
        .context("Cannot determine Native Image Java major version")?;
    ensure!(
        major == crate::JAVA_MAJOR,
        "Native Image must use Java {}, found {major}",
        crate::JAVA_MAJOR
    );
    fs::create_dir_all(&plan.working_directory)?;
    let compatibility = plan
        .compatibility_jar
        .as_ref()
        .map(|path| crate::compatibility::prepare(inputs, &plan.executable, path))
        .transpose()?;
    let plan_path = plan.working_directory.join("build-plan.json");
    files::write_atomic(&plan_path, &serde_json::to_vec_pretty(plan)?)?;
    let log_path = plan.working_directory.join("native-image.log");
    let log = File::create(&log_path)?;
    eprintln!("Native Image output: {}", log_path.display());
    // Avoid cmd.exe's short command limit when invoking native-image.cmd.
    let argument_file = plan.working_directory.join("native-image.args");
    files::write_atomic(
        &argument_file,
        argument_file_text(&plan.arguments)?.as_bytes(),
    )?;
    let mut command = Command::new(&plan.executable);
    command
        .arg(format!("@{}", argument_file.display()))
        .current_dir(&plan.working_directory);
    tools::clean_java_environment(&mut command);
    tools::configure_msvc(&mut command)?;
    let status = command
        .stdout(Stdio::from(log.try_clone()?))
        .stderr(Stdio::from(log))
        .status()
        .context("Cannot execute Native Image")?;
    let output_name = plan
        .arguments
        .iter()
        .position(|arg| arg == "-o")
        .and_then(|index| plan.arguments.get(index + 1))
        .context("Native build has no output path")?;
    let output_path = format!("{output_name}.exe");
    let artifact = if status.success() && Path::new(&output_path).is_file() {
        Some(files::digest(Path::new(&output_path))?)
    } else {
        None
    };
    let report = serde_json::json!({"kind":"native-image-build", "input_fingerprint":plan.input_fingerprint, "backend_version":version_text.trim(), "backend_digest":files::digest(&plan.executable)?, "compatibility":compatibility,"exit_code":status.code(), "success":status.success() && artifact.is_some(), "artifact":artifact.as_ref(),"argument_file":argument_file,"log":log_path});
    files::write_atomic(
        &plan.working_directory.join("build-result.json"),
        &serde_json::to_vec_pretty(&report)?,
    )?;
    ensure!(
        status.success(),
        "Native compilation failed; inspect {}",
        log_path.display()
    );
    ensure!(
        artifact.is_some(),
        "Native Image returned success without producing {}",
        output_path
    );
    Ok(())
}

fn argument_file_text(arguments: &[String]) -> Result<String> {
    let mut text = String::new();
    for argument in arguments {
        ensure!(
            !argument.contains(['\r', '\n', '\0']),
            "Control character in Native Image argument"
        );
        text.push('"');
        text.push_str(&argument.replace('\\', "\\\\").replace('"', "\\\""));
        text.push_str("\"\n");
    }
    Ok(text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_argument_file_quotes_windows_paths_without_shell_expansion() {
        let text =
            argument_file_text(&[r"C:\a folder\game.jar;C:\b.jar".into(), "a\"b".into()]).unwrap();
        assert!(text.contains(r"C:\\a folder\\game.jar;C:\\b.jar"));
        assert!(text.contains("a\\\"b"));
        assert!(argument_file_text(&["injected\noption".into()]).is_err());
    }

    #[test]
    fn placeholder_values_are_not_expanded_recursively() {
        let vars = BTreeMap::from([("name".into(), "a ${unknown} value".into())]);
        assert_eq!(
            substitute("hello ${name}", &vars).unwrap(),
            "hello a ${unknown} value"
        );
        assert!(substitute("${missing}", &vars).is_err());
    }

    #[test]
    fn authentication_values_are_redacted() {
        let plan = CommandPlan {
            kind: "reference-jvm".into(),
            input_fingerprint: String::new(),
            executable: "java".into(),
            working_directory: ".".into(),
            compatibility_jar: None,
            arguments: vec![
                "--accessToken".into(),
                "secret".into(),
                "--clientId".into(),
                "private".into(),
                "--xuid".into(),
                "123".into(),
            ],
        };
        let output = serde_json::to_string(&plan.redacted()).unwrap();
        assert!(
            !output.contains("secret") && !output.contains("private") && !output.contains("123")
        );
    }
}
