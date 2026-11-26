//! Offline parsing/resolution of the locked system image. No game execution here.
use crate::{
    compiler::classfile::{ClassFile, ModuleDescriptor},
    files,
    lock::InputLock,
    tools::{self, RuntimeFile},
};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    fs,
    path::Path,
    process::Command,
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LoaderSets {
    pub bootstrap: BTreeSet<String>,
    pub platform: BTreeSet<String>,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Loader {
    Bootstrap,
    Platform,
    Application,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Resolved {
    pub loader: Loader,
    /// Includes self, matching Module.canRead; requires-static only when resolved.
    pub reads: BTreeSet<String>,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ServiceBinding {
    pub consumer: String,
    pub service: String,
    pub providers: BTreeSet<String>,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Graph {
    pub profile: String,
    pub roots: BTreeSet<String>,
    pub resolved: BTreeMap<String, Resolved>,
    pub service_bindings: Vec<ServiceBinding>,
}
fn module_name(name: &str) -> Result<()> {
    ensure!(
        !name.is_empty()
            && name.split('.').all(|p| !p.is_empty()
                && p.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
                && !p.as_bytes()[0].is_ascii_digit()),
        "Unsupported system module name {name:?}"
    );
    Ok(())
}

pub fn resolve_default(
    descriptors: &BTreeMap<String, ModuleDescriptor>,
    loaders: &LoaderSets,
) -> Result<Graph> {
    ensure!(
        !descriptors.is_empty()
            && descriptors.len() <= 256
            && descriptors.contains_key("java.base"),
        "Invalid system module universe"
    );
    ensure!(
        loaders.bootstrap.contains("java.base") && loaders.bootstrap.is_disjoint(&loaders.platform),
        "Conflicting system defining loader tables"
    );
    for (name, d) in descriptors {
        module_name(name)?;
        ensure!(name == &d.name, "Descriptor key/name mismatch");
    }
    let mut roots: BTreeSet<_> = descriptors
        .iter()
        .filter(|(_, d)| {
            d.resolution_flags & 1 == 0 && d.exports.iter().any(|e| e.targets.is_empty())
        })
        .map(|(n, _)| n.clone())
        .collect();
    roots.insert("java.base".into());
    let mut pending: VecDeque<_> = roots.iter().cloned().collect();
    let mut selected = BTreeSet::new();
    loop {
        while let Some(name) = pending.pop_front() {
            let d = descriptors
                .get(&name)
                .with_context(|| format!("Required system module {name} is unavailable"))?;
            if !selected.insert(name) {
                continue;
            }
            for req in &d.requires {
                if req.flags & 0x40 == 0 {
                    pending.push_back(req.module.clone());
                }
            }
        }
        let services: BTreeSet<_> = selected
            .iter()
            .flat_map(|n| descriptors[n].uses.iter())
            .collect();
        for (name, d) in descriptors {
            if !selected.contains(name) && d.provides.iter().any(|p| services.contains(&p.service))
            {
                pending.push_back(name.clone());
            }
        }
        if pending.is_empty() {
            break;
        }
    }
    // The named system-module dependency graph must not contain a runtime cycle.
    fn visit(
        name: &str,
        descriptors: &BTreeMap<String, ModuleDescriptor>,
        selected: &BTreeSet<String>,
        active: &mut BTreeSet<String>,
        done: &mut BTreeSet<String>,
    ) -> Result<()> {
        if done.contains(name) {
            return Ok(());
        }
        ensure!(
            active.insert(name.into()),
            "Cyclic system module dependency at {name}"
        );
        for req in &descriptors[name].requires {
            if req.flags & 0x40 == 0 && selected.contains(&req.module) {
                visit(&req.module, descriptors, selected, active, done)?;
            }
        }
        active.remove(name);
        done.insert(name.into());
        Ok(())
    }
    let mut done = BTreeSet::new();
    for name in &selected {
        visit(
            name,
            descriptors,
            &selected,
            &mut BTreeSet::new(),
            &mut done,
        )?;
    }
    let mut resolved = BTreeMap::new();
    for name in &selected {
        let loader = if loaders.bootstrap.contains(name) {
            Loader::Bootstrap
        } else if loaders.platform.contains(name) {
            Loader::Platform
        } else {
            Loader::Application
        };
        let mut reads = BTreeSet::from([name.clone()]);
        reads.extend(
            descriptors[name]
                .requires
                .iter()
                .filter(|r| selected.contains(&r.module))
                .map(|r| r.module.clone()),
        );
        loop {
            let previous = reads.len();
            let mut additions = Vec::new();
            for dependency in &reads {
                additions.extend(
                    descriptors[dependency]
                        .requires
                        .iter()
                        .filter(|r| r.flags & 0x20 != 0 && selected.contains(&r.module))
                        .map(|r| r.module.clone()),
                );
            }
            reads.extend(additions);
            if reads.len() == previous {
                break;
            }
        }
        resolved.insert(name.clone(), Resolved { loader, reads });
    }
    let mut service_bindings = Vec::new();
    for consumer in &selected {
        let mut services = descriptors[consumer].uses.clone();
        services.sort();
        for service in services {
            let providers = selected
                .iter()
                .filter(|n| {
                    descriptors[*n]
                        .provides
                        .iter()
                        .any(|p| p.service == service)
                })
                .cloned()
                .collect();
            service_bindings.push(ServiceBinding {
                consumer: consumer.clone(),
                service,
                providers,
            });
        }
    }
    Ok(Graph {
        profile: "jdk21-system-classpath-default".into(),
        roots,
        resolved,
        service_bindings,
    })
}

/// Read the two immutable String[] -> Set.of -> putstatic blocks, without running
/// the JDK initializer. Unexpected bytecode is rejected rather than interpreted.
fn loader_sets(bytes: &[u8]) -> Result<LoaderSets> {
    let class = ClassFile::parse(bytes)?;
    const OWNER: &str = "jdk/internal/module/ModuleLoaderMap$Modules";
    ensure!(class.name == OWNER, "Unexpected module loader table class");
    let code = &class
        .method("<clinit>", Some("()V"))?
        .code
        .as_ref()
        .context("Missing system loader table initializer")?
        .bytes;
    struct R<'a> {
        bytes: &'a [u8],
        at: usize,
    }
    impl R<'_> {
        fn byte(&mut self) -> Result<u8> {
            let b = *self.bytes.get(self.at).context("Truncated loader table")?;
            self.at += 1;
            Ok(b)
        }
        fn word(&mut self) -> Result<u16> {
            Ok(u16::from_be_bytes([self.byte()?, self.byte()?]))
        }
        fn op(&mut self, expected: u8) -> Result<()> {
            ensure!(
                self.byte()? == expected,
                "Unsupported system loader table bytecode"
            );
            Ok(())
        }
        fn integer(&mut self) -> Result<usize> {
            let value = match self.byte()? {
                b @ 3..=8 => i32::from(b - 3),
                0x10 => i32::from(self.byte()? as i8),
                0x11 => i32::from(self.word()? as i16),
                _ => bail!("Unsupported loader table integer"),
            };
            ensure!(
                (0..=1024).contains(&value),
                "Invalid loader table size/index"
            );
            Ok(value as usize)
        }
    }
    let mut r = R { bytes: code, at: 0 };
    let mut tables = BTreeMap::new();
    for _ in 0..2 {
        let count = r.integer()?;
        r.op(0xbd)?;
        ensure!(
            class.constant_class(r.word()?)? == "java/lang/String",
            "Loader table is not String[]"
        );
        let mut names = BTreeSet::new();
        for index in 0..count {
            r.op(0x59)?;
            ensure!(r.integer()? == index, "Nonlinear loader table array write");
            let constant = match r.byte()? {
                0x12 => u16::from(r.byte()?),
                0x13 => r.word()?,
                _ => bail!("Expected loader table String literal"),
            };
            let name = String::from_utf16(
                &class
                    .string_literal(constant)?
                    .context("Missing loader table String")?,
            )?;
            module_name(&name)?;
            ensure!(names.insert(name), "Duplicate loader module");
            r.op(0x53)?;
        }
        r.op(0xb8)?;
        let (owner, name, descriptor, interface) = class.special_method_reference(r.word()?)?;
        ensure!(
            interface
                && owner == "java/util/Set"
                && name == "of"
                && descriptor == "([Ljava/lang/Object;)Ljava/util/Set;",
            "Unsupported loader set factory"
        );
        r.op(0xb3)?;
        let (owner, name, descriptor) = class.field_reference(r.word()?)?;
        ensure!(
            owner == OWNER
                && descriptor == "Ljava/util/Set;"
                && matches!(name.as_str(), "bootModules" | "platformModules"),
            "Unknown loader table field"
        );
        ensure!(
            tables.insert(name, names).is_none(),
            "Duplicate loader table"
        );
    }
    r.op(0xb1)?;
    ensure!(r.at == code.len(), "Unexpected trailing loader table work");
    Ok(LoaderSets {
        bootstrap: tables
            .remove("bootModules")
            .context("Missing bootstrap module table")?,
        platform: tables
            .remove("platformModules")
            .context("Missing platform module table")?,
    })
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ModuleInput {
    pub sha256: String,
    pub descriptor: ModuleDescriptor,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    pub schema: u32,
    pub input_fingerprint: String,
    pub image: RuntimeFile,
    pub extractor: RuntimeFile,
    pub loader_table_sha256: String,
    pub loaders: LoaderSets,
    pub modules: BTreeMap<String, ModuleInput>,
    pub graph: Graph,
    pub fingerprint: String,
}
fn plain(path: &Path) -> Result<()> {
    let mut current = Some(path);
    while let Some(p) = current {
        let m = fs::symlink_metadata(p)?;
        ensure!(!m.file_type().is_symlink(), "Module cache contains a link");
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            ensure!(
                m.file_attributes() & 0x400 == 0,
                "Module cache contains a reparse point"
            );
        }
        current = p.parent();
    }
    Ok(())
}
fn read_small(path: &Path) -> Result<Vec<u8>> {
    plain(path)?;
    ensure!(
        fs::metadata(path)?.len() <= 1024 * 1024,
        "Oversized system module input"
    );
    use std::io::Read;
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take(1024 * 1024 + 1)
        .read_to_end(&mut bytes)?;
    ensure!(
        bytes.len() <= 1024 * 1024,
        "System module input grew beyond budget"
    );
    Ok(bytes)
}
impl Snapshot {
    fn identity(&self) -> Result<String> {
        Ok(files::digest_bytes(&serde_json::to_vec(&(
            &self.schema,
            &self.input_fingerprint,
            &self.image.digest,
            &self.extractor.digest,
            &self.loader_table_sha256,
            &self.loaders,
            &self.modules,
            &self.graph,
        ))?)
        .sha256)
    }
    pub fn read(manifest: &Path, inputs: &InputLock) -> Result<Self> {
        let manifest = files::absolute(manifest)?;
        plain(&manifest)?;
        ensure!(
            fs::metadata(&manifest)?.len() <= 16 * 1024 * 1024,
            "Oversized system module manifest"
        );
        let s: Self = serde_json::from_slice(&fs::read(&manifest)?)?;
        ensure!(
            s.schema == 1
                && s.fingerprint == s.identity()?
                && s.input_fingerprint == inputs.fingerprint,
            "System module snapshot identity mismatch"
        );
        ensure!(
            s.image.path == inputs.java.home.join("lib/modules")
                && inputs
                    .java
                    .runtime_files
                    .iter()
                    .any(|f| f.path == s.image.path && f.digest == s.image.digest),
            "System modules do not come from the locked image"
        );
        ensure!(
            files::digest(&s.image.path)? == s.image.digest,
            "Locked JDK module image changed"
        );
        ensure!(
            s.extractor.path
                == inputs.java.home.join(if cfg!(windows) {
                    "bin/jimage.exe"
                } else {
                    "bin/jimage"
                })
                && files::digest(&s.extractor.path)? == s.extractor.digest,
            "JDK module extractor changed"
        );
        let root = manifest
            .parent()
            .context("No module snapshot directory")?
            .join("image");
        let bytes =
            read_small(&root.join("java.base/jdk/internal/module/ModuleLoaderMap$Modules.class"))?;
        ensure!(
            files::digest_bytes(&bytes).sha256 == s.loader_table_sha256
                && loader_sets(&bytes)? == s.loaders,
            "Module defining loader tables changed"
        );
        ensure!(
            !s.modules.is_empty() && s.modules.len() <= 256,
            "Invalid system module snapshot count"
        );
        let mut descriptors = BTreeMap::new();
        for (name, input) in &s.modules {
            module_name(name)?;
            let bytes = read_small(&root.join(name).join("module-info.class"))?;
            let parsed = ClassFile::parse(&bytes)?
                .module
                .context("Missing module-info descriptor")?;
            ensure!(
                files::digest_bytes(&bytes).sha256 == input.sha256
                    && parsed == input.descriptor
                    && parsed.name == *name,
                "System module descriptor changed: {name}"
            );
            descriptors.insert(name.clone(), parsed);
        }
        ensure!(
            resolve_default(&descriptors, &s.loaders)? == s.graph,
            "Cached system module resolution does not match its inputs"
        );
        Ok(s)
    }
}
pub fn prepare(inputs: &InputLock, output: &Path) -> Result<Snapshot> {
    inputs.verify()?;
    let image = inputs
        .java
        .runtime_files
        .iter()
        .find(|f| f.path == inputs.java.home.join("lib/modules"))
        .context("No locked JDK image")?
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
        ensure!(
            output.is_dir() && fs::read_dir(output)?.next().is_none(),
            "System module output must be new or empty"
        );
    } else {
        fs::create_dir_all(output)?;
    }
    let output = files::absolute(output)?;
    plain(&output)?;
    let destination = output.join("image");
    fs::create_dir(&destination)?;
    let mut command = Command::new(&extractor.path);
    tools::clean_java_environment(&mut command);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let result=command.args(["extract","--include", "glob:/**/module-info.class,glob:/java.base/jdk/internal/module/ModuleLoaderMap$Modules.class","--dir"]).arg(&destination).arg(&image.path).output()?;
    ensure!(
        result.status.success(),
        "JDK module extraction failed: {}",
        String::from_utf8_lossy(&result.stderr)
    );
    ensure!(
        files::digest(&image.path)? == image.digest
            && files::digest(&extractor.path)? == extractor.digest,
        "Module image/extractor changed during extraction"
    );
    let bytes = read_small(
        &destination.join("java.base/jdk/internal/module/ModuleLoaderMap$Modules.class"),
    )?;
    let loaders = loader_sets(&bytes)?;
    let loader_table_sha256 = files::digest_bytes(&bytes).sha256;
    let mut modules = BTreeMap::new();
    let mut descriptors = BTreeMap::new();
    for entry in fs::read_dir(&destination)? {
        let entry = entry?;
        plain(&entry.path())?;
        ensure!(
            entry.file_type()?.is_dir(),
            "Unexpected module extraction entry"
        );
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| anyhow::anyhow!("Non-UTF8 system module name"))?;
        module_name(&name)?;
        let bytes = read_small(&entry.path().join("module-info.class"))?;
        let descriptor = ClassFile::parse(&bytes)?
            .module
            .context("Expected module-info descriptor")?;
        ensure!(descriptor.name == name, "Module directory/name mismatch");
        descriptors.insert(name.clone(), descriptor.clone());
        ensure!(modules.len() < 256, "Too many extracted system modules");
        modules.insert(
            name,
            ModuleInput {
                sha256: files::digest_bytes(&bytes).sha256,
                descriptor,
            },
        );
    }
    let graph = resolve_default(&descriptors, &loaders)?;
    let mut snapshot = Snapshot {
        schema: 1,
        input_fingerprint: inputs.fingerprint.clone(),
        image,
        extractor,
        loader_table_sha256,
        loaders,
        modules,
        graph,
        fingerprint: String::new(),
    };
    snapshot.fingerprint = snapshot.identity()?;
    files::write_atomic(
        &output.join("jdk-modules.json"),
        &serde_json::to_vec_pretty(&snapshot)?,
    )?;
    Ok(snapshot)
}

