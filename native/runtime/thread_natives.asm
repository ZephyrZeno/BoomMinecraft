; Source-verified Thread native table. Five platform operations are executable;
; remaining registered thunks report UnsatisfiedLinkError, never success.
option casemap:none
EXTERN boom_threads_current:PROC
EXTERN boom_threads_id_address:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
EXTERN SwitchToThread:PROC
PUBLIC boom_thread_native_register
PUBLIC boom_thread_native_dispatch
PUBLIC boom_thread_native_bind
thread_native_thunk MACRO number
PUBLIC boom_thread_native_&number
boom_thread_native_&number PROC
    mov r9d,number
    jmp thread_native_execute
boom_thread_native_&number ENDP
ENDM
.const
ALIGN 8
thread_native_functions LABEL QWORD
    QWORD OFFSET boom_thread_native_0,OFFSET boom_thread_native_1,OFFSET boom_thread_native_2
    QWORD OFFSET boom_thread_native_3,OFFSET boom_thread_native_4,OFFSET boom_thread_native_5
    QWORD OFFSET boom_thread_native_6,OFFSET boom_thread_native_7,OFFSET boom_thread_native_8
    QWORD OFFSET boom_thread_native_9,OFFSET boom_thread_native_10,OFFSET boom_thread_native_11
    QWORD OFFSET boom_thread_native_12,OFFSET boom_thread_native_13,OFFSET boom_thread_native_14
    QWORD OFFSET boom_thread_native_15,OFFSET boom_thread_native_16,OFFSET boom_thread_native_17
.code
thread_native_pool_valid PROC
    test rcx,rcx
    jz thread_pool_invalid
    cmp DWORD PTR [rcx],0544E504Ch
    jne thread_pool_invalid
    cmp DWORD PTR [rcx+4],1
    jne thread_pool_invalid
    cmp DWORD PTR [rcx+12],0
    jne thread_pool_invalid
    cmp QWORD PTR [rcx+72],0
    jne thread_pool_invalid
    cmp QWORD PTR [rcx+24],0
    je thread_pool_invalid
    cmp QWORD PTR [rcx+32],0
    je thread_pool_invalid
    cmp QWORD PTR [rcx+40],0
    je thread_pool_invalid
    cmp QWORD PTR [rcx+48],0
    je thread_pool_invalid
    cmp QWORD PTR [rcx+56],0
    je thread_pool_invalid
    cmp QWORD PTR [rcx+64],0
    je thread_pool_invalid
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz thread_pool_invalid
    cmp DWORD PTR [rax],0544E4154h
    jne thread_pool_invalid
    cmp DWORD PTR [rax+4],1
    jne thread_pool_invalid
    cmp DWORD PTR [rax+8],18
    jne thread_pool_invalid
    cmp DWORD PTR [rax+12],028034h
    jne thread_pool_invalid
    mov eax,1
    ret
thread_pool_invalid:
    xor eax,eax
    ret
thread_native_pool_valid ENDP

; register(Context16,Pool80)->0. Installs exact table addresses and preserves
; the explicit unsupported capability bits; class initialization is separate.
boom_thread_native_register PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    test rbx,rbx
    jz thread_register_done
    cmp DWORD PTR [rbx],0
    jne thread_register_done
    mov rcx,rsi
    call thread_native_pool_valid
    test eax,eax
    jz thread_register_bad
    mov r10,QWORD PTR [rsi+16]
    add r10,16
    lea r11,thread_native_functions
    xor ecx,ecx
thread_register_row:
    cmp QWORD PTR [r10],0
    je thread_register_bad
    cmp QWORD PTR [r10+8],0
    je thread_register_bad
    mov rax,QWORD PTR [r11+rcx*8]
    cmp QWORD PTR [r10+16],rax
    jne thread_register_bad
    mov eax,028034h
    shr eax,cl
    and eax,1
    cmp DWORD PTR [r10+28],eax
    jne thread_register_bad
    add r10,32
    inc ecx
    cmp ecx,18
    jb thread_register_row
    xor eax,eax
    mov edx,2
    lock cmpxchg DWORD PTR [rsi+8],edx
    test eax,eax
    jz thread_register_done
    cmp eax,2
    je thread_register_done
thread_register_bad:
    mov DWORD PTR [rbx],7
thread_register_done:
    xor eax,eax
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_thread_native_register ENDP

; dispatch(Context16,argv,Pool80,index). Even unimplemented entries have real
; error thunks; the AOT linker additionally rejects their Java call sites.
boom_thread_native_dispatch PROC
    jmp thread_native_execute
