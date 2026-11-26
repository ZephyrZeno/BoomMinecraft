; Assembly-only tuning for repeated, independent homogeneous task batches.
; Every submitted record runs exactly once. No calibration replay of game logic.
; Candidate budgets: 1,2,4,...,max (up to 64), two real batches each.
; Normalize QPC elapsed ticks per record, take the better of two samples, then
; prefer the smallest budget within 10% of the measured minimum. Explicit reset
; is required when the workload changes; changing the kernel resets it too.
; This is not a Java-thread scheduler or proof that arbitrary game work is parallel.
option casemap:none
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN QueryPerformanceCounter:PROC
EXTERN boom_pool_create:PROC
EXTERN boom_pool_run_budget:PROC
EXTERN boom_pool_destroy:PROC
PUBLIC boom_scheduler_create
PUBLIC boom_scheduler_run
PUBLIC boom_scheduler_budget
PUBLIC boom_scheduler_reset
PUBLIC boom_scheduler_destroy
SCHED_MAGIC EQU 053434844h
; magic0,busy4,pool8,max16,last20,candidates24,stage32,selected36
; minCost64[7],budgets128[7],kernel176. Storage is outside Java heap budget.
.code

boom_scheduler_create PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp, 40
    .allocstack 40
    .endprolog
    cmp ecx, 1
    jb sched_create_fail
    cmp ecx, 64
    ja sched_create_fail
    mov esi, ecx
    call boom_pool_create
    test rax, rax
    jz sched_create_fail
    mov rbx, rax
    xor ecx, ecx
    mov edx, 4096
    mov r8d, 03000h
    mov r9d, 4
    call VirtualAlloc
    test rax, rax
    jz sched_create_cleanup
    mov DWORD PTR [rax], SCHED_MAGIC
    mov QWORD PTR [rax+8], rbx
    mov DWORD PTR [rax+16], esi
    mov DWORD PTR [rax+20], 1
    mov DWORD PTR [rax+36], 1
    ; Pool creation may gracefully degrade after an OS thread allocation failure.
    mov esi, DWORD PTR [rbx+4]
    mov DWORD PTR [rax+16], esi
    xor edx, edx
    mov ecx, 1
sched_create_candidate:
    mov DWORD PTR [rax+rdx*4+128], ecx
    inc edx
    cmp ecx, esi
    jae sched_create_ready
    shl ecx, 1
    cmp ecx, esi
    cmova ecx, esi
    jmp sched_create_candidate
sched_create_ready:
    mov DWORD PTR [rax+24], edx
    jmp sched_create_done
sched_create_cleanup:
    mov rcx, rbx
    call boom_pool_destroy
sched_create_fail:
    xor eax, eax
sched_create_done:
    add rsp, 40
    pop rsi
    pop rbx
    ret
boom_scheduler_create ENDP

; run(state,kernel,argv128,output32,count) -> Win32 status.
boom_scheduler_run PROC FRAME
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
    sub rsp, 72
    .allocstack 72
    .endprolog
    test rcx, rcx
    jz sched_run_invalid
    cmp DWORD PTR [rcx], SCHED_MAGIC
    jne sched_run_invalid
    mov rbx, rcx
    mov rsi, rdx
    mov rdi, r8
    mov r12, r9
    mov r14d, DWORD PTR [rsp+160]
    xor eax, eax
    mov edx, 1
    lock cmpxchg DWORD PTR [rbx+4], edx
    jne sched_run_busy
    cmp rsi, QWORD PTR [rbx+176]
    je sched_kernel_same
    mov QWORD PTR [rbx+176], rsi
    mov DWORD PTR [rbx+32], 0
    mov DWORD PTR [rbx+36], 1
    xor ecx, ecx
sched_clear_costs:
    mov QWORD PTR [rbx+rcx*8+64], 0
    inc ecx
    cmp ecx, 7
    jb sched_clear_costs
sched_kernel_same:
    mov eax, DWORD PTR [rbx+32]
    shr eax, 1
    mov edx, DWORD PTR [rbx+36]
    cmp eax, DWORD PTR [rbx+24]
    jae sched_budget_ready
    mov edx, DWORD PTR [rbx+rax*4+128]
sched_budget_ready:
    cmp r14d, 1024
    jae sched_profile_batch
    mov edx, 1
