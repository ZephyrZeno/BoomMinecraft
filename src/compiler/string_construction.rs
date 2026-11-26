//! Constructors across the VM-owned UTF16 String representation boundary.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/String";
pub const DESCRIPTOR: &str = "([CII)V";
pub const ALL_DESCRIPTOR: &str = "([C)V";
pub(super) fn supports(descriptor: &str) -> bool {
    matches!(descriptor, DESCRIPTOR | ALL_DESCRIPTOR)
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub allocation: bool,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub origin: ClassOrigin,
    pub constructor_code_sha256: String,
    pub descriptor: String,
    pub storage_abi: u32,
    pub compact_strings: bool,
    #[serde(rename = "original_Java_constructor_executed")]
    pub original_java_constructor_executed: bool,
    pub native_source_sha256: String,
    pub string_source_sha256: String,
    pub heap_source_sha256: String,
    pub object_source_sha256: String,
    pub automatic_gc: bool,
}
pub(super) fn signature(descriptor: &str) -> numeric::Signature {
    use numeric::{ArrayKind, Signature, Type};
    let mut arguments = vec![Type::BootstrapString, Type::Array(ArrayKind::Char)];
    if descriptor == DESCRIPTOR {
        arguments.extend([Type::I32, Type::I32]);
    }
    Signature {
        arguments,
        result: Type::Void,
    }
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    allocation: bool,
) -> Result<Binding> {
    ensure!(
        source.binary_name == caller.name.replace('/', "."),
        "String construction caller changed"
    );
    let mut descriptor = DESCRIPTOR;
    let requested;
    if allocation {
        ensure!(
            caller.constant_class(constant)? == OWNER,
            "String allocation class changed"
        );
    } else {
        let (o, n, d, interface) = caller.special_method_reference(constant)?;
        ensure!(
            !interface && o == OWNER && n == "<init>" && supports(&d),
            "Unsupported VM String constructor"
        );
        requested = d;
        descriptor = &requested;
    }
    let id = registry.class("bootstrap", OWNER)?;
    let types::Type::Class { key, origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "String construction needs original java.base"
    );
    let class = registry
        .definition(id)
        .context("Missing String definition")?;
    ensure!(
        class.access & 0x211 == 0x11,
        "String construction requires the original concrete final class"
    );
    let method = class.method("<init>", Some(DESCRIPTOR))?;
    let code = method
        .code
        .as_ref()
        .context("Missing String constructor Code")?;
    ensure!(
        method.access == 1 && code.bytes.len() == 14 && code.handlers.is_empty(),
        "String range constructor changed"
    );
    let b = &code.bytes;
    ensure!(
        b[..7] == [0x2a, 0x2b, 0x1c, 0x1d, 0x2b, 0x1c, 0x1d]
            && b[7] == 0xb8
            && b[10] == 0xb7
            && b[13] == 0xb1,
        "String constructor evaluation order changed"
    );
    let cp = |i| u16::from_be_bytes([b[i], b[i + 1]]);
    ensure!(
        class.static_method_reference(cp(8))?
            == (
                OWNER.into(),
                "rangeCheck".into(),
                "([CII)Ljava/lang/Void;".into(),
                false
            )
            && class.special_method_reference(cp(11))?
                == (
                    OWNER.into(),
                    "<init>".into(),
                    "([CIILjava/lang/Void;)V".into(),
                    false
                ),
        "String range delegation changed"
    );
    let range = class.method("rangeCheck", Some("([CII)Ljava/lang/Void;"))?;
    ensure!(
        range.access == 0xa && range.code.as_ref().is_some_and(|c| c.bytes.len() == 10),
        "String null/bounds check changed"
    );
    let utf16 = class.method("<init>", Some("([CIILjava/lang/Void;)V"))?;
    ensure!(
        utf16.access == 2 && utf16.code.is_some(),
        "String UTF16 construction helper changed"
    );
    let constructor = if descriptor == ALL_DESCRIPTOR {
        let all = class.method("<init>", Some(ALL_DESCRIPTOR))?;
        let all_code = all
            .code
            .as_ref()
            .context("Missing String full-array constructor Code")?;
        let a = &all_code.bytes;
        ensure!(
            all.access == 1
                && a.len() == 10
                && all_code.handlers.is_empty()
                && a[..7] == [0x2a, 0x2b, 0x03, 0x2b, 0xbe, 0x01, 0xb7]
                && a[9] == 0xb1,
            "String full-array constructor evaluation order changed"
        );
        ensure!(
            class.special_method_reference(u16::from_be_bytes([a[7], a[8]]))?
                == (
                    OWNER.into(),
                    "<init>".into(),
                    "([CIILjava/lang/Void;)V".into(),
                    false
                ),
            "String full-array delegation changed"
        );
        a
    } else {
        b
    };
    Ok(Binding {
        abi: 1,
        allocation,
        caller: source.clone(),
        constant,
        origin: origin.as_ref().clone(),
        constructor_code_sha256: files::digest_bytes(constructor).sha256,
        descriptor: descriptor.into(),
        storage_abi: 3,
        compact_strings: false,
        original_java_constructor_executed: false,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/string_construction.asm"
        ))
        .sha256,
        string_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/strings.asm"
        ))
        .sha256,
        heap_source_sha256: files::digest_bytes(include_bytes!("../../native/runtime/heap.asm"))
            .sha256,
        object_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/objects.asm"
        ))
        .sha256,
        automatic_gc: false,
    })
}
