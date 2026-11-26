; Original Unsafe.park/unpark over private per-thread normal Object gates.
; No caller Java monitor is required. Only runtime monitor helpers are called;
; no Object.wait Java/native frame or source Object.wait counter is introduced.
; PARK128/1: state8,active12,heapCell16,registryCell24,TLCP32,OWAI40,RPRC48,
; typeMap56,UnsafeLayout64,ThreadType72,virtualType80,irqMap88,peerMap96,tidMap104,
; slots112,gateRoots120. Lifecycle is bounded by the existing VM wait owner.
; Slot64: real token0,JavaId8,weak source oop16,gate24,permit32,borrow36,
; wait entries40,unpark operations48,reserved56. Only gateRoots are strong roots.
.data
ALIGN 8
up_lock QWORD 0
up_main_oop QWORD 0
up_main_token QWORD 0
up_main_id QWORD 0
PUBLIC boom_unsafe_park_slots
boom_unsafe_park_slots BYTE 1048576 DUP(0)
PUBLIC boom_unsafe_park_gate_roots
boom_unsafe_park_gate_roots QWORD 16384 DUP(0)
PUBLIC boom_unsafe_park_counters
; park0,unpark8,actual waits16,fast permits24,woken permits32,restored IRQ40,
; issued stops48,gates56,active64,waiters72,unpermitted returns80,negative88,
; expired absolute96,last DWORD timeout104,early IRQ112,recycled gates120.
boom_unsafe_park_counters QWORD 16 DUP(0)
.code

up_valid PROC PRIVATE
 xor eax,eax
 test rcx,rcx
 jz up_valid_done
 cmp DWORD PTR [rcx],04B524150h
 jne up_valid_done
 cmp DWORD PTR [rcx+4],1
 jne up_valid_done
 mov edx,16
up_valid_pointer:
 cmp QWORD PTR [rcx+rdx],0
 je up_valid_done
 add edx,8
 cmp edx,128
 jb up_valid_pointer
 mov eax,1
up_valid_done:
 ret
up_valid ENDP

; (Context32,source Thread oop,PARK128) -> token RAX,JavaId RDX,irq address R8.
; No native token is dereferenced here. Normal FMAP callbacks validate each oop.
up_thread PROC PRIVATE FRAME
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
 mov r12,r8
 xor edi,edi
 xor r13d,r13d
 xor r14d,r14d
 mov rcx,QWORD PTR [r12+16]
 mov rcx,QWORD PTR [rcx]
 call boom_heap_contains
 test eax,eax
 jz up_thread_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r12+56]
 mov r8,rbx
 call boom_runtime_type
 test rax,rax
 jz up_thread_done
 mov QWORD PTR [rsp+32],rax
 mov rcx,rax
 mov rdx,QWORD PTR [r12+72]
 call boom_type_assignable
 test eax,eax
 jz up_thread_bad
 mov rcx,QWORD PTR [rsp+32]
 mov rdx,QWORD PTR [r12+80]
 call boom_type_assignable
 test eax,eax
 jnz up_thread_unbound
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [r12+96]
 test rax,rax
 jz up_thread_done
 mov rdi,QWORD PTR [rax]
 test rdi,rdi
 jz up_thread_done
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [r12+104]
 test rax,rax
 jz up_thread_done
 mov r13,QWORD PTR [rax]
 test r13,r13
 jle up_thread_bad
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [r12+88]
 test rax,rax
 jz up_thread_done
 cmp BYTE PTR [rax],1
 ja up_thread_bad
 mov r14,rax
 jmp up_thread_done
up_thread_bad:
 mov DWORD PTR [rbx],7
 xor edi,edi
 jmp up_thread_done
up_thread_unbound:
 mov DWORD PTR [rbx],20
 xor edi,edi
up_thread_done:
 cmp DWORD PTR [rbx],0
 je up_thread_values
 xor edi,edi
up_thread_values:
 mov rax,rdi
 mov rdx,r13
 mov r8,r14
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
up_thread ENDP

; (PARK pool,target,token,JavaId)->1/0. TLCP lock protects source-owned slots.
; The primordial oop/token/id were captured from its actual FLS record at open.
up_managed PROC PRIVATE FRAME
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
 mov r12,r8
 mov r13,r9
 xor edi,edi
 cmp QWORD PTR [up_main_oop],rsi
 jne up_managed_worker
 cmp QWORD PTR [up_main_token],r12
 jne up_managed_done
 cmp QWORD PTR [up_main_id],r13
 jne up_managed_done
 mov edi,1
 jmp up_managed_done
