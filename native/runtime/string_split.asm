; Source-bound String literal-delimiter split. No regular-expression fallback.
; SPLT48/ABI1: strings8,heapCell16,String[] layout24,emptyLiteral32D,
; flags36D=0,reserved40Q=0. All allocation/copy/counting is MASM.
; A single BMP non-surrogate or an escaped non-ASCII-alphanumeric delimiter
; follows the original JDK fast-path predicate. Other regexes fail explicitly.
option casemap:none
EXTERN boom_string_view:PROC
EXTERN boom_string_load:PROC
EXTERN boom_string_allocate:PROC
EXTERN boom_reference_array_new:PROC
PUBLIC boom_string_split
.const
split_meta WORD 02Eh,024h,07Ch,028h,029h,05Bh,07Bh,05Eh,03Fh,02Ah,02Bh,05Ch
.code
; (heap,oop)->complete live ownership; no tag reads before arena bounds.
split_owned PROC
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz split_owned_no
    cmp rax,040000000h
    ja split_owned_no
    lea r10,[rcx+128]
    add rax,r10
    jc split_owned_no
    cmp rax,QWORD PTR [rcx+24]
    jne split_owned_no
    lea r10,[rcx+160]
    cmp rdx,r10
    jb split_owned_no
    cmp rdx,rax
    ja split_owned_no
    test dl,15
    jnz split_owned_no
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,0B00B0001h
    jne split_owned_no
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb split_owned_no
    test r10b,15
    jnz split_owned_no
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja split_owned_no
    add r10,rdx
    jc split_owned_no
    cmp r10,rax
    ja split_owned_no
    mov eax,1
    ret
split_owned_no:
    xor eax,eax
    ret
split_owned ENDP
; (context RCX,String RDX,SPLT pool R8)->chars RAX,length EDX.
split_view PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    test rsi,rsi
    jz split_view_null
    mov rax,QWORD PTR [rdi+16]
    mov r12,QWORD PTR [rax]
    mov rcx,r12
    mov rdx,rsi
    call split_owned
    test eax,eax
    jz split_view_bad
    mov rax,QWORD PTR [rdi+8]
    mov rax,QWORD PTR [rax+40]
    cmp QWORD PTR [rsi-8],rax
    jne split_view_bad
    cmp QWORD PTR [rsi-16],16
    jne split_view_bad
    cmp DWORD PTR [rsi-20],1
    jne split_view_bad
    mov rcx,r12
    mov rdx,QWORD PTR [rsi]
    call split_owned
    test eax,eax
    jz split_view_bad
    mov rcx,rsi
    mov rdx,QWORD PTR [rdi+8]
    mov rdx,QWORD PTR [rdx+40]
    mov r8,rbx
    call boom_string_view
    jmp split_view_done
split_view_null:
    mov DWORD PTR [rbx],4
    jmp split_view_zero
split_view_bad:
    mov DWORD PTR [rbx],7
split_view_zero:
    xor eax,eax
    xor edx,edx
split_view_done:
    add rsp,40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
split_view ENDP
; state64: pool0Q,heap8Q,chars16Q,len24D,delimiter28D,source32Q,
; strings40Q,result48Q,delimiterObject56Q.
; (context RCX,state RDX,begin R8D,count R9D)->fresh piece/canonical empty.
split_piece PROC FRAME
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
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov edi,r8d
    mov r12d,r9d
    cmp edi,DWORD PTR [rsi+24]
    ja split_piece_bad
    mov eax,DWORD PTR [rsi+24]
    sub eax,edi
    cmp r12d,eax
    ja split_piece_bad
    test r12d,r12d
    jz split_piece_empty
    mov rcx,QWORD PTR [rsi+8]
    mov rdx,QWORD PTR [rsi+40]
    mov r8d,r12d
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz split_piece_done
    mov r13,rax
    mov rdx,QWORD PTR [rsi+16]
    lea rdx,[rdx+rdi*2]
    mov rdi,QWORD PTR [rax]
    mov rsi,rdx
    mov ecx,r12d
    rep movsw
    mov rax,r13
    jmp split_piece_done
split_piece_empty:
    mov rcx,QWORD PTR [rsi+8]
    mov rdx,QWORD PTR [rsi+40]
    mov rax,QWORD PTR [rsi]
    mov r8d,DWORD PTR [rax+32]
    mov r9,rbx
    call boom_string_load
    jmp split_piece_done
split_piece_bad:
    mov DWORD PTR [rbx],7
    xor eax,eax
split_piece_done:
    add rsp,32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
split_piece ENDP

