; Shadow pure-MASM writable native owner. Frozen ABI: abi.json v1.
; Caller supplies trusted Owner128/Job128 metadata, never arbitrary host objects.
; All payload accesses are range-checked against this owner's live records.
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN GetLastError:PROC
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC

NM_MAGIC EQU 03130574D4E4F4F42h

.code

; Leaf helpers use only Win64 volatile registers. No DF changes, no hidden heap.
nm_valid_owner PROC PRIVATE
 test rcx,rcx
 jz nmvo_bad
 test cl,7
 jnz nmvo_bad
 mov rax,NM_MAGIC
 cmp QWORD PTR [rcx],rax
 jne nmvo_bad
 cmp DWORD PTR [rcx+8],128
 jne nmvo_bad
 cmp DWORD PTR [rcx+12],1
 jne nmvo_bad
 mov eax,1
 ret
nmvo_bad:
 xor eax,eax
 ret
nm_valid_owner ENDP

; RCX owner, RDX address, R8 bytes. RAX record, EDX status.
; Only a range BEGINNING inside an allocation can be a bounded hit.
nm_find_range PROC PRIVATE
 test r8,r8
 js nmfr_args
 mov rax,rdx
 add rax,r8
 jc nmfr_args
 mov r9,QWORD PTR [rcx+64]
 mov r10d,DWORD PTR [rcx+28]
nmfr_loop:
 test r10d,r10d
 jz nmfr_miss
 cmp DWORD PTR [r9+40],0
 je nmfr_next
 mov r11,QWORD PTR [r9]
 cmp rdx,r11
 jb nmfr_next
 mov rax,rdx
 sub rax,r11
 cmp rax,QWORD PTR [r9+8]
 jae nmfr_next
 cmp DWORD PTR [r9+40],1
 jne nmfr_closed
 mov r11,QWORD PTR [r9+8]
 sub r11,rax
 cmp r8,r11
 ja nmfr_args
 mov rax,r9
 xor edx,edx
 ret
nmfr_next:
 add r9,64
 dec r10d
 jmp nmfr_loop
nmfr_miss:
 mov edx,1
 xor eax,eax
 ret
nmfr_args:
 mov edx,3
 xor eax,eax
 ret
nmfr_closed:
 mov edx,9
 xor eax,eax
 ret
nm_find_range ENDP

nm_free_record PROC PRIVATE
 mov rax,QWORD PTR [rcx+64]
 mov edx,DWORD PTR [rcx+28]
nmfre_loop:
 test edx,edx
 jz nmfre_none
 cmp DWORD PTR [rax+40],0
 je nmfre_return
 add rax,64
 dec edx
 jmp nmfre_loop
nmfre_none:
 xor eax,eax
nmfre_return:
 ret
nm_free_record ENDP

nm_clear_record PROC PRIVATE
 xor eax,eax
 mov QWORD PTR [rcx],rax
 mov QWORD PTR [rcx+8],rax
 mov QWORD PTR [rcx+16],rax
 mov QWORD PTR [rcx+24],rax
 mov QWORD PTR [rcx+32],rax
 mov QWORD PTR [rcx+40],rax
 mov QWORD PTR [rcx+48],rax
 mov QWORD PTR [rcx+56],rax
 ret
nm_clear_record ENDP

; RCX source, RDX destination, R8 bytes, R9D=0 auto unit or swap2/4/8.
; Full-element load before store; chosen direction also handles partial overlap.
; Plain auto unit is the common source/destination/length alignment (8/4/2/1).
nm_move PROC PRIVATE
 test r8,r8
 jz nmm_return
 xor r11d,r11d
 test r9d,r9d
 jnz nmm_swap
 mov rax,rcx
 or rax,rdx
 or rax,r8
 mov r9d,8
 test al,7
 jz nmm_unit
 mov r9d,4
 test al,3
 jz nmm_unit
 mov r9d,2
 test al,1
 jz nmm_unit
 mov r9d,1
 jmp nmm_unit
nmm_swap:
 mov r11d,1
nmm_unit:
 mov r10,r9
 cmp rdx,rcx
 jbe nmm_loop
 mov rax,rdx
 sub rax,rcx
 cmp rax,r8
 jae nmm_loop
 add rcx,r8
 sub rcx,r9
 add rdx,r8
 sub rdx,r9
 neg r10
