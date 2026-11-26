; Normal source Thread.start0 over Start88/2. All guest execution is MASM.
; TLCP256/1: immutable pointers16..104; SRW112; failureState120/highWater124;
; source field-address functions128..160; counters168..216; failure Context224.
; Slot64: pool0,peerAddress8,statusAddress16,JavaId24,stackReserve32,
; nativeToken40,sourceOop48,reserved56. Addresses borrow a nonmoving heap lifetime.
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_threads_current:PROC
EXTERN boom_provider_thread_priority_start:PROC
EXTERN boom_threads_start:PROC
EXTERN boom_threads_join:PROC
EXTERN boom_threads_result:PROC
EXTERN boom_threads_release:PROC
EXTERN boom_monitor_enter:PROC
EXTERN boom_monitor_exit:PROC
EXTERN boom_monitor_notify_all:PROC
PUBLIC boom_provider_threads_service
PUBLIC boom_provider_threads_reap
PUBLIC boom_provider_threads_close
.data
ALIGN 8
PUBLIC boom_provider_threads_control_binding
; Optional process-owned callback and its pool. Installed before Java workers
; start and held until they have been joined. TLCP256/1 keeps its original ABI.
boom_provider_threads_control_binding QWORD 0,0
.code
tl_control_boundary PROC PRIVATE
 mov rax,QWORD PTR [boom_provider_threads_control_binding]
 test rax,rax
 jz tl_no_control
 mov rdx,QWORD PTR [boom_provider_threads_control_binding+8]
 jmp rax
tl_no_control:
 ret
tl_control_boundary ENDP
tl_pool_valid PROC PRIVATE
 test rcx,rcx
 jz tl_pool_bad
 cmp DWORD PTR [rcx],050434C54h
 jne tl_pool_bad
 cmp DWORD PTR [rcx+4],1
 jne tl_pool_bad
 cmp DWORD PTR [rcx+8],1
 ja tl_pool_bad
 mov eax,DWORD PTR [rcx+12]
 dec eax
 cmp eax,16383
 ja tl_pool_bad
 mov eax,DWORD PTR [rcx+124]
 cmp eax,DWORD PTR [rcx+12]
 ja tl_pool_bad
 cmp DWORD PTR [rcx+120],2
 ja tl_pool_bad
 cmp QWORD PTR [rcx+232],0
 jne tl_pool_bad
 cmp QWORD PTR [rcx+240],0
 jne tl_pool_bad
 cmp QWORD PTR [rcx+248],0
 jne tl_pool_bad
 cmp QWORD PTR [rcx+224],0
 je tl_pool_bad
 mov r10d,16
tl_pool_pointer:
 cmp QWORD PTR [rcx+r10],0
 je tl_pool_bad
 add r10d,8
 cmp r10d,112
 jb tl_pool_pointer
 mov r10d,128
tl_pool_field_function:
 cmp QWORD PTR [rcx+r10],0
 je tl_pool_bad
 add r10d,8
 cmp r10d,168
 jb tl_pool_field_function
 mov eax,1
 ret
tl_pool_bad:
 xor eax,eax
 ret
tl_pool_valid ENDP

; (Context32,oop,pool,expected TypeDesc) -> checked assignability boolean.
tl_object PROC PRIVATE FRAME
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
 mov r12,r9
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 call boom_heap_contains
 test eax,eax
 jz tl_object_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [rdi+24]
 mov r8,rbx
 call boom_runtime_type
 cmp DWORD PTR [rbx],0
 jne tl_object_zero
 test rax,rax
 jz tl_object_bad
 mov rcx,rax
 mov rdx,r12
 call boom_type_assignable
 test eax,eax
 jnz tl_object_done
tl_object_bad:
 mov DWORD PTR [rbx],7
tl_object_zero:
 xor eax,eax
tl_object_done:
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
tl_object ENDP

