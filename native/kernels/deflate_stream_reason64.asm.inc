; Incremental RFC1951 raw decoder. Caller-owned opaque State34304/Job80.
; No heap, imports, global mutable data, external dictionary or replay buffer.
; Job: state0,src8,len16,dst24,cap32,flags40,status44,inUsed48,outUsed56,
; cumulativeIn64,cumulativeOut72. flags1=END_INPUT for the supplied last chunk.
; Status0 finished,1 need input,2 need output,3 arguments,4 truncated,
; 5 block,6 Huffman,7 symbol/repeat,8 distance,9 invalid opaque-state header.
DS_BYTES EQU 34304
DS_MAGIC EQU 0315354464C464544h
DS_LIT EQU 256
DS_DIST EQU 896
DS_CL EQU 1024
DS_LENGTHS EQU 1152
DS_CLLENS EQU 1472
DS_HISTORY EQU 1536
.const
boom_ds_order BYTE 16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15
boom_ds_length_base WORD 3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258
boom_ds_length_bits BYTE 0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0
boom_ds_distance_base WORD 1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577
boom_ds_distance_bits BYTE 0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13
.code

; RCX lengths,EDX symbols,R8 table,R9 kind0 CL/1 literal/2 distance.
; counts[0] holds max length; counts[1..15] and sorted WORD symbols follow.
boom_ds_build PROC PRIVATE FRAME
 push rbp
 .pushreg rbp
 sub rsp,112
 .allocstack 112
 .endprolog
 mov rbp,r8
 mov QWORD PTR [rsp+32],rcx
 mov DWORD PTR [rsp+40],edx
 mov DWORD PTR [rsp+44],r9d
 pxor xmm0,xmm0
 movdqu XMMWORD PTR [rbp],xmm0
 movdqu XMMWORD PTR [rbp+16],xmm0
 movdqu XMMWORD PTR [rbp+32],xmm0
 movdqu XMMWORD PTR [rbp+48],xmm0
 xor r9d,r9d
 xor r10d,r10d
boom_ds_build_count:
 cmp r9d,DWORD PTR [rsp+40]
 jae boom_ds_build_check
 movzx eax,BYTE PTR [rcx+r9]
 cmp eax,15
 ja boom_ds_build_bad
 test eax,eax
 jz boom_ds_build_next
 inc DWORD PTR [rbp+rax*4]
 cmp eax,r10d
 cmova r10d,eax
boom_ds_build_next:
 inc r9d
 jmp boom_ds_build_count
boom_ds_build_check:
 mov DWORD PTR [rbp],r10d
 test r10d,r10d
 jnz boom_ds_build_nonempty
 cmp DWORD PTR [rsp+44],2
 jne boom_ds_build_bad
 jmp boom_ds_build_good
boom_ds_build_nonempty:
 mov edx,1
 mov r9d,1
boom_ds_build_kraft:
 shl edx,1
 sub edx,DWORD PTR [rbp+r9*4]
 js boom_ds_build_bad
 inc r9d
 cmp r9d,16
 jb boom_ds_build_kraft
 test edx,edx
 jz boom_ds_build_sort
 cmp DWORD PTR [rsp+44],0
 je boom_ds_build_bad
 cmp DWORD PTR [rbp],1
 jne boom_ds_build_bad
boom_ds_build_sort:
 xor eax,eax
 mov r9d,1
boom_ds_build_offsets:
 mov DWORD PTR [rsp+48+r9*4],eax
 add eax,DWORD PTR [rbp+r9*4]
 inc r9d
 cmp r9d,16
 jb boom_ds_build_offsets
 mov rcx,QWORD PTR [rsp+32]
 xor r9d,r9d
boom_ds_build_symbols:
 cmp r9d,DWORD PTR [rsp+40]
 jae boom_ds_build_good
 movzx edx,BYTE PTR [rcx+r9]
 test edx,edx
 jz boom_ds_build_symbol_next
 mov eax,DWORD PTR [rsp+48+rdx*4]
 inc DWORD PTR [rsp+48+rdx*4]
 mov WORD PTR [rbp+64+rax*2],r9w
boom_ds_build_symbol_next:
 inc r9d
 jmp boom_ds_build_symbols
boom_ds_build_good:
 xor eax,eax
 add rsp,112
 pop rbp
 ret
