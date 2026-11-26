//! Original Float/Double native raw-bit entries, using the managed raw-slot ABI.
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

pub const SPECS: [(&str, &str, &str, u32); 4] = [
    ("java/lang/Float", "floatToRawIntBits", "(F)I", 0),
    ("java/lang/Float", "intBitsToFloat", "(I)F", 1),
    ("java/lang/Double", "doubleToRawLongBits", "(D)J", 2),
    ("java/lang/Double", "longBitsToDouble", "(J)D", 3),
];

#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_bytes: usize,
    pub native_methods: usize,
    pub source_native_declarations: usize,
    pub source_class_ids: Vec<usize>,
    pub kernel_sha256: String,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub raw_nan_payloads_preserved: bool,
    pub numeric_conversion: bool,
    pub original_initialization_executed: bool,
    pub game_started: bool,
}

pub(super) fn source_methods(catalog: &Catalog) -> Result<Vec<Method>> {
    SPECS
        .into_iter()
        .map(|(owner, name, descriptor, operation)| {
            let class_id = catalog.lookup("bootstrap", owner)?;
            let node = &catalog.nodes[class_id];
            ensure!(
                node.origin.source_id == "jdk:java.base"
                    && node.origin.generated.is_none()
                    && node.access == 0x31,
                "Raw bitcast requires original final java.base numeric class"
            );
            let i = node
                .methods
                .iter()
                .position(|m| m.name == name && m.descriptor == descriptor)
                .context("Missing original raw bitcast native")?;
            ensure!(
                node.methods[i].access == 0x109,
                "Raw bitcast source native flags differ"
            );
            Ok(Method {
                method: node.method_ids[i],
                class_id,
                class_sha256: node.origin.sha256.clone(),
                name: name.into(),
                descriptor: descriptor.into(),
                access: 0x109,
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
    let classes: BTreeSet<_> = methods.iter().map(|m| m.class_id).collect();
    let mut body = String::from(
        ".const\nALIGN 8\nPUBLIC boom_java_bitcast_pool\nboom_java_bitcast_pool DWORD 054534342h,1,4,0\n",
    );
    for m in &methods {
        body.push_str(&native_adapter(
            m.method,
            m.class_id,
            "boom_java_bitcast_pool",
            "boom_java_bitcast",
            m.operation,
        ));
    }
    let dir = output.join("bitcasts");
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
    let declarations = classes
        .iter()
        .map(|&id| {
            catalog.nodes[id]
                .methods
                .iter()
                .filter(|m| m.access & 0x100 != 0)
                .count()
        })
        .sum();
    let provided = methods.iter().map(|m| m.method).collect();
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            pool_bytes: 16,
            native_methods: 4,
            source_native_declarations: declarations,
            source_class_ids: classes.into_iter().collect(),
            kernel_sha256: files::digest(Path::new("native/runtime/java_bitcasts.asm"))?.sha256,
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
            raw_nan_payloads_preserved: true,
            numeric_conversion: false,
            original_initialization_executed: false,
            game_started: false,
        },
        provided,
    ))
}
