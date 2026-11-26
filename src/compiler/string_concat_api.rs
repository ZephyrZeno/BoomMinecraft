//! Source-verified String.concat; allocation and UTF16 copying are assembly.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/String";
pub const DESCRIPTOR: &str = "(Ljava/lang/String;)Ljava/lang/String;";
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub origin: ClassOrigin,
    pub helper_origin: ClassOrigin,
    pub native_source_sha256: String,
}
pub(super) fn is_concat(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == OWNER && name == "concat" && descriptor == DESCRIPTOR
}
pub(super) fn signature() -> numeric::Signature {
    numeric::Signature {
        arguments: vec![numeric::Type::BootstrapString; 2],
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
        "String.concat requires original bootstrap members"
    );
    Ok((id, origin.as_ref().clone()))
}
fn body(class: &ClassFile) -> Result<()> {
    let method = class.method("concat", Some(DESCRIPTOR))?;
    ensure!(
        class.access & 0x211 == 0x11 && method.access == 1,
        "String.concat public/final-class contract changed"
    );
    let code = method
        .code
        .as_ref()
        .context("String.concat must be original Java code")?;
    let b = &code.bytes;
    ensure!(
        b.len() == 15
            && code.handlers.is_empty()
            && b[0] == 0x2b
            && b[1] == 0xb6
            && b[4..11] == [0x99, 0, 5, 0x2a, 0xb0, 0x2a, 0x2b]
            && b[11] == 0xb8
            && b[14] == 0xb0,
        "String.concat empty-suffix/identity body changed"
    );
    ensure!(
        class.method_reference(u16::from_be_bytes([b[2], b[3]]))?
            == (OWNER.into(), "isEmpty".into(), "()Z".into()),
        "String.concat emptiness delegate changed"
    );
    let (owner, name, descriptor, interface) =
        class.static_method_reference(u16::from_be_bytes([b[12], b[13]]))?;
    ensure!(
        !interface
            && owner == "java/lang/StringConcatHelper"
            && name == "simpleConcat"
            && descriptor == "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/String;",
        "String.concat allocation delegate changed"
    );
    let copy = class.method("<init>", Some("(Ljava/lang/String;)V"))?;
    ensure!(
        copy.access == 1 && copy.code.is_some(),
        "String copy construction contract changed"
    );
    Ok(())
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    caller_origin: &ClassOrigin,
    constant: u16,
) -> Result<Binding> {
    let (owner, name, descriptor) = caller.method_reference(constant)?;
    ensure!(
        is_concat(&owner, &name, &descriptor)
            && caller_origin.binary_name == caller.name.replace('/', "."),
        "String.concat caller proof changed"
    );
    let (id, origin) = original(registry, OWNER)?;
    body(registry.definition(id).context("Missing original String")?)?;
    let (helper, helper_origin) = original(registry, "java/lang/StringConcatHelper")?;
    let helper = registry
        .definition(helper)
        .context("Missing StringConcatHelper")?
        .method(
            "simpleConcat",
            Some("(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/String;"),
        )?;
    ensure!(
        helper.access == 8 && helper.code.is_some(),
        "String concatenation helper contract changed"
    );
    Ok(Binding {
        abi: 1,
        caller: caller_origin.clone(),
        constant,
        origin,
        helper_origin,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/string_concat_api.asm"
        ))
        .sha256,
    })
}
