; String.join runtime ABI1. All callbacks enter compiled MASM dispatch sites.
; Plan88: magic0 abi4 kind8 reserved12 pool16 typeMap24 CharSequenceType32,
; toString40 iterator48 hasNext56 next64 StringArrayTag72 nullLiteral80 reserved84.
; Kind0 CharSequence[], kind1 Iterable. Return RAX String, EDX=1 only when
; an existing callback exception must retain its Java method/PC provenance.
; Native frame references are live until return; collection is quiescent only.
option casemap:none
EXTERN boom_heap_alloc:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_string_load:PROC
EXTERN boom_string_view:PROC
EXTERN boom_string_allocate:PROC
EXTERN boom_string_replace_sequence:PROC
PUBLIC boom_string_join
.code
boom_string_join PROC FRAME
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
    sub rsp, 160
    .allocstack 160
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov r12, r8
    mov r13, r9
    mov DWORD PTR [rsp+128], 0
    test r12, r12
    jz join_invalid
    cmp DWORD PTR [r12], 048454150h
    jne join_invalid
    cmp DWORD PTR [r12+4], 1
    jne join_invalid
    test r13, r13
    jz join_invalid
    cmp DWORD PTR [r13], 04A4F494Eh
    jne join_invalid
    cmp DWORD PTR [r13+4], 1
    jne join_invalid
    cmp DWORD PTR [r13+8], 2
    je join_replace_sequence
    cmp DWORD PTR [r13+8], 1
    ja join_invalid
    cmp DWORD PTR [r13+12], 0
    jne join_invalid
    cmp DWORD PTR [r13+84], 0
    jne join_invalid
    mov rax, QWORD PTR [r13+16]
    test rax, rax
    jz join_invalid
    cmp DWORD PTR [rax], 053545250h
    jne join_invalid
    cmp DWORD PTR [rax+4], 3
    jne join_invalid
    mov ecx, DWORD PTR [r13+80]
    cmp ecx, DWORD PTR [rax+16]
    jae join_invalid
    mov rcx, QWORD PTR [rax+48]
    test rcx, rcx
    jz join_heap_ok
    cmp rcx, r12
    jne join_invalid
join_heap_ok:
    cmp QWORD PTR [r13+24], 0
    je join_invalid
    mov rcx, QWORD PTR [r13+32]
    test rcx, rcx
    jz join_invalid
    cmp DWORD PTR [rcx], 054595045h
    jne join_invalid
    cmp DWORD PTR [rcx+4], 1
    jne join_invalid
    cmp DWORD PTR [rcx+8], 2
    jne join_invalid
    cmp QWORD PTR [r13+40], 0
    je join_invalid
    mov rcx, QWORD PTR [r13+72]
    test rcx, rcx
    jz join_invalid
    cmp DWORD PTR [rcx], 052454641h
    jne join_invalid
    cmp DWORD PTR [rcx+4], 1
    jne join_invalid
    mov rcx, QWORD PTR [rcx+8]
    cmp rcx, QWORD PTR [rax+40]
    jne join_invalid
    cmp DWORD PTR [r13+8], 0
    je join_plan_ok
    cmp QWORD PTR [r13+48], 0
    je join_invalid
    cmp QWORD PTR [r13+56], 0
    je join_invalid
    cmp QWORD PTR [r13+64], 0
    je join_invalid
join_plan_ok:
    mov rax, QWORD PTR [rsi]
    mov rdi, QWORD PTR [rsi+8]
    test rax, rax
    jz join_null
    ; Iterable checks both arguments before delimiter.toString; array checks
    ; its array only after that callback. These orders are observably different.
    cmp DWORD PTR [r13+8], 0
    je join_delimiter
    test rdi, rdi
    jz join_null