pub fn plan(inputs: &InputLock, manifest: &Path, output: &Path) -> Result<Snapshot> {
    let snapshot = Snapshot::read(manifest, inputs)?;
    fs::create_dir_all(output)?;
    let report = serde_json::json!({"schema":1,"input_fingerprint":inputs.fingerprint,"snapshot_fingerprint":snapshot.fingerprint,"available":snapshot.modules.len(),"graph":snapshot.graph,"module_layer_execution":false,"game_started":false,"full_game_ready":false});
    files::write_atomic(
        &output.join("boot-modules.json"),
        &serde_json::to_vec_pretty(&report)?,
    )?;
    Ok(snapshot)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::compiler::classfile::{ModuleExport, ModuleProvide, ModuleRequire};
    fn module(name: &str, api: bool) -> ModuleDescriptor {
        ModuleDescriptor {
            name: name.into(),
            flags: 0,
            version: None,
            requires: if name == "java.base" {
                vec![]
            } else {
                vec![ModuleRequire {
                    module: "java.base".into(),
                    flags: 0x8000,
                    version: None,
                }]
            },
            exports: if api {
                vec![ModuleExport {
                    package: name.replace('.', "/"),
                    flags: 0,
                    targets: vec![],
                }]
            } else {
                vec![]
            },
            opens: vec![],
            uses: vec![],
            provides: vec![],
            packages: vec![],
            resolution_flags: 0,
            target: None,
            main_class: None,
        }
    }
    #[test]
    fn defaults_dependencies_services_and_readability_are_distinct() {
        let mut modules: BTreeMap<_, _> = [
            ("java.base", true),
            ("api", true),
            ("dep", false),
            ("leaf", false),
            ("provider", false),
            ("second", false),
            ("optional", false),
            ("incubator", true),
        ]
        .into_iter()
        .map(|(n, api)| (n.into(), module(n, api)))
        .collect();
        modules.get_mut("api").unwrap().requires.extend([
            ModuleRequire {
                module: "dep".into(),
                flags: 0,
                version: None,
            },
            ModuleRequire {
                module: "optional".into(),
                flags: 0x40,
                version: None,
            },
        ]);
        modules
            .get_mut("dep")
            .unwrap()
            .requires
            .push(ModuleRequire {
                module: "leaf".into(),
                flags: 0x20,
                version: None,
            });
        modules.get_mut("incubator").unwrap().resolution_flags = 1;
        modules
            .get_mut("java.base")
            .unwrap()
            .uses
            .push("p/Service".into());
        modules
            .get_mut("provider")
            .unwrap()
            .provides
            .push(ModuleProvide {
                service: "p/Service".into(),
                providers: vec!["p/Impl".into()],
            });
        modules
            .get_mut("provider")
            .unwrap()
            .uses
            .push("p/Second".into());
        modules
            .get_mut("second")
            .unwrap()
            .provides
            .push(ModuleProvide {
                service: "p/Second".into(),
                providers: vec!["p/SecondImpl".into()],
            });
        let loaders = LoaderSets {
            bootstrap: BTreeSet::from(["java.base".into()]),
            platform: BTreeSet::from(["provider".into()]),
        };
        let graph = resolve_default(&modules, &loaders).unwrap();
        assert_eq!(
            graph.roots,
            BTreeSet::from(["java.base".into(), "api".into()])
        );
        assert_eq!(graph.resolved.len(), 6);
        assert_eq!(
            graph.resolved["api"].reads,
            BTreeSet::from([
                "api".into(),
                "java.base".into(),
                "dep".into(),
                "leaf".into()
            ])
        );
        assert_eq!(graph.resolved["provider"].loader, Loader::Platform);
        assert!(!graph.resolved["java.base"].reads.contains("provider"));
        assert_eq!(graph.service_bindings.len(), 2);
        modules
            .get_mut("api")
            .unwrap()
            .requires
            .push(ModuleRequire {
                module: "incubator".into(),
                flags: 0,
                version: None,
            });
        assert!(
            resolve_default(&modules, &loaders)
                .unwrap()
                .resolved
                .contains_key("incubator")
        );
        modules
            .get_mut("api")
            .unwrap()
            .requires
            .push(ModuleRequire {
                module: "missing".into(),
                flags: 0,
                version: None,
            });
        assert!(resolve_default(&modules, &loaders).is_err());
    }
    #[test]
    fn cycles_and_conflicting_loader_sets_are_rejected() {
        let mut base = module("java.base", true);
        base.requires.push(ModuleRequire {
            module: "other".into(),
            flags: 0,
            version: None,
        });
        let modules = BTreeMap::from([
            ("java.base".into(), base),
            ("other".into(), module("other", false)),
        ]);
        let mut loaders = LoaderSets {
            bootstrap: BTreeSet::from(["java.base".into()]),
            platform: BTreeSet::new(),
        };
        assert!(resolve_default(&modules, &loaders).is_err());
        loaders.platform.insert("java.base".into());
        assert!(resolve_default(&modules, &loaders).is_err());
        for bad in ["../escape", "java/base", "java..base", "1name", "name:bad"] {
            assert!(module_name(bad).is_err());
        }
    }
}
