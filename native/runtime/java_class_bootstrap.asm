; Normal-source Class bootstrap, Context32. No host/JVM guest execution.
; Pool80: JCBT/1/state8/nativeCount12, ClassPool16 StringPool24
; NativeRow24*32 PrimitiveRow16*40, primitiveCount48/reserved52
; system/application defaults56/60, sourceClassId64/reserved68/reserved72.
; NativeRow24: operation0 method4 entry8 flags16 reserved20.
; Primitives: UTF16 name*0 charCount8 typeId12. No represented-class init.
option casemap:none
EXTERN boom_heap_contains:PROC
EXTERN boom_object_check:PROC
EXTERN boom_java_class_load:PROC
EXTERN boom_java_class_typeid:PROC
PUBLIC boom_java_class_bootstrap
.code
boom_java_class_bootstrap PROC FRAME
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
 mov r12,rdx
 mov r13,r8
 mov DWORD PTR [rsp+32],r9d
 test rbx,rbx
 jz jcb_zero
 cmp DWORD PTR [rbx],0
 jne jcb_zero
 test r13,r13
 jz jcb_bad
 cmp DWORD PTR [r13],04A434254h
 jne jcb_bad
 cmp DWORD PTR [r13+4],1
 jne jcb_bad
 cmp DWORD PTR [r13+12],10
 jne jcb_bad
 cmp DWORD PTR [r13+48],9
 jne jcb_bad
 cmp DWORD PTR [r13+52],0
 jne jcb_bad
 cmp DWORD PTR [r13+56],1
 ja jcb_bad
 cmp DWORD PTR [r13+60],1
 ja jcb_bad
 cmp DWORD PTR [r13+68],0
 jne jcb_bad
 cmp QWORD PTR [r13+72],0
 jne jcb_bad
 mov rsi,QWORD PTR [r13+16]
 test rsi,rsi
 jz jcb_bad
 cmp DWORD PTR [rsi],04A434C53h
 jne jcb_bad
 cmp DWORD PTR [rsi+4],1
 jne jcb_bad
 mov eax,DWORD PTR [r13+64]
 cmp eax,DWORD PTR [rsi+108]
 jne jcb_bad
 cmp DWORD PTR [rsp+32],0
 je jcb_register
 cmp DWORD PTR [r13+8],2
 jne jcb_unbound
 test r12,r12
 jz jcb_bad
 cmp DWORD PTR [rsp+32],10
 je jcb_primitive
 cmp DWORD PTR [rsp+32],11
 jne jcb_bad
 mov rcx,rbx
 mov rdx,rsi
 mov r8,QWORD PTR [r12]
 call boom_java_class_typeid
 cmp eax,0FFFFFFFFh
 je jcb_zero
 imul rax,48
 add rax,QWORD PTR [rsi+24]
 mov r10,QWORD PTR [rax]
 mov edx,DWORD PTR [r10+8]
 xor ecx,ecx
 test edx,edx
 jz jcb_assertion_done
 cmp edx,3
 je jcb_assertion_done
 mov ecx,DWORD PTR [r13+56]
 cmp DWORD PTR [rax+16],0
 je jcb_assertion_done
 mov ecx,DWORD PTR [r13+60]
jcb_assertion_done:
 mov eax,ecx
 jmp jcb_done
jcb_register:
 mov rdi,QWORD PTR [r13+32]
 test rdi,rdi
 jz jcb_bad
 xor r14d,r14d
 xor r15d,r15d
jcb_registration_row:
 mov ecx,DWORD PTR [rdi]
 cmp ecx,11
 ja jcb_bad
 test ecx,ecx
 jz jcb_bad
 mov eax,1
 shl eax,cl
 test r14d,eax
 jnz jcb_bad
 or r14d,eax
 cmp DWORD PTR [rdi+4],0
 je jcb_bad
 cmp QWORD PTR [rdi+8],0
 je jcb_bad
 mov eax,DWORD PTR [rdi+16]
 and eax,0100h
 cmp eax,0100h
 jne jcb_bad
 cmp DWORD PTR [rdi+20],0
 jne jcb_bad
 inc r15d
 add rdi,24
 cmp r15d,10
 jb jcb_registration_row
 cmp r14d,0DFEh
 jne jcb_bad
 xor eax,eax
 mov edx,2
 lock cmpxchg DWORD PTR [r13+8],edx
 test eax,eax
 jz jcb_zero
 cmp eax,2
 jne jcb_bad
 jmp jcb_zero
