; VM-created real Throwable objects, Context32 materialization and failure causes.
; Java constructors still execute Java source. These factories create VM exceptions
; directly in verified original bootstrap layouts and use real Java sentinels.
; VM160 offsets are specified by compiler/unwind.rs. No Context16 caller is valid.
option casemap:none
EXTERN GetCurrentThreadId:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
EXTERN boom_object_new:PROC
EXTERN boom_object_check:PROC
EXTERN boom_throwable_fill:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_string_load:PROC
EXTERN boom_class_ensure32:PROC
PUBLIC boom_exception_prepare
PUBLIC boom_exception_materialize
PUBLIC boom_exception_init_failure
PUBLIC boom_exception_class_failed
PUBLIC boom_exception_npe_message
PUBLIC boom_exception_create
.code
; VM factory(ctx,kind,cause,flags)->Throwable. Does not publish it as pending.
boom_exception_create PROC
    jmp exception_vm_new
boom_exception_create ENDP
exception_vm_row PROC
    test rcx,rcx
    jz exception_vm_row_bad
    cmp DWORD PTR [rcx],04558564Dh
    jne exception_vm_row_bad
    cmp DWORD PTR [rcx+4],1
    jne exception_vm_row_bad
    mov r8d,DWORD PTR [rcx+64]
    test r8d,r8d
    jz exception_vm_row_bad
    cmp r8d,64
    ja exception_vm_row_bad
    mov rax,QWORD PTR [rcx+56]
    test rax,rax
    jz exception_vm_row_bad
exception_vm_row_loop:
    cmp DWORD PTR [rax],edx
    je exception_vm_row_done
    add rax,80
    dec r8d
    jnz exception_vm_row_loop
exception_vm_row_bad:
    xor eax,eax
exception_vm_row_done:
    ret
exception_vm_row ENDP

; diagnostic(vm,method,bci)->literal ID or -1. Compiler-owned immutable table.
exception_vm_diagnostic PROC
    mov r9d,DWORD PTR [rcx+136]
    cmp r9d,1048576
    ja exception_vm_diagnostic_none
    mov rcx,QWORD PTR [rcx+112]
    test rcx,rcx
    jz exception_vm_diagnostic_none
exception_vm_diagnostic_loop:
    test r9d,r9d
    jz exception_vm_diagnostic_none
    cmp DWORD PTR [rcx],edx
    jne exception_vm_diagnostic_next
    cmp DWORD PTR [rcx+4],r8d
    jne exception_vm_diagnostic_next
    mov eax,DWORD PTR [rcx+8]
    ret
exception_vm_diagnostic_next:
    add rcx,16
    dec r9d
    jmp exception_vm_diagnostic_loop
exception_vm_diagnostic_none:
    mov eax,-1
    ret
exception_vm_diagnostic ENDP

; new(ctx,kind,cause,flags), flag1=emergency, flag2=explicit null cause.
exception_vm_new PROC FRAME
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
    sub rsp,72
    .allocstack 72
    .endprolog
    mov rbx,rcx
    mov r12,r8
    mov r13d,r9d
    mov rdi,QWORD PTR [rbx+24]
    mov rcx,rdi
    call exception_vm_row
    test rax,rax
    jz exception_vm_new_bad
    mov rsi,rax
    test r13d,1
    jnz exception_vm_new_allocate
    mov rcx,QWORD PTR [rsi+16]
    mov rdx,rbx
    call boom_class_ensure32
    test eax,eax
    jnz exception_vm_new_error
exception_vm_new_allocate:
    mov rcx,QWORD PTR [rdi+16]
    test rcx,rcx
    jz exception_vm_new_bad
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rsi+8]
    mov r8,rbx
    call boom_object_new
    test rax,rax
    jz exception_vm_new_error
    mov r14,rax
    mov edx,DWORD PTR [rsi+48]
    mov rax,r12
    test rax,rax
    jnz exception_vm_new_cause
    test r13d,2
    jnz exception_vm_new_cause
    mov rax,r14
