; Native-only GetFileAttributesEx0. Span metadata is persistent across failures.
; Caller uses the original static Frame(ctx,argv,pool,operation0).
; No Java fields or class state are written here; error helper executes Java.
EXTERN boom_native_memory_span_acquire:PROC
EXTERN boom_native_memory_span_release:PROC
EXTERN boom_windows_nio_throw_error:PROC
EXTERN boom_provider_owned_unsafe_pool:BYTE
EXTERN GetFileAttributesExW:PROC
EXTERN GetLastError:PROC
EXTERN GetTickCount64:PROC
EXTERN Sleep:PROC
WF_SLOT_COUNT EQU 256
WF_SLOT_BYTES EQU 192
.data
ALIGN 8
PUBLIC boom_provider_windows_nio_file_attributes_pool
; WFAT64/1: magic0,abi4,bytes8,state12;slots16,roots24,count32,stride36;
; publication lock40,active44,sequence48,pending56,drainer60.
; state0 admits calls;state1 drains/retries;state2 closed. No restart in-process.
boom_provider_windows_nio_file_attributes_pool DWORD 054414657h,1,64,0
 QWORD OFFSET boom_windows_nio_attributes_slots
 QWORD OFFSET boom_windows_nio_attributes_throwable_roots
 DWORD WF_SLOT_COUNT,WF_SLOT_BYTES,0,0
 QWORD 0
 DWORD 0,0
ALIGN 8
PUBLIC boom_windows_nio_attributes_slots
boom_windows_nio_attributes_slots BYTE 49152 DUP(0)
ALIGN 8
PUBLIC boom_windows_nio_attributes_throwable_roots
boom_windows_nio_attributes_throwable_roots QWORD 256 DUP(0)
.const
PUBLIC boom_windows_nio_attributes_throwable_root_count
boom_windows_nio_attributes_throwable_root_count QWORD 256
.code

wf_pool_valid PROC PRIVATE
 xor eax,eax
 lea r10,boom_provider_windows_nio_file_attributes_pool
 cmp rcx,r10
 jne wfp_return
 cmp DWORD PTR [r10],054414657h
 jne wfp_return
 cmp DWORD PTR [r10+4],1
 jne wfp_return
 cmp DWORD PTR [r10+8],64
 jne wfp_return
 cmp DWORD PTR [r10+12],2
 ja wfp_return
 lea r11,boom_windows_nio_attributes_slots
 cmp QWORD PTR [r10+16],r11
 jne wfp_return
 lea r11,boom_windows_nio_attributes_throwable_roots
 cmp QWORD PTR [r10+24],r11
 jne wfp_return
 cmp DWORD PTR [r10+32],WF_SLOT_COUNT
 jne wfp_return
 cmp DWORD PTR [r10+36],WF_SLOT_BYTES
 jne wfp_return
 cmp DWORD PTR [r10+60],1
 ja wfp_return
 mov eax,1
wfp_return:
 ret
wf_pool_valid ENDP

wf_lock PROC PRIVATE
 lea r10,boom_provider_windows_nio_file_attributes_pool
wfl_again:
 mov eax,1
 xchg DWORD PTR [r10+40],eax
 test eax,eax
 jz wfl_done
wfl_wait:
 pause
 cmp DWORD PTR [r10+40],0
 jne wfl_wait
 jmp wfl_again
wfl_done:
 ret
wf_lock ENDP

; -> RAX persistent slot or0; RDX its separate zero Java root cell.
wf_claim PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 call wf_lock
 cmp DWORD PTR [r10+12],0
 jne wfc_none
 cmp DWORD PTR [r10+60],0
 jne wfc_none
 cmp QWORD PTR [r10+48],-1
 je wfc_none
 lea r9,boom_windows_nio_attributes_slots
 lea r11,boom_windows_nio_attributes_throwable_roots
 xor ecx,ecx
