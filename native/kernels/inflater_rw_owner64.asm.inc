; INFL256/2 native lifecycle only. Source registry owns the actual pool.
; All persistent ownership/Job metadata stays outside RW decoder allocations.
IFW_NODE_BYTES EQU 34608
IFW_STATE EQU 48
IFW_CAP EQU 256
IFW_REC_BYTES EQU 256
IFW_JOB EQU 64
EXTERN AcquireSRWLockExclusive:PROC
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN ReleaseSRWLockShared:PROC
EXTERN TryAcquireSRWLockExclusive:PROC
EXTERN boom_native_memory_service:PROC
EXTERN boom_deflate_stream_reset:PROC
EXTERN boom_zlib_stream_reset:PROC
.data
ALIGN 8
PUBLIC boom_inflater_owner_records
boom_inflater_owner_records BYTE 65536 DUP(0)
ALIGN 8
ifw_bound_pool QWORD 0
.code

ifw_pool_valid PROC PRIVATE
 xor eax,eax
 test rcx,rcx
 jz ifwp_done
 cmp DWORD PTR [rcx],04C464E49h
 jne ifwp_done
 cmp DWORD PTR [rcx+4],2
 jne ifwp_done
 mov r10,QWORD PTR [ifw_bound_pool]
 test r10,r10
 jz ifwp_unbound
 cmp r10,rcx
 jne ifwp_done
ifwp_unbound:
 lea r10,boom_inflater_owner_records
 cmp QWORD PTR [rcx+120],r10
 jne ifwp_done
 cmp DWORD PTR [rcx+128],IFW_CAP
 jne ifwp_done
 cmp DWORD PTR [rcx+132],IFW_NODE_BYTES
 jne ifwp_done
 cmp DWORD PTR [rcx+144],IFW_REC_BYTES
 jne ifwp_done
 cmp QWORD PTR [rcx+160],65536
 jne ifwp_done
 cmp DWORD PTR [rcx+156],0
 jne ifwp_done
 mov eax,1
ifwp_done:
 ret
ifw_pool_valid ENDP

; Trusted pool+candidate record -> bool, no RW node dereference.
ifw_record_valid PROC PRIVATE
 xor eax,eax
 lea r10,boom_inflater_owner_records
 cmp rdx,r10
 jb ifwr_done
 mov r11,rdx
 sub r11,r10
 cmp r11,65536
 jae ifwr_done
 test r11d,255
 jnz ifwr_done
 cmp QWORD PTR [rdx+192],rcx
 jne ifwr_done
 mov eax,1
ifwr_done:
 ret
ifw_record_valid ENDP

; RCX pool,RDX handle -> RAX stable record, EDX0/1miss/5corrupt.
; Pool lifetime lock is held by caller. All links stay in fixed image records.
ifw_find PROC PRIVATE
 mov r8,rdx
 mov r9,rcx
 mov r10,QWORD PTR [rcx+24]
 mov r11d,IFW_CAP
ifwf_loop:
 test r10,r10
 jz ifwf_miss
 lea rax,boom_inflater_owner_records
 cmp r10,rax
 jb ifwf_bad
 mov rdx,r10
 sub rdx,rax
 cmp rdx,65536
 jae ifwf_bad
 test edx,255
 jnz ifwf_bad
 cmp QWORD PTR [r10+192],r9
 jne ifwf_bad
 cmp QWORD PTR [r10+8],r8
 je ifwf_found
 mov r10,QWORD PTR [r10]
 dec r11d
 jnz ifwf_loop
ifwf_bad:
 xor eax,eax
 mov edx,5
 ret
ifwf_miss:
 xor eax,eax
 mov edx,1
 ret
ifwf_found:
 mov rax,r10
 xor edx,edx
 ret
ifw_find ENDP

; RCX record. A token must be released before clearing a persistent Job.
ifw_clear_job PROC PRIVATE
 lea r10,[rcx+IFW_JOB]
 xor eax,eax
 mov r11d,16
ifwcj_loop:
 mov QWORD PTR [r10],rax
 add r10,8
 dec r11d
 jnz ifwcj_loop
 ret
ifw_clear_job ENDP

; RCX pool,RDX record, lifeEXCLUSIVE and record lock0. No live allocation/token.
ifw_retire PROC PRIVATE
 lea r8,[rcx+24]
 mov r9d,IFW_CAP
