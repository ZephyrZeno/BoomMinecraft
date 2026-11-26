; Wait set sidecar for the existing per-object reentrant Monitor32 heap ABI.
; All runtime code is native MASM. See DESIGN.md for source binding contracts.
option casemap:none
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN GetCurrentThreadId:PROC
EXTERN GetLastError:PROC
EXTERN QueryPerformanceCounter:PROC
EXTERN QueryPerformanceFrequency:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressSingle:PROC
EXTERN WakeByAddressAll:PROC
EXTERN Sleep:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_threads_current:PROC
PUBLIC boom_monitor_wait_open
PUBLIC boom_monitor_wait
PUBLIC boom_monitor_wait_notify
PUBLIC boom_monitor_wait_notify_all
PUBLIC boom_monitor_wait_interrupt
PUBLIC boom_monitor_wait_stop
PUBLIC boom_monitor_wait_stopping
PUBLIC boom_monitor_wait_close

; MWAI72/1: heap8, registry16, receiver-specific interrupt field mapper24,
; waiting and re-entering list32, active40, stopping44, poolNext48, QPC Hz56.
; Slot48: next0, node8, object16, currentThread24, interrupt address32,
; reason40, saved recursion depth44. Slot storage is the waiting thread's stack.
MW_INFINITE EQU 0FFFFFFFFh
MW_INTERRUPTED EQU 010001h
MW_STOPPED EQU 995
MW_NOTIFIED EQU 1
MW_TIMED_OUT EQU 2
MW_INTERRUPT EQU 3
MW_STOP EQU 4
MW_OS_ERROR EQU 5
.data?
ALIGN 8
mw_lock QWORD ?
mw_pools QWORD ?
.code
MW_LOCK MACRO
 lea rcx,mw_lock
 call AcquireSRWLockExclusive
ENDM
MW_UNLOCK MACRO
 lea rcx,mw_lock
 call ReleaseSRWLockExclusive
ENDM

; Lookup compares opaque pool tokens before any dereference. mw_lock held.
mw_find_pool PROC PRIVATE
 lea r10,mw_pools
mw_find_link:
 mov rax,QWORD PTR [r10]
 test rax,rax
 jz mw_find_end
 cmp rax,rcx
 je mw_find_end
 lea r10,[rax+48]
 jmp mw_find_link
mw_find_end:
 ret
mw_find_pool ENDP

mw_find_heap PROC PRIVATE
 mov rax,QWORD PTR [mw_pools]
mw_find_heap_next:
 test rax,rax
 jz mw_find_heap_end
 cmp QWORD PTR [rax+8],rcx
 je mw_find_heap_end
 mov rax,QWORD PTR [rax+48]
 jmp mw_find_heap_next
mw_find_heap_end:
 ret
mw_find_heap ENDP

; Same byte and ordering as monitor_registry_lock in the existing heap runtime.
mw_heap_lock PROC PRIVATE
 mov eax,1
 xchg DWORD PTR [rcx+104],eax
 test eax,eax
 jz mw_heap_locked
mw_heap_lock_busy:
 pause
 cmp DWORD PTR [rcx+104],0
 jne mw_heap_lock_busy
 jmp mw_heap_lock
mw_heap_locked:
 ret
mw_heap_lock ENDP

; (heap,object) while heap monitor registry locked. Node or zero.
mw_node PROC PRIVATE
 mov rax,QWORD PTR [rcx+96]
mw_node_next:
 test rax,rax
 jz mw_node_done
 cmp QWORD PTR [rax],rdx
 je mw_node_done
 mov rax,QWORD PTR [rax+8]
 jmp mw_node_next
mw_node_done:
 ret
mw_node ENDP