up_managed_worker:
 mov rbx,QWORD PTR [rbx+32]
 cmp DWORD PTR [rbx],050434C54h
 jne up_managed_done
 cmp DWORD PTR [rbx+4],1
 jne up_managed_done
 cmp DWORD PTR [rbx+8],0
 jne up_managed_done
 lea rcx,[rbx+112]
 call AcquireSRWLockShared
 mov ecx,DWORD PTR [rbx+124]
 cmp ecx,DWORD PTR [rbx+12]
 ja up_managed_unlock
 cmp ecx,16384
 ja up_managed_unlock
 mov rdx,QWORD PTR [rbx+96]
 test rdx,rdx
 jz up_managed_unlock
 xor eax,eax
up_managed_scan:
 cmp eax,ecx
 jae up_managed_unlock
 cmp QWORD PTR [rdx+48],rsi
 jne up_managed_next
 cmp QWORD PTR [rdx+40],r12
 jne up_managed_next
 cmp QWORD PTR [rdx+24],r13
 jne up_managed_next
 cmp QWORD PTR [rdx],rbx
 jne up_managed_unlock
 mov r8,QWORD PTR [rdx+8]
 test r8,r8
 jz up_managed_unlock
 cmp QWORD PTR [r8],r12
 jne up_managed_unlock
 mov edi,1
 jmp up_managed_unlock
up_managed_next:
 add rdx,64
 inc eax
 jmp up_managed_scan
up_managed_unlock:
 lea rcx,[rbx+112]
 call ReleaseSRWLockShared
up_managed_done:
 mov eax,edi
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
up_managed ENDP

; (Context32,pool,target,token,JavaId stack5)->borrowed Slot64/null.
; Normal gate allocation/its original empty Object ctor run outside up_lock.
up_slot PROC PRIVATE FRAME
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
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov r12,r8
 mov r13,r9
 mov r15,QWORD PTR [rsp+160]
 xor r14d,r14d
up_slot_retry:
 lea rcx,up_lock
 call AcquireSRWLockExclusive
 mov rdi,QWORD PTR [rsi+112]
 xor ecx,ecx
up_slot_find:
 cmp QWORD PTR [rdi],r13
 jne up_slot_next
 cmp QWORD PTR [rdi+8],r15
 jne up_slot_next
 cmp QWORD PTR [rdi+16],r12
 je up_slot_found
up_slot_next:
 add rdi,64
 inc ecx
 cmp ecx,16384
 jb up_slot_find
 test r14,r14
 jz up_slot_allocate
 mov rdi,QWORD PTR [rsi+112]
 xor ecx,ecx
up_slot_empty:
 cmp QWORD PTR [rdi],0
 je up_slot_publish
 add rdi,64
 inc ecx
 cmp ecx,16384
 jb up_slot_empty
 ; Recycle only unborrowed records no longer owned by main or a live TLCP slot.
 ; Weak source addresses are compared, never dereferenced after retirement.
 mov rdi,QWORD PTR [rsi+112]
 xor ecx,ecx
up_slot_retired:
 cmp DWORD PTR [rdi+36],0
 jne up_slot_retired_next
 mov DWORD PTR [rsp+40],ecx
 mov rcx,rsi
 mov rdx,QWORD PTR [rdi+16]
 mov r8,QWORD PTR [rdi]
 mov r9,QWORD PTR [rdi+8]
 call up_managed
 mov ecx,DWORD PTR [rsp+40]
 test eax,eax
 jnz up_slot_retired_next
 lock inc QWORD PTR [boom_unsafe_park_counters+120]
 jmp up_slot_publish
up_slot_retired_next:
 add rdi,64
 inc ecx
 cmp ecx,16384
 jb up_slot_retired
 lea rcx,up_lock
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rbx],3
 xor edi,edi
 jmp up_slot_done
up_slot_publish:
 mov QWORD PTR [rdi],r13
 mov QWORD PTR [rdi+8],r15
 mov QWORD PTR [rdi+16],r12
 mov QWORD PTR [rdi+24],r14
 mov DWORD PTR [rdi+32],0
 mov DWORD PTR [rdi+36],0
 mov QWORD PTR [rdi+40],0
 mov QWORD PTR [rdi+48],0
 mov QWORD PTR [rdi+56],0
 mov rax,QWORD PTR [rsi+120]
 mov QWORD PTR [rax+rcx*8],r14
 lock inc QWORD PTR [boom_unsafe_park_counters+56]
