; VM platform-thread bookkeeping. MASM and Windows APIs only.
; Not a replacement Thread constructor/run/exit implementation. Source adapters
; must provide the Java callbacks and maintain the original object fields.
; One registry per runtime module/process; heap remains owned by its caller.
; Registry page: magic0/abi4,heap8,head16,count24/max28,nextJavaId32,mainUsed40.
; GC root lease: frozen44,ownerOSId48. Live frames are not yet safepoints.
; Record page: magic0/abi4,registry8,next16,handle24,osId32,state36,
; rootObject40,JavaId48,main56,exit64,uncaught72,user80,result88,
; Context32@96,status128,exitStatus132,argv[16]@160.
; States: external1,starting2,running3,finished4,abnormal5.
; Start64: magic0/abi4,oop8,JavaId16,main24,exit32,uncaught40,user48,reserved56.
; Start88/2 adds publish56,rollback64,stackReserve72,reserved80 instead.
; Publication hooks are nonthrowing VM stores, called under threads_lock.
; They must not allocate, wait, invoke Java or reenter this registry.
; Callback(record RCX,user RDX)->DWORD status. Context and result are in record.
option casemap:none
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockShared:PROC
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN GetCurrentThreadId:PROC
EXTERN GetLastError:PROC
EXTERN SetLastError:PROC
EXTERN GetModuleHandleExW:PROC
EXTERN FlsAlloc:PROC
EXTERN FlsGetValue:PROC
EXTERN FlsSetValue:PROC
EXTERN CreateThread:PROC
EXTERN WaitForSingleObject:PROC
EXTERN CloseHandle:PROC
EXTERN DuplicateHandle:PROC
EXTERN OpenThread:PROC
EXTERN SetThreadPriority:PROC
PUBLIC boom_threads_create
PUBLIC boom_threads_destroy
PUBLIC boom_threads_next_id
PUBLIC boom_threads_id_address
PUBLIC boom_threads_id_memory
PUBLIC boom_threads_attach
PUBLIC boom_threads_detach
PUBLIC boom_threads_current
PUBLIC boom_threads_start
PUBLIC boom_threads_join
PUBLIC boom_threads_result
PUBLIC boom_threads_release
PUBLIC boom_threads_roots
PUBLIC boom_threads_roots_end
PUBLIC boom_threads_set_priority
.data
ALIGN 8
threads_lock QWORD 0
threads_active QWORD 0
threads_fls DWORD -1
.code
; create(heap,maxRecords)->registry/null. IDs begin at 2; main ID1 is reserved.
boom_threads_create PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rsi,rcx
    mov edi,edx
    xor ebx,ebx
    test rsi,rsi
    jz threads_create_invalid
    test edi,edi
    jz threads_create_invalid
    cmp edi,16384
    ja threads_create_invalid
    cmp DWORD PTR [rsi],048454150h
    jne threads_create_invalid
    cmp DWORD PTR [rsi+4],1
    jne threads_create_invalid
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    cmp QWORD PTR threads_active,0
    jne threads_create_busy
    mov ecx,5
    lea rdx,threads_fls_cleanup
    lea r8,[rsp+32]
    call GetModuleHandleExW
    test eax,eax
    jz threads_create_os_error
    cmp DWORD PTR threads_fls,-1
    jne threads_create_fls_ready
    lea rcx,threads_fls_cleanup
    call FlsAlloc
    cmp eax,-1
    je threads_create_os_error
    mov DWORD PTR threads_fls,eax
threads_create_fls_ready:
    xor ecx,ecx
    mov edx,4096
    mov r8d,03000h
    mov r9d,4
    call VirtualAlloc
    test rax,rax
    jz threads_create_os_error
    mov rbx,rax
    mov DWORD PTR [rax],054524547h
    mov DWORD PTR [rax+4],1
    mov QWORD PTR [rax+8],rsi
    mov DWORD PTR [rax+28],edi
    mov QWORD PTR [rax+32],2
    mov QWORD PTR threads_active,rax
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    mov rax,rbx
    jmp threads_create_done
threads_create_busy:
    mov ebx,183
    jmp threads_create_unlock_error
threads_create_os_error:
    call GetLastError
    mov ebx,eax
threads_create_unlock_error:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    mov ecx,ebx
    call SetLastError
    xor eax,eax
    jmp threads_create_done
