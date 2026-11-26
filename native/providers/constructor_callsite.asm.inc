; Shared source-constructor call site, ASM only. Entry needs a source-verified
; immutable site, not a user-authored address. Native Constructor selection and
; InvocationTargetException wrapping belong to the outer service.
; (Context32 RCX,boxed Object[]/NULL RDX,Site64 R8,Pool48 R9)->object/NULL RAX.
; EDX=1 only for a pending error from the constructor body; otherwise zero.
; Site64 CINV/1: typeId8D nargs12D noninstantiable16D reserved20D,
; layout24Q classState32Q originalJavaEntry40Q parameters48Q methodId56D res60D.
; Param16: primitive kind0..7 or reference8 at0D, source typeId4D, TypeDesc8Q.
; Pool48 PCIV/1: heapCell8Q runtimeMap16Q BoxPool24Q reserved32/40Q=0.
EXTERN boom_class_ensure32:PROC
EXTERN boom_object_new:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_runtime_row:PROC
EXTERN boom_runtime_instanceof:PROC
EXTERN boom_constructor_unbox:PROC
PUBLIC boom_constructor_callsite
.code
boom_constructor_callsite PROC FRAME
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
 sub rsp,2160
 .allocstack 2160
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov r13,r8
 mov r14,r9
 mov DWORD PTR [rsp+64],0
 mov DWORD PTR [rsp+80],0
 test rbx,rbx
 jz cc_zero
 cmp DWORD PTR [rbx],0
 jne cc_zero
 test r13,r13
 jz cc_bad
 cmp DWORD PTR [r13],0564E4943h
 jne cc_bad
 cmp DWORD PTR [r13+4],1
 jne cc_bad
 cmp DWORD PTR [r13+16],1
 ja cc_bad
 cmp DWORD PTR [r13+20],0
 jne cc_bad
 cmp DWORD PTR [r13+60],0
 jne cc_bad
 mov r12d,DWORD PTR [r13+12]
 cmp r12d,255
 ja cc_bad
 test r12d,r12d
 jz cc_site_params_valid
 cmp QWORD PTR [r13+48],0
 je cc_bad
cc_site_params_valid:
 cmp QWORD PTR [r13+24],0
 je cc_bad
 cmp QWORD PTR [r13+40],0
 je cc_unlinked
 mov rax,QWORD PTR [r13+32]
 test rax,rax
 jz cc_bad
 cmp DWORD PTR [rax],0434C4153h
 jne cc_bad
 cmp DWORD PTR [rax+4],2
 jne cc_bad
 mov edx,DWORD PTR [r13+8]
 cmp DWORD PTR [rax+24],edx
 jne cc_bad
 test r14,r14
 jz cc_bad
 cmp DWORD PTR [r14],056494350h
 jne cc_bad
 cmp DWORD PTR [r14+4],1
 jne cc_bad
 cmp QWORD PTR [r14+32],0
 jne cc_bad
 cmp QWORD PTR [r14+40],0
 jne cc_bad
 cmp QWORD PTR [r14+16],0
 je cc_bad
 mov rax,QWORD PTR [r14+16]
 cmp DWORD PTR [rax],052545950h
 jne cc_bad
 cmp DWORD PTR [rax+4],2
 jne cc_bad
 mov edx,DWORD PTR [r13+8]
 cmp edx,DWORD PTR [rax+12]
 jae cc_bad
 mov rax,QWORD PTR [r14+8]
 test rax,rax
 jz cc_bad
 mov rdi,QWORD PTR [rax]
 test rdi,rdi
 jz cc_bad
 mov rdx,QWORD PTR [r14+24]
 test rdx,rdx
 jz cc_bad
 cmp DWORD PTR [rdx],0564E4342h
 jne cc_bad
 cmp DWORD PTR [rdx+4],1
 jne cc_bad
 cmp DWORD PTR [rdx+8],8
 jne cc_bad
 cmp DWORD PTR [rdx+12],24
 jne cc_bad
 cmp QWORD PTR [rdx+32],0
 je cc_bad
 cmp QWORD PTR [rdx+40],0
 jne cc_bad
 cmp QWORD PTR [rdx+16],rax
 jne cc_bad
 mov rax,QWORD PTR [r14+16]
 cmp QWORD PTR [rdx+24],rax
 jne cc_bad
 stmxcsr DWORD PTR [rsp+72]
 mov DWORD PTR [rsp+76],01F80h
 ldmxcsr DWORD PTR [rsp+76]
 mov DWORD PTR [rsp+80],1
 ; Match the VM's observable order: initialization, eligibility, allocation,
 ; argument checking/conversion, original Java constructor invocation.
 mov rcx,QWORD PTR [r13+32]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz cc_zero
 cmp DWORD PTR [rbx],0
 jne cc_zero
 cmp DWORD PTR [r13+16],0
 jne cc_abstract
 mov rcx,rdi
 mov rdx,QWORD PTR [r13+24]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz cc_zero
 mov r15,rax
 mov rcx,r15
 mov rdx,QWORD PTR [r14+16]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz cc_zero
 cmp DWORD PTR [rax+20],0
 jne cc_bad
 mov edx,DWORD PTR [r13+8]
 cmp DWORD PTR [rax+16],edx
 jne cc_bad
 test rsi,rsi
 jz cc_null_args
 mov rcx,rdi
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz cc_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r14+16]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz cc_zero
 cmp DWORD PTR [rax+20],2
 jne cc_argument
 cmp DWORD PTR [rsi-20],r12d
 jne cc_argument
 jmp cc_args_counted