nmm_loop:
 cmp r9d,8
 je nmm_qword
 cmp r9d,4
 je nmm_dword
 cmp r9d,2
 je nmm_word
 mov al,BYTE PTR [rcx]
 mov BYTE PTR [rdx],al
 jmp nmm_advance
nmm_qword:
 mov rax,QWORD PTR [rcx]
 test r11d,r11d
 jz nmm_q_store
 bswap rax
nmm_q_store:
 mov QWORD PTR [rdx],rax
 jmp nmm_advance
nmm_dword:
 mov eax,DWORD PTR [rcx]
 test r11d,r11d
 jz nmm_d_store
 bswap eax
nmm_d_store:
 mov DWORD PTR [rdx],eax
 jmp nmm_advance
nmm_word:
 mov ax,WORD PTR [rcx]
 test r11d,r11d
 jz nmm_w_store
 rol ax,8
nmm_w_store:
 mov WORD PTR [rdx],ax
nmm_advance:
 add rcx,r10
 add rdx,r10
 sub r8,r9
 jnz nmm_loop
nmm_return:
 ret
nm_move ENDP

; RCX destination, RDX bytes, R8B fill byte. Same aligned coherent unit rule.
nm_fill PROC PRIVATE
 movzx eax,r8b
 mov r10,0101010101010101h
 imul rax,r10
 mov r10,rcx
 or r10,rdx
 mov r9d,8
 test r10b,7
 jz nmf_loop
 mov r9d,4
 test r10b,3
 jz nmf_loop
 mov r9d,2
 test r10b,1
 jz nmf_loop
 mov r9d,1
nmf_loop:
 test rdx,rdx
 jz nmf_return
 cmp r9d,8
 je nmf_qword
 cmp r9d,4
 je nmf_dword
 cmp r9d,2
 je nmf_word
 mov BYTE PTR [rcx],al
 jmp nmf_advance
nmf_qword:
 mov QWORD PTR [rcx],rax
 jmp nmf_advance
nmf_dword:
 mov DWORD PTR [rcx],eax
 jmp nmf_advance
nmf_word:
 mov WORD PTR [rcx],ax
nmf_advance:
 add rcx,r9
 sub rdx,r9
 jmp nmf_loop
nmf_return:
 ret
nm_fill ENDP

PUBLIC boom_native_memory_init
boom_native_memory_init PROC FRAME
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
 mov r12d,r8d
 mov rsi,r9
 xor edi,edi
 test rbx,rbx
 jz nmi_bad
 test bl,7
 jnz nmi_bad
 cmp rdx,128
 jne nmi_bad
 test r12d,r12d
 jz nmi_args
 cmp r12d,4096
 ja nmi_args
 test rsi,rsi
 jle nmi_args
 cmp QWORD PTR [rbx],0
 je nmi_zero_check
 mov rcx,rbx
 call nm_valid_owner
 test eax,eax
 jz nmi_bad
 cmp DWORD PTR [rbx+24],3
 jne nmi_busy
 cmp QWORD PTR [rbx+32],0
 jne nmi_bad
 cmp QWORD PTR [rbx+40],0
 jne nmi_bad
 cmp QWORD PTR [rbx+48],0
 jne nmi_bad
 cmp QWORD PTR [rbx+64],0
 jne nmi_bad
 cmp QWORD PTR [rbx+72],0
 jne nmi_bad
 cmp QWORD PTR [rbx+80],0
 jne nmi_bad
 mov rdi,QWORD PTR [rbx+88]
 jmp nmi_clear
nmi_zero_check:
 xor ecx,ecx
nmiz_loop:
 cmp QWORD PTR [rbx+rcx],0
 jne nmi_bad
 add ecx,8
 cmp ecx,128
 jb nmiz_loop
nmi_clear:
 xor eax,eax
 xor ecx,ecx
