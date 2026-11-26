; Restricted source-native builtin library lifecycle. No external JNI loading.
; NLIB32/1: count8=2,stride12=64,rows16,SRW24.
; Module64/1: magic0,abi4,kind8,refs12,real HMODULE16,version24,state28,
; internal load32,internal close40,resource owner48,loading OS thread56,reserved60.
; States: cold0,ready1,failed-owned2,transition3. Java callbacks run unlocked.
; The VM retains its base image reference until all module pins are released.
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN GetCurrentThreadId:PROC
EXTERN GetModuleHandleExW:PROC
EXTERN FreeLibrary:PROC
EXTERN GetLastError:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
PUBLIC boom_native_library_service
.code

; Normal String -> known module kind. R8D is the required ASCII C-string
; length (7 for a mapped name, 3 for a builtin basename). Embedded NUL follows
; the locked platform-char API; non-ASCII conversion is an explicit boundary.
lib_source_name PROC PRIVATE FRAME
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
 mov rdi,rdx
 mov r12d,r8d
 test rdi,rdi
 jz lsn_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 call boom_heap_contains
 test eax,eax
 jz lsn_bad
 mov rcx,rdi
 lea rdx,NLL_STRING_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz lsn_zero
 mov QWORD PTR [rsp+32],rdi
 mov rcx,rbx
 lea rdx,[rsp+32]
 call NLL_STRING_CHARS
 cmp DWORD PTR [rbx],0
 jne lsn_zero
 mov rsi,rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rax
 call boom_heap_contains
 test eax,eax
 jz lsn_bad
 cmp QWORD PTR [rsi-8],261
 jne lsn_bad
 cmp DWORD PTR [rsi-20],0
 jne lsn_bad
 mov rdi,QWORD PTR [rsi-16]
 shr rdi,1
 xor ecx,ecx
lsn_scan:
 cmp rcx,rdi
 jae lsn_length
 movzx edx,WORD PTR [rsi+rcx*2]
 test edx,edx
 jz lsn_length
 cmp edx,127
 ja lsn_unsupported
 inc rcx
 jmp lsn_scan
lsn_length:
 cmp rcx,r12
 jne lsn_zero
 cmp WORD PTR [rsi],110
 jne lsn_zero
 cmp WORD PTR [rsi+2],101
 je lsn_net
 cmp WORD PTR [rsi+2],105
 jne lsn_zero
 cmp WORD PTR [rsi+4],111
 jne lsn_zero
 mov eax,2
 jmp lsn_done
lsn_net:
 cmp WORD PTR [rsi+4],116
 jne lsn_zero
 mov eax,1
 jmp lsn_done
lsn_unsupported:
 mov DWORD PTR [rbx],20
 jmp lsn_zero
lsn_null:
 mov DWORD PTR [rbx],4
 jmp lsn_zero
lsn_bad:
 mov DWORD PTR [rbx],7
lsn_zero:
 xor eax,eax
lsn_done:
 add rsp,56
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
lib_source_name ENDP

; Close the resource owner before releasing our actual OS image pin. This
; callback ABI never consumes a Context or exposes a standard JNI pointer.
; The caller has reserved transition3, but holds no lock during this call.
lib_close_module PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 xor ecx,ecx
 mov rdx,rbx
 call QWORD PTR [rbx+40]
 test eax,eax
 jnz lcm_done
 mov rcx,QWORD PTR [rbx+16]
 test rcx,rcx
 jz lcm_clear
 call FreeLibrary
 test eax,eax
 jnz lcm_clear
 call GetLastError
 test eax,eax
 jnz lcm_done
 mov eax,31
 jmp lcm_done
lcm_clear:
 cmp QWORD PTR [rbx+16],0
 je lcm_clear_fields
 lock dec QWORD PTR [boom_native_library_pins]
lcm_clear_fields:
 mov QWORD PTR [rbx+16],0
 mov DWORD PTR [rbx+24],0
 mov DWORD PTR [rbx+12],0
 xor eax,eax
lcm_done:
 add rsp,32
 pop rbx
 ret
lib_close_module ENDP

; Source adapters supply exact native frames, source layouts/field offsets,
; source Java callbacks, typed exception materializers and immutable descriptors.
; 0 findBuiltinLib, 1 load, 2 unload, 3 findEntry0.
boom_native_library_service PROC FRAME
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
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,96
 .allocstack 96
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov r12d,r9d
 xor r15d,r15d
 test rbx,rbx
 jz nll_done
 cmp DWORD PTR [rbx],0
 jne nll_done
 test rsi,rsi
 jz nll_bad
 test rdi,rdi
 jz nll_bad
 cmp DWORD PTR [rdi],042494C4Eh
 jne nll_bad
 cmp DWORD PTR [rdi+4],1
 jne nll_bad
 cmp DWORD PTR [rdi+8],2
 jne nll_bad
 cmp DWORD PTR [rdi+12],64
 jne nll_bad
 cmp QWORD PTR [rdi+16],0
 je nll_bad
 cmp r12d,3
 ja nll_bad
 test r12d,r12d
 jz nll_find_builtin
 cmp r12d,3
 je nll_find_entry
 cmp r12d,2
 je nll_unload_name
 cmp QWORD PTR [rsi+16],1
 jne nll_unsupported
 cmp QWORD PTR [rsi+24],1
 ja nll_bad
 lea rcx,NLL_IMPL_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne nll_done
 mov r14,QWORD PTR [rsi]
 test r14,r14
 jz nll_null_receiver
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz nll_bad
 mov rcx,r14
 lea rdx,NLL_IMPL_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz nll_done
 mov rdx,QWORD PTR [rsi+8]
 jmp nll_name
