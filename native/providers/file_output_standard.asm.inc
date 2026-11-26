; Original FOS write/writeBytes, bounded to the actual source FD.out/err.
; Context32/argv, ordinary source frames. No HANDLE adoption/open/close.
; Each partial iteration re-reads FOS.fd, source handle and real GetStdHandle.
.const
fos_closed_message WORD 83,116,114,101,97,109,32,67,108,111,115,101,100
fos_write_message WORD 87,114,105,116,101,32,101,114,114,111,114
.data
ALIGN 8
PUBLIC boom_file_output_standard_counters
; calls0,WriteFile8,bytes16,partials24,live buffers32,alloc40,free48,
; source handle lookups56,zero-progress64,unsupported72,closed80,typed errors88.
boom_file_output_standard_counters QWORD 12 DUP(0)
.code

fos_registration PROC PRIVATE
 lea rax,boom_provider_file_bootstrap_pool
 cmp DWORD PTR [rax],04F49464Eh
 jne fos_registration_bad
 cmp DWORD PTR [rax+4],1
 jne fos_registration_bad
 mov rdx,QWORD PTR [rax+16]
 test rdx,rdx
 jz fos_registration_bad
 cmp DWORD PTR [rdx],05346504Ch
 jne fos_registration_bad
 cmp DWORD PTR [rdx+4],1
 jne fos_registration_bad
 mov rcx,QWORD PTR [rdx+8]
 cmp rcx,QWORD PTR [rdx+16]
 jne fos_registration_bad
 test rcx,rcx
 jz fos_registration_bad
 cmp DWORD PTR [rcx],053465442h
 jne fos_registration_bad
 cmp DWORD PTR [rcx+4],1
 jne fos_registration_bad
 lea rdx,FOS_STREAM_LAYOUT
 cmp QWORD PTR [rcx+8],rdx
 jne fos_registration_bad
 cmp DWORD PTR [rcx+16],FOS_STREAM_FD
 jne fos_registration_bad
 cmp DWORD PTR [rcx+20],8
 jne fos_registration_bad
 mov rdx,QWORD PTR [rax+24]
 test rdx,rdx
 jz fos_registration_bad
 cmp DWORD PTR [rdx],04644504Ch
 jne fos_registration_bad
 cmp DWORD PTR [rdx+4],1
 jne fos_registration_bad
 mov rcx,QWORD PTR [rdx+8]
 test rcx,rcx
 jz fos_registration_bad
 cmp rcx,QWORD PTR [rdx+16]
 jne fos_registration_bad
 cmp DWORD PTR [rcx],046445442h
 jne fos_registration_bad
 cmp DWORD PTR [rcx+4],1
 jne fos_registration_bad
 lea rdx,FOS_FD_LAYOUT
 cmp QWORD PTR [rcx+8],rdx
 jne fos_registration_bad
 cmp DWORD PTR [rcx+16],FOS_FD_INT
 jne fos_registration_bad
 cmp DWORD PTR [rcx+20],4
 jne fos_registration_bad
 cmp DWORD PTR [rcx+24],FOS_FD_HANDLE
 jne fos_registration_bad
 cmp DWORD PTR [rcx+28],8
 jne fos_registration_bad
 cmp DWORD PTR [rcx+32],FOS_FD_APPEND
 jne fos_registration_bad
 cmp DWORD PTR [rcx+36],1
 jne fos_registration_bad
 mov eax,1
 ret
fos_registration_bad:
 xor eax,eax
 ret
fos_registration ENDP

; (ctx,source FOS)->RAX real handle (possibly NULL),EDX 0 ready/1 closed.
; Any unsupported target sets ctx20; invalid heap/type/field protocol sets ctx7.
fos_standard_handle PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 xor r12d,r12d
 xor edi,edi
 lock inc QWORD PTR [boom_file_output_standard_counters+56]
 lea r8,boom_provider_file_bootstrap_pool
 mov r8,QWORD PTR [r8+16]
 call boom_stream_descriptor
 cmp DWORD PTR [rbx],0
 jne fos_std_done
 mov rsi,rax
 test rsi,rsi
 jz fos_std_closed
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz fos_std_bad
 mov rcx,rsi
 lea rdx,FOS_FD_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz fos_std_done
 mov r12,QWORD PTR [rsi+FOS_FD_HANDLE]
 cmp r12,-1
 je fos_std_closed
 mov r13d,1
 mov ecx,-11
 cmp rsi,QWORD PTR [FOS_STD_OUT]
 je fos_std_identity
 mov r13d,2
 mov ecx,-12
 cmp rsi,QWORD PTR [FOS_STD_ERR]
 jne fos_std_unsupported
