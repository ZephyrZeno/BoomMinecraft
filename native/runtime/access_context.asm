; AccessController VM services. Actual AOT frame metadata and VM-bound domains.
; There is no permissive fallback for an unbound application protection domain.
option casemap:none
EXTERN boom_trace_head:PROC
EXTERN boom_mirror_typeid:PROC
EXTERN boom_mirror_load:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_threads_current:PROC
EXTERN boom_heap_alloc:PROC
EXTERN boom_object_new:PROC
EXTERN boom_class_ensure32:PROC
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockShared:PROC
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
PUBLIC boom_access_context_query
PUBLIC boom_access_bind_domain
.code
; ACCP192/1. Immutable pointers except domain roots/state and SRW lock160.
access_pool_valid PROC
    test rcx,rcx
    jz access_pool_bad
    cmp DWORD PTR [rcx],050434341h
    jne access_pool_bad
    cmp DWORD PTR [rcx+4],1
    jne access_pool_bad
    cmp DWORD PTR [rcx+8],4
    jne access_pool_bad
    cmp DWORD PTR [rcx+12],0
    jne access_pool_bad
    cmp DWORD PTR [rcx+148],0
    jne access_pool_bad
    cmp QWORD PTR [rcx+168],0
    jne access_pool_bad
    cmp QWORD PTR [rcx+176],0
    jne access_pool_bad
    cmp QWORD PTR [rcx+184],0
    jne access_pool_bad
    mov r10d,16
access_pool_ptrs:
    cmp QWORD PTR [rcx+r10],0
    je access_pool_bad
    add r10d,8
    cmp r10d,96
    jb access_pool_ptrs
    cmp QWORD PTR [rcx+120],0
    je access_pool_bad
    cmp QWORD PTR [rcx+128],0
    je access_pool_bad
    cmp QWORD PTR [rcx+136],0
    je access_pool_bad
    cmp QWORD PTR [rcx+152],0
    je access_pool_bad
    mov eax,DWORD PTR [rcx+116]
    dec eax
    cmp eax,16383
    ja access_pool_bad
    mov eax,DWORD PTR [rcx+144]
    dec eax
    cmp eax,262143
    ja access_pool_bad
    mov eax,1
    ret
access_pool_bad:
    xor eax,eax
    ret
access_pool_valid ENDP

; (heap,oop)->boolean, live complete owned block. Typed VM inputs, not a sandbox.
access_owned PROC
    test rcx,rcx
    jz access_owned_bad
    cmp DWORD PTR [rcx],048454150h
    jne access_owned_bad
    cmp DWORD PTR [rcx+4],1
    jne access_owned_bad
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz access_owned_bad
    cmp rax,040000000h
    ja access_owned_bad
    lea r10,[rcx+128]
    add rax,r10
    jc access_owned_bad
    cmp rax,QWORD PTR [rcx+24]
    jne access_owned_bad
    lea r10,[rcx+160]
    cmp rdx,r10
    jb access_owned_bad
    cmp rdx,rax
    ja access_owned_bad
    test dl,15
    jnz access_owned_bad
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,0B00B0001h
    jne access_owned_bad
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb access_owned_bad
    test r10b,15
    jnz access_owned_bad
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja access_owned_bad
    add r10,rdx
    jc access_owned_bad
    cmp r10,rax
    ja access_owned_bad
    mov eax,1
    ret
access_owned_bad:
    xor eax,eax
    ret
access_owned ENDP

; (ctx,nonnull oop,pool,expected TypeDesc)->boolean/VerifyError.
access_object_type PROC FRAME
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
    call access_owned
    test eax,eax
    jz access_type_bad
    mov rcx,rsi
    mov rdx,QWORD PTR [rdi+24]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne access_type_error
    test rax,rax
    jz access_type_bad
    mov rcx,rax
    mov rdx,r12
    call boom_type_assignable
    test eax,eax
    jnz access_type_done
access_type_bad:
    mov DWORD PTR [rbx],7
access_type_error:
    xor eax,eax
access_type_done:
    add rsp,40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
access_object_type ENDP

