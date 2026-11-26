; Native Windows signal transport. No CRT, JVM, guest allocation or GC.
; This is the transport below Signal.dispatch, not a replacement Java handler.
; Config48: SGCF/1, dispatch(vm,number), vm_break(vm,number), vm, flags=0, reserved.
; Config64/2 preserves that prefix and adds enter(vm)48 / exit(vm)56.
; Both lifecycle hooks are required in ABI2. Enter succeeds before create
; publishes the transport; exit runs on that same OS worker before close joins.
; Hooks cannot reenter this transport. A failed enter must undo its own work;
; exit is called exactly once after a successful enter, including create rollback.
; Both callbacks return a DWORD status and must remain valid until close joins.
; The runtime module is pinned once registered with Windows; late OS callbacks
; can safely observe a null active pointer after the VM has been destroyed.
option casemap:none
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockShared:PROC
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN CreateEventW:PROC
EXTERN SetEvent:PROC
EXTERN CreateThread:PROC
EXTERN SetThreadPriority:PROC
EXTERN WaitForSingleObject:PROC
EXTERN CloseHandle:PROC
EXTERN SetConsoleCtrlHandler:PROC
EXTERN GetModuleHandleExW:PROC
EXTERN GetLastError:PROC
EXTERN SetLastError:PROC
EXTERN GetCurrentThreadId:PROC
EXTERN TlsAlloc:PROC
EXTERN TlsGetValue:PROC
EXTERN TlsSetValue:PROC
EXTERN FlsAlloc:PROC
EXTERN FlsGetValue:PROC
EXTERN FlsSetValue:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
EXTERN TerminateProcess:PROC
EXTERN GetProcessWindowStation:PROC
EXTERN GetUserObjectInformationW:PROC
PUBLIC boom_signal_control_create
PUBLIC boom_signal_control_close
PUBLIC boom_signal_control_register
PUBLIC boom_signal_control_raise
PUBLIC boom_signal_control_snapshot
PUBLIC boom_signal_control_console
PUBLIC boom_signal_control_thread_slots
.data
ALIGN 8
signal_control_lock QWORD 0
signal_control_active QWORD 0
signal_control_tls DWORD -1
signal_control_closing DWORD 0
signal_control_fls DWORD -1
ALIGN 8
signal_control_epoch QWORD 0
signal_control_live_slots DWORD 0
.code
; create(Config48*) -> opaque transport or null. One active VM per process.
boom_signal_control_create PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rsi,rcx
    xor ebx,ebx
    mov edi,87
    test rsi,rsi
    jz signal_create_return_error
    cmp DWORD PTR [rsi],053474346h
    jne signal_create_return_error
    cmp DWORD PTR [rsi+4],1
    je signal_create_config_prefix
    cmp DWORD PTR [rsi+4],2
    jne signal_create_return_error
    cmp QWORD PTR [rsi+48],0
    je signal_create_return_error
    cmp QWORD PTR [rsi+56],0
    je signal_create_return_error
signal_create_config_prefix:
    cmp QWORD PTR [rsi+8],0
    je signal_create_return_error
    cmp QWORD PTR [rsi+16],0
    je signal_create_return_error
    cmp QWORD PTR [rsi+32],0
    jne signal_create_return_error
    cmp QWORD PTR [rsi+40],0
    jne signal_create_return_error
    lea rcx,signal_control_lock
    call AcquireSRWLockExclusive
    mov edi,170
    cmp DWORD PTR signal_control_closing,0
    jne signal_create_unlock_error
    mov edi,183
    cmp QWORD PTR signal_control_active,0
    jne signal_create_unlock_error
    mov ecx,5
    lea rdx,boom_signal_control_console
    lea r8,[rsp+48]
    call GetModuleHandleExW
    test eax,eax
    jz signal_create_os_error
    cmp DWORD PTR signal_control_tls,-1
    jne signal_create_tls_ready
    call TlsAlloc
    cmp eax,-1
    je signal_create_os_error
    mov DWORD PTR signal_control_tls,eax
signal_create_tls_ready:
    cmp DWORD PTR signal_control_fls,-1
    jne signal_create_fls_ready
    lea rcx,signal_control_fls_free
    call FlsAlloc
    cmp eax,-1
    je signal_create_os_error
    mov DWORD PTR signal_control_fls,eax