fos_std_identity:
 cmp DWORD PTR [rsi+FOS_FD_INT],r13d
 jne fos_std_bad
 cmp BYTE PTR [rsi+FOS_FD_APPEND],1
 ja fos_std_bad
 cmp BYTE PTR [rsi+FOS_FD_APPEND],0
 jne fos_std_unsupported
 call GetStdHandle
 cmp rax,r12
 jne fos_std_unsupported
 jmp fos_std_done
fos_std_closed:
 mov edi,1
 lock inc QWORD PTR [boom_file_output_standard_counters+80]
 jmp fos_std_done
fos_std_unsupported:
 mov DWORD PTR [rbx],20
 jmp fos_std_done
fos_std_bad:
 mov DWORD PTR [rbx],7
fos_std_done:
 mov rax,r12
 mov edx,edi
 add rsp,48
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
fos_standard_handle ENDP

; (ctx,PROP112,kind0 IOE/1 NPE/2 bounds/3 OOM,Win32 code,
;  default UTF16 pointer stack5,units stack6). All original String constructors.
fos_throw PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 sub rsp,624
 .allocstack 624
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov edi,r8d
 mov r12d,r9d
 cmp DWORD PTR [rbx],0
 jne fos_throw_done
 mov QWORD PTR [rsp+80],0
 test edi,edi
 jnz fos_throw_allocate
 test r12d,r12d
 jz fos_throw_default
 mov ecx,01200h
 xor edx,edx
 mov r8d,r12d
 xor r9d,r9d
 lea rax,[rsp+96]
 mov QWORD PTR [rsp+32],rax
 mov DWORD PTR [rsp+40],256
 mov QWORD PTR [rsp+48],0
 call FormatMessageW
 cmp eax,256
 jae fos_throw_bad
 cmp eax,3
 jbe fos_throw_format_ready
 cmp WORD PTR [rsp+rax*2+94],10
 jne fos_throw_trim_cr
 dec eax
fos_throw_trim_cr:
 cmp WORD PTR [rsp+rax*2+94],13
 jne fos_throw_trim_dot
 dec eax
fos_throw_trim_dot:
 cmp WORD PTR [rsp+rax*2+94],46
 jne fos_throw_format_ready
 dec eax
fos_throw_format_ready:
 lea r8,[rsp+96]
 mov r9d,eax
 jmp fos_throw_string
fos_throw_default:
 mov r8,QWORD PTR [rsp+704]
 mov r9d,DWORD PTR [rsp+712]
fos_throw_string:
 mov rcx,rbx
 mov rdx,rsi
 call boom_java_property_copy
 test rax,rax
 jz fos_throw_done
 mov QWORD PTR [rsp+80],rax
fos_throw_allocate:
 lea r12,FOS_IOE_CLASS
 lea r13,FOS_IOE_LAYOUT
 test edi,edi
 jz fos_throw_class
 lea r12,FOS_NPE_CLASS
 lea r13,FOS_NPE_LAYOUT
 cmp edi,1
 je fos_throw_class
 lea r12,FOS_BOUNDS_CLASS
 lea r13,FOS_BOUNDS_LAYOUT
 cmp edi,2
 je fos_throw_class
 lea r12,FOS_OOM_CLASS
 lea r13,FOS_OOM_LAYOUT
fos_throw_class:
 mov rcx,r12
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne fos_throw_done
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r13
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz fos_throw_done
 mov QWORD PTR [rsp+64],rax
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [rsp+72],rax
 mov rcx,rbx
 lea rdx,[rsp+64]
 test edi,edi
 jz fos_throw_ioe
 cmp edi,1
 je fos_throw_npe
 cmp edi,2
 je fos_throw_bounds
 call FOS_OOM_CTOR
 jmp fos_throw_set
