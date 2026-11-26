; Loader-aware heap tag lookup and Java checkcast/instanceof/getClass. MASM only.
; Map ABI1 size32: magic0 abi4 count8 typeCount12 rows*16 mirrorPool*24.
; Row40: tag0 TypeDesc*8 typeId16 kind20 payload24 refs32 shift36.
; kind object0 primitive-array1 reference-array2. Native callers provide live,
; typed heap pointers and immutable compiler metadata; this is not a sandbox.
option casemap:none
EXTERN boom_type_assignable:PROC
EXTERN boom_mirror_load:PROC
EXTERN boom_mirror_typeid:PROC
EXTERN boom_runtime_lookup_indexed:PROC
PUBLIC boom_runtime_type
PUBLIC boom_runtime_cast
PUBLIC boom_runtime_instanceof
PUBLIC boom_runtime_getclass
PUBLIC boom_class_is_instance
PUBLIC boom_runtime_row
.code
; target validates the map and reference target, preserving RCX/RDX/R8/R9.
runtime_target PROC
    test rdx, rdx
    jz runtime_target_bad
    cmp DWORD PTR [rdx], 052545950h
    jne runtime_target_bad
    cmp DWORD PTR [rdx+4], 2
    je runtime_target_large
    cmp DWORD PTR [rdx+4], 1
    jne runtime_target_bad
    mov eax, DWORD PTR [rdx+8]
    dec eax
    cmp eax, 65535
    ja runtime_target_bad
    mov eax, DWORD PTR [rdx+12]
    dec eax
    cmp eax, 16383
    ja runtime_target_bad
    cmp QWORD PTR [rdx+16], 0
    je runtime_target_bad
    jmp runtime_target_descriptor
runtime_target_large:
    mov eax,DWORD PTR [rdx+8]
    dec eax
    cmp eax,0FFFFFh
    ja runtime_target_bad
    mov eax,DWORD PTR [rdx+12]
    dec eax
    cmp eax,0FFFFFh
    ja runtime_target_bad
    cmp QWORD PTR [rdx+16],0
    je runtime_target_bad
runtime_target_descriptor:
    test r8, r8
    jz runtime_target_bad
    cmp DWORD PTR [r8], 054595045h
    jne runtime_target_bad
    cmp DWORD PTR [r8+4], 1
    jne runtime_target_bad
    mov eax, DWORD PTR [r8+8]
    dec eax
    cmp eax, 2
    ja runtime_target_bad
    mov eax, 1
    ret
runtime_target_bad:
    mov DWORD PTR [r9], 7
    xor eax, eax
    ret
runtime_target ENDP

; lookup(object RCX,map RDX,context R8)->validated row or NULL/error.
runtime_lookup PROC
    ; Dispatch ABI2 before the legacy null guard so its pending-error contract
    ; also applies to null receivers. Metadata pointers are trusted/live inputs.
    test rdx,rdx
    jz runtime_lookup_legacy
    cmp DWORD PTR [rdx],052545950h
    jne runtime_lookup_legacy
    cmp DWORD PTR [rdx+4],2
    je runtime_lookup_indexed
runtime_lookup_legacy:
    test rcx, rcx
    jz runtime_lookup_null
    test rdx, rdx
    jz runtime_lookup_bad
    cmp DWORD PTR [rdx], 052545950h
    jne runtime_lookup_bad
    cmp DWORD PTR [rdx+4], 2
    je runtime_lookup_indexed
    cmp DWORD PTR [rdx+4], 1
    jne runtime_lookup_bad
    mov r9d, DWORD PTR [rdx+8]
    lea eax, [r9-1]
    cmp eax, 65535
    ja runtime_lookup_bad
    mov eax, DWORD PTR [rdx+12]
    dec eax
    cmp eax, 16383
    ja runtime_lookup_bad
    mov r10, QWORD PTR [rdx+16]
    test r10, r10
    jz runtime_lookup_bad
    mov eax, DWORD PTR [rcx-24]
    and eax, 0FFFFFFFDh
    cmp eax, 0B00B0001h
    jne runtime_lookup_bad
    mov r11, QWORD PTR [rcx-8]
runtime_lookup_loop:
    cmp QWORD PTR [r10], r11
    je runtime_lookup_match
    add r10, 40
    dec r9d
    jnz runtime_lookup_loop
    jmp runtime_lookup_bad
runtime_lookup_match:
    mov eax, DWORD PTR [r10+16]
    cmp eax, DWORD PTR [rdx+12]
    jae runtime_lookup_bad
    mov r11, QWORD PTR [r10+8]
    test r11, r11
    jz runtime_lookup_bad
    cmp DWORD PTR [r11], 054595045h
    jne runtime_lookup_bad
    cmp DWORD PTR [r11+4], 1
    jne runtime_lookup_bad
    mov eax, DWORD PTR [r10+20]
    test eax, eax
    jnz runtime_lookup_array
    cmp DWORD PTR [r11+8], 1
    jne runtime_lookup_bad
    mov rax, QWORD PTR [r10+24]
    cmp QWORD PTR [rcx-16], rax
    jne runtime_lookup_bad
    mov eax, DWORD PTR [r10+32]
    cmp DWORD PTR [rcx-20], eax
    jne runtime_lookup_bad
    jmp runtime_lookup_found