ifwrt_find:
 mov r10,QWORD PTR [r8]
 test r10,r10
 jz ifwrt_bad
 cmp r10,rdx
 je ifwrt_got
 lea r11,boom_inflater_owner_records
 mov rax,r10
 sub rax,r11
 cmp rax,65536
 jae ifwrt_bad
 test eax,255
 jnz ifwrt_bad
 mov r8,r10
 dec r9d
 jnz ifwrt_find
ifwrt_bad:
 mov eax,5
 ret
ifwrt_got:
 cmp QWORD PTR [rdx+32],0
 jne ifwrt_bad
 cmp QWORD PTR [rdx+IFW_JOB+48],0
 jne ifwrt_bad
 cmp QWORD PTR [rdx+16],0
 jne ifwrt_bad
 mov rax,QWORD PTR [rdx]
 mov QWORD PTR [r8],rax
 mov r10,rdx
 mov r9d,32
 xor eax,eax
ifwrt_zero:
 mov QWORD PTR [r10],rax
 add r10,8
 dec r9d
 jnz ifwrt_zero
 ret
ifw_retire ENDP

; RCX pool,RDX record under lifeEXCLUSIVE. Retry retained release then real free.
; Free Job is in stable native record, never in the allocation being freed.
ifw_free_record PROC PRIVATE FRAME
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
 cmp QWORD PTR [rsi+IFW_JOB+48],0
 je ifwfr_no_token
 mov DWORD PTR [rsi+IFW_JOB+64],0
 mov DWORD PTR [rsi+IFW_JOB+68],0
 mov DWORD PTR [rsi+IFW_JOB+72],9
 lea rcx,[rsi+IFW_JOB]
 call boom_native_memory_service
 test eax,eax
 jnz ifwfr_store
 cmp QWORD PTR [rsi+IFW_JOB+48],0
 jne ifwfr_retained_invariant
ifwfr_no_token:
 cmp QWORD PTR [rsi+32],0
 je ifwfr_retire
 cmp QWORD PTR [rsi+40],IFW_NODE_BYTES
 jne ifwfr_bad
 cmp QWORD PTR [rbx+32],0
 je ifwfr_bad
 cmp QWORD PTR [rbx+104],IFW_NODE_BYTES
 jb ifwfr_bad
 mov rcx,rsi
 call ifw_clear_job
 mov rax,QWORD PTR [rbx+112]
 mov QWORD PTR [rsi+IFW_JOB],rax
 mov rax,QWORD PTR [rsi+32]
 mov QWORD PTR [rsi+IFW_JOB+8],rax
 mov DWORD PTR [rsi+IFW_JOB+72],2
 lea rcx,[rsi+IFW_JOB]
 call boom_native_memory_service
 test eax,eax
 jnz ifwfr_store
 ; No access to the freed RW node is made after successful op2.
 mov QWORD PTR [rsi+32],0
 mov QWORD PTR [rsi+40],0
 mov QWORD PTR [rsi+48],0
 dec QWORD PTR [rbx+32]
 inc QWORD PTR [rbx+48]
 sub QWORD PTR [rbx+104],IFW_NODE_BYTES
ifwfr_retire:
 mov rcx,rbx
 mov rdx,rsi
 call ifw_retire
 jmp ifwfr_done
ifwfr_bad:
 mov eax,5
 jmp ifwfr_done
ifwfr_retained_invariant:
 mov eax,5
ifwfr_store:
 ; Any incomplete retry release/free is persistent cleanup, never Java OOME.
 mov DWORD PTR [rsi+200],eax
 mov edx,DWORD PTR [rsi+IFW_JOB+80]
 mov DWORD PTR [rsi+204],edx
 mov DWORD PTR [rbx+152],edx
 mov eax,12
ifwfr_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
ifw_free_record ENDP

