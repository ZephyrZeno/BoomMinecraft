//! Physical java.lang.Module fields shared by original Java and VM services.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/Module";
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub class_id: usize,
    pub layout: numeric::ObjectLayout,
    pub name_offset: usize,
    pub loader_offset: usize,
    pub layer_offset: usize,
    pub descriptor_offset: usize,
    pub loader_unnamed_offset: usize,
    pub native_source_sha256: String,
    pub original_unnamed_constructor_code_sha256: String,
    pub named_module_bootstrap_complete: bool,
    pub automatic_gc: bool,
    pub bootstrap_entry: bool,
}
impl Plan {
    pub(super) fn new(
        registry: &mut types::Registry<'_>,
        class_id: usize,
        layout: numeric::ObjectLayout,
        loader_layout: &numeric::ObjectLayout,
    ) -> Result<Self> {
        let id = registry.class("bootstrap", OWNER)?;
        let types::Type::Class { key, origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Physical Module objects require original java.base source"
        );
        let origin = origin.as_ref().clone();
        let class = registry.definition(id).unwrap();
        let m = class.method("<init>", Some("(Ljava/lang/ClassLoader;)V"))?;
        let code = m
            .code
            .as_ref()
            .context("Missing original Module constructor")?;
        ensure!(
            m.access == 0 && code.bytes.len() == 25,
            "Original unnamed Module constructor changed"
        );
        let field = |name: &str, desc: &str| -> Result<usize> {
            ensure!(
                class
                    .field_info
                    .iter()
                    .any(|f| f.name == name && f.descriptor == desc && f.access == 0x12),
                "Original Module field changed: {name}"
            );
            reference_slot(&layout, OWNER, name, desc)
        };
        Ok(Self {
            abi: 1,
            origin,
            class_id,
            name_offset: field("name", "Ljava/lang/String;")?,
            loader_offset: field("loader", "Ljava/lang/ClassLoader;")?,
            layer_offset: field("layer", "Ljava/lang/ModuleLayer;")?,
            descriptor_offset: field("descriptor", "Ljava/lang/module/ModuleDescriptor;")?,
            loader_unnamed_offset: reference_slot(
                loader_layout,
                "java/lang/ClassLoader",
                "unnamedModule",
                "Ljava/lang/Module;",
            )?,
            layout,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/module_objects.asm"
            ))
            .sha256,
            original_unnamed_constructor_code_sha256: files::digest_bytes(&code.bytes).sha256,
            named_module_bootstrap_complete: false,
            automatic_gc: false,
            bootstrap_entry: false,
        })
    }
}
pub(super) fn bootstrap_entry(class: &str, method: &str, descriptor: Option<&str>) -> bool {
    class.replace('.', "/") == OWNER
        && method == "<init>"
        && descriptor == Some("(Ljava/lang/ClassLoader;)V")
}
fn reference_slot(
    layout: &numeric::ObjectLayout,
    owner: &str,
    name: &str,
    desc: &str,
) -> Result<usize> {
    ensure!(
        layout.abi == 2,
        "Physical Module services require compact layout ABI2"
    );
    let f = layout
        .fields
        .iter()
        .find(|f| {
            f.name == name && f.descriptor == desc && f.declaring_class.as_deref() == Some(owner)
        })
        .context("Missing physical module reference slot")?;
    ensure!(
        f.storage_bytes == Some(8)
            && f.offset % 8 == 0
            && f.offset < layout.reference_prefix_fields * 8
            && f.offset + 8 <= layout.payload_bytes,
        "Module reference must fit the live reference prefix"
    );
    Ok(f.offset)
}
pub(super) fn original(class: &ClassFile, source: Option<&ClassOrigin>) -> bool {
    class.name == OWNER
        && source.is_some_and(|s| {
            s.loader == "bootstrap" && s.source_id == "jdk:java.base" && s.generated.is_none()
        })
}
