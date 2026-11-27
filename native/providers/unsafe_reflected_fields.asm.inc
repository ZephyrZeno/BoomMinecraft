; Normal original Unsafe(Field) protocol. Existing UFMP validation algorithms.
.const
urf_widths BYTE 1,1,2,2,4,8,4,8,8
.code
urf_pool_valid PROC PRIVATE
 xor eax,eax
 test r13,r13
 jz urf_pool_done
 cmp DWORD PTR [r13],055464D50h
 jne urf_pool_done
 mov ecx,DWORD PTR [r13+4]
 dec ecx
 cmp ecx,1
 ja urf_pool_done
 mov ecx,DWORD PTR [r13+8]
 dec ecx
 cmp ecx,0FFFFFh
 ja urf_pool_done
 mov ecx,DWORD PTR [r13+12]
 dec ecx
 cmp ecx,0FFFFFEh
 ja urf_pool_done
 shr ecx,10
 inc ecx
 cmp ecx,DWORD PTR [r13+92]
 jne urf_pool_done
 mov ecx,DWORD PTR [r13+88]
 dec ecx
 cmp ecx,0FFFFFFh
 ja urf_pool_done
 cmp DWORD PTR [r13+108],64
 jne urf_pool_done
 mov r10,055464C4400000000h
 cmp DWORD PTR [r13+4],1
 je urf_pool_tag_ready
 mov r10,055464C3200000000h
urf_pool_tag_ready:
 cmp QWORD PTR [r13+112],r10
 jne urf_pool_done
 cmp QWORD PTR [r13+120],0
 jne urf_pool_done
 mov ecx,16
urf_pool_pointers:
 cmp QWORD PTR [r13+rcx],0
 je urf_pool_done
 add ecx,8
 cmp ecx,88
 jb urf_pool_pointers
 mov r10,QWORD PTR [r13+24]
 cmp DWORD PTR [r10],04A434C53h
 jne urf_pool_done
 cmp DWORD PTR [r10+4],1
 jne urf_pool_done
 mov ecx,DWORD PTR [r13+8]
 cmp ecx,DWORD PTR [r10+12]
 jne urf_pool_done
 mov r10,QWORD PTR [r13+32]
 cmp DWORD PTR [r10],052545950h
 jne urf_pool_done
 cmp DWORD PTR [r10+4],2
 jne urf_pool_done
 cmp ecx,DWORD PTR [r10+12]
 jne urf_pool_done
 cmp DWORD PTR [r13+104],ecx
 jae urf_pool_done
 mov r10,QWORD PTR [r13+48]
 cmp DWORD PTR [r10],04A554E53h
 jne urf_pool_done
 cmp DWORD PTR [r10+4],1
 jne urf_pool_done
 mov r11,QWORD PTR [r13+16]
 cmp r11,QWORD PTR [r10+32]
 jne urf_pool_done
 mov r11,QWORD PTR [r13+40]
 cmp r11,QWORD PTR [r10+40]
 jne urf_pool_done
 mov r10,QWORD PTR [r13+56]
 cmp DWORD PTR [r10],04F424A43h
 jne urf_pool_done
 cmp DWORD PTR [r10+4],2
 jne urf_pool_done
 mov ecx,DWORD PTR [r13+96]
 test cl,7
 jnz urf_pool_done
 add rcx,8
 mov r11d,DWORD PTR [r10+16]
 shl r11,3
 cmp rcx,r11
 ja urf_pool_done
 mov ecx,DWORD PTR [r13+100]
 cmp rcx,QWORD PTR [r10+8]
 jae urf_pool_done
 cmp rcx,r11
 jb urf_pool_done
 mov eax,1
urf_pool_done:
 ret
urf_pool_valid ENDP

