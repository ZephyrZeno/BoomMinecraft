; Normal source Method objects, immutable original classfile metadata.
; NMTH192/1: capacity8D rows12D JCLS16 heapCell24 ranges32 rows40,
; MethodLayout48 Method[]tag56 Class[]tag64 StringLayout72 MethodState80,
; originalMethodCtor88 internPool96 String.value104D coder108D byteTag112Q,
; rowBytes120D=144 rangeBytes124D=16 ctorSlots128D=12 compact132D=0/1,
; reserved136..191Q=0. Range16: first/count/status/reserved.
; Row144: owner0D slot4D mods8D nargs12D params16Q exceptions24Q,
; nex32D unavailable36D name40Q nameUnits48D returnType52D,
; signature56Q sigUnits64D sigPresent68D annotations72Q annBytes80D,
; annPresent84D paramAnnotations88Q paramBytes96D paramPresent100D,
; annotationDefault104Q defaultBytes112D defaultPresent116D,
; typeAnnotations120Q typeBytes128D typePresent132D reserved136Q.
; No represented class initialization. No host callbacks or mutable method table.
; Method ctor remains original Java. Explicit collection requires quiescence.
PUBLIC boom_normal_method_service
.code
normal_method_refs PROC PRIVATE FRAME
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
 jnz normal_method_refs_done
 mov DWORD PTR [rbx],3
normal_method_refs_done:
 add rsp,40
 ret
normal_method_refs ENDP

normal_method_types PROC PRIVATE FRAME
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
 call normal_method_refs
 mov rbp,rax
 test rax,rax
 jz normal_method_types_zero
 xor r13d,r13d
normal_method_types_loop:
 cmp r13d,r12d
 jae normal_method_types_done
 mov r8d,DWORD PTR [rsi+r13*4]
 cmp r8d,DWORD PTR [rdi+8]
 jae normal_method_types_unavailable
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 call boom_java_class_load
 test rax,rax
 jz normal_method_types_zero
 mov QWORD PTR [rbp+r13*8],rax
 inc r13d
 jmp normal_method_types_loop
normal_method_types_unavailable:
 mov DWORD PTR [rbx],20
normal_method_types_zero:
 xor ebp,ebp
normal_method_types_done:
 mov rax,rbp
 add rsp,40
 pop r13
 pop r12
 pop rbp
 pop rsi
 ret
normal_method_types ENDP

; RCX points to an original attribute (even when present-empty); EDX length.
normal_method_bytes PROC PRIVATE FRAME
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
 jz normal_method_bytes_absent
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 xor r8d,r8d
 mov r9,QWORD PTR [rdi+112]
 call boom_heap_alloc
 test rax,rax
 jz normal_method_bytes_oom
 xor r10d,r10d
normal_method_bytes_loop:
 cmp r10d,r12d
 jae normal_method_bytes_done
 mov r11b,BYTE PTR [rsi+r10]
 mov BYTE PTR [rax+r10],r11b
 inc r10d
 jmp normal_method_bytes_loop
normal_method_bytes_oom:
 mov DWORD PTR [rbx],3
normal_method_bytes_absent:
 xor eax,eax
normal_method_bytes_done:
 add rsp,32
 pop r13
 pop r12
 pop rsi
 ret
normal_method_bytes ENDP

; A VM String factory with the exact normal String compact configuration.
normal_method_string PROC PRIVATE FRAME
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
 jz normal_method_string_absent
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+72]
 mov r8,rbx
 call boom_object_new
 mov r13,rax
 test rax,rax
 jz normal_method_string_absent
 mov r14d,1
 cmp DWORD PTR [rdi+132],0
 je normal_method_string_allocate
 xor eax,eax
normal_method_string_scan:
 cmp eax,r12d
 jae normal_method_string_latin
 cmp WORD PTR [rsi+rax*2],255
 ja normal_method_string_allocate
 inc eax
 jmp normal_method_string_scan
normal_method_string_latin:
 xor r14d,r14d
normal_method_string_allocate:
 mov edx,r12d
 mov ecx,r14d
 shl edx,cl
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 xor r8d,r8d
 mov r9,QWORD PTR [rdi+112]
 call boom_heap_alloc
 test rax,rax
 jz normal_method_string_oom
 xor r10d,r10d
