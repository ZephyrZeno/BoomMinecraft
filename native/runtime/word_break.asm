; Source-bound RuleBasedBreakIterator forward/backward DFA for case context.
; WBRP96 ABI2: states8D,categories12D; stateTable16,end24,lookahead32,
; BMPindex40,BMPbytes48,supplementary56; stateLength64D,BMPsize68D,
; supplementaryCount72D,reserved76D0,backwards80,backLength88D,backStates92D.
option casemap:none
PUBLIC boom_word_next
PUBLIC boom_word_is_boundary
.code
; (code point ECX,plan RDX)->category EAX, -1 ignore, -2 invalid metadata.
word_category PROC
    cmp ecx,0FFFFh
    ja word_category_supplementary
    mov r8d,ecx
    shr r8d,7
    mov r10,QWORD PTR [rdx+40]
    movzx eax,WORD PTR [r10+r8*2]
    and ecx,127
    add eax,ecx
    cmp eax,DWORD PTR [rdx+68]
    jae word_category_bad
    mov r10,QWORD PTR [rdx+48]
    movsx eax,BYTE PTR [r10+rax]
    jmp word_category_check
word_category_supplementary:
    mov r9d,ecx
    xor r10d,r10d
    mov r11d,DWORD PTR [rdx+72]
    sub r11d,2
    mov r8,QWORD PTR [rdx+56]
word_category_search:
    cmp r10d,r11d
    ja word_category_bad
    lea ecx,[r10+r11]
    shr ecx,1
    mov eax,DWORD PTR [r8+rcx*4]
    shr eax,8
    cmp r9d,eax
    jb word_category_less
    mov eax,DWORD PTR [r8+rcx*4+4]
    shr eax,8
    cmp r9d,eax
    jae word_category_greater
    movzx eax,BYTE PTR [r8+rcx*4]
    cmp eax,255
    jne word_category_check
    mov eax,-1
    ret
word_category_less:
    test ecx,ecx
    jz word_category_bad
    lea r11d,[rcx-1]
    jmp word_category_search
word_category_greater:
    lea r10d,[rcx+1]
    jmp word_category_search
word_category_check:
    cmp eax,-1
    je word_category_done
    cmp eax,DWORD PTR [rdx+12]
    jae word_category_bad
word_category_done:
    ret
word_category_bad:
    mov eax,-2
    ret
word_category ENDP

; (UTF16 chars RCX,length EDX,start R8D,plan R9)->next boundary or -1.
; Trusted span view supplied by the String VM. No allocation or collection.
; U+FFFF retains the original CharacterIterator.DONE behavior.
boom_word_next PROC FRAME
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
    sub rsp,48
    .allocstack 48
    .endprolog
    mov r12,rcx
    mov ebx,edx
    mov r14d,r8d
    mov DWORD PTR [rsp+32],r8d
    mov r13,r9
    test ebx,ebx
    js word_next_invalid
    cmp r14d,ebx
    jae word_next_invalid
    test r12,r12
    jz word_next_invalid
    test r13,r13
    jz word_next_invalid
    cmp DWORD PTR [r13],050524257h
    jne word_next_invalid
    cmp DWORD PTR [r13+4],2
    jne word_next_invalid
    cmp DWORD PTR [r13+76],0
    jne word_next_invalid
    mov eax,DWORD PTR [r13+8]
    cmp eax,2
    jb word_next_invalid
    cmp eax,4096
    ja word_next_invalid
    mov ecx,DWORD PTR [r13+12]
    dec ecx
    cmp ecx,254
    ja word_next_invalid
    inc ecx
    imul eax,ecx
    cmp eax,DWORD PTR [r13+64]
    jne word_next_invalid
    cmp DWORD PTR [r13+68],128
    jb word_next_invalid
    cmp DWORD PTR [r13+68],65536
    ja word_next_invalid
    mov eax,DWORD PTR [r13+72]
    sub eax,2
    cmp eax,65534
    ja word_next_invalid
    mov ecx,16
word_next_pointers:
    cmp QWORD PTR [r13+rcx],0
    je word_next_invalid
    add ecx,8
    cmp ecx,64
    jb word_next_pointers
    xor edi,edi
    mov r15d,1
    mov esi,-1