exception_vm_new_cause:
    mov QWORD PTR [r14+rdx],rax
    mov rax,QWORD PTR [rdi+80]
    mov rax,QWORD PTR [rax]
    mov edx,DWORD PTR [rsi+56]
    mov QWORD PTR [r14+rdx],rax
    test r13d,1
    jnz exception_vm_new_success
    mov QWORD PTR [rsp+32],r14
    mov QWORD PTR [rsp+40],0
    mov rcx,rbx
    lea rdx,[rsp+32]
    mov r8,QWORD PTR [rdi+24]
    call boom_throwable_fill
    cmp DWORD PTR [rbx],0
    jne exception_vm_new_error
    mov rax,QWORD PTR [rdi+88]
    mov rax,QWORD PTR [rax]
    mov edx,DWORD PTR [rsi+52]
    mov QWORD PTR [r14+rdx],rax
    mov r8d,DWORD PTR [rsi+68]
    cmp DWORD PTR [rsi],4
    jne exception_vm_new_message
    mov rcx,rdi
    mov edx,DWORD PTR [rbx+8]
    mov r8d,DWORD PTR [rbx+4]
    call exception_vm_diagnostic
    mov r8d,eax
exception_vm_new_message:
    cmp r8d,-1
    je exception_vm_new_npe_state
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rdi+120]
    mov r9,rbx
    call boom_string_load
    cmp DWORD PTR [rbx],0
    jne exception_vm_new_error
    cmp DWORD PTR [rsi],4
    je exception_vm_new_npe_message
    mov edx,DWORD PTR [rsi+44]
    mov QWORD PTR [r14+rdx],rax
    jmp exception_vm_new_npe_state
exception_vm_new_npe_message:
    mov edx,DWORD PTR [rsi+64]
    cmp edx,-1
    je exception_vm_new_bad
    mov QWORD PTR [r14+rdx],rax
exception_vm_new_npe_state:
    mov edx,DWORD PTR [rsi+60]
    cmp edx,-1
    je exception_vm_new_success
    mov DWORD PTR [r14+rdx],2
exception_vm_new_success:
    mov rax,r14
    jmp exception_vm_new_done
exception_vm_new_bad:
    mov DWORD PTR [rbx],7
exception_vm_new_error:
    xor eax,eax
exception_vm_new_done:
    add rsp,72
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
exception_vm_new ENDP

boom_exception_prepare PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    cmp DWORD PTR [rbx],0
    jne exception_prepare_error
    cmp QWORD PTR [rbx+24],rsi
    jne exception_prepare_bad
    cmp DWORD PTR [rsi],04558564Dh
    jne exception_prepare_bad
    cmp DWORD PTR [rsi+4],1
    jne exception_prepare_bad
    cmp DWORD PTR [rsi+8],2
    je exception_prepare_success
    call GetCurrentThreadId
    mov edi,eax
exception_prepare_state:
    mov eax,DWORD PTR [rsi+8]
    cmp eax,2
    je exception_prepare_success
    cmp eax,3
    je exception_prepare_oom
    cmp eax,1
    je exception_prepare_wait
    test eax,eax
    jnz exception_prepare_bad
    mov edx,1
    lock cmpxchg DWORD PTR [rsi+8],edx
    jne exception_prepare_state
    mov DWORD PTR [rsi+12],edi
    mov rcx,rbx
    lea rdx,[rsp+40]
    call QWORD PTR [rsi+72]
    cmp DWORD PTR [rbx],0
    jne exception_prepare_failed
    mov rcx,rbx
    mov edx,3
    xor r8d,r8d
    mov r9d,1
    call exception_vm_new
    test rax,rax
    jz exception_prepare_failed
    mov r10,QWORD PTR [rsi+96]
    mov QWORD PTR [r10],rax
    mov rcx,rbx
    mov edx,10
    xor r8d,r8d
    mov r9d,1
    call exception_vm_new
    test rax,rax
    jz exception_prepare_failed
    mov r10,QWORD PTR [rsi+104]
    mov QWORD PTR [r10],rax
    mov DWORD PTR [rsi+12],0
    mov DWORD PTR [rsi+8],2
    lea rcx,[rsi+8]
    call WakeByAddressAll