PUBLIC boom_inflater_owner_open
boom_inflater_owner_open PROC FRAME
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
 call ifw_pool_valid
 test eax,eax
 jz ifwo_bad
 test rsi,rsi
 jz ifwo_bad
 mov rax,03130574D4E4F4F42h
 cmp QWORD PTR [rsi],rax
 jne ifwo_bad
 cmp DWORD PTR [rsi+8],128
 jne ifwo_bad
 cmp DWORD PTR [rsi+12],1
 jne ifwo_bad
 cmp DWORD PTR [rsi+24],1
 jne ifwo_closed
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 mov eax,DWORD PTR [rbx+140]
 cmp eax,1
 je ifwo_repeat
 test eax,eax
 jnz ifwo_closed_unlock
 cmp QWORD PTR [rbx+24],0
 jne ifwo_bad_unlock
 cmp QWORD PTR [rbx+32],0
 jne ifwo_bad_unlock
 cmp QWORD PTR [rbx+104],0
 jne ifwo_bad_unlock
 cmp DWORD PTR [rbx+136],0
 jne ifwo_bad_unlock
 cmp QWORD PTR [rbx+96],0
 jne ifwo_bad_unlock
 mov rax,QWORD PTR [ifw_bound_pool]
 test rax,rax
 jz ifwo_bind
 cmp rax,rbx
 jne ifwo_bad_unlock
ifwo_bind:
 xor eax,eax
 lock cmpxchg QWORD PTR [ifw_bound_pool],rbx
 test rax,rax
 jz ifwo_bound
 cmp rax,rbx
 jne ifwo_bad_unlock
ifwo_bound:
 lea r10,boom_inflater_owner_records
 mov ecx,8192
 xor eax,eax
ifwo_verify_zero:
 cmp QWORD PTR [r10],0
 jne ifwo_bad_unlock
 add r10,8
 dec ecx
 jnz ifwo_verify_zero
 mov QWORD PTR [rbx+112],rsi
 mov DWORD PTR [rbx+140],1
 xor edi,edi
 jmp ifwo_unlock
ifwo_repeat:
 cmp QWORD PTR [rbx+112],rsi
 jne ifwo_bad_unlock
 cmp QWORD PTR [rbx+96],0
 jne ifwo_closed_unlock
 xor edi,edi
 jmp ifwo_unlock
ifwo_bad_unlock:
 mov edi,5
 jmp ifwo_unlock
ifwo_closed_unlock:
 mov edi,9
ifwo_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rbx+148],edi
 mov eax,edi
 jmp ifwo_done
ifwo_bad:
 mov eax,5
 jmp ifwo_done
ifwo_closed:
 mov eax,9
ifwo_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_inflater_owner_open ENDP

PUBLIC boom_inflater_owner_init
boom_inflater_owner_init PROC FRAME
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
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov r12d,edx
 mov r13,r8
 xor esi,esi
 xor r15d,r15d
 test r13,r13
 jz ifwi_args_early
 mov QWORD PTR [r13],0
 cmp r12d,1
 ja ifwi_args_early
 call ifw_pool_valid
 test eax,eax
 jz ifwi_bad_early
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 lock inc DWORD PTR [rbx+136]
 cmp DWORD PTR [rbx+140],1
 jne ifwi_closed
 cmp QWORD PTR [rbx+96],0
 jne ifwi_closed
 cmp QWORD PTR [rbx+56],-1
 je ifwi_limit
 lea rsi,boom_inflater_owner_records
 mov ecx,IFW_CAP
ifwi_find_free:
 cmp DWORD PTR [rsi+24],0
 jne ifwi_next
 cmp QWORD PTR [rsi+32],0
 jne ifwi_bad
 cmp QWORD PTR [rsi+IFW_JOB+48],0
 jne ifwi_bad
 cmp QWORD PTR [rsi+16],0
 jne ifwi_bad
 jmp ifwi_reserve
ifwi_next:
 add rsi,IFW_REC_BYTES
 dec ecx
 jnz ifwi_find_free
 jmp ifwi_limit
