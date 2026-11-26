; One complete RFC1951 raw stream; no allocator, OS decoder, mutable globals,
; wrapper, preset dictionary or incremental/resume API. Windows x64 ABI.
; Job64: src0,len8,dst16,cap24,consumed32,written40,lastByteBits48,status52,
; bitPosition56. Status:0 OK,1 arguments,2 truncated,3 output full,4 block,
; 5 Huffman,6 symbol/repeat,7 distance. Progress on error is private-reader
; progress, not a claim to reproduce zlib's partial-output error policy.
; Internal IO registers: RBX job,RSI src,RDI dst,R12 len,R13 cap,R14 bitpos,
; R15 written. All workspace is on the owning native stack, below 2KiB.
.const
boom_deflate_dr_cl_order BYTE 16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15
boom_deflate_dr_length_base WORD 3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258
boom_deflate_dr_length_extra BYTE 0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0
boom_deflate_dr_distance_base WORD 1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577
boom_deflate_dr_distance_extra BYTE 0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13
.code

; ECX bits0..16 -> EAX little-endian value, CF=truncation. No lookahead.
boom_deflate_dr_bits PROC PRIVATE
 mov r8d,ecx
 xor r9d,r9d
 xor r10d,r10d
 test r8d,r8d
 jz boom_deflate_dr_bits_done
boom_deflate_dr_bits_loop:
 mov rax,r14
 shr rax,3
 cmp rax,r12
 jae boom_deflate_dr_bits_short
 movzx edx,BYTE PTR [rsi+rax]
 mov ecx,r14d
 and ecx,7
 shr edx,cl
 and edx,1
 mov ecx,r10d
 shl edx,cl
 or r9d,edx
 inc r14
 inc r10d
 cmp r10d,r8d
 jb boom_deflate_dr_bits_loop
boom_deflate_dr_bits_done:
 mov eax,r9d
 clc
 ret
boom_deflate_dr_bits_short:
 mov DWORD PTR [rbx+52],2
 stc
 ret
boom_deflate_dr_bits ENDP

; Build canonical counts[16]DWORD + sorted symbols[]WORD.
; RCX byte lengths,EDX count,R8 table,R9 kind0 code-length/1 literal/2 distance.
; table[0] becomes maximum code length. Empty distance tree is permitted, but
; any attempt to decode it is invalid. Single one-bit literal/distance trees
; are valid; other incomplete trees and oversubscribed trees are rejected.
boom_deflate_dr_build PROC PRIVATE FRAME
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
boom_deflate_dr_build_count:
 cmp r9d,DWORD PTR [rsp+40]
 jae boom_deflate_dr_build_check
 movzx eax,BYTE PTR [rcx+r9]
 cmp eax,15
 ja boom_deflate_dr_build_bad
 test eax,eax
 jz boom_deflate_dr_build_next
 inc DWORD PTR [rbp+rax*4]
 cmp eax,r10d
 cmova r10d,eax
boom_deflate_dr_build_next:
 inc r9d
 jmp boom_deflate_dr_build_count
boom_deflate_dr_build_check:
 mov DWORD PTR [rbp],r10d
 test r10d,r10d
 jnz boom_deflate_dr_build_nonempty
 cmp DWORD PTR [rsp+44],2
 jne boom_deflate_dr_build_bad
 jmp boom_deflate_dr_build_good
boom_deflate_dr_build_nonempty:
 mov edx,1
 mov r9d,1
boom_deflate_dr_build_kraft:
 shl edx,1
 sub edx,DWORD PTR [rbp+r9*4]
 js boom_deflate_dr_build_bad
 inc r9d
 cmp r9d,16
 jb boom_deflate_dr_build_kraft
 test edx,edx
 jz boom_deflate_dr_build_sort
 cmp DWORD PTR [rsp+44],0
 je boom_deflate_dr_build_bad
 cmp DWORD PTR [rbp],1
 jne boom_deflate_dr_build_bad
boom_deflate_dr_build_sort:
 xor eax,eax
 mov r9d,1
