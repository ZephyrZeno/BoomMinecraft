//! Synchronized Java method envelopes. All acquisition, waiting and release run MASM.
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub class_name: String,
    pub loader: String,
    pub method: String,
    pub descriptor: String,
    pub static_method: bool,
    pub mirror_type: Option<usize>,
    pub source_sha256: String,
}

pub(super) fn wrapper(
    id: usize,
    owner: usize,
    mirror: Option<usize>,
    context32: bool,
    normal_class_mirrors: bool,
) -> String {
    let mut s = format!(
        "boom_m{id} PROC FRAME\n    sub rsp, 88\n    .allocstack 88\n    .endprolog\n    mov QWORD PTR [rsp+48], rcx\n    mov QWORD PTR [rsp+56], rdx\n"
    );
    if let Some(mirror) = mirror {
        let ensure = if normal_class_mirrors {
            "boom_class_ensure32"
        } else {
            "boom_class_ensure"
        };
        let failed = if normal_class_mirrors {
            "monitor_propagate"
        } else {
            "monitor_error"
        };
        s.push_str(&format!("    lea rcx, boom_class{owner}\n    mov rdx, QWORD PTR [rsp+48]\n    call {ensure}\n    test eax, eax\n    jnz boom_m{id}_{failed}\n"));
        if normal_class_mirrors {
            assert!(context32, "Normal Class monitor requires Context32");
            s.push_str(&format!("    mov rcx, QWORD PTR [rsp+48]\n    lea rdx, boom_java_class_pool\n    mov r8d, {mirror}\n    call boom_java_class_load\n"));
        } else {
            s.push_str(&format!("    mov rcx, QWORD PTR [boom_heap_ptr]\n    lea rdx, boom_mirror_pool\n    mov r8d, {mirror}\n    mov r9, QWORD PTR [rsp+48]\n    call boom_mirror_load\n"));
        }
        s.push_str(&format!("    mov r10, QWORD PTR [rsp+48]\n    cmp DWORD PTR [r10], 0\n    jne boom_m{id}_monitor_error\n"));
    } else {
        s.push_str("    mov rax, QWORD PTR [rdx]\n");
    }
    s.push_str(&format!("    mov QWORD PTR [rsp+64], rax\n    mov rcx, QWORD PTR [boom_heap_ptr]\n    mov rdx, rax\n    mov r8, QWORD PTR [rsp+48]\n    call boom_monitor_enter\n    test eax, eax\n    jnz boom_m{id}_monitor_error\n    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    call boom_m{id}_body\n    mov QWORD PTR [rsp+72], rax\n    mov rcx, QWORD PTR [boom_heap_ptr]\n    mov rdx, QWORD PTR [rsp+64]\n    mov r8, QWORD PTR [rsp+48]\n    call boom_monitor_exit\n    test eax, eax\n    jnz boom_m{id}_monitor_error\n    mov rax, QWORD PTR [rsp+72]\n    jmp boom_m{id}_monitor_done\nboom_m{id}_monitor_error:\n    mov r10, QWORD PTR [rsp+48]\n    mov DWORD PTR [r10+4], 0\n    mov DWORD PTR [r10+8], {id}\n    xor eax, eax\nboom_m{id}_monitor_done:\n    add rsp, 88\n    ret\nboom_m{id} ENDP\n"));
    if context32 {
        let old = format!(
            "boom_m{id}_monitor_error:\n    mov r10, QWORD PTR [rsp+48]\n    mov DWORD PTR [r10+4], 0\n    mov DWORD PTR [r10+8], {id}\n    xor eax, eax\n"
        );
        let new = format!(
            "boom_m{id}_monitor_error:\n    mov rcx, QWORD PTR [rsp+48]\n    cmp DWORD PTR [rcx], 16\n    je boom_m{id}_monitor_keep\n    mov DWORD PTR [rcx+4], 0\n    mov DWORD PTR [rcx+8], {id}\n    call boom_exception_materialize\nboom_m{id}_monitor_keep:\n    xor eax, eax\n"
        );
        s = s.replace(&old, &new);
    }
    if normal_class_mirrors && mirror.is_some() {
        // Class initialization already records the real failure origin. A
        // synchronized entry must propagate it before acquiring any monitor.
        let done = format!("boom_m{id}_monitor_done:\n");
        s = s.replace(
            &done,
            &format!("boom_m{id}_monitor_propagate:\n    xor eax, eax\n{done}"),
        );
    }
    s
}