; VM owner: (heap, bound platform-thread registry, original field mapper)->pool/null.
; All these inputs outlive the pool. No Java monitor, registry, or heap allocation
; lock is held by this caller. Multiple heaps can have independent wait domains.
boom_monitor_wait_open PROC FRAME
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
 xor r12d,r12d
 test rbx,rbx
 jz mow_done
 test rsi,rsi
 jz mow_done
 test rdi,rdi
 jz mow_done
 cmp DWORD PTR [rbx],048454150h
 jne mow_done
 cmp DWORD PTR [rbx+4],1
 jne mow_done
 cmp DWORD PTR [rbx+108],1
 jne mow_done
 cmp DWORD PTR [rsi],054524547h
 jne mow_done
 cmp DWORD PTR [rsi+4],1
 jne mow_done
 cmp QWORD PTR [rsi+8],rbx
 jne mow_done
 lea rcx,[rsp+32]
 call QueryPerformanceFrequency
 test eax,eax
 jz mow_done
 cmp QWORD PTR [rsp+32],1000
 jb mow_done
 MW_LOCK
 mov rcx,rbx
 call mw_find_heap
 test rax,rax
 jnz mow_unlock
 xor ecx,ecx
 mov edx,4096
 mov r8d,03000h
 mov r9d,4
 call VirtualAlloc
 test rax,rax
 jz mow_unlock
 mov r12,rax
 mov DWORD PTR [rax],04941574Dh
 mov DWORD PTR [rax+4],1
 mov QWORD PTR [rax+8],rbx
 mov QWORD PTR [rax+16],rsi
 mov QWORD PTR [rax+24],rdi
 mov rdx,QWORD PTR [mw_pools]
 mov QWORD PTR [rax+48],rdx
 mov rdx,QWORD PTR [rsp+32]
 mov QWORD PTR [rax+56],rdx
 mov QWORD PTR [mw_pools],rax
mow_unlock:
 MW_UNLOCK
mow_done:
 mov rax,r12
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_monitor_wait_open ENDP

; (pool,object,Context32,signed millis)->0/Java kind/0x10001 interrupt/995 VM stop.
; The two non-Java statuses REQUIRE a checked source adapter. Context+24 is untouched.
boom_monitor_wait PROC FRAME
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
 sub rsp,128
 .allocstack 128
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov r12,r9
 test rdi,rdi
 jz mw_no_context
 mov eax,DWORD PTR [rdi]
 test eax,eax
 jnz mw_return
 test rsi,rsi
 jz mw_null
 call GetCurrentThreadId
 mov r15d,eax
 MW_LOCK
 mov rcx,rbx
 call mw_find_pool
 test rax,rax
 jz mw_unbound
 mov r13,QWORD PTR [rbx+8]
 mov rcx,r13
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz mw_bad
 mov rcx,r13
 call mw_heap_lock
 mov rcx,r13
 mov rdx,rsi
 call mw_node
 test rax,rax
 jz mw_unowned
 mov r14,rax
 cmp DWORD PTR [r14+16],r15d
 jne mw_unowned
 mov eax,DWORD PTR [r14+20]
 test eax,eax
 jz mw_bad_heap
 mov DWORD PTR [rsp+76],eax
 cmp QWORD PTR [r13+112],rax
 jb mw_bad_heap
 cmp DWORD PTR [r14+28],0
 jne mw_unbound_heap
 test r12,r12
 js mw_negative
 mov rcx,QWORD PTR [rbx+16]
 call boom_threads_current
 test rax,rax
 jz mw_unbound_heap
 mov QWORD PTR [rsp+56],rax
 mov rcx,r13
 mov rdx,rax
 call boom_heap_contains
 test eax,eax
 jz mw_bad_heap
 mov rcx,QWORD PTR [rsp+56]
 mov rdx,rdi
 call QWORD PTR [rbx+24]
 cmp DWORD PTR [rdi],0
 jne mw_preserve_heap
 mov rdx,QWORD PTR [rsp+56]
 cmp rax,rdx
 jb mw_bad_heap
 mov rcx,rax
 sub rcx,rdx
 cmp rcx,QWORD PTR [rdx-16]
 jae mw_bad_heap
 ; The Java boolean must be a scalar outside the object's reference prefix.
 mov edx,DWORD PTR [rdx-20]
 shl rdx,3
 cmp rcx,rdx
 jb mw_bad_heap
 mov QWORD PTR [rsp+64],rax
 movzx ecx,BYTE PTR [rax]
 cmp ecx,1
 ja mw_bad_heap
 test ecx,ecx
 jnz mw_preinterrupted
 cmp DWORD PTR [rbx+44],0
 jne mw_prestopped
 cmp DWORD PTR [r14+24],07FFFFFFFh
 jae mw_bad_heap
 cmp DWORD PTR [rbx+40],16384
 jae mw_bad_heap
 test r12,r12
 jz mw_enroll
 lea rcx,[rsp+80]
 call QueryPerformanceCounter
 test eax,eax
 jz mw_bad_heap