sched_profile_batch:
    mov DWORD PTR [rbx+20], edx
    mov DWORD PTR [rsp+40], edx
    lea rcx, [rsp+48]
    call QueryPerformanceCounter
    mov DWORD PTR [rsp+64], eax
    mov rcx, QWORD PTR [rbx+8]
    mov rdx, rsi
    mov r8, rdi
    mov r9, r12
    mov DWORD PTR [rsp+32], r14d
    call boom_pool_run_budget
    mov r13d, eax
    lea rcx, [rsp+56]
    call QueryPerformanceCounter
    test r13d, r13d
    jnz sched_run_release
    test eax, eax
    jz sched_run_release
    cmp DWORD PTR [rsp+64], 0
    je sched_run_release
    cmp r14d, 1024
    jb sched_run_release
    mov ecx, DWORD PTR [rbx+32]
    shr ecx, 1
    cmp ecx, DWORD PTR [rbx+24]
    jae sched_run_release
    mov rax, QWORD PTR [rsp+56]
    sub rax, QWORD PTR [rsp+48]
    jbe sched_run_release
    mov r10d, 1024
    mul r10
    cmp rdx, r14
    jae sched_run_release ; avoid quotient overflow on an extreme elapsed time
    div r14
    test rax, rax
    jnz sched_cost_nonzero
    inc eax
sched_cost_nonzero:
    mov rdx, QWORD PTR [rbx+rcx*8+64]
    test rdx, rdx
    jz sched_save_cost
    cmp rax, rdx
    cmova rax, rdx
sched_save_cost:
    mov QWORD PTR [rbx+rcx*8+64], rax
    inc DWORD PTR [rbx+32]
    mov eax, DWORD PTR [rbx+24]
    add eax, eax
    cmp DWORD PTR [rbx+32], eax
    jb sched_run_release
    xor ecx, ecx
    mov r10, -1
sched_find_min:
    mov rax, QWORD PTR [rbx+rcx*8+64]
    cmp rax, r10
    cmovb r10, rax
    inc ecx
    cmp ecx, DWORD PTR [rbx+24]
    jb sched_find_min
    mov rax, r10
    xor edx, edx
    mov ecx, 10
    div rcx
    add r10, rax
    jnc sched_threshold_ready
    mov r10, -1
sched_threshold_ready:
    xor ecx, ecx
sched_choose_budget:
    cmp QWORD PTR [rbx+rcx*8+64], r10
    jbe sched_selected
    inc ecx
    jmp sched_choose_budget
sched_selected:
    mov eax, DWORD PTR [rbx+rcx*4+128]
    mov DWORD PTR [rbx+36], eax
sched_run_release:
    mov DWORD PTR [rbx+4], 0
    mov eax, r13d
    jmp sched_run_done
sched_run_busy:
    mov eax, 170
    jmp sched_run_done
sched_run_invalid:
    mov eax, 87
sched_run_done:
    add rsp, 72
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_scheduler_run ENDP

boom_scheduler_budget PROC
    xor eax, eax
    test rcx, rcx
    jz sched_budget_done
    cmp DWORD PTR [rcx], SCHED_MAGIC
    jne sched_budget_done
    mov eax, DWORD PTR [rcx+20]
sched_budget_done:
    ret
boom_scheduler_budget ENDP

boom_scheduler_reset PROC
    test rcx, rcx
    jz sched_reset_invalid
    cmp DWORD PTR [rcx], SCHED_MAGIC
    jne sched_reset_invalid
    xor eax, eax
    mov edx, 1
    lock cmpxchg DWORD PTR [rcx+4], edx
    jne sched_reset_busy
    mov QWORD PTR [rcx+176], 0
    mov DWORD PTR [rcx+32], 0
    mov DWORD PTR [rcx+36], 1
    mov DWORD PTR [rcx+20], 1
    mov DWORD PTR [rcx+4], 0
    xor eax, eax
    ret
sched_reset_busy:
    mov eax, 170
    ret
sched_reset_invalid:
    mov eax, 87
    ret
boom_scheduler_reset ENDP

boom_scheduler_destroy PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp, 32
    .allocstack 32
    .endprolog
    test rcx, rcx
    jz sched_destroy_invalid
    cmp DWORD PTR [rcx], SCHED_MAGIC
    jne sched_destroy_invalid
    mov rbx, rcx
    xor eax, eax
    mov edx, 1
    lock cmpxchg DWORD PTR [rbx+4], edx
    jne sched_destroy_busy
    mov rcx, QWORD PTR [rbx+8]
    call boom_pool_destroy
    test eax, eax
    jnz sched_destroy_unlock
    mov DWORD PTR [rbx], 0
    mov rcx, rbx
    xor edx, edx
    mov r8d, 08000h
    call VirtualFree
    test eax, eax
    jz sched_destroy_free_fail
    xor eax, eax
    jmp sched_destroy_done
sched_destroy_free_fail:
    mov eax, 31
    jmp sched_destroy_done
sched_destroy_unlock:
    mov DWORD PTR [rbx+4], 0
    jmp sched_destroy_done
sched_destroy_invalid:
    mov eax, 87
    jmp sched_destroy_done
sched_destroy_busy:
    mov eax, 170
sched_destroy_done:
    add rsp, 32
    pop rbx
    ret
boom_scheduler_destroy ENDP
END
