; Java array clone: fresh allocation, exact runtime type, shallow reference copy.
; Pool32: magic0 ABI4 heapCell*8 typeMap*16 reserved24.
; (ctx RCX, argv{array} RDX, pool R8, symbolic array TypeDesc* R9)->array/NULL.
; Source and immutable metadata are trusted VM pointers. No automatic GC may run
; while native references are live; collection remains explicit and quiescent.
option casemap:none
EXTERN boom_heap_alloc:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
PUBLIC boom_array_clone
.code
boom_array_clone PROC FRAME
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
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rbx,rcx
    mov r14,r9
    test rbx,rbx
    jz clone_error
    cmp DWORD PTR [rbx],0
    jne clone_error
    test rdx,rdx
    jz clone_bad
    mov rsi,QWORD PTR [rdx]
    test rsi,rsi
    jz clone_null
    test r8,r8
    jz clone_bad
    cmp DWORD PTR [r8],041434C50h
    jne clone_bad
    cmp DWORD PTR [r8+4],1
    jne clone_bad
    cmp QWORD PTR [r8+24],0
    jne clone_bad
    mov rax,QWORD PTR [r8+8]
    test rax,rax
    jz clone_bad
    mov r12,QWORD PTR [rax]
    test r12,r12
    jz clone_bad
    cmp DWORD PTR [r12],048454150h
    jne clone_bad
    cmp DWORD PTR [r12+4],1
    jne clone_bad
    mov r13,QWORD PTR [r8+16]
    test r14,r14
    jz clone_bad
    cmp DWORD PTR [r14],054595045h
    jne clone_bad
    cmp DWORD PTR [r14+4],1
    jne clone_bad
    cmp DWORD PTR [r14+8],3
    jne clone_bad
    ; Check the entire source block before asking the runtime tag map to read it.
    lea r10,[r12+160]
    cmp rsi,r10
    jb clone_bad
    test rsi,15
    jnz clone_bad
    mov r11,QWORD PTR [r12+16]
    add r11,r12
    jc clone_bad
    add r11,128
    jc clone_bad
    cmp r11,QWORD PTR [r12+24]
    jne clone_bad
    cmp rsi,r11
    ja clone_bad
    mov rax,QWORD PTR [rsi-32]
    cmp rax,32
    jb clone_bad
    test rax,15
    jnz clone_bad
    sub rax,32
    mov r15,QWORD PTR [rsi-16]
    cmp r15,rax
    ja clone_bad
    add rax,rsi
    jc clone_bad
    cmp rax,r11
    ja clone_bad
    mov rcx,rsi
    mov rdx,r13
    mov r8,rbx
    call boom_runtime_type
    test rax,rax
    jz clone_error
    cmp DWORD PTR [rax+8],3
    jne clone_bad
    mov rcx,rax
    mov rdx,r14
    call boom_type_assignable
    test eax,eax
    jz clone_bad
    mov rcx,r12
    mov rdx,r15
    mov r8d,DWORD PTR [rsi-20]
    mov r9,QWORD PTR [rsi-8]
    call boom_heap_alloc
    test rax,rax
    jz clone_oom
    mov QWORD PTR [rsp+32],rax
    mov rdi,rax
    mov rcx,r15
    rep movsb
    mov rax,QWORD PTR [rsp+32]
    jmp clone_done
clone_null:
    mov DWORD PTR [rbx],4
    jmp clone_error
clone_oom:
    mov DWORD PTR [rbx],3
    jmp clone_error
clone_bad:
    mov DWORD PTR [rbx],7
clone_error:
    xor eax,eax
clone_done:
    add rsp,64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_array_clone ENDP
END
