; Java shadow frames on the actual generated method stack. MASM only.
; Pool48 magic0 ABI4 state8 TLSslot12 count16 reserved20 rows24 leases32 closing40.
; Node48 magic0 ABI4 prev8 methodRow16 PC24 flags28 context32 pool40.
; ABI2 flag1 owns a Context entry lease. Nested methods do not contend on leases.
; PoolABI2 MethodRow32 id0 flags4 declaringType8 codeBytes16 lineCount20 lines24.
; PoolABI3 MethodRow32 id0 flags4 declaringType8 codeBytes16 classId20 reserved24.
; enter(pool,node,row,Context16/32)->0/1; leave(pool,node,Context16/32)->0/1.
; release(pool)->0/ERROR_BUSY170/ERROR_INVALID_PARAMETER87; final and quiescent.
option casemap:none
EXTERN TlsAlloc:PROC
EXTERN TlsGetValue:PROC
EXTERN TlsSetValue:PROC
EXTERN TlsFree:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
PUBLIC boom_trace_enter
PUBLIC boom_trace_leave
PUBLIC boom_trace_release
PUBLIC boom_trace_head
.code
trace_pool_valid PROC
    test rcx,rcx
    jz trace_pool_bad
    cmp DWORD PTR [rcx],05452504Ch
    jne trace_pool_bad
    cmp DWORD PTR [rcx+4],2
    je trace_pool_version_valid
    cmp DWORD PTR [rcx+4],3
    jne trace_pool_bad
trace_pool_version_valid:
    cmp DWORD PTR [rcx+20],0
    jne trace_pool_bad
    cmp DWORD PTR [rcx+44],0
    jne trace_pool_bad
    mov eax,DWORD PTR [rcx+16]
    test eax,eax
    jz trace_pool_bad
    cmp DWORD PTR [rcx+4],3
    je trace_pool_large
    cmp eax,262144
    ja trace_pool_bad
    jmp trace_pool_count_valid
trace_pool_large:
    cmp eax,1048576
    ja trace_pool_bad
trace_pool_count_valid:
    cmp QWORD PTR [rcx+24],0
    je trace_pool_bad
    cmp DWORD PTR [rcx+8],4
    ja trace_pool_bad
    mov eax,1
    ret
trace_pool_bad:
    xor eax,eax
    ret
trace_pool_valid ENDP

boom_trace_enter PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    sub rsp,56
    .allocstack 56
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    mov r12,r9
    mov DWORD PTR [rsp+48],0
    cmp DWORD PTR [r12],0
    jne trace_enter_error
    call trace_pool_valid
    test eax,eax
    jz trace_enter_invalid
    test rsi,rsi
    jz trace_enter_invalid
    test rdi,rdi
    jz trace_enter_invalid
    mov rax,rdi
    sub rax,QWORD PTR [rbx+24]
    jc trace_enter_invalid
    test eax,31
    jnz trace_enter_invalid
    shr rax,5
    mov edx,DWORD PTR [rbx+16]
    cmp rax,rdx
    jae trace_enter_invalid
    cmp DWORD PTR [rbx+4],3
    jne trace_enter_legacy_row
    test DWORD PTR [rdi+4],0FFFFFF00h
    jnz trace_enter_invalid
    cmp QWORD PTR [rdi+24],0
    jne trace_enter_invalid
    test DWORD PTR [rdi+4],128
    jnz trace_enter_unbound
    cmp QWORD PTR [rdi+8],0
    je trace_enter_invalid
    test DWORD PTR [rdi+4],32
    jz trace_enter_java_row
    cmp DWORD PTR [rdi+16],0
    jne trace_enter_invalid
    jmp trace_enter_row_valid
trace_enter_legacy_row:
    cmp QWORD PTR [rdi+8],0
    je trace_enter_invalid
    test DWORD PTR [rdi+4],0FFFFFFF8h
    jnz trace_enter_invalid
