; Normal Reference get0/refersTo0/clear0 and PhantomReference.refersTo0.
; RGET48/2: heapCell8, inherited referent FMAP16, runtimeMap24,
; PhantomReference TypeDesc32, FinalReference TypeDesc40.
; op0 get,1 weak identity,2 clear,3 phantom identity. No pending-list service.
; Nonmoving heap; collection requires quiescence. Reads take one aligned
; snapshot. Clear linearizes at an atomic xchg and never enqueues a reference.
PUBLIC boom_provider_reference_referent_get
.code
boom_provider_reference_referent_get PROC FRAME
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
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,r8
 mov r12,rdx
 mov r13d,r9d
 test rbx,rbx
 jz refget_zero
 cmp DWORD PTR [rbx],0
 jne refget_zero
 cmp r13d,3
 ja refget_invalid
 test rsi,rsi
 jz refget_invalid
 cmp DWORD PTR [rsi],054454752h
 jne refget_invalid
 cmp DWORD PTR [rsi+4],2
 jne refget_invalid
 cmp QWORD PTR [rsi+8],0
 je refget_invalid
 cmp QWORD PTR [rsi+16],0
 je refget_invalid
 cmp QWORD PTR [rsi+24],0
 je refget_invalid
 cmp QWORD PTR [rsi+32],0
 je refget_invalid
 cmp QWORD PTR [rsi+40],0
 je refget_invalid
 test r12,r12
 jz refget_invalid
 mov rdi,QWORD PTR [r12]
 test rdi,rdi
 jz refget_null
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz refget_invalid
 mov rcx,rdi
 mov rdx,QWORD PTR [rsi+24]
 mov r8,rbx
 call boom_runtime_type
 test rax,rax
 jz refget_zero
 mov rcx,rax
 mov rdx,QWORD PTR [rsi+32]
 cmp r13d,2
 jne refget_phantom_guard
 mov rdx,QWORD PTR [rsi+40]
 call boom_type_assignable
 test eax,eax
 jnz refget_invalid
 jmp refget_field
refget_phantom_guard:
 call boom_type_assignable
 cmp r13d,3
 je refget_require_phantom
 test eax,eax
 jnz refget_invalid
 jmp refget_field
refget_require_phantom:
 test eax,eax
 jz refget_invalid
refget_field:
 mov rcx,rdi
 mov rdx,rbx
 call QWORD PTR [rsi+16]
 test rax,rax
 jz refget_zero
 mov rdi,rax
 mov r14,QWORD PTR [rdi]
 test r14,r14
 jz refget_action
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz refget_invalid
refget_action:
 test r13d,r13d
 jz refget_value
 cmp r13d,2
 je refget_clear
 mov r12,QWORD PTR [r12+8]
 test r12,r12
 jz refget_compare
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r12
 call boom_heap_contains
 test eax,eax
 jz refget_invalid
refget_compare:
 xor eax,eax
 cmp r14,r12
 sete al
 jmp refget_done
refget_clear:
 xor eax,eax
 xchg QWORD PTR [rdi],rax
 jmp refget_zero
refget_value:
 mov rax,r14
 jmp refget_done
refget_null:
 mov DWORD PTR [rbx],4
 jmp refget_zero
refget_invalid:
 mov DWORD PTR [rbx],7
refget_zero:
 xor eax,eax
refget_done:
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_reference_referent_get ENDP
