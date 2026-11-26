; Normal Class/ACC layouts, ACCP192/2 and source ABI3 frames.
; Derived from our existing MASM domain collector. Unbound domains fail closed.
; AccessController VM services. Actual AOT frame metadata and VM-bound domains.
; There is no permissive fallback for an unbound application protection domain.
EXTERN boom_trace_head:PROC
EXTERN boom_java_class_typeid:PROC
EXTERN boom_java_class_load:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_threads_current:PROC
EXTERN boom_heap_alloc:PROC
EXTERN boom_object_new:PROC
EXTERN boom_class_ensure32:PROC
PUBLIC boom_provider_access_service
PUBLIC boom_provider_access_bind_domain
.code
; Pool-local RW lock: bit63 writer reservation, low63 active readers.
; Reserving the writer bit blocks new readers while existing readers drain.
; All publication and acquisition ordering is implemented by x86 atomics.
nac_acquire_shared PROC PRIVATE
nac_read_retry:
    mov rax,QWORD PTR [rcx]
    test rax,rax
    js nac_read_wait
    lea rdx,[rax+1]
    lock cmpxchg QWORD PTR [rcx],rdx
    jne nac_read_retry
    ret
nac_read_wait:
    pause
    jmp nac_read_retry
nac_acquire_shared ENDP
nac_release_shared PROC PRIVATE
    lock dec QWORD PTR [rcx]
    ret
nac_release_shared ENDP
nac_acquire_exclusive PROC PRIVATE
nac_write_retry:
    lock bts QWORD PTR [rcx],63
    jnc nac_write_drain
    pause
    jmp nac_write_retry
nac_write_drain:
    mov rax,QWORD PTR [rcx]
    btr rax,63
    test rax,rax
    jz nac_write_ready
    pause
    jmp nac_write_drain
nac_write_ready:
    ret
nac_acquire_exclusive ENDP
nac_release_exclusive PROC PRIVATE
    mov QWORD PTR [rcx],0
    ret
nac_release_exclusive ENDP
; ACCP192/2. Immutable pointers except domain roots/state and RW lock160.
nac_pool_valid PROC PRIVATE
    test rcx,rcx
    jz nac_pool_bad
    cmp DWORD PTR [rcx],050434341h
    jne nac_pool_bad
    cmp DWORD PTR [rcx+4],2
    jne nac_pool_bad
    cmp DWORD PTR [rcx+8],4
    jne nac_pool_bad
    cmp DWORD PTR [rcx+12],0
    jne nac_pool_bad
    cmp DWORD PTR [rcx+148],0
    jne nac_pool_bad
    cmp QWORD PTR [rcx+168],0
    jne nac_pool_bad
    cmp QWORD PTR [rcx+176],0
    jne nac_pool_bad
    cmp QWORD PTR [rcx+184],0
    jne nac_pool_bad
    mov r10d,16
nac_pool_ptrs:
    cmp QWORD PTR [rcx+r10],0
    je nac_pool_bad
    add r10d,8
    cmp r10d,96
    jb nac_pool_ptrs
    cmp QWORD PTR [rcx+120],0
    je nac_pool_bad
    cmp QWORD PTR [rcx+128],0
    je nac_pool_bad
    cmp QWORD PTR [rcx+136],0
    je nac_pool_bad
    cmp QWORD PTR [rcx+152],0
    je nac_pool_bad
    mov eax,DWORD PTR [rcx+116]
    dec eax
    cmp eax,1048575
    ja nac_pool_bad
    mov eax,DWORD PTR [rcx+144]
    dec eax
    cmp eax,1048575
    ja nac_pool_bad
    mov eax,1
    ret
nac_pool_bad:
    xor eax,eax
    ret
nac_pool_valid ENDP

; (heap,oop)->boolean, live complete owned block. Typed VM inputs, not a sandbox.
nac_owned PROC PRIVATE
    test rcx,rcx
    jz nac_owned_bad
    cmp DWORD PTR [rcx],048454150h
    jne nac_owned_bad
    cmp DWORD PTR [rcx+4],1
    jne nac_owned_bad
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz nac_owned_bad
    cmp rax,040000000h
    ja nac_owned_bad
    lea r10,[rcx+128]
    add rax,r10
    jc nac_owned_bad
    cmp rax,QWORD PTR [rcx+24]
    jne nac_owned_bad
    lea r10,[rcx+160]
    cmp rdx,r10
    jb nac_owned_bad
    cmp rdx,rax
    ja nac_owned_bad
    test dl,15
    jnz nac_owned_bad
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,0B00B0001h
    jne nac_owned_bad
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb nac_owned_bad
    test r10b,15
    jnz nac_owned_bad
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja nac_owned_bad
    add r10,rdx
    jc nac_owned_bad
    cmp r10,rax
    ja nac_owned_bad
    mov eax,1
    ret
