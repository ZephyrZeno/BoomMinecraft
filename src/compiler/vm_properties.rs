//! Frozen native-image properties. Only configuration is handled in Rust;
//! property array construction and all guest execution are handwritten MASM.
use super::{classfile::ClassFile, numeric, system_properties, types};
use crate::{bytecode::ClassOrigin, files, lock::InputLock};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::Path};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Property {
    pub key: String,
    pub value: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Profile {
    pub schema: u32,
    pub java_home: String,
    pub class_path: String,
    pub library_path: String,
    #[serde(default)]
    pub properties: Vec<Property>,
}
impl Profile {
    pub fn for_image(inputs: &InputLock, output: &Path) -> Result<Self> {
        // Explicit compilation creates its output directory after graph checks.
        let home = std::path::absolute(output)?;
        Ok(Self {
            schema: 1,
            java_home: home.to_string_lossy().into_owned(),
            class_path: std::env::join_paths(inputs.classpath_paths()?)?
                .into_string()
                .map_err(|_| anyhow::anyhow!("Non-Unicode native class path"))?,
            library_path: inputs
                .natives_directory
                .as_ref()
                .unwrap_or(&home)
                .to_string_lossy()
                .into_owned(),
            properties: Vec::new(),
        })
    }
    pub fn read(path: &Path) -> Result<Self> {
        ensure!(
            std::fs::metadata(path)?.len() <= 1024 * 1024,
            "VM profile exceeds limit"
        );
        let p: Self = serde_json::from_slice(&std::fs::read(path)?)?;
        p.values()?;
        Ok(p)
    }
    pub(super) fn values(&self) -> Result<BTreeMap<String, String>> {
        ensure!(self.schema == 1, "Unsupported native VM profile");
        ensure!(
            Path::new(&self.java_home).is_absolute(),
            "Native java.home must be absolute"
        );
        ensure!(
            self.properties.len() <= 1024,
            "Too many VM property definitions"
        );
        let mut values: BTreeMap<String, String> = [
            ("java.home", self.java_home.as_str()),
            ("java.class.path", self.class_path.as_str()),
            ("java.library.path", self.library_path.as_str()),
            ("sun.boot.library.path", self.library_path.as_str()),
            ("java.class.version", "65.0"),
            ("java.vm.name", "BoomMinecraft Assembly VM"),
            ("java.vm.vendor", "BoomMinecraft"),
            ("java.vm.version", env!("CARGO_PKG_VERSION")),
            ("java.vm.info", "ahead-of-time assembly"),
            (
                "java.vm.specification.name",
                "Java Virtual Machine Specification",
            ),
            ("java.vm.specification.vendor", "Oracle Corporation"),
            ("java.vm.specification.version", "21"),
            ("jdk.debug", "release"),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_owned(), v.to_owned()))
        .collect();
        for p in &self.properties {
            ensure!(
                !p.key.starts_with("java.vm.")
                    && p.key != "java.class.version"
                    && p.key != "sun.nio.MaxDirectMemorySize",
                "VM-owned property cannot be overridden: {}",
                p.key
            );
            values.insert(p.key.clone(), p.value.clone().unwrap_or_default());
        }
        let mut units = 0usize;
        for (k, v) in &values {
            ensure!(
                !k.is_empty() && !k.contains(['\0', '=']) && !v.contains('\0'),
                "Invalid VM property text"
            );
            let n = k.encode_utf16().count() + v.encode_utf16().count();
            ensure!(
                k.encode_utf16().count() <= 65535 && v.encode_utf16().count() <= 65535,
                "VM property exceeds string limit"
            );
            units += n;
        }
        ensure!(
            units <= 512 * 1024,
            "VM property profile exceeds UTF16 budget"
        );
        ensure!(
            values
                .get("java.home")
                .is_some_and(|p| Path::new(p).is_absolute()),
            "Native java.home override must be absolute"
        );
        Ok(values)
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Row {
    pub name: String,
    pub key_literal: usize,
    pub value_literal: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub class_id: usize,
    pub origin: ClassOrigin,
    pub profile: Profile,
    pub rows: Vec<Row>,
    pub bindings: Vec<system_properties::Binding>,
    pub entry_method_id: Option<usize>,
    pub native_source_sha256: String,
    pub string_storage_abi: u32,
    pub string_source_sha256: String,
    pub heap_source_sha256: String,
    pub reference_source_sha256: String,
}
pub(super) fn is_native(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == system_properties::OWNER
        && name == "vmProperties"
        && descriptor == system_properties::DESCRIPTOR
}
pub(super) fn verify(class: &ClassFile, origin: &ClassOrigin) -> Result<()> {
    ensure!(
        class.name == system_properties::OWNER
            && origin.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none()
            && origin.binary_name == class.name.replace('/', "."),
        "VM property native requires original Raw source"
    );
    let m = class.method("vmProperties", Some(system_properties::DESCRIPTOR))?;
    ensure!(
        m.access == 0x10a && m.code.is_none(),
        "Raw.vmProperties native contract changed"
    );
    Ok(())
}
impl Plan {
    pub(super) fn prepare(
        registry: &mut types::Registry<'_>,
        class_id: usize,
        profile: Profile,
        mut literal: impl FnMut(&str) -> Result<usize>,
    ) -> Result<Self> {
        let id = registry.class("bootstrap", system_properties::OWNER)?;
        let types::Type::Class { origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        let origin = origin.as_ref().clone();
        verify(
            registry.definition(id).context("Missing Raw source")?,
            &origin,
        )?;
        let rows = profile
            .values()?
            .into_iter()
            .map(|(name, value)| {
                Ok(Row {
                    key_literal: literal(&name)?,
                    value_literal: literal(&value)?,
                    name,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        Ok(Self {
            abi: 1,
            class_id,
            origin,
            profile,
            rows,
            bindings: Vec::new(),
            entry_method_id: None,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/vm_properties.asm"
            ))
            .sha256,
            string_storage_abi: 3,
            string_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/strings.asm"
            ))
            .sha256,
            heap_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/heap.asm"
            ))
            .sha256,
            reference_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/references.asm"
            ))
            .sha256,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        origin: &ClassOrigin,
        constant: u16,
    ) -> Result<()> {
        let (o, n, d, i) = caller.static_method_reference(constant)?;
        ensure!(
            !i && is_native(&o, &n, &d)
                && caller.name == system_properties::OWNER
                && origin == &self.origin,
            "Raw private VM native requires its original declaring caller"
        );
        if !self.bindings.iter().any(|b| b.constant == constant) {
            self.bindings.push(system_properties::Binding {
                constant,
                caller: origin.clone(),
            });
            self.bindings.sort_by_key(|b| b.constant);
        }
        Ok(())
    }
    pub(super) fn signature() -> numeric::Signature {
        system_properties::Plan::signature()
    }
    pub(super) fn emit(&self, out: &mut String) {
        out.push_str(
            "EXTERN boom_vm_properties:PROC\n.const\nALIGN 8\nboom_vm_property_rows LABEL DWORD\n",
        );
        for r in &self.rows {
            out.push_str(&format!(
                "    DWORD {}, {}\n",
                r.key_literal, r.value_literal
            ));
        }
        out.push_str(&format!(".data\nALIGN 8\nboom_vm_property_pool DWORD 0564D5052h, 1, {}, 0\n    QWORD OFFSET boom_heap_ptr, OFFSET boom_string_pool, OFFSET boom_string_array_layout, OFFSET boom_vm_property_rows\n    QWORD 0, 0\n.code\nPUBLIC boom_get_vm_property_pool\nboom_get_vm_property_pool PROC\n    lea rax, boom_vm_property_pool\n    ret\nboom_get_vm_property_pool ENDP\n", self.rows.len()));
        if let Some(m) = self.entry_method_id {
            let c = self.class_id;
            out.push_str(&format!("; VM-owned invoker for original private static native Raw.vmProperties.\nboom_m{m} PROC FRAME\n    sub rsp, 56\n    .allocstack 56\n    .endprolog\n    mov QWORD PTR [rsp+40], rcx\n    cmp DWORD PTR [rcx], 0\n    jne boom_vm_entry{m}_error\n    lea rcx, boom_class{c}\n    mov rdx, QWORD PTR [rsp+40]\n    call boom_class_ensure\n    test eax, eax\n    jnz boom_vm_entry{m}_error\n    mov rcx, QWORD PTR [rsp+40]\n    xor edx, edx\n    lea r8, boom_vm_property_pool\n    call boom_vm_properties\n    jmp boom_vm_entry{m}_done\nboom_vm_entry{m}_error:\n    xor eax, eax\nboom_vm_entry{m}_done:\n    add rsp, 56\n    ret\nboom_m{m} ENDP\n"));
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn profile() -> Profile {
        Profile {
            schema: 1,
            java_home: r"D:\native-image".into(),
            class_path: "a.jar;b.jar".into(),
            library_path: r"D:\native-image\native".into(),
            properties: vec![],
        }
    }
    #[test]
    fn definitions_are_frozen_last_wins_and_null_becomes_empty() {
        let mut p = profile();
        p.properties = vec![
            Property {
                key: "x".into(),
                value: Some("first".into()),
            },
            Property {
                key: "x".into(),
                value: Some("最后 🧱".into()),
            },
            Property {
                key: "empty".into(),
                value: None,
            },
        ];
        let v = p.values().unwrap();
        assert_eq!(v["x"], "最后 🧱");
        assert_eq!(v["empty"], "");
        assert_eq!(v["java.vm.name"], "BoomMinecraft Assembly VM");
        p.properties.reverse();
        assert_eq!(p.values().unwrap()["x"], "first");
    }
    #[test]
    fn invalid_or_unimplemented_vm_owned_configuration_is_rejected() {
        for key in [
            "",
            "x=y",
            "a\0b",
            "java.vm.name",
            "java.class.version",
            "sun.nio.MaxDirectMemorySize",
        ] {
            let mut p = profile();
            p.properties.push(Property {
                key: key.into(),
                value: None,
            });
            assert!(p.values().is_err(), "{key}");
        }
        let mut p = profile();
        p.schema = 2;
        assert!(p.values().is_err());
        p = profile();
        p.java_home = "relative".into();
        assert!(p.values().is_err());
    }
}