threads_create_invalid:
    mov ecx,87
    call SetLastError
    xor eax,eax
threads_create_done:
    add rsp,48
    pop rdi
    pop rsi
    pop rbx
    ret
boom_threads_create ENDP

boom_threads_next_id PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    lea rcx,threads_lock
    call AcquireSRWLockShared
    test rbx,rbx
    jz threads_id_bad
    cmp QWORD PTR threads_active,rbx
    jne threads_id_bad
    mov rax,QWORD PTR [rbx+32]
threads_id_retry:
    test rax,rax
    jle threads_id_bad
    mov rdx,07FFFFFFFFFFFFFFFh
    cmp rax,rdx
    je threads_id_bad
    lea rdx,[rax+1]
    lock cmpxchg QWORD PTR [rbx+32],rdx
    jne threads_id_retry
    mov rbx,rax
    jmp threads_id_unlock
threads_id_bad:
    xor ebx,ebx
threads_id_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockShared
    mov rax,rbx
    add rsp,32
    pop rbx
    ret
boom_threads_next_id ENDP
boom_threads_id_address PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    lea rcx,threads_lock
    call AcquireSRWLockShared
    test rbx,rbx
    jz threads_address_bad
    cmp QWORD PTR threads_active,rbx
    jne threads_address_bad
    add rbx,32
    jmp threads_address_unlock
threads_address_bad:
    xor ebx,ebx
threads_address_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockShared
    mov rax,rbx
    add rsp,32
    pop rbx
    ret
boom_threads_id_address ENDP

; Private VM counter domain for original Unsafe Long operations. There is no
; arbitrary off-heap dereference. The shared registry lock covers validation,
; the entire access and its result capture, excluding concurrent destruction.
; (Context32, Unsafe argv, action0load/2volatile/4CAS/5exchange, owning heap).
boom_threads_id_memory PROC FRAME
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
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov r12d,r8d
    mov rdi,r9
    xor r13d,r13d
    test rbx,rbx
    jz threads_memory_done
    cmp DWORD PTR [rbx],0
    jne threads_memory_done
    test rsi,rsi
    jz threads_memory_bad
    cmp QWORD PTR [rsi+8],0
    jne threads_memory_bad
    cmp r12d,0
    je threads_memory_lock
    cmp r12d,2
    je threads_memory_lock
    cmp r12d,4
    je threads_memory_lock
    cmp r12d,5
    jne threads_memory_bad
threads_memory_lock:
    lea rcx,threads_lock
    call AcquireSRWLockShared
    mov r10,QWORD PTR threads_active
    test r10,r10
    jz threads_memory_reject
    cmp rdi,QWORD PTR [r10+8]
    jne threads_memory_reject
    add r10,32
    cmp r10,QWORD PTR [rsi+16]
    jne threads_memory_reject
    cmp r12d,4
    jae threads_memory_exchange
    cmp r12d,2
    jne threads_memory_load
    mfence
threads_memory_load:
    mov r13,QWORD PTR [r10]
    cmp r12d,2
    jne threads_memory_unlock
    mfence
    jmp threads_memory_unlock
threads_memory_exchange:
    mov rax,QWORD PTR [rsi+24]
    mov rdx,QWORD PTR [rsi+32]
    lock cmpxchg QWORD PTR [r10],rdx
    setz dl
    mov r13,rax
    cmp r12d,4
    jne threads_memory_unlock
    movzx r13d,dl
    jmp threads_memory_unlock
threads_memory_reject:
    mov DWORD PTR [rbx],20
threads_memory_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockShared
    jmp threads_memory_done
threads_memory_bad:
    mov DWORD PTR [rbx],20
threads_memory_done:
    mov rax,r13
    add rsp,32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_threads_id_memory ENDP

; Shared/exclusive global lock required. (registry,oop)->1 if complete owned block.
threads_owned PROC
    mov r8,QWORD PTR [rcx+8]
    mov rax,QWORD PTR [r8+16]
    test rax,rax
    jz threads_owned_bad
    cmp rax,040000000h
    ja threads_owned_bad
    lea r9,[r8+128]
    add rax,r9
    jc threads_owned_bad
    cmp rax,QWORD PTR [r8+24]
    jne threads_owned_bad
    lea r9,[r8+160]
    cmp rdx,r9
    jb threads_owned_bad
    cmp rdx,rax
    ja threads_owned_bad
    test dl,15
    jnz threads_owned_bad
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,0B00B0001h
    jne threads_owned_bad
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb threads_owned_bad
    test r10b,15
    jnz threads_owned_bad
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja threads_owned_bad
    add r10,rdx
    jc threads_owned_bad
    cmp r10,rax
    ja threads_owned_bad
    mov eax,1
    ret
