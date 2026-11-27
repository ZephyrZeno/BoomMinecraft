; NEW shared-NFIO RAF extension. Include after the complete original FIS source.
; Original fir_* helpers, macros, locks, Slot32/FD roots/39399 remain unchanged.
; Cleanup helpers never inspect or overwrite Java Context32, even if pending.
; Quiescent/nonmoving-GC scope matches the original FIS native callbacks.

RFIO_MAGIC EQU 04F494652h
RFIO_REQUESTS EQU 256
RFIO_REQUEST_BYTES EQU 64
RFIO_MAX_HANDLES EQU 4096
.data
ALIGN 8
PUBLIC boom_provider_random_access_file_pool
boom_provider_random_access_file_pool DWORD RFIO_MAGIC,1,64,0
 DWORD 63,0,RFIO_MAX_HANDLES,0
 QWORD OFFSET boom_provider_file_input_pool
 QWORD OFFSET boom_random_access_file_init_ids_pool
 QWORD OFFSET boom_provider_file_bootstrap_pool
 QWORD 0
; Native-only request records: stateD0/opD4/statusD8/flagsD12, scratchQ16,
; scratchBytesQ24, opaqueContextQ32, resultQ40, ownerSlotQ48,reservedQ56.
; No Java oop resides here. Failed HeapFree retains the native scratch pointer.
ALIGN 8
rfio_requests BYTE 16384 DUP(0)
ALIGN 4
rfio_drainer DWORD 0
rfio_last_drain_os DWORD 0
.const
rfio_negative_seek WORD 78,101,103,97,116,105,118,101,32,115,101,101,107,32,111,102,102,115,101,116
.code

; Trusted internal Job96 -> exact old Slot32 RAX / exact root cell RDX, or0.
; The actual original registry lock is already held. This performs no callback.
rfio_job_slot PROC PRIVATE
 mov r9d,DWORD PTR [rcx+24]
 cmp r9d,RFIO_MAX_HANDLES
 jae rjs_bad
 lea rax,boom_file_input_owners
 mov r10,r9
 shl r10,5
 add rax,r10
 cmp rax,QWORD PTR [rcx+16]
 jne rjs_bad
 lea rdx,boom_file_input_owner_roots
 lea rdx,[rdx+r9*8]
 mov r10,QWORD PTR [rcx+8]
 test r10,r10
 jz rjs_bad
 cmp QWORD PTR [rdx],r10
 jne rjs_bad
 ret
rjs_bad:
 xor eax,eax
 xor edx,edx
 ret
rfio_job_slot ENDP

; Internal reserve(Job96*), after real FD/registration validation outside lock.
; Claim the original root/state4 before path callbacks or CreateFileW.
rfio_reserve PROC PRIVATE FRAME
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
 mov rsi,QWORD PTR [rbx+8]
 mov edi,3
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 cmp QWORD PTR [rsi+FIR_FD_HANDLE],-1
 jne rres_unlock
 cmp DWORD PTR [rsi+FIR_FD_INT],-1
 jne rres_unlock
 mov rdx,rsi
 call fir_find
 test rax,rax
 jnz rres_unlock
 lea r8,boom_file_input_owner_roots
 lea r9,boom_file_input_owners
 xor ecx,ecx
rres_scan:
 cmp QWORD PTR [r8+rcx*8],0
 jne rres_next
 cmp DWORD PTR [r9],0
 jne rres_next
 cmp DWORD PTR [r9+4],0
 jne rres_invariant
 cmp QWORD PTR [r9+8],0
 jne rres_invariant
 cmp QWORD PTR [r9+16],0
 jne rres_invariant
 cmp QWORD PTR [r9+24],0
 jne rres_invariant
 mov QWORD PTR [r8+rcx*8],rsi
 mov DWORD PTR [r9],4
 mov QWORD PTR [rbx+16],r9
 mov DWORD PTR [rbx+24],ecx
 mov DWORD PTR [rbx+28],4
 xor edi,edi
 jmp rres_unlock
rres_next:
 add r9,32
 inc ecx
 cmp ecx,RFIO_MAX_HANDLES
 jb rres_scan
 mov edi,7
 jmp rres_unlock
rres_invariant:
 mov edi,5
rres_unlock:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rbx+52],edi
 mov eax,edi
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
rfio_reserve ENDP

; Publish only this service's fresh CreateFileW-owned HANDLE into its own4 slot.
; Unknown/external/standard handles are never accepted from Java argv.
rfio_publish PROC PRIVATE FRAME
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
 xor esi,esi
 mov edi,5
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rcx,rbx
 call rfio_job_slot
 test rax,rax
 jz rpub_unlock
 mov rsi,rax
 cmp DWORD PTR [rsi],4
 jne rpub_unlock
 cmp DWORD PTR [rsi+4],0
 jne rpub_unlock
 cmp QWORD PTR [rsi+8],0
 jne rpub_unlock
 mov r8,QWORD PTR [rbx+8]
 cmp QWORD PTR [r8+FIR_FD_HANDLE],-1
 jne rpub_unlock
 cmp DWORD PTR [r8+FIR_FD_INT],-1
 jne rpub_unlock
 mov rax,QWORD PTR [rbx+32]
 test rax,rax
 jz rpub_unlock
 cmp rax,-1
 je rpub_unlock
 mov QWORD PTR [rsi+8],rax
 mov QWORD PTR [r8+FIR_FD_HANDLE],rax
 mov BYTE PTR [r8+FIR_FD_APPEND],0
 lock inc QWORD PTR [boom_file_input_live_handles]
 mov DWORD PTR [rsi],1
 mov DWORD PTR [rbx+28],1
 xor edi,edi
