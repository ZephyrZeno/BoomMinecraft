//! VM identity hashes for the nonmoving Heap1; source selection remains offline.
use super::{classfile::ClassFile, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Kind {
    SystemIdentity,
    ObjectDefault,
    ArrayDefault,
    OpaqueDefault,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub kind: Kind,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub origin: ClassOrigin,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub receiver_origin: Option<ClassOrigin>,
    pub nonmoving_heap_abi: u32,
    pub heap_source_sha256: String,
    pub native_source_sha256: String,
}
pub(super) fn object_member(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == "java/lang/Object" && name == "hashCode" && descriptor == "()I"
}
pub(super) fn system_member(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == "java/lang/System"
        && name == "identityHashCode"
        && descriptor == "(Ljava/lang/Object;)I"
}
pub(super) fn verify_object(class: &ClassFile, origin: &ClassOrigin) -> Result<()> {
    ensure!(
        origin.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none()
            && origin.binary_name == "java.lang.Object"
            && class.name == "java/lang/Object",
        "Object hash requires original bootstrap source"
    );
    let m = class.method("hashCode", Some("()I"))?;
    ensure!(
        class.access & 0x611 == 1 && m.access == 0x101 && m.code.is_none(),
        "Object.hashCode native contract changed"
    );
    Ok(())
}
pub(super) fn fixed_receiver(owner: &str) -> bool {
    owner.starts_with('[')
        || matches!(
            owner,
            "java/lang/Class" | "java/lang/Module" | "java/lang/ModuleLayer"
        )
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    kind: Kind,
) -> Result<Binding> {
    ensure!(
        caller.name.replace('/', ".") == source.binary_name,
        "Identity hash caller origin changed"
    );
    let owner = match kind {
        Kind::SystemIdentity => "java/lang/System",
        Kind::ObjectDefault | Kind::ArrayDefault | Kind::OpaqueDefault => "java/lang/Object",
    };
    let id = registry.class("bootstrap", owner)?;
    let types::Type::Class { key, origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "Identity hash requires original java.base native source"
    );
    let class = registry
        .definition(id)
        .context("Missing identity hash source")?;
    let origin = origin.as_ref().clone();
    let mut receiver_origin = None;
    match kind {
        Kind::ObjectDefault => {
            let (_, name, descriptor, _) = caller.special_method_reference(constant)?;
            ensure!(
                name == "hashCode" && descriptor == "()I",
                "Object identity dispatch call site changed"
            );
            verify_object(class, &origin)?;
        }
        Kind::ArrayDefault => {
            let (o, n, d) = caller.method_reference(constant)?;
            ensure!(
                o.starts_with('[') && n == "hashCode" && d == "()I",
                "Array hash call site changed"
            );
            verify_object(class, &origin)?;
        }
        Kind::OpaqueDefault => {
            verify_object(class, &origin)?;
            let (o, n, d) = caller.method_reference(constant)?;
            ensure!(
                fixed_receiver(&o) && !o.starts_with('[') && n == "hashCode" && d == "()I",
                "Opaque hash call site changed"
            );
            let ci = registry.class("bootstrap", &o)?;
            let types::Type::Class {
                key,
                origin,
                access,
                ..
            } = &registry.types[ci]
            else {
                unreachable!()
            };
            let class = registry
                .definition(ci)
                .context("Missing VM-owned receiver source")?;
            ensure!(
                key.loader == "bootstrap"
                    && origin.source_id == "jdk:java.base"
                    && origin.generated.is_none()
                    && access & 0x211 == 0x11
                    && class.super_name == "java/lang/Object"
                    && !class
                        .methods
                        .iter()
                        .any(|m| m.name == "hashCode" && m.descriptor == "()I"),
                "VM-owned hash receiver must be original, final and inherit Object's native hash"
            );
            receiver_origin = Some(origin.as_ref().clone());
        }
        Kind::SystemIdentity => {
            let (o, n, d, i) = caller.static_method_reference(constant)?;
            ensure!(
                !i && system_member(&o, &n, &d),
                "System identity call site changed"
            );
            let m = class.method("identityHashCode", Some("(Ljava/lang/Object;)I"))?;
            ensure!(
                m.access == 0x109 && m.code.is_none(),
                "System.identityHashCode native contract changed"
            );
        }
    }
    Ok(Binding {
        abi: 1,
        kind,
        caller: source.clone(),
        constant,
        origin,
        receiver_origin,
        nonmoving_heap_abi: 1,
        heap_source_sha256: files::digest_bytes(include_bytes!("../../native/runtime/heap.asm"))
            .sha256,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/identity_hash.asm"
        ))
        .sha256,
    })
}