; Preserve the first VM/diagnostic failure. Materialized application throwables
; remain in the native record and go through original Java uncaught dispatch.
tl_remember_failure PROC PRIVATE
 mov eax,DWORD PTR [rcx]
 test eax,eax
 jz tl_failure_done
 cmp eax,0B001h
 je tl_failure_claim
 cmp QWORD PTR [rcx+16],0
 jne tl_failure_done
tl_failure_claim:
 xor eax,eax
 mov r8d,1
 lock cmpxchg DWORD PTR [rdx+120],r8d
 test eax,eax
 jnz tl_failure_done
 mov r8,QWORD PTR [rdx+224]
 mov rax,QWORD PTR [rcx]
 mov QWORD PTR [r8],rax
 mov rax,QWORD PTR [rcx+8]
 mov QWORD PTR [r8+8],rax
 mov rax,QWORD PTR [rcx+16]
 mov QWORD PTR [r8+16],rax
 mov rax,QWORD PTR [rcx+24]
 mov QWORD PTR [r8+24],rax
 mov DWORD PTR [rdx+120],2
tl_failure_done:
 ret
tl_remember_failure ENDP

; The registry calls these two VM-store hooks while holding its publication
; lock, before CreateThread or before discarding a failed record respectively.
tl_publish PROC PRIVATE
 mov QWORD PTR [rdx+40],rcx
 mov rax,QWORD PTR [rdx+8]
 mov QWORD PTR [rax],rcx
 mov rax,QWORD PTR [rdx+16]
 mov DWORD PTR [rax],4
 ret
tl_publish ENDP
tl_rollback PROC PRIVATE
 mov rax,QWORD PTR [rdx+8]
 mov QWORD PTR [rax],0
 mov rax,QWORD PTR [rdx+16]
 mov DWORD PTR [rax],0
 mov QWORD PTR [rdx+40],0
 ret
tl_rollback ENDP

; (record,Slot64) -> status. Invoke the complete original Runnable dispatch
; contract with the real Thread receiver; subclass overrides stay in the table.
tl_main PROC PRIVATE FRAME
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
 mov rdi,QWORD PTR [rsi]
 mov rcx,QWORD PTR [rdi+32]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_current
 cmp rax,QWORD PTR [rbx+40]
 jne tl_main_bad
 lea rcx,[rbx+96]
 mov rdx,QWORD PTR [rbx+40]
 call boom_provider_thread_priority_start
 cmp DWORD PTR [rbx+96],0
 jne tl_main_record
 mov rax,QWORD PTR [rbx+40]
 mov QWORD PTR [rbx+160],rax
 lock inc QWORD PTR [rdi+176]
 lea rcx,[rbx+96]
 lea rdx,[rbx+160]
 call QWORD PTR [rdi+64]
 cmp DWORD PTR [rbx+96],0
 jne tl_main_record
 lock inc QWORD PTR [rdi+184]
 jmp tl_main_record
tl_main_bad:
 mov DWORD PTR [rbx+96],7
tl_main_record:
 lea rcx,[rbx+96]
 call tl_control_boundary
 lea rcx,[rbx+96]
 mov rdx,rdi
 call tl_remember_failure
 mov eax,DWORD PTR [rbx+96]
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
tl_main ENDP

tl_uncaught PROC PRIVATE FRAME
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
 mov rdi,QWORD PTR [rsi]
 lock inc QWORD PTR [rdi+192]
 cmp QWORD PTR [rbx+112],0
 je tl_uncaught_vm_failure
 cmp DWORD PTR [rbx+96],0B001h
 je tl_uncaught_vm_failure
 xor eax,eax
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],rax
 mov QWORD PTR [rsp+48],rax
 mov QWORD PTR [rsp+56],rax
 lea rcx,[rsp+32]
 mov rdx,QWORD PTR [rbx+112]
 mov r8,rdi
 mov r9,QWORD PTR [rdi+88]
 call tl_object
 test eax,eax
 jz tl_uncaught_record
 mov rax,QWORD PTR [rbx+40]
 mov QWORD PTR [rsp+64],rax
 mov rax,QWORD PTR [rbx+112]
 mov QWORD PTR [rsp+72],rax
 lea rcx,[rsp+32]
 lea rdx,[rsp+64]
 call QWORD PTR [rdi+80]
