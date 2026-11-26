//! VM-owned UTF16 storage configuration. Constants execute as generated MASM.
use super::{classfile::ClassFile, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Property {
    CompactStrings,
    BigEndian,
    Coder,
    GetBytes,
    GetBytesRange,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub property: Property,
    pub value: u32,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub origin: ClassOrigin,
    pub storage_abi: u32,
    pub string_source_sha256: String,
    pub dynamic_source_sha256: String,
    pub target: String,
    pub method_code_sha256: Option<String>,
}
pub(super) fn compact_field(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == "java/lang/String" && name == "COMPACT_STRINGS" && descriptor == "Z"
}
pub(super) fn endian_method(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == "java/lang/StringUTF16" && name == "isBigEndian" && descriptor == "()Z"
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    property: Property,
) -> Result<Binding> {
    ensure!(
        source.loader == "bootstrap"
            && source.source_id == "jdk:java.base"
            && source.generated.is_none()
            && source.binary_name == caller.name.replace('/', ".")
            && caller.name.rsplit_once('/').map(|p| p.0) == Some("java/lang"),
        "String storage configuration requires original java.lang access"
    );
    let name = match property {
        Property::CompactStrings
        | Property::Coder
        | Property::GetBytes
        | Property::GetBytesRange => "java/lang/String",
        Property::BigEndian => "java/lang/StringUTF16",
    };
    let id = registry.class("bootstrap", name)?;
    let types::Type::Class { key, origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "String storage requires original bootstrap source"
    );
    let class = registry
        .definition(id)
        .context("Missing string storage source")?;
    let mut method_code_sha256 = None;
    match property {
        Property::GetBytes | Property::GetBytesRange => {
            let descriptor = if property == Property::GetBytes {
                "([BIB)V"
            } else {
                "([BIIBI)V"
            };
            ensure!(
                caller.method_reference(constant)?
                    == (name.into(), "getBytes".into(), descriptor.into()),
                "String byte-copy reference changed"
            );
            let method = class.method("getBytes", Some(descriptor))?;
            ensure!(
                method.access == 0,
                "String byte-copy method must have package access"
            );
            let code = method
                .code
                .as_ref()
                .context("String byte-copy requires original Java Code")?;
            ensure!(
                code.handlers.is_empty() && !code.bytes.is_empty(),
                "String byte-copy Code contract changed"
            );
            method_code_sha256 = Some(files::digest_bytes(&code.bytes).sha256);
        }
        Property::Coder => {
            let (o, n, d) = caller.method_reference(constant)?;
            ensure!(
                o == "java/lang/String" && n == "coder" && d == "()B",
                "String coder reference changed"
            );
            let m = class.method(&n, Some(&d))?;
            let code = m
                .code
                .as_ref()
                .context("String coder requires original Java Code")?;
            ensure!(
                m.access == 0
                    && code.handlers.is_empty()
                    && code.bytes.len() == 15
                    && code.bytes[0] == 0xb2
                    && code.bytes[3..8] == [0x99, 0, 10, 0x2a, 0xb4]
                    && code.bytes[10..15] == [0xa7, 0, 4, 4, 0xac],
                "String coder access/body contract changed"
            );
            ensure!(
                class.field_reference(u16::from_be_bytes([code.bytes[1], code.bytes[2]]))?
                    == (
                        "java/lang/String".into(),
                        "COMPACT_STRINGS".into(),
                        "Z".into()
                    ),
                "String coder compact configuration changed"
            );
            ensure!(
                class.field_reference(u16::from_be_bytes([code.bytes[8], code.bytes[9]]))?
                    == ("java/lang/String".into(), "coder".into(), "B".into()),
                "String coder backing field changed"
            );
        }
        Property::CompactStrings => {
            let (o, n, d) = caller.field_reference(constant)?;
            ensure!(
                compact_field(&o, &n, &d),
                "String compact field reference changed"
            );
            let field = class
                .field_info
                .iter()
                .find(|f| f.name == n && f.descriptor == d)
                .context("Missing VM String compact flag")?;
            ensure!(
                field.access == 0x18 && field.constant_value.is_none(),
                "String compact flag must be VM-injected, package static final and non-ConstantValue"
            );
        }
        Property::BigEndian => {
            let (o, n, d, i) = caller.static_method_reference(constant)?;
            ensure!(
                !i && endian_method(&o, &n, &d) && caller.name == name && source == origin.as_ref(),
                "Private endian native requires its original caller"
            );
            let m = class.method(&n, Some(&d))?;
            ensure!(
                m.access == 0x10a && m.code.is_none(),
                "UTF16 endian native contract changed"
            );
        }
    }
    Ok(Binding {
        abi: 1,
        property,
        value: if property == Property::Coder { 1 } else { 0 },
        caller: source.clone(),
        constant,
        origin: origin.as_ref().clone(),
        storage_abi: 3,
        string_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/strings.asm"
        ))
        .sha256,
        dynamic_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/string_dynamic.asm"
        ))
        .sha256,
        target: "windows-x86_64-little-endian-UTF16".into(),
        method_code_sha256,
    })
}