signal_create_fls_ready:
    xor ecx,ecx
    mov edx,4096
    mov r8d,03000h
    mov r9d,4
    call VirtualAlloc
    test rax,rax
    jz signal_create_os_error
    mov rbx,rax
    mov DWORD PTR [rbx],053474354h
    mov DWORD PTR [rbx+4],1
    inc QWORD PTR signal_control_epoch
    mov rax,QWORD PTR signal_control_epoch
    mov QWORD PTR [rbx+120],rax
    mov rax,QWORD PTR [rsi+8]
    mov QWORD PTR [rbx+24],rax
    mov rax,QWORD PTR [rsi+16]
    mov QWORD PTR [rbx+32],rax
    mov rax,QWORD PTR [rsi+24]
    mov QWORD PTR [rbx+40],rax
    ; 128..311 are signal counts, 320..503 are dispositions. Lifecycle
    ; storage starts at 512, outside both arrays; legacy Config48 is not read
    ; past byte 47. VirtualAlloc supplies zero lifecycle fields in ABI1.
    cmp DWORD PTR [rsi+4],2
    jne signal_create_config_stored
    mov rax,QWORD PTR [rsi+48]
    mov QWORD PTR [rbx+512],rax
    mov rax,QWORD PTR [rsi+56]
    mov QWORD PTR [rbx+520],rax
signal_create_config_stored:
    xor ecx,ecx
    xor edx,edx
    xor r8d,r8d
    xor r9d,r9d
    call CreateEventW
    test rax,rax
    jz signal_create_os_error
    mov QWORD PTR [rbx+8],rax
    xor ecx,ecx
    xor edx,edx
    lea r8,signal_control_worker
    mov r9,rbx
    mov QWORD PTR [rsp+32],0
    lea rax,[rbx+108]
    mov QWORD PTR [rsp+40],rax
    call CreateThread
    test rax,rax
    jz signal_create_os_error
    mov QWORD PTR [rbx+16],rax
    mov rcx,rax
    mov edx,2
    call SetThreadPriority
    test eax,eax
    jz signal_create_os_error
    cmp QWORD PTR [rbx+512],0
    je signal_create_worker_ready
signal_create_wait_enter:
    cmp DWORD PTR [rbx+552],1
    je signal_create_enter_result
    lea rcx,[rbx+552]
    mov DWORD PTR [rsp+48],0
    lea rdx,[rsp+48]
    mov r8d,4
    mov r9d,-1
    call WaitOnAddress
    test eax,eax
    jnz signal_create_wait_enter
    jmp signal_create_os_error
signal_create_enter_result:
    mov edi,DWORD PTR [rbx+536]
    test edi,edi
    jnz signal_create_known_error
signal_create_worker_ready:
    lea rcx,boom_signal_control_console
    mov edx,1
    call SetConsoleCtrlHandler
    test eax,eax
    jz signal_create_os_error
    mov DWORD PTR [rbx+52],1
    mov QWORD PTR signal_control_active,rbx
    lea rcx,signal_control_lock
    call ReleaseSRWLockExclusive
    mov rax,rbx
    jmp signal_create_done
signal_create_os_error:
    call GetLastError
    mov edi,eax
signal_create_known_error:
    test rbx,rbx
    jz signal_create_unlock_error
    cmp QWORD PTR [rbx+16],0
    je signal_create_close_event
    mov DWORD PTR [rbx+48],1
    mov rcx,QWORD PTR [rbx+8]
    call SetEvent
    mov rcx,QWORD PTR [rbx+16]
    mov edx,-1
    call WaitForSingleObject
    mov rcx,QWORD PTR [rbx+16]
    call CloseHandle
signal_create_close_event:
    mov rcx,QWORD PTR [rbx+8]
    test rcx,rcx
    jz signal_create_free
    call CloseHandle
signal_create_free:
    mov rcx,rbx
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
signal_create_unlock_error:
    lea rcx,signal_control_lock
    call ReleaseSRWLockExclusive
signal_create_return_error:
    mov ecx,edi
    call SetLastError
    xor eax,eax
signal_create_done:
    add rsp,64
    pop rdi
    pop rsi
    pop rbx
    ret
boom_signal_control_create ENDP

