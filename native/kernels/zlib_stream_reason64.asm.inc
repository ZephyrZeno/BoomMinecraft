; RFC1950 wrapper around the source-pinned incremental RFC1951 kernel.
; State34560 = header256 + unmodified opaque raw State34304 at offset256.
; Job96: raw Job80 shape, then Adler80,DICTID84,trailer88,reserved92.
; END_INPUT=1. Status0..9 raw-compatible;10 header,11 checksum,
; 12 dictionary identified but unsupported,13 CINFO distance,14 internal.
; Only the explicitly pinned raw phase/pending-op layout is READ below.
ZW_BYTES EQU 34560
ZW_MAGIC EQU 03142494C5A574F42h
ZW_RAW_BYTES EQU 34304
ZW_RAW_MAGIC EQU 0315354464C464544h
EXTERN boom_deflate_stream_reset:PROC
EXTERN boom_deflate_stream_step_reason:PROC
.code

; ECX packed seed,RDX bytes,R8 length -> EAX Adler32. Caller validates IO.
; The 5552-byte reduction interval bounds both unsigned 32-bit sums.
boom_zw_adler PROC PRIVATE
 mov r9d,ecx
 and r9d,65535
 mov r11d,ecx
 shr r11d,16
 cmp r9d,65521
 jb boom_zw_adler_s2
 sub r9d,65521
boom_zw_adler_s2:
 cmp r11d,65521
 jb boom_zw_adler_begin
 sub r11d,65521
boom_zw_adler_begin:
 test r8,r8
 jz boom_zw_adler_pack
 mov r10,rdx
boom_zw_adler_block:
 mov ecx,5552
 cmp r8,5552
 jae boom_zw_adler_count
 mov ecx,r8d
boom_zw_adler_count:
 sub r8,rcx
 mov edx,ecx
boom_zw_adler_byte:
 movzx ecx,BYTE PTR [r10]
 add r9d,ecx
 add r11d,r9d
 inc r10
 dec edx
 jnz boom_zw_adler_byte
 mov ecx,65521
 mov eax,r9d
 xor edx,edx
 div ecx
 mov r9d,edx
 mov eax,r11d
 xor edx,edx
 div ecx
 mov r11d,edx
 test r8,r8
 jnz boom_zw_adler_block
boom_zw_adler_pack:
 mov eax,r11d
 shl eax,16
 or eax,r9d
boom_zw_adler_return:
 ret
boom_zw_adler ENDP

PUBLIC boom_adler32_update_reason
; Job32: seed0 DWORD,reserved4 DWORD,src8,length16,result24,status28.
boom_adler32_update_reason PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz boom_zw_adler_null
 mov ecx,DWORD PTR [rbx]
 mov rdx,QWORD PTR [rbx+8]
 mov r8,QWORD PTR [rbx+16]
 mov QWORD PTR [rbx+24],0
 cmp DWORD PTR [rbx+4],0
 jne boom_zw_adler_arguments
 mov rax,01FFFFFFFFFFFFFFFh
 cmp r8,rax
 ja boom_zw_adler_arguments
 test r8,r8
 jz boom_zw_adler_call
 test rdx,rdx
 jz boom_zw_adler_arguments
 mov r9,rdx
 add r9,r8
 jc boom_zw_adler_arguments
 mov r10,rbx
 add r10,32
 jc boom_zw_adler_arguments
 cmp rdx,r10
 jae boom_zw_adler_call
 cmp r9,rbx
 ja boom_zw_adler_arguments
boom_zw_adler_call:
 call boom_zw_adler
 mov DWORD PTR [rbx+24],eax
 xor eax,eax
 jmp boom_zw_adler_done
boom_zw_adler_arguments:
 mov DWORD PTR [rbx+28],3
boom_zw_adler_null:
 mov eax,3
boom_zw_adler_done:
 add rsp,32
 pop rbx
 ret
boom_adler32_update_reason ENDP

; Acquire one wrapper byte; no bit cache or lookahead in this layer.
boom_zw_byte PROC PRIVATE
 cmp r14,r12
 jae boom_zw_byte_empty
 movzx eax,BYTE PTR [rsi+r14]
 inc r14
 clc
 ret
boom_zw_byte_empty:
 mov DWORD PTR [rbx+44],1
 test DWORD PTR [rbx+40],1
 jnz boom_zw_byte_eof
 cmp DWORD PTR [rbp+52],0
 je boom_zw_byte_wait
boom_zw_byte_eof:
 mov DWORD PTR [rbx+44],4
boom_zw_byte_wait:
 stc
 ret
boom_zw_byte ENDP

