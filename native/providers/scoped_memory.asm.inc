; SCNP32/1 validation/publication using the canonical DLL export address.
PUBLIC boom_provider_scoped_memory_service
.code
boom_provider_scoped_memory_service PROC
 test rcx,rcx
 jz provider_scoped_zero
 cmp DWORD PTR [rcx],0
 jne provider_scoped_zero
 test r9d,r9d
 jnz provider_scoped_bad
 test r8,r8
 jz provider_scoped_bad
 cmp DWORD PTR [r8],0504E4353h
 jne provider_scoped_bad
 cmp DWORD PTR [r8+4],1
 jne provider_scoped_bad
 cmp DWORD PTR [r8+12],1
 jne provider_scoped_bad
 cmp QWORD PTR [r8+24],0
 jne provider_scoped_bad
 mov eax,DWORD PTR [r8+8]
 test eax,eax
 jz provider_scoped_target
 cmp eax,2
 jne provider_scoped_bad
 cmp QWORD PTR [r8+16],0
 je provider_scoped_bad
provider_scoped_target:
 mov r10,QWORD PTR [__imp_boom_scoped_close_unavailable]
 test r10,r10
 jz provider_scoped_bad
 xor eax,eax
 lock cmpxchg QWORD PTR [r8+16],r10
 test rax,rax
 jz provider_scoped_ready
 cmp rax,r10
 jne provider_scoped_bad
provider_scoped_ready:
 mov rdx,r8
 jmp boom_scoped_native_register
provider_scoped_bad:
 mov DWORD PTR [rcx],7
provider_scoped_zero:
 xor eax,eax
 ret
boom_provider_scoped_memory_service ENDP
