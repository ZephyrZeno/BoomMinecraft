; Unregistered original Inflater native subset, Context32/argv/pool/operation.
; INFL128/1: heapCell8,lifeSRW16,list24,live32,alloc40,free48,generation56,
; IDsready64,inputFMAP72,outputFMAP80,StringFactory88,closed96,ownedBytes104.
; Node34608: next0,token8,SRW16,nowrap24D,reserved28D,OSheap32,reserved40,
; unchanged raw34304 or zlib34560 state at48. No persistent managed oop.
IF_NODE_BYTES EQU 34608
IF_STATE_OFFSET EQU 48
.const
if_bad_data WORD 73,110,118,97,108,105,100,32,99,111,109,112,114,101,115,115,101,100,32,100,97,116,97
if_alloc_error WORD 73,110,102,108,97,116,101,114,32,97,108,108,111,99,97,116,105,111,110,32,102,97,105,108,101,100
if_state_error WORD 73,110,102,108,97,116,101,114,32,110,97,116,105,118,101,32,115,116,97,116,101,32,102,97,105,108,117,114,101
.code

; Materialize through original String factory + error(String) Java Code.
; All native lifetime/node locks MUST already be released. RCX ctx,RDX pool,
; R8D kind0 DataFormat/1 OOME/2 InternalError. Preserve pending Java failures.
boom_inflater_throw PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push rbp
 .pushreg rbp
 push r12
 .pushreg r12
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov r12d,r8d
 cmp r12d,2
 ja if_throw_done
 lea r8,if_bad_data
 mov r9d,23
 test r12d,r12d
 jz if_throw_message
 lea r8,if_alloc_error
 mov r9d,26
 cmp r12d,1
 je if_throw_message
 lea r8,if_state_error
 mov r9d,29
if_throw_message:
 mov rdx,QWORD PTR [rsi+88]
 call boom_java_property_copy
 test rax,rax
 jz if_throw_done
 mov QWORD PTR [rsp+40],rax
 imul edi,r12d,24
 lea rbp,boom_inflater_errors
 add rbp,rdi
 mov rcx,QWORD PTR [rbp]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne if_throw_done
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rbp+8]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz if_throw_done
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rbp+16]
 cmp DWORD PTR [rbx],0
 jne if_throw_done
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+32]
 lea r8,boom_runtime_type_map
 lea r9,IF_THROWABLE_TYPE
 call boom_exception_set32
if_throw_done:
 add rsp,64
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
boom_inflater_throw ENDP

; Owning service registers: RSI pool,R13 node, both locks currently held.
boom_inflater_unlock PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 lea rcx,[r13+16]
 call ReleaseSRWLockExclusive
 lea rcx,[rsi+16]
 call ReleaseSRWLockShared
 add rsp,40
 ret
boom_inflater_unlock ENDP

PUBLIC boom_provider_inflater_service
boom_provider_inflater_service PROC FRAME
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
 sub rsp,280
 .allocstack 280
 .endprolog
 mov rbx,rcx
 mov rdi,rdx
 mov rsi,r8
 mov r12d,r9d
 xor r15d,r15d
 test rbx,rbx
 jz if_service_done
 cmp DWORD PTR [rbx],0
 jne if_service_done
 test rsi,rsi
 jz if_service_bad
 cmp DWORD PTR [rsi],04C464E49h
 jne if_service_bad
 cmp DWORD PTR [rsi+4],1
 jne if_service_bad
 cmp QWORD PTR [rsi+8],0
 je if_service_bad
 cmp QWORD PTR [rsi+72],0
 je if_service_bad
 cmp QWORD PTR [rsi+80],0
 je if_service_bad
 cmp QWORD PTR [rsi+88],0
 je if_service_bad
 cmp r12d,10
 ja if_service_bad
 cmp r12d,5
 ja if_service_unsupported
 test r12d,r12d
 jz if_service_ids
 cmp QWORD PTR [rsi+64],2
 jne if_service_bad
 test rdi,rdi
 jz if_service_bad
 cmp r12d,1
 je if_service_init
 cmp r12d,5
 je if_service_arrays
 mov r14,QWORD PTR [rdi]
 cmp r12d,4
 je if_service_end
 jmp if_service_lookup