word_next_loop:
    cmp r14d,ebx
    jae word_next_finish
    movzx ecx,WORD PTR [r12+r14*2]
    inc r14d
    mov eax,ecx
    sub eax,0D800h
    cmp eax,03FFh
    ja word_next_decoded
    cmp r14d,ebx
    jae word_next_decoded
    movzx edx,WORD PTR [r12+r14*2]
    sub edx,0DC00h
    cmp edx,03FFh
    ja word_next_decoded
    shl eax,10
    lea ecx,[rax+rdx+010000h]
    inc r14d
word_next_decoded:
    cmp esi,-1
    jne word_next_have_initial
    mov esi,r14d
word_next_have_initial:
    cmp ecx,0FFFFh
    je word_next_at_done
    mov rdx,r13
    call word_category
    cmp eax,-2
    je word_next_invalid
    cmp eax,-1
    je word_next_state
    mov ecx,r15d
    imul ecx,DWORD PTR [r13+12]
    add ecx,eax
    mov r10,QWORD PTR [r13+16]
    movzx r15d,WORD PTR [r10+rcx*2]
    cmp r15d,DWORD PTR [r13+8]
    jae word_next_invalid
word_next_state:
    mov r10,QWORD PTR [r13+24]
    mov r11,QWORD PTR [r13+32]
    cmp BYTE PTR [r11+r15],0
    je word_next_accepting
    cmp BYTE PTR [r10+r15],0
    jne word_next_accept_lookahead
    mov edi,r14d
    jmp word_next_advance
word_next_accept_lookahead:
    mov esi,edi
    jmp word_next_advance
word_next_accepting:
    cmp BYTE PTR [r10+r15],0
    je word_next_advance
    mov esi,r14d
word_next_advance:
    test r15d,r15d
    jnz word_next_loop
word_next_finish:
    cmp r14d,ebx
    jae word_next_at_done
    cmp WORD PTR [r12+r14*2],0FFFFh
    jne word_next_result
word_next_at_done:
    cmp edi,ebx
    jne word_next_result
    mov esi,edi
word_next_result:
    cmp esi,DWORD PTR [rsp+32]
    jbe word_next_invalid
    cmp esi,ebx
    ja word_next_invalid
    mov eax,esi
    jmp word_next_return
word_next_invalid:
    mov eax,-1
word_next_return:
    add rsp,48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_word_next ENDP

; chars RCX,index EDX,len R8D -> EAX current CP,EDX next index.
word_current PROC
    cmp edx,r8d
    jae word_current_end
    movzx eax,WORD PTR [rcx+rdx*2]
    inc edx
    mov r9d,eax
    sub r9d,0D800h
    cmp r9d,03FFh
    ja word_current_done
    cmp edx,r8d
    jae word_current_done
    movzx r10d,WORD PTR [rcx+rdx*2]
    sub r10d,0DC00h
    cmp r10d,03FFh
    ja word_current_done
    shl r9d,10
    lea eax,[r9+r10+010000h]
    inc edx
word_current_done:
    ret
word_current_end:
    mov edx,r8d
    mov eax,0FFFFh
    ret
word_current ENDP
; chars RCX,index EDX -> EAX preceding CP,EDX previous index.
word_previous PROC
    test edx,edx
    jz word_previous_begin
    dec edx
    movzx eax,WORD PTR [rcx+rdx*2]
    mov r9d,eax
    sub r9d,0DC00h
    cmp r9d,03FFh
    ja word_previous_done
    test edx,edx
    jz word_previous_done
    movzx r10d,WORD PTR [rcx+rdx*2-2]
    sub r10d,0D800h
    cmp r10d,03FFh
    ja word_previous_done
    shl r10d,10
    lea eax,[r9+r10+010000h]
    dec edx
word_previous_done:
    ret
word_previous_begin:
    mov eax,0FFFFh
    ret
word_previous ENDP
; handlePrevious(chars RCX,len EDX,index R8D,plan R9) -> safe position/-1.
word_safe_previous PROC FRAME
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
    sub rsp,32
    .allocstack 32
    .endprolog
    mov r12,rcx
    mov ebx,edx
    mov r14d,r8d
    mov r13,r9
    mov r15d,1
    xor esi,esi
    xor edi,edi
    mov edx,r14d
    mov r8d,ebx
    call word_current