boom_ds_build_bad:
 mov DWORD PTR [rbx+44],6
 mov eax,1
 add rsp,112
 pop rbp
 ret
boom_ds_build ENDP

; Atomic field read ECX0..16. Incomplete bytes remain in state bit cache;
; R14 counts exactly the bytes acquired from this call, never reread later.
boom_ds_bits PROC PRIVATE
 mov r11d,ecx
boom_ds_bits_fill:
 mov ecx,DWORD PTR [rbp+32]
 cmp ecx,r11d
 jae boom_ds_bits_ready
 cmp r14,r12
 jae boom_ds_bits_empty
 movzx r8d,BYTE PTR [rsi+r14]
 shl r8,cl
 or QWORD PTR [rbp+24],r8
 add DWORD PTR [rbp+32],8
 inc r14
 jmp boom_ds_bits_fill
boom_ds_bits_ready:
 mov ecx,r11d
 mov r9d,1
 shl r9d,cl
 dec r9d
 mov eax,DWORD PTR [rbp+24]
 and eax,r9d
 shr QWORD PTR [rbp+24],cl
 sub DWORD PTR [rbp+32],r11d
 add QWORD PTR [rbp+56],r11
 clc
 ret
boom_ds_bits_empty:
 mov DWORD PTR [rbx+44],1
 test DWORD PTR [rbx+40],1
 jnz boom_ds_bits_eof
 cmp DWORD PTR [rbp+136],0
 je boom_ds_bits_wait
boom_ds_bits_eof:
 mov DWORD PTR [rbx+44],4
boom_ds_bits_wait:
 stc
 ret
boom_ds_bits ENDP

; ECX table offset. Partial canonical code/first/index/length are state-owned.
boom_ds_decode PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 cmp DWORD PTR [rbp+120],0
 jne boom_ds_decode_resume
 mov DWORD PTR [rbp+108],0
 mov DWORD PTR [rbp+112],0
 mov DWORD PTR [rbp+116],0
 mov DWORD PTR [rbp+120],1
 mov DWORD PTR [rbp+124],ecx
boom_ds_decode_resume:
 cmp ecx,DWORD PTR [rbp+124]
 jne boom_ds_decode_bad
 mov eax,DWORD PTR [rbp+rcx]
 test eax,eax
 jz boom_ds_decode_bad
 cmp eax,15
 ja boom_ds_decode_bad
boom_ds_decode_loop:
 mov ecx,1
 call boom_ds_bits
 jc boom_ds_decode_error
 mov edx,DWORD PTR [rbp+108]
 shl edx,1
 or edx,eax
 mov DWORD PTR [rbp+108],edx
 mov ecx,DWORD PTR [rbp+120]
 mov r10d,DWORD PTR [rbp+124]
 lea r10,[rbp+r10]
 mov r8d,DWORD PTR [r10+rcx*4]
 cmp r8d,288
 ja boom_ds_decode_bad
 sub edx,DWORD PTR [rbp+112]
 cmp edx,r8d
 jb boom_ds_decode_found
 add DWORD PTR [rbp+116],r8d
 mov eax,DWORD PTR [rbp+112]
 add eax,r8d
 shl eax,1
 mov DWORD PTR [rbp+112],eax
 inc DWORD PTR [rbp+120]
 mov eax,DWORD PTR [rbp+120]
 cmp eax,DWORD PTR [r10]
 jbe boom_ds_decode_loop
boom_ds_decode_bad:
 mov DWORD PTR [rbx+44],6
boom_ds_decode_error:
 add rsp,40
 stc
 ret
boom_ds_decode_found:
 add edx,DWORD PTR [rbp+116]
 cmp edx,288
 jae boom_ds_decode_bad
 movzx eax,WORD PTR [r10+64+rdx*2]
 mov DWORD PTR [rbp+120],0
 add rsp,40
 clc
 ret
boom_ds_decode ENDP

; AL byte; caller already established R15 < R13. Update ring immediately.
boom_ds_emit PROC PRIVATE
 mov BYTE PTR [rdi+r15],al
 inc r15
 mov r8d,DWORD PTR [rbp+64]
 mov BYTE PTR [rbp+DS_HISTORY+r8],al
 inc r8d
 and r8d,32767
 mov DWORD PTR [rbp+64],r8d
 cmp DWORD PTR [rbp+68],32768
 jae boom_ds_emit_done
 inc DWORD PTR [rbp+68]
