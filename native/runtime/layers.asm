; Frozen boot/empty module layers. All game operations are MASM.
; Module pool ABI2 size96; tail layerPool80 and heapPointerCell88.
; Layer pool64 ABI1: magic0 abi4 lock8 count12=2 roots16 layout24
; modulePool32 heapPointerCell40 boundHeap48 reserved56=0.
; Layer payload8 holds id 0(empty) or 1(boot), no guest references.
; Find returns Module/NULL; generated code wraps it using AOT JDK Optional.
option casemap:none
EXTERN boom_module_pool_valid:PROC
EXTERN boom_module_index:PROC
EXTERN boom_module_load:PROC
EXTERN boom_module_objects_value:PROC
EXTERN boom_object_new:PROC
EXTERN boom_string_view:PROC
PUBLIC boom_layer_intrinsic
.code
; Caller has validated module/layer descriptors. Layer RCX,pool RDX,context R8.
; Return layer id or -1, requiring its exact tag and canonical rooted identity.
layer_value PROC
    test rcx, rcx
    jz layer_value_null
    mov rax, QWORD PTR [rdx+24]
    cmp QWORD PTR [rcx-8], rax
    jne layer_value_invalid
    cmp QWORD PTR [rcx-16], 8
    jne layer_value_invalid
    cmp DWORD PTR [rcx-20], 0
    jne layer_value_invalid
    mov eax, DWORD PTR [rcx-24]
    and eax, 0FFFFFFFDh
    cmp eax, 0B00B0001h
    jne layer_value_invalid
    mov rax, QWORD PTR [rcx]
    cmp rax, 1
    ja layer_value_invalid
    mov r10, QWORD PTR [rdx+16]
    cmp QWORD PTR [r10+rax*8], rcx
    jne layer_value_invalid
    mov r11, QWORD PTR [rdx+40]
    mov r11, QWORD PTR [r11]
    cmp QWORD PTR [rdx+48], r11
    jne layer_value_invalid
    ret
layer_value_null:
    mov DWORD PTR [r8], 4
    mov rax, -1
    ret
layer_value_invalid:
    mov DWORD PTR [r8], 7
    mov rax, -1
    ret
layer_value ENDP

; (Context16 RCX,argv RDX,module pool R8,operation R9D)->guest value RAX.
; 3 Module.getLayer,4 Layer.boot,5 Layer.empty,6 Layer.findModule raw Module.
boom_layer_intrinsic PROC FRAME
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
    sub rsp, 32
    .allocstack 32
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov rdi, r8
    mov r12d, r9d
    cmp DWORD PTR [rbx], 0
    jne layer_zero
    cmp r12d, 3
    jb layer_invalid
    cmp r12d, 6
    ja layer_invalid
    mov rdx, rdi
    call boom_module_pool_valid
    test eax, eax
    jz layer_invalid
    mov eax, DWORD PTR [rdi+4]
    sub eax, 2
    cmp eax, 1
    ja layer_invalid
    mov r13, QWORD PTR [rdi+88]
    mov r13, QWORD PTR [r13]
    test r13, r13
    jz layer_invalid
    cmp DWORD PTR [r13], 048454150h
    jne layer_invalid
    cmp DWORD PTR [r13+4], 1
    jne layer_invalid
    mov r14, QWORD PTR [rdi+80]
    test r14, r14
    jnz layer_pool_present
    cmp r12d, 3
    jne layer_invalid
    cmp DWORD PTR [rdi+4], 3
    jne layer_invalid
    test rsi, rsi
    jz layer_invalid
    jmp layer_of_physical_module
layer_pool_present:
    cmp QWORD PTR [r14+48], 0
    je layer_heap_ok
    cmp QWORD PTR [r14+48], r13
    jne layer_invalid
layer_heap_ok:
    cmp r12d, 6
    je layer_find
    cmp r12d, 3
    je layer_of_module
    sub r12d, 4
    xor r12d, 1 ; op4 -> boot1, op5 -> empty0
    jmp layer_load
layer_of_module:
    test rsi, rsi
    jz layer_invalid
    cmp DWORD PTR [rdi+4], 3
    je layer_of_physical_module
    mov rcx, rbx
    mov rdx, QWORD PTR [rsi]
    mov r8, rdi
    call boom_module_index
    cmp rax, -1
    je layer_zero
    mov r10, QWORD PTR [rdi+24]
    mov eax, DWORD PTR [r10+rax*8+4]
    cmp eax, 1
    ja layer_invalid
    test eax, eax
    jz layer_zero ; unnamed modules are not in a layer
    mov r12d, 1
    jmp layer_load
