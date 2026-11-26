; VM-owned Class.classLoader field, stored by canonical metadata type identity.
; Loader roots are immutable after VM binding. Unbound application loaders fail.
; LDRP96/1: heapCell8,mirrors16,runtimeTypes24,roots32,bound40,typeLoaderIds48,
; loaderCount56,typeCount60,ClassLoaderType64,tracePool72,SRW80,reserved88.
option casemap:none
EXTERN boom_mirror_typeid:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_heap_contains:PROC
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockShared:PROC
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
PUBLIC boom_class_loader_field
PUBLIC boom_class_loader_bind
PUBLIC boom_class_loader_register
PUBLIC boom_class_loader_retrieve
PUBLIC boom_class_loader_key
.code
loader_pool_valid PROC
    test rcx,rcx
    jz loader_pool_bad
    cmp DWORD PTR [rcx],05052444Ch
    jne loader_pool_bad
    cmp DWORD PTR [rcx+4],1
    jne loader_pool_bad
    cmp QWORD PTR [rcx+88],0
    jne loader_pool_bad
    mov r10d,8
loader_pool_ptrs:
    cmp QWORD PTR [rcx+r10],0
    je loader_pool_bad
    add r10d,8
    cmp r10d,56
    jb loader_pool_ptrs
    mov eax,DWORD PTR [rcx+56]
    dec eax
    cmp eax,16383
    ja loader_pool_bad
    mov eax,DWORD PTR [rcx+60]
    dec eax
    cmp eax,16383
    ja loader_pool_bad
    cmp QWORD PTR [rcx+64],0
    je loader_pool_bad
    mov rax,QWORD PTR [rcx+72]
    test rax,rax
    jz loader_pool_bad
    cmp DWORD PTR [rax],05452504Ch
    jne loader_pool_bad
    cmp DWORD PTR [rax+4],2
    jne loader_pool_bad
    mov eax,1
    ret
loader_pool_bad:
    xor eax,eax
    ret
loader_pool_valid ENDP

; get(Context32,argv[Class mirror],pool)->actual loader or bootstrap null.
boom_class_loader_field PROC FRAME
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
    test rbx,rbx
    jz loader_field_error
    cmp DWORD PTR [rbx],0
    jne loader_field_error
    test rsi,rsi
    jz loader_field_bad
    mov rcx,rdi
    call loader_pool_valid
    test eax,eax
    jz loader_field_bad
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi]
    mov r8,QWORD PTR [rdi+16]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne loader_field_error
    cmp eax,DWORD PTR [rdi+60]
    jae loader_field_bad
    mov rdx,QWORD PTR [rdi+48]
    mov esi,DWORD PTR [rdx+rax*4]
    cmp esi,DWORD PTR [rdi+56]
    jae loader_field_bad
    lea rcx,[rdi+80]
    call AcquireSRWLockShared
    mov rax,QWORD PTR [rdi+40]
    cmp DWORD PTR [rax+rsi*4],1
    jne loader_field_unbound
    mov rax,QWORD PTR [rdi+32]
    mov rsi,QWORD PTR [rax+rsi*8]
    lea rcx,[rdi+80]
    call ReleaseSRWLockShared
    mov rax,rsi
    jmp loader_field_done
loader_field_unbound:
    lea rcx,[rdi+80]
    call ReleaseSRWLockShared
loader_field_bad:
    mov DWORD PTR [rbx],7
loader_field_error:
    xor eax,eax
loader_field_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_class_loader_field ENDP

 ; key(Context32,ClassLoader oop,LDRP96)->index/-1. Null is the bootstrap loader.
