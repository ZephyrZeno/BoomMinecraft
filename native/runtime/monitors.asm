; Reentrant object monitors for one managed heap, entirely MASM.
; enter(heap RCX, object RDX, Context16 R8) / exit(same) -> 0 or exception kind.
; Heap ABI1 extended fields: active-list96, registry-lock104, monitor-ABI108,
; outstanding acquisitions/waiters112, reusable-node-list120.
; Node payload32: strong object0, next8, owner16, depth20, waiters24, reserved28.
; Nodes are ordinary in-budget allocations. Idle nodes clear their object and are
; reused; quiescent collection drops the idle list. No global/striped object lock.
; Registry lock order is registry -> allocator. GC takes the same order and refuses
; outstanding monitors. This is not an automatic GC/Java safepoint implementation.
; Native notify/notifyAll implement the proven empty-wait-set case only.
; Object.wait and Java interruption remain unavailable; reserved28 must be zero.
option casemap:none
EXTERN GetCurrentThreadId:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
EXTERN boom_heap_alloc:PROC
EXTERN boom_heap_contains:PROC
PUBLIC boom_monitor_enter
PUBLIC boom_monitor_exit
PUBLIC boom_monitor_notify
PUBLIC boom_monitor_notify_all
.code
monitor_registry_lock PROC
    mov eax, 1
    xchg DWORD PTR [rcx+104], eax
    test eax, eax
    jz monitor_registry_locked
monitor_registry_spin:
    pause
    cmp DWORD PTR [rcx+104], 0
    jne monitor_registry_spin
    jmp monitor_registry_lock
monitor_registry_locked:
    ret
monitor_registry_lock ENDP

boom_monitor_enter PROC FRAME
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
    sub rsp, 48
    .allocstack 48
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov rdi, r8
    test rdi, rdi
    jz monitor_enter_noctx
    mov eax, DWORD PTR [rdi]
    test eax, eax
    jnz monitor_enter_done
    test rsi, rsi
    jz monitor_enter_null
    test rbx, rbx
    jz monitor_enter_bad
    cmp DWORD PTR [rbx], 048454150h
    jne monitor_enter_bad
    cmp DWORD PTR [rbx+4], 1
    jne monitor_enter_bad
    cmp DWORD PTR [rbx+108], 1
    jne monitor_enter_bad
    lea rax, [rbx+160]
    cmp rsi, rax
    jb monitor_enter_bad
    cmp rsi, QWORD PTR [rbx+24]
    ja monitor_enter_bad
    test sil, 15
    jnz monitor_enter_bad
    mov eax, DWORD PTR [rsi-24]
    and eax, 0FFFFFFFDh
    cmp eax, 0B00B0001h
    jne monitor_enter_bad
    call GetCurrentThreadId
    mov r12d, eax
    xor r14d, r14d
monitor_enter_retry:
    mov rcx, rbx
    call monitor_registry_lock
    mov r13, QWORD PTR [rbx+96]
monitor_enter_find:
    test r13, r13
    jz monitor_enter_new
    cmp QWORD PTR [r13], rsi
    je monitor_enter_found
    mov r13, QWORD PTR [r13+8]
    jmp monitor_enter_find
monitor_enter_found:
    mov eax, DWORD PTR [r13+16]
    test eax, eax
    jz monitor_enter_claim
    cmp eax, r12d
    je monitor_enter_recursive
    mov DWORD PTR [rsp+40], eax
    test r14d, r14d
    jnz monitor_enter_sleep
    cmp DWORD PTR [r13+24], 07FFFFFFFh
    jae monitor_enter_unlock_bad
    inc DWORD PTR [r13+24]
    inc QWORD PTR [rbx+112]
    mov r14d, 1
monitor_enter_sleep:
    mov DWORD PTR [rbx+104], 0
    lea rcx, [r13+16]
    lea rdx, [rsp+40]
    mov r8d, 4
    mov r9d, -1
    call WaitOnAddress
    ; Wait failures and spurious wakes recheck the owner under the registry lock.
    jmp monitor_enter_retry