if_service_ids:
 mov eax,2
 xchg QWORD PTR [rsi+64],rax
 test rax,rax
 jz if_service_done
 cmp rax,2
 je if_service_done
 jmp if_service_bad

if_service_init:
 cmp DWORD PTR [rdi],1
 ja if_service_bad
 call GetProcessHeap
 test rax,rax
 jz if_service_oom
 mov rbp,rax
 mov rcx,rax
 mov edx,8
 mov r8d,IF_NODE_BYTES
 call HeapAlloc
 test rax,rax
 jz if_service_oom
 mov r13,rax
 mov QWORD PTR [r13+32],rbp
 mov eax,DWORD PTR [rdi]
 mov DWORD PTR [r13+24],eax
 lea rcx,[r13+IF_STATE_OFFSET]
 test eax,eax
 jz if_init_zlib
 mov edx,34304
 call boom_deflate_stream_reset
 jmp if_init_ready
if_init_zlib:
 mov edx,34560
 call boom_zlib_stream_reset
if_init_ready:
 test eax,eax
 jnz if_init_free_internal
 lea rcx,[rsi+16]
 call AcquireSRWLockExclusive
 cmp QWORD PTR [rsi+96],0
 jne if_init_closed
 cmp QWORD PTR [rsi+56],-1
 je if_init_exhausted
 inc QWORD PTR [rsi+56]
 mov r15,QWORD PTR [rsi+56]
 mov QWORD PTR [r13+8],r15
 mov rax,QWORD PTR [rsi+24]
 mov QWORD PTR [r13],rax
 mov QWORD PTR [rsi+24],r13
 inc QWORD PTR [rsi+32]
 inc QWORD PTR [rsi+40]
 add QWORD PTR [rsi+104],IF_NODE_BYTES
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 jmp if_service_done
if_init_closed:
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 mov rcx,rbp
 xor edx,edx
 mov r8,r13
 call HeapFree
 jmp if_service_unsupported
if_init_exhausted:
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
if_init_free_internal:
 mov rcx,rbp
 xor edx,edx
 mov r8,r13
 call HeapFree
 jmp if_service_internal

if_service_arrays:
 ; Original private argv: this,addr,in,off,len,out,off,len. The two FMAPs
 ; validate normal receiver types, including any represented descendants.
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi]
 call boom_heap_contains
 test eax,eax
 jz if_service_bad
 mov rcx,QWORD PTR [rdi]
 mov rdx,rbx
 call IF_INPUT_MAP
 test rax,rax
 jz if_service_done
 mov QWORD PTR [rsp+152],rax
 mov rcx,QWORD PTR [rdi]
 mov rdx,rbx
 call IF_OUTPUT_MAP
 test rax,rax
 jz if_service_done
 mov QWORD PTR [rsp+160],rax
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+16]
 call boom_heap_contains
 test eax,eax
 jz if_service_bad
 mov rax,QWORD PTR [rdi+16]
 cmp QWORD PTR [rax-8],264
 jne if_service_bad
 cmp DWORD PTR [rax-20],0
 jne if_service_bad
 movsxd rdx,DWORD PTR [rdi+24]
 test rdx,rdx
 js if_service_bad
 movsxd rcx,DWORD PTR [rdi+32]
 test rcx,rcx
 js if_service_bad
 mov r8,QWORD PTR [rax-16]
 sub r8,rdx
 jc if_service_bad
 cmp r8,rcx
 jb if_service_bad
 add rax,rdx
 mov QWORD PTR [rsp+184],rax
 mov QWORD PTR [rsp+200],rcx
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+40]
 call boom_heap_contains
 test eax,eax
 jz if_service_bad
 mov rax,QWORD PTR [rdi+40]
 cmp QWORD PTR [rax-8],264
 jne if_service_bad
 cmp DWORD PTR [rax-20],0
 jne if_service_bad
 movsxd rdx,DWORD PTR [rdi+48]
 test rdx,rdx
 js if_service_bad
 movsxd rcx,DWORD PTR [rdi+56]
 test rcx,rcx
 js if_service_bad
 mov r8,QWORD PTR [rax-16]
 sub r8,rdx
 jc if_service_bad
 cmp r8,rcx
 jb if_service_bad
 add rax,rdx
 mov QWORD PTR [rsp+192],rax
 mov QWORD PTR [rsp+208],rcx
 test rcx,rcx
 jz if_arrays_ready
 mov r8,QWORD PTR [rsp+200]
 test r8,r8
 jz if_arrays_ready
 mov r9,QWORD PTR [rsp+184]
 add r8,r9
 add rcx,rax
 cmp r9,rcx
 jae if_arrays_ready
 cmp rax,r8
 jb if_service_unsupported
