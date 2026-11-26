; Pending-reference batch transport, native kernel only; no Java replacement.
; Pool page RPND/1: heap8, reserved SRW16, pendingEvent24, stopEvent32,
; strong head cell40, waiters48, stopping52, frozen56, leaseOwner60, next64.
; publish accepts one complete caller-rooted batch; BUSY retains caller ownership.
; The VM must join producers/consumers before destroying their heap or pool.
; A root lease pins the head cell and blocks publish/get/wait/stop/destroy.
option casemap:none
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN CreateEventW:PROC
EXTERN SetEvent:PROC
EXTERN ResetEvent:PROC
EXTERN CloseHandle:PROC
EXTERN WaitForMultipleObjects:PROC
EXTERN GetCurrentThreadId:PROC
EXTERN GetLastError:PROC
EXTERN SetLastError:PROC
EXTERN boom_heap_contains:PROC
PUBLIC boom_reference_pending_create
PUBLIC boom_reference_pending_publish
PUBLIC boom_reference_pending_get
PUBLIC boom_reference_pending_has
PUBLIC boom_reference_pending_wait
PUBLIC boom_reference_pending_stop
PUBLIC boom_reference_pending_stopping
PUBLIC boom_reference_pending_roots_begin
PUBLIC boom_reference_pending_roots_end
PUBLIC boom_reference_pending_destroy
.data?
ALIGN 8
rp_lock QWORD ?
rp_head QWORD ?
rp_count DWORD ?
.code
RP_SAVE MACRO
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
 sub rsp,64
 .allocstack 64
 .endprolog
ENDM
RP_RETURN MACRO
 add rsp,64
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
ENDM
RP_LOCK MACRO
 lea rcx,rp_lock
 call AcquireSRWLockExclusive
 mov rcx,rbx
 call rp_find
ENDM
RP_UNLOCK MACRO
 lea rcx,rp_lock
 call ReleaseSRWLockExclusive
 mov eax,edi
 RP_RETURN
ENDM

; Global lock protects pool lifetime, including callers queued behind destroy.
; RCX candidate -> RAX live pool/0, R10 predecessor. Never read unknown pointers.
rp_find PROC PRIVATE
 xor r10d,r10d
 mov r11d,DWORD PTR [rp_count]
 cmp r11d,1024
 ja rp_find_bad
 mov rax,QWORD PTR [rp_head]
rp_find_next:
 test rax,rax
 jz rp_find_bad
 test r11d,r11d
 jz rp_find_bad
 dec r11d
 cmp rax,rcx
 je rp_find_header
 mov r10,rax
 mov rax,QWORD PTR [rax+64]
 jmp rp_find_next
rp_find_header:
 cmp DWORD PTR [rax],0444E5052h
 jne rp_find_bad
 cmp DWORD PTR [rax+4],1
 jne rp_find_bad
 cmp QWORD PTR [rax+8],0
 je rp_find_bad
 cmp QWORD PTR [rax+16],0
 jne rp_find_bad
 cmp QWORD PTR [rax+24],0
 je rp_find_bad
 cmp QWORD PTR [rax+32],0
 je rp_find_bad
 cmp DWORD PTR [rax+48],16384
 ja rp_find_bad
 cmp DWORD PTR [rax+52],1
 ja rp_find_bad
 cmp DWORD PTR [rax+56],1
 ja rp_find_bad
 ret
rp_find_bad:
 xor eax,eax
 ret
rp_find ENDP

rp_error PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 call GetLastError
 test eax,eax
 jnz rp_error_done
 mov eax,31
rp_error_done:
 add rsp,40
 ret
rp_error ENDP

