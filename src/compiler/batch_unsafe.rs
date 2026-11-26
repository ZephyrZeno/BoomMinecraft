//! Normal-source Unsafe bootstrap bindings. Unsupported natives stay unresolved.
use super::{
    batch_catalog::Catalog,
    batch_class_bootstrap::Method,
    batch_class_state,
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    batch_metadata::{self, TypeRecord},
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{
    collections::BTreeSet,
    fmt::Write as _,
    fs,
    io::{Read, Write},
    path::Path,
};
use zip::{ZipArchive, ZipWriter, write::SimpleFileOptions};

pub const OWNER: &str = "jdk/internal/misc/Unsafe";
pub const CONSTANTS: &str = "jdk/internal/misc/UnsafeConstants";
pub const SPECS: [(&str, &str, u16, u32); 4] = [
    ("registerNatives", "()V", 0x10a, 0),
    ("arrayBaseOffset0", "(Ljava/lang/Class;)I", 0x102, 1),
    ("arrayIndexScale0", "(Ljava/lang/Class;)I", 0x102, 2),
    ("fullFence", "()V", 0x101, 3),
];
pub const FIELDS: [(&str, &str); 5] = [
    ("ADDRESS_SIZE0", "I"),
    ("PAGE_SIZE", "I"),
    ("BIG_ENDIAN", "Z"),
    ("UNALIGNED_ACCESS", "Z"),
    ("DATA_CACHE_LINE_FLUSH_SIZE", "I"),
];

#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_bytes: usize,
    pub native_methods: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub constants_class_id: usize,
    pub constants_class_sha256: String,
    pub constants_initializer: usize,
    pub constants_initializer_sha256: String,
    pub source_native_declarations: usize,
    pub registered_prelinked_methods: usize,
    pub type_capacity: usize,
    pub kernel_sha256: String,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub unsupported_natives_remain_unprovided: bool,
    pub original_initialization_executed: bool,
    pub game_started: bool,
}

pub(super) fn source_methods(catalog: &Catalog) -> Result<Vec<Method>> {
    let class_id = catalog.lookup("bootstrap", OWNER)?;
    let node = &catalog.nodes[class_id];
    ensure!(
        node.origin.source_id == "jdk:java.base"
            && node.origin.generated.is_none()
            && node.access == 0x31,
        "Unsafe requires original java.base source"
    );
    let mut result = vec![];
    for (name, descriptor, access, operation) in SPECS {
        let i = node
            .methods
            .iter()
            .position(|m| m.name == name && m.descriptor == descriptor)
            .context("Missing source Unsafe native")?;
        ensure!(
            node.methods[i].access == access,
            "Source Unsafe native flags differ"
        );
        result.push(Method {
            method: node.method_ids[i],
            class_id,
            class_sha256: node.origin.sha256.clone(),
            name: name.into(),
            descriptor: descriptor.into(),
            access,
            operation,
            assembly_unit: 0,
        });
    }
    let constants = &catalog.nodes[catalog.lookup("bootstrap", CONSTANTS)?];
    ensure!(
        constants.origin.source_id == "jdk:java.base"
            && constants.origin.generated.is_none()
            && constants.access == 0x30
            && constants.fields.len() == FIELDS.len(),
        "UnsafeConstants source differs"
    );
    for (field, (name, descriptor)) in constants.fields.iter().zip(FIELDS) {
        ensure!(
            field.name == name && field.descriptor == descriptor && field.access == 0x18,
            "UnsafeConstants fields differ"
        );
    }
    let i = constants
        .methods
        .iter()
        .position(|m| m.name == "<clinit>" && m.descriptor == "()V")
        .context("Missing original UnsafeConstants initializer")?;
    ensure!(
        constants.methods[i].access == 8,
        "UnsafeConstants initializer flags differ"
    );
    Ok(result)
}

pub(super) fn native_body(method: usize, class: usize, operation: u32) -> String {
    // Use the common source-init/pending-error wrapper, preserving its ABI.
    super::batch_class_bootstrap::native_adapter(
        method,
        class,
        "boom_java_unsafe_pool",
        "boom_java_unsafe",
        operation,
    )
}

