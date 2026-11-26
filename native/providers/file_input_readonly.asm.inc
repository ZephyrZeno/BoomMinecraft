; Original FileInputStream read-only native batch, normal Context32/argv.
; ops open0=0/read0=1/readBytes=2/length0=3/position0=4/skip0=5/available0=6/FD.close0=7.
; Each owned FD is rooted until explicit close. No external/standard handle adoption.
.const
fir_closed WORD 83,116,114,101,97,109,32,67,108,111,115,101,100
fir_read_error WORD 82,101,97,100,32,101,114,114,111,114
fir_seek_error WORD 83,101,101,107,32,101,114,114,111,114
fir_length_error WORD 71,101,116,76,101,110,103,116,104,32,102,97,105,108,101,100
fir_close_error WORD 99,108,111,115,101,32,102,97,105,108,101,100
.data
ALIGN 8
fir_registry_lock QWORD 0
PUBLIC boom_file_input_owner_roots
boom_file_input_owner_roots QWORD 4096 DUP(0)
; Slot32: state0,borrow4,owned HANDLE8,exclusive I/O SRW16,reserved24.
; states free0/open1/closing2/failed-owned3/opening4.
PUBLIC boom_file_input_owners
boom_file_input_owners BYTE 131072 DUP(0)
PUBLIC boom_file_input_live_handles
boom_file_input_live_handles QWORD 0
PUBLIC boom_file_input_owned_buffers
boom_file_input_owned_buffers QWORD 0
PUBLIC boom_file_input_close_waits
boom_file_input_close_waits QWORD 0
.code

; Original published FileDescriptor registration must agree with this source model.
fir_registration PROC PRIVATE
 lea rax,boom_provider_file_bootstrap_pool
 cmp DWORD PTR [rax],04F49464Eh
 jne fir_registration_bad
 cmp DWORD PTR [rax+4],1
 jne fir_registration_bad
 mov rax,QWORD PTR [rax+24]
 test rax,rax
 jz fir_registration_bad
 cmp DWORD PTR [rax],04644504Ch
 jne fir_registration_bad
 cmp DWORD PTR [rax+4],1
 jne fir_registration_bad
 mov rdx,QWORD PTR [rax+8]
 test rdx,rdx
 jz fir_registration_bad
 cmp QWORD PTR [rax+16],rdx
 jne fir_registration_bad
 cmp DWORD PTR [rdx],046445442h
 jne fir_registration_bad
 cmp DWORD PTR [rdx+4],1
 jne fir_registration_bad
 lea rax,FIR_FD_LAYOUT
 cmp QWORD PTR [rdx+8],rax
 jne fir_registration_bad
 cmp DWORD PTR [rdx+16],FIR_FD_INT
 jne fir_registration_bad
 cmp DWORD PTR [rdx+20],4
 jne fir_registration_bad
 cmp DWORD PTR [rdx+24],FIR_FD_HANDLE
 jne fir_registration_bad
 cmp DWORD PTR [rdx+28],8
 jne fir_registration_bad
 cmp DWORD PTR [rdx+32],FIR_FD_APPEND
 jne fir_registration_bad
 cmp DWORD PTR [rdx+36],1
 jne fir_registration_bad
 mov eax,1
 ret
fir_registration_bad:
 xor eax,eax
 ret
fir_registration ENDP

; Find an owner while holding fir_registry_lock. RDX=FD -> RAX=slot,ECX=index.
fir_find PROC PRIVATE
 lea r8,boom_file_input_owner_roots
 xor ecx,ecx
fir_find_next:
 cmp QWORD PTR [r8+rcx*8],rdx
 je fir_find_yes
 inc ecx
 cmp ecx,4096
 jb fir_find_next
 xor eax,eax
 ret
fir_find_yes:
 mov eax,ecx
 shl rax,5
 lea r8,boom_file_input_owners
 add rax,r8
 ret
fir_find ENDP