boom_reference_pending_create PROC FRAME
 RP_SAVE
 mov rsi,rcx
 xor ebx,ebx
 mov r12d,87
 test rsi,rsi
 jz rp_create_fail
 cmp DWORD PTR [rsi],048454150h
 jne rp_create_fail
 cmp DWORD PTR [rsi+4],1
 jne rp_create_fail
 xor ecx,ecx
 mov edx,4096
 mov r8d,03000h
 mov r9d,4
 call VirtualAlloc
 test rax,rax
 jz rp_create_os_error
 mov rbx,rax
 mov DWORD PTR [rax],0444E5052h
 mov DWORD PTR [rax+4],1
 mov QWORD PTR [rax+8],rsi
 xor ecx,ecx
 mov edx,1
 xor r8d,r8d
 xor r9d,r9d
 call CreateEventW
 test rax,rax
 jz rp_create_os_error
 mov QWORD PTR [rbx+24],rax
 xor ecx,ecx
 mov edx,1
 xor r8d,r8d
 xor r9d,r9d
 call CreateEventW
 test rax,rax
 jz rp_create_os_error
 mov QWORD PTR [rbx+32],rax
 lea rcx,rp_lock
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rp_count],1024
 jae rp_create_full
 mov rax,QWORD PTR [rp_head]
 mov QWORD PTR [rbx+64],rax
 mov QWORD PTR [rp_head],rbx
 inc DWORD PTR [rp_count]
 lea rcx,rp_lock
 call ReleaseSRWLockExclusive
 mov rax,rbx
 RP_RETURN
rp_create_full:
 mov r12d,170
 lea rcx,rp_lock
 call ReleaseSRWLockExclusive
 jmp rp_create_fail
rp_create_os_error:
 call rp_error
 mov r12d,eax
rp_create_fail:
 test rbx,rbx
 jz rp_create_set_error
 mov rcx,QWORD PTR [rbx+24]
 test rcx,rcx
 jz rp_create_close_stop
 call CloseHandle
rp_create_close_stop:
 mov rcx,QWORD PTR [rbx+32]
 test rcx,rcx
 jz rp_create_free
 call CloseHandle
rp_create_free:
 mov rcx,rbx
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
rp_create_set_error:
 mov ecx,r12d
 call SetLastError
 xor eax,eax
 RP_RETURN
boom_reference_pending_create ENDP

; publish(pool, nonnull source batch head)->Win32 status.
boom_reference_pending_publish PROC FRAME
 RP_SAVE
 mov rbx,rcx
 mov rsi,rdx
 mov edi,87
 RP_LOCK
 test rax,rax
 jz rp_publish_done
 cmp DWORD PTR [rbx+52],0
 jne rp_publish_stopped
 cmp DWORD PTR [rbx+56],0
 jne rp_publish_busy
 test rsi,rsi
 jz rp_publish_done
 mov rcx,QWORD PTR [rbx+8]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz rp_publish_done
 cmp QWORD PTR [rbx+40],0
 jne rp_publish_busy
 mov QWORD PTR [rbx+40],rsi
 mov rcx,QWORD PTR [rbx+24]
 call SetEvent
 test eax,eax
 jnz rp_publish_ok
 call rp_error
 mov edi,eax
 mov QWORD PTR [rbx+40],0
 jmp rp_publish_done
rp_publish_ok:
 xor edi,edi
 jmp rp_publish_done
rp_publish_stopped:
 mov edi,995
 jmp rp_publish_done
rp_publish_busy:
 mov edi,170
rp_publish_done:
 RP_UNLOCK
boom_reference_pending_publish ENDP

boom_reference_pending_get PROC
 xor r8d,r8d
 jmp rp_read
boom_reference_pending_get ENDP
boom_reference_pending_has PROC
 mov r8d,1
 jmp rp_read
boom_reference_pending_has ENDP
rp_read PROC PRIVATE FRAME
 RP_SAVE
 mov rbx,rcx
 mov rsi,rdx
 mov r12d,r8d
 mov edi,87
 test rsi,rsi
 jz rp_read_return
 test r12d,r12d
 jnz rp_read_zero_bool
 mov QWORD PTR [rsi],0
 jmp rp_read_lock
rp_read_zero_bool:
 mov DWORD PTR [rsi],0
