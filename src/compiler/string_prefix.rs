//! String.startsWith(String,int) at the VM-owned UTF16 storage boundary.
//! The one-argument and suffix wrappers retain their original Java Code.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const DESCRIPTOR: &str = "(Ljava/lang/String;I)Z";
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub origin: ClassOrigin,
    pub arrays_support_origin: ClassOrigin,
    pub utf16_origin: ClassOrigin,
    pub code_sha256: String,
    pub storage_abi: u32,
    pub compact_strings: bool,
    pub native_source_sha256: String,
    pub string_source_sha256: String,
    pub heap_source_sha256: String,
    pub vector_bytes: u32,
}
pub(super) fn is_prefix(o: &str, n: &str, d: &str) -> bool {
    o == "java/lang/String" && n == "startsWith" && d == DESCRIPTOR
}
pub(super) fn signature() -> numeric::Signature {
    use numeric::Type::{BootstrapString as S, I32};
    numeric::Signature {
        arguments: vec![S, S, I32],
        result: I32,
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
        "String prefix comparison requires original java.base sources"
    );
    Ok((id, origin.as_ref().clone()))
}
fn body(class: &ClassFile) -> Result<String> {
    let m = class.method("startsWith", Some(DESCRIPTOR))?;
    let c = m
        .code
        .as_ref()
        .context("String prefix comparison requires original Java Code")?;
    ensure!(
        class.access & 0x211 == 0x11
            && m.access == 1
            && c.handlers.is_empty()
            && c.bytes.len() == 123,
        "String prefix source shape changed"
    );
    let b = &c.bytes;
    let cp = |i| u16::from_be_bytes([b[i], b[i + 1]]);
    for (i, n, d) in [
        (7, "length", "()I"),
        (11, "length", "()I"),
        (40, "coder", "()B"),
        (48, "coder", "()B"),
    ] {
        ensure!(
            class.method_reference(cp(i))? == ("java/lang/String".into(), n.into(), d.into()),
            "String prefix length/encoding contract changed"
        );
    }
    for i in [21, 26] {
        ensure!(
            class.field_reference(cp(i))?
                == ("java/lang/String".into(), "value".into(), "[B".into()),
            "String prefix backing field changed"
        );
    }
    for (i, o, n, d) in [
        (
            71,
            "jdk/internal/util/ArraysSupport",
            "mismatch",
            "([BI[BII)I",
        ),
        (102, "java/lang/StringUTF16", "getChar", "([BI)C"),
    ] {
        let (owner, name, desc, interface) = class.static_method_reference(cp(i))?;
        ensure!(
            !interface && owner == o && name == n && desc == d,
            "String prefix comparison helper changed"
        );
    }
    let mut normalized = b.clone();
    for i in [7, 11, 21, 26, 40, 48, 71, 102] {
        normalized[i..i + 2].fill(0);
    }
    let actual = normalized
        .iter()
        .map(|v| format!("{v:02x}"))
        .collect::<String>();
    ensure!(
        actual
            == "1c9b00101c2ab600002bb6000064a4000503ac2ab400004e2bb400003a040336051904be36062ab60000360715072bb60000a00020150704a000071c04783d2d1c1904031506b800009c000704a7000403ac15079a000503ac15051506a2001c2d1c840201b8000019041505840501331100ff7e9fffe503ac04ac",
        "String prefix branches or comparison body changed"
    );
    Ok(files::digest_bytes(b).sha256)
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
) -> Result<Binding> {
    let (o, n, d) = caller.method_reference(constant)?;
    ensure!(
        is_prefix(&o, &n, &d) && source.binary_name == caller.name.replace('/', "."),
        "String prefix caller changed"
    );
    let (id, origin) = original(registry, "java/lang/String")?;
    let code_sha256 = body(
        registry
            .definition(id)
            .context("Missing String definition")?,
    )?;
    let (id, arrays_support_origin) = original(registry, "jdk/internal/util/ArraysSupport")?;
    let m = registry
        .definition(id)
        .context("Missing arrays comparison source")?
        .method("mismatch", Some("([BI[BII)I"))?;
    ensure!(
        m.access == 9 && m.code.is_some(),
        "Arrays comparison helper contract changed"
    );
    let (_, utf16_origin) = original(registry, "java/lang/StringUTF16")?;
    Ok(Binding {
        abi: 1,
        caller: source.clone(),
        constant,
        origin,
        arrays_support_origin,
        utf16_origin,
        code_sha256,
        storage_abi: 3,
        compact_strings: false,
        vector_bytes: 16,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/string_prefix.asm"
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