urf_record PROC PRIVATE
 mov r9d,ecx
 cmp ecx,DWORD PTR [r13+12]
 jae urf_record_bad
 mov eax,ecx
 shr eax,10
 mov r10,QWORD PTR [r13+80]
 mov r10,QWORD PTR [r10+rax*8]
 test r10,r10
 jz urf_record_bad
 and ecx,1023
 shl ecx,6
 add r10,rcx
 cmp DWORD PTR [r10+48],r9d
 jne urf_record_bad
 cmp QWORD PTR [r10+40],0
 jne urf_record_bad
 cmp DWORD PTR [r10+52],0
 jne urf_record_bad
 cmp QWORD PTR [r10+56],0
 jne urf_record_bad
 mov eax,DWORD PTR [r10]
 cmp eax,DWORD PTR [r13+8]
 jae urf_record_bad
 mov r11,QWORD PTR [r13+72]
 lea r11,[r11+rax*8]
 mov eax,DWORD PTR [r11]
 add eax,DWORD PTR [r10+4]
 jc urf_record_bad
 cmp eax,r9d
 jne urf_record_bad
 mov eax,DWORD PTR [r10+4]
 cmp eax,DWORD PTR [r11+4]
 jae urf_record_bad
 cmp DWORD PTR [r10+8],0FFFFh
 ja urf_record_bad
 mov eax,DWORD PTR [r10+12]
 dec eax
 cmp eax,8
 ja urf_record_bad
 lea r11,urf_widths
 movzx ecx,BYTE PTR [r11+rax]
 cmp ecx,DWORD PTR [r10+24]
 jne urf_record_bad
 xor ecx,ecx
 cmp eax,8
 sete cl
 mov edx,DWORD PTR [r10+8]
 and edx,8
 shr edx,2
 or ecx,edx
 cmp ecx,DWORD PTR [r10+28]
 jne urf_record_bad
 mov ecx,DWORD PTR [r10+20]
 dec ecx
 cmp ecx,65534
 ja urf_record_bad
 inc ecx
 mov eax,DWORD PTR [r10+16]
 add rax,rcx
 mov ecx,DWORD PTR [r13+88]
 cmp rax,rcx
 ja urf_record_bad
 mov rax,r10
 ret
urf_record_bad:
 xor eax,eax
 ret
urf_record ENDP

; UFRO128/1. Exact normal Field -> original UFMP identity, no physical offsets.
; Existing Context32 and original declaring Class initialization are preserved.
PUBLIC boom_unsafe_reflected_field_service
boom_unsafe_reflected_field_service PROC FRAME
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
 sub rsp,96
 .allocstack 96
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov rdi,r8
 mov DWORD PTR [rsp+32],r9d
 test rbx,rbx
 jz urf_zero
 cmp DWORD PTR [rbx],0
 jne urf_zero
 cmp QWORD PTR [rbx+16],0
 jne urf_zero
 lea rax,boom_unsafe_reflected_field_pool
 cmp rdi,rax
 jne urf_bad
 cmp DWORD PTR [rdi],05546524Fh
 jne urf_bad
 cmp DWORD PTR [rdi+4],1
 jne urf_bad
 cmp DWORD PTR [rdi+8],128
 jne urf_bad
 cmp DWORD PTR [rdi+12],7
 jne urf_bad
 cmp DWORD PTR [rsp+32],2
 ja urf_bad
 mov ecx,80
urf_reserved:
 cmp QWORD PTR [rdi+rcx],0
 jne urf_bad
 add ecx,8
 cmp ecx,128
 jb urf_reserved
 mov ecx,16
