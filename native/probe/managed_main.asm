; Integrated assembly bootstrap test, not a Minecraft client.
; Entry, compiled numeric method, persistent workers, heap and GC are assembly.
option casemap:none
IFDEF ARRAY_KERNEL
HEAP_KERNEL EQU 1
ENDIF
IFDEF OBJECT_KERNEL
HEAP_KERNEL EQU 1
ENDIF
IFDEF REFERENCE_KERNEL
HEAP_KERNEL EQU 1
ENDIF
IFDEF OBJECT_PROGRAM_KERNEL
HEAP_KERNEL EQU 1
ENDIF
EXTERN boom_entry:PROC
IFDEF HEAP_KERNEL
EXTERN boom_bind_heap:PROC
ENDIF
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
PUBLIC boom_managed_main
COUNT EQU 65539
IFDEF OBJECT_PROGRAM_KERNEL
TEMP_ALLOCATIONS EQU COUNT*2
ELSE
IFDEF REFERENCE_KERNEL
TEMP_ALLOCATIONS EQU COUNT*2
ELSE
TEMP_ALLOCATIONS EQU COUNT
ENDIF
ENDIF
.data
IFDEF HEAP_KERNEL
IFDEF OBJECT_PROGRAM_KERNEL
ok db '{"passed":true,"records":65539,"workers":8,"cross_class_objects":true,"persistent_pool":true,"heap_and_gc":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ELSE
IFDEF REFERENCE_KERNEL
ok db '{"passed":true,"records":65539,"workers":8,"translated_java_reference_arrays":true,"persistent_pool":true,"heap_and_gc":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ELSE
IFDEF OBJECT_KERNEL
ok db '{"passed":true,"records":65539,"workers":8,"translated_java_objects":true,"persistent_pool":true,"heap_and_gc":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ELSE
ok db '{"passed":true,"records":65539,"workers":8,"translated_java_arrays":true,"persistent_pool":true,"heap_and_gc":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ENDIF
ENDIF
ENDIF
ELSE
IFDEF PROGRAM_KERNEL
ok db '{"passed":true,"records":65539,"workers":8,"linked_java_classes":true,"persistent_pool":true,"heap_and_gc":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ELSE
ok db '{"passed":true,"records":65539,"workers":8,"persistent_pool":true,"heap_and_gc":true,"execution_runtime":"assembly","full_game_ready":false}',13,10
ENDIF
ENDIF
OK_LENGTH EQU $-ok
failed db '{"passed":false,"stage":"assembly bootstrap"}',13,10
FAIL_LENGTH EQU $-failed
roots QWORD 3 DUP (0)
.data?
context QWORD 2 DUP (?)
written DWORD ?
.code
boom_managed_main PROC FRAME
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
    xor ebx, ebx
    xor r12d, r12d
    mov ecx, 33554432
    call boom_heap_create
    test rax, rax
    jz bootstrap_fail
    mov rbx, rax
IFDEF HEAP_KERNEL
    mov rcx, rbx
    call boom_bind_heap
    cmp eax, 1
    jne bootstrap_fail
ENDIF
    mov rcx, rbx
    mov edx, COUNT*128
    xor r8d, r8d
    mov r9d, 1
    call boom_heap_alloc
    test rax, rax
    jz bootstrap_fail
    mov r13, rax
    mov QWORD PTR [roots], rax
    mov rcx, rbx
    mov edx, COUNT*32
    xor r8d, r8d
    mov r9d, 2
    call boom_heap_alloc
    test rax, rax
    jz bootstrap_fail
    mov r14, rax
    mov QWORD PTR [roots+8], rax
    mov rcx, rbx
    mov edx, COUNT*8
    xor r8d, r8d
    mov r9d, 3
    call boom_heap_alloc
    test rax, rax
    jz bootstrap_fail
    mov r15, rax
    mov QWORD PTR [roots+16], rax
    xor esi, esi