tl_uncaught_record:
 lea rcx,[rsp+32]
 call tl_control_boundary
 lea rcx,[rsp+32]
 mov rdx,rdi
 call tl_remember_failure
 mov eax,DWORD PTR [rsp+32]
 jmp tl_uncaught_done
tl_uncaught_vm_failure:
 lea rcx,[rbx+96]
 mov rdx,rdi
 call tl_remember_failure
 mov eax,DWORD PTR [rbx+96]
tl_uncaught_done:
 add rsp,80
 pop rdi
 pop rsi
 pop rbx
 ret
tl_uncaught ENDP

; Execute original Java exit with a clean Context; retain any source stop, then
; perform VM terminal-state publication while owning the real object monitor.
tl_exit PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,144
 .allocstack 144
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,QWORD PTR [rsi]
 xor eax,eax
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],rax
 mov QWORD PTR [rsp+48],rax
 mov QWORD PTR [rsp+56],rax
 mov QWORD PTR [rsp+64],rax
 mov QWORD PTR [rsp+72],rax
 mov QWORD PTR [rsp+80],rax
 mov QWORD PTR [rsp+88],rax
 mov DWORD PTR [rsp+128],0
 mov rax,QWORD PTR [rbx+40]
 mov QWORD PTR [rsp+96],rax
 lock inc QWORD PTR [rdi+200]
 lea rcx,[rsp+32]
 lea rdx,[rsp+96]
 call QWORD PTR [rdi+72]
 mov eax,DWORD PTR [rsp+32]
 mov DWORD PTR [rsp+128],eax
 test eax,eax
 jnz tl_exit_remember
 lock inc QWORD PTR [rdi+208]
tl_exit_remember:
 lea rcx,[rsp+32]
 call tl_control_boundary
 lea rcx,[rsp+32]
 mov rdx,rdi
 call tl_remember_failure
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rbx+40]
 lea r8,[rsp+64]
 call boom_monitor_enter
 test eax,eax
 jnz tl_exit_monitor_error
 mov rax,QWORD PTR [rsi+8]
 mov QWORD PTR [rax],0
 mov rax,QWORD PTR [rsi+16]
 mov DWORD PTR [rax],2
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rbx+40]
 lea r8,[rsp+64]
 call boom_monitor_notify_all
 cmp DWORD PTR [rsp+64],0
 je tl_exit_unlock
 lea rcx,[rsp+64]
 mov rdx,rdi
 call tl_remember_failure
 cmp DWORD PTR [rsp+128],0
 jne tl_exit_reset_monitor_context
 mov eax,DWORD PTR [rsp+64]
 mov DWORD PTR [rsp+128],eax
tl_exit_reset_monitor_context:
 xor eax,eax
 mov QWORD PTR [rsp+64],rax
 mov QWORD PTR [rsp+72],rax
 mov QWORD PTR [rsp+80],rax
 mov QWORD PTR [rsp+88],rax
tl_exit_unlock:
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rbx+40]
 lea r8,[rsp+64]
 call boom_monitor_exit
tl_exit_monitor_error:
 cmp DWORD PTR [rsp+64],0
 je tl_exit_done
 lea rcx,[rsp+64]
 mov rdx,rdi
 call tl_remember_failure
 cmp DWORD PTR [rsp+128],0
 jne tl_exit_done
 mov eax,DWORD PTR [rsp+64]
 mov DWORD PTR [rsp+128],eax
tl_exit_done:
 mov eax,DWORD PTR [rsp+128]
 add rsp,144
 pop rdi
 pop rsi
 pop rbx
 ret
tl_exit ENDP

; (pool,target oop or null) -> 0/170/87; caller owns the pool lock.
; Join is always nonblocking: a worker may itself need to start another Thread.
tl_reap_locked PROC PRIVATE FRAME
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
 sub rsp,96
 .allocstack 96
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 xor r12d,r12d
 xor r13d,r13d
 test rsi,rsi
 jz tl_reap_loop
 mov r13d,87