#[cfg(test)]
mod wrapper_tests {
    use super::wrapper;

    #[test]
    fn normal_static_monitor_loads_canonical_class_with_context32() {
        let body = wrapper(7, 20_001, Some(20_001), true, true);
        assert!(body.contains("mov rcx, QWORD PTR [rsp+48]\n    lea rdx, boom_java_class_pool\n    mov r8d, 20001\n    call boom_java_class_load"));
        assert!(body.contains("call boom_class_ensure32"));
        assert!(!body.contains("boom_mirror_pool") && !body.contains("call boom_mirror_load"));
        assert!(body.contains("mov QWORD PTR [rsp+64], rax"));
    }

    #[test]
    fn normal_static_initialization_failure_keeps_original_context() {
        let body = wrapper(7, 8, Some(8), true, true);
        assert!(body.contains(
            "call boom_class_ensure32\n    test eax, eax\n    jnz boom_m7_monitor_propagate"
        ));
        let propagation = body.split("boom_m7_monitor_propagate:\n").nth(1).unwrap();
        assert!(propagation.starts_with("    xor eax, eax\nboom_m7_monitor_done:"));
    }

    #[test]
    fn instance_monitor_keeps_receiver_locking_without_class_initialization() {
        let old = wrapper(7, 8, None, true, false);
        assert_eq!(old, wrapper(7, 8, None, true, true));
        assert!(!old.contains("boom_class_ensure") && !old.contains("boom_java_class_load"));
    }
}

/// Notification uses the same wait set as the native Object.wait0 source provider.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Notification {
    pub caller: crate::bytecode::ClassOrigin,
    pub constant: u16,
    pub origin: crate::bytecode::ClassOrigin,
    pub receiver_type: usize,
    pub method: String,
    pub wait_sets_supported: bool,
    pub source_sha256: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub wait_source_sha256: Option<String>,
}
impl Notification {
    pub(super) fn bind(
        registry: &mut super::types::Registry<'_>,
        loader: &str,
        caller: &super::classfile::ClassFile,
        source: &crate::bytecode::ClassOrigin,
        constant: u16,
        all: bool,
    ) -> anyhow::Result<Self> {
        use super::types::Type;
        use anyhow::{Context, ensure};
        let (owner, name, descriptor) = caller.method_reference(constant)?;
        ensure!(
            name == if all { "notifyAll" } else { "notify" } && descriptor == "()V",
            "Notification reference changed"
        );
        let receiver_type = registry.literal(loader, &owner)?;
        let object = registry.class("bootstrap", "java/lang/Object")?;
        let mut id = receiver_type;
        loop {
            match &registry.types[id] {
                Type::Array { .. } => id = object,
                Type::Class { superclass, .. } => {
                    let class = registry
                        .definition(id)
                        .context("Missing notification owner")?;
                    if let Some(method) = class
                        .methods
                        .iter()
                        .find(|m| m.name == name && m.descriptor == descriptor)
                    {
                        ensure!(
                            id == object && method.access == 0x111 && method.code.is_none(),
                            "Notification must resolve to original final native Object member"
                        );
                        break;
                    }
                    id = superclass.context("Missing inherited Object notification")?;
                }
                _ => anyhow::bail!("Primitive notification receiver"),
            }
        }
        let Type::Class { key, origin, .. } = &registry.types[object] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Notification requires original java.base Object"
        );
        Ok(Self {
            caller: source.clone(),
            constant,
            origin: origin.as_ref().clone(),
            receiver_type,
            method: name,
            wait_sets_supported: true,
            source_sha256: crate::files::digest_bytes(include_bytes!(
                "../../native/runtime/monitors.asm"
            ))
            .sha256,
            wait_source_sha256: Some(
                crate::files::digest_bytes(include_bytes!("../../native/runtime/object_wait.asm"))
                    .sha256,
            ),
        })
    }
}