threads_owned_bad:
    xor eax,eax
    ret
threads_owned ENDP

; Exclusive lock required. Allocate/insert a page with unique live oop/id.
; (registry RCX,oop RDX,id R8)->record/null. Caller validates id source/fields.
threads_insert PROC FRAME
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
    mov rdi,r8
    test rbx,rbx
    jz threads_insert_bad
    cmp QWORD PTR threads_active,rbx
    jne threads_insert_bad
    cmp DWORD PTR [rbx+44],0
    jne threads_insert_bad
    test rdi,rdi
    jle threads_insert_bad
    cmp rdi,QWORD PTR [rbx+32]
    jae threads_insert_bad
    mov eax,DWORD PTR [rbx+24]
    cmp eax,DWORD PTR [rbx+28]
    jae threads_insert_bad
    cmp rdi,1
    jne threads_insert_scan
    cmp DWORD PTR [rbx+40],0
    jne threads_insert_bad
threads_insert_scan:
    mov rax,QWORD PTR [rbx+16]
threads_insert_next:
    test rax,rax
    jz threads_insert_ownership
    cmp QWORD PTR [rax+40],rsi
    je threads_insert_bad
    cmp QWORD PTR [rax+48],rdi
    je threads_insert_bad
    mov rax,QWORD PTR [rax+16]
    jmp threads_insert_next
threads_insert_ownership:
    mov rcx,rbx
    mov rdx,rsi
    call threads_owned
    test eax,eax
    jz threads_insert_bad
    xor ecx,ecx
    mov edx,4096
    mov r8d,03000h
    mov r9d,4
    call VirtualAlloc
    test rax,rax
    jz threads_insert_done
    mov DWORD PTR [rax],054485244h
    mov DWORD PTR [rax+4],1
    mov QWORD PTR [rax+8],rbx
    mov QWORD PTR [rax+40],rsi
    mov QWORD PTR [rax+48],rdi
    mov QWORD PTR [rax+160],rsi
    mov rdx,QWORD PTR [rbx+16]
    mov QWORD PTR [rax+16],rdx
    mov QWORD PTR [rbx+16],rax
    inc DWORD PTR [rbx+24]
    cmp rdi,1
    jne threads_insert_done
    mov DWORD PTR [rbx+40],1
    jmp threads_insert_done
threads_insert_bad:
    xor eax,eax
threads_insert_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
threads_insert ENDP
; Exclusive lock required; removes only a known record, no memory release.
threads_remove PROC
    lea r8,[rcx+16]
threads_remove_next:
    mov rax,QWORD PTR [r8]
    test rax,rax
    jz threads_remove_done
    cmp rax,rdx
    je threads_remove_found
    lea r8,[rax+16]
    jmp threads_remove_next
threads_remove_found:
    mov rax,QWORD PTR [rdx+16]
    mov QWORD PTR [r8],rax
    dec DWORD PTR [rcx+24]
threads_remove_done:
    ret
threads_remove ENDP
; Lock required: validate record membership before dereferencing a token.
threads_find PROC
    test rcx,rcx
    jz threads_find_bad
    cmp QWORD PTR threads_active,rcx
    jne threads_find_bad
    mov rax,QWORD PTR [rcx+16]
threads_find_next:
    test rax,rax
    jz threads_find_bad
    cmp rax,rdx
    je threads_find_done
    mov rax,QWORD PTR [rax+16]
    jmp threads_find_next
threads_find_bad:
    xor eax,eax
threads_find_done:
    ret
threads_find ENDP

