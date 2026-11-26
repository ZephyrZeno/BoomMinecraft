//! Original Thread native registration with explicitly incomplete capabilities.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/Thread";
const MEMBERS: [(&str, &str, u16); 18] = [
    ("start0", "()V", 0x102),
    ("setPriority0", "(I)V", 0x102),
    ("yield0", "()V", 0x10a),
    ("sleep0", "(J)V", 0x10a),
    ("currentCarrierThread", "()Ljava/lang/Thread;", 0x108),
    ("currentThread", "()Ljava/lang/Thread;", 0x109),
    ("setCurrentThread", "(Ljava/lang/Thread;)V", 0x100),
    ("interrupt0", "()V", 0x102),
    ("holdsLock", "(Ljava/lang/Object;)Z", 0x109),
    ("getThreads", "()[Ljava/lang/Thread;", 0x10a),
    (
        "dumpThreads",
        "([Ljava/lang/Thread;)[[Ljava/lang/StackTraceElement;",
        0x10a,
    ),
    ("getStackTrace0", "()Ljava/lang/Object;", 0x102),
    ("setNativeName", "(Ljava/lang/String;)V", 0x102),
    ("scopedValueCache", "()[Ljava/lang/Object;", 0x108),
    ("setScopedValueCache", "([Ljava/lang/Object;)V", 0x108),
    ("getNextThreadIdOffset", "()J", 0x10a),
    ("findScopedValueBindings", "()Ljava/lang/Object;", 0x108),
    (
        "ensureMaterializedForStackWalk",
        "(Ljava/lang/Object;)V",
        0x108,
    ),
];
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Operation {
    Register,
    Yield,
    Carrier,
    Current,
    IdAddress,
    Materialize,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, desc: &str) -> Option<Self> {
        if owner != OWNER {
            return None;
        }
        match (name, desc) {
            ("registerNatives", "()V") => Some(Self::Register),
            ("yield0", "()V") => Some(Self::Yield),
            ("currentCarrierThread", "()Ljava/lang/Thread;") => Some(Self::Carrier),
            ("currentThread", "()Ljava/lang/Thread;") => Some(Self::Current),
            ("getNextThreadIdOffset", "()J") => Some(Self::IdAddress),
            ("ensureMaterializedForStackWalk", "(Ljava/lang/Object;)V") => Some(Self::Materialize),
            _ => None,
        }
    }
    pub(super) fn index(self) -> u32 {
        match self {
            Self::Register => 255,
            Self::Yield => 2,
            Self::Carrier => 4,
            Self::Current => 5,
            Self::IdAddress => 15,
            Self::Materialize => 17,
        }
    }
    pub(super) fn signature(self, owner: usize) -> numeric::Signature {
        numeric::Signature {
            arguments: if self == Self::Materialize {
                vec![numeric::Type::AnyRef]
            } else {
                vec![]
            },
            result: match self {
                Self::Register | Self::Yield | Self::Materialize => numeric::Type::Void,
                Self::Carrier | Self::Current => numeric::Type::LinkedObject(owner),
                Self::IdAddress => numeric::Type::I64,
            },
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Declaration {
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub implemented: bool,
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
    pub thread_type: usize,
    pub virtual_base_type: usize,
    pub class_initializer_code_sha256: String,
    pub declarations: Vec<Declaration>,
    pub bindings: Vec<Binding>,
    pub native_source_sha256: String,
    pub registry_source_sha256: String,
    pub runtime_types_source_sha256: String,
    pub native_coverage_complete: bool,
    pub platform_threads_only: bool,
    pub automatic_gc: bool,
}
impl Plan {
    pub(super) fn new(registry: &mut types::Registry<'_>, class_id: usize) -> Result<Self> {
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
                && access & 0x601 == 1,
            "Thread natives require the original public bootstrap Thread"
        );
        let origin = origin.as_ref().clone();
        let class = registry
            .definition(id)
            .context("Missing original Thread definition")?;
        let register = class.method("registerNatives", Some("()V"))?;
        ensure!(
            register.access == 0x10a && register.code.is_none(),
            "Original Thread registration declaration changed"
        );
        let mut declarations = Vec::new();
        for (index, (name, desc, flags)) in MEMBERS.iter().enumerate() {
            let method = class.method(name, Some(desc))?;
            ensure!(
                method.access == *flags && method.code.is_none(),
                "Original Thread native declaration changed: {name}{desc}"
            );
            declarations.push(Declaration {
                name: (*name).into(),
                descriptor: (*desc).into(),
                access: *flags,
                implemented: matches!(index, 2 | 4 | 5 | 15 | 17),
            });
        }
        let init = class
            .method("<clinit>", Some("()V"))?
            .code
            .as_ref()
            .context("Thread must retain original class initialization")?;
        ensure!(
            init.bytes.len() == 16 && init.bytes[0] == 0xb8,
            "Original Thread initializer changed"
        );
        let class_initializer_code_sha256 = files::digest_bytes(&init.bytes).sha256;
        let virtual_base_type = registry.class("bootstrap", "java/lang/BaseVirtualThread")?;
        Ok(Self {
            abi: 1,
            origin,
            class_id,
            thread_type: id,
            virtual_base_type,
            class_initializer_code_sha256,
            declarations,
            bindings: Vec::new(),
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/thread_natives.asm"
            ))
            .sha256,
            registry_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/thread_registry.asm"
            ))
            .sha256,
            runtime_types_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/runtime_types.asm"
            ))
            .sha256,
            native_coverage_complete: false,
            platform_threads_only: true,
            automatic_gc: false,
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
        let (owner, name, desc, interface) = caller.static_method_reference(constant)?;
        ensure!(
            !interface && Operation::resolve(&owner, &name, &desc) == Some(operation),
            "Thread native callsite changed"
        );
        match operation {
            Operation::Current => {}
            Operation::Carrier => ensure!(
                source.loader == "bootstrap"
                    && caller.name.rsplit_once('/').map(|x| x.0) == Some("java/lang"),
                "Thread.currentCarrierThread requires its bootstrap runtime package"
            ),
            Operation::Register | Operation::Yield | Operation::Materialize => ensure!(
                caller.name == OWNER && source == &self.origin,
                "Thread private native is restricted to its original Thread caller"
            ),
            Operation::IdAddress => {
                if caller.name != OWNER {
                    let id = registry.class("bootstrap", "java/lang/Thread$ThreadIdentifiers")?;
                    let types::Type::Class { origin, .. } = &registry.types[id] else {
                        unreachable!()
                    };
                    ensure!(
                        source == origin.as_ref() && caller.nest_host.as_deref() == Some(OWNER),
                        "Thread ID address is private to its original nest"
                    );
                    ensure!(
                        registry
                            .definition(self.thread_type)
                            .context("Missing Thread nest host")?
                            .nest_members
                            .as_ref()
                            .is_some_and(|members| members.iter().any(|n| n == &caller.name)),
                        "Thread ID caller is not in the verified Thread nest"
                    );
                } else {
                    ensure!(
                        source == &self.origin,
                        "Thread ID address requires original source"
                    );
                }
            }
        }
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
        Ok(())
    }
    pub(super) fn emit(&self, out: &mut String) {
        out.push_str("EXTERN boom_thread_native_register:PROC\nEXTERN boom_thread_native_dispatch:PROC\nEXTERN boom_thread_native_bind:PROC\n");
        for i in 0..18 {
            out.push_str(&format!("EXTERN boom_thread_native_{i}:PROC\n"));
        }
        out.push_str(".const\n");
        for (i, d) in self.declarations.iter().enumerate() {
            for (suffix, text) in [("name", &d.name), ("desc", &d.descriptor)] {
                out.push_str(&format!("boom_thread_{suffix}{i} LABEL BYTE\n"));
                let bytes: Vec<_> = text.bytes().chain(std::iter::once(0)).collect();
                for chunk in bytes.chunks(16) {
                    out.push_str("    BYTE ");
                    out.push_str(
                        &chunk
                            .iter()
                            .map(u8::to_string)
                            .collect::<Vec<_>>()
                            .join(","),
                    );
                    out.push('\n');
                }
            }
        }
        out.push_str("ALIGN 8\nboom_thread_native_table DWORD 0544E4154h,1,18,028034h\n");
        for (i, d) in self.declarations.iter().enumerate() {
            out.push_str(&format!("    QWORD OFFSET boom_thread_name{i},OFFSET boom_thread_desc{i},OFFSET boom_thread_native_{i}\n    DWORD {},{}\n",d.access,u32::from(d.implemented)));
        }
        out.push_str(&format!(".data\nALIGN 8\nboom_thread_registry_ptr QWORD 0\nboom_thread_native_pool DWORD 0544E504Ch,1,0,0\n    QWORD OFFSET boom_thread_native_table,OFFSET boom_layout{},OFFSET boom_runtime_type_map,OFFSET boom_t{},OFFSET boom_t{},OFFSET boom_thread_registry_ptr,OFFSET boom_heap_ptr,0\n.code\nPUBLIC boom_get_thread_native_pool\nboom_get_thread_native_pool PROC\n    lea rax,boom_thread_native_pool\n    ret\nboom_get_thread_native_pool ENDP\nPUBLIC boom_bind_thread_registry\nboom_bind_thread_registry PROC\n    lea rdx,boom_thread_native_pool\n    jmp boom_thread_native_bind\nboom_bind_thread_registry ENDP\n",self.class_id,self.thread_type,self.virtual_base_type));
    }
}
