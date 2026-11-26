; Closed classpath module identity services, entirely MASM.
; Pool80 ABI1: magic0 abi4 lock8 count12 roots16 rows24 layout32 strings40
; boundHeap48 mirrors56 typeCount64 reserved68 membershipDWORDs72.
; ABI2 extends to96: layerPool80 heapPointerCell88. ABI1 stays80.
; Row8: nameLiteral DWORD0 (-1 for unnamed), named DWORD4 (0/1).
; Guest payload8: moduleId QWORD0, no guest references. Strong pool roots.
; Only java.base and per-defining-loader unnamed modules currently have providers.
option casemap:none
EXTERN boom_mirror_typeid:PROC
EXTERN boom_object_new:PROC
EXTERN boom_string_load:PROC
EXTERN boom_module_objects_pool_valid:PROC
EXTERN boom_module_objects_index:PROC
EXTERN boom_module_objects_load:PROC
EXTERN boom_module_objects_intrinsic:PROC
PUBLIC boom_module_intrinsic
PUBLIC boom_module_pool_valid
PUBLIC boom_module_load
PUBLIC boom_module_index
.code
; pool RDX -> EAX bool; preserve argument registers except RAX/R10/R11.
module_pool_valid PROC
    test rdx,rdx
    jz module_pool_no
    cmp DWORD PTR [rdx+4],3
    je boom_module_objects_pool_valid
    test rdx, rdx
    jz module_pool_no
    cmp DWORD PTR [rdx], 04D4F4455h
    jne module_pool_no
    cmp DWORD PTR [rdx+4], 1
    je module_pool_version_ok
    cmp DWORD PTR [rdx+4], 2
    jne module_pool_no
    mov r10, QWORD PTR [rdx+80]
    test r10, r10
    jz module_pool_no
    cmp DWORD PTR [r10], 04C415952h
    jne module_pool_no
    cmp DWORD PTR [r10+4], 1
    jne module_pool_no
    cmp DWORD PTR [r10+12], 2
    jne module_pool_no
    cmp QWORD PTR [r10+16], 0
    je module_pool_no
    cmp QWORD PTR [r10+32], rdx
    jne module_pool_no
    cmp QWORD PTR [r10+56], 0
    jne module_pool_no
    mov r11, QWORD PTR [rdx+88]
    test r11, r11
    jz module_pool_no
    cmp QWORD PTR [r10+40], r11
    jne module_pool_no
    mov r10, QWORD PTR [r10+24]
    test r10, r10
    jz module_pool_no
    cmp r10, QWORD PTR [rdx+32]
    je module_pool_no
    cmp DWORD PTR [r10], 04F424A43h
    jne module_pool_no
    cmp DWORD PTR [r10+4], 1
    jne module_pool_no
    cmp QWORD PTR [r10+8], 8
    jne module_pool_no
    cmp DWORD PTR [r10+16], 0
    jne module_pool_no
    cmp DWORD PTR [r10+20], 1
    jne module_pool_no
module_pool_version_ok:
    mov eax, DWORD PTR [rdx+12]
    dec eax
    cmp eax, 1023
    ja module_pool_no
    cmp DWORD PTR [rdx+68], 0
    jne module_pool_no
    cmp QWORD PTR [rdx+16], 0
    je module_pool_no
    cmp QWORD PTR [rdx+24], 0
    je module_pool_no
    cmp QWORD PTR [rdx+40], 0
    je module_pool_no
    cmp QWORD PTR [rdx+72], 0
    je module_pool_no
    mov r10, QWORD PTR [rdx+32]
    test r10, r10
    jz module_pool_no
    cmp DWORD PTR [r10], 04F424A43h
    jne module_pool_no
    cmp DWORD PTR [r10+4], 1
    jne module_pool_no
    cmp QWORD PTR [r10+8], 8
    jne module_pool_no
    cmp DWORD PTR [r10+16], 0
    jne module_pool_no
    cmp DWORD PTR [r10+20], 1
    jne module_pool_no
    mov r10, QWORD PTR [rdx+56]
    test r10, r10
    jz module_pool_no
    cmp DWORD PTR [r10], 04D495252h
    jne module_pool_no
    mov eax, DWORD PTR [r10+4]
    dec eax
    cmp eax, 1
    ja module_pool_no
    mov eax, DWORD PTR [rdx+64]
    dec eax
    cmp eax, 16383
    ja module_pool_no
    inc eax
    cmp eax, DWORD PTR [r10+12]
    jne module_pool_no
    mov eax, 1
    ret
module_pool_no:
    xor eax, eax
    ret
module_pool_valid ENDP
boom_module_pool_valid PROC
    jmp module_pool_valid
boom_module_pool_valid ENDP

