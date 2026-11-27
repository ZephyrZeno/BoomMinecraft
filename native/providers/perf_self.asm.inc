; Original Perf source-bound registration/clock/self-counter subset.
; All native work is MASM. Explicit quiescent nonmoving GC; no stack scanner.
; Immutable source table is separately generated from original Class/C/Frame.
; Request slots have no Java oops. A retained Core token keeps its slot until
; real close retries release. No failure clears an outstanding native lease.
PERF_BYTES EQU 1048576
PERF_COUNTERS EQU 1024
PERF_REQUESTS EQU 256
PERF_STRIDE EQU 6144
PERF_JOB EQU 5376
.code
perf_lock PROC PRIVATE
 lea r11,boom_provider_perf_pool
pl_try:
 mov eax,1
 xchg DWORD PTR [r11+24],eax
 test eax,eax
 jz pl_got
pl_spin:
 pause
 cmp DWORD PTR [r11+24],0
 jne pl_spin
 jmp pl_try
pl_got:
 ret
perf_lock ENDP

PUBLIC boom_perf_owner_open
boom_perf_owner_open PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,176
 .allocstack 176
 .endprolog
 mov rsi,rcx
 lea rbx,boom_provider_perf_pool
 lea rax,boom_main_native_memory_owner
 cmp rsi,rax
 jne poo_bad
 mov rax,03130574D4E4F4F42h
 cmp QWORD PTR [rsi],rax
 jne poo_bad
 cmp DWORD PTR [rsi+8],128
 jne poo_bad
 cmp DWORD PTR [rsi+12],1
 jne poo_bad
 cmp DWORD PTR [rsi+24],1
 jne poo_closed
 call perf_lock
 cmp DWORD PTR [rbx],046524550h
 jne poo_bad_unlock
 cmp DWORD PTR [rbx+4],1
 jne poo_bad_unlock
 cmp DWORD PTR [rbx+8],256
 jne poo_bad_unlock
 cmp DWORD PTR [rbx+12],0
 je poo_cold
 cmp DWORD PTR [rbx+12],1
 jne poo_closed_unlock
 cmp QWORD PTR [rbx+32],rsi
 jne poo_bad_unlock
 cmp QWORD PTR [rbx+40],0
 je poo_bad_unlock
 cmp QWORD PTR [rbx+72],0
 jle poo_bad_unlock
 xor edi,edi
 jmp poo_unlock
poo_cold:
 lea rcx,[rsp+160]
 call QueryPerformanceFrequency
 test eax,eax
 jz poo_clock_error
 cmp QWORD PTR [rsp+160],0
 jle poo_clock_error
 lea rcx,[rsp+168]
 call QueryPerformanceCounter
 test eax,eax
 jz poo_clock_error
 lea rdi,[rsp+32]
 xor eax,eax
 mov ecx,16
 rep stosq
 mov QWORD PTR [rsp+32],rsi
 mov QWORD PTR [rsp+48],PERF_BYTES
 lea rcx,[rsp+32]
 call boom_native_memory_service
 mov edi,eax
 test eax,eax
 jnz poo_unlock
 mov rsi,QWORD PTR [rsp+72]
 test rsi,rsi
 jz poo_internal
 ; No Java/user can see the region before open publication.
 mov DWORD PTR [rsi],0C0C0FECAh
 mov DWORD PTR [rsi+4],01000201h
 mov QWORD PTR [rsi+8],0
 mov QWORD PTR [rsi+16],0
 mov DWORD PTR [rsi+24],32
 mov DWORD PTR [rsi+28],0
 mov rax,QWORD PTR [rsp+32]
 mov QWORD PTR [rbx+32],rax
 mov QWORD PTR [rbx+40],rsi
 mov QWORD PTR [rbx+48],PERF_BYTES
 mov rax,QWORD PTR [rsp+168]
 mov QWORD PTR [rbx+64],rax
 mov rax,QWORD PTR [rsp+160]
 mov QWORD PTR [rbx+72],rax
 mov QWORD PTR [rbx+80],32
 mov DWORD PTR [rbx+12],1
 inc QWORD PTR [rbx+168]
 xor edi,edi
 jmp poo_unlock
