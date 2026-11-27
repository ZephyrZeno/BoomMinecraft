; Job64: Owner0,normalHeap8,sourceAddress16,destinationByteArray24,
; destinationPayloadOffset32,bytes40,status48D,reserved52D,copied56Q.
; 0 copied;1 no leased source range;2 arguments/range;3 invalid owner;
; 4 owner not ready;5 destination not byte[];6 destination not in normal heap.
; All caller/native structures remain live. GC is quiescent during this call.
; Only real leased readonly owner bytes -> a real normal heap byte[] are copied.
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockShared:PROC
EXTERN boom_heap_contains:PROC
.code
PUBLIC boom_jimage_owned_copy_to_bytes
boom_jimage_owned_copy_to_bytes PROC FRAME
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
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz juc_unsafe_job
 test bl,7
 jnz juc_unsafe_job
 mov rax,rbx
 add rax,64
 jc juc_unsafe_job
 mov r12,QWORD PTR [rbx]
 test r12,r12
 jz juc_unsafe_job
 test r12b,7
 jnz juc_unsafe_job
 mov rdx,r12
 add rdx,128
 jc juc_unsafe_job
 cmp rbx,rdx
 jae juc_job_ok
 cmp r12,rax
 jb juc_unsafe_job
juc_job_ok:
 mov DWORD PTR [rbx+48],2
 mov QWORD PTR [rbx+56],0
 cmp DWORD PTR [rbx+52],0
 jne juc_return
 mov rbp,QWORD PTR [rbx+40]
 test rbp,rbp
 js juc_return
 mov rsi,QWORD PTR [rbx+16]
 mov rax,rsi
 add rax,rbp
 jc juc_return
 mov rax,QWORD PTR [rbx+32]
 test rax,rax
 js juc_return
 add rax,rbp
 jc juc_return
 mov DWORD PTR [rbx+48],6
 mov rdi,QWORD PTR [rbx+24]
 mov rcx,QWORD PTR [rbx+8]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz juc_return
 mov DWORD PTR [rbx+48],5
 cmp QWORD PTR [rdi-8],264
 jne juc_return
 cmp DWORD PTR [rdi-20],0
 jne juc_return
 mov DWORD PTR [rbx+48],2
 mov rax,QWORD PTR [rbx+32]
 mov rdx,QWORD PTR [rdi-16]
 sub rdx,rax
 jc juc_return
 cmp rbp,rdx
 ja juc_return
 add rdi,rax
 jc juc_return
 mov rdx,rdi
 add rdx,rbp
 jc juc_return
 test rbp,rbp
 jz juc_owner_header
 lea rax,[rbx+64]
 cmp rdi,rax
 jae juc_owner_header
 cmp rdx,rbx
 ja juc_return
juc_owner_header:
 mov DWORD PTR [rbx+48],3
 mov rax,03130474D494A4F42h
 cmp QWORD PTR [r12],rax
 jne juc_return
 cmp DWORD PTR [r12+8],128
 jne juc_return
 cmp DWORD PTR [r12+12],1
 jne juc_return
 lea rcx,[r12+16]
 call AcquireSRWLockShared
 ; Check and use the same owner while close/release cannot acquire exclusive.
 mov rax,03130474D494A4F42h
 cmp QWORD PTR [r12],rax
 jne juc_unlock
 cmp DWORD PTR [r12+8],128
 jne juc_unlock
 cmp DWORD PTR [r12+12],1
 jne juc_unlock
 cmp QWORD PTR [r12+120],0
 jne juc_unlock
 mov eax,DWORD PTR [r12+28]
 dec eax
 cmp eax,1023
 ja juc_unlock
 inc eax
 mov r14,QWORD PTR [r12+32]
 cmp r14,rax
 ja juc_unlock
 cmp DWORD PTR [r12+24],1
 jne juc_not_ready
 mov r13,QWORD PTR [r12+48]
juc_find:
 test r13,r13
 jz juc_end_list
 test r14,r14
 jz juc_unlock
 dec r14
 test r13b,7
 jnz juc_unlock
 cmp QWORD PTR [r13+8],0
 je juc_unlock
 cmp DWORD PTR [r13+60],0
 jne juc_unlock
 cmp QWORD PTR [r13+72],0
 jne juc_unlock
 mov rax,QWORD PTR [r13+16]
 test rax,rax
 jz juc_unlock
 mov rdx,QWORD PTR [r13+24]
 cmp rdx,28
 jb juc_unlock
 mov rcx,rax
 add rcx,rdx
 jc juc_unlock
 cmp QWORD PTR [r13+32],0
 je juc_unlock
 cmp QWORD PTR [r13+32],-1
 je juc_unlock
 cmp QWORD PTR [r13+40],0
 je juc_unlock
 mov r8,QWORD PTR [r13+64]
 cmp r8,28
 jb juc_unlock
 cmp r8,rdx
 ja juc_unlock
 cmp QWORD PTR [r13+48],0
 je juc_next
 cmp rsi,rax
 jb juc_next
 cmp rsi,rcx
 ja juc_next
 mov r8,rsi
 add r8,rbp
 jc juc_unlock
 cmp r8,rcx
 ja juc_next
 ; The entire copy, not just range lookup, is protected by this shared lock.
 mov rcx,rbp
 cld
 rep movsb
 mov QWORD PTR [rbx+56],rbp
 mov DWORD PTR [rbx+48],0
 jmp juc_unlock
juc_next:
 mov r13,QWORD PTR [r13]
 jmp juc_find
juc_end_list:
 test r14,r14
 jnz juc_unlock
 mov DWORD PTR [rbx+48],1
 jmp juc_unlock
juc_not_ready:
 mov DWORD PTR [rbx+48],4
juc_unlock:
 lea rcx,[r12+16]
 call ReleaseSRWLockShared
juc_return:
 mov eax,DWORD PTR [rbx+48]
 jmp juc_done
juc_unsafe_job:
 mov eax,2
juc_done:
 add rsp,32
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_jimage_owned_copy_to_bytes ENDP
