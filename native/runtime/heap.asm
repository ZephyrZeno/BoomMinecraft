; Bootstrap nonmoving heap, entirely MASM. Explicit, quiescent mark/sweep GC.
; create(total budget)->heap/NULL; alloc(heap,bytes,reference-prefix-slots,type)->object/NULL.
; collect(heap,root-pointer-array,count)->freed-object-count, -1 on invalid input.
; Java thread safepoints/stack maps and automatic allocation retry are not yet integrated.
; Header128 includes an in-budget GC worklist. Blocks: span0, flags8, refs12,
; payloadBytes16, type24; data32. References occupy the first refs*8 payload bytes.
; Reserved header96/104/112/120 hold the monitor registry/lock/outstanding/free list.
option casemap:none
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
PUBLIC boom_heap_create
PUBLIC boom_heap_alloc
PUBLIC boom_heap_collect
PUBLIC boom_heap_destroy
PUBLIC boom_heap_contains
HEAP_MAGIC EQU 048454150h
OBJECT_MAGIC EQU 0B00B0001h
.code

; contains(heap,oop)->1 for a complete live block in this arena, otherwise 0.
; Caller supplies a live heap; no allocation, synchronization or payload reads.
boom_heap_contains PROC
    test rcx,rcx
    jz heap_contains_no
    cmp DWORD PTR [rcx],HEAP_MAGIC
    jne heap_contains_no
    cmp DWORD PTR [rcx+4],1
    jne heap_contains_no
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz heap_contains_no
    cmp rax,040000000h
    ja heap_contains_no
    lea r10,[rcx+128]
    add rax,r10
    jc heap_contains_no
    cmp rax,QWORD PTR [rcx+24]
    jne heap_contains_no
    lea r10,[rcx+160]
    cmp rdx,r10
    jb heap_contains_no
    cmp rdx,rax
    ja heap_contains_no
    test dl,15
    jnz heap_contains_no
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,OBJECT_MAGIC
    jne heap_contains_no
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb heap_contains_no
    test r10b,15
    jnz heap_contains_no
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja heap_contains_no
    add r10,rdx
    jc heap_contains_no
    cmp r10,rax
    ja heap_contains_no
    mov eax,DWORD PTR [rdx-20]
    shl rax,3
    cmp rax,QWORD PTR [rdx-16]
    ja heap_contains_no
    mov eax,1
    ret
heap_contains_no:
    xor eax,eax
    ret
boom_heap_contains ENDP

heap_lock PROC
    mov eax, 1
    xchg DWORD PTR [rcx+8], eax
    test eax, eax
    jz heap_locked
heap_spin:
    pause
    cmp DWORD PTR [rcx+8], 0
    jne heap_spin
    jmp heap_lock
heap_locked:
    ret
heap_lock ENDP

heap_registry_lock PROC
    mov eax, 1
    xchg DWORD PTR [rcx+104], eax
    test eax, eax
    jz heap_registry_locked
heap_registry_spin:
    pause
    cmp DWORD PTR [rcx+104], 0
    jne heap_registry_spin
    jmp heap_registry_lock
heap_registry_locked:
    ret
heap_registry_lock ENDP

boom_heap_create PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp, 40
    .allocstack 40
    .endprolog
    cmp rcx, 4096
    jb heap_create_fail
    cmp rcx, 1073741824
    ja heap_create_fail
    and rcx, -4096
    mov rbx, rcx
    mov rax, rcx
    sub rax, 128
    xor edx, edx
    mov ecx, 5
    div rcx
    shl rax, 2
    and rax, -16
    mov rsi, rax
    xor ecx, ecx
    mov rdx, rbx
    mov r8d, 03000h
    mov r9d, 4
    call VirtualAlloc
    test rax, rax
    jz heap_create_fail
    mov DWORD PTR [rax], HEAP_MAGIC
    mov DWORD PTR [rax+4], 1 ; heap ABI includes allocation cursor semantics
    mov DWORD PTR [rax+108], 1 ; optional monitor registry ABI1 capability
    mov QWORD PTR [rax+16], rsi
    lea r10, [rax+rsi+128]
    mov QWORD PTR [rax+24], r10
    mov QWORD PTR [rax+32], r10
    sub rbx, 128
    sub rbx, rsi
    shr rbx, 3
    mov QWORD PTR [rax+40], rbx
    mov QWORD PTR [rax+128], rsi
    lea r10, [rax+128]
    mov QWORD PTR [rax+88], r10
    jmp heap_create_done
