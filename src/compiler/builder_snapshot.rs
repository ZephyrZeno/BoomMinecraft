//! StringBuilder's source-verified new String(this) storage boundary.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/StringBuilder";
pub const DESCRIPTOR: &str = "()Ljava/lang/String;";
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Call {
    pub caller: ClassOrigin,
    pub constant: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub owner: usize,
    pub origin: ClassOrigin,
    pub abstract_origin: ClassOrigin,
    pub string_origin: ClassOrigin,
    pub value_offset: usize,
    pub coder_offset: usize,
    pub count_offset: usize,
    pub payload_bytes: usize,
    pub native_source_sha256: String,
    pub bindings: Vec<Call>,
}
pub(super) fn is_snapshot(o: &str, n: &str, d: &str) -> bool {
    o == OWNER && n == "toString" && d == DESCRIPTOR
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
        "Builder snapshot requires original java.base classes"
    );
    Ok((id, origin.as_ref().clone()))
}
impl Plan {
    pub(super) fn prepare(
        registry: &mut types::Registry<'_>,
        owner: usize,
        layout: &numeric::ObjectLayout,
    ) -> Result<Self> {
        let (id, origin) = original(registry, OWNER)?;
        let class = registry
            .definition(id)
            .context("Missing StringBuilder source")?;
        let m = class.method("toString", Some(DESCRIPTOR))?;
        let c = m.code.as_ref().context("Missing builder copy Code")?;
        let b = &c.bytes;
        ensure!(
            class.access & 0x211 == 0x11
                && m.access == 1
                && c.handlers.is_empty()
                && b.len() == 9
                && b[0] == 0xbb
                && b[3..6] == [0x59, 0x2a, 0xb7]
                && b[8] == 0xb0,
            "Builder toString must create new String(this)"
        );
        ensure!(
            class.constant_class(u16::from_be_bytes([b[1], b[2]]))? == "java/lang/String",
            "Builder result allocation changed"
        );
        let (o, n, d) = class.method_reference(u16::from_be_bytes([b[6], b[7]]))?;
        ensure!(
            o == "java/lang/String" && n == "<init>" && d == "(Ljava/lang/StringBuilder;)V",
            "Builder copy constructor changed"
        );
        let (ai, abstract_origin) = original(registry, "java/lang/AbstractStringBuilder")?;
        let parent = registry.definition(ai).context("Missing builder parent")?;
        for (n, d) in [
            ("value", "[B"),
            ("coder", "B"),
            ("maybeLatin1", "Z"),
            ("count", "I"),
        ] {
            let f = parent
                .field_info
                .iter()
                .find(|f| f.name == n && f.descriptor == d)
                .context("Missing builder storage field")?;
            ensure!(f.access == 0, "Builder storage field access changed");
        }
        let (si, string_origin) = original(registry, "java/lang/String")?;
        let ctor = registry
            .definition(si)
            .unwrap()
            .method("<init>", Some("(Ljava/lang/StringBuilder;)V"))?;
        ensure!(
            ctor.access == 1 && ctor.code.is_some(),
            "String builder copy constructor changed"
        );
        ensure!(
            layout.abi == 2 && layout.reference_prefix_fields == 1 && layout.fields.len() == 4,
            "Builder physical layout changed"
        );
        let offset = |name: &str, descriptor: &str, width: usize| -> Result<usize> {
            let f = layout
                .fields
                .iter()
                .find(|f| {
                    f.name == name
                        && f.descriptor == descriptor
                        && f.declaring_class.as_deref() == Some("java/lang/AbstractStringBuilder")
                })
                .context("Builder storage absent from physical layout")?;
            ensure!(
                f.storage_bytes == Some(width),
                "Builder field width changed"
            );
            Ok(f.offset)
        };
        Ok(Self {
            abi: 1,
            owner,
            origin,
            abstract_origin,
            string_origin,
            value_offset: offset("value", "[B", 8)?,
            coder_offset: offset("coder", "B", 1)?,
            count_offset: offset("count", "I", 4)?,
            payload_bytes: layout.payload_bytes,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/builder_snapshot.asm"
            ))
            .sha256,
            bindings: vec![],
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
    ) -> Result<()> {
        let (_, n, d, _) = caller.special_method_reference(constant)?;
        ensure!(
            n == "toString"
                && d == DESCRIPTOR
                && source.binary_name == caller.name.replace('/', "."),
            "Builder snapshot caller changed"
        );
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.bindings.push(Call {
                caller: source.clone(),
                constant,
            });
            self.bindings.sort_by(|a, b| {
                (&a.caller.binary_name, a.constant).cmp(&(&b.caller.binary_name, b.constant))
            });
        }
        Ok(())
    }
    pub(super) fn signature(&self) -> numeric::Signature {
        numeric::Signature {
            arguments: vec![numeric::Type::LinkedObject(self.owner)],
            result: numeric::Type::BootstrapString,
        }
    }
    pub(super) fn emit(&self, assembly: &mut String) {
        assembly.push_str(&format!("EXTERN boom_builder_snapshot:PROC\n.const\nALIGN 8\nboom_builder_snapshot_pool DWORD 042534E50h, 1\n    QWORD OFFSET boom_string_pool, OFFSET boom_layout{}\n    DWORD {}, {}, {}, 0\n    QWORD OFFSET boom_heap_ptr\n.code\nPUBLIC boom_get_builder_snapshot_pool\nboom_get_builder_snapshot_pool PROC\n    lea rax, boom_builder_snapshot_pool\n    ret\nboom_get_builder_snapshot_pool ENDP\n",self.owner,self.value_offset,self.coder_offset,self.count_offset));
    }
}