rpub_unlock:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 test edi,edi
 jnz rpub_store
 mov rcx,rsi
 call WakeByAddressAll
rpub_store:
 mov DWORD PTR [rbx+52],edi
 mov eax,edi
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
rfio_publish ENDP

; Abort own opening4 reservation regardless of the original Context's status.
; A fresh HANDLE is first durably claimed as closing2, never published failed3
; while the abort itself could still close it. That prevents a double close.
rfio_abort PROC PRIVATE FRAME
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
 xor esi,esi
 xor r12d,r12d
 mov edi,5
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rcx,rbx
 call rfio_job_slot
 test rax,rax
 jz rab_unlock_return
 mov rsi,rax
 cmp DWORD PTR [rsi],4
 jne rab_unlock_return
 cmp DWORD PTR [rsi+4],0
 jne rab_unlock_return
 cmp QWORD PTR [rsi+8],0
 jne rab_unlock_return
 mov r12,QWORD PTR [rbx+32]
 test r12,r12
 jz rab_no_handle
 cmp r12,-1
 je rab_no_handle
 mov QWORD PTR [rsi+8],r12
 mov DWORD PTR [rsi],2
 mov DWORD PTR [rbx+28],2
 lock inc QWORD PTR [boom_file_input_live_handles]
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rcx,r12
 call CloseHandle
 test eax,eax
 jnz rab_closed
 call GetLastError
 mov DWORD PTR [rbx+56],eax
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov DWORD PTR [rsi],3
 mov DWORD PTR [rbx+28],3
 mov edi,12
 jmp rab_unlock_wake
rab_closed:
 lock dec QWORD PTR [boom_file_input_live_handles]
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rcx,rbx
 call rfio_job_slot
 test rax,rax
 jz rab_unlock_return
 cmp rax,rsi
 jne rab_unlock_return
 cmp DWORD PTR [rsi],2
 jne rab_unlock_return
 cmp QWORD PTR [rsi+8],r12
 jne rab_unlock_return
rab_no_handle:
 mov QWORD PTR [rdx],0
 mov QWORD PTR [rsi+8],0
 mov DWORD PTR [rsi],0
 mov DWORD PTR [rbx+28],0
 mov QWORD PTR [rbx+32],0
 xor edi,edi
rab_unlock_wake:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rcx,rsi
 call WakeByAddressAll
 jmp rab_store
rab_unlock_return:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
rab_store:
 mov DWORD PTR [rbx+52],edi
 mov eax,edi
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
rfio_abort ENDP

; Borrow exact rooted FD and recorded HANDLE. Caller takes IO lock afterwards.
rfio_borrow PROC PRIVATE FRAME
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
 mov rsi,QWORD PTR [rbx+8]
 mov edi,1
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rdx,rsi
 call fir_find
 test rax,rax
 jz rbor_unlock
 cmp DWORD PTR [rax],1
 jne rbor_unlock
 mov edi,5
 mov r8,QWORD PTR [rax+8]
 test r8,r8
 jz rbor_unlock
 cmp r8,-1
 je rbor_unlock
 cmp QWORD PTR [rsi+FIR_FD_HANDLE],r8
 jne rbor_unlock
 cmp DWORD PTR [rsi+FIR_FD_INT],-1
 jne rbor_unlock
 mov edi,7
 cmp DWORD PTR [rax+4],-1
 je rbor_unlock
 inc DWORD PTR [rax+4]
 mov QWORD PTR [rbx+16],rax
 mov DWORD PTR [rbx+24],ecx
 mov DWORD PTR [rbx+28],1
 mov QWORD PTR [rbx+32],r8
 xor edi,edi
rbor_unlock:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rbx+52],edi
 mov eax,edi
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
rfio_borrow ENDP

; Call ONLY after this same OS thread released IO SRW. Never guard on pending.
rfio_release PROC PRIVATE FRAME
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
 xor esi,esi
 mov edi,5
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov rcx,rbx
 call rfio_job_slot
 test rax,rax
 jz rrel_unlock
 mov rsi,rax
 cmp DWORD PTR [rsi+4],0
 je rrel_unlock
 mov r8,QWORD PTR [rbx+32]
 cmp QWORD PTR [rsi+8],r8
 jne rrel_unlock
 lock dec DWORD PTR [rsi+4]
 setz al
 movzx eax,al
 mov QWORD PTR [rbx+40],rax
 xor edi,edi
