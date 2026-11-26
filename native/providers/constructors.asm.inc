; Normal source Constructor objects. All game execution is MASM.
; NCTR160/1: cap8D rows12D ClassPool16 heapCell24 ranges32 rows40
; ctorLayout48 ctorArrayTag56 ClassArrayTag64 StringLayout72 ctorClass80
; fieldOffsets88 String.value96D coder100D byteTag104Q
; rangeBytes112D=16 rowBytes116D=80 offsets120D=8 reserved124D=0
; nonmoving128D=1 reserved132D=0 reserved136..159=0.
; Range16: first0 count4 state8 (1 usable,3 unavailable) reserved12.
; Row80: owner0 slot4 mods8 nargs12 params16 exceptions24 nex32
; unavailable36 signature40 sigUnits48 annBytes52 annotations56
; parameterAnnBytes64 reserved68 parameterAnnotations72.
; Field offsets: clazz,parameterTypes,exceptionTypes,signature,annotations,
; parameterAnnotations,slot,modifiers. All other Java fields remain zero.
; Allocations require explicit/quiescent GC; automatic stack roots are pending.
PUBLIC boom_provider_constructor_service
.code
provider_ctor_refs PROC PRIVATE FRAME
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
 jnz provider_ctor_refs_done
 mov DWORD PTR [rbx],3
provider_ctor_refs_done:
 add rsp,40
 ret
provider_ctor_refs ENDP

provider_ctor_types PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
 push rbp
 .pushreg rbp
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rsi,rcx
 mov r12d,edx
 mov ecx,edx
 mov rdx,QWORD PTR [rdi+64]
 call provider_ctor_refs
 mov rbp,rax
 test rax,rax
 jz provider_ctor_types_zero
 xor r13d,r13d
provider_ctor_types_loop:
 cmp r13d,r12d
 jae provider_ctor_types_done
 mov r8d,DWORD PTR [rsi+r13*4]
 cmp r8d,DWORD PTR [rdi+8]
 jae provider_ctor_types_unavailable
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 call boom_java_class_load
 test rax,rax
 jz provider_ctor_types_zero
 mov QWORD PTR [rbp+r13*8],rax
 inc r13d
 jmp provider_ctor_types_loop
provider_ctor_types_unavailable:
 mov DWORD PTR [rbx],20
provider_ctor_types_zero:
 xor ebp,ebp
provider_ctor_types_done:
 mov rax,rbp
 add rsp,40
 pop r13
 pop r12
 pop rbp
 pop rsi
 ret
provider_ctor_types ENDP

provider_ctor_bytes PROC PRIVATE FRAME
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
 test edx,edx
 jz provider_ctor_bytes_zero
 test rsi,rsi
 jz provider_ctor_bytes_bad
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 xor r8d,r8d
 mov r9,QWORD PTR [rdi+104]
 call boom_heap_alloc
 test rax,rax
 jz provider_ctor_bytes_oom
 xor r10d,r10d
provider_ctor_bytes_copy:
 cmp r10d,r12d
 jae provider_ctor_bytes_done
 mov r11b,BYTE PTR [rsi+r10]
 mov BYTE PTR [rax+r10],r11b
 inc r10d
 jmp provider_ctor_bytes_copy
provider_ctor_bytes_bad:
 mov DWORD PTR [rbx],7
 jmp provider_ctor_bytes_zero
provider_ctor_bytes_oom:
 mov DWORD PTR [rbx],3
provider_ctor_bytes_zero:
 xor eax,eax
provider_ctor_bytes_done:
 add rsp,32
 pop r13
 pop r12
 pop rsi
 ret
provider_ctor_bytes ENDP