; Source String -> owned NUL-terminated path; RDX returns a captured Win32 error.
; Heap scratch is released here on failure and by the service on success.
fir_path PROC PRIVATE FRAME
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
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 xor edi,edi
 xor r13d,r13d
 test rsi,rsi
 jz fir_path_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 call boom_heap_contains
 test eax,eax
 jz fir_path_bad
 mov rcx,rsi
 lea rdx,FIR_STRING_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz fir_path_done
 mov QWORD PTR [rsp+32],rsi
 mov rcx,rbx
 lea rdx,[rsp+32]
 call FIR_STRING_LENGTH
 cmp DWORD PTR [rbx],0
 jne fir_path_done
 test eax,eax
 js fir_path_bad
 mov DWORD PTR [rsp+40],eax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call FIR_STRING_CHARS
 cmp DWORD PTR [rbx],0
 jne fir_path_done
 mov r12,rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rax
 call boom_heap_contains
 test eax,eax
 jz fir_path_bad
 cmp QWORD PTR [r12-8],261
 jne fir_path_bad
 cmp DWORD PTR [r12-20],0
 jne fir_path_bad
 mov eax,DWORD PTR [rsp+40]
 shl rax,1
 cmp QWORD PTR [r12-16],rax
 jne fir_path_bad
 mov rsi,QWORD PTR [r12-16]
 shr rsi,1
 xor ecx,ecx
fir_path_length:
 cmp rcx,rsi
 jae fir_path_length_ready
 cmp WORD PTR [r12+rcx*2],0
 je fir_path_length_ready
 inc ecx
 cmp ecx,32767
 jbe fir_path_length
 mov r13d,206
 jmp fir_path_done
fir_path_length_ready:
 test ecx,ecx
 jz fir_path_done
 mov esi,ecx
 call GetProcessHeap
 mov QWORD PTR [rsp+48],rax
 mov rcx,rax
 xor edx,edx
 mov r8d,131104
 call HeapAlloc
 test rax,rax
 jz fir_path_oom
 mov rdi,rax
 lock inc QWORD PTR [boom_file_input_owned_buffers]
 xor ecx,ecx
fir_path_copy:
 movzx eax,WORD PTR [r12+rcx*2]
 mov WORD PTR [rdi+rcx*2],ax
 inc ecx
 cmp ecx,esi
 jb fir_path_copy
 mov WORD PTR [rdi+rsi*2],0
 mov rcx,rdi
 mov edx,32768
 lea r8,[rdi+65552]
 xor r9d,r9d
 call GetFullPathNameW
 test eax,eax
 jz fir_path_system_error
 cmp eax,32768
 jae fir_path_too_long
 cmp eax,247
 jbe fir_path_success
 lea r12,[rdi+65552]
 mov esi,eax
 xor ecx,ecx
 cmp DWORD PTR [r12],005C005Ch
 jne fir_path_drive_prefix
 cmp DWORD PTR [r12+4],005C003Fh
 je fir_path_copy_full
 cmp esi,32761
 ja fir_path_too_long
 mov rax,005C003F005C005Ch
 mov QWORD PTR [rdi],rax
 mov rax,005C0043004E0055h
 mov QWORD PTR [rdi+8],rax
 add r12,4
 sub esi,2
 mov ecx,8
 jmp fir_path_copy_full
fir_path_drive_prefix:
 cmp esi,32763
 ja fir_path_too_long
 mov rax,005C003F005C005Ch
 mov QWORD PTR [rdi],rax
 mov ecx,4
fir_path_copy_full:
 xor edx,edx
fir_path_copy_full_loop:
 movzx eax,WORD PTR [r12+rdx*2]
 mov WORD PTR [rdi+rcx*2],ax
 inc ecx
 inc edx
 cmp edx,esi
 jbe fir_path_copy_full_loop
fir_path_success:
 mov rax,rdi
 xor edx,edx
 jmp fir_path_return
fir_path_too_long:
 mov r13d,206
 jmp fir_path_free
fir_path_system_error:
 call GetLastError
 mov r13d,eax
fir_path_free:
 mov rcx,QWORD PTR [rsp+48]
 xor edx,edx
 mov r8,rdi
 call HeapFree
 test eax,eax
 jz fir_path_free_failed
 lock dec QWORD PTR [boom_file_input_owned_buffers]
 jmp fir_path_done
fir_path_free_failed:
 mov DWORD PTR [rbx],20
 jmp fir_path_done