tl_reap_loop:
 cmp r12d,DWORD PTR [rbx+124]
 jae tl_reap_done
 mov edi,r12d
 shl rdi,6
 add rdi,QWORD PTR [rbx+96]
 cmp QWORD PTR [rdi+40],0
 je tl_reap_next
 test rsi,rsi
 jz tl_reap_check
 cmp QWORD PTR [rdi+48],rsi
 jne tl_reap_next
 mov r13d,170
tl_reap_check:
 mov rcx,QWORD PTR [rbx+32]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+40]
 xor r8d,r8d
 call boom_threads_join
 test eax,eax
 jz tl_reap_result
 cmp eax,258
 jne tl_reap_bad
 mov r13d,170
 jmp tl_reap_next
tl_reap_result:
 mov rcx,QWORD PTR [rbx+32]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+40]
 lea r8,[rsp+32]
 call boom_threads_result
 test eax,eax
 jnz tl_reap_bad
 lea rcx,[rsp+40]
 mov rdx,rbx
 call tl_remember_failure
 cmp DWORD PTR [rsp+76],0
 je tl_reap_release
 cmp DWORD PTR [rbx+120],0
 jne tl_reap_release
 cmp DWORD PTR [rsp+40],0
 jne tl_reap_release
 mov DWORD PTR [rsp+40],7
 lea rcx,[rsp+40]
 mov rdx,rbx
 call tl_remember_failure
tl_reap_release:
 ; An OS/FLS attach failure can bypass source callbacks. Clear only our peer.
 mov rax,QWORD PTR [rdi+8]
 mov rdx,QWORD PTR [rdi+40]
 cmp QWORD PTR [rax],rdx
 jne tl_reap_peer_cleared
 mov QWORD PTR [rax],0
 mov rax,QWORD PTR [rdi+16]
 mov DWORD PTR [rax],2
tl_reap_peer_cleared:
 mov rcx,QWORD PTR [rbx+32]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+40]
 call boom_threads_release
 test eax,eax
 jnz tl_reap_bad
 xor eax,eax
 mov QWORD PTR [rdi],rax
 mov QWORD PTR [rdi+8],rax
 mov QWORD PTR [rdi+16],rax
 mov QWORD PTR [rdi+24],rax
 mov QWORD PTR [rdi+32],rax
 mov QWORD PTR [rdi+40],rax
 mov QWORD PTR [rdi+48],rax
 mov QWORD PTR [rdi+56],rax
 mov rdx,QWORD PTR [rbx+104]
 mov QWORD PTR [rdx+r12*8],rax
 lock inc QWORD PTR [rbx+216]
 test rsi,rsi
 jz tl_reap_next
 xor r13d,r13d
 jmp tl_reap_done
tl_reap_next:
 inc r12d
 jmp tl_reap_loop
tl_reap_bad:
 mov r13d,87
tl_reap_done:
 mov eax,r13d
 add rsp,96
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
tl_reap_locked ENDP

boom_provider_threads_reap PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 call tl_pool_valid
 test eax,eax
 jz tl_reap_public_bad
 lea rcx,[rbx+112]
 call AcquireSRWLockExclusive
 mov rcx,rbx
 mov rdx,rsi
 call tl_reap_locked
 mov DWORD PTR [rsp+32],eax
 lea rcx,[rbx+112]
 call ReleaseSRWLockExclusive
 mov eax,DWORD PTR [rsp+32]
 jmp tl_reap_public_done
tl_reap_public_bad:
 mov eax,87
tl_reap_public_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_provider_threads_reap ENDP

boom_provider_threads_close PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 call tl_pool_valid
 test eax,eax
 jz tl_close_bad
 lea rcx,[rbx+112]
 call AcquireSRWLockExclusive
 mov rcx,rbx
 xor edx,edx
 call tl_reap_locked
 mov DWORD PTR [rsp+32],eax
 test eax,eax
 jnz tl_close_unlock
 mov DWORD PTR [rbx+8],1
