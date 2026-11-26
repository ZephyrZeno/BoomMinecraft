; Source-verified java.lang.Throwable native fillInStackTrace. MASM only.
; fill(Context16 RCX, argv {receiver,dummy} RDX,plan R8)->same receiver.
; Plan64: magic0 ABI4 rows8 reserved12 rows*16 tracePool*24 heapCell*32
;          bootstrapThrowableType*40 reserved48/56.
; ReceiverRow48: layout*0 backtrace8 depth12 depthWidth16 stackTrace20
;                reserved24 actualType*32 reserved40.
; backtrace is a private long[]: {magic/ABI,pool*,(methodID<<32)|bci...}.
; The source Java constructors, sentinels and public synchronized wrapper run
; normally. GC is explicit/quiescent; receiver and native temporaries stay live.
option casemap:none
EXTERN boom_object_check:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_array_new:PROC
EXTERN boom_trace_head:PROC
PUBLIC boom_throwable_fill
.code
boom_throwable_fill PROC FRAME
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
    cmp DWORD PTR [rbx],0
    jne throwable_fill_error
    test rdx,rdx
    jz throwable_fill_bad
    mov rsi,QWORD PTR [rdx]
    test rsi,rsi
    jz throwable_fill_null
    test rdi,rdi
    jz throwable_fill_bad
    cmp DWORD PTR [rdi],054485250h
    jne throwable_fill_bad
    cmp DWORD PTR [rdi+4],1
    jne throwable_fill_bad
    cmp DWORD PTR [rdi+12],0
    jne throwable_fill_bad
    cmp QWORD PTR [rdi+48],0
    jne throwable_fill_bad
    cmp QWORD PTR [rdi+56],0
    jne throwable_fill_bad
    mov eax,DWORD PTR [rdi+8]
    test eax,eax
    jz throwable_fill_bad
    cmp eax,4096
    ja throwable_fill_bad
    mov r13,QWORD PTR [rdi+16]
    test r13,r13
    jz throwable_fill_bad
    mov r12,QWORD PTR [rdi+24]
    test r12,r12
    jz throwable_fill_bad
    mov rax,QWORD PTR [rdi+32]
    test rax,rax
    jz throwable_fill_bad
    mov r14,QWORD PTR [rax]
    test r14,r14
    jz throwable_fill_bad
    cmp DWORD PTR [r14],048454150h
    jne throwable_fill_bad
    cmp DWORD PTR [r14+4],1
    jne throwable_fill_bad
    lea rax,[r14+160]
    cmp rsi,rax
    jb throwable_fill_bad
    cmp rsi,QWORD PTR [r14+24]
    jae throwable_fill_bad
    mov rdx,QWORD PTR [rsi-8]
    mov ecx,DWORD PTR [rdi+8]
throwable_find_receiver:
    cmp QWORD PTR [r13],rdx
    je throwable_receiver_found
    add r13,48
    dec ecx
    jnz throwable_find_receiver
    jmp throwable_fill_bad
throwable_receiver_found:
    cmp QWORD PTR [r13+24],0
    jne throwable_fill_bad
    cmp QWORD PTR [r13+40],0
    jne throwable_fill_bad
    mov rcx,rsi
    mov rdx,QWORD PTR [r13]
    mov r8,rbx
    call boom_object_check
    cmp DWORD PTR [rbx],0
    jne throwable_fill_error
    mov rdx,QWORD PTR [r13]
    mov rax,QWORD PTR [rdx+8]
    add rax,rsi
    jc throwable_fill_bad
    cmp rax,QWORD PTR [r14+24]
    ja throwable_fill_bad
    mov r9d,DWORD PTR [rdx+16]
    shl r9,3
    mov eax,DWORD PTR [r13+8]
    test eax,7
    jnz throwable_fill_bad
    cmp rax,r9
    jae throwable_fill_bad
    mov ecx,DWORD PTR [r13+20]
    test ecx,7
    jnz throwable_fill_bad
    cmp rcx,r9
    jae throwable_fill_bad
    cmp eax,ecx
    je throwable_fill_bad
    mov ecx,DWORD PTR [r13+16]
    cmp ecx,4
    je throwable_depth_width_ok
    cmp ecx,8
    jne throwable_fill_bad
throwable_depth_width_ok:
    mov r8d,DWORD PTR [r13+12]
    mov eax,ecx
    dec eax
    test r8d,eax
    jnz throwable_fill_bad
    cmp r8,r9
    jb throwable_fill_bad
    add r8,rcx
    cmp r8,QWORD PTR [rdx+8]
    ja throwable_fill_bad
    mov rcx,QWORD PTR [r13+32]
    test rcx,rcx
    jz throwable_fill_bad
    cmp DWORD PTR [rcx],054595045h
    jne throwable_fill_bad
    cmp DWORD PTR [rcx+4],1
    jne throwable_fill_bad
    cmp DWORD PTR [rcx+8],1
    jne throwable_fill_bad
    mov rdx,QWORD PTR [rdi+40]
    test rdx,rdx
    jz throwable_fill_bad
    call boom_type_assignable
    test eax,eax
    jz throwable_fill_bad
    mov rcx,r12
    mov rdx,rbx
    call boom_trace_head
    cmp DWORD PTR [rbx],0
    jne throwable_fill_error
    mov r15,rax
    xor ebp,ebp
    mov DWORD PTR [rsp+32],0 ; fill/constructor/rest filtering phase
    mov DWORD PTR [rsp+36],0 ; bounded traversal even with hidden frames
