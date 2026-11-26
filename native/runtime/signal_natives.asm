; Original Signal.handle0/raise0 ABI over the live Windows assembly transport.
; The VM must create the transport with real dispatch/break callbacks, bind it
; before Java entry, then quiesce Java, close/join transport and unbind at exit.
; This module does not invent a Java dispatcher or install empty callbacks.
option casemap:none
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockShared:PROC
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN boom_signal_control_snapshot:PROC
EXTERN boom_signal_control_register:PROC
EXTERN boom_signal_control_raise:PROC
PUBLIC boom_signal_native_query
PUBLIC boom_signal_native_bind
.code
; SGNP64/1: control8, native leases16, binding lock24, trace pool32, reserved40..63.
; TracePool48 ABI2 and normal-source ABI3 share the lease/lifecycle fields.
signal_native_pool_valid PROC
    test rcx,rcx
    jz signal_native_pool_bad
    cmp DWORD PTR [rcx],0504E4753h
    jne signal_native_pool_bad
    cmp DWORD PTR [rcx+4],1
    jne signal_native_pool_bad
    cmp QWORD PTR [rcx+40],0
    jne signal_native_pool_bad
    cmp QWORD PTR [rcx+48],0
    jne signal_native_pool_bad
    cmp QWORD PTR [rcx+56],0
    jne signal_native_pool_bad
    mov rax,QWORD PTR [rcx+32]
    test rax,rax
    jz signal_native_pool_bad
    cmp DWORD PTR [rax],05452504Ch
    jne signal_native_pool_bad
    cmp DWORD PTR [rax+4],2
    je signal_native_trace_legacy
    cmp DWORD PTR [rax+4],3
    jne signal_native_pool_bad
    cmp DWORD PTR [rax+16],1048576
    ja signal_native_pool_bad
    jmp signal_native_trace_count
signal_native_trace_legacy:
    cmp DWORD PTR [rax+16],262144
    ja signal_native_pool_bad
signal_native_trace_count:
    cmp DWORD PTR [rax+16],0
    je signal_native_pool_bad
    cmp DWORD PTR [rax+20],0
    jne signal_native_pool_bad
    cmp QWORD PTR [rax+24],0
    je signal_native_pool_bad
    cmp DWORD PTR [rax+44],0
    jne signal_native_pool_bad
    cmp DWORD PTR [rax+8],4
    ja signal_native_pool_bad
    mov eax,1
    ret
signal_native_pool_bad:
    xor eax,eax
    ret
signal_native_pool_valid ENDP

; bind(control or null,pool)->Win32 status. Replacement requires close/unbind.
; Caller serializes VM lifecycle and entry. Native calls additionally hold leases.
boom_signal_native_bind PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,96
    .allocstack 96
    .endprolog
    mov rsi,rcx
    mov rbx,rdx
    mov edi,87
    mov rcx,rdx
    call signal_native_pool_valid
    test eax,eax
    jz signal_bind_done
    lea rcx,[rbx+24]
    call AcquireSRWLockExclusive
    mov edi,170
    cmp QWORD PTR [rbx+16],0
    jne signal_bind_unlock
    mov rax,QWORD PTR [rbx+32]
    cmp QWORD PTR [rax+32],0
    jne signal_bind_unlock
    cmp DWORD PTR [rax+40],0
    jne signal_bind_unlock
    mov edi,87
    cmp DWORD PTR [rax+8],4
    je signal_bind_unlock
    mov rcx,QWORD PTR [rbx+8]
    test rsi,rsi
    jnz signal_bind_live
    test rcx,rcx
    jz signal_bind_publish
    lea rdx,[rsp+32]
    call boom_signal_control_snapshot
    test eax,eax
    jnz signal_bind_publish
    mov edi,170 ; close/join the old transport before removing its binding.
    jmp signal_bind_unlock
signal_bind_live:
    test rcx,rcx
    jz signal_bind_validate
    cmp rcx,rsi
    jne signal_bind_unlock
signal_bind_validate:
    mov rcx,rsi
    lea rdx,[rsp+32]
    call boom_signal_control_snapshot
    test eax,eax
    jnz signal_bind_unlock
    cmp QWORD PTR [rsp+88],1
    jne signal_bind_unlock
signal_bind_publish:
    mov QWORD PTR [rbx+8],rsi
    xor edi,edi
signal_bind_unlock:
    lea rcx,[rbx+24]
    call ReleaseSRWLockExclusive
signal_bind_done:
    mov eax,edi
    add rsp,96
    pop rdi
    pop rsi
    pop rbx
    ret
boom_signal_native_bind ENDP

; (Context32,argv,pool,operation)->previous handler/void. 0 handle0,1 raise0.
boom_signal_native_query PROC FRAME
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
    sub rsp,112
    .allocstack 112
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    mov r12d,r9d
    mov QWORD PTR [rsp+32],0
    mov DWORD PTR [rsp+40],0
    test rbx,rbx
    jz signal_query_done
    cmp DWORD PTR [rbx],0
    jne signal_query_done
    test rsi,rsi
    jz signal_query_bad
    cmp r12d,1
    ja signal_query_bad
    mov rcx,rdi
    call signal_native_pool_valid
    test eax,eax
    jz signal_query_bad
    lea rcx,[rdi+24]
    call AcquireSRWLockShared
    mov r13,QWORD PTR [rdi+8]
    test r13,r13
    jz signal_query_unbound
    lock inc QWORD PTR [rdi+16]
    mov DWORD PTR [rsp+40],1
    lea rcx,[rdi+24]
    call ReleaseSRWLockShared
    mov rcx,r13
    lea rdx,[rsp+48]
    call boom_signal_control_snapshot
    test eax,eax
    jnz signal_query_bad
    cmp QWORD PTR [rsp+104],1
    jne signal_query_bad
    mov rcx,r13
    mov edx,DWORD PTR [rsi]
    test r12d,r12d
    jnz signal_query_raise
    mov r8,QWORD PTR [rsi+8]
    call boom_signal_control_register
    mov QWORD PTR [rsp+32],rax ; -1 is the real native rejection result.
    jmp signal_query_done
signal_query_raise:
    call boom_signal_control_raise
    test eax,eax
    jz signal_query_done
    cmp eax,87 ; Signal.c ignores the CRT/JVM invalid-number result.
    je signal_query_done
    mov DWORD PTR [rbx],23
    jmp signal_query_done
signal_query_unbound:
    lea rcx,[rdi+24]
    call ReleaseSRWLockShared
signal_query_bad:
    mov DWORD PTR [rbx],7
signal_query_done:
    cmp DWORD PTR [rsp+40],0
    je signal_query_return
    lock dec QWORD PTR [rdi+16]
signal_query_return:
    mov rax,QWORD PTR [rsp+32]
    add rsp,112
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_signal_native_query ENDP
END
