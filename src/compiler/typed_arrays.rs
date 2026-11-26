//! Loader-aware array descriptors and allocation plans; execution is MASM.
use super::{runtime_types, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Site {
    pub caller: ClassOrigin,
    pub descriptor: String,
    pub dimensions: u8,
    pub type_id: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub sites: Vec<Site>,
    pub root_types: Vec<usize>,
    pub reference_array_types: Vec<usize>,
    pub native_source_sha256: String,
    pub heap_source_sha256: String,
    pub runtime_types_source_sha256: String,
    pub types_source_sha256: String,
    pub automatic_gc: bool,
}
impl Plan {
    pub(super) fn new(
        sites: Vec<Site>,
        roots: Vec<usize>,
        registry: &types::Registry<'_>,
    ) -> Result<Option<Self>> {
        if roots.is_empty() && sites.is_empty() {
            return Ok(None);
        }
        let mut references = BTreeSet::new();
        for site in &sites {
            let mut id = site.type_id;
            for _ in 0..site.dimensions {
                let types::Type::Array { component } = registry.types[id] else {
                    anyhow::bail!("Array dimensions exceed declared rank")
                };
                if !matches!(registry.types[component], types::Type::Primitive { .. }) {
                    references.insert(id);
                }
                id = component;
            }
        }
        for &root in &roots {
            let mut id = root;
            while let types::Type::Array { component } = registry.types[id] {
                if !matches!(registry.types[component], types::Type::Primitive { .. }) {
                    references.insert(id);
                }
                id = component;
            }
        }
        Ok(Some(Self {
            abi: 1,
            sites,
            root_types: roots,
            reference_array_types: references.into_iter().collect(),
            automatic_gc: false,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/typed_arrays.asm"
            ))
            .sha256,
            heap_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/heap.asm"
            ))
            .sha256,
            runtime_types_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/runtime_types.asm"
            ))
            .sha256,
            types_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/types.asm"
            ))
            .sha256,
        }))
    }
    pub(super) fn extend_rows(&self, rows: &mut Vec<runtime_types::Binding>) {
        for &id in &self.reference_array_types {
            rows.push(runtime_types::Binding {
                tag: format!("OFFSET boom_t{id}"),
                type_id: id,
                kind: 2,
                payload_bytes: 0,
                references: 0,
                element_shift: 3,
            });
        }
    }
    pub(super) fn emit(&self, out: &mut String) {
        out.push_str("EXTERN boom_typed_multi_new:PROC\nEXTERN boom_typed_array_length:PROC\n");
    }
}

pub(super) fn descriptor(registry: &types::Registry<'_>, id: usize) -> String {
    match &registry.types[id] {
        types::Type::Class { key, .. } => format!("L{};", key.name),
        types::Type::Array { component } => format!("[{}", descriptor(registry, *component)),
        types::Type::Primitive { value } => match value {
            types::Primitive::Boolean => "Z",
            types::Primitive::Byte => "B",
            types::Primitive::Char => "C",
            types::Primitive::Short => "S",
            types::Primitive::Int => "I",
            types::Primitive::Long => "J",
            types::Primitive::Float => "F",
            types::Primitive::Double => "D",
            types::Primitive::Void => "V",
        }
        .into(),
    }
}
pub(super) fn rank(descriptor: &str, dimensions: u8) -> Result<()> {
    let rank = descriptor.bytes().take_while(|&c| c == b'[').count();
    ensure!(
        (1..=255).contains(&rank) && dimensions != 0 && usize::from(dimensions) <= rank,
        "Array allocation dimensions exceed descriptor rank or JVM limit"
    );
    Ok(())
}
