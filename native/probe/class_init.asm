; Test-only callbacks for deterministic initialization races and failures.
option casemap:none
EXTERN boom_class_ensure:PROC
PUBLIC boom_probe_configure_class
PUBLIC boom_probe_class_initializer
PUBLIC boom_probe_class_failure
PUBLIC boom_probe_class_error
PUBLIC boom_probe_class_floating
PUBLIC boom_probe_ensure_entry
.data
probe_descriptor QWORD 0
probe_gate QWORD 0
probe_count QWORD 0
.code
boom_probe_configure_class PROC
    mov QWORD PTR [probe_descriptor], rcx
    mov QWORD PTR [probe_gate], rdx
    mov QWORD PTR [probe_count], r8
    ret
boom_probe_configure_class ENDP
boom_probe_class_initializer PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp, 32
    .allocstack 32
    .endprolog
    mov rbx, rcx
    mov rax, QWORD PTR [probe_count]
    lock inc QWORD PTR [rax]
    mov rcx, QWORD PTR [probe_descriptor]
    mov rdx, rbx
    call boom_class_ensure ; owning thread must be able to reenter its class
    test eax, eax
    jnz probe_initializer_done
    mov rax, QWORD PTR [probe_gate]
probe_initializer_wait:
    cmp DWORD PTR [rax], 0
    jne probe_initializer_done
    pause
    jmp probe_initializer_wait
probe_initializer_done:
    xor eax, eax
    add rsp, 32
    pop rbx
    ret
boom_probe_class_initializer ENDP
boom_probe_class_failure PROC
    mov DWORD PTR [rcx], 1
    mov DWORD PTR [rcx+4], 19
    mov DWORD PTR [rcx+8], 27
    xor eax, eax
    ret
boom_probe_class_failure ENDP
boom_probe_class_error PROC
    mov DWORD PTR [rcx], 3
    mov DWORD PTR [rcx+4], 23
    mov DWORD PTR [rcx+8], 29
    xor eax, eax
    ret
boom_probe_class_error ENDP
boom_probe_class_floating PROC
    mov ecx, 16777217
    cvtsi2ss xmm0, ecx
    movd eax, xmm0
    mov rdx, QWORD PTR [probe_count]
    mov DWORD PTR [rdx], eax
    xor eax, eax
    ret
boom_probe_class_floating ENDP
boom_probe_ensure_entry PROC
    mov rdx, rcx
    mov rcx, QWORD PTR [probe_descriptor]
    jmp boom_class_ensure
boom_probe_ensure_entry ENDP
END
