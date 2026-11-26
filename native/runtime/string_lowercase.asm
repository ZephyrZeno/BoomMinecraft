; Source-bound String.toLowerCase(Locale), VM UTF16 String storage.
; LCAS96 ABI1: strings8,heapCell16,typeMap24,LocaleType32,BaseType40,word48;
; baseOffset56D,languageOffset60D,LocaleBytes64Q,BaseBytes72Q,refs80D/84D;
; flags88D=0,reserved92D=0. Original Locale Java initialization is not bypassed.
; Native state64: chars0Q,len8D,language12D,wordPlan16Q,wordStart24D,
; wordEnd28D,context32Q. language: default0,Turkic1,Lithuanian2,Thai3.
; Dictionary/SPI word providers are not implemented; Thai Sigma fails explicitly.
option casemap:none
EXTERN boom_unicode_case:PROC
EXTERN boom_unicode_context:PROC
EXTERN boom_word_next:PROC
EXTERN boom_word_is_boundary:PROC
EXTERN boom_string_view:PROC
EXTERN boom_string_allocate:PROC
EXTERN boom_runtime_type:PROC
PUBLIC boom_string_lowercase
.code
; chars RCX,index EDX,length R8D -> EAX code point,EDX next index.
lower_read PROC
    movzx eax,WORD PTR [rcx+rdx*2]
    inc edx
    mov r9d,eax
    sub r9d,0D800h
    cmp r9d,03FFh
    ja lower_read_done
    cmp edx,r8d
    jae lower_read_done
    movzx r10d,WORD PTR [rcx+rdx*2]
    sub r10d,0DC00h
    cmp r10d,03FFh
    ja lower_read_done
    shl r9d,10
    lea eax,[r9+r10+010000h]
    inc edx
lower_read_done:
    ret
lower_read ENDP
; chars RCX,index EDX -> EAX preceding code point,EDX preceding index.
lower_before PROC
    dec edx
    movzx eax,WORD PTR [rcx+rdx*2]
    mov r9d,eax
    sub r9d,0DC00h
    cmp r9d,03FFh
    ja lower_before_done
    test edx,edx
    jz lower_before_done
    movzx r10d,WORD PTR [rcx+rdx*2-2]
    sub r10d,0D800h
    cmp r10d,03FFh
    ja lower_before_done
    shl r10d,10
    lea eax,[r9+r10+010000h]
    dec edx
lower_before_done:
    ret
lower_before ENDP
; heap RCX,oop RDX -> complete live block. No tag reads before bounds.
lower_owned PROC
    mov rax,QWORD PTR [rcx+16]
    test rax,rax
    jz lower_owned_no
    cmp rax,040000000h
    ja lower_owned_no
    lea r10,[rcx+128]
    add rax,r10
    jc lower_owned_no
    cmp rax,QWORD PTR [rcx+24]
    jne lower_owned_no
    lea r10,[rcx+160]
    cmp rdx,r10
    jb lower_owned_no
    cmp rdx,rax
    ja lower_owned_no
    test dl,15
    jnz lower_owned_no
    mov r10d,DWORD PTR [rdx-24]
    and r10d,0FFFFFFFDh
    cmp r10d,0B00B0001h
    jne lower_owned_no
    mov r10,QWORD PTR [rdx-32]
    cmp r10,32
    jb lower_owned_no
    test r10b,15
    jnz lower_owned_no
    sub r10,32
    cmp QWORD PTR [rdx-16],r10
    ja lower_owned_no
    add r10,rdx
    jc lower_owned_no
    cmp r10,rax
    ja lower_owned_no
    mov eax,1
    ret
lower_owned_no:
    xor eax,eax
    ret
