//! VM-owned Class.classLoader field and immutable loader identities. Java API
//! bodies (including permission checks) remain original bytecode.
use super::{classfile::ClassFile, jdk_bridges, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
pub const OWNER: &str = "java/lang/Class";
pub const LOADER: &str = "java/lang/ClassLoader";
pub(super) fn field(o: &str, n: &str, d: &str) -> bool {
    o == OWNER && n == "classLoader" && d == "Ljava/lang/ClassLoader;"
}
pub(super) fn registration(o: &str, n: &str, d: &str) -> bool {
    o == LOADER && n == "registerNatives" && d == "()V"
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub class_origin: ClassOrigin,
    pub loader_origin: ClassOrigin,
    pub loader_type: usize,
    pub loader_vm_layout: numeric::ObjectLayout,
    pub bindings: Vec<Binding>,
    pub registration_bindings: Vec<Binding>,
    pub registered_name: String,
    pub registered_descriptor: String,
    pub retrieve_directives_implemented: bool,
    pub keys: Vec<String>,
    pub type_loader_ids: Vec<usize>,
    pub native_source_sha256: String,
    pub automatic_gc: bool,
    pub field_read_only: bool,
    pub application_loaders_require_explicit_binding: bool,
}
impl Plan {
    pub(super) fn new(
        registry: &mut types::Registry<'_>,
        layout: numeric::ObjectLayout,
    ) -> Result<Self> {
        let mut origins = Vec::new();
        let mut ids = Vec::new();
        for name in [OWNER, LOADER] {
            let id = registry.class("bootstrap", name)?;
            let types::Type::Class { key, origin, .. } = &registry.types[id] else {
                unreachable!()
            };
            ensure!(
                key.loader == "bootstrap"
                    && origin.source_id == "jdk:java.base"
                    && origin.generated.is_none(),
                "Class loader fields require original java.base definitions"
            );
            ids.push(id);
            origins.push(origin.as_ref().clone());
        }
        let loader = registry.definition(ids[1]).unwrap();
        for (name, desc) in [
            ("registerNatives", "()V"),
            (
                "retrieveDirectives",
                "()Ljava/lang/AssertionStatusDirectives;",
            ),
        ] {
            let method = loader.method(name, Some(desc))?;
            ensure!(
                method.access == 0x10a && method.code.is_none(),
                "ClassLoader native declaration changed: {name}"
            );
        }
        let class = registry.definition(ids[0]).unwrap();
        let f = class
            .field_info
            .iter()
            .find(|f| field(OWNER, &f.name, &f.descriptor))
            .context("Missing VM Class.classLoader field")?;
        ensure!(f.access == 0x12, "Class.classLoader field flags changed");
        let m = class.method("getClassLoader0", Some("()Ljava/lang/ClassLoader;"))?;
        let code = m
            .code
            .as_ref()
            .context("Class loader getter must retain original Code")?;
        ensure!(
            m.access == 0
                && code.bytes.len() == 5
                && code.bytes[0] == 0x2a
                && code.bytes[1] == 0xb4
                && code.bytes[4] == 0xb0,
            "Class.getClassLoader0 field contract changed"
        );
        let (o, n, d) =
            class.field_reference(u16::from_be_bytes([code.bytes[2], code.bytes[3]]))?;
        ensure!(
            field(&o, &n, &d),
            "Class loader getter field reference changed"
        );
        Ok(Self {
            abi: 1,
            class_origin: origins.remove(0),
            loader_origin: origins.remove(0),
            loader_type: ids[1],
            loader_vm_layout: layout,
            bindings: Vec::new(),
            registration_bindings: Vec::new(),
            registered_name: "retrieveDirectives".into(),
            registered_descriptor: "()Ljava/lang/AssertionStatusDirectives;".into(),
            retrieve_directives_implemented: false,
            keys: Vec::new(),
            type_loader_ids: Vec::new(),
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/class_loaders.asm"
            ))
            .sha256,
            automatic_gc: false,
            field_read_only: true,
            application_loaders_require_explicit_binding: true,
        })
    }
    pub(super) fn bind_registration(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
    ) -> Result<()> {
        let (o, n, d, interface) = caller.static_method_reference(constant)?;
        ensure!(
            !interface
                && registration(&o, &n, &d)
                && caller.name == LOADER
                && source == &self.loader_origin,
            "ClassLoader.registerNatives is private to original ClassLoader source"
        );
        if !self
            .registration_bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.registration_bindings.push(Binding {
                caller: source.clone(),
                constant,
            });
            self.registration_bindings.sort_by_key(|b| b.constant);
        }
        Ok(())
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
    ) -> Result<numeric::Signature> {
        let (o, n, d) = caller.field_reference(constant)?;
        ensure!(field(&o, &n, &d), "Class loader field reference changed");
        if source != &self.class_origin {
            jdk_bridges::validate(caller, source)?;
            let g = source.generated.as_ref().unwrap();
            ensure!(
                g.host_class == OWNER
                    && g.host_sha256 == self.class_origin.sha256
                    && matches!(g.site, 14 | 15),
                "Class loader field is private to original Class getters"
            );
        } else {
            ensure!(caller.name == OWNER, "Class field source identity mismatch");
        }
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.bindings.push(Binding {
                caller: source.clone(),
                constant,
            });
            self.bindings.sort_by(|a, b| {
                (&a.caller.binary_name, a.constant).cmp(&(&b.caller.binary_name, b.constant))
            });
        }
        Ok(numeric::Signature {
            arguments: vec![numeric::Type::BootstrapClass],
            result: numeric::Type::MetadataReference(self.loader_type),
        })
    }
    pub(super) fn finish(&mut self, types: &[types::Type]) -> Result<()> {
        self.finish_with_keys(types, &[])
    }
    pub(super) fn finish_with_keys(
        &mut self,
        types: &[types::Type],
        extra: &[String],
    ) -> Result<()> {
        let keys = types
            .iter()
            .enumerate()
            .map(|(id, _)| loader(types, id))
            .collect::<Result<Vec<_>>>()?;
        let mut unique = keys.iter().cloned().collect::<BTreeSet<_>>();
        ensure!(
            extra.iter().all(|k| !k.is_empty()),
            "Empty module defining loader key"
        );
        unique.extend(extra.iter().cloned());
        unique.remove("bootstrap");
        self.keys = std::iter::once("bootstrap".into()).chain(unique).collect();
        self.type_loader_ids = keys
            .iter()
            .map(|key| self.keys.iter().position(|k| k == key).unwrap())
            .collect();
        ensure!(
            self.keys.len() <= 16384 && types.len() <= 16384,
            "Class loader identity table exceeds ABI budget"
        );
        Ok(())
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        ensure!(
            !self.keys.is_empty() && !self.type_loader_ids.is_empty(),
            "Class loader table is not frozen"
        );
        out.push_str("EXTERN boom_class_loader_field:PROC\nEXTERN boom_class_loader_bind:PROC\n.const\nALIGN 8\n");
        if !self.registration_bindings.is_empty() {
            out.push_str("EXTERN boom_class_loader_register:PROC\nEXTERN boom_class_loader_retrieve:PROC\n.data\nALIGN 8\nboom_loader_native_pool DWORD 050524E4Ch,1,0,1\n    QWORD OFFSET boom_class_loader_retrieve,0\n.code\nPUBLIC boom_get_class_loader_native_pool\nboom_get_class_loader_native_pool PROC\n    lea rax,boom_loader_native_pool\n    ret\nboom_get_class_loader_native_pool ENDP\n.const\n");
        }
        out.push_str(&format!(
            "boom_loader_vm_layout DWORD 04F424A43h,{}\n    QWORD {}\n    DWORD {},{}\n",
            self.loader_vm_layout.abi,
            self.loader_vm_layout.payload_bytes,
            self.loader_vm_layout.reference_prefix_fields,
            self.loader_vm_layout.fields.len()
        ));
        out.push_str("ALIGN 4\nboom_loader_type_ids LABEL DWORD\n");
        for id in &self.type_loader_ids {
            out.push_str(&format!("    DWORD {id}\n"));
        }
        out.push_str(".data\nALIGN 4\nboom_loader_bound LABEL DWORD\n");
        for key in &self.keys {
            out.push_str(&format!("    DWORD {}\n", u32::from(key == "bootstrap")));
        }
        out.push_str(&format!("ALIGN 8\nboom_loader_pool DWORD 05052444Ch,1\n    QWORD OFFSET boom_heap_ptr,OFFSET boom_mirror_pool,OFFSET boom_runtime_type_map\n    QWORD OFFSET boom_loader_roots,OFFSET boom_loader_bound,OFFSET boom_loader_type_ids\n    DWORD {},{}\n    QWORD OFFSET boom_t{},OFFSET boom_trace_pool,0,0\n.code\nPUBLIC boom_get_class_loader_pool\nboom_get_class_loader_pool PROC\n    lea rax,boom_loader_pool\n    ret\nboom_get_class_loader_pool ENDP\n",self.keys.len(),self.type_loader_ids.len(),self.loader_type));
        Ok(())
    }
}
fn loader(types: &[types::Type], mut id: usize) -> Result<String> {
    for _ in 0..=255 {
        match types.get(id).context("Missing loader type")? {
            types::Type::Primitive { .. } => return Ok("bootstrap".into()),
            types::Type::Class { key, .. } => return Ok(key.loader.clone()),
            types::Type::Array { component } => id = *component,
        }
    }
    anyhow::bail!("Cyclic or excessive array loader relationship")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn array_loaders_follow_components_and_reject_cycles() {
        let types = vec![
            types::Type::Primitive {
                value: types::Primitive::Int,
            },
            types::Type::Array { component: 0 },
            types::Type::Class {
                key: types::ClassKey {
                    loader: "application-test".into(),
                    name: "Example".into(),
                },
                origin: Box::new(ClassOrigin {
                    loader: "application-test".into(),
                    binary_name: "Example".into(),
                    source_id: "fixture".into(),
                    jar_entry: "Example.class".into(),
                    java_class_major: 65,
                    sha256: "0".repeat(64),
                    generated: None,
                }),
                access: 1,
                superclass: None,
                interfaces: vec![],
            },
            types::Type::Array { component: 2 },
            types::Type::Array { component: 3 },
            types::Type::Array { component: 5 },
        ];
        assert_eq!(loader(&types, 1).unwrap(), "bootstrap");
        assert_eq!(loader(&types, 4).unwrap(), "application-test");
        assert!(loader(&types, 5).is_err());
        assert!(loader(&types, 6).is_err());
    }
}