provider_ctor_string PROC PRIVATE FRAME
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
 test rcx,rcx
 jz provider_ctor_string_zero
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+72]
 mov r8,rbx
 call boom_object_new
 mov r13,rax
 test rax,rax
 jz provider_ctor_string_zero
 mov rcx,rsi
 lea edx,[r12d*2]
 call provider_ctor_bytes
 test rax,rax
 jz provider_ctor_string_zero
 mov ecx,DWORD PTR [rdi+96]
 mov QWORD PTR [r13+rcx],rax
 mov ecx,DWORD PTR [rdi+100]
 mov BYTE PTR [r13+rcx],1
 mov rax,r13
 jmp provider_ctor_string_done
provider_ctor_string_zero:
 xor eax,eax
provider_ctor_string_done:
 add rsp,32
 pop r13
 pop r12
 pop rsi
 ret
provider_ctor_string ENDP

boom_provider_constructor_service PROC FRAME
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
 sub rsp,152
 .allocstack 152
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 test rbx,rbx
 jz provider_ctor_zero
 cmp DWORD PTR [rbx],0
 jne provider_ctor_zero
 test rsi,rsi
 jz provider_ctor_bad
 test rdi,rdi
 jz provider_ctor_bad
 test r9d,r9d
 jnz provider_ctor_bad
 cmp DWORD PTR [rdi],04E435452h
 jne provider_ctor_bad
 cmp DWORD PTR [rdi+4],1
 jne provider_ctor_bad
 mov eax,DWORD PTR [rdi+8]
 dec eax
 cmp eax,0FFFFFh
 ja provider_ctor_bad
 cmp DWORD PTR [rdi+12],1048576
 ja provider_ctor_bad
 cmp DWORD PTR [rdi+112],16
 jne provider_ctor_bad
 cmp DWORD PTR [rdi+116],80
 jne provider_ctor_bad
 cmp QWORD PTR [rdi+120],8
 jne provider_ctor_bad
 cmp QWORD PTR [rdi+128],1
 jne provider_ctor_bad
 cmp QWORD PTR [rdi+136],0
 jne provider_ctor_bad
 cmp QWORD PTR [rdi+144],0
 jne provider_ctor_bad
 cmp QWORD PTR [rdi+152],0
 jne provider_ctor_bad
 cmp QWORD PTR [rdi+104],264
 jne provider_ctor_bad
 mov ecx,16
provider_ctor_pointer_check:
 cmp QWORD PTR [rdi+rcx],0
 je provider_ctor_bad
 add ecx,8
 cmp ecx,88
 jbe provider_ctor_pointer_check
 mov rax,QWORD PTR [rdi+16]
 cmp DWORD PTR [rax],04A434C53h
 jne provider_ctor_bad
 cmp DWORD PTR [rax+4],1
 jne provider_ctor_bad
 mov eax,DWORD PTR [rax+12]
 cmp eax,DWORD PTR [rdi+8]
 jne provider_ctor_bad
 mov r12,QWORD PTR [rsi+8]
 cmp r12,1
 ja provider_ctor_bad
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 mov r8,QWORD PTR [rsi]
 call boom_java_class_typeid
 cmp eax,-1
 je provider_ctor_zero
 mov r13,QWORD PTR [rsi]
 shl rax,4
 add rax,QWORD PTR [rdi+32]
 cmp DWORD PTR [rax+8],1
 jne provider_ctor_unavailable
 cmp DWORD PTR [rax+12],0
 jne provider_ctor_bad
 mov r14d,DWORD PTR [rax]
 mov r15d,DWORD PTR [rax+4]
 mov ecx,r14d
 add rcx,r15
 mov edx,DWORD PTR [rdi+12]
 cmp rcx,rdx
 ja provider_ctor_bad
 imul r14,80
 add r14,QWORD PTR [rdi+40]
 xor ecx,ecx
 xor edx,edx
provider_ctor_count:
 cmp edx,r15d
 jae provider_ctor_allocate
 imul rax,rdx,80
 test r12d,r12d
 jz provider_ctor_count_include
 test DWORD PTR [r14+rax+8],1
 jz provider_ctor_count_next
provider_ctor_count_include:
 cmp DWORD PTR [r14+rax+36],0
 jne provider_ctor_unavailable
 inc ecx
provider_ctor_count_next:
 inc edx
 jmp provider_ctor_count
