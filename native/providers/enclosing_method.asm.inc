; ENCM128/1, original EnclosingMethod -> normal fresh Object[3].
; String.ensure precedes temporary allocation; later calls are noncollecting
; native ASM only. Explicit quiescent GC cannot overlap this active call.
.code

encm_string PROC PRIVATE FRAME
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
 mov rdx,QWORD PTR [rdi+40]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz encm_string_zero
 mov r13,rax
 mov r14d,1
 cmp DWORD PTR [rdi+80],0
 je encm_string_allocate
 xor eax,eax
encm_string_scan:
 cmp eax,r12d
 jae encm_string_latin
 cmp WORD PTR [rsi+rax*2],255
 ja encm_string_allocate
 inc eax
 jmp encm_string_scan
encm_string_latin:
 xor r14d,r14d
encm_string_allocate:
 mov edx,r12d
 mov ecx,r14d
 shl edx,cl
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 xor r8d,r8d
 mov r9,QWORD PTR [rdi+64]
 call boom_heap_alloc
 test rax,rax
 jz encm_string_oom
 xor r10d,r10d
encm_string_copy:
 cmp r10d,r12d
 jae encm_string_publish
 movzx r11d,WORD PTR [rsi+r10*2]
 test r14d,r14d
 jnz encm_string_utf16
 mov BYTE PTR [rax+r10],r11b
 jmp encm_string_next
encm_string_utf16:
 mov WORD PTR [rax+r10*2],r11w
encm_string_next:
 inc r10d
 jmp encm_string_copy
encm_string_publish:
 mov ecx,DWORD PTR [rdi+72]
 mov QWORD PTR [r13+rcx],rax
 mov ecx,DWORD PTR [rdi+76]
 mov BYTE PTR [r13+rcx],r14b
 mov rax,r13
 jmp encm_string_done
encm_string_oom:
 mov DWORD PTR [rbx],3
encm_string_zero:
 xor eax,eax
encm_string_done:
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rsi
 ret
encm_string ENDP

PUBLIC boom_enclosing_method_service
boom_enclosing_method_service PROC FRAME
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
 mov rsi,rdx
 mov rdi,r8
 test rbx,rbx
 jz encm_zero
 cmp DWORD PTR [rbx],0
 jne encm_zero
 cmp QWORD PTR [rbx+16],0
 jne encm_zero
 test rsi,rsi
 jz encm_bad
 lea rax,boom_enclosing_method_pool
 cmp rdi,rax
 jne encm_bad
 test r9d,r9d
 jnz encm_bad
 cmp DWORD PTR [rdi],0454E434Dh
 jne encm_bad
 cmp DWORD PTR [rdi+4],1
 jne encm_bad
 mov eax,DWORD PTR [rdi+8]
 dec eax
 cmp eax,0FFFFFh
 ja encm_bad
 cmp DWORD PTR [rdi+12],32
 jne encm_bad
 cmp DWORD PTR [rdi+80],1
 ja encm_bad
 cmp DWORD PTR [rdi+84],128
 jne encm_bad
 cmp DWORD PTR [rdi+92],0
 jne encm_bad
 mov ecx,96
encm_reserved:
 cmp QWORD PTR [rdi+rcx],0
 jne encm_bad
 add ecx,8
 cmp ecx,128
 jb encm_reserved
 mov ecx,16
encm_pointers:
 cmp QWORD PTR [rdi+rcx],0
 je encm_bad
 add ecx,8
 cmp ecx,56
 jbe encm_pointers
 cmp QWORD PTR [rdi+64],264
 jne encm_bad
 mov r10,QWORD PTR [rdi+16]
 cmp DWORD PTR [r10],04A434C53h
 jne encm_bad
 cmp DWORD PTR [r10+4],1
 jne encm_bad
 mov eax,DWORD PTR [r10+12]
 mov r11,QWORD PTR [r10+40]
 test r11,r11
 jz encm_bad
 cmp DWORD PTR [r11],052545950h
 jne encm_bad
 cmp DWORD PTR [r11+4],2
 jne encm_bad
 cmp eax,DWORD PTR [r11+12]
 jne encm_bad
 mov r11,QWORD PTR [rdi+24]
 cmp QWORD PTR [r10+48],r11
 jne encm_bad
 cmp QWORD PTR [r11],0
 je encm_unsupported
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 mov r8,QWORD PTR [rsi]
 call boom_java_class_typeid
 cmp eax,-1
 je encm_zero
 cmp eax,DWORD PTR [rdi+8]
 jae encm_unsupported
 shl rax,5
 add rax,QWORD PTR [rdi+32]
 mov r15,rax
 mov ebp,DWORD PTR [r15]
 test ebp,ebp
 jz encm_zero
 cmp ebp,3
 jae encm_unsupported
 mov r13d,DWORD PTR [r15+4]
 mov r10,QWORD PTR [rdi+16]
 cmp r13d,DWORD PTR [r10+12]
 jae encm_bad
 cmp ebp,2
 je encm_class_only_metadata
 cmp QWORD PTR [r15+8],0
 je encm_bad
 cmp QWORD PTR [r15+16],0
 je encm_bad
 cmp DWORD PTR [r15+24],65535
 ja encm_bad
 cmp DWORD PTR [r15+28],65535
 ja encm_bad
 mov rcx,QWORD PTR [rdi+48]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz encm_zero
 jmp encm_allocate
encm_class_only_metadata:
 cmp QWORD PTR [r15+8],0
 jne encm_bad
 cmp QWORD PTR [r15+16],0
 jne encm_bad
 cmp QWORD PTR [r15+24],0
 jne encm_bad
encm_allocate:
 mov r9,QWORD PTR [rdi+56]
 cmp DWORD PTR [r9],054595045h
 jne encm_bad
 cmp DWORD PTR [r9+4],1
 jne encm_bad
 cmp DWORD PTR [r9+8],3
 jne encm_bad
 cmp QWORD PTR [r9+16],0
 je encm_bad
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov edx,24
 mov r8d,3
 call boom_heap_alloc
 test rax,rax
 jz encm_oom
 mov r14,rax
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 mov r8d,r13d
 call boom_java_class_load
 test rax,rax
 jz encm_zero
 mov QWORD PTR [r14],rax
 cmp ebp,2
 je encm_return_array
 mov rcx,QWORD PTR [r15+8]
 mov edx,DWORD PTR [r15+24]
 call encm_string
 test rax,rax
 jz encm_zero
 mov QWORD PTR [r14+8],rax
 mov rcx,QWORD PTR [r15+16]
 mov edx,DWORD PTR [r15+28]
 call encm_string
 test rax,rax
 jz encm_zero
 mov QWORD PTR [r14+16],rax
encm_return_array:
 mov rax,r14
 jmp encm_done
encm_oom:
 mov DWORD PTR [rbx],3
 jmp encm_zero
encm_unsupported:
 mov DWORD PTR [rbx],20
 jmp encm_zero
encm_bad:
 mov DWORD PTR [rbx],7
encm_zero:
 xor eax,eax
encm_done:
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
boom_enclosing_method_service ENDP