word_previous_loop:
    cmp eax,0FFFFh
    je word_previous_return_index
    test r15d,r15d
    jz word_previous_adjust
    mov edi,esi
    mov ecx,eax
    mov rdx,r13
    call word_category
    cmp eax,-2
    je word_previous_invalid
    mov esi,eax
    cmp eax,-1
    je word_previous_step
    mov ecx,r15d
    imul ecx,DWORD PTR [r13+12]
    add ecx,eax
    cmp ecx,DWORD PTR [r13+88]
    jae word_previous_invalid
    mov r10,QWORD PTR [r13+80]
    movzx r15d,WORD PTR [r10+rcx*2]
    cmp r15d,DWORD PTR [r13+92]
    jae word_previous_invalid
word_previous_step:
    mov rcx,r12
    mov edx,r14d
    call word_previous
    mov r14d,edx
    jmp word_previous_loop
word_previous_adjust:
    mov rcx,r12
    mov edx,r14d
    mov r8d,ebx
    call word_current
    mov r14d,edx
    cmp edi,-1
    je word_previous_return_index
    mov rcx,r12
    mov edx,r14d
    mov r8d,ebx
    call word_current
    mov r14d,edx
word_previous_return_index:
    mov eax,r14d
    jmp word_previous_finish
word_previous_invalid:
    mov eax,-1
word_previous_finish:
    add rsp,32
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
word_safe_previous ENDP

; isBoundary(chars RCX,len EDX,index R8D,plan R9,cache* stack40).
; Cache is cachedLastKnownBreak (initial -1) for this logical iterator.
; Returns 0/1 or -1 for invalid metadata/view. Exact following(index-1) path.
boom_word_is_boundary PROC FRAME
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
    mov rsi,rcx
    mov ebx,edx
    mov r12d,r8d
    mov rdi,r9
    mov r13,QWORD PTR [rsp+128]
    test ebx,ebx
    js word_boundary_invalid
    cmp r12d,ebx
    ja word_boundary_invalid
    test r13,r13
    jz word_boundary_invalid
    test rdi,rdi
    jz word_boundary_invalid
    cmp DWORD PTR [rdi],050524257h
    jne word_boundary_invalid
    cmp DWORD PTR [rdi+4],2
    jne word_boundary_invalid
    cmp DWORD PTR [rdi+76],0
    jne word_boundary_invalid
    test r12d,r12d
    jz word_boundary_yes
    test rsi,rsi
    jz word_boundary_invalid
    mov eax,DWORD PTR [rdi+12]
    dec eax
    cmp eax,254
    ja word_boundary_invalid
    inc eax
    mov ecx,DWORD PTR [rdi+92]
    cmp ecx,2
    jb word_boundary_invalid
    cmp ecx,4096
    ja word_boundary_invalid
    imul eax,ecx
    cmp eax,DWORD PTR [rdi+88]
    jne word_boundary_invalid
    cmp QWORD PTR [rdi+80],0
    je word_boundary_invalid
    mov ecx,16
word_boundary_pointers:
    cmp QWORD PTR [rdi+rcx],0
    je word_boundary_invalid
    add ecx,8
    cmp ecx,64
    jb word_boundary_pointers
    cmp DWORD PTR [rdi+68],128
    jb word_boundary_invalid
    cmp DWORD PTR [rdi+68],65536
    ja word_boundary_invalid
    mov eax,DWORD PTR [rdi+72]
    sub eax,2
    cmp eax,65534
    ja word_boundary_invalid
    lea eax,[r12-1]
    test eax,eax
    jz word_boundary_first
    mov r14d,DWORD PTR [r13]
    cmp r14d,-1
    jle word_boundary_backward
    cmp r14d,eax
    jl word_boundary_forward
word_boundary_backward:
    mov rcx,rsi
    mov edx,ebx
    lea r8d,[r12-1]
    mov r9,rdi
    call word_safe_previous
    cmp eax,-1
    je word_boundary_invalid
    mov r14d,eax
    jmp word_boundary_forward
word_boundary_first:
    xor r14d,r14d
word_boundary_forward:
    lea eax,[r12-1]
    cmp r14d,eax
    jg word_boundary_compare
    mov rcx,rsi
    mov edx,ebx
    mov r8d,r14d
    mov r9,rdi
    call boom_word_next
    cmp eax,-1
    je word_boundary_invalid
    mov r14d,eax
    jmp word_boundary_forward
word_boundary_compare:
    mov DWORD PTR [r13],r14d
    cmp r14d,r12d
    sete al
    movzx eax,al
    jmp word_boundary_done
word_boundary_yes:
    mov eax,1
    jmp word_boundary_done
word_boundary_invalid:
    mov eax,-1
word_boundary_done:
    add rsp,40
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_word_is_boundary ENDP
END
