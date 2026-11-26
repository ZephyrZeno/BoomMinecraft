//! Source-bound name catalog and initialization graph for Class.forName0.
use super::{class_loaders, classfile::ClassFile, mirrors, program, types};
use crate::{
    bytecode::{BytecodeProvider, ClassOrigin, VanillaBytecodeProvider},
    files,
    jdk::JdkBase,
    lock::InputLock,
};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt::Write as _,
    path::Path,
    process::Command,
};
pub(super) fn candidate(units: &[u16]) -> Option<String> {
    let name = String::from_utf16(units).ok()?;
    if name.is_empty() || name.contains(['\0', '/']) {
        return None;
    }
    if name.starts_with('[') {
        array_descriptor(&name)?;
        return Some(name);
    }
    if name.contains(';') || name.split('.').any(str::is_empty) {
        return None;
    }
    Some(name)
}
fn array_descriptor(name: &str) -> Option<(String, Option<String>)> {
    let rank = name.bytes().take_while(|&b| b == b'[').count();
    if rank == 0 || rank > 255 {
        return None;
    }
    let tail = &name[rank..];
    if tail.len() == 1 && "ZBCSIJFD".contains(tail) {
        return Some((name.into(), None));
    }
    let component = tail.strip_prefix('L')?.strip_suffix(';')?;
    if component.is_empty()
        || component.contains(['[', ';', '/', '\0'])
        || component.split('.').any(str::is_empty)
    {
        return None;
    }
    Some((name.replace('.', "/"), Some(component.replace('.', "/"))))
}
pub(super) fn register_literals(
    registry: &mut types::Registry<'_>,
    literals: &BTreeSet<(String, String)>,
) -> Result<()> {
    for (loader, name) in literals {
        if name.starts_with('[') {
            if let Some((descriptor, component)) = array_descriptor(name)
                && component
                    .as_ref()
                    .map(|c| registry.contains_name(c))
                    .transpose()?
                    .unwrap_or(true)
            {
                registry.field(loader, &descriptor)?;
            }
        } else {
            let internal = name.replace('.', "/");
            if registry.contains_name(&internal)? {
                registry.class(loader, &internal)?;
            }
        }
    }
    Ok(())
}
pub const DESCRIPTOR: &str =
    "(Ljava/lang/String;ZLjava/lang/ClassLoader;Ljava/lang/Class;)Ljava/lang/Class;";
