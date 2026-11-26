//! Original Integer/Long hex delegation; formatting and allocation are MASM.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Kind {
    Int,
    Long,
}
impl Kind {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Option<Self> {
        match (owner, name, descriptor) {
            ("java/lang/Integer", "toHexString", "(I)Ljava/lang/String;") => Some(Self::Int),
            ("java/lang/Long", "toHexString", "(J)Ljava/lang/String;") => Some(Self::Long),
            _ => None,
        }
    }
    pub(super) fn owner(self) -> &'static str {
        if self == Self::Int {
            "java/lang/Integer"
        } else {
            "java/lang/Long"
        }
    }
    pub(super) fn descriptor(self) -> &'static str {
        if self == Self::Int {
            "(I)Ljava/lang/String;"
        } else {
            "(J)Ljava/lang/String;"
        }
    }
    pub(super) fn signature(self) -> numeric::Signature {
        numeric::Signature {
            arguments: vec![if self == Self::Int {
                numeric::Type::I32
            } else {
                numeric::Type::I64
            }],
            result: numeric::Type::BootstrapString,
        }
    }
    pub(super) fn bits(self) -> u32 {
        if self == Self::Int { 32 } else { 64 }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub kind: Kind,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub owner: usize,
    pub origin: ClassOrigin,
    pub native_source_sha256: String,
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    kind: Kind,
    owner: usize,
) -> Result<Binding> {
    let (o, n, d, i) = caller.static_method_reference(constant)?;
    ensure!(
        !i && Kind::resolve(&o, &n, &d) == Some(kind)
            && source.binary_name == caller.name.replace('/', "."),
        "Hex conversion caller proof changed"
    );
    let id = registry.class("bootstrap", kind.owner())?;
    let types::Type::Class {
        key,
        origin,
        access,
        ..
    } = &registry.types[id]
    else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none()
            && access & 0x211 == 0x11,
        "Hex conversion requires its original final bootstrap class"
    );
    let class = registry.definition(id).context("Missing hex source")?;
    let m = class.method("toHexString", Some(kind.descriptor()))?;
    let code = m.code.as_ref().context("Missing original hex Code")?;
    let b = &code.bytes;
    ensure!(
        m.access == 9
            && code.handlers.is_empty()
            && b.len() == 6
            && b[0] == if kind == Kind::Int { 0x1a } else { 0x1e }
            && b[1] == 7
            && b[2] == 0xb8
            && b[5] == 0xb0,
        "Hex source must delegate with shift four"
    );
    let helper_desc = if kind == Kind::Int {
        "(II)Ljava/lang/String;"
    } else {
        "(JI)Ljava/lang/String;"
    };
    let (ho, hn, hd, hi) = class.static_method_reference(u16::from_be_bytes([b[3], b[4]]))?;
    ensure!(
        !hi && ho == kind.owner() && hn == "toUnsignedString0" && hd == helper_desc,
        "Hex delegate changed"
    );
    let helper = class.method(&hn, Some(helper_desc))?;
    ensure!(
        helper.access == if kind == Kind::Int { 10 } else { 8 } && helper.code.is_some(),
        "Unsigned hex helper contract changed"
    );
    Ok(Binding {
        abi: 1,
        kind,
        caller: source.clone(),
        constant,
        owner,
        origin: origin.as_ref().clone(),
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/hex_strings.asm"
        ))
        .sha256,
    })
}