ifwi_reserve:
 inc QWORD PTR [rbx+56]
 mov rax,QWORD PTR [rbx+56]
 mov QWORD PTR [rsi+8],rax
 mov DWORD PTR [rsi+24],1
 mov DWORD PTR [rsi+28],r12d
 mov QWORD PTR [rsi+192],rbx
 mov rax,QWORD PTR [rbx+24]
 mov QWORD PTR [rsi],rax
 mov QWORD PTR [rbx+24],rsi
 mov rcx,rsi
 call ifw_clear_job
 mov rax,QWORD PTR [rbx+112]
 mov QWORD PTR [rsi+IFW_JOB],rax
 mov QWORD PTR [rsi+IFW_JOB+16],IFW_NODE_BYTES
 lea rcx,[rsi+IFW_JOB]
 call boom_native_memory_service
 mov edi,eax
 mov r14,QWORD PTR [rsi+IFW_JOB+40]
 test r14,r14
 jz ifwi_alloc_no_result
 ; Adopt only the actual Core result, and preserve it before any reset call.
 mov QWORD PTR [rsi+32],r14
 mov QWORD PTR [rsi+40],IFW_NODE_BYTES
 inc QWORD PTR [rbx+32]
 inc QWORD PTR [rbx+40]
 add QWORD PTR [rbx+104],IFW_NODE_BYTES
 mov DWORD PTR [rsi+24],2
 test edi,edi
 jnz ifwi_rollback
 mov rcx,rsi
 call ifw_clear_job
 mov rax,QWORD PTR [rbx+112]
 mov QWORD PTR [rsi+IFW_JOB],rax
 mov QWORD PTR [rsi+IFW_JOB+8],r14
 mov QWORD PTR [rsi+IFW_JOB+16],IFW_NODE_BYTES
 mov DWORD PTR [rsi+IFW_JOB+68],2
 mov DWORD PTR [rsi+IFW_JOB+72],8
 lea rcx,[rsi+IFW_JOB]
 call boom_native_memory_service
 mov edi,eax
 test eax,eax
 jnz ifwi_rollback
 mov rax,QWORD PTR [rsi+IFW_JOB+56]
 mov QWORD PTR [rsi+48],rax
 xor eax,eax
 mov QWORD PTR [r14],rax
 mov rax,QWORD PTR [rsi+8]
 mov QWORD PTR [r14+8],rax
 mov QWORD PTR [r14+16],0
 mov DWORD PTR [r14+24],r12d
 mov DWORD PTR [r14+28],2
 mov rax,QWORD PTR [rbx+112]
 mov QWORD PTR [r14+32],rax
 mov rax,QWORD PTR [rsi+48]
 mov QWORD PTR [r14+40],rax
 lea rcx,[r14+IFW_STATE]
 test r12d,r12d
 jz ifwi_zlib
 mov edx,34304
 call boom_deflate_stream_reset
 jmp ifwi_reset_result
ifwi_zlib:
 mov edx,34560
 call boom_zlib_stream_reset
ifwi_reset_result:
 mov r15d,eax
 mov DWORD PTR [rsi+208],eax
 mov DWORD PTR [r14+28],3
 test eax,eax
 jz ifwi_release_init
 mov DWORD PTR [r14+28],5
ifwi_release_init:
 mov DWORD PTR [rsi+IFW_JOB+68],0
 mov DWORD PTR [rsi+IFW_JOB+72],9
 lea rcx,[rsi+IFW_JOB]
 call boom_native_memory_service
 test eax,eax
 jnz ifwi_retained_token
 cmp QWORD PTR [rsi+IFW_JOB+48],0
 jne ifwi_retained_token
 test r15d,r15d
 jnz ifwi_decoder_failed
 cmp QWORD PTR [rbx+96],0
 jne ifwi_reset_closed
 mov DWORD PTR [rsi+24],3
 mov rax,QWORD PTR [rsi+8]
 mov QWORD PTR [r13],rax
 xor edi,edi
 jmp ifwi_unlock
ifwi_alloc_no_result:
 test edi,edi
 jz ifwi_alloc_null_success
 cmp edi,4
 je ifwi_alloc_resource_failure
 cmp edi,7
 jne ifwi_retire_unallocated
ifwi_alloc_resource_failure:
 ; Public init maps real Core OS/budget/capacity allocation failure to OOME4.
 ; Keep the original Core status in Pool.last_status instead of relabeling it.
 mov r15d,edi
 or r15d,080000000h
 mov edi,4
 jmp ifwi_retire_unallocated
ifwi_alloc_null_success:
 mov edi,5
ifwi_retire_unallocated:
 mov rcx,rbx
 mov rdx,rsi
 call ifw_retire
 test eax,eax
 jz ifwi_unlock
 mov edi,eax
 jmp ifwi_unlock
ifwi_retained_token:
 mov DWORD PTR [rsi+24],5
 test eax,eax
 jnz ifwi_retained_status
 mov eax,5
