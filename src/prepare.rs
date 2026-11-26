use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::{Read, Write},
    path::{Path, PathBuf},
    time::Duration,
};

use anyhow::{Context, Result, bail, ensure};
use reqwest::blocking::Client;
use serde::Deserialize;
use zip::ZipArchive;

use crate::{
    files,
    lock::{InputLock, Side},
    metadata::{Download, Target, VersionMetadata, rules_allow},
    tools,
};

pub struct PrepareOptions {
    pub side: Side,
    pub cache: PathBuf,
    pub minecraft_dir: Option<PathBuf>,
    pub metadata: Option<PathBuf>,
    pub server_jar: Option<PathBuf>,
    pub java: Option<PathBuf>,
    pub download: bool,
    pub jobs: usize,
}

pub fn http_client() -> Result<Client> {
    Client::builder()
        .user_agent(concat!("BoomMinecraft/", env!("CARGO_PKG_VERSION")))
        .connect_timeout(Duration::from_secs(20))
        .timeout(Duration::from_secs(180))
        .build()
        .context("Cannot initialize HTTP client")
}

pub fn metadata(options: &PrepareOptions, client: &Client) -> Result<(VersionMetadata, PathBuf)> {
    let cached = options.cache.join("metadata/1.21.1.json");
    let local = options
        .minecraft_dir
        .as_ref()
        .map(|root| root.join("versions/1.21.1/1.21.1.json"));
    let path = if let Some(path) = &options.metadata {
        path.clone()
    } else if cached.is_file() {
        cached
    } else if local.as_ref().is_some_and(|path| path.is_file()) {
        local.unwrap()
    } else if options.download {
        files::fetch(
            client,
            crate::METADATA_URL,
            &cached,
            crate::METADATA_SHA1,
            None,
        )?
    } else {
        bail!(
            "Vanilla 1.21.1 metadata is missing. Use --metadata, --minecraft-dir, or --download."
        );
    };
    files::verify_expected(&path, crate::METADATA_SHA1, None)
        .context("Version metadata differs from the pinned official 1.21.1 input")?;
    let metadata: VersionMetadata = serde_json::from_slice(&fs::read(&path)?)?;
    metadata.validate()?;
    Ok((metadata, files::absolute(&path)?))
}

fn artifact(
    options: &PrepareOptions,
    client: &Client,
    download: &Download,
    local: Option<&Path>,
) -> Result<PathBuf> {
    if let Some(local) = local.filter(|path| path.is_file()) {
        files::verify_expected(local, &download.sha1, Some(download.size))?;
        return files::absolute(local);
    }
    let cached = files::safe_join(&options.cache.join("downloads"), &download.sha1)?;
    if cached.is_file() {
        files::verify_expected(&cached, &download.sha1, Some(download.size))?;
        return files::absolute(&cached);
    }
    ensure!(
        options.download,
        "Missing input: {}. Supply a local installation or enable --download.",
        download.path.as_deref().unwrap_or(&download.url)
    );
    eprintln!(
        "Fetching {} ({} bytes)",
        download.path.as_deref().unwrap_or(&download.sha1),
        download.size
    );
    files::fetch(
        client,
        &download.url,
        &cached,
        &download.sha1,
        Some(download.size),
    )
}