up_slot_found:
 inc DWORD PTR [rdi+36]
 lea rcx,up_lock
 call ReleaseSRWLockExclusive
 jmp up_slot_done
up_slot_allocate:
 lea rcx,up_lock
 call ReleaseSRWLockExclusive
 lea rcx,UP_OBJECT_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne up_slot_zero
 mov rcx,QWORD PTR [rsi+16]
 mov rcx,QWORD PTR [rcx]
 lea rdx,UP_OBJECT_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz up_slot_zero
 mov r14,rax
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call UP_OBJECT_CTOR
 cmp DWORD PTR [rbx],0
 je up_slot_retry
up_slot_zero:
 xor edi,edi
up_slot_done:
 mov rax,rdi
 add rsp,64
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
up_slot ENDP

PUBLIC boom_provider_unsafe_park_open
boom_provider_unsafe_park_open PROC FRAME
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
 mov edi,87
 call up_valid
 test eax,eax
 jz up_open_done
 cmp DWORD PTR [rbx+8],0
 jne up_open_busy
 mov rax,QWORD PTR [rbx+40]
 cmp DWORD PTR [rax],04941574Fh
 jne up_open_done
 cmp DWORD PTR [rax+4],1
 jne up_open_done
 cmp DWORD PTR [rax+8],2
 jne up_open_done
 cmp QWORD PTR [rax+40],0
 je up_open_done
 mov rax,QWORD PTR [rbx+48]
 cmp DWORD PTR [rax],043525052h
 jne up_open_done
 cmp DWORD PTR [rax+4],2
 jne up_open_done
 cmp DWORD PTR [rax+8],2
 jne up_open_done
 mov rcx,QWORD PTR [rbx+24]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_current
 test rax,rax
 jz up_open_done
 mov rsi,rax
 mov QWORD PTR [rsp+32],0
 mov QWORD PTR [rsp+40],0
 mov QWORD PTR [rsp+48],0
 mov QWORD PTR [rsp+56],0
 lea rcx,[rsp+32]
 mov rdx,rsi
 mov r8,rbx
 call up_thread
 test rax,rax
 jz up_open_done
 cmp rdx,1
 jne up_open_done
 mov QWORD PTR [up_main_oop],rsi
 mov QWORD PTR [up_main_token],rax
 mov QWORD PTR [up_main_id],rdx
 mov DWORD PTR [rbx+8],2
 xor edi,edi
 jmp up_open_done
up_open_busy:
 mov edi,170
up_open_done:
 mov eax,edi
 add rsp,64
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_unsafe_park_open ENDP

PUBLIC boom_provider_unsafe_park_close
boom_provider_unsafe_park_close PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov esi,87
 call up_valid
 test eax,eax
 jz up_close_done
 cmp DWORD PTR [rbx+8],4
 je up_close_ok
 cmp DWORD PTR [rbx+8],2
 jne up_close_done
 lea rcx,up_lock
 call AcquireSRWLockExclusive
 mov esi,170
 cmp DWORD PTR [rbx+12],0
 jne up_close_unlock
 mov rax,QWORD PTR [rbx+40]
 cmp DWORD PTR [rax+8],3
 jne up_close_unlock
 mov rax,QWORD PTR [rbx+48]
 cmp DWORD PTR [rax+8],4
 jne up_close_unlock
 mov r10,QWORD PTR [rbx+112]
 mov r11,QWORD PTR [rbx+120]
 xor ecx,ecx
up_close_clear:
 mov QWORD PTR [r11+rcx*8],0
 mov QWORD PTR [r10],0
 mov QWORD PTR [r10+8],0
 mov QWORD PTR [r10+16],0
 mov QWORD PTR [r10+24],0
 mov QWORD PTR [r10+32],0
 mov QWORD PTR [r10+40],0
 mov QWORD PTR [r10+48],0
 mov QWORD PTR [r10+56],0
 add r10,64
 inc ecx
 cmp ecx,16384
 jb up_close_clear
 mov QWORD PTR [up_main_oop],0
 mov QWORD PTR [up_main_token],0
 mov QWORD PTR [up_main_id],0
 mov DWORD PTR [rbx+8],4
 xor esi,esi
up_close_unlock:
 lea rcx,up_lock
 call ReleaseSRWLockExclusive
 jmp up_close_done
up_close_ok:
 xor esi,esi
up_close_done:
 mov eax,esi
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_provider_unsafe_park_close ENDP