nmic_loop:
 mov QWORD PTR [rbx+rcx],rax
 add ecx,8
 cmp ecx,128
 jb nmic_loop
 mov rax,NM_MAGIC
 mov QWORD PTR [rbx],rax
 mov DWORD PTR [rbx+8],128
 mov DWORD PTR [rbx+12],1
 mov DWORD PTR [rbx+24],3
 mov QWORD PTR [rbx+88],rdi
 xor ecx,ecx
 imul edx,r12d,576
 mov r8d,03000h
 mov r9d,4
 call VirtualAlloc
 test rax,rax
 jz nmi_alloc_failure
 mov QWORD PTR [rbx+64],rax
 mov edx,r12d
 shl rdx,6
 add rax,rdx
 mov QWORD PTR [rbx+72],rax
 imul edx,r12d,576
 mov QWORD PTR [rbx+80],rdx
 mov DWORD PTR [rbx+28],r12d
 mov edx,r12d
 shl edx,4
 mov DWORD PTR [rbx+124],edx
 mov QWORD PTR [rbx+56],rsi
 mov DWORD PTR [rbx+24],1
 xor eax,eax
 jmp nmi_return
nmi_alloc_failure:
 call GetLastError
 mov DWORD PTR [rbx+120],eax
 mov eax,4
 jmp nmi_return
nmi_bad:
 mov eax,5
 jmp nmi_return
nmi_args:
 mov eax,3
 jmp nmi_return
nmi_busy:
 mov eax,2
nmi_return:
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_native_memory_init ENDP

PUBLIC boom_native_memory_service
boom_native_memory_service PROC FRAME
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
 sub rsp,112
 .allocstack 112
 .endprolog
 mov rbx,rcx
 mov edi,5
 test rbx,rbx
 jz nms_return
 test bl,7
 jnz nms_return
 xor eax,eax
 mov QWORD PTR [rbx+40],rax
 mov QWORD PTR [rbx+56],rax
 mov QWORD PTR [rbx+76],rax
 mov QWORD PTR [rbx+88],rax
 cmp DWORD PTR [rbx+72],9
 je nms_keep_token
 mov QWORD PTR [rbx+48],rax
nms_keep_token:
 mov r12,QWORD PTR [rbx]
 mov rcx,r12
 call nm_valid_owner
 test eax,eax
 jz nms_store_return
 lea rcx,[r12+16]
 call AcquireSRWLockExclusive
 mov r13,QWORD PTR [rbx+16]
 mov r14,QWORD PTR [rbx+8]
 cmp DWORD PTR [rbx+72],9
 ja nms_args
 cmp DWORD PTR [r12+24],1
 je nms_ready
 cmp DWORD PTR [rbx+72],9
 jne nms_closed
 cmp QWORD PTR [rbx+48],0
 je nms_ok
 cmp DWORD PTR [r12+24],2
 jne nms_closed
nms_ready:
 cmp QWORD PTR [r12+64],0
 je nms_bad_locked
 cmp QWORD PTR [r12+72],0
 je nms_bad_locked
 mov eax,DWORD PTR [r12+28]
 test eax,eax
 jz nms_bad_locked
 cmp eax,4096
 ja nms_bad_locked
 mov edx,eax
 shl edx,4
 cmp DWORD PTR [r12+124],edx
 jne nms_bad_locked
 cmp DWORD PTR [rbx+68],0
 je nms_flags_ok
 cmp DWORD PTR [rbx+72],8
 jne nms_args
nms_flags_ok:
 mov eax,DWORD PTR [rbx+72]
 cmp eax,0
 je nms_alloc
 cmp eax,1
 je nms_realloc
 cmp eax,2
 je nms_free
 cmp eax,3
 je nms_read
 cmp eax,4
 je nms_write
 cmp eax,5
 je nms_fill
 cmp eax,6
 je nms_copy
 cmp eax,7
 je nms_copy_swap
 cmp eax,8
 je nms_borrow
 jmp nms_release

nms_alloc:
 cmp DWORD PTR [rbx+64],0
 jne nms_args
 test r13,r13
 js nms_args
 jz nms_ok
 mov rax,QWORD PTR [r12+48]
 add rax,r13
 jc nms_limit
 cmp rax,QWORD PTR [r12+56]
 ja nms_limit
 cmp QWORD PTR [r12+88],-1
 je nms_limit
 mov rcx,r12
 call nm_free_record
 test rax,rax
 jz nms_limit
 mov r15,rax
 xor ecx,ecx
 mov rdx,r13
 mov r8d,03000h
 mov r9d,4
 call VirtualAlloc
 test rax,rax
 jz nms_alloc_failure
 mov QWORD PTR [r15],rax
 mov QWORD PTR [r15+8],r13
 mov QWORD PTR [r15+16],r13
 inc QWORD PTR [r12+88]
 mov rcx,QWORD PTR [r12+88]
 mov QWORD PTR [r15+24],rcx
 mov DWORD PTR [r15+40],1
 mov QWORD PTR [r15+48],3
 inc QWORD PTR [r12+32]
 add QWORD PTR [r12+48],r13
 inc QWORD PTR [r12+96]
 mov QWORD PTR [rbx+40],rax
 mov QWORD PTR [rbx+56],rcx
 mov QWORD PTR [rbx+88],r13
 jmp nms_ok