mw_enroll:
 ; Zero is the sole unselected reason; addresses remain live through reacquire.
 mov rax,QWORD PTR [rbx+32]
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],r14
 mov QWORD PTR [rsp+48],rsi
 mov DWORD PTR [rsp+72],0
 mov DWORD PTR [rsp+96],0
 lea rax,[rsp+32]
 mov QWORD PTR [rbx+32],rax
 inc DWORD PTR [rbx+40]
 inc DWORD PTR [r14+24]
 mov eax,DWORD PTR [rsp+76]
 dec rax
 sub QWORD PTR [r13+112],rax
 mov DWORD PTR [r14+20],0
 mov DWORD PTR [r14+16],0
 mov DWORD PTR [r13+104],0
 lea rcx,[r14+16]
 call WakeByAddressAll
 ; Keep mw_lock until the first predicate check, then park without either lock.
mw_decide:
 mov eax,DWORD PTR [rsp+72]
 test eax,eax
 jnz mw_decided
 mov DWORD PTR [rsp+100],MW_INFINITE
 test r12,r12
 jz mw_park
 lea rcx,[rsp+88]
 call QueryPerformanceCounter
 test eax,eax
 jz mw_wait_error
 mov rax,QWORD PTR [rsp+88]
 sub rax,QWORD PTR [rsp+80]
 jc mw_wait_error
 mov ecx,1000
 mul rcx
 div QWORD PTR [rbx+56]
 mov rdx,r12
 sub rdx,rax
 jbe mw_timeout
 mov eax,0FFFFFFFEh
 cmp rdx,rax
 cmova rdx,rax
 mov DWORD PTR [rsp+100],edx
mw_park:
 MW_UNLOCK
 lea rcx,[rsp+72]
 lea rdx,[rsp+96]
 mov r8d,4
 mov r9d,DWORD PTR [rsp+100]
 call WaitOnAddress
 test eax,eax
 jnz mw_recheck
 call GetLastError
 cmp eax,1460
 je mw_recheck
 ; A genuine OS failure is preserved unless another event already won.
 MW_LOCK
 cmp DWORD PTR [rsp+72],0
 jne mw_decide
mw_wait_error:
 mov DWORD PTR [rsp+72],MW_OS_ERROR
 jmp mw_decided
mw_recheck:
 MW_LOCK
 jmp mw_decide
mw_timeout:
 mov DWORD PTR [rsp+72],MW_TIMED_OUT
mw_decided:
 MW_UNLOCK
mw_reacquire:
 mov rcx,r13
 call mw_heap_lock
 mov eax,DWORD PTR [r14+16]
 test eax,eax
 jz mw_restore
 mov DWORD PTR [rsp+104],eax
 mov DWORD PTR [r13+104],0
 lea rcx,[r14+16]
 lea rdx,[rsp+104]
 mov r8d,4
 mov r9d,MW_INFINITE
 call WaitOnAddress
 test eax,eax
 jnz mw_reacquire
 ; A failed OS wait must neither bypass ownership nor spin indefinitely.
 mov ecx,1
 call Sleep
 jmp mw_reacquire
mw_restore:
 mov eax,DWORD PTR [rsp+76]
 mov DWORD PTR [r14+20],eax
 mov DWORD PTR [r14+16],r15d
 dec DWORD PTR [r14+24]
 dec rax
 add QWORD PTR [r13+112],rax
 mov DWORD PTR [r13+104],0
 MW_LOCK
 lea rcx,[rbx+32]
 lea rdx,[rsp+32]
mw_unlink:
 mov rax,QWORD PTR [rcx]
 cmp rax,rdx
 je mw_unlinked
 lea rcx,[rax]
 jmp mw_unlink
mw_unlinked:
 mov rax,QWORD PTR [rsp+32]
 mov QWORD PTR [rcx],rax
 dec DWORD PTR [rbx+40]
 mov eax,DWORD PTR [rsp+72]
 cmp eax,MW_INTERRUPT
 je mw_consume_interrupt
 cmp eax,MW_STOP
 je mw_stopped
 cmp eax,MW_OS_ERROR
 je mw_bad
 xor r12d,r12d
 jmp mw_unlock
mw_consume_interrupt:
 mov rcx,QWORD PTR [rsp+64]
 xor eax,eax
 xchg BYTE PTR [rcx],al
 mov r12d,MW_INTERRUPTED
 jmp mw_unlock
mw_preinterrupted:
 mov rcx,QWORD PTR [rsp+64]
 xor eax,eax
 xchg BYTE PTR [rcx],al
 mov DWORD PTR [r13+104],0
 mov r12d,MW_INTERRUPTED
 jmp mw_unlock
mw_prestopped:
 mov DWORD PTR [r13+104],0
mw_stopped:
 mov r12d,MW_STOPPED
 jmp mw_unlock
