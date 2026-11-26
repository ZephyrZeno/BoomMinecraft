; Development-only fail-stop. This is not a guest native implementation.
; (Context32 RCX, Row48 RDX, Pool96 R8) -> 0 with diagnostic kind B001.
; No catchable Java Throwable, no heap allocation, no host callback.
PUBLIC boom_diagnostic_stop
.code
boom_diagnostic_stop PROC
 test rcx,rcx
 jz diag_stop_return
 cmp DWORD PTR [rcx],0
 jne diag_stop_return
 test r8,r8
 jz diag_stop_bad
 cmp DWORD PTR [r8],044535450h
 jne diag_stop_bad
 cmp DWORD PTR [r8+4],1
 jne diag_stop_bad
 cmp DWORD PTR [r8+8],2
 ja diag_stop_bad
 cmp DWORD PTR [r8+24],48
 jne diag_stop_bad
 cmp DWORD PTR [r8+28],32
 jne diag_stop_bad
 test rdx,rdx
 jz diag_stop_bad
 mov r10d,DWORD PTR [rdx]
 dec r10d
 cmp r10d,DWORD PTR [r8+12]
 jae diag_stop_bad
 imul r10,48
 add r10,QWORD PTR [r8+16]
 cmp r10,rdx
 jne diag_stop_bad
 mov r9,QWORD PTR [rcx+16]
 mov DWORD PTR [rcx],0B001h
 mov QWORD PTR [rcx+16],0
 xor eax,eax
 mov r11d,1
 lock cmpxchg DWORD PTR [r8+8],r11d
 test eax,eax
 jnz diag_stop_return
 mov eax,DWORD PTR [rdx]
 mov DWORD PTR [r8+32],eax
 mov DWORD PTR [r8+36],0
 mov DWORD PTR [r8+40],0
 mov eax,DWORD PTR [rcx+4]
 mov DWORD PTR [r8+44],eax
 mov eax,DWORD PTR [rcx+8]
 mov DWORD PTR [r8+48],eax
 mov eax,DWORD PTR [rcx+12]
 mov DWORD PTR [r8+52],eax
 mov DWORD PTR [r8+56],0B001h
 mov DWORD PTR [r8+60],0
 mov QWORD PTR [r8+64],r9
 mov QWORD PTR [r8+72],rdx
 mov QWORD PTR [r8+80],rcx
 mov QWORD PTR [r8+88],0
 mov DWORD PTR [r8+8],2
 jmp diag_stop_return
diag_stop_bad:
 mov DWORD PTR [rcx],7
diag_stop_return:
 xor eax,eax
 ret
boom_diagnostic_stop ENDP