nms_realloc:
 cmp DWORD PTR [rbx+64],0
 jne nms_args
 test r13,r13
 js nms_args
 test r14,r14
 jz nms_alloc
 test r13,r13
 jz nms_free
 mov rcx,r12
 mov rdx,r14
 xor r8d,r8d
 call nm_find_range
 test edx,edx
 jnz nms_from_find
 cmp QWORD PTR [rax],r14
 jne nms_args
 cmp DWORD PTR [rax+32],0
 jne nms_busy
 mov QWORD PTR [rsp+32],rax
 mov rsi,QWORD PTR [rax+8]
 ; Peak live logical bytes, including temporary old+new, obey budget.
 mov rcx,QWORD PTR [r12+48]
 add rcx,r13
 jc nms_limit
 cmp rcx,QWORD PTR [r12+56]
 ja nms_limit
 cmp QWORD PTR [r12+88],-1
 je nms_limit
 mov rcx,r12
 call nm_free_record
 test rax,rax
 jz nms_limit
 mov r15,rax
 xor ecx,ecx
 mov rdx,r13
 mov r8d,03000h
 mov r9d,4
 call VirtualAlloc
 test rax,rax
 jz nms_alloc_failure
 mov QWORD PTR [r15],rax
 mov QWORD PTR [r15+8],r13
 mov QWORD PTR [r15+16],r13
 inc QWORD PTR [r12+88]
 mov rcx,QWORD PTR [r12+88]
 mov QWORD PTR [r15+24],rcx
 mov DWORD PTR [r15+40],1
 mov QWORD PTR [r15+48],3
 inc QWORD PTR [r12+32]
 add QWORD PTR [r12+48],r13
 inc QWORD PTR [r12+96]
 mov rcx,r14
 mov rdx,rax
 mov r8,rsi
 cmp r8,r13
 cmova r8,r13
 xor r9d,r9d
 call nm_move
 mov rcx,r14
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
 test eax,eax
 jz nms_resize_old_free_failure
 dec QWORD PTR [r12+32]
 sub QWORD PTR [r12+48],rsi
 inc QWORD PTR [r12+104]
 inc QWORD PTR [r12+112]
 mov rcx,QWORD PTR [rsp+32]
 call nm_clear_record
 mov rax,QWORD PTR [r15]
 mov QWORD PTR [rbx+40],rax
 mov rax,QWORD PTR [r15+24]
 mov QWORD PTR [rbx+56],rax
 mov QWORD PTR [rbx+88],r13
 jmp nms_ok
nms_resize_old_free_failure:
 call GetLastError
 mov DWORD PTR [rbx+80],eax
 mov DWORD PTR [r12+120],eax
 mov rcx,QWORD PTR [rsp+32]
 mov DWORD PTR [rcx+44],eax
 ; Old block remains live. Attempt to discard unpublished replacement.
 mov rcx,QWORD PTR [r15]
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
 test eax,eax
 jz nms_resize_rollback_failure
 dec QWORD PTR [r12+32]
 sub QWORD PTR [r12+48],r13
 inc QWORD PTR [r12+104]
 mov rcx,r15
 call nm_clear_record
 jmp nms_cleanup_failure
nms_resize_rollback_failure:
 call GetLastError
 mov DWORD PTR [r15+44],eax
 mov DWORD PTR [r12+120],eax
 mov DWORD PTR [r15+40],2
 jmp nms_cleanup_failure

nms_free:
 cmp DWORD PTR [rbx+64],0
 jne nms_args
 ; realloc(size0) reaches this same exact-base, zero-lease release.
 cmp DWORD PTR [rbx+72],2
 jne nms_free_address
 test r13,r13
 jnz nms_args
