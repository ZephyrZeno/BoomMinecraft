; Game-side runtime: handwritten x86-64 MASM, no Rust/C runtime and no JVM.
; boom_parallel_i32(kernel, input_records, output, count, jobs) -> Win32 error/0.
; kernel: int32 kernel(int32,int32,int32,int32), pure and reentrant.
; Each input record is 16 bytes. Jobs 1..64, count <= 16,777,216.
; All buffers remain owned by the caller until every worker has joined.
; boom_parallel_numeric: same five arguments, but 128-byte argv records and
; 32-byte outputs {u64 value; Context16 exception; u64 reserved}. Each item owns
; its exception context; neither failures nor FP state leak into another item.
option casemap:none
EXTERN CreateThread:PROC
EXTERN WaitForSingleObject:PROC
EXTERN CloseHandle:PROC
PUBLIC boom_parallel_i32
PUBLIC boom_parallel_numeric
PUBLIC boom_worker
.code

boom_worker PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    sub rsp, 40
    .allocstack 40
    .endprolog
    mov rbx, rcx
claim_chunk:
    mov eax, 64
    lock xadd DWORD PTR [rbx+28], eax
    cmp eax, DWORD PTR [rbx+24]
    jae worker_done
    mov esi, eax
    lea edi, [eax+64]
    cmp edi, DWORD PTR [rbx+24]
    cmova edi, DWORD PTR [rbx+24]
map_item:
    cmp DWORD PTR [rbx+32], 0
    jne map_numeric_item
    mov r12d, esi
    shl r12, 4
    add r12, QWORD PTR [rbx+8]
    mov ecx, DWORD PTR [r12]
    mov edx, DWORD PTR [r12+4]
    mov r8d, DWORD PTR [r12+8]
    mov r9d, DWORD PTR [r12+12]
    call QWORD PTR [rbx]
    mov rdx, QWORD PTR [rbx+16]
    mov DWORD PTR [rdx+rsi*4], eax
    jmp mapped_item
map_numeric_item:
    mov rdx, rsi
    shl rdx, 5
    add rdx, QWORD PTR [rbx+16]
    mov QWORD PTR [rdx+8], 0
    mov QWORD PTR [rdx+16], 0
    mov QWORD PTR [rdx+24], 0
    lea rcx, [rdx+8]
    mov r12, rsi
    shl r12, 7
    add r12, QWORD PTR [rbx+8]
    mov rdx, r12
    call QWORD PTR [rbx]
    mov rdx, rsi
    shl rdx, 5
    add rdx, QWORD PTR [rbx+16]
    mov QWORD PTR [rdx], rax
mapped_item:
    inc esi
    cmp esi, edi
    jb map_item
    jmp claim_chunk
worker_done:
    xor eax, eax
    add rsp, 40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_worker ENDP

boom_parallel_i32 PROC
    xor r10d, r10d
    jmp boom_parallel_common
boom_parallel_i32 ENDP

boom_parallel_numeric PROC
    mov r10d, 1
    jmp boom_parallel_common
boom_parallel_numeric ENDP

boom_parallel_common PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    ; shadow/args 0..47, context/mode 48..87, 63 handles 96..599.
    sub rsp, 608
    .allocstack 608
    .endprolog
    mov DWORD PTR [rsp+80], r10d
    mov eax, DWORD PTR [rsp+672] ; fifth argument, original rsp+40
    test eax, eax
    jz invalid_argument
    cmp eax, 64
    ja invalid_argument
    cmp r9d, 16777216
    ja invalid_argument
    test r9d, r9d
    jz empty_success
    test rcx, rcx
    jz invalid_argument
    test rdx, rdx
    jz invalid_argument
    test r8, r8
    jz invalid_argument
    ; Disallow overlapping input/output ranges and pointer arithmetic wrap.
    mov r10d, r9d
    mov r11d, r9d
    cmp DWORD PTR [rsp+80], 0
    jne numeric_ranges
    shl r10, 4
    shl r11, 2
    jmp check_ranges
numeric_ranges:
    shl r10, 7
    shl r11, 5
check_ranges:
    add r10, rdx
    jc invalid_argument
    add r11, r8
    jc invalid_argument
    cmp rdx, r11
    jae disjoint_buffers
    cmp r8, r10
    jb invalid_argument
disjoint_buffers:
    mov QWORD PTR [rsp+48], rcx
    mov QWORD PTR [rsp+56], rdx
    mov QWORD PTR [rsp+64], r8
    mov DWORD PTR [rsp+72], r9d
    mov DWORD PTR [rsp+76], 0
    ; No more workers than available chunks; caller participates as one worker.
    lea ecx, [r9d+63]
    shr ecx, 6
    cmp eax, ecx
    cmova eax, ecx
    mov edi, eax
    dec edi
    xor esi, esi
    lea rbx, [rsp+48]
spawn_worker:
    cmp esi, edi
    jae run_on_caller
    xor ecx, ecx
    xor edx, edx
    lea r8, boom_worker
    mov r9, rbx
    mov QWORD PTR [rsp+32], 0
    mov QWORD PTR [rsp+40], 0
    call CreateThread
    test rax, rax
    ; Resource exhaustion falls back to the participating caller, without lost work.
    jz run_on_caller
    mov QWORD PTR [rsp+rsi*8+96], rax
    inc esi
    jmp spawn_worker
run_on_caller:
    mov rcx, rbx
    call boom_worker
join_worker:
    test esi, esi
    jz empty_success
    dec esi
    mov rcx, QWORD PTR [rsp+rsi*8+96]
    mov edx, -1
    call WaitForSingleObject
    ; These handles are private and never closed until after their wait.
    mov rcx, QWORD PTR [rsp+rsi*8+96]
    call CloseHandle
    jmp join_worker
invalid_argument:
    mov eax, 87 ; ERROR_INVALID_PARAMETER; no work has started.
    jmp map_done
empty_success:
    xor eax, eax
map_done:
    add rsp, 608
    pop rdi
    pop rsi
    pop rbx
    ret
boom_parallel_common ENDP
END
