; Standalone integration of translated static-array initialization and workers.
; This is a runtime probe, not Minecraft. All execution in this EXE is assembly.
option casemap:none
EXTERN boom_entry:PROC
EXTERN boom_bind_heap:PROC
EXTERN boom_get_static_roots:PROC
EXTERN boom_get_static_field:PROC
EXTERN boom_get_class_descriptor:PROC
EXTERN boom_pool_create:PROC
EXTERN boom_pool_run:PROC
EXTERN boom_pool_destroy:PROC
EXTERN boom_heap_create:PROC
EXTERN boom_heap_alloc:PROC
EXTERN boom_heap_collect:PROC
EXTERN boom_heap_destroy:PROC
EXTERN GetStdHandle:PROC
EXTERN WriteFile:PROC
EXTERN ExitProcess:PROC
PUBLIC boom_state_main
COUNT EQU 65539
IFDEF TYPE_KERNEL
MIRROR_KERNEL EQU 1
ENDIF
IFDEF CONCAT_KERNEL
MIRROR_KERNEL EQU 1
MIRROR_ROOT_COUNT EQU 1
ENDIF
.data
IFDEF TYPE_KERNEL
ok db '{"passed":true,"records":65539,"workers":8,"repeats":3,"runtime_type_checks":true,"getclass_identity":true,"mirror_and_literal_roots_retained":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ELSEIFDEF CONCAT_KERNEL
ok db '{"passed":true,"records":65539,"workers":8,"repeats":3,"dynamic_strings":true,"temporary_strings_reclaimed":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ELSEIFDEF MIRROR_KERNEL
ok db '{"passed":true,"records":65539,"workers":8,"repeats":3,"class_mirrors":true,"mirror_and_name_roots_retained":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ELSEIFDEF STRING_KERNEL
ok db '{"passed":true,"records":65539,"workers":8,"repeats":3,"string_literals":true,"intern_roots_retained":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ELSE
ok db '{"passed":true,"records":65539,"workers":8,"repeats":3,"class_initialization":true,"initializer_runs":1,"static_roots_retained":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ENDIF
OK_LENGTH EQU $-ok
failed db '{"passed":false,"stage":"class state bootstrap"}',13,10
FAIL_LENGTH EQU $-failed
IFDEF MIRROR_KERNEL
roots QWORD (MIRROR_ROOT_COUNT+3) DUP (0)
ELSE
roots QWORD 5 DUP (0)
ENDIF
context QWORD 2 DUP (0)
root_count DWORD 0
written DWORD 0
.code
boom_state_main PROC FRAME
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
    sub rsp, 64
    .allocstack 64
    .endprolog
    xor ebx, ebx
    xor r12d, r12d
    mov ecx, 33554432
    call boom_heap_create
    test rax, rax
    jz state_fail
    mov rbx, rax
    mov rcx, rbx
    call boom_bind_heap
    cmp eax, 1
    jne state_fail
    mov rcx, rbx
    mov edx, COUNT*128
    xor r8d, r8d
    mov r9d, 1
    call boom_heap_alloc
    test rax, rax
    jz state_fail
    mov r13, rax
    mov QWORD PTR [roots], rax
    mov rcx, rbx
    mov edx, COUNT*32
    xor r8d, r8d
    mov r9d, 2
    call boom_heap_alloc
    test rax, rax
    jz state_fail
    mov r14, rax
    mov QWORD PTR [roots+8], rax
    mov rcx, rbx
    mov edx, COUNT*8
    xor r8d, r8d
    mov r9d, 3
    call boom_heap_alloc
    test rax, rax
    jz state_fail
    mov r15, rax
    mov QWORD PTR [roots+16], rax
    xor esi, esi
state_prepare:
    mov rdi, rsi
    shl rdi, 7
    add rdi, r13
    mov eax, esi
    and eax, 31
    mov QWORD PTR [rdi], rax
    imul eax, esi, 1664525
    add eax, 1013904223
    mov QWORD PTR [rdi+8], rax
    lea rcx, context
    mov rdx, rdi
    call boom_entry
    cmp DWORD PTR [context], 0
    jne state_fail
    mov QWORD PTR [r15+rsi*8], rax
    inc esi
    cmp esi, COUNT
    jb state_prepare
    lea rcx, root_count
    call boom_get_static_roots
IFDEF MIRROR_KERNEL
    cmp DWORD PTR [root_count], MIRROR_ROOT_COUNT
    jne state_fail
    mov rsi, rax
    lea rdi, [roots+24]
    mov ecx, MIRROR_ROOT_COUNT
    rep movsq
ELSE
IFDEF STRING_KERNEL
    cmp DWORD PTR [root_count], 1
ELSE
    cmp DWORD PTR [root_count], 2
ENDIF
    jne state_fail
    mov r10, QWORD PTR [rax]
    test r10, r10
    jz state_fail
    mov QWORD PTR [roots+24], r10
IFNDEF STRING_KERNEL
    cmp r10, QWORD PTR [rax+8]
    jne state_fail
    mov QWORD PTR [roots+32], r10