; pool RCX -> valid bound heap or NULL. Preserves RCX/RDX/R8/R9.
module_heap PROC
    mov r10, QWORD PTR [rcx+56]
    mov rax, QWORD PTR [r10+48]
    cmp DWORD PTR [rcx+4], 2
    jne module_heap_check
    mov r11, QWORD PTR [rcx+88]
    mov r11, QWORD PTR [r11]
    test rax, rax
    jz module_heap_cell
    cmp rax, r11
    jne module_heap_no
module_heap_cell:
    mov rax, r11
module_heap_check:
    test rax, rax
    jz module_heap_no
    cmp DWORD PTR [rax], 048454150h
    jne module_heap_no
    cmp DWORD PTR [rax+4], 1
    jne module_heap_no
    ret
module_heap_no:
    xor eax, eax
    ret
module_heap ENDP


; module payload RCX,pool RDX,context R8 -> row or NULL. Trusted native ABI.
module_value PROC
    test rcx, rcx
    jz module_value_null
    cmp QWORD PTR [rdx+48], 0
    je module_value_invalid
    cmp DWORD PTR [rdx+4], 2
    jne module_value_legacy_heap
    mov rax, QWORD PTR [rdx+88]
    mov rax, QWORD PTR [rax]
    cmp rax, QWORD PTR [rdx+48]
    jne module_value_invalid
    mov r10, QWORD PTR [rdx+56]
    mov r10, QWORD PTR [r10+48]
    test r10, r10
    jz module_value_heap_ok
    cmp rax, r10
    jne module_value_invalid
    jmp module_value_heap_ok
module_value_legacy_heap:
    mov rax, QWORD PTR [rdx+56]
    mov rax, QWORD PTR [rax+48]
    cmp rax, QWORD PTR [rdx+48]
    jne module_value_invalid
module_value_heap_ok:
    mov rax, QWORD PTR [rdx+32]
    cmp QWORD PTR [rcx-8], rax
    jne module_value_invalid
    cmp QWORD PTR [rcx-16], 8
    jne module_value_invalid
    cmp DWORD PTR [rcx-20], 0
    jne module_value_invalid
    mov eax, DWORD PTR [rcx-24]
    and eax, 0FFFFFFFDh
    cmp eax, 0B00B0001h
    jne module_value_invalid
    mov r10, QWORD PTR [rcx]
    mov r11d, DWORD PTR [rdx+12]
    cmp r10, r11
    jae module_value_invalid
    mov rax, QWORD PTR [rdx+16]
    cmp QWORD PTR [rax+r10*8], rcx
    jne module_value_invalid
    mov rax, QWORD PTR [rdx+24]
    lea rax, [rax+r10*8]
    ret
module_value_null:
    mov DWORD PTR [r8], 4
    xor eax, eax
    ret
module_value_invalid:
    mov DWORD PTR [r8], 7
    xor eax, eax
    ret
module_value ENDP

; intrinsic(Context16 RCX,argv RDX,pool R8,op R9D)->RAX
; op0 Class.getModule; op1 Module.getName; op2 Module.isNamed.
boom_module_intrinsic PROC FRAME
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
    sub rsp, 32
    .allocstack 32
    .endprolog
    test r8,r8
    jz module_intrinsic_legacy
    cmp DWORD PTR [r8+4],3
    jne module_intrinsic_legacy
    add rsp,32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    jmp boom_module_objects_intrinsic
module_intrinsic_legacy:
    mov rbx, rcx
    mov rsi, rdx
    mov rdi, r8
    mov r12d, r9d
    cmp r12d, 2
    ja module_invalid
    test rsi, rsi
    jz module_invalid
    mov rdx, rdi
    call module_pool_valid
    test eax, eax
    jz module_invalid
    test r12d, r12d
    jz module_from_class
    mov rcx, QWORD PTR [rsi]
    mov rdx, rdi
    mov r8, rbx
    call module_value
    test rax, rax
    jz module_done
    mov r13, rax
    mov eax, DWORD PTR [r13+4]
    cmp eax, 1
    ja module_invalid
    test eax, eax
    jnz module_named_row
    cmp DWORD PTR [r13], -1
    jne module_invalid
    xor eax, eax ; unnamed getName null / isNamed false
    jmp module_done
module_named_row:
    cmp DWORD PTR [r13], -1
    je module_invalid
    cmp r12d, 2
    je module_true
    mov rcx, QWORD PTR [rdi+48]
    mov rdx, QWORD PTR [rdi+40]
    mov r8d, DWORD PTR [r13]
    mov r9, rbx
    call boom_string_load
    jmp module_done
module_true:
    mov eax, 1
    jmp module_done
