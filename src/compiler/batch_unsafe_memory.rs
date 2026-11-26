//! One typed heap-memory/atomic rule generates every matching original native.
use super::{
    batch_catalog::Catalog,
    batch_class_bootstrap::{Method, native_adapter},
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Result, ensure};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Write,
    path::Path,
};
use zip::{ZipWriter, write::SimpleFileOptions};

const OWNER: &str = "jdk/internal/misc/Unsafe";
const TYPES: [(&str, &str, u32); 9] = [
    ("Boolean", "Z", 1),
    ("Byte", "B", 2),
    ("Char", "C", 3),
    ("Short", "S", 4),
    ("Int", "I", 5),
    ("Long", "J", 6),
    ("Float", "F", 7),
    ("Double", "D", 8),
    ("Reference", "Ljava/lang/Object;", 9),
];

pub(super) fn source_methods(catalog: &Catalog) -> Result<Vec<Method>> {
    let class_id = catalog.lookup("bootstrap", OWNER)?;
    let c = &catalog.nodes[class_id];
    ensure!(
        c.origin.source_id == "jdk:java.base" && c.origin.generated.is_none() && c.access == 0x31,
        "Typed Unsafe requires original final java.base source"
    );
    let mut specs = vec![];
    for (name, ty, kind) in TYPES {
        for action in 0..4 {
            let verb = if action & 1 == 0 { "get" } else { "put" };
            let suffix = if action >= 2 { "Volatile" } else { "" };
            let descriptor = if action & 1 == 0 {
                format!("(Ljava/lang/Object;J){ty}")
            } else {
                format!("(Ljava/lang/Object;J{ty})V")
            };
            specs.push((
                format!("{verb}{name}{suffix}"),
                descriptor,
                0x101,
                action * 16 + kind,
            ));
        }
        if matches!(kind, 5 | 6 | 9) {
            for action in 4..6 {
                let (verb, result) = if action == 4 {
                    ("compareAndSet", "Z")
                } else {
                    ("compareAndExchange", ty)
                };
                specs.push((
                    format!("{verb}{name}"),
                    format!("(Ljava/lang/Object;J{ty}{ty}){result}"),
                    0x111,
                    action * 16 + kind,
                ));
            }
        }
    }
    let mut methods = vec![];
    for (name, descriptor, access, operation) in specs {
        let found: Vec<_> = c
            .methods
            .iter()
            .enumerate()
            .filter(|(_, m)| m.name == name && m.descriptor == descriptor)
            .collect();
        ensure!(
            found.len() == 1 && found[0].1.access == access,
            "Original typed Unsafe declaration differs: {name}{descriptor}"
        );
        methods.push(Method {
            method: c.method_ids[found[0].0],
            class_id,
            class_sha256: c.origin.sha256.clone(),
            name,
            descriptor,
            access,
            operation,
            assembly_unit: 0,
        });
    }
    ensure!(methods.len() == 42, "Typed Unsafe rule coverage differs");
    Ok(methods)
}

#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub shared_field_pool_bytes: usize,
    pub native_methods: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub source_native_declarations: usize,
    pub kernel_sha256: BTreeMap<String, String>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub field_cookies: bool,
    pub primitive_array_byte_views: bool,
    pub reference_arrays: bool,
    pub unaligned_plain_scalar_access: bool,
    pub unaligned_atomic_access: bool,
    pub off_heap: bool,
    pub vm_thread_id_counter: bool,
    pub vm_thread_id_operations: Vec<u32>,
    pub static_field_base: bool,
    pub automatic_gc: bool,
    pub original_initialization_executed: bool,
    pub game_started: bool,
}

pub(super) fn generate(
    catalog: &Catalog,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let methods = source_methods(catalog)?;
    let class_id = methods[0].class_id;
    let mut body = String::new();
    for m in &methods {
        body.push_str(&native_adapter(
            m.method,
            class_id,
            "boom_java_unsafe_field_pool",
            "boom_java_unsafe_memory",
            m.operation,
        ));
    }
    let directory = output.join("unsafe-memory");
    fs::create_dir_all(&directory)?;
    let unit = write_unit(
        &Symbols::new()?,
        &directory.join("0000.asm"),
        0,
        &body,
        assemble,
    )?;
    let path = directory.join("index.zip");
    let mut tmp = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut z = ZipWriter::new(tmp.as_file_mut());
        z.start_file(
            "methods.jsonl",
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )?;
        for m in &methods {
            serde_json::to_writer(&mut z, m)?;
            z.write_all(b"\n")?;
        }
        z.finish()?;
    }
    tmp.persist(&path).map_err(|e| e.error)?;
    let kernel_sha256 = [
        "java_unsafe_fields.asm",
        "field_address.asm",
        "java_unsafe.asm",
        "objects.asm",
        "heap.asm",
        "runtime_types.asm",
        "runtime_type_index.asm",
        "thread_registry.asm",
    ]
    .into_iter()
    .map(|name| {
        let p = format!("native/runtime/{name}");
        Ok((p.clone(), files::digest(Path::new(&p))?.sha256))
    })
    .collect::<Result<_>>()?;
    let declarations = catalog.nodes[class_id]
        .methods
        .iter()
        .filter(|m| m.access & 0x100 != 0)
        .count();
    let provided = methods.iter().map(|m| m.method).collect();
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            shared_field_pool_bytes: 128,
            native_methods: 42,
            class_id,
            class_sha256: catalog.nodes[class_id].origin.sha256.clone(),
            source_native_declarations: declarations,
            kernel_sha256,
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
            field_cookies: true,
            primitive_array_byte_views: true,
            reference_arrays: true,
            unaligned_plain_scalar_access: true,
            unaligned_atomic_access: false,
            off_heap: false,
            vm_thread_id_counter: true,
            vm_thread_id_operations: vec![6, 38, 70, 86],
            static_field_base: false,
            automatic_gc: false,
            original_initialization_executed: false,
            game_started: false,
        },
        provided,
    ))
}