tl_close_unlock:
 lea rcx,[rbx+112]
 call ReleaseSRWLockExclusive
 mov eax,DWORD PTR [rsp+32]
 jmp tl_close_done
tl_close_bad:
 mov eax,87
tl_close_done:
 add rsp,48
 pop rbx
 ret
boom_provider_threads_close ENDP

; (Context32,argv,pool,operation0) -> void. Original Java start owns its monitor.
boom_provider_threads_service PROC FRAME
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
 sub rsp,208
 .allocstack 208
 .endprolog
 mov rbx,rcx
 mov rdi,r8
 mov DWORD PTR [rsp+160],0
 test rbx,rbx
 jz tl_start_zero
 cmp DWORD PTR [rbx],0
 jne tl_start_zero
 test r9d,r9d
 jnz tl_start_bad
 test rdx,rdx
 jz tl_start_bad
 mov rsi,QWORD PTR [rdx]
 test rsi,rsi
 jz tl_start_null
 mov rcx,rdi
 call tl_pool_valid
 test eax,eax
 jz tl_start_bad
 cmp DWORD PTR [rdi+8],0
 jne tl_start_bad
 mov rcx,rbx
 mov rdx,rsi
 mov r8,rdi
 mov r9,QWORD PTR [rdi+40]
 call tl_object
 test eax,eax
 jz tl_start_zero
 mov rcx,rsi
 mov rdx,QWORD PTR [rdi+24]
 mov r8,rbx
 call boom_runtime_type
 cmp DWORD PTR [rbx],0
 jne tl_start_zero
 mov rcx,rax
 mov rdx,QWORD PTR [rdi+48]
 call boom_type_assignable
 test eax,eax
 jnz tl_start_unsupported
 mov rcx,QWORD PTR [rdi+32]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_current
 test rax,rax
 jz tl_start_bad
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [rdi+128]
 test rax,rax
 jz tl_start_zero
 mov r14,QWORD PTR [rax]
 cmp r14,2
 jl tl_start_bad
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [rdi+136]
 test rax,rax
 jz tl_start_zero
 mov r12,rax
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [rdi+144]
 test rax,rax
 jz tl_start_zero
 mov rax,QWORD PTR [rax]
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 mov rdx,rax
 mov r8,rdi
 mov r9,QWORD PTR [rdi+56]
 call tl_object
 test eax,eax
 jz tl_start_zero
 mov rcx,QWORD PTR [rsp+32]
 mov rdx,rbx
 call QWORD PTR [rdi+152]
 test rax,rax
 jz tl_start_zero
 mov r13,rax
 mov rcx,QWORD PTR [rsp+32]
 mov rdx,rbx
 call QWORD PTR [rdi+160]
 test rax,rax
 jz tl_start_zero
 mov r15,QWORD PTR [rax]
 test r15,r15
 jg tl_start_stack_ready
 xor r15d,r15d
tl_start_stack_ready:
 lea rcx,[rdi+112]
 call AcquireSRWLockExclusive
 mov DWORD PTR [rsp+160],1
 cmp DWORD PTR [rdi+8],0
 jne tl_start_bad
 cmp QWORD PTR [r12],0
 jne tl_start_bad
 cmp DWORD PTR [r13],0
 jne tl_start_bad
 mov rcx,rdi
 xor edx,edx
 call tl_reap_locked
 cmp eax,87
 je tl_start_bad
 cmp DWORD PTR [rdi+120],2
 je tl_start_prior_failure
 xor r9d,r9d
tl_start_find_slot:
 cmp r9d,DWORD PTR [rdi+124]
 jae tl_start_extend
 mov r10d,r9d
 shl r10,6
 add r10,QWORD PTR [rdi+96]
 cmp QWORD PTR [r10+40],0
 jne tl_start_next_slot
 mov r11,QWORD PTR [rdi+104]
 cmp QWORD PTR [r11+r9*8],0
 je tl_start_slot
