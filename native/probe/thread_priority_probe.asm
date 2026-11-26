; Kernel test callbacks only, not Java Thread bodies.
option casemap:none
EXTERN SetEvent:PROC
EXTERN WaitForSingleObject:PROC
PUBLIC boom_priority_test_main
PUBLIC boom_priority_test_exit
.code
; User16: entered HANDLE0, release HANDLE8.
boom_priority_test_main PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rdx
 mov rcx,QWORD PTR [rbx]
 call SetEvent
 test eax,eax
 jz priority_test_bad
 mov rcx,QWORD PTR [rbx+8]
 mov edx,60000
 call WaitForSingleObject
 test eax,eax
 jz priority_test_done
priority_test_bad:
 mov eax,87
priority_test_done:
 add rsp,32
 pop rbx
 ret
boom_priority_test_main ENDP
boom_priority_test_exit PROC
 xor eax,eax
 ret
boom_priority_test_exit ENDP
END
