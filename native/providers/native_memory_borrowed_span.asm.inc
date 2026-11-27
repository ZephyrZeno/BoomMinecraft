; Span64/1, Win64 native helper, no Java Context, oop, ID or payload access.
; Caller owns stable Span64 storage; do not share/mutate one Span concurrently.
; Owner128/Job128 remain the separately frozen original core ABI.
EXTERN boom_native_memory_service:PROC
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC

SPAN_OWNER_MAGIC EQU 03130574D4E4F4F42h

SPAN_CLEAR_JOB MACRO
 LOCAL clear_next
 lea r10,[rsp+32]
 xor eax,eax
 mov ecx,16
clear_next:
 mov QWORD PTR [r10],rax
 add r10,8
 dec ecx
 jnz clear_next
ENDM

.code
PUBLIC boom_native_memory_span_acquire
boom_native_memory_span_acquire PROC FRAME
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
 sub rsp,184
 .allocstack 184
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz span_a_bad_pointer
 test bl,7
 jnz span_a_bad_pointer
 mov edi,2
 cmp QWORD PTR [rbx+32],0
 jne span_a_busy_return
 xor eax,eax
 mov QWORD PTR [rbx+24],rax
 mov QWORD PTR [rbx+40],rax
 mov DWORD PTR [rbx+52],eax
 mov DWORD PTR [rbx+56],eax
 mov edi,3
 cmp DWORD PTR [rbx+60],0
 jne span_a_store
 cmp QWORD PTR [rbx+16],0
 jle span_a_store
 mov eax,DWORD PTR [rbx+48]
 dec eax
 cmp eax,2
 ja span_a_store
 mov rsi,QWORD PTR [rbx]
 SPAN_CLEAR_JOB
 mov QWORD PTR [rsp+32],rsi
 mov rax,QWORD PTR [rbx+8]
 mov QWORD PTR [rsp+40],rax
 mov rax,QWORD PTR [rbx+16]
 mov QWORD PTR [rsp+48],rax
 mov eax,DWORD PTR [rbx+48]
 mov DWORD PTR [rsp+100],eax
 mov DWORD PTR [rsp+104],8
 lea rcx,[rsp+32]
 call boom_native_memory_service
 mov edi,eax
 mov eax,DWORD PTR [rsp+112]
 mov DWORD PTR [rbx+56],eax
 ; Publish any real acquired token immediately, before any metadata lookup.
 mov r12,QWORD PTR [rsp+80]
 mov r13,QWORD PTR [rsp+88]
 test r12,r12
 jz span_a_no_token
 mov QWORD PTR [rbx+32],r12
 mov QWORD PTR [rbx+40],r13
 test edi,edi
 jnz span_a_rollback
 test r13,r13
 jz span_a_bad_unlocked
 mov rax,QWORD PTR [rsp+72]
 cmp rax,QWORD PTR [rbx+8]
 jne span_a_bad_unlocked
 mov rax,QWORD PTR [rsp+120]
 cmp rax,QWORD PTR [rbx+16]
 jne span_a_bad_unlocked
 ; Core just validated this trusted native Owner storage. A real active lease
 ; prevents core.close/free/resize from invalidating records across this gap.
 mov rax,SPAN_OWNER_MAGIC
 cmp QWORD PTR [rsi],rax
 jne span_a_bad_unlocked
 cmp DWORD PTR [rsi+8],128
 jne span_a_bad_unlocked
 cmp DWORD PTR [rsi+12],1
 jne span_a_bad_unlocked
 lea rcx,[rsi+16]
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rsi+24],1
 jne span_a_bad_locked
 mov ecx,DWORD PTR [rsi+28]
 test ecx,ecx
 jz span_a_bad_locked
 cmp ecx,4096
 ja span_a_bad_locked
 mov eax,ecx
 shl eax,4
 cmp DWORD PTR [rsi+124],eax
 jne span_a_bad_locked
 cmp QWORD PTR [rsi+40],0
 je span_a_bad_locked
 cmp QWORD PTR [rsi+40],rax
 ja span_a_bad_locked
 cmp QWORD PTR [rsi+32],0
 je span_a_bad_locked
 mov edx,ecx
 cmp QWORD PTR [rsi+32],rdx
 ja span_a_bad_locked
 cmp QWORD PTR [rsi+48],0
 jle span_a_bad_locked
 cmp QWORD PTR [rsi+56],0
 jle span_a_bad_locked
 mov rdx,QWORD PTR [rsi+48]
 cmp rdx,QWORD PTR [rsi+56]
 ja span_a_bad_locked
 imul edx,ecx,576
 cmp QWORD PTR [rsi+80],rdx
 jne span_a_bad_locked
 mov r8,QWORD PTR [rsi+64]
 test r8,r8
 jz span_a_bad_locked
 test r8b,7
 jnz span_a_bad_locked
 mov r9,r8
 add r9,rdx
 jc span_a_bad_locked
 mov edx,ecx
 shl rdx,6
 add rdx,r8
 jc span_a_bad_locked
 cmp rdx,QWORD PTR [rsi+72]
 jne span_a_bad_locked
 mov r10,rax
 shl r10,5
 add r10,rdx
 jc span_a_bad_locked
 cmp r10,r9
 jne span_a_bad_locked
 cmp QWORD PTR [rsi+88],r12
 jb span_a_bad_locked
 cmp QWORD PTR [rsi+88],r13
 jb span_a_bad_locked
 mov r8,rdx
 mov ecx,eax
