; System.setIn0/setOut0/setErr0: update the actual rooted static final cells.
; Private source access is checked by the compiler. No allocation or automatic GC.
option casemap:none
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
PUBLIC boom_system_stream_set
.code
; (Context16/32 RCX, argv{stream} RDX, Pool64 R8, operation R9D) -> void.
; Pool: magic0 ABI4 class*8 heapCell*16 typeMap*24 rows*32 count40 res44/48/56.
; Row16: rooted field cell*, expected TypeDesc*. NULL is a valid stream value.
boom_system_stream_set PROC FRAME
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
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,r8
    mov r14,rdx
    test rbx,rbx
    jz stream_set_done
    cmp DWORD PTR [rbx],0
    jne stream_set_done
    test rsi,rsi
    jz stream_set_bad
    test r14,r14
    jz stream_set_bad
    cmp DWORD PTR [rsi],053595349h
    jne stream_set_bad
    cmp DWORD PTR [rsi+4],1
    jne stream_set_bad
    cmp DWORD PTR [rsi+40],3
    jne stream_set_bad
    cmp DWORD PTR [rsi+44],0
    jne stream_set_bad
    cmp QWORD PTR [rsi+48],0
    jne stream_set_bad
    cmp QWORD PTR [rsi+56],0
    jne stream_set_bad
    cmp r9d,2
    ja stream_set_bad
    mov r9d,r9d
    mov rax,QWORD PTR [rsi+24]
    test rax,rax
    jz stream_set_bad
    cmp DWORD PTR [rax],052545950h
    jne stream_set_bad
    mov eax,DWORD PTR [rax+4]
    dec eax
    cmp eax,1
    ja stream_set_bad
    mov rcx,QWORD PTR [rsi+8]
    test rcx,rcx
    jz stream_set_bad
    cmp DWORD PTR [rcx],0434C4153h
    jne stream_set_bad
    mov eax,DWORD PTR [rcx+4]
    dec eax
    cmp eax,1
    ja stream_set_bad
    cmp DWORD PTR [rcx+8],2
    jne stream_set_bad
    mov r12,QWORD PTR [rsi+32]
    test r12,r12
    jz stream_set_bad
    shl r9,4
    add r12,r9
    mov r13,QWORD PTR [r12+8]
    mov r12,QWORD PTR [r12]
    test r12,r12
    jz stream_set_bad
    test r13,r13
    jz stream_set_bad
    cmp DWORD PTR [r13],054595045h
    jne stream_set_bad
    cmp DWORD PTR [r13+4],1
    jne stream_set_bad
    cmp DWORD PTR [r13+8],1
    jne stream_set_bad
    mov r10,QWORD PTR [rsi+16]
    test r10,r10
    jz stream_set_bad
    ; NULL is legal even before the guest heap is bound. The immutable pool
    ; still supplies a real heap cell and rooted destination slot.
    mov rdi,QWORD PTR [r14]
    test rdi,rdi
    jz stream_set_store
    mov r10,QWORD PTR [r10]
    test r10,r10
    jz stream_set_bad
    cmp DWORD PTR [r10],048454150h
    jne stream_set_bad
    cmp DWORD PTR [r10+4],1
    jne stream_set_bad
    lea r11,[r10+160]
    cmp rdi,r11
    jb stream_set_bad
    test dil,15
    jnz stream_set_bad
    mov r11,QWORD PTR [r10+24]
    cmp rdi,r11
    ja stream_set_bad
    mov rax,QWORD PTR [rdi-32]
    cmp rax,32
    jb stream_set_bad
    test al,15
    jnz stream_set_bad
    sub rax,32
    cmp QWORD PTR [rdi-16],rax
    ja stream_set_bad
    add rax,rdi
    jc stream_set_bad
    cmp rax,r11
    ja stream_set_bad
    mov rcx,rdi
    mov rdx,QWORD PTR [rsi+24]
    mov r8,rbx
    call boom_runtime_type
    test rax,rax
    jz stream_set_done
    mov rcx,rax
    mov rdx,r13
    call boom_type_assignable
    test eax,eax
    jz stream_set_bad
stream_set_store:
    ; Publish the reference through the same cell enumerated by static roots.
    xchg QWORD PTR [r12],rdi
    jmp stream_set_done
stream_set_bad:
    mov DWORD PTR [rbx],7
stream_set_done:
    xor eax,eax
    add rsp,40
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_system_stream_set ENDP
END