boom_ds_emit_done:
 ret
boom_ds_emit ENDP

PUBLIC boom_deflate_stream_reset_reason
boom_deflate_stream_reset_reason PROC FRAME
 push rdi
 .pushreg rdi
 .endprolog
 mov eax,3
 test rcx,rcx
 jz boom_ds_reset_done
 cmp edx,DS_BYTES
 jne boom_ds_reset_done
 mov r8,rcx
 add r8,DS_BYTES
 jc boom_ds_reset_done
 mov rdi,rcx
 mov r8,rcx
 xor eax,eax
 mov ecx,DS_BYTES/8
 rep stosq
 mov rax,DS_MAGIC
 mov QWORD PTR [r8],rax
 mov DWORD PTR [r8+8],DS_BYTES
 xor eax,eax
boom_ds_reset_done:
 pop rdi
 ret
boom_deflate_stream_reset_reason ENDP

; IO: RBX job,RBP state,RSI source,RDI dest,R12 length,R13 capacity,
; R14 acquired input bytes,R15 emitted output bytes. All are callee-saved.
PUBLIC boom_deflate_stream_step_reason
boom_deflate_stream_step_reason PROC FRAME
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
 sub rsp,72
 .allocstack 72
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz boom_ds_null_job
 mov rbp,QWORD PTR [rbx]
 mov rsi,QWORD PTR [rbx+8]
 mov r12,QWORD PTR [rbx+16]
 mov rdi,QWORD PTR [rbx+24]
 mov r13,QWORD PTR [rbx+32]
 xor r14d,r14d
 xor r15d,r15d
 ; A job placed inside its state cannot be written without corrupting that
 ; state. Reject it through EAX alone, before publishing any job output.
 mov r8,rbx
 add r8,96
 jc boom_ds_null_job
 mov r9,rbp
 add r9,DS_BYTES
 jc boom_ds_null_job
 cmp rbp,r8
 jae boom_ds_clear_job
 cmp r9,rbx
 ja boom_ds_null_job
boom_ds_clear_job:
 mov DWORD PTR [rbx+44],0
 mov QWORD PTR [rbx+48],0
 mov QWORD PTR [rbx+56],0
 mov QWORD PTR [rbx+64],0
 mov QWORD PTR [rbx+72],0
 mov DWORD PTR [rbx+92],0
 test DWORD PTR [rbx+40],0FFFFFFFEh
 jnz boom_ds_arguments
 test rbp,rbp
 jz boom_ds_arguments
 mov rax,01FFFFFFFFFFFFFFFh
 cmp r12,rax
 ja boom_ds_arguments
 test r12,r12
 jz boom_ds_validate_dst
 test rsi,rsi
 jz boom_ds_arguments
boom_ds_validate_dst:
 test r13,r13
 jz boom_ds_validate_ends
 test rdi,rdi
 jz boom_ds_arguments
boom_ds_validate_ends:
 mov r8,rsi
 add r8,r12
 jc boom_ds_arguments
 mov r9,rdi
 add r9,r13
 jc boom_ds_arguments
 mov r10,rbp
 add r10,DS_BYTES
 jc boom_ds_arguments
 mov r11,rbx
 add r11,96
 jc boom_ds_arguments
 cmp rbp,r11
 jae boom_ds_validate_input
 cmp r10,rbx
 ja boom_ds_arguments
boom_ds_validate_input:
 test r12,r12
 jz boom_ds_validate_output
 cmp rsi,r11
 jae boom_ds_input_state
 cmp r8,rbx
 ja boom_ds_arguments
boom_ds_input_state:
 cmp rsi,r10
 jae boom_ds_validate_output
 cmp r8,rbp
 ja boom_ds_arguments
boom_ds_validate_output:
 test r13,r13
 jz boom_ds_validate_state
 cmp rdi,r11
 jae boom_ds_output_state
 cmp r9,rbx
 ja boom_ds_arguments
boom_ds_output_state:
 cmp rdi,r10
 jae boom_ds_input_output
 cmp r9,rbp
 ja boom_ds_arguments
boom_ds_input_output:
 test r12,r12
 jz boom_ds_validate_state
 cmp rsi,r9
 jae boom_ds_validate_state
 cmp rdi,r8
 jb boom_ds_arguments