; attach(registry,rootObject,JavaId)->external record/null, current OS thread.
boom_threads_attach PROC FRAME
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
    mov rdi,r8
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    test rbx,rbx
    jz threads_attach_bad
    cmp QWORD PTR threads_active,rbx
    jne threads_attach_bad
    mov ecx,DWORD PTR threads_fls
    call FlsGetValue
    test rax,rax
    jnz threads_attach_bad
    mov rcx,rbx
    mov rdx,rsi
    mov r8,rdi
    call threads_insert
    test rax,rax
    jz threads_attach_bad
    mov rdi,rax
    mov DWORD PTR [rdi+36],1
    call GetCurrentThreadId
    mov DWORD PTR [rdi+32],eax
    mov ecx,DWORD PTR threads_fls
    mov rdx,rdi
    call FlsSetValue
    test eax,eax
    jnz threads_attach_success
    mov rcx,rbx
    mov rdx,rdi
    call threads_remove
    cmp QWORD PTR [rdi+48],1
    jne threads_attach_free_failed
    mov DWORD PTR [rbx+40],0
threads_attach_free_failed:
    mov rcx,rdi
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
threads_attach_bad:
    xor edi,edi
threads_attach_success:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    mov rax,rdi
    add rsp,48
    pop rdi
    pop rsi
    pop rbx
    ret
boom_threads_attach ENDP

boom_threads_current PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    ; The current thread owns its FLS record. Active records prevent registry
    ; destruction, so this hot path needs no shared global lock.
    cmp DWORD PTR threads_fls,-1
    je threads_current_bad
    mov ecx,DWORD PTR threads_fls
    call FlsGetValue
    test rax,rax
    jz threads_current_bad
    cmp QWORD PTR [rax+8],rbx
    jne threads_current_bad
    mov rbx,QWORD PTR [rax+40]
    jmp threads_current_done
threads_current_bad:
    xor ebx,ebx
threads_current_done:
    mov rax,rbx
    add rsp,32
    pop rbx
    ret
boom_threads_current ENDP
boom_threads_detach PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov esi,87
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    test rbx,rbx
    jz threads_detach_unlock
    cmp QWORD PTR threads_active,rbx
    jne threads_detach_unlock
    cmp DWORD PTR [rbx+44],0
    jne threads_detach_unlock
    mov ecx,DWORD PTR threads_fls
    call FlsGetValue
    test rax,rax
    jz threads_detach_unlock
    cmp QWORD PTR [rax+8],rbx
    jne threads_detach_unlock
    cmp DWORD PTR [rax+36],1
    jne threads_detach_unlock
    mov rbx,rax
    mov ecx,DWORD PTR threads_fls
    xor edx,edx
    call FlsSetValue
    test eax,eax
    jz threads_detach_unlock
    mov rcx,QWORD PTR [rbx+8]
    mov rdx,rbx
    call threads_remove
    xor esi,esi
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    mov rcx,rbx
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
    jmp threads_detach_done
threads_detach_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
threads_detach_done:
    mov eax,esi
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_threads_detach ENDP

; start(registry,Start64/1 or Start88/2*) -> native token/null.
; ABI2 publishes source peer/state before CreateThread can run the worker;
; a failed CreateThread rolls back while the record is still live and locked.
boom_threads_start PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    xor edi,edi
    mov DWORD PTR [rsp+48],0
    mov DWORD PTR [rsp+52],0
    test rsi,rsi
    jz threads_start_done
    cmp DWORD PTR [rsi],05453504Eh
    jne threads_start_done
    cmp DWORD PTR [rsi+4],1
    je threads_start_legacy
    cmp DWORD PTR [rsi+4],2
    jne threads_start_done
    cmp QWORD PTR [rsi+56],0
    je threads_start_done
    cmp QWORD PTR [rsi+64],0
    je threads_start_done
    cmp QWORD PTR [rsi+80],0
    jne threads_start_done
    mov DWORD PTR [rsp+48],1
    jmp threads_start_common
threads_start_legacy:
    cmp QWORD PTR [rsi+56],0
    jne threads_start_done