runtime_lookup_array:
    cmp eax, 2
    ja runtime_lookup_bad
    cmp DWORD PTR [r11+8], 3
    jne runtime_lookup_bad
    cmp eax, 2
    je runtime_lookup_refs
    cmp DWORD PTR [rcx-20], 0
    jne runtime_lookup_bad
    mov eax, DWORD PTR [r10+36]
    cmp eax, 3
    ja runtime_lookup_bad
    ; Count trailing byte alignment without changing the object pointer RCX.
    mov r11, QWORD PTR [rcx-16]
    mov r9d, eax
runtime_lookup_shift:
    test r9d, r9d
    jz runtime_lookup_length
    test r11b, 1
    jnz runtime_lookup_bad
    shr r11, 1
    dec r9d
    jmp runtime_lookup_shift
runtime_lookup_refs:
    mov r11d, DWORD PTR [rcx-20]
    mov rax, r11
    shl rax, 3
    cmp QWORD PTR [rcx-16], rax
    jne runtime_lookup_bad
runtime_lookup_length:
    cmp r11, 07FFFFFFFh
    ja runtime_lookup_bad
runtime_lookup_found:
    mov rax, r10
    ret
runtime_lookup_indexed:
    jmp boom_runtime_lookup_indexed
runtime_lookup_null:
    mov DWORD PTR [r8], 4
    xor eax, eax
    ret
runtime_lookup_bad:
    mov DWORD PTR [r8], 7
    xor eax, eax
    ret
runtime_lookup ENDP

boom_runtime_row PROC
    jmp runtime_lookup
boom_runtime_row ENDP

; query(object RCX,map RDX,ctx R8)->TypeDesc/NULL.
boom_runtime_type PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    call runtime_lookup
    test rax, rax
    jz runtime_query_done
    mov rax, QWORD PTR [rax+8]
runtime_query_done:
    add rsp, 40
    ret
boom_runtime_type ENDP
boom_runtime_cast PROC
    mov r10d, 1
    jmp runtime_check
boom_runtime_cast ENDP
boom_runtime_instanceof PROC
    xor r10d, r10d
    jmp runtime_check
boom_runtime_instanceof ENDP
runtime_check PROC FRAME
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
    sub rsp, 32
    .allocstack 32
    .endprolog
    mov rbx, r9
    mov rsi, rcx
    mov rdi, r8
    mov r12, rdx
    mov r13d, r10d
    call runtime_target
    test eax, eax
    jz runtime_check_failed
    test rsi, rsi
    jz runtime_check_failed
    mov rcx, rsi
    mov rdx, r12
    mov r8, rbx
    call runtime_lookup
    test rax, rax
    jz runtime_check_failed
    mov rcx, QWORD PTR [rax+8]
    mov rdx, rdi
    call boom_type_assignable
    test eax, eax
    jz runtime_check_mismatch
    test r13d, r13d
    jz runtime_check_done
    mov rax, rsi
    jmp runtime_check_done
runtime_check_mismatch:
    test r13d, r13d
    jz runtime_check_failed
    mov DWORD PTR [rbx], 12
runtime_check_failed:
    xor eax, eax
runtime_check_done:
    add rsp, 32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
runtime_check ENDP

; getclass(context RCX,argv RDX,heap R8,map R9)->Class/NULL.
boom_runtime_getclass PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp, 32
    .allocstack 32
    .endprolog
    mov rbx, rcx
    mov rsi, r8
    mov rdi, r9
    mov rcx, QWORD PTR [rdx]
    mov rdx, rdi
    mov r8, rbx
    call runtime_lookup
    test rax, rax
    jz runtime_getclass_done
    mov r8d, DWORD PTR [rax+16]
    mov rcx, rsi
    mov rdx, QWORD PTR [rdi+24]
    mov r9, rbx
    call boom_mirror_load
runtime_getclass_done:
    add rsp, 32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_runtime_getclass ENDP

; Class.isInstance(ctx RCX,argv RDX,runtimeMap R8)->boolean. Resolves the
; canonical mirror first, then uses the same loader-aware subtype relation as
; instanceof. Primitive/void mirrors and null objects always return false.
boom_class_is_instance PROC FRAME
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
    cmp DWORD PTR [rbx],0
    jne class_instance_zero
    test rsi,rsi
    jz class_instance_bad
    test rdi,rdi
    jz class_instance_bad
    cmp DWORD PTR [rdi],052545950h
    jne class_instance_bad
    cmp DWORD PTR [rdi+4],1
    jne class_instance_bad
    mov r12,QWORD PTR [rdi+24]
    test r12,r12
    jz class_instance_bad
    mov eax,DWORD PTR [rdi+12]
    cmp eax,DWORD PTR [r12+12]
    jne class_instance_bad
    mov rdx,QWORD PTR [rsi]
    mov r8,r12
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne class_instance_zero
    cmp eax,DWORD PTR [r12+12]
    jae class_instance_bad
    imul rax,24
    add rax,QWORD PTR [r12+24]
    mov r13,QWORD PTR [rax]
    cmp DWORD PTR [r13+8],0
    je class_instance_zero
    mov rcx,QWORD PTR [rsi+8]
    mov rdx,rdi
    mov r8,r13
    mov r9,rbx
    call boom_runtime_instanceof
    jmp class_instance_done
class_instance_bad:
    mov DWORD PTR [rbx],7
class_instance_zero:
    xor eax,eax
class_instance_done:
    add rsp,32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_class_is_instance ENDP
END