trace_enter_java_row:
    mov eax,DWORD PTR [rdi+16]
    test eax,eax
    jz trace_enter_invalid
    cmp eax,65535
    ja trace_enter_invalid
trace_enter_row_valid:
    cmp DWORD PTR [r12+12],1
    ja trace_enter_nested
    lock inc QWORD PTR [rbx+32]
    mov DWORD PTR [rsp+48],1
    cmp DWORD PTR [rbx+40],0
    jne trace_enter_drop_invalid
trace_enter_state:
    mov eax,DWORD PTR [rbx+8]
    cmp eax,2
    je trace_enter_ready
    cmp eax,3
    jae trace_enter_drop_invalid
    cmp eax,1
    je trace_enter_wait
    xor eax,eax
    mov edx,1
    lock cmpxchg DWORD PTR [rbx+8],edx
    jne trace_enter_state
    call TlsAlloc
    cmp eax,-1
    je trace_enter_alloc_failed
    mov DWORD PTR [rbx+12],eax
    mov DWORD PTR [rbx+8],2
    lea rcx,[rbx+8]
    call WakeByAddressAll
    jmp trace_enter_ready
trace_enter_alloc_failed:
    mov DWORD PTR [rbx+8],3
    lea rcx,[rbx+8]
    call WakeByAddressAll
    mov DWORD PTR [r12],3
    jmp trace_enter_drop
trace_enter_wait:
    mov DWORD PTR [rsp+32],1
    lea rcx,[rbx+8]
    lea rdx,[rsp+32]
    mov r8d,4
    mov r9d,-1
    call WaitOnAddress
    jmp trace_enter_state
trace_enter_nested:
    ; A generated nested call retains the lease of its same-Context parent.
    cmp DWORD PTR [rbx+8],2
    jne trace_enter_drop_invalid
    cmp QWORD PTR [rbx+32],0
    je trace_enter_drop_invalid
trace_enter_ready:
    cmp DWORD PTR [rbx+12],-1
    je trace_enter_drop_invalid
    mov ecx,DWORD PTR [rbx+12]
    call TlsGetValue
    test rax,rax
    jnz trace_enter_check_parent
    cmp DWORD PTR [rsp+48],0
    je trace_enter_drop_invalid
    jmp trace_enter_link
trace_enter_check_parent:
    cmp DWORD PTR [rax],04652414Dh
    jne trace_enter_drop_invalid
    cmp DWORD PTR [rax+4],2
    jne trace_enter_drop_invalid
    cmp QWORD PTR [rax+40],rbx
    jne trace_enter_drop_invalid
    cmp DWORD PTR [rsp+48],0
    jne trace_enter_link
    cmp QWORD PTR [rax+32],r12
    jne trace_enter_drop_invalid
trace_enter_link:
    mov DWORD PTR [rsi],04652414Dh
    mov DWORD PTR [rsi+4],2
    mov QWORD PTR [rsi+8],rax
    mov QWORD PTR [rsi+16],rdi
    mov QWORD PTR [rsi+24],0
    mov edx,DWORD PTR [rsp+48]
    mov DWORD PTR [rsi+28],edx
    mov QWORD PTR [rsi+32],r12
    mov QWORD PTR [rsi+40],rbx
    mov ecx,DWORD PTR [rbx+12]
    mov rdx,rsi
    call TlsSetValue
    test eax,eax
    jz trace_enter_set_failed
    xor eax,eax
    jmp trace_enter_done
trace_enter_set_failed:
    mov QWORD PTR [rsi],0
    mov DWORD PTR [r12],3
    jmp trace_enter_drop
trace_enter_drop_invalid:
    mov DWORD PTR [r12],7
trace_enter_drop:
    cmp DWORD PTR [rsp+48],0
    je trace_enter_error
    lock dec QWORD PTR [rbx+32]
    jmp trace_enter_error
trace_enter_invalid:
    mov DWORD PTR [r12],7
    jmp trace_enter_error
trace_enter_unbound:
    mov DWORD PTR [r12],20