boom_ds_validate_state:
 mov rax,DS_MAGIC
 cmp QWORD PTR [rbp],rax
 jne boom_ds_invalid_state
 cmp DWORD PTR [rbp+8],DS_BYTES
 jne boom_ds_invalid_state
 cmp DWORD PTR [rbp+12],16
 ja boom_ds_invalid_state
 cmp DWORD PTR [rbp+20],1
 ja boom_ds_invalid_state
 cmp DWORD PTR [rbp+136],1
 ja boom_ds_invalid_state
 mov ecx,DWORD PTR [rbp+32]
 cmp ecx,23
 ja boom_ds_invalid_state
 mov rax,QWORD PTR [rbp+24]
 shr rax,cl
 test rax,rax
 jnz boom_ds_invalid_state
 mov rax,01FFFFFFFFFFFFFFFh
 cmp QWORD PTR [rbp+40],rax
 ja boom_ds_invalid_state
 mov rax,QWORD PTR [rbp+40]
 shl rax,3
 sub rax,QWORD PTR [rbp+56]
 jc boom_ds_invalid_state
 cmp rax,rcx
 jne boom_ds_invalid_state
 mov rax,QWORD PTR [rbp+48]
 mov ecx,eax
 and ecx,32767
 cmp ecx,DWORD PTR [rbp+64]
 jne boom_ds_invalid_state
 cmp rax,32768
 jb boom_ds_window_small
 mov eax,32768
boom_ds_window_small:
 cmp eax,DWORD PTR [rbp+68]
 jne boom_ds_invalid_state
 cmp DWORD PTR [rbp+120],15
 ja boom_ds_invalid_state
 cmp DWORD PTR [rbp+12],15
 je boom_ds_existing_finished
 cmp DWORD PTR [rbp+12],16
 je boom_ds_existing_error
 cmp DWORD PTR [rbp+136],0
 je boom_ds_validate_totals
 test r12,r12
 jnz boom_ds_arguments
boom_ds_validate_totals:
 mov rax,QWORD PTR [rbp+40]
 add rax,r12
 jc boom_ds_arguments
 mov rdx,01FFFFFFFFFFFFFFFh
 cmp rax,rdx
 ja boom_ds_arguments
 mov rax,QWORD PTR [rbp+48]
 add rax,r13
 jc boom_ds_arguments
boom_ds_dispatch:
 mov DWORD PTR [rbp+140],0
 mov eax,DWORD PTR [rbp+12]
 test eax,eax
 jz boom_ds_header
 cmp eax,1
 je boom_ds_stored_align
 cmp eax,2
 je boom_ds_stored_length
 cmp eax,3
 je boom_ds_stored_complement
 cmp eax,4
 je boom_ds_stored_copy
 cmp eax,5
 je boom_ds_dynamic_counts
 cmp eax,6
 je boom_ds_dynamic_cl
 cmp eax,7
 je boom_ds_dynamic_lengths
 cmp eax,8
 je boom_ds_dynamic_repeat
 cmp eax,9
 je boom_ds_compressed
 cmp eax,10
 je boom_ds_literal
 cmp eax,11
 je boom_ds_length_extra
 cmp eax,12
 je boom_ds_distance_code
 cmp eax,13
 je boom_ds_distance_extra
 cmp eax,14
 je boom_ds_match
 jmp boom_ds_bad_huffman

boom_ds_header:
 mov ecx,3
 call boom_ds_bits
 jc boom_ds_finish
 mov edx,eax
 and edx,1
 mov DWORD PTR [rbp+20],edx
 shr eax,1
 test eax,eax
 jz boom_ds_new_stored
 cmp eax,1
 je boom_ds_fixed
 cmp eax,2
 je boom_ds_new_dynamic
 jmp boom_ds_bad_block_type_reason
boom_ds_new_stored:
 mov DWORD PTR [rbp+12],1
boom_ds_stored_align:
 mov ecx,DWORD PTR [rbp+56]
 neg ecx
 and ecx,7
 call boom_ds_bits
 jc boom_ds_finish
 mov DWORD PTR [rbp+12],2
boom_ds_stored_length:
 mov ecx,16
 call boom_ds_bits
 jc boom_ds_finish
 mov DWORD PTR [rbp+72],eax
 mov DWORD PTR [rbp+12],3