PUBLIC boom_zlib_stream_reset_reason
boom_zlib_stream_reset_reason PROC FRAME
 push rbx
 .pushreg rbx
 push rdi
 .pushreg rdi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov eax,3
 test rcx,rcx
 jz boom_zw_reset_done
 cmp edx,ZW_BYTES
 jne boom_zw_reset_done
 mov rax,rcx
 add rax,ZW_BYTES
 jc boom_zw_reset_arguments
 mov rbx,rcx
 mov rdi,rcx
 xor eax,eax
 mov ecx,ZW_BYTES/8
 rep stosq
 mov rax,ZW_MAGIC
 mov QWORD PTR [rbx],rax
 mov DWORD PTR [rbx+8],ZW_BYTES
 mov DWORD PTR [rbx+28],1
 lea rcx,[rbx+256]
 mov edx,ZW_RAW_BYTES
 call boom_deflate_stream_reset
 test eax,eax
 jz boom_zw_reset_done
 mov eax,14
 jmp boom_zw_reset_done
boom_zw_reset_arguments:
 mov eax,3
boom_zw_reset_done:
 add rsp,40
 pop rdi
 pop rbx
 ret
boom_zlib_stream_reset_reason ENDP

PUBLIC boom_zlib_stream_step_reason
boom_zlib_stream_step_reason PROC FRAME
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
 mov rbx,rcx
 test rbx,rbx
 jz boom_zw_null_job
 mov rbp,QWORD PTR [rbx]
 mov rsi,QWORD PTR [rbx+8]
 mov r12,QWORD PTR [rbx+16]
 mov rdi,QWORD PTR [rbx+24]
 mov r13,QWORD PTR [rbx+32]
 xor r14d,r14d
 xor r15d,r15d
 mov r8,rbx
 add r8,96
 jc boom_zw_null_job
 mov r9,rbp
 add r9,ZW_BYTES
 jc boom_zw_null_job
 cmp rbp,r8
 jae boom_zw_clear_job
 cmp r9,rbx
 ja boom_zw_null_job
boom_zw_clear_job:
 mov DWORD PTR [rbx+44],0
 mov QWORD PTR [rbx+48],0
 mov QWORD PTR [rbx+56],0
 mov QWORD PTR [rbx+64],0
 mov QWORD PTR [rbx+72],0
 mov QWORD PTR [rbx+80],0
 mov QWORD PTR [rbx+88],0
 test DWORD PTR [rbx+40],0FFFFFFFEh
 jnz boom_zw_arguments
 test rbp,rbp
 jz boom_zw_arguments
 mov rax,01FFFFFFFFFFFFFFFh
 cmp r12,rax
 ja boom_zw_arguments
 test r12,r12
 jz boom_zw_validate_dst
 test rsi,rsi
 jz boom_zw_arguments
boom_zw_validate_dst:
 test r13,r13
 jz boom_zw_validate_ends
 test rdi,rdi
 jz boom_zw_arguments
boom_zw_validate_ends:
 mov r8,rsi
 add r8,r12
 jc boom_zw_arguments
 mov r9,rdi
 add r9,r13
 jc boom_zw_arguments
 mov r10,rbp
 add r10,ZW_BYTES
 jc boom_zw_arguments
 mov r11,rbx
 add r11,96
 jc boom_zw_arguments
 test r12,r12
 jz boom_zw_validate_output
 cmp rsi,r11
 jae boom_zw_input_state
 cmp r8,rbx
 ja boom_zw_arguments
boom_zw_input_state:
 cmp rsi,r10
 jae boom_zw_validate_output
 cmp r8,rbp
 ja boom_zw_arguments
boom_zw_validate_output:
 test r13,r13
 jz boom_zw_validate_state
 cmp rdi,r11
 jae boom_zw_output_state
 cmp r9,rbx
 ja boom_zw_arguments
boom_zw_output_state:
 cmp rdi,r10
 jae boom_zw_input_output
 cmp r9,rbp
 ja boom_zw_arguments
boom_zw_input_output:
 test r12,r12
 jz boom_zw_validate_state
 cmp rsi,r9
 jae boom_zw_validate_state
 cmp rdi,r8
 jb boom_zw_arguments
boom_zw_validate_state:
 mov rax,ZW_MAGIC
 cmp QWORD PTR [rbp],rax
 jne boom_zw_invalid_state
 cmp DWORD PTR [rbp+8],ZW_BYTES
 jne boom_zw_invalid_state
 cmp DWORD PTR [rbp+12],7
 ja boom_zw_invalid_state
 cmp DWORD PTR [rbp+52],1
 ja boom_zw_invalid_state
 cmp DWORD PTR [rbp+12],5
 je boom_zw_publish_job
 cmp DWORD PTR [rbp+12],6
 je boom_zw_existing_error
 cmp DWORD PTR [rbp+12],7
 je boom_zw_existing_dictionary
 cmp DWORD PTR [rbp+52],0
 je boom_zw_validate_totals
 test r12,r12
 jnz boom_zw_arguments