; Actual non-null loaders require an existing immutable VM binding.
boom_class_loader_key PROC FRAME
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
    test rbx,rbx
    jz loader_key_zero
    cmp DWORD PTR [rbx],0
    jne loader_key_zero
    mov rcx,rdi
    call loader_pool_valid
    test eax,eax
    jz loader_key_bad
    test rsi,rsi
    jz loader_key_boot
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,rsi
    call boom_heap_contains
    test eax,eax
    jz loader_key_bad
    mov rcx,rsi
    mov rdx,QWORD PTR [rdi+24]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne loader_key_zero
    mov rcx,rax
    mov rdx,QWORD PTR [rdi+64]
    call boom_type_assignable
    test eax,eax
    jz loader_key_bad
    lea rcx,[rdi+80]
    call AcquireSRWLockShared
    mov r12d,1
    mov r13d,-1
loader_key_loop:
    cmp r12d,DWORD PTR [rdi+56]
    jae loader_key_unlock
    mov rax,QWORD PTR [rdi+40]
    cmp DWORD PTR [rax+r12*4],1
    jne loader_key_next
    mov rax,QWORD PTR [rdi+32]
    cmp QWORD PTR [rax+r12*8],rsi
    jne loader_key_next
    cmp r13d,-1
    jne loader_key_ambiguous
    mov r13d,r12d
loader_key_next:
    inc r12d
    jmp loader_key_loop
loader_key_ambiguous:
    mov r13d,-2
loader_key_unlock:
    lea rcx,[rdi+80]
    call ReleaseSRWLockShared
    cmp r13d,-2
    je loader_key_bad
    cmp r13d,-1
    je loader_key_unlinked
    mov eax,r13d
    jmp loader_key_done
loader_key_boot:
    xor eax,eax
    jmp loader_key_done
loader_key_unlinked:
    mov DWORD PTR [rbx],20
    jmp loader_key_zero
loader_key_bad:
    mov DWORD PTR [rbx],7
loader_key_zero:
    mov eax,-1
loader_key_done:
    add rsp,32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_class_loader_key ENDP

; bind(pool,loader key index,ClassLoader oop)->Win32 status. VM lifecycle only.
; Caller holds the live constructed loader and serializes lifecycle/explicit GC.
boom_class_loader_bind PROC FRAME
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
    call loader_pool_valid
    test eax,eax
    jz loader_bind_done
    cmp esi,DWORD PTR [rdi+56]
    jae loader_bind_done
    test r12,r12
    jz loader_bind_lock
    ; Check complete heap ownership before tag/assignability lookup.
    mov rax,QWORD PTR [rdi+8]
    mov rax,QWORD PTR [rax]
    test rax,rax
    jz loader_bind_done
    cmp DWORD PTR [rax],048454150h
    jne loader_bind_done
    cmp DWORD PTR [rax+4],1
    jne loader_bind_done
    mov rcx,QWORD PTR [rax+16]
    test rcx,rcx
    jz loader_bind_done
    cmp rcx,040000000h
    ja loader_bind_done
    lea rdx,[rax+128]
    add rcx,rdx
    jc loader_bind_done
    cmp rcx,QWORD PTR [rax+24]
    jne loader_bind_done
    lea rcx,[rax+160]
    cmp r12,rcx
    jb loader_bind_done
    cmp r12,QWORD PTR [rax+24]
    ja loader_bind_done
    test r12b,15
    jnz loader_bind_done
    mov ecx,DWORD PTR [r12-24]
    and ecx,0FFFFFFFDh
    cmp ecx,0B00B0001h
    jne loader_bind_done
    mov rcx,QWORD PTR [r12-32]
    cmp rcx,32
    jb loader_bind_done
    test cl,15
    jnz loader_bind_done
    sub rcx,32
    cmp QWORD PTR [r12-16],rcx
    ja loader_bind_done
    add rcx,r12
    jc loader_bind_done
    cmp rcx,QWORD PTR [rax+24]
    ja loader_bind_done
    xor eax,eax
    mov QWORD PTR [rsp+32],rax
    mov QWORD PTR [rsp+40],rax
    mov QWORD PTR [rsp+48],rax
    mov QWORD PTR [rsp+56],rax
    mov rcx,r12
    mov rdx,QWORD PTR [rdi+24]
    lea r8,[rsp+32]
    call boom_runtime_type
    cmp DWORD PTR [rsp+32],0
    jne loader_bind_done
    test rax,rax
    jz loader_bind_done
    mov rcx,rax
    mov rdx,QWORD PTR [rdi+64]
    call boom_type_assignable
    test eax,eax
    jz loader_bind_done
