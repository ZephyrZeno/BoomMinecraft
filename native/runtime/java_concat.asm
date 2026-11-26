; Normal source String concatenation. No opaque String/JVM/C runtime.
; (Context32 RCX, captured argv64 RDX, Pool80 R8) -> fresh normal String / NULL.
; Pool80: magic0 ABI4 rows8 argc12 rows*16 heapCell24 StringLayout32,
; value/coder/hash/zero offsets40/44/48/52 compact56 reserved60 ctxBytes64
; reserved68 reserved72. Row24: kind0 argIndex4 UTF16*8 charCount16.
; kinds: 0 literal,1 int,2 long,3 boolean,4 char,5 normal String (NULL->null).
; Object/float conversions run original source Java through generated thunks.
; Caller retains stack references; collection remains explicit/quiescent.
option casemap:none
EXTERN boom_array_new:PROC
EXTERN boom_object_new:PROC
PUBLIC boom_java_concat
.const
java_concat_null WORD 110,117,108,108
java_concat_true WORD 116,114,117,101
java_concat_false WORD 102,97,108,115,101
.code
boom_java_concat PROC FRAME
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
 sub rsp,128
 .allocstack 128
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov r13,r8
 test rbx,rbx
 jz java_concat_zero
 cmp DWORD PTR [rbx],0
 jne java_concat_zero
 test r13,r13
 jz java_concat_bad
 cmp DWORD PTR [r13],04A434E43h
 jne java_concat_bad
 cmp DWORD PTR [r13+4],1
 jne java_concat_bad
 cmp DWORD PTR [r13+8],65535
 ja java_concat_bad
 cmp DWORD PTR [r13+12],200
 ja java_concat_bad
 cmp DWORD PTR [r13+12],0
 je java_concat_args_ready
 test r12,r12
 jz java_concat_bad
java_concat_args_ready:
 cmp QWORD PTR [r13+16],0
 je java_concat_bad
 cmp DWORD PTR [r13+40],0
 jne java_concat_bad
 cmp DWORD PTR [r13+56],1
 ja java_concat_bad
 cmp DWORD PTR [r13+60],0
 jne java_concat_bad
 cmp DWORD PTR [r13+64],32
 jne java_concat_bad
 cmp DWORD PTR [r13+68],0
 jne java_concat_bad
 cmp QWORD PTR [r13+72],0
 jne java_concat_bad
 mov r10,QWORD PTR [r13+32]
 test r10,r10
 jz java_concat_bad
 cmp DWORD PTR [r10],04F424A43h
 jne java_concat_bad
 cmp DWORD PTR [r10+4],2
 jne java_concat_bad
 cmp DWORD PTR [r10+16],1
 jne java_concat_bad
 cmp DWORD PTR [r10+20],4
 jne java_concat_bad
 mov r11,QWORD PTR [r10+8]
 cmp r11,14
 jb java_concat_bad
 cmp r11,32
 ja java_concat_bad
 mov eax,DWORD PTR [r13+48]
 cmp eax,8
 jb java_concat_bad
 test al,3
 jnz java_concat_bad
 lea edx,[eax+4]
 cmp rdx,r11
 ja java_concat_bad
 mov ecx,DWORD PTR [r13+44]
 cmp ecx,8
 jb java_concat_bad
 cmp rcx,r11
 jae java_concat_bad
 cmp ecx,eax
 jb java_concat_coder_ready
 cmp ecx,edx
 jb java_concat_bad
java_concat_coder_ready:
 mov r8d,DWORD PTR [r13+52]
 cmp r8d,8
 jb java_concat_bad
 cmp r8,r11
 jae java_concat_bad
 cmp r8d,ecx
 je java_concat_bad
 cmp r8d,eax
 jb java_concat_offsets_ready
 cmp r8d,edx
 jb java_concat_bad
java_concat_offsets_ready:
 mov rax,QWORD PTR [r13+24]
 test rax,rax
 jz java_concat_bad
 mov rax,QWORD PTR [rax]
 test rax,rax
 jz java_concat_unbound
 cmp DWORD PTR [rax],048454150h
 jne java_concat_bad
 cmp DWORD PTR [rax+4],1
 jne java_concat_bad
 mov QWORD PTR [rsp+64],rax
 mov eax,DWORD PTR [r13+56]
 mov DWORD PTR [rsp+32],eax
 mov DWORD PTR [rsp+36],0
 xor r14d,r14d
 lea rsi,[rsp+80]
 mov rdi,QWORD PTR [r13+16]
