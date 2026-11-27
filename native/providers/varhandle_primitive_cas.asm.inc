; VPCP192/1. Source CP shapes and operation/runtime-family dispatch only.
; Win64(ctx RCX, unchanged argv RDX, immutable pool R8, immutable site R9).
; Site64: caller0,cp4,opcode8,operation12,argTYPEs16/20/24,boolTag28,wire32,slots36,res40..63.
; Dispatch80: operation0,runtimeType4,originalJava8,layout16,exactFMAP24,receiverFMAP32,
; primitiveTYPE40,wire44,argCount48,boolTag52,flags56,res60,fieldOffsetFMAP64,res72.
; No Java field writes, native resources, persistent oop roots, or held locks.
PUBLIC boom_varhandle_primitive_compare
.code
boom_varhandle_primitive_compare PROC FRAME
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
 sub rsp,96
 .allocstack 96
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov r13,r8
 mov r14,r9
 test rbx,rbx
 jz vpc_zero
 cmp DWORD PTR [rbx],0
 jne vpc_zero
 cmp QWORD PTR [rbx+16],0
 jne vpc_zero
 mov rax,QWORD PTR [rbx+4]
 mov QWORD PTR [rsp+48],rax
 mov eax,DWORD PTR [rbx+12]
 mov DWORD PTR [rsp+56],eax
 test r12,r12
 jz vpc_bad
 test r13,r13
 jz vpc_bad
 cmp DWORD PTR [r13],050435056h
 jne vpc_bad
 cmp DWORD PTR [r13+4],1
 jne vpc_bad
 cmp DWORD PTR [r13+8],192
 jne vpc_bad
 mov eax,DWORD PTR [r13+12]
 dec eax
 cmp eax,0FFFFFh
 ja vpc_bad
 cmp DWORD PTR [r13+60],64
 jne vpc_bad
 cmp DWORD PTR [r13+64],80
 jne vpc_bad
 cmp DWORD PTR [r13+68],4
 jne vpc_bad
 mov eax,DWORD PTR [r13+56]
 dec eax
 cmp eax,31
 ja vpc_bad
 mov ecx,104
vpc_reserved:
 cmp QWORD PTR [r13+rcx],0
 jne vpc_bad
 add ecx,8
 cmp ecx,192
 jb vpc_reserved
 mov ecx,16
vpc_pointers:
 cmp QWORD PTR [r13+rcx],0
 je vpc_bad
 add ecx,8
 cmp ecx,56
 jb vpc_pointers
 mov ecx,72
vpc_exception_pointers:
 cmp QWORD PTR [r13+rcx],0
 je vpc_bad
 add ecx,8
 cmp ecx,104
 jb vpc_exception_pointers
 mov rdi,QWORD PTR [r13+16]
 mov rdi,QWORD PTR [rdi]
 test rdi,rdi
 jz vpc_bad
 cmp DWORD PTR [rdi],048454150h
 jne vpc_bad
 cmp DWORD PTR [rdi+4],1
 jne vpc_bad
 mov QWORD PTR [rsp+72],rdi
 mov r10,QWORD PTR [r13+24]
 cmp DWORD PTR [r10],052545950h
 jne vpc_bad
 cmp DWORD PTR [r10+4],2
 jne vpc_bad
 mov r11,QWORD PTR [r13+32]
 cmp DWORD PTR [r11],04A434C53h
 jne vpc_bad
 cmp DWORD PTR [r11+4],1
 jne vpc_bad
 mov eax,DWORD PTR [r10+12]
 test eax,eax
 jz vpc_bad
 cmp eax,DWORD PTR [r11+12]
 jne vpc_bad
 mov rdx,r14
 sub rdx,QWORD PTR [r13+40]
 jc vpc_bad
 test edx,63
 jnz vpc_bad
 mov ecx,DWORD PTR [r13+12]
 shl rcx,6
 cmp rdx,rcx
 jae vpc_bad
 cmp DWORD PTR [r14+8],182
 jne vpc_bad
 mov r9d,DWORD PTR [r14+12]
 dec r9d
 cmp r9d,4
 ja vpc_unsupported
 cmp DWORD PTR [r14+28],1
 jne vpc_unsupported
 cmp DWORD PTR [r14+36],4
 jne vpc_bad
 cmp QWORD PTR [r14+40],0
 jne vpc_bad
 cmp QWORD PTR [r14+48],0
 jne vpc_bad
 cmp QWORD PTR [r14+56],0
 jne vpc_bad
 mov r9d,DWORD PTR [r14+32]
 dec r9d
 cmp r9d,1
 ja vpc_unsupported
 mov r9d,DWORD PTR [r14+20]
 cmp r9d,DWORD PTR [r14+24]
 jne vpc_unsupported
 cmp DWORD PTR [r14+16],eax
 jae vpc_bad
 cmp DWORD PTR [r14+20],eax
 jae vpc_bad
 cmp DWORD PTR [r14+24],eax
 jae vpc_bad
 mov rsi,QWORD PTR [r12]
 test rsi,rsi
 jz vpc_null
 mov rcx,rdi
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz vpc_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+24]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz vpc_zero
 cmp DWORD PTR [rax+20],0
 jne vpc_unsupported
 mov edi,DWORD PTR [rax+16]
 mov r15,QWORD PTR [r13+48]
 mov ecx,DWORD PTR [r13+56]
