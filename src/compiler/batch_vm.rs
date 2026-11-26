//! Normal VM registration/time services. No fabricated Java boot-level changes.
use super::{
    batch_catalog::Catalog,
    batch_class_bootstrap::{Method, native_adapter},
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{collections::BTreeSet, fs, io::Write, path::Path};
use zip::{ZipWriter, write::SimpleFileOptions};

pub const OWNER: &str = "jdk/internal/misc/VM";
pub const SPECS: [(&str, &str, u16, u32); 2] = [
    ("initialize", "()V", 0x10a, 0),
    ("getNanoTimeAdjustment", "(J)J", 0x109, 1),
];

#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_abi: u32,
    pub pool_bytes: usize,
    pub native_methods: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub source_native_declarations: usize,
    pub registered_prelinked_methods: usize,
    pub kernel_sha256: String,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub unsupported_natives_remain_unprovided: bool,
    pub original_initialization_executed: bool,
    pub java_boot_level_changed_by_native: bool,
    pub game_started: bool,
}

pub(super) fn source_methods(catalog: &Catalog) -> Result<Vec<Method>> {
    let class_id = catalog.lookup("bootstrap", OWNER)?;
    let node = &catalog.nodes[class_id];
    ensure!(
        node.origin.source_id == "jdk:java.base"
            && node.origin.generated.is_none()
            && node.access == 0x21,
        "VM registration requires original java.base VM"
    );
    SPECS
        .into_iter()
        .map(|(name, descriptor, access, operation)| {
            let i = node
                .methods
                .iter()
                .position(|m| m.name == name && m.descriptor == descriptor)
                .context("Missing source VM native")?;
            ensure!(
                node.methods[i].access == access,
                "Source VM native flags differ"
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
    let mut body = String::from(
        ".data\nALIGN 8\nPUBLIC boom_java_vm_pool\nboom_java_vm_pool DWORD 0564D5247h,2,0,1\n QWORD 0,0\n",
    );
    for m in &methods {
        body.push_str(&native_adapter(
            m.method,
            class_id,
            "boom_java_vm_pool",
            "boom_vm_native",
            m.operation,
        ));
    }
    let dir = output.join("vm-registration");
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
    let provided = methods.iter().map(|m| m.method).collect();
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            pool_abi: 2,
            pool_bytes: 32,
            native_methods: 2,
            class_id,
            class_sha256: node.origin.sha256.clone(),
            source_native_declarations: node
                .methods
                .iter()
                .filter(|m| m.access & 0x100 != 0)
                .count(),
            registered_prelinked_methods: 1,
            kernel_sha256: files::digest(Path::new("native/runtime/vm_registration.asm"))?.sha256,
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
            unsupported_natives_remain_unprovided: true,
            original_initialization_executed: false,
            java_boot_level_changed_by_native: false,
            game_started: false,
        },
        provided,
    ))
}