fos_throw_ioe:
 call FOS_IOE_CTOR
 jmp fos_throw_set
fos_throw_npe:
 call FOS_NPE_CTOR
 jmp fos_throw_set
fos_throw_bounds:
 call FOS_BOUNDS_CTOR
fos_throw_set:
 cmp DWORD PTR [rbx],0
 jne fos_throw_done
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+64]
 lea r8,boom_runtime_type_map
 lea r9,FOS_THROWABLE_TYPE
 call boom_exception_set32
 lock inc QWORD PTR [boom_file_output_standard_counters+88]
 jmp fos_throw_done
fos_throw_bad:
 mov DWORD PTR [rbx],7
fos_throw_done:
 xor eax,eax
 add rsp,624
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
fos_throw ENDP

PUBLIC boom_provider_file_output_standard_service
boom_provider_file_output_standard_service PROC FRAME
 push rbx
 .pushreg rbx
 push rbp
 .pushreg rbp
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,4096
 .allocstack 4096
 mov BYTE PTR [rsp],0
 sub rsp,4096
 .allocstack 4096
 mov BYTE PTR [rsp],0
 sub rsp,312
 .allocstack 312
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov r15d,r9d
 xor ebp,ebp
 xor r12d,r12d
 xor r13d,r13d
 lea r14,[rsp+256]
 mov QWORD PTR [rsp+48],0
 mov QWORD PTR [rsp+56],0
 mov DWORD PTR [rsp+64],0
 mov DWORD PTR [rsp+72],-1
 mov QWORD PTR [rsp+80],0
 mov DWORD PTR [rsp+88],0
 test rbx,rbx
 jz fos_done
 cmp DWORD PTR [rbx],0
 jne fos_done
 test rsi,rsi
 jz fos_bad
 test rdi,rdi
 jz fos_bad
 cmp DWORD PTR [rdi],050524F50h
 jne fos_bad
 cmp DWORD PTR [rdi+4],2
 jne fos_bad
 cmp r15d,1
 ja fos_bad
 call fos_registration
 test eax,eax
 jz fos_unsupported
 lock inc QWORD PTR [boom_file_output_standard_counters]
 mov rdx,QWORD PTR [rsi]
 test rdx,rdx
 jz fos_null_receiver
 mov rcx,QWORD PTR [boom_heap_ptr]
 call boom_heap_contains
 test eax,eax
 jz fos_bad
 mov rcx,QWORD PTR [rsi]
 lea rdx,FOS_STREAM_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz fos_cleanup
 test r15d,r15d
 jnz fos_array
 mov eax,DWORD PTR [rsi+8]
 mov BYTE PTR [r14],al
 mov r12d,1
 mov eax,DWORD PTR [rsi+16]
 mov DWORD PTR [rsp+128],eax
 jmp fos_write_loop
fos_array:
 mov r13,QWORD PTR [rsi+8]
 test r13,r13
 jz fos_null_array
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r13
 call boom_heap_contains
 test eax,eax
 jz fos_bad
 cmp QWORD PTR [r13-8],264
 jne fos_bad
 cmp DWORD PTR [r13-20],0
 jne fos_bad
 movsxd rax,DWORD PTR [rsi+16]
 movsxd r12,DWORD PTR [rsi+24]
 test rax,rax
 js fos_bounds
 test r12,r12
 js fos_bounds
 lea rdx,[rax+r12]
 cmp rdx,QWORD PTR [r13-16]
 ja fos_bounds
 test r12,r12
 jz fos_cleanup
 add r13,rax
 mov eax,DWORD PTR [rsi+32]
 mov DWORD PTR [rsp+128],eax
 cmp r12d,8192
 jbe fos_copy
 call GetProcessHeap
 mov QWORD PTR [rsp+48],rax
 mov rcx,rax
 xor edx,edx
 mov r8,r12
 call HeapAlloc
 test rax,rax
 jz fos_oom
 mov r14,rax
 mov QWORD PTR [rsp+56],rax
 lock inc QWORD PTR [boom_file_output_standard_counters+32]
 lock inc QWORD PTR [boom_file_output_standard_counters+40]
