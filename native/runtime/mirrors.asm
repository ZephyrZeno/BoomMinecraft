; Bootstrap Class mirrors. All runtime operations are handwritten MASM.
; Pool ABI1 size64: magic0 abi4 lock8 count12 roots16 rows24 layout32
; strings40 boundHeap48 reserved56. Row24: type*0 nameLiteral8 superId12
; componentId16 reserved20. Absent relationship = FFFFFFFF.
; Mirror payload8: typeId QWORD0, no guest references. Strong pool roots.
; ABI2 keeps the size/rows and uses pool+56 -> immutable assertion policy32:
; magic0 abi4 startupFlags8 count12 statusDWORDs*16 reserved24. Flag1 app/2 system.
; Operation7 reads the stored status (0/1) of the actual mirrored type.
; Metadata is immutable/source-verified. No target class initialization here.
option casemap:none
EXTERN boom_object_new:PROC
EXTERN boom_string_load:PROC
EXTERN boom_string_view:PROC
EXTERN boom_type_assignable:PROC
PUBLIC boom_mirror_load
PUBLIC boom_mirror_intrinsic
PUBLIC boom_mirror_typeid
PUBLIC boom_mirror_primitive
.const
ALIGN 8
primitive_names LABEL BYTE
    QWORD OFFSET primitive_boolean
    DWORD 7, 0
    QWORD OFFSET primitive_byte
    DWORD 4, 0
    QWORD OFFSET primitive_char
    DWORD 4, 0
    QWORD OFFSET primitive_short
    DWORD 5, 0
    QWORD OFFSET primitive_int
    DWORD 3, 0
    QWORD OFFSET primitive_long
    DWORD 4, 0
    QWORD OFFSET primitive_float
    DWORD 5, 0
    QWORD OFFSET primitive_double
    DWORD 6, 0
    QWORD OFFSET primitive_void
    DWORD 4, 0
primitive_boolean WORD 'b','o','o','l','e','a','n'
primitive_byte WORD 'b','y','t','e'
primitive_char WORD 'c','h','a','r'
primitive_short WORD 's','h','o','r','t'
primitive_int WORD 'i','n','t'
primitive_long WORD 'l','o','n','g'
primitive_float WORD 'f','l','o','a','t'
primitive_double WORD 'd','o','u','b','l','e'
primitive_void WORD 'v','o','i','d'
.code
; validate(pool RDX)->EAX 0/1, clobbers R10/R11 only besides RAX.
; Preserve RCX/RDX/R8/R9 so callers can keep object/context arguments.
mirror_pool_valid PROC
    test rdx, rdx
    jz mirror_pool_no
    cmp DWORD PTR [rdx], 04D495252h
    jne mirror_pool_no
    mov eax, DWORD PTR [rdx+12]
    dec eax
    cmp eax, 16383
    ja mirror_pool_no
    cmp DWORD PTR [rdx+4], 1
    je mirror_pool_v1
    cmp DWORD PTR [rdx+4], 2
    jne mirror_pool_no
    mov r10, QWORD PTR [rdx+56]
    test r10, r10
    jz mirror_pool_no
    cmp DWORD PTR [r10], 041535354h
    jne mirror_pool_no
    cmp DWORD PTR [r10+4], 1
    jne mirror_pool_no
    cmp DWORD PTR [r10+8], 3
    ja mirror_pool_no
    mov r11d, DWORD PTR [r10+12]
    cmp r11d, DWORD PTR [rdx+12]
    jne mirror_pool_no
    cmp QWORD PTR [r10+16], 0
    je mirror_pool_no
    cmp QWORD PTR [r10+24], 0
    jne mirror_pool_no
    jmp mirror_pool_yes
mirror_pool_v1:
    cmp QWORD PTR [rdx+56], 0
    jne mirror_pool_no
mirror_pool_yes:
    mov eax, 1
    ret
mirror_pool_no:
    xor eax, eax
    ret
mirror_pool_valid ENDP

boom_mirror_load PROC FRAME
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
    sub rsp, 48
    .allocstack 48
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov rdi, r9
    mov r13d, r8d
    test rbx, rbx
    jz mirror_load_invalid
    cmp DWORD PTR [rbx], 048454150h
    jne mirror_load_invalid
    cmp DWORD PTR [rbx+4], 1
    jne mirror_load_invalid
    mov rdx, rsi
    call mirror_pool_valid
    test eax, eax
    jz mirror_load_invalid
    cmp r13d, DWORD PTR [rsi+12]
    jae mirror_load_invalid
    cmp QWORD PTR [rsi+24], 0
    je mirror_load_invalid
    mov r12, QWORD PTR [rsi+16]
    test r12, r12
    jz mirror_load_invalid
    lea r12, [r12+r13*8]
    mov rax, QWORD PTR [rsi+32]
    test rax, rax
    jz mirror_load_invalid
    cmp DWORD PTR [rax], 04F424A43h
    jne mirror_load_invalid
    cmp DWORD PTR [rax+4], 1
    jne mirror_load_invalid
    cmp QWORD PTR [rax+8], 8
    jne mirror_load_invalid
    cmp DWORD PTR [rax+16], 0
    jne mirror_load_invalid
    cmp DWORD PTR [rax+20], 1
    jne mirror_load_invalid
    cmp QWORD PTR [rsi+48], rbx
    jne mirror_load_lock
    mov rax, QWORD PTR [r12]
    test rax, rax
    jnz mirror_load_done