rrel_unlock:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 test edi,edi
 jnz rrel_store
 cmp QWORD PTR [rbx+40],1
 jne rrel_store
 lea rcx,[rsi+4]
 call WakeByAddressAll
rrel_store:
 mov DWORD PTR [rbx+52],edi
 mov eax,edi
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
rfio_release ENDP

; Reserve native-only request storage, increment active under original lock.
; RCX Context pointer is opaque diagnostic data, never used after retirement.
rfio_request_claim PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 lea r10,boom_provider_random_access_file_pool
 cmp DWORD PTR [r10+12],0
 jne rrq_none
 cmp DWORD PTR [r10+20],-1
 je rrq_none
 lea r11,rfio_requests
 xor edx,edx
rrq_scan:
 cmp DWORD PTR [r11],0
 jne rrq_next
 cmp QWORD PTR [r11+16],0
 jne rrq_next
 xor eax,eax
 mov ecx,8
 mov r8,r11
rrq_zero:
 mov QWORD PTR [r8],rax
 add r8,8
 dec ecx
 jnz rrq_zero
 mov QWORD PTR [r11+32],rbx
 mov DWORD PTR [r11],1
 inc DWORD PTR [r10+20]
 mov rbx,r11
 jmp rrq_unlock
rrq_next:
 add r11,RFIO_REQUEST_BYTES
 inc edx
 cmp edx,RFIO_REQUESTS
 jb rrq_scan
rrq_none:
 xor ebx,ebx
rrq_unlock:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rax,rbx
 add rsp,32
 pop rbx
 ret
rfio_request_claim ENDP

; Native scratch cleanup before Java errors; active stays held across callbacks.
rfio_request_cleanup PROC PRIVATE FRAME
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
 xor edi,edi
 mov rsi,QWORD PTR [rbx+16]
 test rsi,rsi
 jz rrc_return
 call GetProcessHeap
 mov rcx,rax
 xor edx,edx
 mov r8,rsi
 call HeapFree
 test eax,eax
 jz rrt_free_failed
 lock dec QWORD PTR [boom_file_input_owned_buffers]
 mov QWORD PTR [rbx+16],0
 mov QWORD PTR [rbx+24],0
 jmp rrc_return
rrt_free_failed:
 mov edi,12
rrc_return:
 mov eax,edi
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
rfio_request_cleanup ENDP

; Retire only after every Java callback; never gate cleanup on Context pending.
rfio_request_retire PROC PRIVATE FRAME
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
 xor edi,edi
 cmp QWORD PTR [rbx+16],0
 je rrt_lock
 mov edi,12
rrt_lock:
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov QWORD PTR [rbx+32],0
 lea r10,boom_provider_random_access_file_pool
 cmp DWORD PTR [rbx],1
 jne rrt_invariant
 cmp DWORD PTR [r10+20],0
 je rrt_invariant
 dec DWORD PTR [r10+20]
 cmp DWORD PTR [rbx+12],0
 je rrt_status_ready
 mov edi,12
rrt_status_ready:
 test edi,edi
 jnz rrt_pending
 xor eax,eax
 mov ecx,8
 mov r8,rbx
rrt_zero:
 mov QWORD PTR [r8],rax
 add r8,8
 dec ecx
 jnz rrt_zero
 jmp rrt_unlock
rrt_pending:
 mov DWORD PTR [rbx],2
 mov DWORD PTR [rbx+8],edi
 jmp rrt_unlock
rrt_invariant:
 mov edi,5
rrt_unlock:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov eax,edi
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
rfio_request_retire ENDP

; RFIO_RAF_FD_MAP is a source-derived TEXTEQU supplied by the composite tool.
; All native IO/registry locks and borrowed references end before fir_throw.
PUBLIC boom_provider_random_access_file_service
boom_provider_random_access_file_service PROC FRAME
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
 sub rsp,488
 .allocstack 488
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov DWORD PTR [rsp+256],r9d
 xor ebp,ebp
 xor r12d,r12d
 xor r13d,r13d
 xor r14d,r14d
 xor r15d,r15d
 lea r10,[rsp+64]
 xor eax,eax
 mov ecx,28
