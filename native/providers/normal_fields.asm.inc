; Normal original Field objects. NFLD192/1, Row96, normal ctor9 argv.
; Allocation/String helper algorithms reuse the proven normal Method service.
.code
normal_field_refs PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 mov r9,rdx
 mov r8,rcx
 lea rdx,[rcx*8]
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 call boom_heap_alloc
 test rax,rax
 jnz normal_field_refs_done
 mov DWORD PTR [rbx],3
normal_field_refs_done:
 add rsp,40
 ret
normal_field_refs ENDP

normal_field_bytes PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rsi,rcx
 mov r12d,edx
 test rsi,rsi
 jz normal_field_bytes_absent
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 xor r8d,r8d
 mov r9,QWORD PTR [rdi+112]
 call boom_heap_alloc
 test rax,rax
 jz normal_field_bytes_oom
 xor r10d,r10d
normal_field_bytes_loop:
 cmp r10d,r12d
 jae normal_field_bytes_done
 mov r11b,BYTE PTR [rsi+r10]
 mov BYTE PTR [rax+r10],r11b
 inc r10d
 jmp normal_field_bytes_loop
normal_field_bytes_oom:
 mov DWORD PTR [rbx],3
normal_field_bytes_absent:
 xor eax,eax
normal_field_bytes_done:
 add rsp,32
 pop r13
 pop r12
 pop rsi
 ret
normal_field_bytes ENDP

normal_field_string PROC PRIVATE FRAME
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
 jz normal_field_string_absent
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+72]
 mov r8,rbx
 call boom_object_new
 mov r13,rax
 test rax,rax
 jz normal_field_string_absent
 mov r14d,1
 cmp DWORD PTR [rdi+132],0
 je normal_field_string_allocate
 xor eax,eax
normal_field_string_scan:
 cmp eax,r12d
 jae normal_field_string_latin
 cmp WORD PTR [rsi+rax*2],255
 ja normal_field_string_allocate
 inc eax
 jmp normal_field_string_scan
normal_field_string_latin:
 xor r14d,r14d
normal_field_string_allocate:
 mov edx,r12d
 mov ecx,r14d
 shl edx,cl
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 xor r8d,r8d
 mov r9,QWORD PTR [rdi+112]
 call boom_heap_alloc
 test rax,rax
 jz normal_field_string_oom
 xor r10d,r10d
normal_field_string_copy:
 cmp r10d,r12d
 jae normal_field_string_publish
 movzx r11d,WORD PTR [rsi+r10*2]
 test r14d,r14d
 jnz normal_field_string_copy_utf16
 mov BYTE PTR [rax+r10],r11b
 jmp normal_field_string_copy_next
normal_field_string_copy_utf16:
 mov WORD PTR [rax+r10*2],r11w
normal_field_string_copy_next:
 inc r10d
 jmp normal_field_string_copy
normal_field_string_publish:
 mov ecx,DWORD PTR [rdi+104]
 mov QWORD PTR [r13+rcx],rax
 mov ecx,DWORD PTR [rdi+108]
 mov BYTE PTR [r13+rcx],r14b
 mov rax,r13
 jmp normal_field_string_done
normal_field_string_oom:
 mov DWORD PTR [rbx],3
normal_field_string_absent:
 xor eax,eax
normal_field_string_done:
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rsi
 ret
normal_field_string ENDP

