; Source-verified String.toCharArray: fresh char[], including empty strings.
; Copies UTF16 code units without encoding conversion. No automatic collection.
option casemap:none
EXTERN boom_string_view:PROC
EXTERN boom_heap_alloc:PROC
PUBLIC boom_string_to_chars
.code
; (Context16 RCX, argv{String} RDX, StringPool3 R8) -> char[] / NULL.
boom_string_to_chars PROC FRAME
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
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov r12,r8
    test rbx,rbx
    jz chars_error
    cmp DWORD PTR [rbx],0
    jne chars_error
    test rsi,rsi
    jz chars_bad
    test r12,r12
    jz chars_bad
    cmp DWORD PTR [r12],053545250h
    jne chars_bad
    cmp DWORD PTR [r12+4],3
    jne chars_bad
    cmp DWORD PTR [r12+16],65536
    ja chars_bad
    cmp QWORD PTR [r12+64],0
    je chars_bad
    cmp QWORD PTR [rsi],0
    je chars_null
    mov r13,QWORD PTR [r12+48]
    test r13,r13
    jz chars_bad
    cmp DWORD PTR [r13],048454150h
    jne chars_bad
    cmp DWORD PTR [r13+4],1
    jne chars_bad
    mov rax,QWORD PTR [r13+16]
    test rax,rax
    jz chars_bad
    cmp rax,040000000h
    ja chars_bad
    lea r10,[r13+128]
    add rax,r10
    jc chars_bad
    cmp rax,QWORD PTR [r13+24]
    jne chars_bad
    mov rcx,QWORD PTR [rsi]
    call chars_owned
    test eax,eax
    jz chars_bad
    cmp QWORD PTR [rcx-16],16
    jne chars_bad
    mov rcx,QWORD PTR [rcx]
    call chars_owned
    test eax,eax
    jz chars_bad
    mov rcx,QWORD PTR [rsi]
    mov rdx,QWORD PTR [r12+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne chars_error
    mov rsi,rax
    mov r14d,edx
    mov rcx,r13
    shl rdx,1
    xor r8d,r8d
    mov r9d,261
    call boom_heap_alloc
    test rax,rax
    jz chars_oom
    mov rdi,rax
    mov rdx,rax
    mov ecx,r14d
    rep movsw
    mov rax,rdx
    jmp chars_done
chars_null:
    mov DWORD PTR [rbx],4
    jmp chars_error
chars_oom:
    mov DWORD PTR [rbx],3
    jmp chars_error
chars_bad:
    mov DWORD PTR [rbx],7
chars_error:
    xor eax,eax
chars_done:
    add rsp,40
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_to_chars ENDP
; Bound both header and complete block before string_view dereferences them.
; A zero-byte array payload may equal the arena end.
chars_owned PROC
    lea r10,[r13+160]
    cmp rcx,r10
    jb chars_not_owned
    mov r11,QWORD PTR [r13+24]
    cmp rcx,r11
    ja chars_not_owned
    test cl,15
    jnz chars_not_owned
    mov eax,DWORD PTR [rcx-24]
    and eax,0FFFFFFFDh
    cmp eax,0B00B0001h
    jne chars_not_owned
    mov rax,QWORD PTR [rcx-32]
    cmp rax,32
    jb chars_not_owned
    test al,15
    jnz chars_not_owned
    sub rax,32
    cmp QWORD PTR [rcx-16],rax
    ja chars_not_owned
    add rax,rcx
    jc chars_not_owned
    cmp rax,r11
    ja chars_not_owned
    mov eax,1
    ret
chars_not_owned:
    xor eax,eax
    ret
chars_owned ENDP
END