boom_zw_validate_totals:
 mov rax,QWORD PTR [rbp+56]
 add rax,r12
 jc boom_zw_arguments
 mov rdx,01FFFFFFFFFFFFFFFh
 cmp rax,rdx
 ja boom_zw_arguments
 mov rax,QWORD PTR [rbp+64]
 add rax,r13
 jc boom_zw_arguments
boom_zw_dispatch:
 mov DWORD PTR [rbp+72],0
 mov eax,DWORD PTR [rbp+12]
 test eax,eax
 jz boom_zw_cmf
 cmp eax,1
 je boom_zw_flg
 cmp eax,2
 je boom_zw_dictionary
 cmp eax,3
 je boom_zw_raw
 cmp eax,4
 je boom_zw_trailer
 jmp boom_zw_internal
boom_zw_cmf:
 call boom_zw_byte
 jc boom_zw_finish
 mov DWORD PTR [rbp+20],eax
 mov edx,eax
 and edx,15
 cmp edx,8
 jne boom_zw_bad_header
 shr eax,4
 cmp eax,7
 ja boom_zw_bad_header
 lea ecx,[rax+8]
 mov eax,1
 shl eax,cl
 mov DWORD PTR [rbp+36],eax
 mov DWORD PTR [rbp+12],1
boom_zw_flg:
 call boom_zw_byte
 jc boom_zw_finish
 mov DWORD PTR [rbp+24],eax
 mov eax,DWORD PTR [rbp+20]
 shl eax,8
 or eax,DWORD PTR [rbp+24]
 xor edx,edx
 mov ecx,31
 div ecx
 test edx,edx
 jnz boom_zw_bad_fcheck_reason
 test DWORD PTR [rbp+24],32
 jz boom_zw_new_raw
 mov DWORD PTR [rbp+12],2
boom_zw_dictionary:
 call boom_zw_byte
 jc boom_zw_finish
 shl DWORD PTR [rbp+32],8
 or DWORD PTR [rbp+32],eax
 inc DWORD PTR [rbp+40]
 cmp DWORD PTR [rbp+40],4
 jb boom_zw_dictionary
 mov DWORD PTR [rbp+12],7
 mov DWORD PTR [rbx+44],12
 jmp boom_zw_finish
boom_zw_new_raw:
 mov DWORD PTR [rbp+12],3
boom_zw_raw:
 mov rax,ZW_RAW_MAGIC
 cmp QWORD PTR [rbp+256],rax
 jne boom_zw_internal
 cmp DWORD PTR [rbp+264],ZW_RAW_BYTES
 jne boom_zw_internal
 lea rax,[rbp+256]
 mov QWORD PTR [rsp+32],rax
 lea rax,[rsi+r14]
 mov QWORD PTR [rsp+40],rax
 mov rax,r12
 sub rax,r14
 mov QWORD PTR [rsp+48],rax
 lea rax,[rdi+r15]
 mov QWORD PTR [rsp+56],rax
 mov rax,r13
 sub rax,r15
 ; CINFO7 uses the full remaining output fast path. Smaller windows use
 ; bounded raw pending-op stepping, so each distance is checked before copy.
 cmp DWORD PTR [rbp+36],32768
 je boom_zw_raw_capacity
 mov edx,DWORD PTR [rbp+268]
 cmp edx,4
 je boom_zw_raw_stored
 cmp edx,10
 je boom_zw_raw_literal
 cmp edx,14
 je boom_zw_raw_match
 xor eax,eax
 jmp boom_zw_raw_capacity
boom_zw_raw_stored:
 mov edx,DWORD PTR [rbp+328]
 jmp boom_zw_raw_minimum
boom_zw_raw_literal:
 mov edx,1
 jmp boom_zw_raw_minimum
boom_zw_raw_match:
 mov edx,DWORD PTR [rbp+360]
 cmp edx,DWORD PTR [rbp+36]
 ja boom_zw_bad_window
 mov edx,DWORD PTR [rbp+356]
boom_zw_raw_minimum:
 cmp rax,rdx
 cmova rax,rdx
boom_zw_raw_capacity:
 mov QWORD PTR [rsp+64],rax
 mov eax,DWORD PTR [rbx+40]
 or eax,DWORD PTR [rbp+52]
 mov DWORD PTR [rsp+72],eax
 lea rcx,[rsp+32]
 call boom_deflate_stream_step_reason
 mov DWORD PTR [rsp+112],eax
 mov rax,QWORD PTR [rsp+80]
 cmp rax,QWORD PTR [rsp+48]
 ja boom_zw_internal
 add r14,rax
 mov r8,QWORD PTR [rsp+88]
 cmp r8,QWORD PTR [rsp+64]
 ja boom_zw_internal
 mov ecx,DWORD PTR [rbp+28]
 lea rdx,[rdi+r15]
 call boom_zw_adler
 mov DWORD PTR [rbp+28],eax
 add r15,QWORD PTR [rsp+88]
 mov eax,DWORD PTR [rsp+112]
 test eax,eax
 jz boom_zw_new_trailer
 cmp eax,1
 je boom_zw_need_input
 cmp eax,2
 je boom_zw_raw_need_output
 cmp eax,4
 jb boom_zw_internal
 cmp eax,8
 ja boom_zw_internal
 mov ecx,DWORD PTR [rsp+124]
 mov DWORD PTR [rbp+72],ecx
 mov DWORD PTR [rbx+44],eax
 jmp boom_zw_finish