nll_unload_name:
 cmp QWORD PTR [rsi+8],1
 jne nll_unsupported
 mov rdx,QWORD PTR [rsi]
nll_name:
 mov rcx,rbx
 mov r8d,3
 call lib_source_name
 cmp DWORD PTR [rbx],0
 jne nll_done
 test eax,eax
 jz nll_unsupported
 dec eax
 shl eax,6
 mov r13,QWORD PTR [rdi+16]
 add r13,rax
 cmp DWORD PTR [r13],0444F4D42h
 jne nll_bad
 cmp DWORD PTR [r13+4],1
 jne nll_bad
 cmp QWORD PTR [r13+32],0
 je nll_bad
 cmp QWORD PTR [r13+40],0
 je nll_bad
 cmp r12d,2
 je nll_owner
 mov rcx,rbx
 lea rdx,boom_builtin_module_pool
 mov r8d,00010002h
 call boom_builtin_module_check
 test eax,eax
 jnz nll_unsupported_if_clear
nll_owner:
 call GetCurrentThreadId
 mov DWORD PTR [rsp+48],eax
nll_lock:
 lea rcx,[rdi+24]
 call AcquireSRWLockExclusive
 cmp DWORD PTR [r13+28],3
 jne nll_locked
 mov eax,DWORD PTR [rsp+48]
 cmp DWORD PTR [r13+56],eax
 je nll_unlock_unsupported
 lea rcx,[rdi+24]
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rsp+32],3
 lea rcx,[r13+28]
 lea rdx,[rsp+32]
 mov r8d,4
 mov r9d,-1
 call WaitOnAddress
 test eax,eax
 jz nll_unsupported
 jmp nll_lock
nll_locked:
 cmp r12d,2
 je nll_unload_locked
 cmp QWORD PTR [r14+NLL_HANDLE_OFFSET],0
 jne nll_unlock_unsupported
 cmp DWORD PTR [r14+NLL_VERSION_OFFSET],0
 jne nll_unlock_unsupported
 cmp DWORD PTR [r13+28],0
 je nll_load_cold
 cmp DWORD PTR [r13+28],1
 jne nll_unlock_unsupported
 cmp DWORD PTR [r13+24],00010008h
 jne nll_unlock_unsupported
 cmp QWORD PTR [r13+16],0
 je nll_unlock_unsupported
 cmp DWORD PTR [r13+12],-1
 je nll_unlock_unsupported
 inc DWORD PTR [r13+12]
 jmp nll_publish
nll_load_cold:
 cmp QWORD PTR [r13+16],0
 jne nll_unlock_unsupported
 cmp DWORD PTR [r13+12],0
 jne nll_unlock_unsupported
 mov DWORD PTR [r13+28],3
 mov eax,DWORD PTR [rsp+48]
 mov DWORD PTR [r13+56],eax
 lea rcx,[rdi+24]
 call ReleaseSRWLockExclusive
 mov ecx,4
 mov rdx,QWORD PTR [r13+32]
 lea r8,[rsp+40]
 call GetModuleHandleExW
 test eax,eax
 jz nll_pin_failed
 mov rax,QWORD PTR [rsp+40]
 mov QWORD PTR [r13+16],rax
 lock inc QWORD PTR [boom_native_library_pins]
 mov rcx,rbx
 mov rdx,r13
 lock inc QWORD PTR [boom_native_library_load_callbacks]
 call QWORD PTR [r13+32]
 mov DWORD PTR [rsp+56],eax
 cmp DWORD PTR [rbx],0
 jne nll_load_failed
 cmp eax,00010008h
 jne nll_bad_version
 lea rcx,[rdi+24]
 call AcquireSRWLockExclusive
 cmp QWORD PTR [r14+NLL_HANDLE_OFFSET],0
 jne nll_conflicting_receiver
 cmp DWORD PTR [r14+NLL_VERSION_OFFSET],0
 jne nll_conflicting_receiver
 mov DWORD PTR [r13+12],1
 mov DWORD PTR [r13+24],00010008h
 mov DWORD PTR [r13+28],1
 mov DWORD PTR [r13+56],0
nll_publish:
 mov eax,DWORD PTR [r13+24]
 mov DWORD PTR [r14+NLL_VERSION_OFFSET],eax
 mov rax,QWORD PTR [r13+16]
 mov QWORD PTR [r14+NLL_HANDLE_OFFSET],rax
 mov r15d,1
 jmp nll_unlock_wake