lower_owned ENDP
; (context,oop,LCAS pool)->immutable UTF16 view EAX pointer,EDX units.
lower_string PROC FRAME
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
    jz lower_string_null
    mov rax,QWORD PTR [rdi+16]
    mov r12,QWORD PTR [rax]
    mov rcx,r12
    mov rdx,rsi
    call lower_owned
    test eax,eax
    jz lower_string_bad
    mov rax,QWORD PTR [rdi+8]
    mov rax,QWORD PTR [rax+40]
    cmp QWORD PTR [rsi-8],rax
    jne lower_string_bad
    cmp QWORD PTR [rsi-16],16
    jne lower_string_bad
    cmp DWORD PTR [rsi-20],1
    jne lower_string_bad
    mov rcx,r12
    mov rdx,QWORD PTR [rsi]
    call lower_owned
    test eax,eax
    jz lower_string_bad
    mov rcx,rsi
    mov rdx,QWORD PTR [rdi+8]
    mov rdx,QWORD PTR [rdx+40]
    mov r8,rbx
    call boom_string_view
    jmp lower_string_done
lower_string_null:
    mov DWORD PTR [rbx],4
    jmp lower_string_zero
lower_string_bad:
    mov DWORD PTR [rbx],7
lower_string_zero:
    xor eax,eax
    xor edx,edx
lower_string_done:
    add rsp,40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
lower_string ENDP
; (index ECX,mode EDX,state R8)->Before_Dot(mode0)/More_Above(mode1).
lower_following PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,r8
    lea esi,[rcx+1]
    mov edi,edx
lower_following_loop:
    cmp esi,DWORD PTR [rbx+8]
    jae lower_following_no
    mov rcx,QWORD PTR [rbx]
    mov edx,esi
    mov r8d,DWORD PTR [rbx+8]
    call lower_read
    mov esi,edx
    test edi,edi
    jnz lower_following_cc
    cmp eax,0307h
    je lower_following_yes
lower_following_cc:
    mov ecx,eax
    call boom_unicode_context
    and eax,255
    test eax,eax
    jz lower_following_no
    cmp eax,230
    jne lower_following_loop
    test edi,edi
    jz lower_following_no
lower_following_yes:
    mov eax,1
    jmp lower_following_done
lower_following_no:
    xor eax,eax
lower_following_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
lower_following ENDP
; (index ECX,state RDX)->After_I.
lower_after_i PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rdx
    mov esi,ecx
lower_after_loop:
    test esi,esi
    jz lower_after_no
    mov rcx,QWORD PTR [rbx]
    mov edx,esi
    call lower_before
    mov esi,edx
    cmp eax,049h
    je lower_after_yes
    mov ecx,eax
    call boom_unicode_context
    and eax,255
    test eax,eax
    jz lower_after_no
    cmp eax,230
    jne lower_after_loop
lower_after_no:
    xor eax,eax
    jmp lower_after_done
lower_after_yes:
    mov eax,1
lower_after_done:
    add rsp,40
    pop rsi
    pop rbx
    ret
lower_after_i ENDP
; (Sigma index ECX,state RDX)->Final_Cased, -1 metadata/provider error.
lower_sigma PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rdx
    mov edi,ecx
    cmp DWORD PTR [rbx+12],3
    je lower_sigma_provider
    mov DWORD PTR [rsp+40],-1
    mov esi,edi
lower_sigma_before_loop:
    lea rax,[rsp+40]
    mov QWORD PTR [rsp+32],rax
    mov rcx,QWORD PTR [rbx]
    mov edx,DWORD PTR [rbx+8]
    mov r8d,esi
    mov r9,QWORD PTR [rbx+16]
    call boom_word_is_boundary
    cmp eax,-1
    je lower_sigma_bad
    test eax,eax
    jnz lower_sigma_no
    mov rcx,QWORD PTR [rbx]
    mov edx,esi
    call lower_before
    mov esi,edx
    mov ecx,eax
    call boom_unicode_context
    test eax,256
    jz lower_sigma_before_loop
    lea esi,[rdi+1]