wfc_scan:
 imul rdx,rcx,WF_SLOT_BYTES
 lea r8,[r9+rdx]
 cmp DWORD PTR [r8+128],0
 jne wfc_next
 cmp QWORD PTR [r8+32],0
 jne wfc_next
 cmp QWORD PTR [r8+96],0
 jne wfc_next
 cmp QWORD PTR [r11+rcx*8],0
 jne wfc_next
 xor eax,eax
 xor edx,edx
wfc_zero:
 mov QWORD PTR [r8+rdx*8],rax
 inc edx
 cmp edx,24
 jb wfc_zero
 mov DWORD PTR [r8+128],1
 inc DWORD PTR [r10+44]
 inc QWORD PTR [r10+48]
 mov rax,QWORD PTR [r10+48]
 mov QWORD PTR [r8+152],rax
 mov DWORD PTR [r10+40],0
 mov rax,r8
 lea rdx,[r11+rcx*8]
 jmp wfc_return
wfc_next:
 inc ecx
 cmp ecx,WF_SLOT_COUNT
 jb wfc_scan
wfc_none:
 mov DWORD PTR [r10+40],0
 xor eax,eax
 xor edx,edx
wfc_return:
 add rsp,40
 ret
wf_claim ENDP

; (Span64*) retries only busy2 with token0, outside every owner/pool lock.
wf_acquire PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 call GetTickCount64
 mov rsi,rax
wfa_again:
 mov rcx,rbx
 call boom_native_memory_span_acquire
 cmp eax,2
 jne wfa_return
 cmp QWORD PTR [rbx+32],0
 jne wfa_return
 call GetTickCount64
 sub rax,rsi
 cmp rax,2000
 jae wfa_busy
 mov ecx,1
 call Sleep
 jmp wfa_again
wfa_busy:
 mov eax,2
wfa_return:
 add rsp,40
 pop rsi
 pop rbx
 ret
wf_acquire ENDP

; (persistent slot*) -> first actual release error, output before input.
; Failed releases preserve Span tokens. Never discard storage here.
wf_release_spans PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov DWORD PTR [rbx+140],0
 lea rcx,[rbx+64]
 call boom_native_memory_span_release
 mov DWORD PTR [rbx+140],eax
 mov rcx,rbx
 call boom_native_memory_span_release
 cmp DWORD PTR [rbx+140],0
 jne wfr_return
 mov DWORD PTR [rbx+140],eax
wfr_return:
 mov eax,DWORD PTR [rbx+140]
 add rsp,32
 pop rbx
 ret
wf_release_spans ENDP

; (slot,rootCell) retires only a fully released request. Opaque Context pointer
; is never retained after return. No Java root is blindly cleared on failure.
wf_retire PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 call wf_lock
 mov QWORD PTR [rbx+144],0
 cmp DWORD PTR [rbx+128],1
 jne wft_bad
 cmp DWORD PTR [r10+44],0
 je wft_bad
 cmp QWORD PTR [rbx+32],0
 jne wft_pending
 cmp QWORD PTR [rbx+96],0
 jne wft_pending
 cmp DWORD PTR [rbx+140],0
 jne wft_pending
 cmp QWORD PTR [rsi],0
 jne wft_pending
 xor eax,eax
 xor ecx,ecx
wft_zero:
 mov QWORD PTR [rbx+rcx*8],rax
 inc ecx
 cmp ecx,24
 jb wft_zero
 dec DWORD PTR [r10+44]
 jmp wft_unlock
wft_pending:
 mov DWORD PTR [rbx+128],2
 dec DWORD PTR [r10+44]
 inc DWORD PTR [r10+56]
wft_bad:
 mov eax,20
wft_unlock:
 mov DWORD PTR [r10+40],0
 add rsp,40
 pop rsi
 pop rbx
 ret
wf_retire ENDP

