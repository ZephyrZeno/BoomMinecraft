; Dynamic reference-array operations using the verified runtime type map.
; (Context16 RCX, argv64 RDX, typeMap R8, operation R9D) -> RAX.
; argv: array, signed int index, value. Operations 0 length, 1 load, 2 store.
; Null/bounds precede element assignability; stores preserve the previous slot
; on failure. Allocation and GC retain the existing reference-prefix heap ABI.
option casemap:none
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
PUBLIC boom_covariant_array
.code
boom_covariant_array PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    push r13
    .pushreg r13
    sub rsp, 64
    .allocstack 64
    .endprolog
    mov rsi, rcx
    mov rdi, rdx
    mov r12, r8
    mov r13d, r9d
    cmp r13d, 2
    ja covariant_invalid
    test rdi, rdi
    jz covariant_invalid
    mov rbx, QWORD PTR [rdi]
    mov rcx, rbx
    mov rdx, r12
    mov r8, rsi
    call boom_runtime_type
    test rax, rax
    jz covariant_done
    cmp DWORD PTR [rax+8], 3
    jne covariant_invalid
    mov rax, QWORD PTR [rax+16]
    test rax, rax
    jz covariant_invalid
    cmp DWORD PTR [rax], 054595045h
    jne covariant_invalid
    cmp DWORD PTR [rax+4], 1
    jne covariant_invalid
    mov ecx, DWORD PTR [rax+8]
    dec ecx
    cmp ecx, 2
    ja covariant_invalid
covariant_component:
    mov QWORD PTR [rsp+40], rax
    mov eax, DWORD PTR [rbx-20]
    test r13d, r13d
    jz covariant_done
    mov edx, DWORD PTR [rdi+8]
    cmp edx, eax
    jae covariant_bounds
    cmp r13d, 1
    je covariant_load
    mov rcx, QWORD PTR [rdi+16]
    test rcx, rcx
    jz covariant_store
    mov rdx, r12
    mov r8, rsi
    call boom_runtime_type
    test rax, rax
    jz covariant_done
    mov rcx, rax
    mov rdx, QWORD PTR [rsp+40]
    call boom_type_assignable
    test eax, eax
    jz covariant_type
covariant_store:
    mov edx, DWORD PTR [rdi+8]
    mov rax, QWORD PTR [rdi+16]
    mov QWORD PTR [rbx+rdx*8], rax
    xor eax, eax
    jmp covariant_done
covariant_load:
    mov rax, QWORD PTR [rbx+rdx*8]
    jmp covariant_done
covariant_bounds:
    mov DWORD PTR [rsi], 5
    jmp covariant_zero
covariant_type:
    mov DWORD PTR [rsi], 6
    jmp covariant_zero
covariant_invalid:
    mov DWORD PTR [rsi], 7
covariant_zero:
    xor eax, eax
covariant_done:
    add rsp, 64
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_covariant_array ENDP
END
