//! Player-facing launch entry. Development compiler commands are never UI actions.
use crate::{
    compiler::classfile::ClassFile,
    files,
    lock::{InputLock, Side},
    metadata::VersionMetadata,
};
use anyhow::{Context, Result, bail, ensure};
use serde::Serialize;
use std::{
    fs,
    io::{Cursor, Read},
    path::{Path, PathBuf},
};
use zip::ZipArchive;

const MAIN_DESCRIPTOR: &str = "([Ljava/lang/String;)V";

#[derive(Debug, Serialize)]
pub struct ClientJarEntry {
    pub class: String,
    pub method: &'static str,
    pub descriptor: &'static str,
    pub input_fingerprint: String,
    pub jar_sha256: String,
    pub class_sha256: String,
    pub bytecode_sha256: String,
    pub bytecode_bytes: usize,
}

#[derive(Debug, Serialize)]
pub struct StartupPlan {
    pub schema: u32,
    pub game_version: &'static str,
    pub backend: &'static str,
    pub game_directory: PathBuf,
    pub memory_mib: u32,
    pub stages: [&'static str; 5],
    pub full_game_ready: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub verified_client_jar_entry: Option<ClientJarEntry>,
    pub missing_capabilities: Vec<&'static str>,
}

pub fn plan(game_directory: &Path, memory_mib: u32) -> Result<StartupPlan> {
    plan_with_lock(
        game_directory,
        memory_mib,
        Path::new(".boom/locks/client.json"),
    )
}

fn plan_with_lock(game_directory: &Path, memory_mib: u32, lock: &Path) -> Result<StartupPlan> {
    ensure!(
        (512..=32768).contains(&memory_mib),
        "Game memory must be 512..=32768 MiB"
    );
    Ok(StartupPlan {
        schema: 1,
        game_version: crate::GAME_VERSION,
        backend: "own-assembly",
        game_directory: std::path::absolute(game_directory)?,
        memory_mib,
        stages: [
            "preflight",
            "verify_or_prepare_inputs",
            "translate_and_compile_cache",
            "link_game",
            "start_game",
        ],
        full_game_ready: false,
        verified_client_jar_entry: if lock.try_exists()? {
            Some(client_jar_entry(lock)?)
        } else {
            None
        },
        missing_capabilities: vec![
            "complete_class_access_loading_and_general_arrays",
            "java_complete_string_conversion_and_reflection",
            "complete_class_linking_and_initialization",
            "java_throwable_and_handlers",
            "java_safepoints_and_stack_maps",
            "jdk_provider_program_integration_and_jni",
            "lwjgl_graphics_audio",
            "complete_application_linker",
        ],
    })
}

fn client_jar_entry(path: &Path) -> Result<ClientJarEntry> {
    let input = InputLock::read(path)?;
    ensure!(input.side == Side::Client, "Expected a client input lock");
    let metadata = input.file("version-metadata")?;
    let raw = fs::read(&metadata.path).context("Cannot read local version metadata")?;
    ensure!(
        metadata.digest.sha1 == crate::METADATA_SHA1
            && files::digest_bytes(&raw) == metadata.digest,
        "Version metadata differs from pinned Minecraft 1.21.1"
    );
    let version: VersionMetadata = serde_json::from_slice(&raw)?;
    version.validate()?;
    ensure!(
        input.main_class == version.main_class,
        "Client lock entry differs from vanilla metadata"
    );

    let game = input.file("client-game")?;
    let download = version
        .downloads
        .get("client")
        .context("Missing vanilla client download")?;
    ensure!(
        game.role == "client-game"
            && input
                .classpath
                .iter()
                .filter(|id| id.as_str() == "client-game")
                .count()
                == 1
            && game.digest.sha1 == download.sha1
            && game.digest.size == download.size,
        "Official client JAR differs from input lock"
    );
    let jar = fs::read(&game.path).context("Cannot read local client JAR")?;
    ensure!(
        files::digest_bytes(&jar) == game.digest,
        "Locked client JAR content changed"
    );
    let mut archive = ZipArchive::new(Cursor::new(jar))?;
    let name = version.main_class.replace('.', "/");
    let mut class = Vec::new();
    archive
        .by_name(&format!("{name}.class"))?
        .read_to_end(&mut class)?;
    let parsed = ClassFile::parse(&class)?;
    ensure!(
        parsed.name == name,
        "Client main class name differs from its JAR entry"
    );
    let method = parsed.method("main", Some(MAIN_DESCRIPTOR))?;
    ensure!(
        method.access & 0x0009 == 0x0009 && method.access & 0x0500 == 0,
        "Client main must be a public static Java method"
    );
    let code = &method
        .code
        .as_ref()
        .context("Client main has no bytecode")?
        .bytes;
    Ok(ClientJarEntry {
        class: version.main_class,
        method: "main",
        descriptor: MAIN_DESCRIPTOR,
        input_fingerprint: input.fingerprint.clone(),
        jar_sha256: game.digest.sha256.clone(),
        class_sha256: files::digest_bytes(&class).sha256,
        bytecode_sha256: files::digest_bytes(code).sha256,
        bytecode_bytes: code.len(),
    })
}

pub fn play(game_directory: &Path, memory_mib: u32, _auth_file: Option<&Path>) -> Result<()> {
    let plan = plan(game_directory, memory_mib)?;
    // Do not download gigabytes, claim partial DLLs are a game, or silently start
    // a JVM when the full assembly runtime/application linker is unavailable.
    // The player launch path remains closed until those implementations exist.
    if !plan.full_game_ready {
        bail!(
            "当前开发构建尚不能启动完整 Minecraft 1.21.1。缺少完整 String 转换与反射、动态类加载和通用数组执行、完整类链接与初始化、完整异常处理、GC 安全点与栈映射、标准库/JNI、图形音频和完整应用链接支持。启动检查已停止；没有切换到 JVM，也没有修改游戏存档。"
        );
    }
    bail!("No complete assembly game image is available")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn player_launch_never_falls_back_to_java_or_creates_game_data() {
        let dir = tempfile::tempdir().unwrap();
        let target = dir.path().join("game with spaces");
        let plan = plan(&target, 4096).unwrap();
        assert!(!plan.full_game_ready);
        assert_eq!(plan.backend, "own-assembly");
        assert!(!plan.missing_capabilities.is_empty());
        assert!(play(&target, 4096, None).is_err());
        assert!(!target.exists());
    }
    #[test]
    fn invalid_memory_is_rejected_before_any_launch_work() {
        assert!(plan(Path::new("unused"), 0).is_err());
        assert!(plan(Path::new("unused"), 65536).is_err());
    }

    #[test]
    fn missing_and_corrupt_client_locks_are_distinguished_before_creating_game_data() {
        let temp = tempfile::tempdir().unwrap();
        let lock = temp.path().join("client.json");
        let game = temp.path().join("game");
        assert!(
            plan_with_lock(&game, 4096, &lock)
                .unwrap()
                .verified_client_jar_entry
                .is_none()
        );
        fs::write(&lock, b"{}").unwrap();
        assert!(plan_with_lock(&game, 4096, &lock).is_err());
        assert!(!game.exists());
    }
}
