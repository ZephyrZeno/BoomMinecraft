; Source-bound runtime map ABI2. All indexing and validation execute in MASM.
; Map48: RTYP0 ABI4 rows8 typeCount12 Row40*16 mirrorPool24 slots*32 mask40 state44.
; Slots are writable Row40 pointers, zeroed and filled once without guest allocation.
; States 0 new / 1 building / 2 ready / 3 rejected; metadata lives until quiescence.
option casemap:none
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
PUBLIC boom_runtime_index_prepare
PUBLIC boom_runtime_lookup_indexed
.code
; prepare(map RCX,Context RDX)->0 success / 1 error. Pending errors survive.
boom_runtime_index_prepare PROC FRAME
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
 sub rsp,56
 .allocstack 56
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 test rsi,rsi
 jz index_prepare_error
 cmp DWORD PTR [rsi],0
 je index_prepare_context_ready
 cmp DWORD PTR [rsi],16
 jne index_prepare_error
index_prepare_context_ready:
 test rbx,rbx
 jz index_prepare_bad
 cmp DWORD PTR [rbx],052545950h
 jne index_prepare_bad
 cmp DWORD PTR [rbx+4],2
 jne index_prepare_bad
 mov eax,DWORD PTR [rbx+8]
 dec eax
 cmp eax,0FFFFFh
 ja index_prepare_bad
 mov eax,DWORD PTR [rbx+12]
 dec eax
 cmp eax,0FFFFFh
 ja index_prepare_bad
 cmp QWORD PTR [rbx+16],0
 je index_prepare_bad
 mov r12,QWORD PTR [rbx+32]
 test r12,r12
 jz index_prepare_bad
 mov r13d,DWORD PTR [rbx+40]
 cmp r13d,15
 jb index_prepare_bad
 cmp r13d,01FFFFFh
 ja index_prepare_bad
 lea eax,[r13+1]
 test eax,r13d
 jnz index_prepare_bad
 shr eax,1
 cmp DWORD PTR [rbx+8],eax
 ja index_prepare_bad
index_prepare_state:
 mov eax,DWORD PTR [rbx+44]
 cmp eax,2
 je index_prepare_success
 cmp eax,1
 je index_prepare_wait
 test eax,eax
 jnz index_prepare_bad
 mov edx,1
 lock cmpxchg DWORD PTR [rbx+44],edx
 jne index_prepare_state
 mov rdi,r12
 lea ecx,[r13+1]
 xor eax,eax
 rep stosq
 mov rdi,QWORD PTR [rbx+16]
 mov r14d,DWORD PTR [rbx+8]
index_prepare_row:
 mov rdx,QWORD PTR [rdi]
 test rdx,rdx
 jz index_prepare_reject
 mov eax,DWORD PTR [rdi+16]
 cmp eax,DWORD PTR [rbx+12]
 jae index_prepare_reject
 mov r10,QWORD PTR [rdi+8]
 test r10,r10
 jz index_prepare_reject
 cmp DWORD PTR [r10],054595045h
 jne index_prepare_reject
 cmp DWORD PTR [r10+4],1
 jne index_prepare_reject
 mov rax,rdx
 shr rax,4
 mov r10,rax
 shr r10,32
 xor eax,r10d
 imul eax,eax,045D9F3Bh
 mov ecx,eax
 shr ecx,16
 xor eax,ecx
 and eax,r13d
 lea r9d,[r13+1]
index_prepare_probe:
 mov r10,QWORD PTR [r12+rax*8]
 test r10,r10
 jz index_prepare_insert
 cmp QWORD PTR [r10],rdx
 je index_prepare_reject
 inc eax
 and eax,r13d
 dec r9d
 jnz index_prepare_probe
 jmp index_prepare_reject
index_prepare_insert:
 mov QWORD PTR [r12+rax*8],rdi
 add rdi,40
 dec r14d
 jnz index_prepare_row
 mov DWORD PTR [rbx+44],2
 lea rcx,[rbx+44]
 call WakeByAddressAll
index_prepare_success:
 xor eax,eax
 jmp index_prepare_done