exception_prepare_success:
    xor eax,eax
    jmp exception_prepare_done
exception_prepare_wait:
    cmp DWORD PTR [rsi+12],edi
    je exception_prepare_success
    mov DWORD PTR [rsp+32],1
    lea rcx,[rsi+8]
    lea rdx,[rsp+32]
    mov r8d,4
    mov r9d,-1
    call WaitOnAddress
    jmp exception_prepare_state
exception_prepare_failed:
    mov DWORD PTR [rsi+12],0
    mov DWORD PTR [rsi+8],3
    lea rcx,[rsi+8]
    call WakeByAddressAll
    jmp exception_prepare_error
exception_prepare_oom:
    mov DWORD PTR [rbx],3
    jmp exception_prepare_error
exception_prepare_bad:
    mov DWORD PTR [rbx],7
exception_prepare_error:
    mov eax,1
exception_prepare_done:
    add rsp,48
    pop rdi
    pop rsi
    pop rbx
    ret
boom_exception_prepare ENDP

boom_exception_materialize PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    test rbx,rbx
    jz exception_materialize_error
    mov eax,DWORD PTR [rbx]
    test eax,eax
    jz exception_materialized
    cmp eax,16
    je exception_materialized
    mov rsi,QWORD PTR [rbx+24]
    ; A source batch can propagate the pending kind before a normal Throwable
    ; factory is bound. Preserve that error; never dereference an absent pool
    ; or interpret another Context32 extension as the legacy VM160 contract.
    test rsi,rsi
    jz exception_materialize_error
    cmp DWORD PTR [rsi],04558564Dh
    jne exception_materialize_error
    cmp DWORD PTR [rsi+4],1
    jne exception_materialize_error
    cmp DWORD PTR [rsi+8],2
    jne exception_materialize_error
    mov edx,eax
    mov DWORD PTR [rbx],0
    mov QWORD PTR [rbx+16],0
    cmp edx,3
    je exception_materialize_oom
    cmp edx,10
    je exception_materialize_stack
    xor r8d,r8d
    xor r9d,r9d
    call exception_vm_new
    test rax,rax
    jnz exception_materialize_publish
    cmp DWORD PTR [rbx],16
    je exception_materialized
    jmp exception_materialize_oom
exception_materialize_stack:
    mov rax,QWORD PTR [rsi+104]
    mov rax,QWORD PTR [rax]
    jmp exception_materialize_publish
exception_materialize_oom:
    mov rax,QWORD PTR [rsi+96]
    mov rax,QWORD PTR [rax]
exception_materialize_publish:
    test rax,rax
    jz exception_materialize_error
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
exception_materialized:
    xor eax,eax
    jmp exception_materialize_done
exception_materialize_error:
    mov eax,1
exception_materialize_done:
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_exception_materialize ENDP

boom_exception_init_failure PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,56
    .allocstack 56
    .endprolog
    mov rbx,rcx
    call boom_exception_materialize
    cmp DWORD PTR [rbx],16
    jne exception_init_failure_done
    mov rsi,QWORD PTR [rbx+24]
    mov QWORD PTR [rsp+32],0
    mov QWORD PTR [rsp+40],0
    mov rcx,QWORD PTR [rbx+16]
    mov rdx,QWORD PTR [rsi+32]
    lea r8,[rsp+32]
    call boom_runtime_type
    test rax,rax
    jz exception_init_failure_oom
    mov rcx,rax
    mov rdx,QWORD PTR [rsi+48]
    call boom_type_assignable
    test eax,eax
    jnz exception_init_failure_done
    mov r8,QWORD PTR [rbx+16]
    mov DWORD PTR [rbx],0
    mov QWORD PTR [rbx+16],0
    mov rcx,rbx
    mov edx,8
    xor r9d,r9d
    call exception_vm_new
    test rax,rax
    jz exception_init_failure_oom
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp exception_init_failure_done
exception_init_failure_oom:
    mov DWORD PTR [rbx],3
    mov rcx,rbx
    call boom_exception_materialize