nll_conflicting_receiver:
 lea rcx,[rdi+24]
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rbx],20
 jmp nll_load_failed
nll_bad_version:
 mov rcx,rbx
 mov edx,DWORD PTR [rsp+56]
 mov r8d,DWORD PTR [r13+8]
 call lib_raise_bad_version
 jmp nll_load_failed
nll_pin_failed:
 mov DWORD PTR [rbx],20
 mov DWORD PTR [rsp+56],0
 jmp nll_failed_state
nll_load_failed:
 mov rcx,r13
 call lib_close_module
 mov DWORD PTR [rsp+56],eax
nll_failed_state:
 lea rcx,[rdi+24]
 call AcquireSRWLockExclusive
 mov DWORD PTR [r13+12],0
 mov DWORD PTR [r13+24],0
 mov DWORD PTR [r13+28],0
 cmp DWORD PTR [rsp+56],0
 je nll_failure_published
 mov DWORD PTR [r13+28],2
nll_failure_published:
 mov DWORD PTR [r13+56],0
 jmp nll_unlock_wake
nll_unload_locked:
 mov rax,QWORD PTR [rsi+16]
 test rax,rax
 jz nll_unlock_bad
 cmp QWORD PTR [r13+16],rax
 jne nll_unlock_bad
 mov eax,DWORD PTR [r13+28]
 mov DWORD PTR [rsp+52],eax
 cmp eax,2
 je nll_close_reserved
 cmp eax,1
 jne nll_unlock_bad
 cmp DWORD PTR [r13+12],1
 jb nll_unlock_bad
 je nll_close_reserved
 dec DWORD PTR [r13+12]
 jmp nll_unlock_wake
nll_close_reserved:
 mov DWORD PTR [r13+28],3
 mov eax,DWORD PTR [rsp+48]
 mov DWORD PTR [r13+56],eax
 lea rcx,[rdi+24]
 call ReleaseSRWLockExclusive
 mov rcx,r13
 call lib_close_module
 mov DWORD PTR [rsp+56],eax
 lea rcx,[rdi+24]
 call AcquireSRWLockExclusive
 mov DWORD PTR [r13+28],0
 cmp DWORD PTR [rsp+56],0
 je nll_close_published
 mov DWORD PTR [r13+28],2
 cmp DWORD PTR [rsp+56],170
 jne nll_close_error
 cmp DWORD PTR [rsp+52],1
 jne nll_close_error
 mov DWORD PTR [r13+28],1
 jmp nll_close_error_context
nll_close_error:
 mov DWORD PTR [r13+12],0
 mov DWORD PTR [r13+24],0
nll_close_error_context:
 mov DWORD PTR [rbx],20
nll_close_published:
 mov DWORD PTR [r13+56],0
 jmp nll_unlock_wake
nll_find_builtin:
 cmp QWORD PTR [rsi],0
 je nll_null_find
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi]
 mov r8d,7
 call lib_source_name
 cmp DWORD PTR [rbx],0
 jne nll_done
 test eax,eax
 jz nll_done
 mov r8d,eax
 mov rcx,rbx
 call lib_new_module_name
 mov r15,rax
 jmp nll_done
nll_null_find:
 mov rcx,rbx
 call lib_raise_null_filename
 jmp nll_done
nll_find_entry:
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+8]
 mov r8d,3
 call lib_source_name
 cmp DWORD PTR [rbx],0
 jne nll_done
 lea rcx,[rdi+24]
 call AcquireSRWLockExclusive
 mov r13,QWORD PTR [rdi+16]
 mov rax,QWORD PTR [rsi]
 test rax,rax
 jz nll_unlock_bad
 mov ecx,2
nll_find_handle:
 cmp DWORD PTR [r13+28],1
 jne nll_next_handle
 cmp QWORD PTR [r13+16],rax
 je nll_unlock_unsupported
nll_next_handle:
 add r13,64
 dec ecx
 jnz nll_find_handle
 jmp nll_unlock_bad
nll_unlock_bad:
 mov DWORD PTR [rbx],7
 jmp nll_unlock
nll_unlock_unsupported:
 mov DWORD PTR [rbx],20
nll_unlock:
 lea rcx,[rdi+24]
 call ReleaseSRWLockExclusive
 jmp nll_done
nll_unlock_wake:
 lea rcx,[rdi+24]
 call ReleaseSRWLockExclusive
 lea rcx,[r13+28]
 call WakeByAddressAll
 jmp nll_done
nll_bad:
 mov DWORD PTR [rbx],7
 jmp nll_done
nll_null_receiver:
 mov DWORD PTR [rbx],4
 jmp nll_done
nll_unsupported_if_clear:
 cmp DWORD PTR [rbx],0
 jne nll_done
nll_unsupported:
 mov DWORD PTR [rbx],20
nll_done:
 mov rax,r15
 add rsp,96
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_native_library_service ENDP