if_arrays_ready:
 mov r14,QWORD PTR [rdi+8]
if_service_lookup:
 test r14,r14
 jz if_service_bad
 lea rcx,[rsi+16]
 call AcquireSRWLockShared
 cmp QWORD PTR [rsi+96],0
 jne if_shared_unsupported
 mov r13,QWORD PTR [rsi+24]
if_find_node:
 test r13,r13
 jz if_shared_bad
 cmp QWORD PTR [r13+8],r14
 je if_lock_node
 mov r13,QWORD PTR [r13]
 jmp if_find_node
if_lock_node:
 lea rcx,[r13+16]
 call AcquireSRWLockExclusive
 cmp r12d,2
 je if_get_adler
 cmp r12d,3
 je if_reset
 ; Neither JNI input nor Java has an END_INPUT flag: incomplete input is
 ; NEED_INPUT and does not become our standalone truncated terminal error.
 lea rax,[r13+IF_STATE_OFFSET]
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [rsp+184]
 mov QWORD PTR [rsp+40],rax
 mov rax,QWORD PTR [rsp+200]
 mov QWORD PTR [rsp+48],rax
 mov rax,QWORD PTR [rsp+192]
 mov QWORD PTR [rsp+56],rax
 mov rax,QWORD PTR [rsp+208]
 mov QWORD PTR [rsp+64],rax
 mov DWORD PTR [rsp+72],0
 lea rcx,[rsp+32]
 cmp DWORD PTR [r13+24],0
 je if_inflate_zlib
 call boom_deflate_stream_step
 jmp if_inflate_result
if_inflate_zlib:
 call boom_zlib_stream_step
if_inflate_result:
 mov DWORD PTR [rsp+216],eax
 mov r15,QWORD PTR [rsp+88]
 shl r15,31
 or r15,QWORD PTR [rsp+80]
 cmp eax,0
 je if_inflate_finished
 cmp eax,12
 je if_inflate_dictionary
 cmp eax,1
 je if_inflate_unlock
 cmp eax,2
 je if_inflate_unlock
 call boom_inflater_unlock
 mov eax,DWORD PTR [rsp+216]
 cmp eax,4
 jb if_service_internal
 cmp eax,8
 jbe if_inflate_data_error
 cmp eax,10
 je if_inflate_data_error
 cmp eax,11
 je if_inflate_data_error
 cmp eax,13
 jne if_service_internal
if_inflate_data_error:
 mov rdx,QWORD PTR [rsp+152]
 mov eax,DWORD PTR [rsp+80]
 mov DWORD PTR [rdx],eax
 mov rdx,QWORD PTR [rsp+160]
 mov eax,DWORD PTR [rsp+88]
 mov DWORD PTR [rdx],eax
 xor r8d,r8d
 jmp if_service_throw
if_inflate_finished:
 mov rax,04000000000000000h
 or r15,rax
 jmp if_inflate_unlock
if_inflate_dictionary:
 cmp DWORD PTR [r13+24],0
 jne if_inflate_bad_dictionary
 mov rax,08000000000000000h
 or r15,rax
if_inflate_unlock:
 call boom_inflater_unlock
 jmp if_service_done