poo_internal:
 ; An impossible successful-null Core allocation is an explicit ABI failure;
 ; no backing pointer exists to lose. Nothing has been published.
 mov edi,5
 jmp poo_unlock
poo_clock_error:
 mov edi,20
 jmp poo_unlock
poo_bad_unlock:
 mov edi,5
 jmp poo_unlock
poo_closed_unlock:
 mov edi,9
poo_unlock:
 mov DWORD PTR [rbx+216],edi
 mov DWORD PTR [rbx+24],0
 mov eax,edi
 jmp poo_done
poo_bad:
 mov eax,5
 jmp poo_done
poo_closed:
 mov eax,9
poo_done:
 add rsp,176
 pop rdi
 pop rsi
 pop rbx
 ret
boom_perf_owner_open ENDP

PUBLIC boom_perf_owner_close
boom_perf_owner_close PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,160
 .allocstack 160
 .endprolog
 lea rbx,boom_provider_perf_pool
 call perf_lock
 inc QWORD PTR [rbx+160]
 cmp DWORD PTR [rbx+20],0
 jne poc_busy
 cmp DWORD PTR [rbx+12],3
 je poc_ok
 cmp DWORD PTR [rbx+12],0
 je poc_cold
 mov DWORD PTR [rbx+12],2
 lea rsi,perf_requests
 mov edi,PERF_REQUESTS
poc_slots:
 cmp DWORD PTR [rsi],1
 je poc_busy
 cmp QWORD PTR [rsi+PERF_JOB+48],0
 je poc_slot_empty
 lea rcx,[rsi+PERF_JOB]
 mov DWORD PTR [rcx+68],0
 mov DWORD PTR [rcx+72],9
 call boom_native_memory_service
 test eax,eax
 jnz poc_result
 cmp QWORD PTR [rsi+PERF_JOB+48],0
 jne poc_internal
poc_slot_empty:
 mov DWORD PTR [rsi],0
 add rsi,PERF_STRIDE
 dec edi
 jnz poc_slots
 cmp QWORD PTR [rbx+40],0
 je poc_cold
 lea rdi,[rsp+32]
 xor eax,eax
 mov ecx,16
 rep stosq
 mov rax,QWORD PTR [rbx+32]
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [rbx+40]
 mov QWORD PTR [rsp+40],rax
 mov DWORD PTR [rsp+104],2
 lea rcx,[rsp+32]
 call boom_native_memory_service
 test eax,eax
 jnz poc_result
 mov QWORD PTR [rbx+40],0
 mov QWORD PTR [rbx+48],0
poc_cold:
 mov DWORD PTR [rbx+12],3
poc_ok:
 xor eax,eax
 jmp poc_result
poc_busy:
 mov eax,2
 jmp poc_result
poc_internal:
 mov eax,5
poc_result:
 mov DWORD PTR [rbx+216],eax
 mov DWORD PTR [rbx+24],0
 add rsp,160
 pop rdi
 pop rsi
 pop rbx
 ret
boom_perf_owner_close ENDP

