; Source String/String[] callbacks for platform/VM property pools, ABI2.
; Pool112 shares heapCell16, StringPool80*24, source String[] type32.
; callbacks80 array(ctx,pool,count),88 copy(ctx,pool,UTF16*,length),
;          96 literal(ctx,pool,index),104 same-image ASM String factory.
; All allocation/copy/OS query execution is MASM. Explicit quiescent GC only.
option casemap:none
EXTERN boom_heap_alloc:PROC
PUBLIC boom_java_property_array
PUBLIC boom_java_property_copy
PUBLIC boom_java_property_literal
.code
boom_java_property_array PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz jpa_zero
 cmp DWORD PTR [rbx],0
 jne jpa_zero
 test rdx,rdx
 jz jpa_bad
 cmp DWORD PTR [rdx+4],2
 jne jpa_bad
 test r8d,r8d
 js jpa_negative
 cmp r8d,0100000h
 ja jpa_bad
 mov r9,QWORD PTR [rdx+32]
 test r9,r9
 jz jpa_bad
 cmp DWORD PTR [r9],054595045h
 jne jpa_bad
 cmp DWORD PTR [r9+4],1
 jne jpa_bad
 cmp DWORD PTR [r9+8],3
 jne jpa_bad
 cmp QWORD PTR [r9+16],0
 je jpa_bad
 mov rcx,QWORD PTR [rdx+16]
 test rcx,rcx
 jz jpa_bad
 mov rcx,QWORD PTR [rcx]
 test rcx,rcx
 jz jpa_unbound
 mov edx,r8d
 shl rdx,3
 call boom_heap_alloc
 test rax,rax
 jnz jpa_done
 mov DWORD PTR [rbx],3
 jmp jpa_zero
jpa_negative:
 mov DWORD PTR [rbx],2
 jmp jpa_zero
jpa_unbound:
 mov DWORD PTR [rbx],20
 jmp jpa_zero
jpa_bad:
 mov DWORD PTR [rbx],7
jpa_zero:
 xor eax,eax
jpa_done:
 add rsp,32
 pop rbx
 ret
boom_java_property_array ENDP

boom_java_property_literal PROC
 test rcx,rcx
 jz jpl_zero
 cmp DWORD PTR [rcx],0
 jne jpl_zero
 test rdx,rdx
 jz jpl_bad
 cmp DWORD PTR [rdx+4],2
 jne jpl_bad
 mov r9,QWORD PTR [rdx+104]
 test r9,r9
 jz jpl_bad
 mov r10,QWORD PTR [rdx+24]
 test r10,r10
 jz jpl_bad
 cmp DWORD PTR [r10],04A534C50h
 jne jpl_bad
 cmp DWORD PTR [r10+4],1
 jne jpl_bad
 mov rax,QWORD PTR [rdx+16]
 test rax,rax
 jz jpl_bad
 mov r11,QWORD PTR [rax]
 test r11,r11
 jz jpl_unbound
 xor eax,eax
 lock cmpxchg QWORD PTR [r10+64],r11
 je jpl_bound
 cmp rax,r11
 jne jpl_bad
jpl_bound:
 mov rdx,r10
 jmp r9
jpl_unbound:
 mov DWORD PTR [rcx],20
 jmp jpl_zero
jpl_bad:
 test rcx,rcx
 jz jpl_zero
 cmp DWORD PTR [rcx],0
 jne jpl_zero
 mov DWORD PTR [rcx],7
jpl_zero:
 xor eax,eax
 ret
boom_java_property_literal ENDP

boom_java_property_copy PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,200
 .allocstack 200
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov r12d,r9d
 test rbx,rbx
 jz jpc_zero
 cmp DWORD PTR [rbx],0
 jne jpc_zero
 test rsi,rsi
 jz jpc_bad
 cmp DWORD PTR [rsi+4],2
 jne jpc_bad
 cmp r12d,65535
 ja jpc_bad
 test r12d,r12d
 jz jpc_metadata
 test rdi,rdi
 jz jpc_bad
jpc_metadata:
 cmp QWORD PTR [rsi+104],0
 je jpc_bad
 mov r10,QWORD PTR [rsi+24]
 test r10,r10
 jz jpc_bad
 cmp DWORD PTR [r10],04A534C50h
 jne jpc_bad
 cmp DWORD PTR [r10+4],1
 jne jpc_bad
 mov DWORD PTR [rsp+32],04A534C50h
 mov DWORD PTR [rsp+36],1
 mov DWORD PTR [rsp+40],1
 mov DWORD PTR [rsp+44],1
 lea rax,[rsp+112]
 mov QWORD PTR [rsp+48],rax
 lea rax,[rsp+128]
 mov QWORD PTR [rsp+56],rax
 lea rax,[rsp+144]
 mov QWORD PTR [rsp+64],rax
 mov rax,QWORD PTR [r10+40]
 mov QWORD PTR [rsp+72],rax
 mov rax,QWORD PTR [r10+48]
 mov QWORD PTR [rsp+80],rax
 mov rax,QWORD PTR [r10+56]
 mov QWORD PTR [rsp+88],rax
 mov rax,QWORD PTR [rsi+16]
 test rax,rax
 jz jpc_bad
 mov rax,QWORD PTR [rax]
 test rax,rax
 jz jpc_unbound
 mov QWORD PTR [rsp+96],rax
 mov QWORD PTR [rsp+104],0
 mov QWORD PTR [rsp+112],rdi
 mov DWORD PTR [rsp+120],r12d
 xor eax,eax
 xor edx,edx
jpc_hash:
 cmp edx,r12d
 jae jpc_ready
 imul eax,eax,31
 movzx ecx,WORD PTR [rdi+rdx*2]
 add eax,ecx
 inc edx
 jmp jpc_hash
jpc_ready:
 mov DWORD PTR [rsp+124],eax
 mov QWORD PTR [rsp+128],0
 mov QWORD PTR [rsp+136],0
 mov DWORD PTR [rsp+144],0
 mov rcx,rbx
 lea rdx,[rsp+32]
 xor r8d,r8d
 call QWORD PTR [rsi+104]
 jmp jpc_done
jpc_unbound:
 mov DWORD PTR [rbx],20
 jmp jpc_zero
jpc_bad:
 mov DWORD PTR [rbx],7
jpc_zero:
 xor eax,eax
jpc_done:
 add rsp,200
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_property_copy ENDP
END