; (ctx,argv,pool,operation)->ACC/Class/null/void. 0 stack,1 inherited,2 escape,3 caller.
boom_access_context_query PROC FRAME
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
    sub rsp,1136
    .allocstack 1136
    .endprolog
    mov rbx,rcx
    mov r12,rdx
    mov rdi,r8
    mov esi,r9d
    mov DWORD PTR [rsp+32],0
    mov QWORD PTR [rsp+64],0
    test rbx,rbx
    jz access_query_error
    cmp DWORD PTR [rbx],0
    jne access_query_error
    mov rcx,rdi
    call access_pool_valid
    test eax,eax
    jz access_query_bad
    cmp esi,3
    ja access_query_bad
    je access_query_caller
    cmp esi,2
    je access_query_escape
    test esi,esi
    jnz access_query_inherited
    mov rcx,QWORD PTR [rdi+48]
    mov rdx,rbx
    call boom_class_ensure32
    test eax,eax
    jnz access_query_error
    lea rcx,[rdi+160]
    call AcquireSRWLockShared
    mov DWORD PTR [rsp+32],1
    mov DWORD PTR [rsp+48],0
    mov DWORD PTR [rsp+56],0
    xor r13d,r13d
    xor r14d,r14d
    xor r15d,r15d
    mov rcx,QWORD PTR [rdi+40]
    mov rdx,rbx
    call boom_trace_head
    cmp DWORD PTR [rbx],0
    jne access_query_error
    mov r12,rax
access_frame_loop:
    test r12,r12
    jz access_capture_done
    inc DWORD PTR [rsp+56]
    cmp DWORD PTR [rsp+56],128
    ja access_query_bad
    cmp DWORD PTR [r12],04652414Dh
    jne access_query_bad
    cmp DWORD PTR [r12+4],2
    jne access_query_bad
    mov rax,QWORD PTR [rdi+40]
    cmp QWORD PTR [r12+40],rax
    jne access_query_bad
    test DWORD PTR [r12+28],0FFFFFFFEh
    jnz access_query_bad
    mov rax,QWORD PTR [r12+16]
    test rax,rax
    jz access_query_bad
    mov ecx,DWORD PTR [rax]
    cmp ecx,DWORD PTR [rdi+144]
    jae access_query_bad
    shl rcx,5
    add rcx,QWORD PTR [rdi+136]
    cmp QWORD PTR [rcx],rax
    jne access_query_bad
    mov edx,DWORD PTR [r12+24]
    cmp edx,DWORD PTR [rax+16]
    jae access_query_bad
    cmp QWORD PTR [rcx+24],0
    jne access_query_bad
    mov edx,DWORD PTR [rcx+8]
    test DWORD PTR [rcx+12],0FFFFFFF8h
    jnz access_query_bad
    test DWORD PTR [rcx+12],4
    jnz access_frame_next
    test DWORD PTR [rcx+12],1
    jz access_frame_domain
    cmp DWORD PTR [rcx+20],3
    jb access_query_bad
    movsxd rax,DWORD PTR [rcx+16]
    cmp rax,-4096
    jl access_query_bad
    cmp rax,-24
    jg access_query_bad
    add rax,r12
    mov r15,QWORD PTR [rax+8]
    mov rdx,QWORD PTR [rax+16]
    mov rcx,rbx
    mov r8,QWORD PTR [rdi+32]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne access_query_error
    mov edx,eax
    test r15,r15
    jz access_privileged_ready
    mov DWORD PTR [rsp+80],edx
    mov rcx,rbx
    mov rdx,r15
    mov r8,rdi
    mov r9,QWORD PTR [rdi+80]
    call access_object_type
    test eax,eax
    jz access_query_error
    mov edx,DWORD PTR [rsp+80]
access_privileged_ready:
    mov DWORD PTR [rsp+48],1
access_frame_domain:
    cmp edx,DWORD PTR [rdi+116]
    jae access_query_bad
    mov rax,QWORD PTR [rdi+128]
    cmp DWORD PTR [rax+rdx*4],1
    jne access_query_bad
    mov rax,QWORD PTR [rdi+120]
    mov rax,QWORD PTR [rax+rdx*8]
    test rax,rax
    jz access_frame_next
    cmp rax,r14
    je access_frame_next
    cmp r13d,128
    jae access_query_bad
    mov QWORD PTR [rsp+r13*8+96],rax
    inc r13d
    mov r14,rax
