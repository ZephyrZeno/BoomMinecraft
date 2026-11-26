//! Cross-package protected constructor resolution and its invalidation proof.
use super::{classfile::ClassFile, types};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub caller: ClassOrigin,
    pub owner: ClassOrigin,
    pub constant: u16,
    pub descriptor: String,
    pub access: u16,
    pub superclass_chain: Vec<ClassOrigin>,
    pub receiver_rule: String,
}

pub(super) fn prove(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    caller_loader: &str,
    owner: &ClassFile,
    owner_loader: &str,
    constant: u16,
) -> Result<Binding> {
    let (name, method, descriptor) = caller.method_reference(constant)?;
    ensure!(
        name == owner.name && method == "<init>",
        "Protected constructor call site changed"
    );
    let m = owner.method(&method, Some(&descriptor))?;
    ensure!(
        m.access & 0x50f == 4 && m.code.is_some() && caller.access & 0x200 == 0,
        "Protected constructor must have original nonstatic Java Code"
    );
    let c = registry.class(caller_loader, &caller.name)?;
    let target = registry.class(caller_loader, &owner.name)?;
    let mut chain = Vec::new();
    let mut current = c;
    loop {
        ensure!(
            chain.len() < 16384,
            "Protected constructor superclass chain exceeds budget"
        );
        let types::Type::Class {
            origin,
            superclass,
            key,
            ..
        } = &registry.types[current]
        else {
            anyhow::bail!("Protected constructor requires class identities")
        };
        if current == c {
            ensure!(
                key.loader == caller_loader,
                "Protected caller defining loader differs"
            );
        }
        chain.push(origin.as_ref().clone());
        if current == target {
            ensure!(
                key.loader == owner_loader,
                "Protected owner defining loader differs"
            );
            break;
        }
        current =
            superclass.context("Protected constructor caller is not a subclass of its owner")?;
    }
    ensure!(
        chain.len() > 1,
        "Cross-package constructor must name an ancestor"
    );
    Ok(Binding {
        abi: 1,
        caller: chain[0].clone(),
        owner: chain.last().unwrap().clone(),
        constant,
        descriptor,
        access: m.access,
        superclass_chain: chain,
        receiver_rule: "initialized-receiver-type-assignable-to-current-class".into(),
    })
}