fir_path_null:
 mov DWORD PTR [rbx],4
 jmp fir_path_done
fir_path_bad:
 mov DWORD PTR [rbx],7
 jmp fir_path_done
fir_path_oom:
 mov DWORD PTR [rbx],3
fir_path_done:
 xor eax,eax
 mov edx,r13d
fir_path_return:
 add rsp,64
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
fir_path ENDP

; Throw original typed errors after every OS lock/borrow has been released.
; RCX ctx,RDX PROP pool,R8D kind(IOE0/FNFE1/NPE2/bounds3),R9D Win32 code.
; Stack args: original path String,default UTF16 pointer,default units.
fir_throw PROC PRIVATE FRAME
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
 jne fir_throw_done
 cmp edi,2
 jae fir_throw_allocate
 test r12d,r12d
 jz fir_throw_default
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
 jae fir_throw_bad
 cmp eax,3
 jbe fir_throw_format_ready
 cmp WORD PTR [rsp+rax*2+94],10
 jne fir_throw_trim_cr
 dec eax
fir_throw_trim_cr:
 cmp WORD PTR [rsp+rax*2+94],13
 jne fir_throw_trim_dot
 dec eax
fir_throw_trim_dot:
 cmp WORD PTR [rsp+rax*2+94],46
 jne fir_throw_format_ready
 dec eax
fir_throw_format_ready:
 lea r8,[rsp+96]
 mov r9d,eax
 jmp fir_throw_string
fir_throw_default:
 mov r8,QWORD PTR [rsp+712]
 mov r9d,DWORD PTR [rsp+720]
 test r8,r8
 jnz fir_throw_string
 xor eax,eax
 jmp fir_throw_message
fir_throw_string:
 mov rcx,rbx
 mov rdx,rsi
 call boom_java_property_copy
 test rax,rax
 jz fir_throw_done
fir_throw_message:
 mov QWORD PTR [rsp+80],rax
fir_throw_allocate:
 lea r12,FIR_IOE_CLASS
 lea r13,FIR_IOE_LAYOUT
 test edi,edi
 jz fir_throw_class
 lea r12,FIR_FNFE_CLASS
 lea r13,FIR_FNFE_LAYOUT
 cmp edi,1
 je fir_throw_class
 lea r12,FIR_NPE_CLASS
 lea r13,FIR_NPE_LAYOUT
 cmp edi,2
 je fir_throw_class
 lea r12,FIR_BOUNDS_CLASS
 lea r13,FIR_BOUNDS_LAYOUT
fir_throw_class:
 mov rcx,r12
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne fir_throw_done
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r13
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz fir_throw_done
 mov QWORD PTR [rsp+64],rax
 mov rcx,rbx
 lea rdx,[rsp+64]
 cmp edi,1
 je fir_throw_fnfe
 cmp edi,2
 je fir_throw_npe
 cmp edi,3
 je fir_throw_bounds
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [rsp+72],rax
 call FIR_IOE_CTOR
 jmp fir_throw_set
fir_throw_fnfe:
 mov rax,QWORD PTR [rsp+704]
 mov QWORD PTR [rsp+72],rax
 call FIR_FNFE_CTOR
 jmp fir_throw_set
fir_throw_npe:
 call FIR_NPE_CTOR
 jmp fir_throw_set
fir_throw_bounds:
 call FIR_BOUNDS_CTOR
fir_throw_set:
 cmp DWORD PTR [rbx],0
 jne fir_throw_done
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+64]
 lea r8,boom_runtime_type_map
 lea r9,FIR_THROWABLE_TYPE
 call boom_exception_set32
 jmp fir_throw_done
fir_throw_bad:
 mov DWORD PTR [rbx],7
fir_throw_done:
 xor eax,eax
 add rsp,624
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
fir_throw ENDP

