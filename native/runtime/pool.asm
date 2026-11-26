; Persistent game-side primitive executor. Handwritten MASM; Windows APIs only.
; create(jobs 1..64)->pool/NULL
; run(pool,kernel,argv128[],output32[],count)->0 / ERROR_BUSY / invalid parameter
; destroy(pool)->0 / ERROR_BUSY. Owner must not race destruction with new calls.
; Pool: magic0 jobs4 shutdown8 busy12, work context16..51, remaining52, done56.
; Child records at64, 32 bytes each: pool0, wake8, thread16, reserved24.
option casemap:none
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN CreateEventW:PROC
EXTERN SetEvent:PROC
EXTERN ResetEvent:PROC
EXTERN CreateThread:PROC
EXTERN WaitForSingleObject:PROC
EXTERN CloseHandle:PROC
EXTERN boom_worker:PROC
PUBLIC boom_pool_create
PUBLIC boom_pool_run
PUBLIC boom_pool_run_budget
PUBLIC boom_pool_destroy
.code

boom_pool_thread PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp, 40
    .allocstack 40
    .endprolog
    mov rsi, rcx
    mov rbx, QWORD PTR [rsi]
pool_thread_wait:
    mov rcx, QWORD PTR [rsi+8]
    mov edx, -1
    call WaitForSingleObject
    cmp DWORD PTR [rbx+8], 0
    jne pool_thread_exit
    lea rcx, [rbx+16]
    call boom_worker
    lock dec DWORD PTR [rbx+52]
    jnz pool_thread_wait
    mov rcx, QWORD PTR [rbx+56]
    call SetEvent
    jmp pool_thread_wait
pool_thread_exit:
    xor eax, eax
    add rsp, 40
    pop rsi
    pop rbx
    ret
boom_pool_thread ENDP

boom_pool_create PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp, 48
    .allocstack 48
    .endprolog
    cmp ecx, 1
    jb pool_create_null
    cmp ecx, 64
    ja pool_create_null
    mov edi, ecx
    xor ecx, ecx
    mov edx, 4096
    mov r8d, 03000h
    mov r9d, 4
    call VirtualAlloc
    test rax, rax
    jz pool_create_null
    mov rbx, rax
    mov DWORD PTR [rbx], 0424F4F4Dh
    mov DWORD PTR [rbx+4], 1
    mov DWORD PTR [rbx+48], 1
    xor ecx, ecx
    mov edx, 1
    xor r8d, r8d
    xor r9d, r9d
    call CreateEventW
    test rax, rax
    jz pool_create_free
    mov QWORD PTR [rbx+56], rax
    dec edi
    xor esi, esi
pool_create_child:
    cmp esi, edi
    jae pool_create_success
    xor ecx, ecx
    xor edx, edx
    xor r8d, r8d
    xor r9d, r9d
    call CreateEventW
    test rax, rax
    jz pool_create_success
    mov r10, rsi
    shl r10, 5
    lea r10, [rbx+r10+64]
    mov QWORD PTR [r10], rbx
    mov QWORD PTR [r10+8], rax
    xor ecx, ecx
    xor edx, edx
    lea r8, boom_pool_thread
    mov r9, r10
    mov QWORD PTR [rsp+32], 0
    mov QWORD PTR [rsp+40], 0
    call CreateThread
    test rax, rax
    jz pool_create_close_event
    mov r10, rsi
    shl r10, 5
    mov QWORD PTR [rbx+r10+80], rax
    inc esi
    inc DWORD PTR [rbx+4]
    jmp pool_create_child
pool_create_close_event:
    mov r10, rsi
    shl r10, 5
    mov rcx, QWORD PTR [rbx+r10+72]
    call CloseHandle
pool_create_success:
    mov rax, rbx
    jmp pool_create_done
pool_create_free:
    mov rcx, rbx
    xor edx, edx
    mov r8d, 08000h
    call VirtualFree
pool_create_null:
    xor eax, eax
pool_create_done:
    add rsp, 48
    pop rdi
    pop rsi
    pop rbx
    ret
boom_pool_create ENDP

boom_pool_run PROC
    xor r10d, r10d
    jmp boom_pool_run_common
boom_pool_run ENDP

; Same five arguments plus an active worker budget. Threads stay alive;
; only the requested number are woken. Caller counts toward that budget.
boom_pool_run_budget PROC
    mov r10d, DWORD PTR [rsp+48]
    cmp r10d, 1
    jb pool_budget_invalid
    cmp r10d, 64
    ja pool_budget_invalid
    jmp boom_pool_run_common
pool_budget_invalid:
    mov eax, 87
    ret
boom_pool_run_budget ENDP