nac_owned_bad:
    xor eax,eax
    ret
nac_owned ENDP

; (ctx,nonnull oop,pool,expected TypeDesc)->boolean/VerifyError.
nac_object_type PROC PRIVATE FRAME
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
    call nac_owned
    test eax,eax
    jz nac_type_bad
    mov rcx,rsi
    mov rdx,QWORD PTR [rdi+24]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne nac_type_error
    test rax,rax
    jz nac_type_bad
    mov rcx,rax
    mov rdx,r12
    call boom_type_assignable
    test eax,eax
    jnz nac_type_done
nac_type_bad:
    mov DWORD PTR [rbx],7
nac_type_error:
    xor eax,eax
nac_type_done:
    add rsp,40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
nac_object_type ENDP

; (ctx,argv,pool,operation)->ACC/Class/null/void. 0 stack,1 inherited,2 escape,3 caller.
boom_provider_access_service PROC FRAME
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
    jz nac_query_error
    cmp DWORD PTR [rbx],0
    jne nac_query_error
    mov rcx,rdi
    call nac_pool_valid
    test eax,eax
    jz nac_query_bad
    cmp esi,3
    ja nac_query_bad
    je nac_query_caller
    cmp esi,2
    je nac_query_escape
    test esi,esi
    jnz nac_query_inherited
    mov rcx,QWORD PTR [rdi+48]
    mov rdx,rbx
    call boom_class_ensure32
    test eax,eax
    jnz nac_query_error
    lea rcx,[rdi+160]
    call nac_acquire_shared
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
    jne nac_query_error
    mov r12,rax
nac_frame_loop:
    test r12,r12
    jz nac_capture_done
    inc DWORD PTR [rsp+56]
    cmp DWORD PTR [rsp+56],128
    ja nac_query_bad
    cmp DWORD PTR [r12],04652414Dh
    jne nac_query_bad
    cmp DWORD PTR [r12+4],2
    jne nac_query_bad
    cmp QWORD PTR [r12+32],rbx
    jne nac_query_unbound
    mov rax,QWORD PTR [rdi+40]
    cmp QWORD PTR [r12+40],rax
    jne nac_query_bad
    test DWORD PTR [r12+28],0FFFFFFFEh
    jnz nac_query_bad
    mov rax,QWORD PTR [r12+16]
    test rax,rax
    jz nac_query_bad
    mov ecx,DWORD PTR [rax]
    cmp ecx,DWORD PTR [rdi+144]
    jae nac_query_bad
    shl rcx,5
    add rcx,QWORD PTR [rdi+136]
    cmp QWORD PTR [rcx],rax
    jne nac_query_bad
    test DWORD PTR [rax+4],128
    jnz nac_query_unbound
    mov edx,DWORD PTR [r12+24]
    test DWORD PTR [rax+4],32
    jz nac_stack_pc_ready_java
    test edx,edx
    jnz nac_query_bad
    cmp DWORD PTR [rax+16],0
    jne nac_query_bad
    jmp nac_stack_pc_ready
nac_stack_pc_ready_java:
    cmp edx,DWORD PTR [rax+16]
    jae nac_query_bad
nac_stack_pc_ready:
    cmp QWORD PTR [rcx+24],0
    jne nac_query_bad
    mov edx,DWORD PTR [rcx+8]
    test DWORD PTR [rcx+12],0FFFFFFF8h
    jnz nac_query_bad
    test DWORD PTR [rcx+12],4
    jnz nac_frame_next
    test DWORD PTR [rcx+12],1
    jz nac_frame_domain
    cmp DWORD PTR [rcx+20],3
    jb nac_query_bad
    movsxd rax,DWORD PTR [rcx+16]
    cmp rax,-4096
    jl nac_query_bad
    cmp rax,-24
    jg nac_query_bad
    add rax,r12
    mov r15,QWORD PTR [rax+8]
    mov rdx,QWORD PTR [rax+16]
    mov rcx,rbx
    mov r8,QWORD PTR [rdi+32]
    xchg rdx,r8
    call boom_java_class_typeid
    cmp DWORD PTR [rbx],0
    jne nac_query_error
    mov edx,eax
    test r15,r15
    jz nac_privileged_ready
    mov DWORD PTR [rsp+80],edx
    mov rcx,rbx
    mov rdx,r15
    mov r8,rdi
    mov r9,QWORD PTR [rdi+80]
    call nac_object_type
    test eax,eax
    jz nac_query_error
    mov edx,DWORD PTR [rsp+80]
