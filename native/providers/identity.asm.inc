; Identity for live typed references in the nonmoving Heap ABI1.
; Pool32/1: magic0 ABI4 nonmoving8D=1 reserved12 heapCell16 typeMap24.
; op0 Object.hashCode: null receiver -> NPE; op1 System identity: null -> 0.
; Hashing delegates to the existing address mixer only after arena/type checks.
PUBLIC boom_provider_identity_service
.code
boom_provider_identity_service PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov rdi,r8
 test rbx,rbx
 jz provider_identity_zero
 cmp DWORD PTR [rbx],0
 jne provider_identity_zero
 test rdx,rdx
 jz provider_identity_bad
 test rdi,rdi
 jz provider_identity_bad
 cmp DWORD PTR [rdi],04A494448h
 jne provider_identity_bad
 cmp DWORD PTR [rdi+4],1
 jne provider_identity_bad
 cmp QWORD PTR [rdi+8],1
 jne provider_identity_bad
 cmp QWORD PTR [rdi+16],0
 je provider_identity_bad
 cmp QWORD PTR [rdi+24],0
 je provider_identity_bad
 cmp r9d,1
 ja provider_identity_bad
 mov rsi,QWORD PTR [rdx]
 test rsi,rsi
 jnz provider_identity_nonnull
 test r9d,r9d
 jnz provider_identity_zero
 mov DWORD PTR [rbx],4
 jmp provider_identity_zero
provider_identity_nonnull:
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 test rcx,rcx
 jz provider_identity_bad
 cmp DWORD PTR [rcx],048454150h
 jne provider_identity_bad
 cmp DWORD PTR [rcx+4],1
 jne provider_identity_bad
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz provider_identity_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [rdi+24]
 mov r8,rbx
 call boom_runtime_type
 test rax,rax
 jz provider_identity_zero
 mov rcx,rbx
 mov rdx,rsi
 call boom_identity_hash
 jmp provider_identity_done
provider_identity_bad:
 mov DWORD PTR [rbx],7
provider_identity_zero:
 xor eax,eax
provider_identity_done:
 add rsp,48
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_identity_service ENDP