; Every service enters admission under the same close/publication lock.
; Context32 is never changed for any original pending kind/oop/VM plan.
PUBLIC boom_provider_perf_service
boom_provider_perf_service PROC FRAME
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
 mov rsi,rdx
 mov edi,r9d
 test rbx,rbx
 jz psvc_zero
 cmp DWORD PTR [rbx],0
 jne psvc_zero
 cmp QWORD PTR [rbx+16],0
 jne psvc_zero
 cmp QWORD PTR [rbx+24],0
 jne psvc_zero
 lea r12,boom_provider_perf_pool
 cmp r8,r12
 jne psvc_bad
 cmp DWORD PTR [r12],046524550h
 jne psvc_bad
 cmp DWORD PTR [r12+4],1
 jne psvc_bad
 cmp DWORD PTR [r12+8],256
 jne psvc_bad
 cmp edi,6
 ja psvc_bad
 test rsi,rsi
 jz psvc_bad
 call perf_lock
 cmp DWORD PTR [r12+12],1
 jne psvc_closed_unlock
 cmp QWORD PTR [r12+40],0
 je psvc_closed_unlock
 cmp DWORD PTR [r12+20],-1
 je psvc_closed_unlock
 test edi,edi
 jz psvc_admit
 cmp DWORD PTR [r12+16],1
 jne psvc_closed_unlock
 cmp QWORD PTR [r12+rdi*8+104],0
 je psvc_closed_unlock
psvc_admit:
 inc DWORD PTR [r12+20]
 mov DWORD PTR [r12+24],0
 mov rcx,rbx
 mov rdx,rsi
 mov r8,r12
 test edi,edi
 jz psvc_register
 call QWORD PTR [r12+rdi*8+104]
 jmp psvc_return
psvc_register:
 call perf_register
psvc_return:
 lock dec DWORD PTR [r12+20]
 jmp psvc_done
psvc_closed_unlock:
 mov DWORD PTR [r12+24],0
 mov DWORD PTR [rbx],20
 jmp psvc_zero
psvc_bad:
 mov DWORD PTR [rbx],7
psvc_zero:
 xor eax,eax
psvc_done:
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_perf_service ENDP

; Runtime consumes the same six original names/descriptors/Frames and actual
; backend addresses that the generator re-derives from the locked source.
perf_register PROC PRIVATE FRAME
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
 lea r12,boom_provider_perf_pool
 call perf_lock
 lea rsi,perf_registration_rows
 cmp QWORD PTR [r12+96],rsi
 jne preg_bad
 lea rax,PERF_CLASS
 cmp QWORD PTR [r12+104],rax
 jne preg_bad
 cmp DWORD PTR [r12+12],1
 jne preg_unsupported
 xor edi,edi
preg_validate:
 cmp DWORD PTR [rsi+76],0
 jne preg_bad
 lea eax,[rdi+1]
 cmp DWORD PTR [rsi+72],eax
 jne preg_bad
 cmp DWORD PTR [rsi+4],PERF_CLASS_ID
 jne preg_bad
 mov edx,0102h
 cmp edi,2
 jb preg_access
 mov edx,0101h
preg_access:
 cmp DWORD PTR [rsi+8],edx
 jne preg_bad
 cmp DWORD PTR [rsi+12],32
 jne preg_bad
 mov rax,QWORD PTR [rsi+16]
 test rax,rax
 jz preg_bad
 mov edx,DWORD PTR [rsi]
 cmp DWORD PTR [rax],edx
 jne preg_bad
 cmp DWORD PTR [rax+4],32
 jne preg_bad
 cmp DWORD PTR [rax+20],PERF_CLASS_ID
 jne preg_bad
 lea rax,PERF_CLASS
 cmp QWORD PTR [rsi+24],rax
 jne preg_bad
 lea rax,perf_expected_backends
 mov rax,QWORD PTR [rax+rdi*8]
 cmp QWORD PTR [rsi+32],rax
 jne preg_bad
 mov r13,rax
 mov rcx,QWORD PTR [rsi+40]
 mov edx,DWORD PTR [rsi+56]
 call perf_text_hash
 cmp eax,DWORD PTR [rsi+64]
 jne preg_bad
 mov rcx,QWORD PTR [rsi+48]
 mov edx,DWORD PTR [rsi+60]
 call perf_text_hash
 cmp eax,DWORD PTR [rsi+68]
 jne preg_bad
 cmp DWORD PTR [r12+16],0
 je preg_next
 cmp DWORD PTR [r12+16],1
 jne preg_bad
 cmp QWORD PTR [r12+rdi*8+112],r13
 jne preg_bad