nac_privileged_ready:
    mov DWORD PTR [rsp+48],1
nac_frame_domain:
    cmp edx,DWORD PTR [rdi+116]
    jae nac_query_bad
    mov rax,QWORD PTR [rdi+128]
    cmp DWORD PTR [rax+rdx*4],1
    jne nac_query_bad
    mov rax,QWORD PTR [rdi+120]
    mov rax,QWORD PTR [rax+rdx*8]
    test rax,rax
    jz nac_frame_next
    cmp rax,r14
    je nac_frame_next
    cmp r13d,128
    jae nac_query_bad
    mov QWORD PTR [rsp+r13*8+96],rax
    inc r13d
    mov r14,rax
nac_frame_next:
    cmp DWORD PTR [rsp+48],0
    jne nac_capture_done
    mov rax,QWORD PTR [r12+8]
    test rax,rax
    jz nac_capture_done
    cmp rax,r12
    jbe nac_query_bad
    mov r12,rax
    jmp nac_frame_loop
nac_capture_done:
    test r13d,r13d
    jnz nac_allocate_array
    cmp DWORD PTR [rsp+48],0
    je nac_no_domains
    test r15,r15
    jz nac_query_error
nac_no_domains:
    mov QWORD PTR [rsp+40],0
    jmp nac_allocate_context
nac_allocate_array:
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    mov edx,r13d
    shl rdx,3
    mov r8d,r13d
    mov r9,QWORD PTR [rdi+64]
    call boom_heap_alloc
    test rax,rax
    jz nac_query_oom
    mov QWORD PTR [rsp+40],rax
    xor ecx,ecx
nac_copy_domains:
    mov rdx,QWORD PTR [rsp+rcx*8+96]
    mov QWORD PTR [rax+rcx*8],rdx
    inc ecx
    cmp ecx,r13d
    jb nac_copy_domains
nac_allocate_context:
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rdi+56]
    mov r8,rbx
    call boom_object_new
    test rax,rax
    jz nac_query_error
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
    jmp nac_query_result
nac_query_inherited:
    mov rcx,QWORD PTR [rdi+72]
    mov rcx,QWORD PTR [rcx]
    call boom_threads_current
    test rax,rax
    jz nac_query_bad
    mov r12,rax
    mov rcx,rbx
    mov rdx,rax
    mov r8,rdi
    mov r9,QWORD PTR [rdi+152]
    call nac_object_type
    test eax,eax
    jz nac_query_error
    mov edx,DWORD PTR [rdi+112]
    mov r12,QWORD PTR [r12+rdx]
    test r12,r12
    jz nac_query_error
    mov rcx,rbx
    mov rdx,r12
    mov r8,rdi
    mov r9,QWORD PTR [rdi+80]
    call nac_object_type
    test eax,eax
    jz nac_query_error
    mov rax,r12
    jmp nac_query_result
nac_query_escape:
    test r12,r12
    jz nac_query_bad
    mov rdx,QWORD PTR [r12]
    test rdx,rdx
    jz nac_query_error
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    call nac_owned
    test eax,eax
    jz nac_query_bad
    mov rcx,rdx
    mov rdx,QWORD PTR [rdi+24]
    mov r8,rbx
    call boom_runtime_type
    jmp nac_query_error
nac_query_caller:
    xor r13d,r13d
    mov rcx,QWORD PTR [rdi+40]
    mov rdx,rbx
    call boom_trace_head
    cmp DWORD PTR [rbx],0
    jne nac_query_error
    mov r12,rax
nac_caller_loop:
    test r12,r12
    jz nac_query_error
    inc r13d
    cmp r13d,128
    ja nac_query_bad
    cmp DWORD PTR [r12],04652414Dh
    jne nac_query_bad
    cmp DWORD PTR [r12+4],2
    jne nac_query_bad
    cmp QWORD PTR [r12+32],rbx
    jne nac_query_unbound
    mov rax,QWORD PTR [rdi+40]
    cmp QWORD PTR [r12+40],rax
    jne nac_query_bad
    test DWORD PTR [r12+28],0FFFFFFFEh
    jnz nac_query_bad
    mov rax,QWORD PTR [r12+16]
    test rax,rax
    jz nac_query_bad
    mov ecx,DWORD PTR [rax]
    cmp ecx,DWORD PTR [rdi+144]
    jae nac_query_bad
    shl rcx,5
    add rcx,QWORD PTR [rdi+136]
    cmp QWORD PTR [rcx],rax
    jne nac_query_bad
    cmp QWORD PTR [rcx+24],0
    jne nac_query_bad
    test DWORD PTR [rax+4],128
    jnz nac_query_unbound
    mov edx,DWORD PTR [r12+24]
    test DWORD PTR [rax+4],32
    jz nac_caller_pc_ready_java
    test edx,edx
    jnz nac_query_bad
    cmp DWORD PTR [rax+16],0
    jne nac_query_bad
    jmp nac_caller_pc_ready
