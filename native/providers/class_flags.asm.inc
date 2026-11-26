; Normal Class access queries. JCFG32/1 cap8D rowBytes12D=16.
; ClassPool16Q rows24Q; Row16 raw0D modifiers4D usable8D reserved12D.
; raw ClassFile flags and reflection modifiers intentionally differ.
; op0 Reflection.getClassAccessFlags(Class); op1 Class.getModifiers().
PUBLIC boom_provider_class_flags_service
.code
boom_provider_class_flags_service PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov DWORD PTR [rsp+32],r9d
 test rbx,rbx
 jz provider_flags_zero
 cmp DWORD PTR [rbx],0
 jne provider_flags_zero
 test rsi,rsi
 jz provider_flags_bad
 test rdi,rdi
 jz provider_flags_bad
 cmp r9d,1
 ja provider_flags_bad
 cmp DWORD PTR [rdi],04A434647h
 jne provider_flags_bad
 cmp DWORD PTR [rdi+4],1
 jne provider_flags_bad
 mov eax,DWORD PTR [rdi+8]
 dec eax
 cmp eax,0FFFFFh
 ja provider_flags_bad
 cmp DWORD PTR [rdi+12],16
 jne provider_flags_bad
 cmp QWORD PTR [rdi+24],0
 je provider_flags_bad
 mov rdx,QWORD PTR [rdi+16]
 test rdx,rdx
 jz provider_flags_bad
 cmp DWORD PTR [rdx],04A434C53h
 jne provider_flags_bad
 cmp DWORD PTR [rdx+4],1
 jne provider_flags_bad
 mov eax,DWORD PTR [rdi+8]
 cmp eax,DWORD PTR [rdx+12]
 jne provider_flags_bad
 mov rcx,rbx
 mov r8,QWORD PTR [rsi]
 call boom_java_class_typeid
 cmp eax,-1
 je provider_flags_zero
 shl rax,4
 add rax,QWORD PTR [rdi+24]
 cmp DWORD PTR [rax+8],1
 jne provider_flags_unavailable
 cmp DWORD PTR [rax+12],0
 jne provider_flags_bad
 mov ecx,DWORD PTR [rsp+32]
 mov eax,DWORD PTR [rax+rcx*4]
 jmp provider_flags_done
provider_flags_unavailable:
 mov DWORD PTR [rbx],20
 jmp provider_flags_zero
provider_flags_bad:
 mov DWORD PTR [rbx],7
provider_flags_zero:
 xor eax,eax
provider_flags_done:
 add rsp,48
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_class_flags_service ENDP
