; Complete concrete-class layouts, supplied separately per actual class.
; The compiler generates hierarchy dispatch and inherited-field maps alongside
; these physical layouts. Distinct layout addresses preserve class identity.
; Layout: magic DWORD, ABI DWORD, payloadBytes QWORD, refs DWORD, fields DWORD.
; Reference fields precede scalar fields. ABI1 uses eight-byte field slots;
; ABI2 packs naturally aligned scalar fields and records actual payload bytes.
; The layout address is the heap type tag. Keep its module loaded until heap death.
option casemap:none
EXTERN boom_heap_alloc:PROC
PUBLIC boom_object_new
PUBLIC boom_object_check
.code

boom_object_new PROC FRAME
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
    mov rsi, rdx
    mov rdi, r8
    test rsi, rsi
    jz object_bad_layout
    cmp DWORD PTR [rsi], 04F424A43h
    jne object_bad_layout
    mov r10d, DWORD PTR [rsi+20]
    cmp r10d, 65536
    ja object_bad_layout
    mov r11d, DWORD PTR [rsi+16]
    cmp r11d, r10d
    ja object_bad_layout
    cmp DWORD PTR [rsi+4], 1
    je object_layout_slots
    cmp DWORD PTR [rsi+4], 2
    jne object_bad_layout
    mov eax, r10d
    sub eax, r11d
    lea rax, [rax+r11*8]
    cmp QWORD PTR [rsi+8], rax
    jb object_bad_layout
    mov eax, r10d
    shl rax, 3
    cmp QWORD PTR [rsi+8], rax
    ja object_bad_layout
    mov rax, QWORD PTR [rsi+8]
    jmp object_layout_ready
object_layout_slots:
    mov eax, r10d
    shl rax, 3
    cmp QWORD PTR [rsi+8], rax
    jne object_bad_layout
object_layout_ready:
    mov rcx, rbx
    mov rdx, rax
    mov r8d, DWORD PTR [rsi+16]
    mov r9, rsi
    call boom_heap_alloc
    test rax, rax
    jnz object_new_done
    mov DWORD PTR [rdi], 3
    jmp object_new_done
object_bad_layout:
    mov DWORD PTR [rdi], 7
    xor eax, eax
object_new_done:
    add rsp, 32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_object_new ENDP

boom_object_check PROC
    test rcx, rcx
    jz object_null
    test rdx, rdx
    jz object_wrong_type
    cmp DWORD PTR [rdx], 04F424A43h
    jne object_wrong_type
    mov r9d, DWORD PTR [rdx+20]
    cmp r9d, 65536
    ja object_wrong_type
    mov r10d, DWORD PTR [rdx+16]
    cmp r10d, r9d
    ja object_wrong_type
    cmp DWORD PTR [rdx+4], 1
    je object_check_slots
    cmp DWORD PTR [rdx+4], 2
    jne object_wrong_type
    mov eax, r9d
    sub eax, r10d
    lea rax, [rax+r10*8]
    cmp QWORD PTR [rdx+8], rax
    jb object_wrong_type
    mov eax, r9d
    shl rax, 3
    cmp QWORD PTR [rdx+8], rax
    ja object_wrong_type
    jmp object_check_header
object_check_slots:
    mov eax, r9d
    shl rax, 3
    cmp QWORD PTR [rdx+8], rax
    jne object_wrong_type
object_check_header:
    mov eax, DWORD PTR [rcx-24]
    and eax, 0FFFFFFFDh
    cmp eax, 0B00B0001h
    jne object_wrong_type
    cmp QWORD PTR [rcx-8], rdx
    jne object_wrong_type
    mov rax, QWORD PTR [rdx+8]
    cmp QWORD PTR [rcx-16], rax
    jne object_wrong_type
    mov eax, DWORD PTR [rdx+16]
    cmp DWORD PTR [rcx-20], eax
    jne object_wrong_type
    mov rax, rcx
    ret
object_null:
    mov DWORD PTR [r8], 4
    xor eax, eax
    ret
object_wrong_type:
    mov DWORD PTR [r8], 7
    xor eax, eax
    ret
boom_object_check ENDP
END
