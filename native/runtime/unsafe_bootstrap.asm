; Partial source-verified Unsafe natives. Payload-relative array offsets;
; typed int[]/long[] operations, the VM ThreadIdentifiers counter and static cells.
option casemap:none
EXTERN boom_mirror_typeid:PROC
EXTERN boom_threads_id_address:PROC
EXTERN GetNativeSystemInfo:PROC
PUBLIC boom_unsafe_native
PUBLIC boom_unsafe_constants_fill
.code
; Pool96 UNSF/1/state/count5, layout16,map24,mirrors32,heapCell40,
; scales48,typeCount56,constantCells64,optionalThreadRegistryCell72,reserved80/88.
unsafe_pool_valid PROC
    test rcx,rcx
    jz unsafe_pool_bad
    cmp DWORD PTR [rcx],0554E5346h
    jne unsafe_pool_bad
    cmp DWORD PTR [rcx+4],3
    je unsafe_pool_instances
    cmp DWORD PTR [rcx+4],2
    je unsafe_pool_extended
    cmp DWORD PTR [rcx+4],1
    jne unsafe_pool_bad
    cmp DWORD PTR [rcx+12],5
    jne unsafe_pool_bad
    cmp QWORD PTR [rcx+80],0
    jne unsafe_pool_bad
    cmp QWORD PTR [rcx+88],0
    jne unsafe_pool_bad
    jmp unsafe_pool_base
unsafe_pool_instances:
    cmp DWORD PTR [rcx+12],13
    jne unsafe_pool_bad
    cmp QWORD PTR [rcx+80],0
    je unsafe_pool_no_instance_fields
    cmp QWORD PTR [rcx+88],0
    je unsafe_pool_bad
    cmp QWORD PTR [rcx+96],0
    je unsafe_pool_bad
    cmp QWORD PTR [rcx+104],0
    je unsafe_pool_bad
    jmp unsafe_pool_base
unsafe_pool_no_instance_fields:
    cmp QWORD PTR [rcx+104],0
    jne unsafe_pool_bad
    jmp unsafe_pool_no_fields
unsafe_pool_extended:
    mov eax,DWORD PTR [rcx+12]
    sub eax,9
    cmp eax,1
    ja unsafe_pool_bad
    cmp QWORD PTR [rcx+104],0
    jne unsafe_pool_bad
    cmp QWORD PTR [rcx+80],0
    je unsafe_pool_no_fields
    cmp QWORD PTR [rcx+88],0
    je unsafe_pool_bad
    cmp QWORD PTR [rcx+96],0
    je unsafe_pool_bad
    jmp unsafe_pool_base
unsafe_pool_no_fields:
    cmp QWORD PTR [rcx+88],0
    jne unsafe_pool_bad
    cmp QWORD PTR [rcx+96],0
    jne unsafe_pool_bad
unsafe_pool_base:
    mov r10d,16
unsafe_pool_pointers:
    cmp QWORD PTR [rcx+r10],0
    je unsafe_pool_bad
    add r10d,8
    cmp r10d,72
    jb unsafe_pool_pointers
    cmp QWORD PTR [rcx+56],16384
    ja unsafe_pool_bad
    mov eax,1
    ret
unsafe_pool_bad:
    xor eax,eax
    ret
unsafe_pool_valid ENDP

; (heap,oop)->boolean. Typed live VM references, complete owned block required.
unsafe_owned PROC
    test rcx,rcx
    jz unsafe_owned_bad
    cmp DWORD PTR [rcx],048454150h
    jne unsafe_owned_bad
    cmp DWORD PTR [rcx+4],1
    jne unsafe_owned_bad
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz unsafe_owned_bad
    cmp rax,040000000h
    ja unsafe_owned_bad
    lea r10,[rcx+128]
    add rax,r10
    jc unsafe_owned_bad
    cmp rax,QWORD PTR [rcx+24]
    jne unsafe_owned_bad
    lea r10,[rcx+160]
    cmp rdx,r10
    jb unsafe_owned_bad
    cmp rdx,rax
    ja unsafe_owned_bad
    test dl,15
    jnz unsafe_owned_bad
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,0B00B0001h
    jne unsafe_owned_bad
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb unsafe_owned_bad
    test r10b,15
    jnz unsafe_owned_bad
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja unsafe_owned_bad
    add r10,rdx
    jc unsafe_owned_bad
    cmp r10,rax
    ja unsafe_owned_bad
    mov eax,1
    ret
unsafe_owned_bad:
    xor eax,eax
    ret
unsafe_owned ENDP