threads_start_common:
    cmp QWORD PTR [rsi+24],0
    je threads_start_done
    cmp QWORD PTR [rsi+32],0
    je threads_start_done
    cmp QWORD PTR [rsi+40],0
    je threads_start_done
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi+8]
    mov r8,QWORD PTR [rsi+16]
    cmp r8,1
    je threads_start_unlock
    call threads_insert
    test rax,rax
    jz threads_start_unlock
    mov rdi,rax
    mov DWORD PTR [rdi+36],2
    mov rax,QWORD PTR [rsi+24]
    mov QWORD PTR [rdi+56],rax
    mov rax,QWORD PTR [rsi+32]
    mov QWORD PTR [rdi+64],rax
    mov rax,QWORD PTR [rsi+40]
    mov QWORD PTR [rdi+72],rax
    mov rax,QWORD PTR [rsi+48]
    mov QWORD PTR [rdi+80],rax
    cmp DWORD PTR [rsp+48],0
    je threads_start_published
    mov rcx,rdi
    mov rdx,rax
    call QWORD PTR [rsi+56]
threads_start_published:
    xor ecx,ecx
    xor edx,edx
    mov QWORD PTR [rsp+32],0
    cmp DWORD PTR [rsp+48],0
    je threads_start_stack_ready
    mov rdx,QWORD PTR [rsi+72]
    test rdx,rdx
    jz threads_start_stack_ready
    mov QWORD PTR [rsp+32],010000h
threads_start_stack_ready:
    lea r8,threads_worker
    mov r9,rdi
    lea rax,[rdi+32]
    mov QWORD PTR [rsp+40],rax
    call CreateThread
    test rax,rax
    jnz threads_start_created
    call GetLastError
    mov DWORD PTR [rsp+52],eax
    cmp DWORD PTR [rsp+48],0
    je threads_start_rollback_done
    mov rcx,rdi
    mov rdx,QWORD PTR [rdi+80]
    call QWORD PTR [rsi+64]
threads_start_rollback_done:
    mov rcx,rbx
    mov rdx,rdi
    call threads_remove
    mov rcx,rdi
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
    xor edi,edi
    jmp threads_start_unlock
threads_start_created:
    mov QWORD PTR [rdi+24],rax
threads_start_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
threads_start_done:
    cmp DWORD PTR [rsp+52],0
    je threads_start_return
    mov ecx,DWORD PTR [rsp+52]
    call SetLastError
threads_start_return:
    mov rax,rdi
    add rsp,64
    pop rdi
    pop rsi
    pop rbx
    ret
boom_threads_start ENDP

threads_worker PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    ; Publication lock also prevents completion before CreateThread's handle
    ; has been stored by the creator.
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    mov ecx,DWORD PTR threads_fls
    mov rdx,rbx
    call FlsSetValue
    test eax,eax
    jz threads_worker_attach_error
    mov DWORD PTR [rbx+36],3
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    stmxcsr DWORD PTR [rsp+32]
    mov DWORD PTR [rsp+36],01F80h
    ldmxcsr DWORD PTR [rsp+36]
    mov rcx,rbx
    mov rdx,QWORD PTR [rbx+80]
    call QWORD PTR [rbx+56]
    mov DWORD PTR [rbx+128],eax
    cmp DWORD PTR [rbx+96],0
    jne threads_worker_uncaught
    test eax,eax
    jz threads_worker_exit_callback
threads_worker_uncaught:
    ldmxcsr DWORD PTR [rsp+36]
    mov rcx,rbx
    mov rdx,QWORD PTR [rbx+80]
    call QWORD PTR [rbx+72]
    test eax,eax
    jz threads_worker_exit_callback
    mov DWORD PTR [rbx+128],eax
threads_worker_exit_callback:
    ldmxcsr DWORD PTR [rsp+36]
    mov rcx,rbx
    mov rdx,QWORD PTR [rbx+80]
    call QWORD PTR [rbx+64]
    mov DWORD PTR [rbx+132],eax
    ldmxcsr DWORD PTR [rsp+32]
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    mov ecx,DWORD PTR threads_fls
    xor edx,edx
    call FlsSetValue
    mov DWORD PTR [rbx+36],4
    jmp threads_worker_unlock
threads_worker_attach_error:
    mov DWORD PTR [rbx+96],3
    mov DWORD PTR [rbx+128],8
    mov DWORD PTR [rbx+36],5
threads_worker_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    xor eax,eax
    add rsp,48
    pop rbx
    ret
threads_worker ENDP

