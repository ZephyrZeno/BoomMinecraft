; Development ABI fixture: actually grow/touch 64 KiB, preserving argument regs.
option casemap:none
EXTERN boom_stack_probe:PROC
PUBLIC boom_test_large_stack
.code
boom_test_large_stack PROC FRAME
 mov eax,65576
 call boom_stack_probe
 sub rsp,65576
 .allocstack 65576
 .endprolog
 mov r10,rsp
 lea r11,[rsp+65560]
stack_fixture_touch:
 mov QWORD PTR [r10],rax
 add r10,4096
 cmp r10,r11
 jb stack_fixture_touch
 mov QWORD PTR [r11],rax
 add rax,rcx
 add rax,rdx
 add rax,r8
 add rax,r9
 add rsp,65576
 ret
boom_test_large_stack ENDP
END