boom_deflate_dr_build_offsets:
 mov DWORD PTR [rsp+48+r9*4],eax
 add eax,DWORD PTR [rbp+r9*4]
 inc r9d
 cmp r9d,16
 jb boom_deflate_dr_build_offsets
 mov rcx,QWORD PTR [rsp+32]
 xor r9d,r9d
boom_deflate_dr_build_symbols:
 cmp r9d,DWORD PTR [rsp+40]
 jae boom_deflate_dr_build_good
 movzx edx,BYTE PTR [rcx+r9]
 test edx,edx
 jz boom_deflate_dr_build_symbol_next
 mov eax,DWORD PTR [rsp+48+rdx*4]
 inc DWORD PTR [rsp+48+rdx*4]
 mov WORD PTR [rbp+64+rax*2],r9w
boom_deflate_dr_build_symbol_next:
 inc r9d
 jmp boom_deflate_dr_build_symbols
boom_deflate_dr_build_good:
 xor eax,eax
 add rsp,112
 pop rbp
 ret
boom_deflate_dr_build_bad:
 mov DWORD PTR [rbx+52],5
 mov eax,1
 add rsp,112
 pop rbp
 ret
boom_deflate_dr_build ENDP

; RCX canonical table -> symbol EAX, CF=error. Read Huffman bits in stream
; order; form the MSB-first canonical code without table lookahead bytes.
boom_deflate_dr_decode PROC PRIVATE FRAME
 push rbp
 .pushreg rbp
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbp,rcx
 cmp DWORD PTR [rbp],0
 je boom_deflate_dr_decode_bad
 mov DWORD PTR [rsp+32],0
 mov DWORD PTR [rsp+36],0
 mov DWORD PTR [rsp+40],0
 mov DWORD PTR [rsp+44],1
boom_deflate_dr_decode_loop:
 mov ecx,1
 call boom_deflate_dr_bits
 jc boom_deflate_dr_decode_error
 mov edx,DWORD PTR [rsp+32]
 shl edx,1
 or edx,eax
 mov DWORD PTR [rsp+32],edx
 mov ecx,DWORD PTR [rsp+44]
 mov r8d,DWORD PTR [rbp+rcx*4]
 sub edx,DWORD PTR [rsp+36]
 cmp edx,r8d
 jb boom_deflate_dr_decode_found
 add DWORD PTR [rsp+40],r8d
 mov eax,DWORD PTR [rsp+36]
 add eax,r8d
 shl eax,1
 mov DWORD PTR [rsp+36],eax
 inc DWORD PTR [rsp+44]
 mov eax,DWORD PTR [rsp+44]
 cmp eax,DWORD PTR [rbp]
 jbe boom_deflate_dr_decode_loop
boom_deflate_dr_decode_bad:
 mov DWORD PTR [rbx+52],5
boom_deflate_dr_decode_error:
 add rsp,64
 pop rbp
 stc
 ret
boom_deflate_dr_decode_found:
 add edx,DWORD PTR [rsp+40]
 movzx eax,WORD PTR [rbp+64+rdx*2]
 add rsp,64
 pop rbp
 clc
 ret
boom_deflate_dr_decode ENDP

PUBLIC boom_deflate_raw64
boom_deflate_raw64 PROC FRAME
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
 sub rsp,1400
 .allocstack 1400
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz boom_deflate_dr_null_job
 mov rsi,QWORD PTR [rbx]
 mov r12,QWORD PTR [rbx+8]
 mov rdi,QWORD PTR [rbx+16]
 mov r13,QWORD PTR [rbx+24]
 xor r14d,r14d
 xor r15d,r15d
 mov QWORD PTR [rbx+32],0
 mov QWORD PTR [rbx+40],0
 mov QWORD PTR [rbx+48],0
 mov QWORD PTR [rbx+56],0
 mov rax,01FFFFFFFFFFFFFFFh
 cmp r12,rax
 ja boom_deflate_dr_arguments
 test r12,r12
 jz boom_deflate_dr_validate_destination
 test rsi,rsi
 jz boom_deflate_dr_arguments
