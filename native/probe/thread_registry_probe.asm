; Test adapters only. The workload, failure and exit hooks execute AOT Java.
; User96: registry0,run8,failure16,exit24,mainCount32,failureCount40,
; exitCount48,badCurrent56,entered64,release72,badFP80,abrupt88,resultOffset96.
option casemap:none
EXTERN boom_threads_current:PROC
EXTERN boom_threads_next_id:PROC
EXTERN SetEvent:PROC
EXTERN WaitForSingleObject:PROC
EXTERN ExitThread:PROC
PUBLIC boom_thread_test_main
PUBLIC boom_thread_test_failure
PUBLIC boom_thread_test_exit
PUBLIC boom_thread_test_id_job
PUBLIC boom_thread_test_publish
PUBLIC boom_thread_test_rollback
PUBLIC boom_thread_test_publication_main
PUBLIC boom_thread_test_publication_exit
PUBLIC boom_thread_test_publication_failure
.code
thread_test_current PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rcx,QWORD PTR [rsi]
    call boom_threads_current
    cmp rax,QWORD PTR [rbx+40]
    je thread_test_current_ok
    lock inc QWORD PTR [rsi+56]
thread_test_current_ok:
    stmxcsr DWORD PTR [rsp+32]
    cmp DWORD PTR [rsp+32],01F80h
    je thread_test_fp_ok
    lock inc QWORD PTR [rsi+80]
thread_test_fp_ok:
    add rsp,40
    pop rsi
    pop rbx
    ret
thread_test_current ENDP
boom_thread_test_main PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    call thread_test_current
    lock inc QWORD PTR [rsi+32]
    mov rcx,QWORD PTR [rsi+64]
    test rcx,rcx
    jz thread_test_main_gate_done
    call SetEvent
    mov rcx,QWORD PTR [rsi+72]
    mov edx,20000
    call WaitForSingleObject
    test eax,eax
    jnz thread_test_main_wait_error
thread_test_main_gate_done:
    cmp DWORD PTR [rsi+88],0
    jne thread_test_main_abrupt
    mov QWORD PTR [rbx+160],1
    mov rax,QWORD PTR [rbx+40]
    mov QWORD PTR [rbx+168],rax
    lea rcx,[rbx+96]
    lea rdx,[rbx+160]
    call QWORD PTR [rsi+8]
    mov r10,QWORD PTR [rbx+40]
    mov eax,DWORD PTR [rsi+96]
    mov rax,QWORD PTR [r10+rax]
    mov QWORD PTR [rbx+88],rax
    mov rcx,rbx
    mov rdx,rsi
    call thread_test_current
    mov eax,DWORD PTR [rbx+96]
    jmp thread_test_main_done
thread_test_main_wait_error:
    mov eax,1460
    jmp thread_test_main_done
thread_test_main_abrupt:
    mov ecx,17
    call ExitThread
    int 3
thread_test_main_done:
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_thread_test_main ENDP
boom_thread_test_failure PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,56
    .allocstack 56
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    call thread_test_current
    lock inc QWORD PTR [rsi+40]
    mov QWORD PTR [rbx+160],2
    xor eax,eax
    mov QWORD PTR [rsp+32],rax
    mov QWORD PTR [rsp+40],rax
    lea rcx,[rsp+32]
    lea rdx,[rbx+160]
    call QWORD PTR [rsi+16]
    mov eax,DWORD PTR [rsp+32]
    test DWORD PTR [rsi+100],1
    jz thread_test_failure_done
    mov eax,12345
thread_test_failure_done:
    add rsp,56
    pop rsi
    pop rbx
    ret
boom_thread_test_failure ENDP
boom_thread_test_exit PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,56
    .allocstack 56
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    call thread_test_current
    lock inc QWORD PTR [rsi+48]
    mov QWORD PTR [rbx+160],3
    xor eax,eax
    mov QWORD PTR [rsp+32],rax
    mov QWORD PTR [rsp+40],rax
    lea rcx,[rsp+32]
    lea rdx,[rbx+160]
    call QWORD PTR [rsi+24]
    mov eax,DWORD PTR [rsp+32]
    test DWORD PTR [rsi+100],2
    jz thread_test_exit_done
    mov eax,54321
thread_test_exit_done:
    add rsp,56
    pop rsi
    pop rbx
    ret
boom_thread_test_exit ENDP
boom_thread_test_id_job PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rcx,QWORD PTR [rdx]
    call boom_threads_next_id
    add rsp,40
    ret
boom_thread_test_id_job ENDP
; Publication test storage is an explicit raw VM fixture, not a Thread oop.
; User: registry0,published8,ran16,bad24,rolledBack32,exited40.
; Root payload: peer0,state8. VM publication callbacks never reenter registry.
boom_thread_test_publish PROC
    mov rax,QWORD PTR [rcx+40]
    mov QWORD PTR [rax],rcx
    mov QWORD PTR [rax+8],4
    lock inc QWORD PTR [rdx+8]
    ret
boom_thread_test_publish ENDP
boom_thread_test_rollback PROC
    mov rax,QWORD PTR [rcx+40]
    mov QWORD PTR [rax],0
    mov QWORD PTR [rax+8],0
    lock inc QWORD PTR [rdx+32]
    ret
boom_thread_test_rollback ENDP
boom_thread_test_publication_main PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    lock inc QWORD PTR [rsi+16]
    mov rax,QWORD PTR [rbx+40]
    cmp QWORD PTR [rax],rbx
    jne thread_publication_bad
    cmp QWORD PTR [rax+8],4
    jne thread_publication_bad
    mov rcx,QWORD PTR [rsi]
    call boom_threads_current
    cmp rax,QWORD PTR [rbx+40]
    jne thread_publication_bad
    xor eax,eax
    jmp thread_publication_done
thread_publication_bad:
    lock inc QWORD PTR [rsi+24]
    mov DWORD PTR [rbx+96],7
    mov eax,7
thread_publication_done:
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_thread_test_publication_main ENDP
boom_thread_test_publication_exit PROC
    mov rax,QWORD PTR [rcx+40]
    mov QWORD PTR [rax],0
    mov QWORD PTR [rax+8],2
    lock inc QWORD PTR [rdx+40]
    xor eax,eax
    ret
boom_thread_test_publication_exit ENDP
boom_thread_test_publication_failure PROC
    lock inc QWORD PTR [rdx+24]
    mov eax,7
    ret
boom_thread_test_publication_failure ENDP
END
