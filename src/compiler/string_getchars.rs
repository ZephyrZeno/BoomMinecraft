//! Source-verified String.getChars checks and UTF16 copy, executed in ASM.
use super::{classfile::ClassFile, jdk_bridges, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const DESCRIPTOR: &str = "(II[CI)V";
pub const GUARDS: [jdk_bridges::Kind; 2] = [
    jdk_bridges::Kind::CheckBeginEnd,
    jdk_bridges::Kind::CheckOffCount,
];
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub string_origin: ClassOrigin,
    pub code_sha256: String,
    pub guard_code_sha256: [String; 2],
    pub preconditions_origin: ClassOrigin,
    pub preconditions_code_sha256: [String; 2],
    pub original_range_guard_bodies_executed: bool,
    pub original_get_chars_body_executed: bool,
    pub native_source_sha256: String,
}
pub(super) fn signature() -> numeric::Signature {
    numeric::Signature {
        arguments: vec![
            numeric::Type::BootstrapString,
            numeric::Type::I32,
            numeric::Type::I32,
            numeric::Type::Array(numeric::ArrayKind::Char),
            numeric::Type::I32,
        ],
        result: numeric::Type::Void,
    }
}
pub(super) fn bind(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
) -> Result<Binding> {
    ensure!(
        caller.method_reference(constant)?
            == (
                "java/lang/String".into(),
                "getChars".into(),
                DESCRIPTOR.into()
            ),
        "String.getChars call changed"
    );
    let id = registry.class("bootstrap", "java/lang/String")?;
    let types::Type::Class { origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    ensure!(
        origin.source_id == "jdk:java.base" && origin.generated.is_none(),
        "String.getChars requires original bootstrap source"
    );
    let class = registry
        .definition(id)
        .context("Missing String declaration")?;
    let method = class.method("getChars", Some(DESCRIPTOR))?;
    let code = method
        .code
        .as_ref()
        .context("Missing original String.getChars Code")?;
    ensure!(
        method.access == 1
            && code.handlers.is_empty()
            && code.bytes.len() >= 20
            && code.bytes[..4] == [0x1b, 0x1c, 0x2a, 0xb6]
            && code.bytes[6] == 0xb8
            && code.bytes[9..17] == [0x15, 4, 0x1c, 0x1b, 0x64, 0x2d, 0xbe, 0xb8]
            && code.bytes[19] == 0x57,
        "String.getChars range-guard order changed"
    );
    let index = |at: usize| u16::from_be_bytes([code.bytes[at], code.bytes[at + 1]]);
    ensure!(
        class.method_reference(index(4))?
            == ("java/lang/String".into(), "length".into(), "()I".into()),
        "String.getChars length check changed"
    );
    for (guard, at) in GUARDS.iter().zip([7, 17]) {
        let (owner, name, descriptor, interface) = class.static_method_reference(index(at))?;
        ensure!(
            !interface
                && owner == guard.owner()
                && name == guard.name()
                && descriptor == guard.original_descriptor(),
            "String.getChars guard declaration changed"
        );
    }
    let origin = origin.as_ref().clone();
    let mut guard_hashes = Vec::new();
    for kind in GUARDS {
        let m = class.method(kind.name(), Some(kind.original_descriptor()))?;
        let c = m.code.as_ref().context("Missing String range guard Code")?;
        ensure!(
            m.access == 8 && c.handlers.is_empty(),
            "String range guard changed"
        );
        guard_hashes.push(files::digest_bytes(&c.bytes).sha256);
    }
    let code_sha256 = files::digest_bytes(&code.bytes).sha256;
    let pid = registry.class("bootstrap", "jdk/internal/util/Preconditions")?;
    let types::Type::Class {
        origin: preconditions_origin,
        ..
    } = &registry.types[pid]
    else {
        unreachable!()
    };
    ensure!(
        preconditions_origin.source_id == "jdk:java.base"
            && preconditions_origin.generated.is_none(),
        "Range checks require original Preconditions"
    );
    let preconditions_origin = preconditions_origin.as_ref().clone();
    let pc = registry
        .definition(pid)
        .context("Missing Preconditions source")?;
    let mut checks = Vec::new();
    for (name, prefix) in [
        (
            "checkFromToIndex",
            &[
                0x1a, 0x9b, 0, 13, 0x1a, 0x1b, 0xa3, 0, 8, 0x1b, 0x1c, 0xa4, 0, 11,
            ][..],
        ),
        (
            "checkFromIndexSize",
            &[
                0x1c, 0x1a, 0x80, 0x1b, 0x80, 0x9b, 0, 10, 0x1b, 0x1c, 0x1a, 0x64, 0xa4, 0, 11,
            ][..],
        ),
    ] {
        let m = pc.method(name, Some("(IIILjava/util/function/BiFunction;)I"))?;
        let c = m
            .code
            .as_ref()
            .context("Missing Preconditions check Code")?;
        ensure!(
            m.access == 9 && c.handlers.is_empty() && c.bytes.starts_with(prefix),
            "Preconditions range algorithm changed"
        );
        checks.push(files::digest_bytes(&c.bytes).sha256);
    }
    Ok(Binding {
        caller: source.clone(),
        constant,
        string_origin: origin,
        code_sha256,
        guard_code_sha256: guard_hashes.try_into().unwrap(),
        preconditions_origin,
        preconditions_code_sha256: checks.try_into().unwrap(),
        original_range_guard_bodies_executed: false,
        original_get_chars_body_executed: false,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/strings.asm"
        ))
        .sha256,
    })
}
