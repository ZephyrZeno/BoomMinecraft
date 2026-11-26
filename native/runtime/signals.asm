; Windows signal-name lookup for the original Signal.findSignal0 contract.
; No handler registration, OS signal emission, allocation, conversion or GC.
option casemap:none
EXTERN boom_string_view:PROC
PUBLIC boom_signal_find
.const
signal_abrt WORD 65,66,82,84
signal_fpe WORD 70,80,69
signal_segv WORD 83,69,71,86
signal_int WORD 73,78,84
signal_term WORD 84,69,82,77
signal_break WORD 66,82,69,65,75
signal_ill WORD 73,76,76
ALIGN 8
signal_names LABEL BYTE
    DWORD 4,22
    QWORD OFFSET signal_abrt
    DWORD 3,8
    QWORD OFFSET signal_fpe
    DWORD 4,11
    QWORD OFFSET signal_segv
    DWORD 3,2
    QWORD OFFSET signal_int
    DWORD 4,15
    QWORD OFFSET signal_term
    DWORD 5,21
    QWORD OFFSET signal_break
    DWORD 3,4
    QWORD OFFSET signal_ill
.code
; (Context16 RCX,argv{String name} RDX,StringPool3 R8)->Java int.
; Java call sites ensure the original Signal class; raw VM service tests do not
; invoke a Java member and do not claim the Hashtable initializer has executed.
boom_signal_find PROC FRAME
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
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    test rbx,rbx
    jz signal_error
    cmp DWORD PTR [rbx],0
    jne signal_error
    test rsi,rsi
    jz signal_bad
    test rdi,rdi
    jz signal_bad
    cmp DWORD PTR [rdi],053545250h
    jne signal_bad
    cmp DWORD PTR [rdi+4],3
    jne signal_bad
    cmp DWORD PTR [rdi+16],65536
    ja signal_bad
    cmp QWORD PTR [rdi+64],0
    je signal_bad
    mov r12,QWORD PTR [rdi+48]
    test r12,r12
    jz signal_bad
    cmp DWORD PTR [r12],048454150h
    jne signal_bad
    cmp DWORD PTR [r12+4],1
    jne signal_bad
    mov rax,QWORD PTR [r12+16]
    test rax,rax
    jz signal_bad
    cmp rax,040000000h
    ja signal_bad
    lea r10,[r12+128]
    add rax,r10
    jc signal_bad
    cmp rax,QWORD PTR [r12+24]
    jne signal_bad
    mov rcx,QWORD PTR [rsi]
    test rcx,rcx
    jz signal_null
    call signal_owned
    test eax,eax
    jz signal_bad
    cmp QWORD PTR [rcx-16],16
    jne signal_bad
    mov rcx,QWORD PTR [rcx]
    call signal_owned
    test eax,eax
    jz signal_bad
    mov rcx,QWORD PTR [rsi]
    mov rdx,QWORD PTR [rdi+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne signal_error
    mov r13,rax
    lea rsi,signal_names
    mov r12d,7
signal_row:
    cmp edx,DWORD PTR [rsi]
    jne signal_next
    mov rdi,QWORD PTR [rsi+8]
    xor ecx,ecx
signal_compare:
    cmp ecx,edx
    jae signal_match
    movzx eax,WORD PTR [r13+rcx*2]
    cmp ax,WORD PTR [rdi+rcx*2]
    jne signal_next
    inc ecx
    jmp signal_compare
signal_next:
    add rsi,16
    dec r12d
    jnz signal_row
    mov eax,-1
    jmp signal_done
signal_match:
    mov eax,DWORD PTR [rsi+4]
    jmp signal_done
signal_null:
    mov DWORD PTR [rbx],4
    jmp signal_error
signal_bad:
    mov DWORD PTR [rbx],7
signal_error:
    xor eax,eax
signal_done:
    add rsp,48
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_signal_find ENDP
signal_owned PROC
    lea r10,[r12+160]
    cmp rcx,r10
    jb signal_not_owned
    mov r11,QWORD PTR [r12+24]
    cmp rcx,r11
    ja signal_not_owned
    test cl,15
    jnz signal_not_owned
    mov eax,DWORD PTR [rcx-24]
    and eax,0FFFFFFFDh
    cmp eax,0B00B0001h
    jne signal_not_owned
    mov rax,QWORD PTR [rcx-32]
    cmp rax,32
    jb signal_not_owned
    test al,15
    jnz signal_not_owned
    sub rax,32
    cmp QWORD PTR [rcx-16],rax
    ja signal_not_owned
    add rax,rcx
    jc signal_not_owned
    cmp rax,r11
    ja signal_not_owned
    mov eax,1
    ret
signal_not_owned:
    xor eax,eax
    ret
signal_owned ENDP
END
