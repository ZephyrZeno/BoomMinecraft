; Context32 class initialization. Descriptor64 ABI2 has a cause-root cell pointer56.
; Context32: kind0 PC4 method8 depth12 pending16 VMplan24.
; All source initializers and hierarchy trampolines execute generated assembly.
option casemap:none
EXTERN GetCurrentThreadId:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
EXTERN boom_exception_init_failure:PROC
EXTERN boom_exception_class_failed:PROC
PUBLIC boom_class_ensure32
.const
class32_java_mxcsr DWORD 01F80h
.code
boom_class_ensure32 PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    test rbx,rbx
    jz class32_invalid
    cmp DWORD PTR [rbx],0434C4153h
    jne class32_invalid
    cmp DWORD PTR [rbx+4],2
    jne class32_invalid
    cmp DWORD PTR [rsi],0
    jne class32_error
    cmp DWORD PTR [rbx+8],2
    je class32_success
    call GetCurrentThreadId
    mov edi,eax
class32_state:
    mov eax,DWORD PTR [rbx+8]
    cmp eax,2
    je class32_success
    cmp eax,3
    je class32_failed
    cmp eax,1
    je class32_wait
    test eax,eax
    jnz class32_invalid
    mov edx,1
    lock cmpxchg DWORD PTR [rbx+8],edx
    jne class32_state
    mov DWORD PTR [rbx+12],edi
    mov rax,QWORD PTR [rbx+16]
    test rax,rax
    jz class32_publish_success
    mov rcx,rsi
    lea rdx,[rsp+40]
    stmxcsr DWORD PTR [rsp+36]
    ldmxcsr DWORD PTR [class32_java_mxcsr]
    call rax
    ldmxcsr DWORD PTR [rsp+36]
    cmp DWORD PTR [rsi],0
    jne class32_publish_failure
class32_publish_success:
    mov DWORD PTR [rbx+12],0
    mov DWORD PTR [rbx+8],2
    lea rcx,[rbx+8]
    call WakeByAddressAll
class32_success:
    xor eax,eax
    jmp class32_done
class32_wait:
    cmp DWORD PTR [rbx+12],edi
    je class32_success
    lock inc DWORD PTR [rbx+48]
    mov DWORD PTR [rsp+32],1
    lea rcx,[rbx+8]
    lea rdx,[rsp+32]
    mov r8d,4
    mov r9d,-1
    call WaitOnAddress
    lock dec DWORD PTR [rbx+48]
    jmp class32_state
class32_publish_failure:
    mov rcx,rsi
    call boom_exception_init_failure
    mov rax,QWORD PTR [rsi]
    mov QWORD PTR [rbx+32],rax
    mov rax,QWORD PTR [rsi+8]
    mov QWORD PTR [rbx+40],rax
    mov rax,QWORD PTR [rsi+16]
    mov r10,QWORD PTR [rbx+56]
    mov QWORD PTR [r10],rax
    mov DWORD PTR [rbx+12],0
    mov DWORD PTR [rbx+8],3
    lea rcx,[rbx+8]
    call WakeByAddressAll
    jmp class32_error
class32_failed:
    mov rcx,rsi
    mov rdx,rbx
    call boom_exception_class_failed
    jmp class32_error
class32_invalid:
    mov DWORD PTR [rsi],7
class32_error:
    mov eax,1
class32_done:
    add rsp,48
    pop rdi
    pop rsi
    pop rbx
    ret
boom_class_ensure32 ENDP
END
