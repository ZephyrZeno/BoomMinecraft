; Source-bound normal Inflater array subset over INFL256/2 RW owner.
; The owner is the sole native allocator. Every decoder borrow is released
; before Java callbacks, field writes or return. No private handle is a pointer.
; Dictionary/direct-buffer methods remain explicit Context20 boundaries.
.const
ifr_bad_header_check WORD 105,110,99,111,114,114,101,99,116,32,104,101,97,100,101,114,32,99,104,101,99,107
ifr_bad_block_type WORD 105,110,118,97,108,105,100,32,98,108,111,99,107,32,116,121,112,101
ifr_bad_stored_lengths WORD 105,110,118,97,108,105,100,32,115,116,111,114,101,100,32,98,108,111,99,107,32,108,101,110,103,116,104,115
ifr_bad_data WORD 73,110,118,97,108,105,100,32,99,111,109,112,114,101,115,115,101,100,32,100,97,116,97
ifr_alloc_error WORD 73,110,102,108,97,116,101,114,32,97,108,108,111,99,97,116,105,111,110,32,102,97,105,108,101,100
ifr_state_error WORD 73,110,102,108,97,116,101,114,32,110,97,116,105,118,101,32,115,116,97,116,101,32,102,97,105,108,117,114,101
.code

; ctx RCX,pool RDX,error kind R8D: DFE0/OOME1/InternalError2.
; No owner locks or borrows can be held at this call site.
ifr_throw PROC PRIVATE FRAME
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
 mov edi,r9d
 cmp r12d,2
 ja ifrt_done
 lea r8,ifr_bad_data
 mov r9d,23
 test r12d,r12d
 jnz ifrt_non_data
 cmp edi,1
 je ifrt_header_check
 cmp edi,4
 je ifrt_block_type
 cmp edi,5
 je ifrt_stored_lengths
 jmp ifrt_message
ifrt_header_check:
 lea r8,ifr_bad_header_check
 mov r9d,22
 jmp ifrt_message
ifrt_block_type:
 lea r8,ifr_bad_block_type
 mov r9d,18
 jmp ifrt_message
ifrt_stored_lengths:
 lea r8,ifr_bad_stored_lengths
 mov r9d,28
 jmp ifrt_message
ifrt_non_data:
 lea r8,ifr_alloc_error
 mov r9d,26
 cmp r12d,1
 je ifrt_message
 lea r8,ifr_state_error
 mov r9d,29
ifrt_message:
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+88]
 call boom_java_property_copy
 test rax,rax
 jz ifrt_done
 mov QWORD PTR [rsp+40],rax
 imul edi,r12d,24
 lea rbp,ifr_errors
 add rbp,rdi
 mov rcx,QWORD PTR [rbp]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne ifrt_done
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rbp+8]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz ifrt_done
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rbp+16]
 cmp DWORD PTR [rbx],0
 jne ifrt_done
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+32]
 lea r8,boom_runtime_type_map
 lea r9,IFR_THROWABLE_TYPE
 call boom_exception_set32
ifrt_done:
 xor eax,eax
 add rsp,64
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
ifr_throw ENDP

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
 ; Stack: decoderJob96@32,Borrow64@128,fieldPtrs@192/200,
 ; slices@208/216/224/232,decoderStatus240,handleOut248.
 mov rbx,rcx
 mov rdi,rdx
 mov rsi,r8
 mov r12d,r9d
 xor r15d,r15d
 test rbx,rbx
 jz ifrs_done
 cmp DWORD PTR [rbx],0
 jne ifrs_done
 cmp QWORD PTR [rbx+16],0
 jne ifrs_done
 cmp QWORD PTR [rbx+24],0
 jne ifrs_done
 test rsi,rsi
 jz ifrs_bad
 cmp DWORD PTR [rsi],04C464E49h
 jne ifrs_bad
 cmp DWORD PTR [rsi+4],2
 jne ifrs_bad
 cmp QWORD PTR [rsi+8],0
 je ifrs_bad
 cmp QWORD PTR [rsi+64],2
 jne ifrs_bad
 cmp QWORD PTR [rsi+72],0
 je ifrs_bad
 cmp QWORD PTR [rsi+80],0
 je ifrs_bad
 cmp QWORD PTR [rsi+88],0
 je ifrs_bad
 cmp r12d,1
 jb ifrs_bad
 cmp r12d,10
 ja ifrs_bad
 cmp r12d,5
 ja ifrs_unsupported
 test rdi,rdi
 jz ifrs_bad
 cmp r12d,1
 je ifrs_init
 cmp r12d,5
 je ifrs_arrays
 mov r14,QWORD PTR [rdi]
 cmp r12d,4
 je ifrs_end
 jmp ifrs_acquire
