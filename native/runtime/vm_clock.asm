; VM-native System clock services. All arithmetic and execution are MASM.
; Game ABI: Context16* RCX, argv64* RDX -> raw Java long RAX.
; Native clocks are VM services; this does not initialize Java System properties,
; standard streams or the rest of System's Java bootstrap sequence.
option casemap:none
EXTERN GetSystemTimePreciseAsFileTime:PROC
EXTERN QueryPerformanceCounter:PROC
EXTERN QueryPerformanceFrequency:PROC
PUBLIC boom_vm_current_time_millis
PUBLIC boom_vm_nano_time
PUBLIC boom_vm_filetime_to_millis
PUBLIC boom_vm_counter_to_nanos
.code
; Exact mathematical floor for all unsigned FILETIME inputs, including pre-1970.
boom_vm_filetime_to_millis PROC
    mov rax, rcx
    xor edx, edx
    mov r10d, 10000
    div r10
    mov r10, 11644473600000
    sub rax, r10
    ret
boom_vm_filetime_to_millis ENDP

; Unsigned counter ticks RCX / nonzero frequency RDX -> nanoseconds modulo 2^64.
; Quotient/remainder decomposition avoids overflowing a direct 64-bit multiply,
; and still handles the full 128-bit remainder product exactly.
boom_vm_counter_to_nanos PROC
    mov r8, rdx
    mov rax, rcx
    xor edx, edx
    div r8
    mov r9, rax
    mov rax, rdx
    mov r10d, 1000000000
    mul r10
    div r8
    imul r9, r10
    add rax, r9
    ret
boom_vm_counter_to_nanos ENDP

boom_vm_current_time_millis PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    lea rcx, [rsp+32]
    call GetSystemTimePreciseAsFileTime
    mov rcx, QWORD PTR [rsp+32]
    call boom_vm_filetime_to_millis
    add rsp, 40
    ret
boom_vm_current_time_millis ENDP

boom_vm_nano_time PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp, 48
    .allocstack 48
    .endprolog
    mov rbx, rcx
    lea rcx, [rsp+40]
    call QueryPerformanceFrequency
    test eax, eax
    jz vm_clock_invalid
    cmp QWORD PTR [rsp+40], 0
    jle vm_clock_invalid
    lea rcx, [rsp+32]
    call QueryPerformanceCounter
    test eax, eax
    jz vm_clock_invalid
    mov rcx, QWORD PTR [rsp+32]
    mov rdx, QWORD PTR [rsp+40]
    call boom_vm_counter_to_nanos
    jmp vm_clock_done
vm_clock_invalid:
    mov DWORD PTR [rbx], 7 ; violated native platform/binding precondition
    xor eax, eax
vm_clock_done:
    add rsp, 48
    pop rbx
    ret
boom_vm_nano_time ENDP
END