; (context,argv,pool,op)->value. argv includes the actual Unsafe receiver.
boom_unsafe_native PROC FRAME
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
    mov r12d,r9d
    test rbx,rbx
    jz unsafe_error
    cmp DWORD PTR [rbx],0
    jne unsafe_error
    mov rcx,rdi
    call unsafe_pool_valid
    test eax,eax
    jz unsafe_bad
    cmp r12d,DWORD PTR [rdi+12]
    jae unsafe_bad
    cmp r12d,12
    ja unsafe_bad
    test r12d,r12d
    jz unsafe_register
    cmp DWORD PTR [rdi+8],2
    jne unsafe_bad
    test rsi,rsi
    jz unsafe_bad
    mov rdx,QWORD PTR [rsi]
    test rdx,rdx
    jz unsafe_null
    mov rcx,QWORD PTR [rdi+40]
    mov rcx,QWORD PTR [rcx]
    call unsafe_owned
    test eax,eax
    jz unsafe_bad
    mov rax,QWORD PTR [rdi+16]
    cmp QWORD PTR [rdx-8],rax
    jne unsafe_bad
    cmp QWORD PTR [rdx-16],0
    jne unsafe_bad
    cmp DWORD PTR [rdx-20],0
    jne unsafe_bad
    cmp r12d,9
    je unsafe_full_fence
    cmp r12d,10
    je unsafe_object_descriptor
    cmp r12d,11
    jae unsafe_memory
    cmp r12d,7
    jae unsafe_static_descriptor
    cmp r12d,2
    ja unsafe_memory
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi+8]
    mov r8,QWORD PTR [rdi+32]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne unsafe_error
    cmp rax,QWORD PTR [rdi+56]
    jae unsafe_bad
    mov r10,QWORD PTR [rdi+48]
    mov eax,DWORD PTR [r10+rax*4]
    test eax,eax
    jz unsafe_argument
    cmp r12d,1
    jne unsafe_done
    xor eax,eax
    jmp unsafe_done
unsafe_register:
    xor eax,eax
    mov edx,2
    lock cmpxchg DWORD PTR [rdi+8],edx
    test eax,eax
    jz unsafe_error
    cmp eax,2
    jne unsafe_bad
    jmp unsafe_error
unsafe_full_fence:
    mfence
    xor eax,eax
    jmp unsafe_done
unsafe_memory:
    mov eax,8
    cmp r12d,5
    jb unsafe_width_ready
    mov eax,4
    cmp r12d,11
    jb unsafe_width_ready
    mov eax,1
unsafe_width_ready:
    mov DWORD PTR [rsp+32],eax
    mov rax,QWORD PTR [rsi+16]
    shr rax,32
    cmp eax,0424F4F4Dh
    je unsafe_static_cell
    cmp eax,0424F4F49h
    je unsafe_instance_cell
    mov rdx,QWORD PTR [rsi+8]
    test rdx,rdx
    jz unsafe_counter
    mov rcx,QWORD PTR [rdi+40]
    mov rcx,QWORD PTR [rcx]
    call unsafe_owned
    test eax,eax
    jz unsafe_bad
    mov eax,267
    cmp DWORD PTR [rsp+32],1
    jne unsafe_array_wide_tag
    mov eax,260
    cmp r12d,12
    jne unsafe_array_tag_ready
    cmp QWORD PTR [rdx-8],264
    jne unsafe_array_tag_ready
    mov eax,264
    jmp unsafe_array_tag_ready
unsafe_array_wide_tag:
    cmp DWORD PTR [rsp+32],8
    je unsafe_array_tag_ready
    dec eax
unsafe_array_tag_ready:
    cmp QWORD PTR [rdx-8],rax
    jne unsafe_unsupported
    cmp DWORD PTR [rdx-20],0
    jne unsafe_bad
    mov rax,QWORD PTR [rdx-16]
    mov r8d,DWORD PTR [rsp+32]
    mov ecx,r8d
    dec ecx
    test eax,ecx
    jnz unsafe_bad
    cmp rax,r8
    jb unsafe_argument
    sub rax,r8
    mov rcx,QWORD PTR [rsi+16]
    dec r8d
    test ecx,r8d
    jnz unsafe_argument
    cmp rcx,rax
    ja unsafe_argument
    add rdx,rcx
    jmp unsafe_memory_address
unsafe_counter:
    cmp DWORD PTR [rsp+32],8
    jne unsafe_unsupported
    mov rcx,QWORD PTR [rdi+72]
    test rcx,rcx
    jz unsafe_unsupported
    mov rcx,QWORD PTR [rcx]
    call boom_threads_id_address
    test rax,rax
    jz unsafe_bad
    cmp rax,QWORD PTR [rsi+16]
    jne unsafe_unsupported
    mov rdx,rax
unsafe_memory_address:
    cmp r12d,11
    je unsafe_read_boolean
    cmp r12d,12
    je unsafe_exchange_byte
    cmp r12d,3
    je unsafe_read_long
    cmp r12d,5
    je unsafe_read_int
    cmp r12d,6
    je unsafe_cas_int
    jmp unsafe_cas
unsafe_read_long:
    mov rax,QWORD PTR [rdx]
    jmp unsafe_done
unsafe_read_int:
    movsxd rax,DWORD PTR [rdx]
    jmp unsafe_done
