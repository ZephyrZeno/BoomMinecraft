; Normal-source bootstrap class lookup. JCFN128/1, NameRow32, InitRow16.
; (Context32,raw managed argv,pool,op0 forName / op1 findBootstrapClass).
; Bootstrap-only. Custom Java loader dispatch and new array identities remain
; explicit unavailable domains. No JVM callbacks or hidden host resolution.
option casemap:none
EXTERN boom_heap_contains:PROC
EXTERN boom_object_check:PROC
EXTERN boom_runtime_instanceof:PROC
EXTERN boom_java_class_typeid:PROC
EXTERN boom_java_class_load:PROC
EXTERN boom_class_ensure32:PROC
PUBLIC boom_java_class_lookup
.code
boom_java_class_lookup PROC FRAME
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
 mov rdx,QWORD PTR [rsi+112]
 mov r8,QWORD PTR [rsi+40]
 mov r9,rbx
 call boom_runtime_instanceof
 test eax,eax
 jz jfn_bad
 jmp jfn_unbound
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
 xor eax,eax
 xor r10d,r10d
jfn_hash_loop:
 cmp r10,r15
 jae jfn_hash_done
 test ebp,ebp
 jnz jfn_hash_wide
 movzx edx,BYTE PTR [r14+r10]
 jmp jfn_hash_unit
jfn_hash_wide:
 movzx edx,WORD PTR [r14+r10*2]
jfn_hash_unit:
 imul eax,eax,31
 add eax,edx
 inc r10d
 jmp jfn_hash_loop
jfn_hash_done:
 mov DWORD PTR [rsp+44],eax
 mov rdi,QWORD PTR [r13+40]
 xor ecx,ecx
 mov edx,DWORD PTR [r13+12]
jfn_lower:
 cmp ecx,edx
 jae jfn_lower_done
 mov r10d,edx
 sub r10d,ecx
 shr r10d,1
 add r10d,ecx
 mov r11d,r10d
 shl r11,5
 cmp DWORD PTR [rdi+r11+8],eax
 jb jfn_lower_right
 mov edx,r10d
 jmp jfn_lower
jfn_lower_right:
 lea ecx,[r10+1]
 jmp jfn_lower
jfn_lower_done:
 mov r10d,ecx
jfn_collision:
 cmp r10d,DWORD PTR [r13+12]
 jae jfn_array_missing
 mov eax,r10d
 shl rax,5
 lea rdi,[rax+rdi]
 mov eax,DWORD PTR [rsp+44]
 cmp eax,DWORD PTR [rdi+8]
 jne jfn_array_missing
 cmp r15d,DWORD PTR [rdi+4]
 jne jfn_next
 mov eax,DWORD PTR [rdi]
 add rax,r15
 mov edx,DWORD PTR [r13+88]
 cmp rax,rdx
 ja jfn_bad
 mov eax,DWORD PTR [rdi]
 mov r11,QWORD PTR [r13+80]
 lea r11,[r11+rax*2]
 xor ecx,ecx
jfn_compare:
 cmp rcx,r15
 jae jfn_found
 test ebp,ebp
 jnz jfn_compare_wide
 movzx eax,BYTE PTR [r14+rcx]
 jmp jfn_compare_unit
jfn_compare_wide:
 movzx eax,WORD PTR [r14+rcx*2]
jfn_compare_unit:
 cmp ax,WORD PTR [r11+rcx*2]
 jne jfn_next
 inc ecx
 jmp jfn_compare
jfn_next:
 inc r10d
 mov rdi,QWORD PTR [r13+40]
 jmp jfn_collision
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
 mov DWORD PTR [rbx],16
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
boom_java_class_lookup ENDP
END
