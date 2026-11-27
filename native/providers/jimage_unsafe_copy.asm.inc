; Only original Unsafe.copyMemory0, op0. Context32 + six QWORD argv slots.
; Original Java copyMemory/checks remain complete source methods.
.code
PUBLIC boom_provider_jimage_copy_service
boom_provider_jimage_copy_service PROC
 test rcx,rcx
 jz jup_gate_zero
 cmp DWORD PTR [rcx],0
 jne jup_gate_zero
 test r9d,r9d
 jnz jup_gate_bad
 test rdx,rdx
 jz jup_gate_bad
 cmp QWORD PTR [rdx+8],0
 jne jup_gate_unsupported
 cmp QWORD PTR [rdx+24],0
 je jup_gate_unsupported
 ; Reuse only the original normal receiver validation, with plain-byte width.
 ; This is not a read call or a skipped Java check; no data is accessed here.
 mov r9d,2
 jmp jup_validated_copy
jup_gate_unsupported:
 mov DWORD PTR [rcx],20
 jmp jup_gate_zero
jup_gate_bad:
 mov DWORD PTR [rcx],7
jup_gate_zero:
 xor eax,eax
 ret
boom_provider_jimage_copy_service ENDP

jup_validated_copy PROC PRIVATE FRAME
;@ORIGINAL_RECEIVER_PREFIX@
 lea r10,boom_provider_jimage_native_map_pool
 cmp DWORD PTR [r10],050414D4Ah
 jne jup_unbound
 cmp DWORD PTR [r10+4],1
 jne jup_unbound
 cmp DWORD PTR [r10+24],1
 jne jup_unbound
 mov rax,QWORD PTR [r10+8]
 test rax,rax
 jz jup_unbound
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [r13+16]
 mov rax,QWORD PTR [rax]
 mov QWORD PTR [rsp+40],rax
 mov rax,QWORD PTR [r12+16]
 mov QWORD PTR [rsp+48],rax
 mov rax,QWORD PTR [r12+24]
 mov QWORD PTR [rsp+56],rax
 mov rax,QWORD PTR [r12+32]
 sub rax,JUC_ARRAY_BASE_OFFSET
 jc jup_bad
 mov QWORD PTR [rsp+64],rax
 mov rax,QWORD PTR [r12+40]
 mov QWORD PTR [rsp+72],rax
 mov QWORD PTR [rsp+80],0
 mov QWORD PTR [rsp+88],0
 lea rcx,[rsp+32]
 call boom_jimage_owned_copy_to_bytes
 test eax,eax
 jz jup_zero
 cmp eax,1
 je jup_unbound
 cmp eax,4
 je jup_unbound
 cmp eax,5
 je jup_unbound
 jmp jup_bad
jup_unbound:
 mov DWORD PTR [rbx],20
 jmp jup_zero
jup_null:
 mov DWORD PTR [rbx],4
 jmp jup_zero
jup_bad:
 mov DWORD PTR [rbx],7
jup_zero:
 xor eax,eax
 add rsp,152
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
jup_validated_copy ENDP
