; NSIG256/1: state8; heapCell16,registryCell24,trace32,nativePool40,type48,
; layout56,ctor64,exit72,dispatch80,fieldFns88..112,roots120,record128,
; peerAddress136,statusAddress144,JavaId152,control160,failureState168,
; failureContext176,counters dispatch184/exit192/exitOK200/attach208/detach216,
; source normal String copy pool224,reserved232..255. Borrow a nonmoving heap.
EXTERN GetLastError:PROC
EXTERN boom_object_new:PROC
EXTERN boom_java_property_copy:PROC
EXTERN boom_threads_current:PROC
EXTERN boom_threads_attach:PROC
EXTERN boom_threads_detach:PROC
EXTERN boom_signal_control_create:PROC
EXTERN boom_signal_control_close:PROC
EXTERN boom_signal_native_bind:PROC
EXTERN boom_signal_native_query:PROC
EXTERN boom_monitor_enter:PROC
EXTERN boom_monitor_notify_all:PROC
EXTERN boom_monitor_exit:PROC
PUBLIC boom_provider_signal_open
PUBLIC boom_provider_signal_close
PUBLIC boom_provider_signal_service
.code
sig_remember PROC PRIVATE
 cmp DWORD PTR [rcx],0
 je sig_remember_done
 xor eax,eax
 mov r8d,1
 lock cmpxchg DWORD PTR [rdx+168],r8d
 test eax,eax
 jnz sig_remember_done
 mov r8,QWORD PTR [rdx+176]
 mov rax,QWORD PTR [rcx]
 mov QWORD PTR [r8],rax
 mov rax,QWORD PTR [rcx+8]
 mov QWORD PTR [r8+8],rax
 mov rax,QWORD PTR [rcx+16]
 mov QWORD PTR [r8+16],rax
 mov rax,QWORD PTR [rcx+24]
 mov QWORD PTR [r8+24],rax
 mov DWORD PTR [rdx+168],2
sig_remember_done:
 ret
sig_remember ENDP

; Copy the first worker failure only into a clean caller; retain caller depth.
sig_observe PROC PRIVATE
 cmp DWORD PTR [rcx],0
 jne sig_observe_done
 cmp DWORD PTR [rdx+168],2
 jne sig_observe_done
 mov r8,QWORD PTR [rdx+176]
 mov r9d,DWORD PTR [rcx+12]
 mov rax,QWORD PTR [r8]
 mov QWORD PTR [rcx],rax
 mov rax,QWORD PTR [r8+8]
 mov QWORD PTR [rcx+8],rax
 mov DWORD PTR [rcx+12],r9d
 mov rax,QWORD PTR [r8+16]
 mov QWORD PTR [rcx+16],rax
 mov rax,QWORD PTR [r8+24]
 mov QWORD PTR [rcx+24],rax
sig_observe_done:
 ret
sig_observe ENDP

; Transport ABI2 enter runs once on its actual worker before publication.
sig_enter PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rcx,QWORD PTR [rbx+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rbx+120]
 mov rdx,QWORD PTR [rdx]
 mov r8,QWORD PTR [rbx+152]
 call boom_threads_attach
 test rax,rax
 jz sig_enter_bad
 mov QWORD PTR [rbx+128],rax
 mov rdx,QWORD PTR [rbx+136]
 mov QWORD PTR [rdx],rax
 mov rdx,QWORD PTR [rbx+144]
 mov DWORD PTR [rdx],4
 lock inc QWORD PTR [rbx+208]
 xor eax,eax
 jmp sig_enter_done
sig_enter_bad:
 mov eax,87
sig_enter_done:
 add rsp,32
 pop rbx
 ret
sig_enter ENDP

; Java callback uses the original static dispatch body and the attached identity.
sig_dispatch PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,80
 .allocstack 80
 .endprolog
 mov rbx,rcx
 movsxd rax,edx
 mov QWORD PTR [rsp+64],rax
 xor eax,eax
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],rax
 mov QWORD PTR [rsp+48],rax
 mov QWORD PTR [rsp+56],rax
 mov rcx,QWORD PTR [rbx+24]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_current
 mov rdx,QWORD PTR [rbx+120]
 cmp rax,QWORD PTR [rdx]
 jne sig_dispatch_bad
 lea rcx,[rsp+32]
 mov rdx,rbx
 call sig_observe
 cmp DWORD PTR [rsp+32],0
 jne sig_dispatch_record
 lock inc QWORD PTR [rbx+184]
 lea rcx,[rsp+32]
 lea rdx,[rsp+64]
 call QWORD PTR [rbx+80]
 jmp sig_dispatch_record
sig_dispatch_bad:
 mov DWORD PTR [rsp+32],7
