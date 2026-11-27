; Original NativeImageBuffer.getNativeMap: lookup only, never open an image.
; JMAP80/1: owner8,SRW16,state24,active28,nodeHead32,nodes40,leases48,
; successful Java buffers56,lookups64,generation72. States cold0/open1/
; draining2/closed3/closing4. Node96: Job64,next64,heap72,leased80,token88.
; No node contains a Java oop. Successful lookup leases outlive all Java users.
; The lifecycle caller must join workers and end all heap/view users before close.
.code
PUBLIC boom_jimage_native_map_open
PUBLIC boom_jimage_native_map_close
PUBLIC boom_jimage_native_map_ready
PUBLIC boom_provider_jimage_native_map_service

; Caller supplies a real, accessible Owner128 allocated for this VM lifetime.
jmap_owner_ready PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz jmr_invalid
 test bl,7
 jnz jmr_invalid
 mov rax,03130474D494A4F42h
 cmp QWORD PTR [rbx],rax
 jne jmr_invalid
 cmp DWORD PTR [rbx+8],128
 jne jmr_invalid
 cmp DWORD PTR [rbx+12],1
 jne jmr_invalid
 cmp DWORD PTR [rbx+28],1
 jb jmr_invalid
 cmp DWORD PTR [rbx+28],1024
 ja jmr_invalid
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rbx+24],1
 mov esi,9
 jne jmr_unlock
 xor esi,esi
jmr_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,esi
 jmp jmr_return
jmr_invalid:
 mov eax,5
jmr_return:
 add rsp,40
 pop rsi
 pop rbx
 ret
jmap_owner_ready ENDP

; Readiness is an internal source-library capability check, never a JNI env.
boom_jimage_native_map_ready PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz jmready_invalid
 cmp DWORD PTR [rbx],050414D4Ah
 jne jmready_invalid
 cmp DWORD PTR [rbx+4],1
 jne jmready_invalid
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rbx+24],1
 jne jmready_closed
 mov rcx,QWORD PTR [rbx+8]
 call jmap_owner_ready
 mov esi,eax
 jmp jmready_unlock
jmready_closed:
 mov esi,9
jmready_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,esi
 jmp jmready_return
jmready_invalid:
 mov eax,5
jmready_return:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_jimage_native_map_ready ENDP

; open(bridge pool, already initialized real owner pool). No mapping is opened.
boom_jimage_native_map_open PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 test rbx,rbx
 jz jmo_argument
 test rsi,rsi
 jz jmo_argument
 cmp DWORD PTR [rbx],050414D4Ah
 jne jmo_argument
 cmp DWORD PTR [rbx+4],1
 jne jmo_argument
 mov rcx,rsi
 call jmap_owner_ready
 test eax,eax
 jnz jmo_return
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rbx+24],1
 jne jmo_cold
 cmp QWORD PTR [rbx+8],rsi
 je jmo_ok
 jmp jmo_busy
jmo_cold:
 cmp DWORD PTR [rbx+24],2
 je jmo_busy
 cmp DWORD PTR [rbx+24],3
 ja jmo_busy
 cmp DWORD PTR [rbx+28],0
 jne jmo_busy
 cmp QWORD PTR [rbx+32],0
 jne jmo_busy
 cmp QWORD PTR [rbx+40],0
 jne jmo_busy
 cmp QWORD PTR [rbx+48],0
 jne jmo_busy
 mov QWORD PTR [rbx+8],rsi
 inc QWORD PTR [rbx+72]
 mov DWORD PTR [rbx+24],1
jmo_ok:
 xor esi,esi
 jmp jmo_unlock
jmo_busy:
 mov esi,2
jmo_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,esi
 jmp jmo_return
jmo_argument:
 mov eax,3
jmo_return:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_jimage_native_map_open ENDP

; Remove exactly one private node. A failed release or HeapFree stays tracked.
; No owner lock is nested inside the bridge lock; no Java executes here.
jmap_drop_node PROC PRIVATE FRAME
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
 xor edi,edi
 cmp DWORD PTR [rsi+80],0
 je jmd_lock
 mov rax,QWORD PTR [rsi+88]
 mov QWORD PTR [rsi+24],rax
 mov QWORD PTR [rsi+8],0
 mov QWORD PTR [rsi+16],0
 mov QWORD PTR [rsi+56],0
 mov rcx,rsi
 call boom_jimage_owner_release
 test eax,eax
 jnz jmd_pending
 mov DWORD PTR [rsi+80],0
 mov QWORD PTR [rsi+88],0
 mov edi,1