preg_next:
 add rsi,80
 inc edi
 cmp edi,6
 jb preg_validate
 ; Publish only after every row validated; no partial six-slot success.
 lea rsi,perf_expected_backends
 xor edi,edi
preg_publish:
 mov rax,QWORD PTR [rsi+rdi*8]
 mov QWORD PTR [r12+rdi*8+112],rax
 inc edi
 cmp edi,6
 jb preg_publish
 mov DWORD PTR [r12+16],1
 mov DWORD PTR [r12+24],0
 xor eax,eax
 jmp preg_done
preg_bad:
 mov DWORD PTR [rbx],7
 jmp preg_unlock
preg_unsupported:
 mov DWORD PTR [rbx],20
preg_unlock:
 mov DWORD PTR [r12+24],0
 xor eax,eax
preg_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
perf_register ENDP

; UTF16 hash with bounded length and exact NUL terminator. Source immutable.
perf_text_hash PROC PRIVATE
 test rcx,rcx
 jz pth_bad
 test edx,edx
 jz pth_bad
 cmp edx,256
 ja pth_bad
 xor eax,eax
 xor r8d,r8d
pth_loop:
 movzx r9d,WORD PTR [rcx+r8*2]
 test r9d,r9d
 jz pth_bad
 imul eax,eax,31
 add eax,r9d
 inc r8d
 cmp r8d,edx
 jb pth_loop
 cmp WORD PTR [rcx+r8*2],0
 jne pth_bad
 ret
pth_bad:
 mov eax,0FFFFFFFFh
 ret
perf_text_hash ENDP

perf_high_counter PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 lea rcx,[rsp+32]
 call QueryPerformanceCounter
 test eax,eax
 jz phc_bad
 mov rax,QWORD PTR [rsp+32]
 sub rax,QWORD PTR [boom_provider_perf_pool+64]
 js phc_bad
 lock inc QWORD PTR [boom_provider_perf_pool+208]
 jmp phc_done
phc_bad:
 mov DWORD PTR [rbx],20
 xor eax,eax
phc_done:
 add rsp,48
 pop rbx
 ret
perf_high_counter ENDP

perf_high_frequency PROC PRIVATE
 mov rax,QWORD PTR [boom_provider_perf_pool+72]
 test rax,rax
 jle phf_bad
 lock inc QWORD PTR [boom_provider_perf_pool+208]
 ret
phf_bad:
 mov DWORD PTR [rcx],20
 xor eax,eax
 ret
perf_high_frequency ENDP

; Normal source constructor (JI,Object,MemorySegment)V, not the JJ mapping
; constructor and never host writes to address/capacity/Java initialization.
perf_new_buffer PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,80
 .allocstack 80
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov edi,r8d
 lea rcx,PERF_BUFFER_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne pnb_zero
 mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,PERF_BUFFER_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz pnb_zero
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],rsi
 mov QWORD PTR [rsp+48],rdi
 mov QWORD PTR [rsp+56],0
 mov QWORD PTR [rsp+64],0
 mov rcx,rbx
 lea rdx,[rsp+32]
 call PERF_BUFFER_CTOR
 cmp DWORD PTR [rbx],0
 jne pnb_zero
 mov rax,QWORD PTR [rsp+32]
 jmp pnb_done
pnb_zero:
 xor eax,eax
pnb_done:
 add rsp,80
 pop rdi
 pop rsi
 pop rbx
 ret
perf_new_buffer ENDP

perf_attach PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov esi,DWORD PTR [rdx+8]
 test esi,esi
 jz pat_self
 call GetCurrentProcessId
 cmp eax,esi
 jne pat_remote