join_delimiter:
    mov QWORD PTR [rsp+32], rax
    mov rcx, rbx
    lea rdx, [rsp+32]
    call QWORD PTR [r13+40]
    cmp DWORD PTR [rbx], 0
    jne join_callback_failed
    mov QWORD PTR [rsp+40], rax
    xor r15d, r15d
    cmp DWORD PTR [r13+8], 0
    jne join_iterable_prepare
    test rdi, rdi
    jz join_null
    mov rcx, rdi
    mov rdx, QWORD PTR [r13+24]
    mov r8, rbx
    call boom_runtime_type
    test rax, rax
    jz join_failed
    cmp DWORD PTR [rax+8], 3
    jne join_invalid
    mov rcx, QWORD PTR [rax+16]
    mov rdx, QWORD PTR [r13+32]
    call boom_type_assignable
    test eax, eax
    jz join_invalid
    mov eax, DWORD PTR [rdi-20]
    mov DWORD PTR [rsp+60], eax
    mov DWORD PTR [rsp+56], eax
    jmp join_allocate_vector
join_iterable_prepare:
    mov DWORD PTR [rsp+56], 8
join_allocate_vector:
    mov rcx, r12
    mov r8d, DWORD PTR [rsp+56]
    lea rdx, [r8*8]
    mov r9, QWORD PTR [r13+72]
    call boom_heap_alloc
    test rax, rax
    jz join_oom
    mov r14, rax
    cmp DWORD PTR [r13+8], 0
    je join_next_array
    mov QWORD PTR [rsp+32], rdi
    mov rcx, rbx
    lea rdx, [rsp+32]
    call QWORD PTR [r13+48]
    cmp DWORD PTR [rbx], 0
    jne join_callback_failed
    test rax, rax
    jz join_null
    mov QWORD PTR [rsp+48], rax
join_next_iterable:
    mov rax, QWORD PTR [rsp+48]
    mov QWORD PTR [rsp+32], rax
    mov rcx, rbx
    lea rdx, [rsp+32]
    call QWORD PTR [r13+56]
    cmp DWORD PTR [rbx], 0
    jne join_callback_failed
    test eax, eax
    jz join_collected
    mov rax, QWORD PTR [rsp+48]
    mov QWORD PTR [rsp+32], rax
    mov rcx, rbx
    lea rdx, [rsp+32]
    call QWORD PTR [r13+64]
    cmp DWORD PTR [rbx], 0
    jne join_callback_failed
    jmp join_element
join_next_array:
    cmp r15d, DWORD PTR [rsp+60]
    jae join_collected
    mov rax, QWORD PTR [rdi+r15*8]
join_element:
    mov QWORD PTR [rsp+112], rax
    test rax, rax
    jz join_element_typed
    mov rcx, rax
    mov rdx, QWORD PTR [r13+24]
    mov r8, rbx
    call boom_runtime_type
    test rax, rax
    jz join_failed
    mov rcx, rax
    mov rdx, QWORD PTR [r13+32]
    call boom_type_assignable
    test eax, eax
    jz join_cast
join_element_typed:
    cmp r15d, DWORD PTR [rsp+56]
    jb join_element_convert
    mov eax, DWORD PTR [rsp+56]
    test eax, eax
    jz join_oom
    shl eax, 1
    test eax, eax
    jle join_oom
    mov DWORD PTR [rsp+56], eax
    mov r8d, eax
    lea rdx, [r8*8]
    mov rcx, r12
    mov r9, QWORD PTR [r13+72]
    call boom_heap_alloc
    test rax, rax
    jz join_oom
    xor ecx, ecx
join_grow_copy:
    cmp rcx, r15
    jae join_grow_done
    mov rdx, QWORD PTR [r14+rcx*8]
    mov QWORD PTR [rax+rcx*8], rdx
    inc rcx
    jmp join_grow_copy
join_grow_done:
    mov r14, rax
join_element_convert:
    mov rax, QWORD PTR [rsp+112]
    test rax, rax
    jz join_null_element
    mov QWORD PTR [rsp+32], rax
    mov rcx, rbx
    lea rdx, [rsp+32]
    call QWORD PTR [r13+40]
    cmp DWORD PTR [rbx], 0
    jne join_callback_failed
    jmp join_append
