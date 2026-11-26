; Integer/Long.toHexString: exact unsigned 32/64-bit lowercase UTF16.
; Fresh immutable String plus char[]; no leading zeros, zero becomes "0".
; Native temporaries use the explicit quiescent-GC contract.
option casemap:none
EXTERN boom_string_allocate:PROC
PUBLIC boom_hex_string
.const
hex_digits WORD 030h,031h,032h,033h,034h,035h,036h,037h,038h,039h,061h,062h,063h,064h,065h,066h
.code
; format(ctx RCX,argv RDX,StringPool3 R8,width R9D)->String/NULL.
boom_hex_string PROC FRAME
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
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov r12,r8
    test rbx,rbx
    jz hex_error
    cmp DWORD PTR [rbx],0
    jne hex_error
    test rsi,rsi
    jz hex_bad
    test r12,r12
    jz hex_bad
    cmp DWORD PTR [r12],053545250h
    jne hex_bad
    cmp DWORD PTR [r12+4],3
    jne hex_bad
    cmp QWORD PTR [r12+48],0
    je hex_bad
    cmp r9d,32
    je hex_int
    cmp r9d,64
    jne hex_bad
    mov r13,QWORD PTR [rsi]
    jmp hex_count
hex_int:
    mov r13d,DWORD PTR [rsi]
hex_count:
    mov r14d,1
    test r13,r13
    jz hex_allocate
    bsr r14,r13
    shr r14d,2
    inc r14d
hex_allocate:
    mov rcx,QWORD PTR [r12+48]
    mov rdx,r12
    mov r8d,r14d
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz hex_error
    mov r15,rax
    mov rdi,QWORD PTR [rax]
    lea r11,hex_digits
    mov ecx,r14d
hex_write:
    mov r10d,r13d
    and r10d,15
    movzx edx,WORD PTR [r11+r10*2]
    dec ecx
    mov WORD PTR [rdi+rcx*2],dx
    shr r13,4
    test ecx,ecx
    jnz hex_write
    mov rax,r15
    jmp hex_done
hex_bad:
    mov DWORD PTR [rbx],7
hex_error:
    xor eax,eax
hex_done:
    add rsp,32
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_hex_string ENDP
END
