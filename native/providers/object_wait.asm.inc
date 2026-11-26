; OWAI128/1: state8,error12,heap cell16,registry cell24,source field-map32,
; wait domain40,InterruptedException class48/layout56/source ctor64,
; shared stop controller72,normal runtime type map80,BaseVirtualThread type88.
; Wait calls96, constructed interrupts104, issued VM stops112, normal wakes120.
.code
ow_valid PROC PRIVATE
 xor eax,eax
 test rcx,rcx
 jz ow_valid_done
 cmp DWORD PTR [rcx],04941574Fh
 jne ow_valid_done
 cmp DWORD PTR [rcx+4],1
 jne ow_valid_done
 cmp QWORD PTR [rcx+72],0
 je ow_valid_done
 inc eax
ow_valid_done:
 ret
ow_valid ENDP

PUBLIC boom_provider_object_wait_open
boom_provider_object_wait_open PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 call ow_valid
 test eax,eax
 jz owo_bad
 mov rsi,QWORD PTR [rbx+72]
 cmp DWORD PTR [rsi],043525052h
 jne owo_bad
 cmp DWORD PTR [rsi+4],2
 jne owo_bad
 cmp DWORD PTR [rsi+8],2
 jne owo_bad
 cmp QWORD PTR [rsi+80],0
 jne owo_busy
 mov rax,QWORD PTR [rsi+16]
 cmp rax,QWORD PTR [rbx+16]
 jne owo_bad
 xor eax,eax
 mov ecx,1
 lock cmpxchg DWORD PTR [rbx+8],ecx
 jne owo_busy
 mov rcx,QWORD PTR [rbx+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rbx+24]
 mov rdx,QWORD PTR [rdx]
 mov r8,QWORD PTR [rbx+32]
 call boom_monitor_wait_open
 test rax,rax
 jz owo_failed
 mov QWORD PTR [rbx+40],rax
 mov QWORD PTR [rsi+80],rax
 mov DWORD PTR [rbx+8],2
 xor eax,eax
 jmp owo_done
owo_failed:
 mov DWORD PTR [rbx+8],0
 mov eax,8
 jmp owo_done
owo_bad:
 mov eax,87
 jmp owo_done
owo_busy:
 mov eax,170
owo_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_provider_object_wait_open ENDP

PUBLIC boom_provider_object_wait_stop
boom_provider_object_wait_stop PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 call ow_valid
 test eax,eax
 jz ows_bad
 cmp DWORD PTR [rbx+8],3
 je ows_ok
 cmp DWORD PTR [rbx+8],2
 jne ows_bad
 mov rcx,QWORD PTR [rbx+72]
 cmp DWORD PTR [rcx+8],4
 jne ows_bad
 mov rcx,QWORD PTR [rbx+40]
 call boom_monitor_wait_stop
 test eax,eax
 jnz ows_done
 mov DWORD PTR [rbx+8],3
ows_ok:
 xor eax,eax
 jmp ows_done
ows_bad:
 mov eax,87
ows_done:
 add rsp,32
 pop rbx
 ret
boom_provider_object_wait_stop ENDP

PUBLIC boom_provider_object_wait_close
boom_provider_object_wait_close PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 call ow_valid
 test eax,eax
 jz owc_bad
 cmp DWORD PTR [rbx+8],3
 jne owc_bad
 mov rax,QWORD PTR [rbx+72]
 mov rcx,QWORD PTR [rbx+40]
 cmp QWORD PTR [rax+80],rcx
 jne owc_bad
 call boom_monitor_wait_close
 test eax,eax
 jnz owc_done
 mov rax,QWORD PTR [rbx+72]
 mov QWORD PTR [rax+80],0
 mov QWORD PTR [rbx+40],0
 mov DWORD PTR [rbx+8],4
 xor eax,eax
 jmp owc_done
owc_bad:
 mov eax,87
owc_done:
 add rsp,32
 pop rbx
 ret
boom_provider_object_wait_close ENDP