join_null_element:
    mov rcx, r12
    mov rdx, QWORD PTR [r13+16]
    mov r8d, DWORD PTR [r13+80]
    mov r9, rbx
    call boom_string_load
    test rax, rax
    jz join_failed
join_append:
    ; A toString() result may be null. JDK detects it only after iteration;
    ; do not skip subsequent iterator/toString side effects by checking it here.
    mov QWORD PTR [r14+r15*8], rax
    inc r15
    cmp DWORD PTR [r13+8], 0
    je join_next_array
    jmp join_next_iterable
join_collected:
    mov QWORD PTR [rsp+88], 0
    mov QWORD PTR [rsp+96], 0
    mov QWORD PTR [rsp+104], 0
    cmp r15, 1
    jbe join_count_elements
    mov rcx, QWORD PTR [rsp+40]
    mov rdx, QWORD PTR [r13+16]
    mov rdx, QWORD PTR [rdx+40]
    mov r8, rbx
    call boom_string_view
    test rax, rax
    jz join_failed
    mov QWORD PTR [rsp+96], rax
    mov QWORD PTR [rsp+104], rdx
    lea rax, [r15-1]
    imul rax, rdx
    mov QWORD PTR [rsp+88], rax
join_count_elements:
    mov QWORD PTR [rsp+120], 0
join_count_next:
    mov rax, QWORD PTR [rsp+120]
    cmp rax, r15
    jae join_count_done
    mov rcx, QWORD PTR [r14+rax*8]
    mov rdx, QWORD PTR [r13+16]
    mov rdx, QWORD PTR [rdx+40]
    mov r8, rbx
    call boom_string_view
    test rax, rax
    jz join_failed
    add QWORD PTR [rsp+88], rdx
    inc QWORD PTR [rsp+120]
    jmp join_count_next
join_count_done:
    cmp QWORD PTR [rsp+88], 03FFFFFFFh
    ja join_oom
    mov rcx, r12
    mov rdx, QWORD PTR [r13+16]
    mov r8d, DWORD PTR [rsp+88]
    mov r9, rbx
    call boom_string_allocate
    test rax, rax
    jz join_failed
    mov QWORD PTR [rsp+72], rax
    mov rdi, QWORD PTR [rax]
    mov QWORD PTR [rsp+120], 0
    cld
join_copy_next:
    mov rax, QWORD PTR [rsp+120]
    cmp rax, r15
    jae join_complete
    test rax, rax
    jz join_copy_element
    mov rsi, QWORD PTR [rsp+96]
    mov rcx, QWORD PTR [rsp+104]
    rep movsw
join_copy_element:
    mov rax, QWORD PTR [rsp+120]
    mov rcx, QWORD PTR [r14+rax*8]
    mov rdx, QWORD PTR [r13+16]
    mov rdx, QWORD PTR [rdx+40]
    mov r8, rbx
    call boom_string_view
    test rax, rax
    jz join_failed
    mov rsi, rax
    mov ecx, edx
    rep movsw
    inc QWORD PTR [rsp+120]
    jmp join_copy_next
join_complete:
    mov rax, QWORD PTR [rsp+72]
    jmp join_exit
join_null:
    mov DWORD PTR [rbx], 4
    jmp join_failed
join_cast:
    mov DWORD PTR [rbx], 12
    jmp join_failed
join_oom:
    mov DWORD PTR [rbx], 3
    jmp join_failed
join_invalid:
    mov DWORD PTR [rbx], 7
    jmp join_failed
join_callback_failed:
    mov DWORD PTR [rsp+128], edx
join_failed:
    xor eax, eax
join_exit:
    mov edx, DWORD PTR [rsp+128]
    add rsp, 160
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
join_replace_sequence:
    mov rcx,rbx
    mov rdx,rsi
    mov r8,r12
    mov r9,r13
    add rsp,160
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    jmp boom_string_replace_sequence
boom_string_join ENDP
END
