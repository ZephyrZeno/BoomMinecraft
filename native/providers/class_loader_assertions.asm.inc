; Source-bound ClassLoader registration and the declared no-override assertion VM.
; LNRP32/1 publishes only retrieveDirectives. It is not a Java Class descriptor.
; Defaults come from the existing, registered normal JCBT80/1 configuration.
; Objects/arrays use the ordinary heap; class state changes only through ensure32.
.code
PUBLIC boom_class_loader_assertions
boom_class_loader_assertions PROC FRAME
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
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 mov rdi,r8
 mov esi,r9d
 test rbx,rbx
 jz cla_zero
 cmp DWORD PTR [rbx],0
 jne cla_zero
 lea rax,boom_class_loader_assertions_pool
 cmp rdi,rax
 jne cla_bad
 cmp DWORD PTR [rdi],050524E4Ch
 jne cla_bad
 cmp DWORD PTR [rdi+4],1
 jne cla_bad
 cmp DWORD PTR [rdi+12],1
 jne cla_bad
 cmp QWORD PTR [rdi+24],0
 jne cla_bad
 lea rax,CLA_RETRIEVE
 cmp QWORD PTR [rdi+16],rax
 jne cla_bad
 test esi,esi
 jz cla_register
 cmp esi,1
 jne cla_bad
 mov eax,DWORD PTR [rdi+8]
 cmp eax,2
 je cla_config
 test eax,eax
 jz cla_unbound
 jmp cla_bad
cla_register:
 xor eax,eax
 mov edx,2
 lock cmpxchg DWORD PTR [rdi+8],edx
 test eax,eax
 jz cla_zero
 cmp eax,2
 jne cla_bad
 jmp cla_zero
cla_config:
 lea r15,boom_java_class_bootstrap_pool
 cmp DWORD PTR [r15],04A434254h
 jne cla_bad
 cmp DWORD PTR [r15+4],1
 jne cla_bad
 cmp DWORD PTR [r15+8],2
 jne cla_unbound
 cmp DWORD PTR [r15+12],10
 jne cla_bad
 cmp DWORD PTR [r15+48],9
 jne cla_bad
 cmp DWORD PTR [r15+52],0
 jne cla_bad
 cmp DWORD PTR [r15+56],1
 ja cla_bad
 mov r13d,DWORD PTR [r15+60]
 cmp r13d,1
 ja cla_bad
 cmp DWORD PTR [r15+64],CLA_CLASS_ID
 jne cla_bad
 cmp DWORD PTR [r15+68],0
 jne cla_bad
 cmp QWORD PTR [r15+72],0
 jne cla_bad
 lea rax,boom_java_class_pool
 cmp QWORD PTR [r15+16],rax
 jne cla_bad
 lea rax,boom_java_string_literal_pool
 cmp QWORD PTR [r15+24],rax
 jne cla_bad
 mov r14,QWORD PTR [boom_heap_ptr]
 test r14,r14
 jz cla_bad
 cmp DWORD PTR [r14],048454150h
 jne cla_bad
 cmp DWORD PTR [r14+4],1
 jne cla_bad
 lea rcx,CLA_DIRECTIVES_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz cla_zero
 mov rcx,r14
 lea rdx,CLA_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz cla_zero
 mov r12,rax
 mov QWORD PTR [rsp+48],0
 ; The VM source creates four arrays, even when all option lists are empty.
 mov rcx,r14
 lea rdx,[rsp+48]
 lea r8,CLA_STRING_ARRAY
 mov r9d,1
 mov QWORD PTR [rsp+32],rbx
 call boom_typed_multi_new
 test rax,rax
 jz cla_zero
 mov QWORD PTR [r12+CLA_PACKAGES],rax
 mov rcx,r14
 lea rdx,[rsp+48]
 lea r8,CLA_BOOLEAN_ARRAY
 mov r9d,1
 mov QWORD PTR [rsp+32],rbx
 call boom_typed_multi_new
 test rax,rax
 jz cla_zero
 mov QWORD PTR [r12+CLA_PACKAGE_ENABLED],rax
 mov rcx,r14
 lea rdx,[rsp+48]
 lea r8,CLA_STRING_ARRAY
 mov r9d,1
 mov QWORD PTR [rsp+32],rbx
 call boom_typed_multi_new
 test rax,rax
 jz cla_zero
 mov QWORD PTR [r12+CLA_CLASSES],rax
 mov rcx,r14
 lea rdx,[rsp+48]
 lea r8,CLA_BOOLEAN_ARRAY
 mov r9d,1
 mov QWORD PTR [rsp+32],rbx
 call boom_typed_multi_new
 test rax,rax
 jz cla_zero
 mov QWORD PTR [r12+CLA_CLASS_ENABLED],rax
 mov BYTE PTR [r12+CLA_DEFAULT],r13b
 mov rax,r12
 jmp cla_done
cla_unbound:
 mov DWORD PTR [rbx],20
 jmp cla_zero
cla_bad:
 mov DWORD PTR [rbx],7
cla_zero:
 xor eax,eax
cla_done:
 add rsp,64
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_class_loader_assertions ENDP