PUBLIC boom_provider_unsafe_park_service
boom_provider_unsafe_park_service PROC FRAME
 push rbx
 .pushreg rbx
 push rbp
 .pushreg rbp
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
 sub rsp,200
 .allocstack 200
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov DWORD PTR [rsp+64],r9d
 mov DWORD PTR [rsp+72],0
 mov DWORD PTR [rsp+80],0
 mov DWORD PTR [rsp+88],0
 mov DWORD PTR [rsp+128],0
 mov DWORD PTR [rsp+136],0
 xor r14d,r14d
 test rbx,rbx
 jz up_service_done
 cmp DWORD PTR [rbx],0
 jne up_service_done
 cmp r9d,1
 ja up_service_bad
 mov rcx,rdi
 call up_valid
 test eax,eax
 jz up_service_bad
 test rsi,rsi
 jz up_service_bad
 cmp DWORD PTR [rdi+8],2
 jne up_service_unbound
 lea rcx,up_lock
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rdi+8],2
 jne up_service_closed_unlock
 inc DWORD PTR [rdi+12]
 lea rcx,up_lock
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rsp+80],1
 lock inc QWORD PTR [boom_unsafe_park_counters+64]
 mov rdx,QWORD PTR [rsi]
 test rdx,rdx
 jz up_service_null
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 call boom_heap_contains
 test eax,eax
 jz up_service_bad
 mov rcx,QWORD PTR [rsi]
 mov rdx,QWORD PTR [rdi+64]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz up_service_cleanup
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_current
 test rax,rax
 jz up_service_unbound
 mov rbp,rax
 cmp DWORD PTR [rsp+64],0
 je up_park_target
 lock inc QWORD PTR [boom_unsafe_park_counters+8]
 mov rbp,QWORD PTR [rsi+8]
 test rbp,rbp
 jz up_service_cleanup
 jmp up_resolve
up_park_target:
 lock inc QWORD PTR [boom_unsafe_park_counters]
up_resolve:
 mov rcx,rbx
 mov rdx,rbp
 mov r8,rdi
 call up_thread
 cmp DWORD PTR [rbx],0
 jne up_service_cleanup
 mov r12,rax
 mov r13,rdx
 mov r15,r8
 test r12,r12
 jnz up_check_owned
 cmp DWORD PTR [rsp+64],1
 je up_service_cleanup
 jmp up_service_unbound
up_check_owned:
 mov rcx,rdi
 mov rdx,rbp
 mov r8,r12
 mov r9,r13
 call up_managed
 test eax,eax
 jz up_service_unbound
 cmp DWORD PTR [rsp+64],1
 je up_get_slot
 ; A verified shared VM stop never turns into Java park success.
 mov rax,QWORD PTR [rdi+48]
 cmp DWORD PTR [rax+8],4
 je up_request_global_stop
 mov rax,QWORD PTR [rdi+40]
 cmp DWORD PTR [rax+8],3
 je up_request_stop
 mov rax,QWORD PTR [rsi+16]
 test rax,rax
 js up_negative_time
 cmp DWORD PTR [rsi+8],1
 ja up_service_bad
 cmp DWORD PTR [rsi+8],0
 jne up_absolute
 test rax,rax
 jz up_infinite
 xor edx,edx
 mov ecx,1000000
 div rcx
 test rax,rax
 jnz up_timeout_dword
 mov eax,1
 jmp up_timeout_dword
up_absolute:
 lea rcx,[rsp+144]
 call GetSystemTimeAsFileTime
 mov rax,QWORD PTR [rsp+144]
 mov rcx,019DB1DED53E8000h
 sub rax,rcx
 xor edx,edx
 mov ecx,10000
 div rcx
 mov rdx,QWORD PTR [rsi+16]
 cmp rdx,rax
 jle up_expired_time
 sub rdx,rax
 mov rax,rdx
up_timeout_dword:
 mov eax,eax
 mov QWORD PTR [boom_unsafe_park_counters+104],rax
 test eax,eax
 jnz up_timeout_nonzero
 mov DWORD PTR [rsp+128],1
 mov QWORD PTR [rsp+96],0
 jmp up_get_slot
up_timeout_nonzero:
 cmp eax,-1
 je up_infinite
 mov QWORD PTR [rsp+96],rax
 jmp up_get_slot
up_infinite:
 mov QWORD PTR [rsp+96],0
 mov eax,-1
 mov QWORD PTR [boom_unsafe_park_counters+104],rax
