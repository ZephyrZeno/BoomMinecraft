//! Original java.lang shutdown natives; Java owns hook ordering and halt locks.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/Shutdown";
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Operation {
    BeforeHalt,
    Halt,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Option<Self> {
        if owner != OWNER {
            return None;
        }
        match (name, descriptor) {
            ("beforeHalt", "()V") => Some(Self::BeforeHalt),
            ("halt0", "(I)V") => Some(Self::Halt),
            _ => None,
        }
    }
    pub(super) fn name(self) -> &'static str {
        if self == Self::BeforeHalt {
            "beforeHalt"
        } else {
            "halt0"
        }
    }
    pub(super) fn descriptor(self) -> &'static str {
        if self == Self::BeforeHalt {
            "()V"
        } else {
            "(I)V"
        }
    }
    pub(super) fn signature(self) -> numeric::Signature {
        numeric::Signature {
            arguments: if self == Self::BeforeHalt {
                vec![]
            } else {
                vec![numeric::Type::I32]
            },
            result: numeric::Type::Void,
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub operation: Operation,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub class_id: usize,
    pub initializer_code_sha256: String,
    pub bindings: Vec<Binding>,
    pub native_source_sha256: String,
    pub jfr_supported: bool,
    pub java_hook_order_owned_by_original_code: bool,
}
impl Plan {
    pub(super) fn new(registry: &mut types::Registry<'_>, class_id: usize) -> Result<Self> {
        let id = registry.class("bootstrap", OWNER)?;
        let types::Type::Class { origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            origin.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Shutdown requires original bootstrap source"
        );
        let origin = origin.as_ref().clone();
        let class = registry
            .definition(id)
            .context("Missing Shutdown definition")?;
        for op in [Operation::BeforeHalt, Operation::Halt] {
            let m = class.method(op.name(), Some(op.descriptor()))?;
            ensure!(
                m.access == 0x108 && m.code.is_none(),
                "Shutdown package native declaration changed"
            );
        }
        let init = class
            .method("<clinit>", Some("()V"))?
            .code
            .as_ref()
            .context("Missing Shutdown initializer")?;
        Ok(Self {
            abi: 1,
            origin,
            class_id,
            initializer_code_sha256: files::digest_bytes(&init.bytes).sha256,
            bindings: vec![],
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/shutdown.asm"
            ))
            .sha256,
            jfr_supported: false,
            java_hook_order_owned_by_original_code: true,
        })
    }
    pub(super) fn bind(
        &mut self,
        registry: &mut types::Registry<'_>,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
        operation: Operation,
    ) -> Result<()> {
        let (o, n, d) = caller.method_reference(constant)?;
        ensure!(
            Operation::resolve(&o, &n, &d) == Some(operation),
            "Shutdown native call changed"
        );
        ensure!(
            source.loader == "bootstrap"
                && source.source_id == "jdk:java.base"
                && source.generated.is_none()
                && caller
                    .name
                    .rsplit_once('/')
                    .is_some_and(|p| p.0 == "java/lang"),
            "Shutdown native requires original java.lang package caller"
        );
        let id = registry.class("bootstrap", &caller.name)?;
        ensure!(
            matches!(&registry.types[id],types::Type::Class { origin,.. } if origin.as_ref()==source),
            "Shutdown caller differs from original definition"
        );
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.bindings.push(Binding {
                caller: source.clone(),
                constant,
                operation,
            });
        }
        Ok(())
    }
    pub(super) fn emit(&self, out: &mut String) {
        out.push_str("EXTERN boom_shutdown_native:PROC\n.data\nALIGN 8\nboom_shutdown_pool DWORD 053485554h,1\n    QWORD 0\n    DWORD 0,0\n    QWORD 0\n.code\nPUBLIC boom_get_shutdown_pool\nboom_get_shutdown_pool PROC\n    lea rax,boom_shutdown_pool\n    ret\nboom_get_shutdown_pool ENDP\n");
    }
}
