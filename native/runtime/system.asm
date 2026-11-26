; Source-verified System VM services. All guest execution is MASM.
; arraycopy(Context16 RCX, argv64 RDX, RuntimeTypeMap R8) -> void.
; argv: source, signed srcPos, destination, signed dstPos, signed count.
; Null/type/bounds checks precede writes; narrowing reference copies retain
; the successfully copied prefix on ArrayStoreException. Quiescent GC only.
option casemap:none
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
PUBLIC boom_system_arraycopy
PUBLIC boom_system_register
PUBLIC boom_system_dispatch
.const
system_primitive_shifts BYTE 0,0,1,1,2,3,2,3
.code
boom_system_arraycopy PROC FRAME
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
    push r14
    .pushreg r14
    push r15
    .pushreg r15
    sub rsp, 64
    .allocstack 64
    .endprolog
    mov rbx, rcx
    mov r12, r8
    mov rsi, QWORD PTR [rdx]
    mov rdi, QWORD PTR [rdx+16]
    movsxd r13, DWORD PTR [rdx+8]
    movsxd r14, DWORD PTR [rdx+24]
    movsxd r15, DWORD PTR [rdx+32]
    test rsi, rsi
    jz system_copy_null
    test rdi, rdi
    jz system_copy_null
    mov rcx, rsi
    mov rdx, r12
    mov r8, rbx
    call boom_runtime_type
    test rax, rax
    jz system_copy_done
    cmp DWORD PTR [rax+8], 3
    jne system_copy_type
    mov rax, QWORD PTR [rax+16]
    mov QWORD PTR [rsp+40], rax
    mov rcx, rdi
    mov rdx, r12
    mov r8, rbx
    call boom_runtime_type
    test rax, rax
    jz system_copy_done
    cmp DWORD PTR [rax+8], 3
    jne system_copy_type
    mov rax, QWORD PTR [rax+16]
    mov QWORD PTR [rsp+48], rax
    mov r10, QWORD PTR [rsp+40]
    test rax, rax
    jz system_copy_invalid
    test r10, r10
    jz system_copy_invalid
    cmp DWORD PTR [rax], 054595045h
    jne system_copy_invalid
    cmp DWORD PTR [r10], 054595045h
    jne system_copy_invalid
    cmp DWORD PTR [rax+4], 1
    jne system_copy_invalid
    cmp DWORD PTR [r10+4], 1
    jne system_copy_invalid
    cmp DWORD PTR [rax+8], 0
    je system_copy_primitive
    cmp DWORD PTR [r10+8], 0
    je system_copy_type
    mov DWORD PTR [rsp+32], 3
    mov DWORD PTR [rsp+36], 1
    jmp system_copy_bounds_check
system_copy_primitive:
    cmp rax, r10
    jne system_copy_type
    mov eax, DWORD PTR [rax+12]
    cmp eax, 7
    ja system_copy_invalid
    lea r10, system_primitive_shifts
    movzx eax, BYTE PTR [r10+rax]
    mov DWORD PTR [rsp+32], eax
    mov DWORD PTR [rsp+36], 0
system_copy_bounds_check:
    test r13, r13
    js system_copy_bounds
    test r14, r14
    js system_copy_bounds
    test r15, r15
    js system_copy_bounds
    mov ecx, DWORD PTR [rsp+32]
    mov rax, QWORD PTR [rsi-16]
    shr rax, cl
    lea r10, [r13+r15]
    cmp r10, rax
    ja system_copy_bounds
    mov rax, QWORD PTR [rdi-16]
    shr rax, cl
    lea r10, [r14+r15]
    cmp r10, rax
    ja system_copy_bounds
    test r15, r15
    jz system_copy_done
    cmp DWORD PTR [rsp+36], 0
    je system_copy_bulk
    mov rcx, QWORD PTR [rsp+40]
    mov rdx, QWORD PTR [rsp+48]
    call boom_type_assignable
    test eax, eax
    jnz system_copy_bulk
    lea rsi, [rsi+r13*8]
    lea rdi, [rdi+r14*8]
system_copy_checked:
    mov r13, QWORD PTR [rsi]
    test r13, r13
    jz system_copy_store
    mov rcx, r13
    mov rdx, r12
    mov r8, rbx
    call boom_runtime_type
    test rax, rax
    jz system_copy_done
    mov rcx, rax
    mov rdx, QWORD PTR [rsp+48]
    call boom_type_assignable
    test eax, eax
    jz system_copy_type
system_copy_store:
    mov QWORD PTR [rdi], r13
    add rsi, 8
    add rdi, 8
    dec r15
    jnz system_copy_checked
    jmp system_copy_done
system_copy_bulk:
    mov ecx, DWORD PTR [rsp+32]
    shl r13, cl
    shl r14, cl
    add rsi, r13
    add rdi, r14
    cmp rdi, rsi
    jbe system_copy_forward
    mov rax, r15
    shl rax, cl
    add rax, rsi
    cmp rdi, rax
    jae system_copy_forward
    dec r15
    mov rax, r15
    shl rax, cl
    add rsi, rax
    add rdi, rax
    inc r15
    cmp ecx, 3
    je system_copy_back64
    cmp ecx, 2
    je system_copy_back32
    cmp ecx, 1
    je system_copy_back16
