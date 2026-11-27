; Win64(ctx RCX, original validated name RDX, JCFN128* R8).
; The callback table is source-bound readonly data emitted by the producer.
; No persistent oop, borrowed native memory, or lock survives this function.
; Managed temporaries are held on the active native stack. Collection during
; active frames is forbidden by the current nonmoving/quiescent GC contract.
.code
jfn_throw_cnfe PROC PRIVATE FRAME
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
 sub rsp,80
 .allocstack 80
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 lea r13,boom_class_lookup_cnfe_callbacks
 test rbx,rbx
 jz jfn_cnfe_zero
 cmp DWORD PTR [rbx],0
 jne jfn_cnfe_zero
 cmp QWORD PTR [rbx+16],0
 jne jfn_cnfe_zero
 ; Preserve the original String. The original Java replace(CC) implements
 ; the bootstrap JNI message's dot-to-slash conversion without host fields.
 mov QWORD PTR [rsp+32],rsi
 mov QWORD PTR [rsp+40],46
 mov QWORD PTR [rsp+48],47
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [r13+40]
 cmp DWORD PTR [rbx],0
 jne jfn_cnfe_zero
 test rax,rax
 jz jfn_cnfe_contract
 mov rsi,rax
 mov rcx,QWORD PTR [r13]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz jfn_cnfe_zero
 cmp DWORD PTR [rbx],0
 jne jfn_cnfe_zero
 mov rcx,QWORD PTR [rdi+56]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [r13+8]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz jfn_cnfe_zero
 mov r12,rax
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],rsi
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [r13+16]
 cmp DWORD PTR [rbx],0
 jne jfn_cnfe_zero
 mov rcx,rbx
 mov rdx,r12
 mov r8,QWORD PTR [r13+24]
 mov r9,QWORD PTR [r13+32]
 call boom_exception_set32
 jmp jfn_cnfe_zero
jfn_cnfe_contract:
 ; A successful String.replace on a validated nonnull String cannot return
 ; null. Fail explicitly if this independently bound source contract breaks.
 mov DWORD PTR [rbx],7
jfn_cnfe_zero:
 xor eax,eax
 add rsp,80
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
jfn_throw_cnfe ENDP
