; Source-verified Class queries over the closed nominal type registry.
; Hidden class definition is not implemented and cannot enter this ABI1 profile.
; All runtime behavior is MASM, with no guest allocation or class initialization.
option casemap:none
EXTERN boom_mirror_typeid:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_string_load:PROC
EXTERN boom_string_fresh_literal:PROC
PUBLIC boom_class_is_hidden
.code
; (context RCX,argv RDX,queryPool R8)->boolean. Pool32:
; magic0 ABI4 count8 nominal-profile12 mirrorPool16 reserved24.
boom_class_is_hidden PROC FRAME
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
    cmp DWORD PTR [rbx],0
    jne class_hidden_done
    test r8,r8
    jz class_hidden_bad
    cmp DWORD PTR [r8],0434C5152h
    jne class_hidden_bad
    cmp DWORD PTR [r8+4],1
    jne class_hidden_bad
    cmp DWORD PTR [r8+12],1
    jne class_hidden_bad
    cmp QWORD PTR [r8+24],0
    jne class_hidden_bad
    mov eax,DWORD PTR [r8+8]
    test eax,eax
    jz class_hidden_bad
    cmp eax,65536
    ja class_hidden_bad
    mov r8,QWORD PTR [r8+16]
    test r8,r8
    jz class_hidden_bad
    cmp eax,DWORD PTR [r8+12]
    jne class_hidden_bad
    mov rsi,r8
    mov rdx,QWORD PTR [rdx]
    mov rdi,rdx
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne class_hidden_done
    ; A valid canonical mirror also belongs to this live pool's bound heap.
    mov rax,QWORD PTR [rsi+48]
    test rax,rax
    jz class_hidden_bad
    cmp DWORD PTR [rax],048454150h
    jne class_hidden_bad
    cmp DWORD PTR [rax+4],1
    jne class_hidden_bad
    lea rcx,[rax+160]
    cmp rdi,rcx
    jb class_hidden_bad
    mov rcx,QWORD PTR [rax+16]
    lea rax,[rax+rcx+128]
    cmp rdi,rax
    jae class_hidden_bad
    jmp class_hidden_done
class_hidden_bad:
    mov DWORD PTR [rbx],7
class_hidden_done:
    xor eax,eax
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_class_is_hidden ENDP
; name(ctx,argv{Class},namePool64/2,operation0canonical/1simple)->String/null.
; Rows16 hold two literal IDs and fresh-result flags. Private per-name caches
; preserve Class's stable String identities, independently of interned templates.
; Cache pointers are static roots. Locks never occupy reference slots.
PUBLIC boom_class_name
boom_class_name PROC FRAME
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
    mov rsi,r8
    mov r12d,r9d
    test rbx,rbx
    jz class_name_zero
    cmp DWORD PTR [rbx],0
    jne class_name_zero
    cmp r12d,1
    ja class_name_bad
    test rsi,rsi
    jz class_name_bad
    test rdx,rdx
    jz class_name_bad
    cmp DWORD PTR [rsi],0434C4E4Dh
    jne class_name_bad
    cmp DWORD PTR [rsi+4],2
    jne class_name_bad
    cmp DWORD PTR [rsi+12],0
    jne class_name_bad
    cmp QWORD PTR [rsi+56],0
    jne class_name_bad
    mov eax,DWORD PTR [rsi+8]
    test eax,eax
    jz class_name_bad
    cmp eax,65536
    ja class_name_bad
    mov r13,QWORD PTR [rsi+16]
    test r13,r13
    jz class_name_bad
    cmp eax,DWORD PTR [r13+12]
    jne class_name_bad
    mov rdi,QWORD PTR [rdx]
    test rdi,rdi
    jz class_name_null
    mov rcx,QWORD PTR [r13+48]
    mov rdx,rdi
    call boom_heap_contains
    test eax,eax
    jz class_name_bad
    mov rcx,rbx
    mov rdx,rdi
    mov r8,r13
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne class_name_zero
    cmp eax,DWORD PTR [rsi+8]
    jae class_name_bad
    lea rdi,[rax+rax]
    add rdi,r12
    mov r10,QWORD PTR [rsi+32]
    test r10,r10
    jz class_name_bad
    shl rax,4
    add r10,rax
    cmp DWORD PTR [r10+12],0
    jne class_name_bad
    test DWORD PTR [r10+8],0FFFFFFFCh
    jnz class_name_bad
    mov r8d,DWORD PTR [r10+r12*4]
    cmp r8d,-1
    je class_name_zero
    mov DWORD PTR [rsp+32],r8d
    mov rdx,QWORD PTR [rsi+24]
    test rdx,rdx
    jz class_name_bad
    mov rcx,QWORD PTR [r13+48]
    cmp QWORD PTR [rdx+48],0
    je class_name_heap_ready
    cmp rcx,QWORD PTR [rdx+48]
    jne class_name_bad
