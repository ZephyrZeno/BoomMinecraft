; Normal source Throwable.fillInStackTrace, Context32 and TracePool48/3.
; fill(ctx RCX, argv {receiver,dummy} RDX,plan R8)->same receiver.
; NTHP64/1: magic0 ABI4 rows8 reserved12 rows*16 tracePool*24 heapCell*32
;          bootstrapThrowableType*40 reserved48/56.
; ReceiverRow48: layout*0 backtrace8 depth12 depthWidth16 stackTrace20
;                reserved24 actualType*32 reserved40.
; backtrace is a private long[]: {magic/ABI,pool*,(methodID<<32)|bci...}.
; Original Java constructors and sentinels remain source methods. This captures
; at most 128 visible frames, stops at Context boundaries, and suppresses trace
; allocation OOM. Collection remains explicit/quiescent, without stack roots.
EXTERN boom_object_check:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_array_new:PROC
EXTERN boom_trace_head:PROC
EXTERN boom_heap_contains:PROC
PUBLIC boom_normal_throwable_fill
.code
boom_normal_throwable_fill PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push rbp
    .pushreg rbp
    push r12
    .pushreg r12
    push r13
    .pushreg r13
    push r14
    .pushreg r14
    push r15
    .pushreg r15
    sub rsp,1112
    .allocstack 1112
    .endprolog
    mov rbx,rcx
    mov rdi,r8
    test rbx,rbx
    jz normal_throwable_fill_error
    cmp DWORD PTR [rbx],0
    jne normal_throwable_fill_error
    test rdx,rdx
    jz normal_throwable_fill_bad
    mov rsi,QWORD PTR [rdx]
    test rsi,rsi
    jz normal_throwable_fill_null
    test rdi,rdi
    jz normal_throwable_fill_bad
    cmp DWORD PTR [rdi],05048544Eh
    jne normal_throwable_fill_bad
    cmp DWORD PTR [rdi+4],1
    jne normal_throwable_fill_bad
    cmp DWORD PTR [rdi+12],0
    jne normal_throwable_fill_bad
    cmp QWORD PTR [rdi+48],0
    jne normal_throwable_fill_bad
    cmp QWORD PTR [rdi+56],0
    jne normal_throwable_fill_bad
    mov eax,DWORD PTR [rdi+8]
    test eax,eax
    jz normal_throwable_fill_bad
    cmp eax,1048576
    ja normal_throwable_fill_bad
    mov r13,QWORD PTR [rdi+16]
    test r13,r13
    jz normal_throwable_fill_bad
    mov r12,QWORD PTR [rdi+24]
    test r12,r12
    jz normal_throwable_fill_bad
    cmp DWORD PTR [r12],05452504Ch
    jne normal_throwable_fill_bad
    cmp DWORD PTR [r12+4],3
    jne normal_throwable_fill_bad
    mov rax,QWORD PTR [rdi+32]
    test rax,rax
    jz normal_throwable_fill_bad
    mov r14,QWORD PTR [rax]
    test r14,r14
    jz normal_throwable_fill_bad
    cmp DWORD PTR [r14],048454150h
    jne normal_throwable_fill_bad
    cmp DWORD PTR [r14+4],1
    jne normal_throwable_fill_bad
    lea rax,[r14+160]
    cmp rsi,rax
    jb normal_throwable_fill_bad
    cmp rsi,QWORD PTR [r14+24]
    jae normal_throwable_fill_bad
    mov rcx,r14
    mov rdx,rsi
    call boom_heap_contains
    test eax,eax
    jz normal_throwable_fill_bad
    mov rdx,QWORD PTR [rsi-8]
    mov ecx,DWORD PTR [rdi+8]
normal_throwable_find_receiver:
    cmp QWORD PTR [r13],rdx
    je normal_throwable_receiver_found
    add r13,48
    dec ecx
    jnz normal_throwable_find_receiver
    jmp normal_throwable_fill_bad
