; Test-only assembly caller: corrupt the caller FP environment deliberately,
; invoke generated code, record its restored MXCSR, then restore the test host.
option casemap:none
PUBLIC boom_probe_numeric
PUBLIC boom_probe_gate
PUBLIC boom_probe_counted
.code
boom_probe_numeric PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp, 48
    .allocstack 48
    .endprolog
    stmxcsr DWORD PTR [rsp+32]
    mov DWORD PTR [rsp+36], r9d
    mov r10, rcx
    mov rbx, rdx
    mov rcx, rdx
    mov rdx, r8
    ldmxcsr DWORD PTR [rsp+36]
    call r10
    stmxcsr DWORD PTR [rbx+12]
    ldmxcsr DWORD PTR [rsp+32]
    add rsp, 48
    pop rbx
    ret
boom_probe_numeric ENDP
; Test-only pure assembly barrier. argv[0] points to a caller-owned DWORD gate.
boom_probe_gate PROC
    mov rax, QWORD PTR [rdx]
gate_wait:
    cmp DWORD PTR [rax], 0
    jne gate_open
    pause
    jmp gate_wait
gate_open:
    xor eax, eax
    ret
boom_probe_gate ENDP
; Count externally observable executions to detect scheduler replay/lost work.
boom_probe_counted PROC
    mov r10, QWORD PTR [rdx]
    lock inc QWORD PTR [r10]
    mov rax, QWORD PTR [rdx+8]
    ret
boom_probe_counted ENDP
END