ENDIF
ENDIF
    mov rcx, rbx
    lea rdx, roots
IFDEF MIRROR_KERNEL
    mov r8d, MIRROR_ROOT_COUNT+3
ELSEIFDEF STRING_KERNEL
    mov r8d, 4
ELSE
    mov r8d, 5
ENDIF
    call boom_heap_collect
IFDEF CONCAT_KERNEL
    cmp rax, COUNT*2
ELSE
    test rax, rax
ENDIF
    jne state_fail
IFDEF CONCAT_KERNEL
    cmp QWORD PTR [rbx+56], 3
ELSEIFDEF MIRROR_KERNEL
    cmp QWORD PTR [rbx+56], 6
ELSEIFDEF STRING_KERNEL
    cmp QWORD PTR [rbx+56], 5
ELSE
    cmp QWORD PTR [rbx+56], 4
ENDIF
    jne state_fail
    mov ecx, 8
    call boom_pool_create
    test rax, rax
    jz state_fail
    mov r12, rax
    mov DWORD PTR [rsp+48], 3
state_batch:
    mov rcx, r12
    lea rdx, boom_entry
    mov r8, r13
    mov r9, r14
    mov DWORD PTR [rsp+32], COUNT
    call boom_pool_run
    test eax, eax
    jnz state_fail
    xor esi, esi
state_compare:
    mov rdi, rsi
    shl rdi, 5
    add rdi, r14
    mov rax, QWORD PTR [r15+rsi*8]
    cmp rax, QWORD PTR [rdi]
    jne state_fail
    cmp QWORD PTR [rdi+8], 0
    jne state_fail
    cmp QWORD PTR [rdi+16], 0
    jne state_fail
    cmp QWORD PTR [rdi+24], 0
    jne state_fail
    inc esi
    cmp esi, COUNT
    jb state_compare
    mov rcx, rbx
    lea rdx, roots
IFDEF MIRROR_KERNEL
    mov r8d, MIRROR_ROOT_COUNT+3
ELSEIFDEF STRING_KERNEL
    mov r8d, 4
ELSE
    mov r8d, 5
ENDIF
    call boom_heap_collect
IFDEF CONCAT_KERNEL
    cmp rax, COUNT*2
ELSE
    test rax, rax
ENDIF
    jne state_fail
IFDEF CONCAT_KERNEL
    cmp QWORD PTR [rbx+56], 3
ELSEIFDEF MIRROR_KERNEL
    cmp QWORD PTR [rbx+56], 6
ELSEIFDEF STRING_KERNEL
    cmp QWORD PTR [rbx+56], 5
ELSE
    cmp QWORD PTR [rbx+56], 4
ENDIF
    jne state_fail
    dec DWORD PTR [rsp+48]
    jnz state_batch
IFNDEF MIRROR_KERNEL
IFNDEF STRING_KERNEL
    mov ecx, TABLE_CLASS_ID
    mov edx, TABLE_RUNS_INDEX
    call boom_get_static_field
    test rax, rax
    jz state_fail
    cmp DWORD PTR [rax], 1
    jne state_fail
    mov ecx, TABLE_CLASS_ID
    call boom_get_class_descriptor
    test rax, rax
    jz state_fail
    cmp DWORD PTR [rax+8], 2
    jne state_fail
    cmp DWORD PTR [rax+12], 0
    jne state_fail
ENDIF
ENDIF
    mov rcx, r12
    call boom_pool_destroy
    test eax, eax
    jnz state_fail
    xor r12d, r12d
    lea rcx, root_count
    call boom_get_static_roots
    mov rdx, rax
    mov rcx, rbx
    mov r8d, DWORD PTR [root_count]
    call boom_heap_collect
    cmp rax, 3
    jne state_fail
IFDEF CONCAT_KERNEL
    cmp QWORD PTR [rbx+56], 0
ELSEIFDEF MIRROR_KERNEL
    cmp QWORD PTR [rbx+56], 3
ELSEIFDEF STRING_KERNEL
    cmp QWORD PTR [rbx+56], 2
ELSE
    cmp QWORD PTR [rbx+56], 1
ENDIF
    jne state_fail
    mov rcx, rbx
    call boom_heap_destroy
    xor ebx, ebx
    test eax, eax
    jz state_fail
    mov ecx, -11
    call GetStdHandle
    mov rcx, rax
    lea rdx, ok
    mov r8d, OK_LENGTH
    lea r9, written
    mov QWORD PTR [rsp+32], 0
    call WriteFile
    xor ecx, ecx
    call ExitProcess
state_fail:
    test r12, r12
    jz state_no_pool
    mov rcx, r12
    call boom_pool_destroy
state_no_pool:
    test rbx, rbx
    jz state_no_heap
    mov rcx, rbx
    call boom_heap_destroy
state_no_heap:
    mov ecx, -11
    call GetStdHandle
    mov rcx, rax
    lea rdx, failed
    mov r8d, FAIL_LENGTH
    lea r9, written
    mov QWORD PTR [rsp+32], 0
    call WriteFile
    mov ecx, 1
    call ExitProcess
    add rsp, 64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_state_main ENDP
END
