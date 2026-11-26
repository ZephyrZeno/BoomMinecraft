; Invoke an intact original dedicated-server Main after real System phase3.
; Context32 RCX, report576 RDX. No Java object or VM-level writes by a host.
; Owner macros: ORIGINAL_GAME_MAIN, GAME_MAIN_CLASS, GAME_ARGC,
; GAME_ARGV_TEXT_ROWS (rows16: UTF16*0, units8, reserved12), GAME_ARGV_ROOT.
; The owner includes the argv root in its normal primordial GC root span.
.code
boom_vm_call_game_main PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,56
 .allocstack 56
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 test rbx,rbx
 jz game_main_no_report
 test rsi,rsi
 jz game_main_no_report
 cmp DWORD PTR [rbx],0
 jne game_main_incomplete
 cmp DWORD PTR [VM_LEVEL_CELL],4
 jne game_main_incomplete
 cmp DWORD PTR [rsi+512],1
 jne game_main_incomplete
 cmp DWORD PTR [rsi+516],1
 jne game_main_incomplete
 cmp DWORD PTR [rsi+520],2
 jne game_main_incomplete
 cmp DWORD PTR [rsi+524],4
 jne game_main_incomplete
 cmp DWORD PTR [rsi+528],0
 jne game_main_incomplete
 cmp DWORD PTR [rsi+540],0
 jne game_main_incomplete
 mov DWORD PTR [rsi+556],GAME_ARGC
 cmp QWORD PTR [GAME_ARGV_ROOT],0
 jne game_main_invalid
 mov rcx,rbx
 lea rdx,boom_java_platform_properties_pool
 mov r8d,GAME_ARGC
 call boom_java_property_array
 cmp DWORD PTR [rbx],0
 jne game_main_incomplete
 test rax,rax
 jz game_main_invalid
 mov r12,rax
 mov QWORD PTR [GAME_ARGV_ROOT],rax
 xor edi,edi
game_main_copy_arguments:
 cmp edi,GAME_ARGC
 jae game_main_initialize
 lea r10,GAME_ARGV_TEXT_ROWS
 mov eax,edi
 shl rax,4
 mov r8,QWORD PTR [r10+rax]
 mov r9d,DWORD PTR [r10+rax+8]
 mov rcx,rbx
 lea rdx,boom_java_platform_properties_pool
 call boom_java_property_copy
 cmp DWORD PTR [rbx],0
 jne game_main_incomplete
 test rax,rax
 jz game_main_invalid
 mov QWORD PTR [r12+rdi*8],rax
 inc edi
 jmp game_main_copy_arguments
game_main_initialize:
 lea rcx,GAME_MAIN_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne game_main_incomplete
 mov DWORD PTR [rsi+544],1
 mov QWORD PTR [rsp+32],r12
 mov rcx,rbx
 lea rdx,[rsp+32]
 mov DWORD PTR [rsi+548],1
 call ORIGINAL_GAME_MAIN
 cmp DWORD PTR [rbx],0
 jne game_main_incomplete
 mov DWORD PTR [rsi+552],1
 mov eax,1
 jmp game_main_capture
game_main_invalid:
 mov DWORD PTR [rbx],7
game_main_incomplete:
 xor eax,eax
game_main_capture:
 mov rcx,QWORD PTR [rbx]
 mov QWORD PTR [rsi+560],rcx
 mov rcx,QWORD PTR [rbx+8]
 mov QWORD PTR [rsi+568],rcx
 jmp game_main_done
game_main_no_report:
 xor eax,eax
game_main_done:
 add rsp,56
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_vm_call_game_main ENDP