PUBLIC boom_provider_file_input_service
boom_provider_file_input_service PROC FRAME
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
 sub rsp,328
 .allocstack 328
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov r15d,r9d
 xor ebp,ebp
 xor r12d,r12d
 xor r13d,r13d
 xor r14d,r14d
 mov QWORD PTR [rsp+64],0
 mov QWORD PTR [rsp+104],0
 mov DWORD PTR [rsp+96],0
 mov DWORD PTR [rsp+160],0
 mov DWORD PTR [rsp+168],0
 mov DWORD PTR [rsp+176],0
 mov DWORD PTR [rsp+184],-1
 mov QWORD PTR [rsp+192],0
 mov DWORD PTR [rsp+200],0
 mov QWORD PTR [rsp+208],0
 test rbx,rbx
 jz fir_done
 cmp DWORD PTR [rbx],0
 jne fir_done
 cmp r15d,7
 ja fir_bad
 test rdi,rdi
 jz fir_bad
 cmp DWORD PTR [rdi],050524F50h
 jne fir_bad
 cmp DWORD PTR [rdi+4],2
 jne fir_bad
 test rsi,rsi
 jz fir_bad
 call fir_registration
 test eax,eax
 jz fir_unregistered
 mov rdx,QWORD PTR [rsi]
 test rdx,rdx
 jz fir_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 call boom_heap_contains
 test eax,eax
 jz fir_bad
 cmp r15d,7
 je fir_direct_fd
 mov rcx,QWORD PTR [rsi]
 lea rdx,FIR_STREAM_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz fir_cleanup
 cmp r15d,2
 jne fir_get_fd
 mov r14,QWORD PTR [rsi+8]
 test r14,r14
 jz fir_array_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz fir_bad
 cmp QWORD PTR [r14-8],264
 jne fir_bad
 cmp DWORD PTR [r14-20],0
 jne fir_bad
 movsxd rax,DWORD PTR [rsi+16]
 movsxd rdx,DWORD PTR [rsi+24]
 test rax,rax
 js fir_bounds
 test rdx,rdx
 js fir_bounds
 add rdx,rax
 cmp rdx,QWORD PTR [r14-16]
 ja fir_bounds
 add r14,rax
 cmp DWORD PTR [rsi+24],0
 je fir_cleanup
fir_get_fd:
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi]
 lea r8,boom_provider_file_bootstrap_pool
 mov r8,QWORD PTR [r8+8]
 call boom_stream_descriptor
 cmp DWORD PTR [rbx],0
 jne fir_cleanup
 mov rbp,rax
 test rbp,rbp
 jz fir_stream_closed
 jmp fir_check_fd
fir_direct_fd:
 mov rbp,QWORD PTR [rsi]
fir_check_fd:
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rbp
 call boom_heap_contains
 test eax,eax
 jz fir_bad
 mov rcx,rbp
 lea rdx,FIR_FD_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz fir_cleanup
 cmp r15d,7
 je fir_close
 cmp DWORD PTR [rbp+FIR_FD_INT],-1
 jne fir_unregistered
 test r15d,r15d
 jz fir_open
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rdx,rbp
 call fir_find
 test rax,rax
 jz fir_borrow_missing
 mov r12,rax
 cmp DWORD PTR [r12],1
 jne fir_borrow_closed
 mov r13,QWORD PTR [r12+8]
 cmp QWORD PTR [rbp+FIR_FD_HANDLE],r13
 jne fir_borrow_unknown
 inc DWORD PTR [r12+4]
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rsp+160],1
 lea rcx,[r12+16]
 call AcquireSRWLockExclusive
 mov DWORD PTR [rsp+176],1
 cmp r15d,2
 jbe fir_read
 cmp r15d,3
 je fir_length
 cmp r15d,4
 je fir_position
 cmp r15d,5
 je fir_skip
 jmp fir_available
fir_borrow_missing:
 cmp QWORD PTR [rbp+FIR_FD_HANDLE],-1
 jne fir_borrow_unknown
fir_borrow_closed:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 jmp fir_stream_closed
fir_borrow_unknown:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 jmp fir_unregistered

fir_open:
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rdx,rbp
 call fir_find
 test rax,rax
 jnz fir_open_reject
 cmp QWORD PTR [rbp+FIR_FD_HANDLE],-1
 jne fir_open_reject
 lea r8,boom_file_input_owner_roots
 xor ecx,ecx
fir_open_slot:
 cmp QWORD PTR [r8+rcx*8],0
 je fir_open_slot_ready
 inc ecx
 cmp ecx,4096
 jb fir_open_slot
 jmp fir_open_reject