rfs_zero_locals:
 mov QWORD PTR [r10],rax
 add r10,8
 dec ecx
 jnz rfs_zero_locals
 ; The loop ends at287 and cleared the saved operation; publish it afterwards.
 mov DWORD PTR [rsp+256],r9d
 mov DWORD PTR [rsp+196],-1
 test rbx,rbx
 jz rfs_return
 cmp DWORD PTR [rbx],0
 jne rfs_return
 cmp QWORD PTR [rbx+16],0
 jne rfs_return
 cmp QWORD PTR [rbx+24],0
 jne rfs_return
 lea rax,boom_provider_random_access_file_pool
 cmp rdi,rax
 jne rfs_bad
 cmp DWORD PTR [rdi],RFIO_MAGIC
 jne rfs_bad
 cmp DWORD PTR [rdi+4],1
 jne rfs_bad
 cmp DWORD PTR [rdi+8],64
 jne rfs_bad
 cmp DWORD PTR [rdi+16],63
 jne rfs_bad
 cmp DWORD PTR [rdi+24],RFIO_MAX_HANDLES
 jne rfs_bad
 cmp DWORD PTR [rdi+28],0
 jne rfs_bad
 lea rax,boom_provider_file_input_pool
 cmp QWORD PTR [rdi+32],rax
 jne rfs_bad
 lea rax,boom_random_access_file_init_ids_pool
 cmp QWORD PTR [rdi+40],rax
 jne rfs_bad
 lea rax,boom_provider_file_bootstrap_pool
 cmp QWORD PTR [rdi+48],rax
 jne rfs_bad
 cmp QWORD PTR [rdi+56],0
 jne rfs_bad
 test rsi,rsi
 jz rfs_bad
 cmp DWORD PTR [rsp+256],6
 jae rfs_unsupported
 call fir_registration
 test eax,eax
 jz rfs_unsupported
 lea r10,boom_random_access_file_init_ids_pool
 cmp DWORD PTR [r10],044494652h
 jne rfs_unsupported
 cmp DWORD PTR [r10+4],1
 jne rfs_unsupported
 cmp DWORD PTR [r10+8],128
 jne rfs_unsupported
 cmp DWORD PTR [r10+12],1
 jne rfs_unsupported
 lea rax,RFIO_RAF_FD_MAP
 cmp QWORD PTR [r10+64],rax
 jne rfs_unsupported
 mov rcx,rbx
 call rfio_request_claim
 test rax,rax
 jz rfs_unsupported
 mov r15,rax
 mov eax,DWORD PTR [rsp+256]
 mov DWORD PTR [r15+4],eax
 mov QWORD PTR [rsp+80],rbx
 cmp QWORD PTR [rsi],0
 je rfs_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,QWORD PTR [rsi]
 call boom_heap_contains
 test eax,eax
 jz rfs_bad
 ; Preserve original readBytes null/bounds/zero ordering before FD lookup.
 cmp DWORD PTR [rsp+256],2
 jne rfs_get_fd
 mov r14,QWORD PTR [rsi+8]
 test r14,r14
 jz rfs_array_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz rfs_bad
 cmp QWORD PTR [r14-8],264
 jne rfs_bad
 cmp DWORD PTR [r14-20],0
 jne rfs_bad
 movsxd rax,DWORD PTR [rsi+16]
 movsxd rdx,DWORD PTR [rsi+24]
 test rax,rax
 js rfs_bounds
 test rdx,rdx
 js rfs_bounds
 add rdx,rax
 cmp rdx,QWORD PTR [r14-16]
 ja rfs_bounds
 add r14,rax
 mov QWORD PTR [rsp+224],r14
 mov eax,DWORD PTR [rsi+24]
 mov DWORD PTR [rsp+220],eax
 test eax,eax
 jz rfs_cleanup
rfs_get_fd:
 mov rcx,QWORD PTR [rsi]
 mov rdx,rbx
 lea r10,boom_random_access_file_init_ids_pool
 call QWORD PTR [r10+64]
 cmp DWORD PTR [rbx],0
 jne rfs_cleanup
 test rax,rax
 jz rfs_unsupported
 mov rbp,QWORD PTR [rax]
 test rbp,rbp
 jz rfs_closed
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rbp
 call boom_heap_contains
 test eax,eax
 jz rfs_bad
 mov rcx,rbp
 lea rdx,FIR_FD_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz rfs_cleanup
 mov QWORD PTR [rsp+88],rbp
 cmp DWORD PTR [rsp+256],0
 je rfs_open
 lea rcx,[rsp+80]
 call rfio_borrow
 test eax,eax
 jz rfs_borrowed
 cmp eax,1
 je rfs_closed
 jmp rfs_unsupported
rfs_borrowed:
 mov r13,QWORD PTR [rsp+96]
 mov r14,QWORD PTR [rsp+112]
 mov DWORD PTR [rsp+184],1
 mov QWORD PTR [r15+48],r13
 mov QWORD PTR [r15+40],r14
 lea rcx,[r13+16]
 call AcquireSRWLockExclusive
 mov DWORD PTR [rsp+188],1
 cmp DWORD PTR [rsp+256],2
 jbe rfs_read
 cmp DWORD PTR [rsp+256],3
 je rfs_position
 cmp DWORD PTR [rsp+256],4
 je rfs_seek
 jmp rfs_length
rfs_open:
 cmp DWORD PTR [rsi+16],1
 jne rfs_unsupported
 mov rax,QWORD PTR [rsi+8]
 mov QWORD PTR [rsp+248],rax
 lea rcx,[rsp+80]
 call rfio_reserve
 test eax,eax
 jnz rfs_unsupported
 mov DWORD PTR [rsp+192],1
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+8]
 call fir_path
 mov DWORD PTR [rsp+200],edx
 test rax,rax
 jnz rfs_path_ready
 cmp DWORD PTR [rbx],0
 jne rfs_cleanup
 mov DWORD PTR [rsp+196],1
 jmp rfs_cleanup
