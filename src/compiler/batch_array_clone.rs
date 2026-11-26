//! Source-bound generation of every public array clone call-site adapter.
//! Copies and allocation execute the existing assembly native kernel only.
use super::{
    batch_catalog::Catalog,
    batch_compile::{ASSEMBLY_BODY_BUDGET, AssemblyBodies, AssemblyUnit, Symbols, write_unit},
    batch_types::{Binding, Universe},
    hierarchy::Metadata,
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

pub(super) const POOL: &str = ".const\nALIGN 8\nPUBLIC boom_batch_array_clone_pool\nboom_batch_array_clone_pool DWORD 041434C50h,1\n QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,0\n";
#[derive(Serialize)]
pub struct Site {
    pub label: String,
    pub caller_class: usize,
    pub class_sha256: String,
    pub constant: u16,
    pub opcode: u8,
    pub descriptor: String,
    pub array_type: usize,
    pub caller_methods: BTreeSet<usize>,
    pub assembly_unit: Option<usize>,
}
#[derive(Serialize)]
pub struct Contract {
    pub object_class: usize,
    pub class_sha256: String,
    pub clone_method: usize,
    pub source_access: u16,
    pub heap_abi: u32,
    pub runtime_map_abi: u32,
    pub pool_abi: u32,
    pub pool_unit: usize,
    pub kernel_sha256: String,
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub generated_sites: usize,
    pub source_array_types: usize,
    pub contract: Option<Contract>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub linked: bool,
    pub execution_verified: bool,
    pub automatic_gc: bool,
}
pub(super) fn record(
    sites: &mut BTreeMap<String, Site>,
    method: usize,
    sha: &str,
    binding: &Binding,
) -> Result<()> {
    ensure!(
        binding.kind == "array_clone"
            && binding.opcode == 182
            && binding.descriptor == "()Ljava/lang/Object;"
            && binding.resolved_method.is_none(),
        "Invalid public array clone binding"
    );
    let array_type = binding
        .array_type
        .context("Array clone has no source array identity")?;
    let site = sites.entry(binding.label.clone()).or_insert_with(|| Site {
        label: binding.label.clone(),
        caller_class: binding.caller_class,
        class_sha256: sha.into(),
        constant: binding.constant,
        opcode: binding.opcode,
        descriptor: binding.descriptor.clone(),
        array_type,
        caller_methods: BTreeSet::new(),
        assembly_unit: None,
    });
    ensure!(
        site.caller_class == binding.caller_class
            && site.class_sha256 == sha
            && site.constant == binding.constant
            && site.opcode == binding.opcode
            && site.descriptor == binding.descriptor
            && site.array_type == array_type,
        "Conflicting source array clone call site"
    );
    site.caller_methods.insert(method);
    Ok(())
}
fn body(site: &Site) -> String {
    format!(
        ".code\n{} PROC\n lea r8,boom_batch_array_clone_pool\n lea r9,boom_t{}\n jmp boom_array_clone\n{} ENDP\n",
        site.label, site.array_type, site.label
    )
}
pub(super) fn generate(
    catalog: &Catalog,
    universe: &Universe,
    mut sites: BTreeMap<String, Site>,
    output: &Path,
    assemble: bool,
) -> Result<Summary> {
    let mut bodies = AssemblyBodies::new(ASSEMBLY_BODY_BUDGET);
    let contract = if sites.is_empty() {
        None
    } else {
        let id = catalog.root_object()?;
        let node = &catalog.nodes[id];
        ensure!(
            node.origin.source_id == "jdk:java.base"
                && node.origin.generated.is_none()
                && node.access & 0x611 == 1,
            "Array clone requires original bootstrap Object definition"
        );
        let index = node
            .methods
            .iter()
            .position(|m| m.name == "clone" && m.descriptor == "()Ljava/lang/Object;")
            .context("Missing original Object.clone declaration")?;
        ensure!(
            node.methods[index].access == 0x104,
            "Original Object.clone is not protected native"
        );
        Some(Contract {
            object_class: id,
            class_sha256: node.origin.sha256.clone(),
            clone_method: node.method_ids[index],
            source_access: node.methods[index].access,
            heap_abi: 1,
            runtime_map_abi: 2,
            pool_abi: 1,
            pool_unit: bodies.push(POOL),
            kernel_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/array_clone.asm"
            ))
            .sha256,
        })
    };
    let mut types = BTreeSet::new();
    for site in sites.values_mut() {
        universe.array(site.array_type)?;
        types.insert(site.array_type);
        site.assembly_unit = Some(bodies.push(&body(site)));
    }
    let directory = output.join("array-clone");
    fs::create_dir_all(&directory)?;
    let mut units = vec![];
    let symbols = Symbols::new()?;
    for (id, body) in bodies.parts.iter().enumerate() {
        units.push(write_unit(
            &symbols,
            &directory.join(format!("{id:04}.asm")),
            id,
            body,
            assemble,
        )?);
    }
    let path = directory.join("index.zip");
    let mut temp = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temp.as_file_mut());
        zip.start_file(
            "sites.jsonl",
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )?;
        for site in sites.values() {
            serde_json::to_writer(&mut zip, site)?;
            zip.write_all(b"\n")?;
        }
        zip.finish()?;
    }
    temp.persist(&path).map_err(|e| e.error)?;
    eprintln!(
        "Automatic array clone: {} original source sites, {} symbolic array types",
        sites.len(),
        types.len()
    );
    Ok(Summary {
        abi: 1,
        context_bytes: 32,
        generated_sites: sites.len(),
        source_array_types: types.len(),
        contract,
        index: Artifact {
            path: path.display().to_string(),
            digest: files::digest(&path)?,
        },
        units,
        linked: false,
        execution_verified: false,
        automatic_gc: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn clones_share_a_site_and_reject_conflicting_array_identity() {
        let mut binding = Binding {
            label: "boom_batch_call_4_8_182".into(),
            kind: "array_clone".into(),
            caller_class: 4,
            caller_method: 1,
            constant: 8,
            opcode: 182,
            resolved_method: None,
            descriptor: "()Ljava/lang/Object;".into(),
            implemented: false,
            dispatch: None,
            protocol: None,
            array_type: Some(9),
            literal_type: None,
        };
        let mut sites = BTreeMap::new();
        record(&mut sites, 1, "hash", &binding).unwrap();
        record(&mut sites, 2, "hash", &binding).unwrap();
        assert_eq!(sites.len(), 1);
        assert_eq!(sites[&binding.label].caller_methods, BTreeSet::from([1, 2]));
        assert!(body(&sites[&binding.label]).contains("lea r9,boom_t9\n jmp boom_array_clone"));
        binding.array_type = Some(10);
        assert!(record(&mut sites, 3, "hash", &binding).is_err());
    }
}