fir_open_slot_ready:
 mov QWORD PTR [r8+rcx*8],rbp
 mov r12d,ecx
 shl r12,5
 lea rax,boom_file_input_owners
 add r12,rax
 mov DWORD PTR [r12],4
 mov DWORD PTR [r12+4],0
 mov QWORD PTR [r12+8],0
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rsp+168],1
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+8]
 mov QWORD PTR [rsp+208],rdx
 call fir_path
 mov QWORD PTR [rsp+104],rax
 mov DWORD PTR [rsp+96],edx
 test rax,rax
 jz fir_open_path_failed
 mov rcx,rax
 mov edx,080000000h
 mov r8d,3
 xor r9d,r9d
 mov QWORD PTR [rsp+32],3
 mov QWORD PTR [rsp+40],080h
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 je fir_open_system_error
 mov r13,rax
 mov QWORD PTR [r12+8],rax
 lock inc QWORD PTR [boom_file_input_live_handles]
 mov rcx,rax
 call GetFileType
 cmp eax,1
 jne fir_open_unsupported
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov QWORD PTR [rbp+FIR_FD_HANDLE],r13
 mov BYTE PTR [rbp+FIR_FD_APPEND],0
 mov DWORD PTR [r12],1
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rsp+168],0
 mov rcx,r12
 call WakeByAddressAll
 jmp fir_cleanup
fir_open_reject:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 jmp fir_unregistered
fir_open_system_error:
 call GetLastError
 mov DWORD PTR [rsp+96],eax
fir_open_path_failed:
 mov DWORD PTR [rsp+184],1
 jmp fir_cleanup
fir_open_unsupported:
 mov rcx,r13
 call CloseHandle
 test eax,eax
 jz fir_open_rollback_failed
 lock dec QWORD PTR [boom_file_input_live_handles]
 mov QWORD PTR [r12+8],0
 jmp fir_unregistered
fir_open_rollback_failed:
 call GetLastError
 mov DWORD PTR [rsp+96],eax
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov DWORD PTR [r12],3
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rsp+168],0
 mov rcx,r12
 call WakeByAddressAll
 mov DWORD PTR [rsp+184],0
 lea rax,fir_close_error
 mov QWORD PTR [rsp+192],rax
 mov DWORD PTR [rsp+200],12
 jmp fir_cleanup

fir_read:
 lea rdx,[rsp+256]
 mov r8d,1
 cmp r15d,1
 je fir_read_buffer
 mov r8d,DWORD PTR [rsi+24]
 cmp r8d,8192
 jbe fir_read_buffer
 mov QWORD PTR [rsp+120],r8
 call GetProcessHeap
 mov QWORD PTR [rsp+112],rax
 mov rcx,rax
 xor edx,edx
 mov r8,QWORD PTR [rsp+120]
 call HeapAlloc
 test rax,rax
 jz fir_oom
 mov QWORD PTR [rsp+104],rax
 lock inc QWORD PTR [boom_file_input_owned_buffers]
 mov rdx,rax
 mov r8d,DWORD PTR [rsi+24]
fir_read_buffer:
 mov rcx,r13
 lea r9,[rsp+72]
 mov DWORD PTR [rsp+72],0
 mov QWORD PTR [rsp+32],0
 call ReadFile
 test eax,eax
 jz fir_read_failed
 mov eax,DWORD PTR [rsp+72]
 test eax,eax
 jz fir_eof
 cmp r15d,1
 je fir_read_single
 cmp eax,DWORD PTR [rsi+24]
 ja fir_bad
 mov QWORD PTR [rsp+64],rax
 mov rcx,rax
 mov rdx,QWORD PTR [rsp+104]
 test rdx,rdx
 jnz fir_copy_read
 lea rdx,[rsp+256]
fir_copy_read:
 mov al,BYTE PTR [rdx]
 mov BYTE PTR [r14],al
 inc rdx
 inc r14
 dec rcx
 jnz fir_copy_read
 jmp fir_cleanup
fir_read_single:
 cmp eax,1
 jne fir_bad
 movzx eax,BYTE PTR [rsp+256]
 mov QWORD PTR [rsp+64],rax
 jmp fir_cleanup