lower_sigma_after_loop:
    cmp esi,DWORD PTR [rbx+8]
    jae lower_sigma_yes
    lea rax,[rsp+40]
    mov QWORD PTR [rsp+32],rax
    mov rcx,QWORD PTR [rbx]
    mov edx,DWORD PTR [rbx+8]
    mov r8d,esi
    mov r9,QWORD PTR [rbx+16]
    call boom_word_is_boundary
    cmp eax,-1
    je lower_sigma_bad
    test eax,eax
    jnz lower_sigma_yes
    mov rcx,QWORD PTR [rbx]
    mov edx,esi
    mov r8d,DWORD PTR [rbx+8]
    call lower_read
    mov esi,edx
    mov ecx,eax
    call boom_unicode_context
    test eax,256
    jnz lower_sigma_no
    jmp lower_sigma_after_loop
lower_sigma_provider:
    mov rax,QWORD PTR [rbx+32]
    mov DWORD PTR [rax],20
    jmp lower_sigma_error
lower_sigma_bad:
    mov rax,QWORD PTR [rbx+32]
    mov DWORD PTR [rax],7
lower_sigma_error:
    mov eax,-1
    jmp lower_sigma_done
lower_sigma_yes:
    mov eax,1
    jmp lower_sigma_done
lower_sigma_no:
    xor eax,eax
lower_sigma_done:
    add rsp,48
    pop rdi
    pop rsi
    pop rbx
    ret
lower_sigma ENDP
; (code point ECX,index EDX,state R8)->packed UTF16 RAX,count EDX(0..3).
lower_map PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,r8
    mov esi,ecx
    mov edi,edx
    cmp esi,03A3h
    je lower_map_sigma
    cmp DWORD PTR [rbx+12],1
    je lower_map_turkic
    cmp DWORD PTR [rbx+12],2
    je lower_map_lithuanian
lower_map_general:
    cmp esi,0130h
    je lower_map_dotted
lower_map_simple:
    mov ecx,esi
    mov edx,1
    call boom_unicode_case
    cmp eax,0FFFFh
    jbe lower_map_one
    sub eax,010000h
    mov ecx,eax
    and ecx,03FFh
    or ecx,0DC00h
    shl ecx,16
    shr eax,10
    or eax,0D800h
    or eax,ecx
    jmp lower_map_two
lower_map_turkic:
    cmp esi,0130h
    je lower_map_i
    cmp esi,0307h
    je lower_map_remove_dot
    cmp esi,049h
    jne lower_map_general
    mov ecx,edi
    xor edx,edx
    mov r8,rbx
    call lower_following
    test eax,eax
    jnz lower_map_simple
    mov eax,0131h
    jmp lower_map_one
lower_map_remove_dot:
    mov ecx,edi
    mov rdx,rbx
    call lower_after_i
    test eax,eax
    jz lower_map_simple
    xor eax,eax
    xor edx,edx
    jmp lower_map_done
lower_map_lithuanian:
    cmp esi,0CCh
    je lower_map_lt_grave
    cmp esi,0CDh
    je lower_map_lt_acute
    cmp esi,0128h
    je lower_map_lt_tilde
    cmp esi,049h
    je lower_map_lt_above
    cmp esi,04Ah
    je lower_map_lt_above
    cmp esi,012Eh
    jne lower_map_general
lower_map_lt_above:
    mov ecx,edi
    mov edx,1
    mov r8,rbx
    call lower_following
    test eax,eax
    jz lower_map_simple
    mov ecx,esi
    mov edx,1
    call boom_unicode_case
    or eax,03070000h
    jmp lower_map_two
lower_map_lt_grave:
    mov rax,0030003070069h
    jmp lower_map_three
lower_map_lt_acute:
    mov rax,0030103070069h
    jmp lower_map_three
lower_map_lt_tilde:
    mov rax,0030303070069h
lower_map_three:
    mov edx,3
    jmp lower_map_done
lower_map_i:
    mov eax,069h
    jmp lower_map_one
lower_map_dotted:
    mov eax,03070069h
lower_map_two:
    mov edx,2
    jmp lower_map_done
lower_map_sigma:
    mov ecx,edi
    mov rdx,rbx
    call lower_sigma
    cmp eax,-1
    je lower_map_error
    test eax,eax
    mov eax,03C3h
    jz lower_map_one
    mov eax,03C2h