; register(control, signal, native_handler) -> previous J64 or -1.
; SIGFPE and SIGBREAK are VM-owned under the normal Windows startup policy.
boom_signal_control_register PROC FRAME
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
    mov esi,edx
    mov rdi,r8
    lea rcx,signal_control_lock
    call AcquireSRWLockExclusive
    test rbx,rbx
    jz signal_register_invalid
    cmp QWORD PTR signal_control_active,rbx
    jne signal_register_invalid
    cmp DWORD PTR [rbx+52],1
    jne signal_register_invalid
    cmp rdi,-1
    je signal_register_invalid
    cmp rdi,3
    je signal_register_invalid
    cmp rdi,4
    je signal_register_invalid
    cmp esi,2
    je signal_register_valid
    cmp esi,4
    je signal_register_valid
    cmp esi,6
    je signal_register_valid
    cmp esi,11
    je signal_register_valid
    cmp esi,15
    je signal_register_valid
    cmp esi,22
    jne signal_register_invalid
signal_register_valid:
    mov rcx,rbx
    mov edx,esi
    call signal_control_action
    test rax,rax
    jz signal_register_invalid
    xchg rdi,QWORD PTR [rax]
    jmp signal_register_unlock
signal_register_invalid:
    mov rdi,-1
signal_register_unlock:
    lea rcx,signal_control_lock
    call ReleaseSRWLockExclusive
    mov rax,rdi
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_signal_control_register ENDP

; raise(control, signal) -> DWORD error/0. Valid default dispositions terminate
; this process with status 3, as the supported Windows CRT signal defaults do.
boom_signal_control_raise PROC FRAME
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
    mov esi,edx
    mov edi,87
    lea rcx,signal_control_lock
    call AcquireSRWLockShared
    test rbx,rbx
    jz signal_raise_unlock
    cmp QWORD PTR signal_control_active,rbx
    jne signal_raise_unlock
    cmp DWORD PTR [rbx+52],1
    jne signal_raise_unlock
    cmp esi,2
    je signal_raise_valid
    cmp esi,4
    je signal_raise_valid
    cmp esi,6
    je signal_raise_valid
    cmp esi,8
    je signal_raise_valid
    cmp esi,11
    je signal_raise_valid
    cmp esi,15
    je signal_raise_valid
    cmp esi,21
    je signal_raise_valid
    cmp esi,22
    jne signal_raise_unlock
signal_raise_valid:
    lock inc DWORD PTR [rbx+112]
    lea rcx,signal_control_lock
    call ReleaseSRWLockShared
    lock inc QWORD PTR [rbx+80]
    mov rcx,rbx
    mov edx,esi
    call signal_control_deliver
    mov edi,eax
    mov rcx,rbx
    call signal_control_release
    jmp signal_raise_done
signal_raise_unlock:
    lea rcx,signal_control_lock
    call ReleaseSRWLockShared
signal_raise_done:
    mov eax,edi
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_signal_control_raise ENDP

; OS callback. The caller never runs the Java dispatch callback synchronously.
boom_signal_control_console PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,64
    .allocstack 64
    .endprolog
    mov esi,ecx
    xor edi,edi
    lea rcx,signal_control_lock
    call AcquireSRWLockShared
    mov rbx,QWORD PTR signal_control_active
    test rbx,rbx
    jz signal_console_unlock
    cmp DWORD PTR [rbx+52],1
    jne signal_console_unlock
    test esi,esi
    jz signal_console_int
    cmp esi,1
    je signal_console_break
    cmp esi,2
    je signal_console_term
    cmp esi,6
    je signal_console_term
    cmp esi,5
    jne signal_console_unlock
    call GetProcessWindowStation
    test rax,rax
    jz signal_console_term
    mov rcx,rax
    mov edx,1
    lea r8,[rsp+48]
    mov r9d,12
    mov QWORD PTR [rsp+32],0
    call GetUserObjectInformationW
    test eax,eax
    jz signal_console_term
    test DWORD PTR [rsp+56],1
    jz signal_console_unlock
signal_console_term:
    mov esi,15
    jmp signal_console_deliver
signal_console_break:
    mov esi,21
    jmp signal_console_deliver
signal_console_int:
    mov esi,2
signal_console_deliver:
    lock inc DWORD PTR [rbx+112]
    lea rcx,signal_control_lock
    call ReleaseSRWLockShared
    lock inc QWORD PTR [rbx+88]
    mov rcx,rbx
    mov edx,esi
    call signal_control_deliver
    mov DWORD PTR [rbx+76],eax
    mov edi,1
    mov rcx,rbx
    call signal_control_release
    jmp signal_console_done