fir_read_failed:
 call GetLastError
 cmp eax,109
 je fir_eof
 mov DWORD PTR [rsp+96],eax
 mov DWORD PTR [rsp+184],0
 lea rax,fir_read_error
 mov QWORD PTR [rsp+192],rax
 mov DWORD PTR [rsp+200],10
 jmp fir_cleanup
fir_eof:
 mov QWORD PTR [rsp+64],-1
 jmp fir_cleanup
fir_length:
 mov rcx,r13
 lea rdx,[rsp+80]
 call GetFileSizeEx
 test eax,eax
 jz fir_length_failed
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [rsp+64],rax
 jmp fir_cleanup
fir_length_failed:
 call GetLastError
 mov DWORD PTR [rsp+96],eax
 mov DWORD PTR [rsp+184],0
 lea rax,fir_length_error
 mov QWORD PTR [rsp+192],rax
 mov DWORD PTR [rsp+200],16
 jmp fir_cleanup
fir_position:
 mov rcx,r13
 xor edx,edx
 lea r8,[rsp+80]
 mov r9d,1
 call SetFilePointerEx
 test eax,eax
 jz fir_seek_failed
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [rsp+64],rax
 jmp fir_cleanup
fir_skip:
 mov rcx,r13
 xor edx,edx
 lea r8,[rsp+88]
 mov r9d,1
 call SetFilePointerEx
 test eax,eax
 jz fir_seek_failed
 mov rcx,r13
 mov rdx,QWORD PTR [rsi+8]
 lea r8,[rsp+80]
 mov r9d,1
 call SetFilePointerEx
 test eax,eax
 jz fir_seek_failed
 mov rax,QWORD PTR [rsp+80]
 sub rax,QWORD PTR [rsp+88]
 mov QWORD PTR [rsp+64],rax
 jmp fir_cleanup
fir_available:
 mov rcx,r13
 xor edx,edx
 lea r8,[rsp+88]
 mov r9d,1
 call SetFilePointerEx
 test eax,eax
 jz fir_seek_failed
 mov rcx,r13
 lea rdx,[rsp+80]
 call GetFileSizeEx
 test eax,eax
 jz fir_length_failed
 mov rax,QWORD PTR [rsp+80]
 sub rax,QWORD PTR [rsp+88]
 xor edx,edx
 test rax,rax
 cmovs rax,rdx
 mov edx,07FFFFFFFh
 cmp rax,rdx
 cmova rax,rdx
 mov QWORD PTR [rsp+64],rax
 jmp fir_cleanup
fir_seek_failed:
 call GetLastError
 mov DWORD PTR [rsp+96],eax
 mov DWORD PTR [rsp+184],0
 lea rax,fir_seek_error
 mov QWORD PTR [rsp+192],rax
 mov DWORD PTR [rsp+200],10
 jmp fir_cleanup

fir_close:
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rdx,rbp
 call fir_find
 test rax,rax
 jz fir_close_absent
 mov r12,rax
 mov eax,DWORD PTR [r12]
 cmp eax,2
 je fir_close_wait_state
 cmp eax,4
 je fir_close_wait_state
 cmp eax,1
 je fir_close_claim
 cmp eax,3
 jne fir_close_unknown
fir_close_claim:
 mov r13,QWORD PTR [r12+8]
 mov DWORD PTR [r12],2
 mov QWORD PTR [rbp+FIR_FD_HANDLE],-1
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
fir_close_wait_borrow:
 mov eax,DWORD PTR [r12+4]
 test eax,eax
 jz fir_close_os
 lock inc QWORD PTR [boom_file_input_close_waits]
 mov DWORD PTR [rsp+72],eax
 lea rcx,[r12+4]
 lea rdx,[rsp+72]
 mov r8d,4
 mov r9d,-1
 call WaitOnAddress
 jmp fir_close_wait_borrow