exception_init_failure_done:
    add rsp,56
    pop rsi
    pop rbx
    ret
boom_exception_init_failure ENDP

boom_exception_class_failed PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    test rbx,rbx
    jz exception_class_failed_done
    mov rax,QWORD PTR [rbx+24]
    test rax,rax
    jz exception_class_failed_raw
    cmp DWORD PTR [rax],04558564Dh
    jne exception_class_failed_raw
    cmp DWORD PTR [rax+4],1
    jne exception_class_failed_raw
    cmp DWORD PTR [rax+8],2
    jne exception_class_failed_raw
    mov r8,QWORD PTR [rdx+56]
    mov r8,QWORD PTR [r8]
    mov edx,9
    xor r9d,r9d
    call exception_vm_new
    test rax,rax
    jz exception_class_failed_oom
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp exception_class_failed_done
exception_class_failed_raw:
    mov DWORD PTR [rbx],9
    jmp exception_class_failed_done
exception_class_failed_oom:
    mov DWORD PTR [rbx],3
    mov rcx,rbx
    call boom_exception_materialize
exception_class_failed_done:
    add rsp,32
    pop rbx
    ret
boom_exception_class_failed ENDP

; getExtendedNPEMessage(ctx,receiver,VMplan): source backtrace -> lazy diagnostic.
boom_exception_npe_message PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    test rsi,rsi
    jz exception_npe_null
    mov rax,QWORD PTR [rdi+24]
    mov ecx,DWORD PTR [rax+8]
    mov rax,QWORD PTR [rax+16]
    mov rdx,QWORD PTR [rsi-8]
exception_npe_row:
    test ecx,ecx
    jz exception_npe_bad
    cmp QWORD PTR [rax],rdx
    je exception_npe_receiver
    add rax,48
    dec ecx
    jmp exception_npe_row
exception_npe_receiver:
    mov QWORD PTR [rsp+32],rax
    mov rcx,rsi
    mov rdx,QWORD PTR [rax]
    mov r8,rbx
    call boom_object_check
    cmp DWORD PTR [rbx],0
    jne exception_npe_none
    mov rax,QWORD PTR [rsp+32]
    mov eax,DWORD PTR [rax+8]
    mov rsi,QWORD PTR [rsi+rax]
    test rsi,rsi
    jz exception_npe_none
    cmp QWORD PTR [rsi-8],267
    jne exception_npe_bad
    cmp QWORD PTR [rsi-16],24
    jb exception_npe_none
    mov rax,0000000142545243h
    cmp QWORD PTR [rsi],rax
    jne exception_npe_bad
    mov rax,QWORD PTR [rdi+128]
    cmp QWORD PTR [rsi+8],rax
    jne exception_npe_bad
    mov rax,QWORD PTR [rsi+16]
    mov r8d,eax
    shr rax,32
    mov edx,eax
    mov rcx,rdi
    call exception_vm_diagnostic
    cmp eax,-1
    je exception_npe_none
    mov r8d,eax
    mov rcx,QWORD PTR [rdi+16]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rdi+120]
    mov r9,rbx
    call boom_string_load
    jmp exception_npe_done
exception_npe_null:
    mov DWORD PTR [rbx],4
    jmp exception_npe_none
exception_npe_bad:
    mov DWORD PTR [rbx],7
exception_npe_none:
    xor eax,eax
exception_npe_done:
    add rsp,48
    pop rdi
    pop rsi
    pop rbx
    ret
boom_exception_npe_message ENDP
END
