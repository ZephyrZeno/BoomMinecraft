; Physical java.lang.Module services. Module pool ABI3/144 keeps ABI2 offsets
; through heapCell88; loaderPool96,loaderKeys104; name112,loader116,layer120,
; ClassLoader.unnamedModule124,descriptor128,flags132=0,reserved136=0.
; Canonical identity is the rooted object, never a Java field/payload overlay.
option casemap:none
EXTERN boom_object_new:PROC
EXTERN boom_string_load:PROC
EXTERN boom_mirror_typeid:PROC
EXTERN boom_layer_intrinsic:PROC
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockShared:PROC
EXTERN GetCurrentThreadId:PROC
PUBLIC boom_module_objects_pool_valid
PUBLIC boom_module_objects_index
PUBLIC boom_module_objects_load
PUBLIC boom_module_objects_intrinsic
PUBLIC boom_module_objects_value
.code
; pool RDX -> boolean. Preserve RCX/RDX/R8/R9, clobber RAX/R10/R11.
boom_module_objects_pool_valid PROC
    test rdx,rdx
    jz module_obj_pool_no
    cmp DWORD PTR [rdx],04D4F4455h
    jne module_obj_pool_no
    cmp DWORD PTR [rdx+4],3
    jne module_obj_pool_no
    cmp DWORD PTR [rdx+68],0
    jne module_obj_pool_no
    cmp DWORD PTR [rdx+132],0
    jne module_obj_pool_no
    cmp QWORD PTR [rdx+136],0
    jne module_obj_pool_no
    mov eax,DWORD PTR [rdx+12]
    dec eax
    cmp eax,1023
    ja module_obj_pool_no
    mov eax,DWORD PTR [rdx+64]
    dec eax
    cmp eax,16383
    ja module_obj_pool_no
    mov r10d,16
module_obj_pool_ptrs:
    cmp QWORD PTR [rdx+r10],0
    je module_obj_pool_no
    add r10d,8
    cmp r10d,48
    jb module_obj_pool_ptrs
    cmp QWORD PTR [rdx+56],0
    je module_obj_pool_no
    cmp QWORD PTR [rdx+72],0
    je module_obj_pool_no
    cmp QWORD PTR [rdx+88],0
    je module_obj_pool_no
    cmp QWORD PTR [rdx+104],0
    je module_obj_pool_no
    mov r10,QWORD PTR [rdx+32]
    cmp DWORD PTR [r10],04F424A43h
    jne module_obj_pool_no
    cmp DWORD PTR [r10+4],2
    jne module_obj_pool_no
    mov eax,DWORD PTR [r10+16]
    test eax,eax
    jz module_obj_pool_no
    cmp eax,DWORD PTR [r10+20]
    ja module_obj_pool_no
    cmp eax,4096
    ja module_obj_pool_no
    shl rax,3
    cmp rax,QWORD PTR [r10+8]
    ja module_obj_pool_no
    mov r11d,112
module_obj_pool_offsets:
    mov r10d,DWORD PTR [rdx+r11]
    test r10b,7
    jnz module_obj_pool_no
    cmp r10,rax
    jae module_obj_pool_no
    add r11d,4
    cmp r11d,124
    jb module_obj_pool_offsets
    mov r10d,DWORD PTR [rdx+128]
    test r10b,7
    jnz module_obj_pool_no
    cmp r10,rax
    jae module_obj_pool_no
    test DWORD PTR [rdx+124],7
    jnz module_obj_pool_no
    mov r10,QWORD PTR [rdx+96]
    test r10,r10
    jz module_obj_pool_no
    cmp DWORD PTR [r10],05052444Ch
    jne module_obj_pool_no
    cmp DWORD PTR [r10+4],1
    jne module_obj_pool_no
    mov r11,QWORD PTR [rdx+88]
    cmp QWORD PTR [r10+8],r11
    jne module_obj_pool_no
    mov r11,QWORD PTR [rdx+56]
    cmp QWORD PTR [r10+16],r11
    jne module_obj_pool_no
    mov eax,DWORD PTR [rdx+64]
    cmp DWORD PTR [r10+60],eax
    jne module_obj_pool_no
    cmp DWORD PTR [r11],04D495252h
    jne module_obj_pool_no
    cmp DWORD PTR [r11+12],eax
    jne module_obj_pool_no
    mov eax,DWORD PTR [r10+56]
    dec eax
    cmp eax,16383
    ja module_obj_pool_no
    mov r10,QWORD PTR [rdx+80]
    test r10,r10
    jz module_obj_pool_yes
    cmp DWORD PTR [r10],04C415952h
    jne module_obj_pool_no
    cmp DWORD PTR [r10+4],1
    jne module_obj_pool_no
    cmp DWORD PTR [r10+12],2
    jne module_obj_pool_no
    cmp QWORD PTR [r10+32],rdx
    jne module_obj_pool_no
    mov r11,QWORD PTR [rdx+88]
    cmp QWORD PTR [r10+40],r11
    jne module_obj_pool_no
