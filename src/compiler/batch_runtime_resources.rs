//! Normal-source Runtime CPU/memory adapters to the shared assembly service.
use super::{
    batch_catalog::Catalog,
    batch_class_bootstrap::{Method, native_adapter},
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Write,
    path::Path,
};
use zip::{ZipWriter, write::SimpleFileOptions};

pub const OWNER: &str = "java/lang/Runtime";
pub const SPECS: [(&str, &str, u16, u32); 4] = [
    ("availableProcessors", "()I", 0x101, 0),
    ("freeMemory", "()J", 0x101, 1),
    ("totalMemory", "()J", 0x101, 2),
    ("maxMemory", "()J", 0x101, 3),
];

#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_bytes: usize,
    pub native_methods: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub source_native_declarations: usize,
    pub exact_runtime_receiver: bool,
    pub override_dispatch_complete: bool,
    pub memory_counters: &'static str,
    pub processor_policy: &'static str,
    pub kernel_sha256: BTreeMap<String, String>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub unsupported_natives_remain_unprovided: bool,
    pub original_initialization_executed: bool,
    pub automatic_gc: bool,
    pub game_started: bool,
}

pub(super) fn source_methods(catalog: &Catalog) -> Result<Vec<Method>> {
    let class_id = catalog.lookup("bootstrap", OWNER)?;
    let node = &catalog.nodes[class_id];
    ensure!(
        node.origin.source_id == "jdk:java.base"
            && node.origin.generated.is_none()
            && node.access == 0x21,
        "Runtime resources require original java.base Runtime"
    );
    let constructors: Vec<_> = node.methods.iter().filter(|m| m.name == "<init>").collect();
    ensure!(
        constructors.len() == 1
            && constructors[0].descriptor == "()V"
            && constructors[0].access == 2,
        "Source Runtime constructor contract differs"
    );
    SPECS
        .into_iter()
        .map(|(name, descriptor, access, operation)| {
            let i = node
                .methods
                .iter()
                .position(|m| m.name == name && m.descriptor == descriptor)
                .context("Missing source Runtime resource native")?;
            ensure!(
                node.methods[i].access == access,
                "Source Runtime resource native flags differ"
            );
            Ok(Method {
                method: node.method_ids[i],
                class_id,
                class_sha256: node.origin.sha256.clone(),
                name: name.into(),
                descriptor: descriptor.into(),
                access,
                operation,
                assembly_unit: 0,
            })
        })
        .collect()
}

pub(super) fn generate(
    catalog: &Catalog,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let methods = source_methods(catalog)?;
    let class_id = methods[0].class_id;
    let node = &catalog.nodes[class_id];
    let mut body = format!(
        ".data\nALIGN 8\nPUBLIC boom_java_runtime_pool\nboom_java_runtime_pool DWORD 0544E5552h,1\n QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_t{class_id}\n QWORD 0,0,0,0\n"
    );
    for m in &methods {
        body.push_str(&native_adapter(
            m.method,
            class_id,
            "boom_java_runtime_pool",
            "boom_runtime_resource",
            m.operation,
        ));
    }
    let dir = output.join("runtime-resources");
    fs::create_dir_all(&dir)?;
    let unit = write_unit(&Symbols::new()?, &dir.join("0000.asm"), 0, &body, assemble)?;
    let path = dir.join("index.zip");
    let mut tmp = tempfile::NamedTempFile::new_in(&dir)?;
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
    let kernels = [
        "runtime_resources.asm",
        "heap.asm",
        "runtime_types.asm",
        "runtime_type_index.asm",
    ]
    .into_iter()
    .map(|n| {
        let p = format!("native/runtime/{n}");
        Ok((p.clone(), files::digest(Path::new(&p))?.sha256))
    })
    .collect::<Result<BTreeMap<_, _>>>()?;
    let provided = methods.iter().map(|m| m.method).collect();
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            pool_bytes: 64,
            native_methods: 4,
            class_id,
            class_sha256: node.origin.sha256.clone(),
            source_native_declarations: node
                .methods
                .iter()
                .filter(|m| m.access & 0x100 != 0)
                .count(),
            exact_runtime_receiver: true,
            override_dispatch_complete: false,
            memory_counters: "Heap1 committed capacity minus occupied block spans",
            processor_policy: "windows-default-group-and-job-affinity",
            kernel_sha256: kernels,
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
            unsupported_natives_remain_unprovided: true,
            original_initialization_executed: false,
            automatic_gc: false,
            game_started: false,
        },
        provided,
    ))
}
