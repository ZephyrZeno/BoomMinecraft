; Original native invoke0, noarg static Java reference-return slice.
; MIVK128/1: rows8D cap12D. All pointer offsets follow below.
; heap16 classPool24 runtime32 MethodLayout40 StringLayout48 fields56
; records64 ranges72 selectedSites80 Throwable88 Class[]type96D reserved100D
; StringFactory104 reserved112/120=0. Record48 original owner/slot/method/mods,
; UTF16name16Q units24D returnType28D index32D reserved36D/40Q=0.
; SelectedSite32: classInit0Q realJava8Q originalDiagnostic16Q reserved24Q.
; Never calls unselected compiled Code. No enum name or class special case.
.const
minvoke_wrong_arity WORD 119,114,111,110,103,32,110,117,109,98,101,114,32
 WORD 111,102,32,97,114,103,117,109,101,110,116,115
.data
ALIGN 8
PUBLIC boom_method_invoke_counters
; native calls, real target entries, original diagnostic callbacks,
; typed target exceptions wrapped, wrong-arity exceptions, unsupported calls.
boom_method_invoke_counters QWORD 6 DUP(0)
.code

; Normal String RCX versus trusted UTF16 RDX/units R8D; outer ctx/pool RBX/RDI.
minvoke_name_matches PROC PRIVATE FRAME
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
 sub rsp,48
 .allocstack 48
 .endprolog
 mov r12,rcx
 mov r13,rdx
 mov r14d,r8d
 test rcx,rcx
 jz minvoke_name_bad
 test r13,r13
 jz minvoke_name_bad
 cmp r14d,65535
 ja minvoke_name_bad
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r12
 call boom_heap_contains
 test eax,eax
 jz minvoke_name_bad
 mov rcx,r12
 mov rdx,QWORD PTR [rdi+48]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz minvoke_name_zero
 mov rax,QWORD PTR [rdi+56]
 mov edx,DWORD PTR [rax+24]
 mov rsi,QWORD PTR [r12+rdx]
 mov edx,DWORD PTR [rax+28]
 movzx ebp,BYTE PTR [r12+rdx]
 cmp ebp,1
 ja minvoke_name_bad
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz minvoke_name_bad
 cmp QWORD PTR [rsi-8],264
 jne minvoke_name_bad
 cmp DWORD PTR [rsi-20],0
 jne minvoke_name_bad
 mov eax,r14d
 mov ecx,ebp
 shl rax,cl
 cmp QWORD PTR [rsi-16],rax
 jne minvoke_name_bad
 xor r10d,r10d
minvoke_name_loop:
 cmp r10d,r14d
 jae minvoke_name_equal
 test ebp,ebp
 jnz minvoke_name_utf16
 movzx eax,BYTE PTR [rsi+r10]
 jmp minvoke_name_compare
minvoke_name_utf16:
 movzx eax,WORD PTR [rsi+r10*2]
minvoke_name_compare:
 cmp ax,WORD PTR [r13+r10*2]
 jne minvoke_name_bad
 inc r10d
 jmp minvoke_name_loop
minvoke_name_equal:
 mov eax,1
 jmp minvoke_name_done
minvoke_name_bad:
 mov DWORD PTR [rbx],7
minvoke_name_zero:
 xor eax,eax
minvoke_name_done:
 add rsp,48
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rsi
 ret
minvoke_name_matches ENDP

