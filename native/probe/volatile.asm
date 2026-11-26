; Native-only two-actor litmus harness. No CLR/JVM transitions between actor operations.
; stress(entry RCX,rounds EDX,output R8,resetMode R9D)->Win32 status.
; The controller resets via the same generated entry, releases two persistent
; native threads, then waits for both actors. Their entry modes are resetMode+1/+2.
; Output64 per round: two {RAX8,Context16,zero8} records. Caller owns the buffer.
; Controller/worker barriers occur before and after the WHOLE actor invocation;
; no fence is inserted between an actor's Java volatile store and following load.
option casemap:none
EXTERN CreateThread:PROC
EXTERN WaitForSingleObject:PROC
EXTERN CloseHandle:PROC
EXTERN GetTickCount64:PROC
PUBLIC boom_volatile_stress
.code
volatile_actor PROC FRAME
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
    sub rsp, 224
    .allocstack 224
    .endprolog
    mov rbx, QWORD PTR [rcx]
    mov r14d, DWORD PTR [rcx+8]
    mov r15d, DWORD PTR [rcx+12]
    mov rdi, QWORD PTR [rbx]
    mov rsi, QWORD PTR [rbx+8]
    mov r12d, DWORD PTR [rbx+16]
    mov r13d, 1
    xorps xmm0, xmm0
    movdqu XMMWORD PTR [rsp+64], xmm0
    movdqu XMMWORD PTR [rsp+80], xmm0
    movdqu XMMWORD PTR [rsp+96], xmm0
    movdqu XMMWORD PTR [rsp+112], xmm0
    movdqu XMMWORD PTR [rsp+128], xmm0
    movdqu XMMWORD PTR [rsp+144], xmm0
    movdqu XMMWORD PTR [rsp+160], xmm0
    movdqu XMMWORD PTR [rsp+176], xmm0
    mov QWORD PTR [rsp+64], r14
volatile_actor_wait:
    cmp DWORD PTR [rbx+28], 0
    jne volatile_actor_exit
    cmp DWORD PTR [rbx+20], r13d
    je volatile_actor_run
    pause
    jmp volatile_actor_wait
volatile_actor_run:
    xorps xmm0, xmm0
    movdqu XMMWORD PTR [rsp+32], xmm0
    lea rcx, [rsp+32]
    lea rdx, [rsp+64]
    call rdi
    mov r10, r13
    dec r10
    shl r10, 6
    add r10, rsi
    mov r11, r15
    shl r11, 5
    add r10, r11
    mov QWORD PTR [r10], rax
    movdqu xmm0, XMMWORD PTR [rsp+32]
    movdqu XMMWORD PTR [r10+8], xmm0
    mov QWORD PTR [r10+24], 0
    cmp DWORD PTR [rsp+32], 0
    jne volatile_actor_error
    cmp DWORD PTR [rsp+44], 0
    je volatile_actor_finish
volatile_actor_error:
    mov DWORD PTR [rbx+64], 13
volatile_actor_finish:
    lock inc DWORD PTR [rbx+24]
    inc r13d
    cmp r13d, r12d
    jbe volatile_actor_wait
volatile_actor_exit:
    xor eax, eax
    add rsp, 224
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
volatile_actor ENDP

