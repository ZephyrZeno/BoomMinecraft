; Normal ConstantPool owner mirrors and readonly original CP ROM. Guest execution is ASM.
; NCPP192/1 shares normal String factory offsets104/108/112/132 with NMTH192.
PUBLIC boom_normal_constant_pool_service
.code
ncp_string PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rsi,rcx
 mov r12d,edx
 test rsi,rsi
 jz ncp_string_absent
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+72]
 mov r8,rbx
 call boom_object_new
 mov r13,rax
 test rax,rax
 jz ncp_string_absent
 mov r14d,1
 cmp DWORD PTR [rdi+132],0
 je ncp_string_allocate
 xor eax,eax
ncp_string_scan:
 cmp eax,r12d
 jae ncp_string_latin
 cmp WORD PTR [rsi+rax*2],255
 ja ncp_string_allocate
 inc eax
 jmp ncp_string_scan
ncp_string_latin:
 xor r14d,r14d
ncp_string_allocate:
 mov edx,r12d
 mov ecx,r14d
 shl edx,cl
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 xor r8d,r8d
 mov r9,QWORD PTR [rdi+112]
 call boom_heap_alloc
 test rax,rax
 jz ncp_string_oom
 xor r10d,r10d
ncp_string_copy:
 cmp r10d,r12d
 jae ncp_string_publish
 movzx r11d,WORD PTR [rsi+r10*2]
 test r14d,r14d
 jnz ncp_string_copy_utf16
 mov BYTE PTR [rax+r10],r11b
 jmp ncp_string_copy_next
ncp_string_copy_utf16:
 mov WORD PTR [rax+r10*2],r11w
ncp_string_copy_next:
 inc r10d
 jmp ncp_string_copy
ncp_string_publish:
 mov ecx,DWORD PTR [rdi+104]
 mov QWORD PTR [r13+rcx],rax
 mov ecx,DWORD PTR [rdi+108]
 mov BYTE PTR [r13+rcx],r14b
 mov rax,r13
 jmp ncp_string_done
ncp_string_oom:
 mov DWORD PTR [rbx],3
ncp_string_absent:
 xor eax,eax
ncp_string_done:
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rsi
 ret
ncp_string ENDP

; Normal original IllegalArgumentException(String), source messages.
; ECX=0 bounds, 1 wrong tag. RBX ctx and RDI immutable pool are preserved.
ncp_raise PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
 sub rsp,64
 .allocstack 64
 .endprolog
 mov esi,ecx
 lea rcx,ncp_bounds_message
 mov edx,NCP_BOUNDS_UNITS
 test esi,esi
 jz ncp_raise_message
 lea rcx,ncp_type_message
 mov edx,NCP_TYPE_UNITS
ncp_raise_message:
 call ncp_string
 test rax,rax
 jz ncp_raise_done
 mov QWORD PTR [rsp+40],rax
 mov rcx,QWORD PTR [rdi+152]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne ncp_raise_done
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+160]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz ncp_raise_done
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rdi+168]
 cmp DWORD PTR [rbx],0
 jne ncp_raise_done
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+32]
 mov r8,QWORD PTR [rdi+184]
 mov r9,QWORD PTR [rdi+176]
 call boom_exception_set32
ncp_raise_done:
 xor eax,eax
 add rsp,64
 pop rsi
 ret
ncp_raise ENDP

; RCX raw entry pointer, EDX required width (including tag); no raw read yet.
ncp_width PROC PRIVATE
 mov r8,QWORD PTR [rdi+136]
 cmp rcx,r8
 jb ncp_width_bad
 mov eax,DWORD PTR [r14+12]
 add rax,r8
 cmp rcx,rax
 jb ncp_width_bad
 mov r9d,DWORD PTR [r14+16]
 add r9,rax
 mov r10,rcx
 add r10,rdx
 jc ncp_width_bad
 cmp r10,r9
 ja ncp_width_bad
 mov rax,QWORD PTR [rdi+144]
 add rax,r8
 cmp r10,rax
 ja ncp_width_bad
 mov eax,1
 ret
ncp_width_bad:
 mov DWORD PTR [rbx],7
 xor eax,eax
 ret
ncp_width ENDP