PUBLIC boom_provider_method_invoke_service
boom_provider_method_invoke_service PROC FRAME
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
 sub rsp,184
 .allocstack 184
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 xor r14d,r14d
 mov DWORD PTR [rsp+64],0
 test rbx,rbx
 jz minvoke_zero
 cmp DWORD PTR [rbx],0
 jne minvoke_zero
 test rsi,rsi
 jz minvoke_bad
 test rdi,rdi
 jz minvoke_bad
 cmp r9d,1
 ja minvoke_bad
 cmp DWORD PTR [rdi],04B56494Dh
 jne minvoke_bad
 cmp DWORD PTR [rdi+4],1
 jne minvoke_bad
 cmp QWORD PTR [rdi+112],0
 jne minvoke_bad
 cmp QWORD PTR [rdi+120],0
 jne minvoke_bad
 cmp DWORD PTR [rdi+100],0
 jne minvoke_bad
 mov eax,DWORD PTR [rdi+12]
 dec eax
 cmp eax,0FFFFFh
 ja minvoke_bad
 cmp QWORD PTR [rdi+16],0
 je minvoke_bad
 cmp QWORD PTR [rdi+24],0
 je minvoke_bad
 cmp QWORD PTR [rdi+32],0
 je minvoke_bad
 cmp QWORD PTR [rdi+56],0
 je minvoke_bad
 cmp QWORD PTR [rdi+64],0
 je minvoke_bad
 cmp QWORD PTR [rdi+72],0
 je minvoke_bad
 cmp QWORD PTR [rdi+80],0
 je minvoke_bad
 lock inc QWORD PTR [boom_method_invoke_counters]
 stmxcsr DWORD PTR [rsp+56]
 mov DWORD PTR [rsp+60],01F80h
 ldmxcsr DWORD PTR [rsp+60]
 mov DWORD PTR [rsp+64],1
 mov r12,QWORD PTR [rsi]
 test r12,r12
 jz minvoke_null
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r12
 call boom_heap_contains
 test eax,eax
 jz minvoke_bad
 mov rcx,r12
 mov rdx,QWORD PTR [rdi+40]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz minvoke_zero
 ; Declaring mirror and original classfile slot select the immutable row.
 mov rax,QWORD PTR [rdi+56]
 mov edx,DWORD PTR [rax]
 mov r8,QWORD PTR [r12+rdx]
 mov QWORD PTR [rsp+136],r8
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r8
 call boom_heap_contains
 test eax,eax
 jz minvoke_bad
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+24]
 mov r8,QWORD PTR [rsp+136]
 call boom_java_class_typeid
 cmp DWORD PTR [rbx],0
 jne minvoke_zero
 cmp eax,DWORD PTR [rdi+12]
 jae minvoke_bad
 mov r15d,eax
 mov rdx,QWORD PTR [rdi+56]
 mov edx,DWORD PTR [rdx+4]
 mov ebp,DWORD PTR [r12+rdx]
 cmp ebp,65535
 ja minvoke_bad
 mov rdx,QWORD PTR [rdi+72]
 lea rdx,[rdx+rax*8]
 mov ecx,DWORD PTR [rdx]
 mov edx,DWORD PTR [rdx+4]
 add rdx,rcx
 mov eax,DWORD PTR [rdi+8]
 cmp rdx,rax
 ja minvoke_bad
minvoke_find:
 cmp rcx,rdx
 jae minvoke_unsupported
 imul r13,rcx,48
 add r13,QWORD PTR [rdi+64]
 cmp DWORD PTR [r13],r15d
 jne minvoke_bad
 cmp DWORD PTR [r13+4],ebp
 je minvoke_found
 inc rcx
 jmp minvoke_find
minvoke_found:
 cmp DWORD PTR [r13+36],0
 jne minvoke_bad
 cmp QWORD PTR [r13+40],0
 jne minvoke_bad
 ; Validate the ordinary source Method fields. Do not follow/mutate root,
 ; methodAccessor, callerSensitive, annotations, or any Java cache.
 mov rax,QWORD PTR [rdi+56]
 mov edx,DWORD PTR [rax+20]
 mov edx,DWORD PTR [r12+rdx]
 cmp edx,DWORD PTR [r13+12]
 jne minvoke_bad
 mov edx,DWORD PTR [rax+8]
 mov rcx,QWORD PTR [r12+rdx]
 mov rdx,QWORD PTR [r13+16]
 mov r8d,DWORD PTR [r13+24]
 call minvoke_name_matches
 test eax,eax
 jz minvoke_zero
 mov rax,QWORD PTR [rdi+56]
 mov edx,DWORD PTR [rax+12]
 mov r8,QWORD PTR [r12+rdx]
 mov QWORD PTR [rsp+136],r8
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r8
 call boom_heap_contains
 test eax,eax
 jz minvoke_bad
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+24]
 mov r8,QWORD PTR [rsp+136]
 call boom_java_class_typeid
 cmp DWORD PTR [rbx],0
 jne minvoke_zero
 cmp eax,DWORD PTR [r13+28]
 jne minvoke_bad
 mov rax,QWORD PTR [rdi+56]
 mov edx,DWORD PTR [rax+16]
 mov r12,QWORD PTR [r12+rdx]
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r12
 call boom_heap_contains
 test eax,eax
 jz minvoke_bad
 mov rcx,r12
 mov rdx,QWORD PTR [rdi+32]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz minvoke_zero
 mov edx,DWORD PTR [rax+16]
 cmp edx,DWORD PTR [rdi+96]
 jne minvoke_bad
 cmp DWORD PTR [rax+20],2
 jne minvoke_bad
 cmp DWORD PTR [r12-20],0
 jne minvoke_bad
 ; Sites carry only this exact source selection's capabilities. A compiled
 ; but unselected Java method remains an actual source diagnostic callback.
 mov eax,DWORD PTR [r13+32]
 cmp eax,DWORD PTR [rdi+8]
 jae minvoke_bad
 shl rax,5
 add rax,QWORD PTR [rdi+80]
 mov QWORD PTR [rsp+48],rax
 cmp QWORD PTR [rax+24],0
 jne minvoke_bad
 mov rcx,QWORD PTR [rax]
 test rcx,rcx
 jz minvoke_no_init
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne minvoke_zero
minvoke_no_init:
 mov rax,QWORD PTR [rsp+48]
 mov r12,QWORD PTR [rax+8]
 test r12,r12
 jz minvoke_pending
 cmp QWORD PTR [rax],0
 je minvoke_bad
 cmp QWORD PTR [rax+16],0
 jne minvoke_bad
 ; The C path initializes the declaring class before argument count checks.
 ; Static receiver argv[1] is deliberately never dereferenced.
 mov r15,QWORD PTR [rsi+16]
 test r15,r15
 jz minvoke_call
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r15
 call boom_heap_contains
 test eax,eax
 jz minvoke_bad
 mov rcx,r15
 mov rdx,QWORD PTR [rdi+32]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz minvoke_zero
 cmp DWORD PTR [rax+20],2
 jne minvoke_bad
 cmp DWORD PTR [r15-20],0
 jne minvoke_arity