module_obj_pool_yes:
    mov eax,1
    ret
module_obj_pool_no:
    xor eax,eax
    ret
boom_module_objects_pool_valid ENDP

; (heap,oop)->complete live ownership, no object/tag reads before bounds checks.
module_obj_owned PROC
    test rcx,rcx
    jz module_obj_owned_no
    cmp DWORD PTR [rcx],048454150h
    jne module_obj_owned_no
    cmp DWORD PTR [rcx+4],1
    jne module_obj_owned_no
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz module_obj_owned_no
    cmp rax,040000000h
    ja module_obj_owned_no
    lea r10,[rcx+128]
    add rax,r10
    jc module_obj_owned_no
    cmp rax,QWORD PTR [rcx+24]
    jne module_obj_owned_no
    lea r10,[rcx+160]
    cmp rdx,r10
    jb module_obj_owned_no
    cmp rdx,rax
    ja module_obj_owned_no
    test dl,15
    jnz module_obj_owned_no
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,0B00B0001h
    jne module_obj_owned_no
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb module_obj_owned_no
    test r10b,15
    jnz module_obj_owned_no
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja module_obj_owned_no
    add r10,rdx
    jc module_obj_owned_no
    cmp r10,rax
    ja module_obj_owned_no
    mov eax,1
    ret
module_obj_owned_no:
    xor eax,eax
    ret
module_obj_owned ENDP

; (oop,pool,Context32)->same physical Module or NULL/error.
boom_module_objects_value PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rsi,rcx
    mov rdi,rdx
    mov rbx,r8
    cmp DWORD PTR [rbx],0
    jne module_obj_value_zero
    call boom_module_objects_pool_valid
    test eax,eax
    jz module_obj_value_bad
    test rsi,rsi
    jz module_obj_value_null
    mov rax,QWORD PTR [rdi+88]
    mov rcx,QWORD PTR [rax]
    cmp QWORD PTR [rdi+48],0
    je module_obj_value_owned
    cmp QWORD PTR [rdi+48],rcx
    jne module_obj_value_bad
module_obj_value_owned:
    mov rdx,rsi
    call module_obj_owned
    test eax,eax
    jz module_obj_value_bad
    mov rax,QWORD PTR [rdi+32]
    cmp QWORD PTR [rsi-8],rax
    jne module_obj_value_bad
    mov rcx,QWORD PTR [rax+8]
    cmp QWORD PTR [rsi-16],rcx
    jne module_obj_value_bad
    mov ecx,DWORD PTR [rax+16]
    cmp DWORD PTR [rsi-20],ecx
    jne module_obj_value_bad
    mov rax,rsi
    jmp module_obj_value_done
module_obj_value_null:
    mov DWORD PTR [rbx],4
    jmp module_obj_value_zero
module_obj_value_bad:
    mov DWORD PTR [rbx],7
module_obj_value_zero:
    xor eax,eax
module_obj_value_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_module_objects_value ENDP

; (Context32,Module,pool)->canonical index or -1/error.
boom_module_objects_index PROC FRAME
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
    cmp DWORD PTR [rbx],0
    jne module_obj_index_fail
    mov rdx,rdi
    call boom_module_objects_pool_valid
    test eax,eax
    jz module_obj_index_bad
    mov rcx,rsi
    mov rdx,rdi
    mov r8,rbx
    call boom_module_objects_value
    test rax,rax
    jz module_obj_index_fail
    mov r10,QWORD PTR [rdi+16]
    xor eax,eax
