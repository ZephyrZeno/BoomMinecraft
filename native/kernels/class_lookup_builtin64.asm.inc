.code
boom_java_class_lookup_builtin PROC FRAME
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
 sub rsp,56
 .allocstack 56
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov r13,r8
 mov DWORD PTR [rsp+40],r9d
 mov DWORD PTR [rsp+48],0
 mov DWORD PTR [rsp+52],0
 test rbx,rbx
 jz jfn_zero
 cmp DWORD PTR [rbx],0
 jne jfn_zero
 test r13,r13
 jz jfn_bad
 cmp DWORD PTR [r13],04A43464Eh
 jne jfn_bad
 cmp DWORD PTR [r13+4],1
 jne jfn_bad
 cmp r9d,1
 ja jfn_bad
 mov eax,DWORD PTR [r13+8]
 dec eax
 cmp eax,0FFFFFh
 ja jfn_bad
 cmp DWORD PTR [r13+12],0
 je jfn_bad
 cmp DWORD PTR [r13+12],0100000h
 ja jfn_bad
 cmp DWORD PTR [r13+76],0
 jne jfn_bad
 cmp DWORD PTR [r13+92],32
 jne jfn_bad
 cmp DWORD PTR [r13+96],16
 jne jfn_bad
 cmp DWORD PTR [r13+108],1
 jne jfn_bad
 cmp QWORD PTR [r13+112],0
 jne jfn_bad
 cmp QWORD PTR [r13+120],0
 jne jfn_bad
 mov rsi,QWORD PTR [r13+16]
 test rsi,rsi
 jz jfn_bad
 cmp DWORD PTR [rsi],04A434C53h
 jne jfn_bad
 cmp DWORD PTR [rsi+4],1
 jne jfn_bad
 mov eax,DWORD PTR [r13+8]
 cmp eax,DWORD PTR [rsi+12]
 jne jfn_bad
 mov r8,r13
 mov r9,rsi
 call jfn_loader_config_valid
 test eax,eax
 jz jfn_bad
 mov eax,DWORD PTR [r13+100]
 cmp eax,DWORD PTR [rsi+108]
 jne jfn_bad
 mov rax,QWORD PTR [r13+32]
 test rax,rax
 jz jfn_bad
 cmp DWORD PTR [rax],04A434254h
 jne jfn_bad
 cmp DWORD PTR [rax+4],1
 jne jfn_bad
 cmp QWORD PTR [rax+16],rsi
 jne jfn_bad
 cmp DWORD PTR [rax+8],2
 jne jfn_unbound
 mov rdi,QWORD PTR [r13+24]
 test rdi,rdi
 jz jfn_bad
 cmp DWORD PTR [rdi],04A534C50h
 jne jfn_bad
 cmp DWORD PTR [rdi+4],1
 jne jfn_bad
 mov eax,DWORD PTR [r13+64]
 cmp eax,DWORD PTR [rdi+48]
 jne jfn_bad
 mov eax,DWORD PTR [r13+68]
 cmp eax,DWORD PTR [rdi+52]
 jne jfn_bad
 cmp QWORD PTR [r13+40],0
 je jfn_bad
 cmp QWORD PTR [r13+48],0
 je jfn_bad
 cmp QWORD PTR [r13+80],0
 je jfn_bad
 mov rax,QWORD PTR [r13+56]
 test rax,rax
 jz jfn_bad
 cmp rax,QWORD PTR [rsi+48]
 jne jfn_bad
 mov rdx,QWORD PTR [r13+32]
 cmp QWORD PTR [rdx+24],rdi
 jne jfn_bad
 mov rcx,QWORD PTR [rax]
 test rcx,rcx
 jz jfn_unbound
 test r12,r12
 jz jfn_bad
 mov r14,QWORD PTR [r12]
 test r14,r14
 jz jfn_null
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz jfn_bad
 mov rcx,r14
 mov rdx,QWORD PTR [rdi+40]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jfn_zero
 mov eax,DWORD PTR [r13+68]
 cmp rax,QWORD PTR [r14-16]
 jae jfn_bad
 movzx ebp,BYTE PTR [r14+rax]
 cmp ebp,1
 ja jfn_bad
 mov eax,DWORD PTR [r13+64]
 test al,7
 jnz jfn_bad
 lea rdx,[rax+8]
 cmp rdx,QWORD PTR [r14-16]
 ja jfn_bad
 mov r14,QWORD PTR [r14+rax]
 mov rcx,QWORD PTR [r13+56]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz jfn_bad
 cmp QWORD PTR [r14-8],264
 jne jfn_bad
 cmp DWORD PTR [r14-20],0
 jne jfn_bad
 mov r15,QWORD PTR [r14-16]
 test ebp,ebp
 jz jfn_string_ready
 test r15b,1
 jnz jfn_bad
 shr r15,1
jfn_string_ready:
 cmp DWORD PTR [rsp+40],0
 jne jfn_hash
 ; Non-null loader dispatch must remain a real Java loading operation. Validate
 ; the source type before reporting that unprovided domain.
 mov rdx,QWORD PTR [r12+16]
 test rdx,rdx
 jz jfn_caller
 mov rcx,QWORD PTR [r13+56]
 mov rcx,QWORD PTR [rcx]
 call boom_heap_contains
 test eax,eax
 jz jfn_bad
 mov rcx,QWORD PTR [r12+16]
 mov rdx,QWORD PTR [rsi+40]
 mov r8,QWORD PTR [rsi+112]
 mov r9,rbx
 call boom_runtime_instanceof
 test eax,eax
 jz jfn_bad
 mov rcx,rbx
 mov rdx,QWORD PTR [r12+16]
 mov r8,rsi
 mov r9,r13
 call jfn_known_loader
 cmp DWORD PTR [rbx],0
 jne jfn_zero
 mov DWORD PTR [rsp+48],eax
 jmp jfn_caller