nac_caller_pc_ready_java:
    cmp edx,DWORD PTR [rax+16]
    jae nac_query_bad
nac_caller_pc_ready:
    mov edx,DWORD PTR [rcx+8]
    cmp edx,DWORD PTR [rdi+116]
    jae nac_query_bad
    mov eax,DWORD PTR [rcx+12]
    test eax,0FFFFFFF8h
    jnz nac_query_bad
    cmp r13d,1
    jne nac_caller_candidate
    test eax,2
    jz nac_caller_annotation_error
    jmp nac_caller_next
nac_caller_candidate:
    test eax,4
    jnz nac_caller_next
    mov r8d,edx
    mov rcx,rbx
    mov rdx,QWORD PTR [rdi+32]
    call boom_java_class_load
    jmp nac_query_result
nac_caller_next:
    mov rax,QWORD PTR [r12+8]
    test rax,rax
    jz nac_query_error
    cmp rax,r12
    jbe nac_query_bad
    mov r12,rax
    jmp nac_caller_loop
nac_caller_annotation_error:
    mov DWORD PTR [rbx],23
    jmp nac_query_error
nac_query_oom:
    mov DWORD PTR [rbx],3
    jmp nac_query_error
nac_query_unbound:
    mov DWORD PTR [rbx],20
    jmp nac_query_error
nac_query_bad:
    mov DWORD PTR [rbx],7
nac_query_error:
    xor eax,eax
nac_query_result:
    mov QWORD PTR [rsp+64],rax
    cmp DWORD PTR [rsp+32],0
    je nac_query_done
    lea rcx,[rdi+160]
    call nac_release_shared
nac_query_done:
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
boom_provider_access_service ENDP

; VM-only bind(pool,typeID,nonnull PD)->0/87/170. Once bound, identity is immutable.
; Caller must hold a live PD and serialize VM lifecycle/explicit GC.
boom_provider_access_bind_domain PROC FRAME
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
    call nac_pool_valid
    test eax,eax
    jz nac_bind_done
    cmp esi,DWORD PTR [rdi+116]
    jae nac_bind_done
    test r12,r12
    jz nac_bind_lock
    xor eax,eax
    mov QWORD PTR [rsp+32],rax
    mov QWORD PTR [rsp+40],rax
    mov QWORD PTR [rsp+48],rax
    mov QWORD PTR [rsp+56],rax
    lea rcx,[rsp+32]
    mov rdx,r12
    mov r8,rdi
    mov r9,QWORD PTR [rdi+88]
    call nac_object_type
    test eax,eax
    jz nac_bind_done
nac_bind_lock:
    lea rcx,[rdi+160]
    call nac_acquire_exclusive
    mov rax,QWORD PTR [rdi+40]
    cmp QWORD PTR [rax+32],0
    jne nac_bind_busy
    cmp DWORD PTR [rax+40],0
    jne nac_bind_busy
    cmp DWORD PTR [rax+8],4
    je nac_bind_unlock
    mov rax,QWORD PTR [rdi+128]
    mov rcx,QWORD PTR [rdi+120]
    cmp DWORD PTR [rax+rsi*4],0
    jne nac_bind_existing
    test r12,r12
    jz nac_bind_unlock
    mov QWORD PTR [rcx+rsi*8],r12
    mov DWORD PTR [rax+rsi*4],1
    xor ebx,ebx
    jmp nac_bind_unlock
nac_bind_existing:
    cmp QWORD PTR [rcx+rsi*8],r12
    jne nac_bind_unlock
    xor ebx,ebx
    jmp nac_bind_unlock
nac_bind_busy:
    mov ebx,170
nac_bind_unlock:
    lea rcx,[rdi+160]
    call nac_release_exclusive
nac_bind_done:
    mov eax,ebx
    add rsp,72
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_provider_access_bind_domain ENDP