module_obj_index_loop:
    cmp eax,DWORD PTR [rdi+12]
    jae module_obj_index_bad
    cmp QWORD PTR [r10+rax*8],rsi
    je module_obj_index_done
    inc eax
    jmp module_obj_index_loop
module_obj_index_bad:
    mov DWORD PTR [rbx],7
module_obj_index_fail:
    mov rax,-1
module_obj_index_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_module_objects_index ENDP

; (Context32,pool,id)->canonical physical Module. No automatic GC.
boom_module_objects_load PROC FRAME
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
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    mov rdi,rdx
    mov r13d,r8d
    cmp DWORD PTR [rbx],0
    jne module_obj_load_zero
    call boom_module_objects_pool_valid
    test eax,eax
    jz module_obj_load_bad
    cmp r13d,DWORD PTR [rdi+12]
    jae module_obj_load_bad
    mov rax,QWORD PTR [rdi+88]
    mov r12,QWORD PTR [rax]
    test r12,r12
    jz module_obj_load_bad
    cmp DWORD PTR [r12],048454150h
    jne module_obj_load_bad
    cmp DWORD PTR [r12+4],1
    jne module_obj_load_bad
module_obj_load_lock:
    mov eax,1
    xchg DWORD PTR [rdi+8],eax
    test eax,eax
    jz module_obj_load_owned
    pause
    jmp module_obj_load_lock
module_obj_load_owned:
    cmp QWORD PTR [rdi+48],0
    je module_obj_load_bind_heap
    cmp QWORD PTR [rdi+48],r12
    jne module_obj_load_unlock_bad
module_obj_load_bind_heap:
    mov QWORD PTR [rdi+48],r12
    mov r15,QWORD PTR [rdi+96]
    mov rax,QWORD PTR [rdi+104]
    mov esi,DWORD PTR [rax+r13*4]
    cmp esi,DWORD PTR [r15+56]
    jae module_obj_load_unlock_bad
    lea rcx,[r15+80]
    call AcquireSRWLockShared
    mov rax,QWORD PTR [r15+40]
    cmp DWORD PTR [rax+rsi*4],1
    jne module_obj_load_loader_unbound
    mov rax,QWORD PTR [r15+32]
    mov r14,QWORD PTR [rax+rsi*8]
    lea rcx,[r15+80]
    call ReleaseSRWLockShared
    test esi,esi
    jz module_obj_load_loader_ready
    test r14,r14
    jz module_obj_load_unlock_bad
module_obj_load_loader_ready:
    mov rax,QWORD PTR [rdi+24]
    lea r15,[rax+r13*8]
    cmp DWORD PTR [r15+4],0
    je module_obj_load_unnamed
    cmp DWORD PTR [r15+4],1
    jne module_obj_load_unlock_bad
    cmp DWORD PTR [r15],-1
    je module_obj_load_unlock_bad
    mov rax,QWORD PTR [rdi+16]
    mov rsi,QWORD PTR [rax+r13*8]
    test rsi,rsi
    jnz module_obj_load_existing
    mov rcx,r12
    mov rdx,QWORD PTR [rdi+40]
    mov r8d,DWORD PTR [r15]
    mov r9,rbx
    call boom_string_load
    test rax,rax
    jz module_obj_load_unlock_zero
    mov QWORD PTR [rsp+32],rax
    mov rcx,r12
    mov rdx,QWORD PTR [rdi+32]
    mov r8,rbx
    call boom_object_new
    test rax,rax
    jz module_obj_load_unlock_zero
    mov rsi,rax
    mov ecx,DWORD PTR [rdi+112]
    mov rax,QWORD PTR [rsp+32]
    mov QWORD PTR [rsi+rcx],rax
    mov ecx,DWORD PTR [rdi+116]
    mov QWORD PTR [rsi+rcx],r14
    cmp QWORD PTR [rdi+80],0
    je module_obj_load_publish
    mov rcx,rbx
    xor edx,edx
    mov r8,rdi
    mov r9d,4
    call boom_layer_intrinsic
    test rax,rax
    jz module_obj_load_unlock_zero
    mov ecx,DWORD PTR [rdi+120]
    mov QWORD PTR [rsi+rcx],rax
    jmp module_obj_load_publish