normal_throwable_receiver_found:
    cmp QWORD PTR [r13+24],0
    jne normal_throwable_fill_bad
    cmp QWORD PTR [r13+40],0
    jne normal_throwable_fill_bad
    mov rcx,rsi
    mov rdx,QWORD PTR [r13]
    mov r8,rbx
    call boom_object_check
    cmp DWORD PTR [rbx],0
    jne normal_throwable_fill_error
    mov rdx,QWORD PTR [r13]
    mov rax,QWORD PTR [rdx+8]
    add rax,rsi
    jc normal_throwable_fill_bad
    cmp rax,QWORD PTR [r14+24]
    ja normal_throwable_fill_bad
    mov r9d,DWORD PTR [rdx+16]
    shl r9,3
    mov eax,DWORD PTR [r13+8]
    test eax,7
    jnz normal_throwable_fill_bad
    cmp rax,r9
    jae normal_throwable_fill_bad
    mov ecx,DWORD PTR [r13+20]
    test ecx,7
    jnz normal_throwable_fill_bad
    cmp rcx,r9
    jae normal_throwable_fill_bad
    cmp eax,ecx
    je normal_throwable_fill_bad
    mov ecx,DWORD PTR [r13+16]
    cmp ecx,4
    je normal_throwable_depth_width_ok
    cmp ecx,8
    jne normal_throwable_fill_bad
normal_throwable_depth_width_ok:
    mov r8d,DWORD PTR [r13+12]
    mov eax,ecx
    dec eax
    test r8d,eax
    jnz normal_throwable_fill_bad
    cmp r8,r9
    jb normal_throwable_fill_bad
    add r8,rcx
    cmp r8,QWORD PTR [rdx+8]
    ja normal_throwable_fill_bad
    mov rcx,QWORD PTR [r13+32]
    test rcx,rcx
    jz normal_throwable_fill_bad
    cmp DWORD PTR [rcx],054595045h
    jne normal_throwable_fill_bad
    cmp DWORD PTR [rcx+4],1
    jne normal_throwable_fill_bad
    cmp DWORD PTR [rcx+8],1
    jne normal_throwable_fill_bad
    mov rdx,QWORD PTR [rdi+40]
    test rdx,rdx
    jz normal_throwable_fill_bad
    call boom_type_assignable
    test eax,eax
    jz normal_throwable_fill_bad
    mov rcx,r12
    mov rdx,rbx
    call boom_trace_head
    cmp DWORD PTR [rbx],0
    jne normal_throwable_fill_error
    mov r15,rax
    xor ebp,ebp
    mov DWORD PTR [rsp+32],0 ; fill/constructor/rest filtering phase
    mov DWORD PTR [rsp+36],0 ; bounded traversal even with hidden frames
normal_throwable_frame_loop:
    test r15,r15
    jz normal_throwable_frames_captured
    inc DWORD PTR [rsp+36]
    cmp DWORD PTR [rsp+36],65536
    ja normal_throwable_fill_bad
    cmp DWORD PTR [r15],04652414Dh
    jne normal_throwable_fill_bad
    cmp DWORD PTR [r15+4],2
    jne normal_throwable_fill_bad
    test DWORD PTR [r15+28],0FFFFFFFEh
    jnz normal_throwable_fill_bad
    cmp QWORD PTR [r15+40],r12
    jne normal_throwable_fill_bad
    cmp QWORD PTR [r15+32],0
    je normal_throwable_fill_bad
    cmp QWORD PTR [r15+32],rbx
    jne normal_throwable_frames_captured
    mov rdi,QWORD PTR [r15+16]
    mov rax,rdi
    sub rax,QWORD PTR [r12+24]
    jc normal_throwable_fill_bad
    test eax,31
    jnz normal_throwable_fill_bad
    shr rax,5
    mov edx,DWORD PTR [r12+16]
    cmp rax,rdx
    jae normal_throwable_fill_bad
    test DWORD PTR [rdi+4],0FFFFFF00h
    jnz normal_throwable_fill_bad
    test DWORD PTR [rdi+4],128
    jnz normal_throwable_fill_bad
    cmp QWORD PTR [rdi+24],0
    jne normal_throwable_fill_bad
    mov eax,DWORD PTR [rdi+16]
    test DWORD PTR [rdi+4],32
    jz normal_throwable_java_pc
    test eax,eax
    jnz normal_throwable_fill_bad
    cmp DWORD PTR [r15+24],0
    jne normal_throwable_fill_bad
    jmp normal_throwable_pc_valid
normal_throwable_java_pc:
    test eax,eax
    jz normal_throwable_fill_bad
    cmp eax,65535
    ja normal_throwable_fill_bad
    cmp DWORD PTR [r15+24],eax
    jae normal_throwable_fill_bad