prepare_record:
    mov rdi, rsi
    shl rdi, 7
    add rdi, r13
IFDEF HEAP_KERNEL
    mov eax, esi
    xor edx, edx
    mov ecx, 33
    div ecx
    mov QWORD PTR [rdi], rdx
    imul eax, esi, 1664525
    add eax, 1013904223
    mov QWORD PTR [rdi+8], rax
ELSE
    mov rax, 00123456789ABCDEFh
    imul rax, rsi
    mov r10, 0FEDCBA9876543210h
    add rax, r10
    mov QWORD PTR [rdi], rax
    mov QWORD PTR [rdi+8], 256
ENDIF
    lea rcx, context
    mov rdx, rdi
    call boom_entry
    cmp DWORD PTR [context], 0
    jne bootstrap_fail
    mov QWORD PTR [r15+rsi*8], rax
    inc esi
    cmp esi, COUNT
    jb prepare_record
IFDEF HEAP_KERNEL
    mov rcx, rbx
    lea rdx, roots
    mov r8d, 3
    call boom_heap_collect
    cmp rax, TEMP_ALLOCATIONS
    jne bootstrap_fail
ENDIF
    mov ecx, 8
    call boom_pool_create
    test rax, rax
    jz bootstrap_fail
    mov r12, rax
    mov rcx, r12
    lea rdx, boom_entry
    mov r8, r13
    mov r9, r14
    mov DWORD PTR [rsp+32], COUNT
    call boom_pool_run
    test eax, eax
    jnz bootstrap_fail
    xor esi, esi
compare_record:
    mov rdi, rsi
    shl rdi, 5
    add rdi, r14
    mov rax, QWORD PTR [r15+rsi*8]
    cmp QWORD PTR [rdi], rax
    jne bootstrap_fail
    cmp QWORD PTR [rdi+8], 0
    jne bootstrap_fail
    cmp QWORD PTR [rdi+16], 0
    jne bootstrap_fail
    cmp QWORD PTR [rdi+24], 0
    jne bootstrap_fail
    inc esi
    cmp esi, COUNT
    jb compare_record
    mov rcx, r12
    call boom_pool_destroy
    test eax, eax
    jnz bootstrap_fail
    xor r12d, r12d
IFDEF HEAP_KERNEL
    mov rcx, rbx
    lea rdx, roots
    mov r8d, 3
    call boom_heap_collect
    cmp rax, TEMP_ALLOCATIONS
    jne bootstrap_fail
ENDIF
    mov rcx, rbx
    mov edx, 4096
    xor r8d, r8d
    mov r9d, 4
    call boom_heap_alloc
    test rax, rax
    jz bootstrap_fail
    mov rcx, rbx
    lea rdx, roots
    mov r8d, 3
    call boom_heap_collect
    cmp rax, 1
    jne bootstrap_fail
    mov rcx, rbx
    xor edx, edx
    xor r8d, r8d
    call boom_heap_collect
    cmp rax, 3
    jne bootstrap_fail
    mov rcx, rbx
    call boom_heap_destroy
    test eax, eax
    jz bootstrap_fail
    xor ebx, ebx
    xor edi, edi
    lea r13, ok
    mov r14d, OK_LENGTH
    jmp bootstrap_print
bootstrap_fail:
    mov edi, 1
    test r12, r12
    jz bootstrap_free_heap
    mov rcx, r12
    call boom_pool_destroy
bootstrap_free_heap:
    test rbx, rbx
    jz bootstrap_failed_text
    mov rcx, rbx
    call boom_heap_destroy
bootstrap_failed_text:
    lea r13, failed
    mov r14d, FAIL_LENGTH
bootstrap_print:
    mov ecx, -11
    call GetStdHandle
    mov rcx, rax
    mov rdx, r13
    mov r8d, r14d
    lea r9, written
    mov QWORD PTR [rsp+32], 0
    call WriteFile
    mov ecx, edi
    call ExitProcess
    int 3
boom_managed_main ENDP
END