mw_unowned:
 mov r12d,17
 jmp mw_fail_heap
mw_negative:
 mov r12d,18
 jmp mw_fail_heap
mw_unbound_heap:
 mov r12d,20
 jmp mw_fail_heap
mw_bad_heap:
 mov r12d,7
mw_fail_heap:
 mov DWORD PTR [rdi],r12d
mw_preserve_heap:
 mov r12d,DWORD PTR [rdi]
 mov DWORD PTR [r13+104],0
 jmp mw_unlock
mw_unbound:
 mov r12d,20
 jmp mw_set
mw_bad:
 mov r12d,7
mw_set:
 mov DWORD PTR [rdi],r12d
mw_unlock:
 MW_UNLOCK
 mov eax,r12d
 jmp mw_return
mw_null:
 mov DWORD PTR [rdi],4
 mov eax,4
 jmp mw_return
mw_no_context:
 mov eax,7
mw_return:
 add rsp,128
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_monitor_wait ENDP

; Drop-in ABI for existing heap/object/Context32 notification calls.
boom_monitor_wait_notify PROC
 xor r9d,r9d
 jmp mw_notify
boom_monitor_wait_notify ENDP
boom_monitor_wait_notify_all PROC
 mov r9d,1
 jmp mw_notify
boom_monitor_wait_notify_all ENDP

mw_notify PROC PRIVATE FRAME
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
 mov rdi,r8
 mov r12d,r9d
 test rdi,rdi
 jz mwn_noctx
 mov eax,DWORD PTR [rdi]
 test eax,eax
 jnz mwn_done
 test rsi,rsi
 jz mwn_null
 test rbx,rbx
 jz mwn_bad
 cmp DWORD PTR [rbx],048454150h
 jne mwn_bad
 cmp DWORD PTR [rbx+4],1
 jne mwn_bad
 cmp DWORD PTR [rbx+108],1
 jne mwn_bad
 call boom_heap_contains
 test eax,eax
 jz mwn_bad
 call GetCurrentThreadId
 mov r13d,eax
 MW_LOCK
 mov rcx,rbx
 call mw_heap_lock
 mov rcx,rbx
 mov rdx,rsi
 call mw_node
 test rax,rax
 jz mwn_unowned
 cmp DWORD PTR [rax+16],r13d
 jne mwn_unowned
 cmp DWORD PTR [rax+20],0
 je mwn_corrupt
 cmp QWORD PTR [rbx+112],0
 je mwn_corrupt
 cmp DWORD PTR [rax+28],0
 jne mwn_unsupported
 mov DWORD PTR [rbx+104],0
 mov rcx,rbx
 call mw_find_heap
 test rax,rax
 jz mwn_ok
 mov r13,QWORD PTR [rax+32]
mwn_scan:
 test r13,r13
 jz mwn_ok
 cmp QWORD PTR [r13+16],rsi
 jne mwn_next
 cmp DWORD PTR [r13+40],0
 jne mwn_next
 mov DWORD PTR [r13+40],MW_NOTIFIED
 lea rcx,[r13+40]
 call WakeByAddressSingle
 test r12d,r12d
 jz mwn_ok
mwn_next:
 mov r13,QWORD PTR [r13]
 jmp mwn_scan
mwn_unowned:
 mov r12d,17
 jmp mwn_fail
mwn_unsupported:
 mov r12d,20
 jmp mwn_fail
mwn_corrupt:
 mov r12d,7
mwn_fail:
 mov DWORD PTR [rbx+104],0
 mov DWORD PTR [rdi],r12d
 jmp mwn_unlock
mwn_ok:
 xor r12d,r12d
mwn_unlock:
 MW_UNLOCK
 mov eax,r12d
 jmp mwn_done
mwn_null:
 mov eax,4
 jmp mwn_set
mwn_bad:
 mov eax,7
mwn_set:
 mov DWORD PTR [rdi],eax
 jmp mwn_done
mwn_noctx:
 mov eax,7
mwn_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
mw_notify ENDP

; Monitor-specific Thread.interrupt0 wake. Original Java has already stored true
; in the volatile field. A delayed native wake never reasserts a cleared flag.
; 1168 means no matching Java monitor waiter: the interrupt dispatcher must
; check its other blocking domains before declaring the whole interrupt handled.
boom_monitor_wait_interrupt PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 MW_LOCK
 mov rcx,rbx
 call mw_find_pool
 test rax,rax
 jz mwi_bad
 mov rcx,QWORD PTR [rbx+8]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz mwi_bad
 mov rax,QWORD PTR [rbx+32]