fir_close_os:
 mov rcx,r13
 call CloseHandle
 test eax,eax
 jz fir_close_failed
 lock dec QWORD PTR [boom_file_input_live_handles]
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rax,r12
 lea rdx,boom_file_input_owners
 sub rax,rdx
 shr rax,5
 lea rdx,boom_file_input_owner_roots
 mov QWORD PTR [rdx+rax*8],0
 mov QWORD PTR [r12+8],0
 mov DWORD PTR [r12],0
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rcx,r12
 call WakeByAddressAll
 jmp fir_cleanup
fir_close_failed:
 call GetLastError
 mov DWORD PTR [rsp+96],eax
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov DWORD PTR [r12],3
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rcx,r12
 call WakeByAddressAll
 mov DWORD PTR [rsp+184],0
 lea rax,fir_close_error
 mov QWORD PTR [rsp+192],rax
 mov DWORD PTR [rsp+200],12
 jmp fir_cleanup
fir_close_wait_state:
 mov DWORD PTR [rsp+72],eax
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rcx,r12
 lea rdx,[rsp+72]
 mov r8d,4
 mov r9d,-1
 call WaitOnAddress
 jmp fir_close
fir_close_absent:
 cmp QWORD PTR [rbp+FIR_FD_HANDLE],-1
 jne fir_close_unknown
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 jmp fir_cleanup
fir_close_unknown:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 jmp fir_unregistered

fir_stream_closed:
 mov DWORD PTR [rsp+184],0
 lea rax,fir_closed
 mov QWORD PTR [rsp+192],rax
 mov DWORD PTR [rsp+200],13
 jmp fir_cleanup
fir_array_null:
 mov DWORD PTR [rsp+184],2
 jmp fir_cleanup
fir_bounds:
 mov DWORD PTR [rsp+184],3
 jmp fir_cleanup
fir_null:
 mov DWORD PTR [rbx],4
 jmp fir_cleanup
fir_bad:
 mov DWORD PTR [rbx],7
 jmp fir_cleanup
fir_unregistered:
 mov DWORD PTR [rbx],20
 jmp fir_cleanup
fir_oom:
 mov DWORD PTR [rbx],3
fir_cleanup:
 cmp DWORD PTR [rsp+176],0
 je fir_cleanup_borrow
 lea rcx,[r12+16]
 call ReleaseSRWLockExclusive
fir_cleanup_borrow:
 cmp DWORD PTR [rsp+160],0
 je fir_cleanup_reservation
 lock dec DWORD PTR [r12+4]
 jnz fir_cleanup_reservation
 lea rcx,[r12+4]
 call WakeByAddressAll
fir_cleanup_reservation:
 cmp DWORD PTR [rsp+168],0
 je fir_cleanup_buffer
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rax,r12
 lea rdx,boom_file_input_owners
 sub rax,rdx
 shr rax,5
 lea rdx,boom_file_input_owner_roots
 mov QWORD PTR [rdx+rax*8],0
 mov DWORD PTR [r12],0
 mov QWORD PTR [r12+8],0
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rcx,r12
 call WakeByAddressAll
fir_cleanup_buffer:
 mov r14,QWORD PTR [rsp+104]
 test r14,r14
 jz fir_cleanup_throw
 call GetProcessHeap
 mov rcx,rax
 xor edx,edx
 mov r8,r14
 call HeapFree
 test eax,eax
 jz fir_cleanup_free_failed
 lock dec QWORD PTR [boom_file_input_owned_buffers]
 jmp fir_cleanup_throw
fir_cleanup_free_failed:
 cmp DWORD PTR [rbx],0
 jne fir_cleanup_throw
 mov DWORD PTR [rbx],20
fir_cleanup_throw:
 cmp DWORD PTR [rbx],0
 jne fir_zero_result
 mov r8d,DWORD PTR [rsp+184]
 cmp r8d,-1
 je fir_done
 mov rcx,rbx
 mov rdx,rdi
 mov r9d,DWORD PTR [rsp+96]
 mov rax,QWORD PTR [rsp+208]
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [rsp+192]
 mov QWORD PTR [rsp+40],rax
 mov eax,DWORD PTR [rsp+200]
 mov DWORD PTR [rsp+48],eax
 call fir_throw
fir_zero_result:
 mov QWORD PTR [rsp+64],0
fir_done:
 mov rax,QWORD PTR [rsp+64]
 add rsp,8520
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_provider_file_input_service ENDP