index_prepare_wait:
 mov DWORD PTR [rsp+32],1
 lea rcx,[rbx+44]
 lea rdx,[rsp+32]
 mov r8d,4
 mov r9d,-1
 call WaitOnAddress
 jmp index_prepare_state
index_prepare_reject:
 mov DWORD PTR [rbx+44],3
 lea rcx,[rbx+44]
 call WakeByAddressAll
index_prepare_bad:
 mov DWORD PTR [rsi],7
index_prepare_error:
 mov eax,1
index_prepare_done:
 add rsp,56
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_runtime_index_prepare ENDP

; lookup(object RCX,map RDX,Context R8)->validated Row40 / NULL.
boom_runtime_lookup_indexed PROC FRAME
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
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 test rdi,rdi
 jz index_lookup_zero
 cmp DWORD PTR [rdi],0
 je index_lookup_context_ready
 ; Exception matching queries a pending Throwable without consuming its root.
 cmp DWORD PTR [rdi],16
 jne index_lookup_zero
index_lookup_context_ready:
 test rbx,rbx
 jz index_lookup_null
 mov rcx,rsi
 mov rdx,rdi
 call boom_runtime_index_prepare
 test eax,eax
 jnz index_lookup_zero
 mov eax,DWORD PTR [rbx-24]
 and eax,0FFFFFFFDh
 cmp eax,0B00B0001h
 jne index_lookup_bad
 mov r12,QWORD PTR [rbx-8]
 mov r13d,DWORD PTR [rsi+40]
 mov rax,r12
 shr rax,4
 mov r10,rax
 shr r10,32
 xor eax,r10d
 imul eax,eax,045D9F3Bh
 mov ecx,eax
 shr ecx,16
 xor eax,ecx
 and eax,r13d
 mov r11,QWORD PTR [rsi+32]
 lea r9d,[r13+1]
index_lookup_probe:
 mov r10,QWORD PTR [r11+rax*8]
 test r10,r10
 jz index_lookup_bad
 cmp QWORD PTR [r10],r12
 je index_lookup_match
 inc eax
 and eax,r13d
 dec r9d
 jnz index_lookup_probe
 jmp index_lookup_bad
index_lookup_match:
 mov eax,DWORD PTR [r10+16]
 cmp eax,DWORD PTR [rsi+12]
 jae index_lookup_bad
 mov r11,QWORD PTR [r10+8]
 mov eax,DWORD PTR [r10+20]
 test eax,eax
 jnz index_lookup_array
 cmp DWORD PTR [r11+8],1
 jne index_lookup_bad
 mov rax,QWORD PTR [r10+24]
 cmp QWORD PTR [rbx-16],rax
 jne index_lookup_bad
 mov eax,DWORD PTR [r10+32]
 cmp DWORD PTR [rbx-20],eax
 jne index_lookup_bad
 jmp index_lookup_found
index_lookup_array:
 cmp eax,2
 ja index_lookup_bad
 cmp DWORD PTR [r11+8],3
 jne index_lookup_bad
 cmp eax,2
 je index_lookup_references
 cmp DWORD PTR [rbx-20],0
 jne index_lookup_bad
 mov ecx,DWORD PTR [r10+36]
 cmp ecx,3
 ja index_lookup_bad
 mov rax,QWORD PTR [rbx-16]
 mov edx,1
 shl edx,cl
 dec edx
 test rax,rdx
 jnz index_lookup_bad
 shr rax,cl
 jmp index_lookup_length
index_lookup_references:
 mov eax,DWORD PTR [rbx-20]
 mov rdx,rax
 shl rdx,3
 cmp QWORD PTR [rbx-16],rdx
 jne index_lookup_bad
index_lookup_length:
 cmp rax,07FFFFFFFh
 ja index_lookup_bad
index_lookup_found:
 mov rax,r10
 jmp index_lookup_done
index_lookup_null:
 mov DWORD PTR [rdi],4
 jmp index_lookup_zero
index_lookup_bad:
 mov DWORD PTR [rdi],7
index_lookup_zero:
 xor eax,eax
index_lookup_done:
 add rsp,48
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_runtime_lookup_indexed ENDP
END
