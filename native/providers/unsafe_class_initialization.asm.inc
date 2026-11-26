; Frozen Unsafe instance natives. UCIN48/1: count8, reserved12, Class pool16,
; InitRow16 table24, heap cell32, Unsafe layout40. Op0 initializes, op1 queries.
.code
PUBLIC boom_provider_unsafe_class_init
boom_provider_unsafe_class_init PROC FRAME
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
 mov rdi,rdx
 mov rsi,r8
 mov r12d,r9d
 test rbx,rbx
 jz uci_zero
 cmp DWORD PTR [rbx],0
 jne uci_zero
 test rdi,rdi
 jz uci_bad
 test rsi,rsi
 jz uci_bad
 cmp r12d,1
 ja uci_bad
 cmp DWORD PTR [rsi],05543494Eh
 jne uci_bad
 cmp DWORD PTR [rsi+4],1
 jne uci_bad
 mov eax,DWORD PTR [rsi+8]
 dec eax
 cmp eax,0FFFFFh
 ja uci_bad
 cmp DWORD PTR [rsi+12],0
 jne uci_bad
 cmp QWORD PTR [rsi+24],0
 je uci_bad
 cmp QWORD PTR [rsi+40],0
 je uci_bad
 mov r13,QWORD PTR [rsi+16]
 test r13,r13
 jz uci_bad
 cmp DWORD PTR [r13],04A434C53h
 jne uci_bad
 cmp DWORD PTR [r13+4],1
 jne uci_bad
 mov eax,DWORD PTR [r13+12]
 cmp eax,DWORD PTR [rsi+8]
 jne uci_bad
 mov rax,QWORD PTR [rsi+32]
 test rax,rax
 jz uci_bad
 cmp rax,QWORD PTR [r13+48]
 jne uci_bad
 mov rcx,QWORD PTR [rax]
 test rcx,rcx
 jz uci_unbound
 mov rdx,QWORD PTR [rdi]
 test rdx,rdx
 jz uci_null
 call boom_heap_contains
 test eax,eax
 jz uci_bad
 mov rcx,QWORD PTR [rdi]
 mov rdx,QWORD PTR [rsi+40]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz uci_zero
 mov rcx,rbx
 mov rdx,r13
 mov r8,QWORD PTR [rdi+8]
 call boom_java_class_typeid
 cmp eax,-1
 je uci_zero
 ; Canonical reverse lookup verified both the identity slot and the type ID.
 mov edi,eax
 imul rax,rdi,48
 add rax,QWORD PTR [r13+24]
 mov rax,QWORD PTR [rax]
 test rax,rax
 jz uci_bad
 cmp DWORD PTR [rax],054595045h
 jne uci_bad
 cmp DWORD PTR [rax+4],1
 jne uci_bad
 mov eax,DWORD PTR [rax+8]
 test eax,eax
 jz uci_zero
 cmp eax,3
 je uci_zero
 ja uci_bad
 mov rax,rdi
 shl rax,4
 add rax,QWORD PTR [rsi+24]
 mov rcx,QWORD PTR [rax]
 mov rdx,QWORD PTR [rax+8]
 test rcx,rcx
 jz uci_unselected
 test rdx,rdx
 jnz uci_bad
 cmp DWORD PTR [rcx],0434C4153h
 jne uci_bad
 cmp DWORD PTR [rcx+4],2
 jne uci_bad
 cmp DWORD PTR [rcx+24],edi
 jne uci_bad
 mov eax,DWORD PTR [rcx+8]
 cmp eax,3
 ja uci_bad
 test r12d,r12d
 jz uci_initialize
 cmp eax,2
 setne al
 movzx eax,al
 jmp uci_done
uci_initialize:
 mov rdx,rbx
 call boom_class_ensure32
 jmp uci_zero
uci_unselected:
 ; A diagnostic trampoline requests the source descriptor. It must set a stop
 ; on either operation; a query must never execute a Java initializer.
 test rdx,rdx
 jz uci_unbound
 mov rcx,rbx
 call rdx
 cmp DWORD PTR [rbx],0
 jne uci_zero
uci_bad:
 mov DWORD PTR [rbx],7
 jmp uci_zero
uci_null:
 mov DWORD PTR [rbx],4
 jmp uci_zero
uci_unbound:
 mov DWORD PTR [rbx],20
uci_zero:
 xor eax,eax
uci_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_unsafe_class_init ENDP
