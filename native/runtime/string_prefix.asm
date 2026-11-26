; Source-verified String.startsWith(String,int), VM UTF16 profile.
; Integer SSE2 compares read at most the requested range. Zero guest allocation.
option casemap:none
EXTERN boom_string_view:PROC
PUBLIC boom_string_starts_with
.code
; (Context16 RCX,argv{receiver,prefix,offset32} RDX,StringPool3 R8)->boolean.
boom_string_starts_with PROC FRAME
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
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    test rbx,rbx
    jz prefix_false
    cmp DWORD PTR [rbx],0
    jne prefix_false
    test rsi,rsi
    jz prefix_bad
    test rdi,rdi
    jz prefix_bad
    cmp DWORD PTR [rdi],053545250h
    jne prefix_bad
    cmp DWORD PTR [rdi+4],3
    jne prefix_bad
    cmp DWORD PTR [rdi+16],65536
    ja prefix_bad
    cmp QWORD PTR [rdi+64],0
    je prefix_bad
    mov r10,QWORD PTR [rdi+48]
    test r10,r10
    jz prefix_bad
    cmp DWORD PTR [r10],048454150h
    jne prefix_bad
    cmp DWORD PTR [r10+4],1
    jne prefix_bad
    mov rax,QWORD PTR [r10+16]
    test rax,rax
    jz prefix_bad
    cmp rax,040000000h
    ja prefix_bad
    lea r11,[r10+128]
    add rax,r11
    jc prefix_bad
    cmp rax,QWORD PTR [r10+24]
    jne prefix_bad
    mov rcx,QWORD PTR [rsi]
    call prefix_view
    cmp DWORD PTR [rbx],0
    jne prefix_false
    mov r12,rax
    mov r13d,edx
    mov eax,DWORD PTR [rsi+16]
    test eax,eax
    js prefix_false
    mov DWORD PTR [rsp+32],eax
    ; The original Java branch returns false for a negative offset before
    ; dereferencing prefix. All nonnegative offsets must first check prefix.
    mov rcx,QWORD PTR [rsi+8]
    call prefix_view
    cmp DWORD PTR [rbx],0
    jne prefix_false
    mov r14,rax
    mov r15d,edx
    sub r13d,r15d
    mov eax,DWORD PTR [rsp+32]
    cmp eax,r13d
    jg prefix_false
    lea r12,[r12+rax*2]
    mov ecx,r15d
prefix_vector:
    cmp ecx,8
    jb prefix_tail
    movdqu xmm0,XMMWORD PTR [r12]
    movdqu xmm1,XMMWORD PTR [r14]
    pcmpeqb xmm0,xmm1
    pmovmskb eax,xmm0
    cmp eax,0FFFFh
    jne prefix_false
    add r12,16
    add r14,16
    sub ecx,8
    jmp prefix_vector
prefix_tail:
    test ecx,ecx
    jz prefix_true
    movzx eax,WORD PTR [r12]
    cmp ax,WORD PTR [r14]
    jne prefix_false
    add r12,2
    add r14,2
    dec ecx
    jmp prefix_tail
prefix_bad:
    mov DWORD PTR [rbx],7
prefix_false:
    xor eax,eax
    jmp prefix_done
prefix_true:
    mov eax,1
prefix_done:
    add rsp,48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_starts_with ENDP
; Validated receiver/backing ownership precedes the existing String shape view.
prefix_view PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    mov QWORD PTR [rsp+32],rcx
    test rcx,rcx
    jz prefix_view_null
    call prefix_owned
    test eax,eax
    jz prefix_view_bad
    cmp QWORD PTR [rcx-16],16
    jne prefix_view_bad
    mov rcx,QWORD PTR [rcx]
    call prefix_owned
    test eax,eax
    jz prefix_view_bad
    mov rcx,QWORD PTR [rsp+32]
    mov rdx,QWORD PTR [rdi+40]
    mov r8,rbx
    call boom_string_view
    jmp prefix_view_done
prefix_view_null:
    mov DWORD PTR [rbx],4
    jmp prefix_view_fail
prefix_view_bad:
    mov DWORD PTR [rbx],7
prefix_view_fail:
    xor eax,eax
    xor edx,edx
prefix_view_done:
    add rsp,40
    ret
prefix_view ENDP
prefix_owned PROC
    mov r10,QWORD PTR [rdi+48]
    lea r11,[r10+160]
    cmp rcx,r11
    jb prefix_owned_no
    mov r11,QWORD PTR [r10+24]
    cmp rcx,r11
    ja prefix_owned_no
    test cl,15
    jnz prefix_owned_no
    mov eax,DWORD PTR [rcx-24]
    and eax,0FFFFFFFDh
    cmp eax,0B00B0001h
    jne prefix_owned_no
    mov rax,QWORD PTR [rcx-32]
    cmp rax,32
    jb prefix_owned_no
    test al,15
    jnz prefix_owned_no
    sub rax,32
    cmp QWORD PTR [rcx-16],rax
    ja prefix_owned_no
    add rax,rcx
    jc prefix_owned_no
    cmp rax,r11
    ja prefix_owned_no
    mov eax,1
    ret
prefix_owned_no:
    xor eax,eax
    ret
prefix_owned ENDP
END