access_frame_next:
    cmp DWORD PTR [rsp+48],0
    jne access_capture_done
    mov rax,QWORD PTR [r12+8]
    test rax,rax
    jz access_capture_done
    cmp rax,r12
    jbe access_query_bad
    mov r12,rax
    jmp access_frame_loop
access_capture_done:
    test r13d,r13d
    jnz access_allocate_array
    cmp DWORD PTR [rsp+48],0
    je access_no_domains
    test r15,r15
    jz access_query_error
access_no_domains:
    mov QWORD PTR [rsp+40],0
    jmp access_allocate_context
access_allocate_array:
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    mov edx,r13d
    shl rdx,3
    mov r8d,r13d
    mov r9,QWORD PTR [rdi+64]
    call boom_heap_alloc
    test rax,rax
    jz access_query_oom
    mov QWORD PTR [rsp+40],rax
    xor ecx,ecx
access_copy_domains:
    mov rdx,QWORD PTR [rsp+rcx*8+96]
    mov QWORD PTR [rax+rcx*8],rdx
    inc ecx
    cmp ecx,r13d
    jb access_copy_domains
access_allocate_context:
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rdi+56]
    mov r8,rbx
    call boom_object_new
    test rax,rax
    jz access_query_error
    mov edx,DWORD PTR [rdi+96]
    mov rcx,QWORD PTR [rsp+40]
    mov QWORD PTR [rax+rdx],rcx
    mov edx,DWORD PTR [rdi+100]
    mov QWORD PTR [rax+rdx],r15
    mov edx,DWORD PTR [rdi+104]
    mov ecx,DWORD PTR [rsp+48]
    mov BYTE PTR [rax+rdx],cl
    mov edx,DWORD PTR [rdi+108]
    mov BYTE PTR [rax+rdx],1
    jmp access_query_result
access_query_inherited:
    mov rcx,QWORD PTR [rdi+72]
    mov rcx,QWORD PTR [rcx]
    call boom_threads_current
    test rax,rax
    jz access_query_bad
    mov r12,rax
    mov rcx,rbx
    mov rdx,rax
    mov r8,rdi
    mov r9,QWORD PTR [rdi+152]
    call access_object_type
    test eax,eax
    jz access_query_error
    mov edx,DWORD PTR [rdi+112]
    mov r12,QWORD PTR [r12+rdx]
    test r12,r12
    jz access_query_error
    mov rcx,rbx
    mov rdx,r12
    mov r8,rdi
    mov r9,QWORD PTR [rdi+80]
    call access_object_type
    test eax,eax
    jz access_query_error
    mov rax,r12
    jmp access_query_result
access_query_escape:
    test r12,r12
    jz access_query_bad
    mov rdx,QWORD PTR [r12]
    test rdx,rdx
    jz access_query_error
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    call access_owned
    test eax,eax
    jz access_query_bad
    mov rcx,rdx
    mov rdx,QWORD PTR [rdi+24]
    mov r8,rbx
    call boom_runtime_type
    jmp access_query_error
access_query_caller:
    xor r13d,r13d
    mov rcx,QWORD PTR [rdi+40]
    mov rdx,rbx
    call boom_trace_head
    cmp DWORD PTR [rbx],0
    jne access_query_error
    mov r12,rax
