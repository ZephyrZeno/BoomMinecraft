; DCLR160/1 source-proven InnerClasses identity and native error protocol.
; Existing explicit/quiescent GC only. Native frame locals are temporary;
; no monitor/owner lock or lease is held across original Java callbacks.
.code

dclr_string PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
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
 mov r12d,edx
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+80]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz dclr_string_zero
 mov r13,rax
 mov r14d,1
 cmp DWORD PTR [rdi+104],0
 je dclr_string_allocate
 xor eax,eax
dclr_string_scan:
 cmp eax,r12d
 jae dclr_string_latin
 cmp WORD PTR [rsi+rax*2],255
 ja dclr_string_allocate
 inc eax
 jmp dclr_string_scan
dclr_string_latin:
 xor r14d,r14d
dclr_string_allocate:
 mov edx,r12d
 mov ecx,r14d
 shl edx,cl
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 xor r8d,r8d
 mov r9d,264
 call boom_heap_alloc
 test rax,rax
 jz dclr_string_oom
 xor r10d,r10d
dclr_string_copy:
 cmp r10d,r12d
 jae dclr_string_publish
 movzx r11d,WORD PTR [rsi+r10*2]
 test r14d,r14d
 jnz dclr_string_utf16
 mov BYTE PTR [rax+r10],r11b
 jmp dclr_string_next
dclr_string_utf16:
 mov WORD PTR [rax+r10*2],r11w
dclr_string_next:
 inc r10d
 jmp dclr_string_copy
dclr_string_publish:
 mov ecx,DWORD PTR [rdi+96]
 mov QWORD PTR [r13+rcx],rax
 mov ecx,DWORD PTR [rdi+100]
 mov BYTE PTR [r13+rcx],r14b
 mov rax,r13
 jmp dclr_string_done
dclr_string_oom:
 mov DWORD PTR [rbx],3
dclr_string_zero:
 xor eax,eax
dclr_string_done:
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rsi
 ret
dclr_string ENDP

dclr_throw PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 sub rsp,96
 .allocstack 96
 .endprolog
 mov rsi,r15
 mov rax,QWORD PTR [rbx+4]
 mov QWORD PTR [rsp+64],rax
 mov eax,DWORD PTR [rbx+12]
 mov DWORD PTR [rsp+72],eax
 mov rcx,QWORD PTR [rdi+40]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz dclr_throw_done
 mov rcx,QWORD PTR [rdi+88]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz dclr_throw_done
 mov rcx,QWORD PTR [rsi+8]
 mov edx,DWORD PTR [rsi+16]
 call dclr_string
 test rax,rax
 jz dclr_throw_done
 mov QWORD PTR [rsp+40],rax
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+48]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz dclr_throw_done
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+56],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rdi+56]
 cmp DWORD PTR [rbx],0
 jne dclr_throw_done
 cmp QWORD PTR [rbx+16],0
 jne dclr_throw_done
 mov rax,QWORD PTR [rsp+64]
 mov QWORD PTR [rbx+4],rax
 mov eax,DWORD PTR [rsp+72]
 mov DWORD PTR [rbx+12],eax
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+56]
 mov r8,QWORD PTR [rdi+72]
 mov r9,QWORD PTR [rdi+64]
 call boom_exception_set32
dclr_throw_done:
 xor eax,eax
 add rsp,96
 pop r13
 pop r12
 pop rsi
 ret
dclr_throw ENDP

PUBLIC boom_declaring_class_service
boom_declaring_class_service PROC FRAME
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
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 test rbx,rbx
 jz dclr_zero
 cmp DWORD PTR [rbx],0
 jne dclr_zero
 cmp QWORD PTR [rbx+16],0
 jne dclr_zero
 test rsi,rsi
 jz dclr_bad
 lea rax,boom_declaring_class_pool
 cmp rdi,rax
 jne dclr_bad
 test r9d,r9d
 jnz dclr_bad
 cmp DWORD PTR [rdi],044434C52h
 jne dclr_bad
 cmp DWORD PTR [rdi+4],1
 jne dclr_bad
 mov eax,DWORD PTR [rdi+8]
 dec eax
 cmp eax,0FFFFFh
 ja dclr_bad
 cmp DWORD PTR [rdi+12],32
 jne dclr_bad
 cmp DWORD PTR [rdi+104],1
 ja dclr_bad
 cmp DWORD PTR [rdi+108],160
 jne dclr_bad
 cmp DWORD PTR [rdi+116],0
 jne dclr_bad
 mov ecx,120
dclr_reserved:
 cmp QWORD PTR [rdi+rcx],0
 jne dclr_bad
 add ecx,8
 cmp ecx,160
 jb dclr_reserved
 mov ecx,16
dclr_pointers:
 cmp QWORD PTR [rdi+rcx],0
 je dclr_bad
 add ecx,8
 cmp ecx,88
 jbe dclr_pointers
 mov r10,QWORD PTR [rdi+16]
 cmp DWORD PTR [r10],04A434C53h
 jne dclr_bad
 cmp DWORD PTR [r10+4],1
 jne dclr_bad
 mov r11,QWORD PTR [rdi+72]
 cmp QWORD PTR [r10+40],r11
 jne dclr_bad
 cmp DWORD PTR [r11],052545950h
 jne dclr_bad
 cmp DWORD PTR [r11+4],2
 jne dclr_bad
 mov eax,DWORD PTR [r10+12]
 cmp eax,DWORD PTR [r11+12]
 jne dclr_bad
 mov r11,QWORD PTR [rdi+24]
 cmp QWORD PTR [r10+48],r11
 jne dclr_bad
 cmp QWORD PTR [r11],0
 je dclr_unsupported
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 mov r8,QWORD PTR [rsi]
 call boom_java_class_typeid
 cmp eax,-1
 je dclr_zero
 cmp eax,DWORD PTR [rdi+8]
 jae dclr_unsupported
 shl rax,5
 add rax,QWORD PTR [rdi+32]
 mov r15,rax
 mov r12d,DWORD PTR [r15]
 test r12d,r12d
 jz dclr_zero
 cmp r12d,3
 je dclr_unsupported
 cmp r12d,4
 ja dclr_bad
 cmp QWORD PTR [r15+24],0
 jne dclr_bad
 mov r13d,DWORD PTR [r15+4]
 mov r10,QWORD PTR [rdi+16]
 cmp r13d,DWORD PTR [r10+12]
 jae dclr_unsupported
 cmp r12d,4
 jne dclr_resolve_outer
 cmp QWORD PTR [r15+8],0
 je dclr_bad
 cmp DWORD PTR [r15+16],65535
 ja dclr_bad
 cmp DWORD PTR [r15+20],1
 ja dclr_bad
 cmp DWORD PTR [r15+20],1
 je dclr_error
dclr_resolve_outer:
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 mov r8d,r13d
 call boom_java_class_load
 test rax,rax
 jz dclr_zero
 cmp r12d,1
 je dclr_done
 cmp r12d,2
 je dclr_zero
dclr_error:
 call dclr_throw
 jmp dclr_zero
dclr_unsupported:
 mov DWORD PTR [rbx],20
 jmp dclr_zero
dclr_bad:
 mov DWORD PTR [rbx],7
dclr_zero:
 xor eax,eax
dclr_done:
 add rsp,48
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_declaring_class_service ENDP
