; Original String.concat(String) semantic bridge, entirely MASM.
; UTF16 is copied exactly, including NUL and isolated surrogate units.
; Empty suffix returns this. Empty receiver creates a fresh String sharing the
; immutable suffix backing array; other concatenations allocate their own data.
; No automatic GC: native temporary references require the quiescent contract.
option casemap:none
EXTERN boom_string_view:PROC
EXTERN boom_string_allocate:PROC
EXTERN boom_object_new:PROC
PUBLIC boom_string_concat_api
.code
; concat(ctx RCX,argv{receiver,suffix} RDX,StringPool3 R8)->String/NULL.
; Typed objects and live module/heap metadata are trusted caller inputs.
boom_string_concat_api PROC FRAME
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
    jz concat_api_error
    cmp DWORD PTR [rbx],0
    jne concat_api_error
    test r12,r12
    jz concat_api_bad
    test rsi,rsi
    jz concat_api_bad
    cmp DWORD PTR [r12],053545250h
    jne concat_api_bad
    cmp DWORD PTR [r12+4],3
    jne concat_api_bad
    mov r10,QWORD PTR [r12+48]
    test r10,r10
    jz concat_api_bad
    cmp DWORD PTR [r10],048454150h
    jne concat_api_bad
    cmp DWORD PTR [r10+4],1
    jne concat_api_bad
    cmp DWORD PTR [r12+16],65536
    ja concat_api_bad
    cmp QWORD PTR [r12+64],0
    je concat_api_bad
    mov rcx,QWORD PTR [rsi]
    call concat_api_owned
    test eax,eax
    jz concat_api_bad
    mov QWORD PTR [rsp+32],rcx
    mov rdx,QWORD PTR [r12+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne concat_api_error
    mov r13,rax
    mov r14d,edx
    mov rcx,QWORD PTR [rsi+8]
    call concat_api_owned
    test eax,eax
    jz concat_api_bad
    mov QWORD PTR [rsp+40],rcx
    mov rdx,QWORD PTR [r12+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne concat_api_error
    mov r15,rax
    mov DWORD PTR [rsp+48],edx
    test edx,edx
    jz concat_api_identity
    test r14d,r14d
    jz concat_api_copy_object
    mov r8d,r14d
    add r8d,edx
    jc concat_api_oom
    cmp r8d,07FFFFFFFh
    ja concat_api_oom
    mov rcx,QWORD PTR [r12+48]
    mov rdx,r12
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz concat_api_error
    mov QWORD PTR [rsp+56],rax
    mov rdi,QWORD PTR [rax]
    mov rsi,r13
    mov ecx,r14d
    rep movsw
    mov rsi,r15
    mov ecx,DWORD PTR [rsp+48]
    rep movsw
    mov rax,QWORD PTR [rsp+56]
    jmp concat_api_done
concat_api_copy_object:
    mov rcx,QWORD PTR [r12+48]
    mov rdx,QWORD PTR [r12+40]
    mov r8,rbx
    call boom_object_new
    test rax,rax
    jz concat_api_error
    mov r10,QWORD PTR [rsp+40]
    mov r11,QWORD PTR [r10]
    mov QWORD PTR [rax],r11
    mov r11,QWORD PTR [r10+8]
    mov QWORD PTR [rax+8],r11
    jmp concat_api_done
concat_api_identity:
    mov rax,QWORD PTR [rsp+32]
    jmp concat_api_done
concat_api_oom:
    mov DWORD PTR [rbx],3
    jmp concat_api_error
concat_api_bad:
    mov DWORD PTR [rbx],7
concat_api_error:
    xor eax,eax
concat_api_done:
    add rsp,64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_concat_api ENDP
; Check both object pointers belong to this bound heap before viewing payload.
; This is a module lifetime gate, not a verifier for arbitrary native pointers.
; NULL is passed to string_view to produce the Java null error.
concat_api_owned PROC
    test rcx,rcx
    jz concat_api_owned_yes
    mov r10,QWORD PTR [r12+48]
    mov r11,QWORD PTR [r10+16]
    lea r11,[r10+r11+128]
    add r10,160
    cmp rcx,r10
    jb concat_api_owned_no
    lea rax,[rcx+16]
    cmp rax,r11
    ja concat_api_owned_no
    mov rax,QWORD PTR [rcx]
    cmp rax,r10
    jb concat_api_owned_no
    cmp rax,r11
    ja concat_api_owned_no
    add rax,QWORD PTR [rax-16]
    jc concat_api_owned_no
    cmp rax,r11
    ja concat_api_owned_no
concat_api_owned_yes:
    mov eax,1
    ret
concat_api_owned_no:
    xor eax,eax
    ret
concat_api_owned ENDP
END