boom_pool_run_common PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp, 32
    .allocstack 32
    .endprolog
    mov edi, r10d
    mov eax, DWORD PTR [rsp+96] ; original rsp+40
    test rcx, rcx
    jz pool_run_invalid
    cmp DWORD PTR [rcx], 0424F4F4Dh
    jne pool_run_invalid
    cmp DWORD PTR [rcx+8], 0
    jne pool_run_invalid
    cmp eax, 16777216
    ja pool_run_invalid
    test eax, eax
    jz pool_run_empty
    test rdx, rdx
    jz pool_run_invalid
    test r8, r8
    jz pool_run_invalid
    test r9, r9
    jz pool_run_invalid
    mov r10d, eax
    shl r10, 7
    add r10, r8
    jc pool_run_invalid
    mov r11d, eax
    shl r11, 5
    add r11, r9
    jc pool_run_invalid
    cmp r8, r11
    jae pool_run_disjoint
    cmp r9, r10
    jb pool_run_invalid
pool_run_disjoint:
    mov ebx, eax
    xor eax, eax
    mov r10d, 1
    lock cmpxchg DWORD PTR [rcx+12], r10d
    jne pool_run_busy
    mov DWORD PTR [rcx+40], ebx
    mov rbx, rcx
    mov QWORD PTR [rbx+16], rdx
    mov QWORD PTR [rbx+24], r8
    mov QWORD PTR [rbx+32], r9
    mov DWORD PTR [rbx+44], 0
    mov eax, DWORD PTR [rbx+4]
    test edi, edi
    cmovz edi, eax
    cmp edi, eax
    cmova edi, eax
    dec edi
    ; A single chunk never wakes the persistent workers.
    cmp DWORD PTR [rbx+40], 64
    jbe pool_run_caller_only
    test edi, edi
    jz pool_run_caller_only
    mov DWORD PTR [rbx+52], edi
    mov rcx, QWORD PTR [rbx+56]
    call ResetEvent
    xor esi, esi
pool_run_wake:
    mov r10, rsi
    shl r10, 5
    mov rcx, QWORD PTR [rbx+r10+72]
    call SetEvent
    inc esi
    cmp esi, edi
    jb pool_run_wake
    lea rcx, [rbx+16]
    call boom_worker
    mov rcx, QWORD PTR [rbx+56]
    mov edx, -1
    call WaitForSingleObject
    jmp pool_run_release
pool_run_caller_only:
    lea rcx, [rbx+16]
    call boom_worker
pool_run_release:
    mov DWORD PTR [rbx+12], 0
pool_run_empty:
    xor eax, eax
    jmp pool_run_done
pool_run_invalid:
    mov eax, 87
    jmp pool_run_done
pool_run_busy:
    mov eax, 170
pool_run_done:
    add rsp, 32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_pool_run_common ENDP

boom_pool_destroy PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp, 32
    .allocstack 32
    .endprolog
    test rcx, rcx
    jz pool_destroy_invalid
    cmp DWORD PTR [rcx], 0424F4F4Dh
    jne pool_destroy_invalid
    xor eax, eax
    mov r10d, 1
    lock cmpxchg DWORD PTR [rcx+12], r10d
    jne pool_destroy_busy
    mov rbx, rcx
    mov DWORD PTR [rbx+8], 1
    mov edi, DWORD PTR [rbx+4]
    dec edi
    xor esi, esi
pool_destroy_wake:
    cmp esi, edi
    jae pool_destroy_join_start
    mov r10, rsi
    shl r10, 5
    mov rcx, QWORD PTR [rbx+r10+72]
    call SetEvent
    inc esi
    jmp pool_destroy_wake
pool_destroy_join_start:
    xor esi, esi
pool_destroy_join:
    cmp esi, edi
    jae pool_destroy_free
    mov r10, rsi
    shl r10, 5
    mov rcx, QWORD PTR [rbx+r10+80]
    mov edx, -1
    call WaitForSingleObject
    mov r10, rsi
    shl r10, 5
    mov rcx, QWORD PTR [rbx+r10+80]
    call CloseHandle
    mov r10, rsi
    shl r10, 5
    mov rcx, QWORD PTR [rbx+r10+72]
    call CloseHandle
    inc esi
    jmp pool_destroy_join
pool_destroy_free:
    mov rcx, QWORD PTR [rbx+56]
    call CloseHandle
    mov rcx, rbx
    xor edx, edx
    mov r8d, 08000h
    call VirtualFree
    xor eax, eax
    jmp pool_destroy_done
pool_destroy_invalid:
    mov eax, 87
    jmp pool_destroy_done
pool_destroy_busy:
    mov eax, 170
pool_destroy_done:
    add rsp, 32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_pool_destroy ENDP
END