; join(registry,record,timeoutMilliseconds)->WAIT_OBJECT_0/TIMEOUT/error.
; A duplicated OS handle lets a concurrent owner release a finished token.
boom_threads_join PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,80
    .allocstack 80
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov edi,r8d
    lea rcx,threads_lock
    call AcquireSRWLockShared
    mov rcx,rbx
    mov rdx,rsi
    call threads_find
    test rax,rax
    jz threads_join_bad
    cmp QWORD PTR [rsi+24],0
    je threads_join_bad
    call GetCurrentThreadId
    cmp eax,DWORD PTR [rsi+32]
    je threads_join_self
    mov rcx,-1
    mov rdx,QWORD PTR [rsi+24]
    mov r8,-1
    lea r9,[rsp+64]
    mov QWORD PTR [rsp+32],0
    mov QWORD PTR [rsp+40],0
    mov QWORD PTR [rsp+48],2
    call DuplicateHandle
    test eax,eax
    jz threads_join_bad
    lea rcx,threads_lock
    call ReleaseSRWLockShared
    mov rcx,QWORD PTR [rsp+64]
    mov edx,edi
    call WaitForSingleObject
    mov ebx,eax
    mov rcx,QWORD PTR [rsp+64]
    call CloseHandle
    jmp threads_join_done
threads_join_self:
    mov ebx,1131
    jmp threads_join_unlock
threads_join_bad:
    mov ebx,87
threads_join_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockShared
threads_join_done:
    mov eax,ebx
    add rsp,80
    pop rdi
    pop rsi
    pop rbx
    ret
boom_threads_join ENDP

; result(registry,record,out64)->0/ERROR_BUSY170/87. Exact completed Context32,
; result, callback statuses, JavaId and OS id are copied; record stays rooted.
boom_threads_result PROC FRAME
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
    mov rdi,r8
    test rdi,rdi
    jz threads_result_bad_direct
    lea rcx,threads_lock
    call AcquireSRWLockShared
    mov rcx,rbx
    mov rdx,rsi
    call threads_find
    test rax,rax
    jz threads_result_bad
    mov ebx,170
    cmp DWORD PTR [rsi+36],4
    jb threads_result_unlock
    mov rax,QWORD PTR [rsi+88]
    mov QWORD PTR [rdi],rax
    mov rax,QWORD PTR [rsi+96]
    mov QWORD PTR [rdi+8],rax
    mov rax,QWORD PTR [rsi+104]
    mov QWORD PTR [rdi+16],rax
    mov rax,QWORD PTR [rsi+112]
    mov QWORD PTR [rdi+24],rax
    mov rax,QWORD PTR [rsi+120]
    mov QWORD PTR [rdi+32],rax
    mov rax,QWORD PTR [rsi+128]
    mov QWORD PTR [rdi+40],rax
    mov rax,QWORD PTR [rsi+48]
    mov QWORD PTR [rdi+48],rax
    mov rax,QWORD PTR [rsi+32]
    mov QWORD PTR [rdi+56],rax
    xor ebx,ebx
    jmp threads_result_unlock
threads_result_bad:
    mov ebx,87
threads_result_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockShared
    mov eax,ebx
    jmp threads_result_done
threads_result_bad_direct:
    mov eax,87
threads_result_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_threads_result ENDP

; release(registry,record)->0/170/87. Never frees a running OS thread.
boom_threads_release PROC FRAME
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
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    mov rcx,rbx
    mov rdx,rsi
    call threads_find
    test rax,rax
    jz threads_release_unlock
    mov edi,170
    cmp DWORD PTR [rbx+44],0
    jne threads_release_unlock
    cmp DWORD PTR [rsi+36],4
    jb threads_release_unlock
    mov rcx,QWORD PTR [rsi+24]
    xor edx,edx
    call WaitForSingleObject
    test eax,eax
    jnz threads_release_unlock
    mov rcx,rbx
    mov rdx,rsi
    call threads_remove
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    mov rcx,QWORD PTR [rsi+24]
    call CloseHandle
    mov rcx,rsi
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
    xor edi,edi
    jmp threads_release_done
threads_release_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
threads_release_done:
    mov eax,edi
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_threads_release ENDP

