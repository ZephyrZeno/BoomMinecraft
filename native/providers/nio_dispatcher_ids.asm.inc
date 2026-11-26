; NIO field registration. Immutable 48-byte entries contain the original
; class, layout and inherited field map plus owner/index/offset/width/ref.
; The table is observable only after every declaring initialization succeeds.
PUBLIC boom_nio_dispatcher_init_ids
.code
boom_nio_dispatcher_init_ids PROC FRAME
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
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rsi,r8
 test rbx,rbx
 jz ndi_done
 cmp DWORD PTR [rbx],0
 jne ndi_done
 test r9d,r9d
 jnz ndi_bad
 test rsi,rsi
 jz ndi_bad
 cmp DWORD PTR [rsi],044494F4Eh
 jne ndi_bad
 cmp DWORD PTR [rsi+4],1
 jne ndi_bad
 cmp DWORD PTR [rsi+8],20
 jne ndi_bad
 cmp DWORD PTR [rsi+12],48
 jne ndi_bad
 mov rdi,QWORD PTR [rsi+16]
 test rdi,rdi
 jz ndi_bad
 cmp QWORD PTR [rsi+24],rdi
 je ndi_done
 mov r12d,DWORD PTR [rsi+8]
 xor r13d,r13d
ndi_row:
 mov rcx,QWORD PTR [rdi]
 test rcx,rcx
 jz ndi_bad
 cmp DWORD PTR [rcx],0434C4153h
 jne ndi_bad
 cmp DWORD PTR [rcx+4],2
 jne ndi_bad
 mov eax,DWORD PTR [rdi+24]
 cmp DWORD PTR [rcx+24],eax
 jne ndi_bad
 mov rdx,QWORD PTR [rdi+8]
 test rdx,rdx
 jz ndi_bad
 cmp DWORD PTR [rdx],04F424A43h
 jne ndi_bad
 cmp DWORD PTR [rdx+4],2
 jne ndi_bad
 mov r8,QWORD PTR [rdi+16]
 test r8,r8
 jz ndi_bad
 cmp DWORD PTR [r8],0464D4150h
 jne ndi_bad
 cmp DWORD PTR [r8+4],1
 jne ndi_bad
 mov eax,DWORD PTR [rdi+36]
 cmp DWORD PTR [r8+12],eax
 jne ndi_bad
 cmp eax,4
 je ndi_width
 cmp eax,8
 jne ndi_bad
ndi_width:
 mov r9d,DWORD PTR [rdi+32]
 lea r10d,[rax-1]
 test r9d,r10d
 jnz ndi_bad
 add r9,rax
 cmp r9,QWORD PTR [rdx+8]
 ja ndi_bad
 mov eax,DWORD PTR [rdi+40]
 cmp eax,DWORD PTR [r8+16]
 jne ndi_bad
 cmp eax,1
 ja ndi_bad
 cmp rcx,r13
 je ndi_next
 mov r13,rcx
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne ndi_done
ndi_next:
 add rdi,48
 dec r12d
 jnz ndi_row
 mov rdx,QWORD PTR [rsi+16]
 xor eax,eax
 lock cmpxchg QWORD PTR [rsi+24],rdx
 je ndi_done
 cmp rax,rdx
 je ndi_done
ndi_bad:
 mov DWORD PTR [rbx],7
ndi_done:
 xor eax,eax
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_nio_dispatcher_init_ids ENDP