jmd_lock:
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 test edi,edi
 jz jmd_find
 dec QWORD PTR [rbx+48]
jmd_find:
 lea rdi,[rbx+32]
jmd_next:
 mov rax,QWORD PTR [rdi]
 test rax,rax
 jz jmd_missing
 cmp rax,rsi
 je jmd_free
 lea rdi,[rax+64]
 jmp jmd_next
jmd_free:
 mov rcx,QWORD PTR [rsi+72]
 xor edx,edx
 mov r8,rsi
 mov rsi,QWORD PTR [rsi+64]
 call HeapFree
 test eax,eax
 jz jmd_missing
 mov QWORD PTR [rdi],rsi
 dec QWORD PTR [rbx+40]
 xor esi,esi
 jmp jmd_unlock
jmd_missing:
 mov esi,12
jmd_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,esi
 jmp jmd_return
jmd_pending:
 mov eax,12
jmd_return:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
jmap_drop_node ENDP

; close(bridge pool): reject active native calls, then drain retained leases.
; An OS/owner cleanup failure leaves draining state and the exact node for retry.
boom_jimage_native_map_close PROC FRAME
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
 test rbx,rbx
 jz jmc_argument
 cmp DWORD PTR [rbx],050414D4Ah
 jne jmc_argument
 cmp DWORD PTR [rbx+4],1
 jne jmc_argument
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rbx+28],0
 jne jmc_busy
 cmp DWORD PTR [rbx+24],3
 je jmc_already_closed
 cmp DWORD PTR [rbx+24],4
 je jmc_busy
 cmp DWORD PTR [rbx+24],2
 ja jmc_bad_locked
 mov DWORD PTR [rbx+24],4
 mov rsi,QWORD PTR [rbx+32]
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 xor edi,edi
jmc_next:
 test rsi,rsi
 jz jmc_drained
 mov rdx,rsi
 mov rsi,QWORD PTR [rsi+64]
 mov rcx,rbx
 call jmap_drop_node
 test eax,eax
 jz jmc_next
 mov edi,12
 jmp jmc_next
jmc_drained:
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 test edi,edi
 jz jmc_check_drained
 mov DWORD PTR [rbx+24],2
 jmp jmc_unlock
jmc_check_drained:
 cmp QWORD PTR [rbx+32],0
 jne jmc_bad_locked
 cmp QWORD PTR [rbx+40],0
 jne jmc_bad_locked
 cmp QWORD PTR [rbx+48],0
 jne jmc_bad_locked
 mov QWORD PTR [rbx+8],0
 mov DWORD PTR [rbx+24],3
jmc_already_closed:
 xor edi,edi
 jmp jmc_unlock
jmc_busy:
 mov edi,2
 jmp jmc_unlock
jmc_bad_locked:
 mov edi,3
jmc_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp jmc_return
jmc_argument:
 mov eax,3
jmc_return:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_jimage_native_map_close ENDP

; Context32, argv{normal String}, bridge pool, operation0.
boom_provider_jimage_native_map_service PROC FRAME
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
 mov r12,rdx
 mov rsi,r8
 xor edi,edi
 xor r15d,r15d
 mov QWORD PTR [rsp+80],0
 test rbx,rbx
 jz jms_return
 cmp DWORD PTR [rbx],0
 jne jms_return
 test r9d,r9d
 jnz jms_bad
 test r12,r12
 jz jms_bad
 test rsi,rsi
 jz jms_bad
 cmp DWORD PTR [rsi],050414D4Ah
 jne jms_bad
 cmp DWORD PTR [rsi+4],1
 jne jms_bad
 lea rcx,[rsi+16]
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rsi+24],1
 jne jms_locked_closed
 cmp QWORD PTR [rsi+8],0
 je jms_locked_closed
 cmp DWORD PTR [rsi+28],-1
 je jms_locked_closed
 inc DWORD PTR [rsi+28]
 mov edi,1
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 mov rdx,QWORD PTR [r12]
 test rdx,rdx
 jz jms_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 call boom_heap_contains
 test eax,eax
 jz jms_bad
 mov rcx,QWORD PTR [r12]
 lea rdx,JMAP_STRING_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jms_finish
 mov rcx,rbx
 mov rdx,r12
 call JMAP_STRING_CHARS
 cmp DWORD PTR [rbx],0
 jne jms_finish
 mov r13,rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rax
 call boom_heap_contains
 test eax,eax
 jz jms_bad
 cmp QWORD PTR [r13-8],261
 jne jms_bad
 cmp DWORD PTR [r13-20],0
 jne jms_bad
 mov r14,QWORD PTR [r13-16]
 test r14b,1
 jnz jms_bad
 shr r14,1
 ; No real Win32 owner key can be empty, contain NUL, or exceed 32767
 ; units. These valid Java queries are proven misses, not owner errors.
 test r14,r14
 jz jms_finish
 cmp r14,32767
 ja jms_finish
 xor ecx,ecx
