; Two test receiver layouts intentionally place the same Java boolean at different offsets.
option casemap:none
PUBLIC boom_test_interrupt_field
.code
boom_test_interrupt_field PROC
 cmp QWORD PTR [rcx-8],041h
 je map_first
 cmp QWORD PTR [rcx-8],042h
 je map_second
 mov DWORD PTR [rdx],7
 xor eax,eax
 ret
map_first:
 lea rax,[rcx+8]
 ret
map_second:
 lea rax,[rcx+24]
 ret
boom_test_interrupt_field ENDP
END
