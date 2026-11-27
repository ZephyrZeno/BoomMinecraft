; VRCB160/1. Source CP rows and active operation/runtime-family dispatch only.
; Win64(ctx RCX, unchanged argv RDX, immutable pool R8, immutable site R9).
; Site32: caller0,cp4,opcode8,operation12,argTypeIds16/20/24,resultTag28.
; Dispatch64: operation0,runtimeType4,originalJava8,layout16,exactFMAP24,
; receiverClassFMAP32,fieldClassFMAP40,argCount48,resultTag52,flags56,res60.
; No Java field writes, native resources, persistent oop roots, or held locks.
PUBLIC boom_varhandle_reference_cas
.code
boom_varhandle_reference_cas PROC FRAME
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
 jz vrc_zero
 cmp DWORD PTR [rbx],0
 jne vrc_zero
 cmp QWORD PTR [rbx+16],0
 jne vrc_zero
 mov rax,QWORD PTR [rbx+4]
 mov QWORD PTR [rsp+48],rax
 mov eax,DWORD PTR [rbx+12]
 mov DWORD PTR [rsp+56],eax
 test r12,r12
 jz vrc_bad
 test r13,r13
 jz vrc_bad
 cmp DWORD PTR [r13],042435256h
 jne vrc_bad
 cmp DWORD PTR [r13+4],1
 jne vrc_bad
 cmp DWORD PTR [r13+8],160
 jne vrc_bad
 mov eax,DWORD PTR [r13+12]
 dec eax
 cmp eax,0FFFFFh
 ja vrc_bad
 cmp DWORD PTR [r13+60],32
 jne vrc_bad
 cmp DWORD PTR [r13+64],64
 jne vrc_bad
 cmp DWORD PTR [r13+68],0
 jne vrc_bad
 mov eax,DWORD PTR [r13+56]
 dec eax
 cmp eax,31
 ja vrc_bad
 mov ecx,104
vrc_reserved:
 cmp QWORD PTR [r13+rcx],0
 jne vrc_bad
 add ecx,8
 cmp ecx,160
 jb vrc_reserved
 mov ecx,16
vrc_pointers:
 cmp QWORD PTR [r13+rcx],0
 je vrc_bad
 add ecx,8
 cmp ecx,56
 jb vrc_pointers
 mov ecx,72
vrc_exception_pointers:
 cmp QWORD PTR [r13+rcx],0
 je vrc_bad
 add ecx,8
 cmp ecx,104
 jb vrc_exception_pointers
 mov rdi,QWORD PTR [r13+16]
 mov rdi,QWORD PTR [rdi]
 test rdi,rdi
 jz vrc_bad
 cmp DWORD PTR [rdi],048454150h
 jne vrc_bad
 cmp DWORD PTR [rdi+4],1
 jne vrc_bad
 mov QWORD PTR [rsp+72],rdi
 mov r10,QWORD PTR [r13+24]
 cmp DWORD PTR [r10],052545950h
 jne vrc_bad
 cmp DWORD PTR [r10+4],2
 jne vrc_bad
 mov r11,QWORD PTR [r13+32]
 cmp DWORD PTR [r11],04A434C53h
 jne vrc_bad
 cmp DWORD PTR [r11+4],1
 jne vrc_bad
 mov eax,DWORD PTR [r10+12]
 test eax,eax
 jz vrc_bad
 cmp eax,DWORD PTR [r11+12]
 jne vrc_bad
 mov rdx,r14
 sub rdx,QWORD PTR [r13+40]
 jc vrc_bad
 test edx,31
 jnz vrc_bad
 mov ecx,DWORD PTR [r13+12]
 shl rcx,5
 cmp rdx,rcx
 jae vrc_bad
 cmp DWORD PTR [r14+8],182
 jne vrc_bad
 cmp DWORD PTR [r14+12],1
 jne vrc_unsupported
 cmp DWORD PTR [r14+28],1
 jne vrc_unsupported
 cmp DWORD PTR [r14+16],eax
 jae vrc_bad
 cmp DWORD PTR [r14+20],eax
 jae vrc_bad
 cmp DWORD PTR [r14+24],eax
 jae vrc_bad
 mov rsi,QWORD PTR [r12]
 test rsi,rsi
 jz vrc_null
 mov rcx,rdi
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz vrc_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+24]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz vrc_zero
 cmp DWORD PTR [rax+20],0
 jne vrc_unsupported
 mov edi,DWORD PTR [rax+16]
 mov r15,QWORD PTR [r13+48]
 mov ecx,DWORD PTR [r13+56]