cc_null_args:
 test r12d,r12d
 jnz cc_argument
cc_args_counted:
 mov QWORD PTR [rsp+96],r15
 mov DWORD PTR [rsp+40],0
cc_arg_loop:
 mov eax,DWORD PTR [rsp+40]
 cmp eax,r12d
 jae cc_invoke
 mov rdx,QWORD PTR [rsi+rax*8]
 mov QWORD PTR [rsp+48],rdx
 shl eax,4
 add rax,QWORD PTR [r13+48]
 mov QWORD PTR [rsp+56],rax
 mov r8d,DWORD PTR [rax]
 cmp r8d,8
 ja cc_bad
 je cc_reference
 mov rcx,rbx
 mov r9,QWORD PTR [r14+24]
 call boom_constructor_unbox
 cmp DWORD PTR [rbx],0
 jne cc_zero
 jmp cc_arg_store
cc_reference:
 mov r8,QWORD PTR [rax+8]
 test r8,r8
 jz cc_bad
 cmp DWORD PTR [r8],054595045h
 jne cc_bad
 cmp DWORD PTR [r8+4],1
 jne cc_bad
 mov eax,DWORD PTR [r8+8]
 dec eax
 cmp eax,2
 ja cc_bad
 test rdx,rdx
 jz cc_reference_null
 mov rcx,rdi
 call boom_heap_contains
 test eax,eax
 jz cc_bad
 mov rcx,QWORD PTR [rsp+48]
 mov rdx,QWORD PTR [r14+16]
 mov rax,QWORD PTR [rsp+56]
 mov r8,QWORD PTR [rax+8]
 mov r9,rbx
 call boom_runtime_instanceof
 cmp DWORD PTR [rbx],0
 jne cc_zero
 test eax,eax
 jz cc_argument
cc_reference_null:
 mov rax,QWORD PTR [rsp+48]
cc_arg_store:
 mov ecx,DWORD PTR [rsp+40]
 mov QWORD PTR [rsp+rcx*8+104],rax
 inc DWORD PTR [rsp+40]
 jmp cc_arg_loop
cc_invoke:
 mov rcx,rbx
 lea rdx,[rsp+96]
 call QWORD PTR [r13+40]
 cmp DWORD PTR [rbx],0
 jne cc_body_error
 mov rax,r15
 jmp cc_done
cc_body_error:
 mov DWORD PTR [rsp+64],1
 jmp cc_zero
cc_abstract:
 mov DWORD PTR [rbx],24
 jmp cc_zero
cc_argument:
 mov DWORD PTR [rbx],18
 jmp cc_zero
cc_unlinked:
 mov DWORD PTR [rbx],20
 jmp cc_zero
cc_bad:
 mov DWORD PTR [rbx],7
cc_zero:
 xor eax,eax
cc_done:
 cmp DWORD PTR [rsp+80],0
 je cc_no_fp_restore
 ldmxcsr DWORD PTR [rsp+72]
cc_no_fp_restore:
 mov edx,DWORD PTR [rsp+64]
 add rsp,2160
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_constructor_callsite ENDP
