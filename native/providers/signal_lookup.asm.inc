; Windows Signal.findSignal0 over normal source-layout compact Strings.
; SIGP32/1: heapCell8, normal StringPool80*16, reserved24.
; Exact, case-sensitive seven-name lookup. No handler/raise/dispatch stubs.
PUBLIC boom_provider_signal_lookup_service
.code
boom_provider_signal_lookup_service PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push rbp
 .pushreg rbp
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov r13,r8
 test rbx,rbx
 jz provider_signal_zero
 cmp DWORD PTR [rbx],0
 jne provider_signal_zero
 test r9d,r9d
 jnz provider_signal_bad
 test r13,r13
 jz provider_signal_bad
 cmp DWORD PTR [r13],053494750h
 jne provider_signal_bad
 cmp DWORD PTR [r13+4],1
 jne provider_signal_bad
 cmp QWORD PTR [r13+24],0
 jne provider_signal_bad
 mov rax,QWORD PTR [r13+8]
 test rax,rax
 jz provider_signal_bad
 mov rsi,QWORD PTR [rax]
 test rsi,rsi
 jz provider_signal_unbound
 mov rdi,QWORD PTR [r13+16]
 test rdi,rdi
 jz provider_signal_bad
 cmp DWORD PTR [rdi],04A534C50h
 jne provider_signal_bad
 cmp DWORD PTR [rdi+4],1
 jne provider_signal_bad
 cmp QWORD PTR [rdi+40],0
 je provider_signal_bad
 test r12,r12
 jz provider_signal_bad
 mov r14,QWORD PTR [r12]
 test r14,r14
 jz provider_signal_null
 mov rcx,rsi
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz provider_signal_bad
 mov rcx,r14
 mov rdx,QWORD PTR [rdi+40]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz provider_signal_zero
 mov eax,DWORD PTR [rdi+52]
 cmp rax,QWORD PTR [r14-16]
 jae provider_signal_bad
 movzx ebp,BYTE PTR [r14+rax]
 cmp ebp,1
 ja provider_signal_bad
 mov eax,DWORD PTR [rdi+48]
 test al,7
 jnz provider_signal_bad
 lea rdx,[rax+8]
 cmp rdx,QWORD PTR [r14-16]
 ja provider_signal_bad
 mov r14,QWORD PTR [r14+rax]
 mov rcx,rsi
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz provider_signal_bad
 cmp QWORD PTR [r14-8],264
 jne provider_signal_bad
 cmp DWORD PTR [r14-20],0
 jne provider_signal_bad
 mov r15,QWORD PTR [r14-16]
 cmp r15,07FFFFFFFh
 ja provider_signal_bad
 test ebp,ebp
 jz provider_signal_length
 test r15b,1
 jnz provider_signal_bad
 shr r15,1
provider_signal_length:
 cmp r15,3
 jb provider_signal_unknown
 cmp r15,5
 ja provider_signal_unknown
 lea rdi,provider_signal_lookup_rows
 mov r12d,7
provider_signal_row:
 cmp r15d,DWORD PTR [rdi]
 jne provider_signal_next
 xor r10d,r10d
provider_signal_compare:
 cmp r10,r15
 jae provider_signal_found
 test ebp,ebp
 jnz provider_signal_wide
 movzx eax,BYTE PTR [r14+r10]
 jmp provider_signal_character
provider_signal_wide:
 movzx eax,WORD PTR [r14+r10*2]
provider_signal_character:
 movzx edx,BYTE PTR [rdi+r10+8]
 cmp eax,edx
 jne provider_signal_next
 inc r10d
 jmp provider_signal_compare
provider_signal_next:
 add rdi,16
 dec r12d
 jnz provider_signal_row
provider_signal_unknown:
 mov eax,-1
 jmp provider_signal_done
provider_signal_found:
 mov eax,DWORD PTR [rdi+4]
 jmp provider_signal_done
provider_signal_null:
 mov DWORD PTR [rbx],4
 jmp provider_signal_zero
provider_signal_unbound:
 mov DWORD PTR [rbx],20
 jmp provider_signal_zero
provider_signal_bad:
 mov DWORD PTR [rbx],7
provider_signal_zero:
 xor eax,eax
provider_signal_done:
 add rsp,40
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_signal_lookup_service ENDP
