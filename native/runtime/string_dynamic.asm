; Dynamic immutable Strings and content interning. All execution is MASM.
; Pool ABI3 size80 extends ABI2: internLock56 count60 rootSlot*64 capacity72.
; rootSlot belongs to the module's quiescent GC root vector. The growable intern
; table is a heap reference-prefix block with open addressing and 75% load limit.
; Java hashes are computed before locking; growth rehashes into a zeroed table.
; Old tables become collectible garbage.
; Literal matching adopts the caller into an uninitialized literal root, avoiding
; a second allocation and preserving intern-before-ldc identity.
option casemap:none
EXTERN boom_array_new:PROC
EXTERN boom_object_new:PROC
EXTERN boom_heap_alloc:PROC
EXTERN boom_string_view:PROC
PUBLIC boom_string_allocate
PUBLIC boom_string_intern
.code
; bind(heap RCX,pool RDX,context R8)->bool. Never holds lock during allocation.
dynamic_bind PROC
    test rcx, rcx
    jz dynamic_bind_bad
    cmp DWORD PTR [rcx], 048454150h
    jne dynamic_bind_bad
    cmp DWORD PTR [rcx+4], 1
    jne dynamic_bind_bad
    test rdx, rdx
    jz dynamic_bind_bad
    cmp DWORD PTR [rdx], 053545250h
    jne dynamic_bind_bad
    cmp DWORD PTR [rdx+4], 3
    jne dynamic_bind_bad
    cmp DWORD PTR [rdx+16], 65536
    ja dynamic_bind_bad
    cmp QWORD PTR [rdx+64], 0
    je dynamic_bind_bad
    mov r10, QWORD PTR [rdx+40]
    test r10, r10
    jz dynamic_bind_bad
    cmp DWORD PTR [r10], 04F424A43h
    jne dynamic_bind_bad
    cmp DWORD PTR [r10+4], 1
    jne dynamic_bind_bad
    cmp QWORD PTR [r10+8], 16
    jne dynamic_bind_bad
    cmp DWORD PTR [r10+16], 1
    jne dynamic_bind_bad
    cmp DWORD PTR [r10+20], 2
    jne dynamic_bind_bad
    cmp DWORD PTR [rdx+16], 0
    je dynamic_bind_fast
    cmp QWORD PTR [rdx+24], 0
    je dynamic_bind_bad
    cmp QWORD PTR [rdx+32], 0
    je dynamic_bind_bad
dynamic_bind_fast:
    cmp QWORD PTR [rdx+48], rcx
    je dynamic_bound
dynamic_bind_lock:
    mov eax, 1
    xchg DWORD PTR [rdx+8], eax
    test eax, eax
    jz dynamic_bind_owned
    pause
    jmp dynamic_bind_lock
dynamic_bind_owned:
    mov rax, QWORD PTR [rdx+48]
    test rax, rax
    jz dynamic_bind_publish
    cmp rax, rcx
    jne dynamic_bind_wrong_heap
    jmp dynamic_bind_release
dynamic_bind_publish:
    mov QWORD PTR [rdx+48], rcx
dynamic_bind_release:
    mov DWORD PTR [rdx+8], 0
dynamic_bound:
    mov eax, 1
    ret
dynamic_bind_wrong_heap:
    mov DWORD PTR [rdx+8], 0
dynamic_bind_bad:
    mov DWORD PTR [r8], 7
    xor eax, eax
    ret
dynamic_bind ENDP

; allocate(heap RCX,pool RDX,length R8D,context R9)->String/NULL.
; The assembly caller fills the private zeroed char[] before guest publication.
boom_string_allocate PROC FRAME
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
    mov rdi, r9
    mov r12d, r8d
    mov r8, rdi
    call dynamic_bind
    test eax, eax
    jz dynamic_allocate_failed
    mov rcx, rbx
    mov edx, r12d
    mov r8d, 5
    mov r9, rdi
    call boom_array_new
    test rax, rax
    jz dynamic_allocate_failed
    mov r13, rax
    mov rcx, rbx
    mov rdx, QWORD PTR [rsi+40]
    mov r8, rdi
    call boom_object_new
    test rax, rax
    jz dynamic_allocate_failed
    mov QWORD PTR [rax], r13
    jmp dynamic_allocate_done
dynamic_allocate_failed:
    xor eax, eax
dynamic_allocate_done:
    add rsp, 32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_allocate ENDP