nms_free_address:
 test r14,r14
 jz nms_ok
nms_free_find:
 mov rcx,r12
 mov rdx,r14
 xor r8d,r8d
 call nm_find_range
 test edx,edx
 jnz nms_from_find
 cmp QWORD PTR [rax],r14
 jne nms_args
 cmp DWORD PTR [rax+32],0
 jne nms_busy
 mov r15,rax
 mov rsi,QWORD PTR [rax+8]
 mov rcx,r14
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
 test eax,eax
 jz nms_free_failure
 dec QWORD PTR [r12+32]
 sub QWORD PTR [r12+48],rsi
 inc QWORD PTR [r12+104]
 mov rcx,r15
 call nm_clear_record
 jmp nms_ok
nms_free_failure:
 call GetLastError
 mov DWORD PTR [r15+44],eax
 mov DWORD PTR [r12+120],eax
 mov DWORD PTR [rbx+80],eax
 jmp nms_cleanup_failure

nms_read:
nms_write:
 mov eax,DWORD PTR [rbx+64]
 cmp eax,1
 je nms_typed_width
 cmp eax,2
 je nms_typed_width
 cmp eax,4
 je nms_typed_width
 cmp eax,8
 jne nms_args
nms_typed_width:
 cmp r13,rax
 jne nms_args
 mov rcx,r12
 mov rdx,r14
 mov r8,r13
 call nm_find_range
 test edx,edx
 jnz nms_from_find
 cmp DWORD PTR [rbx+72],4
 je nms_typed_write
 cmp DWORD PTR [rax+36],0
 jne nms_busy
 mov eax,DWORD PTR [rbx+64]
 cmp eax,8
 je nms_read8
 cmp eax,4
 je nms_read4
 cmp eax,2
 je nms_read2
 movzx eax,BYTE PTR [r14]
 jmp nms_read_store
nms_read8:
 mov rax,QWORD PTR [r14]
 jmp nms_read_store
nms_read4:
 mov eax,DWORD PTR [r14]
 jmp nms_read_store
nms_read2:
 movzx eax,WORD PTR [r14]
nms_read_store:
 mov QWORD PTR [rbx+40],rax
 mov QWORD PTR [rbx+88],r13
 jmp nms_ok
nms_typed_write:
 cmp DWORD PTR [rax+32],0
 jne nms_busy
 mov rax,QWORD PTR [rbx+32]
 cmp DWORD PTR [rbx+64],8
 je nms_write8
 cmp DWORD PTR [rbx+64],4
 je nms_write4
 cmp DWORD PTR [rbx+64],2
 je nms_write2
 mov BYTE PTR [r14],al
 jmp nms_written
nms_write8:
 mov QWORD PTR [r14],rax
 jmp nms_written
nms_write4:
 mov DWORD PTR [r14],eax
 jmp nms_written
nms_write2:
 mov WORD PTR [r14],ax
nms_written:
 mov QWORD PTR [rbx+88],r13
 jmp nms_ok

nms_fill:
 cmp DWORD PTR [rbx+64],0
 jne nms_args
 test r13,r13
 js nms_args
 jz nms_ok
 mov rcx,r12
 mov rdx,r14
 mov r8,r13
 call nm_find_range
 test edx,edx
 jnz nms_from_find
 cmp DWORD PTR [rax+32],0
 jne nms_busy
 mov rcx,r14
 mov rdx,r13
 mov r8,QWORD PTR [rbx+32]
 call nm_fill
 mov QWORD PTR [rbx+88],r13
 jmp nms_ok

nms_copy:
 cmp DWORD PTR [rbx+64],0
 jne nms_args
 jmp nms_copy_ranges
nms_copy_swap:
 mov eax,DWORD PTR [rbx+64]
 cmp eax,2
 je nms_swap_width
 cmp eax,4
 je nms_swap_width
 cmp eax,8
 jne nms_args
nms_swap_width:
 dec eax
 test r13,rax
 jnz nms_args
