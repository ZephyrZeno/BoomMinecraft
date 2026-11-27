; Source-normal java.lang.reflect.Array allocation adapter, RARP48/2. MASM only.
; RARP48/2: heapCell8,JCLS144*16,rows24,RTYP2*32,typeCount40,reserved44.
; Row16: exact next-array TypeDesc*0, next-array typeId8, component rank12.
; Rank FFFFFFFF is void. Absent next type is an explicit metadata error.
option casemap:none
EXTERN boom_java_class_typeid:PROC
EXTERN boom_typed_multi_new:PROC
PUBLIC boom_provider_reflection_array_allocate
.code
; Ordinary VM oop header/range guard; not forged-interior membership proof.
rfa_owned PROC PRIVATE
    test rcx,rcx
    jz rfa_owned_bad
    cmp DWORD PTR [rcx],048454150h
    jne rfa_owned_bad
    cmp DWORD PTR [rcx+4],1
    jne rfa_owned_bad
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz rfa_owned_bad
    cmp rax,040000000h
    ja rfa_owned_bad
    lea r10,[rcx+128]
    add rax,r10
    jc rfa_owned_bad
    cmp rax,QWORD PTR [rcx+24]
    jne rfa_owned_bad
    lea r10,[rcx+160]
    cmp rdx,r10
    jb rfa_owned_bad
    cmp rdx,rax
    ja rfa_owned_bad
    test dl,15
    jnz rfa_owned_bad
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,0B00B0001h
    jne rfa_owned_bad
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb rfa_owned_bad
    test r10b,15
    jnz rfa_owned_bad
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja rfa_owned_bad
    add r10,rdx
    jc rfa_owned_bad
    cmp r10,rax
    ja rfa_owned_bad
    mov eax,1
    ret
rfa_owned_bad:
    xor eax,eax
    ret
rfa_owned ENDP

; allocate(Context32,argv[Class,int/int[]],pool,op0=new/op1=multi)->array/null.
; Temporary counts/native references are live only with automatic GC disabled.
boom_provider_reflection_array_allocate PROC FRAME
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
    sub rsp,2160
    .allocstack 2160
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    mov r14d,r9d
    test rbx,rbx
    jz rfa_new_zero
    cmp DWORD PTR [rbx],0
    jne rfa_new_zero
    cmp QWORD PTR [rbx+16],0
    jne rfa_new_zero
    cmp QWORD PTR [rbx+24],0
    jne rfa_new_zero
    test rsi,rsi
    jz rfa_new_bad
    test rdi,rdi
    jz rfa_new_bad
    cmp DWORD PTR [rdi],050524152h
    jne rfa_new_bad
    cmp DWORD PTR [rdi+4],2
    jne rfa_new_bad
    cmp DWORD PTR [rdi+44],0
    jne rfa_new_bad
    mov eax,DWORD PTR [rdi+40]
    dec eax
    cmp eax,0FFFFFh
    ja rfa_new_bad
    cmp QWORD PTR [rdi+24],0
    je rfa_new_bad
    mov rax,QWORD PTR [rdi+32]
    test rax,rax
    jz rfa_new_bad
    cmp DWORD PTR [rax],052545950h
    jne rfa_new_bad
    cmp DWORD PTR [rax+4],2
    jne rfa_new_bad
    mov edx,DWORD PTR [rdi+40]
    cmp DWORD PTR [rax+12],edx
    jne rfa_new_bad
    mov rdx,QWORD PTR [rdi+16]
    test rdx,rdx
    jz rfa_new_bad
    cmp DWORD PTR [rdx],04A434C53h
    jne rfa_new_bad
    cmp DWORD PTR [rdx+4],1
    jne rfa_new_bad
    mov ecx,DWORD PTR [rdi+40]
    cmp DWORD PTR [rdx+12],ecx
    jne rfa_new_bad
    cmp QWORD PTR [rdx+40],rax
    jne rfa_new_bad
    mov rax,QWORD PTR [rdi+8]
    cmp QWORD PTR [rdx+48],rax
    jne rfa_new_bad
    mov rax,QWORD PTR [rdi+8]
    test rax,rax
    jz rfa_new_bad
    mov r12,QWORD PTR [rax]
    test r12,r12
    jz rfa_new_bad
    cmp r14d,1
    ja rfa_new_bad
    mov rcx,rbx
    mov rdx,QWORD PTR [rdi+16]
    mov r8,QWORD PTR [rsi]
    call boom_java_class_typeid
    cmp DWORD PTR [rbx],0
    jne rfa_new_zero
    cmp eax,DWORD PTR [rdi+40]
    jae rfa_new_bad
    mov r13d,eax
    test r14d,r14d
    jnz rfa_new_multi
    movsxd rax,DWORD PTR [rsi+8]
    test eax,eax
    js rfa_new_negative
    mov QWORD PTR [rsp+48],rax
    mov r14d,1
    jmp rfa_new_resolve
rfa_new_multi:
    mov r15,QWORD PTR [rsi+8]
    test r15,r15
    jz rfa_new_null
    mov rcx,r12
    mov rdx,r15
    call rfa_owned
    test eax,eax
    jz rfa_new_bad
    cmp QWORD PTR [r15-8],266
    jne rfa_new_bad
    cmp DWORD PTR [r15-20],0
    jne rfa_new_bad
    mov rax,QWORD PTR [r15-16]
    test al,3
    jnz rfa_new_bad
    shr rax,2
    lea rcx,[rax-1]
    cmp rcx,254
    ja rfa_new_illegal
    mov r14d,eax
    xor r10d,r10d
rfa_new_copy:
    movsxd rax,DWORD PTR [r15+r10*4]
    test eax,eax
    js rfa_new_negative
    mov QWORD PTR [rsp+r10*8+48],rax
    inc r10d
    cmp r10d,r14d
    jb rfa_new_copy
rfa_new_resolve:
    mov r15,QWORD PTR [rdi+24]
    mov eax,r13d
    shl rax,4
    mov eax,DWORD PTR [r15+rax+12]
    cmp eax,255
    jae rfa_new_illegal
    add eax,r14d
    cmp eax,255
    ja rfa_new_illegal
    xor r11d,r11d
rfa_new_type:
    mov eax,r13d
    shl rax,4
    mov r8,QWORD PTR [r15+rax]
    test r8,r8
    jz rfa_new_missing
    mov r13d,DWORD PTR [r15+rax+8]
    cmp r13d,DWORD PTR [rdi+40]
    jae rfa_new_bad
    inc r11d
    cmp r11d,r14d
    jb rfa_new_type
    mov rcx,r12
    lea rdx,[rsp+48]
    mov r9d,r14d
    mov QWORD PTR [rsp+32],rbx
    call boom_typed_multi_new
    jmp rfa_new_done
rfa_new_null:
    mov DWORD PTR [rbx],4
    jmp rfa_new_zero
rfa_new_negative:
    mov DWORD PTR [rbx],2
    jmp rfa_new_zero
rfa_new_illegal:
    mov DWORD PTR [rbx],18
    jmp rfa_new_zero
rfa_new_missing:
    mov DWORD PTR [rbx],20
    jmp rfa_new_zero
rfa_new_bad:
    mov DWORD PTR [rbx],7
rfa_new_zero:
    xor eax,eax
rfa_new_done:
    add rsp,2160
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_provider_reflection_array_allocate ENDP