lower_map_one:
    mov edx,1
    jmp lower_map_done
lower_map_error:
    xor eax,eax
    mov edx,-1
lower_map_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
lower_map ENDP

; (Context32 RCX,argv{String,Locale} RDX,LCAS96 R8)->String/NULL.
boom_string_lowercase PROC FRAME
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
    jz lower_zero
    cmp DWORD PTR [rbx],0
    jne lower_zero
    test rsi,rsi
    jz lower_bad
    test rdi,rdi
    jz lower_bad
    cmp DWORD PTR [rdi],05341434Ch
    jne lower_bad
    cmp DWORD PTR [rdi+4],1
    jne lower_bad
    cmp QWORD PTR [rdi+88],0
    jne lower_bad
    mov ecx,8
lower_pool_pointers:
    cmp QWORD PTR [rdi+rcx],0
    je lower_bad
    add ecx,8
    cmp ecx,56
    jb lower_pool_pointers
    mov rax,QWORD PTR [rdi+16]
    mov r12,QWORD PTR [rax]
    test r12,r12
    jz lower_bad
    cmp DWORD PTR [r12],048454150h
    jne lower_bad
    cmp DWORD PTR [r12+4],1
    jne lower_bad
    mov r13,QWORD PTR [rsi]
    mov rax,QWORD PTR [rsi+8]
    mov QWORD PTR [rsp+32],rax
    mov rcx,rbx
    mov rdx,r13
    mov r8,rdi
    call lower_string
    cmp DWORD PTR [rbx],0
    jne lower_zero
    mov r14,rax
    mov r15d,edx
    mov rsi,QWORD PTR [rsp+32]
    test rsi,rsi
    jz lower_null
    mov rcx,r12
    mov rdx,rsi
    call lower_owned
    test eax,eax
    jz lower_bad
    mov rax,QWORD PTR [rdi+64]
    cmp QWORD PTR [rsi-16],rax
    jne lower_bad
    mov eax,DWORD PTR [rdi+80]
    cmp DWORD PTR [rsi-20],eax
    jne lower_bad
    mov rcx,rsi
    mov rdx,QWORD PTR [rdi+24]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne lower_zero
    cmp rax,QWORD PTR [rdi+32]
    jne lower_bad
    xor esi,esi
lower_initial_scan:
    cmp esi,r15d
    jae lower_unchanged
    movzx ecx,WORD PTR [r14+rsi*2]
    mov eax,ecx
    sub eax,0D800h
    cmp eax,07FFh
    jbe lower_convert
    mov DWORD PTR [rsp+112],ecx
    mov edx,1
    call boom_unicode_case
    cmp eax,DWORD PTR [rsp+112]
    jne lower_convert
    inc esi
    jmp lower_initial_scan
lower_convert:
    mov QWORD PTR [rsp+48],r14
    mov DWORD PTR [rsp+56],r15d
    mov DWORD PTR [rsp+60],0
    mov rax,QWORD PTR [rdi+48]
    mov QWORD PTR [rsp+64],rax
    mov QWORD PTR [rsp+72],0
    mov QWORD PTR [rsp+80],rbx
    mov rsi,QWORD PTR [rsp+32]
    mov eax,DWORD PTR [rdi+56]
    test al,7
    jnz lower_bad
    mov ecx,DWORD PTR [rsi-20]
    shl rcx,3
    cmp rax,rcx
    jae lower_bad
    mov rsi,QWORD PTR [rsi+rax]
    test rsi,rsi
    jz lower_null
    mov rcx,r12
    mov rdx,rsi
    call lower_owned
    test eax,eax
    jz lower_bad
    mov rax,QWORD PTR [rdi+72]
    cmp QWORD PTR [rsi-16],rax
    jne lower_bad
    mov eax,DWORD PTR [rdi+84]
    cmp DWORD PTR [rsi-20],eax
    jne lower_bad
    mov rcx,rsi
    mov rdx,QWORD PTR [rdi+24]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne lower_zero
    cmp rax,QWORD PTR [rdi+40]
    jne lower_bad
    mov eax,DWORD PTR [rdi+60]
    test al,7
    jnz lower_bad
    mov ecx,DWORD PTR [rsi-20]
    shl rcx,3
    cmp rax,rcx
    jae lower_bad
    mov rdx,QWORD PTR [rsi+rax]
    mov rcx,rbx
    mov r8,rdi
    call lower_string
    cmp DWORD PTR [rbx],0
    jne lower_zero
    cmp edx,2
    jne lower_pass_begin
    cmp DWORD PTR [rax],00720074h
    je lower_turkic
    cmp DWORD PTR [rax],007A0061h
    je lower_turkic
    cmp DWORD PTR [rax],0074006Ch
    je lower_lithuanian
    cmp DWORD PTR [rax],00680074h
    jne lower_pass_begin
    mov DWORD PTR [rsp+60],3
    jmp lower_pass_begin