java_concat_measure:
 mov eax,DWORD PTR [rsp+36]
 cmp eax,DWORD PTR [r13+8]
 jae java_concat_allocate
 call java_concat_piece
 cmp DWORD PTR [rbx],0
 jne java_concat_zero
 mov r8d,ecx
 add r14,r8
 cmp r14,07FFFFFFFh
 ja java_concat_oom
 cmp DWORD PTR [rsp+32],0
 je java_concat_measured
 test edx,edx
 jz java_concat_measured
 xor r8d,r8d
java_concat_latin_scan:
 cmp r8d,ecx
 jae java_concat_measured
 cmp WORD PTR [rax+r8*2],255
 ja java_concat_wide
 inc r8d
 jmp java_concat_latin_scan
java_concat_wide:
 mov DWORD PTR [rsp+32],0
java_concat_measured:
 inc DWORD PTR [rsp+36]
 add rdi,24
 jmp java_concat_measure
java_concat_allocate:
 mov rdx,r14
 cmp DWORD PTR [rsp+32],1
 je java_concat_bytes_ready
 shl rdx,1
 cmp rdx,07FFFFFFFh
 ja java_concat_oom
java_concat_bytes_ready:
 mov rcx,QWORD PTR [rsp+64]
 mov r8d,8
 mov r9,rbx
 call boom_array_new
 test rax,rax
 jz java_concat_zero
 mov r15,rax
 mov QWORD PTR [rsp+40],0
 mov DWORD PTR [rsp+48],0
 mov DWORD PTR [rsp+36],0
 mov rdi,QWORD PTR [r13+16]
java_concat_copy_row:
 mov eax,DWORD PTR [rsp+36]
 cmp eax,DWORD PTR [r13+8]
 jae java_concat_make_String
 call java_concat_piece
 cmp DWORD PTR [rbx],0
 jne java_concat_zero
 mov r9d,ecx
 mov r11d,edx
 xor r8d,r8d
java_concat_copy_char:
 cmp r8d,r9d
 jae java_concat_copied_row
 test r11d,r11d
 jnz java_concat_read_wide
 movzx r10d,BYTE PTR [rax+r8]
 jmp java_concat_write
java_concat_read_wide:
 movzx r10d,WORD PTR [rax+r8*2]
java_concat_write:
 mov edx,DWORD PTR [rsp+48]
 imul edx,edx,31
 add edx,r10d
 mov DWORD PTR [rsp+48],edx
 mov rdx,QWORD PTR [rsp+40]
 cmp rdx,r14
 jae java_concat_bad
 cmp DWORD PTR [rsp+32],1
 jne java_concat_write_wide
 cmp r10d,255
 ja java_concat_bad
 mov BYTE PTR [r15+rdx],r10b
 jmp java_concat_written
java_concat_write_wide:
 mov WORD PTR [r15+rdx*2],r10w
java_concat_written:
 inc QWORD PTR [rsp+40]
 inc r8d
 jmp java_concat_copy_char
java_concat_copied_row:
 inc DWORD PTR [rsp+36]
 add rdi,24
 jmp java_concat_copy_row
java_concat_make_String:
 cmp QWORD PTR [rsp+40],r14
 jne java_concat_bad
 mov rcx,QWORD PTR [rsp+64]
 mov rdx,QWORD PTR [r13+32]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz java_concat_zero
 mov QWORD PTR [rax],r15
 mov ecx,DWORD PTR [r13+44]
 mov edx,1
 sub edx,DWORD PTR [rsp+32]
 mov BYTE PTR [rax+rcx],dl
 mov ecx,DWORD PTR [r13+48]
 mov edx,DWORD PTR [rsp+48]
 mov DWORD PTR [rax+rcx],edx
 test edx,edx
 setz dl
 mov ecx,DWORD PTR [r13+52]
 mov BYTE PTR [rax+rcx],dl
 jmp java_concat_done