class_name_heap_ready:
    bt DWORD PTR [r10+8],r12d
    jnc class_name_literal
    mov r15,QWORD PTR [rsi+40]
    test r15,r15
    jz class_name_bad
    lea r15,[r15+rdi*8]
    mov r14,QWORD PTR [rsi+48]
    test r14,r14
    jz class_name_bad
    lea r14,[r14+rdi*4]
    mov rax,QWORD PTR [r15]
    test rax,rax
    jnz class_name_done
class_name_claim:
    mov eax,1
    xchg DWORD PTR [r14],eax
    test eax,eax
    jz class_name_owned
class_name_wait:
    pause
    cmp DWORD PTR [r14],0
    jne class_name_wait
    jmp class_name_claim
class_name_owned:
    mov rax,QWORD PTR [r15]
    test rax,rax
    jnz class_name_unlock
    mov rcx,QWORD PTR [r13+48]
    mov rdx,QWORD PTR [rsi+24]
    mov r8d,DWORD PTR [rsp+32]
    mov r9,rbx
    call boom_string_fresh_literal
    test rax,rax
    jz class_name_unlock
    mov QWORD PTR [r15],rax
class_name_unlock:
    mov DWORD PTR [r14],0
    jmp class_name_done
class_name_literal:
    mov r9,rbx
    call boom_string_load
    jmp class_name_done
class_name_null:
    mov DWORD PTR [rbx],4
    jmp class_name_zero
class_name_bad:
    mov DWORD PTR [rbx],7
class_name_zero:
    xor eax,eax
class_name_done:
    add rsp,48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_class_name ENDP
; Class.classValueMap lives in a VM sidecar, not in the 8-byte Class mirror.
; CVAL64/1: count8,mirrors16,roots24,typeMap32,expectedMapType40,
; runtimeType callback48,typeAssignable callback56. Callbacks are module metadata.
; Field reads/writes remain plain aligned Java reference accesses. The original
; ClassValue initialization lock and storeFence control publication separately.
PUBLIC boom_class_value_field
boom_class_value_field PROC FRAME
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
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    mov DWORD PTR [rsp+32],r9d
    test rbx,rbx
    jz class_value_zero
    cmp DWORD PTR [rbx],0
    jne class_value_zero
    cmp r9d,1
    ja class_value_bad
    test rsi,rsi
    jz class_value_bad
    test rdi,rdi
    jz class_value_bad
    cmp DWORD PTR [rdi],04356414Ch
    jne class_value_bad
    cmp DWORD PTR [rdi+4],1
    jne class_value_bad
    cmp DWORD PTR [rdi+12],0
    jne class_value_bad
    mov eax,DWORD PTR [rdi+8]
    test eax,eax
    jz class_value_bad
    cmp eax,65536
    ja class_value_bad
    mov r13,QWORD PTR [rdi+16]
    test r13,r13
    jz class_value_bad
    cmp eax,DWORD PTR [r13+12]
    jne class_value_bad
    cmp QWORD PTR [rdi+24],0
    je class_value_bad
    cmp QWORD PTR [rdi+32],0
    je class_value_bad
    cmp QWORD PTR [rdi+40],0
    je class_value_bad
    cmp QWORD PTR [rdi+48],0
    je class_value_bad
    cmp QWORD PTR [rdi+56],0
    je class_value_bad
    mov r12,QWORD PTR [r13+48]
    test r12,r12
    jz class_value_bad
    mov rdx,QWORD PTR [rsi]
    test rdx,rdx
    jz class_value_null
    mov rcx,r12
    call boom_heap_contains
    test eax,eax
    jz class_value_bad
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi]
    mov r8,r13
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne class_value_zero
    cmp eax,DWORD PTR [rdi+8]
    jae class_value_bad
    mov r13,QWORD PTR [rdi+24]
    lea r13,[r13+rax*8]
    mov rax,QWORD PTR [r13]
    cmp DWORD PTR [rsp+32],0
    je class_value_check
    mov rax,QWORD PTR [rsi+8]
class_value_check:
    mov QWORD PTR [rsp+40],rax
    test rax,rax
    jz class_value_ready
    mov rcx,r12
    mov rdx,rax
    call boom_heap_contains
    test eax,eax
    jz class_value_bad
    mov rcx,QWORD PTR [rsp+40]
    mov rdx,QWORD PTR [rdi+32]
    mov r8,rbx
    call QWORD PTR [rdi+48]
    test rax,rax
    jz class_value_bad
    mov rcx,rax
    mov rdx,QWORD PTR [rdi+40]
    call QWORD PTR [rdi+56]
    test eax,eax
    jz class_value_bad
class_value_ready:
    mov rax,QWORD PTR [rsp+40]
    cmp DWORD PTR [rsp+32],0
    je class_value_done
    mov QWORD PTR [r13],rax
    jmp class_value_zero
class_value_null:
    mov DWORD PTR [rbx],4
    jmp class_value_zero
class_value_bad:
    mov DWORD PTR [rbx],7
class_value_zero:
    xor eax,eax
class_value_done:
    add rsp,48
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_class_value_field ENDP
END