PUBLIC boom_normal_field_service
boom_normal_field_service PROC FRAME
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
 test rbx,rbx
 jz normal_field_zero
 cmp DWORD PTR [rbx],0
 jne normal_field_zero
 cmp QWORD PTR [rbx+16],0
 jne normal_field_zero
 test rsi,rsi
 jz normal_field_bad
 lea rax,boom_normal_field_pool
 cmp rdi,rax
 jne normal_field_bad
 test r9d,r9d
 jnz normal_field_bad
 cmp DWORD PTR [rdi],04E464C44h
 jne normal_field_bad
 cmp DWORD PTR [rdi+4],1
 jne normal_field_bad
 mov eax,DWORD PTR [rdi+8]
 dec eax
 cmp eax,0FFFFFh
 ja normal_field_bad
 cmp DWORD PTR [rdi+12],0FFFFFFh
 ja normal_field_bad
 cmp DWORD PTR [rdi+120],96
 jne normal_field_bad
 cmp DWORD PTR [rdi+124],16
 jne normal_field_bad
 cmp DWORD PTR [rdi+128],9
 jne normal_field_bad
 cmp DWORD PTR [rdi+132],1
 ja normal_field_bad
 cmp QWORD PTR [rdi+64],0
 jne normal_field_bad
 cmp QWORD PTR [rdi+112],264
 jne normal_field_bad
 mov ecx,136
normal_field_reserved:
 cmp QWORD PTR [rdi+rcx],0
 jne normal_field_bad
 add ecx,8
 cmp ecx,192
 jb normal_field_reserved
 mov ecx,16
normal_field_pointers:
 cmp ecx,64
 je normal_field_pointer_next
 cmp QWORD PTR [rdi+rcx],0
 je normal_field_bad
normal_field_pointer_next:
 add ecx,8
 cmp ecx,96
 jbe normal_field_pointers
 mov r10,QWORD PTR [rdi+16]
 cmp DWORD PTR [r10],04A434C53h
 jne normal_field_bad
 cmp DWORD PTR [r10+4],1
 jne normal_field_bad
 mov eax,DWORD PTR [r10+12]
 cmp eax,DWORD PTR [rdi+8]
 jb normal_field_bad
 mov r11,QWORD PTR [r10+40]
 cmp DWORD PTR [r11],052545950h
 jne normal_field_bad
 cmp DWORD PTR [r11+4],2
 jne normal_field_bad
 cmp eax,DWORD PTR [r11+12]
 jne normal_field_bad
 mov r11,QWORD PTR [rdi+24]
 cmp QWORD PTR [r10+48],r11
 jne normal_field_bad
 xor r12d,r12d
 cmp QWORD PTR [rsi+8],0
 setne r12b
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 mov r8,QWORD PTR [rsi]
 call boom_java_class_typeid
 cmp eax,-1
 je normal_field_zero
 mov DWORD PTR [rsp+40],eax
 mov r13,QWORD PTR [rsi]
 mov r10,QWORD PTR [rdi+16]
 imul rax,48
 add rax,QWORD PTR [r10+24]
 mov r11,QWORD PTR [rax]
 cmp DWORD PTR [r11],054595045h
 jne normal_field_bad
 cmp DWORD PTR [r11+4],1
 jne normal_field_bad
 mov ecx,DWORD PTR [r11+8]
 test ecx,ecx
 jz normal_field_empty
 cmp ecx,3
 je normal_field_empty
 cmp ecx,2
 ja normal_field_bad
 mov eax,DWORD PTR [rsp+40]
 cmp eax,DWORD PTR [rdi+8]
 jae normal_field_unavailable
 shl rax,4
 add rax,QWORD PTR [rdi+32]
 cmp DWORD PTR [rax+8],1
 jne normal_field_unavailable
 cmp DWORD PTR [rax+12],0
 jne normal_field_bad
 mov r14d,DWORD PTR [rax]
 mov r15d,DWORD PTR [rax+4]
 mov ecx,r14d
 add rcx,r15
 mov edx,DWORD PTR [rdi+12]
 cmp rcx,rdx
 ja normal_field_bad
 imul r14,96
 add r14,QWORD PTR [rdi+40]
 xor ecx,ecx
 xor edx,edx
normal_field_count:
 cmp edx,r15d
 jae normal_field_allocate
 imul rax,rdx,96
 mov r10d,DWORD PTR [rsp+40]
 cmp DWORD PTR [r14+rax],r10d
 jne normal_field_bad
 cmp DWORD PTR [r14+rax+4],edx
 jne normal_field_bad
 cmp QWORD PTR [r14+rax+88],0
 jne normal_field_bad
 test r12d,r12d
 jz normal_field_count_include
 test DWORD PTR [r14+rax+8],1
 jz normal_field_count_next
