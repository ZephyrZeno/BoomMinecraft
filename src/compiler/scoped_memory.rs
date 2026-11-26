//! Original ScopedMemoryAccess bootstrap. Its close handshake remains explicit.
use super::{classfile::ClassFile, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "jdk/internal/misc/ScopedMemoryAccess";
pub(super) fn registration(owner: &str, name: &str, desc: &str) -> bool {
    owner == OWNER && name == "registerNatives" && desc == "()V"
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
    pub registered_name: String,
    pub registered_descriptor: String,
    pub close_scope_implemented: bool,
    pub native_source_sha256: String,
    pub automatic_gc: bool,
}
impl Plan {
    pub(super) fn new(registry: &mut types::Registry<'_>, class_id: usize) -> Result<Self> {
        let id = registry.class("bootstrap", OWNER)?;
        let types::Type::Class { key, origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "ScopedMemoryAccess requires original java.base source"
        );
        let class = registry.definition(id).unwrap();
        ensure!(
            class
                .methods
                .iter()
                .filter(|m| m.access & 0x100 != 0)
                .count()
                == 2,
            "ScopedMemoryAccess native inventory changed"
        );
        for (name, desc, flags) in [
            ("registerNatives", "()V", 0x10a),
            (
                "closeScope0",
                "(Ljdk/internal/foreign/MemorySessionImpl;)Z",
                0x100,
            ),
        ] {
            let m = class.method(name, Some(desc))?;
            ensure!(
                m.access == flags && m.code.is_none(),
                "ScopedMemoryAccess native declaration changed: {name}"
            );
        }
        Ok(Self {
            abi: 1,
            origin: origin.as_ref().clone(),
            class_id,
            bindings: Vec::new(),
            registered_name: "closeScope0".into(),
            registered_descriptor: "(Ljdk/internal/foreign/MemorySessionImpl;)Z".into(),
            close_scope_implemented: false,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/scoped_memory.asm"
            ))
            .sha256,
            automatic_gc: false,
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
            !i && registration(&o, &n, &d) && caller.name == OWNER && source == &self.origin,
            "ScopedMemoryAccess.registerNatives is private to its original source"
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
        out.push_str("EXTERN boom_scoped_native_register:PROC\nEXTERN boom_scoped_close_unavailable:PROC\n.data\nALIGN 8\nboom_scoped_native_pool DWORD 0504E4353h,1,0,1\n    QWORD OFFSET boom_scoped_close_unavailable,0\n.code\nPUBLIC boom_get_scoped_native_pool\nboom_get_scoped_native_pool PROC\n    lea rax,boom_scoped_native_pool\n    ret\nboom_get_scoped_native_pool ENDP\n");
    }
}