minvoke_call:
 lock inc QWORD PTR [boom_method_invoke_counters+8]
 mov QWORD PTR [rsp+176],0
 mov rcx,rbx
 lea rdx,[rsp+176]
 call r12
 cmp DWORD PTR [rbx],0
 je minvoke_return
 cmp DWORD PTR [rbx],16
 jne minvoke_zero
 mov r14,QWORD PTR [rbx+16]
 test r14,r14
 jz minvoke_bad
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz minvoke_bad
 ; Only a materialized target-body Throwable is consumed and wrapped.
 ; Class initialization and capability diagnostics never enter this branch.
 mov rcx,rbx
 call boom_exception_take32
 cmp rax,r14
 jne minvoke_bad
 lea rcx,MINV_ITE_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne minvoke_zero
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 lea rdx,MINV_ITE_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz minvoke_zero
 mov QWORD PTR [rsp+128],rax
 mov QWORD PTR [rsp+96],rax
 mov QWORD PTR [rsp+104],r14
 mov rcx,rbx
 lea rdx,[rsp+96]
 call MINV_ITE_CTOR
 cmp DWORD PTR [rbx],0
 jne minvoke_zero
 lock inc QWORD PTR [boom_method_invoke_counters+24]
 jmp minvoke_set_exception
minvoke_return:
 mov r14,rax
 test r14,r14
 jz minvoke_zero
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz minvoke_bad
 mov rax,r14
 jmp minvoke_done
minvoke_pending:
 mov rax,QWORD PTR [rax+16]
 test rax,rax
 jz minvoke_unsupported
 lock inc QWORD PTR [boom_method_invoke_counters+16]
 mov rcx,rbx
 mov rdx,rsi
 call rax
 cmp DWORD PTR [rbx],0
 je minvoke_bad
 jmp minvoke_zero
minvoke_arity:
 lock inc QWORD PTR [boom_method_invoke_counters+32]
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+104]
 lea r8,minvoke_wrong_arity
 mov r9d,25
 call boom_java_property_copy
 test rax,rax
 jz minvoke_zero
 mov r14,rax
 lea rcx,MINV_IAE_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne minvoke_zero
 mov rcx,QWORD PTR [rdi+16]
 mov rcx,QWORD PTR [rcx]
 lea rdx,MINV_IAE_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz minvoke_zero
 mov QWORD PTR [rsp+128],rax
 mov QWORD PTR [rsp+96],rax
 mov QWORD PTR [rsp+104],r14
 mov rcx,rbx
 lea rdx,[rsp+96]
 call MINV_IAE_CTOR
 cmp DWORD PTR [rbx],0
 jne minvoke_zero
minvoke_set_exception:
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+128]
 mov r8,QWORD PTR [rdi+32]
 mov r9,QWORD PTR [rdi+88]
 call boom_exception_set32
 jmp minvoke_zero
minvoke_null:
 mov DWORD PTR [rbx],4
 jmp minvoke_zero
minvoke_unsupported:
 mov DWORD PTR [rbx],20
 lock inc QWORD PTR [boom_method_invoke_counters+40]
 jmp minvoke_zero
minvoke_bad:
 mov DWORD PTR [rbx],7
minvoke_zero:
 xor eax,eax
minvoke_done:
 cmp DWORD PTR [rsp+64],0
 je minvoke_restore
 ldmxcsr DWORD PTR [rsp+56]
minvoke_restore:
 add rsp,184
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_provider_method_invoke_service ENDP