ifwi_retained_status:
 mov DWORD PTR [rsi+200],eax
 mov edx,DWORD PTR [rsi+IFW_JOB+80]
 mov DWORD PTR [rsi+204],edx
 mov DWORD PTR [rbx+152],edx
 mov edi,12
 jmp ifwi_unlock
ifwi_decoder_failed:
 mov edi,10
 jmp ifwi_rollback
ifwi_reset_closed:
 mov edi,9
ifwi_rollback:
 mov DWORD PTR [rsi+24],5
 mov rcx,rbx
 mov rdx,rsi
 call ifw_free_record
 test eax,eax
 jz ifwi_unlock
 mov edi,12
 jmp ifwi_unlock
ifwi_args_early:
 mov eax,3
 jmp ifwi_done
ifwi_bad_early:
 mov eax,5
 jmp ifwi_done
ifwi_bad:
 mov edi,5
 jmp ifwi_unlock
ifwi_limit:
 mov edi,7
 jmp ifwi_unlock
ifwi_closed:
 mov edi,9
ifwi_unlock:
 lock dec DWORD PTR [rbx+136]
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rbx+148],edi
 test r15d,080000000h
 jz ifwi_public_status
 mov eax,r15d
 and eax,07FFFFFFFh
 mov DWORD PTR [rbx+148],eax
ifwi_public_status:
 mov eax,edi
ifwi_done:
 add rsp,32
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_inflater_owner_init ENDP

PUBLIC boom_inflater_owner_acquire
boom_inflater_owner_acquire PROC FRAME
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
 mov rdi,r8
 test rdi,rdi
 jz ifwa_args
 mov r10,rdi
 mov ecx,8
 xor eax,eax
ifwa_zero:
 mov QWORD PTR [r10],rax
 add r10,8
 dec ecx
 jnz ifwa_zero
 mov QWORD PTR [rdi],rbx
 mov QWORD PTR [rdi+32],r12
 mov rcx,rbx
 call ifw_pool_valid
 test eax,eax
 jz ifwa_bad
 lea rcx,[rbx+16]
 call AcquireSRWLockShared
 lock inc DWORD PTR [rbx+136]
 mov DWORD PTR [rdi+40],1
 cmp DWORD PTR [rbx+140],1
 jne ifwa_closed_life
 cmp QWORD PTR [rbx+96],0
 jne ifwa_closed_life
 test r12,r12
 jz ifwa_miss_life
 mov rcx,rbx
 mov rdx,r12
 call ifw_find
 test rax,rax
 jnz ifwa_found
 mov r13d,edx
 jmp ifwa_unlock_life
ifwa_found:
 mov rsi,rax
 mov QWORD PTR [rdi+8],rsi
 lea rcx,[rsi+16]
 call AcquireSRWLockExclusive
 mov DWORD PTR [rdi+40],3
 cmp DWORD PTR [rsi+24],6
 je ifwa_pending_record
 cmp DWORD PTR [rsi+24],3
 jne ifwa_closed_record
 cmp QWORD PTR [rsi+IFW_JOB+48],0
 jne ifwa_pending_record
 cmp QWORD PTR [rsi+32],0
 je ifwa_bad_record
 cmp QWORD PTR [rsi+40],IFW_NODE_BYTES
 jne ifwa_bad_record
 mov rcx,rsi
 call ifw_clear_job
 mov rax,QWORD PTR [rbx+112]
 mov QWORD PTR [rsi+IFW_JOB],rax
 mov rax,QWORD PTR [rsi+32]
 mov QWORD PTR [rsi+IFW_JOB+8],rax
 mov QWORD PTR [rsi+IFW_JOB+16],IFW_NODE_BYTES
 mov DWORD PTR [rsi+IFW_JOB+68],2
 mov DWORD PTR [rsi+IFW_JOB+72],8
 lea rcx,[rsi+IFW_JOB]
 call boom_native_memory_service
 mov r13d,eax
 test eax,eax
 jnz ifwa_core_failed
 mov rax,QWORD PTR [rsi+IFW_JOB+56]
 cmp rax,QWORD PTR [rsi+48]
 jne ifwa_generation
 mov rax,QWORD PTR [rsi+32]
 mov QWORD PTR [rdi+16],rax
 add rax,IFW_STATE
 mov QWORD PTR [rdi+24],rax
 mov DWORD PTR [rdi+40],7
 mov DWORD PTR [rdi+44],0
 mov DWORD PTR [rbx+148],0
 xor eax,eax
 jmp ifwa_done