jfn_caller:
 mov r8,QWORD PTR [r12+24]
 test r8,r8
 jz jfn_hash
 mov rcx,rbx
 mov rdx,rsi
 call boom_java_class_typeid
 cmp eax,0FFFFFFFFh
 je jfn_zero
jfn_hash:
 cmp r15,65535
 ja jfn_missing
 cmp DWORD PTR [rsp+48],0
 je jfn_g_scalar
 test r15,r15
 jz jfn_g_scalar
 test ebp,ebp
 jnz jfn_g_array_wide
 movzx eax,BYTE PTR [r14]
 jmp jfn_g_array_check
jfn_g_array_wide:
 movzx eax,WORD PTR [r14]
jfn_g_array_check:
 cmp eax,91
 je jfn_unbound
jfn_g_scalar:
 xor eax,eax
 xor r10d,r10d
jfn_g_hash_loop:
 cmp r10,r15
 jae jfn_g_hash_done
 test ebp,ebp
 jnz jfn_g_hash_wide
 movzx edx,BYTE PTR [r14+r10]
 jmp jfn_g_hash_unit
jfn_g_hash_wide:
 movzx edx,WORD PTR [r14+r10*2]
jfn_g_hash_unit:
 imul eax,eax,31
 add eax,edx
 inc r10d
 jmp jfn_g_hash_loop
jfn_g_hash_done:
 mov DWORD PTR [rsp+44],eax
 mov DWORD PTR [rsp+52],0
jfn_g_domain:
 mov eax,DWORD PTR [rsp+44]
 mov QWORD PTR [rsp+32],rax
 mov rcx,r14
 mov rdx,r15
 mov r8d,ebp
 mov r9d,DWORD PTR [rsp+52]
 call jfn_find_domain
 test edx,edx
 jnz jfn_bad
 test rax,rax
 jnz jfn_g_domain_found
 inc DWORD PTR [rsp+52]
 mov eax,DWORD PTR [rsp+52]
 cmp eax,DWORD PTR [rsp+48]
 jbe jfn_g_domain
 jmp jfn_array_missing
jfn_g_domain_found:
 mov rdi,rax
 jmp jfn_found
jfn_found:
 cmp DWORD PTR [rdi+20],0
 jne jfn_bad
 cmp QWORD PTR [rdi+24],0
 jne jfn_bad
 test DWORD PTR [rdi+16],1
 jz jfn_unbound
 mov r8d,DWORD PTR [rdi+12]
 cmp r8d,DWORD PTR [r13+8]
 jae jfn_bad
 mov DWORD PTR [rsp+32],r8d
 mov eax,r8d
 imul rax,48
 add rax,QWORD PTR [rsi+24]
 mov r8d,DWORD PTR [rax+16]
 cmp r8d,DWORD PTR [rsp+52]
 jne jfn_bad
 mov r9d,DWORD PTR [rax+20]
 mov rcx,rbx
 mov rdx,rsi
 call jfn_bind_defining_loader
 test eax,eax
 jz jfn_zero
 cmp DWORD PTR [rbx],0
 jne jfn_zero
 mov r8d,DWORD PTR [rsp+32]
 mov rcx,rbx
 mov rdx,rsi
 call boom_java_class_load
 test rax,rax
 jz jfn_zero
 mov QWORD PTR [rsp+32],rax
 cmp DWORD PTR [rsp+40],1
 je jfn_result
 cmp BYTE PTR [r12+8],0
 je jfn_result
 test DWORD PTR [rdi+16],2
 jnz jfn_result
 mov eax,DWORD PTR [rdi+12]
 shl rax,4
 add rax,QWORD PTR [r13+48]
 mov rcx,QWORD PTR [rax]
 test rcx,rcx
 jz jfn_init_request
 cmp DWORD PTR [rcx],0434C4153h
 jne jfn_bad
 cmp DWORD PTR [rcx+4],2
 jne jfn_bad
 mov edx,DWORD PTR [rdi+12]
 cmp edx,DWORD PTR [rcx+24]
 jne jfn_bad
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz jfn_zero
 cmp DWORD PTR [rbx],0
 jne jfn_zero
 jmp jfn_result
jfn_init_request:
 mov rax,QWORD PTR [rax+8]
 test rax,rax
 jz jfn_unbound
 mov rcx,rbx
 call rax
 cmp DWORD PTR [rbx],0
 je jfn_bad
 jmp jfn_zero
jfn_result:
 mov rax,QWORD PTR [rsp+32]
 jmp jfn_done
jfn_array_missing:
 ; Missing array identities may be created in a future runtime registry. Keep
 ; their domain explicitly unprovided rather than return a false CNFE.
 test r15,r15
 jz jfn_missing
 test ebp,ebp
 jnz jfn_array_wide
 movzx eax,BYTE PTR [r14]
 jmp jfn_array_first
jfn_array_wide:
 movzx eax,WORD PTR [r14]
jfn_array_first:
 cmp eax,91
 jne jfn_missing
 jmp jfn_unbound
jfn_missing:
 cmp DWORD PTR [rsp+40],1
 je jfn_zero
 mov rcx,rbx
 mov rdx,QWORD PTR [r12]
 mov r8,r13
 mov r9d,DWORD PTR [rsp+48]
 call jfn_throw_cnfe
 jmp jfn_zero
jfn_null:
 mov DWORD PTR [rbx],4
 jmp jfn_zero
jfn_unbound:
 mov DWORD PTR [rbx],20
 jmp jfn_zero
jfn_bad:
 mov DWORD PTR [rbx],7
jfn_zero:
 xor eax,eax
jfn_done:
 add rsp,56
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_class_lookup_builtin ENDP
