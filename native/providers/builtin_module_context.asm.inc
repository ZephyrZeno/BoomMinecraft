; Internal module ABI, never a JavaVM/JNIEnv table or a JNI function address.
; VMBC48/1: heap cell8, actual Thread provider registry cell16, type map24,
; original Thread TypeDesc32, original BaseVirtualThread TypeDesc40.
; check(Context32,pool,body version)->JNI-style status, without an env pointer.
; Only the 1.2 query used by the locked nio body is implemented here.
EXTERN boom_threads_current:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
PUBLIC boom_builtin_module_check
PUBLIC boom_builtin_nio_body
PUBLIC boom_builtin_nio_on_load
.code
boom_builtin_module_check PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 test rbx,rbx
 jz bmc_error
 cmp DWORD PTR [rbx],0
 jne bmc_error
 cmp r8d,00010002h
 jne bmc_version
 test rsi,rsi
 jz bmc_invalid
 cmp DWORD PTR [rsi],043424D56h
 jne bmc_invalid
 cmp DWORD PTR [rsi+4],1
 jne bmc_invalid
 mov ecx,8
bmc_pool_pointer:
 cmp QWORD PTR [rsi+rcx],0
 je bmc_invalid
 add ecx,8
 cmp ecx,48
 jb bmc_pool_pointer
 mov rcx,QWORD PTR [rsi+16]
 mov rcx,QWORD PTR [rcx]
 test rcx,rcx
 jz bmc_detached
 call boom_threads_current
 test rax,rax
 jz bmc_detached
 mov rdi,rax
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 test rcx,rcx
 jz bmc_invalid
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz bmc_invalid
 mov rcx,rdi
 mov rdx,QWORD PTR [rsi+24]
 mov r8,rbx
 call boom_runtime_type
 cmp DWORD PTR [rbx],0
 jne bmc_error
 test rax,rax
 jz bmc_invalid
 mov rdi,rax
 mov rcx,rax
 mov rdx,QWORD PTR [rsi+32]
 call boom_type_assignable
 test eax,eax
 jz bmc_invalid
 mov rcx,rdi
 mov rdx,QWORD PTR [rsi+40]
 call boom_type_assignable
 test eax,eax
 jnz bmc_unsupported
 xor eax,eax
 jmp bmc_done
bmc_unsupported:
 mov DWORD PTR [rbx],20
 jmp bmc_error
bmc_invalid:
 mov DWORD PTR [rbx],7
bmc_error:
 mov eax,-1
 jmp bmc_done
bmc_detached:
 mov eax,-2
 jmp bmc_done
bmc_version:
 mov eax,-3
bmc_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_builtin_module_check ENDP

; Semantic body of the locked nio OnLoad: test the current attached VM thread
; for its required 1.2 interface, then return the body's version. Internal ABI.
boom_builtin_nio_body PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov r8d,00010002h
 call boom_builtin_module_check
 test eax,eax
 jnz bnb_failed
 mov eax,00010002h
 jmp bnb_done
bnb_failed:
 test rbx,rbx
 jz bnb_version_error
 cmp DWORD PTR [rbx],0
 jne bnb_version_error
 mov DWORD PTR [rbx],20
bnb_version_error:
 mov eax,-3
bnb_done:
 add rsp,32
 pop rbx
 ret
boom_builtin_nio_body ENDP

; The static module wrapper executes the dynamic body before reporting 1.8.
; A failed or unsupported internal adaptation is never published as loaded.
boom_builtin_nio_on_load PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 call boom_builtin_nio_body
 test rbx,rbx
 jz bnl_zero
 cmp DWORD PTR [rbx],0
 jne bnl_zero
 cmp eax,00010002h
 jne bnl_invalid
 mov eax,00010008h
 jmp bnl_done
bnl_invalid:
 mov DWORD PTR [rbx],20
bnl_zero:
 xor eax,eax
bnl_done:
 add rsp,32
 pop rbx
 ret
boom_builtin_nio_on_load ENDP
