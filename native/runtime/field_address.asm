; Checked source field address from actual receiver type, including inherited
; fields moved by reference-prefix compaction. No allocation or Java execution.
; FMAP32: magic0 ABI4 count8 storage12 reference16 reserved20 Row8*24.
; Rows sorted by source receiver ID: DWORD id,offset. Immutable metadata.
; address(oop RCX,Context RDX,fieldMap R8,runtimeMap R9)->address / NULL.
option casemap:none
EXTERN boom_runtime_row:PROC
PUBLIC boom_field_address
.code
boom_field_address PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rdx
 mov rsi,r8
 mov rdi,r9
 mov r12,rcx
 test rbx,rbx
 jz field_address_zero
 cmp DWORD PTR [rbx],0
 jne field_address_zero
 test rsi,rsi
 jz field_address_bad
 cmp DWORD PTR [rsi],0464D4150h
 jne field_address_bad
 cmp DWORD PTR [rsi+4],1
 jne field_address_bad
 mov eax,DWORD PTR [rsi+8]
 dec eax
 cmp eax,0FFFFFh
 ja field_address_bad
 mov eax,DWORD PTR [rsi+12]
 test eax,eax
 jz field_address_bad
 cmp eax,8
 ja field_address_bad
 lea edx,[rax-1]
 test eax,edx
 jnz field_address_bad
 cmp DWORD PTR [rsi+16],1
 ja field_address_bad
 cmp QWORD PTR [rsi+24],0
 je field_address_bad
 mov rdx,rdi
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz field_address_zero
 cmp DWORD PTR [rax+20],0
 jne field_address_bad
 mov r11,rax
 mov r10d,DWORD PTR [rax+16]
 xor r8d,r8d
 mov r9d,DWORD PTR [rsi+8]
 mov rdx,QWORD PTR [rsi+24]
field_address_search:
 cmp r8d,r9d
 jae field_address_bad
 mov eax,r9d
 sub eax,r8d
 shr eax,1
 add eax,r8d
 cmp DWORD PTR [rdx+rax*8],r10d
 je field_address_match
 jb field_address_right
 mov r9d,eax
 jmp field_address_search
field_address_right:
 lea r8d,[rax+1]
 jmp field_address_search
field_address_match:
 mov eax,DWORD PTR [rdx+rax*8+4]
 mov ecx,DWORD PTR [rsi+12]
 lea r9,[rax+rcx]
 cmp r9,QWORD PTR [r11+24]
 ja field_address_bad
 mov r8d,ecx
 dec r8d
 test eax,r8d
 jnz field_address_bad
 mov r8d,DWORD PTR [r11+32]
 shl r8,3
 cmp DWORD PTR [rsi+16],0
 je field_address_scalar
 cmp ecx,8
 jne field_address_bad
 cmp r9,r8
 ja field_address_bad
 jmp field_address_found
field_address_scalar:
 cmp rax,r8
 jb field_address_bad
field_address_found:
 add rax,r12
 jmp field_address_done
field_address_bad:
 mov DWORD PTR [rbx],7
field_address_zero:
 xor eax,eax
field_address_done:
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_field_address ENDP
END
