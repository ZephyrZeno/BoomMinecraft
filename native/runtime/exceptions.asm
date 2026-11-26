; Materialized Throwable propagation and ordered handler selection. MASM only.
; Explicit Context32 API: kind0 pc4 method8 depth12 pending-object16 reserved24.
; kind16 means a materialized pending Throwable. No Context16 caller may use this API.
; This layer does NOT materialize implicit VM exceptions or implement Java athrow-null.
; Compiler/VM must create the actual Throwable first, and register pending-object as
; a root at a safepoint. Current collector is explicit/quiescent; it does not scan stacks.
; Handler table40: magic0 ABI4 count8 reserved12 rows*16 typeMap*24 ThrowableType*32.
; Row24: startPC0 endPC4 handlerPC8 reserved12 catchType*16 (NULL = catch-all).
; All metadata and heap pointers must be live trusted module inputs, not arbitrary addresses.
option casemap:none
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
PUBLIC boom_exception_set32
PUBLIC boom_exception_match32
PUBLIC boom_exception_take32
.code
; set32(ctx RCX,nonnull Throwable RDX,typeMap R8,bootstrap ThrowableType R9)
; -> EAX=16 on success, 7 on malformed/non-Throwable input. Origin PC/method/depth
; are untouched. Failure retains an existing pending root for diagnostics/collection.
boom_exception_set32 PROC FRAME
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
    mov rdi, r9
    test rbx, rbx
    jz exception_set_noctx
    test rsi, rsi
    jz exception_set_bad
    test rdi, rdi
    jz exception_set_bad
    cmp DWORD PTR [rdi], 054595045h
    jne exception_set_bad
    cmp DWORD PTR [rdi+4], 1
    jne exception_set_bad
    cmp DWORD PTR [rdi+8], 1
    jne exception_set_bad
    mov rcx, rsi
    mov rdx, r8
    mov r8, rbx
    call boom_runtime_type
    test rax, rax
    jz exception_set_bad
    mov rcx, rax
    mov rdx, rdi
    call boom_type_assignable
    test eax, eax
    jz exception_set_bad
    mov QWORD PTR [rbx+16], rsi
    mov DWORD PTR [rbx], 16
    mov eax, 16
    jmp exception_set_done
exception_set_bad:
    mov DWORD PTR [rbx], 7
exception_set_noctx:
    mov eax, 7
exception_set_done:
    add rsp, 32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_exception_set32 ENDP

; match32(ctx RCX,LOCAL protected call-site PC EDX,handler table R8)
; -> EAX=handlerPC+1, or 0 when unhandled/malformed. No match consumes the root.
; Local PC is distinct from the original throwing PC stored in ctx+4.
boom_exception_match32 PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push rbp
    .pushreg rbp
    push r12
    .pushreg r12
    push r13
    .pushreg r13
    push r14
    .pushreg r14
    sub rsp, 32
    .allocstack 32
    .endprolog
    mov rbx, rcx
    mov r12d, edx
    mov rsi, r8
    test rbx, rbx
    jz exception_match_none
    cmp DWORD PTR [rbx], 16
    jne exception_match_none
    cmp QWORD PTR [rbx+16], 0
    je exception_match_bad
    cmp r12d, 65535
    jae exception_match_bad
    test rsi, rsi
    jz exception_match_bad
    cmp DWORD PTR [rsi], 045584348h
    jne exception_match_bad
    cmp DWORD PTR [rsi+4], 1
    jne exception_match_bad
    cmp DWORD PTR [rsi+12], 0
    jne exception_match_bad
    mov r13d, DWORD PTR [rsi+8]
    cmp r13d, 65535
    ja exception_match_bad
    test r13d, r13d
    jz exception_match_none
    mov r14, QWORD PTR [rsi+16]
    test r14, r14
    jz exception_match_bad
    mov rdi, QWORD PTR [rsi+32]
    test rdi, rdi
    jz exception_match_bad
    cmp DWORD PTR [rdi], 054595045h
    jne exception_match_bad
    cmp DWORD PTR [rdi+4], 1
    jne exception_match_bad
    cmp DWORD PTR [rdi+8], 1
    jne exception_match_bad
    mov rcx, QWORD PTR [rbx+16]
    mov rdx, QWORD PTR [rsi+24]
    mov r8, rbx
    call boom_runtime_type
    test rax, rax
    jz exception_match_bad
    mov rbp, rax
    mov rcx, rbp
    mov rdx, rdi
    call boom_type_assignable
    test eax, eax
    jz exception_match_bad
exception_match_row:
    mov eax, DWORD PTR [r14]
    cmp eax, DWORD PTR [r14+4]
    jae exception_match_bad
    cmp DWORD PTR [r14+4], 65535
    ja exception_match_bad
    cmp DWORD PTR [r14+8], 65535
    jae exception_match_bad
    cmp DWORD PTR [r14+12], 0
    jne exception_match_bad
    cmp r12d, eax
    jb exception_match_next
    cmp r12d, DWORD PTR [r14+4]
    jae exception_match_next
    mov rdx, QWORD PTR [r14+16]
    test rdx, rdx
    jz exception_match_found
    cmp DWORD PTR [rdx], 054595045h
    jne exception_match_bad
    cmp DWORD PTR [rdx+4], 1
    jne exception_match_bad
    cmp DWORD PTR [rdx+8], 1
    jne exception_match_bad
    mov rcx, rdx
    mov rdx, rdi
    call boom_type_assignable
    test eax, eax
    jz exception_match_bad
    mov rcx, rbp
    mov rdx, QWORD PTR [r14+16]
    call boom_type_assignable
    test eax, eax
    jnz exception_match_found
exception_match_next:
    add r14, 24
    dec r13d
    jnz exception_match_row
    jmp exception_match_none
exception_match_found:
    mov eax, DWORD PTR [r14+8]
    inc eax
    jmp exception_match_done
exception_match_bad:
    mov DWORD PTR [rbx], 7
exception_match_none:
    xor eax, eax
exception_match_done:
    add rsp, 32
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rdi
    pop rsi
    pop rbx
    ret
boom_exception_match32 ENDP

; take32(ctx RCX)->same Throwable reference RAX; clears pending exception state,
; preserves current depth and the reserved tail. Caller places RAX at stack[0].
boom_exception_take32 PROC
    xor eax, eax
    test rcx, rcx
    jz exception_take_done
    cmp DWORD PTR [rcx], 16
    jne exception_take_done
    mov rax, QWORD PTR [rcx+16]
    test rax, rax
    jz exception_take_done
    mov QWORD PTR [rcx], 0
    mov DWORD PTR [rcx+8], 0
    mov QWORD PTR [rcx+16], 0
exception_take_done:
    ret
boom_exception_take32 ENDP
END