; ECX CP index -> RAX raw pointer, EDX spec tag, R8D resolved class type.
; Index0/wide holes return tag0 with NULL raw pointer, just like VM tags.
ncp_entry PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 test ecx,ecx
 js ncp_entry_bounds
 cmp ecx,DWORD PTR [r14+4]
 jae ncp_entry_bounds
 mov eax,DWORD PTR [r14]
 add rax,rcx
 mov edx,DWORD PTR [rdi+12]
 cmp rax,rdx
 jae ncp_entry_bad
 mov rdx,QWORD PTR [rdi+40]
 lea rdx,[rdx+rax*8]
 mov r8d,DWORD PTR [rdx+4]
 mov eax,DWORD PTR [rdx]
 cmp eax,-1
 je ncp_entry_hole
 mov ecx,DWORD PTR [r14+12]
 cmp eax,ecx
 jb ncp_entry_bad
 mov edx,DWORD PTR [r14+16]
 add rcx,rdx
 cmp rax,rcx
 jae ncp_entry_bad
 cmp rax,QWORD PTR [rdi+144]
 jae ncp_entry_bad
 add rax,QWORD PTR [rdi+136]
 movzx edx,BYTE PTR [rax]
 jmp ncp_entry_done
ncp_entry_bounds:
 xor ecx,ecx
 call ncp_raise
 xor edx,edx
 jmp ncp_entry_done
ncp_entry_hole:
 xor eax,eax
 xor edx,edx
 jmp ncp_entry_done
ncp_entry_bad:
 mov DWORD PTR [rbx],7
 xor eax,eax
 xor edx,edx
ncp_entry_done:
 add rsp,40
 ret
ncp_entry ENDP

; ECX is a UTF8 CP index. Decode original MUTF8 to bounded temporary Java
; byte[] storage, then use the normal compact String factory. No CRT/OS buffers.
ncp_utf8 PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
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
 sub rsp,40
 .allocstack 40
 .endprolog
 call ncp_entry
 cmp DWORD PTR [rbx],0
 jne ncp_utf8_zero
 cmp edx,1
 jne ncp_utf8_type
 mov rsi,rax
 mov rcx,rax
 mov edx,3
 call ncp_width
 test eax,eax
 jz ncp_utf8_zero
 movzx r12d,WORD PTR [rsi+1]
 rol r12w,8
 mov rcx,rsi
 lea edx,[r12d+3]
 call ncp_width
 test eax,eax
 jz ncp_utf8_zero
 add rsi,3
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 lea edx,[r12d*2]
 xor r8d,r8d
 mov r9d,264
 call boom_heap_alloc
 test rax,rax
 jz ncp_utf8_oom
 mov r15,rax
 xor ebp,ebp
 xor r14d,r14d
ncp_utf8_loop:
 cmp ebp,r12d
 jae ncp_utf8_string
 movzx eax,BYTE PTR [rsi+rbp]
 inc ebp
 cmp eax,128
 jb ncp_utf8_store
 mov edx,eax
 and edx,0E0h
 cmp edx,0C0h
 je ncp_utf8_two
 mov edx,eax
 and edx,0F0h
 cmp edx,0E0h
 jne ncp_utf8_bad
 lea edx,[ebp+1]
 cmp edx,r12d
 jae ncp_utf8_bad
 and eax,15
 shl eax,12
 movzx edx,BYTE PTR [rsi+rbp]
 mov r8d,edx
 and r8d,0C0h
 cmp r8d,080h
 jne ncp_utf8_bad
 and edx,63
 shl edx,6
 or eax,edx
 inc ebp
 movzx edx,BYTE PTR [rsi+rbp]
 mov r8d,edx
 and r8d,0C0h
 cmp r8d,080h
 jne ncp_utf8_bad
 and edx,63
 or eax,edx
 inc ebp
 cmp eax,0800h
 jb ncp_utf8_bad
 jmp ncp_utf8_store
ncp_utf8_two:
 cmp ebp,r12d
 jae ncp_utf8_bad
 and eax,31
 shl eax,6
 movzx edx,BYTE PTR [rsi+rbp]
 mov r8d,edx
 and r8d,0C0h
 cmp r8d,080h
 jne ncp_utf8_bad
 and edx,63
 or eax,edx
 inc ebp
 test eax,eax
 jz ncp_utf8_store
 cmp eax,080h
 jb ncp_utf8_bad
