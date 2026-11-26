//! The public array clone member; copying and allocation execute only in MASM.
use super::{classfile::ClassFile, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub owner: String,
    pub owner_type: usize,
    pub origin: ClassOrigin,
    pub heap_abi: u32,
    pub runtime_type_map_abi: u32,
    pub native_source_sha256: String,
    pub heap_source_sha256: String,
    pub runtime_types_source_sha256: String,
    pub types_source_sha256: String,
}

pub(super) fn is_clone(owner: &str, name: &str, descriptor: &str) -> bool {
    owner.starts_with('[') && name == "clone" && descriptor == "()Ljava/lang/Object;"
}

pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    owner_type: usize,
) -> Result<Binding> {
    let (owner, name, descriptor) = caller.method_reference(constant)?;
    ensure!(
        is_clone(&owner, &name, &descriptor)
            && caller.name.replace('/', ".") == source.binary_name
            && registry.literal(&source.loader, &owner)? == owner_type
            && matches!(registry.types[owner_type], types::Type::Array { .. }),
        "Array clone caller/type contract changed"
    );
    let id = registry.class("bootstrap", "java/lang/Object")?;
    let types::Type::Class { origin, key, .. } = &registry.types[id] else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "Array clone requires original bootstrap Object source"
    );
    let class = registry
        .definition(id)
        .context("Missing Object clone source")?;
    let m = class.method("clone", Some("()Ljava/lang/Object;"))?;
    ensure!(
        class.access & 0x611 == 1 && m.access == 0x104 && m.code.is_none(),
        "Object.clone protected/native source contract changed"
    );
    Ok(Binding {
        abi: 1,
        caller: source.clone(),
        constant,
        owner,
        owner_type,
        origin: origin.as_ref().clone(),
        heap_abi: 1,
        runtime_type_map_abi: 1,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/array_clone.asm"
        ))
        .sha256,
        heap_source_sha256: files::digest_bytes(include_bytes!("../../native/runtime/heap.asm"))
            .sha256,
        runtime_types_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/runtime_types.asm"
        ))
        .sha256,
        types_source_sha256: files::digest_bytes(include_bytes!("../../native/runtime/types.asm"))
            .sha256,
    })
}

pub(super) fn emit(out: &mut String) {
    out.push_str("EXTERN boom_array_clone:PROC\n.const\nALIGN 8\nboom_array_clone_pool DWORD 041434C50h, 1\n    QWORD OFFSET boom_heap_ptr, OFFSET boom_runtime_type_map, 0\n.code\nPUBLIC boom_get_array_clone_pool\nboom_get_array_clone_pool PROC\n    lea rax, boom_array_clone_pool\n    ret\nboom_get_array_clone_pool ENDP\n");
}