boom_zw_raw_need_output:
 cmp r15,r13
 jb boom_zw_raw
 mov DWORD PTR [rbx+44],2
 jmp boom_zw_finish
boom_zw_need_input:
 mov DWORD PTR [rbx+44],1
 test DWORD PTR [rbx+40],1
 jnz boom_zw_truncated
 cmp DWORD PTR [rbp+52],0
 jne boom_zw_truncated
 jmp boom_zw_finish
boom_zw_new_trailer:
 cmp DWORD PTR [rbp+268],15
 jne boom_zw_internal
 cmp DWORD PTR [rbp+288],7
 ja boom_zw_internal
 mov DWORD PTR [rbp+12],4
boom_zw_trailer:
 call boom_zw_byte
 jc boom_zw_finish
 shl DWORD PTR [rbp+48],8
 or DWORD PTR [rbp+48],eax
 inc DWORD PTR [rbp+44]
 cmp DWORD PTR [rbp+44],4
 jb boom_zw_trailer
 mov eax,DWORD PTR [rbp+48]
 cmp eax,DWORD PTR [rbp+28]
 jne boom_zw_bad_checksum
 mov DWORD PTR [rbp+12],5
 jmp boom_zw_finish
boom_zw_truncated:
 mov DWORD PTR [rbx+44],4
 jmp boom_zw_finish
boom_zw_bad_fcheck_reason:
 mov DWORD PTR [rbp+72],1
 jmp boom_zw_bad_header
boom_zw_bad_header:
 mov DWORD PTR [rbx+44],10
 jmp boom_zw_finish
boom_zw_bad_checksum:
 mov DWORD PTR [rbx+44],11
 jmp boom_zw_finish
boom_zw_bad_window:
 mov DWORD PTR [rbx+44],13
 jmp boom_zw_finish
boom_zw_internal:
 mov DWORD PTR [rbx+44],14
boom_zw_finish:
 mov eax,DWORD PTR [rbx+44]
 cmp eax,4
 jb boom_zw_publish_totals
 cmp eax,12
 je boom_zw_publish_totals
 mov DWORD PTR [rbp+16],eax
 mov DWORD PTR [rbp+12],6
boom_zw_publish_totals:
 add QWORD PTR [rbp+56],r14
 add QWORD PTR [rbp+64],r15
 test DWORD PTR [rbx+40],1
 jz boom_zw_publish_job
 cmp r14,r12
 jne boom_zw_publish_job
 mov DWORD PTR [rbp+52],1
boom_zw_publish_job:
 mov QWORD PTR [rbx+48],r14
 mov QWORD PTR [rbx+56],r15
 mov rax,QWORD PTR [rbp+56]
 mov QWORD PTR [rbx+64],rax
 mov rax,QWORD PTR [rbp+64]
 mov QWORD PTR [rbx+72],rax
 mov eax,DWORD PTR [rbp+28]
 mov DWORD PTR [rbx+80],eax
 mov eax,DWORD PTR [rbp+32]
 mov DWORD PTR [rbx+84],eax
 mov eax,DWORD PTR [rbp+48]
 mov DWORD PTR [rbx+88],eax
 mov eax,DWORD PTR [rbp+72]
 mov DWORD PTR [rbx+92],eax
 jmp boom_zw_job_return
boom_zw_existing_dictionary:
 mov DWORD PTR [rbx+44],12
 jmp boom_zw_publish_job
boom_zw_existing_error:
 mov eax,DWORD PTR [rbp+16]
 cmp eax,4
 jb boom_zw_invalid_state
 cmp eax,14
 ja boom_zw_invalid_state
 mov DWORD PTR [rbx+44],eax
 jmp boom_zw_publish_job
boom_zw_arguments:
 mov DWORD PTR [rbx+44],3
 jmp boom_zw_job_return
boom_zw_invalid_state:
 mov DWORD PTR [rbx+44],9
boom_zw_job_return:
 mov eax,DWORD PTR [rbx+44]
 jmp boom_zw_return
boom_zw_null_job:
 mov eax,3
boom_zw_return:
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
boom_zlib_stream_step_reason ENDP
