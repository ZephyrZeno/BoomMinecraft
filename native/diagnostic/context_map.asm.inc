; Development-only sidecar. Context32 is an opaque key, never dereferenced or
; modified. VM exception-plan pointer at Context+24 remains entirely untouched.
; DCMP64/1: capacity8,probeLimit12,Slot16*16,entries24,dropped28,reserved32..63.
; Slot16: context key0Q,row8D,reserved12D. One context owner publishes its row;
; capture the row before that context is reused or its native record is reaped.
; Configuration/entry memory must stay live and immutable except our counters.
DC_VALIDATE MACRO invalid
 test r8,r8
 jz invalid
 cmp DWORD PTR [r8],0504D4344h
 jne invalid
 cmp DWORD PTR [r8+4],1
 jne invalid
 mov eax,DWORD PTR [r8+8]
 test eax,eax
 jz invalid
 cmp eax,65536
 ja invalid
 lea r9d,[eax-1]
 test eax,r9d
 jnz invalid
 mov r10d,DWORD PTR [r8+12]
 test r10d,r10d
 jz invalid
 cmp r10d,eax
 ja invalid
 cmp QWORD PTR [r8+16],0
 je invalid
 test BYTE PTR [r8+16],15
 jnz invalid
 cmp QWORD PTR [r8+32],0
 jne invalid
 cmp QWORD PTR [r8+40],0
 jne invalid
 cmp QWORD PTR [r8+48],0
 jne invalid
 cmp QWORD PTR [r8+56],0
 jne invalid
 mov r11,rcx
 shr r11,4
 imul r11,r11,-1640531535
 and r11d,r9d
 shl r11,4
 mov r9,QWORD PTR [r8+16]
 add r11,r9
ENDM
DC_ADVANCE MACRO again
 add r11,16
 mov eax,DWORD PTR [r8+8]
 shl rax,4
 add rax,r9
 cmp r11,rax
 jb @F
 mov r11,r9
@@:
 dec r10d
 jnz again
ENDM
.code
PUBLIC boom_diagnostic_context_map_record
PUBLIC boom_diagnostic_context_map_row
; record(context RCX, nonzero rowId EDX, sidecar R8)->boolean.
boom_diagnostic_context_map_record PROC
 test rcx,rcx
 jz dc_record_bad
 test edx,edx
 jz dc_record_bad
 DC_VALIDATE dc_record_bad
dc_record_probe:
 mov rax,QWORD PTR [r11]
 cmp rax,rcx
 je dc_record_store
 test rax,rax
 jnz dc_record_next
 lock cmpxchg QWORD PTR [r11],rcx
 test rax,rax
 jz dc_record_claimed
 cmp rax,rcx
 je dc_record_store
 jmp dc_record_next
dc_record_claimed:
 lock inc DWORD PTR [r8+24]
dc_record_store:
 mov DWORD PTR [r11+8],edx
 mov eax,1
 ret
dc_record_next:
 DC_ADVANCE dc_record_probe
 lock inc DWORD PTR [r8+28]
dc_record_bad:
 xor eax,eax
 ret
boom_diagnostic_context_map_record ENDP
; row(context RCX,sidecar RDX)->rowId,0 if absent/not yet published/invalid.
boom_diagnostic_context_map_row PROC
 test rcx,rcx
 jz dc_row_none
 mov r8,rdx
 DC_VALIDATE dc_row_none
dc_row_probe:
 mov rax,QWORD PTR [r11]
 cmp rax,rcx
 je dc_row_found
 test rax,rax
 jz dc_row_none
 DC_ADVANCE dc_row_probe
dc_row_none:
 xor eax,eax
 ret
dc_row_found:
 mov eax,DWORD PTR [r11+8]
 ret
boom_diagnostic_context_map_row ENDP
