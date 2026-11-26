; Bootstrap arrays in MASM. Payload is elements only; heap type=256+atype.
; Kinds 4..11 are JVM newarray kinds; 12 is an untyped reference array.
; Primitive Java lowering is integrated. Typed reference arrays and safepoints are pending.
; Context16 errors: 2 negative size, 3 OOM, 4 null, 5 bounds, 6 type, 7 kind.
option casemap:none
EXTERN boom_heap_alloc:PROC
PUBLIC boom_array_new
PUBLIC boom_array_length
PUBLIC boom_array_load
PUBLIC boom_array_store
PUBLIC boom_array_copy
.const
array_shifts BYTE 0,0,0,0,0,1,2,3,0,1,2,3,3
.code
; new(heap,len,kind,context) -> array/NULL
boom_array_new PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    sub rsp, 40
    .allocstack 40
    .endprolog
    mov rbx, r9
    test edx, edx
    js array_new_negative
    cmp r8d, 4
    jb array_new_kind
    cmp r8d, 12
    ja array_new_kind
    mov rsi, rcx
    mov edi, edx
    mov r12d, r8d
    lea r10, array_shifts
    movzx ecx, BYTE PTR [r10+r12]
    mov edx, edi
    shl rdx, cl
    xor r8d, r8d
    cmp r12d, 12
    cmove r8d, edi
    lea r9, [r12+256]
    mov rcx, rsi
    call boom_heap_alloc
    test rax, rax
    jnz array_new_done
    mov DWORD PTR [rbx], 3
    jmp array_new_done
array_new_negative:
    mov DWORD PTR [rbx], 2
    xor eax, eax
    jmp array_new_done
array_new_kind:
    mov DWORD PTR [rbx], 7
    xor eax, eax
array_new_done:
    add rsp, 40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_array_new ENDP

; length(array,context) -> length/0; array length derives from payload bytes.
boom_array_length PROC
    test rcx, rcx
    jz array_length_null
    mov eax, DWORD PTR [rcx-8]
    sub eax, 256
    cmp eax, 4
    jb array_length_kind
    cmp eax, 12
    ja array_length_kind
    lea r10, array_shifts
    movzx r10d, BYTE PTR [r10+rax]
    mov rax, QWORD PTR [rcx-16]
    mov ecx, r10d
    shr rax, cl
    ret
array_length_null:
    mov DWORD PTR [rdx], 4
    xor eax, eax
    ret
array_length_kind:
    mov DWORD PTR [rdx], 7
    xor eax, eax
    ret
boom_array_length ENDP

; access(array,index,expected kind,context) -> element address, r10d actual kind
array_access PROC
    test rcx, rcx
    jz array_access_null
    test edx, edx
    js array_access_bounds
    mov r10d, DWORD PTR [rcx-8]
    sub r10d, 256
    cmp r10d, 4
    jb array_access_type
    cmp r10d, 12
    ja array_access_type
    cmp r10d, r8d
    je array_access_kind_ok
    cmp r10d, 4
    jne array_access_type
    cmp r8d, 8
    jne array_access_type
array_access_kind_ok:
    mov r11, rcx
    lea rax, array_shifts
    movzx ecx, BYTE PTR [rax+r10]
    mov eax, edx
    shl rax, cl
    cmp rax, QWORD PTR [r11-16]
    jae array_access_bounds
    add rax, r11
    ret
array_access_null:
    mov DWORD PTR [r9], 4
    xor eax, eax
    ret
array_access_bounds:
    mov DWORD PTR [r9], 5
    xor eax, eax
    ret
array_access_type:
    mov DWORD PTR [r9], 6
    xor eax, eax
    ret
array_access ENDP

; load(array,index,expected kind,context) -> canonical raw bits
boom_array_load PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    call array_access
    test rax, rax
    jz array_load_done
    cmp r10d, 12
    je array_load_qword
    cmp r10d, 11
    je array_load_qword
    cmp r10d, 7
    je array_load_qword
    cmp r10d, 10
    je array_load_dword
    cmp r10d, 6
    je array_load_dword
    cmp r10d, 5
    je array_load_char
    cmp r10d, 9
    je array_load_short
    cmp r10d, 4
    je array_load_boolean
    movsx eax, BYTE PTR [rax]
    jmp array_load_done
