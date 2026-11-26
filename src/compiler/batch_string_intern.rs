//! Source-normal String.intern provider; all guest behavior is MASM.
use super::{
    batch_catalog::Catalog,
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    batch_literals::StringShape,
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

#[derive(Serialize)]
pub struct Method {
    pub method: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub assembly_unit: usize,
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub root_cells: usize,
    pub native_methods: usize,
    pub general_string_intern: bool,
    pub strong_retention: bool,
    pub weak_intern: bool,
    pub original_string_initialization_executed: bool,
    pub automatic_gc: bool,
    pub linked: bool,
    pub kernel_sha256: BTreeMap<String, String>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
}
pub(super) fn pool(shape: &StringShape) -> String {
    format!(
        ".data?\nALIGN 8\nPUBLIC boom_java_string_intern_root\nboom_java_string_intern_root QWORD ?\n.const\nPUBLIC boom_java_string_intern_root_count\nboom_java_string_intern_root_count QWORD 1\n.data\nALIGN 8\nPUBLIC boom_java_string_intern_pool\nboom_java_string_intern_pool DWORD 04A494E50h,1,0,0,0,0\n QWORD OFFSET boom_heap_ptr,OFFSET boom_layout{class}\n DWORD {value},{coder},{hash},{zero}\n QWORD OFFSET boom_java_string_literal_pool,OFFSET boom_java_class_name_pool,OFFSET boom_java_string_intern_root\n DWORD 32,1\n QWORD 0\n",
        class = shape.class_id,
        value = shape.value_offset,
        coder = shape.coder_offset,
        hash = shape.hash_offset,
        zero = shape.hash_is_zero_offset
    )
}
pub(super) fn body(id: usize) -> String {
    format!(
        ".code\nboom_m{id} PROC\n jmp boom_m{id}_native\nboom_m{id} ENDP\nboom_m{id}_native PROC\n lea r8,boom_java_string_intern_pool\n jmp boom_java_string_intern\nboom_m{id}_native ENDP\n"
    )
}
pub(super) fn generate(
    catalog: &Catalog,
    shape: &StringShape,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let id = catalog.lookup("bootstrap", "java/lang/String")?;
    let node = &catalog.nodes[id];
    ensure!(
        id == shape.class_id
            && node.origin.source_id == "jdk:java.base"
            && node.origin.generated.is_none()
            && node.access & 0x10 != 0
            && node.origin.sha256 == shape.source_sha256,
        "Intern requires original final source String"
    );
    let (index, method) = node
        .methods
        .iter()
        .enumerate()
        .find(|(_, m)| m.name == "intern" && m.descriptor == "()Ljava/lang/String;")
        .context("Missing source String.intern")?;
    ensure!(
        method.access == 0x101,
        "String.intern signature/access changed"
    );
    let method_id = node.method_ids[index];
    let record = Method {
        method: method_id,
        class_id: id,
        class_sha256: node.origin.sha256.clone(),
        name: "intern".into(),
        descriptor: "()Ljava/lang/String;".into(),
        access: method.access,
        assembly_unit: 0,
    };
    let directory = output.join("string-intern");
    fs::create_dir_all(&directory)?;
    let unit = write_unit(
        &Symbols::new()?,
        &directory.join("0000.asm"),
        0,
        &(pool(shape) + &body(method_id)),
        assemble,
    )?;
    let path = directory.join("index.zip");
    let mut temporary = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temporary.as_file_mut());
        zip.start_file(
            "methods.jsonl",
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )?;
        serde_json::to_writer(&mut zip, &record)?;
        zip.write_all(b"\n")?;
        zip.finish()?;
    }
    temporary.persist(&path).map_err(|e| e.error)?;
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            root_cells: 1,
            native_methods: 1,
            general_string_intern: true,
            strong_retention: true,
            weak_intern: false,
            original_string_initialization_executed: false,
            automatic_gc: false,
            linked: false,
            kernel_sha256: BTreeMap::from([(
                "native/runtime/java_string_intern.asm".into(),
                files::digest_bytes(include_bytes!(
                    "../../native/runtime/java_string_intern.asm"
                ))
                .sha256,
            )]),
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
        },
        BTreeSet::from([method_id]),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn instance_intern_does_not_initialize_string_or_claim_registration() {
        let asm = body(7);
        assert!(
            asm.contains("jmp boom_java_string_intern")
                && !asm.contains("class_ensure")
                && !asm.contains("registerNatives")
        );
    }
}