pat_self:
 lock inc QWORD PTR [boom_provider_perf_pool+192]
 mov rcx,rbx
 mov rdx,QWORD PTR [boom_provider_perf_pool+40]
 mov r8d,PERF_BYTES
 call perf_new_buffer
 jmp pat_done
pat_remote:
 mov DWORD PTR [rbx],20
 xor eax,eax
pat_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
perf_attach ENDP

perf_detach PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,QWORD PTR [rdx+8]
 test rsi,rsi
 jz pdt_bad
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz pdt_bad
 mov rcx,rsi
 lea rdx,PERF_BUFFER_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz pdt_zero
 mov rax,QWORD PTR [boom_provider_perf_pool+40]
 cmp QWORD PTR [rsi+PERF_BUFFER_ADDRESS],rax
 jne pdt_unsupported
 cmp DWORD PTR [rsi+PERF_BUFFER_CAPACITY],PERF_BYTES
 jne pdt_unsupported
 lock inc QWORD PTR [boom_provider_perf_pool+200]
 jmp pdt_zero
pdt_unsupported:
 mov DWORD PTR [rbx],20
 jmp pdt_zero
pdt_bad:
 mov DWORD PTR [rbx],7
pdt_zero:
 xor eax,eax
 add rsp,40
 pop rsi
 pop rbx
 ret
perf_detach ENDP

; Claim a persistent native-only request. Job token can outlive a failed call.
perf_request PROC PRIVATE
 lea r10,perf_requests
 mov r9d,PERF_REQUESTS
prq_next:
 xor eax,eax
 mov r11d,1
 lock cmpxchg DWORD PTR [r10],r11d
 je prq_got
 add r10,PERF_STRIDE
 dec r9d
 jnz prq_next
 xor eax,eax
 ret
prq_got:
 mov rax,r10
 ret
perf_request ENDP

; rcx Context, rdx name oop, r8 request: source toCharArray then exact
; primitive heap-base/char[] validation. Convert original UTF16 to JNI MUTF8.
perf_name PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,72
 .allocstack 72
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov r12,r8
 test rsi,rsi
 jz pnm_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz pnm_bad
 mov rcx,rsi
 lea rdx,PERF_STRING_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz pnm_zero
 mov QWORD PTR [rsp+48],rsi
 mov rcx,rbx
 lea rdx,[rsp+48]
 call PERF_STRING_CHARS
 cmp DWORD PTR [rbx],0
 jne pnm_zero
 test rax,rax
 jz pnm_bad
 mov rdi,rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rdi
 xor r8d,r8d
 xor r9d,r9d
 lea rax,[rsp+56]
 mov QWORD PTR [rsp+32],rax
 call boom_primitive_heap_span
 test eax,eax
 jnz pnm_bad
 cmp QWORD PTR [rdi-8],261
 jne pnm_bad
 mov rax,QWORD PTR [rdi-16]
 shr rax,1
 cmp rax,1024
 ja pnm_unsupported
 mov DWORD PTR [r12+8],eax
 xor r10d,r10d
 xor r11d,r11d
pnm_convert:
 cmp r10d,DWORD PTR [r12+8]
 jae pnm_end
 movzx eax,WORD PTR [rdi+r10*2]
 mov WORD PTR [r12+r10*2+64],ax
 test eax,eax
 jz pnm_two
 cmp eax,07Fh
 ja pnm_large
 mov BYTE PTR [r12+r11+2112],al
 inc r11d
 jmp pnm_char_done
pnm_large:
 cmp eax,07FFh
 ja pnm_three
pnm_two:
 mov edx,eax
 shr edx,6
 or edx,0C0h
 mov BYTE PTR [r12+r11+2112],dl
 inc r11d
 and eax,03Fh
 or eax,080h
 mov BYTE PTR [r12+r11+2112],al
 inc r11d
 jmp pnm_char_done