array_load_qword:
    mov rax, QWORD PTR [rax]
    jmp array_load_done
array_load_dword:
    mov eax, DWORD PTR [rax]
    jmp array_load_done
array_load_char:
    movzx eax, WORD PTR [rax]
    jmp array_load_done
array_load_short:
    movsx eax, WORD PTR [rax]
    jmp array_load_done
array_load_boolean:
    movzx eax, BYTE PTR [rax]
array_load_done:
    add rsp, 40
    ret
boom_array_load ENDP

; store(array,index,bits,expected kind,context)
boom_array_store PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp, 32
    .allocstack 32
    .endprolog
    mov rbx, r8
    mov r8d, r9d
    mov r9, QWORD PTR [rsp+80]
    call array_access
    test rax, rax
    jz array_store_done
    cmp r10d, 12
    je array_store_qword
    cmp r10d, 11
    je array_store_qword
    cmp r10d, 7
    je array_store_qword
    cmp r10d, 10
    je array_store_dword
    cmp r10d, 6
    je array_store_dword
    cmp r10d, 5
    je array_store_word
    cmp r10d, 9
    je array_store_word
    cmp r10d, 4
    jne array_store_byte
    and ebx, 1
array_store_byte:
    mov BYTE PTR [rax], bl
    jmp array_store_done
array_store_word:
    mov WORD PTR [rax], bx
    jmp array_store_done
array_store_dword:
    mov DWORD PTR [rax], ebx
    jmp array_store_done
array_store_qword:
    mov QWORD PTR [rax], rbx
array_store_done:
    xor eax, eax
    add rsp, 32
    pop rbx
    ret
boom_array_store ENDP

; copy(src,srcPos,dst,dstPos,len,context), supports overlapping ranges
boom_array_copy PROC FRAME
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
    sub rsp, 40
    .allocstack 40
    .endprolog
    mov rbx, QWORD PTR [rsp+136]
    mov r14d, DWORD PTR [rsp+128]
    test rcx, rcx
    jz array_copy_null
    test r8, r8
    jz array_copy_null
    mov rsi, rcx
    mov rdi, r8
    mov r12d, edx
    mov r13d, r9d
    mov eax, DWORD PTR [rsi-8]
    cmp eax, DWORD PTR [rdi-8]
    jne array_copy_type
    sub eax, 256
    cmp eax, 4
    jb array_copy_type
    cmp eax, 12
    ja array_copy_type
    test r12d, r12d
    js array_copy_bounds
    test r13d, r13d
    js array_copy_bounds
    test r14d, r14d
    js array_copy_bounds
    lea r10, array_shifts
    movzx ecx, BYTE PTR [r10+rax]
    lea r10, [r12+r14]
    shl r10, cl
    cmp r10, QWORD PTR [rsi-16]
    ja array_copy_bounds
    lea r10, [r13+r14]
    shl r10, cl
    cmp r10, QWORD PTR [rdi-16]
    ja array_copy_bounds
    test r14d, r14d
    jz array_copy_done
    shl r12, cl
    shl r13, cl
    shl r14, cl
    add rsi, r12
    add rdi, r13
    mov rcx, r14
    cld
    cmp rdi, rsi
    jbe array_copy_forward
    lea rax, [rsi+rcx]
    cmp rdi, rax
    jae array_copy_forward
    lea rsi, [rsi+rcx-1]
    lea rdi, [rdi+rcx-1]
    std
    rep movsb
    cld
    jmp array_copy_done
array_copy_forward:
    rep movsb
    jmp array_copy_done
array_copy_null:
    mov DWORD PTR [rbx], 4
    jmp array_copy_done
array_copy_bounds:
    mov DWORD PTR [rbx], 5
    jmp array_copy_done
array_copy_type:
    mov DWORD PTR [rbx], 6
array_copy_done:
    xor eax, eax
    add rsp, 40
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_array_copy ENDP
END