; (Context32, argv, OWAI128, operation) -> Java void. The provider keeps the
; framed native caller active through actual exception creation and the ctor.
PUBLIC boom_provider_object_wait_service
boom_provider_object_wait_service PROC FRAME
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
 mov rdi,rdx
 mov rsi,r8
 mov r12d,r9d
 test rbx,rbx
 jz ow_zero
 cmp DWORD PTR [rbx],0
 jne ow_zero
 mov rcx,rsi
 call ow_valid
 test eax,eax
 jz ow_bad
 mov eax,DWORD PTR [rsi+8]
 sub eax,2
 cmp eax,1
 ja ow_unbound
 cmp r12d,2
 ja ow_bad
 mov rcx,QWORD PTR [rsi+24]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_current
 test rax,rax
 jz ow_unbound
 mov r13,rax
 cmp r12d,1
 jne ow_validate_platform
 test rdi,rdi
 jz ow_bad
 mov rax,QWORD PTR [rdi]
 test rax,rax
 jz ow_null
ow_validate_platform:
 mov QWORD PTR [rsp+40],rax
 mov rcx,QWORD PTR [rsi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rax
 call boom_heap_contains
 test eax,eax
 jz ow_bad
 mov rcx,QWORD PTR [rsp+40]
 mov rdx,rbx
 call QWORD PTR [rsi+32]
 test rax,rax
 jz ow_checked_error
 mov rcx,QWORD PTR [rsp+40]
 mov rdx,QWORD PTR [rsi+80]
 mov r8,rbx
 call boom_runtime_type
 test rax,rax
 jz ow_checked_error
 mov rcx,rax
 mov rdx,QWORD PTR [rsi+88]
 call boom_type_assignable
 test eax,eax
 jnz ow_unbound
 cmp r12d,2
 je ow_zero
 test r12d,r12d
 jnz ow_interrupt
 test rdi,rdi
 jz ow_bad
 mov rcx,QWORD PTR [rsi+40]
 mov rdx,QWORD PTR [rdi]
 mov r8,rbx
 mov r9,QWORD PTR [rdi+8]
 lock inc QWORD PTR [rsi+96]
 call boom_monitor_wait
 test eax,eax
 jnz ow_reason
 lock inc QWORD PTR [rsi+120]
 jmp ow_zero
ow_reason:
 cmp eax,010001h
 je ow_throw
 cmp eax,995
 jne ow_zero
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+72]
 mov r8,QWORD PTR [rsi+40]
 call boom_provider_reference_issue_stop
 cmp DWORD PTR [rbx],0B002h
 jne ow_zero
 lock inc QWORD PTR [rsi+112]
 jmp ow_zero
ow_throw:
 mov rcx,QWORD PTR [rsi+48]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne ow_zero
 mov rcx,QWORD PTR [rsi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rsi+56]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz ow_checked_error
 ; GC is quiescent-only. No collection is admitted while the monitor is held.
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+64]
 cmp DWORD PTR [rbx],0
 jne ow_zero
 mov rax,QWORD PTR [rsp+32]
 mov QWORD PTR [rbx+16],rax
 mov DWORD PTR [rbx],16
 lock inc QWORD PTR [rsi+104]
 jmp ow_zero
ow_interrupt:
 mov rcx,QWORD PTR [rsi+40]
 mov rdx,QWORD PTR [rdi]
 call boom_monitor_wait_interrupt
 test eax,eax
 jz ow_zero
 cmp eax,1168
 jne ow_bad
 ; A current thread executing interrupt0 is runnable. A foreign thread that
 ; is outside the monitor domain may be sleeping, parked or blocked in I/O.
 cmp QWORD PTR [rdi],r13
 je ow_zero
 jmp ow_unbound
ow_checked_error:
 cmp DWORD PTR [rbx],0
 jne ow_zero
ow_bad:
 mov DWORD PTR [rbx],7
 jmp ow_zero
ow_null:
 mov DWORD PTR [rbx],4
 jmp ow_zero
ow_unbound:
 mov DWORD PTR [rbx],20
ow_zero:
 xor eax,eax
 add rsp,48
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_object_wait_service ENDP