pub fn prepare(options: &PrepareOptions) -> Result<InputLock> {
    ensure!(
        (1..=crate::parallel::MAX_JOBS).contains(&options.jobs),
        "Prepare jobs must be 1..=64"
    );
    let client = http_client()?;
    let (metadata, metadata_path) = metadata(options, &client)?;
    let java = tools::probe_java(&tools::find_java(options.java.as_deref())?)?;
    let mut lock = InputLock {
        schema: 1,
        tool_version: env!("CARGO_PKG_VERSION").into(),
        game_version: crate::GAME_VERSION.into(),
        side: options.side,
        target: Target::windows_x64(),
        java,
        files: Vec::new(),
        classpath: Vec::new(),
        main_class: metadata.main_class.clone(),
        assets_root: None,
        natives_directory: None,
        fingerprint: String::new(),
    };
    lock.add("version-metadata", "metadata", &metadata_path)?;
    match options.side {
        Side::Server => {
            if let Some(path) = &options.server_jar {
                ensure!(
                    path.is_file(),
                    "Server JAR does not exist: {}",
                    path.display()
                );
            }
            let download = metadata
                .downloads
                .get("server")
                .context("Missing server download")?;
            let bundle = artifact(options, &client, download, options.server_jar.as_deref())?;
            lock.add("server-bundle", "server-bundle", &bundle)?;
            let root = options.cache.join("server").join(&download.sha1);
            prepare_server_bundle(&bundle, &root, &mut lock)?;
        }
        Side::Client => prepare_client(options, &client, &metadata, &mut lock)?,
    }
    lock.fingerprint = lock.identity()?;
    Ok(lock)
}

fn read_zip_text(archive: &mut ZipArchive<File>, name: &str) -> Result<String> {
    let mut text = String::new();
    archive
        .by_name(name)
        .with_context(|| format!("Missing bundle entry {name}"))?
        .take(2 * 1024 * 1024 + 1)
        .read_to_string(&mut text)?;
    ensure!(text.len() <= 2 * 1024 * 1024, "Oversized bundle metadata");
    Ok(text.trim_start_matches('\u{feff}').to_owned())
}

fn extract_hashed(
    archive: &mut ZipArchive<File>,
    entry: &str,
    path: &Path,
    sha256: &str,
) -> Result<()> {
    files::validate_hash(sha256, 64)?;
    if path.exists() {
        ensure!(
            files::digest(path)?.sha256.eq_ignore_ascii_case(sha256),
            "Corrupted extracted input: {}",
            path.display()
        );
        return Ok(());
    }
    let parent = path.parent().context("Invalid extraction path")?;
    fs::create_dir_all(parent)?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    let member = archive
        .by_name(entry)
        .with_context(|| format!("Missing bundle entry {entry}"))?;
    ensure!(
        !member.is_symlink(),
        "Symlink bundle entries are unsupported"
    );
    let size = member.size();
    ensure!(size <= 256 * 1024 * 1024, "Oversized bundled JAR: {entry}");
    let copied = std::io::copy(&mut member.take(size + 1), &mut temporary)?;
    ensure!(copied == size, "Truncated bundle entry: {entry}");
    temporary.flush()?;
    ensure!(
        files::digest(temporary.path())?
            .sha256
            .eq_ignore_ascii_case(sha256),
        "Bundled SHA-256 mismatch: {entry}"
    );
    temporary.as_file().sync_all()?;
    match temporary.persist_noclobber(path) {
        Ok(_) => (),
        Err(_) if path.exists() && files::digest(path)?.sha256.eq_ignore_ascii_case(sha256) => (),
        Err(error) => return Err(error.error.into()),
    }
    Ok(())
}

pub fn prepare_server_bundle(bundle: &Path, root: &Path, lock: &mut InputLock) -> Result<()> {
    let mut archive = ZipArchive::new(File::open(bundle)?)?;
    lock.main_class = read_zip_text(&mut archive, "META-INF/main-class")?
        .trim()
        .to_owned();
    ensure!(
        lock.main_class == "net.minecraft.server.Main",
        "Unexpected vanilla server entry point: {}",
        lock.main_class
    );
    for (list, prefix, role) in [
        ("versions.list", "versions", "server-game"),
        ("libraries.list", "libraries", "library"),
    ] {
        let entries = read_zip_text(&mut archive, &format!("META-INF/{list}"))?;
        let mut count = 0;
        for line in entries.lines().filter(|line| !line.trim().is_empty()) {
            let fields: Vec<_> = line.split('\t').collect();
            ensure!(fields.len() == 3, "Invalid {list} record");
            let (expected, relative) = (fields[0], fields[2]);
            let destination = files::safe_join(&root.join(prefix), relative)?;
            let entry = format!("META-INF/{prefix}/{relative}");
            extract_hashed(&mut archive, &entry, &destination, expected)?;
            let id = format!("server/{prefix}/{relative}");
            lock.add(&id, role, &destination)?;
            lock.classpath.push(id);
            count += 1;
        }
        ensure!(count > 0, "Empty server {list}");
        if prefix == "versions" {
            ensure!(
                count == 1,
                "Only a single bundled vanilla version is supported"
            );
        }
    }
    Ok(())
}