boom_ds_stored_complement:
 mov ecx,16
 call boom_ds_bits
 jc boom_ds_finish
 xor eax,DWORD PTR [rbp+72]
 cmp eax,0FFFFh
 jne boom_ds_bad_stored_length_reason
 mov DWORD PTR [rbp+12],4
boom_ds_stored_copy:
 cmp DWORD PTR [rbp+72],0
 je boom_ds_end_block
 cmp r15,r13
 jae boom_ds_need_output
 mov ecx,8
 call boom_ds_bits
 jc boom_ds_finish
 call boom_ds_emit
 dec DWORD PTR [rbp+72]
 jmp boom_ds_stored_copy

boom_ds_fixed:
 xor ecx,ecx
boom_ds_fixed_lens:
 mov al,8
 cmp ecx,144
 jb boom_ds_fixed_store
 mov al,9
 cmp ecx,256
 jb boom_ds_fixed_store
 mov al,7
 cmp ecx,280
 jb boom_ds_fixed_store
 mov al,8
boom_ds_fixed_store:
 mov BYTE PTR [rbp+DS_LENGTHS+rcx],al
 inc ecx
 cmp ecx,288
 jb boom_ds_fixed_lens
 mov ecx,288
boom_ds_fixed_distance:
 mov BYTE PTR [rbp+DS_LENGTHS+rcx],5
 inc ecx
 cmp ecx,320
 jb boom_ds_fixed_distance
 lea rcx,[rbp+DS_LENGTHS]
 mov edx,288
 lea r8,[rbp+DS_LIT]
 mov r9d,1
 call boom_ds_build
 test eax,eax
 jnz boom_ds_finish
 lea rcx,[rbp+DS_LENGTHS+288]
 mov edx,32
 lea r8,[rbp+DS_DIST]
 mov r9d,2
 call boom_ds_build
 test eax,eax
 jnz boom_ds_finish
 mov DWORD PTR [rbp+12],9
 jmp boom_ds_compressed

boom_ds_new_dynamic:
 mov DWORD PTR [rbp+12],5
boom_ds_dynamic_counts:
 mov ecx,14
 call boom_ds_bits
 jc boom_ds_finish
 mov edx,eax
 and edx,31
 add edx,257
 cmp edx,286
 ja boom_ds_bad_huffman
 mov DWORD PTR [rbp+76],edx
 mov edx,eax
 shr edx,5
 and edx,31
 inc edx
 mov DWORD PTR [rbp+80],edx
 shr eax,10
 add eax,4
 mov DWORD PTR [rbp+84],eax
 pxor xmm0,xmm0
 movdqu XMMWORD PTR [rbp+DS_CLLENS],xmm0
 movdqu XMMWORD PTR [rbp+DS_CLLENS+16],xmm0
 mov DWORD PTR [rbp+88],0
 mov DWORD PTR [rbp+12],6
boom_ds_dynamic_cl:
 mov ecx,3
 call boom_ds_bits
 jc boom_ds_finish
 mov edx,DWORD PTR [rbp+88]
 lea r10,boom_ds_order
 movzx edx,BYTE PTR [r10+rdx]
 mov BYTE PTR [rbp+DS_CLLENS+rdx],al
 inc DWORD PTR [rbp+88]
 mov eax,DWORD PTR [rbp+88]
 cmp eax,DWORD PTR [rbp+84]
 jb boom_ds_dynamic_cl
 lea rcx,[rbp+DS_CLLENS]
 mov edx,19
 lea r8,[rbp+DS_CL]
 xor r9d,r9d
 call boom_ds_build
 test eax,eax
 jnz boom_ds_finish
 mov DWORD PTR [rbp+88],0
 mov DWORD PTR [rbp+92],0
 mov DWORD PTR [rbp+12],7
boom_ds_dynamic_lengths:
 mov ecx,DS_CL
 call boom_ds_decode
 jc boom_ds_finish
 cmp eax,15
 ja boom_ds_dynamic_new_repeat
 mov edx,DWORD PTR [rbp+88]
 mov BYTE PTR [rbp+DS_LENGTHS+rdx],al
 mov DWORD PTR [rbp+92],eax
 inc DWORD PTR [rbp+88]
 jmp boom_ds_dynamic_length_end