; equal(char* RCX,char* RDX,length R8D)->bool.
dynamic_equal PROC
    xor r9d, r9d
dynamic_equal_loop:
    cmp r9d, r8d
    jae dynamic_equal_yes
    movzx eax, WORD PTR [rcx+r9*2]
    cmp ax, WORD PTR [rdx+r9*2]
    jne dynamic_equal_no
    inc r9d
    jmp dynamic_equal_loop
dynamic_equal_yes:
    mov eax, 1
    ret
dynamic_equal_no:
    xor eax, eax
    ret
dynamic_equal ENDP

; Compute Java's wrapping UTF16 hash before taking the intern lock.
dynamic_hash PROC
    cmp DWORD PTR [rcx+12], 1
    je dynamic_hash_cached
    xor eax, eax
    xor r9d, r9d
dynamic_hash_loop:
    cmp r9d, r8d
    jae dynamic_hash_publish
    imul eax, eax, 31
    movzx r10d, WORD PTR [rdx+r9*2]
    add eax, r10d
    inc r9d
    jmp dynamic_hash_loop
dynamic_hash_publish:
    mov DWORD PTR [rcx+8], eax
    mov DWORD PTR [rcx+12], 1
    ret
dynamic_hash_cached:
    mov eax, DWORD PTR [rcx+8]
    ret
dynamic_hash ENDP

; intern(context RCX,argv RDX,pool R8)->canonical String/NULL.
boom_string_intern PROC FRAME
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
    sub rsp, 48
    .allocstack 48
    .endprolog
    mov rbx, rcx
    mov rsi, r8
    mov r12, QWORD PTR [rdx]
    test rsi, rsi
    jz dynamic_intern_invalid
    cmp DWORD PTR [rsi+4], 3
    jne dynamic_intern_invalid
    mov rcx, QWORD PTR [rsi+48]
    mov rdx, rsi
    mov r8, rbx
    call dynamic_bind
    test eax, eax
    jz dynamic_intern_done
    mov rcx, r12
    mov rdx, QWORD PTR [rsi+40]
    mov r8, rbx
    call boom_string_view
    cmp DWORD PTR [rbx], 0
    jne dynamic_intern_failed
    mov r13, rax
    mov r14d, edx
    mov rcx, r12
    mov rdx, r13
    mov r8d, r14d
    call dynamic_hash
    mov DWORD PTR [rsp+40], eax
dynamic_intern_lock:
    mov eax, 1
    xchg DWORD PTR [rsi+56], eax
    test eax, eax
    jz dynamic_intern_owned
    pause
    jmp dynamic_intern_lock
dynamic_intern_owned:
    xor r15d, r15d
dynamic_literal_loop:
    cmp r15d, DWORD PTR [rsi+16]
    jae dynamic_table_begin
    mov rdi, QWORD PTR [rsi+32]
    mov eax, r15d
    shl rax, 4
    add rdi, rax
    cmp r14d, DWORD PTR [rdi+8]
    jne dynamic_literal_next
    mov rcx, r13
    mov rdx, QWORD PTR [rdi]
    mov r8d, r14d
    call dynamic_equal
    test eax, eax
    jnz dynamic_literal_match
dynamic_literal_next:
    inc r15d
    jmp dynamic_literal_loop
dynamic_literal_match:
    ; Only this order exists: intern lock -> literal lock -> heap allocator.
    mov eax, 1
    xchg DWORD PTR [rsi+8], eax
    test eax, eax
    jz dynamic_literal_owned
    pause
    jmp dynamic_literal_match
dynamic_literal_owned:
    mov rdx, QWORD PTR [rsi+24]
    lea rdx, [rdx+r15*8]
    mov rax, QWORD PTR [rdx]
    test rax, rax
    jnz dynamic_literal_release
    mov QWORD PTR [rdx], r12
    mov rax, r12
dynamic_literal_release:
    mov DWORD PTR [rsi+8], 0
    jmp dynamic_intern_unlock
dynamic_table_begin:
    mov eax, DWORD PTR [rsi+60]
    cmp eax, DWORD PTR [rsi+72]
    ja dynamic_table_invalid
    cmp DWORD PTR [rsi+72], 1048576
    ja dynamic_table_invalid
    mov rdi, QWORD PTR [rsi+64]
    mov rdi, QWORD PTR [rdi]
    test rdi, rdi
    jnz dynamic_table_validate
    cmp DWORD PTR [rsi+72], 0
    jne dynamic_table_invalid
    jmp dynamic_table_grow