; (Context32 RCX,argv{String,regex,limit,withDelimiters} RDX,SPLT48 R8).
boom_string_split PROC FRAME
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
    sub rsp,160
    .allocstack 160
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    test rbx,rbx
    jz split_zero
    cmp DWORD PTR [rbx],0
    jne split_zero
    test rsi,rsi
    jz split_bad
    test rdi,rdi
    jz split_bad
    cmp DWORD PTR [rdi],0544C5053h
    jne split_bad
    cmp DWORD PTR [rdi+4],1
    jne split_bad
    cmp DWORD PTR [rdi+36],0
    jne split_bad
    cmp QWORD PTR [rdi+40],0
    jne split_bad
    cmp QWORD PTR [rdi+8],0
    je split_bad
    cmp QWORD PTR [rdi+16],0
    je split_bad
    cmp QWORD PTR [rdi+24],0
    je split_bad
    mov rax,QWORD PTR [rdi+8]
    cmp DWORD PTR [rax],053545250h
    jne split_bad
    cmp DWORD PTR [rax+4],3
    jne split_bad
    mov ecx,DWORD PTR [rdi+32]
    cmp ecx,DWORD PTR [rax+16]
    jae split_bad
    mov r10,QWORD PTR [rax+32]
    test r10,r10
    jz split_bad
    shl rcx,4
    cmp DWORD PTR [r10+rcx+8],0
    jne split_bad
    mov r10,QWORD PTR [rdi+24]
    cmp DWORD PTR [r10],052454641h
    jne split_bad
    cmp DWORD PTR [r10+4],1
    jne split_bad
    mov r11,QWORD PTR [rax+40]
    cmp QWORD PTR [r10+8],r11
    jne split_bad
    mov rax,QWORD PTR [rdi+16]
    mov r12,QWORD PTR [rax]
    test r12,r12
    jz split_bad
    cmp DWORD PTR [r12],048454150h
    jne split_bad
    cmp DWORD PTR [r12+4],1
    jne split_bad
    mov eax,DWORD PTR [rsi+16]
    mov DWORD PTR [rsp+32],eax
    mov eax,DWORD PTR [rsi+24]
    cmp eax,1
    ja split_bad
    mov DWORD PTR [rsp+36],eax
    mov QWORD PTR [rsp+64],rdi
    mov QWORD PTR [rsp+72],r12
    mov rax,QWORD PTR [rdi+8]
    mov QWORD PTR [rsp+104],rax
    mov rax,QWORD PTR [rsi]
    mov QWORD PTR [rsp+96],rax
    mov rcx,rbx
    mov rdx,rax
    mov r8,rdi
    call split_view
    cmp DWORD PTR [rbx],0
    jne split_zero
    mov r13,rax
    mov r14d,edx
    mov QWORD PTR [rsp+80],rax
    mov DWORD PTR [rsp+88],edx
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi+8]
    mov r8,rdi
    call split_view
    cmp DWORD PTR [rbx],0
    jne split_zero
    cmp edx,1
    je split_single_regex
    cmp edx,2
    jne split_unsupported
    cmp WORD PTR [rax],05Ch
    jne split_unsupported
    movzx eax,WORD PTR [rax+2]
    lea edx,[rax-030h]
    cmp edx,9
    jbe split_unsupported
    lea edx,[rax-061h]
    cmp edx,25
    jbe split_unsupported
    lea edx,[rax-041h]
    cmp edx,25
    jbe split_unsupported
    jmp split_delimiter_ready
split_single_regex:
    movzx eax,WORD PTR [rax]
    lea r10,split_meta
    xor ecx,ecx
split_meta_loop:
    cmp ax,WORD PTR [r10+rcx*2]
    je split_unsupported
    inc ecx
    cmp ecx,12
    jb split_meta_loop
split_delimiter_ready:
    lea edx,[rax-0D800h]
    cmp edx,07FFh
    jbe split_unsupported
    mov DWORD PTR [rsp+92],eax
    xor r15d,r15d
    mov DWORD PTR [rsp+40],0
    mov DWORD PTR [rsp+44],0
    mov DWORD PTR [rsp+48],0
    mov DWORD PTR [rsp+52],0
split_count_loop:
    cmp r15d,r14d
    jae split_count_tail
    movzx eax,WORD PTR [r13+r15*2]
    cmp eax,DWORD PTR [rsp+92]
    jne split_count_next
    mov eax,DWORD PTR [rsp+32]
    test eax,eax
    jle split_count_accept
    dec eax
    cmp DWORD PTR [rsp+40],eax
    jae split_count_tail
split_count_accept:
    inc DWORD PTR [rsp+48]
    cmp r15d,DWORD PTR [rsp+44]
    je split_count_delimiter
    mov eax,DWORD PTR [rsp+48]
    mov DWORD PTR [rsp+52],eax
