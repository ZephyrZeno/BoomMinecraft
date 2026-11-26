; Owned cold probe. The original DebugGraphics(Graphics)->DebugGraphics()
; constructors create and consume the StackWalker; no Java fields are patched.
; This is development instrumentation, not a production VM entry.
.data?
ALIGN 8
PUBLIC boom_stack_walk_component_report
boom_stack_walk_component_report BYTE 128 DUP(?)
.code
PUBLIC boom_stack_walk_component_entry
boom_stack_walk_component_entry PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 mov DWORD PTR [boom_stack_walk_component_report],1
 mov eax,DWORD PTR [SW_TEST_BUFFERED_CLASS+8]
 mov DWORD PTR [boom_stack_walk_component_report+8],eax
 lea rcx,SW_TEST_GRAPHICS_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne st_component_capture
 mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,SW_TEST_GRAPHICS_LAYOUT
 mov r8,rbx
 call boom_object_new
 cmp DWORD PTR [rbx],0
 jne st_component_capture
 test rax,rax
 jz st_component_invalid
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],0
 mov rcx,rbx
 lea rdx,[rsp+32]
 call SW_TEST_GRAPHICS_CONSTRUCTOR
 cmp DWORD PTR [rbx],0
 jne st_component_capture
 mov DWORD PTR [boom_stack_walk_component_report+4],1
 jmp st_component_capture
st_component_invalid:
 mov DWORD PTR [rbx],7
st_component_capture:
 mov eax,DWORD PTR [SW_TEST_BUFFERED_CLASS+8]
 mov DWORD PTR [boom_stack_walk_component_report+12],eax
 mov rax,QWORD PTR [rbx]
 mov QWORD PTR [boom_stack_walk_component_report+16],rax
 mov rax,QWORD PTR [rbx+8]
 mov QWORD PTR [boom_stack_walk_component_report+24],rax
 mov rax,QWORD PTR [rbx+16]
 mov QWORD PTR [boom_stack_walk_component_report+32],rax
 mov rax,QWORD PTR [rbx+24]
 mov QWORD PTR [boom_stack_walk_component_report+40],rax
 mov rax,QWORD PTR [boom_stack_walk_active_count]
 mov QWORD PTR [boom_stack_walk_component_report+48],rax
 mov rax,QWORD PTR [boom_stack_walk_counters]
 mov QWORD PTR [boom_stack_walk_component_report+56],rax
 mov rax,QWORD PTR [boom_stack_walk_counters+8]
 mov QWORD PTR [boom_stack_walk_component_report+64],rax
 mov rax,QWORD PTR [boom_stack_walk_counters+16]
 mov QWORD PTR [boom_stack_walk_component_report+72],rax
 mov rax,QWORD PTR [boom_stack_walk_counters+24]
 mov QWORD PTR [boom_stack_walk_component_report+80],rax
 mov rax,QWORD PTR [boom_stack_walk_counters+48]
 mov QWORD PTR [boom_stack_walk_component_report+88],rax
 mov QWORD PTR [rsp+32],0
 mov DWORD PTR [rsp+40],080h
 mov QWORD PTR [rsp+48],0
 lea rcx,st_component_file
 mov edx,040000000h
 xor r8d,r8d
 xor r9d,r9d
 mov DWORD PTR [rsp+32],2
 call CreateFileW
 cmp rax,-1
 je st_component_io_fail
 mov QWORD PTR [rsp+56],rax
 mov rcx,rax
 lea rdx,boom_stack_walk_component_report
 mov r8d,128
 lea r9,st_component_written
 mov QWORD PTR [rsp+32],0
 call WriteFile
 mov DWORD PTR [rsp+48],eax
 mov rcx,QWORD PTR [rsp+56]
 call CloseHandle
 cmp DWORD PTR [rsp+48],0
 je st_component_io_fail
 cmp DWORD PTR [st_component_written],128
 jne st_component_io_fail
 mov eax,DWORD PTR [boom_stack_walk_component_report+4]
 jmp st_component_done
st_component_io_fail:
 cmp DWORD PTR [rbx],0
 jne st_component_done_zero
 mov DWORD PTR [rbx],7
st_component_done_zero:
 xor eax,eax
st_component_done:
 add rsp,64
 pop rbx
 ret
boom_stack_walk_component_entry ENDP
.const
st_component_file WORD 115,116,97,99,107,45,119,97,108,107,45,99,111,109,112,111,110,101,110,116,46,98,105,110,0
.data?
st_component_written DWORD ?
