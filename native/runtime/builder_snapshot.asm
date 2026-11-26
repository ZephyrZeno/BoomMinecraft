; Original StringBuilder.toString's new String(this): copy mutable storage.
; Snapshot pool48: magic0 ABI4 StringPool*8 layout*16 valueOff24 coderOff28 countOff32 reserved36 heapCell*40.
; Original inherited builder fields and byte[] are used, not a replacement builder.
option casemap:none
EXTERN boom_object_check:PROC
EXTERN boom_string_allocate:PROC
PUBLIC boom_builder_snapshot
.code
; copy(ctx RCX,argv{builder} RDX,pool R8)->fresh String/NULL, even empty.
boom_builder_snapshot PROC FRAME
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
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov r12,r8
    test rbx,rbx
    jz snapshot_error
    cmp DWORD PTR [rbx],0
    jne snapshot_error
    test rsi,rsi
    jz snapshot_bad
    test r12,r12
    jz snapshot_bad
    cmp DWORD PTR [r12],042534E50h
    jne snapshot_bad
    cmp DWORD PTR [r12+4],1
    jne snapshot_bad
    cmp DWORD PTR [r12+36],0
    jne snapshot_bad
    mov r15,QWORD PTR [r12+8]
    test r15,r15
    jz snapshot_bad
    cmp DWORD PTR [r15],053545250h
    jne snapshot_bad
    cmp DWORD PTR [r15+4],3
    jne snapshot_bad
    mov r10,QWORD PTR [r12+40]
    test r10,r10
    jz snapshot_bad
    mov r10,QWORD PTR [r10]
    test r10,r10
    jz snapshot_bad
    cmp DWORD PTR [r10],048454150h
    jne snapshot_bad
    cmp DWORD PTR [r10+4],1
    jne snapshot_bad
    mov QWORD PTR [rsp+48],r10
    mov rax,QWORD PTR [r15+48]
    test rax,rax
    jz snapshot_heap_ready
    cmp rax,r10
    jne snapshot_bad
snapshot_heap_ready:
    mov rcx,QWORD PTR [rsi]
    mov rdx,r10
    call snapshot_owned
    test eax,eax
    jz snapshot_bad
    mov rdx,QWORD PTR [r12+16]
    mov r8,rbx
    call boom_object_check
    test rax,rax
    jz snapshot_error
    mov r10,QWORD PTR [r12+16]
    mov rax,QWORD PTR [r10+8]
    cmp rax,14
    jb snapshot_bad
    cmp DWORD PTR [r12+24],0
    jne snapshot_bad
    mov ecx,DWORD PTR [r12+28]
    cmp rcx,rax
    jae snapshot_bad
    mov ecx,DWORD PTR [r12+32]
    test cl,3
    jnz snapshot_bad
    add rcx,4
    cmp rcx,rax
    ja snapshot_bad
    mov r10,QWORD PTR [rsi]
    mov eax,DWORD PTR [r12+24]
    mov r13,QWORD PTR [r10+rax]
    mov eax,DWORD PTR [r12+28]
    movzx eax,BYTE PTR [r10+rax]
    cmp eax,1
    ja snapshot_bad
    mov DWORD PTR [rsp+32],eax
    mov ecx,DWORD PTR [r12+32]
    mov r14d,DWORD PTR [r10+rcx]
    test r14d,r14d
    js snapshot_bad
    test r13,r13
    jz snapshot_bad
    mov rcx,r13
    mov rdx,QWORD PTR [rsp+48]
    call snapshot_owned
    test eax,eax
    jz snapshot_bad
    mov eax,DWORD PTR [r13-24]
    and eax,0FFFFFFFDh
    cmp eax,0B00B0001h
    jne snapshot_bad
    cmp DWORD PTR [r13-20],0
    jne snapshot_bad
    cmp QWORD PTR [r13-8],264
    jne snapshot_bad
    mov rax,QWORD PTR [r13-16]
    cmp rax,07FFFFFFFh
    ja snapshot_bad
    mov ecx,DWORD PTR [rsp+32]
    test ecx,ecx
    jz snapshot_capacity
    test al,1
    jnz snapshot_bad
    shr rax,1
snapshot_capacity:
    cmp r14,rax
    ja snapshot_bad
    mov rcx,QWORD PTR [rsp+48]
    mov rdx,r15
    mov r8d,r14d
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz snapshot_error
    mov QWORD PTR [rsp+40],rax
    mov rdi,QWORD PTR [rax]
    mov rsi,r13
    mov ecx,r14d
    cmp DWORD PTR [rsp+32],0
    je snapshot_latin
    rep movsw
    jmp snapshot_result
snapshot_latin:
    test ecx,ecx
    jz snapshot_result
snapshot_latin_loop:
    movzx eax,BYTE PTR [rsi]
    mov WORD PTR [rdi],ax
    inc rsi
    add rdi,2
    dec ecx
    jnz snapshot_latin_loop
snapshot_result:
    mov rax,QWORD PTR [rsp+40]
    jmp snapshot_done
snapshot_bad:
    mov DWORD PTR [rbx],7
snapshot_error:
    xor eax,eax
snapshot_done:
    add rsp,64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_builder_snapshot ENDP
; Live typed pointers must belong to the bound heap. NULL is checked separately.
snapshot_owned PROC
    test rcx,rcx
    jz snapshot_owned_yes
    mov r10,rdx
    mov r11,QWORD PTR [r10+16]
    lea r11,[r10+r11+128]
    add r10,160
    cmp rcx,r10
    jb snapshot_owned_no
    cmp rcx,r11
    jae snapshot_owned_no
snapshot_owned_yes:
    mov eax,1
    ret
snapshot_owned_no:
    xor eax,eax
    ret
snapshot_owned ENDP
END