span_a_find_token:
 cmp QWORD PTR [r8],r12
 je span_a_token_found
 add r8,32
 dec ecx
 jnz span_a_find_token
 jmp span_a_bad_locked
span_a_token_found:
 mov eax,DWORD PTR [r8+12]
 cmp eax,DWORD PTR [rbx+48]
 jne span_a_bad_locked
 mov rax,QWORD PTR [r8+24]
 cmp rax,QWORD PTR [rbx+16]
 jne span_a_bad_locked
 mov eax,DWORD PTR [r8+8]
 cmp eax,DWORD PTR [rsi+28]
 jae span_a_bad_locked
 shl rax,6
 add rax,QWORD PTR [rsi+64]
 mov r14,rax
 cmp DWORD PTR [r14+40],1
 jne span_a_bad_locked
 mov rax,QWORD PTR [r14+24]
 ; SPAN_QUERY_GENERATION_CHECK -- exact test-only fault-injection anchor.
 cmp rax,r13
 jne span_a_bad_locked
 cmp DWORD PTR [r14+32],0
 je span_a_bad_locked
 mov eax,DWORD PTR [r14+32]
 cmp rax,QWORD PTR [rsi+40]
 ja span_a_bad_locked
 cmp DWORD PTR [rbx+48],1
 jne span_a_check_writer
 cmp DWORD PTR [r14+36],0
 jne span_a_bad_locked
 jmp span_a_permission_ready
span_a_check_writer:
 cmp DWORD PTR [r14+32],1
 jne span_a_bad_locked
 cmp DWORD PTR [r14+36],1
 jne span_a_bad_locked
span_a_permission_ready:
 cmp QWORD PTR [r14+48],3
 jne span_a_bad_locked
 cmp QWORD PTR [r14+56],0
 jne span_a_bad_locked
 mov r10,QWORD PTR [r14]
 test r10,r10
 jz span_a_bad_locked
 mov r11,QWORD PTR [r14+8]
 test r11,r11
 jle span_a_bad_locked
 cmp r11,QWORD PTR [r14+16]
 jne span_a_bad_locked
 cmp r11,QWORD PTR [rsi+48]
 ja span_a_bad_locked
 mov rax,r10
 add rax,r11
 jc span_a_bad_locked
 mov rax,QWORD PTR [rbx+8]
 cmp rax,r10
 jb span_a_bad_locked
 sub rax,r10
 cmp rax,QWORD PTR [r8+16]
 jne span_a_bad_locked
 cmp rax,r11
 jae span_a_bad_locked
 sub r11,rax
 cmp QWORD PTR [rbx+16],r11
 ja span_a_bad_locked
 mov QWORD PTR [rbx+24],r11
 xor edi,edi
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 jmp span_a_store
span_a_bad_locked:
 mov edi,5
 lea rcx,[rsi+16]
 call ReleaseSRWLockExclusive
 jmp span_a_rollback
span_a_no_token:
 test edi,edi
 jnz span_a_store
 mov edi,5
 jmp span_a_store
span_a_bad_unlocked:
 mov edi,5
span_a_rollback:
 ; Never call the core while holding Owner.SRW. Failure keeps the real token.
 mov QWORD PTR [rbx+24],0
 SPAN_CLEAR_JOB
 mov QWORD PTR [rsp+32],rsi
 mov QWORD PTR [rsp+80],r12
 mov DWORD PTR [rsp+104],9
 lea rcx,[rsp+32]
 call boom_native_memory_service
 test eax,eax
 jnz span_a_release_failed
 mov QWORD PTR [rbx+32],0
 mov QWORD PTR [rbx+40],0
 jmp span_a_store
span_a_release_failed:
 mov edi,eax
 mov eax,DWORD PTR [rsp+112]
 mov DWORD PTR [rbx+56],eax
 jmp span_a_store
span_a_busy_return:
 mov DWORD PTR [rbx+56],0
span_a_store:
 mov DWORD PTR [rbx+52],edi
 mov eax,edi
 jmp span_a_return
span_a_bad_pointer:
 mov eax,3
span_a_return:
 add rsp,184
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_native_memory_span_acquire ENDP

PUBLIC boom_native_memory_span_release
boom_native_memory_span_release PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,160
 .allocstack 160
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz span_r_bad_pointer
 test bl,7
 jnz span_r_bad_pointer
 xor edi,edi
 mov DWORD PTR [rbx+56],0
 cmp QWORD PTR [rbx+32],0
 je span_r_clear
 mov rsi,QWORD PTR [rbx]
 SPAN_CLEAR_JOB
 mov QWORD PTR [rsp+32],rsi
 mov rax,QWORD PTR [rbx+32]
 mov QWORD PTR [rsp+80],rax
 mov DWORD PTR [rsp+104],9
 lea rcx,[rsp+32]
 call boom_native_memory_service
 mov edi,eax
 mov eax,DWORD PTR [rsp+112]
 mov DWORD PTR [rbx+56],eax
 test edi,edi
 jnz span_r_store
span_r_clear:
 mov QWORD PTR [rbx+24],0
 mov QWORD PTR [rbx+32],0
 mov QWORD PTR [rbx+40],0
span_r_store:
 mov DWORD PTR [rbx+52],edi
 mov eax,edi
 jmp span_r_return
span_r_bad_pointer:
 mov eax,3
span_r_return:
 add rsp,160
 pop rdi
 pop rsi
 pop rbx
 ret
boom_native_memory_span_release ENDP