pnm_three:
 mov edx,eax
 shr edx,12
 or edx,0E0h
 mov BYTE PTR [r12+r11+2112],dl
 inc r11d
 mov edx,eax
 shr edx,6
 and edx,03Fh
 or edx,080h
 mov BYTE PTR [r12+r11+2112],dl
 inc r11d
 and eax,03Fh
 or eax,080h
 mov BYTE PTR [r12+r11+2112],al
 inc r11d
pnm_char_done:
 inc r10d
 jmp pnm_convert
pnm_end:
 mov BYTE PTR [r12+r11+2112],0
 mov DWORD PTR [r12+12],r11d
 mov eax,1
 jmp pnm_done
pnm_null:
 mov rcx,rbx
 mov edx,1
 xor r8d,r8d
 xor r9d,r9d
 call perf_throw
 jmp pnm_zero
pnm_unsupported:
 mov DWORD PTR [rbx],20
 jmp pnm_zero
pnm_bad:
 mov DWORD PTR [rbx],7
pnm_zero:
 xor eax,eax
pnm_done:
 add rsp,72
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
perf_name ENDP

perf_create_long PROC PRIVATE FRAME
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
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 mov r13,rdx
 xor r12d,r12d
 ; Native C checks units before null name and duplicates before variability.
 mov eax,DWORD PTR [r13+24]
 dec eax
 cmp eax,5
 ja pcl_argument
 call perf_request
 test rax,rax
 jz pcl_unsupported
 mov r12,rax
 lea rdi,[r12+PERF_JOB]
 xor eax,eax
 mov ecx,16
 rep stosq
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+8]
 mov r8,r12
 call perf_name
 test eax,eax
 jz pcl_zero
 call perf_lock
 lea r15,boom_provider_perf_pool
 mov r14d,DWORD PTR [r15+88]
 cmp r14d,PERF_COUNTERS
 ja pcl_bad_unlock
 xor esi,esi
pcl_duplicates:
 cmp esi,r14d
 jae pcl_new
 mov eax,esi
 shl rax,5
 lea rdi,perf_counter_info
 add rdi,rax
 mov eax,DWORD PTR [r12+8]
 cmp DWORD PTR [rdi+4],eax
 jne pcl_next
 mov eax,esi
 shl rax,11
 lea rdi,perf_counter_names
 add rdi,rax
 lea rdx,[r12+64]
 xor ecx,ecx
pcl_compare:
 cmp ecx,DWORD PTR [r12+8]
 jae pcl_duplicate
 mov ax,WORD PTR [rdx+rcx*2]
 cmp WORD PTR [rdi+rcx*2],ax
 jne pcl_next
 inc ecx
 jmp pcl_compare
pcl_next:
 inc esi
 jmp pcl_duplicates
pcl_new:
 mov eax,DWORD PTR [r13+16]
 dec eax
 cmp eax,2
 ja pcl_argument_unlock
 cmp r14d,PERF_COUNTERS
 jae pcl_limit_unlock
 ; Entry20+MUTF8name+NUL, align data and total to8, scalar J has8 bytes.
 mov eax,DWORD PTR [r12+12]
 add eax,28
 and eax,-8
 mov QWORD PTR [r12+16],rax
 add eax,8
 mov QWORD PTR [r12+24],rax
 add rax,QWORD PTR [r15+80]
 jc pcl_limit_unlock
 cmp rax,PERF_BYTES
 ja pcl_limit_unlock
 mov rax,QWORD PTR [r15+32]
 mov QWORD PTR [r12+PERF_JOB],rax
 mov rax,QWORD PTR [r15+40]
 mov QWORD PTR [r12+PERF_JOB+8],rax
 mov QWORD PTR [r12+PERF_JOB+16],PERF_BYTES
 mov DWORD PTR [r12+PERF_JOB+68],2
 mov DWORD PTR [r12+PERF_JOB+72],8
 lea rcx,[r12+PERF_JOB]
 call boom_native_memory_service
 test eax,eax
 jnz pcl_limit_unlock
 mov rsi,QWORD PTR [r15+40]
 add rsi,QWORD PTR [r15+80]
 mov eax,DWORD PTR [r12+24]
 mov DWORD PTR [rsi],eax
 mov DWORD PTR [rsi+4],20
 mov DWORD PTR [rsi+8],0
 mov BYTE PTR [rsi+12],74
 mov BYTE PTR [rsi+13],0
 mov eax,DWORD PTR [r13+24]
 mov BYTE PTR [rsi+14],al
 mov eax,DWORD PTR [r13+16]
 mov BYTE PTR [rsi+15],al
 mov eax,DWORD PTR [r12+16]
 mov DWORD PTR [rsi+16],eax
 lea rdi,[rsi+20]
 lea rsi,[r12+2112]
 mov ecx,DWORD PTR [r12+12]
 inc ecx
 rep movsb
 ; F_Supported follows the original java./com.sun. prefix rule.
 mov rsi,QWORD PTR [r15+40]
 add rsi,QWORD PTR [r15+80]
 cmp DWORD PTR [r12+12],5
 jb pcl_flags_done
 cmp DWORD PTR [r12+2112],06176616Ah
 jne pcl_com
 cmp BYTE PTR [r12+2116],46
 je pcl_supported