normal_throwable_pc_valid:
    mov rdx,QWORD PTR [rdi+8]
    test rdx,rdx
    jz normal_throwable_fill_bad
    cmp DWORD PTR [rdx],054595045h
    jne normal_throwable_fill_bad
    cmp DWORD PTR [rdx+4],1
    jne normal_throwable_fill_bad
    mov eax,DWORD PTR [rdx+8]
    dec eax
    cmp eax,1
    ja normal_throwable_fill_bad
    cmp DWORD PTR [rsp+32],0
    jne normal_throwable_check_constructor
    test DWORD PTR [rdi+4],2
    jz normal_throwable_end_fill_prefix
    mov rcx,QWORD PTR [r13+32]
    call boom_type_assignable
    test eax,eax
    jnz normal_throwable_next_frame
normal_throwable_end_fill_prefix:
    mov DWORD PTR [rsp+32],1
normal_throwable_check_constructor:
    cmp DWORD PTR [rsp+32],1
    jne normal_throwable_capture_visible
    test DWORD PTR [rdi+4],1
    jz normal_throwable_end_constructor_prefix
    mov rcx,QWORD PTR [r13+32]
    mov rdx,QWORD PTR [rdi+8]
    call boom_type_assignable
    test eax,eax
    jnz normal_throwable_next_frame
normal_throwable_end_constructor_prefix:
    mov DWORD PTR [rsp+32],2
normal_throwable_capture_visible:
    test DWORD PTR [rdi+4],16
    jnz normal_throwable_next_frame
    mov eax,DWORD PTR [rdi]
    shl rax,32
    mov edx,DWORD PTR [r15+24]
    or rax,rdx
    mov QWORD PTR [rsp+rbp*8+64],rax
    inc ebp
    cmp ebp,128
    jae normal_throwable_frames_captured
normal_throwable_next_frame:
    mov r15,QWORD PTR [r15+8]
    jmp normal_throwable_frame_loop
normal_throwable_frames_captured:
    ; OpenJDK clears the old trace before allocation and suppresses trace OOM.
    mov eax,DWORD PTR [r13+8]
    mov QWORD PTR [rsi+rax],0
    mov eax,DWORD PTR [r13+20]
    mov QWORD PTR [rsi+rax],0
    mov eax,DWORD PTR [r13+12]
    cmp DWORD PTR [r13+16],8
    jne normal_throwable_clear_depth32
    mov QWORD PTR [rsi+rax],0
    jmp normal_throwable_allocate_trace
normal_throwable_clear_depth32:
    mov DWORD PTR [rsi+rax],0
normal_throwable_allocate_trace:
    mov QWORD PTR [rsp+40],0
    mov QWORD PTR [rsp+48],0
    mov rcx,r14
    lea edx,[rbp+2]
    mov r8d,11 ; JVM long[]
    lea r9,[rsp+40]
    call boom_array_new
    test rax,rax
    jnz normal_throwable_trace_allocated
    cmp DWORD PTR [rsp+40],3
    je normal_throwable_fill_success
    mov DWORD PTR [rbx],7
    jmp normal_throwable_fill_error
normal_throwable_trace_allocated:
    cmp DWORD PTR [rsp+40],0
    jne normal_throwable_fill_bad
    mov r11,0000000142545243h
    mov QWORD PTR [rax],r11
    mov QWORD PTR [rax+8],r12
    xor ecx,ecx
normal_throwable_copy_frames:
    cmp ecx,ebp
    jae normal_throwable_publish_trace
    mov rdx,QWORD PTR [rsp+rcx*8+64]
    mov QWORD PTR [rax+rcx*8+16],rdx
    inc ecx
    jmp normal_throwable_copy_frames
normal_throwable_publish_trace:
    mov edx,DWORD PTR [r13+12]
    cmp DWORD PTR [r13+16],8
    jne normal_throwable_store_depth32
    mov QWORD PTR [rsi+rdx],rbp
    jmp normal_throwable_store_trace
normal_throwable_store_depth32:
    mov DWORD PTR [rsi+rdx],ebp
normal_throwable_store_trace:
    mov edx,DWORD PTR [r13+8]
    mov QWORD PTR [rsi+rdx],rax
normal_throwable_fill_success:
    mov rax,rsi
    jmp normal_throwable_fill_done
normal_throwable_fill_null:
    mov DWORD PTR [rbx],4
    jmp normal_throwable_fill_error
normal_throwable_fill_bad:
    mov DWORD PTR [rbx],7
normal_throwable_fill_error:
    xor eax,eax
normal_throwable_fill_done:
    add rsp,1112
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rdi
    pop rsi
    pop rbx
    ret
boom_normal_throwable_fill ENDP