urf_pointers:
 cmp QWORD PTR [rdi+rcx],0
 je urf_bad
 add ecx,8
 cmp ecx,64
 jb urf_pointers
 mov r13,QWORD PTR [rdi+16]
 call urf_pool_valid
 test eax,eax
 jz urf_bad
 mov r10,QWORD PTR [rdi+24]
 cmp DWORD PTR [r10],04F424A43h
 jne urf_bad
 cmp DWORD PTR [r10+4],2
 jne urf_bad
 mov eax,DWORD PTR [rdi+64]
 test al,7
 jnz urf_bad
 add rax,8
 mov r11d,DWORD PTR [r10+16]
 shl r11,3
 cmp rax,r11
 ja urf_bad
 mov eax,DWORD PTR [rdi+68]
 cmp eax,r11d
 jb urf_bad
 add rax,4
 cmp rax,QWORD PTR [r10+8]
 ja urf_bad
 mov eax,DWORD PTR [rdi+72]
 cmp eax,r11d
 jb urf_bad
 add rax,4
 cmp rax,QWORD PTR [r10+8]
 ja urf_bad
 mov ecx,DWORD PTR [rdi+76]
 cmp ecx,DWORD PTR [r13+8]
 jae urf_bad
 mov r10,QWORD PTR [r13+48]
 cmp DWORD PTR [r10+8],2
 jne urf_unbound
 test r12,r12
 jz urf_bad
 mov rsi,QWORD PTR [r12]
 test rsi,rsi
 jz urf_null
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz urf_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+40]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz urf_zero
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+32]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz urf_zero
 mov ecx,DWORD PTR [r13+104]
 cmp ecx,DWORD PTR [rax+16]
 jne urf_bad
 mov r14,QWORD PTR [r12+8]
 test r14,r14
 jz urf_null
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz urf_bad
 mov rcx,r14
 mov rdx,QWORD PTR [rdi+24]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz urf_zero
 mov rcx,r14
 mov rdx,QWORD PTR [r13+32]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz urf_zero
 mov ecx,DWORD PTR [rdi+76]
 cmp ecx,DWORD PTR [rax+16]
 jne urf_bad
 mov ecx,DWORD PTR [rdi+64]
 mov r15,QWORD PTR [r14+rcx]
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+24]
 mov r8,r15
 call boom_java_class_typeid
 cmp eax,-1
 je urf_zero
 cmp eax,DWORD PTR [r13+8]
 jae urf_bad
 mov DWORD PTR [rsp+36],eax
 mov ecx,DWORD PTR [rdi+68]
 mov r10d,DWORD PTR [r14+rcx]
 mov r11,QWORD PTR [r13+72]
 cmp r10d,DWORD PTR [r11+rax*8+4]
 jae urf_bad
 mov ecx,DWORD PTR [r11+rax*8]
 add ecx,r10d
 jc urf_bad
 mov DWORD PTR [rsp+40],ecx
 call urf_record
 test rax,rax
 jz urf_bad
 mov ecx,DWORD PTR [rsp+36]
 cmp ecx,DWORD PTR [rax]
 jne urf_bad
 mov ecx,DWORD PTR [rdi+68]
 mov ecx,DWORD PTR [r14+rcx]
 cmp ecx,DWORD PTR [rax+4]
 jne urf_bad
 mov ecx,DWORD PTR [rdi+72]
 mov ecx,DWORD PTR [r14+rcx]
 mov edx,DWORD PTR [rax+8]
 and edx,050DFh
 cmp ecx,edx
 jne urf_bad
 and ecx,8
 mov eax,DWORD PTR [rsp+32]
 test eax,eax
 jz urf_expect_instance
 test ecx,ecx
 jz urf_wrong_domain
 cmp eax,2
 je urf_base
 jmp urf_cookie
urf_expect_instance:
 test ecx,ecx
 jnz urf_wrong_domain
urf_cookie:
 mov eax,DWORD PTR [rsp+40]
 inc eax
 cmp DWORD PTR [r13+4],1
 je urf_cookie_tag
 shl eax,8
 or eax,80h
urf_cookie_tag:
 or rax,QWORD PTR [r13+112]
 jmp urf_done
urf_base:
 mov rax,r15
 jmp urf_done
urf_wrong_domain:
 mov rax,QWORD PTR [rbx+4]
 mov QWORD PTR [rsp+72],rax
 mov eax,DWORD PTR [rbx+12]
 mov DWORD PTR [rsp+80],eax
 mov rcx,QWORD PTR [rdi+32]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz urf_zero
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+40]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz urf_zero
 mov QWORD PTR [rsp+64],rax
 mov rcx,rbx
 lea rdx,[rsp+64]
 call QWORD PTR [rdi+48]
 cmp DWORD PTR [rbx],0
 jne urf_zero
 mov rax,QWORD PTR [rsp+72]
 mov QWORD PTR [rbx+4],rax
 mov eax,DWORD PTR [rsp+80]
 mov DWORD PTR [rbx+12],eax
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+64]
 mov r8,QWORD PTR [r13+32]
 mov r9,QWORD PTR [rdi+56]
 call boom_exception_set32
 jmp urf_zero
urf_unbound:
 mov DWORD PTR [rbx],20
 jmp urf_zero
urf_null:
 mov DWORD PTR [rbx],4
 jmp urf_zero
urf_bad:
 mov DWORD PTR [rbx],7
urf_zero:
 xor eax,eax
urf_done:
 add rsp,96
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_unsafe_reflected_field_service ENDP