boom_volatile_stress PROC FRAME
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
    sub rsp, 640
    .allocstack 640
    .endprolog
    test rcx, rcx
    jz volatile_invalid
    test r8, r8
    jz volatile_invalid
    test edx, edx
    jz volatile_invalid
    cmp edx, 1000000
    ja volatile_invalid
    cmp r9d, 2147483645
    ja volatile_invalid
    lea rbx, [rsp+64]
    xorps xmm0, xmm0
    movdqu XMMWORD PTR [rbx], xmm0
    movdqu XMMWORD PTR [rbx+16], xmm0
    movdqu XMMWORD PTR [rbx+32], xmm0
    movdqu XMMWORD PTR [rbx+48], xmm0
    movdqu XMMWORD PTR [rbx+64], xmm0
    movdqu XMMWORD PTR [rbx+80], xmm0
    movdqu XMMWORD PTR [rbx+96], xmm0
    movdqu XMMWORD PTR [rbx+112], xmm0
    mov QWORD PTR [rbx], rcx
    mov QWORD PTR [rbx+8], r8
    mov DWORD PTR [rbx+16], edx
    mov DWORD PTR [rbx+32], r9d
    mov rdi, rcx
    mov r12d, edx
    ; Task records at192/224. Native thread mode and output index are immutable.
    mov QWORD PTR [rsp+192], rbx
    lea eax, [r9d+1]
    mov DWORD PTR [rsp+200], eax
    mov DWORD PTR [rsp+204], 0
    mov QWORD PTR [rsp+224], rbx
    inc eax
    mov DWORD PTR [rsp+232], eax
    mov DWORD PTR [rsp+236], 1
    call GetTickCount64
    add rax, 30000
    mov r14, rax
    xor ecx, ecx
    xor edx, edx
    lea r8, volatile_actor
    lea r9, [rsp+192]
    mov QWORD PTR [rsp+32], 0
    mov QWORD PTR [rsp+40], 0
    call CreateThread
    test rax, rax
    jz volatile_thread_failed
    mov QWORD PTR [rbx+40], rax
    xor ecx, ecx
    xor edx, edx
    lea r8, volatile_actor
    lea r9, [rsp+224]
    mov QWORD PTR [rsp+32], 0
    mov QWORD PTR [rsp+40], 0
    call CreateThread
    test rax, rax
    jz volatile_thread_failed
    mov QWORD PTR [rbx+48], rax
    xorps xmm0, xmm0
    movdqu XMMWORD PTR [rsp+288], xmm0
    movdqu XMMWORD PTR [rsp+304], xmm0
    movdqu XMMWORD PTR [rsp+320], xmm0
    movdqu XMMWORD PTR [rsp+336], xmm0
    movdqu XMMWORD PTR [rsp+352], xmm0
    movdqu XMMWORD PTR [rsp+368], xmm0
    movdqu XMMWORD PTR [rsp+384], xmm0
    movdqu XMMWORD PTR [rsp+400], xmm0
    mov eax, DWORD PTR [rbx+32]
    mov QWORD PTR [rsp+288], rax
    mov r13d, 1
    xor r15d, r15d
volatile_round:
    xorps xmm0, xmm0
    movdqu XMMWORD PTR [rsp+256], xmm0
    lea rcx, [rsp+256]
    lea rdx, [rsp+288]
    call rdi
    cmp DWORD PTR [rsp+256], 0
    jne volatile_reset_failed
    cmp DWORD PTR [rsp+268], 0
    jne volatile_reset_failed
    mov DWORD PTR [rbx+24], 0
    mov eax, r13d
    xchg DWORD PTR [rbx+20], eax
volatile_wait:
    cmp DWORD PTR [rbx+64], 0
    jne volatile_cleanup
    cmp DWORD PTR [rbx+24], 2
    je volatile_round_done
    pause
    inc r15d
    test r15d, 4095
    jnz volatile_wait
    call GetTickCount64
    cmp rax, r14
    jbe volatile_wait
    mov DWORD PTR [rbx+64], 1460
    jmp volatile_cleanup
volatile_round_done:
    inc r13d
    cmp r13d, r12d
    jbe volatile_round
    jmp volatile_cleanup
volatile_thread_failed:
    mov DWORD PTR [rbx+64], 8
    jmp volatile_cleanup
volatile_reset_failed:
    mov DWORD PTR [rbx+64], 13
volatile_cleanup:
    mov eax, 1
    xchg DWORD PTR [rbx+28], eax
    mov rcx, QWORD PTR [rbx+40]
    test rcx, rcx
    jz volatile_cleanup_second
    mov edx, -1
    call WaitForSingleObject
    mov rcx, QWORD PTR [rbx+40]
    call CloseHandle
volatile_cleanup_second:
    mov rcx, QWORD PTR [rbx+48]
    test rcx, rcx
    jz volatile_cleanup_done
    mov edx, -1
    call WaitForSingleObject
    mov rcx, QWORD PTR [rbx+48]
    call CloseHandle
volatile_cleanup_done:
    mov eax, DWORD PTR [rbx+64]
    jmp volatile_done
volatile_invalid:
    mov eax, 87
volatile_done:
    add rsp, 640
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_volatile_stress ENDP
END