boom_ds_dynamic_new_repeat:
 mov DWORD PTR [rbp+96],eax
 cmp eax,16
 jne boom_ds_dynamic_zero
 cmp DWORD PTR [rbp+88],0
 je boom_ds_bad_symbol
 jmp boom_ds_dynamic_repeat_phase
boom_ds_dynamic_zero:
 cmp eax,18
 ja boom_ds_bad_symbol
 mov DWORD PTR [rbp+92],0
boom_ds_dynamic_repeat_phase:
 mov DWORD PTR [rbp+12],8
boom_ds_dynamic_repeat:
 mov ecx,2
 cmp DWORD PTR [rbp+96],16
 je boom_ds_dynamic_repeat_bits
 mov ecx,3
 cmp DWORD PTR [rbp+96],17
 je boom_ds_dynamic_repeat_bits
 mov ecx,7
boom_ds_dynamic_repeat_bits:
 call boom_ds_bits
 jc boom_ds_finish
 add eax,3
 cmp DWORD PTR [rbp+96],18
 jne boom_ds_dynamic_repeat_count
 add eax,8
boom_ds_dynamic_repeat_count:
 mov ecx,eax
 add eax,DWORD PTR [rbp+88]
 mov edx,DWORD PTR [rbp+76]
 add edx,DWORD PTR [rbp+80]
 cmp eax,edx
 ja boom_ds_bad_symbol
 mov edx,DWORD PTR [rbp+88]
 mov eax,DWORD PTR [rbp+92]
boom_ds_dynamic_repeat_store:
 mov BYTE PTR [rbp+DS_LENGTHS+rdx],al
 inc edx
 dec ecx
 jnz boom_ds_dynamic_repeat_store
 mov DWORD PTR [rbp+88],edx
 mov DWORD PTR [rbp+12],7
boom_ds_dynamic_length_end:
 mov eax,DWORD PTR [rbp+76]
 add eax,DWORD PTR [rbp+80]
 cmp DWORD PTR [rbp+88],eax
 jb boom_ds_dynamic_lengths
 cmp BYTE PTR [rbp+DS_LENGTHS+256],0
 je boom_ds_bad_huffman
 lea rcx,[rbp+DS_LENGTHS]
 mov edx,DWORD PTR [rbp+76]
 lea r8,[rbp+DS_LIT]
 mov r9d,1
 call boom_ds_build
 test eax,eax
 jnz boom_ds_finish
 mov eax,DWORD PTR [rbp+76]
 lea rcx,[rbp+DS_LENGTHS+rax]
 mov edx,DWORD PTR [rbp+80]
 lea r8,[rbp+DS_DIST]
 mov r9d,2
 call boom_ds_build
 test eax,eax
 jnz boom_ds_finish
 mov DWORD PTR [rbp+12],9

boom_ds_compressed:
 mov ecx,DS_LIT
 call boom_ds_decode
 jc boom_ds_finish
 cmp eax,256
 jb boom_ds_new_literal
 je boom_ds_end_block
 cmp eax,285
 ja boom_ds_bad_symbol
 sub eax,257
 lea r10,boom_ds_length_base
 movzx edx,WORD PTR [r10+rax*2]
 mov DWORD PTR [rbp+128],edx
 lea r10,boom_ds_length_bits
 movzx edx,BYTE PTR [r10+rax]
 mov DWORD PTR [rbp+132],edx
 mov DWORD PTR [rbp+12],11
 jmp boom_ds_length_extra
boom_ds_new_literal:
 mov DWORD PTR [rbp+96],eax
 mov DWORD PTR [rbp+12],10
boom_ds_literal:
 cmp r15,r13
 jae boom_ds_need_output
 mov eax,DWORD PTR [rbp+96]
 call boom_ds_emit
 mov DWORD PTR [rbp+12],9
 jmp boom_ds_compressed
boom_ds_length_extra:
 mov ecx,DWORD PTR [rbp+132]
 call boom_ds_bits
 jc boom_ds_finish
 add eax,DWORD PTR [rbp+128]
 mov DWORD PTR [rbp+100],eax
 mov DWORD PTR [rbp+12],12