; roots begins an owner-thread GC lease: 0/170/122/87. Only FINISHED/ABNORMAL
; records qualify. Until roots_end, new attachment/start/release/destroy fail.
; The VM must register every mutator and merge image static roots before GC.
boom_threads_roots PROC FRAME
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
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov edi,r8d
    mov r12,r9
    mov r14d,87
    test r12,r12
    jz threads_roots_done
    mov DWORD PTR [r12],0
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    test rbx,rbx
    jz threads_roots_unlock
    cmp QWORD PTR threads_active,rbx
    jne threads_roots_unlock
    cmp DWORD PTR [rbx+44],0
    jne threads_roots_active
    mov r13,QWORD PTR [rbx+16]
    xor r14d,r14d
threads_roots_validate:
    test r13,r13
    jz threads_roots_capacity
    cmp DWORD PTR [r13+36],4
    jb threads_roots_active
    mov rcx,rbx
    mov rdx,QWORD PTR [r13+40]
    call threads_owned
    test eax,eax
    jz threads_roots_invalid
    inc r14d
    mov rdx,QWORD PTR [r13+112]
    test rdx,rdx
    jz threads_roots_next
    mov rcx,rbx
    call threads_owned
    test eax,eax
    jz threads_roots_invalid
    inc r14d
threads_roots_next:
    mov r13,QWORD PTR [r13+16]
    jmp threads_roots_validate
threads_roots_capacity:
    cmp edi,r14d
    jb threads_roots_small
    test r14d,r14d
    jz threads_roots_ok
    test rsi,rsi
    jz threads_roots_invalid
    mov r13,QWORD PTR [rbx+16]
    xor edi,edi
threads_roots_copy:
    mov rax,QWORD PTR [r13+40]
    mov QWORD PTR [rsi+rdi*8],rax
    inc edi
    mov rax,QWORD PTR [r13+112]
    test rax,rax
    jz threads_roots_copy_next
    mov QWORD PTR [rsi+rdi*8],rax
    inc edi
threads_roots_copy_next:
    mov r13,QWORD PTR [r13+16]
    test r13,r13
    jnz threads_roots_copy
threads_roots_ok:
    mov DWORD PTR [r12],r14d
    call GetCurrentThreadId
    mov DWORD PTR [rbx+48],eax
    mov DWORD PTR [rbx+44],1
    xor r14d,r14d
    jmp threads_roots_unlock
threads_roots_active:
    mov r14d,170
    jmp threads_roots_unlock
threads_roots_small:
    mov r14d,122
    jmp threads_roots_unlock
threads_roots_invalid:
    mov r14d,87
threads_roots_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
threads_roots_done:
    mov eax,r14d
    add rsp,40
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_threads_roots ENDP

boom_threads_roots_end PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov esi,87
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    test rbx,rbx
    jz threads_thaw_unlock
    cmp QWORD PTR threads_active,rbx
    jne threads_thaw_unlock
    cmp DWORD PTR [rbx+44],1
    jne threads_thaw_unlock
    call GetCurrentThreadId
    mov esi,5
    cmp eax,DWORD PTR [rbx+48]
    jne threads_thaw_unlock
    mov DWORD PTR [rbx+44],0
    mov DWORD PTR [rbx+48],0
    xor esi,esi
threads_thaw_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    mov eax,esi
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_threads_roots_end ENDP

boom_threads_destroy PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov esi,87
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    test rbx,rbx
    jz threads_destroy_unlock
    cmp QWORD PTR threads_active,rbx
    jne threads_destroy_unlock
    mov esi,170
    cmp DWORD PTR [rbx+44],0
    jne threads_destroy_unlock
    cmp DWORD PTR [rbx+24],0
    jne threads_destroy_unlock
    mov QWORD PTR threads_active,0
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    mov rcx,rbx
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
    xor esi,esi
    jmp threads_destroy_done
threads_destroy_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
threads_destroy_done:
    mov eax,esi
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_threads_destroy ENDP

; Automatic external detach on OS thread exit. Owned workers that bypass their
; wrapper are recorded as abnormal, never reported as a successful Java exit.
threads_fls_cleanup PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    test rbx,rbx
    jz threads_cleanup_done
    lea rcx,threads_lock
    call AcquireSRWLockExclusive
    mov ecx,DWORD PTR threads_fls
    xor edx,edx
    call FlsSetValue
    mov rsi,QWORD PTR [rbx+8]
    cmp QWORD PTR threads_active,rsi
    jne threads_cleanup_unlock
    cmp DWORD PTR [rbx+36],1
    jne threads_cleanup_worker
    mov rcx,rsi
    mov rdx,rbx
    call threads_remove
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
    mov rcx,rbx
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
    jmp threads_cleanup_done