ifwa_generation:
 mov DWORD PTR [rsi+IFW_JOB+68],0
 mov DWORD PTR [rsi+IFW_JOB+72],9
 lea rcx,[rsi+IFW_JOB]
 call boom_native_memory_service
 test eax,eax
 jnz ifwa_generation_pending
 cmp QWORD PTR [rsi+IFW_JOB+48],0
 jne ifwa_generation_pending
 mov DWORD PTR [rsi+24],4
 mov r13d,13
 jmp ifwa_unlock_record
ifwa_generation_pending:
 test eax,eax
 jnz ifwa_retained_status
 mov eax,5
ifwa_retained_status:
 mov DWORD PTR [rsi+24],6
 mov DWORD PTR [rsi+200],eax
 mov DWORD PTR [rdi+48],eax
 mov edx,DWORD PTR [rsi+IFW_JOB+80]
 mov DWORD PTR [rsi+204],edx
 mov DWORD PTR [rdi+52],edx
 mov r13d,12
 jmp ifwa_unlock_record
ifwa_core_failed:
 cmp QWORD PTR [rsi+IFW_JOB+48],0
 jne ifwa_retained_status
 cmp eax,2
 je ifwa_record_status
 mov DWORD PTR [rsi+24],4
ifwa_record_status:
 mov DWORD PTR [rsi+200],eax
 mov DWORD PTR [rdi+48],eax
 mov eax,DWORD PTR [rsi+IFW_JOB+80]
 mov DWORD PTR [rsi+204],eax
 mov DWORD PTR [rdi+52],eax
 jmp ifwa_unlock_record
ifwa_pending_record:
 mov r13d,12
 jmp ifwa_unlock_record
ifwa_closed_record:
 mov r13d,9
 jmp ifwa_unlock_record
ifwa_bad_record:
 mov r13d,5
ifwa_unlock_record:
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
ifwa_unlock_life:
 lock dec DWORD PTR [rbx+136]
 lea rcx,[rbx+16]
 call ReleaseSRWLockShared
 mov DWORD PTR [rdi+40],0
 mov DWORD PTR [rdi+44],r13d
 mov DWORD PTR [rbx+148],r13d
 mov eax,r13d
 jmp ifwa_done
ifwa_miss_life:
 mov r13d,1
 jmp ifwa_unlock_life
ifwa_closed_life:
 mov r13d,9
 jmp ifwa_unlock_life
ifwa_bad:
 mov DWORD PTR [rdi+44],5
 mov eax,5
 jmp ifwa_done
ifwa_args:
 mov eax,3
ifwa_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_inflater_owner_acquire ENDP

PUBLIC boom_inflater_owner_release
boom_inflater_owner_release PROC FRAME
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
 mov rdi,rcx
 test rdi,rdi
 jz ifwl_args
 cmp DWORD PTR [rdi+40],0
 je ifwl_ok_early
 cmp DWORD PTR [rdi+40],7
 jne ifwl_bad
 mov rbx,QWORD PTR [rdi]
 mov rsi,QWORD PTR [rdi+8]
 mov rcx,rbx
 call ifw_pool_valid
 test eax,eax
 jz ifwl_bad
 mov rcx,rbx
 mov rdx,rsi
 call ifw_record_valid
 test eax,eax
 jz ifwl_bad
 mov rax,QWORD PTR [rdi+32]
 cmp rax,QWORD PTR [rsi+8]
 jne ifwl_bad
 mov rax,QWORD PTR [rdi+16]
 cmp rax,QWORD PTR [rsi+32]
 jne ifwl_bad
 cmp QWORD PTR [rsi+IFW_JOB+48],0
 je ifwl_bad
 mov DWORD PTR [rsi+IFW_JOB+68],0
 mov DWORD PTR [rsi+IFW_JOB+72],9
 lea rcx,[rsi+IFW_JOB]
 call boom_native_memory_service
 mov DWORD PTR [rdi+48],eax
 mov DWORD PTR [rsi+200],eax
 mov edx,DWORD PTR [rsi+IFW_JOB+80]
 mov DWORD PTR [rdi+52],edx
 mov DWORD PTR [rsi+204],edx
 mov DWORD PTR [rbx+152],edx
 xor r12d,r12d
 test eax,eax
 jnz ifwl_pending
 cmp QWORD PTR [rsi+IFW_JOB+48],0
 je ifwl_unlock