ncp_utf8_store:
 mov WORD PTR [r15+r14*2],ax
 inc r14d
 jmp ncp_utf8_loop
ncp_utf8_string:
 mov rcx,r15
 mov edx,r14d
 call ncp_string
 jmp ncp_utf8_done
ncp_utf8_type:
 mov ecx,1
 call ncp_raise
 jmp ncp_utf8_zero
ncp_utf8_bad:
 mov DWORD PTR [rbx],7
 jmp ncp_utf8_zero
ncp_utf8_oom:
 mov DWORD PTR [rbx],3
ncp_utf8_zero:
 xor eax,eax
ncp_utf8_done:
 add rsp,40
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rsi
 ret
ncp_utf8 ENDP

boom_normal_constant_pool_service PROC FRAME
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
 sub rsp,248
 .allocstack 248
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov r12d,r9d
 test rbx,rbx
 jz ncp_zero
 cmp DWORD PTR [rbx],0
 jne ncp_zero
 test rsi,rsi
 jz ncp_bad
 test rdi,rdi
 jz ncp_bad
 cmp DWORD PTR [rdi],04E435050h
 jne ncp_bad
 cmp DWORD PTR [rdi+4],1
 jne ncp_bad
 mov eax,DWORD PTR [rdi+8]
 dec eax
 cmp eax,0FFFFFh
 ja ncp_bad
 cmp DWORD PTR [rdi+12],04000000h
 ja ncp_bad
 cmp DWORD PTR [rdi+120],24
 jne ncp_bad
 cmp DWORD PTR [rdi+124],8
 jne ncp_bad
 cmp DWORD PTR [rdi+132],1
 ja ncp_bad
 cmp QWORD PTR [rdi+64],0
 jne ncp_bad
 cmp QWORD PTR [rdi+88],0
 jne ncp_bad
 cmp QWORD PTR [rdi+112],264
 jne ncp_bad
 mov rax,QWORD PTR [rdi+144]
 shr rax,31
 jnz ncp_bad
 mov ecx,16
ncp_pool_pointers_first:
 cmp QWORD PTR [rdi+rcx],0
 je ncp_bad
 add ecx,8
 cmp ecx,56
 jbe ncp_pool_pointers_first
 cmp QWORD PTR [rdi+72],0
 je ncp_bad
 cmp QWORD PTR [rdi+80],0
 je ncp_bad
 cmp QWORD PTR [rdi+96],0
 je ncp_bad
 cmp QWORD PTR [rdi+136],0
 je ncp_bad
 mov ecx,152
ncp_pool_pointers_last:
 cmp QWORD PTR [rdi+rcx],0
 je ncp_bad
 add ecx,8
 cmp ecx,184
 jbe ncp_pool_pointers_last
 mov rax,QWORD PTR [rdi+16]
 cmp DWORD PTR [rax],04A434C53h
 jne ncp_bad
 mov eax,DWORD PTR [rax+12]
 cmp eax,DWORD PTR [rdi+8]
 jne ncp_bad
 mov rax,QWORD PTR [rdi+48]
 cmp DWORD PTR [rax],04F424A43h
 jne ncp_bad
 cmp DWORD PTR [rax+4],2
 jne ncp_bad
 mov ecx,DWORD PTR [rdi+128]
 test ecx,7
 jnz ncp_bad
 mov edx,ecx
 add rdx,8
 cmp rdx,QWORD PTR [rax+8]
 ja ncp_bad
 shr ecx,3
 cmp ecx,DWORD PTR [rax+16]
 jae ncp_bad
 cmp r12d,18
 ja ncp_unsupported
 mov r13,QWORD PTR [rsi]
 test r12d,r12d
 jz ncp_class_input
 test r13,r13
 jz ncp_null
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r13
 call boom_heap_contains
 test eax,eax
 jz ncp_bad
 mov rcx,r13
 mov rdx,QWORD PTR [rdi+48]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz ncp_zero
 mov ecx,DWORD PTR [rdi+128]
 mov r13,QWORD PTR [r13+rcx]
 test r13,r13
 jz ncp_bad
