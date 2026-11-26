; Standalone normal Reference.get0. Source-equivalent to the tested NIO reader.
; RGET24/1 contains the heap cell and original inherited referent FMAP routine.
; The heap is nonmoving; collection must be quiescent. No weak GC is supplied.
PUBLIC boom_provider_reference_referent_get
.code
boom_provider_reference_referent_get PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rsi,r8
 test rbx,rbx
 jz refget_zero
 cmp DWORD PTR [rbx],0
 jne refget_zero
 test r9d,r9d
 jnz refget_invalid
 test rsi,rsi
 jz refget_invalid
 cmp DWORD PTR [rsi],054454752h
 jne refget_invalid
 cmp DWORD PTR [rsi+4],1
 jne refget_invalid
 cmp QWORD PTR [rsi+8],0
 je refget_invalid
 cmp QWORD PTR [rsi+16],0
 je refget_invalid
 test rdx,rdx
 jz refget_invalid
 mov rdi,QWORD PTR [rdx]
 test rdi,rdi
 jz refget_null
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz refget_invalid
 mov rcx,rdi
 mov rdx,rbx
 call QWORD PTR [rsi+16]
 test rax,rax
 jz refget_zero
 mov rdi,QWORD PTR [rax]
 test rdi,rdi
 jz refget_zero
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz refget_invalid
 mov rax,rdi
 jmp refget_done
refget_null:
 mov DWORD PTR [rbx],4
 jmp refget_zero
refget_invalid:
 mov DWORD PTR [rbx],7
refget_zero:
 xor eax,eax
refget_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_reference_referent_get ENDP
