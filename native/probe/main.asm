; Standalone assembly executable. Runs the generated ASM kernel with the ASM
; multicore runtime, without a Rust/C#/Java execution host or any CRT.
option casemap:none
EXTERN boom_entry:PROC
EXTERN boom_parallel_i32:PROC
EXTERN GetStdHandle:PROC
EXTERN WriteFile:PROC
EXTERN ExitProcess:PROC
PUBLIC boom_probe_main
COUNT EQU 65539
.data
success db '{"passed":true,"cases":65539,"worker_budgets":[1,2,4,8],"game_runtime":"assembly","kernel":"assembly","full_game_ready":false}',13,10
SUCCESS_LENGTH EQU $-success
failure db '{"passed":false,"error":"assembly runtime mismatch"}',13,10
FAILURE_LENGTH EQU $-failure
.data?
ALIGN 16
inputs DWORD (COUNT*4) DUP (?)
outputs DWORD COUNT DUP (?)
expected DWORD COUNT DUP (?)
written DWORD ?
.code
boom_probe_main PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    sub rsp, 56
    .allocstack 56
    .endprolog
    xor esi, esi
    lea rbx, inputs
    lea rdi, expected
prepare_item:
    imul ecx, esi, 1664525
    add ecx, 1013904223
    mov edx, 1013904223
    mov r8d, 255
    mov r9d, 1024
    mov DWORD PTR [rbx], ecx
    mov DWORD PTR [rbx+4], edx
    mov DWORD PTR [rbx+8], r8d
    mov DWORD PTR [rbx+12], r9d
    call boom_entry
    mov DWORD PTR [rdi+rsi*4], eax
    add rbx, 16
    inc esi
    cmp esi, COUNT
    jb prepare_item
    mov r12d, 1
test_budget:
    lea rcx, boom_entry
    lea rdx, inputs
    lea r8, outputs
    mov r9d, COUNT
    mov DWORD PTR [rsp+32], r12d
    call boom_parallel_i32
    test eax, eax
    jnz test_failed
    lea rbx, outputs
    xor esi, esi
compare_item:
    mov eax, DWORD PTR [rbx+rsi*4]
    cmp eax, DWORD PTR [rdi+rsi*4]
    jne test_failed
    inc esi
    cmp esi, COUNT
    jb compare_item
    shl r12d, 1
    cmp r12d, 8
    jbe test_budget
    xor edi, edi
    lea rbx, success
    mov esi, SUCCESS_LENGTH
    jmp print_result
test_failed:
    mov edi, 1
    lea rbx, failure
    mov esi, FAILURE_LENGTH
print_result:
    mov ecx, -11
    call GetStdHandle
    mov rcx, rax
    mov rdx, rbx
    mov r8d, esi
    lea r9, written
    mov QWORD PTR [rsp+32], 0
    call WriteFile
    mov ecx, edi
    call ExitProcess
    int 3
boom_probe_main ENDP
END
