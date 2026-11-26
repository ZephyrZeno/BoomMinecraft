; Diagnostic task-pool wrapper around actual assembly type assignment checks.
option casemap:none
EXTERN boom_type_assignable:PROC
EXTERN boom_get_type_descriptor:PROC
PUBLIC boom_type_probe_entry
.code
boom_type_probe_entry PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp, 32
    .allocstack 32
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov ecx, DWORD PTR [rsi]
    call boom_get_type_descriptor
    mov rdi, rax
    mov ecx, DWORD PTR [rsi+8]
    call boom_get_type_descriptor
    test rdi, rdi
    jz type_probe_bad
    test rax, rax
    jz type_probe_bad
    mov rdx, rax
    mov rcx, rdi
    call boom_type_assignable
    jmp type_probe_done
type_probe_bad:
    mov DWORD PTR [rbx], 7
    xor eax, eax
type_probe_done:
    add rsp, 32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_type_probe_entry ENDP
END
