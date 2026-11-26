; A source stub records its own Context after the ABI1 stop validates its row.
; Pool96 still publishes the first process-wide stop. A prior pending error is
; never associated with a second row. Neither path borrows the VM plan field.
.data?
ALIGN 16
diag_context_slots BYTE 16384 DUP(?)
.data
ALIGN 8
PUBLIC boom_diagnostic_context_map
boom_diagnostic_context_map DWORD 0504D4344h,1,1024,64
 QWORD OFFSET diag_context_slots
 DWORD 0,0
 QWORD 0,0,0,0
.code
boom_diagnostic_stop_context PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 test rbx,rbx
 jz diag_context_done
 cmp DWORD PTR [rbx],0
 jne diag_context_done
 call boom_diagnostic_stop
 cmp DWORD PTR [rbx],0B001h
 jne diag_context_done
 mov rcx,rbx
 mov edx,DWORD PTR [rsi]
 lea r8,boom_diagnostic_context_map
 call boom_diagnostic_context_map_record
diag_context_done:
 xor eax,eax
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_diagnostic_stop_context ENDP
