//! Guarded VM-only primordial constructor variant. Original bytes are retained;
//! every selected conditional is still checked by emitted assembly.
use super::{
    classfile::{ClassFile, Code},
    constructor_entries, numeric,
    program::ProgramObjectLayout,
};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/Thread";
pub const DESC: &str = "(Ljava/lang/ThreadGroup;Ljava/lang/String;ILjava/lang/Runnable;JLjava/security/AccessControlContext;)V";
pub const EXTRA: [(&str, &str); 2] = [
    ("java/lang/ThreadGroup", "()V"),
    (
        "java/security/AccessControlContext",
        "([Ljava/security/ProtectionDomain;Z)V",
    ),
];
pub(super) fn entry(owner: &str, name: &str, desc: Option<&str>) -> bool {
    owner == OWNER && name == "<init>" && desc == Some(DESC)
}
pub(super) fn applies(class: &ClassFile, code: &Code) -> bool {
    class.name == OWNER
        && class.methods.iter().any(|m| {
            m.name == "<init>"
                && m.descriptor == DESC
                && m.code.as_ref().is_some_and(|c| std::ptr::eq(c, code))
        })
}
pub(super) fn check(class: &ClassFile, code: &Code) -> Result<()> {
    ensure!(
        applies(class, code) && code.bytes.len() == 311 && code.handlers.is_empty(),
        "Primordial constructor requires its original 311-byte Java body"
    );
    for (pc, op, target) in [
        (23, 0xa6, 30),
        (35, 0x99, 73),
        (39, 0xc7, 52),
        (171, 0x99, 189),
        (178, 0xa2, 189),
        (198, 0xc6, 205),
        (213, 0xc6, 225),
        (234, 0x9a, 303),
    ] {
        ensure!(
            code.bytes[pc] == op
                && pc as i32 + i16::from_be_bytes([code.bytes[pc + 1], code.bytes[pc + 2]]) as i32
                    == target,
            "Primordial constructor branch changed at {pc}"
        );
    }
    Ok(())
}
pub(super) fn skip(pc: usize) -> Option<usize> {
    match pc {
        30 => Some(31),
        42 => Some(52),
        73 => Some(169),
        189 => Some(196),
        205 => Some(208),
        225 => Some(232),
        237 => Some(303),
        _ => None,
    }
}
pub(super) fn branch(pc: usize) -> Option<bool> {
    match pc {
        23 | 35 | 171 | 178 | 198 | 213 => Some(false),
        39 | 234 => Some(true),
        _ => None,
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub original_descriptor: String,
    pub original_code_sha256: String,
    pub guarded_conditionals: Vec<usize>,
    pub invocation_only: bool,
    pub primordial_only: bool,
    pub general_thread_constructor_complete: bool,
    pub explicit_bootstrap_access_context: bool,
    pub helper_owns_registry: bool,
    pub main_name_literal: usize,
    pub thread_class: usize,
    pub method: usize,
    pub helper: usize,
    pub group: constructor_entries::Plan,
    pub access_context: constructor_entries::Plan,
}
impl Plan {
    pub(super) fn new(
        origin: ClassOrigin,
        class: &ClassFile,
        code: &Code,
        ctor: &constructor_entries::Plan,
        group: constructor_entries::Plan,
        access_context: constructor_entries::Plan,
        name: usize,
    ) -> Result<Self> {
        check(class, code)?;
        ensure!(
            origin.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Primordial constructor requires original bootstrap Thread"
        );
        Ok(Self {
            abi: 1,
            origin,
            original_descriptor: DESC.into(),
            original_code_sha256: files::digest_bytes(&code.bytes).sha256,
            guarded_conditionals: vec![23, 35, 39, 171, 178, 198, 213, 234],
            invocation_only: true,
            primordial_only: true,
            general_thread_constructor_complete: false,
            explicit_bootstrap_access_context: true,
            helper_owns_registry: false,
            main_name_literal: name,
            thread_class: ctor.class_id,
            method: ctor.method_id,
            helper: ctor.helper_id,
            group,
            access_context,
        })
    }
    pub(super) fn signature(&self) -> numeric::Signature {
        numeric::Signature {
            arguments: vec![],
            result: numeric::Type::LinkedObject(self.thread_class),
        }
    }
    pub(super) fn emit(
        &self,
        out: &mut String,
        layouts: &[ProgramObjectLayout],
        context32: bool,
    ) -> Result<()> {
        out.push_str("EXTERN boom_threads_current:PROC\nEXTERN boom_threads_attach:PROC\nEXTERN boom_threads_detach:PROC\n");
        self.group.emit(out, context32);
        self.access_context.emit(out, context32);
        let holder = layouts
            .iter()
            .find(|l| l.class_name == "java/lang/Thread$FieldHolder")
            .context("Missing bootstrap FieldHolder layout")?;
        let thread = layouts
            .iter()
            .find(|l| l.class_name == OWNER)
            .context("Missing bootstrap Thread layout")?;
        let holder_offset = thread
            .layout
            .fields
            .iter()
            .find(|f| f.name == "holder")
            .context("Missing Thread holder")?
            .offset;
        let status_offset = holder
            .layout
            .fields
            .iter()
            .find(|f| f.name == "threadStatus")
            .context("Missing Thread status")?
            .offset;
        let h = self.helper;
        let m = self.method;
        let t = self.thread_class;
        out.push_str(&format!("; VM-only primordial entry. Registry is borrowed; no automatic GC.\n.code\nboom_m{h} PROC FRAME\n    sub rsp,216\n    .allocstack 216\n    .endprolog\n    mov QWORD PTR [rsp+48],rcx\n    mov QWORD PTR [rsp+64],0\n    mov DWORD PTR [rsp+56],0\n    cmp DWORD PTR [rcx],0\n    jne boom_boot{h}_error\n    mov rcx,QWORD PTR [boom_thread_registry_ptr]\n    test rcx,rcx\n    jz boom_boot{h}_bad\n    call boom_threads_current\n    test rax,rax\n    jnz boom_boot{h}_bad\n    lea rcx,boom_class{t}\n    mov rdx,QWORD PTR [rsp+48]\n    call boom_class_ensure\n    test eax,eax\n    jnz boom_boot{h}_error\n    mov rcx,QWORD PTR [rsp+48]\n    lea rdx,[rsp+80]\n    call boom_m{}\n    mov r10,QWORD PTR [rsp+48]\n    cmp DWORD PTR [r10],0\n    jne boom_boot{h}_error\n    mov QWORD PTR [rsp+152],rax\n    mov QWORD PTR [rsp+80],0\n    mov QWORD PTR [rsp+88],1\n    mov rcx,r10\n    lea rdx,[rsp+80]\n    call boom_m{}\n    mov r10,QWORD PTR [rsp+48]\n    cmp DWORD PTR [r10],0\n    jne boom_boot{h}_error\n    mov QWORD PTR [rsp+160],rax\n    mov rcx,QWORD PTR [boom_heap_ptr]\n    lea rdx,boom_string_pool\n    mov r8d,{}\n    mov r9,r10\n    call boom_string_load\n    mov r10,QWORD PTR [rsp+48]\n    cmp DWORD PTR [r10],0\n    jne boom_boot{h}_error\n    mov QWORD PTR [rsp+168],rax\n    mov rcx,QWORD PTR [boom_heap_ptr]\n    lea rdx,boom_layout{t}\n    mov r8,r10\n    call boom_object_new\n    test rax,rax\n    jz boom_boot{h}_error\n    mov QWORD PTR [rsp+64],rax\n    mov rcx,QWORD PTR [boom_thread_registry_ptr]\n    mov rdx,rax\n    mov r8d,1\n    call boom_threads_attach\n    test rax,rax\n    jz boom_boot{h}_bad\n    mov DWORD PTR [rsp+56],1\n    mov rax,QWORD PTR [rsp+64]\n    mov QWORD PTR [rsp+80],rax\n    mov rax,QWORD PTR [rsp+152]\n    mov QWORD PTR [rsp+88],rax\n    mov rax,QWORD PTR [rsp+168]\n    mov QWORD PTR [rsp+96],rax\n    mov QWORD PTR [rsp+104],0\n    mov QWORD PTR [rsp+112],0\n    mov QWORD PTR [rsp+120],0\n    mov rax,QWORD PTR [rsp+160]\n    mov QWORD PTR [rsp+128],rax\n    mov rcx,QWORD PTR [rsp+48]\n    lea rdx,[rsp+80]\n    call boom_m{m}\n    mov r10,QWORD PTR [rsp+48]\n    cmp DWORD PTR [r10],0\n    jne boom_boot{h}_error\n    mov rax,QWORD PTR [rsp+64]\n    mov rdx,QWORD PTR [rax+{holder_offset}]\n    mov ecx,5\n    xchg ecx,DWORD PTR [rdx+{status_offset}]\n    jmp boom_boot{h}_done\nboom_boot{h}_bad:\n    mov r10,QWORD PTR [rsp+48]\n    mov DWORD PTR [r10],7\nboom_boot{h}_error:\n    cmp DWORD PTR [rsp+56],0\n    je boom_boot{h}_detached\n    mov rcx,QWORD PTR [boom_thread_registry_ptr]\n    call boom_threads_detach\nboom_boot{h}_detached:\n",self.group.helper_id,self.access_context.helper_id,self.main_name_literal));
        if context32 {
            out.push_str("    mov rcx,QWORD PTR [rsp+48]\n    call boom_exception_materialize\n");
        }
        out.push_str(&format!(
            "    xor eax,eax\nboom_boot{h}_done:\n    add rsp,216\n    ret\nboom_m{h} ENDP\n"
        ));
        Ok(())
    }
}
