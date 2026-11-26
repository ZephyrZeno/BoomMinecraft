; Raw managed-slot reinterpretation only. No FP instructions, conversion or allocation.
; Context32 RCX, argv64 RDX, BCST16 R8, op R9D. Return raw bits in RAX.
; Pool16: magic0 ABI4 count8 reserved12. Ops0/1 binary32, ops2/3 binary64.
option casemap:none
PUBLIC boom_java_bitcast
.code
boom_java_bitcast PROC
 test rcx,rcx
 jz bitcast_zero
 cmp DWORD PTR [rcx],0
 jne bitcast_zero
 test r8,r8
 jz bitcast_bad
 cmp DWORD PTR [r8],054534342h
 jne bitcast_bad
 cmp DWORD PTR [r8+4],1
 jne bitcast_bad
 cmp DWORD PTR [r8+8],4
 jne bitcast_bad
 cmp DWORD PTR [r8+12],0
 jne bitcast_bad
 cmp r9d,3
 ja bitcast_bad
 test rdx,rdx
 jz bitcast_bad
 cmp r9d,1
 ja bitcast_wide
 mov eax,DWORD PTR [rdx]
 ret
bitcast_wide:
 mov rax,QWORD PTR [rdx]
 ret
bitcast_bad:
 mov DWORD PTR [rcx],7
bitcast_zero:
 xor eax,eax
 ret
boom_java_bitcast ENDP
END