threads_cleanup_worker:
    cmp DWORD PTR [rbx+36],4
    jae threads_cleanup_unlock
    mov DWORD PTR [rbx+36],5
    mov DWORD PTR [rbx+96],7
    mov DWORD PTR [rbx+128],574
threads_cleanup_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockExclusive
threads_cleanup_done:
    add rsp,40
    pop rsi
    pop rbx
    ret
threads_fls_cleanup ENDP
.const
ALIGN 4
; Default Windows Java priorities 1..10 (OpenJDK21u, policy zero).
threads_java_priorities DWORD -2,-2,-1,-1,0,0,1,1,2,2
.code
; set_priority(registry,sourceRoot,JavaPriority)->Win32 status.
; The caller validates the source oop. Missing/finished records are NEW or
; terminated Java threads: the Java field update requires no OS operation.
; Hold the registry lock through OS use. An external record cannot complete
; its FLS detach and recycle its OS id while OpenThread obtains its handle.
boom_threads_set_priority PROC FRAME
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
    mov edi,87
    xor r12d,r12d
    xor r13d,r13d
    test rsi,rsi
    jz threads_priority_done
    mov eax,r8d
    dec eax
    cmp eax,9
    ja threads_priority_done
    lea rdx,threads_java_priorities
    mov eax,DWORD PTR [rdx+rax*4]
    mov DWORD PTR [rsp+32],eax
    lea rcx,threads_lock
    call AcquireSRWLockShared
    test rbx,rbx
    jz threads_priority_unlock
    cmp QWORD PTR threads_active,rbx
    jne threads_priority_unlock
    cmp DWORD PTR [rbx],054524547h
    jne threads_priority_unlock
    cmp DWORD PTR [rbx+4],1
    jne threads_priority_unlock
    mov r10d,DWORD PTR [rbx+24]
    cmp r10d,DWORD PTR [rbx+28]
    ja threads_priority_unlock
    mov rax,QWORD PTR [rbx+16]
threads_priority_scan:
    test rax,rax
    jz threads_priority_no_peer
    test r10d,r10d
    jz threads_priority_unlock
    dec r10d
    cmp DWORD PTR [rax],054485244h
    jne threads_priority_unlock
    cmp DWORD PTR [rax+4],1
    jne threads_priority_unlock
    cmp QWORD PTR [rax+8],rbx
    jne threads_priority_unlock
    cmp QWORD PTR [rax+40],rsi
    je threads_priority_found
    mov rax,QWORD PTR [rax+16]
    jmp threads_priority_scan
threads_priority_found:
    cmp DWORD PTR [rax+36],5
    ja threads_priority_unlock
    cmp DWORD PTR [rax+36],4
    jae threads_priority_no_peer
    cmp DWORD PTR [rax+36],1
    jb threads_priority_unlock
    mov r12,QWORD PTR [rax+24]
    test r12,r12
    jnz threads_priority_apply
    cmp DWORD PTR [rax+36],1
    jne threads_priority_unlock
    mov r8d,DWORD PTR [rax+32]
    test r8d,r8d
    jz threads_priority_unlock
    mov ecx,020h ; THREAD_SET_INFORMATION
    xor edx,edx
    call OpenThread
    test rax,rax
    jz threads_priority_os_error
    mov r12,rax
    mov r13d,1
threads_priority_apply:
    mov rcx,r12
    mov edx,DWORD PTR [rsp+32]
    call SetThreadPriority
    test eax,eax
    jz threads_priority_os_error
threads_priority_no_peer:
    xor edi,edi
    jmp threads_priority_close
threads_priority_os_error:
    call GetLastError
    mov edi,eax
    test edi,edi
    jnz threads_priority_close
    mov edi,87
threads_priority_close:
    test r13d,r13d
    jz threads_priority_unlock
    mov rcx,r12
    call CloseHandle
    test eax,eax
    jnz threads_priority_unlock
    test edi,edi
    jnz threads_priority_unlock
    call GetLastError
    mov edi,eax
threads_priority_unlock:
    lea rcx,threads_lock
    call ReleaseSRWLockShared
threads_priority_done:
    mov eax,edi
    add rsp,48
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_threads_set_priority ENDP
END