boom_thread_native_dispatch ENDP
thread_native_thunk 0
thread_native_thunk 1
thread_native_thunk 2
thread_native_thunk 3
thread_native_thunk 4
thread_native_thunk 5
thread_native_thunk 6
thread_native_thunk 7
thread_native_thunk 8
thread_native_thunk 9
thread_native_thunk 10
thread_native_thunk 11
thread_native_thunk 12
thread_native_thunk 13
thread_native_thunk 14
thread_native_thunk 15
thread_native_thunk 16
thread_native_thunk 17
thread_native_execute PROC FRAME
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
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    mov r12d,r9d
    test rbx,rbx
    jz thread_execute_error
    cmp DWORD PTR [rbx],0
    jne thread_execute_error
    mov rcx,rdi
    call thread_native_pool_valid
    test eax,eax
    jz thread_execute_bad
    cmp DWORD PTR [rdi+8],2
    jne thread_execute_bad
    cmp r12d,18
    jae thread_execute_bad
    mov rax,QWORD PTR [rdi+16]
    mov ecx,r12d
    shl rcx,5
    mov rdx,QWORD PTR [rax+rcx+32]
    lea r10,thread_native_functions
    cmp rdx,QWORD PTR [r10+r12*8]
    jne thread_execute_bad
    cmp r12d,2
    je thread_execute_yield
    cmp r12d,4
    je thread_execute_current
    cmp r12d,5
    je thread_execute_current
    cmp r12d,17
    je thread_execute_materialize
    cmp r12d,15
    jne thread_execute_unsupported
    mov rcx,QWORD PTR [rdi+56]
    mov rcx,QWORD PTR [rcx]
    call boom_threads_id_address
    test rax,rax
    jz thread_execute_bad
    jmp thread_execute_done
thread_execute_current:
    mov rcx,QWORD PTR [rdi+56]
    mov rcx,QWORD PTR [rcx]
    call boom_threads_current
    test rax,rax
    jz thread_execute_bad
    mov QWORD PTR [rsp+32],rax
    mov rcx,rax
    mov rdx,QWORD PTR [rdi+32]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne thread_execute_error
    test rax,rax
    jz thread_execute_bad
    mov r13,rax
    mov rcx,rax
    mov rdx,QWORD PTR [rdi+40]
    call boom_type_assignable
    test eax,eax
    jz thread_execute_bad
    mov rcx,r13
    mov rdx,QWORD PTR [rdi+48]
    call boom_type_assignable
    test eax,eax
    jnz thread_execute_unsupported
    mov rax,QWORD PTR [rsp+32]
    jmp thread_execute_done
thread_execute_yield:
    call SwitchToThread
    xor eax,eax
    jmp thread_execute_done
thread_execute_materialize:
    ; Objects already have heap storage and real native-stack references. This
    ; native escape is retained even for NULL; there is no scalar replacement
    ; or deoptimization in this backend. It does not provide stack walking/GC.
    test rsi,rsi
    jz thread_execute_bad
    mov rdx,QWORD PTR [rsi]
    test rdx,rdx
    jz thread_execute_error
    mov rcx,QWORD PTR [rdi+64]
    mov rcx,QWORD PTR [rcx]
    test rcx,rcx
    jz thread_execute_bad
    cmp DWORD PTR [rcx],048454150h
    jne thread_execute_bad
    cmp DWORD PTR [rcx+4],1
    jne thread_execute_bad
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz thread_execute_bad
    cmp rax,040000000h
    ja thread_execute_bad
    lea r10,[rcx+128]
    add rax,r10
    jc thread_execute_bad
    cmp rax,QWORD PTR [rcx+24]
    jne thread_execute_bad
    lea r10,[rcx+160]
    cmp rdx,r10
    jb thread_execute_bad
    cmp rdx,rax
    ja thread_execute_bad
    test dl,15
    jnz thread_execute_bad
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,0B00B0001h
    jne thread_execute_bad
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb thread_execute_bad
    test r10b,15
    jnz thread_execute_bad
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja thread_execute_bad
    add r10,rdx
    jc thread_execute_bad
    cmp r10,rax
    ja thread_execute_bad
    mov rcx,rdx
    mov rdx,QWORD PTR [rdi+32]
    mov r8,rbx
    call boom_runtime_type
    jmp thread_execute_error
thread_execute_unsupported:
    mov DWORD PTR [rbx],20
    jmp thread_execute_error
thread_execute_bad:
    mov DWORD PTR [rbx],7
thread_execute_error:
    xor eax,eax
thread_execute_done:
    add rsp,48
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
thread_native_execute ENDP

; bind(registry,Pool80)->0/87/170. Borrowed registry must use this image's heap.
boom_thread_native_bind PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov edi,87
    mov rcx,rdx
    call thread_native_pool_valid
    test eax,eax
    jz thread_bind_done
    test rbx,rbx
    jz thread_bind_clear
    mov rcx,rbx
    call boom_threads_id_address
    test rax,rax
    jz thread_bind_done
    mov rax,QWORD PTR [rsi+64]
    mov rax,QWORD PTR [rax]
    test rax,rax
    jz thread_bind_done
    cmp rax,QWORD PTR [rbx+8]
    jne thread_bind_done
    mov rcx,QWORD PTR [rsi+56]
    mov rax,QWORD PTR [rcx]
    test rax,rax
    jz thread_bind_set
    cmp rax,rbx
    je thread_bind_set
    mov edi,170
    jmp thread_bind_done
thread_bind_clear:
    mov rax,QWORD PTR [rsi+56]
    mov rcx,QWORD PTR [rax]
    test rcx,rcx
    jz thread_bind_set
    mov rbx,rcx
    call boom_threads_id_address
    test rax,rax
    jz thread_bind_clear_ready
    mov edi,170
    cmp DWORD PTR [rbx+24],0
    jne thread_bind_done
thread_bind_clear_ready:
    xor ebx,ebx
thread_bind_set:
    mov rcx,QWORD PTR [rsi+56]
    xchg rbx,QWORD PTR [rcx]
    xor edi,edi
thread_bind_done:
    mov eax,edi
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_thread_native_bind ENDP
END
