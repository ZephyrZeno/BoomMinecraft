; Loader-aware array allocation, including multianewarray. All execution MASM.
; new(heap RCX, counts64* RDX, array TypeDesc* R8, dimensions R9D,
;     Context16* stack arg5) -> array/NULL. No automatic GC with native roots live.
; Reference arrays use their immutable TypeDesc address as heap tag; primitive
; leaves retain the existing newarray tags. Reference-prefix slots preserve GC.
option casemap:none
EXTERN boom_heap_alloc:PROC
EXTERN boom_runtime_type:PROC
PUBLIC boom_typed_multi_new
PUBLIC boom_typed_array_length
.const
typed_primitive_tags DWORD 260,264,261,265,266,267,262,263
typed_primitive_shifts BYTE 0,0,1,1,2,3,2,3
.code
boom_typed_multi_new PROC FRAME
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
    sub rsp,56
    .allocstack 56
    .endprolog
    mov rbx,QWORD PTR [rsp+144]
    mov r12,rcx
    mov rsi,rdx
    mov rdi,r8
    mov r13d,r9d
    test rbx,rbx
    jz typed_new_zero
    cmp DWORD PTR [rbx],0
    jne typed_new_zero
    test r12,r12
    jz typed_new_bad
    cmp DWORD PTR [r12],048454150h
    jne typed_new_bad
    cmp DWORD PTR [r12+4],1
    jne typed_new_bad
    test rsi,rsi
    jz typed_new_bad
    lea eax,[r13-1]
    cmp eax,254
    ja typed_new_bad
    mov r14,rdi
    xor r10d,r10d
typed_validate:
    test r14,r14
    jz typed_new_bad
    cmp DWORD PTR [r14],054595045h
    jne typed_new_bad
    cmp DWORD PTR [r14+4],1
    jne typed_new_bad
    cmp DWORD PTR [r14+8],3
    jne typed_new_bad
    mov r14,QWORD PTR [r14+16]
    test r14,r14
    jz typed_new_bad
    cmp DWORD PTR [r14],054595045h
    jne typed_new_bad
    cmp DWORD PTR [r14+4],1
    jne typed_new_bad
    mov eax,DWORD PTR [r14+8]
    cmp eax,3
    ja typed_new_bad
    test eax,eax
    jnz typed_validate_component
    cmp DWORD PTR [r14+12],7
    ja typed_new_bad
typed_validate_component:
    inc r10d
    cmp r10d,r13d
    jb typed_validate
    ; Every dimension is checked, even when an earlier dimension is zero.
    xor r10d,r10d
typed_validate_counts:
    cmp DWORD PTR [rsi+r10*8],0
    jl typed_new_negative
    inc r10d
    cmp r10d,r13d
    jb typed_validate_counts
    mov rcx,r12
    mov rdx,rsi
    mov r8,rdi
    mov r9d,r13d
    mov QWORD PTR [rsp+32],rbx
    call typed_allocate_level
    jmp typed_new_done
typed_new_negative:
    mov DWORD PTR [rbx],2 ; NegativeArraySizeException, shared Context ABI
    jmp typed_new_zero
typed_new_bad:
    mov DWORD PTR [rbx],7
typed_new_zero:
    xor eax,eax
typed_new_done:
    add rsp,56
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_typed_multi_new ENDP

; All metadata/counts have been validated before entering this recursion.
typed_allocate_level PROC FRAME
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
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,QWORD PTR [rsp+144]
    mov r12,rcx
    mov rsi,rdx
    mov rdi,r8
    mov r13d,r9d
    mov r10,QWORD PTR [rdi+16]
    mov edx,DWORD PTR [rsi]
    cmp DWORD PTR [r10+8],0
    je typed_allocate_primitive
    mov r8d,edx
    shl rdx,3
    mov r9,rdi
    jmp typed_allocate_call
typed_allocate_primitive:
    mov eax,DWORD PTR [r10+12]
    lea r10,typed_primitive_tags
    mov r9d,DWORD PTR [r10+rax*4]
    lea r10,typed_primitive_shifts
    movzx ecx,BYTE PTR [r10+rax]
    shl rdx,cl
    xor r8d,r8d
typed_allocate_call:
    mov rcx,r12
    call boom_heap_alloc
    test rax,rax
    jz typed_allocate_oom
    mov r14,rax
    cmp r13d,1
    je typed_allocate_return
    xor r15d,r15d
typed_allocate_child:
    cmp r15d,DWORD PTR [rsi]
    jae typed_allocate_return
    mov rcx,r12
    lea rdx,[rsi+8]
    mov r8,QWORD PTR [rdi+16]
    lea r9d,[r13-1]
    mov QWORD PTR [rsp+32],rbx
    call typed_allocate_level
    test rax,rax
    jz typed_allocate_done
    mov QWORD PTR [r14+r15*8],rax
    inc r15d
    jmp typed_allocate_child
typed_allocate_return:
    mov rax,r14
    jmp typed_allocate_done
typed_allocate_oom:
    mov DWORD PTR [rbx],3
    xor eax,eax
typed_allocate_done:
    add rsp,48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
typed_allocate_level ENDP

; length(array RCX, runtime map RDX, context R8) -> Java int length/0.
boom_typed_array_length PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    mov rsi,r8
    cmp DWORD PTR [rsi],0
    jne typed_length_zero
    call boom_runtime_type
    test rax,rax
    jz typed_length_done
    cmp DWORD PTR [rax+8],3
    jne typed_length_bad
    mov rdi,QWORD PTR [rax+16]
    cmp DWORD PTR [rdi+8],0
    je typed_length_primitive
    mov eax,DWORD PTR [rbx-20]
    jmp typed_length_done
typed_length_primitive:
    mov ecx,DWORD PTR [rdi+12]
    cmp ecx,7
    ja typed_length_bad
    lea r10,typed_primitive_shifts
    movzx ecx,BYTE PTR [r10+rcx]
    mov rax,QWORD PTR [rbx-16]
    shr rax,cl
    jmp typed_length_done
typed_length_bad:
    mov DWORD PTR [rsi],7
typed_length_zero:
    xor eax,eax
typed_length_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_typed_array_length ENDP
END
