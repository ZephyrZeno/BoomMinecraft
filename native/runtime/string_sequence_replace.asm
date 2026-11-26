; String.replace(CharSequence,CharSequence), VM UTF16 boundary, MASM only.
; Same JOIN88/1 descriptor, kind2. toString callback40 executes actual AOT Java;
; literal80 is reserved/validated. Other callback slots must be zero.
; (ctx RCX, argv{String,target,replacement} RDX, heap R8, plan R9).
; EDX1 only preserves an existing Java callback exception's provenance.
; Collection is quiescent and explicit while native frame references are live.
option casemap:none
EXTERN boom_heap_contains:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_string_view:PROC
EXTERN boom_string_allocate:PROC
PUBLIC boom_string_replace_sequence
.code
boom_string_replace_sequence PROC FRAME
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
    sub rsp,192
    .allocstack 192
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov r12,r8
    mov r13,r9
    mov DWORD PTR [rsp+124],0
    test rbx,rbx
    jz seq_zero
    cmp DWORD PTR [rbx],0
    jne seq_zero
    test rsi,rsi
    jz seq_bad
    test r12,r12
    jz seq_bad
    cmp DWORD PTR [r12],048454150h
    jne seq_bad
    cmp DWORD PTR [r12+4],1
    jne seq_bad
    test r13,r13
    jz seq_bad
    cmp DWORD PTR [r13],04A4F494Eh
    jne seq_bad
    cmp DWORD PTR [r13+4],1
    jne seq_bad
    cmp DWORD PTR [r13+8],2
    jne seq_bad
    cmp DWORD PTR [r13+12],0
    jne seq_bad
    cmp DWORD PTR [r13+84],0
    jne seq_bad
    mov rdi,QWORD PTR [r13+16]
    test rdi,rdi
    jz seq_bad
    cmp DWORD PTR [rdi],053545250h
    jne seq_bad
    cmp DWORD PTR [rdi+4],3
    jne seq_bad
    mov rax,QWORD PTR [rdi+48]
    test rax,rax
    jz seq_heap_ok
    cmp rax,r12
    jne seq_bad