pub(super) fn data(class: usize, constants: usize, scales: &[u32], methods: &[Method]) -> String {
    let mut text = String::from(
        ".const\nALIGN 8\nPUBLIC boom_java_unsafe_bindings\nboom_java_unsafe_bindings LABEL BYTE\n",
    );
    for m in methods.iter().filter(|m| m.operation != 0) {
        writeln!(
            text,
            " DWORD {},{}\n QWORD OFFSET boom_m{}_native\n DWORD {},0",
            m.operation, m.method, m.method, m.access
        )
        .unwrap();
    }
    text.push_str("PUBLIC boom_java_unsafe_scales\nboom_java_unsafe_scales LABEL DWORD\n");
    for part in scales.chunks(16) {
        writeln!(
            text,
            " DWORD {}",
            part.iter()
                .map(u32::to_string)
                .collect::<Vec<_>>()
                .join(",")
        )
        .unwrap();
    }
    text.push_str("ALIGN 8\nPUBLIC boom_java_unsafe_constant_cells\nboom_java_unsafe_constant_cells LABEL QWORD\n");
    for i in 0..FIELDS.len() {
        writeln!(text, " QWORD OFFSET boom_s{constants}_{i}").unwrap();
    }
    writeln!(text, ".data\nALIGN 8\nPUBLIC boom_java_unsafe_pool\nboom_java_unsafe_pool DWORD 04A554E53h,1,0,3\n QWORD OFFSET boom_java_class_pool,OFFSET boom_runtime_type_map,OFFSET boom_heap_ptr,OFFSET boom_layout{class}\n QWORD OFFSET boom_java_unsafe_bindings,OFFSET boom_java_unsafe_scales\n DWORD {},{class}\n QWORD OFFSET boom_java_unsafe_constant_cells",scales.len()).unwrap();
    text
}

pub(super) fn generate(
    catalog: &Catalog,
    metadata: &batch_metadata::Summary,
    state: &batch_class_state::Summary,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let methods = source_methods(catalog)?;
    let class_id = methods[0].class_id;
    let constants_class_id = catalog.lookup("bootstrap", CONSTANTS)?;
    let node = &catalog.nodes[constants_class_id];
    let init = node
        .methods
        .iter()
        .position(|m| m.name == "<clinit>")
        .unwrap();
    let mut states = ZipArchive::new(fs::File::open(&state.index.path)?)?;
    let mut state_text = String::new();
    states
        .by_name("classes.jsonl")?
        .read_to_string(&mut state_text)?;
    let mut constants_state = None;
    for line in state_text.lines() {
        let value: serde_json::Value = serde_json::from_str(line)?;
        if value["class_id"].as_u64() == Some(constants_class_id as u64) {
            constants_state = Some(value);
            break;
        }
    }
    let constants_state = constants_state.context("Missing UnsafeConstants source state")?;
    ensure!(
        constants_state["diagnostic"].is_null()
            && constants_state["initializer"]["assembly_emitted"].as_bool() == Some(true)
            && constants_state["vm_post_initializer"].as_str() == Some("unsafe_constants"),
        "UnsafeConstants original initializer/post-hook is not available"
    );
    let constants_initializer_sha256 = constants_state["initializer"]["code_sha256"]
        .as_str()
        .context("Missing UnsafeConstants original Code digest")?
        .to_string();
    let mut z = ZipArchive::new(fs::File::open(&metadata.index.path)?)?;
    let mut input = String::new();
    z.by_name("types.jsonl")?.read_to_string(&mut input)?;
    let types = input
        .lines()
        .map(serde_json::from_str::<TypeRecord>)
        .collect::<std::result::Result<Vec<_>, _>>()?;
    ensure!(
        types.len() == metadata.provided_types
            && types.iter().all(|t| t.id < metadata.type_capacity)
            && types.windows(2).all(|w| w[0].id < w[1].id),
        "Unsafe type identity coverage differs"
    );
    let mut scales = vec![0_u32; metadata.type_capacity];
    for t in &types {
        if t.kind == 3 {
            scales[t.id] = match t.name.as_str() {
                "[Z" | "[B" => 1,
                "[C" | "[S" => 2,
                "[I" | "[F" => 4,
                _ => 8,
            };
        }
    }
    let mut assembly = data(class_id, constants_class_id, &scales, &methods);
    for m in &methods {
        assembly.push_str(&native_body(m.method, class_id, m.operation));
    }
    let directory = output.join("unsafe-bootstrap");
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
        let mut z = ZipWriter::new(temp.as_file_mut());
        let options =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        z.start_file("methods.jsonl", options)?;
        for row in &methods {
            serde_json::to_writer(&mut z, row)?;
            z.write_all(b"\n")?;
        }
        z.start_file("scales.json", options)?;
        serde_json::to_writer(&mut z, &scales)?;
        z.finish()?;
    }
    temp.persist(&path).map_err(|e| e.error)?;
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            pool_bytes: 80,
            native_methods: methods.len(),
            class_id,
            class_sha256: catalog.nodes[class_id].origin.sha256.clone(),
            constants_class_id,
            constants_class_sha256: node.origin.sha256.clone(),
            constants_initializer: node.method_ids[init],
            constants_initializer_sha256,
            source_native_declarations: catalog.nodes[class_id]
                .methods
                .iter()
                .filter(|m| m.access & 0x100 != 0)
                .count(),
            registered_prelinked_methods: 3,
            type_capacity: scales.len(),
            kernel_sha256: files::digest(Path::new("native/runtime/java_unsafe.asm"))?.sha256,
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
            unsupported_natives_remain_unprovided: true,
            original_initialization_executed: false,
            game_started: false,
        },
        methods.iter().map(|m| m.method).collect(),
    ))
}
