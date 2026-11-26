//! VM raw floating-bit reinterpretation; no numeric conversion or allocation.
use super::{classfile::ClassFile, numeric, types};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Kind {
    FloatToInt,
    IntToFloat,
    DoubleToLong,
    LongToDouble,
}
impl Kind {
    pub(super) fn resolve(o: &str, n: &str, d: &str) -> Option<Self> {
        match (o, n, d) {
            ("java/lang/Float", "floatToRawIntBits", "(F)I") => Some(Self::FloatToInt),
            ("java/lang/Float", "intBitsToFloat", "(I)F") => Some(Self::IntToFloat),
            ("java/lang/Double", "doubleToRawLongBits", "(D)J") => Some(Self::DoubleToLong),
            ("java/lang/Double", "longBitsToDouble", "(J)D") => Some(Self::LongToDouble),
            _ => None,
        }
    }
    pub(super) fn owner(self) -> &'static str {
        if matches!(self, Self::FloatToInt | Self::IntToFloat) {
            "java/lang/Float"
        } else {
            "java/lang/Double"
        }
    }
    pub(super) fn signature(self) -> numeric::Signature {
        use numeric::Type::*;
        let (a, result) = match self {
            Self::FloatToInt => (F32, I32),
            Self::IntToFloat => (I32, F32),
            Self::DoubleToLong => (F64, I64),
            Self::LongToDouble => (I64, F64),
        };
        numeric::Signature {
            arguments: vec![a],
            result,
        }
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
        "Bitcast call source changed"
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
        "Bitcasts require original final numeric classes"
    );
    let m = registry
        .definition(id)
        .context("Missing bitcast source")?
        .method(&n, Some(&d))?;
    ensure!(
        m.access == 0x109 && m.code.is_none(),
        "Raw floating bitcast must be public static native"
    );
    Ok(Binding {
        abi: 1,
        kind,
        caller: source.clone(),
        constant,
        owner,
        origin: origin.as_ref().clone(),
    })
}