nms_copy_ranges:
 test r13,r13
 js nms_args
 jz nms_ok
 mov rcx,r12
 mov rdx,r14
 mov r8,r13
 call nm_find_range
 test edx,edx
 jnz nms_from_find
 cmp DWORD PTR [rax+36],0
 jne nms_busy
 mov rcx,r12
 mov rdx,QWORD PTR [rbx+24]
 mov r8,r13
 call nm_find_range
 test edx,edx
 jnz nms_from_find
 cmp DWORD PTR [rax+32],0
 jne nms_busy
 mov rcx,r14
 mov rdx,QWORD PTR [rbx+24]
 mov r8,r13
 mov r9d,DWORD PTR [rbx+64]
 call nm_move
 mov QWORD PTR [rbx+88],r13
 jmp nms_ok

nms_borrow:
 cmp DWORD PTR [rbx+64],0
 jne nms_args
 mov eax,DWORD PTR [rbx+68]
 dec eax
 cmp eax,2
 ja nms_args
 test r13,r13
 js nms_args
 jz nms_ok
 mov rcx,r12
 mov rdx,r14
 mov r8,r13
 call nm_find_range
 test edx,edx
 jnz nms_from_find
 mov r15,rax
 test DWORD PTR [rbx+68],2
 jnz nms_borrow_writer
 cmp DWORD PTR [r15+36],0
 jne nms_busy
 cmp DWORD PTR [r15+32],-1
 je nms_limit
 jmp nms_borrow_slot
nms_borrow_writer:
 cmp DWORD PTR [r15+32],0
 jne nms_busy
nms_borrow_slot:
 cmp QWORD PTR [r12+88],-1
 je nms_limit
 mov rsi,QWORD PTR [r12+72]
 mov ecx,DWORD PTR [r12+124]
nms_borrow_scan:
 cmp QWORD PTR [rsi],0
 je nms_borrow_got
 add rsi,32
 dec ecx
 jnz nms_borrow_scan
 jmp nms_limit
nms_borrow_got:
 inc QWORD PTR [r12+88]
 mov rax,QWORD PTR [r12+88]
 mov QWORD PTR [rsi],rax
 mov QWORD PTR [rbx+48],rax
 mov rax,r15
 sub rax,QWORD PTR [r12+64]
 shr rax,6
 mov DWORD PTR [rsi+8],eax
 mov eax,DWORD PTR [rbx+68]
 mov DWORD PTR [rsi+12],eax
 mov rax,r14
 sub rax,QWORD PTR [r15]
 mov QWORD PTR [rsi+16],rax
 mov QWORD PTR [rsi+24],r13
 inc DWORD PTR [r15+32]
 inc QWORD PTR [r12+40]
 test DWORD PTR [rbx+68],2
 jz nms_borrow_readonly
 inc DWORD PTR [r15+36]
nms_borrow_readonly:
 mov QWORD PTR [rbx+40],r14
 mov rax,QWORD PTR [r15+24]
 mov QWORD PTR [rbx+56],rax
 mov QWORD PTR [rbx+88],r13
 jmp nms_ok

nms_release:
 cmp DWORD PTR [rbx+64],0
 jne nms_args
 mov rax,QWORD PTR [rbx+48]
 test rax,rax
 jz nms_ok
 mov rsi,QWORD PTR [r12+72]
 mov ecx,DWORD PTR [r12+124]
nms_release_scan:
 cmp QWORD PTR [rsi],rax
 je nms_release_found
 add rsi,32
 dec ecx
 jnz nms_release_scan
 jmp nms_args
nms_release_found:
 mov eax,DWORD PTR [rsi+8]
 cmp eax,DWORD PTR [r12+28]
 jae nms_bad_locked
 shl rax,6
 add rax,QWORD PTR [r12+64]
 cmp DWORD PTR [rax+40],1
 jne nms_bad_locked
 cmp DWORD PTR [rax+32],0
 je nms_bad_locked
 cmp QWORD PTR [r12+40],0
 je nms_bad_locked
 test DWORD PTR [rsi+12],2
 jz nms_release_readonly
 cmp DWORD PTR [rax+36],1
 jne nms_bad_locked
 dec DWORD PTR [rax+36]
nms_release_readonly:
 dec DWORD PTR [rax+32]
 dec QWORD PTR [r12+40]
 xor eax,eax
 mov QWORD PTR [rsi],rax
 mov QWORD PTR [rsi+8],rax
 mov QWORD PTR [rsi+16],rax
 mov QWORD PTR [rsi+24],rax
 mov QWORD PTR [rbx+48],rax
 jmp nms_ok