PUBLIC boom_provider_windows_nio_file_attributes_service
boom_provider_windows_nio_file_attributes_service PROC FRAME
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
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,72
 .allocstack 72
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov r13,r8
 xor esi,esi
 test rbx,rbx
 jz wfs_done
 cmp DWORD PTR [rbx],0
 jne wfs_done
 cmp QWORD PTR [rbx+16],0
 jne wfs_done
 cmp QWORD PTR [rbx+24],0
 jne wfs_done
 test r12,r12
 jz wfs_bad_argument
 test r9d,r9d
 jnz wfs_unsupported
 mov rcx,r13
 call wf_pool_valid
 test eax,eax
 jz wfs_bad_argument
 lea r10,boom_provider_owned_unsafe_pool
 cmp DWORD PTR [r10],04E574F55h
 jne wfs_unsupported
 cmp DWORD PTR [r10+4],1
 jne wfs_unsupported
 cmp DWORD PTR [r10+16],1
 jne wfs_unsupported
 cmp DWORD PTR [r10+20],32
 jne wfs_unsupported
 cmp QWORD PTR [r10+24],0
 jne wfs_unsupported
 mov r14,QWORD PTR [r10+8]
 test r14,r14
 jz wfs_unsupported
 test r14b,7
 jnz wfs_unsupported
 call wf_claim
 test rax,rax
 jz wfs_unsupported
 mov rsi,rax
 mov QWORD PTR [rsp+64],rdx
 mov QWORD PTR [rsi+144],rbx
 mov DWORD PTR [rsp+48],20
 mov QWORD PTR [rsi],r14
 mov rax,QWORD PTR [r12]
 mov QWORD PTR [rsi+8],rax
 mov QWORD PTR [rsi+16],2
 mov DWORD PTR [rsi+48],1
 mov QWORD PTR [rsi+64],r14
 mov rax,QWORD PTR [r12+8]
 mov QWORD PTR [rsi+72],rax
 mov QWORD PTR [rsi+80],36
 mov DWORD PTR [rsi+112],1
 mov rcx,rsi
 call wf_acquire
 test eax,eax
 jnz wfs_acquire_failed
 lea rcx,[rsi+64]
 call wf_acquire
 test eax,eax
 jnz wfs_acquire_failed
 ; Source wrapper holds distinct NativeBuffers. Two readonly probes detect
 ; private aliases without waiting on our own read lease for a write upgrade.
 mov rbp,QWORD PTR [rsi+104]
 cmp rbp,QWORD PTR [rsi+40]
 je wfs_cleanup
 lea rcx,[rsi+64]
 call boom_native_memory_span_release
 test eax,eax
 jnz wfs_cleanup
 mov DWORD PTR [rsi+112],2
 lea rcx,[rsi+64]
 call wf_acquire
 test eax,eax
 jnz wfs_acquire_failed
 cmp rbp,QWORD PTR [rsi+104]
 jne wfs_cleanup
 ; Scan only within the actual held input allocation, never page padding.
 mov rdi,QWORD PTR [rsi+24]
 shr rdi,1
 mov rdx,QWORD PTR [rsi+8]
wfs_find_zero:
 test rdi,rdi
 jz wfs_unterminated
 cmp WORD PTR [rdx],0
 je wfs_call_OS
 add rdx,2
 dec rdi
 jmp wfs_find_zero
wfs_call_OS:
 mov DWORD PTR [rsi+164],1
 mov rcx,QWORD PTR [rsi+8]
 xor edx,edx
 mov r8,QWORD PTR [rsi+72]
 call GetFileAttributesExW
 mov DWORD PTR [rsi+136],eax
 test eax,eax
 jnz wfs_cleanup
 call GetLastError
 mov DWORD PTR [rsi+132],eax
 jmp wfs_cleanup
wfs_unterminated:
 mov DWORD PTR [rsp+48],7
 jmp wfs_cleanup
wfs_acquire_failed:
 cmp eax,3
 jne wfs_cleanup
 mov DWORD PTR [rsp+48],7
wfs_cleanup:
 mov rcx,rsi
 call wf_release_spans
 test eax,eax
 jnz wfs_set_failure
 cmp DWORD PTR [rsi+164],1
 jne wfs_set_failure
 cmp DWORD PTR [rsi+136],0
 jne wfs_retire
 ; Native resources are released before executing the original Java ctor.
 mov rcx,rbx
 mov edx,DWORD PTR [rsi+132]
 mov r8,QWORD PTR [rsp+64]
 call boom_windows_nio_throw_error
 jmp wfs_retire