heap_create_fail:
    xor eax, eax
heap_create_done:
    add rsp, 40
    pop rsi
    pop rbx
    ret
boom_heap_create ENDP

boom_heap_alloc PROC FRAME
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
    test rcx, rcx
    jz heap_alloc_fail
    cmp DWORD PTR [rcx], HEAP_MAGIC
    jne heap_alloc_fail
    cmp DWORD PTR [rcx+4], 1
    jne heap_alloc_fail
    cmp rdx, QWORD PTR [rcx+16]
    ja heap_alloc_fail
    mov eax, r8d
    shl rax, 3
    cmp rax, rdx
    ja heap_alloc_fail
    test r9, r9
    jz heap_alloc_fail
    mov rbx, rcx
    mov rsi, rdx
    mov r12d, r8d
    mov r13, r9
    call heap_lock
    lea r10, [rsi+47]
    and r10, -16
    mov rax, QWORD PTR [rbx+16]
    sub rax, QWORD PTR [rbx+48]
    cmp rax, r10
    jb heap_alloc_unlock_fail
    ; Cursor makes the common append path constant-time. On fragmentation,
    ; wrap once to search earlier free blocks rather than dropping capacity.
    mov rdi, QWORD PTR [rbx+88]
    xor r11d, r11d
    test rdi, rdi
    jnz heap_find_space
    lea rdi, [rbx+128]
    mov r11d, 1
heap_find_space:
    cmp rdi, QWORD PTR [rbx+24]
    jb heap_check_space
    test r11d, r11d
    jnz heap_alloc_unlock_fail
    mov r11d, 1
    lea rdi, [rbx+128]
heap_check_space:
    test DWORD PTR [rdi+8], 1
    jnz heap_alloc_next
    mov rax, QWORD PTR [rdi]
    cmp rax, r10
    jb heap_alloc_next
    sub rax, r10
    mov QWORD PTR [rbx+88], 0
    cmp rax, 32
    jb heap_use_block
    lea r11, [rdi+r10]
    mov QWORD PTR [r11], rax
    mov QWORD PTR [r11+8], 0
    mov QWORD PTR [r11+16], 0
    mov QWORD PTR [r11+24], 0
    mov QWORD PTR [rdi], r10
    mov QWORD PTR [rbx+88], r11
heap_use_block:
    mov DWORD PTR [rdi+8], OBJECT_MAGIC
    mov DWORD PTR [rdi+12], r12d
    mov QWORD PTR [rdi+16], rsi
    mov QWORD PTR [rdi+24], r13
    mov rax, QWORD PTR [rdi]
    add QWORD PTR [rbx+48], rax
    inc QWORD PTR [rbx+56]
    mov rcx, QWORD PTR [rbx+48]
    cmp rcx, QWORD PTR [rbx+64]
    jbe heap_peak_done
    mov QWORD PTR [rbx+64], rcx
heap_peak_done:
    ; Reservation, headers and accounting are now complete. Payloads belong only
    ; to this allocating caller until return; quiescent GC never overlaps alloc.
    ; Zero disjoint payloads in parallel instead of holding the heap lock here.
    mov DWORD PTR [rbx+8], 0
    mov rsi, rdi
    lea rdi, [rdi+32]
    mov rcx, rax
    sub rcx, 32
    shr rcx, 3
    xor eax, eax
    rep stosq
    lea rax, [rsi+32]
    jmp heap_alloc_done