provider_ctor_allocate:
 mov rdx,QWORD PTR [rdi+56]
 call provider_ctor_refs
 mov rbp,rax
 test rax,rax
 jz provider_ctor_zero
 mov DWORD PTR [rsp+32],0
 mov DWORD PTR [rsp+36],0
provider_ctor_loop:
 mov eax,DWORD PTR [rsp+32]
 cmp eax,r15d
 jae provider_ctor_return
 imul rax,80
 lea rsi,[r14+rax]
 test r12d,r12d
 jz provider_ctor_include
 test DWORD PTR [rsi+8],1
 jz provider_ctor_next
provider_ctor_include:
 mov rcx,QWORD PTR [rsi+16]
 mov edx,DWORD PTR [rsi+12]
 call provider_ctor_types
 test rax,rax
 jz provider_ctor_zero
 mov QWORD PTR [rsp+48],rax
 mov rcx,QWORD PTR [rsi+24]
 mov edx,DWORD PTR [rsi+32]
 call provider_ctor_types
 test rax,rax
 jz provider_ctor_zero
 mov QWORD PTR [rsp+56],rax
 mov rcx,QWORD PTR [rdi+80]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz provider_ctor_zero
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+48]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz provider_ctor_zero
 mov QWORD PTR [rsp+40],rax
 mov rcx,QWORD PTR [rsi+40]
 mov edx,DWORD PTR [rsi+48]
 call provider_ctor_string
 cmp DWORD PTR [rbx],0
 jne provider_ctor_zero
 mov QWORD PTR [rsp+64],rax
 mov rcx,QWORD PTR [rsi+56]
 mov edx,DWORD PTR [rsi+52]
 call provider_ctor_bytes
 cmp DWORD PTR [rbx],0
 jne provider_ctor_zero
 mov QWORD PTR [rsp+72],rax
 mov rcx,QWORD PTR [rsi+72]
 mov edx,DWORD PTR [rsi+64]
 call provider_ctor_bytes
 cmp DWORD PTR [rbx],0
 jne provider_ctor_zero
 mov QWORD PTR [rsp+80],rax
 mov r10,QWORD PTR [rdi+88]
 mov r11,QWORD PTR [rsp+40]
 mov ecx,DWORD PTR [r10]
 mov QWORD PTR [r11+rcx],r13
 mov ecx,DWORD PTR [r10+4]
 mov rax,QWORD PTR [rsp+48]
 mov QWORD PTR [r11+rcx],rax
 mov ecx,DWORD PTR [r10+8]
 mov rax,QWORD PTR [rsp+56]
 mov QWORD PTR [r11+rcx],rax
 mov ecx,DWORD PTR [r10+12]
 mov rax,QWORD PTR [rsp+64]
 mov QWORD PTR [r11+rcx],rax
 mov ecx,DWORD PTR [r10+16]
 mov rax,QWORD PTR [rsp+72]
 mov QWORD PTR [r11+rcx],rax
 mov ecx,DWORD PTR [r10+20]
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [r11+rcx],rax
 mov ecx,DWORD PTR [r10+24]
 mov eax,DWORD PTR [rsi+4]
 mov DWORD PTR [r11+rcx],eax
 mov ecx,DWORD PTR [r10+28]
 mov eax,DWORD PTR [rsi+8]
 mov DWORD PTR [r11+rcx],eax
 mov ecx,DWORD PTR [rsp+36]
 mov QWORD PTR [rbp+rcx*8],r11
 inc DWORD PTR [rsp+36]
provider_ctor_next:
 inc DWORD PTR [rsp+32]
 jmp provider_ctor_loop
provider_ctor_unavailable:
 mov DWORD PTR [rbx],20
 jmp provider_ctor_zero
provider_ctor_bad:
 mov DWORD PTR [rbx],7
provider_ctor_zero:
 xor ebp,ebp
provider_ctor_return:
 mov rax,rbp
 add rsp,152
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_constructor_service ENDP
