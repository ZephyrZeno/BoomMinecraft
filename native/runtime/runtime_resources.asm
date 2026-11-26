; Runtime CPU/memory queries, original Runtime receiver, all execution MASM.
; RUNT64/1: heapCell8,typeMap16,RuntimeType24,policy32D=0,res36..63=0.
; Policy follows the default Windows processor-group policy; no JVM flag overrides.
option casemap:none
EXTERN GetCurrentProcess:PROC
EXTERN GetSystemInfo:PROC
EXTERN GetProcessAffinityMask:PROC
EXTERN GetProcessGroupAffinity:PROC
EXTERN IsProcessInJob:PROC
EXTERN QueryInformationJobObject:PROC
EXTERN GetLastError:PROC
EXTERN RtlGetVersion:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
PUBLIC boom_processor_count
PUBLIC boom_runtime_available_processors
PUBLIC boom_runtime_resource
.code
; In-register bit count, baseline x64 without requiring POPCNT/BMI.
processor_bits PROC
    xor eax,eax
processor_bit_loop:
    test rcx,rcx
    jz processor_bits_done
    lea rdx,[rcx-1]
    and rcx,rdx
    inc eax
    jmp processor_bit_loop
processor_bits_done:
    ret
processor_bits ENDP
; Context32 RCX -> positive Java int or zero with error. No guest/OS allocation.
boom_processor_count PROC FRAME
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
    sub rsp,1600
    .allocstack 1600
    .endprolog
    mov rbx,rcx
    test rbx,rbx
    jz processor_count_zero
    cmp DWORD PTR [rbx],0
    jne processor_count_zero
    lea rcx,[rsp+64]
    call GetSystemInfo
    mov esi,DWORD PTR [rsp+96]
    test esi,esi
    jz processor_count_internal
    call GetCurrentProcess
    mov r12,rax
    mov rcx,rax
    xor edx,edx
    lea r8,[rsp+112]
    mov DWORD PTR [rsp+112],0
    call IsProcessInJob
    test eax,eax
    jz processor_count_process
    cmp DWORD PTR [rsp+112],0
    je processor_count_process
    xor ecx,ecx
    mov edx,14
    lea r8,[rsp+512]
    mov r9d,1024
    lea rax,[rsp+116]
    mov DWORD PTR [rax],0
    mov QWORD PTR [rsp+32],rax
    call QueryInformationJobObject
    test eax,eax
    jz processor_count_job_failed
    mov ecx,DWORD PTR [rsp+116]
    test ecx,15
    jnz processor_count_internal
    cmp ecx,1024
    ja processor_count_unavailable
    shr ecx,4
    xor edi,edi
    xor r13d,r13d
    xor r10d,r10d
processor_job_groups:
    cmp r10d,ecx
    jae processor_job_counted
    mov eax,r10d
    shl rax,4
    mov r8,QWORD PTR [rsp+rax+512]
    test r8,r8
    jz processor_job_next
    inc r13d
processor_job_bits:
    lea r9,[r8-1]
    and r8,r9
    inc edi
    test r8,r8
    jnz processor_job_bits
processor_job_next:
    inc r10d
    jmp processor_job_groups
processor_job_counted:
    test edi,edi
    jz processor_count_process
    cmp r13d,1
    jbe processor_count_job_return
    ; On modern Windows the default VM policy uses its default group when a job
    ; spans multiple groups. Older Windows uses the job group sum.
    lea rdi,[rsp+160]
    xor eax,eax
    mov ecx,36
    rep stosq
    mov DWORD PTR [rsp+160],284
    lea rcx,[rsp+160]
    call RtlGetVersion
    test eax,eax
    jnz processor_count_process
    cmp DWORD PTR [rsp+164],10
    ja processor_count_process
    jb processor_count_old_job
    mov eax,DWORD PTR [rsp+172]
    cmp BYTE PTR [rsp+442],1
    jne processor_count_server
    cmp eax,22000
    jae processor_count_process
    jmp processor_count_old_job
processor_count_server:
    cmp eax,20348
    jae processor_count_process
processor_count_old_job:
    ; Sum was overwritten while clearing the version structure. Recompute.
    mov ecx,DWORD PTR [rsp+116]
    shr ecx,4
    xor edi,edi
    xor r10d,r10d
