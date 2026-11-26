; Original VM.initialize registration contract, and VM.getNanoTimeAdjustment.
; Pool32: magic0 ABI4 state8 count12 target*16 reserved24. State0/2.
; ABI1 prelinked target; ABI2 installs the real runtime-DLL entry at registration,
; avoiding a caller-DLL import thunk being mistaken for the implementation.
; Context16/32 shared prefix RCX, argv64 RDX, pool R8, operation R9D -> long RAX.
; Registration publishes exactly one prelinked target; no Java boot-level writes.
option casemap:none
EXTERN GetSystemTimePreciseAsFileTime:PROC
PUBLIC boom_vm_native
PUBLIC boom_vm_nano_adjustment
PUBLIC boom_vm_adjustment_from_filetime
.code
boom_vm_native PROC
    test rcx,rcx
    jz vm_reg_zero
    cmp DWORD PTR [rcx],0
    jne vm_reg_zero
    test r8,r8
    jz vm_reg_bad
    cmp DWORD PTR [r8],0564D5247h
    jne vm_reg_bad
    cmp DWORD PTR [r8+4],1
    je vm_reg_header
    cmp DWORD PTR [r8+4],2
    jne vm_reg_bad
vm_reg_header:
    cmp DWORD PTR [r8+12],1
    jne vm_reg_bad
    cmp QWORD PTR [r8+24],0
    jne vm_reg_bad
    lea r11,boom_vm_nano_adjustment
    cmp QWORD PTR [r8+16],r11
    je vm_reg_target_ready
    cmp DWORD PTR [r8+4],2
    jne vm_reg_bad
    test r9d,r9d
    jnz vm_reg_bad
    cmp DWORD PTR [r8+8],0
    je vm_reg_install_target
    cmp DWORD PTR [r8+8],2
    jne vm_reg_bad
    cmp QWORD PTR [r8+16],r11
    jne vm_reg_bad
    jmp vm_reg_target_ready
vm_reg_install_target:
    xor eax,eax
    lock cmpxchg QWORD PTR [r8+16],r11
    test rax,rax
    jz vm_reg_target_ready
    cmp rax,r11
    jne vm_reg_bad
vm_reg_target_ready:
    mov eax,DWORD PTR [r8+8]
    test eax,eax
    jz vm_reg_state_ok
    cmp eax,2
    jne vm_reg_bad
vm_reg_state_ok:
    test r9d,r9d
    jz vm_reg_publish
    cmp r9d,1
    jne vm_reg_bad
    cmp eax,2
    jne vm_reg_bad
    test rdx,rdx
    jz vm_reg_bad
    jmp QWORD PTR [r8+16]
vm_reg_publish:
    mov eax,2
    xchg DWORD PTR [r8+8],eax
vm_reg_zero:
    xor eax,eax
    ret
vm_reg_bad:
    mov DWORD PTR [rcx],7
    jmp vm_reg_zero
boom_vm_native ENDP

; Pure arithmetic helper: unsigned FILETIME RCX, signed offset seconds RDX.
; The valid interval is strict: -2^32 < epochSeconds-offset < 2^32.
; Checked subtraction prevents an extreme offset wrapping into the valid range.
boom_vm_adjustment_from_filetime PROC
    mov r8,rdx
    mov rax,rcx
    xor edx,edx
    mov r10d,10000000
    div r10
    mov r9,rdx
    imul r9,r9,100
    mov r10,11644473600
    sub rax,r10
    sub rax,r8
    jo vm_adjust_far
    mov r10,4294967296
    cmp rax,r10
    jge vm_adjust_far
    neg r10
    cmp rax,r10
    jle vm_adjust_far
    imul rax,rax,1000000000
    add rax,r9
    ret
vm_adjust_far:
    mov rax,-1
    ret
boom_vm_adjustment_from_filetime ENDP

boom_vm_nano_adjustment PROC FRAME
    sub rsp,56
    .allocstack 56
    .endprolog
    mov rax,QWORD PTR [rdx]
    mov QWORD PTR [rsp+40],rax
    lea rcx,[rsp+32]
    call GetSystemTimePreciseAsFileTime
    mov rcx,QWORD PTR [rsp+32]
    mov rdx,QWORD PTR [rsp+40]
    call boom_vm_adjustment_from_filetime
    add rsp,56
    ret
boom_vm_nano_adjustment ENDP
; This native image deliberately supports Java 21's finalization-disabled policy.
; It is not an enabled-finalizer implementation. The policy is recorded in the
; AOT binding; original Finalizer Java bytecode still executes its own branches.
PUBLIC boom_finalization_enabled
boom_finalization_enabled PROC
    ; False needs no Java allocation, global mutation or pending-context writes.
    xor eax,eax
    ret
boom_finalization_enabled ENDP
END
