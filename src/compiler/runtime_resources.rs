//! Original Runtime CPU/memory native boundary; all queries run MASM.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/Runtime";
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Operation {
    AvailableProcessors = 0,
    FreeMemory = 1,
    TotalMemory = 2,
    MaxMemory = 3,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Option<Self> {
        if owner != OWNER {
            return None;
        }
        match (name, descriptor) {
            ("availableProcessors", "()I") => Some(Self::AvailableProcessors),
            ("freeMemory", "()J") => Some(Self::FreeMemory),
            ("totalMemory", "()J") => Some(Self::TotalMemory),
            ("maxMemory", "()J") => Some(Self::MaxMemory),
            _ => None,
        }
    }
    pub fn member(self) -> (&'static str, &'static str) {
        match self {
            Self::AvailableProcessors => ("availableProcessors", "()I"),
            Self::FreeMemory => ("freeMemory", "()J"),
            Self::TotalMemory => ("totalMemory", "()J"),
            Self::MaxMemory => ("maxMemory", "()J"),
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
    pub runtime_type: usize,
    pub bindings: Vec<Binding>,
    pub exact_runtime_receiver: bool,
    pub override_dispatch_complete: bool,
    pub policy: String,
    pub queries_process_affinity: bool,
    pub queries_job_group_affinity: bool,
    pub guest_heap_allocation: bool,
    pub memory_counters: String,
    pub automatic_gc: bool,
    pub native_source_sha256: String,
    pub heap_source_sha256: String,
    pub type_source_sha256: String,
}
impl Plan {
    pub(super) fn new(registry: &mut types::Registry<'_>) -> Result<Self> {
        let id = registry.class("bootstrap", OWNER)?;
        let types::Type::Class {
            key,
            origin,
            access,
            ..
        } = &registry.types[id]
        else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none()
                && access & 0x611 == 1,
            "Processor query needs original concrete Runtime"
        );
        let origin = origin.as_ref().clone();
        let class = registry.definition(id).context("Missing Runtime source")?;
        for op in [
            Operation::AvailableProcessors,
            Operation::FreeMemory,
            Operation::TotalMemory,
            Operation::MaxMemory,
        ] {
            let (name, descriptor) = op.member();
            let method = class.method(name, Some(descriptor))?;
            ensure!(
                method.access == 0x101 && method.code.is_none(),
                "Runtime resource native declaration changed: {name}"
            );
        }
        ensure!(
            class
                .methods
                .iter()
                .filter(|m| m.name == "<init>")
                .all(|m| m.access == 2)
                && class.method("<init>", Some("()V"))?.code.is_some(),
            "Runtime constructor access changed"
        );
        Ok(Self {
            abi: 1,
            origin,
            runtime_type: id,
            bindings: Vec::new(),
            exact_runtime_receiver: true,
            override_dispatch_complete: false,
            policy: "windows-default-group-and-job-affinity".into(),
            queries_process_affinity: true,
            queries_job_group_affinity: true,
            guest_heap_allocation: false,
            memory_counters: "Heap1 committed capacity minus occupied block spans".into(),
            automatic_gc: false,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/runtime_resources.asm"
            ))
            .sha256,
            heap_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/heap.asm"
            ))
            .sha256,
            type_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/runtime_types.asm"
            ))
            .sha256,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
        operation: Operation,
    ) -> Result<numeric::Signature> {
        ensure!(
            caller.name.replace('/', ".") == source.binary_name,
            "Processor caller identity changed"
        );
        let (o, n, d) = caller.method_reference(constant)?;
        ensure!(
            Operation::resolve(&o, &n, &d) == Some(operation),
            "Runtime resource reference changed"
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
            self.bindings.sort_by(|a, b| {
                (&a.caller.binary_name, a.constant).cmp(&(&b.caller.binary_name, b.constant))
            });
        }
        Ok(numeric::Signature {
            arguments: vec![numeric::Type::MetadataReference(self.runtime_type)],
            result: if operation == Operation::AvailableProcessors {
                numeric::Type::I32
            } else {
                numeric::Type::I64
            },
        })
    }
    pub(super) fn emit(&self, out: &mut String) {
        out.push_str(&format!("EXTERN boom_runtime_resource:PROC\n.const\nALIGN 8\nboom_processor_pool DWORD 0544E5552h,1\n    QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_t{}\n    QWORD 0,0,0,0\n.code\nPUBLIC boom_get_processor_pool\nboom_get_processor_pool PROC\n    lea rax,boom_processor_pool\n    ret\nboom_get_processor_pool ENDP\n",self.runtime_type));
    }
}