tl_start_next_slot:
 inc r9d
 jmp tl_start_find_slot
tl_start_extend:
 cmp r9d,DWORD PTR [rdi+12]
 jae tl_start_oom
 inc DWORD PTR [rdi+124]
 mov r10d,r9d
 shl r10,6
 add r10,QWORD PTR [rdi+96]
tl_start_slot:
 mov QWORD PTR [rsp+40],r10
 mov DWORD PTR [rsp+48],r9d
 mov QWORD PTR [r10],rdi
 mov QWORD PTR [r10+8],r12
 mov QWORD PTR [r10+16],r13
 mov QWORD PTR [r10+24],r14
 mov QWORD PTR [r10+32],r15
 mov QWORD PTR [r10+40],0
 mov QWORD PTR [r10+48],rsi
 mov QWORD PTR [r10+56],0
 mov r11,QWORD PTR [rdi+104]
 mov QWORD PTR [r11+r9*8],rsi
 mov DWORD PTR [rsp+64],05453504Eh
 mov DWORD PTR [rsp+68],2
 mov QWORD PTR [rsp+72],rsi
 mov QWORD PTR [rsp+80],r14
 lea rax,tl_main
 mov QWORD PTR [rsp+88],rax
 lea rax,tl_exit
 mov QWORD PTR [rsp+96],rax
 lea rax,tl_uncaught
 mov QWORD PTR [rsp+104],rax
 mov QWORD PTR [rsp+112],r10
 lea rax,tl_publish
 mov QWORD PTR [rsp+120],rax
 lea rax,tl_rollback
 mov QWORD PTR [rsp+128],rax
 mov QWORD PTR [rsp+136],r15
 mov QWORD PTR [rsp+144],0
 mov rcx,QWORD PTR [rdi+32]
 mov rcx,QWORD PTR [rcx]
 lea rdx,[rsp+64]
 call boom_threads_start
 test rax,rax
 jz tl_start_failed
 mov r10,QWORD PTR [rsp+40]
 cmp QWORD PTR [r10+40],rax
 jne tl_start_bad
 lock inc QWORD PTR [rdi+168]
 jmp tl_start_zero
tl_start_failed:
 mov ecx,DWORD PTR [rsp+48]
 mov rdx,QWORD PTR [rdi+104]
 mov QWORD PTR [rdx+rcx*8],0
 mov r10,QWORD PTR [rsp+40]
 xor eax,eax
 mov QWORD PTR [r10],rax
 mov QWORD PTR [r10+8],rax
 mov QWORD PTR [r10+16],rax
 mov QWORD PTR [r10+24],rax
 mov QWORD PTR [r10+32],rax
 mov QWORD PTR [r10+40],rax
 mov QWORD PTR [r10+48],rax
 mov QWORD PTR [r10+56],rax
tl_start_oom:
 mov DWORD PTR [rbx],3
 jmp tl_start_zero
tl_start_prior_failure:
 mov r10,QWORD PTR [rdi+224]
 mov rax,QWORD PTR [r10]
 mov QWORD PTR [rbx],rax
 mov eax,DWORD PTR [r10+8]
 mov DWORD PTR [rbx+8],eax
 mov rax,QWORD PTR [r10+16]
 mov QWORD PTR [rbx+16],rax
 mov rax,QWORD PTR [r10+24]
 mov QWORD PTR [rbx+24],rax
 jmp tl_start_zero
tl_start_null:
 mov DWORD PTR [rbx],1
 jmp tl_start_zero
tl_start_unsupported:
 mov DWORD PTR [rbx],20
 jmp tl_start_zero
tl_start_bad:
 mov DWORD PTR [rbx],7
tl_start_zero:
 cmp DWORD PTR [rsp+160],0
 je tl_start_done
 lea rcx,[rdi+112]
 call ReleaseSRWLockExclusive
tl_start_done:
 xor eax,eax
 add rsp,208
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_threads_service ENDP
