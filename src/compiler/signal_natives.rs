//! Original Signal control calls backed by the live assembly Windows transport.
use super::{classfile::ClassFile, numeric, signals, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum Operation {
    Handle,
    Raise,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, desc: &str) -> Option<Self> {
        if owner != signals::OWNER {
            return None;
        }
        match (name, desc) {
            ("handle0", "(IJ)J") => Some(Self::Handle),
            ("raise0", "(I)V") => Some(Self::Raise),
            _ => None,
        }
    }
    pub(super) fn signature(self) -> numeric::Signature {
        use numeric::{
            Signature,
            Type::{I32, I64, Void},
        };
        match self {
            Self::Handle => Signature {
                arguments: vec![I32, I64],
                result: I64,
            },
            Self::Raise => Signature {
                arguments: vec![I32],
                result: Void,
            },
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub operation: Operation,
    pub origin: ClassOrigin,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub class_id: usize,
    pub native_source_sha256: String,
    pub transport_source_sha256: String,
    pub windows_policy: String,
    pub requires_bound_transport: bool,
    pub java_dispatch_integrated: bool,
    pub automatic_gc: bool,
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    op: Operation,
    class_id: usize,
) -> Result<Binding> {
    let contract = signals::contract(registry)?;
    let (owner, name, desc, interface) = caller.static_method_reference(constant)?;
    ensure!(
        !interface
            && Operation::resolve(&owner, &name, &desc) == Some(op)
            && caller.name == signals::OWNER
            && source == &contract.origin,
        "Signal control native is private to its original Signal caller"
    );
    Ok(Binding {
        abi: 1,
        operation: op,
        origin: contract.origin,
        caller: source.clone(),
        constant,
        class_id,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/signal_natives.asm"
        ))
        .sha256,
        transport_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/signal_control.asm"
        ))
        .sha256,
        windows_policy: "normal".into(),
        requires_bound_transport: true,
        java_dispatch_integrated: false,
        automatic_gc: false,
    })
}
pub(super) fn emit(out: &mut String) {
    out.push_str("EXTERN boom_signal_native_query:PROC\nEXTERN boom_signal_native_bind:PROC\n.data\nALIGN 8\nboom_signal_native_pool DWORD 0504E4753h,1\n    QWORD 0,0,0,OFFSET boom_trace_pool,0,0,0\n.code\nPUBLIC boom_get_signal_native_pool\nboom_get_signal_native_pool PROC\n    lea rax,boom_signal_native_pool\n    ret\nboom_get_signal_native_pool ENDP\nPUBLIC boom_bind_signal_transport\nboom_bind_signal_transport PROC\n    lea rdx,boom_signal_native_pool\n    jmp boom_signal_native_bind\nboom_bind_signal_transport ENDP\n");
}