heap_alloc_next:
    add rdi, QWORD PTR [rdi]
    jmp heap_find_space
heap_alloc_unlock_fail:
    mov DWORD PTR [rbx+8], 0
heap_alloc_fail:
    xor eax, eax
heap_alloc_done:
    add rsp, 32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_heap_alloc ENDP

; Mark a trusted typed heap reference. Header/range checks catch stale or
; out-of-heap references; this native ABI is not an arbitrary-pointer sandbox.
; rcx heap, rdx reference, r8 pointer to worklist-used counter. eax=0/invalid1.
heap_mark PROC
    test rdx, rdx
    jz heap_mark_ok
    test dl, 15
    jnz heap_mark_invalid
    lea r9, [rcx+160]
    cmp rdx, r9
    jb heap_mark_invalid
    cmp rdx, QWORD PTR [rcx+24]
    ja heap_mark_invalid
    sub rdx, 32
    mov eax, DWORD PTR [rdx+8]
    and eax, 0FFFFFFFDh
    cmp eax, OBJECT_MAGIC
    jne heap_mark_invalid
    mov r9, QWORD PTR [rdx]
    cmp r9, 32
    jb heap_mark_invalid
    test r9b, 15
    jnz heap_mark_invalid
    add r9, rdx
    jc heap_mark_invalid
    cmp r9, QWORD PTR [rcx+24]
    ja heap_mark_invalid
    test DWORD PTR [rdx+8], 2
    jnz heap_mark_ok
    mov r10, QWORD PTR [r8]
    cmp r10, QWORD PTR [rcx+40]
    jae heap_mark_invalid
    mov r11, QWORD PTR [rcx+32]
    mov QWORD PTR [r11+r10*8], rdx
    inc QWORD PTR [r8]
    or DWORD PTR [rdx+8], 2
heap_mark_ok:
    xor eax, eax
    ret
heap_mark_invalid:
    mov eax, 1
    ret
heap_mark ENDP

boom_heap_collect PROC FRAME
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
    test rcx, rcx
    jz heap_collect_invalid
    cmp DWORD PTR [rcx], HEAP_MAGIC
    jne heap_collect_invalid
    cmp DWORD PTR [rcx+4], 1
    jne heap_collect_invalid
    cmp r8d, 1048576
    ja heap_collect_invalid
    test r8d, r8d
    jz heap_roots_valid
    test rdx, rdx
    jz heap_collect_invalid
heap_roots_valid:
    mov rbx, rcx
    mov r12, rdx
    mov r13d, r8d
    call heap_registry_lock
    cmp QWORD PTR [rbx+112], 0
    jne heap_collect_busy
    cmp QWORD PTR [rbx+96], 0
    jne heap_collect_busy
    ; Idle monitor records no longer retain Java objects and become ordinary garbage.
    mov QWORD PTR [rbx+120], 0
    mov rcx, rbx
    call heap_lock
    lea rsi, [rbx+128]
heap_clear_marks:
    cmp rsi, QWORD PTR [rbx+24]
    jae heap_mark_roots
    and DWORD PTR [rsi+8], 0FFFFFFFDh
    add rsi, QWORD PTR [rsi]
    jmp heap_clear_marks
heap_mark_roots:
    mov QWORD PTR [rsp+32], 0
    xor edi, edi
heap_next_root:
    cmp edi, r13d
    jae heap_walk_start
    mov rcx, rbx
    mov rdx, QWORD PTR [r12+rdi*8]
    lea r8, [rsp+32]
    call heap_mark
    test eax, eax
    jnz heap_collect_unlock_invalid
    inc edi
    jmp heap_next_root
heap_walk_start:
    xor r14d, r14d