mirror_load_lock:
    mov eax, 1
    xchg DWORD PTR [rsi+8], eax
    test eax, eax
    jz mirror_load_owned
mirror_load_spin:
    pause
    cmp DWORD PTR [rsi+8], 0
    jne mirror_load_spin
    jmp mirror_load_lock
mirror_load_owned:
    mov rax, QWORD PTR [rsi+48]
    test rax, rax
    jz mirror_load_bind
    cmp rax, rbx
    jne mirror_load_wrong_heap
    jmp mirror_load_bound
mirror_load_bind:
    mov QWORD PTR [rsi+48], rbx
mirror_load_bound:
    mov rax, QWORD PTR [r12]
    test rax, rax
    jnz mirror_load_unlock
    mov rcx, rbx
    mov rdx, QWORD PTR [rsi+32]
    mov r8, rdi
    call boom_object_new
    test rax, rax
    jz mirror_load_unlock
    mov QWORD PTR [rax], r13
    mov QWORD PTR [r12], rax
    jmp mirror_load_unlock
mirror_load_wrong_heap:
    mov DWORD PTR [rdi], 7
    xor eax, eax
mirror_load_unlock:
    mov DWORD PTR [rsi+8], 0
    jmp mirror_load_done
mirror_load_invalid:
    mov DWORD PTR [rdi], 7
    xor eax, eax
mirror_load_done:
    add rsp, 48
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_mirror_load ENDP

; value(object RCX,pool RDX,context R8)->row RAX or null/error.
; Only pointers from a validated live module/heap may be supplied.
mirror_value PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    test rcx, rcx
    jz mirror_value_null
    call mirror_pool_valid
    test eax, eax
    jz mirror_value_invalid
    mov rax, QWORD PTR [rdx+32]
    test rax, rax
    jz mirror_value_invalid
    cmp QWORD PTR [rcx-8], rax
    jne mirror_value_invalid
    cmp QWORD PTR [rcx-16], 8
    jne mirror_value_invalid
    cmp DWORD PTR [rcx-20], 0
    jne mirror_value_invalid
    mov eax, DWORD PTR [rcx-24]
    and eax, 0FFFFFFFDh
    cmp eax, 0B00B0001h
    jne mirror_value_invalid
    mov r10, QWORD PTR [rcx]
    mov r11d, DWORD PTR [rdx+12]
    cmp r10, r11
    jae mirror_value_invalid
    mov rax, QWORD PTR [rdx+16]
    test rax, rax
    jz mirror_value_invalid
    cmp QWORD PTR [rax+r10*8], rcx
    jne mirror_value_invalid
    imul r10, 24
    mov rax, QWORD PTR [rdx+24]
    test rax, rax
    jz mirror_value_invalid
    add rax, r10
    add rsp, 40
    ret
mirror_value_null:
    mov DWORD PTR [r8], 4
    xor eax, eax
    add rsp, 40
    ret
mirror_value_invalid:
    mov DWORD PTR [r8], 7
    xor eax, eax
    add rsp, 40
    ret
mirror_value ENDP

; typeid(context RCX,mirror RDX,pool R8)->id or -1 with Context16 error.
; Separate service: existing mirror opcodes and ABI1/ABI2 contracts are unchanged.
boom_mirror_typeid PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    mov QWORD PTR [rsp+32], rdx
    mov rax, rcx
    mov rcx, rdx
    mov rdx, r8
    mov r8, rax
    call mirror_value
    test rax, rax
    jz mirror_typeid_error
    mov rax, QWORD PTR [rsp+32]
    mov rax, QWORD PTR [rax]
    jmp mirror_typeid_done
mirror_typeid_error:
    mov rax, -1
mirror_typeid_done:
    add rsp, 40
    ret
boom_mirror_typeid ENDP

; primitive(Context16 RCX,argv RDX,mirrorPool R8,typeIds9 R9)->Class/NULL.
; Exact UTF16 names (including length); no decoding, allocation or wrapper init.
; Uses the same rooted mirror identity as ldc/component queries, including void.
boom_mirror_primitive PROC FRAME
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
    mov rbx, rcx
    mov rsi, rdx
    mov rdi, r8
    mov r12, r9
    mov rdx, rdi
    call mirror_pool_valid
    test eax, eax
    jz primitive_invalid
    test r12, r12
    jz primitive_invalid
    mov r13, QWORD PTR [rdi+40]
    test r13, r13
    jz primitive_invalid
    cmp DWORD PTR [r13], 053545250h
    jne primitive_invalid
    cmp DWORD PTR [r13+4], 2
    je primitive_string_pool_ok
    cmp DWORD PTR [r13+4], 3
    jne primitive_invalid
