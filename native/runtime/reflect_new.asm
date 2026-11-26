; Class.newInstance over canonical, source-bound frozen-image constructor rows.
; RNEW80 ABI1: mirrors8,heapCell16,rows24,count32D,callerType36D,
; Throwable.messageOffset40D,flags44D=0,typeMap48,ClassType56,res64/res72=0.
; Row24: action0D,nameLiteral4D,factory8Q,noSuchMessage16D,reserved20D=0.
; Actions: 0=real Java constructor factory,1=missing constructor,
; 2=illegal access,3=abstract,4=body not linked (explicit unimplemented).
; Factories allocate only after real class initialization and invoke generated ASM.
option casemap:none
EXTERN boom_runtime_type:PROC
EXTERN boom_mirror_typeid:PROC
EXTERN boom_exception_create:PROC
EXTERN boom_string_load:PROC
PUBLIC boom_reflect_new
.code
; (Context32 RCX,argv{Class} RDX,RNEW80 R8)->object/NULL.
boom_reflect_new PROC FRAME
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
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    test rbx,rbx
    jz reflect_new_zero
    cmp DWORD PTR [rbx],0
    jne reflect_new_zero
    test rsi,rsi
    jz reflect_new_bad
    test rdi,rdi
    jz reflect_new_bad
    cmp DWORD PTR [rdi],057454E52h
    jne reflect_new_bad
    cmp DWORD PTR [rdi+4],1
    jne reflect_new_bad
    cmp DWORD PTR [rdi+44],0
    jne reflect_new_bad
    cmp QWORD PTR [rdi+64],0
    jne reflect_new_bad
    cmp QWORD PTR [rdi+72],0
    jne reflect_new_bad
    mov r12,QWORD PTR [rdi+8]
    test r12,r12
    jz reflect_new_bad
    mov eax,DWORD PTR [rdi+32]
    dec eax
    cmp eax,16383
    ja reflect_new_bad
    inc eax
    cmp eax,DWORD PTR [r12+12]
    jne reflect_new_bad
    cmp DWORD PTR [rdi+36],eax
    jae reflect_new_bad
    mov rax,QWORD PTR [rdi+16]
    test rax,rax
    jz reflect_new_bad
    mov rax,QWORD PTR [rax]
    test rax,rax
    jz reflect_new_bad
    cmp QWORD PTR [r12+48],rax
    jne reflect_new_bad
    mov rcx,QWORD PTR [rsi]
    test rcx,rcx
    jz reflect_new_null
    mov rdx,QWORD PTR [rdi+48]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne reflect_new_zero
    cmp rax,QWORD PTR [rdi+56]
    jne reflect_new_bad
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi]
    mov r8,r12
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne reflect_new_zero
    cmp eax,DWORD PTR [rdi+32]
    jae reflect_new_bad
    imul rax,24
    mov r13,QWORD PTR [rdi+24]
    test r13,r13
    jz reflect_new_bad
    add r13,rax
    cmp DWORD PTR [r13+20],0
    jne reflect_new_bad
    mov eax,DWORD PTR [r13]
    cmp eax,4
    ja reflect_new_bad
    test eax,eax
    jz reflect_new_construct
    cmp eax,1
    je reflect_new_missing
    cmp eax,2
    je reflect_new_access
    cmp eax,3
    je reflect_new_abstract
    mov DWORD PTR [rbx],20
    jmp reflect_new_zero
reflect_new_construct:
    cmp QWORD PTR [r13+8],0
    je reflect_new_bad
    mov rcx,rbx
    xor edx,edx
    call QWORD PTR [r13+8]
    mov edx,1
    jmp reflect_new_done
reflect_new_missing:
    ; Original Class.newInstance wraps NoSuchMethodException as the cause.
    mov rcx,rbx
    mov edx,26
    xor r8d,r8d
    xor r9d,r9d
    call boom_exception_create
    test rax,rax
    jz reflect_new_zero
    mov QWORD PTR [rsp+32],rax
    mov ecx,DWORD PTR [r13+16]
    mov QWORD PTR [rsp+40],rcx
    call reflect_new_message
    cmp DWORD PTR [rbx],0
    jne reflect_new_zero
    mov rax,QWORD PTR [rsp+32]
    mov QWORD PTR [rsp+48],rax
    mov edx,24
    jmp reflect_new_error_create
reflect_new_access:
    mov QWORD PTR [rsp+48],0
    mov edx,25
    jmp reflect_new_error_create
reflect_new_abstract:
    mov QWORD PTR [rsp+48],0
    mov edx,24
reflect_new_error_create:
    mov rcx,rbx
    mov r8,QWORD PTR [rsp+48]
    xor r9d,r9d
    call boom_exception_create
    test rax,rax
    jz reflect_new_zero
    mov QWORD PTR [rsp+32],rax
    mov ecx,DWORD PTR [r13+4]
    mov QWORD PTR [rsp+40],rcx
    call reflect_new_message
    cmp DWORD PTR [rbx],0
    jne reflect_new_zero
    mov rax,QWORD PTR [rsp+32]
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp reflect_new_zero
reflect_new_null:
    mov DWORD PTR [rbx],4
    jmp reflect_new_zero
reflect_new_bad:
    mov DWORD PTR [rbx],7
reflect_new_zero:
    xor eax,eax
    xor edx,edx
reflect_new_done:
    add rsp,64
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_reflect_new ENDP

; Internal message helper uses its caller's frame, accessed through RSP+8.
; Inputs remain in nonvolatile RBX/RDI/R12 and caller slots32/40.
reflect_new_message PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    mov r8d,DWORD PTR [rsp+88]
    cmp r8d,-1
    je reflect_new_message_done
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [r12+40]
    mov r9,rbx
    call boom_string_load
    cmp DWORD PTR [rbx],0
    jne reflect_new_message_done
    mov rdx,QWORD PTR [rsp+80]
    mov ecx,DWORD PTR [rdi+40]
    test ecx,7
    jnz reflect_new_message_bad
    mov r10d,DWORD PTR [rdx-20]
    shl r10,3
    cmp rcx,r10
    jae reflect_new_message_bad
    mov r10,QWORD PTR [rdx-16]
    sub r10,8
    jc reflect_new_message_bad
    cmp rcx,r10
    ja reflect_new_message_bad
    mov QWORD PTR [rdx+rcx],rax
    jmp reflect_new_message_done
reflect_new_message_bad:
    mov DWORD PTR [rbx],7
reflect_new_message_done:
    add rsp,40
    ret
reflect_new_message ENDP
END