vrc_dispatch:
 mov edx,DWORD PTR [r14+12]
 cmp edx,DWORD PTR [r15]
 jne vrc_next_dispatch
 cmp edi,DWORD PTR [r15+4]
 je vrc_dispatch_found
vrc_next_dispatch:
 add r15,64
 dec ecx
 jnz vrc_dispatch
 jmp vrc_unsupported
vrc_dispatch_found:
 cmp DWORD PTR [r15+48],3
 jne vrc_bad
 cmp DWORD PTR [r15+52],1
 jne vrc_bad
 cmp DWORD PTR [r15+56],1
 jne vrc_bad
 cmp DWORD PTR [r15+60],0
 jne vrc_bad
 mov ecx,8
vrc_dispatch_pointers:
 cmp QWORD PTR [r15+rcx],0
 je vrc_bad
 add ecx,8
 cmp ecx,48
 jb vrc_dispatch_pointers
 mov rcx,rsi
 mov rdx,QWORD PTR [r15+16]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz vrc_zero
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [r15+24]
 cmp DWORD PTR [rbx],0
 jne vrc_zero
 test rax,rax
 jz vrc_bad
 movzx eax,BYTE PTR [rax]
 test eax,eax
 jz vrc_call_original
 cmp eax,1
 jne vrc_bad
 ; Exact mode compares symbolic CP coordinates with represented Class IDs.
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [r15+32]
 cmp DWORD PTR [rbx],0
 jne vrc_zero
 test rax,rax
 jz vrc_bad
 mov r8,QWORD PTR [rax]
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 call boom_java_class_typeid
 cmp DWORD PTR [rbx],0
 jne vrc_zero
 cmp eax,DWORD PTR [r14+16]
 jne vrc_wrong_method_type
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [r15+40]
 cmp DWORD PTR [rbx],0
 jne vrc_zero
 test rax,rax
 jz vrc_bad
 mov r8,QWORD PTR [rax]
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 call boom_java_class_typeid
 cmp DWORD PTR [rbx],0
 jne vrc_zero
 cmp eax,DWORD PTR [r14+20]
 jne vrc_wrong_method_type
 cmp eax,DWORD PTR [r14+24]
 jne vrc_wrong_method_type
vrc_call_original:
 mov rcx,rbx
 mov rdx,r12
 call QWORD PTR [r15+8]
 jmp vrc_done
vrc_wrong_method_type:
 ; Real selected original WMT() ctor; its detailed JDK message is out of scope.
 mov rcx,QWORD PTR [r13+72]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz vrc_zero
 mov rcx,QWORD PTR [rsp+72]
 mov rdx,QWORD PTR [r13+80]
 mov r8,rbx
 call boom_object_new
 cmp DWORD PTR [rbx],0
 jne vrc_zero
 test rax,rax
 jz vrc_oom
 mov QWORD PTR [rsp+80],rax
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [r13+88]
 cmp DWORD PTR [rbx],0
 jne vrc_zero
 mov rax,QWORD PTR [rsp+48]
 mov QWORD PTR [rbx+4],rax
 mov eax,DWORD PTR [rsp+56]
 mov DWORD PTR [rbx+12],eax
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+80]
 mov r8,QWORD PTR [r13+24]
 mov r9,QWORD PTR [r13+96]
 call boom_exception_set32
 jmp vrc_zero
vrc_null:
 mov DWORD PTR [rbx],4
 jmp vrc_zero
vrc_bad:
 mov DWORD PTR [rbx],7
 jmp vrc_zero
vrc_oom:
 mov DWORD PTR [rbx],3
 jmp vrc_zero
vrc_unsupported:
 mov DWORD PTR [rbx],20
vrc_zero:
 xor eax,eax
vrc_done:
 add rsp,96
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_varhandle_reference_cas ENDP