throwable_frame_loop:
    test r15,r15
    jz throwable_frames_captured
    inc DWORD PTR [rsp+36]
    cmp DWORD PTR [rsp+36],128
    ja throwable_fill_bad
    cmp DWORD PTR [r15],04652414Dh
    jne throwable_fill_bad
    cmp DWORD PTR [r15+4],2
    jne throwable_fill_bad
    test DWORD PTR [r15+28],0FFFFFFFEh
    jnz throwable_fill_bad
    cmp QWORD PTR [r15+40],r12
    jne throwable_fill_bad
    cmp QWORD PTR [r15+32],0
    je throwable_fill_bad
    mov rdi,QWORD PTR [r15+16]
    mov rax,rdi
    sub rax,QWORD PTR [r12+24]
    jc throwable_fill_bad
    test eax,31
    jnz throwable_fill_bad
    shr rax,5
    mov edx,DWORD PTR [r12+16]
    cmp rax,rdx
    jae throwable_fill_bad
    mov eax,DWORD PTR [rdi+16]
    test eax,eax
    jz throwable_fill_bad
    cmp eax,65535
    ja throwable_fill_bad
    cmp DWORD PTR [r15+24],eax
    jae throwable_fill_bad
    test DWORD PTR [rdi+4],0FFFFFFF8h
    jnz throwable_fill_bad
    mov rdx,QWORD PTR [rdi+8]
    test rdx,rdx
    jz throwable_fill_bad
    cmp DWORD PTR [rdx],054595045h
    jne throwable_fill_bad
    cmp DWORD PTR [rdx+4],1
    jne throwable_fill_bad
    cmp DWORD PTR [rdx+8],1
    jne throwable_fill_bad
    cmp DWORD PTR [rsp+32],0
    jne throwable_check_constructor
    test DWORD PTR [rdi+4],2
    jz throwable_end_fill_prefix
    mov rcx,QWORD PTR [r13+32]
    call boom_type_assignable
    test eax,eax
    jnz throwable_next_frame
throwable_end_fill_prefix:
    mov DWORD PTR [rsp+32],1
throwable_check_constructor:
    cmp DWORD PTR [rsp+32],1
    jne throwable_capture_visible
    test DWORD PTR [rdi+4],1
    jz throwable_end_constructor_prefix
    mov rcx,QWORD PTR [r13+32]
    mov rdx,QWORD PTR [rdi+8]
    call boom_type_assignable
    test eax,eax
    jnz throwable_next_frame
throwable_end_constructor_prefix:
    mov DWORD PTR [rsp+32],2
throwable_capture_visible:
    test DWORD PTR [rdi+4],4
    jnz throwable_next_frame
    mov eax,DWORD PTR [rdi]
    shl rax,32
    mov edx,DWORD PTR [r15+24]
    or rax,rdx
    mov QWORD PTR [rsp+rbp*8+64],rax
    inc ebp
throwable_next_frame:
    mov r15,QWORD PTR [r15+8]
    jmp throwable_frame_loop
throwable_frames_captured:
    ; OpenJDK clears the old trace before allocation and suppresses trace OOM.
    mov eax,DWORD PTR [r13+8]
    mov QWORD PTR [rsi+rax],0
    mov eax,DWORD PTR [r13+20]
    mov QWORD PTR [rsi+rax],0
    mov eax,DWORD PTR [r13+12]
    cmp DWORD PTR [r13+16],8
    jne throwable_clear_depth32
    mov QWORD PTR [rsi+rax],0
    jmp throwable_allocate_trace
throwable_clear_depth32:
    mov DWORD PTR [rsi+rax],0
throwable_allocate_trace:
    mov QWORD PTR [rsp+40],0
    mov QWORD PTR [rsp+48],0
    mov rcx,r14
    lea edx,[rbp+2]
    mov r8d,11 ; JVM long[]
    lea r9,[rsp+40]
    call boom_array_new
    test rax,rax
    jnz throwable_trace_allocated
    cmp DWORD PTR [rsp+40],3
    je throwable_fill_success
    mov DWORD PTR [rbx],7
    jmp throwable_fill_error
throwable_trace_allocated:
    cmp DWORD PTR [rsp+40],0
    jne throwable_fill_bad
    mov r11,0000000142545243h
    mov QWORD PTR [rax],r11
    mov QWORD PTR [rax+8],r12
    xor ecx,ecx
throwable_copy_frames:
    cmp ecx,ebp
    jae throwable_publish_trace
    mov rdx,QWORD PTR [rsp+rcx*8+64]
    mov QWORD PTR [rax+rcx*8+16],rdx
    inc ecx
    jmp throwable_copy_frames
throwable_publish_trace:
    mov edx,DWORD PTR [r13+12]
    cmp DWORD PTR [r13+16],8
    jne throwable_store_depth32
    mov QWORD PTR [rsi+rdx],rbp
    jmp throwable_store_trace
throwable_store_depth32:
    mov DWORD PTR [rsi+rdx],ebp
throwable_store_trace:
    mov edx,DWORD PTR [r13+8]
    mov QWORD PTR [rsi+rdx],rax
throwable_fill_success:
    mov rax,rsi
    jmp throwable_fill_done
throwable_fill_null:
    mov DWORD PTR [rbx],4
    jmp throwable_fill_error
throwable_fill_bad:
    mov DWORD PTR [rbx],7
throwable_fill_error:
    xor eax,eax
throwable_fill_done:
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
boom_throwable_fill ENDP
END