ifrs_init:
 mov edx,DWORD PTR [rdi]
 cmp edx,1
 ja ifrs_bad
 mov QWORD PTR [rsp+248],0
 mov rcx,rsi
 lea r8,[rsp+248]
 call boom_inflater_owner_init
 test eax,eax
 jnz ifrs_owner_error
 mov r15,QWORD PTR [rsp+248]
 test r15,r15
 jz ifrs_internal
 jmp ifrs_done
ifrs_end:
 mov rcx,rsi
 mov rdx,r14
 call boom_inflater_owner_end
 test eax,eax
 jnz ifrs_owner_error
 jmp ifrs_done

ifrs_arrays:
 ; Two cached source FMAPPROCs are consumed, not bypassed with offsets.
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi]
 call boom_heap_contains
 test eax,eax
 jz ifrs_bad
 mov rcx,QWORD PTR [rdi]
 mov rdx,rbx
 call QWORD PTR [rsi+72]
 test rax,rax
 jz ifrs_done
 mov QWORD PTR [rsp+192],rax
 mov rcx,QWORD PTR [rdi]
 mov rdx,rbx
 call QWORD PTR [rsi+80]
 test rax,rax
 jz ifrs_done
 mov QWORD PTR [rsp+200],rax
 ; Heap validation checks the whole trusted header before byte[] tag reads.
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+16]
 call boom_heap_contains
 test eax,eax
 jz ifrs_bad
 mov rax,QWORD PTR [rdi+16]
 cmp QWORD PTR [rax-8],264
 jne ifrs_bad
 cmp DWORD PTR [rax-20],0
 jne ifrs_bad
 movsxd rdx,DWORD PTR [rdi+24]
 test rdx,rdx
 js ifrs_bad
 movsxd rcx,DWORD PTR [rdi+32]
 test rcx,rcx
 js ifrs_bad
 mov r8,QWORD PTR [rax-16]
 sub r8,rdx
 jc ifrs_bad
 cmp r8,rcx
 jb ifrs_bad
 add rax,rdx
 mov QWORD PTR [rsp+208],rax
 mov QWORD PTR [rsp+224],rcx
 mov rcx,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+40]
 call boom_heap_contains
 test eax,eax
 jz ifrs_bad
 mov rax,QWORD PTR [rdi+40]
 cmp QWORD PTR [rax-8],264
 jne ifrs_bad
 cmp DWORD PTR [rax-20],0
 jne ifrs_bad
 movsxd rdx,DWORD PTR [rdi+48]
 test rdx,rdx
 js ifrs_bad
 movsxd rcx,DWORD PTR [rdi+56]
 test rcx,rcx
 js ifrs_bad
 mov r8,QWORD PTR [rax-16]
 sub r8,rdx
 jc ifrs_bad
 cmp r8,rcx
 jb ifrs_bad
 add rax,rdx
 mov QWORD PTR [rsp+216],rax
 mov QWORD PTR [rsp+232],rcx
 test rcx,rcx
 jz ifrs_arrays_ready
 mov r8,QWORD PTR [rsp+224]
 test r8,r8
 jz ifrs_arrays_ready
 mov r9,QWORD PTR [rsp+208]
 add r8,r9
 add rcx,rax
 cmp r9,rcx
 jae ifrs_arrays_ready
 cmp rax,r8
 jb ifrs_unsupported
ifrs_arrays_ready:
 mov r14,QWORD PTR [rdi+8]
ifrs_acquire:
 xor eax,eax
 lea r10,[rsp+128]
 mov r11d,8
ifrs_zero_borrow:
 mov QWORD PTR [r10],rax
 add r10,8
 dec r11d
 jnz ifrs_zero_borrow
 mov rcx,rsi
 mov rdx,r14
 lea r8,[rsp+128]
 call boom_inflater_owner_acquire
 test eax,eax
 jnz ifrs_owner_error
 mov r13,QWORD PTR [rsp+144]
 mov rbp,QWORD PTR [rsp+152]
 cmp r12d,2
 je ifrs_adler
 cmp r12d,3
 je ifrs_reset
 ; Both caller ranges and real node lease are now valid. No END_INPUT flag.
 xor eax,eax
 lea r10,[rsp+32]
 mov r11d,12