pcl_com:
 cmp DWORD PTR [r12+12],8
 jb pcl_flags_done
 mov rax,02E6E75732E6D6F63h
 cmp QWORD PTR [r12+2112],rax
 jne pcl_flags_done
pcl_supported:
 mov BYTE PTR [rsi+13],1
pcl_flags_done:
 mov rdi,rsi
 add rdi,QWORD PTR [r12+16]
 mov QWORD PTR [r12+32],rdi
 mov rax,QWORD PTR [r13+32]
 mov QWORD PTR [rdi],rax
 ; Private registry data never trusts writable exported PerfData bytes.
 mov eax,r14d
 shl rax,5
 lea rdi,perf_counter_info
 add rdi,rax
 mov DWORD PTR [rdi],1
 mov eax,DWORD PTR [r12+8]
 mov DWORD PTR [rdi+4],eax
 mov rax,QWORD PTR [r12+32]
 mov QWORD PTR [rdi+8],rax
 mov DWORD PTR [rdi+16],8
 mov DWORD PTR [rdi+20],74
 mov QWORD PTR [rdi+24],rsi
 mov eax,r14d
 shl rax,11
 lea rdi,perf_counter_names
 add rdi,rax
 lea rsi,[r12+64]
 mov ecx,DWORD PTR [r12+8]
 rep movsw
 mov rax,QWORD PTR [r12+24]
 add QWORD PTR [r15+80],rax
 inc DWORD PTR [r15+88]
 mov rsi,QWORD PTR [r15+40]
 mov eax,DWORD PTR [r15+80]
 mov DWORD PTR [rsi+8],eax
 mov eax,DWORD PTR [r15+88]
 mov DWORD PTR [rsi+28],eax
 lea rcx,[rsp+32]
 call QueryPerformanceCounter
 test eax,eax
 jz pcl_timestamp_fail
 mov rax,QWORD PTR [rsp+32]
 sub rax,QWORD PTR [r15+64]
 mov QWORD PTR [rsi+16],rax
 mov DWORD PTR [rsp+40],0
 jmp pcl_release
pcl_timestamp_fail:
 mov DWORD PTR [rsp+40],20
pcl_release:
 lea rcx,[r12+PERF_JOB]
 mov DWORD PTR [rcx+68],0
 mov DWORD PTR [rcx+72],9
 call boom_native_memory_service
 test eax,eax
 jnz pcl_token_retained
 cmp QWORD PTR [r12+PERF_JOB+48],0
 jne pcl_token_retained
 lock inc QWORD PTR [r15+176]
 mov DWORD PTR [r15+24],0
 cmp DWORD PTR [rsp+40],0
 jne pcl_unsupported
 mov rcx,rbx
 mov rdx,QWORD PTR [r12+32]
 mov r8d,8
 call perf_new_buffer
 mov r14,rax
 jmp pcl_request_done