jms_NUL_scan:
 cmp rcx,r14
 jae jms_allocate
 cmp WORD PTR [r13+rcx*2],0
 je jms_finish
 inc rcx
 jmp jms_NUL_scan
jms_allocate:
 call GetProcessHeap
 test rax,rax
 jz jms_oom
 mov QWORD PTR [rsp+72],rax
 mov rcx,rax
 mov edx,8
 mov r8d,96
 call HeapAlloc
 test rax,rax
 jz jms_oom
 mov r15,rax
 mov rax,QWORD PTR [rsp+72]
 mov QWORD PTR [r15+72],rax
 mov rax,QWORD PTR [rsi+8]
 mov QWORD PTR [r15],rax
 mov QWORD PTR [r15+8],r13
 mov DWORD PTR [r15+16],r14d
 lea rcx,[rsi+16]
 call AcquireSRWLockExclusive
 mov rax,QWORD PTR [rsi+32]
 mov QWORD PTR [r15+64],rax
 mov QWORD PTR [rsi+32],r15
 inc QWORD PTR [rsi+40]
 inc QWORD PTR [rsi+64]
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 mov rcx,r15
 call boom_jimage_owner_lookup
 mov QWORD PTR [r15+8],0
 mov QWORD PTR [r15+16],0
 cmp eax,1
 je jms_drop
 test eax,eax
 jnz jms_owner_failure
 mov rax,QWORD PTR [r15+24]
 mov QWORD PTR [r15+88],rax
 mov DWORD PTR [r15+80],1
 lea rcx,[rsi+16]
 call AcquireSRWLockExclusive
 inc QWORD PTR [rsi+48]
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 cmp QWORD PTR [r15+24],0
 je jms_bad
 cmp QWORD PTR [r15+32],0
 je jms_bad
 cmp QWORD PTR [r15+40],0
 je jms_bad
 lea rcx,JMAP_DIRECT_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne jms_drop
 mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,JMAP_DIRECT_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz jms_drop
 mov QWORD PTR [rsp+40],rax
 mov rax,QWORD PTR [r15+32]
 mov QWORD PTR [rsp+48],rax
 mov rax,QWORD PTR [r15+40]
 mov QWORD PTR [rsp+56],rax
 mov rcx,rbx
 lea rdx,[rsp+40]
 call JMAP_DIRECT_CTOR
 cmp DWORD PTR [rbx],0
 jne jms_drop
 mov rax,QWORD PTR [rsp+40]
 mov QWORD PTR [rsp+80],rax
 lock inc QWORD PTR [rsi+56]
 xor r15d,r15d
 jmp jms_finish
jms_owner_failure:
 mov DWORD PTR [rbx],20
 jmp jms_drop
jms_locked_closed:
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 jmp jms_unsupported
jms_null:
 mov DWORD PTR [rbx],4
 jmp jms_drop
jms_bad:
 mov DWORD PTR [rbx],7
 jmp jms_drop
jms_oom:
 mov DWORD PTR [rbx],3
 jmp jms_drop
jms_unsupported:
 mov DWORD PTR [rbx],20
jms_drop:
 test r15,r15
 jz jms_finish
 mov rcx,rsi
 mov rdx,r15
 call jmap_drop_node
 test eax,eax
 jz jms_finish
 cmp DWORD PTR [rbx],0
 jne jms_finish
 mov DWORD PTR [rbx],20
jms_finish:
 test edi,edi
 jz jms_return
 lea rcx,[rsi+16]
 call AcquireSRWLockExclusive
 dec DWORD PTR [rsi+28]
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
jms_return:
 mov rax,QWORD PTR [rsp+80]
 add rsp,96
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_jimage_native_map_service ENDP