normal_field_count_include:
 cmp DWORD PTR [r14+rax+28],0
 jne normal_field_unavailable
 mov r10d,DWORD PTR [r14+rax+12]
 mov r11,QWORD PTR [rdi+16]
 cmp r10d,DWORD PTR [r11+12]
 jae normal_field_unavailable
 cmp DWORD PTR [r14+rax+80],1
 ja normal_field_bad
 inc ecx
normal_field_count_next:
 inc edx
 jmp normal_field_count
normal_field_empty:
 xor ecx,ecx
 xor r15d,r15d
normal_field_allocate:
 mov DWORD PTR [rsp+44],ecx
 mov rdx,QWORD PTR [rdi+56]
 call normal_field_refs
 mov rbp,rax
 test rax,rax
 jz normal_field_zero
 mov DWORD PTR [rsp+32],0
 mov DWORD PTR [rsp+36],0
 cmp DWORD PTR [rsp+44],0
 je normal_field_return
 mov rcx,QWORD PTR [rdi+80]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz normal_field_zero
normal_field_loop:
 mov eax,DWORD PTR [rsp+32]
 cmp eax,r15d
 jae normal_field_return
 imul rax,96
 lea rsi,[r14+rax]
 test r12d,r12d
 jz normal_field_include
 test DWORD PTR [rsi+8],1
 jz normal_field_next
normal_field_include:
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+48]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz normal_field_zero
 mov QWORD PTR [rsp+64],rax
 mov QWORD PTR [rsp+72],r13
 mov rcx,QWORD PTR [rsi+16]
 mov edx,DWORD PTR [rsi+24]
 call normal_field_string
 test rax,rax
 jz normal_field_zero
 mov QWORD PTR [rsp+168],rax
 mov rcx,rbx
 lea rdx,[rsp+168]
 mov r8,QWORD PTR [rdi+96]
 call boom_java_string_intern
 test rax,rax
 jz normal_field_zero
 mov QWORD PTR [rsp+80],rax
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 mov r8d,DWORD PTR [rsi+12]
 call boom_java_class_load
 test rax,rax
 jz normal_field_zero
 mov QWORD PTR [rsp+88],rax
 mov eax,DWORD PTR [rsi+8]
 mov QWORD PTR [rsp+96],rax
 mov eax,DWORD PTR [rsi+80]
 mov QWORD PTR [rsp+104],rax
 mov eax,DWORD PTR [rsi+4]
 mov QWORD PTR [rsp+112],rax
 mov rcx,QWORD PTR [rsi+32]
 mov edx,DWORD PTR [rsi+40]
 call normal_field_string
 cmp DWORD PTR [rbx],0
 jne normal_field_zero
 mov QWORD PTR [rsp+120],rax
 mov rcx,QWORD PTR [rsi+48]
 mov edx,DWORD PTR [rsi+56]
 call normal_field_bytes
 cmp DWORD PTR [rbx],0
 jne normal_field_zero
 mov QWORD PTR [rsp+128],rax
 mov rcx,rbx
 lea rdx,[rsp+64]
 call QWORD PTR [rdi+88]
 cmp DWORD PTR [rbx],0
 jne normal_field_zero
 mov ecx,DWORD PTR [rsp+36]
 mov rax,QWORD PTR [rsp+64]
 mov QWORD PTR [rbp+rcx*8],rax
 inc DWORD PTR [rsp+36]
normal_field_next:
 inc DWORD PTR [rsp+32]
 jmp normal_field_loop
normal_field_return:
 mov rax,rbp
 jmp normal_field_done
normal_field_unavailable:
 mov DWORD PTR [rbx],20
 jmp normal_field_zero
normal_field_bad:
 mov DWORD PTR [rbx],7
normal_field_zero:
 xor eax,eax
normal_field_done:
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
boom_normal_field_service ENDP