trace_enter_error:
    mov eax,1
trace_enter_done:
    add rsp,56
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_trace_enter ENDP

boom_trace_leave PROC FRAME
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
    cmp DWORD PTR [rsi],0
    je trace_leave_ok
    call trace_pool_valid
    test eax,eax
    jz trace_leave_invalid
    cmp DWORD PTR [rbx+8],2
    jne trace_leave_invalid
    cmp DWORD PTR [rsi],04652414Dh
    jne trace_leave_invalid
    cmp DWORD PTR [rsi+4],2
    jne trace_leave_invalid
    cmp QWORD PTR [rsi+40],rbx
    jne trace_leave_invalid
    cmp QWORD PTR [rsi+32],rdi
    jne trace_leave_invalid
    test DWORD PTR [rsi+28],0FFFFFFFEh
    jnz trace_leave_invalid
    mov ecx,DWORD PTR [rbx+12]
    call TlsGetValue
    cmp rax,rsi
    jne trace_leave_invalid
    mov ecx,DWORD PTR [rbx+12]
    mov rdx,QWORD PTR [rsi+8]
    call TlsSetValue
    test eax,eax
    jz trace_leave_poison
    mov QWORD PTR [rsi],0
    test DWORD PTR [rsi+28],1
    jz trace_leave_ok
    lock dec QWORD PTR [rbx+32]
trace_leave_ok:
    xor eax,eax
    jmp trace_leave_done
trace_leave_poison:
    ; Never allow a later traversal of a node whose native frame has returned.
    mov DWORD PTR [rbx+8],3
    mov QWORD PTR [rsi],0
    test DWORD PTR [rsi+28],1
    jz trace_leave_invalid
    lock dec QWORD PTR [rbx+32]
trace_leave_invalid:
    cmp DWORD PTR [rdi],0
    jne trace_leave_error
    mov DWORD PTR [rdi],7
trace_leave_error:
    mov eax,1
trace_leave_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_trace_leave ENDP

boom_trace_release PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    call trace_pool_valid
    test eax,eax
    jz trace_release_invalid
    cmp DWORD PTR [rbx+8],4
    je trace_release_ok
    xor eax,eax
    mov edx,1
    lock cmpxchg DWORD PTR [rbx+40],edx
    jne trace_release_busy
    cmp QWORD PTR [rbx+32],0
    jne trace_release_unlock_busy
    cmp DWORD PTR [rbx+8],1
    je trace_release_unlock_busy
    mov ecx,DWORD PTR [rbx+12]
    cmp ecx,-1
    je trace_release_closed
    call TlsFree
    test eax,eax
    jz trace_release_unlock_invalid
trace_release_closed:
    mov DWORD PTR [rbx+12],-1
    mov DWORD PTR [rbx+8],4
trace_release_ok:
    xor eax,eax
    jmp trace_release_done
trace_release_unlock_invalid:
    mov DWORD PTR [rbx+40],0
trace_release_invalid:
    mov eax,87
    jmp trace_release_done
trace_release_unlock_busy:
    mov DWORD PTR [rbx+40],0
trace_release_busy:
    mov eax,170
trace_release_done:
    add rsp,32
    pop rbx
    ret
boom_trace_release ENDP

; head(pool,Context16)->current Java node/NULL. It does not create a fake frame.
boom_trace_head PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    cmp DWORD PTR [rsi],0
    jne trace_head_none
    call trace_pool_valid
    test eax,eax
    jz trace_head_bad
    cmp DWORD PTR [rbx+8],0
    je trace_head_none
    cmp DWORD PTR [rbx+8],2
    jne trace_head_bad
    cmp DWORD PTR [rbx+12],-1
    je trace_head_bad
    mov ecx,DWORD PTR [rbx+12]
    call TlsGetValue
    jmp trace_head_done
trace_head_bad:
    mov DWORD PTR [rsi],7
trace_head_none:
    xor eax,eax
trace_head_done:
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_trace_head ENDP
END