lower_turkic:
    mov DWORD PTR [rsp+60],1
    jmp lower_pass_begin
lower_lithuanian:
    mov DWORD PTR [rsp+60],2
lower_pass_begin:
    mov DWORD PTR [rsp+112],0
    mov DWORD PTR [rsp+116],0
    mov DWORD PTR [rsp+124],0
lower_pass_loop:
    mov edx,DWORD PTR [rsp+112]
    cmp edx,r15d
    jae lower_pass_complete
    mov rcx,r14
    mov r8d,r15d
    call lower_read
    mov DWORD PTR [rsp+148],edx
    mov ecx,eax
    mov edx,DWORD PTR [rsp+112]
    lea r8,[rsp+48]
    call lower_map
    cmp DWORD PTR [rbx],0
    jne lower_zero
    cmp edx,3
    ja lower_bad
    cmp DWORD PTR [rsp+124],0
    jne lower_write_units
    add DWORD PTR [rsp+116],edx
    js lower_oom
    jmp lower_pass_advance
lower_write_units:
    mov ecx,DWORD PTR [rsp+144]
    mov r8d,ecx
    add r8d,edx
    cmp r8d,DWORD PTR [rsp+116]
    ja lower_bad
    mov DWORD PTR [rsp+144],r8d
    mov r9,QWORD PTR [rsp+136]
lower_write_loop:
    test edx,edx
    jz lower_pass_advance
    mov WORD PTR [r9+rcx*2],ax
    shr rax,16
    inc ecx
    dec edx
    jmp lower_write_loop
lower_pass_advance:
    mov eax,DWORD PTR [rsp+148]
    mov DWORD PTR [rsp+112],eax
    jmp lower_pass_loop
lower_pass_complete:
    cmp DWORD PTR [rsp+124],0
    jne lower_result
    mov rcx,r12
    mov rdx,QWORD PTR [rdi+8]
    mov r8d,DWORD PTR [rsp+116]
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz lower_zero
    mov QWORD PTR [rsp+128],rax
    mov rax,QWORD PTR [rax]
    mov QWORD PTR [rsp+136],rax
    mov QWORD PTR [rsp+72],0
    mov DWORD PTR [rsp+112],0
    mov DWORD PTR [rsp+124],1
    mov DWORD PTR [rsp+144],0
    jmp lower_pass_loop
lower_result:
    mov eax,DWORD PTR [rsp+144]
    cmp eax,DWORD PTR [rsp+116]
    jne lower_bad
    mov rax,QWORD PTR [rsp+128]
    jmp lower_done
lower_unchanged:
    mov rax,r13
    jmp lower_done
lower_null:
    mov DWORD PTR [rbx],4
    jmp lower_zero
lower_oom:
    mov DWORD PTR [rbx],3
    jmp lower_zero
lower_bad:
    mov DWORD PTR [rbx],7
lower_zero:
    xor eax,eax
lower_done:
    add rsp,160
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_lowercase ENDP
END