signal_console_unlock:
    lea rcx,signal_control_lock
    call ReleaseSRWLockShared
signal_console_done:
    mov eax,edi
    add rsp,64
    pop rdi
    pop rsi
    pop rbx
    ret
boom_signal_control_console ENDP

; Internal: the caller holds an active-operation lease, not an SRW lock.
; A native handler may therefore reenter register/raise without deadlocking.
signal_control_deliver PROC FRAME
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
    mov esi,edx
    cmp esi,21
    je signal_deliver_queue
    mov rcx,rbx
    mov edx,esi
    call signal_control_action
    test rax,rax
    jz signal_deliver_no_storage
    mov QWORD PTR [rsp+40],rax
signal_deliver_read:
    mov r10,QWORD PTR [rsp+40]
    mov rax,QWORD PTR [r10]
    cmp rax,2
    je signal_deliver_queue
    cmp rax,1
    je signal_deliver_ignored
    test rax,rax
    jz signal_deliver_default
    xor edx,edx
    lock cmpxchg QWORD PTR [r10],rdx
    jne signal_deliver_read
    mov rdi,rax
    mov ecx,DWORD PTR signal_control_tls
    call TlsGetValue
    mov QWORD PTR [rsp+32],rax
    mov ecx,DWORD PTR signal_control_tls
    mov rdx,rbx
    call TlsSetValue
    test eax,eax
    jz signal_deliver_tls_error
    mov ecx,esi
    call rdi
    mov ecx,DWORD PTR signal_control_tls
    mov rdx,QWORD PTR [rsp+32]
    call TlsSetValue
signal_deliver_ignored:
    xor eax,eax
    jmp signal_deliver_done
signal_deliver_tls_error:
    call GetLastError
    mov DWORD PTR [rsp+48],eax
    xor eax,eax
    mov r10,QWORD PTR [rsp+40]
    lock cmpxchg QWORD PTR [r10],rdi
    mov eax,DWORD PTR [rsp+48]
    jmp signal_deliver_done
signal_deliver_queue:
    lock inc QWORD PTR [rbx+rsi*8+128]
    mov rcx,QWORD PTR [rbx+8]
    call SetEvent
    test eax,eax
    jnz signal_deliver_ignored
    call GetLastError
    mov DWORD PTR [rbx+76],eax
    jmp signal_deliver_done
signal_deliver_no_storage:
    mov eax,8
    jmp signal_deliver_done
signal_deliver_default:
    mov rcx,-1
    mov edx,3
    call TerminateProcess
    call GetLastError
signal_deliver_done:
    add rsp,64
    pop rdi
    pop rsi
    pop rbx
    ret
signal_control_deliver ENDP

; UCRT has per-thread exception actions for ILL/SEGV; INT/TERM/ABRT are
; process actions. ABRT_COMPAT(6) aliases the ABRT(22) disposition, while raise
; still forwards the original signal number. Thread storage has no VM pointer;
; generations reset it on VM replacement, and FLS frees it on thread exit.
signal_control_action PROC FRAME
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
    mov esi,edx
    cmp esi,6
    jne signal_action_not_alias
    mov esi,22
signal_action_not_alias:
    cmp esi,4
    je signal_action_local
    cmp esi,11
    je signal_action_local
    lea rax,[rbx+rsi*8+320]
    jmp signal_action_done
signal_action_local:
    mov ecx,DWORD PTR signal_control_fls
    call FlsGetValue
    mov rdi,rax
    test rax,rax
    jnz signal_action_generation
    xor ecx,ecx
    mov edx,4096
    mov r8d,03000h
    mov r9d,4
    call VirtualAlloc
    test rax,rax
    jz signal_action_done
    mov rdi,rax
    mov ecx,DWORD PTR signal_control_fls
    mov rdx,rdi
    call FlsSetValue
    test eax,eax
    jz signal_action_install_error
    lock inc DWORD PTR signal_control_live_slots
    jmp signal_action_generation
signal_action_install_error:
    mov rcx,rdi
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
    xor eax,eax
    jmp signal_action_done
signal_action_generation:
    mov rax,QWORD PTR [rbx+120]
    cmp QWORD PTR [rdi],rax
    je signal_action_slot
    mov QWORD PTR [rdi],rax
    mov QWORD PTR [rdi+8],0
    mov QWORD PTR [rdi+16],0
signal_action_slot:
    lea rax,[rdi+8]
    cmp esi,4
    je signal_action_done
    lea rax,[rdi+16]