unsafe_read_boolean:
    movzx eax,BYTE PTR [rdx]
    jmp unsafe_done
unsafe_exchange_byte:
    mov eax,DWORD PTR [rsi+24]
    mov ecx,DWORD PTR [rsi+32]
    lock cmpxchg BYTE PTR [rdx],cl
    movsx rax,al
    jmp unsafe_done
unsafe_cas_int:
    mov eax,DWORD PTR [rsi+24]
    mov ecx,DWORD PTR [rsi+32]
    lock cmpxchg DWORD PTR [rdx],ecx
    sete al
    movzx eax,al
    jmp unsafe_done
unsafe_cas:
    mov rax,QWORD PTR [rsi+24]
    mov rcx,QWORD PTR [rsi+32]
    lock cmpxchg QWORD PTR [rdx],rcx
    sete al
    movzx eax,al
    jmp unsafe_done
unsafe_static_cell:
    cmp DWORD PTR [rdi+4],2
    jb unsafe_unsupported
    mov r9,QWORD PTR [rdi+80]
    test r9,r9
    jz unsafe_unsupported
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi+8]
    mov r8,QWORD PTR [rsi+16]
    call QWORD PTR [rdi+88]
    jmp unsafe_field_cell_ready
unsafe_instance_cell:
    cmp DWORD PTR [rdi+4],3
    jb unsafe_unsupported
    mov r9,QWORD PTR [rdi+80]
    test r9,r9
    jz unsafe_unsupported
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi+8]
    mov r8,QWORD PTR [rsi+16]
    call QWORD PTR [rdi+104]
unsafe_field_cell_ready:
    cmp DWORD PTR [rbx],0
    jne unsafe_error
    test rax,rax
    jz unsafe_bad
    cmp edx,DWORD PTR [rsp+32]
    jne unsafe_argument
    cmp edx,1
    jne unsafe_field_cell_valid
    cmp r12d,11
    jne unsafe_field_byte_code
    test r8d,r8d
    jnz unsafe_unsupported
    jmp unsafe_field_cell_valid
unsafe_field_byte_code:
    cmp r8d,1
    ja unsafe_unsupported
unsafe_field_cell_valid:
    mov rdx,rax
    jmp unsafe_memory_address
unsafe_static_descriptor:
    cmp DWORD PTR [rdi+4],2
    jb unsafe_unsupported
    mov r8,QWORD PTR [rdi+80]
    test r8,r8
    jz unsafe_unsupported
    mov rcx,rbx
    mov rdx,rsi
    lea r9d,[r12d-2]
    call QWORD PTR [rdi+96]
    jmp unsafe_done
unsafe_object_descriptor:
    cmp DWORD PTR [rdi+4],3
    jb unsafe_unsupported
    mov r8,QWORD PTR [rdi+80]
    test r8,r8
    jz unsafe_unsupported
    mov rcx,rbx
    mov rdx,rsi
    mov r9d,13
    call QWORD PTR [rdi+96]
    jmp unsafe_done
unsafe_null:
    mov DWORD PTR [rbx],4
    jmp unsafe_error
unsafe_argument:
    mov DWORD PTR [rbx],18
    jmp unsafe_error
unsafe_unsupported:
    mov DWORD PTR [rbx],20
    jmp unsafe_error
unsafe_bad:
    mov DWORD PTR [rbx],7
unsafe_error:
    xor eax,eax
unsafe_done:
    add rsp,40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_unsafe_native ENDP

; Called after the ORIGINAL UnsafeConstants Java initializer and before its
; class state is published initialized. No cache writeback capability exported.
boom_unsafe_constants_fill PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,88
    .allocstack 88
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    cmp DWORD PTR [rbx],0
    jne unsafe_constants_done
    mov rcx,rdx
    call unsafe_pool_valid
    test eax,eax
    jz unsafe_constants_bad
    lea rcx,[rsp+32]
    call GetNativeSystemInfo
    mov edx,DWORD PTR [rsp+36]
    test edx,edx
    jz unsafe_constants_bad
    lea eax,[rdx-1]
    test eax,edx
    jnz unsafe_constants_bad
    mov r10,QWORD PTR [rsi+64]
    mov rax,QWORD PTR [r10]
    mov QWORD PTR [rax],8
    mov rax,QWORD PTR [r10+8]
    mov QWORD PTR [rax],rdx
    mov rax,QWORD PTR [r10+16]
    mov QWORD PTR [rax],0
    mov rax,QWORD PTR [r10+24]
    mov QWORD PTR [rax],1
    mov rax,QWORD PTR [r10+32]
    mov QWORD PTR [rax],0
    jmp unsafe_constants_done
unsafe_constants_bad:
    mov DWORD PTR [rbx],7
unsafe_constants_done:
    xor eax,eax
    add rsp,88
    pop rsi
    pop rbx
    ret
boom_unsafe_constants_fill ENDP
END