mwi_scan:
 test rax,rax
 jz mwi_absent
 cmp QWORD PTR [rax+24],rsi
 jne mwi_next
 cmp DWORD PTR [rax+40],0
 jne mwi_ok
 mov rdx,QWORD PTR [rax+32]
 cmp BYTE PTR [rdx],1
 jne mwi_ok
 mov DWORD PTR [rax+40],MW_INTERRUPT
 lea rcx,[rax+40]
 call WakeByAddressSingle
 jmp mwi_ok
mwi_next:
 mov rax,QWORD PTR [rax]
 jmp mwi_scan
mwi_absent:
 mov ebx,1168
 jmp mwi_unlock
mwi_bad:
 mov ebx,87
 jmp mwi_unlock
mwi_ok:
 xor ebx,ebx
mwi_unlock:
 MW_UNLOCK
 mov eax,ebx
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_monitor_wait_interrupt ENDP

boom_monitor_wait_stop PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 MW_LOCK
 mov rcx,rbx
 call mw_find_pool
 test rax,rax
 jz mws_bad
 mov DWORD PTR [rbx+44],1
 mov rbx,QWORD PTR [rbx+32]
mws_scan:
 test rbx,rbx
 jz mws_ok
 cmp DWORD PTR [rbx+40],0
 jne mws_next
 mov DWORD PTR [rbx+40],MW_STOP
 lea rcx,[rbx+40]
 call WakeByAddressSingle
mws_next:
 mov rbx,QWORD PTR [rbx]
 jmp mws_scan
mws_ok:
 xor ebx,ebx
 jmp mws_unlock
mws_bad:
 mov ebx,87
mws_unlock:
 MW_UNLOCK
 mov eax,ebx
 add rsp,32
 pop rbx
 ret
boom_monitor_wait_stop ENDP

; Source stop-token issuer checks both the global VM stop and this domain.
; False for running, closed, null, and unknown handles. No unchecked dereference.
boom_monitor_wait_stopping PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 MW_LOCK
 mov rcx,rbx
 call mw_find_pool
 xor ebx,ebx
 test rax,rax
 jz mwsq_done
 mov ebx,DWORD PTR [rax+44]
mwsq_done:
 MW_UNLOCK
 mov eax,ebx
 add rsp,32
 pop rbx
 ret
boom_monitor_wait_stopping ENDP

; Join all guest callers before releasing the heap or its registry. Every
; stack registration and all queued pool users are protected by mw_lock.
boom_monitor_wait_close PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 MW_LOCK
 mov rcx,rbx
 call mw_find_pool
 test rax,rax
 jz mwc_bad
 cmp DWORD PTR [rbx+44],1
 jne mwc_busy
 cmp DWORD PTR [rbx+40],0
 jne mwc_busy
 cmp QWORD PTR [rbx+32],0
 jne mwc_busy
 mov rcx,QWORD PTR [rbx+48]
 mov QWORD PTR [r10],rcx
 MW_UNLOCK
 mov rcx,rbx
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
 test eax,eax
 jnz mwc_ok
 call GetLastError
 jmp mwc_done
mwc_ok:
 xor eax,eax
 jmp mwc_done
mwc_bad:
 mov ebx,87
 jmp mwc_unlock
mwc_busy:
 mov ebx,170
mwc_unlock:
 MW_UNLOCK
 mov eax,ebx
mwc_done:
 add rsp,32
 pop rbx
 ret
boom_monitor_wait_close ENDP

IFDEF MONITOR_WAIT_TEST
; Test-only synchronized sample: number of total and still eligible waiters
; for one object in low and high DWORD respectively; acquire no guest locks.
PUBLIC boom_test_monitor_wait_counts
boom_test_monitor_wait_counts PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 MW_LOCK
 mov rcx,rbx
 call mw_find_pool
 xor ebx,ebx
 test rax,rax
 jz mwt_done
 mov rax,QWORD PTR [rax+32]
mwt_scan:
 test rax,rax
 jz mwt_done
 cmp QWORD PTR [rax+16],rsi
 jne mwt_next
 inc rbx
 cmp DWORD PTR [rax+40],0
 jne mwt_next
 mov rdx,0100000000h
 add rbx,rdx
mwt_next:
 mov rax,QWORD PTR [rax]
 jmp mwt_scan
mwt_done:
 MW_UNLOCK
 mov rax,rbx
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_test_monitor_wait_counts ENDP
ENDIF
END
