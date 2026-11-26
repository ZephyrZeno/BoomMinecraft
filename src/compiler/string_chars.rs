//! Fresh char[] copies across the VM-owned String UTF16 storage boundary.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const DESCRIPTOR: &str = "()[C";
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub origin: ClassOrigin,
    pub utf16_origin: ClassOrigin,
    pub latin1_origin: ClassOrigin,
    pub storage_abi: u32,
    pub compact_strings: bool,
    pub native_source_sha256: String,
    pub string_source_sha256: String,
    pub heap_source_sha256: String,
}
pub(super) fn is_to_chars(o: &str, n: &str, d: &str) -> bool {
    o == "java/lang/String" && n == "toCharArray" && d == DESCRIPTOR
}
pub(super) fn signature() -> numeric::Signature {
    numeric::Signature {
        arguments: vec![numeric::Type::BootstrapString],
        result: numeric::Type::Array(numeric::ArrayKind::Char),
    }
}
fn original(registry: &mut types::Registry<'_>, name: &str) -> Result<(usize, ClassOrigin)> {
    let id = registry.class("bootstrap", name)?;
    let types::Type::Class { key, origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "String character copy requires original java.base sources"
    );
    Ok((id, origin.as_ref().clone()))
}
fn body(class: &ClassFile) -> Result<()> {
    let m = class.method("toCharArray", Some(DESCRIPTOR))?;
    let c = m
        .code
        .as_ref()
        .context("String.toCharArray must retain original Java Code")?;
    let b = &c.bytes;
    ensure!(
        class.access & 0x211 == 0x11 && m.access == 1 && c.handlers.is_empty() && b.len() == 25,
        "String.toCharArray source contract changed"
    );
    for (i, v) in [
        (0, 0x2a),
        (1, 0xb6),
        (4, 0x99),
        (5, 0),
        (6, 13),
        (7, 0x2a),
        (8, 0xb4),
        (11, 0xb8),
        (14, 0xa7),
        (15, 0),
        (16, 10),
        (17, 0x2a),
        (18, 0xb4),
        (21, 0xb8),
        (24, 0xb0),
    ] {
        ensure!(b[i] == v, "String.toCharArray copy/encoding body changed");
    }
    let cp = |i| u16::from_be_bytes([b[i], b[i + 1]]);
    ensure!(
        class.method_reference(cp(2))?
            == ("java/lang/String".into(), "isLatin1".into(), "()Z".into()),
        "String.toCharArray encoding branch changed"
    );
    for i in [9, 19] {
        ensure!(
            class.field_reference(cp(i))?
                == ("java/lang/String".into(), "value".into(), "[B".into()),
            "String.toCharArray backing field changed"
        );
    }
    for (i, owner) in [
        (12, "java/lang/StringLatin1"),
        (22, "java/lang/StringUTF16"),
    ] {
        let (o, n, d, interface) = class.static_method_reference(cp(i))?;
        ensure!(
            !interface && o == owner && n == "toChars" && d == "([B)[C",
            "String.toCharArray helper changed"
        );
    }
    Ok(())
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
) -> Result<Binding> {
    let (o, n, d) = caller.method_reference(constant)?;
    ensure!(
        is_to_chars(&o, &n, &d) && source.binary_name == caller.name.replace('/', "."),
        "String.toCharArray caller changed"
    );
    let (id, origin) = original(registry, "java/lang/String")?;
    body(registry.definition(id).context("Missing String source")?)?;
    let mut helpers = Vec::new();
    for name in ["java/lang/StringUTF16", "java/lang/StringLatin1"] {
        let (id, origin) = original(registry, name)?;
        let m = registry
            .definition(id)
            .context("Missing toChars helper")?
            .method("toChars", Some("([B)[C"))?;
        ensure!(
            m.access == 9 && m.code.is_some(),
            "toChars helper public/static Java contract changed"
        );
        helpers.push(origin);
    }
    Ok(Binding {
        abi: 1,
        caller: source.clone(),
        constant,
        origin,
        utf16_origin: helpers.remove(0),
        latin1_origin: helpers.remove(0),
        storage_abi: 3,
        compact_strings: false,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/string_chars.asm"
        ))
        .sha256,
        string_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/strings.asm"
        ))
        .sha256,
        heap_source_sha256: files::digest_bytes(include_bytes!("../../native/runtime/heap.asm"))
            .sha256,
    })
}
