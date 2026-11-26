; Called on the primordial thread immediately after original System.initPhase1.
; The verified emitter supplies the original (ZZ)I entry and VM.initLevel cell.
; Report312/7 extends the worker report. No VM level is assigned by this owner.
.code
boom_vm_call_system_phase2 PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,56
 .allocstack 56
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov DWORD PTR [rsi+272],1
 mov eax,DWORD PTR [VM_LEVEL_CELL]
 mov DWORD PTR [rsi+288],eax
 mov DWORD PTR [rsi+292],eax
 cmp eax,1
 jne phase2_incomplete
 ; initPhase2(printToStderr=true, printStackTrace=false). Each Java argument
 ; occupies one eight-byte managed slot, including booleans on Windows x64.
 mov QWORD PTR [rsp+32],1
 mov QWORD PTR [rsp+40],0
 lea rdx,[rsp+32]
 mov DWORD PTR [rsi+276],1
 call ORIGINAL_SYSTEM_PHASE2
 mov edx,DWORD PTR [VM_LEVEL_CELL]
 mov DWORD PTR [rsi+292],edx
 cmp DWORD PTR [rbx],0
 jne phase2_incomplete
 mov DWORD PTR [rsi+280],1
 mov DWORD PTR [rsi+284],eax
 test eax,eax
 jnz phase2_incomplete
 cmp edx,2
 jne phase2_incomplete
 mov eax,1
 jmp phase2_done
phase2_incomplete:
 xor eax,eax
phase2_done:
 add rsp,56
 pop rsi
 pop rbx
 ret
boom_vm_call_system_phase2 ENDP