seq_heap_ok:
    mov eax,DWORD PTR [r13+80]
    cmp eax,DWORD PTR [rdi+16]
    jae seq_bad
    cmp QWORD PTR [r13+24],0
    je seq_bad
    mov rax,QWORD PTR [r13+32]
    test rax,rax
    jz seq_bad
    cmp DWORD PTR [rax],054595045h
    jne seq_bad
    cmp DWORD PTR [rax+4],1
    jne seq_bad
    cmp DWORD PTR [rax+8],2
    jne seq_bad
    cmp QWORD PTR [r13+40],0
    je seq_bad
    cmp QWORD PTR [r13+48],0
    jne seq_bad
    cmp QWORD PTR [r13+56],0
    jne seq_bad
    cmp QWORD PTR [r13+64],0
    jne seq_bad
    ; Check the String receiver before either toString callback.
    mov rdx,QWORD PTR [rsi]
    mov QWORD PTR [rsp+64],rdx
    test rdx,rdx
    jz seq_null
    mov rcx,r12
    call boom_heap_contains
    test eax,eax
    jz seq_bad
    mov rcx,QWORD PTR [rsp+64]
    mov rdx,QWORD PTR [rdi+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne seq_zero
    mov QWORD PTR [rsp+88],rax
    mov DWORD PTR [rsp+112],edx
    ; target.toString(), then replacement.toString(). A null return from the
    ; first callback is checked only after the second callback has executed.
    mov r14d,1
seq_callback:
    mov rdx,QWORD PTR [rsi+r14*8]
    test rdx,rdx
    jz seq_null
    mov QWORD PTR [rsp+32],rdx
    mov rcx,r12
    call boom_heap_contains
    test eax,eax
    jz seq_bad
    mov rcx,QWORD PTR [rsp+32]
    mov rdx,QWORD PTR [r13+24]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne seq_zero
    mov rcx,rax
    mov rdx,QWORD PTR [r13+32]
    call boom_type_assignable
    test eax,eax
    jz seq_cast
    mov rcx,rbx
    lea rdx,[rsp+32]
    call QWORD PTR [r13+40]
    cmp DWORD PTR [rbx],0
    jne seq_callback_failed
    mov QWORD PTR [rsp+r14*8+64],rax
    inc r14d
    cmp r14d,3
    jb seq_callback
    mov r14d,1
seq_view_callback:
    mov rdx,QWORD PTR [rsp+r14*8+64]
    test rdx,rdx
    jz seq_null
    mov rcx,r12
    call boom_heap_contains
    test eax,eax
    jz seq_bad
    mov rcx,QWORD PTR [rsp+r14*8+64]
    mov rdx,QWORD PTR [rdi+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne seq_zero
    mov QWORD PTR [rsp+r14*8+88],rax
    mov DWORD PTR [rsp+r14*4+112],edx
    inc r14d
    cmp r14d,3
    jb seq_view_callback
    cmp DWORD PTR [rsp+116],1
    jne seq_count
    cmp DWORD PTR [rsp+120],1
    jne seq_count
    mov rax,QWORD PTR [rsp+96]
    movzx eax,WORD PTR [rax]
    mov rdx,QWORD PTR [rsp+104]
    cmp ax,WORD PTR [rdx]
    je seq_receiver
seq_count:
    mov QWORD PTR [rsp+128],0
    mov eax,DWORD PTR [rsp+116]
    test eax,eax
    jz seq_empty_target
    cmp eax,DWORD PTR [rsp+112]
    ja seq_receiver
    mov eax,DWORD PTR [rsp+112]
    sub eax,DWORD PTR [rsp+116]
    mov QWORD PTR [rsp+176],rax
    xor r15d,r15d
seq_count_loop:
    cmp r15,QWORD PTR [rsp+176]
    ja seq_count_done
    mov rcx,QWORD PTR [rsp+88]
    lea rcx,[rcx+r15*2]
    mov rdx,QWORD PTR [rsp+96]
    mov r8d,DWORD PTR [rsp+116]
    call seq_matches
    test eax,eax
    jz seq_count_next
    inc QWORD PTR [rsp+128]
    mov eax,DWORD PTR [rsp+116]
    add r15,rax
    jmp seq_count_loop
seq_count_next:
    inc r15
    jmp seq_count_loop
seq_count_done:
    cmp QWORD PTR [rsp+128],0
    je seq_receiver
    ; (sourceLength - count*targetLength) + count*replacementLength.
    mov eax,DWORD PTR [rsp+116]
    imul rax,QWORD PTR [rsp+128]
    mov ecx,DWORD PTR [rsp+112]
    sub rcx,rax
    mov eax,DWORD PTR [rsp+120]
    imul rax,QWORD PTR [rsp+128]
    add rax,rcx
    jmp seq_allocate
seq_empty_target:
    mov eax,DWORD PTR [rsp+112]
    inc rax
    mov ecx,DWORD PTR [rsp+120]
    imul rax,rcx
    mov ecx,DWORD PTR [rsp+112]
    add rax,rcx
seq_allocate:
    cmp rax,07FFFFFFFh
    ja seq_oom
    mov QWORD PTR [rsp+136],rax
    mov rcx,r12
    mov rdx,rdi
    mov r8d,eax
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz seq_zero
    mov QWORD PTR [rsp+144],rax
    mov r15,QWORD PTR [rax]
    mov QWORD PTR [rsp+160],0
seq_copy_loop:
    cmp DWORD PTR [rsp+116],0
    je seq_copy_replacement
    mov r14,QWORD PTR [rsp+160]
    cmp r14d,DWORD PTR [rsp+112]
    jae seq_copy_done
    cmp r14,QWORD PTR [rsp+176]
    ja seq_copy_char
    mov rcx,QWORD PTR [rsp+88]
    lea rcx,[rcx+r14*2]
    mov rdx,QWORD PTR [rsp+96]
    mov r8d,DWORD PTR [rsp+116]
    call seq_matches
    test eax,eax
    jz seq_copy_char
seq_copy_replacement:
    xor ecx,ecx
    mov rdx,QWORD PTR [rsp+104]
seq_copy_repl_loop:
    cmp ecx,DWORD PTR [rsp+120]
    jae seq_copy_advance
    movzx eax,WORD PTR [rdx+rcx*2]
    mov WORD PTR [r15],ax
    add r15,2
    inc ecx
    jmp seq_copy_repl_loop
seq_copy_advance:
    mov eax,DWORD PTR [rsp+116]
    test eax,eax
    jz seq_copy_empty_advance
    add QWORD PTR [rsp+160],rax
    jmp seq_copy_loop
seq_copy_empty_advance:
    mov r14,QWORD PTR [rsp+160]
    cmp r14d,DWORD PTR [rsp+112]
    jae seq_copy_done
seq_copy_char:
    mov rdx,QWORD PTR [rsp+88]
    movzx eax,WORD PTR [rdx+r14*2]
    mov WORD PTR [r15],ax
    add r15,2
    inc QWORD PTR [rsp+160]
    jmp seq_copy_loop
seq_copy_done:
    mov rax,QWORD PTR [rsp+144]
    jmp seq_done
seq_receiver:
    mov rax,QWORD PTR [rsp+64]
    jmp seq_done
seq_callback_failed:
    mov DWORD PTR [rsp+124],edx
    jmp seq_zero
seq_null:
    mov DWORD PTR [rbx],4
    jmp seq_zero
seq_cast:
    mov DWORD PTR [rbx],12
    jmp seq_zero
seq_bad:
    mov DWORD PTR [rbx],7
    jmp seq_zero
seq_oom:
    mov DWORD PTR [rbx],3
seq_zero:
    xor eax,eax
seq_done:
    mov edx,DWORD PTR [rsp+124]
    add rsp,192
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_replace_sequence ENDP
; Leaf comparison of length R8D UTF16 units at RCX/RDX. Bounds proven by caller.
seq_matches PROC
    xor r9d,r9d
seq_matches_loop:
    cmp r9d,r8d
    jae seq_matches_yes
    movzx eax,WORD PTR [rcx+r9*2]
    cmp ax,WORD PTR [rdx+r9*2]
    jne seq_matches_no
    inc r9d
    jmp seq_matches_loop
seq_matches_yes:
    mov eax,1
    ret
seq_matches_no:
    xor eax,eax
    ret
seq_matches ENDP
END