signal_action_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
signal_control_action ENDP
signal_control_fls_free PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    test rcx,rcx
    jz signal_fls_free_done
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
    test eax,eax
    jz signal_fls_free_done
    lock dec DWORD PTR signal_control_live_slots
signal_fls_free_done:
    add rsp,40
    ret
signal_control_fls_free ENDP
boom_signal_control_thread_slots PROC
    mov eax,DWORD PTR signal_control_live_slots
    ret
boom_signal_control_thread_slots ENDP

signal_control_release PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    lock dec DWORD PTR [rcx+112]
    jnz signal_release_done
    add rcx,112
    call WakeByAddressAll
signal_release_done:
    add rsp,40
    ret
signal_control_release ENDP

signal_control_worker PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,56
    .allocstack 56
    .endprolog
    mov rbx,rcx
    mov rax,QWORD PTR [rbx+512]
    test rax,rax
    jz signal_worker_scan
    stmxcsr DWORD PTR [rsp+32]
    mov DWORD PTR [rsp+36],01F80h
    ldmxcsr DWORD PTR [rsp+36]
    mov rcx,QWORD PTR [rbx+40]
    call rax
    ldmxcsr DWORD PTR [rsp+32]
    mov DWORD PTR [rbx+536],eax
    test eax,eax
    jnz signal_worker_enter_publish
    mov DWORD PTR [rbx+544],1
signal_worker_enter_publish:
    mov DWORD PTR [rbx+552],1
    lea rcx,[rbx+552]
    call WakeByAddressAll
    cmp DWORD PTR [rbx+536],0
    jne signal_worker_return
signal_worker_scan:
    xor esi,esi
signal_worker_next:
    mov rax,QWORD PTR [rbx+rsi*8+128]
signal_worker_claim:
    test rax,rax
    jz signal_worker_empty
    lea rdx,[rax-1]
    lock cmpxchg QWORD PTR [rbx+rsi*8+128],rdx
    jne signal_worker_claim
    mov rax,QWORD PTR [rbx+24]
    cmp esi,21
    jne signal_worker_callback
    mov rax,QWORD PTR [rbx+32]
signal_worker_callback:
    mov DWORD PTR [rbx+104],1
    stmxcsr DWORD PTR [rsp+32]
    mov DWORD PTR [rsp+36],01F80h
    ldmxcsr DWORD PTR [rsp+36]
    mov rcx,QWORD PTR [rbx+40]
    mov edx,esi
    call rax
    ldmxcsr DWORD PTR [rsp+32]
    mov DWORD PTR [rbx+72],eax
    test eax,eax
    jz signal_worker_success
    lock inc QWORD PTR [rbx+64]
signal_worker_success:
    lock inc QWORD PTR [rbx+56]
    mov DWORD PTR [rbx+104],0
    jmp signal_worker_scan
signal_worker_empty:
    inc esi
    cmp esi,23
    jb signal_worker_next
    cmp DWORD PTR [rbx+48],0
    jne signal_worker_exit
    mov rcx,QWORD PTR [rbx+8]
    mov edx,-1
    call WaitForSingleObject
    test eax,eax
    jz signal_worker_scan
    call GetLastError
    mov DWORD PTR [rbx+76],eax
    mov DWORD PTR [rbx+52],3
signal_worker_exit:
    cmp DWORD PTR [rbx+544],1
    jne signal_worker_return
    mov rax,QWORD PTR [rbx+520]
    stmxcsr DWORD PTR [rsp+32]
    mov DWORD PTR [rsp+36],01F80h
    ldmxcsr DWORD PTR [rsp+36]
    mov rcx,QWORD PTR [rbx+40]
    call rax
    ldmxcsr DWORD PTR [rsp+32]
    mov DWORD PTR [rbx+540],eax
    mov DWORD PTR [rbx+548],1
signal_worker_return:
    xor eax,eax
    add rsp,56
    pop rsi
    pop rbx
    ret
signal_control_worker ENDP

