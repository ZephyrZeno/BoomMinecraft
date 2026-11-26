; Typed reference arrays. Allocation accepts object layout ABI1/ABI2. All MASM.
; Descriptor: magic DWORD 0x52454641, ABI DWORD 1, component-layout QWORD.
; Header type is the descriptor address; all payload slots are GC references.
; Legacy access is exact-layout; covariant_arrays.asm supplies hierarchy access.
; Multidimensional arrays, arraycopy and automatic GC remain separate work.
option casemap:none
EXTERN boom_heap_alloc:PROC
PUBLIC boom_reference_array_new
PUBLIC boom_reference_array_length
PUBLIC boom_reference_array_load
PUBLIC boom_reference_array_store
.code

; new(heap,signed length,array descriptor,Context16) -> pointer/NULL
boom_reference_array_new PROC FRAME
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
    mov rsi, r8
    mov rdi, r9
    test edx, edx
    js reference_new_negative
    mov r10d, edx
    test rsi, rsi
    jz reference_new_invalid
    cmp DWORD PTR [rsi], 052454641h
    jne reference_new_invalid
    cmp DWORD PTR [rsi+4], 1
    jne reference_new_invalid
    mov rax, QWORD PTR [rsi+8]
    test rax, rax
    jz reference_new_invalid
    cmp DWORD PTR [rax], 04F424A43h
    jne reference_new_invalid
    mov ecx, DWORD PTR [rax+4]
    dec ecx
    cmp ecx, 1
    ja reference_new_invalid
    mov r8d, r10d
    mov rdx, r8
    shl rdx, 3
    mov r9, rsi
    mov rcx, rbx
    call boom_heap_alloc
    test rax, rax
    jnz reference_new_done
    mov DWORD PTR [rdi], 3
    jmp reference_new_done
reference_new_negative:
    mov DWORD PTR [rdi], 2
    xor eax, eax
    jmp reference_new_done
reference_new_invalid:
    mov DWORD PTR [rdi], 7
    xor eax, eax
reference_new_done:
    add rsp, 32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_reference_array_new ENDP

; length(array,expected descriptor,context). Private access caller relies on
; rcx,rdx,r8,r9,r11 being preserved by this leaf routine.
boom_reference_array_length PROC
    test rcx, rcx
    jz reference_length_null
    mov eax, DWORD PTR [rcx-24]
    and eax, 0FFFFFFFDh
    cmp eax, 0B00B0001h
    jne reference_length_invalid
    cmp QWORD PTR [rcx-8], rdx
    jne reference_length_invalid
    mov eax, DWORD PTR [rcx-20]
    mov r10, rax
    shl r10, 3
    cmp QWORD PTR [rcx-16], r10
    jne reference_length_invalid
    ret
reference_length_null:
    mov DWORD PTR [r8], 4
    mov rax, -1
    ret
reference_length_invalid:
    mov DWORD PTR [r8], 7
    mov rax, -1
    ret
boom_reference_array_length ENDP

; private access(array,index,descriptor,context) -> address/NULL
reference_access PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    mov r11d, edx
    mov rdx, r8
    mov r8, r9
    call boom_reference_array_length
    cmp rax, -1
    je reference_access_fail
    test r11d, r11d
    js reference_access_bounds
    cmp r11, rax
    jae reference_access_bounds
    lea rax, [rcx+r11*8]
    jmp reference_access_done
reference_access_bounds:
    mov DWORD PTR [r8], 5
reference_access_fail:
    xor eax, eax
reference_access_done:
    add rsp, 40
    ret
reference_access ENDP

boom_reference_array_load PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    call reference_access
    test rax, rax
    jz reference_load_done
    mov rax, QWORD PTR [rax]
reference_load_done:
    add rsp, 40
    ret
boom_reference_array_load ENDP

; store(array,index,value,descriptor,context fifth) -> 0, status in context
boom_reference_array_store PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp, 40
    .allocstack 40
    .endprolog
    mov rbx, r8
    mov rsi, r9
    mov r8, r9
    mov r9, QWORD PTR [rsp+96]
    call reference_access
    test rax, rax
    jz reference_store_done
    test rbx, rbx
    jz reference_store_value
    mov edx, DWORD PTR [rbx-24]
    and edx, 0FFFFFFFDh
    cmp edx, 0B00B0001h
    jne reference_store_type
    mov rdx, QWORD PTR [rsi+8]
    cmp QWORD PTR [rbx-8], rdx
    jne reference_store_type
reference_store_value:
    mov QWORD PTR [rax], rbx
    jmp reference_store_done
reference_store_type:
    mov rdx, QWORD PTR [rsp+96]
    mov DWORD PTR [rdx], 6
reference_store_done:
    xor eax, eax
    add rsp, 40
    pop rsi
    pop rbx
    ret
boom_reference_array_store ENDP
END