pub const BOOTSTRAP_DESCRIPTOR: &str = "(Ljava/lang/String;)Ljava/lang/Class;";
pub(super) fn is_bootstrap_call(o: &str, n: &str, d: &str) -> bool {
    o == "java/lang/ClassLoader" && n == "findBootstrapClass" && d == BOOTSTRAP_DESCRIPTOR
}
pub(super) fn is_call(o: &str, n: &str, d: &str) -> bool {
    (o == "java/lang/Class" && n == "forName0" && d == DESCRIPTOR) || is_bootstrap_call(o, n, d)
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub bootstrap_lookup: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entry {
    pub name: String,
    pub hash: u32,
    pub initiator: usize,
    pub defining_loader: String,
    pub type_id: Option<usize>,
    pub array: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Initializer {
    pub type_id: usize,
    pub descriptor: String,
    pub dependencies: Vec<usize>,
    pub linked_body: bool,
    pub ready: bool,
    pub synthetic_slot: Option<usize>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub descriptor: String,
    pub bindings: Vec<Binding>,
    pub input_fingerprint: String,
    pub jdk_fingerprint: String,
    pub module_fingerprint: String,
    pub image_catalog_sha256: String,
    pub catalog: Vec<Entry>,
    pub initializers: Vec<Option<Initializer>>,
    pub synthetic_roots: usize,
    pub message_offset: usize,
    pub native_source_sha256: String,
    pub vm_metadata_fixture: bool,
    pub dynamic_class_definition_complete: bool,
    pub dynamic_array_metadata_complete: bool,
    pub security_manager_supported: bool,
    pub automatic_gc: bool,
}
pub(super) fn origin(registry: &mut types::Registry<'_>) -> Result<ClassOrigin> {
    let id = registry.class("bootstrap", "java/lang/Class")?;
    let types::Type::Class { origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    let origin = origin.as_ref().clone();
    ensure!(
        origin.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "Class lookup requires original java.base Class"
    );
    let m = registry
        .definition(id)
        .unwrap()
        .method("forName0", Some(DESCRIPTOR))?;
    ensure!(
        m.access == 0x10a && m.code.is_none(),
        "Class.forName0 native declaration changed"
    );
    Ok(origin)
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
) -> Result<Binding> {
    let expected = origin(registry)?;
    let (o, n, d) = caller.method_reference(constant)?;
    ensure!(is_call(&o, &n, &d), "Class lookup native reference changed");
    let bootstrap_lookup = is_bootstrap_call(&o, &n, &d);
    if bootstrap_lookup {
        let id = registry.class("bootstrap", "java/lang/ClassLoader")?;
        let types::Type::Class { origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            source == origin.as_ref()
                && source.source_id == "jdk:java.base"
                && source.generated.is_none()
                && caller.name == "java/lang/ClassLoader",
            "Bootstrap lookup is private to original ClassLoader"
        );
        let m = registry
            .definition(id)
            .unwrap()
            .method("findBootstrapClass", Some(BOOTSTRAP_DESCRIPTOR))?;
        ensure!(
            m.access == 0x10a && m.code.is_none(),
            "Bootstrap lookup native declaration changed"
        );
    } else if let Some(g) = &source.generated {
        super::jdk_bridges::validate(caller, source)?;
        ensure!(
            g.host_class == "java/lang/Class"
                && g.host_sha256 == expected.sha256
                && matches!(g.site, 22 | 23),
            "Class.forName0 requires retained original private helpers"
        );
    } else {
        ensure!(
            source == &expected && caller.name == "java/lang/Class",
            "Class.forName0 is private to its original Class caller"
        );
    }
    Ok(Binding {
        caller: source.clone(),
        constant,
        bootstrap_lookup,
    })
}
fn loader(types: &[types::Type], mut id: usize) -> Result<String> {
    for _ in 0..=255 {
        match &types[id] {
            types::Type::Class { key, .. } => return Ok(key.loader.clone()),
            types::Type::Primitive { .. } => return Ok("bootstrap".into()),
            types::Type::Array { component } => id = *component,
        }
    }
    anyhow::bail!("Cyclic array component")
}
fn visible_generated(types: &[types::Type], mut id: usize) -> bool {
    for _ in 0..=255 {
        match &types[id] {
            types::Type::Class { origin, .. } => return origin.generated.is_none(),
            types::Type::Primitive { .. } => return true,
            types::Type::Array { component } => id = *component,
        }
    }
    false
}
fn default_interfaces(
    registry: &types::Registry<'_>,
    id: usize,
    seen: &mut BTreeSet<usize>,
    out: &mut Vec<usize>,
) -> Result<()> {
    if !seen.insert(id) {
        return Ok(());
    }
    let types::Type::Class { interfaces, .. } = &registry.types[id] else {
        unreachable!()
    };
    for &parent in interfaces {
        default_interfaces(registry, parent, seen, out)?;
    }
    let class = registry
        .definition(id)
        .context("Missing initialization interface")?;
    if class
        .methods
        .iter()
        .any(|m| !m.name.starts_with('<') && m.access & (8 | 2 | 0x400) == 0)
    {
        out.push(id)
    }
    Ok(())
}
fn ready(
    id: usize,
    nodes: &[Option<Initializer>],
    active: &mut BTreeSet<usize>,
    memo: &mut BTreeMap<usize, bool>,
) -> Result<bool> {
    if let Some(&v) = memo.get(&id) {
        return Ok(v);
    }
    ensure!(active.insert(id), "Cyclic class initialization metadata");
    let n = nodes[id]
        .as_ref()
        .context("Missing class initialization node")?;
    let mut yes = n.linked_body;
    for &d in &n.dependencies {
        yes &= ready(d, nodes, active, memo)?;
    }
    active.remove(&id);
    memo.insert(id, yes);
    Ok(yes)
}
impl Plan {
    #[allow(clippy::too_many_arguments)]
    pub(super) fn prepare(
        registry: &mut types::Registry<'_>,
        inputs: &InputLock,
        jdk_path: &Path,
        snapshot: &crate::boot_modules::Snapshot,
        loaders: &class_loaders::Plan,
        states: &[program::ClassState],
        sources: &[program::Source],
        bindings: Vec<Binding>,
        message_offset: usize,
    ) -> Result<Self> {
        let origin = origin(registry)?;
        let jdk = JdkBase::read(jdk_path, inputs)?;
        let application = VanillaBytecodeProvider { inputs }.snapshot()?;
        let mut names: BTreeMap<String, BTreeMap<String, Option<usize>>> = BTreeMap::new();
        let mut command = Command::new(&jdk.extractor.path);
        command.arg("list").arg(&jdk.image.path);
        for key in [
            "JAVA_TOOL_OPTIONS",
            "_JAVA_OPTIONS",
            "JDK_JAVA_OPTIONS",
            "CLASSPATH",
        ] {
            command.env_remove(key);
        }
        let listing = command.output().context("Listing locked JDK class names")?;
        ensure!(
            listing.status.success(),
            "JDK class inventory failed: {}",
            String::from_utf8_lossy(&listing.stderr)
        );
        ensure!(
            files::digest(&jdk.image.path)? == jdk.image.digest
                && files::digest(&jdk.extractor.path)? == jdk.extractor.digest,
            "JDK changed during class inventory"
        );
        let mut module = "";
        let text = std::str::from_utf8(&listing.stdout).context("JDK inventory is not UTF8")?;
        for line in text.lines() {
            let line = line.trim();
            if let Some(m) = line.strip_prefix("Module: ") {
                module = m;
                continue;
            }
            if !snapshot.graph.resolved.contains_key(module) || line == "module-info.class" {
                continue;
            }
            if let Some(name) = line.strip_suffix(".class") {
                let defining = if snapshot.loaders.bootstrap.contains(module) {
                    "bootstrap"
                } else if snapshot.loaders.platform.contains(module) {
                    "platform"
                } else {
                    "vanilla-application"
                };
                names
                    .entry(name.replace('/', "."))
                    .or_default()
                    .insert(defining.into(), None);
            }
        }
        let image_catalog_sha256 = files::digest_bytes(&listing.stdout).sha256;
        for name in application.classes.keys() {
            names
                .entry(name.clone())
                .or_default()
                .insert("vanilla-application".into(), None);
        }
        for (id, t) in registry.types.iter().enumerate() {
            if matches!(t, types::Type::Primitive { .. }) || !visible_generated(&registry.types, id)
            {
                continue;
            }
            names
                .entry(mirrors::name(&registry.types, id))
                .or_default()
                .insert(loader(&registry.types, id)?, Some(id));
        }
        let mut catalog = Vec::new();
        for (name, choices) in names {
            for (initiator, key) in loaders.keys.iter().enumerate() {
                let picked = if let Some(v) = choices.get("bootstrap") {
                    Some(("bootstrap", v))
                } else if key == "platform" {
                    choices.get("platform").map(|v| ("platform", v))
                } else if key == "explicit-application" {
                    choices
                        .get("explicit-application")
                        .map(|v| ("explicit-application", v))
                        .or_else(|| choices.get("platform").map(|v| ("platform", v)))
                        .or_else(|| {
                            choices
                                .get("vanilla-application")
                                .map(|v| ("vanilla-application", v))
                        })
                } else if key == "vanilla-application" {
                    choices
                        .get("platform")
                        .map(|v| ("platform", v))
                        .or_else(|| {
                            choices
                                .get("vanilla-application")
                                .map(|v| ("vanilla-application", v))
                        })
                } else {
                    choices.get(key).map(|v| (key.as_str(), v))
                };
                let Some((defining_loader, &type_id)) = picked else {
                    continue;
                };
                let hash = name
                    .encode_utf16()
                    .fold(0u32, |h, c| h.wrapping_mul(31).wrapping_add(c as u32));
                catalog.push(Entry {
                    array: name.starts_with('['),
                    name: name.clone(),
                    hash,
                    initiator,
                    defining_loader: defining_loader.into(),
                    type_id,
                });
            }
        }
        catalog.sort_by(|a, b| (a.initiator, a.hash, &a.name).cmp(&(b.initiator, b.hash, &b.name)));
        ensure!(
            !catalog.is_empty() && catalog.len() <= 1048576,
            "Class lookup catalog exceeds ABI budget"
        );
        let mut initializers = Vec::new();
        let mut synthetic_roots = 0;
        for (id, t) in registry.types.iter().enumerate() {
            let types::Type::Class {
                origin,
                key,
                superclass,
                interfaces,
                access,
                ..
            } = t
            else {
                initializers.push(None);
                continue;
            };
            let class = registry
                .definition(id)
                .context("Missing initialization source")?;
            let source = sources
                .iter()
                .position(|s| s.origin.as_ref() == Some(origin.as_ref()));
            let state = source.and_then(|ci| states.iter().find(|s| s.id == ci));
            let has_body = class.methods.iter().any(|m| m.name == "<clinit>");
            let linked_body = !has_body || state.is_some_and(|s| s.initializer.is_some());
            let mut dependencies = Vec::new();
            if access & 0x200 == 0 {
                if let Some(parent) = superclass {
                    dependencies.push(*parent)
                }
                let mut seen = BTreeSet::new();
                for &iface in interfaces {
                    default_interfaces(registry, iface, &mut seen, &mut dependencies)?;
                }
            }
            let (descriptor, synthetic_slot) = if let Some(state) = state {
                (format!("boom_class{}", state.id), None)
            } else {
                let slot = synthetic_roots;
                synthetic_roots += 1;
                (format!("boom_lookup_class{id}"), Some(slot))
            };
            ensure!(
                key.loader == origin.loader,
                "Initialization source loader mismatch"
            );
            initializers.push(Some(Initializer {
                type_id: id,
                descriptor,
                dependencies,
                linked_body,
                ready: false,
                synthetic_slot,
            }));
        }
        let mut memo = BTreeMap::new();
        for id in 0..initializers.len() {
            if initializers[id].is_some() {
                ready(id, &initializers, &mut BTreeSet::new(), &mut memo)?;
            }
        }
        for (id, yes) in memo {
            initializers[id].as_mut().unwrap().ready = yes;
        }
        Ok(Self {
            abi: 1,
            origin,
            descriptor: DESCRIPTOR.into(),
            vm_metadata_fixture: bindings.is_empty(),
            bindings,
            input_fingerprint: inputs.fingerprint.clone(),
            jdk_fingerprint: jdk.fingerprint,
            module_fingerprint: snapshot.fingerprint.clone(),
            image_catalog_sha256,
            catalog,
            initializers,
            synthetic_roots,
            message_offset,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/class_for_name.asm"
            ))
            .sha256,
            dynamic_class_definition_complete: false,
            dynamic_array_metadata_complete: false,
            security_manager_supported: false,
            automatic_gc: false,
        })
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        if self.bindings.iter().any(|b| b.bootstrap_lookup) {
            out.push_str("EXTERN boom_class_find_bootstrap:PROC\n");
        }
        out.push_str("EXTERN boom_class_for_name:PROC\n.const\nALIGN 8\n");
        let mut name_ids = BTreeMap::new();
        for e in &self.catalog {
            if !name_ids.contains_key(&e.name) {
                let id = name_ids.len();
                name_ids.insert(e.name.clone(), id);
                writeln!(out, "boom_lookup_name{id} LABEL WORD")?;
                let units = e.name.encode_utf16().collect::<Vec<_>>();
                ensure!(
                    !units.is_empty() && units.len() <= 65535,
                    "Invalid lookup name length"
                );
                for chunk in units.chunks(24) {
                    writeln!(
                        out,
                        "    WORD {}",
                        chunk
                            .iter()
                            .map(|c| format!("0{c:X}h"))
                            .collect::<Vec<_>>()
                            .join(",")
                    )?;
                }
            }
        }
        out.push_str("ALIGN 8\nboom_lookup_catalog LABEL BYTE\n");
        for e in &self.catalog {
            writeln!(
                out,
                "    QWORD OFFSET boom_lookup_name{}\n    DWORD {},0{:08X}h,{},0{:08X}h,{},0",
                name_ids[&e.name],
                e.name.encode_utf16().count(),
                e.hash,
                e.initiator,
                e.type_id.map_or(u32::MAX, |v| v as u32),
                u32::from(e.array)
            )?;
        }
        out.push_str("ALIGN 8\nboom_lookup_initializers LABEL QWORD\n");
        for node in &self.initializers {
            writeln!(
                out,
                "    QWORD {}",
                node.as_ref()
                    .map_or("0".into(), |n| format!("OFFSET {}", n.descriptor))
            )?;
        }
        out.push_str("boom_lookup_ready LABEL BYTE\n");
        for n in self.initializers.chunks(32) {
            writeln!(
                out,
                "    BYTE {}",
                n.iter()
                    .map(|n| u8::from(n.as_ref().is_some_and(|n| n.ready)).to_string())
                    .collect::<Vec<_>>()
                    .join(",")
            )?;
        }
        writeln!(
            out,
            "ALIGN 8\nboom_for_name_pool DWORD 04D414E46h,1\n    QWORD OFFSET boom_mirror_pool,OFFSET boom_string_pool,OFFSET boom_heap_ptr,OFFSET boom_loader_pool,OFFSET boom_lookup_catalog\n    DWORD {},{}\n    QWORD OFFSET boom_lookup_initializers,OFFSET boom_lookup_ready\n    DWORD {},0\n    QWORD 0,0\n.code\nPUBLIC boom_get_for_name_pool\nboom_get_for_name_pool PROC\n    lea rax,boom_for_name_pool\n    ret\nboom_get_for_name_pool ENDP",
            self.catalog.len(),
            self.initializers.len(),
            self.message_offset
        )?;
        for node in self
            .initializers
            .iter()
            .flatten()
            .filter(|n| n.synthetic_slot.is_some())
        {
            let id = node.type_id;
            let slot = node.synthetic_slot.unwrap();
            writeln!(
                out,
                ".data\nALIGN 8\n{} DWORD 0434C4153h,2,0,0\n    QWORD OFFSET boom_lookup_init{id}\n    DWORD {id},0\n    QWORD 0,0,0,OFFSET boom_lookup_failure_roots+{}\n.code\nboom_lookup_init{id} PROC FRAME\n    sub rsp,40\n    .allocstack 40\n    .endprolog\n    mov QWORD PTR [rsp+32],rcx",
                node.descriptor,
                slot * 8
            )?;
            if !node.linked_body {
                out.push_str("    mov DWORD PTR [rcx],20\n");
            } else {
                for dep in &node.dependencies {
                    let name = &self.initializers[*dep].as_ref().unwrap().descriptor;
                    writeln!(
                        out,
                        "    lea rcx,{name}\n    mov rdx,QWORD PTR [rsp+32]\n    call boom_class_ensure32\n    test eax,eax\n    jnz boom_lookup_init{id}_done"
                    )?;
                }
            }
            writeln!(
                out,
                "boom_lookup_init{id}_done:\n    xor eax,eax\n    add rsp,40\n    ret\nboom_lookup_init{id} ENDP"
            )?;
        }
        Ok(())
    }
}
