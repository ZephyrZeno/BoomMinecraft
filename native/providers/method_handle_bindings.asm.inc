; MHRG128/1 native binding table publication. All pointers name immutable
; source-derived metadata or native image-owned writable publication cells.
; This does not initialize Java classes or claim unsupported native semantics.
.code
boom_mhn_validate_bindings PROC PRIVATE
 ; RCX exact pool. Volatile registers only. No lock, Java, or OS calls.
 cmp DWORD PTR [rcx],04752484Dh
 jne mhrv_bad
 cmp DWORD PTR [rcx+4],1
 jne mhrv_bad
 cmp DWORD PTR [rcx+8],128
 jne mhrv_bad
 cmp DWORD PTR [rcx+12],1
 ja mhrv_bad
 mov r9d,DWORD PTR [rcx+48]
 test r9d,r9d
 jz mhrv_bad
 cmp r9d,64
 ja mhrv_bad
 cmp r9d,DWORD PTR [rcx+52]
 jne mhrv_bad
 cmp r9d,MHRG_NATIVE_COUNT
 jne mhrv_bad
 cmp DWORD PTR [rcx+64],3
 jne mhrv_bad
 cmp DWORD PTR [rcx+68],64
 jne mhrv_bad
 mov rax,QWORD PTR [rcx+72]
 or rax,QWORD PTR [rcx+80]
 or rax,QWORD PTR [rcx+88]
 or rax,QWORD PTR [rcx+96]
 or rax,QWORD PTR [rcx+104]
 or rax,QWORD PTR [rcx+112]
 or rax,QWORD PTR [rcx+120]
 jnz mhrv_bad
 lea rax,boom_mhn_bindings_input_rows
 cmp QWORD PTR [rcx+24],rax
 jne mhrv_bad
 lea rax,boom_mhn_bindings_expected_rows
 cmp QWORD PTR [rcx+32],rax
 jne mhrv_bad
 lea rax,boom_mhn_bindings_cells
 cmp QWORD PTR [rcx+40],rax
 jne mhrv_bad
 mov r10,QWORD PTR [rcx+56]
 lea rax,boom_trace_pool
 cmp r10,rax
 jne mhrv_bad
 cmp DWORD PTR [r10],05452504Ch
 jne mhrv_bad
 cmp DWORD PTR [r10+4],3
 jne mhrv_bad
 mov eax,DWORD PTR [r10+16]
 dec eax
 cmp eax,0FFFFFh
 ja mhrv_bad
 cmp DWORD PTR [r10+20],0
 jne mhrv_bad
 cmp QWORD PTR [r10+24],0
 je mhrv_bad
 cmp QWORD PTR [r10+40],0
 jne mhrv_bad
 mov rdx,QWORD PTR [rcx+24]
 mov r8,QWORD PTR [rcx+32]
 test rdx,rdx
 jz mhrv_bad
 test r8,r8
 jz mhrv_bad
 xor r11d,r11d