vpc_dispatch:
 mov edx,DWORD PTR [r14+12]
 cmp edx,DWORD PTR [r15]
 jne vpc_next_dispatch
 cmp edi,DWORD PTR [r15+4]
 je vpc_dispatch_found
vpc_next_dispatch:
 add r15,80
 dec ecx
 jnz vpc_dispatch
 jmp vpc_unsupported
vpc_dispatch_found:
 cmp QWORD PTR [r15+64],0
 je vpc_bad
 cmp QWORD PTR [r15+72],0
 jne vpc_bad
 mov r10,QWORD PTR [r13+24]
 mov eax,DWORD PTR [r10+12]
 cmp DWORD PTR [r15+40],eax
 jae vpc_bad
 mov eax,DWORD PTR [r15+44]
 dec eax
 cmp eax,1
 ja vpc_bad
 cmp DWORD PTR [r15+48],3
 jne vpc_bad
 cmp DWORD PTR [r15+52],1
 jne vpc_bad
 cmp DWORD PTR [r15+56],1
 jne vpc_bad
 cmp DWORD PTR [r15+60],0
 jne vpc_bad
 mov ecx,8
vpc_dispatch_pointers:
 cmp QWORD PTR [r15+rcx],0
 je vpc_bad
 add ecx,8
 cmp ecx,40
 jb vpc_dispatch_pointers
 mov rcx,rsi
 mov rdx,QWORD PTR [r15+16]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz vpc_zero
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [r15+24]
 cmp DWORD PTR [rbx],0
 jne vpc_zero
 test rax,rax
 jz vpc_bad
 movzx eax,BYTE PTR [rax]
 test eax,eax
 jz vpc_nonexact_shape
 cmp eax,1
 jne vpc_bad
 ; Exact mode compares symbolic CP coordinates with represented Class IDs.
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [r15+32]
 cmp DWORD PTR [rbx],0
 jne vpc_zero
 test rax,rax
 jz vpc_bad
 mov r8,QWORD PTR [rax]
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 call boom_java_class_typeid
 cmp DWORD PTR [rbx],0
 jne vpc_zero
 cmp eax,DWORD PTR [r14+16]
 jne vpc_wrong_method_type
 mov eax,DWORD PTR [r15+40]
 cmp eax,DWORD PTR [r14+20]
 jne vpc_wrong_method_type
 cmp eax,DWORD PTR [r14+24]
 jne vpc_wrong_method_type
 mov eax,DWORD PTR [r15+44]
 cmp eax,DWORD PTR [r14+32]
 jne vpc_bad
 jmp vpc_call_original
vpc_nonexact_shape:
 ; Same-primitive coordinates only. Widening/boxing are explicit deferred20.
 mov eax,DWORD PTR [r15+40]
 cmp eax,DWORD PTR [r14+20]
 jne vpc_unsupported
 cmp eax,DWORD PTR [r14+24]
 jne vpc_unsupported
 mov eax,DWORD PTR [r15+44]
 cmp eax,DWORD PTR [r14+32]
 jne vpc_unsupported
vpc_call_original:
 mov rcx,rbx
 mov rdx,r12
 call QWORD PTR [r15+8]
 jmp vpc_done
vpc_wrong_method_type:
 ; Real selected original WMT() ctor; its detailed JDK message is out of scope.
 mov rcx,QWORD PTR [r13+72]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz vpc_zero
 mov rcx,QWORD PTR [rsp+72]
 mov rdx,QWORD PTR [r13+80]
 mov r8,rbx
 call boom_object_new
 cmp DWORD PTR [rbx],0
 jne vpc_zero
 test rax,rax
 jz vpc_oom
 mov QWORD PTR [rsp+80],rax
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [r13+88]
 cmp DWORD PTR [rbx],0
 jne vpc_zero
 mov rax,QWORD PTR [rsp+48]
 mov QWORD PTR [rbx+4],rax
 mov eax,DWORD PTR [rsp+56]
 mov DWORD PTR [rbx+12],eax
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+80]
 mov r8,QWORD PTR [r13+24]
 mov r9,QWORD PTR [r13+96]
 call boom_exception_set32
 jmp vpc_zero
vpc_null:
 mov DWORD PTR [rbx],4
 jmp vpc_zero
vpc_bad:
 mov DWORD PTR [rbx],7
 jmp vpc_zero
vpc_oom:
 mov DWORD PTR [rbx],3
 jmp vpc_zero
vpc_unsupported:
 mov DWORD PTR [rbx],20
vpc_zero:
 xor eax,eax
vpc_done:
 add rsp,96
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_varhandle_primitive_compare ENDP