module_obj_load_unnamed:
    cmp DWORD PTR [r15],-1
    jne module_obj_load_unlock_bad
    test r14,r14
    jnz module_obj_load_application_unnamed
    ; The bootstrap loader has no Java ClassLoader object. Its unnamed Module
    ; is created by original BootLoader Java code and published into this root.
    mov rax,QWORD PTR [rdi+16]
    mov rsi,QWORD PTR [rax+r13*8]
    test rsi,rsi
    jz module_obj_load_unlock_bad
    jmp module_obj_load_existing
module_obj_load_application_unnamed:
    mov ecx,DWORD PTR [r14-20]
    shl rcx,3
    mov eax,DWORD PTR [rdi+124]
    cmp rax,rcx
    jae module_obj_load_unlock_bad
    mov rsi,QWORD PTR [r14+rax]
    test rsi,rsi
    jz module_obj_load_unlock_bad
    mov rcx,rsi
    mov rdx,rdi
    mov r8,rbx
    call boom_module_objects_value
    test rax,rax
    jz module_obj_load_unlock_zero
    mov ecx,DWORD PTR [rdi+112]
    cmp QWORD PTR [rsi+rcx],0
    jne module_obj_load_unlock_bad
    mov ecx,DWORD PTR [rdi+116]
    cmp QWORD PTR [rsi+rcx],r14
    jne module_obj_load_unlock_bad
    mov rax,QWORD PTR [rdi+16]
    mov rax,QWORD PTR [rax+r13*8]
    test rax,rax
    jz module_obj_load_publish
    cmp rax,rsi
    jne module_obj_load_unlock_bad
    jmp module_obj_load_existing
module_obj_load_publish:
    mov rax,QWORD PTR [rdi+16]
    mov QWORD PTR [rax+r13*8],rsi
module_obj_load_existing:
    mov rcx,rsi
    mov rdx,rdi
    mov r8,rbx
    call boom_module_objects_value
    test rax,rax
    jz module_obj_load_unlock_zero
    mov ecx,DWORD PTR [rdi+116]
    cmp QWORD PTR [rsi+rcx],r14
    jne module_obj_load_unlock_bad
    mov rax,rsi
    mov DWORD PTR [rdi+8],0
    jmp module_obj_load_done
module_obj_load_loader_unbound:
    lea rcx,[r15+80]
    call ReleaseSRWLockShared
module_obj_load_unlock_bad:
    mov DWORD PTR [rbx],7
module_obj_load_unlock_zero:
    mov DWORD PTR [rdi+8],0
    jmp module_obj_load_zero
module_obj_load_bad:
    mov DWORD PTR [rbx],7
module_obj_load_zero:
    xor eax,eax
module_obj_load_done:
    add rsp,48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_module_objects_load ENDP

; op0 Class.getModule,op1 Module.getName,op2 Module.isNamed.
boom_module_objects_intrinsic PROC FRAME
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
    cmp DWORD PTR [rbx],0
    jne module_obj_intrinsic_zero
    cmp r12d,2
    ja module_obj_intrinsic_bad
    test rsi,rsi
    jz module_obj_intrinsic_bad
    mov rdx,rdi
    call boom_module_objects_pool_valid
    test eax,eax
    jz module_obj_intrinsic_bad
    test r12d,r12d
    jz module_obj_intrinsic_class
    mov rcx,QWORD PTR [rsi]
    mov rdx,rdi
    mov r8,rbx
    call boom_module_objects_value
    test rax,rax
    jz module_obj_intrinsic_zero
    mov ecx,DWORD PTR [rdi+112]
    mov rax,QWORD PTR [rax+rcx]
    cmp r12d,1
    je module_obj_intrinsic_done
    test rax,rax
    setnz al
    movzx eax,al
    jmp module_obj_intrinsic_done
module_obj_intrinsic_class:
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi]
    mov r8,QWORD PTR [rdi+56]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne module_obj_intrinsic_zero
    cmp eax,DWORD PTR [rdi+64]
    jae module_obj_intrinsic_bad
    mov r10,QWORD PTR [rdi+72]
    mov r8d,DWORD PTR [r10+rax*4]
    mov rcx,rbx
    mov rdx,rdi
    call boom_module_objects_load
    jmp module_obj_intrinsic_done
module_obj_intrinsic_bad:
    mov DWORD PTR [rbx],7
module_obj_intrinsic_zero:
    xor eax,eax