rfs_path_ready:
 mov QWORD PTR [r15+16],rax
 mov QWORD PTR [r15+24],131104
 mov rcx,rax
 mov edx,080000000h
 mov r8d,3
 xor r9d,r9d
 mov DWORD PTR [rsp+32],3
 mov DWORD PTR [rsp+40],128
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 je rfs_open_failed
 test rax,rax
 jz rfs_open_failed
 mov QWORD PTR [rsp+112],rax
 mov rcx,rax
 call GetFileType
 cmp eax,1
 jne rfs_unsupported
 lea rcx,[rsp+80]
 call rfio_publish
 test eax,eax
 jnz rfs_unsupported
 mov DWORD PTR [rsp+192],0
 jmp rfs_cleanup
rfs_open_failed:
 call GetLastError
 mov DWORD PTR [rsp+200],eax
 mov DWORD PTR [rsp+196],1
 jmp rfs_cleanup
rfs_read:
 lea rdx,[rsp+288]
 mov r8d,1
 cmp DWORD PTR [rsp+256],1
 je rfs_read_call
 mov r8d,DWORD PTR [rsp+220]
 cmp r8d,8192
 jbe rfs_read_call
 call GetProcessHeap
 mov rcx,rax
 xor edx,edx
 mov r8d,DWORD PTR [rsp+220]
 call HeapAlloc
 test rax,rax
 jz rfs_oom
 mov QWORD PTR [r15+16],rax
 mov ecx,DWORD PTR [rsp+220]
 mov QWORD PTR [r15+24],rcx
 lock inc QWORD PTR [boom_file_input_owned_buffers]
 mov rdx,rax
 mov r8d,DWORD PTR [rsp+220]
rfs_read_call:
 mov QWORD PTR [rsp+240],rdx
 mov rcx,r14
 lea r9,[rsp+232]
 mov DWORD PTR [rsp+232],0
 mov QWORD PTR [rsp+32],0
 call ReadFile
 test eax,eax
 jz rfs_read_failed
 mov eax,DWORD PTR [rsp+232]
 test eax,eax
 jz rfs_eof
 cmp DWORD PTR [rsp+256],1
 jne rfs_read_array
 cmp eax,1
 jne rfs_unsupported
 mov rdx,QWORD PTR [rsp+240]
 movzx r12d,BYTE PTR [rdx]
 jmp rfs_cleanup
rfs_read_array:
 cmp eax,DWORD PTR [rsp+220]
 ja rfs_unsupported
 mov r12d,eax
 mov QWORD PTR [rsp+264],rsi
 mov QWORD PTR [rsp+280],rdi
 mov rsi,QWORD PTR [rsp+240]
 mov rdi,QWORD PTR [rsp+224]
 mov ecx,eax
 rep movsb
 mov rsi,QWORD PTR [rsp+264]
 mov rdi,QWORD PTR [rsp+280]
 jmp rfs_cleanup
rfs_eof:
 mov r12,-1
 jmp rfs_cleanup
rfs_read_failed:
 call GetLastError
 mov DWORD PTR [rsp+200],eax
 mov DWORD PTR [rsp+196],0
 lea rax,fir_read_error
 mov QWORD PTR [rsp+208],rax
 mov DWORD PTR [rsp+216],10
 jmp rfs_cleanup
rfs_position:
 mov rcx,r14
 xor edx,edx
 lea r8,[rsp+272]
 mov r9d,1
 call SetFilePointerEx
 test eax,eax
 jz rfs_seek_failed
 mov r12,QWORD PTR [rsp+272]
 jmp rfs_cleanup
rfs_seek:
 mov rdx,QWORD PTR [rsi+8]
 test rdx,rdx
 js rfs_negative_seek
 mov rcx,r14
 xor r8d,r8d
 xor r9d,r9d
 call SetFilePointerEx
 test eax,eax
 jz rfs_seek_failed
 jmp rfs_cleanup
rfs_negative_seek:
 mov DWORD PTR [rsp+196],0
 lea rax,rfio_negative_seek
 mov QWORD PTR [rsp+208],rax
 mov DWORD PTR [rsp+216],20
 jmp rfs_cleanup
rfs_seek_failed:
 call GetLastError
 mov DWORD PTR [rsp+200],eax
 mov DWORD PTR [rsp+196],0
 lea rax,fir_seek_error
 mov QWORD PTR [rsp+208],rax
 mov DWORD PTR [rsp+216],10
 jmp rfs_cleanup
rfs_length:
 mov rcx,r14
 lea rdx,[rsp+272]
 call GetFileSizeEx
 test eax,eax
 jz rfs_length_failed
 mov r12,QWORD PTR [rsp+272]
 jmp rfs_cleanup
rfs_length_failed:
 call GetLastError
 mov DWORD PTR [rsp+200],eax
 mov DWORD PTR [rsp+196],0
 lea rax,fir_length_error
 mov QWORD PTR [rsp+208],rax
 mov DWORD PTR [rsp+216],16
 jmp rfs_cleanup
rfs_closed:
 mov DWORD PTR [rsp+196],0
 lea rax,fir_closed
 mov QWORD PTR [rsp+208],rax
 mov DWORD PTR [rsp+216],13
 jmp rfs_cleanup
