; Win64(ctx RCX, exact Win32 DWORD error EDX, trusted temporary root R8).
; Normal source object/constructor only; no host field writes or fabricated oop.
; Root storage is owned/registered by the caller, not by this helper.
.code
PUBLIC boom_windows_nio_throw_error
boom_windows_nio_throw_error PROC FRAME
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
 mov esi,edx
 mov rdi,r8
 test rbx,rbx
 jz wnfe_no_context
 cmp DWORD PTR [rbx],0
 jne wnfe_return
 cmp QWORD PTR [rbx+16],0
 jne wnfe_return
 cmp QWORD PTR [rbx+24],0
 jne wnfe_return
 test rdi,rdi
 jz wnfe_argument
 test dil,7
 jnz wnfe_argument
 cmp QWORD PTR [rdi],0
 jne wnfe_root_busy
 lea rcx,WNFA_ERROR_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz wnfe_ensure_failed
 cmp DWORD PTR [rbx],0
 jne wnfe_return
 cmp QWORD PTR [rbx+16],0
 jne wnfe_return
 cmp QWORD PTR [rbx+24],0
 jne wnfe_return
 mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,WNFA_ERROR_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz wnfe_allocation_failed
 mov QWORD PTR [rdi],rax
 mov QWORD PTR [rsp+32],rax
 movsxd rax,esi
 mov QWORD PTR [rsp+40],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call WNFA_ERROR_CTOR
 cmp DWORD PTR [rbx],0
 jne wnfe_clear_root
 cmp QWORD PTR [rbx+16],0
 jne wnfe_clear_root
 cmp QWORD PTR [rbx+24],0
 jne wnfe_clear_root
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi]
 lea r8,boom_runtime_type_map
 lea r9,WNFA_THROWABLE_TYPE
 call boom_exception_set32
wnfe_clear_root:
 mov QWORD PTR [rdi],0
 jmp wnfe_return
wnfe_allocation_failed:
 cmp DWORD PTR [rbx],0
 jne wnfe_return
 mov DWORD PTR [rbx],3
 jmp wnfe_return
wnfe_ensure_failed:
 cmp DWORD PTR [rbx],0
 jne wnfe_return
 cmp QWORD PTR [rbx+16],0
 jne wnfe_return
 cmp QWORD PTR [rbx+24],0
 jne wnfe_return
wnfe_root_busy:
 mov DWORD PTR [rbx],20
 jmp wnfe_return
wnfe_argument:
 mov DWORD PTR [rbx],7
wnfe_return:
 mov eax,DWORD PTR [rbx]
 jmp wnfe_done
wnfe_no_context:
 xor eax,eax
wnfe_done:
 add rsp,56
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_windows_nio_throw_error ENDP
