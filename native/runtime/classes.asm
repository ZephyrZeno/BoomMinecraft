; Class initialization state machine, MASM only. Compiler-generated initializer
; trampolines ensure dependencies in JVMS order before the class's own body.
; Descriptor64: magic0,ABI4,state8,ownerThread12,initializer16,classID24,
; reserved28,original failure Context16 at32,active waiters DWORD48.
; States 0/1/2/3. Descriptors remain alive until every caller has returned.
; ensure(descriptor,Context16)->0 success/1 exception status.
; Failed initialization is persistent; no reset/retry or JVM fallback.
option casemap:none
EXTERN GetCurrentThreadId:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
PUBLIC boom_class_ensure
.const
class_java_mxcsr DWORD 01F80h
.code
boom_class_ensure PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp, 48
    .allocstack 48
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    test rbx, rbx
    jz class_invalid
    cmp DWORD PTR [rbx], 0434C4153h
    jne class_invalid
    cmp DWORD PTR [rbx+4], 1
    jne class_invalid
    cmp DWORD PTR [rsi], 0
    jne class_error
    cmp DWORD PTR [rbx+8], 2
    je class_success
    call GetCurrentThreadId
    mov edi, eax
class_state:
    mov eax, DWORD PTR [rbx+8]
    cmp eax, 2
    je class_success
    cmp eax, 3
    je class_previous_failure
    cmp eax, 1
    je class_in_progress
    test eax, eax
    jnz class_invalid
    mov edx, 1
    lock cmpxchg DWORD PTR [rbx+8], edx
    jne class_state
    mov DWORD PTR [rbx+12], edi
    mov rax, QWORD PTR [rbx+16]
    test rax, rax
    jz class_publish_success
    mov rcx, rsi
    lea rdx, [rsp+40] ; ()V body ignores argv, still pass a valid address
    stmxcsr DWORD PTR [rsp+36]
    ldmxcsr DWORD PTR [class_java_mxcsr]
    call rax
    ldmxcsr DWORD PTR [rsp+36]
    cmp DWORD PTR [rsi], 0
    jne class_publish_failure
class_publish_success:
    mov DWORD PTR [rbx+12], 0
    mov DWORD PTR [rbx+8], 2
    lea rcx, [rbx+8]
    call WakeByAddressAll
class_success:
    xor eax, eax
    jmp class_done
class_in_progress:
    cmp DWORD PTR [rbx+12], edi
    je class_success ; same owner may observe prepared/default fields
    lock inc DWORD PTR [rbx+48]
    mov DWORD PTR [rsp+32], 1
    lea rcx, [rbx+8]
    lea rdx, [rsp+32]
    mov r8d, 4
    mov r9d, -1
    call WaitOnAddress
    lock dec DWORD PTR [rbx+48]
    jmp class_state ; also handle spurious wakeups by rechecking
class_publish_failure:
    mov rax, QWORD PTR [rsi]
    mov QWORD PTR [rbx+32], rax
    mov rax, QWORD PTR [rsi+8]
    mov QWORD PTR [rbx+40], rax
    ; Existing Error categories propagate; non-Error failures get EIIE status.
    mov eax, DWORD PTR [rsi]
    cmp eax, 3
    je class_keep_error
    cmp eax, 7
    je class_keep_error
    cmp eax, 8
    je class_keep_error
    cmp eax, 9
    je class_keep_error
    cmp eax, 10
    je class_keep_error
    cmp eax, 13 ; IncompatibleClassChangeError
    je class_keep_error
    cmp eax, 14 ; AbstractMethodError
    je class_keep_error
    cmp eax, 15 ; IllegalAccessError
    je class_keep_error
    mov DWORD PTR [rsi], 8
class_keep_error:
    mov DWORD PTR [rbx+12], 0
    mov DWORD PTR [rbx+8], 3
    lea rcx, [rbx+8]
    call WakeByAddressAll
    jmp class_error
class_previous_failure:
    mov DWORD PTR [rsi], 9 ; NoClassDefFoundError status, no new initializer run
    jmp class_error
class_invalid:
    mov DWORD PTR [rsi], 7
class_error:
    mov eax, 1
class_done:
    add rsp, 48
    pop rdi
    pop rsi
    pop rbx
    ret
boom_class_ensure ENDP
END