split_count_delimiter:
    cmp DWORD PTR [rsp+36],0
    je split_count_off
    inc DWORD PTR [rsp+48]
    mov eax,DWORD PTR [rsp+48]
    mov DWORD PTR [rsp+52],eax
split_count_off:
    lea eax,[r15+1]
    mov DWORD PTR [rsp+44],eax
    inc DWORD PTR [rsp+40]
split_count_next:
    inc r15d
    jmp split_count_loop
split_count_tail:
    cmp DWORD PTR [rsp+40],0
    je split_no_match
    inc DWORD PTR [rsp+48]
    cmp r14d,DWORD PTR [rsp+44]
    je split_count_size
    mov eax,DWORD PTR [rsp+48]
    mov DWORD PTR [rsp+52],eax
split_count_size:
    mov edx,DWORD PTR [rsp+48]
    cmp DWORD PTR [rsp+32],0
    jne split_allocate
    mov edx,DWORD PTR [rsp+52]
    jmp split_allocate
split_no_match:
    mov edx,1
split_allocate:
    mov DWORD PTR [rsp+56],edx
    mov rcx,r12
    mov r8,QWORD PTR [rdi+24]
    mov r9,rbx
    call boom_reference_array_new
    test rax,rax
    jz split_zero
    mov QWORD PTR [rsp+112],rax
    cmp DWORD PTR [rsp+40],0
    jne split_fill_begin
    mov rdx,QWORD PTR [rsp+96]
    mov QWORD PTR [rax],rdx
    jmp split_done
split_fill_begin:
    cmp DWORD PTR [rsp+56],0
    je split_done
    mov QWORD PTR [rsp+120],0
    mov DWORD PTR [rsp+40],0
    mov DWORD PTR [rsp+44],0
    mov DWORD PTR [rsp+60],0
    xor r15d,r15d
split_fill_loop:
    mov eax,DWORD PTR [rsp+60]
    cmp eax,DWORD PTR [rsp+56]
    jae split_result
    cmp r15d,r14d
    jae split_fill_tail
    movzx eax,WORD PTR [r13+r15*2]
    cmp eax,DWORD PTR [rsp+92]
    jne split_fill_next
    mov eax,DWORD PTR [rsp+32]
    test eax,eax
    jle split_fill_accept
    dec eax
    cmp DWORD PTR [rsp+40],eax
    jae split_fill_tail
split_fill_accept:
    mov rcx,rbx
    lea rdx,[rsp+64]
    mov r8d,DWORD PTR [rsp+44]
    mov r9d,r15d
    sub r9d,r8d
    call split_piece
    test rax,rax
    jz split_zero
    mov ecx,DWORD PTR [rsp+60]
    mov rdx,QWORD PTR [rsp+112]
    mov QWORD PTR [rdx+rcx*8],rax
    inc ecx
    mov DWORD PTR [rsp+60],ecx
    cmp ecx,DWORD PTR [rsp+56]
    jae split_result
    cmp DWORD PTR [rsp+36],0
    je split_fill_off
    mov rax,QWORD PTR [rsp+120]
    test rax,rax
    jnz split_fill_delimiter
    mov rcx,r12
    mov rdx,QWORD PTR [rdi+8]
    mov r8d,1
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz split_zero
    mov rdx,QWORD PTR [rax]
    mov ecx,DWORD PTR [rsp+92]
    mov WORD PTR [rdx],cx
    mov QWORD PTR [rsp+120],rax
split_fill_delimiter:
    mov ecx,DWORD PTR [rsp+60]
    mov rdx,QWORD PTR [rsp+112]
    mov QWORD PTR [rdx+rcx*8],rax
    inc DWORD PTR [rsp+60]
split_fill_off:
    lea eax,[r15+1]
    mov DWORD PTR [rsp+44],eax
    inc DWORD PTR [rsp+40]
split_fill_next:
    inc r15d
    jmp split_fill_loop
split_fill_tail:
    mov rcx,rbx
    lea rdx,[rsp+64]
    mov r8d,DWORD PTR [rsp+44]
    mov r9d,r14d
    sub r9d,r8d
    call split_piece
    test rax,rax
    jz split_zero
    mov ecx,DWORD PTR [rsp+60]
    mov rdx,QWORD PTR [rsp+112]
    mov QWORD PTR [rdx+rcx*8],rax
    inc ecx
    cmp ecx,DWORD PTR [rsp+56]
    jne split_bad
split_result:
    mov rax,QWORD PTR [rsp+112]
    jmp split_done
split_unsupported:
    mov DWORD PTR [rbx],20
    jmp split_zero
split_bad:
    mov DWORD PTR [rbx],7
split_zero:
    xor eax,eax
split_done:
    add rsp,160
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_split ENDP
END