sig_dispatch_record:
 lea rcx,[rsp+32]
 mov rdx,rbx
 call sig_remember
 mov eax,DWORD PTR [rsp+32]
 add rsp,80
 pop rbx
 ret
sig_dispatch ENDP

; A real VM BREAK thread dump is still unavailable. Never report a no-op success.
sig_break PROC PRIVATE FRAME
 sub rsp,72
 .allocstack 72
 .endprolog
 mov rdx,rcx
 xor eax,eax
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],rax
 mov QWORD PTR [rsp+48],rax
 mov QWORD PTR [rsp+56],rax
 mov DWORD PTR [rsp+32],20
 lea rcx,[rsp+32]
 call sig_remember
 mov eax,50
 add rsp,72
 ret
sig_break ENDP

; Exit original Java code on the dispatcher, publish terminal fields under its
; object monitor, and detach before the OS worker can return. No transport calls.
sig_exit PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,120
 .allocstack 120
 .endprolog
 mov rbx,rcx
 mov rsi,QWORD PTR [rbx+120]
 mov rsi,QWORD PTR [rsi]
 xor eax,eax
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],rax
 mov QWORD PTR [rsp+48],rax
 mov QWORD PTR [rsp+56],rax
 mov QWORD PTR [rsp+64],rax
 mov QWORD PTR [rsp+72],rax
 mov QWORD PTR [rsp+80],rax
 mov QWORD PTR [rsp+88],rax
 mov QWORD PTR [rsp+96],rsi
 lock inc QWORD PTR [rbx+192]
 lea rcx,[rsp+32]
 lea rdx,[rsp+96]
 call QWORD PTR [rbx+72]
 cmp DWORD PTR [rsp+32],0
 jne sig_exit_remember
 lock inc QWORD PTR [rbx+200]
