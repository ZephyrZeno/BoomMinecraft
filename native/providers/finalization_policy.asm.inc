; Finalization policy only. Original Java still constructs/runs its workers.
; FNLP32/1: magic0,ABI4,enabled8,reserved12..31. Frozen default is enabled.
.code
PUBLIC boom_provider_finalization_policy_service
boom_provider_finalization_policy_service PROC
 test rcx,rcx
 jz finalization_policy_zero
 cmp DWORD PTR [rcx],0
 jne finalization_policy_zero
 test r9d,r9d
 jnz finalization_policy_bad
 test r8,r8
 jz finalization_policy_bad
 cmp DWORD PTR [r8],0504C4E46h
 jne finalization_policy_bad
 cmp DWORD PTR [r8+4],1
 jne finalization_policy_bad
 cmp DWORD PTR [r8+12],0
 jne finalization_policy_bad
 cmp QWORD PTR [r8+16],0
 jne finalization_policy_bad
 cmp QWORD PTR [r8+24],0
 jne finalization_policy_bad
 mov eax,DWORD PTR [r8+8]
 cmp eax,1
 ja finalization_policy_bad
 ret
finalization_policy_bad:
 mov DWORD PTR [rcx],7
finalization_policy_zero:
 xor eax,eax
 ret
boom_provider_finalization_policy_service ENDP