pcl_token_retained:
 mov DWORD PTR [r12],2
 jmp pcl_limit_unlock
pcl_duplicate:
 mov DWORD PTR [r15+24],0
 mov rcx,rbx
 mov edx,3
 lea r8,perf_duplicate_long
 mov r9d,PERF_DUP_LONG_LENGTH
 call perf_throw
 jmp pcl_zero
pcl_argument_unlock:
 mov DWORD PTR [r15+24],0
pcl_argument:
 mov rcx,rbx
 xor edx,edx
 xor r8d,r8d
 xor r9d,r9d
 call perf_throw
 jmp pcl_zero
pcl_bad_unlock:
 mov DWORD PTR [r15+24],0
 mov DWORD PTR [rbx],7
 jmp pcl_zero
pcl_limit_unlock:
 mov DWORD PTR [r15+24],0
pcl_unsupported:
 mov DWORD PTR [rbx],20
pcl_zero:
 xor r14d,r14d
pcl_request_done:
 test r12,r12
 jz pcl_done
 cmp QWORD PTR [r12+PERF_JOB+48],0
 jne pcl_keep_token
 mov DWORD PTR [r12],0
 jmp pcl_done
pcl_keep_token:
 mov DWORD PTR [r12],2
pcl_done:
 mov rax,r14
 add rsp,64
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
perf_create_long ENDP

; Source table is fully registered, while string-counter backend is an
; explicit unsupported20 boundary in this first clock/long/self subset.
perf_create_bytes PROC PRIVATE
 mov DWORD PTR [rcx],20
 xor eax,eax
 ret
perf_create_bytes ENDP

; rcx Context, edx 0 IAE(),1 NPE(),2 OOME(),3 IAE(String),r8/r9 UTF16.
; All ordinary Java callbacks occur outside both locks and native leases.
perf_throw PROC PRIVATE FRAME
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
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 mov esi,edx
 mov r12,r8
 mov r13d,r9d
 lea rdi,PERF_IAE_CLASS
 cmp esi,1
 jne pth_not_null
 lea rdi,PERF_NPE_CLASS
pth_not_null:
 cmp esi,2
 jne pth_class
 lea rdi,PERF_OOME_CLASS
pth_class:
 mov rcx,rdi
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne pthrow_zero
 cmp esi,3
 jne pth_no_message
 mov rcx,rbx
 lea rdx,boom_java_platform_properties_pool
 mov r8,r12
 mov r9d,r13d
 call boom_java_property_copy
 test rax,rax
 jz pthrow_zero
 mov QWORD PTR [rsp+40],rax
pth_no_message:
 lea rdx,PERF_IAE_LAYOUT
 cmp esi,1
 jne pth_not_null_layout
 lea rdx,PERF_NPE_LAYOUT
pth_not_null_layout:
 cmp esi,2
 jne pth_layout
 lea rdx,PERF_OOME_LAYOUT
pth_layout:
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz pthrow_zero
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 cmp esi,1
 je pth_npe
 cmp esi,2
 je pth_oome
 cmp esi,3
 je pth_iae_message
 call PERF_IAE_CTOR
 jmp pth_set
pth_npe:
 call PERF_NPE_CTOR
 jmp pth_set
pth_oome:
 call PERF_OOME_CTOR
 jmp pth_set
pth_iae_message:
 call PERF_IAE_MESSAGE_CTOR
pth_set:
 cmp DWORD PTR [rbx],0
 jne pthrow_zero
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+32]
 lea r8,boom_runtime_type_map
 lea r9,PERF_THROWABLE_TYPE
 call boom_exception_set32
pthrow_zero:
 xor eax,eax
 add rsp,64
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
perf_throw ENDP