loader_bind_lock:
    lea rcx,[rdi+80]
    call AcquireSRWLockExclusive
    mov rax,QWORD PTR [rdi+72]
    cmp DWORD PTR [rax+8],3
    jae loader_bind_unlock
    cmp QWORD PTR [rax+32],0
    jne loader_bind_busy
    cmp DWORD PTR [rax+40],0
    jne loader_bind_busy
    mov rcx,QWORD PTR [rdi+40]
    mov rdx,QWORD PTR [rdi+32]
    cmp DWORD PTR [rcx+rsi*4],0
    jne loader_bind_existing
    test r12,r12
    jz loader_bind_unlock
    xor eax,eax
loader_bind_unique:
    cmp eax,DWORD PTR [rdi+56]
    jae loader_bind_publish
    cmp QWORD PTR [rdx+rax*8],r12
    je loader_bind_unlock
    inc eax
    jmp loader_bind_unique
loader_bind_publish:
    mov QWORD PTR [rdx+rsi*8],r12
    mov DWORD PTR [rcx+rsi*4],1
    xor ebx,ebx
    jmp loader_bind_unlock
loader_bind_existing:
    cmp DWORD PTR [rcx+rsi*4],1
    jne loader_bind_unlock
    cmp QWORD PTR [rdx+rsi*8],r12
    jne loader_bind_unlock
    xor ebx,ebx
    jmp loader_bind_unlock
loader_bind_busy:
    mov ebx,170
loader_bind_unlock:
    lea rcx,[rdi+80]
    call ReleaseSRWLockExclusive
loader_bind_done:
    mov eax,ebx
    add rsp,72
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_class_loader_bind ENDP

; LNRP32/1 registers the sole RegisterNatives member in OpenJDK ClassLoader.c.
; Other ClassLoader JNI exports do not belong to this registration table.
; retrieveDirectives remains an explicit UnsatisfiedLinkError until implemented.
; register(Context32,pool)->void. Publication is idempotent and atomic.
boom_class_loader_register PROC
    test rcx,rcx
    jz loader_register_zero
    cmp DWORD PTR [rcx],0
    jne loader_register_zero
    test rdx,rdx
    jz loader_register_bad
    cmp DWORD PTR [rdx],050524E4Ch
    jne loader_register_bad
    cmp DWORD PTR [rdx+4],1
    jne loader_register_bad
    cmp DWORD PTR [rdx+12],1
    jne loader_register_bad
    cmp QWORD PTR [rdx+24],0
    jne loader_register_bad
    lea rax,boom_class_loader_retrieve
    cmp QWORD PTR [rdx+16],rax
    jne loader_register_bad
    mov eax,DWORD PTR [rdx+8]
    test eax,eax
    jz loader_register_publish
    cmp eax,2
    jne loader_register_bad
loader_register_publish:
    mov eax,2
    xchg DWORD PTR [rdx+8],eax
loader_register_zero:
    xor eax,eax
    ret
loader_register_bad:
    mov DWORD PTR [rcx],7
    jmp loader_register_zero
boom_class_loader_register ENDP

; This target is deliberately incomplete, not a fabricated assertion policy.
boom_class_loader_retrieve PROC
    test rcx,rcx
    jz loader_retrieve_zero
    cmp DWORD PTR [rcx],0
    jne loader_retrieve_zero
    mov DWORD PTR [rcx],20
loader_retrieve_zero:
    xor eax,eax
    ret
boom_class_loader_retrieve ENDP
END
