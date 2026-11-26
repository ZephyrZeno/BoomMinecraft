//! Source-bound bootstrap name lookup; guest lookup and initialization use MASM.
use super::{
    batch_catalog::Catalog,
    batch_class_bootstrap::Method,
    batch_class_state,
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    batch_frames::native_adapter,
    batch_literals,
    batch_metadata::{self, TypeRecord},
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Result, ensure};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt::Write as _,
    fs,
    io::{Read, Write},
    path::Path,
};
use zip::{ZipArchive, ZipWriter, write::SimpleFileOptions};

pub(super) fn source_methods(catalog: &Catalog) -> Result<Vec<Method>> {
    let mut out = vec![];
    for (owner, name, desc, operation) in [
        (
            "java/lang/Class",
            "forName0",
            "(Ljava/lang/String;ZLjava/lang/ClassLoader;Ljava/lang/Class;)Ljava/lang/Class;",
            0,
        ),
        (
            "java/lang/ClassLoader",
            "findBootstrapClass",
            "(Ljava/lang/String;)Ljava/lang/Class;",
            1,
        ),
    ] {
        let class_id = catalog.lookup("bootstrap", owner)?;
        let c = &catalog.nodes[class_id];
        ensure!(
            c.origin.source_id == "jdk:java.base" && c.origin.generated.is_none(),
            "Name lookup requires original java.base owner"
        );
        let found: Vec<_> = c
            .methods
            .iter()
            .enumerate()
            .filter(|(_, m)| m.name == name && m.descriptor == desc)
            .collect();
        ensure!(
            found.len() == 1 && found[0].1.access == 0x10a,
            "Name lookup native declaration changed"
        );
        out.push(Method {
            method: c.method_ids[found[0].0],
            class_id,
            class_sha256: c.origin.sha256.clone(),
            name: name.into(),
            descriptor: desc.into(),
            access: 0x10a,
            operation,
            assembly_unit: 0,
        });
    }
    Ok(out)
}
#[derive(Serialize)]
pub struct Name {
    pub type_id: usize,
    pub utf16: Vec<u16>,
    pub java_hash: u32,
    pub offset: usize,
    pub flags: u32,
}
#[derive(Serialize)]
pub struct Initialization {
    pub class_id: usize,
    pub source_sha256: String,
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_bytes: usize,
    pub record_bytes: usize,
    pub initialization_record_bytes: usize,
    pub native_methods: usize,
    pub type_capacity: usize,
    pub names: usize,
    pub name_units: usize,
    pub initializers: usize,
    pub kernel_sha256: BTreeMap<String, String>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub bootstrap_loader: bool,
    pub custom_loaders: bool,
    pub dynamic_array_types: bool,
    pub throwable_objects_materialized: bool,
    pub original_initialization_executed: bool,
    pub automatic_gc: bool,
    pub game_started: bool,
}
pub(super) fn generate(
    catalog: &Catalog,
    metadata: &batch_metadata::Summary,
    states: &batch_class_state::Summary,
    strings: &batch_literals::Summary,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let methods = source_methods(catalog)?;
    let mut z = ZipArchive::new(fs::File::open(&metadata.index.path)?)?;
    let mut text = String::new();
    z.by_name("types.jsonl")?.read_to_string(&mut text)?;
    let types: BTreeMap<usize, TypeRecord> = text
        .lines()
        .map(|l| {
            let t: TypeRecord = serde_json::from_str(l)?;
            Ok((t.id, t))
        })
        .collect::<Result<_>>()?;
    let mut names = BTreeMap::<Vec<u16>, (usize, u32)>::new();
    for (id, c) in catalog.nodes.iter().enumerate() {
        if c.origin.loader != "bootstrap"
            || c.origin.generated.is_some()
            || c.key.name == "module-info"
        {
            continue;
        }
        names.insert(
            c.key.name.replace('/', ".").encode_utf16().collect(),
            (id, u32::from(types.contains_key(&id))),
        );
    }
    for t in types
        .values()
        .filter(|t| t.defining_loader == "bootstrap" && t.kind == 3)
    {
        ensure!(
            names
                .insert(t.name.replace('/', ".").encode_utf16().collect(), (t.id, 3))
                .is_none(),
            "Duplicate bootstrap lookup name"
        );
    }
    let mut names: Vec<_> = names
        .into_iter()
        .map(|(utf16, (type_id, flags))| Name {
            type_id,
            java_hash: utf16
                .iter()
                .fold(0u32, |h, u| h.wrapping_mul(31).wrapping_add(u32::from(*u))),
            utf16,
            flags,
            offset: 0,
        })
        .collect();
    names.sort_by(|a, b| {
        a.java_hash
            .cmp(&b.java_hash)
            .then_with(|| a.utf16.cmp(&b.utf16))
    });
    let mut units_count = 0;
    for n in &mut names {
        ensure!(
            !n.utf16.is_empty() && n.utf16.len() <= 65535,
            "Lookup name length invalid"
        );
        n.offset = units_count;
        units_count += n.utf16.len();
    }
    let mut z = ZipArchive::new(fs::File::open(&states.index.path)?)?;
    text.clear();
    z.by_name("classes.jsonl")?.read_to_string(&mut text)?;
    let mut initializers = vec![];
    for line in text.lines() {
        let state: serde_json::Value = serde_json::from_str(line)?;
        let id = state["class_id"].as_u64().unwrap() as usize;
        if types
            .get(&id)
            .is_some_and(|t| matches!(t.kind, 1 | 2) && t.defining_loader == "bootstrap")
            && state["diagnostic"].is_null()
        {
            initializers.push(Initialization {
                class_id: id,
                source_sha256: catalog.nodes[id].origin.sha256.clone(),
            });
        }
    }
    let capacity = metadata.type_capacity;
    let class = methods[0].class_id;
    let loader = methods[1].class_id;
    let s = &strings.source_layout;
    let mut body = format!(
        ".const\nALIGN 8\nPUBLIC boom_java_class_lookup_pool\nboom_java_class_lookup_pool DWORD 04A43464Eh,1,{capacity},{}\n QWORD OFFSET boom_java_class_pool,OFFSET boom_java_string_literal_pool,OFFSET boom_java_class_bootstrap_pool,OFFSET boom_java_class_lookup_rows\n QWORD OFFSET boom_java_class_initialization_map,OFFSET boom_heap_ptr\n DWORD {},{},{},0\n QWORD OFFSET boom_java_class_lookup_names\n DWORD {units_count},32,16,{class},{loader},1\n QWORD 0,0\nPUBLIC boom_java_class_lookup_rows\nboom_java_class_lookup_rows LABEL BYTE\n",
        names.len(),
        s.value_offset,
        s.coder_offset,
        s.class_id
    );
    for n in &names {
        writeln!(
            body,
            " DWORD {},{},0{:08X}h,{},{},0\n QWORD 0",
            n.offset,
            n.utf16.len(),
            n.java_hash,
            n.type_id,
            n.flags
        )?;
    }
    body.push_str(
        "ALIGN 2\nPUBLIC boom_java_class_lookup_names\nboom_java_class_lookup_names LABEL WORD\n",
    );
    for n in &names {
        for chunk in n.utf16.chunks(16) {
            body.push_str(" WORD ");
            body.push_str(
                &chunk
                    .iter()
                    .map(|u| format!("0{u:04X}h"))
                    .collect::<Vec<_>>()
                    .join(","),
            );
            body.push('\n');
        }
    }
    for m in &methods {
        body.push_str(&native_adapter(
            m.method,
            m.class_id,
            "boom_java_class_lookup_pool",
            "boom_java_class_lookup",
            m.operation,
        ));
    }
    let mut init = String::from(
        ".const\nALIGN 8\nPUBLIC boom_java_class_initialization_map\nboom_java_class_initialization_map LABEL QWORD\n",
    );
    let ids: BTreeSet<_> = initializers.iter().map(|r| r.class_id).collect();
    for id in 0..capacity {
        if ids.contains(&id) {
            writeln!(init, " QWORD OFFSET boom_class{id},0")?;
        } else {
            init.push_str(" QWORD 0,0\n");
        }
    }
    let dir = output.join("class-lookup");
    fs::create_dir_all(&dir)?;
    let symbols = Symbols::new()?;
    let units = vec![
        write_unit(&symbols, &dir.join("0000.asm"), 0, &body, assemble)?,
        write_unit(&symbols, &dir.join("0001.asm"), 1, &init, assemble)?,
    ];
    let path = dir.join("index.zip");
    let mut tmp = tempfile::NamedTempFile::new_in(&dir)?;
    {
        let mut z = ZipWriter::new(tmp.as_file_mut());
        for (name, rows) in [
            (
                "methods.jsonl",
                methods
                    .iter()
                    .map(serde_json::to_value)
                    .collect::<std::result::Result<Vec<_>, _>>()?,
            ),
            (
                "names.jsonl",
                names
                    .iter()
                    .map(serde_json::to_value)
                    .collect::<std::result::Result<Vec<_>, _>>()?,
            ),
            (
                "initializers.jsonl",
                initializers
                    .iter()
                    .map(serde_json::to_value)
                    .collect::<std::result::Result<Vec<_>, _>>()?,
            ),
        ] {
            z.start_file(
                name,
                SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
            )?;
            for row in rows {
                serde_json::to_writer(&mut z, &row)?;
                z.write_all(b"\n")?;
            }
        }
        z.finish()?;
    }
    tmp.persist(&path).map_err(|e| e.error)?;
    let kernel_sha256 = [
        "java_class_lookup.asm",
        "java_classes.asm",
        "java_class_bootstrap.asm",
        "classes32.asm",
        "objects.asm",
        "heap.asm",
        "frames.asm",
    ]
    .into_iter()
    .map(|n| {
        let p = format!("native/runtime/{n}");
        Ok((p.clone(), files::digest(Path::new(&p))?.sha256))
    })
    .collect::<Result<_>>()?;
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            pool_bytes: 128,
            record_bytes: 32,
            initialization_record_bytes: 16,
            native_methods: 2,
            type_capacity: capacity,
            names: names.len(),
            name_units: units_count,
            initializers: initializers.len(),
            kernel_sha256,
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units,
            bootstrap_loader: true,
            custom_loaders: false,
            dynamic_array_types: false,
            throwable_objects_materialized: false,
            original_initialization_executed: false,
            automatic_gc: false,
            game_started: false,
        },
        methods.iter().map(|m| m.method).collect(),
    ))
}
