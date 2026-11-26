; Controlled VM abort only, not a Java monitorexit or exception replacement.
; (heap, Context32, outReleasedAcquisitionsQWORD, authorizedStopBOOL)->Win32 status.
; Requires a fully unwound B001 diagnostic, or explicitly authorized B002 stop,
; depth0 and no pending Throwable. Context32 including VMplan24 is read-only.
; Monitor ABI1 only. Two passes validate the whole active list before mutation.
option casemap:none
EXTERN GetCurrentThreadId:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
EXTERN boom_heap_contains:PROC
PUBLIC boom_monitor_abort_owned
.code
boom_monitor_abort_owned PROC FRAME
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
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 test rdi,rdi
 jz ma_invalid
 mov QWORD PTR [rdi],0
 cmp r9d,1
 ja ma_invalid
 test rbx,rbx
 jz ma_invalid
 test rsi,rsi
 jz ma_invalid
 cmp DWORD PTR [rsi+12],0
 jne ma_invalid
 cmp QWORD PTR [rsi+16],0
 jne ma_invalid
 mov eax,DWORD PTR [rsi]
 cmp eax,0B001h
 je ma_context_valid
 cmp eax,0B002h
 jne ma_invalid
 cmp r9d,1
 jne ma_invalid
ma_context_valid:
 cmp DWORD PTR [rbx],048454150h
 jne ma_invalid
 cmp DWORD PTR [rbx+4],1
 jne ma_invalid
 cmp DWORD PTR [rbx+108],1
 jne ma_unsupported
 call GetCurrentThreadId
 mov DWORD PTR [rsp+44],eax
 mov DWORD PTR [rsp+32],1
 mov DWORD PTR [rsp+36],64
ma_lock:
 xor eax,eax
 mov r10d,1
 lock cmpxchg DWORD PTR [rbx+104],r10d
 je ma_locked
 cmp eax,1
 jne ma_invalid
 lea rcx,[rbx+104]
 lea rdx,[rsp+32]
 mov r8d,4
 mov r9d,1
 call WaitOnAddress
 dec DWORD PTR [rsp+36]
 jnz ma_lock
 mov eax,170
 jmp ma_return
ma_locked:
 xor r13d,r13d
 mov rsi,QWORD PTR [rbx+96]
 mov DWORD PTR [rsp+40],1048576
ma_validate:
 test rsi,rsi
 jz ma_validate_total
 dec DWORD PTR [rsp+40]
 jz ma_invalid_locked
 mov rcx,rbx
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz ma_invalid_locked
 cmp QWORD PTR [rsi-16],32
 jb ma_invalid_locked
 cmp DWORD PTR [rsi-20],2
 jne ma_invalid_locked
 cmp DWORD PTR [rsi-8],04D4F4E52h
 jne ma_invalid_locked
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi]
 test rdx,rdx
 jz ma_invalid_locked
 call boom_heap_contains
 test eax,eax
 jz ma_invalid_locked
 cmp DWORD PTR [rsi+28],0
 jne ma_unsupported_locked
 mov eax,DWORD PTR [rsi+16]
 test eax,eax
 jz ma_unowned_node
 cmp DWORD PTR [rsi+20],0
 je ma_invalid_locked
 cmp eax,DWORD PTR [rsp+44]
 jne ma_validate_next
 mov eax,DWORD PTR [rsi+20]
 add r13,rax
 jc ma_invalid_locked
 jmp ma_validate_next
ma_unowned_node:
 cmp DWORD PTR [rsi+20],0
 jne ma_invalid_locked
 cmp DWORD PTR [rsi+24],0
 je ma_invalid_locked
ma_validate_next:
 mov rsi,QWORD PTR [rsi+8]
 jmp ma_validate
ma_validate_total:
 cmp QWORD PTR [rbx+112],r13
 jb ma_invalid_locked
 lea r12,[rbx+96]
ma_release_next:
 mov rsi,QWORD PTR [r12]
 test rsi,rsi
 jz ma_released
 mov eax,DWORD PTR [rsp+44]
 cmp DWORD PTR [rsi+16],eax
 jne ma_keep_node
 mov DWORD PTR [rsi+16],0
 mov DWORD PTR [rsi+20],0
 cmp DWORD PTR [rsi+24],0
 jne ma_wake_contenders
 mov rax,QWORD PTR [rsi+8]
 mov QWORD PTR [r12],rax
 mov QWORD PTR [rsi],0
 mov rax,QWORD PTR [rbx+120]
 mov QWORD PTR [rsi+8],rax
 mov QWORD PTR [rbx+120],rsi
 jmp ma_release_next
ma_wake_contenders:
 lea rcx,[rsi+16]
 call WakeByAddressAll
ma_keep_node:
 lea r12,[rsi+8]
 jmp ma_release_next
ma_released:
 sub QWORD PTR [rbx+112],r13
 mov QWORD PTR [rdi],r13
 mov DWORD PTR [rsp+48],0
 jmp ma_unlock
ma_invalid_locked:
 mov DWORD PTR [rsp+48],87
 jmp ma_unlock
ma_unsupported_locked:
 mov DWORD PTR [rsp+48],50
ma_unlock:
 mov DWORD PTR [rbx+104],0
 lea rcx,[rbx+104]
 call WakeByAddressAll
 mov eax,DWORD PTR [rsp+48]
 jmp ma_return
ma_unsupported:
 mov eax,50
 jmp ma_return
ma_invalid:
 mov eax,87
ma_return:
 add rsp,64
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_monitor_abort_owned ENDP
END