jcb_primitive:
 mov rdi,QWORD PTR [r13+40]
 test rdi,rdi
 jz jcb_bad
 mov r14,QWORD PTR [r12]
 test r14,r14
 jz jcb_null
 mov rcx,QWORD PTR [rsi+48]
 test rcx,rcx
 jz jcb_bad
 mov rcx,QWORD PTR [rcx]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz jcb_bad
 mov r15,QWORD PTR [r13+24]
 test r15,r15
 jz jcb_bad
 cmp DWORD PTR [r15],04A534C50h
 jne jcb_bad
 cmp DWORD PTR [r15+4],1
 jne jcb_bad
 cmp DWORD PTR [r15+48],0
 jne jcb_bad
 mov rcx,r14
 mov rdx,QWORD PTR [r15+40]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jcb_zero
 mov eax,DWORD PTR [r15+52]
 cmp eax,8
 jb jcb_bad
 cmp rax,QWORD PTR [r14-16]
 jae jcb_bad
 movzx eax,BYTE PTR [r14+rax]
 cmp eax,1
 ja jcb_bad
 mov DWORD PTR [rsp+36],eax
 mov r14,QWORD PTR [r14]
 test r14,r14
 jz jcb_bad
 mov rcx,QWORD PTR [rsi+48]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz jcb_bad
 cmp QWORD PTR [r14-8],264
 jne jcb_bad
 mov r15,QWORD PTR [r14-16]
 mov ecx,DWORD PTR [rsp+36]
 test ecx,ecx
 jz jcb_name_ready
 test r15b,1
 jnz jcb_bad
 shr r15,1
jcb_name_ready:
 xor r12d,r12d
jcb_name_row:
 mov eax,DWORD PTR [rdi+8]
 cmp rax,r15
 jne jcb_next_name
 mov r10,QWORD PTR [rdi]
 test r10,r10
 jz jcb_bad
 xor edx,edx
jcb_name_character:
 cmp rdx,r15
 jae jcb_primitive_found
 cmp DWORD PTR [rsp+36],0
 jne jcb_name_wide
 movzx eax,BYTE PTR [r14+rdx]
 jmp jcb_name_compare
jcb_name_wide:
 movzx eax,WORD PTR [r14+rdx*2]
jcb_name_compare:
 cmp ax,WORD PTR [r10+rdx*2]
 jne jcb_next_name
 inc rdx
 jmp jcb_name_character
jcb_next_name:
 add rdi,16
 inc r12d
 cmp r12d,9
 jb jcb_name_row
 mov DWORD PTR [rbx],19
 jmp jcb_zero
jcb_primitive_found:
 mov r8d,DWORD PTR [rdi+12]
 cmp r8d,DWORD PTR [rsi+12]
 jae jcb_bad
 mov eax,r8d
 imul rax,48
 add rax,QWORD PTR [rsi+24]
 mov rax,QWORD PTR [rax]
 test rax,rax
 jz jcb_bad
 cmp DWORD PTR [rax+8],0
 jne jcb_bad
 mov rcx,rbx
 mov rdx,rsi
 call boom_java_class_load
 jmp jcb_done
jcb_null:
 mov DWORD PTR [rbx],4
 jmp jcb_zero
jcb_unbound:
 mov DWORD PTR [rbx],20
 jmp jcb_zero
jcb_bad:
 mov DWORD PTR [rbx],7
jcb_zero:
 xor eax,eax
jcb_done:
 add rsp,64
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_class_bootstrap ENDP
END