module_from_class:
    mov rcx, rbx
    mov rdx, QWORD PTR [rsi]
    mov r8, QWORD PTR [rdi+56]
    call boom_mirror_typeid
    cmp rax, -1
    je module_done_zero
    mov r10d, DWORD PTR [rdi+64]
    cmp rax, r10
    jae module_invalid
    mov r10, QWORD PTR [rdi+72]
    mov r13d, DWORD PTR [r10+rax*4]
    mov rcx, rbx
    mov rdx, rdi
    mov r8d, r13d
    call boom_module_load
    jmp module_done
module_invalid:
    mov DWORD PTR [rbx], 7
module_done_zero:
    xor eax, eax
module_done:
    add rsp, 32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_module_intrinsic ENDP

; index(Context16 RCX,Module RDX,pool R8)->id or -1 with error.
boom_module_index PROC FRAME
    sub rsp, 56
    .allocstack 56
    .endprolog
    test r8,r8
    jz module_index_legacy
    cmp DWORD PTR [r8+4],3
    jne module_index_legacy
    add rsp,56
    jmp boom_module_objects_index
module_index_legacy:
    mov QWORD PTR [rsp+32], rcx
    mov QWORD PTR [rsp+40], rdx
    mov QWORD PTR [rsp+48], r8
    mov rdx, r8
    call module_pool_valid
    test eax, eax
    jz module_index_invalid
    mov rcx, QWORD PTR [rsp+40]
    mov rdx, QWORD PTR [rsp+48]
    mov r8, QWORD PTR [rsp+32]
    call module_value
    test rax, rax
    jz module_index_fail
    mov rax, QWORD PTR [rsp+40]
    mov rax, QWORD PTR [rax]
    jmp module_index_done
module_index_invalid:
    mov r8, QWORD PTR [rsp+32]
    mov DWORD PTR [r8], 7
module_index_fail:
    mov rax, -1
module_index_done:
    add rsp, 56
    ret
boom_module_index ENDP

; load(Context16 RCX,pool RDX,module id R8D)->canonical Module or NULL.
boom_module_load PROC FRAME
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
    sub rsp, 32
    .allocstack 32
    .endprolog
    test rdx,rdx
    jz module_load_legacy
    cmp DWORD PTR [rdx+4],3
    jne module_load_legacy
    add rsp,32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    jmp boom_module_objects_load
module_load_legacy:
    mov rbx, rcx
    mov rdi, rdx
    mov r13d, r8d
    call module_pool_valid
    test eax, eax
    jz module_load_invalid
    cmp r13d, DWORD PTR [rdi+12]
    jae module_load_invalid
    mov r10, QWORD PTR [rdi+24]
    mov eax, DWORD PTR [r10+r13*8+4]
    cmp eax, 1
    ja module_load_invalid
    test eax, eax
    jz module_load_unnamed
    cmp DWORD PTR [r10+r13*8], -1
    je module_load_invalid
    jmp module_load_row_ok
module_load_unnamed:
    cmp DWORD PTR [r10+r13*8], -1
    jne module_load_invalid
module_load_row_ok:
    mov rcx, rdi
    call module_heap
    test rax, rax
    jz module_load_invalid
    mov r12, rax
    cmp QWORD PTR [rdi+48], 0
    je module_load_lock
    cmp QWORD PTR [rdi+48], r12
    jne module_load_invalid
    mov rsi, QWORD PTR [rdi+16]
    mov rax, QWORD PTR [rsi+r13*8]
    test rax, rax
    jnz module_load_done
module_load_lock:
    mov eax, 1
    xchg DWORD PTR [rdi+8], eax
    test eax, eax
    jz module_load_owned
module_load_spin:
    pause
    cmp DWORD PTR [rdi+8], 0
    jne module_load_spin
    jmp module_load_lock
module_load_owned:
    mov rax, QWORD PTR [rdi+48]
    test rax, rax
    jz module_load_bind
    cmp rax, r12
    jne module_load_wrong_heap
    jmp module_load_bound
module_load_bind:
    mov QWORD PTR [rdi+48], r12
module_load_bound:
    mov rsi, QWORD PTR [rdi+16]
    lea rsi, [rsi+r13*8]
    mov rax, QWORD PTR [rsi]
    test rax, rax
    jnz module_load_unlock
    mov rcx, r12
    mov rdx, QWORD PTR [rdi+32]
    mov r8, rbx
    call boom_object_new
    test rax, rax
    jz module_load_unlock
    mov QWORD PTR [rax], r13
    mov QWORD PTR [rsi], rax
module_load_unlock:
    mov DWORD PTR [rdi+8], 0
    jmp module_load_done
module_load_wrong_heap:
    mov DWORD PTR [rdi+8], 0
module_load_invalid:
    mov DWORD PTR [rbx], 7
    xor eax, eax
module_load_done:
    add rsp, 32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_module_load ENDP
END