rfs_array_null:
 mov DWORD PTR [rsp+196],2
 jmp rfs_cleanup
rfs_bounds:
 mov DWORD PTR [rsp+196],3
 jmp rfs_cleanup
rfs_null:
 mov DWORD PTR [rbx],4
 jmp rfs_cleanup
rfs_bad:
 mov DWORD PTR [rbx],7
 jmp rfs_cleanup
rfs_oom:
 mov DWORD PTR [rbx],3
 jmp rfs_cleanup
rfs_unsupported:
 cmp DWORD PTR [rbx],0
 jne rfs_cleanup
 cmp QWORD PTR [rbx+16],0
 jne rfs_cleanup
 cmp QWORD PTR [rbx+24],0
 jne rfs_cleanup
 mov DWORD PTR [rbx],20
rfs_cleanup:
 cmp DWORD PTR [rsp+188],0
 je rfs_cleanup_borrow
 lea rcx,[r13+16]
 call ReleaseSRWLockExclusive
 mov DWORD PTR [rsp+188],0
rfs_cleanup_borrow:
 cmp DWORD PTR [rsp+184],0
 je rfs_cleanup_reserve
 lea rcx,[rsp+80]
 call rfio_release
 test eax,eax
 jz rfs_cleanup_borrow_done
 or DWORD PTR [r15+12],1
 jmp rfs_cleanup_mark
rfs_cleanup_borrow_done:
 mov DWORD PTR [rsp+184],0
 jmp rfs_cleanup_reserve
rfs_cleanup_mark:
 cmp DWORD PTR [rbx],0
 jne rfs_cleanup_reserve
 cmp QWORD PTR [rbx+16],0
 jne rfs_cleanup_reserve
 cmp QWORD PTR [rbx+24],0
 jne rfs_cleanup_reserve
 mov DWORD PTR [rbx],20
rfs_cleanup_reserve:
 cmp DWORD PTR [rsp+192],0
 je rfs_cleanup_request
 lea rcx,[rsp+80]
 call rfio_abort
 test eax,eax
 jz rfs_cleanup_request
 cmp eax,12
 je rfs_cleanup_abort_mark
 test r15,r15
 jz rfs_cleanup_abort_mark
 or DWORD PTR [r15+12],2
 mov rax,QWORD PTR [rsp+96]
 mov QWORD PTR [r15+48],rax
 mov rax,QWORD PTR [rsp+112]
 mov QWORD PTR [r15+40],rax
rfs_cleanup_abort_mark:
 cmp DWORD PTR [rbx],0
 jne rfs_cleanup_request
 cmp QWORD PTR [rbx+16],0
 jne rfs_cleanup_request
 cmp QWORD PTR [rbx+24],0
 jne rfs_cleanup_request
 mov DWORD PTR [rbx],20
rfs_cleanup_request:
 test r15,r15
 jz rfs_throw
 mov rcx,r15
 call rfio_request_cleanup
 test eax,eax
 jz rfs_throw
 cmp DWORD PTR [rbx],0
 jne rfs_throw
 cmp QWORD PTR [rbx+16],0
 jne rfs_throw
 cmp QWORD PTR [rbx+24],0
 jne rfs_throw
 mov DWORD PTR [rbx],20
rfs_throw:
 cmp DWORD PTR [rbx],0
 jne rfs_zero_result
 cmp QWORD PTR [rbx+16],0
 jne rfs_zero_result
 cmp QWORD PTR [rbx+24],0
 jne rfs_zero_result
 mov r8d,DWORD PTR [rsp+196]
 cmp r8d,-1
 je rfs_finish_request
 mov rcx,rbx
 lea rdx,boom_provider_file_input_pool
 mov r9d,DWORD PTR [rsp+200]
 mov rax,QWORD PTR [rsp+248]
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [rsp+208]
 mov QWORD PTR [rsp+40],rax
 mov eax,DWORD PTR [rsp+216]
 mov DWORD PTR [rsp+48],eax
 call fir_throw
rfs_zero_result:
 xor r12d,r12d
rfs_finish_request:
 test r15,r15
 jz rfs_return
 mov rcx,r15
 call rfio_request_retire
 test eax,eax
 jz rfs_return
 cmp DWORD PTR [rbx],0
 jne rfs_finish_failed
 cmp QWORD PTR [rbx+16],0
 jne rfs_finish_failed
 cmp QWORD PTR [rbx+24],0
 jne rfs_finish_failed
 mov DWORD PTR [rbx],20
rfs_finish_failed:
 xor r12d,r12d
rfs_return:
 mov rax,r12
 add rsp,8680
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_provider_random_access_file_service ENDP