access_caller_loop:
    test r12,r12
    jz access_query_error
    inc r13d
    cmp r13d,128
    ja access_query_bad
    cmp DWORD PTR [r12],04652414Dh
    jne access_query_bad
    cmp DWORD PTR [r12+4],2
    jne access_query_bad
    mov rax,QWORD PTR [rdi+40]
    cmp QWORD PTR [r12+40],rax
    jne access_query_bad
    test DWORD PTR [r12+28],0FFFFFFFEh
    jnz access_query_bad
    mov rax,QWORD PTR [r12+16]
    test rax,rax
    jz access_query_bad
    mov ecx,DWORD PTR [rax]
    cmp ecx,DWORD PTR [rdi+144]
    jae access_query_bad
    shl rcx,5
    add rcx,QWORD PTR [rdi+136]
    cmp QWORD PTR [rcx],rax
    jne access_query_bad
    cmp QWORD PTR [rcx+24],0
    jne access_query_bad
    mov edx,DWORD PTR [r12+24]
    cmp edx,DWORD PTR [rax+16]
    jae access_query_bad
    mov edx,DWORD PTR [rcx+8]
    cmp edx,DWORD PTR [rdi+116]
    jae access_query_bad
    mov eax,DWORD PTR [rcx+12]
    test eax,0FFFFFFF8h
    jnz access_query_bad
    cmp r13d,1
    jne access_caller_candidate
    test eax,2
    jz access_caller_annotation_error
    jmp access_caller_next
access_caller_candidate:
    test eax,4
    jnz access_caller_next
    mov r8d,edx
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rdi+32]
    mov r9,rbx
    call boom_mirror_load
    jmp access_query_result
access_caller_next:
    mov rax,QWORD PTR [r12+8]
    test rax,rax
    jz access_query_error
    cmp rax,r12
    jbe access_query_bad
    mov r12,rax
    jmp access_caller_loop
access_caller_annotation_error:
    mov DWORD PTR [rbx],23
    jmp access_query_error
access_query_oom:
    mov DWORD PTR [rbx],3
    jmp access_query_error
access_query_bad:
    mov DWORD PTR [rbx],7
access_query_error:
    xor eax,eax
access_query_result:
    mov QWORD PTR [rsp+64],rax
    cmp DWORD PTR [rsp+32],0
    je access_query_done
    lea rcx,[rdi+160]
    call ReleaseSRWLockShared
access_query_done:
    mov rax,QWORD PTR [rsp+64]
    add rsp,1136
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_access_context_query ENDP

; VM-only bind(pool,typeID,nonnull PD)->0/87/170. Once bound, identity is immutable.
; Caller must hold a live PD and serialize VM lifecycle/explicit GC.
boom_access_bind_domain PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    sub rsp,72
    .allocstack 72
    .endprolog
    mov rdi,rcx
    mov esi,edx
    mov r12,r8
    mov ebx,87
    call access_pool_valid
    test eax,eax
    jz access_bind_done
    cmp esi,DWORD PTR [rdi+116]
    jae access_bind_done
    test r12,r12
    jz access_bind_lock
    xor eax,eax
    mov QWORD PTR [rsp+32],rax
    mov QWORD PTR [rsp+40],rax
    mov QWORD PTR [rsp+48],rax
    mov QWORD PTR [rsp+56],rax
    lea rcx,[rsp+32]
    mov rdx,r12
    mov r8,rdi
    mov r9,QWORD PTR [rdi+88]
    call access_object_type
    test eax,eax
    jz access_bind_done
access_bind_lock:
    lea rcx,[rdi+160]
    call AcquireSRWLockExclusive
    mov rax,QWORD PTR [rdi+40]
    cmp QWORD PTR [rax+32],0
    jne access_bind_busy
    cmp DWORD PTR [rax+40],0
    jne access_bind_busy
    cmp DWORD PTR [rax+8],4
    je access_bind_unlock
    mov rax,QWORD PTR [rdi+128]
    mov rcx,QWORD PTR [rdi+120]
    cmp DWORD PTR [rax+rsi*4],0
    jne access_bind_existing
    test r12,r12
    jz access_bind_unlock
    mov QWORD PTR [rcx+rsi*8],r12
    mov DWORD PTR [rax+rsi*4],1
    xor ebx,ebx
    jmp access_bind_unlock
access_bind_existing:
    cmp QWORD PTR [rcx+rsi*8],r12
    jne access_bind_unlock
    xor ebx,ebx
    jmp access_bind_unlock
access_bind_busy:
    mov ebx,170
access_bind_unlock:
    lea rcx,[rdi+160]
    call ReleaseSRWLockExclusive
access_bind_done:
    mov eax,ebx
    add rsp,72
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_access_bind_domain ENDP
END