if_inflate_bad_dictionary:
 call boom_inflater_unlock
 jmp if_service_internal
if_get_adler:
 xor r15d,r15d
 cmp DWORD PTR [r13+24],0
 jne if_inflate_unlock
 mov r15d,DWORD PTR [r13+IF_STATE_OFFSET+28]
 cmp DWORD PTR [r13+IF_STATE_OFFSET+12],7
 jne if_inflate_unlock
 mov r15d,DWORD PTR [r13+IF_STATE_OFFSET+32]
 jmp if_inflate_unlock
if_reset:
 lea rcx,[r13+IF_STATE_OFFSET]
 cmp DWORD PTR [r13+24],0
 je if_reset_zlib
 mov edx,34304
 call boom_deflate_stream_reset
 jmp if_reset_result
if_reset_zlib:
 mov edx,34560
 call boom_zlib_stream_reset
if_reset_result:
 mov DWORD PTR [rsp+216],eax
 call boom_inflater_unlock
 cmp DWORD PTR [rsp+216],0
 jne if_service_internal
 jmp if_service_done

if_service_end:
 test r14,r14
 jz if_service_bad
 lea rcx,[rsi+16]
 call AcquireSRWLockExclusive
 lea rbp,[rsi+24]
if_end_find:
 mov r13,QWORD PTR [rbp]
 test r13,r13
 jz if_exclusive_bad
 cmp QWORD PTR [r13+8],r14
 je if_end_found
 mov rbp,r13
 jmp if_end_find
if_end_found:
 mov rax,QWORD PTR [r13]
 mov QWORD PTR [rbp],rax
 dec QWORD PTR [rsi+32]
 inc QWORD PTR [rsi+48]
 sub QWORD PTR [rsi+104],IF_NODE_BYTES
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 mov rcx,QWORD PTR [r13+32]
 xor edx,edx
 mov r8,r13
 call HeapFree
 test eax,eax
 jz if_service_internal
 jmp if_service_done
if_exclusive_bad:
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 jmp if_service_bad
if_shared_bad:
 lea rcx,[rsi+16]
 call ReleaseSRWLockShared
 jmp if_service_bad
if_shared_unsupported:
 lea rcx,[rsi+16]
 call ReleaseSRWLockShared
 jmp if_service_unsupported
if_service_oom:
 mov r8d,1
 jmp if_service_throw
if_service_internal:
 mov r8d,2
if_service_throw:
 xor r15d,r15d
 mov rcx,rbx
 mov rdx,rsi
 call boom_inflater_throw
 jmp if_service_done
if_service_unsupported:
 mov DWORD PTR [rbx],20
 jmp if_service_zero
if_service_bad:
 mov DWORD PTR [rbx],7
if_service_zero:
 xor r15d,r15d
if_service_done:
 mov rax,r15
 add rsp,280
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_provider_inflater_service ENDP

; Explicit VM-owner teardown only, not a claim that Java Cleaner executed.
; Close publication under lifetime-exclusive, then free detached native states.
PUBLIC boom_inflater_close_owned
boom_inflater_close_owned PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 xor edi,edi
 test rbx,rbx
 jz if_close_done
 cmp DWORD PTR [rbx],04C464E49h
 jne if_close_done
 cmp DWORD PTR [rbx+4],1
 jne if_close_done
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 mov QWORD PTR [rbx+96],1
 mov rsi,QWORD PTR [rbx+24]
 mov QWORD PTR [rbx+24],0
 mov rdi,QWORD PTR [rbx+32]
 mov QWORD PTR [rbx+32],0
 mov QWORD PTR [rbx+104],0
 add QWORD PTR [rbx+48],rdi
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
if_close_next:
 test rsi,rsi
 jz if_close_done
 mov r12,QWORD PTR [rsi]
 mov rcx,QWORD PTR [rsi+32]
 xor edx,edx
 mov r8,rsi
 call HeapFree
 mov rsi,r12
 jmp if_close_next
if_close_done:
 mov rax,rdi
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_inflater_close_owned ENDP