sig_exit_remember:
 lea rcx,[rsp+32]
 mov rdx,rbx
 call sig_remember
 mov rcx,QWORD PTR [rbx+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 lea r8,[rsp+64]
 call boom_monitor_enter
 test eax,eax
 jnz sig_exit_monitor_error
 mov rax,QWORD PTR [rbx+136]
 mov QWORD PTR [rax],0
 mov rax,QWORD PTR [rbx+144]
 mov DWORD PTR [rax],2
 mov rcx,QWORD PTR [rbx+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 lea r8,[rsp+64]
 call boom_monitor_notify_all
 lea rcx,[rsp+64]
 mov rdx,rbx
 call sig_remember
 xor eax,eax
 mov QWORD PTR [rsp+64],rax
 mov QWORD PTR [rsp+72],rax
 mov QWORD PTR [rsp+80],rax
 mov QWORD PTR [rsp+88],rax
 mov rcx,QWORD PTR [rbx+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 lea r8,[rsp+64]
 call boom_monitor_exit
sig_exit_monitor_error:
 lea rcx,[rsp+64]
 mov rdx,rbx
 call sig_remember
 mov rcx,QWORD PTR [rbx+24]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_detach
 test eax,eax
 jnz sig_exit_detach_error
 mov QWORD PTR [rbx+128],0
 lock inc QWORD PTR [rbx+216]
 jmp sig_exit_result
sig_exit_detach_error:
 mov DWORD PTR [rsp+32],7
 lea rcx,[rsp+32]
 mov rdx,rbx
 call sig_remember
sig_exit_result:
 xor eax,eax
 cmp DWORD PTR [rbx+168],0
 je sig_exit_done
 mov eax,87
sig_exit_done:
 add rsp,120
 pop rsi
 pop rbx
 ret
sig_exit ENDP

; open(Context32, parent ThreadGroup, pool) -> control/null. VM owner only,
; after primordial construction and before entering System.initPhase1.
boom_provider_signal_open PROC FRAME
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
 mov rsi,r8
 mov QWORD PTR [rsp+40],rdx
 test rbx,rbx
 jz sig_open_zero
 cmp DWORD PTR [rbx],0
 jne sig_open_zero
 test rdx,rdx
 jz sig_open_invalid
 test rsi,rsi
 jz sig_open_invalid
 cmp DWORD PTR [rsi],05349474Eh
 jne sig_open_invalid
 cmp DWORD PTR [rsi+4],1
 jne sig_open_invalid
 xor eax,eax
 mov ecx,1
 lock cmpxchg DWORD PTR [rsi+8],ecx
 jne sig_open_invalid
 mov rcx,QWORD PTR [rsi+24]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_current
 test rax,rax
 jz sig_open_bad
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+224]
 lea r8,signal_dispatcher_name
 mov r9d,17
 call boom_java_property_copy
 cmp DWORD PTR [rbx],0
 jne sig_open_failed
 test rax,rax
 jz sig_open_bad
 mov rdi,QWORD PTR [rsi+120]
 mov QWORD PTR [rdi+8],rax
 mov QWORD PTR [rsp+48],rax
 mov rcx,QWORD PTR [rsi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rsi+56]
 mov r8,rbx
 call boom_object_new
 cmp DWORD PTR [rbx],0
 jne sig_open_failed
 test rax,rax
 jz sig_open_bad
 mov QWORD PTR [rdi],rax
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+64]
 cmp DWORD PTR [rbx],0
 jne sig_open_failed
 mov rcx,QWORD PTR [rdi]
 mov rdx,rbx
 call QWORD PTR [rsi+88]
 test rax,rax
 jz sig_open_failed
 mov rax,QWORD PTR [rax]
 cmp rax,2
 jl sig_open_bad
 mov QWORD PTR [rsi+152],rax
 mov rcx,QWORD PTR [rdi]
 mov rdx,rbx
 call QWORD PTR [rsi+96]
 test rax,rax
 jz sig_open_failed
 cmp QWORD PTR [rax],0
 jne sig_open_bad
 mov QWORD PTR [rsi+136],rax
 mov rcx,QWORD PTR [rdi]
 mov rdx,rbx
 call QWORD PTR [rsi+104]
 test rax,rax
 jz sig_open_failed
 mov rcx,QWORD PTR [rax]
 mov rdx,rbx
 call QWORD PTR [rsi+112]
 test rax,rax
 jz sig_open_failed
 cmp DWORD PTR [rax],0
 jne sig_open_bad
 mov QWORD PTR [rsi+144],rax
 lea rcx,signal_dispatcher_config
 call boom_signal_control_create
 test rax,rax
 jz sig_open_create_failed
 mov QWORD PTR [rsi+160],rax
 mov rcx,rax
 mov rdx,QWORD PTR [rsi+40]
 call boom_signal_native_bind
 test eax,eax
 jnz sig_open_bind_failed
 mov DWORD PTR [rsi+8],2
 mov rax,QWORD PTR [rsi+160]
 jmp sig_open_done
sig_open_bind_failed:
 mov DWORD PTR [rsi+12],eax
 mov rcx,QWORD PTR [rsi+160]
 call boom_signal_control_close
 mov QWORD PTR [rsi+160],0
 jmp sig_open_native_failed
sig_open_create_failed:
 call GetLastError
 mov DWORD PTR [rsi+12],eax
sig_open_native_failed:
 mov rcx,rbx
 mov rdx,rsi
 call sig_observe
 cmp DWORD PTR [rbx],0
 jne sig_open_failed
 mov DWORD PTR [rbx],20
 jmp sig_open_failed
sig_open_bad:
 mov DWORD PTR [rbx],7
sig_open_failed:
 mov DWORD PTR [rsi+8],5
 jmp sig_open_zero
sig_open_invalid:
 mov DWORD PTR [rbx],7
sig_open_zero:
 xor eax,eax
sig_open_done:
 add rsp,80
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_signal_open ENDP

; close(Context32,pool) -> status. Join original Java exit before unbinding.
boom_provider_signal_close PROC FRAME
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
 xor edi,edi
 cmp DWORD PTR [rsi+8],2
 jne sig_close_observe
 mov DWORD PTR [rsi+8],3
 mov rcx,QWORD PTR [rsi+160]
 call boom_signal_control_close
 mov edi,eax
 mov QWORD PTR [rsi+160],0
 xor ecx,ecx
 mov rdx,QWORD PTR [rsi+40]
 call boom_signal_native_bind
 test edi,edi
 jnz sig_close_state
 mov edi,eax
sig_close_state:
 mov DWORD PTR [rsi+8],4
sig_close_observe:
 mov rcx,rbx
 mov rdx,rsi
 call sig_observe
 test edi,edi
 jz sig_close_done
 cmp DWORD PTR [rbx],0
 jne sig_close_done
 mov DWORD PTR [rbx],7
sig_close_done:
 mov eax,edi
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_signal_close ENDP

; Original static natives receive the real bound transport, never a stub.
boom_provider_signal_service PROC
 test rcx,rcx
 jz sig_service_zero
 cmp DWORD PTR [rcx],0
 jne sig_service_zero
 cmp DWORD PTR [r8+8],2
 jne sig_service_bad
 mov r8,QWORD PTR [r8+40]
 jmp boom_signal_native_query
sig_service_bad:
 mov DWORD PTR [rcx],20
sig_service_zero:
 xor eax,eax
 ret
boom_provider_signal_service ENDP