dynamic_table_validate:
    mov ecx, DWORD PTR [rsi+72]
    cmp ecx, 64
    jb dynamic_table_invalid
    lea eax, [rcx-1]
    test eax, ecx
    jnz dynamic_table_invalid
    cmp DWORD PTR [rsi+60], ecx
    jae dynamic_table_invalid
    cmp DWORD PTR [rdi-20], ecx
    jne dynamic_table_invalid
    shl rcx, 3
    cmp QWORD PTR [rdi-16], rcx
    jne dynamic_table_invalid
    cmp QWORD PTR [rdi-8], 053545249h
    jne dynamic_table_invalid
    mov r15d, DWORD PTR [rsp+40]
    mov eax, DWORD PTR [rsi+72]
    dec eax
    and r15d, eax
dynamic_table_loop:
    mov rcx, QWORD PTR [rdi+r15*8]
    test rcx, rcx
    jz dynamic_table_insert
    mov eax, DWORD PTR [rsp+40]
    cmp DWORD PTR [rcx+8], eax
    jne dynamic_table_next
    mov rdx, QWORD PTR [rsi+40]
    mov r8, rbx
    call boom_string_view
    cmp DWORD PTR [rbx], 0
    jne dynamic_intern_unlock_failed
    cmp edx, r14d
    jne dynamic_table_next
    mov rcx, r13
    mov rdx, rax
    mov r8d, r14d
    call dynamic_equal
    test eax, eax
    jz dynamic_table_next
    mov rax, QWORD PTR [rdi+r15*8]
    jmp dynamic_intern_unlock
dynamic_table_next:
    inc r15d
    mov eax, DWORD PTR [rsi+72]
    dec eax
    and r15d, eax
    jmp dynamic_table_loop
dynamic_table_insert:
    mov eax, DWORD PTR [rsi+72]
    mov edx, eax
    shr edx, 2
    sub eax, edx
    cmp DWORD PTR [rsi+60], eax
    jb dynamic_table_publish
dynamic_table_grow:
    mov r15d, DWORD PTR [rsi+72]
    test r15d, r15d
    jnz dynamic_table_double
    mov r15d, 32
dynamic_table_double:
    shl r15d, 1
    cmp r15d, 1048576
    ja dynamic_table_oom
    mov rcx, QWORD PTR [rsi+48]
    mov edx, r15d
    shl rdx, 3
    mov r8d, r15d
    mov r9d, 053545249h
    call boom_heap_alloc
    test rax, rax
    jz dynamic_table_oom
    mov QWORD PTR [rsp+32], rax
    xor ecx, ecx
dynamic_table_copy:
    cmp ecx, DWORD PTR [rsi+72]
    jae dynamic_table_replace
    mov rdx, QWORD PTR [rdi+rcx*8]
    test rdx, rdx
    jz dynamic_rehash_next
    mov r10d, DWORD PTR [rdx+8]
    lea r11d, [r15-1]
    and r10d, r11d
dynamic_rehash_probe:
    cmp QWORD PTR [rax+r10*8], 0
    je dynamic_rehash_store
    inc r10d
    and r10d, r11d
    jmp dynamic_rehash_probe
dynamic_rehash_store:
    mov QWORD PTR [rax+r10*8], rdx
dynamic_rehash_next:
    inc ecx
    jmp dynamic_table_copy
dynamic_table_replace:
    mov rdi, QWORD PTR [rsp+32]
    mov rdx, QWORD PTR [rsi+64]
    mov QWORD PTR [rdx], rdi
    mov DWORD PTR [rsi+72], r15d
    jmp dynamic_table_validate
dynamic_table_publish:
    mov QWORD PTR [rdi+r15*8], r12
    inc DWORD PTR [rsi+60]
    mov rax, r12
    jmp dynamic_intern_unlock
dynamic_table_oom:
    mov DWORD PTR [rbx], 3
    jmp dynamic_intern_unlock_failed
dynamic_table_invalid:
    mov DWORD PTR [rbx], 7
dynamic_intern_unlock_failed:
    xor eax, eax
dynamic_intern_unlock:
    mov DWORD PTR [rsi+56], 0
    jmp dynamic_intern_done
dynamic_intern_invalid:
    mov DWORD PTR [rbx], 7
dynamic_intern_failed:
    xor eax, eax
dynamic_intern_done:
    add rsp, 48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_intern ENDP
END