normal_method_string_copy:
 cmp r10d,r12d
 jae normal_method_string_publish
 movzx r11d,WORD PTR [rsi+r10*2]
 test r14d,r14d
 jnz normal_method_string_copy_utf16
 mov BYTE PTR [rax+r10],r11b
 jmp normal_method_string_copy_next
normal_method_string_copy_utf16:
 mov WORD PTR [rax+r10*2],r11w
normal_method_string_copy_next:
 inc r10d
 jmp normal_method_string_copy
normal_method_string_publish:
 mov ecx,DWORD PTR [rdi+104]
 mov QWORD PTR [r13+rcx],rax
 mov ecx,DWORD PTR [rdi+108]
 mov BYTE PTR [r13+rcx],r14b
 mov rax,r13
 jmp normal_method_string_done
normal_method_string_oom:
 mov DWORD PTR [rbx],3
normal_method_string_absent:
 xor eax,eax
normal_method_string_done:
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rsi
 ret
normal_method_string ENDP

boom_normal_method_service PROC FRAME
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
 jz normal_method_zero
 cmp DWORD PTR [rbx],0
 jne normal_method_zero
 test rsi,rsi
 jz normal_method_bad
 test rdi,rdi
 jz normal_method_bad
 test r9d,r9d
 jnz normal_method_bad
 cmp DWORD PTR [rdi],04E4D5448h
 jne normal_method_bad
 cmp DWORD PTR [rdi+4],1
 jne normal_method_bad
 mov eax,DWORD PTR [rdi+8]
 dec eax
 cmp eax,0FFFFFh
 ja normal_method_bad
 cmp DWORD PTR [rdi+12],1048576
 ja normal_method_bad
 cmp DWORD PTR [rdi+120],144
 jne normal_method_bad
 cmp DWORD PTR [rdi+124],16
 jne normal_method_bad
 cmp DWORD PTR [rdi+128],12
 jne normal_method_bad
 cmp DWORD PTR [rdi+132],1
 ja normal_method_bad
 mov ecx,136
normal_method_reserved:
 cmp QWORD PTR [rdi+rcx],0
 jne normal_method_bad
 add ecx,8
 cmp ecx,192
 jb normal_method_reserved
 cmp QWORD PTR [rdi+112],264
 jne normal_method_bad
 mov ecx,16
normal_method_pointers:
 cmp QWORD PTR [rdi+rcx],0
 je normal_method_bad
 add ecx,8
 cmp ecx,96
 jbe normal_method_pointers
 mov rax,QWORD PTR [rdi+16]
 cmp DWORD PTR [rax],04A434C53h
 jne normal_method_bad
 cmp DWORD PTR [rax+4],1
 jne normal_method_bad
 mov eax,DWORD PTR [rax+12]
 cmp eax,DWORD PTR [rdi+8]
 jne normal_method_bad
 mov r12,QWORD PTR [rsi+8]
 cmp r12,1
 ja normal_method_bad
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 mov r8,QWORD PTR [rsi]
 call boom_java_class_typeid
 cmp eax,-1
 je normal_method_zero
 mov r13,QWORD PTR [rsi]
 shl rax,4
 add rax,QWORD PTR [rdi+32]
 cmp DWORD PTR [rax+8],1
 jne normal_method_unavailable
 cmp DWORD PTR [rax+12],0
 jne normal_method_bad
 mov r14d,DWORD PTR [rax]
 mov r15d,DWORD PTR [rax+4]
 mov ecx,r14d
 add rcx,r15
 mov edx,DWORD PTR [rdi+12]
 cmp rcx,rdx
 ja normal_method_bad
 imul r14,144
 add r14,QWORD PTR [rdi+40]
 xor ecx,ecx
 xor edx,edx
normal_method_count:
 cmp edx,r15d
 jae normal_method_allocate
 imul rax,rdx,144
 test r12d,r12d
 jz normal_method_count_include
 test DWORD PTR [r14+rax+8],1
 jz normal_method_count_next
normal_method_count_include:
 cmp DWORD PTR [r14+rax+36],0
 jne normal_method_unavailable
 inc ecx
normal_method_count_next:
 inc edx
 jmp normal_method_count