rp_read_lock:
 RP_LOCK
 test rax,rax
 jz rp_read_done
 cmp DWORD PTR [rbx+52],0
 jne rp_read_stopped
 cmp DWORD PTR [rbx+56],0
 jne rp_read_busy
 test r12d,r12d
 jnz rp_read_bool
 mov r13,QWORD PTR [rbx+40]
 test r13,r13
 jz rp_read_ok
 mov rcx,QWORD PTR [rbx+24]
 call ResetEvent
 test eax,eax
 jnz rp_read_take
 call rp_error
 mov edi,eax
 jmp rp_read_done
rp_read_take:
 mov QWORD PTR [rbx+40],0
 mov QWORD PTR [rsi],r13
 jmp rp_read_ok
rp_read_bool:
 xor eax,eax
 cmp QWORD PTR [rbx+40],0
 setne al
 mov DWORD PTR [rsi],eax
rp_read_ok:
 xor edi,edi
 jmp rp_read_done
rp_read_stopped:
 mov edi,995
 jmp rp_read_done
rp_read_busy:
 mov edi,170
rp_read_done:
 RP_UNLOCK
rp_read_return:
 mov eax,edi
 RP_RETURN
rp_read ENDP

; A real indefinite wait. Recheck the queue after every wake: another consumer
; may have taken the batch before this waiter reacquired the global lock.
boom_reference_pending_wait PROC FRAME
 RP_SAVE
 mov rbx,rcx
 mov edi,87
 RP_LOCK
 test rax,rax
 jz rp_wait_done
 cmp DWORD PTR [rbx+52],0
 jne rp_wait_stopped_no_count
 cmp DWORD PTR [rbx+56],0
 jne rp_wait_busy
 cmp QWORD PTR [rbx+40],0
 jne rp_wait_ok_no_count
 cmp DWORD PTR [rbx+48],16384
 jae rp_wait_busy
 inc DWORD PTR [rbx+48]
 mov rax,QWORD PTR [rbx+32]
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [rbx+24]
 mov QWORD PTR [rsp+40],rax
rp_wait_again:
 lea rcx,rp_lock
 call ReleaseSRWLockExclusive
 mov ecx,2
 lea rdx,[rsp+32]
 xor r8d,r8d
 mov r9d,-1
 call WaitForMultipleObjects
 mov r13d,eax
 xor r12d,r12d
 cmp eax,-1
 jne rp_wait_relock
 call rp_error
 mov r12d,eax
rp_wait_relock:
 RP_LOCK
 test rax,rax
 jz rp_wait_done
 cmp DWORD PTR [rbx+52],0
 jne rp_wait_stopped
 cmp r13d,1
 jne rp_wait_error
 cmp QWORD PTR [rbx+40],0
 je rp_wait_again
 xor edi,edi
 jmp rp_wait_decrement
rp_wait_error:
 mov edi,87
 test r12d,r12d
 jz rp_wait_decrement
 mov edi,r12d
 jmp rp_wait_decrement
rp_wait_stopped:
 mov edi,995
rp_wait_decrement:
 dec DWORD PTR [rbx+48]
 jmp rp_wait_done
rp_wait_ok_no_count:
 xor edi,edi
 jmp rp_wait_done
rp_wait_stopped_no_count:
 mov edi,995
 jmp rp_wait_done
rp_wait_busy:
 mov edi,170
rp_wait_done:
 RP_UNLOCK
boom_reference_pending_wait ENDP

boom_reference_pending_stop PROC FRAME
 RP_SAVE
 mov rbx,rcx
 mov edi,87
 RP_LOCK
 test rax,rax
 jz rp_stop_done
 cmp DWORD PTR [rbx+56],0
 jne rp_stop_busy
 cmp DWORD PTR [rbx+52],0
 jne rp_stop_ok
 mov rcx,QWORD PTR [rbx+32]
 call SetEvent
 test eax,eax
 jnz rp_stop_publish
 call rp_error
 mov edi,eax
 jmp rp_stop_done
rp_stop_publish:
 mov DWORD PTR [rbx+52],1
rp_stop_ok:
 xor edi,edi
 jmp rp_stop_done
rp_stop_busy:
 mov edi,170
rp_stop_done:
 RP_UNLOCK
boom_reference_pending_stop ENDP

