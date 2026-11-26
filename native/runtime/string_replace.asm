; Source-verified String.replace(char,char), all runtime work in MASM.
; Equal arguments or no matching UTF16 unit return the receiver with zero allocation.
; Changed results have a fresh String and private char[], including surrogate units.
; Collection remains explicit/quiescent while native references are active.
option casemap:none
EXTERN boom_string_view:PROC
EXTERN boom_string_allocate:PROC
PUBLIC boom_string_replace
.code
; (ctx RCX,argv{receiver,old32,new32} RDX,StringPool3 R8)->String/NULL.
boom_string_replace PROC FRAME
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
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov r12,r8
    test rbx,rbx
    jz replace_error
    cmp DWORD PTR [rbx],0
    jne replace_error
    test rsi,rsi
    jz replace_bad
    test r12,r12
    jz replace_bad
    cmp DWORD PTR [r12],053545250h
    jne replace_bad
    cmp DWORD PTR [r12+4],3
    jne replace_bad
    cmp DWORD PTR [r12+16],65536
    ja replace_bad
    cmp QWORD PTR [r12+64],0
    je replace_bad
    cmp QWORD PTR [rsi],0
    je replace_null
    mov r10,QWORD PTR [r12+48]
    test r10,r10
    jz replace_bad
    cmp DWORD PTR [r10],048454150h
    jne replace_bad
    cmp DWORD PTR [r10+4],1
    jne replace_bad
    mov rcx,QWORD PTR [rsi]
    call replace_owned
    test eax,eax
    jz replace_bad
    mov r15,rcx
    mov rdx,QWORD PTR [r12+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne replace_error
    mov r13,rax
    mov r14d,edx
    mov edi,DWORD PTR [rsi+8]
    mov eax,DWORD PTR [rsi+16]
    mov DWORD PTR [rsp+32],edi
    mov DWORD PTR [rsp+36],eax
    cmp edi,eax
    je replace_identity
    xor ecx,ecx
replace_find:
    cmp ecx,r14d
    jae replace_identity
    movzx eax,WORD PTR [r13+rcx*2]
    cmp eax,edi
    je replace_found
    inc ecx
    jmp replace_find
replace_found:
    mov DWORD PTR [rsp+40],ecx
    mov rcx,QWORD PTR [r12+48]
    mov rdx,r12
    mov r8d,r14d
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz replace_error
    mov QWORD PTR [rsp+48],rax
    mov rdi,QWORD PTR [rax]
    mov rsi,r13
    mov ecx,DWORD PTR [rsp+40]
    rep movsw
    mov ecx,r14d
    sub ecx,DWORD PTR [rsp+40]
    mov r10d,DWORD PTR [rsp+32]
    mov r11d,DWORD PTR [rsp+36]
replace_copy:
    movzx eax,WORD PTR [rsi]
    cmp eax,r10d
    cmove eax,r11d
    mov WORD PTR [rdi],ax
    add rsi,2
    add rdi,2
    dec ecx
    jnz replace_copy
    mov rax,QWORD PTR [rsp+48]
    jmp replace_done
replace_identity:
    mov rax,r15
    jmp replace_done
replace_null:
    mov DWORD PTR [rbx],4
    jmp replace_error
replace_bad:
    mov DWORD PTR [rbx],7
replace_error:
    xor eax,eax
replace_done:
    add rsp,64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_replace ENDP
; Module/heap lifetime check, accepting NULL so string_view reports Java NPE.
replace_owned PROC
    test rcx,rcx
    jz replace_owned_yes
    mov r10,QWORD PTR [r12+48]
    mov r11,QWORD PTR [r10+16]
    lea r11,[r10+r11+128]
    add r10,160
    cmp rcx,r10
    jb replace_owned_no
    lea rax,[rcx+16]
    cmp rax,r11
    ja replace_owned_no
    mov rax,QWORD PTR [rcx]
    cmp rax,r10
    jb replace_owned_no
    cmp rax,r11
    ja replace_owned_no
    add rax,QWORD PTR [rax-16]
    jc replace_owned_no
    cmp rax,r11
    ja replace_owned_no
replace_owned_yes:
    mov eax,1
    ret
replace_owned_no:
    xor eax,eax
    ret
replace_owned ENDP

; Proven AOT literal replaceAll. R9D packs old16/new16; original String argv
; stays intact so native calls never overwrite typed Java stack slots.
PUBLIC boom_string_replace_literal_chars
boom_string_replace_literal_chars PROC FRAME
    sub rsp,56
    .allocstack 56
    .endprolog
    test rcx,rcx
    jz replace_literal_zero
    cmp DWORD PTR [rcx],0
    jne replace_literal_zero
    test rdx,rdx
    jz replace_literal_bad
    mov rax,QWORD PTR [rdx]
    mov QWORD PTR [rsp+32],rax
    movzx eax,r9w
    mov QWORD PTR [rsp+40],rax
    shr r9d,16
    mov QWORD PTR [rsp+48],r9
    lea rdx,[rsp+32]
    call boom_string_replace
    jmp replace_literal_done
replace_literal_bad:
    mov DWORD PTR [rcx],7
replace_literal_zero:
    xor eax,eax
replace_literal_done:
    add rsp,56
    ret
boom_string_replace_literal_chars ENDP
END
