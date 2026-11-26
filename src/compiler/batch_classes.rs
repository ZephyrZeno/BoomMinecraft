//! Source-layout Class mirrors and Class constants. All guest execution is MASM.
//! Names remain a source-layout lazy cache. This does not replace Class.registerNatives.
use super::{
    batch_catalog::{Catalog, Layout},
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    batch_metadata::{self, TypeRecord},
    batch_types::Binding,
    hierarchy::Metadata,
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{Read, Write},
    path::Path,
};
use zip::{ZipArchive, ZipWriter, write::SimpleFileOptions};

#[derive(Debug, Serialize)]
pub struct Site {
    pub label: String,
    pub caller_class: usize,
    pub class_sha256: String,
    pub constant: u16,
    pub type_id: usize,
    pub caller_methods: BTreeSet<usize>,
    pub assembly_unit: Option<usize>,
    pub diagnostic: Option<String>,
}
pub(super) fn record(
    sites: &mut BTreeMap<String, Site>,
    method: usize,
    sha: &str,
    b: &Binding,
) -> Result<()> {
    let type_id = b
        .literal_type
        .context("Class constant has no represented type identity")?;
    ensure!(
        b.kind == "literal_resolution"
            && b.protocol.as_deref() == Some("java/lang/Class")
            && matches!(b.opcode, 18 | 19),
        "Invalid source Class literal binding"
    );
    let row = sites.entry(b.label.clone()).or_insert_with(|| Site {
        label: b.label.clone(),
        caller_class: b.caller_class,
        class_sha256: sha.into(),
        constant: b.constant,
        type_id,
        caller_methods: BTreeSet::new(),
        assembly_unit: None,
        diagnostic: None,
    });
    ensure!(
        (
            row.caller_class,
            row.constant,
            row.type_id,
            row.class_sha256.as_str()
        ) == (b.caller_class, b.constant, type_id, sha),
        "Conflicting Class constant identity"
    );
    row.caller_methods.insert(method);
    Ok(())
}
#[derive(Serialize)]
pub struct Shape {
    pub class_id: usize,
    pub class_sha256: String,
    pub payload_bytes: usize,
    pub reference_prefix: usize,
    pub fields: usize,
    pub loader_offset: usize,
    pub module_offset: usize,
    pub component_offset: usize,
    pub name_offset: usize,
    pub loader_type: usize,
    pub module_type: usize,
    pub module_loader_offset: usize,
}
fn slot(layout: &super::hierarchy::Layout, owner: usize, name: &str, desc: &str) -> Result<usize> {
    let fields: Vec<_> = layout
        .fields
        .iter()
        .filter(|f| {
            f.member.owner == owner
                && f.member.name == name
                && f.member.descriptor == desc
                && f.reference
                && f.storage_bytes == 8
        })
        .collect();
    ensure!(fields.len() == 1, "Missing/ambiguous source field {name}");
    Ok(fields[0].offset)
}
#[derive(Serialize)]
pub struct Row {
    pub type_id: usize,
    pub component: Option<usize>,
    pub superclass: Option<usize>,
    pub loader: usize,
    pub module: usize,
    pub flags: u32,
    pub raw_access: u16,
    pub major: u16,
}
#[derive(Serialize)]
pub struct Module {
    pub id: usize,
    pub name: Option<String>,
    pub loader: usize,
}
#[derive(Serialize)]
pub struct Native {
    pub method: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub operation: u32,
    pub assembly_unit: usize,
}
pub const SPECS: [(&str, &str, &str, u16, u32); 9] = [
    (
        "java/lang/Object",
        "getClass",
        "()Ljava/lang/Class;",
        0x111,
        0,
    ),
    ("java/lang/Class", "isInterface", "()Z", 0x101, 1),
    ("java/lang/Class", "isArray", "()Z", 0x101, 2),
    ("java/lang/Class", "isPrimitive", "()Z", 0x101, 3),
    ("java/lang/Class", "isHidden", "()Z", 0x101, 4),
    (
        "java/lang/Class",
        "getSuperclass",
        "()Ljava/lang/Class;",
        0x101,
        5,
    ),
    (
        "java/lang/Class",
        "isAssignableFrom",
        "(Ljava/lang/Class;)Z",
        0x101,
        6,
    ),
    (
        "java/lang/Class",
        "isInstance",
        "(Ljava/lang/Object;)Z",
        0x101,
        7,
    ),
    (
        "java/lang/Class",
        "initClassName",
        "()Ljava/lang/String;",
        0x102,
        8,
    ),
];
pub(super) fn native_body(method: usize, op: u32) -> String {
    if op == 8 {
        return format!(
            ".code\nboom_m{method} PROC\n jmp boom_m{method}_native\nboom_m{method} ENDP\nboom_m{method}_native PROC\n lea r8,boom_java_class_pool\n lea r9,boom_java_class_name_pool\n jmp boom_java_class_name\nboom_m{method}_native ENDP\n"
        );
    }
    format!(
        ".code\nboom_m{method} PROC\n jmp boom_m{method}_native\nboom_m{method} ENDP\nboom_m{method}_native PROC\n lea r8,boom_java_class_pool\n mov r9d,{op}\n jmp boom_java_class_query\nboom_m{method}_native ENDP\n"
    )
}
pub(super) fn literal_body(label: &str, id: usize) -> String {
    format!(
        ".code\n{label} PROC\n lea rdx,boom_java_class_pool\n mov r8d,{id}\n jmp boom_java_class_load\n{label} ENDP\n"
    )
}
#[derive(Serialize)]
pub struct Summary {
    pub name_factory: super::batch_class_names::Summary,
    pub abi: u32,
    pub context_bytes: usize,
    pub type_capacity: usize,
    pub provided_types: usize,
    pub literal_sites: usize,
    pub generated_sites: usize,
    pub source_native_methods: usize,
    pub root_cells: usize,
    pub reverse_slots: usize,
    pub loader_keys: Vec<String>,
    pub modules: Vec<Module>,
    pub source_shape: Shape,
    pub kernel_sha256: BTreeMap<String, String>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub class_initialization_executed: bool,
    pub class_native_registration_provided: bool,
    pub module_bootstrap_completed: bool,
    pub automatic_gc: bool,
    pub linked: bool,
}
pub(super) fn generate(
    catalog: &Catalog,
    layouts: &[Layout],
    metadata: &batch_metadata::Summary,
    strings: &super::batch_literals::Summary,
    mut sites: BTreeMap<String, Site>,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let class_id = catalog.lookup("bootstrap", "java/lang/Class")?;
    let class = &catalog.nodes[class_id];
    ensure!(
        class.origin.source_id == "jdk:java.base"
            && class.origin.generated.is_none()
            && class.access == 0x31
            && class.superclass == Some(catalog.root_object()?),
        "Class factory requires original final bootstrap Class"
    );
    let layout = layouts[class_id]
        .candidate
        .as_ref()
        .context("Missing source Class layout")?;
    let module_type = catalog.lookup("bootstrap", "java/lang/Module")?;
    let module_layout = layouts[module_type]
        .candidate
        .as_ref()
        .context("Missing source Module layout")?;
    let shape = Shape {
        class_id,
        class_sha256: class.origin.sha256.clone(),
        payload_bytes: layout.payload_bytes,
        reference_prefix: layout.reference_prefix,
        fields: layout.fields.len(),
        loader_offset: slot(layout, class_id, "classLoader", "Ljava/lang/ClassLoader;")?,
        module_offset: slot(layout, class_id, "module", "Ljava/lang/Module;")?,
        component_offset: slot(layout, class_id, "componentType", "Ljava/lang/Class;")?,
        name_offset: slot(layout, class_id, "name", "Ljava/lang/String;")?,
        loader_type: catalog.lookup("bootstrap", "java/lang/ClassLoader")?,
        module_type,
        module_loader_offset: slot(
            module_layout,
            module_type,
            "loader",
            "Ljava/lang/ClassLoader;",
        )?,
    };
    for (name, desc, access) in [
        ("classLoader", "Ljava/lang/ClassLoader;", 0x12),
        ("componentType", "Ljava/lang/Class;", 0x12),
        ("module", "Ljava/lang/Module;", 0x82),
        ("name", "Ljava/lang/String;", 0x82),
    ] {
        ensure!(
            class
                .fields
                .iter()
                .any(|f| f.name == name && f.descriptor == desc && f.access == access),
            "Source Class VM field contract changed: {name}"
        );
    }
    let mut archive = ZipArchive::new(fs::File::open(&metadata.index.path)?)?;
    let mut text = String::new();
    archive.by_name("types.jsonl")?.read_to_string(&mut text)?;
    let types: BTreeMap<usize, TypeRecord> = text
        .lines()
        .map(|l| -> Result<_> {
            let t: TypeRecord = serde_json::from_str(l)?;
            Ok((t.id, t))
        })
        .collect::<Result<_>>()?;
    let mut loader_keys = vec!["bootstrap".to_string()];
    let loaders: BTreeSet<_> = types.values().map(|t| t.defining_loader.clone()).collect();
    loader_keys.extend(loaders.into_iter().filter(|l| l != "bootstrap"));
    ensure!(
        loader_keys.len() <= 65536,
        "Class loader identity budget exceeded"
    );
    let loader_ids: BTreeMap<_, _> = loader_keys
        .iter()
        .enumerate()
        .map(|(i, l)| (l.clone(), i))
        .collect();
    let mut module_keys = BTreeSet::new();
    for ty in types.values().filter(|t| matches!(t.kind, 1 | 2)) {
        let n = &catalog.nodes[ty.id];
        module_keys.insert((
            ty.defining_loader.clone(),
            n.origin.source_id.strip_prefix("jdk:").map(str::to_string),
        ));
    }
    let base = ("bootstrap".to_string(), Some("java.base".to_string()));
    module_keys.remove(&base);
    let keys: Vec<_> = std::iter::once(base).chain(module_keys).collect();
    ensure!(keys.len() <= 65536, "Class module identity budget exceeded");
    let module_ids: BTreeMap<_, _> = keys
        .iter()
        .cloned()
        .enumerate()
        .map(|(i, k)| (k, i))
        .collect();
    let modules: Vec<_> = keys
        .iter()
        .enumerate()
        .map(|(id, (loader, name))| Module {
            id,
            name: name.clone(),
            loader: loader_ids[loader],
        })
        .collect();
    let mut rows = BTreeMap::<usize, Row>::new();
    for t in types.values().filter(|t| t.kind != 3) {
        let loader = loader_ids[&t.defining_loader];
        let (module, access, major, superclass) = if t.kind == 0 {
            (0, 0, 0, None)
        } else {
            let n = &catalog.nodes[t.id];
            ensure!(
                n.origin.generated.is_none(),
                "Hidden/generated Class metadata requires its own generation contract"
            );
            let module = module_ids[&(
                t.defining_loader.clone(),
                n.origin.source_id.strip_prefix("jdk:").map(str::to_string),
            )];
            (
                module,
                n.access,
                n.origin.java_class_major,
                if t.kind == 2 { None } else { n.superclass },
            )
        };
        rows.insert(
            t.id,
            Row {
                type_id: t.id,
                component: None,
                superclass,
                loader,
                module,
                flags: u32::from(loader == 0 && module == 0),
                raw_access: access,
                major,
            },
        );
    }
    let mut arrays: Vec<_> = types.values().filter(|t| t.kind == 3).collect();
    arrays.sort_by_key(|t| t.name.bytes().take_while(|b| *b == b'[').count());
    for t in arrays {
        let component = t
            .parent_component
            .context("Source array has no component")?;
        let base = rows
            .get(&component)
            .context("Array component Class metadata unavailable")?;
        let loader = base.loader;
        let module = base.module;
        ensure!(
            loader_keys[loader] == t.defining_loader,
            "Array Class loader differs from component"
        );
        rows.insert(
            t.id,
            Row {
                type_id: t.id,
                component: Some(component),
                superclass: Some(catalog.root_object()?),
                loader,
                module,
                flags: u32::from(loader == 0 && module == 0),
                raw_access: 0,
                major: 0,
            },
        );
    }
    let count = metadata.type_capacity;
    let reverse_slots = (count * 2).next_power_of_two();
    ensure!(
        count <= 0x100000 && reverse_slots <= 0x200000,
        "Normal Class registry budget exceeded"
    );
    let mut assembly = format!(
        ".data\nALIGN 8\nPUBLIC boom_java_class_pool\nboom_java_class_pool DWORD 04A434C53h,1,0,{count}\n QWORD OFFSET boom_java_class_roots,OFFSET boom_java_class_records,OFFSET boom_layout{class_id},OFFSET boom_runtime_type_map,OFFSET boom_heap_ptr,OFFSET boom_java_class_loader_roots,OFFSET boom_java_class_module_roots,OFFSET boom_java_class_reverse\n DWORD {mask},{loaders},{mods},1\n DWORD {lo},{mo},{co},{class_id}\n QWORD OFFSET boom_t{lt},OFFSET boom_t{mt},OFFSET boom_java_class_module_loaders\n DWORD {mlo},0\n.const\nPUBLIC boom_java_class_root_count\nboom_java_class_root_count QWORD {root_count}\nboom_java_class_module_loaders LABEL DWORD\n",
        mask = reverse_slots - 1,
        loaders = loader_keys.len(),
        mods = modules.len(),
        lo = shape.loader_offset,
        mo = shape.module_offset,
        co = shape.component_offset,
        lt = shape.loader_type,
        mt = shape.module_type,
        mlo = shape.module_loader_offset,
        root_count = count + loader_keys.len() + modules.len()
    );
    for m in &modules {
        assembly.push_str(&format!(" DWORD {}\n", m.loader));
    }
    assembly.push_str(
        ".data?\nALIGN 8\nPUBLIC boom_java_class_roots\nboom_java_class_roots LABEL QWORD\n",
    );
    assembly.push_str(&format!(" QWORD {count} DUP(?)\nPUBLIC boom_java_class_loader_roots\nboom_java_class_loader_roots QWORD {} DUP(?)\nPUBLIC boom_java_class_module_roots\nboom_java_class_module_roots QWORD {} DUP(?)\nboom_java_class_reverse QWORD {} DUP(?)\n.const\nALIGN 8\nPUBLIC boom_java_class_records\nboom_java_class_records LABEL BYTE\n",loader_keys.len(),modules.len(),reverse_slots*2));
    for id in 0..count {
        if let Some(r) = rows.get(&id) {
            assembly.push_str(&format!(" QWORD OFFSET boom_t{id}\n DWORD {component},{parent},{loader},{module},{flags},{access},{major},0\n QWORD 0\n",component=r.component.unwrap_or(u32::MAX as usize),parent=r.superclass.unwrap_or(u32::MAX as usize),loader=r.loader,module=r.module,flags=r.flags,access=r.raw_access,major=r.major));
        } else {
            assembly.push_str(" QWORD 0\n DWORD 0,0,0,0,0,0,0,0\n QWORD 0\n");
        }
    }
    let (name_factory, names_body, name_bindings, canonical_names) =
        super::batch_class_names::generate(&types, count, shape.name_offset, strings)?;
    assembly.push_str(&names_body);
    let mut natives = vec![];
    let mut provided = BTreeSet::new();
    for (owner, name, desc, flags, op) in SPECS {
        let id = catalog.lookup("bootstrap", owner)?;
        let n = &catalog.nodes[id];
        ensure!(
            n.origin.source_id == "jdk:java.base" && n.origin.generated.is_none(),
            "Class core native requires original java.base source"
        );
        let (index, m) = n
            .methods
            .iter()
            .enumerate()
            .find(|(_, m)| m.name == name && m.descriptor == desc)
            .context("Missing source Class core native")?;
        ensure!(m.access == flags, "Source Class core native access changed");
        let method = n.method_ids[index];
        assembly.push_str(&native_body(method, op));
        provided.insert(method);
        natives.push(Native {
            method,
            class_id: id,
            class_sha256: n.origin.sha256.clone(),
            name: name.into(),
            descriptor: desc.into(),
            access: flags,
            operation: op,
            assembly_unit: 0,
        });
    }
    for s in sites.values_mut() {
        if rows.contains_key(&s.type_id) {
            s.assembly_unit = Some(0);
            assembly.push_str(&literal_body(&s.label, s.type_id));
        } else {
            s.diagnostic = Some("Source Class type metadata unavailable".into());
        }
    }
    let directory = output.join("class-literals");
    fs::create_dir_all(&directory)?;
    let unit = write_unit(
        &Symbols::new()?,
        &directory.join("0000.asm"),
        0,
        &assembly,
        assemble,
    )?;
    let path = directory.join("index.zip");
    let mut temp = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temp.as_file_mut());
        let options =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, records) in [
            (
                "types.jsonl",
                rows.values()
                    .map(serde_json::to_value)
                    .collect::<std::result::Result<Vec<_>, _>>()?,
            ),
            (
                "sites.jsonl",
                sites
                    .values()
                    .map(serde_json::to_value)
                    .collect::<std::result::Result<Vec<_>, _>>()?,
            ),
            (
                "methods.jsonl",
                natives
                    .iter()
                    .map(serde_json::to_value)
                    .collect::<std::result::Result<Vec<_>, _>>()?,
            ),
            (
                "names.jsonl",
                name_bindings
                    .iter()
                    .map(serde_json::to_value)
                    .collect::<std::result::Result<Vec<_>, _>>()?,
            ),
            (
                "canonical_names.jsonl",
                canonical_names
                    .iter()
                    .map(serde_json::to_value)
                    .collect::<std::result::Result<Vec<_>, _>>()?,
            ),
        ] {
            zip.start_file(name, options)?;
            for r in records {
                serde_json::to_writer(&mut zip, &r)?;
                zip.write_all(b"\n")?;
            }
        }
        zip.finish()?;
    }
    temp.persist(&path).map_err(|e| e.error)?;
    Ok((
        Summary {
            name_factory,
            abi: 1,
            context_bytes: 32,
            type_capacity: count,
            provided_types: rows.len(),
            literal_sites: sites.len(),
            generated_sites: sites.values().filter(|s| s.assembly_unit.is_some()).count(),
            source_native_methods: natives.len(),
            root_cells: count + loader_keys.len() + modules.len(),
            reverse_slots,
            loader_keys,
            modules,
            source_shape: shape,
            kernel_sha256: BTreeMap::from([(
                "native/runtime/java_classes.asm".into(),
                files::digest_bytes(include_bytes!("../../native/runtime/java_classes.asm")).sha256,
            )]),
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
            class_initialization_executed: false,
            class_native_registration_provided: false,
            module_bootstrap_completed: false,
            automatic_gc: false,
            linked: false,
        },
        provided,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn literal_does_not_initialize_represented_class() {
        let b = literal_body("boom_batch_literal_load_7_3", 42);
        assert!(b.contains("mov r8d,42\n jmp boom_java_class_load") && !b.contains("class_ensure"));
    }
    #[test]
    fn native_queries_are_instance_entries_and_never_fake_registration() {
        for (_, _, _, flags, op) in SPECS {
            assert_eq!(flags & 8, 0);
            let b = native_body(6, op);
            assert!(
                b.contains(if op == 8 {
                    "boom_java_class_name"
                } else {
                    "boom_java_class_query"
                }) && !b.contains("class_ensure")
            );
        }
        assert!(
            !SPECS
                .iter()
                .any(|(_, name, _, _, _)| *name == "registerNatives")
        );
    }
}