processor_old_sum:
    cmp r10d,ecx
    jae processor_count_job_return
    mov eax,r10d
    shl rax,4
    mov r8,QWORD PTR [rsp+rax+512]
processor_old_bits:
    test r8,r8
    jz processor_old_next
    lea r9,[r8-1]
    and r8,r9
    inc edi
    jmp processor_old_bits
processor_old_next:
    inc r10d
    jmp processor_old_sum
processor_count_job_return:
    mov eax,edi
    jmp processor_count_done
processor_count_job_failed:
    call GetLastError
    cmp eax,122
    jne processor_count_process
    cmp DWORD PTR [rsp+116],1024
    ja processor_count_unavailable
processor_count_process:
    mov WORD PTR [rsp+120],0
    mov rcx,r12
    lea rdx,[rsp+120]
    xor r8d,r8d
    call GetProcessGroupAffinity
    test eax,eax
    jnz processor_count_system
    call GetLastError
    cmp eax,122
    jne processor_count_system
    cmp WORD PTR [rsp+120],1
    jne processor_count_system
    mov rcx,r12
    lea rdx,[rsp+128]
    lea r8,[rsp+136]
    call GetProcessAffinityMask
    test eax,eax
    jz processor_count_system
    mov rcx,QWORD PTR [rsp+128]
    call processor_bits
    test eax,eax
    jnz processor_count_done
processor_count_system:
    mov eax,esi
    jmp processor_count_done
processor_count_internal:
    mov DWORD PTR [rbx],23
    jmp processor_count_zero
processor_count_unavailable:
    mov DWORD PTR [rbx],20
processor_count_zero:
    xor eax,eax
processor_count_done:
    add rsp,1600
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_processor_count ENDP
; Context32 RCX,argv{Runtime oop} RDX,CPUP64 R8 -> int.
boom_runtime_available_processors PROC
    xor r9d,r9d
    jmp boom_runtime_resource
boom_runtime_available_processors ENDP
boom_runtime_resource PROC FRAME
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
    mov r12d,r9d
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    test rbx,rbx
    jz processor_service_zero
    cmp DWORD PTR [rbx],0
    jne processor_service_zero
    test rsi,rsi
    jz processor_service_bad
    test rdi,rdi
    jz processor_service_bad
    cmp DWORD PTR [rdi],0544E5552h
    jne processor_service_bad
    cmp DWORD PTR [rdi+4],1
    jne processor_service_bad
    mov ecx,32
processor_service_reserved:
    cmp QWORD PTR [rdi+rcx],0
    jne processor_service_bad
    add ecx,8
    cmp ecx,64
    jb processor_service_reserved
    cmp QWORD PTR [rdi+8],0
    je processor_service_bad
    cmp QWORD PTR [rdi+16],0
    je processor_service_bad
    cmp QWORD PTR [rdi+24],0
    je processor_service_bad
    mov rdx,QWORD PTR [rsi]
    test rdx,rdx
    jz processor_service_null
    mov rax,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rax]
    test rcx,rcx
    jz processor_service_bad
    call boom_heap_contains
    test eax,eax
    jz processor_service_bad
    mov rcx,QWORD PTR [rsi]
    mov rdx,QWORD PTR [rdi+16]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne processor_service_zero
    cmp rax,QWORD PTR [rdi+24]
    jne processor_service_subtype
    cmp r12d,3
    ja processor_service_bad
    test r12d,r12d
    jz processor_service_cpu
    mov rax,QWORD PTR [rdi+8]
    mov rdx,QWORD PTR [rax]
    mov rax,QWORD PTR [rdx+16]
    cmp r12d,1
    jne processor_service_done
    mov r10,QWORD PTR [rdx+48]
    cmp r10,rax
    ja processor_service_bad
    sub rax,r10
    jmp processor_service_done
processor_service_cpu:
    mov rcx,rbx
    call boom_processor_count
    jmp processor_service_done
processor_service_subtype:
    mov rcx,rax
    mov rdx,QWORD PTR [rdi+24]
    call boom_type_assignable
    test eax,eax
    jz processor_service_bad
    mov DWORD PTR [rbx],20
    jmp processor_service_zero
processor_service_null:
    mov DWORD PTR [rbx],4
    jmp processor_service_zero
processor_service_bad:
    mov DWORD PTR [rbx],7
processor_service_zero:
    xor eax,eax
processor_service_done:
    add rsp,40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_runtime_resource ENDP
END