monitor_enter_claim:
    test r14d, r14d
    jz monitor_enter_fresh_claim
    dec DWORD PTR [r13+24]
    jmp monitor_enter_set_owner
monitor_enter_fresh_claim:
    inc QWORD PTR [rbx+112]
monitor_enter_set_owner:
    mov DWORD PTR [r13+16], r12d
    mov DWORD PTR [r13+20], 1
    jmp monitor_enter_unlock_ok
monitor_enter_recursive:
    cmp DWORD PTR [r13+20], 0FFFFFFFFh
    je monitor_enter_unlock_bad
    inc DWORD PTR [r13+20]
    inc QWORD PTR [rbx+112]
    jmp monitor_enter_unlock_ok
monitor_enter_new:
    ; A registered waiter always keeps its node on the active list.
    test r14d, r14d
    jnz monitor_enter_unlock_bad
    mov r13, QWORD PTR [rbx+120]
    test r13, r13
    jz monitor_enter_allocate
    mov rax, QWORD PTR [r13+8]
    mov QWORD PTR [rbx+120], rax
    jmp monitor_enter_publish
monitor_enter_allocate:
    mov rcx, rbx
    mov edx, 32
    mov r8d, 2
    mov r9d, 04D4F4E52h
    call boom_heap_alloc
    test rax, rax
    jz monitor_enter_oom
    mov r13, rax
monitor_enter_publish:
    mov QWORD PTR [r13], rsi
    mov rax, QWORD PTR [rbx+96]
    mov QWORD PTR [r13+8], rax
    mov DWORD PTR [r13+24], 0
    mov DWORD PTR [r13+28], 0
    mov QWORD PTR [rbx+96], r13
    inc QWORD PTR [rbx+112]
    jmp monitor_enter_set_owner
monitor_enter_unlock_ok:
    mov DWORD PTR [rbx+104], 0
    xor eax, eax
    jmp monitor_enter_done
monitor_enter_oom:
    mov DWORD PTR [rbx+104], 0
    mov eax, 3
    jmp monitor_enter_error
monitor_enter_unlock_bad:
    mov DWORD PTR [rbx+104], 0
monitor_enter_bad:
    mov eax, 7
    jmp monitor_enter_error
monitor_enter_null:
    mov eax, 4
monitor_enter_error:
    mov DWORD PTR [rdi], eax
    jmp monitor_enter_done
monitor_enter_noctx:
    mov eax, 7
monitor_enter_done:
    add rsp, 48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_monitor_enter ENDP

boom_monitor_exit PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    sub rsp, 40
    .allocstack 40
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov rdi, r8
    test rdi, rdi
    jz monitor_exit_noctx
    test rsi, rsi
    jz monitor_exit_null
    test rbx, rbx
    jz monitor_exit_bad
    cmp DWORD PTR [rbx], 048454150h
    jne monitor_exit_bad
    cmp DWORD PTR [rbx+4], 1
    jne monitor_exit_bad
    cmp DWORD PTR [rbx+108], 1
    jne monitor_exit_bad
    call GetCurrentThreadId
    mov DWORD PTR [rsp+32], eax
    mov rcx, rbx
    call monitor_registry_lock
    lea r12, [rbx+96]
    mov r10, QWORD PTR [r12]
monitor_exit_find:
    test r10, r10
    jz monitor_exit_not_owned
    cmp QWORD PTR [r10], rsi
    je monitor_exit_found
    lea r12, [r10+8]
    mov r10, QWORD PTR [r12]
    jmp monitor_exit_find