boom_reference_pending_stopping PROC FRAME
 RP_SAVE
 mov rbx,rcx
 mov edi,-1
 RP_LOCK
 test rax,rax
 jz rp_stopping_done
 mov edi,DWORD PTR [rbx+52]
rp_stopping_done:
 RP_UNLOCK
boom_reference_pending_stopping ENDP

; roots_begin(pool,out Span16)->status. The current OS thread owns the lease.
boom_reference_pending_roots_begin PROC FRAME
 RP_SAVE
 mov rbx,rcx
 mov rsi,rdx
 mov edi,87
 test rsi,rsi
 jz rp_roots_return
 mov QWORD PTR [rsi],0
 mov QWORD PTR [rsi+8],0
 call GetCurrentThreadId
 mov r12d,eax
 RP_LOCK
 test rax,rax
 jz rp_roots_done
 cmp DWORD PTR [rbx+52],0
 jne rp_roots_stopped
 cmp DWORD PTR [rbx+56],0
 jne rp_roots_busy
 cmp DWORD PTR [rbx+48],0
 jne rp_roots_busy
 mov DWORD PTR [rbx+56],1
 mov DWORD PTR [rbx+60],r12d
 lea rax,[rbx+40]
 mov QWORD PTR [rsi],rax
 mov QWORD PTR [rsi+8],1
 xor edi,edi
 jmp rp_roots_done
rp_roots_stopped:
 mov edi,995
 jmp rp_roots_done
rp_roots_busy:
 mov edi,170
rp_roots_done:
 RP_UNLOCK
rp_roots_return:
 mov eax,edi
 RP_RETURN
boom_reference_pending_roots_begin ENDP

boom_reference_pending_roots_end PROC FRAME
 RP_SAVE
 mov rbx,rcx
 mov edi,87
 call GetCurrentThreadId
 mov r12d,eax
 RP_LOCK
 test rax,rax
 jz rp_roots_end_done
 cmp DWORD PTR [rbx+56],1
 jne rp_roots_end_done
 cmp DWORD PTR [rbx+60],r12d
 jne rp_roots_end_done
 mov DWORD PTR [rbx+60],0
 mov DWORD PTR [rbx+56],0
 xor edi,edi
rp_roots_end_done:
 RP_UNLOCK
boom_reference_pending_roots_end ENDP

boom_reference_pending_destroy PROC FRAME
 RP_SAVE
 mov rbx,rcx
 mov edi,87
 RP_LOCK
 test rax,rax
 jz rp_destroy_unlock
 mov edi,170
 cmp DWORD PTR [rbx+52],1
 jne rp_destroy_unlock
 cmp DWORD PTR [rbx+48],0
 jne rp_destroy_unlock
 cmp DWORD PTR [rbx+56],0
 jne rp_destroy_unlock
 mov rax,QWORD PTR [rbx+64]
 test r10,r10
 jz rp_destroy_head
 mov QWORD PTR [r10+64],rax
 jmp rp_destroy_unlinked
rp_destroy_head:
 mov QWORD PTR [rp_head],rax
rp_destroy_unlinked:
 dec DWORD PTR [rp_count]
 mov DWORD PTR [rbx],0
 lea rcx,rp_lock
 call ReleaseSRWLockExclusive
 xor edi,edi
 mov rcx,QWORD PTR [rbx+24]
 call CloseHandle
 test eax,eax
 jnz rp_destroy_stop_handle
 call rp_error
 mov edi,eax
rp_destroy_stop_handle:
 mov rcx,QWORD PTR [rbx+32]
 call CloseHandle
 test eax,eax
 jnz rp_destroy_free
 call rp_error
 test edi,edi
 jnz rp_destroy_free
 mov edi,eax
rp_destroy_free:
 mov rcx,rbx
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
 test eax,eax
 jnz rp_destroy_return
 call rp_error
 test edi,edi
 jnz rp_destroy_return
 mov edi,eax
rp_destroy_return:
 mov eax,edi
 RP_RETURN
rp_destroy_unlock:
 RP_UNLOCK
boom_reference_pending_destroy ENDP
END
