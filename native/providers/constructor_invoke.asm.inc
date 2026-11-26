; Normal source Constructor clazz/slot selector, NIVK96/1.
; Pool: cap8D count12D enum16Q classes24Q heapCell32Q map40Q records48Q
; selectedSites56Q boxes64Q callPool72Q reserved80/88Q=0.
; Record32 owner0D slot4D method8D modifiers12D nargs16D available20D res24Q.
; selected site row16 actualSite0Q pendingDiagnosticCallback8Q.
EXTERN boom_heap_contains:PROC
EXTERN boom_object_check:PROC
EXTERN boom_java_class_typeid:PROC
EXTERN boom_constructor_callsite:PROC
PUBLIC boom_provider_constructor_invoke_service
.code
boom_provider_constructor_invoke_service PROC FRAME
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
 mov rsi,rdx
 mov rdi,r8
 test rbx,rbx
 jz ci_zero
 cmp DWORD PTR [rbx],0
 jne ci_zero
 test r9d,r9d
 jnz ci_bad
 test rsi,rsi
 jz ci_bad
 test rdi,rdi
 jz ci_bad
 cmp DWORD PTR [rdi],04B56494Eh
 jne ci_bad
 cmp DWORD PTR [rdi+4],1
 jne ci_bad
 cmp QWORD PTR [rdi+80],0
 jne ci_bad
 cmp QWORD PTR [rdi+88],0
 jne ci_bad
 cmp QWORD PTR [rdi+48],0
 je ci_bad
 cmp QWORD PTR [rdi+56],0
 je ci_bad
 cmp QWORD PTR [rdi+72],0
 je ci_bad
 mov r12,QWORD PTR [rdi+16]
 test r12,r12
 jz ci_bad
 cmp DWORD PTR [r12],04E435452h
 jne ci_bad
 cmp DWORD PTR [r12+4],1
 jne ci_bad
 mov eax,DWORD PTR [rdi+8]
 test eax,eax
 jz ci_bad
 cmp eax,0100000h
 ja ci_bad
 cmp eax,DWORD PTR [r12+8]
 jne ci_bad
 mov eax,DWORD PTR [rdi+12]
 cmp eax,DWORD PTR [r12+12]
 jne ci_bad
 mov rdx,QWORD PTR [rdi+24]
 cmp rdx,QWORD PTR [r12+16]
 jne ci_bad
 test rdx,rdx
 jz ci_bad
 mov eax,DWORD PTR [rdi+8]
 cmp eax,DWORD PTR [rdx+12]
 jne ci_bad
 mov rax,QWORD PTR [rdi+32]
 cmp rax,QWORD PTR [r12+24]
 jne ci_bad
 test rax,rax
 jz ci_bad
 mov r13,QWORD PTR [rsi]
 test r13,r13
 jz ci_null
 mov rcx,QWORD PTR [rax]
 test rcx,rcx
 jz ci_unlinked
 mov rdx,r13
 call boom_heap_contains
 test eax,eax
 jz ci_bad
 mov rcx,r13
 mov rdx,QWORD PTR [r12+48]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz ci_zero
 mov r14,QWORD PTR [r12+88]
 test r14,r14
 jz ci_bad
 mov eax,DWORD PTR [r14]
 lea rdx,[rax+8]
 cmp rdx,QWORD PTR [r13-16]
 ja ci_bad
 mov r8,QWORD PTR [r13+rax]
 mov rcx,rbx
 mov rdx,QWORD PTR [rdi+24]
 call boom_java_class_typeid
 cmp eax,-1
 je ci_zero
 cmp eax,DWORD PTR [rdi+8]
 jae ci_bad
 mov r15d,eax
 shl rax,4
 add rax,QWORD PTR [r12+32]
 cmp DWORD PTR [rax+8],1
 jne ci_unlinked
 cmp DWORD PTR [rax+12],0
 jne ci_bad
 mov ecx,DWORD PTR [rax]
 mov edx,DWORD PTR [rax+4]
 add rdx,rcx
 mov r8d,DWORD PTR [rdi+12]
 cmp rdx,r8
 ja ci_bad
 mov eax,DWORD PTR [r14+24]
 lea r8,[rax+4]
 cmp r8,QWORD PTR [r13-16]
 ja ci_bad
 mov r14d,DWORD PTR [r13+rax]
ci_find:
 cmp rcx,rdx
 jae ci_bad
 mov rax,rcx
 shl rax,5
 add rax,QWORD PTR [rdi+48]
 cmp DWORD PTR [rax],r15d
 jne ci_bad
 cmp DWORD PTR [rax+4],r14d
 je ci_found
 inc rcx
 jmp ci_find
ci_found:
 cmp DWORD PTR [rax+20],1
 jne ci_unlinked
 cmp QWORD PTR [rax+24],0
 jne ci_bad
 shl rcx,4
 add rcx,QWORD PTR [rdi+56]
 mov r8,QWORD PTR [rcx]
 test r8,r8
 jz ci_pending
 cmp QWORD PTR [rcx+8],0
 jne ci_bad
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+8]
 mov r9,QWORD PTR [rdi+72]
 call boom_constructor_callsite
 ; Preserve pending diagnostic and Context errors. Normal Throwable wrapping
 ; remains a separately tracked, unimplemented normal-runtime compatibility gap.
 jmp ci_done
ci_pending:
 mov rax,QWORD PTR [rcx+8]
 test rax,rax
 jz ci_unlinked
 mov rcx,rbx
 mov rdx,rsi
 call rax
 cmp DWORD PTR [rbx],0
 je ci_bad
 jmp ci_zero
ci_null:
 mov DWORD PTR [rbx],4
 jmp ci_zero
ci_unlinked:
 mov DWORD PTR [rbx],20
 jmp ci_zero
ci_bad:
 mov DWORD PTR [rbx],7
ci_zero:
 xor eax,eax
ci_done:
 add rsp,48
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_constructor_invoke_service ENDP