boom_deflate_dr_validate_destination:
 test r13,r13
 jz boom_deflate_dr_validate_ranges
 test rdi,rdi
 jz boom_deflate_dr_arguments
boom_deflate_dr_validate_ranges:
 mov r8,rsi
 add r8,r12
 jc boom_deflate_dr_arguments
 mov r9,rdi
 add r9,r13
 jc boom_deflate_dr_arguments
 mov r10,rbx
 add r10,64
 jc boom_deflate_dr_arguments
 test r12,r12
 jz boom_deflate_dr_check_job_destination
 cmp rsi,r10
 jae boom_deflate_dr_check_job_destination
 cmp r8,rbx
 ja boom_deflate_dr_arguments
boom_deflate_dr_check_job_destination:
 test r13,r13
 jz boom_deflate_dr_block_header
 cmp rdi,r10
 jae boom_deflate_dr_check_io_overlap
 cmp r9,rbx
 ja boom_deflate_dr_arguments
boom_deflate_dr_check_io_overlap:
 test r12,r12
 jz boom_deflate_dr_block_header
 cmp rsi,r9
 jae boom_deflate_dr_block_header
 cmp rdi,r8
 jb boom_deflate_dr_arguments

boom_deflate_dr_block_header:
 mov ecx,3
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 mov edx,eax
 and edx,1
 mov DWORD PTR [rsp+32],edx
 shr eax,1
 test eax,eax
 jz boom_deflate_dr_stored
 cmp eax,1
 je boom_deflate_dr_fixed
 cmp eax,2
 je boom_deflate_dr_dynamic
 jmp boom_deflate_dr_bad_block

boom_deflate_dr_stored:
 add r14,7
 and r14,-8
 mov ecx,16
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 mov DWORD PTR [rsp+52],eax
 mov ecx,16
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 xor eax,DWORD PTR [rsp+52]
 cmp eax,0FFFFh
 jne boom_deflate_dr_bad_block
 mov eax,DWORD PTR [rsp+52]
 mov r8,r14
 shr r8,3
 mov r9,r12
 sub r9,r8
 cmp rax,r9
 ja boom_deflate_dr_stored_short
 mov r9,r13
 sub r9,r15
 cmp rax,r9
 ja boom_deflate_dr_output_full
 test eax,eax
 jz boom_deflate_dr_end_block
 mov ecx,eax
boom_deflate_dr_stored_copy:
 mov al,BYTE PTR [rsi+r8]
 mov BYTE PTR [rdi+r15],al
 inc r8
 inc r15
 add r14,8
 dec ecx
 jnz boom_deflate_dr_stored_copy
 jmp boom_deflate_dr_end_block
boom_deflate_dr_stored_short:
 mov DWORD PTR [rbx+52],2
 jmp boom_deflate_dr_finish

boom_deflate_dr_fixed:
 xor ecx,ecx
boom_deflate_dr_fixed_lens:
 mov al,8
 cmp ecx,144
 jb boom_deflate_dr_fixed_store
 mov al,9
 cmp ecx,256
 jb boom_deflate_dr_fixed_store
 mov al,7
 cmp ecx,280
 jb boom_deflate_dr_fixed_store
 mov al,8
boom_deflate_dr_fixed_store:
 mov BYTE PTR [rsp+944+rcx],al
 inc ecx
 cmp ecx,288
 jb boom_deflate_dr_fixed_lens
 mov ecx,288
boom_deflate_dr_fixed_dist:
 mov BYTE PTR [rsp+944+rcx],5
 inc ecx
 cmp ecx,320
 jb boom_deflate_dr_fixed_dist
 lea rcx,[rsp+944]
 mov edx,288
 lea r8,[rsp+64]
 mov r9d,1
 call boom_deflate_dr_build
 test eax,eax
 jnz boom_deflate_dr_finish
 lea rcx,[rsp+1232]
 mov edx,32
 lea r8,[rsp+704]
 mov r9d,2
 call boom_deflate_dr_build
 test eax,eax
 jnz boom_deflate_dr_finish
 jmp boom_deflate_dr_compressed