ifrs_zero_job:
 mov QWORD PTR [r10],rax
 add r10,8
 dec r11d
 jnz ifrs_zero_job
 mov QWORD PTR [rsp+32],rbp
 mov rax,QWORD PTR [rsp+208]
 mov QWORD PTR [rsp+40],rax
 mov rax,QWORD PTR [rsp+224]
 mov QWORD PTR [rsp+48],rax
 mov rax,QWORD PTR [rsp+216]
 mov QWORD PTR [rsp+56],rax
 mov rax,QWORD PTR [rsp+232]
 mov QWORD PTR [rsp+64],rax
 lea rcx,[rsp+32]
 cmp DWORD PTR [r13+24],0
 je ifrs_step_zlib
 call boom_deflate_stream_step_reason
 jmp ifrs_step_result
ifrs_step_zlib:
 call boom_zlib_stream_step_reason
ifrs_step_result:
 mov DWORD PTR [rsp+240],eax
 mov r15,QWORD PTR [rsp+88]
 shl r15,31
 or r15,QWORD PTR [rsp+80]
 test eax,eax
 jz ifrs_finished
 cmp eax,12
 je ifrs_dictionary
 cmp eax,1
 je ifrs_release_return
 cmp eax,2
 je ifrs_release_return
 ; Preserve format status until release; no Java field writes under lease.
 lea rcx,[rsp+128]
 call boom_inflater_owner_release
 test eax,eax
 jnz ifrs_release_failure
 mov eax,DWORD PTR [rsp+240]
 cmp eax,4
 jb ifrs_internal
 cmp eax,8
 jbe ifrs_data_error
 cmp eax,10
 je ifrs_data_error
 cmp eax,11
 je ifrs_data_error
 cmp eax,13
 jne ifrs_internal
ifrs_data_error:
 mov rdx,QWORD PTR [rsp+192]
 mov eax,DWORD PTR [rsp+80]
 mov DWORD PTR [rdx],eax
 mov rdx,QWORD PTR [rsp+200]
 mov eax,DWORD PTR [rsp+88]
 mov DWORD PTR [rdx],eax
 mov r9d,DWORD PTR [rsp+124]
 xor r8d,r8d
 jmp ifrs_throw
ifrs_finished:
 mov rax,04000000000000000h
 or r15,rax
 jmp ifrs_release_return
ifrs_dictionary:
 cmp DWORD PTR [r13+24],0
 jne ifrs_release_internal
 mov rax,08000000000000000h
 or r15,rax
 jmp ifrs_release_return
ifrs_adler:
 xor r15d,r15d
 cmp DWORD PTR [r13+24],0
 jne ifrs_release_return
 mov r15d,DWORD PTR [rbp+28]
 cmp DWORD PTR [rbp+12],7
 jne ifrs_release_return
 mov r15d,DWORD PTR [rbp+32]
 jmp ifrs_release_return
ifrs_reset:
 mov rcx,rbp
 cmp DWORD PTR [r13+24],0
 je ifrs_reset_zlib
 mov edx,34304
 call boom_deflate_stream_reset
 jmp ifrs_reset_result
ifrs_reset_zlib:
 mov edx,34560
 call boom_zlib_stream_reset
ifrs_reset_result:
 mov DWORD PTR [rsp+240],eax
 lea rcx,[rsp+128]
 call boom_inflater_owner_release
 test eax,eax
 jnz ifrs_release_failure
 cmp DWORD PTR [rsp+240],0
 jne ifrs_internal
 jmp ifrs_done
ifrs_release_internal:
 lea rcx,[rsp+128]
 call boom_inflater_owner_release
 test eax,eax
 jnz ifrs_release_failure
 jmp ifrs_internal
ifrs_release_return:
 lea rcx,[rsp+128]
 call boom_inflater_owner_release
 test eax,eax
 jnz ifrs_release_failure
 jmp ifrs_done
ifrs_release_failure:
 ; A failed release may retain the real Core token. No Java callback.
 jmp ifrs_unsupported
ifrs_owner_error:
 cmp eax,4
 je ifrs_oom
 cmp eax,2
 je ifrs_unsupported
 cmp eax,7
 je ifrs_unsupported
 cmp eax,9
 je ifrs_unsupported
 cmp eax,12
 je ifrs_unsupported
 cmp eax,10
 je ifrs_internal
 jmp ifrs_bad
ifrs_oom:
 mov r8d,1
 jmp ifrs_throw
ifrs_internal:
 mov r8d,2
ifrs_throw:
 xor r15d,r15d
 mov rcx,rbx
 mov rdx,rsi
 call ifr_throw
 jmp ifrs_done
ifrs_unsupported:
 mov DWORD PTR [rbx],20
 jmp ifrs_zero
ifrs_bad:
 mov DWORD PTR [rbx],7
ifrs_zero:
 xor r15d,r15d
ifrs_done:
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