heap_next_object:
    cmp r14, QWORD PTR [rsp+32]
    jae heap_sweep_start
    mov rax, QWORD PTR [rbx+32]
    mov r13, QWORD PTR [rax+r14*8]
    xor r15d, r15d
heap_next_reference:
    cmp r15d, DWORD PTR [r13+12]
    jae heap_object_scanned
    mov rcx, rbx
    mov rdx, QWORD PTR [r13+r15*8+32]
    lea r8, [rsp+32]
    call heap_mark
    test eax, eax
    jnz heap_collect_unlock_invalid
    inc r15d
    jmp heap_next_reference
heap_object_scanned:
    inc r14
    jmp heap_next_object
heap_sweep_start:
    xor r12d, r12d
    xor r13d, r13d
    xor r14d, r14d
    xor r15d, r15d
    lea rsi, [rbx+128]
heap_sweep_block:
    cmp rsi, QWORD PTR [rbx+24]
    jae heap_coalesce_start
    mov r10, QWORD PTR [rsi]
    test DWORD PTR [rsi+8], 1
    jz heap_sweep_next
    test DWORD PTR [rsi+8], 2
    jz heap_reclaim_block
    and DWORD PTR [rsi+8], 0FFFFFFFDh
    add r12, r10
    inc r13
    jmp heap_sweep_next
heap_reclaim_block:
    add r15, r10
    inc r14
    mov QWORD PTR [rsi+8], 0
    mov QWORD PTR [rsi+16], 0
    mov QWORD PTR [rsi+24], 0
heap_sweep_next:
    add rsi, r10
    jmp heap_sweep_block
heap_coalesce_start:
    mov QWORD PTR [rbx+88], 0
    lea rsi, [rbx+128]
heap_coalesce_block:
    cmp rsi, QWORD PTR [rbx+24]
    jae heap_collect_stats
    lea rdi, [rsi]
    add rdi, QWORD PTR [rsi]
    cmp DWORD PTR [rsi+8], 0
    jne heap_coalesce_next
    cmp QWORD PTR [rbx+88], 0
    jne heap_merge_next
    mov QWORD PTR [rbx+88], rsi
heap_merge_next:
    cmp rdi, QWORD PTR [rbx+24]
    jae heap_coalesce_next
    cmp DWORD PTR [rdi+8], 0
    jne heap_coalesce_next
    mov rax, QWORD PTR [rdi]
    add QWORD PTR [rsi], rax
    add rdi, rax
    jmp heap_merge_next
heap_coalesce_next:
    mov rsi, rdi
    jmp heap_coalesce_block
heap_collect_stats:
    mov QWORD PTR [rbx+48], r12
    mov QWORD PTR [rbx+56], r13
    inc QWORD PTR [rbx+72]
    mov QWORD PTR [rbx+80], r15
    mov rax, r14
    mov DWORD PTR [rbx+8], 0
    mov DWORD PTR [rbx+104], 0
    jmp heap_collect_done
heap_collect_unlock_invalid:
    mov DWORD PTR [rbx+8], 0
heap_collect_busy:
    mov DWORD PTR [rbx+104], 0
heap_collect_invalid:
    mov rax, -1
heap_collect_done:
    add rsp, 48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_heap_collect ENDP

boom_heap_destroy PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    test rcx, rcx
    jz heap_destroy_invalid
    cmp DWORD PTR [rcx], HEAP_MAGIC
    jne heap_destroy_invalid
    cmp DWORD PTR [rcx+4], 1
    jne heap_destroy_invalid
    cmp QWORD PTR [rcx+112], 0
    jne heap_destroy_invalid
    cmp DWORD PTR [rcx+104], 0
    jne heap_destroy_invalid
    xor edx, edx
    mov r8d, 08000h
    call VirtualFree
    jmp heap_destroy_done
heap_destroy_invalid:
    xor eax, eax
heap_destroy_done:
    add rsp, 40
    ret
boom_heap_destroy ENDP
END
