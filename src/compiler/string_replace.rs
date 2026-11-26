//! String.replace(char,char) across the VM-owned UTF16 storage boundary.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const DESCRIPTOR: &str = "(CC)Ljava/lang/String;";
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
    pub dynamic_source_sha256: String,
    pub heap_source_sha256: String,
}
pub(super) fn is_replace(o: &str, n: &str, d: &str) -> bool {
    o == "java/lang/String" && n == "replace" && d == DESCRIPTOR
}
pub(super) fn signature() -> numeric::Signature {
    numeric::Signature {
        arguments: vec![
            numeric::Type::BootstrapString,
            numeric::Type::I32,
            numeric::Type::I32,
        ],
        result: numeric::Type::BootstrapString,
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
        "String replacement requires original java.base sources"
    );
    Ok((id, origin.as_ref().clone()))
}
fn body(class: &ClassFile) -> Result<()> {
    let m = class.method("replace", Some(DESCRIPTOR))?;
    let code = m
        .code
        .as_ref()
        .context("String replacement must retain original Java Code")?;
    let b = &code.bytes;
    ensure!(
        class.access & 0x211 == 0x11 && m.access == 1 && code.handlers.is_empty() && b.len() == 42,
        "String replacement source contract changed"
    );
    for (i, v) in [
        (0, 0x1b),
        (1, 0x1c),
        (2, 0x9f),
        (3, 0),
        (4, 38),
        (5, 0x2a),
        (6, 0xb6),
        (9, 0x99),
        (10, 0),
        (11, 15),
        (12, 0x2a),
        (13, 0xb4),
        (16, 0x1b),
        (17, 0x1c),
        (18, 0xb8),
        (21, 0xa7),
        (22, 0),
        (23, 12),
        (24, 0x2a),
        (25, 0xb4),
        (28, 0x1b),
        (29, 0x1c),
        (30, 0xb8),
        (33, 0x4e),
        (34, 0x2d),
        (35, 0xc6),
        (36, 0),
        (37, 5),
        (38, 0x2d),
        (39, 0xb0),
        (40, 0x2a),
        (41, 0xb0),
    ] {
        ensure!(b[i] == v, "String replacement branch/identity body changed");
    }
    let cp = |i| u16::from_be_bytes([b[i], b[i + 1]]);
    ensure!(
        class.method_reference(cp(7))?
            == ("java/lang/String".into(), "isLatin1".into(), "()Z".into()),
        "String replacement encoding branch changed"
    );
    for i in [14, 26] {
        ensure!(
            class.field_reference(cp(i))?
                == ("java/lang/String".into(), "value".into(), "[B".into()),
            "String replacement backing field changed"
        );
    }
    for (i, owner) in [
        (19, "java/lang/StringLatin1"),
        (31, "java/lang/StringUTF16"),
    ] {
        let (o, n, d, interface) = class.static_method_reference(cp(i))?;
        ensure!(
            !interface && o == owner && n == "replace" && d == "([BCC)Ljava/lang/String;",
            "String replacement helper changed"
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
        is_replace(&o, &n, &d) && source.binary_name == caller.name.replace('/', "."),
        "String replacement caller changed"
    );
    let (id, origin) = original(registry, "java/lang/String")?;
    body(registry.definition(id).context("Missing String source")?)?;
    let mut helpers = Vec::new();
    for name in ["java/lang/StringUTF16", "java/lang/StringLatin1"] {
        let (id, origin) = original(registry, name)?;
        let m = registry
            .definition(id)
            .context("Missing replacement helper")?
            .method("replace", Some("([BCC)Ljava/lang/String;"))?;
        ensure!(
            m.access == 9 && m.code.is_some(),
            "Replacement helper public/static Java contract changed"
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
            "../../native/runtime/string_replace.asm"
        ))
        .sha256,
        string_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/strings.asm"
        ))
        .sha256,
        dynamic_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/string_dynamic.asm"
        ))
        .sha256,
        heap_source_sha256: files::digest_bytes(include_bytes!("../../native/runtime/heap.asm"))
            .sha256,
    })
}