ifwl_pending:
 mov DWORD PTR [rsi+24],6
 mov r12d,12
ifwl_unlock:
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 lock dec DWORD PTR [rbx+136]
 lea rcx,[rbx+16]
 call ReleaseSRWLockShared
 mov QWORD PTR [rdi+16],0
 mov QWORD PTR [rdi+24],0
 mov DWORD PTR [rdi+40],0
 mov DWORD PTR [rdi+44],r12d
 mov DWORD PTR [rbx+148],r12d
 mov eax,r12d
 jmp ifwl_done
ifwl_ok_early:
 mov eax,DWORD PTR [rdi+44]
 jmp ifwl_done
ifwl_args:
 mov eax,3
 jmp ifwl_done
ifwl_bad:
 mov eax,5
ifwl_done:
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_inflater_owner_release ENDP

PUBLIC boom_inflater_owner_end
boom_inflater_owner_end PROC FRAME
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
 call ifw_pool_valid
 test eax,eax
 jz ifwe_bad
 test rsi,rsi
 jz ifwe_ok_early
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 lock inc DWORD PTR [rbx+136]
 mov rcx,rbx
 mov rdx,rsi
 call ifw_find
 test rax,rax
 jnz ifwe_found
 mov edi,edx
 jmp ifwe_unlock
ifwe_found:
 mov rsi,rax
 cmp QWORD PTR [rsi+16],0
 jne ifwe_busy
 mov DWORD PTR [rsi+24],4
 mov rcx,rbx
 mov rdx,rsi
 call ifw_free_record
 mov edi,eax
 jmp ifwe_unlock
ifwe_busy:
 mov edi,2
ifwe_unlock:
 lock dec DWORD PTR [rbx+136]
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rbx+148],edi
 mov eax,edi
 jmp ifwe_done
ifwe_ok_early:
 xor eax,eax
 jmp ifwe_done
ifwe_bad:
 mov eax,5
ifwe_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_inflater_owner_end ENDP

PUBLIC boom_inflater_owner_close
boom_inflater_owner_close PROC FRAME
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
 call ifw_pool_valid
 test eax,eax
 jz ifwx_bad_early
 mov eax,1
 xchg QWORD PTR [rbx+96],rax
 lea rcx,[rbx+16]
 call TryAcquireSRWLockExclusive
 test al,al
 jz ifwx_busy_early
 cmp DWORD PTR [rbx+136],0
 jne ifwx_busy
 mov DWORD PTR [rbx+140],2
 mov r12d,IFW_CAP
ifwx_loop:
 mov rsi,QWORD PTR [rbx+24]
 test rsi,rsi
 jz ifwx_empty
 mov rcx,rbx
 mov rdx,rsi
 call ifw_record_valid
 test eax,eax
 jz ifwx_bad
 cmp QWORD PTR [rsi+16],0
 jne ifwx_busy
 mov eax,DWORD PTR [rsi+24]
 test eax,eax
 jz ifwx_bad
 cmp eax,6
 ja ifwx_bad
 cmp eax,5
 je ifwx_release_record
 mov DWORD PTR [rsi+24],4
ifwx_release_record:
 mov rcx,rbx
 mov rdx,rsi
 call ifw_free_record
 mov edi,eax
 test eax,eax
 jnz ifwx_unlock
 dec r12d
 jnz ifwx_loop
 cmp QWORD PTR [rbx+24],0
 jne ifwx_bad
ifwx_empty:
 cmp QWORD PTR [rbx+32],0
 jne ifwx_bad
 cmp QWORD PTR [rbx+104],0
 jne ifwx_bad
 mov DWORD PTR [rbx+140],3
 xor edi,edi
 jmp ifwx_unlock
ifwx_bad:
 mov edi,5
 jmp ifwx_unlock
ifwx_busy:
 mov edi,2
ifwx_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rbx+148],edi
 mov eax,edi
 jmp ifwx_done
ifwx_busy_early:
 mov DWORD PTR [rbx+140],2
 mov DWORD PTR [rbx+148],2
 mov eax,2
 jmp ifwx_done
ifwx_bad_early:
 mov eax,5
ifwx_done:
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_inflater_owner_close ENDP