; This is not a concurrently callable ordinary close. All Java/native callers
; and owned workers must have ended. It never force-unlocks another OS thread.
; No Java callback or Main Context access occurs, even on a failed cleanup.
PUBLIC boom_random_access_file_io_drain
boom_random_access_file_io_drain PROC FRAME
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
 sub rsp,168
 .allocstack 168
 .endprolog
 xor eax,eax
 mov edx,1
 lock cmpxchg DWORD PTR [rfio_drainer],edx
 jne rfd_busy_without_ownership
 lea r13,boom_provider_random_access_file_pool
 cmp DWORD PTR [r13],RFIO_MAGIC
 jne rfd_bad
 cmp DWORD PTR [r13+4],1
 jne rfd_bad
 cmp DWORD PTR [r13+8],64
 jne rfd_bad
 cmp DWORD PTR [r13+12],2
 ja rfd_bad
 mov DWORD PTR [rfio_last_drain_os],0
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 cmp DWORD PTR [r13+12],0
 jne rfd_admission_closed
 mov DWORD PTR [r13+12],1
rfd_admission_closed:
 cmp DWORD PTR [r13+20],0
 jne rfd_busy_locked
 lea rsi,rfio_requests
 xor r12d,r12d
rfd_request_preflight:
 cmp DWORD PTR [rsi],1
 je rfd_busy_locked
 cmp DWORD PTR [rsi],2
 ja rfd_bad_locked
 cmp QWORD PTR [rsi+32],0
 jne rfd_bad_locked
 cmp DWORD PTR [rsi],0
 jne rfd_request_preflight_next
 cmp QWORD PTR [rsi+16],0
 jne rfd_bad_locked
 cmp DWORD PTR [rsi+12],0
 jne rfd_bad_locked
rfd_request_preflight_next:
 add rsi,RFIO_REQUEST_BYTES
 inc r12d
 cmp r12d,RFIO_REQUESTS
 jb rfd_request_preflight
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 lea rsi,rfio_requests
 xor r12d,r12d
rfd_request:
 cmp DWORD PTR [rsi],0
 je rfd_request_next
 cmp DWORD PTR [rsi],2
 jne rfd_busy
 mov eax,DWORD PTR [rsi+12]
 test eax,0FFFFFFFCh
 jnz rfd_bad
 test eax,eax
 jz rfd_request_scratch
 ; Reconstruct a still-owned internal cleanup job from stable original roots.
 ; A retained borrow prevents its owner slot from being freed or reused.
 lea r10,[rsp+32]
 xor eax,eax
 mov ecx,12
rfd_zero_job:
 mov QWORD PTR [r10],rax
 add r10,8
 dec ecx
 jnz rfd_zero_job
 mov r15,QWORD PTR [rsi+48]
 lea rax,boom_file_input_owners
 cmp r15,rax
 jb rfd_bad
 mov rdx,r15
 sub rdx,rax
 test edx,31
 jnz rfd_bad
 cmp rdx,131072
 jae rfd_bad
 shr rdx,5
 mov DWORD PTR [rsp+56],edx
 mov QWORD PTR [rsp+48],r15
 lea rax,boom_file_input_owner_roots
 mov rax,QWORD PTR [rax+rdx*8]
 test rax,rax
 jz rfd_bad
 mov QWORD PTR [rsp+40],rax
 mov rax,QWORD PTR [rsi+40]
 mov QWORD PTR [rsp+64],rax
 cmp QWORD PTR [r15+16],0
 jne rfd_busy
 test DWORD PTR [rsi+12],1
 jz rfd_request_abort
 lea rcx,[rsp+32]
 call rfio_release
 test eax,eax
 jnz rfd_cleanup_status
 and DWORD PTR [rsi+12],0FFFFFFFEh
rfd_request_abort:
 test DWORD PTR [rsi+12],2
 jz rfd_request_scratch
 lea rcx,[rsp+32]
 call rfio_abort
 test eax,eax
 jz rfd_request_abort_done
 cmp eax,12
 jne rfd_cleanup_status
 ; The failed owned HANDLE is now tracked by original slot.state3, not here.
 and DWORD PTR [rsi+12],0FFFFFFFDh
 jmp rfd_cleanup_status
rfd_request_abort_done:
 and DWORD PTR [rsi+12],0FFFFFFFDh
rfd_request_scratch:
 mov rcx,rsi
 call rfio_request_cleanup
 test eax,eax
 jnz rfd_cleanup_status
 cmp DWORD PTR [rsi+12],0
 jne rfd_bad
 xor eax,eax
 mov ecx,8
 mov r10,rsi
rfd_clear_request:
 mov QWORD PTR [r10],rax
 add r10,8
 dec ecx
 jnz rfd_clear_request
rfd_request_next:
 add rsi,RFIO_REQUEST_BYTES
 inc r12d
 cmp r12d,RFIO_REQUESTS
 jb rfd_request
 ; Preflight every original owner before closing any of them. No live IO lock
 ; or borrow is stolen. Opening4/closing2 has an actual other owner: retain VM.
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 lea rsi,boom_file_input_owners
 lea rdi,boom_file_input_owner_roots
 xor r12d,r12d