#[derive(Deserialize)]
struct AssetObjects {
    objects: BTreeMap<String, AssetObject>,
    #[serde(rename = "virtual", default)]
    virtual_: bool,
}

#[derive(Deserialize)]
struct AssetObject {
    hash: String,
    size: u64,
}

fn prepare_client(
    options: &PrepareOptions,
    client: &Client,
    metadata: &VersionMetadata,
    lock: &mut InputLock,
) -> Result<()> {
    let features = BTreeMap::new();
    let mut native_archives = Vec::new();
    for library in &metadata.libraries {
        if !rules_allow(&library.rules, &lock.target, &features)? {
            continue;
        }
        if let Some(download) = &library.downloads.artifact {
            let relative = download
                .path
                .as_deref()
                .context("Library artifact has no path")?;
            let local = options
                .minecraft_dir
                .as_ref()
                .map(|root| files::safe_join(&root.join("libraries"), relative))
                .transpose()?;
            let path = artifact(options, client, download, local.as_deref())?;
            let id = format!("libraries/{relative}");
            lock.add(&id, "library", &path)?;
            lock.classpath.push(id);
            if library.name.contains(":natives-") {
                native_archives.push(path);
            }
        }
        if let Some(classifier) = library.natives.get(&lock.target.os) {
            let classifier = classifier.replace("${arch}", "64");
            let download = library
                .downloads
                .classifiers
                .get(&classifier)
                .context("Missing native classifier")?;
            let path = artifact(options, client, download, None)?;
            lock.add(
                format!("natives-archive/{}/{}", library.name, classifier),
                "natives-archive",
                &path,
            )?;
            native_archives.push(path);
        }
    }
    let download = metadata
        .downloads
        .get("client")
        .context("Missing client download")?;
    let local = options
        .minecraft_dir
        .as_ref()
        .map(|root| root.join("versions/1.21.1/1.21.1.jar"));
    let client_jar = artifact(options, client, download, local.as_deref())?;
    lock.add("client-game", "client-game", &client_jar)?;
    lock.classpath.push("client-game".into());

    let assets_root = options.cache.join("assets");
    let index_path = files::safe_join(
        &assets_root.join("indexes"),
        &format!("{}.json", metadata.asset_index.id),
    )?;
    let local_index = options.minecraft_dir.as_ref().map(|root| {
        root.join("assets/indexes")
            .join(format!("{}.json", metadata.asset_index.id))
    });
    let descriptor = Download {
        sha1: metadata.asset_index.sha1.clone(),
        size: metadata.asset_index.size,
        url: metadata.asset_index.url.clone(),
        path: None,
    };
    let index_source = artifact(options, client, &descriptor, local_index.as_deref())?;
    if !index_path.exists() {
        files::write_atomic(&index_path, &fs::read(&index_source)?)?;
    }
    files::verify_expected(&index_path, &descriptor.sha1, Some(descriptor.size))?;
    lock.add("asset-index", "asset-index", &index_path)?;
    let assets: AssetObjects = serde_json::from_slice(&fs::read(&index_path)?)?;
    ensure!(!assets.virtual_, "Legacy virtual assets are unsupported");
    let mut unique = BTreeMap::new();
    for asset in assets.objects.values() {
        files::validate_hash(&asset.hash, 40)?;
        if let Some(previous) = unique.insert(asset.hash.clone(), asset) {
            ensure!(
                previous.size == asset.size,
                "Conflicting sizes for one asset hash"
            );
        }
    }
    let tasks: Vec<_> = unique.values().copied().collect();
    let completed = std::sync::atomic::AtomicUsize::new(0);
    let work = crate::parallel::ordered_map(&tasks, options.jobs, |_, asset| -> Result<PathBuf> {
        let relative = format!("{}/{}", &asset.hash[..2], asset.hash);
        let destination = files::safe_join(&assets_root.join("objects"), &relative)?;
        let local = options
            .minecraft_dir
            .as_ref()
            .map(|root| files::safe_join(&root.join("assets/objects"), &relative))
            .transpose()?;
        if !destination.is_file() {
            if let Some(source) = local.as_ref().filter(|p| p.is_file()) {
                files::verify_expected(source, &asset.hash, Some(asset.size))?;
                let parent = destination.parent().unwrap();
                fs::create_dir_all(parent)?;
                // Own cache copy: never mutate an existing launcher installation.
                files::write_atomic(&destination, &fs::read(source)?)?;
            } else {
                ensure!(
                    options.download,
                    "Missing asset {}; use --download or a complete local installation",
                    asset.hash
                );
                files::fetch(
                    client,
                    &format!("https://resources.download.minecraft.net/{relative}"),
                    &destination,
                    &asset.hash,
                    Some(asset.size),
                )?;
            }
        }
        files::verify_expected(&destination, &asset.hash, Some(asset.size))?;
        let completed = completed.fetch_add(1, std::sync::atomic::Ordering::Relaxed) + 1;
        if completed.is_multiple_of(128) || completed == tasks.len() {
            eprintln!("Assets verified: {completed}/{}", tasks.len());
        }
        Ok(destination)
    })?;
    for (asset, result) in tasks.iter().zip(work.results) {
        lock.add(format!("assets/{}", asset.hash), "asset", &result?)?;
    }
    lock.assets_root = Some(files::absolute(&assets_root)?);

    let natives_root = options.cache.join("natives").join(crate::METADATA_SHA1);
    fs::create_dir_all(&natives_root)?;
    let mut names = BTreeSet::new();
    for archive_path in native_archives {
        let mut archive = ZipArchive::new(File::open(archive_path)?)?;
        for index in 0..archive.len() {
            let mut entry = archive.by_index(index)?;
            let enclosed = entry
                .enclosed_name()
                .context("Unsafe native archive path")?;
            if entry.is_dir() || enclosed.extension().and_then(|ext| ext.to_str()) != Some("dll") {
                continue;
            }
            ensure!(
                !entry.is_symlink() && entry.size() <= 64 * 1024 * 1024,
                "Unsupported native archive member"
            );
            let filename = enclosed
                .file_name()
                .context("Invalid native filename")?
                .to_string_lossy()
                .into_owned();
            let destination = files::safe_join(&natives_root, &filename)?;
            let mut bytes = Vec::new();
            entry.read_to_end(&mut bytes)?;
            // 1.21.1 lists x64, x86 and ARM64 native JARs under the same OS rule.
            // Retain their official classpath, but only flatten compatible DLLs.
            let machine = files::pe_machine(&bytes)?;
            if machine != 0x8664 {
                ensure!(
                    matches!(machine, 0x014c | 0xaa64),
                    "Unknown native DLL machine 0x{machine:04x}"
                );
                continue;
            }
            if destination.exists() {
                ensure!(
                    fs::read(&destination)? == bytes,
                    "Conflicting native library: {filename}"
                );
            } else {
                files::write_atomic(&destination, &bytes)?;
            }
            if names.insert(filename.clone()) {
                lock.add(format!("native/{filename}"), "native", &destination)?;
            }
        }
    }
    lock.natives_directory = Some(files::absolute(&natives_root)?);
    if let Some(logging) = metadata.logging.get("client") {
        let descriptor = Download {
            sha1: logging.file.sha1.clone(),
            size: logging.file.size,
            url: logging.file.url.clone(),
            path: None,
        };
        let local = options
            .minecraft_dir
            .as_ref()
            .map(|root| root.join("assets/log_configs").join(&logging.file.id));
        let path = artifact(options, client, &descriptor, local.as_deref())?;
        lock.add("logging-config", "logging-config", &path)?;
    }
    Ok(())
}