mhrv_row:
 ; Exact row equality protects all original IDs, function/Frame/name/signature
 ; pointers, support status and string lengths against coherent table edits.
 mov rax,QWORD PTR [rdx]
 cmp rax,QWORD PTR [r8]
 jne mhrv_bad
 mov rax,QWORD PTR [rdx+8]
 cmp rax,QWORD PTR [r8+8]
 jne mhrv_bad
 mov rax,QWORD PTR [rdx+16]
 cmp rax,QWORD PTR [r8+16]
 jne mhrv_bad
 mov rax,QWORD PTR [rdx+24]
 cmp rax,QWORD PTR [r8+24]
 jne mhrv_bad
 mov rax,QWORD PTR [rdx+32]
 cmp rax,QWORD PTR [r8+32]
 jne mhrv_bad
 mov rax,QWORD PTR [rdx+40]
 cmp rax,QWORD PTR [r8+40]
 jne mhrv_bad
 mov rax,QWORD PTR [rdx+48]
 cmp rax,QWORD PTR [r8+48]
 jne mhrv_bad
 mov rax,QWORD PTR [rdx+56]
 cmp rax,QWORD PTR [r8+56]
 jne mhrv_bad
 lea eax,[r11+1]
 cmp DWORD PTR [rdx+8],eax
 jne mhrv_bad
 cmp DWORD PTR [rdx+12],1
 ja mhrv_bad
 cmp QWORD PTR [rdx+16],0
 je mhrv_bad
 cmp QWORD PTR [rdx+24],0
 je mhrv_bad
 cmp QWORD PTR [rdx+40],0
 je mhrv_bad
 cmp QWORD PTR [rdx+48],0
 je mhrv_bad
 cmp DWORD PTR [rdx+56],0
 je mhrv_bad
 cmp DWORD PTR [rdx+60],0
 je mhrv_bad
 ; Frame32 must be the actual indexed row in this image's normal Frame pool.
 mov rax,QWORD PTR [rdx+32]
 test rax,rax
 jz mhrv_bad
 sub rax,QWORD PTR [r10+24]
 jc mhrv_bad
 test eax,31
 jnz mhrv_bad
 shr rax,5
 cmp eax,DWORD PTR [r10+16]
 jae mhrv_bad
 mov rax,QWORD PTR [rdx+32]
 mov ecx,DWORD PTR [rdx]
 cmp DWORD PTR [rax],ecx
 jne mhrv_bad
 test DWORD PTR [rax+4],32
 jz mhrv_bad
 test DWORD PTR [rax+4],0FFFFFF80h
 jnz mhrv_bad
 cmp DWORD PTR [rax+16],0
 jne mhrv_bad
 mov ecx,DWORD PTR [rdx+4]
 cmp DWORD PTR [rax+20],ecx
 jne mhrv_bad
 cmp QWORD PTR [rax+24],0
 jne mhrv_bad
 mov rax,QWORD PTR [rax+8]
 test rax,rax
 jz mhrv_bad
 cmp DWORD PTR [rax],054595045h
 jne mhrv_bad
 cmp DWORD PTR [rax+4],1
 jne mhrv_bad
 cmp DWORD PTR [rax+8],1
 jne mhrv_bad
 add rdx,64
 add r8,64
 inc r11d
 cmp r11d,r9d
 jb mhrv_row
 mov eax,1
 ret
mhrv_bad:
 xor eax,eax
 ret
boom_mhn_validate_bindings ENDP

PUBLIC boom_mhn_bindings_register
boom_mhn_bindings_register PROC FRAME
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
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 test rbx,rbx
 jz mhrr_invalid
 cmp DWORD PTR [rbx],0
 jne mhrr_preserve
 cmp QWORD PTR [rbx+16],0
 jne mhrr_preserve
 lea rax,boom_mhn_bindings_pool
 cmp rsi,rax
 jne mhrr_bad
 lea rcx,[rsi+16]
 call AcquireSRWLockExclusive
 mov rcx,rsi
 call boom_mhn_validate_bindings
 test eax,eax
 jz mhrr_bad_locked
 mov rdi,QWORD PTR [rsi+32]
 mov r12,QWORD PTR [rsi+40]
 mov r13d,DWORD PTR [rsi+48]
 xor ecx,ecx
 cmp DWORD PTR [rsi+12],1
 je mhrr_repeat
 ; Check the entire cold bank before publishing even the first pointer.
 mov rdx,r12
mhrr_cold:
 mov rax,QWORD PTR [rdx]
 or rax,QWORD PTR [rdx+8]
 or rax,QWORD PTR [rdx+16]
 jnz mhrr_bad_locked
 add rdx,24
 inc ecx
 cmp ecx,r13d
 jb mhrr_cold
 xor ecx,ecx
mhrr_publish:
 mov rax,QWORD PTR [rdi+16]
 mov QWORD PTR [r12],rax
 mov rax,QWORD PTR [rdi+24]
 mov QWORD PTR [r12+8],rax
 mov eax,DWORD PTR [rdi+12]
 mov DWORD PTR [r12+16],eax
 mov DWORD PTR [r12+20],0
 add rdi,64
 add r12,24
 inc ecx
 cmp ecx,r13d
 jb mhrr_publish
 mov DWORD PTR [rsi+12],1
 jmp mhrr_success_locked