ncp_class_input:
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 mov r8,r13
 call boom_java_class_typeid
 cmp eax,-1
 je ncp_zero
 cmp eax,DWORD PTR [rdi+8]
 jae ncp_bad
 imul rax,24
 add rax,QWORD PTR [rdi+32]
 mov r14,rax
 cmp DWORD PTR [r14+20],0
 jne ncp_bad
 cmp DWORD PTR [r14+8],2
 je ncp_primitive_or_array
 cmp DWORD PTR [r14+8],1
 jne ncp_unsupported
 mov eax,DWORD PTR [r14]
 mov edx,DWORD PTR [r14+4]
 test edx,edx
 jz ncp_bad
 add rax,rdx
 mov ecx,DWORD PTR [rdi+12]
 cmp rax,rcx
 ja ncp_bad
 mov eax,DWORD PTR [r14+12]
 mov edx,DWORD PTR [r14+16]
 add rax,rdx
 cmp rax,QWORD PTR [rdi+144]
 ja ncp_bad
 test r12d,r12d
 jz ncp_create
 cmp r12d,1
 je ncp_size
 cmp r12d,3
 je ncp_unsupported
 cmp r12d,5
 jb ncp_index
 cmp r12d,8
 jbe ncp_unsupported
ncp_index:
 mov ecx,DWORD PTR [rsi+16]
 mov DWORD PTR [rsp+32],ecx
 call ncp_entry
 cmp DWORD PTR [rbx],0
 jne ncp_zero
 mov r15,rax
 mov esi,edx
 mov DWORD PTR [rsp+40],r8d
 cmp r12d,18
 je ncp_tag
 cmp r12d,17
 je ncp_UTF8
 cmp r12d,2
 je ncp_class_at
 cmp r12d,16
 je ncp_string_at
 cmp r12d,12
 je ncp_int_at
 cmp r12d,13
 je ncp_long_at
 cmp r12d,14
 je ncp_float_at
 cmp r12d,15
 je ncp_double_at
 cmp r12d,4
 je ncp_class_ref
 cmp r12d,10
 je ncp_name_type_ref
 cmp r12d,9
 je ncp_member_info
 cmp r12d,11
 je ncp_name_type_info
 jmp ncp_unsupported
ncp_create:
 mov rcx,QWORD PTR [rdi+80]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz ncp_zero
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+48]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz ncp_zero
 mov ecx,DWORD PTR [rdi+128]
 mov QWORD PTR [rax+rcx],r13
 mov rbp,rax
 jmp ncp_return
ncp_primitive_or_array:
 test r12d,r12d
 jnz ncp_bad
 jmp ncp_zero
ncp_size:
 mov ebp,DWORD PTR [r14+4]
 jmp ncp_return
ncp_tag:
 mov ebp,esi
 jmp ncp_return
ncp_UTF8:
 mov ecx,DWORD PTR [rsp+32]
 call ncp_utf8
 mov rbp,rax
 jmp ncp_return
ncp_class_at:
 cmp esi,7
 jne ncp_type
 mov rcx,r15
 mov edx,3
 call ncp_width
 test eax,eax
 jz ncp_zero
 mov r8d,DWORD PTR [rsp+40]
 cmp r8d,-1
 je ncp_unsupported
 cmp r8d,DWORD PTR [rdi+8]
 jae ncp_bad
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 call boom_java_class_load
 mov rbp,rax
 jmp ncp_return
ncp_string_at:
 cmp esi,8
 jne ncp_type
 mov rcx,r15
 mov edx,3
 call ncp_width
 test eax,eax
 jz ncp_zero
 movzx ecx,WORD PTR [r15+1]
 rol cx,8
 call ncp_utf8
 test rax,rax
 jz ncp_zero
 mov QWORD PTR [rsp+48],rax
 mov rcx,rbx
 lea rdx,[rsp+48]
 mov r8,QWORD PTR [rdi+96]
 call boom_java_string_intern
 mov rbp,rax
 jmp ncp_return
ncp_int_at:
 cmp esi,3
 jne ncp_type
 jmp ncp_numeric32
ncp_float_at:
 cmp esi,4
 jne ncp_type
ncp_numeric32:
 mov rcx,r15
 mov edx,5
 call ncp_width
 test eax,eax
 jz ncp_zero
 mov eax,DWORD PTR [r15+1]
 bswap eax
 cmp r12d,12
 jne ncp_numeric32_return
 cdqe
ncp_numeric32_return:
 mov rbp,rax
 jmp ncp_return