boom_deflate_dr_dynamic:
 mov ecx,14
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 mov edx,eax
 and edx,31
 add edx,257
 cmp edx,286
 ja boom_deflate_dr_bad_huffman
 mov DWORD PTR [rsp+40],edx
 mov edx,eax
 shr edx,5
 and edx,31
 inc edx
 mov DWORD PTR [rsp+44],edx
 shr eax,10
 add eax,4
 mov DWORD PTR [rsp+48],eax
 pxor xmm0,xmm0
 movdqu XMMWORD PTR [rsp+1264],xmm0
 movdqu XMMWORD PTR [rsp+1280],xmm0
 mov DWORD PTR [rsp+52],0
boom_deflate_dr_dynamic_cl:
 mov ecx,3
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 mov edx,DWORD PTR [rsp+52]
 lea r10,boom_deflate_dr_cl_order
 movzx edx,BYTE PTR [r10+rdx]
 mov BYTE PTR [rsp+1264+rdx],al
 inc DWORD PTR [rsp+52]
 mov eax,DWORD PTR [rsp+52]
 cmp eax,DWORD PTR [rsp+48]
 jb boom_deflate_dr_dynamic_cl
 lea rcx,[rsp+1264]
 mov edx,19
 lea r8,[rsp+832]
 xor r9d,r9d
 call boom_deflate_dr_build
 test eax,eax
 jnz boom_deflate_dr_finish
 mov DWORD PTR [rsp+52],0
 mov DWORD PTR [rsp+56],0
boom_deflate_dr_dynamic_lengths:
 lea rcx,[rsp+832]
 call boom_deflate_dr_decode
 jc boom_deflate_dr_finish
 cmp eax,15
 ja boom_deflate_dr_dynamic_repeat
 mov edx,DWORD PTR [rsp+52]
 mov BYTE PTR [rsp+944+rdx],al
 mov DWORD PTR [rsp+56],eax
 inc DWORD PTR [rsp+52]
 jmp boom_deflate_dr_dynamic_length_end
boom_deflate_dr_dynamic_repeat:
 cmp eax,16
 jne boom_deflate_dr_dynamic_zero
 cmp DWORD PTR [rsp+52],0
 je boom_deflate_dr_bad_symbol
 mov ecx,2
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 add eax,3
 jmp boom_deflate_dr_dynamic_repeat_ready
boom_deflate_dr_dynamic_zero:
 mov DWORD PTR [rsp+56],0
 cmp eax,17
 jne boom_deflate_dr_dynamic_long_zero
 mov ecx,3
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 add eax,3
 jmp boom_deflate_dr_dynamic_repeat_ready
boom_deflate_dr_dynamic_long_zero:
 cmp eax,18
 jne boom_deflate_dr_bad_symbol
 mov ecx,7
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 add eax,11
boom_deflate_dr_dynamic_repeat_ready:
 mov ecx,eax
 add eax,DWORD PTR [rsp+52]
 mov edx,DWORD PTR [rsp+40]
 add edx,DWORD PTR [rsp+44]
 cmp eax,edx
 ja boom_deflate_dr_bad_symbol
 mov edx,DWORD PTR [rsp+52]
 mov eax,DWORD PTR [rsp+56]
boom_deflate_dr_dynamic_repeat_store:
 mov BYTE PTR [rsp+944+rdx],al
 inc edx
 dec ecx
 jnz boom_deflate_dr_dynamic_repeat_store
 mov DWORD PTR [rsp+52],edx