mhrr_repeat:
 mov rax,QWORD PTR [rdi+16]
 cmp QWORD PTR [r12],rax
 jne mhrr_bad_locked
 mov rax,QWORD PTR [rdi+24]
 cmp QWORD PTR [r12+8],rax
 jne mhrr_bad_locked
 mov eax,DWORD PTR [rdi+12]
 cmp DWORD PTR [r12+16],eax
 jne mhrr_bad_locked
 cmp DWORD PTR [r12+20],0
 jne mhrr_bad_locked
 add rdi,64
 add r12,24
 inc ecx
 cmp ecx,r13d
 jb mhrr_repeat
mhrr_success_locked:
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
mhrr_preserve:
 xor eax,eax
 jmp mhrr_done
mhrr_bad_locked:
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
mhrr_bad:
 mov DWORD PTR [rbx],7
mhrr_invalid:
 mov eax,87
mhrr_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_mhn_bindings_register ENDP

PUBLIC boom_mhn_unsupported
boom_mhn_unsupported PROC
 test rcx,rcx
 jz mhru_done
 cmp DWORD PTR [rcx],0
 jne mhru_done
 cmp QWORD PTR [rcx+16],0
 jne mhru_done
 mov DWORD PTR [rcx],20
mhru_done:
 xor eax,eax
 ret
boom_mhn_unsupported ENDP

PUBLIC boom_mhn_bindings_service
boom_mhn_bindings_service PROC FRAME
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
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov rsi,r8
 mov r13d,r9d
 test rbx,rbx
 jz mhrs_zero
 cmp DWORD PTR [rbx],0
 jne mhrs_zero
 cmp QWORD PTR [rbx+16],0
 jne mhrs_zero
 lea rax,boom_mhn_bindings_pool
 cmp rsi,rax
 jne mhrs_bad
 test r13d,r13d
 jnz mhrs_dispatch
 mov rcx,rbx
 mov rdx,rsi
 call boom_mhn_bindings_register
 jmp mhrs_done
mhrs_dispatch:
 lea rcx,[rsi+16]
 call AcquireSRWLockShared
 cmp DWORD PTR [rsi+12],1
 jne mhrs_unbound_locked
 dec r13d
 cmp r13d,DWORD PTR [rsi+48]
 jae mhrs_bad_locked
 mov eax,r13d
 imul rax,rax,24
 add rax,QWORD PTR [rsi+40]
 mov edi,r13d
 shl rdi,6
 add rdi,QWORD PTR [rsi+32]
 mov rdx,QWORD PTR [rdi+16]
 cmp QWORD PTR [rax],rdx
 jne mhrs_bad_locked
 mov rdx,QWORD PTR [rdi+24]
 cmp QWORD PTR [rax+8],rdx
 jne mhrs_bad_locked
 mov ecx,DWORD PTR [rdi+12]
 cmp DWORD PTR [rax+16],ecx
 jne mhrs_bad_locked
 cmp DWORD PTR [rax+20],0
 jne mhrs_bad_locked
 mov rdi,rdx
 lea rcx,[rsi+16]
 call ReleaseSRWLockShared
 ; No native table lock is held across the real delegated native operation.
 mov rcx,rbx
 mov rdx,r12
 call rdi
 jmp mhrs_done
mhrs_unbound_locked:
 lea rcx,[rsi+16]
 call ReleaseSRWLockShared
 mov rcx,rbx
 call boom_mhn_unsupported
 jmp mhrs_done
mhrs_bad_locked:
 lea rcx,[rsi+16]
 call ReleaseSRWLockShared
mhrs_bad:
 mov DWORD PTR [rbx],7
mhrs_zero:
 xor eax,eax
mhrs_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_mhn_bindings_service ENDP
