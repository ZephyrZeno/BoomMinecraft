; ACAS16/1. Normal Context32/unused zero-arg argv/pool/op0 -> Boolean.
; CPUID.0 bounds CPUID.1; EDX[8] is CMPXCHG8B, unrelated to ECX[13].
; Windows x64 source guarantees CX8; missing physical support is Context20.
; Only native metadata is read. Original Java publishes VM_SUPPORTS_LONG_CAS.
PUBLIC boom_provider_atomic_long_cas_service
.code
boom_provider_atomic_long_cas_service PROC FRAME
 push rbx
 .pushreg rbx
 .endprolog
 test rcx,rcx
 jz atomic_cas_zero
 cmp DWORD PTR [rcx],0
 jne atomic_cas_zero
 test r8,r8
 jz atomic_cas_bad
 cmp DWORD PTR [r8],041434153h
 jne atomic_cas_bad
 cmp DWORD PTR [r8+4],1
 jne atomic_cas_bad
 cmp QWORD PTR [r8+8],0
 jne atomic_cas_bad
 test r9d,r9d
 jnz atomic_cas_bad
 mov r10,rcx
 xor eax,eax
 xor ecx,ecx
 cpuid
 cmp eax,1
 jb atomic_cas_unsupported
 mov eax,1
 xor ecx,ecx
 cpuid
 test edx,100h
 jz atomic_cas_unsupported
 mov eax,edx
 shr eax,8
 and eax,1
 jmp atomic_cas_done
atomic_cas_unsupported:
 mov DWORD PTR [r10],20
 jmp atomic_cas_zero
atomic_cas_bad:
 mov DWORD PTR [rcx],7
atomic_cas_zero:
 xor eax,eax
atomic_cas_done:
 pop rbx
 ret
boom_provider_atomic_long_cas_service ENDP