nms_alloc_failure:
 call GetLastError
 mov DWORD PTR [r12+120],eax
 mov DWORD PTR [rbx+80],eax
 mov edi,4
 jmp nms_unlock
nms_from_find:
 mov edi,edx
 jmp nms_unlock
nms_cleanup_failure:
 mov edi,12
 jmp nms_unlock
nms_ok:
 xor edi,edi
 jmp nms_unlock
nms_limit:
 mov edi,7
 jmp nms_unlock
nms_args:
 mov edi,3
 jmp nms_unlock
nms_busy:
 mov edi,2
 jmp nms_unlock
nms_closed:
 mov edi,9
 jmp nms_unlock
nms_bad_locked:
 mov edi,5
nms_unlock:
 lea rcx,[r12+16]
 call ReleaseSRWLockExclusive
nms_store_return:
 mov DWORD PTR [rbx+76],edi
nms_return:
 mov eax,edi
 add rsp,112
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_native_memory_service ENDP

PUBLIC boom_native_memory_close
boom_native_memory_close PROC FRAME
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
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 call nm_valid_owner
 test eax,eax
 jz nmc_bad
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 xor edi,edi
 cmp DWORD PTR [rbx+24],3
 je nmc_already_closed
 cmp DWORD PTR [rbx+24],1
 je nmc_ready
 cmp DWORD PTR [rbx+24],2
 jne nmc_bad_locked
nmc_ready:
 cmp QWORD PTR [rbx+40],0
 jne nmc_busy
 cmp QWORD PTR [rbx+64],0
 je nmc_bad_locked
 mov r13d,DWORD PTR [rbx+28]
 test r13d,r13d
 jz nmc_bad_locked
 cmp r13d,4096
 ja nmc_bad_locked
 mov DWORD PTR [rbx+24],2
 mov rsi,QWORD PTR [rbx+64]
 xor r12d,r12d
nmc_records:
 cmp r12d,r13d
 jae nmc_metadata
 cmp DWORD PTR [rsi+40],0
 je nmc_next
 mov rcx,QWORD PTR [rsi]
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
 test eax,eax
 jz nmc_release_failure
 dec QWORD PTR [rbx+32]
 mov rax,QWORD PTR [rsi+8]
 sub QWORD PTR [rbx+48],rax
 inc QWORD PTR [rbx+104]
 mov rcx,rsi
 call nm_clear_record
 jmp nmc_next
nmc_release_failure:
 call GetLastError
 mov DWORD PTR [rbx+120],eax
 mov DWORD PTR [rsi+44],eax
 mov DWORD PTR [rsi+40],2
 mov edi,12
nmc_next:
 add rsi,64
 inc r12d
 jmp nmc_records
nmc_metadata:
 test edi,edi
 jnz nmc_unlock
 cmp QWORD PTR [rbx+32],0
 jne nmc_bad_locked
 cmp QWORD PTR [rbx+48],0
 jne nmc_bad_locked
 mov rcx,QWORD PTR [rbx+64]
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
 test eax,eax
 jz nmc_metadata_failure
 mov QWORD PTR [rbx+64],0
 mov QWORD PTR [rbx+72],0
 mov QWORD PTR [rbx+80],0
 mov DWORD PTR [rbx+120],0
 mov DWORD PTR [rbx+24],3
 jmp nmc_unlock
nmc_metadata_failure:
 call GetLastError
 mov DWORD PTR [rbx+120],eax
 mov edi,12
 jmp nmc_unlock
nmc_already_closed:
 cmp QWORD PTR [rbx+32],0
 jne nmc_bad_locked
 cmp QWORD PTR [rbx+40],0
 jne nmc_bad_locked
 cmp QWORD PTR [rbx+48],0
 jne nmc_bad_locked
 cmp QWORD PTR [rbx+64],0
 jne nmc_bad_locked
 cmp QWORD PTR [rbx+72],0
 jne nmc_bad_locked
 cmp QWORD PTR [rbx+80],0
 jne nmc_bad_locked
 jmp nmc_unlock
nmc_busy:
 mov edi,2
 jmp nmc_unlock
nmc_bad_locked:
 mov edi,5
nmc_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp nmc_return
nmc_bad:
 mov eax,5
nmc_return:
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_native_memory_close ENDP