monitor_exit_found:
    mov eax, DWORD PTR [rsp+32]
    cmp DWORD PTR [r10+16], eax
    jne monitor_exit_not_owned
    cmp DWORD PTR [r10+20], 0
    je monitor_exit_unlock_bad
    cmp QWORD PTR [rbx+112], 0
    je monitor_exit_unlock_bad
    dec DWORD PTR [r10+20]
    dec QWORD PTR [rbx+112]
    cmp DWORD PTR [r10+20], 0
    jne monitor_exit_unlock_ok
    mov DWORD PTR [r10+16], 0
    cmp DWORD PTR [r10+24], 0
    jne monitor_exit_wake
    mov rax, QWORD PTR [r10+8]
    mov QWORD PTR [r12], rax
    mov QWORD PTR [r10], 0
    mov rax, QWORD PTR [rbx+120]
    mov QWORD PTR [r10+8], rax
    mov QWORD PTR [rbx+120], r10
    jmp monitor_exit_unlock_ok
monitor_exit_wake:
    lea rcx, [r10+16]
    mov DWORD PTR [rbx+104], 0
    call WakeByAddressAll
    xor eax, eax
    jmp monitor_exit_done
monitor_exit_unlock_ok:
    mov DWORD PTR [rbx+104], 0
    xor eax, eax
    jmp monitor_exit_done
monitor_exit_not_owned:
    mov DWORD PTR [rbx+104], 0
    mov eax, 17
    jmp monitor_exit_error
monitor_exit_unlock_bad:
    mov DWORD PTR [rbx+104], 0
monitor_exit_bad:
    mov eax, 7
    jmp monitor_exit_error
monitor_exit_null:
    mov eax, 4
monitor_exit_error:
    mov DWORD PTR [rdi], eax
    jmp monitor_exit_done
monitor_exit_noctx:
    mov eax, 7
monitor_exit_done:
    add rsp, 40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_monitor_exit ENDP
; heap RCX,object RDX,Context32 R8 -> kind. No Java wait service can be linked
; in this ABI1 module. Unknown nonempty wait metadata fails explicitly.
boom_monitor_notify_all PROC
    jmp boom_monitor_notify
boom_monitor_notify_all ENDP
boom_monitor_notify PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    test rdi,rdi
    jz monitor_notify_noctx
    mov eax,DWORD PTR [rdi]
    test eax,eax
    jnz monitor_notify_done
    test rsi,rsi
    jz monitor_notify_null
    test rbx,rbx
    jz monitor_notify_bad
    cmp DWORD PTR [rbx],048454150h
    jne monitor_notify_bad
    cmp DWORD PTR [rbx+4],1
    jne monitor_notify_bad
    cmp DWORD PTR [rbx+108],1
    jne monitor_notify_bad
    call boom_heap_contains
    test eax,eax
    jz monitor_notify_bad
    call GetCurrentThreadId
    mov r12d,eax
    mov rcx,rbx
    call monitor_registry_lock
    mov r10,QWORD PTR [rbx+96]
monitor_notify_find:
    test r10,r10
    jz monitor_notify_unowned
    cmp QWORD PTR [r10],rsi
    je monitor_notify_found
    mov r10,QWORD PTR [r10+8]
    jmp monitor_notify_find
monitor_notify_found:
    cmp DWORD PTR [r10+16],r12d
    jne monitor_notify_unowned
    cmp DWORD PTR [r10+20],0
    je monitor_notify_unlock_bad
    cmp QWORD PTR [rbx+112],0
    je monitor_notify_unlock_bad
    cmp DWORD PTR [r10+28],0
    jne monitor_notify_wait_unavailable
    xor eax,eax
    jmp monitor_notify_unlock
monitor_notify_unowned:
    mov eax,17
    jmp monitor_notify_unlock
monitor_notify_wait_unavailable:
    mov eax,20
    jmp monitor_notify_unlock
monitor_notify_unlock_bad:
    mov eax,7
monitor_notify_unlock:
    mov DWORD PTR [rbx+104],0
    test eax,eax
    jz monitor_notify_done
    jmp monitor_notify_error
monitor_notify_null:
    mov eax,4
    jmp monitor_notify_error
monitor_notify_bad:
    mov eax,7
monitor_notify_error:
    mov DWORD PTR [rdi],eax
    jmp monitor_notify_done
monitor_notify_noctx:
    mov eax,7
monitor_notify_done:
    add rsp,40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_monitor_notify ENDP
END