layer_of_physical_module:
    mov rcx, QWORD PTR [rsi]
    mov rdx, rdi
    mov r8, rbx
    call boom_module_objects_value
    test rax, rax
    jz layer_zero
    mov ecx, DWORD PTR [rdi+120]
    mov rsi, QWORD PTR [rax+rcx]
    test rsi, rsi
    jz layer_zero
    test r14, r14
    jz layer_invalid
    mov rcx, rsi
    mov rdx, r14
    mov r8, rbx
    call layer_value
    cmp rax, -1
    je layer_zero
    mov rax, rsi
    jmp layer_done
layer_load:
    mov rsi, QWORD PTR [r14+16]
    lea rsi, [rsi+r12*8]
    mov rax, QWORD PTR [rsi]
    test rax, rax
    jnz layer_done
layer_lock:
    mov eax, 1
    xchg DWORD PTR [r14+8], eax
    test eax, eax
    jz layer_owned
layer_spin:
    pause
    cmp DWORD PTR [r14+8], 0
    jne layer_spin
    jmp layer_lock
layer_owned:
    mov rax, QWORD PTR [r14+48]
    test rax, rax
    jz layer_bind
    cmp rax, r13
    jne layer_wrong_heap
    jmp layer_bound
layer_bind:
    mov QWORD PTR [r14+48], r13
layer_bound:
    mov rax, QWORD PTR [rsi]
    test rax, rax
    jnz layer_unlock
    mov rcx, r13
    mov rdx, QWORD PTR [r14+24]
    mov r8, rbx
    call boom_object_new
    test rax, rax
    jz layer_unlock
    mov QWORD PTR [rax], r12
    mov QWORD PTR [rsi], rax
layer_unlock:
    mov DWORD PTR [r14+8], 0
    jmp layer_done
layer_wrong_heap:
    mov DWORD PTR [r14+8], 0
    jmp layer_invalid
layer_find:
    test rsi, rsi
    jz layer_invalid
    mov rcx, QWORD PTR [rsi]
    mov rdx, r14
    mov r8, rbx
    call layer_value
    cmp rax, -1
    je layer_zero
    mov r12d, eax
    mov r10, QWORD PTR [rdi+40]
    cmp DWORD PTR [r10], 053545250h
    jne layer_invalid
    mov eax, DWORD PTR [r10+4]
    sub eax, 2
    cmp eax, 1
    ja layer_invalid
    cmp DWORD PTR [r10+16], 65536
    ja layer_invalid
    cmp QWORD PTR [r10+32], 0
    je layer_invalid
    mov rcx, QWORD PTR [rsi+8]
    mov rdx, QWORD PTR [r10+40]
    mov r8, rbx
    call boom_string_view
    test rax, rax
    jz layer_zero
    mov r14, rax ; immutable guest UTF16
    mov r15d, edx
    test r12d, r12d
    jz layer_zero ; even empty layer must reject a null name
    xor r13d, r13d
layer_find_next:
    cmp r13d, DWORD PTR [rdi+12]
    jae layer_zero
    mov r10, QWORD PTR [rdi+24]
    mov eax, DWORD PTR [r10+r13*8+4]
    cmp eax, 1
    ja layer_invalid
    test eax, eax
    jz layer_find_skip
    mov eax, DWORD PTR [r10+r13*8]
    mov r10, QWORD PTR [rdi+40]
    cmp eax, DWORD PTR [r10+16]
    jae layer_invalid
    shl rax, 4
    add rax, QWORD PTR [r10+32]
    cmp DWORD PTR [rax+12], 0
    jne layer_invalid
    cmp DWORD PTR [rax+8], r15d
    jne layer_find_skip
    mov r10, QWORD PTR [rax]
    test r10, r10
    jz layer_invalid
    xor r11d, r11d
layer_find_compare:
    cmp r11d, r15d
    jae layer_found
    movzx eax, WORD PTR [r10+r11*2]
    cmp ax, WORD PTR [r14+r11*2]
    jne layer_find_skip
    inc r11d
    jmp layer_find_compare
layer_find_skip:
    inc r13d
    jmp layer_find_next
layer_found:
    mov rcx, rbx
    mov rdx, rdi
    mov r8d, r13d
    call boom_module_load
    jmp layer_done
layer_invalid:
    mov DWORD PTR [rbx], 7
layer_zero:
    xor eax, eax
layer_done:
    add rsp, 32
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_layer_intrinsic ENDP
END
