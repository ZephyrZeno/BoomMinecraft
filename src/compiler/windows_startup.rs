//! Source-bound Windows process startup API required by original System phase 1.
use super::{classfile::ClassFile, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "sun/io/Win32ErrorMode";
pub(super) fn is_native(owner: &str, name: &str, desc: &str) -> bool {
    owner == OWNER && name == "setErrorMode" && desc == "(J)J"
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub class_id: usize,
    pub bindings: Vec<Binding>,
    pub entry: Option<usize>,
    pub native_source_sha256: String,
    pub mutates_process_error_mode: bool,
    pub original_initialize_executed: bool,
}
impl Plan {
    pub(super) fn new(registry: &mut types::Registry<'_>, class_id: usize) -> Result<Self> {
        let id = registry.class("bootstrap", OWNER)?;
        let types::Type::Class { origin, key, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Win32ErrorMode requires its original java.base source"
        );
        let class = registry.definition(id).unwrap();
        let m = class.method("setErrorMode", Some("(J)J"))?;
        ensure!(
            m.access == 0x10a
                && m.code.is_none()
                && !class.methods.iter().any(|m| m.name == "<clinit>"),
            "Win32ErrorMode native or class initialization contract changed"
        );
        Ok(Self {
            abi: 1,
            origin: origin.as_ref().clone(),
            class_id,
            bindings: Vec::new(),
            entry: None,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/windows_startup.asm"
            ))
            .sha256,
            mutates_process_error_mode: true,
            original_initialize_executed: false,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
    ) -> Result<()> {
        let (o, n, d, i) = caller.static_method_reference(constant)?;
        ensure!(
            !i && is_native(&o, &n, &d) && caller.name == OWNER && source == &self.origin,
            "Win32ErrorMode native is private to its original caller"
        );
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.bindings.push(Binding {
                caller: source.clone(),
                constant,
            });
            self.bindings.sort_by_key(|b| b.constant);
        }
        Ok(())
    }
    pub(super) fn emit(&self, out: &mut String) {
        out.push_str("EXTERN boom_windows_error_mode:PROC\n");
        if let Some(id) = self.entry {
            out.push_str(&format!(".code\nboom_m{id} PROC FRAME\n    sub rsp,56\n    .allocstack 56\n    .endprolog\n    mov QWORD PTR [rsp+32],rcx\n    mov QWORD PTR [rsp+40],rdx\n    lea rcx,boom_class{}\n    mov rdx,QWORD PTR [rsp+32]\n    call boom_class_ensure\n    test eax,eax\n    jnz boom_windows_entry_error\n    mov rcx,QWORD PTR [rsp+32]\n    mov rdx,QWORD PTR [rsp+40]\n    call boom_windows_error_mode\n    jmp boom_windows_entry_done\nboom_windows_entry_error:\n    xor eax,eax\nboom_windows_entry_done:\n    add rsp,56\n    ret\nboom_m{id} ENDP\n",self.class_id));
        }
    }
}