module_obj_intrinsic_done:
    add rsp,40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_module_objects_intrinsic ENDP
; Private BootLoader.setBootLoaderUnnamedModule0 boundary.
; (ctx RCX,argv{Module} RDX,BUMD48/1 pool R8)->void.
; state8D=0/2,reserved12D=0,ownerClass16Q,Java static cell24Q,
; physical MODU3 pool32Q,canonical VM GC-root cell40Q.
PUBLIC boom_boot_unnamed_publish
boom_boot_unnamed_publish PROC FRAME
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
    jz boot_unnamed_done
    cmp DWORD PTR [rbx],0
    jne boot_unnamed_done
    test rsi,rsi
    jz boot_unnamed_bad
    test rdi,rdi
    jz boot_unnamed_bad
    cmp DWORD PTR [rdi],0444D5542h
    jne boot_unnamed_bad
    cmp DWORD PTR [rdi+4],1
    jne boot_unnamed_bad
    cmp DWORD PTR [rdi+12],0
    jne boot_unnamed_bad
    mov eax,DWORD PTR [rdi+8]
    test eax,eax
    jz boot_unnamed_state_ok
    cmp eax,2
    jne boot_unnamed_bad
boot_unnamed_state_ok:
    mov rax,QWORD PTR [rdi+16]
    test rax,rax
    jz boot_unnamed_bad
    cmp DWORD PTR [rax],0434C4153h
    jne boot_unnamed_bad
    cmp DWORD PTR [rax+4],2
    jne boot_unnamed_bad
    mov ecx,DWORD PTR [rax+8]
    cmp ecx,2
    je boot_unnamed_owner_ok
    cmp ecx,1
    jne boot_unnamed_bad
    call GetCurrentThreadId
    mov rcx,QWORD PTR [rdi+16]
    cmp DWORD PTR [rcx+12],eax
    jne boot_unnamed_bad
boot_unnamed_owner_ok:
    mov r12,QWORD PTR [rsi]
    test r12,r12
    jz boot_unnamed_null
    mov rax,QWORD PTR [rdi+24]
    test rax,rax
    jz boot_unnamed_bad
    cmp QWORD PTR [rax],r12
    jne boot_unnamed_bad
    mov r13,QWORD PTR [rdi+40]
    test r13,r13
    jz boot_unnamed_bad
    mov rcx,r12
    mov rdx,QWORD PTR [rdi+32]
    mov r8,rbx
    call boom_module_objects_value
    test rax,rax
    jz boot_unnamed_done
    mov rdx,QWORD PTR [rdi+32]
    mov ecx,DWORD PTR [rdx+112]      ; Module.name must be null
    cmp QWORD PTR [r12+rcx],0
    jne boot_unnamed_bad
    mov ecx,DWORD PTR [rdx+116]      ; bootstrap Module.loader must be null
    cmp QWORD PTR [r12+rcx],0
    jne boot_unnamed_bad
    mov rax,r13
    sub rax,QWORD PTR [rdx+16]
    jc boot_unnamed_bad
    test al,7
    jnz boot_unnamed_bad
    shr rax,3
    mov ecx,DWORD PTR [rdx+12]
    cmp rax,rcx
    jae boot_unnamed_bad
    mov rcx,QWORD PTR [rdx+24]
    cmp DWORD PTR [rcx+rax*8],-1
    jne boot_unnamed_bad
    cmp DWORD PTR [rcx+rax*8+4],0
    jne boot_unnamed_bad
    mov rcx,QWORD PTR [rdx+104]
    cmp DWORD PTR [rcx+rax*4],0   ; canonical bootstrap loader key
    jne boot_unnamed_bad
    xor eax,eax
    lock cmpxchg QWORD PTR [r13],r12
    je boot_unnamed_publish
    cmp rax,r12
    jne boot_unnamed_bad
boot_unnamed_publish:
    mov eax,2
    xchg DWORD PTR [rdi+8],eax
    jmp boot_unnamed_done
boot_unnamed_null:
    mov DWORD PTR [rbx],4
    jmp boot_unnamed_done
boot_unnamed_bad:
    mov DWORD PTR [rbx],7
boot_unnamed_done:
    xor eax,eax
    add rsp,32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_boot_unnamed_publish ENDP
END