boom_deflate_dr_dynamic_length_end:
 mov eax,DWORD PTR [rsp+40]
 add eax,DWORD PTR [rsp+44]
 cmp DWORD PTR [rsp+52],eax
 jb boom_deflate_dr_dynamic_lengths
 cmp BYTE PTR [rsp+1200],0
 je boom_deflate_dr_bad_huffman
 lea rcx,[rsp+944]
 mov edx,DWORD PTR [rsp+40]
 lea r8,[rsp+64]
 mov r9d,1
 call boom_deflate_dr_build
 test eax,eax
 jnz boom_deflate_dr_finish
 mov eax,DWORD PTR [rsp+40]
 lea rcx,[rsp+944+rax]
 mov edx,DWORD PTR [rsp+44]
 lea r8,[rsp+704]
 mov r9d,2
 call boom_deflate_dr_build
 test eax,eax
 jnz boom_deflate_dr_finish

boom_deflate_dr_compressed:
 lea rcx,[rsp+64]
 call boom_deflate_dr_decode
 jc boom_deflate_dr_finish
 cmp eax,256
 jb boom_deflate_dr_literal
 je boom_deflate_dr_end_block
 cmp eax,285
 ja boom_deflate_dr_bad_symbol
 sub eax,257
 lea r10,boom_deflate_dr_length_base
 movzx ebp,WORD PTR [r10+rax*2]
 lea r10,boom_deflate_dr_length_extra
 movzx ecx,BYTE PTR [r10+rax]
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 add ebp,eax
 lea rcx,[rsp+704]
 call boom_deflate_dr_decode
 jc boom_deflate_dr_finish
 cmp eax,29
 ja boom_deflate_dr_bad_symbol
 lea r10,boom_deflate_dr_distance_base
 movzx edx,WORD PTR [r10+rax*2]
 mov DWORD PTR [rsp+52],edx
 lea r10,boom_deflate_dr_distance_extra
 movzx ecx,BYTE PTR [r10+rax]
 call boom_deflate_dr_bits
 jc boom_deflate_dr_finish
 add eax,DWORD PTR [rsp+52]
 cmp rax,r15
 ja boom_deflate_dr_bad_distance
 cmp eax,32768
 ja boom_deflate_dr_bad_distance
 mov r10,rax
 mov rax,r13
 sub rax,r15
 cmp rbp,rax
 ja boom_deflate_dr_output_full
 mov rcx,r15
 sub rcx,r10
boom_deflate_dr_match:
 mov al,BYTE PTR [rdi+rcx]
 mov BYTE PTR [rdi+r15],al
 inc rcx
 inc r15
 dec ebp
 jnz boom_deflate_dr_match
 jmp boom_deflate_dr_compressed
boom_deflate_dr_literal:
 cmp r15,r13
 jae boom_deflate_dr_output_full
 mov BYTE PTR [rdi+r15],al
 inc r15
 jmp boom_deflate_dr_compressed

boom_deflate_dr_end_block:
 cmp DWORD PTR [rsp+32],0
 je boom_deflate_dr_block_header
 jmp boom_deflate_dr_finish
boom_deflate_dr_arguments:
 mov DWORD PTR [rbx+52],1
 jmp boom_deflate_dr_finish
boom_deflate_dr_bad_block:
 mov DWORD PTR [rbx+52],4
 jmp boom_deflate_dr_finish
boom_deflate_dr_bad_huffman:
 mov DWORD PTR [rbx+52],5
 jmp boom_deflate_dr_finish
boom_deflate_dr_bad_symbol:
 mov DWORD PTR [rbx+52],6
 jmp boom_deflate_dr_finish
boom_deflate_dr_bad_distance:
 mov DWORD PTR [rbx+52],7
 jmp boom_deflate_dr_finish
boom_deflate_dr_output_full:
 mov DWORD PTR [rbx+52],3
boom_deflate_dr_finish:
 mov rax,r14
 add rax,7
 shr rax,3
 mov QWORD PTR [rbx+32],rax
 mov QWORD PTR [rbx+40],r15
 mov eax,r14d
 and eax,7
 mov DWORD PTR [rbx+48],eax
 mov QWORD PTR [rbx+56],r14
 mov eax,DWORD PTR [rbx+52]
 jmp boom_deflate_dr_return
boom_deflate_dr_null_job:
 mov eax,1
boom_deflate_dr_return:
 add rsp,1400
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
boom_deflate_raw64 ENDP
