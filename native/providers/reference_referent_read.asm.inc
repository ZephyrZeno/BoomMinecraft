; Reference.get0 in the normal nonmoving heap. Collection requires quiescence.
; The inherited FMAP address routine checks the actual receiver and GC prefix.
PUBLIC boom_source_reference_get
.code
boom_source_reference_get PROC FRAME
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
 jz rget_zero
 cmp DWORD PTR [rbx],0
 jne rget_zero
 test r9d,r9d
 jnz rget_invalid
 test rsi,rsi
 jz rget_invalid
 cmp DWORD PTR [rsi],054454752h
 jne rget_invalid
 cmp DWORD PTR [rsi+4],1
 jne rget_invalid
 cmp QWORD PTR [rsi+8],0
 je rget_invalid
 cmp QWORD PTR [rsi+16],0
 je rget_invalid
 test rdx,rdx
 jz rget_invalid
 mov rdi,QWORD PTR [rdx]
 test rdi,rdi
 jz rget_null
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz rget_invalid
 mov rcx,rdi
 mov rdx,rbx
 call QWORD PTR [rsi+16]
 test rax,rax
 jz rget_zero
 ; Aligned x64 pointer read. A simultaneous clear can produce either value.
 mov rdi,QWORD PTR [rax]
 test rdi,rdi
 jz rget_zero
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz rget_invalid
 mov rax,rdi
 jmp rget_done
rget_null:
 mov DWORD PTR [rbx],4
 jmp rget_zero
rget_invalid:
 mov DWORD PTR [rbx],7
rget_zero:
 xor eax,eax
rget_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_source_reference_get ENDP