up_get_slot:
 mov rcx,rbx
 mov rdx,rdi
 mov r8,rbp
 mov r9,r12
 mov QWORD PTR [rsp+32],r13
 call up_slot
 test rax,rax
 jz up_service_cleanup
 mov r14,rax
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [r14+24]
 mov r8,rbx
 call boom_monitor_enter
 cmp DWORD PTR [rbx],0
 jne up_service_cleanup
 mov DWORD PTR [rsp+72],1
 cmp DWORD PTR [rsp+64],1
 je up_unpark
 xor eax,eax
 xchg eax,DWORD PTR [r14+32]
 test eax,eax
 jnz up_fast_permit
 cmp BYTE PTR [r15],1
 je up_early_interrupt
 cmp BYTE PTR [r15],1
 ja up_service_bad
 cmp DWORD PTR [rsp+128],1
 je up_service_cleanup
 lock inc QWORD PTR [boom_unsafe_park_counters+16]
 lock inc QWORD PTR [boom_unsafe_park_counters+72]
 inc QWORD PTR [r14+40]
 mov rcx,QWORD PTR [rdi+40]
 mov rcx,QWORD PTR [rcx+40]
 mov rdx,QWORD PTR [r14+24]
 mov r8,rbx
 mov r9,QWORD PTR [rsp+96]
 call boom_monitor_wait
 mov DWORD PTR [rsp+88],eax
 lock dec QWORD PTR [boom_unsafe_park_counters+72]
 cmp eax,010001h
 je up_restore_interrupt
 cmp eax,995
 je up_wait_stopped
 test eax,eax
 jnz up_service_cleanup
 jmp up_consume_wake
up_restore_interrupt:
 lock or BYTE PTR [r15],1
 lock inc QWORD PTR [boom_unsafe_park_counters+40]
up_consume_wake:
 xor eax,eax
 xchg eax,DWORD PTR [r14+32]
 test eax,eax
 jz up_unpermitted_return
 lock inc QWORD PTR [boom_unsafe_park_counters+32]
 jmp up_service_cleanup
up_unpermitted_return:
 lock inc QWORD PTR [boom_unsafe_park_counters+80]
 jmp up_service_cleanup
up_wait_stopped:
 mov DWORD PTR [rsp+136],1
 jmp up_service_cleanup
up_unpark:
 mov DWORD PTR [r14+32],1
 inc QWORD PTR [r14+48]
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [r14+24]
 mov r8,rbx
 call boom_monitor_notify
 jmp up_service_cleanup
up_fast_permit:
 lock inc QWORD PTR [boom_unsafe_park_counters+24]
 jmp up_service_cleanup
up_early_interrupt:
 lock inc QWORD PTR [boom_unsafe_park_counters+112]
 jmp up_service_cleanup
up_negative_time:
 lock inc QWORD PTR [boom_unsafe_park_counters+88]
 jmp up_service_cleanup
up_expired_time:
 lock inc QWORD PTR [boom_unsafe_park_counters+96]
 jmp up_service_cleanup
up_request_stop:
 mov DWORD PTR [rsp+136],1
 jmp up_service_cleanup
up_request_global_stop:
 mov DWORD PTR [rsp+136],2
 jmp up_service_cleanup
up_service_closed_unlock:
 lea rcx,up_lock
 call ReleaseSRWLockExclusive
 jmp up_service_unbound
up_service_null:
 mov DWORD PTR [rbx],4
 jmp up_service_cleanup
up_service_bad:
 mov DWORD PTR [rbx],7
 jmp up_service_cleanup
up_service_unbound:
 mov DWORD PTR [rbx],20
up_service_cleanup:
 cmp DWORD PTR [rsp+72],0
 je up_service_stop
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [r14+24]
 mov r8,rbx
 call boom_monitor_exit
up_service_stop:
 cmp DWORD PTR [rsp+136],0
 je up_service_release
 cmp DWORD PTR [rbx],0
 jne up_service_release
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+48]
 xor r8d,r8d
 cmp DWORD PTR [rsp+136],2
 je up_service_issue_stop
 mov r8,QWORD PTR [rdi+40]
 mov r8,QWORD PTR [r8+40]
up_service_issue_stop:
 call boom_provider_reference_issue_stop
 cmp DWORD PTR [rbx],0B002h
 jne up_service_release
 lock inc QWORD PTR [boom_unsafe_park_counters+48]
up_service_release:
 test r14,r14
 jz up_service_active
 lock dec DWORD PTR [r14+36]
up_service_active:
 cmp DWORD PTR [rsp+80],0
 je up_service_done
 lock dec DWORD PTR [rdi+12]
 lock dec QWORD PTR [boom_unsafe_park_counters+64]
up_service_done:
 xor eax,eax
 add rsp,200
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_provider_unsafe_park_service ENDP