; snapshot(control, out64) -> error/0. Counters are observations; a zero
; pending count alone is NOT a GC safepoint. Close joins the actual worker.
boom_signal_control_snapshot PROC FRAME
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
    test rsi,rsi
    jz signal_snapshot_done
    lea rcx,signal_control_lock
    call AcquireSRWLockShared
    test rbx,rbx
    jz signal_snapshot_unlock
    cmp QWORD PTR signal_control_active,rbx
    jne signal_snapshot_unlock
    mov rax,QWORD PTR [rbx+56]
    mov QWORD PTR [rsi],rax
    mov rax,QWORD PTR [rbx+64]
    mov QWORD PTR [rsi+8],rax
    mov rax,QWORD PTR [rbx+72]
    mov QWORD PTR [rsi+16],rax
    mov rax,QWORD PTR [rbx+80]
    mov QWORD PTR [rsi+24],rax
    mov rax,QWORD PTR [rbx+88]
    mov QWORD PTR [rsi+32],rax
    xor eax,eax
    xor edx,edx
signal_snapshot_pending:
    add rax,QWORD PTR [rbx+rdx*8+128]
    inc edx
    cmp edx,23
    jb signal_snapshot_pending
    mov QWORD PTR [rsi+40],rax
    mov eax,DWORD PTR [rbx+104]
    mov QWORD PTR [rsi+48],rax
    mov eax,DWORD PTR [rbx+52]
    mov QWORD PTR [rsi+56],rax
    xor edi,edi
signal_snapshot_unlock:
    lea rcx,signal_control_lock
    call ReleaseSRWLockShared
signal_snapshot_done:
    mov eax,edi
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_signal_control_snapshot ENDP

; close detaches the console handler, drains accepted queued signals and joins
; the dispatcher before releasing any native storage. No forced thread kill.
boom_signal_control_close PROC FRAME
    push rbx
    .pushreg rbx
    push rdi
    .pushreg rdi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov edi,87
    lea rcx,signal_control_lock
    call AcquireSRWLockExclusive
    test rbx,rbx
    jz signal_close_invalid
    cmp QWORD PTR signal_control_active,rbx
    jne signal_close_invalid
    call GetCurrentThreadId
    cmp eax,DWORD PTR [rbx+108]
    je signal_close_reentrant
    mov ecx,DWORD PTR signal_control_tls
    call TlsGetValue
    cmp rax,rbx
    je signal_close_reentrant
    mov DWORD PTR [rbx+52],2
    mov QWORD PTR signal_control_active,0
    mov DWORD PTR signal_control_closing,1
    lea rcx,signal_control_lock
    call ReleaseSRWLockExclusive
    lea rcx,boom_signal_control_console
    xor edx,edx
    call SetConsoleCtrlHandler
    xor edi,edi
    test eax,eax
    jnz signal_close_detached
    call GetLastError
    mov edi,eax
signal_close_detached:
signal_close_wait_leases:
    mov eax,DWORD PTR [rbx+112]
    test eax,eax
    je signal_close_stop_worker
    lea rcx,[rbx+112]
    mov DWORD PTR [rsp+32],eax
    lea rdx,[rsp+32]
    mov r8d,4
    mov r9d,-1
    call WaitOnAddress
    jmp signal_close_wait_leases
signal_close_stop_worker:
    mov DWORD PTR [rbx+48],1
    mov rcx,QWORD PTR [rbx+8]
    call SetEvent
    mov rcx,QWORD PTR [rbx+16]
    mov edx,-1
    call WaitForSingleObject
    test eax,eax
    jnz signal_close_wait_error
    test edi,edi
    jnz signal_close_lifecycle_observed
    mov edi,DWORD PTR [rbx+540]
signal_close_lifecycle_observed:
    mov rcx,QWORD PTR [rbx+16]
    call CloseHandle
    mov rcx,QWORD PTR [rbx+8]
    call CloseHandle
    mov DWORD PTR [rbx],0
    mov rcx,rbx
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
    test eax,eax
    jnz signal_close_reopen
    call GetLastError
    mov edi,eax
signal_close_reopen:
    lea rcx,signal_control_lock
    call AcquireSRWLockExclusive
    mov DWORD PTR signal_control_closing,0
    lea rcx,signal_control_lock
    call ReleaseSRWLockExclusive
    jmp signal_close_done
signal_close_wait_error:
    call GetLastError
    mov edi,eax
    jmp signal_close_done
signal_close_invalid:
    lea rcx,signal_control_lock
    call ReleaseSRWLockExclusive
    jmp signal_close_done
signal_close_reentrant:
    mov edi,1131
    jmp signal_close_invalid
signal_close_done:
    mov eax,edi
    add rsp,40
    pop rdi
    pop rbx
    ret
boom_signal_control_close ENDP
END
