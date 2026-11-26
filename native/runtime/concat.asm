; StringConcatFactory plans, handwritten MASM. No JVM or C formatting calls.
; Plan ABI1 size32: magic0 abi4 parts8 argc12 rows*16 pool*24.
; Row24: kind0 argIndex4 UTF16*8 literalLength16. kinds literal0/I1/J2/Z3/C4/S5.
; Two passes compute the complete UTF16 length, then fill an unpublished String.
option casemap:none
EXTERN boom_string_allocate:PROC
EXTERN boom_string_view:PROC
PUBLIC boom_string_concat
.const
concat_null WORD 110,117,108,108
concat_true WORD 116,114,117,101
concat_false WORD 102,97,108,115,101
.code
; piece(row RCX,argv RDX,pool R8,ctx R9,buffer stack+40)->chars RAX,len EDX.
; Leaf integer conversion uses unsigned magnitude, including LONG_MIN.
concat_piece PROC
    mov r10, rcx
    mov eax, DWORD PTR [r10]
    test eax, eax
    jz concat_literal
    cmp eax, 5
    ja concat_piece_invalid
    mov ecx, DWORD PTR [r10+4]
    cmp ecx, 16
    jae concat_piece_invalid
    mov rcx, QWORD PTR [rdx+rcx*8]
    cmp eax, 5
    je concat_string
    cmp eax, 3
    je concat_boolean
    cmp eax, 4
    je concat_character
    cmp eax, 1
    jne concat_long
    movsxd rcx, ecx
concat_long:
    mov rax, rcx
    mov r10, QWORD PTR [rsp+40]
    add r10, 48
    mov rcx, r10
    xor r8d, r8d
    test rax, rax
    jns concat_magnitude
    neg rax
    mov r8d, 1
concat_magnitude:
    mov r11d, 10
concat_digit:
    xor edx, edx
    div r11
    add edx, 48
    sub rcx, 2
    mov WORD PTR [rcx], dx
    test rax, rax
    jnz concat_digit
    test r8d, r8d
    jz concat_number_done
    sub rcx, 2
    mov WORD PTR [rcx], 45
concat_number_done:
    mov rax, rcx
    sub r10, rcx
    shr r10, 1
    mov edx, r10d
    ret
concat_character:
    mov rax, QWORD PTR [rsp+40]
    mov WORD PTR [rax], cx
    mov edx, 1
    ret
concat_boolean:
    lea rax, concat_false
    mov edx, 5
    test ecx, ecx
    jz concat_piece_done
    lea rax, concat_true
    mov edx, 4
    ret
concat_string:
    test rcx, rcx
    jz concat_string_null
    mov rdx, QWORD PTR [r8+40]
    mov r8, r9
    jmp boom_string_view
concat_string_null:
    lea rax, concat_null
    mov edx, 4
    ret
concat_literal:
    mov rdx, QWORD PTR [r10+16]
    cmp rdx, 65535
    ja concat_piece_invalid
    mov rax, QWORD PTR [r10+8]
    test rax, rax
    jz concat_piece_invalid
concat_piece_done:
    ret
concat_piece_invalid:
    mov DWORD PTR [r9], 7
    xor eax, eax
    xor edx, edx
    ret
concat_piece ENDP

; concat(context RCX,argv RDX,heap R8,plan R9)->String/NULL.
boom_string_concat PROC FRAME
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
    sub rsp, 192
    .allocstack 192
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov r12, r8
    mov QWORD PTR [rsp+48], r9
    test r9, r9
    jz concat_invalid
    cmp DWORD PTR [r9], 0434F4E43h
    jne concat_invalid
    cmp DWORD PTR [r9+4], 1
    jne concat_invalid
    cmp DWORD PTR [r9+8], 256
    ja concat_invalid
    cmp DWORD PTR [r9+12], 16
    ja concat_invalid
    mov r13, QWORD PTR [r9+16]
    test r13, r13
    jz concat_invalid
    mov rax, QWORD PTR [r9+24]
    test rax, rax
    jz concat_invalid
    cmp DWORD PTR [rax], 053545250h
    jne concat_invalid
    cmp DWORD PTR [rax+4], 3
    jne concat_invalid
    mov QWORD PTR [rsp+160], rax
    xor r14d, r14d
    xor r15d, r15d
    mov DWORD PTR [rsp+72], 0
concat_part_loop:
    mov rax, QWORD PTR [rsp+48]
    cmp r14d, DWORD PTR [rax+8]
    jae concat_pass_end
    lea rcx, [r14+r14*2]
    lea rcx, [r13+rcx*8]
    cmp DWORD PTR [rcx], 0
    je concat_part_ready
    mov edx, DWORD PTR [rcx+4]
    cmp edx, DWORD PTR [rax+12]
    jae concat_invalid
concat_part_ready:
    mov rdx, rsi
    mov r8, QWORD PTR [rsp+160]
    mov r9, rbx
    lea rax, [rsp+96]
    mov QWORD PTR [rsp+32], rax
    call concat_piece
    cmp DWORD PTR [rbx], 0
    jne concat_failed
    cmp DWORD PTR [rsp+72], 0
    jne concat_copy
    add r15, rdx
    cmp r15, 03FFFFFFFh
    ja concat_oom
    jmp concat_part_next
concat_copy:
    mov ecx, edx
    mov r10, rsi
    mov rsi, rax
    rep movsw
    mov rsi, r10
concat_part_next:
    inc r14d
    jmp concat_part_loop
concat_pass_end:
    cmp DWORD PTR [rsp+72], 0
    jne concat_complete
    mov QWORD PTR [rsp+56], r15
    mov rcx, r12
    mov rdx, QWORD PTR [rsp+160]
    mov r8d, r15d
    mov r9, rbx
    call boom_string_allocate
    test rax, rax
    jz concat_failed
    mov QWORD PTR [rsp+64], rax
    mov rdi, QWORD PTR [rax]
    mov QWORD PTR [rsp+88], rdi
    xor r14d, r14d
    mov DWORD PTR [rsp+72], 1
    jmp concat_part_loop
concat_complete:
    mov rax, QWORD PTR [rsp+56]
    shl rax, 1
    add rax, QWORD PTR [rsp+88]
    cmp rax, rdi
    jne concat_invalid
    mov rax, QWORD PTR [rsp+64]
    jmp concat_done
concat_invalid:
    mov DWORD PTR [rbx], 7
    jmp concat_failed
concat_oom:
    mov DWORD PTR [rbx], 3
concat_failed:
    xor eax, eax
concat_done:
    add rsp, 192
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_concat ENDP
END