primitive_string_pool_ok:
    mov rcx, QWORD PTR [rsi]
    mov rdx, QWORD PTR [r13+40]
    mov r8, rbx
    call boom_string_view
    test rax, rax
    jz primitive_done
    xor r8d, r8d
    lea r9, primitive_names
primitive_name_next:
    cmp edx, DWORD PTR [r9+8]
    jne primitive_name_skip
    mov r10, QWORD PTR [r9]
    xor ecx, ecx
primitive_name_compare:
    movzx r11d, WORD PTR [rax+rcx*2]
    cmp r11w, WORD PTR [r10+rcx*2]
    jne primitive_name_skip
    inc ecx
    cmp ecx, edx
    jb primitive_name_compare
    mov ecx, r8d
    mov r8d, DWORD PTR [r12+r8*4]
    cmp r8d, DWORD PTR [rdi+12]
    jae primitive_invalid
    mov r10, QWORD PTR [rdi+24]
    test r10, r10
    jz primitive_invalid
    imul r11, r8, 24
    mov r10, QWORD PTR [r10+r11]
    test r10, r10
    jz primitive_invalid
    cmp DWORD PTR [r10], 054595045h
    jne primitive_invalid
    cmp DWORD PTR [r10+4], 1
    jne primitive_invalid
    cmp DWORD PTR [r10+8], 0
    jne primitive_invalid
    cmp DWORD PTR [r10+12], ecx
    jne primitive_invalid
    ; Immutable id vector comes from the same metadata as the row table.
    mov rcx, QWORD PTR [r13+48]
    mov rdx, rdi
    mov r9, rbx
    call boom_mirror_load
    jmp primitive_done
primitive_name_skip:
    add r9, 16
    inc r8d
    cmp r8d, 9
    jb primitive_name_next
    mov DWORD PTR [rbx], 19
    xor eax, eax
    jmp primitive_done
primitive_invalid:
    mov DWORD PTR [rbx], 7
    xor eax, eax
primitive_done:
    add rsp, 32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_mirror_primitive ENDP

; intrinsic(context RCX,argv RDX,pool R8,operation R9D)->guest value RAX.
boom_mirror_intrinsic PROC FRAME
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
    mov rbx, rcx
    mov rsi, rdx
    mov rdi, r8
    mov r12d, r9d
    test rdi, rdi
    jz mirror_intrinsic_invalid
    cmp r12d, 7
    ja mirror_intrinsic_invalid
    mov rcx, QWORD PTR [rsi]
    mov rdx, rdi
    mov r8, rbx
    call mirror_value
    test rax, rax
    jz mirror_intrinsic_done
    mov r13, rax
    cmp r12d, 7
    je mirror_assertion_status
    test r12d, r12d
    jz mirror_name
    cmp r12d, 4
    je mirror_super
    cmp r12d, 5
    je mirror_component
    cmp r12d, 6
    je mirror_assignable
    mov rax, QWORD PTR [r13]
    mov eax, DWORD PTR [rax+8]
    cmp r12d, 1
    jne mirror_not_array
    cmp eax, 3
    jmp mirror_boolean
mirror_not_array:
    cmp r12d, 2
    jne mirror_interface
    cmp eax, 0
    jmp mirror_boolean
mirror_interface:
    cmp eax, 2
mirror_boolean:
    sete al
    movzx eax, al
    jmp mirror_intrinsic_done
mirror_name:
    mov rcx, QWORD PTR [rdi+48]
    mov rdx, QWORD PTR [rdi+40]
    mov r8d, DWORD PTR [r13+8]
    mov r9, rbx
    call boom_string_load
    jmp mirror_intrinsic_done
mirror_super:
    mov r8d, DWORD PTR [r13+12]
    jmp mirror_relation
mirror_component:
    mov r8d, DWORD PTR [r13+16]
mirror_relation:
    cmp r8d, -1
    je mirror_absent
    mov rcx, QWORD PTR [rdi+48]
    mov rdx, rdi
    mov r9, rbx
    call boom_mirror_load
    jmp mirror_intrinsic_done
mirror_absent:
    xor eax, eax
    jmp mirror_intrinsic_done
mirror_assignable:
    mov rcx, QWORD PTR [rsi+8]
    mov rdx, rdi
    mov r8, rbx
    call mirror_value
    test rax, rax
    jz mirror_intrinsic_done
    mov rcx, QWORD PTR [rax]
    mov rdx, QWORD PTR [r13]
    call boom_type_assignable
    jmp mirror_intrinsic_done
mirror_assertion_status:
    cmp DWORD PTR [rdi+4], 2
    jne mirror_intrinsic_invalid
    ; Pool validation already checked the immutable descriptor/count/flags.
    mov r10, QWORD PTR [rdi+56]
    mov r10, QWORD PTR [r10+16]
    mov r11, QWORD PTR [rsi]
    mov r11, QWORD PTR [r11]
    mov eax, DWORD PTR [r10+r11*4]
    cmp eax, 1
    ja mirror_intrinsic_invalid
    jmp mirror_intrinsic_done
mirror_intrinsic_invalid:
    mov DWORD PTR [rbx], 7
    xor eax, eax
mirror_intrinsic_done:
    add rsp, 32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_mirror_intrinsic ENDP
END