normal_method_allocate:
 mov rdx,QWORD PTR [rdi+56]
 call normal_method_refs
 mov rbp,rax
 test rax,rax
 jz normal_method_zero
 mov DWORD PTR [rsp+32],0
 mov DWORD PTR [rsp+36],0
normal_method_loop:
 mov eax,DWORD PTR [rsp+32]
 cmp eax,r15d
 jae normal_method_return
 imul rax,144
 lea rsi,[r14+rax]
 test r12d,r12d
 jz normal_method_include
 test DWORD PTR [rsi+8],1
 jz normal_method_next
normal_method_include:
 ; argv: this,declaringClass,name,parameterTypes,returnType,exceptionTypes,
 ; modifiers,slot,signature,annotations,parameterAnnotations,annotationDefault.
 mov rcx,QWORD PTR [rdi+80]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz normal_method_zero
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdi+48]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz normal_method_zero
 mov QWORD PTR [rsp+64],rax
 mov QWORD PTR [rsp+72],r13
 mov rcx,QWORD PTR [rsi+40]
 mov edx,DWORD PTR [rsi+48]
 call normal_method_string
 test rax,rax
 jz normal_method_zero
 mov QWORD PTR [rsp+168],rax
 mov rcx,rbx
 lea rdx,[rsp+168]
 mov r8,QWORD PTR [rdi+96]
 call boom_java_string_intern
 test rax,rax
 jz normal_method_zero
 mov QWORD PTR [rsp+80],rax
 mov rcx,QWORD PTR [rsi+16]
 mov edx,DWORD PTR [rsi+12]
 call normal_method_types
 test rax,rax
 jz normal_method_zero
 mov QWORD PTR [rsp+88],rax
 mov r8d,DWORD PTR [rsi+52]
 cmp r8d,DWORD PTR [rdi+8]
 jae normal_method_unavailable
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+16]
 call boom_java_class_load
 test rax,rax
 jz normal_method_zero
 mov QWORD PTR [rsp+96],rax
 mov rcx,QWORD PTR [rsi+24]
 mov edx,DWORD PTR [rsi+32]
 call normal_method_types
 test rax,rax
 jz normal_method_zero
 mov QWORD PTR [rsp+104],rax
 mov eax,DWORD PTR [rsi+8]
 mov QWORD PTR [rsp+112],rax
 mov eax,DWORD PTR [rsi+4]
 mov QWORD PTR [rsp+120],rax
 mov rcx,QWORD PTR [rsi+56]
 mov edx,DWORD PTR [rsi+64]
 call normal_method_string
 cmp DWORD PTR [rbx],0
 jne normal_method_zero
 mov QWORD PTR [rsp+128],rax
 mov rcx,QWORD PTR [rsi+72]
 mov edx,DWORD PTR [rsi+80]
 call normal_method_bytes
 cmp DWORD PTR [rbx],0
 jne normal_method_zero
 mov QWORD PTR [rsp+136],rax
 mov rcx,QWORD PTR [rsi+88]
 mov edx,DWORD PTR [rsi+96]
 call normal_method_bytes
 cmp DWORD PTR [rbx],0
 jne normal_method_zero
 mov QWORD PTR [rsp+144],rax
 mov rcx,QWORD PTR [rsi+104]
 mov edx,DWORD PTR [rsi+112]
 call normal_method_bytes
 cmp DWORD PTR [rbx],0
 jne normal_method_zero
 mov QWORD PTR [rsp+152],rax
 mov rcx,rbx
 lea rdx,[rsp+64]
 call QWORD PTR [rdi+88]
 cmp DWORD PTR [rbx],0
 jne normal_method_zero
 mov ecx,DWORD PTR [rsp+36]
 mov rax,QWORD PTR [rsp+64]
 mov QWORD PTR [rbp+rcx*8],rax
 inc DWORD PTR [rsp+36]
normal_method_next:
 inc DWORD PTR [rsp+32]
 jmp normal_method_loop
normal_method_unavailable:
 mov DWORD PTR [rbx],20
 jmp normal_method_zero
normal_method_bad:
 mov DWORD PTR [rbx],7
normal_method_zero:
 xor ebp,ebp
normal_method_return:
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
boom_normal_method_service ENDP