system_copy_back8:
    mov al, BYTE PTR [rsi]
    mov BYTE PTR [rdi], al
    dec rsi
    dec rdi
    dec r15
    jnz system_copy_back8
    jmp system_copy_done
system_copy_back16:
    mov ax, WORD PTR [rsi]
    mov WORD PTR [rdi], ax
    sub rsi, 2
    sub rdi, 2
    dec r15
    jnz system_copy_back16
    jmp system_copy_done
system_copy_back32:
    mov eax, DWORD PTR [rsi]
    mov DWORD PTR [rdi], eax
    sub rsi, 4
    sub rdi, 4
    dec r15
    jnz system_copy_back32
    jmp system_copy_done
system_copy_back64:
    mov rax, QWORD PTR [rsi]
    mov QWORD PTR [rdi], rax
    sub rsi, 8
    sub rdi, 8
    dec r15
    jnz system_copy_back64
    jmp system_copy_done
system_copy_forward:
    cmp ecx, 3
    je system_copy_forward64
    cmp ecx, 2
    je system_copy_forward32
    cmp ecx, 1
    je system_copy_forward16
system_copy_forward8:
    mov al, BYTE PTR [rsi]
    mov BYTE PTR [rdi], al
    inc rsi
    inc rdi
    dec r15
    jnz system_copy_forward8
    jmp system_copy_done
system_copy_forward16:
    mov ax, WORD PTR [rsi]
    mov WORD PTR [rdi], ax
    add rsi, 2
    add rdi, 2
    dec r15
    jnz system_copy_forward16
    jmp system_copy_done
system_copy_forward32:
    mov eax, DWORD PTR [rsi]
    mov DWORD PTR [rdi], eax
    add rsi, 4
    add rdi, 4
    dec r15
    jnz system_copy_forward32
    jmp system_copy_done
system_copy_forward64:
    mov rax, QWORD PTR [rsi]
    mov QWORD PTR [rdi], rax
    add rsi, 8
    add rdi, 8
    dec r15
    jnz system_copy_forward64
    jmp system_copy_done
system_copy_null:
    mov DWORD PTR [rbx], 4
    jmp system_copy_done
system_copy_type:
    mov DWORD PTR [rbx], 6
    jmp system_copy_done
system_copy_bounds:
    mov DWORD PTR [rbx], 5
    jmp system_copy_done
system_copy_invalid:
    mov DWORD PTR [rbx], 7
system_copy_done:
    xor eax, eax
    add rsp, 64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_system_arraycopy ENDP

; Pool32: magic0 ABI4 activeTable*8 expectedTable*16 typeMap*24.
; Immutable table40: magic0 ABI4 count8 flags12, three native entry pointers16.
; Every entry has Context16/argv/typeMap ABI; indices millis0/nanos1/arraycopy2.
system_pool_valid PROC
    test r8, r8
    jz system_pool_bad
    cmp DWORD PTR [r8], 053595350h
    jne system_pool_bad
    cmp DWORD PTR [r8+4], 1
    jne system_pool_bad
    cmp QWORD PTR [r8+24], 0
    je system_pool_bad
    mov r10, QWORD PTR [r8+16]
    test r10, r10
    jz system_pool_bad
    cmp DWORD PTR [r10], 05359534Dh
    jne system_pool_bad
    cmp DWORD PTR [r10+4], 1
    jne system_pool_bad
    cmp DWORD PTR [r10+8], 3
    jne system_pool_bad
    cmp DWORD PTR [r10+12], 0
    jne system_pool_bad
    cmp QWORD PTR [r10+16], 0
    je system_pool_bad
    cmp QWORD PTR [r10+24], 0
    je system_pool_bad
    cmp QWORD PTR [r10+32], 0
    je system_pool_bad
    mov eax, 1
    ret
system_pool_bad:
    xor eax, eax
    ret
system_pool_valid ENDP

; register(ctx RCX,unused argv RDX,pool R8)->void. Publish a fully validated
; complete table with one CAS, so readers never observe partially registered slots.
boom_system_register PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    call system_pool_valid
    test eax, eax
    jz system_register_bad
    xor eax, eax
    lock cmpxchg QWORD PTR [r8+8], r10
    test rax, rax
    jz system_register_done
    cmp rax, r10
    je system_register_done
system_register_bad:
    mov DWORD PTR [rcx], 7
system_register_done:
    xor eax, eax
    add rsp, 40
    ret
boom_system_register ENDP

; dispatch(ctx RCX,argv RDX,pool R8,index R9D)->guest result. Native resolution
; uses the published registration, never a fallback to a JVM or host language.
boom_system_dispatch PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    call system_pool_valid
    test eax, eax
    jz system_dispatch_bad
    cmp r9d, 2
    ja system_dispatch_bad
    mov rax, QWORD PTR [r8+8]
    test rax, rax
    jz system_dispatch_unregistered
    cmp rax, r10
    jne system_dispatch_bad
    mov rax, QWORD PTR [rax+r9*8+16]
    mov r8, QWORD PTR [r8+24]
    call rax
    add rsp, 40
    ret
system_dispatch_unregistered:
    mov DWORD PTR [rcx], 20
    jmp system_dispatch_zero
system_dispatch_bad:
    mov DWORD PTR [rcx], 7
system_dispatch_zero:
    xor eax, eax
    add rsp, 40
    ret
boom_system_dispatch ENDP
END