wfs_set_failure:
 cmp DWORD PTR [rbx],0
 jne wfs_retire
 cmp QWORD PTR [rbx+16],0
 jne wfs_retire
 cmp QWORD PTR [rbx+24],0
 jne wfs_retire
 mov eax,DWORD PTR [rsp+48]
 mov DWORD PTR [rbx],eax
wfs_retire:
 mov rcx,rsi
 mov rdx,QWORD PTR [rsp+64]
 call wf_retire
 test eax,eax
 jz wfs_done
 cmp DWORD PTR [rbx],0
 jne wfs_done
 cmp QWORD PTR [rbx+16],0
 jne wfs_done
 cmp QWORD PTR [rbx+24],0
 jne wfs_done
wfs_unsupported:
 mov DWORD PTR [rbx],20
 jmp wfs_done
wfs_bad_argument:
 mov DWORD PTR [rbx],7
wfs_done:
 xor eax,eax
 add rsp,72
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_windows_nio_file_attributes_service ENDP

; No Java or native callers may remain. Serialized drain is retryable; any
; active/pending root or unreleased token prevents VM/Owner destruction.
PUBLIC boom_windows_nio_attributes_drain
boom_windows_nio_attributes_drain PROC FRAME
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
 lea rcx,boom_provider_windows_nio_file_attributes_pool
 call wf_pool_valid
 test eax,eax
 jz wfd_bad
 lea r13,boom_provider_windows_nio_file_attributes_pool
 xor eax,eax
 mov edx,1
 lock cmpxchg DWORD PTR [r13+60],edx
 jne wfd_busy
 call wf_lock
 cmp DWORD PTR [r13+12],0
 jne wfd_admission_closed
 mov DWORD PTR [r13+12],1
wfd_admission_closed:
 cmp DWORD PTR [r13+44],0
 jne wfd_active
 mov DWORD PTR [r13+40],0
 lea rsi,boom_windows_nio_attributes_slots
 lea rdi,boom_windows_nio_attributes_throwable_roots
 xor r12d,r12d
wfd_slot:
 cmp DWORD PTR [rsi+128],0
 je wfd_free
 cmp DWORD PTR [rsi+128],2
 jne wfd_pending_active
 mov rcx,rsi
 call wf_release_spans
 test eax,eax
 jnz wfd_failed
 cmp QWORD PTR [rsi+32],0
 jne wfd_bad_pending
 cmp QWORD PTR [rsi+96],0
 jne wfd_bad_pending
 cmp QWORD PTR [rdi],0
 jne wfd_bad_pending
 cmp DWORD PTR [r13+56],0
 je wfd_bad_pending
 dec DWORD PTR [r13+56]
 xor eax,eax
 xor ecx,ecx
wfd_zero:
 mov QWORD PTR [rsi+rcx*8],rax
 inc ecx
 cmp ecx,24
 jb wfd_zero
wfd_free:
 cmp QWORD PTR [rsi+32],0
 jne wfd_bad_pending
 cmp QWORD PTR [rsi+96],0
 jne wfd_bad_pending
 cmp QWORD PTR [rdi],0
 jne wfd_bad_pending
 add rsi,WF_SLOT_BYTES
 add rdi,8
 inc r12d
 cmp r12d,WF_SLOT_COUNT
 jb wfd_slot
 cmp DWORD PTR [r13+56],0
 jne wfd_bad_pending
 cmp DWORD PTR [r13+44],0
 jne wfd_bad_pending
 mov DWORD PTR [r13+12],2
 xor eax,eax
 jmp wfd_release_drainer
wfd_active:
 mov DWORD PTR [r13+40],0
wfd_pending_active:
 mov eax,170
 jmp wfd_release_drainer
wfd_bad_pending:
 mov eax,20
wfd_failed:
wfd_release_drainer:
 mov DWORD PTR [r13+60],0
 jmp wfd_done
wfd_busy:
 mov eax,170
 jmp wfd_done
wfd_bad:
 mov eax,87
wfd_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_windows_nio_attributes_drain ENDP