rfd_owner_preflight:
 mov eax,DWORD PTR [rsi]
 cmp eax,2
 je rfd_busy_locked
 cmp eax,4
 je rfd_busy_locked
 cmp eax,3
 ja rfd_bad_locked
 cmp DWORD PTR [rsi+4],0
 jne rfd_busy_locked
 cmp QWORD PTR [rsi+16],0
 jne rfd_busy_locked
 cmp QWORD PTR [rsi+24],0
 jne rfd_bad_locked
 test eax,eax
 jnz rfd_owner_present
 cmp QWORD PTR [rdi],0
 jne rfd_bad_locked
 cmp QWORD PTR [rsi+8],0
 jne rfd_bad_locked
 jmp rfd_owner_preflight_next
rfd_owner_present:
 cmp QWORD PTR [rdi],0
 je rfd_bad_locked
 cmp QWORD PTR [rsi+8],0
 je rfd_bad_locked
 cmp QWORD PTR [rsi+8],-1
 je rfd_bad_locked
rfd_owner_preflight_next:
 add rsi,32
 add rdi,8
 inc r12d
 cmp r12d,RFIO_MAX_HANDLES
 jb rfd_owner_preflight
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 lea rsi,boom_file_input_owners
 lea rdi,boom_file_input_owner_roots
 xor r12d,r12d
rfd_owner:
 cmp DWORD PTR [rsi],0
 je rfd_owner_next
 mov rbp,QWORD PTR [rdi]
 mov r14,QWORD PTR [rsi+8]
 ; Validate real source FD using a separate local Context, with no registry
 ; lock held. Its kind/PC/method never aliases the original Main Context.
 lea r10,[rsp+128]
 xor eax,eax
 mov QWORD PTR [r10],rax
 mov QWORD PTR [r10+8],rax
 mov QWORD PTR [r10+16],rax
 mov QWORD PTR [r10+24],rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rbp
 call boom_heap_contains
 test eax,eax
 jz rfd_bad
 mov rcx,rbp
 lea rdx,FIR_FD_LAYOUT
 lea r8,[rsp+128]
 call boom_object_check
 test rax,rax
 jz rfd_bad
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 cmp QWORD PTR [rdi],rbp
 jne rfd_bad_locked
 cmp QWORD PTR [rsi+8],r14
 jne rfd_bad_locked
 cmp DWORD PTR [rsi+4],0
 jne rfd_busy_locked
 cmp QWORD PTR [rsi+16],0
 jne rfd_busy_locked
 cmp DWORD PTR [rsi],1
 je rfd_live_owner
 cmp DWORD PTR [rsi],3
 jne rfd_busy_locked
 cmp QWORD PTR [rbp+FIR_FD_HANDLE],-1
 je rfd_claim_close
 cmp QWORD PTR [rbp+FIR_FD_HANDLE],r14
 jne rfd_bad_locked
 jmp rfd_claim_close
rfd_live_owner:
 cmp QWORD PTR [rbp+FIR_FD_HANDLE],r14
 jne rfd_bad_locked
rfd_claim_close:
 mov DWORD PTR [rsi],2
 mov QWORD PTR [rbp+FIR_FD_HANDLE],-1
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rcx,r14
 call CloseHandle
 test eax,eax
 jnz rfd_owner_closed
 call GetLastError
 mov DWORD PTR [rfio_last_drain_os],eax
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 mov DWORD PTR [rsi],3
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rcx,rsi
 call WakeByAddressAll
 mov eax,12
 jmp rfd_done
rfd_owner_closed:
 lock dec QWORD PTR [boom_file_input_live_handles]
 lea rcx,fir_registry_lock
 call AcquireSRWLockExclusive
 cmp QWORD PTR [rdi],rbp
 jne rfd_bad_locked
 cmp DWORD PTR [rsi],2
 jne rfd_bad_locked
 cmp QWORD PTR [rsi+8],r14
 jne rfd_bad_locked
 mov QWORD PTR [rdi],0
 mov QWORD PTR [rsi+8],0
 mov DWORD PTR [rsi],0
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
 mov rcx,rsi
 call WakeByAddressAll
rfd_owner_next:
 add rsi,32
 add rdi,8
 inc r12d
 cmp r12d,RFIO_MAX_HANDLES
 jb rfd_owner
 cmp QWORD PTR [boom_file_input_live_handles],0
 jne rfd_bad
 ; Unknown legacy fir_path internal HeapFree failure is not magically fixed.
 ; Its original positive counter still blocks heap teardown and false success.
 cmp QWORD PTR [boom_file_input_owned_buffers],0
 jne rfd_retained
 cmp DWORD PTR [r13+20],0
 jne rfd_busy
 mov DWORD PTR [r13+12],2
 xor eax,eax
 jmp rfd_done
rfd_busy_locked:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
rfd_busy:
 mov eax,170
 jmp rfd_done
rfd_bad_locked:
 lea rcx,fir_registry_lock
 call ReleaseSRWLockExclusive
rfd_bad:
 mov eax,20
 jmp rfd_done
rfd_retained:
 mov eax,12
 jmp rfd_done
rfd_cleanup_status:
 test eax,eax
 jnz rfd_done
 mov eax,20
rfd_done:
 mov DWORD PTR [rfio_drainer],0
 jmp rfd_return
rfd_busy_without_ownership:
 mov eax,170
rfd_return:
 add rsp,168
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_random_access_file_io_drain ENDP