java_concat_oom:
 mov DWORD PTR [rbx],3
 jmp java_concat_zero
java_concat_unbound:
 mov DWORD PTR [rbx],20
 jmp java_concat_zero
java_concat_bad:
 mov DWORD PTR [rbx],7
java_concat_zero:
 xor eax,eax
java_concat_done:
 add rsp,128
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_concat ENDP

; Private leaf convention: RBX ctx, R12 argv, R13 pool, RDI Row24,
; RSI scratch WORD[24]. Returns RAX chars, ECX count, EDX coder/shift.
java_concat_piece PROC
 mov edx,DWORD PTR [rdi]
 test edx,edx
 jz java_concat_literal
 cmp edx,5
 ja java_concat_piece_bad
 mov ecx,DWORD PTR [rdi+4]
 cmp ecx,DWORD PTR [r13+12]
 jae java_concat_piece_bad
 mov rax,QWORD PTR [r12+rcx*8]
 cmp edx,5
 je java_concat_string
 cmp edx,3
 je java_concat_boolean
 cmp edx,4
 je java_concat_character
 cmp edx,1
 jne java_concat_number
 movsxd rax,eax
java_concat_number:
 xor r9d,r9d
 test rax,rax
 jns java_concat_magnitude
 neg rax
 mov r9d,1
 mov WORD PTR [rsi],45
java_concat_magnitude:
 lea r11,[rsi+r9*2]
 xor r8d,r8d
java_concat_digit:
 xor edx,edx
 mov ecx,10
 div rcx
 add dx,48
 mov WORD PTR [r11+r8*2],dx
 inc r8d
 test rax,rax
 jnz java_concat_digit
 xor eax,eax
 lea ecx,[r8-1]
java_concat_reverse:
 cmp eax,ecx
 jae java_concat_number_done
 mov r10w,WORD PTR [r11+rax*2]
 mov dx,WORD PTR [r11+rcx*2]
 mov WORD PTR [r11+rax*2],dx
 mov WORD PTR [r11+rcx*2],r10w
 inc eax
 dec ecx
 jmp java_concat_reverse
java_concat_number_done:
 lea ecx,[r8+r9]
 mov rax,rsi
 mov edx,1
 ret
java_concat_boolean:
 test eax,eax
 jz java_concat_boolean_false
 lea rax,java_concat_true
 mov ecx,4
 mov edx,1
 ret
java_concat_boolean_false:
 lea rax,java_concat_false
 mov ecx,5
 mov edx,1
 ret
java_concat_character:
 mov WORD PTR [rsi],ax
 mov rax,rsi
 mov ecx,1
 mov edx,1
 ret
java_concat_literal:
 mov rcx,QWORD PTR [rdi+16]
 cmp rcx,07FFFFFFFh
 ja java_concat_piece_bad
 mov rax,QWORD PTR [rdi+8]
 test ecx,ecx
 jz java_concat_literal_ready
 test rax,rax
 jz java_concat_piece_bad
java_concat_literal_ready:
 mov edx,1
 ret
java_concat_string:
 test rax,rax
 jz java_concat_string_null
 mov r10,QWORD PTR [r13+32]
 cmp QWORD PTR [rax-8],r10
 jne java_concat_piece_bad
 mov ecx,DWORD PTR [r13+44]
 movzx edx,BYTE PTR [rax+rcx]
 cmp edx,1
 ja java_concat_piece_bad
 mov rax,QWORD PTR [rax]
 test rax,rax
 jz java_concat_piece_bad
 cmp QWORD PTR [rax-8],264
 jne java_concat_piece_bad
 mov rcx,QWORD PTR [rax-16]
 cmp rcx,07FFFFFFFh
 ja java_concat_piece_bad
 test edx,edx
 jz java_concat_string_ready
 test cl,1
 jnz java_concat_piece_bad
 shr ecx,1
java_concat_string_ready:
 ret
java_concat_string_null:
 lea rax,java_concat_null
 mov ecx,4
 mov edx,1
 ret
java_concat_piece_bad:
 mov DWORD PTR [rbx],7
 xor eax,eax
 xor ecx,ecx
 xor edx,edx
 ret
java_concat_piece ENDP
END
