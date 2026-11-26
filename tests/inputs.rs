use std::{
    fs,
    io::{Cursor, Write},
    path::{Path, PathBuf},
};

use boom_minecraft::{
    files,
    lock::{InputLock, Side},
    metadata::Target,
    prepare::prepare_server_bundle,
    tools::JavaIdentity,
};
use sha2::{Digest, Sha256};
use zip::{ZipWriter, write::SimpleFileOptions};

fn empty_lock() -> InputLock {
    InputLock {
        schema: 1,
        tool_version: "test".into(),
        game_version: "1.21.1".into(),
        side: Side::Server,
        target: Target::windows_x64(),
        java: JavaIdentity {
            executable: "java.exe".into(),
            home: "jdk".into(),
            major: 21,
            version: "21-test".into(),
            runtime_files: Vec::new(),
        },
        files: Vec::new(),
        classpath: Vec::new(),
        main_class: "net.minecraft.server.Main".into(),
        assets_root: None,
        natives_directory: None,
        fingerprint: String::new(),
    }
}

fn write_bundle(path: &Path, version_path: &str, corrupt: bool) {
    let game = b"fixture-game";
    let library = b"fixture-library";
    let game_hash = if corrupt {
        "0".repeat(64)
    } else {
        format!("{:x}", Sha256::digest(game))
    };
    let library_hash = format!("{:x}", Sha256::digest(library));
    let entries = vec![
        (
            "META-INF/main-class".to_owned(),
            b"net.minecraft.server.Main\n".to_vec(),
        ),
        (
            "META-INF/versions.list".to_owned(),
            format!("{game_hash}\t1.21.1\t{version_path}\n").into_bytes(),
        ),
        (
            "META-INF/libraries.list".to_owned(),
            format!("{library_hash}\torg.example:test:1\torg/example/test/1/test-1.jar\n")
                .into_bytes(),
        ),
        (format!("META-INF/versions/{version_path}"), game.to_vec()),
        (
            "META-INF/libraries/org/example/test/1/test-1.jar".to_owned(),
            library.to_vec(),
        ),
    ];
    let mut writer = ZipWriter::new(Cursor::new(Vec::new()));
    for (name, bytes) in entries {
        writer
            .start_file(name, SimpleFileOptions::default())
            .unwrap();
        writer.write_all(&bytes).unwrap();
    }
    fs::write(path, writer.finish().unwrap().into_inner()).unwrap();
}

#[test]
fn expands_actual_server_classpath_instead_of_compiling_bootstrap() {
    let directory = tempfile::tempdir().unwrap();
    let bundle = directory.path().join("server.jar");
    write_bundle(&bundle, "1.21.1/server-1.21.1.jar", false);
    let mut lock = empty_lock();
    prepare_server_bundle(&bundle, &directory.path().join("prepared"), &mut lock).unwrap();
    assert_eq!(lock.main_class, "net.minecraft.server.Main");
    assert_eq!(
        lock.classpath,
        [
            "server/versions/1.21.1/server-1.21.1.jar",
            "server/libraries/org/example/test/1/test-1.jar"
        ]
    );
    assert_eq!(
        fs::read(&lock.classpath_paths().unwrap()[0]).unwrap(),
        b"fixture-game"
    );
}

#[test]
fn rejects_corrupted_nested_game_jar() {
    let directory = tempfile::tempdir().unwrap();
    let bundle = directory.path().join("server.jar");
    write_bundle(&bundle, "1.21.1/server.jar", true);
    let error = prepare_server_bundle(
        &bundle,
        &directory.path().join("prepared"),
        &mut empty_lock(),
    )
    .unwrap_err();
    assert!(format!("{error:#}").contains("SHA-256 mismatch"));
    assert!(
        !directory
            .path()
            .join("prepared/versions/1.21.1/server.jar")
            .exists()
    );
}

#[test]
fn refuses_bundle_paths_that_escape_the_owned_cache() {
    let directory = tempfile::tempdir().unwrap();
    let bundle = directory.path().join("server.jar");
    write_bundle(&bundle, "../../escape.jar", false);
    assert!(
        prepare_server_bundle(
            &bundle,
            &directory.path().join("prepared"),
            &mut empty_lock()
        )
        .is_err()
    );
    assert!(!directory.path().join("escape.jar").exists());
}

#[test]
fn identity_ignores_locations_but_tracks_classpath_order_and_bytes() {
    let directory = tempfile::tempdir().unwrap();
    let first = directory.path().join("first.jar");
    let second = directory.path().join("second.jar");
    fs::write(&first, b"first").unwrap();
    fs::write(&second, b"second").unwrap();
    let mut lock = empty_lock();
    lock.add("first", "library", &first).unwrap();
    lock.add("second", "library", &second).unwrap();
    lock.classpath = vec!["first".into(), "second".into()];
    let original = lock.identity().unwrap();
    lock.files[0].path = PathBuf::from("relocated/first.jar");
    assert_eq!(original, lock.identity().unwrap());
    lock.classpath.reverse();
    assert_ne!(original, lock.identity().unwrap());
    lock.classpath.reverse();
    fs::write(&first, b"different").unwrap();
    lock.files[0].digest = files::digest(&first).unwrap();
    assert_ne!(original, lock.identity().unwrap());
}
