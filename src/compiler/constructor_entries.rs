//! VM-owned constructor invokers. Allocation and the actual Java body execute ASM.
use super::numeric::{Signature, Type};
use crate::bytecode::ClassOrigin;
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub class_id: usize,
    pub method_id: usize,
    pub helper_id: usize,
    pub source: Option<ClassOrigin>,
    pub signature: Signature,
    #[serde(default, skip_serializing_if = "is_false")]
    pub module_bootstrap: bool,
    #[serde(default, skip_serializing_if = "is_false")]
    pub preserve_call_site: bool,
    #[serde(default, skip_serializing_if = "is_false")]
    pub report_constructor_phase: bool,
}
fn is_false(value: &bool) -> bool {
    !*value
}
impl Plan {
    pub(super) fn new(
        class_id: usize,
        method_id: usize,
        helper_id: usize,
        source: Option<ClassOrigin>,
        mut instance: Signature,
    ) -> Result<Self> {
        ensure!(
            instance.result == Type::Void
                && !instance.arguments.is_empty()
                && instance.arguments[0] == Type::LinkedObject(class_id)
                && instance.check_arguments().is_ok(),
            "Invalid constructor VM invocation signature"
        );
        instance.arguments.remove(0);
        instance.result = Type::LinkedObject(class_id);
        Ok(Self {
            abi: 1,
            class_id,
            method_id,
            helper_id,
            source,
            signature: instance,
            module_bootstrap: false,
            preserve_call_site: false,
            report_constructor_phase: false,
        })
    }
    pub(super) fn emit(&self, assembly: &mut String, context32: bool) {
        let frame_bytes = ((88 + self.signature.arguments.len() * 8 + 15) & !15) + 8;
        let frame_bytes = frame_bytes.max(216);
        let begin = assembly.len();
        let Self {
            helper_id: h,
            method_id: m,
            class_id: c,
            ..
        } = self;
        let initialize = if self.module_bootstrap {
            format!(
                "    cmp DWORD PTR [boom_class{c}+8], 0\n    jne boom_ctor{h}_bootstrap_error\n"
            )
        } else {
            format!(
                "    lea rcx, boom_class{c}\n    mov rdx, QWORD PTR [rsp+48]\n    call boom_class_ensure\n    test eax, eax\n    jnz boom_ctor{h}_error\n"
            )
        };
        let save_context = if self.preserve_call_site {
            "    mov rax,QWORD PTR [rcx+4]\n    mov QWORD PTR [rsp+72],rax\n"
        } else {
            ""
        };
        let allocation_origin = if self.preserve_call_site {
            "    mov rax,QWORD PTR [rsp+72]\n    mov QWORD PTR [r10+4],rax\n".into()
        } else {
            format!("    mov DWORD PTR [r10+4], 0\n    mov DWORD PTR [r10+8], {m}\n")
        };
        let target = if self.module_bootstrap {
            format!("boom_m{m}_body")
        } else {
            format!("boom_m{m}")
        };
        assembly.push_str(&format!("; VM entry: allocate class {c}, then invoke original constructor method {m}.\n.code\nboom_m{h} PROC FRAME\n    sub rsp, 216\n    .allocstack 216\n    .endprolog\n    mov QWORD PTR [rsp+48], rcx\n    mov QWORD PTR [rsp+56], rdx\n{save_context}    cmp DWORD PTR [rcx], 0\n    jne boom_ctor{h}_error\n{initialize}    mov rcx, QWORD PTR [boom_heap_ptr]\n    lea rdx, boom_layout{c}\n    mov r8, QWORD PTR [rsp+48]\n    call boom_object_new\n    test rax, rax\n    jz boom_ctor{h}_allocation_error\n    mov QWORD PTR [rsp+64], rax\n    mov QWORD PTR [rsp+80], rax\n    mov rdx, QWORD PTR [rsp+56]\n"));
        for arg in 0..self.signature.arguments.len() {
            assembly.push_str(&format!(
                "    mov rax, QWORD PTR [rdx+{}]\n    mov QWORD PTR [rsp+{}], rax\n",
                arg * 8,
                88 + arg * 8
            ));
        }
        assembly.push_str(&format!("    mov rcx, QWORD PTR [rsp+48]\n    lea rdx, [rsp+80]\n    call {target}\n    mov r10, QWORD PTR [rsp+48]\n    cmp DWORD PTR [r10], 0\n    jne boom_ctor{h}_error\n    mov rax, QWORD PTR [rsp+64]\n    jmp boom_ctor{h}_done\nboom_ctor{h}_bootstrap_error:\n    mov r10, QWORD PTR [rsp+48]\n    mov DWORD PTR [r10], 7\nboom_ctor{h}_allocation_error:\n    mov r10, QWORD PTR [rsp+48]\n{allocation_origin}boom_ctor{h}_error:\n"));
        if context32 {
            assembly
                .push_str("    mov rcx, QWORD PTR [rsp+48]\n    call boom_exception_materialize\n");
        }
        assembly.push_str(&format!(
            "    xor eax, eax\nboom_ctor{h}_done:\n    add rsp, 216\n    ret\nboom_m{h} ENDP\n"
        ));
        let mut body = assembly[begin..].to_string();
        if frame_bytes != 216 {
            body = body
                .replace("rsp, 216", &format!("rsp, {frame_bytes}"))
                .replace(".allocstack 216", &format!(".allocstack {frame_bytes}"));
        }
        if self.report_constructor_phase {
            body=body.replace(&format!("    call {target}\n    mov r10, QWORD PTR [rsp+48]\n    cmp DWORD PTR [r10], 0\n    jne boom_ctor{h}_error"),&format!("    call {target}\n    mov r10, QWORD PTR [rsp+48]\n    cmp DWORD PTR [r10], 0\n    jne boom_ctor{h}_constructor_error"));
            body = body.replace(
                &format!("boom_ctor{h}_allocation_error:\n"),
                &format!(
                    "boom_ctor{h}_allocation_error:\n    mov DWORD PTR [rsp+CTOR_PHASE_SLOT],0\n"
                ),
            );
            body=body.replace(&format!("boom_ctor{h}_error:\n"),&format!("    jmp boom_ctor{h}_error\nboom_ctor{h}_constructor_error:\n    mov DWORD PTR [rsp+CTOR_PHASE_SLOT],2\nboom_ctor{h}_error:\n"));
            // Phase storage must not overlap the outgoing argv of large constructors.
            let phase = frame_bytes - 8;
            body = body.replace("[rsp+CTOR_PHASE_SLOT]", &format!("[rsp+{phase}]"));
            body = body.replace(
                "    .endprolog\n",
                &format!("    .endprolog\n    mov DWORD PTR [rsp+{phase}],1\n"),
            );
            body = body.replace(
                &format!("    xor eax, eax\nboom_ctor{h}_done:"),
                &format!(
                    "    mov edx,DWORD PTR [rsp+{phase}]\n    xor eax,eax\nboom_ctor{h}_done:"
                ),
            );
        }
        assembly.truncate(begin);
        assembly.push_str(&body);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reflected_constructor_phase_storage_follows_wide_outgoing_arguments() {
        let mut arguments = vec![Type::LinkedObject(3)];
        arguments.extend([Type::I32; 17]);
        let mut plan = Plan::new(
            3,
            7,
            21,
            None,
            Signature {
                arguments,
                result: Type::Void,
            },
        )
        .unwrap();
        plan.report_constructor_phase = true;
        plan.preserve_call_site = true;
        let mut out = String::new();
        plan.emit(&mut out, true);
        assert!(out.contains("sub rsp, 232\n"));
        assert!(out.contains("mov DWORD PTR [rsp+224],2\n"));
        assert!(out.contains("mov QWORD PTR [rsp+208], rax\n"));
        assert!(out.contains("mov QWORD PTR [rsp+216], rax\n"));
        assert!(out.contains("mov edx,DWORD PTR [rsp+224]\n"));
        assert!(out.contains("call boom_exception_materialize\n"));
        assert!(!out.contains("CTOR_PHASE_SLOT"));
    }
    #[test]
    fn constructor_argument_limit_counts_jvm_wide_slots_and_receiver() {
        for (kind, count, accepted) in [
            (Type::I32, 254, true),
            (Type::I32, 255, false),
            (Type::I64, 127, true),
            (Type::F64, 128, false),
        ] {
            let mut arguments = vec![Type::LinkedObject(3)];
            arguments.extend(vec![kind; count]);
            assert_eq!(
                Plan::new(
                    3,
                    7,
                    21,
                    None,
                    Signature {
                        arguments,
                        result: Type::Void
                    }
                )
                .is_ok(),
                accepted
            );
        }
    }
    #[test]
    fn constructor_factory_removes_only_the_actual_receiver_and_preserves_wide_values() {
        let signature = Signature {
            arguments: vec![Type::LinkedObject(3), Type::I32, Type::I64, Type::F64],
            result: Type::Void,
        };
        let plan = Plan::new(3, 7, 21, None, signature).unwrap();
        assert_eq!(
            plan.signature.arguments,
            vec![Type::I32, Type::I64, Type::F64]
        );
        assert_eq!(plan.signature.result, Type::LinkedObject(3));
    }
    #[test]
    fn constructor_factory_rejects_foreign_receiver_return_and_argument_overflow() {
        for signature in [
            Signature {
                arguments: vec![],
                result: Type::Void,
            },
            Signature {
                arguments: vec![Type::LinkedObject(2)],
                result: Type::Void,
            },
            Signature {
                arguments: vec![Type::LinkedObject(3)],
                result: Type::I32,
            },
            Signature {
                arguments: vec![Type::LinkedObject(3); 256],
                result: Type::Void,
            },
        ] {
            assert!(Plan::new(3, 7, 21, None, signature).is_err());
        }
    }
}