boom_ds_distance_code:
 mov ecx,DS_DIST
 call boom_ds_decode
 jc boom_ds_finish
 cmp eax,29
 ja boom_ds_bad_symbol
 lea r10,boom_ds_distance_base
 movzx edx,WORD PTR [r10+rax*2]
 mov DWORD PTR [rbp+128],edx
 lea r10,boom_ds_distance_bits
 movzx edx,BYTE PTR [r10+rax]
 mov DWORD PTR [rbp+132],edx
 mov DWORD PTR [rbp+12],13
boom_ds_distance_extra:
 mov ecx,DWORD PTR [rbp+132]
 call boom_ds_bits
 jc boom_ds_finish
 add eax,DWORD PTR [rbp+128]
 cmp eax,DWORD PTR [rbp+68]
 ja boom_ds_bad_distance
 cmp eax,32768
 ja boom_ds_bad_distance
 mov DWORD PTR [rbp+104],eax
 mov DWORD PTR [rbp+12],14
boom_ds_match:
 cmp DWORD PTR [rbp+100],0
 je boom_ds_match_done
 cmp r15,r13
 jae boom_ds_need_output
 mov eax,DWORD PTR [rbp+64]
 sub eax,DWORD PTR [rbp+104]
 and eax,32767
 movzx eax,BYTE PTR [rbp+DS_HISTORY+rax]
 call boom_ds_emit
 dec DWORD PTR [rbp+100]
 jmp boom_ds_match
boom_ds_match_done:
 mov DWORD PTR [rbp+12],9
 jmp boom_ds_compressed
boom_ds_end_block:
 cmp DWORD PTR [rbp+20],0
 jne boom_ds_new_finished
 mov DWORD PTR [rbp+12],0
 jmp boom_ds_header
boom_ds_new_finished:
 mov DWORD PTR [rbp+12],15
 jmp boom_ds_finish
boom_ds_need_output:
 mov DWORD PTR [rbx+44],2
 jmp boom_ds_finish
boom_ds_bad_block_type_reason:
 mov DWORD PTR [rbp+140],4
 jmp boom_ds_bad_block
boom_ds_bad_stored_length_reason:
 mov DWORD PTR [rbp+140],5
 jmp boom_ds_bad_block
boom_ds_bad_block:
 mov DWORD PTR [rbx+44],5
 jmp boom_ds_finish
boom_ds_bad_huffman:
 mov DWORD PTR [rbx+44],6
 jmp boom_ds_finish
boom_ds_bad_symbol:
 mov DWORD PTR [rbx+44],7
 jmp boom_ds_finish
boom_ds_bad_distance:
 mov DWORD PTR [rbx+44],8
boom_ds_finish:
 mov eax,DWORD PTR [rbx+44]
 cmp eax,4
 jb boom_ds_publish_totals
 mov DWORD PTR [rbp+16],eax
 mov DWORD PTR [rbp+12],16
boom_ds_publish_totals:
 add QWORD PTR [rbp+40],r14
 add QWORD PTR [rbp+48],r15
 test DWORD PTR [rbx+40],1
 jz boom_ds_publish_job
 cmp r14,r12
 jne boom_ds_publish_job
 mov DWORD PTR [rbp+136],1
boom_ds_publish_job:
 mov QWORD PTR [rbx+48],r14
 mov QWORD PTR [rbx+56],r15
 mov rax,QWORD PTR [rbp+40]
 mov QWORD PTR [rbx+64],rax
 mov rax,QWORD PTR [rbp+48]
 mov QWORD PTR [rbx+72],rax
 mov eax,DWORD PTR [rbp+140]
 mov DWORD PTR [rbx+92],eax
 jmp boom_ds_job_return
boom_ds_existing_error:
 mov eax,DWORD PTR [rbp+16]
 cmp eax,4
 jb boom_ds_invalid_state
 cmp eax,8
 ja boom_ds_invalid_state
 mov DWORD PTR [rbx+44],eax
 jmp boom_ds_publish_job
boom_ds_existing_finished:
 jmp boom_ds_publish_job
boom_ds_arguments:
 mov DWORD PTR [rbx+44],3
 jmp boom_ds_job_return
boom_ds_invalid_state:
 mov DWORD PTR [rbx+44],9
boom_ds_job_return:
 mov eax,DWORD PTR [rbx+44]
 jmp boom_ds_return
boom_ds_null_job:
 mov eax,3
boom_ds_return:
 add rsp,72
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_deflate_stream_step_reason ENDP
