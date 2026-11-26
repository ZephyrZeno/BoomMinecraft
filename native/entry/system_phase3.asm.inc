; Called on the original primordial thread only after complete System.initPhase2.
; ORIGINAL_SYSTEM_PHASE3 is the intact original ()V method. VM_LEVEL_CELL is read
; only: Java publishes levels 3/4 and its loader/context-loader fields itself.
; Report544/13 preserves ABI11's first448 and owner512/12's reserved448..511.
; Phase3 fields: called512,returned516,VM_before520,VM_after524,Context16@528.
.code
boom_vm_call_system_phase3 PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov eax,DWORD PTR [VM_LEVEL_CELL]
 mov DWORD PTR [rsi+520],eax
 mov DWORD PTR [rsi+524],eax
 cmp DWORD PTR [rbx],0
 jne phase3_incomplete
 cmp eax,2
 jne phase3_incomplete
 ; The original private static method has no managed argument slots.
 xor edx,edx
 mov DWORD PTR [rsi+512],1
 call ORIGINAL_SYSTEM_PHASE3
 mov edx,DWORD PTR [VM_LEVEL_CELL]
 mov DWORD PTR [rsi+524],edx
 cmp DWORD PTR [rbx],0
 jne phase3_incomplete
 mov DWORD PTR [rsi+516],1
 cmp edx,4
 jne phase3_incomplete
 mov eax,1
 jmp phase3_done
phase3_incomplete:
 xor eax,eax
phase3_done:
 mov rcx,QWORD PTR [rbx]
 mov QWORD PTR [rsi+528],rcx
 mov rcx,QWORD PTR [rbx+8]
 mov QWORD PTR [rsi+536],rcx
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_vm_call_system_phase3 ENDP