fos_copy:
 mov QWORD PTR [rsp+160],rsi
 mov QWORD PTR [rsp+168],rdi
 mov rsi,r13
 mov rdi,r14
 mov rcx,r12
 rep movsb
 mov rsi,QWORD PTR [rsp+160]
 mov rdi,QWORD PTR [rsp+168]
fos_write_loop:
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi]
 call fos_standard_handle
 cmp DWORD PTR [rbx],0
 jne fos_cleanup
 cmp edx,1
 je fos_closed
 mov r13,rax
 cmp DWORD PTR [rsp+128],0
 jne fos_unsupported
 mov rcx,r13
 lea rdx,[r14+rbp]
 mov r8d,r12d
 lea r9,[rsp+136]
 mov DWORD PTR [rsp+136],0
 mov QWORD PTR [rsp+32],0
 lock inc QWORD PTR [boom_file_output_standard_counters+8]
 call WriteFile
 test eax,eax
 jz fos_write_failed
 mov eax,DWORD PTR [rsp+136]
 cmp eax,r12d
 ja fos_bad
 test eax,eax
 jz fos_zero_progress
 lock add QWORD PTR [boom_file_output_standard_counters+16],rax
 add rbp,rax
 sub r12,rax
 jz fos_cleanup
 lock inc QWORD PTR [boom_file_output_standard_counters+24]
 jmp fos_write_loop
fos_write_failed:
 call GetLastError
 mov DWORD PTR [rsp+64],eax
 jmp fos_write_error
fos_zero_progress:
 ; writeSingle ignores a successful zero count in the pinned C; only the
 ; array loop needs an explicit non-progress failure instead of hanging.
 test r15d,r15d
 jz fos_cleanup
 lock inc QWORD PTR [boom_file_output_standard_counters+64]
fos_write_error:
 mov DWORD PTR [rsp+72],0
 lea rax,fos_write_message
 mov QWORD PTR [rsp+80],rax
 mov DWORD PTR [rsp+88],11
 jmp fos_cleanup
fos_closed:
 mov DWORD PTR [rsp+72],0
 lea rax,fos_closed_message
 mov QWORD PTR [rsp+80],rax
 mov DWORD PTR [rsp+88],13
 jmp fos_cleanup
fos_null_array:
 mov DWORD PTR [rsp+72],1
 jmp fos_cleanup
fos_bounds:
 mov DWORD PTR [rsp+72],2
 jmp fos_cleanup
fos_oom:
 mov DWORD PTR [rsp+72],3
 jmp fos_cleanup
fos_unsupported:
 mov DWORD PTR [rbx],20
 lock inc QWORD PTR [boom_file_output_standard_counters+72]
 jmp fos_cleanup
fos_null_receiver:
 mov DWORD PTR [rbx],4
 jmp fos_cleanup
fos_bad:
 mov DWORD PTR [rbx],7
fos_cleanup:
 cmp QWORD PTR [rsp+56],0
 je fos_after_free
 mov rcx,QWORD PTR [rsp+48]
 xor edx,edx
 mov r8,QWORD PTR [rsp+56]
 call HeapFree
 test eax,eax
 jz fos_free_failed
 lock dec QWORD PTR [boom_file_output_standard_counters+32]
 lock inc QWORD PTR [boom_file_output_standard_counters+48]
 mov QWORD PTR [rsp+56],0
 jmp fos_after_free
fos_free_failed:
 cmp DWORD PTR [rbx],0
 jne fos_after_free
 mov DWORD PTR [rbx],7
fos_after_free:
 cmp DWORD PTR [rbx],0
 jne fos_done
 cmp DWORD PTR [rsp+72],-1
 je fos_done
 mov rcx,rbx
 mov rdx,rdi
 mov r8d,DWORD PTR [rsp+72]
 mov r9d,DWORD PTR [rsp+64]
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [rsp+32],rax
 mov eax,DWORD PTR [rsp+88]
 mov DWORD PTR [rsp+40],eax
 call fos_throw
fos_done:
 xor eax,eax
 add rsp,312
 add rsp,4096
 add rsp,4096
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_provider_file_output_standard_service ENDP