ncp_long_at:
 cmp esi,5
 jne ncp_type
 jmp ncp_numeric64
ncp_double_at:
 cmp esi,6
 jne ncp_type
ncp_numeric64:
 mov rcx,r15
 mov edx,9
 call ncp_width
 test eax,eax
 jz ncp_zero
 mov rax,QWORD PTR [r15+1]
 bswap rax
 mov rbp,rax
 jmp ncp_return
ncp_class_ref:
 cmp esi,9
 jb ncp_type
 cmp esi,11
 ja ncp_type
 mov rcx,r15
 mov edx,5
 call ncp_width
 test eax,eax
 jz ncp_zero
 movzx ebp,WORD PTR [r15+1]
 rol bp,8
 jmp ncp_return
ncp_name_type_ref:
 cmp esi,18
 je ncp_name_type_ref_ok
 cmp esi,9
 jb ncp_type
 cmp esi,11
 ja ncp_type
ncp_name_type_ref_ok:
 mov rcx,r15
 mov edx,5
 call ncp_width
 test eax,eax
 jz ncp_zero
 movzx ebp,WORD PTR [r15+3]
 rol bp,8
 jmp ncp_return
ncp_member_info:
 cmp esi,9
 jb ncp_type
 cmp esi,11
 ja ncp_type
 mov rcx,r15
 mov edx,5
 call ncp_width
 test eax,eax
 jz ncp_zero
 movzx ecx,WORD PTR [r15+1]
 rol cx,8
 movzx eax,WORD PTR [r15+3]
 rol ax,8
 mov DWORD PTR [rsp+64],eax
 call ncp_entry
 cmp DWORD PTR [rbx],0
 jne ncp_zero
 cmp edx,7
 jne ncp_bad
 mov r15,rax
 mov rcx,rax
 mov edx,3
 call ncp_width
 test eax,eax
 jz ncp_zero
 movzx eax,WORD PTR [r15+1]
 rol ax,8
 mov DWORD PTR [rsp+72],eax
 mov ecx,DWORD PTR [rsp+64]
 call ncp_entry
 cmp DWORD PTR [rbx],0
 jne ncp_zero
 cmp edx,12
 jne ncp_bad
 mov r15,rax
 mov DWORD PTR [rsp+84],3
 jmp ncp_info_names
ncp_name_type_info:
 cmp esi,12
 jne ncp_type
 mov DWORD PTR [rsp+84],2
ncp_info_names:
 mov rcx,r15
 mov edx,5
 call ncp_width
 test eax,eax
 jz ncp_zero
 mov ecx,DWORD PTR [rsp+84]
 sub ecx,2
 movzx eax,WORD PTR [r15+1]
 rol ax,8
 mov DWORD PTR [rsp+rcx*4+72],eax
 movzx eax,WORD PTR [r15+3]
 rol ax,8
 mov DWORD PTR [rsp+rcx*4+76],eax
 mov r8d,DWORD PTR [rsp+84]
 lea edx,[r8d*8]
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov r9,QWORD PTR [rdi+56]
 call boom_heap_alloc
 test rax,rax
 jz ncp_oom
 mov rbp,rax
 mov DWORD PTR [rsp+88],0
ncp_info_loop:
 mov eax,DWORD PTR [rsp+88]
 cmp eax,DWORD PTR [rsp+84]
 jae ncp_return
 mov ecx,DWORD PTR [rsp+rax*4+72]
 call ncp_utf8
 test rax,rax
 jz ncp_zero
 mov ecx,DWORD PTR [rsp+88]
 mov QWORD PTR [rbp+rcx*8],rax
 inc DWORD PTR [rsp+88]
 jmp ncp_info_loop
ncp_type:
 mov ecx,1
 call ncp_raise
 jmp ncp_zero
ncp_null:
 mov DWORD PTR [rbx],4
 jmp ncp_zero
ncp_bad:
 mov DWORD PTR [rbx],7
 jmp ncp_zero
ncp_oom:
 mov DWORD PTR [rbx],3
 jmp ncp_zero
ncp_unsupported:
 mov DWORD PTR [rbx],20
ncp_zero:
 xor ebp,ebp
ncp_return:
 mov rax,rbp
 add rsp,248
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
boom_normal_constant_pool_service ENDP
