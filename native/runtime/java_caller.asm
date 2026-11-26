; Normal Reflection.getCallerClass, Source CallerPool64/1, TracePool48/3.
; MethodRow32: id0 flags4 declaringType*8 codeBytes16 classId20 reserved24.
; Nodes are on genuine generated ASM stacks; Context snapshots are not callers.
option casemap:none
EXTERN boom_trace_head:PROC
EXTERN boom_java_class_load:PROC
PUBLIC boom_java_caller
PUBLIC boom_java_caller_type
.code
; private: current node R14, phase R15, Context RBX, TracePool R12,
; ClassPool R13 -> row/0. A different Context is an embedding boundary.
caller_node PROC
 test r14,r14
 jz caller_node_end
 cmp DWORD PTR [r14],04652414Dh
 jne caller_node_bad
 cmp DWORD PTR [r14+4],2
 jne caller_node_bad
 cmp QWORD PTR [r14+40],r12
 jne caller_node_bad
 cmp QWORD PTR [r14+32],rbx
 je caller_node_context
 test r15d,r15d
 jnz caller_node_end
 jmp caller_node_bad
caller_node_context:
 test DWORD PTR [r14+28],0FFFFFFFEh
 jnz caller_node_bad
 mov rax,QWORD PTR [r14+16]
 test rax,rax
 jz caller_node_bad
 mov r10,rax
 sub r10,QWORD PTR [r12+24]
 jc caller_node_bad
 test r10b,31
 jnz caller_node_bad
 shr r10,5
 mov r11d,DWORD PTR [r12+16]
 cmp r10,r11
 jae caller_node_bad
 test DWORD PTR [rax+4],0FFFFFF00h
 jnz caller_node_bad
 cmp QWORD PTR [rax+24],0
 jne caller_node_bad
 test DWORD PTR [rax+4],128
 jnz caller_node_unbound
 mov r10d,DWORD PTR [rax+20]
 cmp r10d,DWORD PTR [r13+12]
 jae caller_node_bad
 imul r10,48
 add r10,QWORD PTR [r13+24]
 mov r11,QWORD PTR [rax+8]
 test r11,r11
 jz caller_node_bad
 cmp QWORD PTR [r10],r11
 jne caller_node_bad
 test DWORD PTR [rax+4],32
 jnz caller_node_native
 mov r10d,DWORD PTR [rax+16]
 dec r10d
 cmp r10d,65534
 ja caller_node_bad
 inc r10d
 cmp DWORD PTR [r14+24],r10d
 jae caller_node_bad
 ret
caller_node_native:
 cmp DWORD PTR [rax+16],0
 jne caller_node_bad
 cmp DWORD PTR [r14+24],0
 jne caller_node_bad
 ret
caller_node_bad:
 mov DWORD PTR [rbx],7
 jmp caller_node_end
caller_node_unbound:
 mov DWORD PTR [rbx],20
caller_node_end:
 xor eax,eax
 ret
caller_node ENDP

; (Context32,argv,CallerPool64,op0)->source type ID / FFFFFFFF.
; Test/development type query also makes the walk independent of heap allocation.
boom_java_caller_type PROC FRAME
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
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov rsi,r8
 test rbx,rbx
 jz caller_no_type
 cmp DWORD PTR [rbx],0
 jne caller_no_type
 test r9d,r9d
 jnz caller_bad
 test rsi,rsi
 jz caller_bad
 cmp DWORD PTR [rsi],04A434352h
 jne caller_bad
 cmp DWORD PTR [rsi+4],1
 jne caller_bad
 cmp DWORD PTR [rsi+32],32
 jne caller_bad
 cmp DWORD PTR [rsi+36],32
 jne caller_bad
 cmp QWORD PTR [rsi+40],0
 jne caller_bad
 cmp QWORD PTR [rsi+48],0
 jne caller_bad
 cmp QWORD PTR [rsi+56],0
 jne caller_bad
 mov r13,QWORD PTR [rsi+8]
 test r13,r13
 jz caller_bad
 cmp DWORD PTR [r13],04A434C53h
 jne caller_bad
 cmp DWORD PTR [r13+4],1
 jne caller_bad
 cmp QWORD PTR [r13+24],0
 je caller_bad
 mov r12,QWORD PTR [rsi+16]
 test r12,r12
 jz caller_bad
 cmp DWORD PTR [r12],05452504Ch
 jne caller_bad
 cmp DWORD PTR [r12+4],3
 jne caller_bad
 mov eax,DWORD PTR [r12+16]
 dec eax
 cmp eax,0FFFFFh
 ja caller_bad
 cmp QWORD PTR [r12+24],0
 je caller_bad
 mov rcx,r12
 mov rdx,rbx
 call boom_trace_head
 cmp DWORD PTR [rbx],0
 jne caller_no_type
 mov r14,rax
 xor r15d,r15d
 call caller_node
 test rax,rax
 jz caller_no_type
 mov edx,DWORD PTR [rsi+24]
 cmp edx,DWORD PTR [rax]
 jne caller_internal
 mov edx,DWORD PTR [rsi+28]
 cmp edx,DWORD PTR [rax+20]
 jne caller_internal
 mov edx,DWORD PTR [rax+4]
 and edx,40
 cmp edx,40
 jne caller_internal
 mov r14,QWORD PTR [r14+8]
 inc r15d
 call caller_node
 test rax,rax
 jz caller_no_type
 test DWORD PTR [rax+4],8
 jz caller_internal
 mov r14,QWORD PTR [r14+8]
 inc r15d
caller_walk:
 cmp r15d,128
 jae caller_bad
 call caller_node
 test rax,rax
 jz caller_no_type
 test DWORD PTR [rax+4],64
 jz caller_found
 mov r14,QWORD PTR [r14+8]
 inc r15d
 jmp caller_walk
caller_found:
 mov eax,DWORD PTR [rax+20]
 jmp caller_type_done
caller_internal:
 mov DWORD PTR [rbx],23
 jmp caller_no_type
caller_bad:
 mov DWORD PTR [rbx],7
caller_no_type:
 mov eax,0FFFFFFFFh
caller_type_done:
 add rsp,48
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_caller_type ENDP

; source native service -> canonical normal-layout Class, never a guessed owner.
boom_java_caller PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,r8
 call boom_java_caller_type
 cmp eax,0FFFFFFFFh
 je caller_class_none
 mov r8d,eax
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+8]
 call boom_java_class_load
 jmp caller_class_done
caller_class_none:
 xor eax,eax
caller_class_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_java_caller ENDP
END
