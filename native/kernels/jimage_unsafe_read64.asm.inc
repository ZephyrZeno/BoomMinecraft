; Caller-owned Job48: Owner128*0,address8,plain kind16D,reserved20D,
; value24Q,status32D,reserved36D,reserved40Q. No Context or Java state.
; Status0 actual read,1 not leased/in range,2 arguments,3 bad owner,4 not ready.
; Owner/record memory is trusted, live, and created by pinned JIMAGE owner ABI1.
; The owner allocation must outlive all calls. Actual reads hold its shared SRW.
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockShared:PROC
.code
PUBLIC boom_jimage_owned_scalar_read
boom_jimage_owned_scalar_read PROC FRAME
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
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz jur_scalar_unsafe_job
 test bl,7
 jnz jur_scalar_unsafe_job
 mov rax,rbx
 add rax,48
 jc jur_scalar_unsafe_job
 mov rsi,QWORD PTR [rbx]
 test rsi,rsi
 jz jur_scalar_unsafe_job
 test sil,7
 jnz jur_scalar_unsafe_job
 mov rdx,rsi
 add rdx,128
 jc jur_scalar_unsafe_job
 cmp rbx,rdx
 jae jur_scalar_job_ok
 cmp rsi,rax
 jb jur_scalar_unsafe_job
jur_scalar_job_ok:
 mov QWORD PTR [rbx+24],0
 mov DWORD PTR [rbx+32],2
 cmp DWORD PTR [rbx+20],0
 jne jur_scalar_return
 cmp DWORD PTR [rbx+36],0
 jne jur_scalar_return
 cmp QWORD PTR [rbx+40],0
 jne jur_scalar_return
 mov ebp,DWORD PTR [rbx+16]
 cmp ebp,2
 jb jur_scalar_return
 cmp ebp,6
 ja jur_scalar_return
 mov r12d,1
 cmp ebp,2
 je jur_scalar_width
 mov r12d,2
 cmp ebp,4
 jbe jur_scalar_width
 mov r12d,4
 cmp ebp,5
 je jur_scalar_width
 mov r12d,8
jur_scalar_width:
 mov rdi,QWORD PTR [rbx+8]
 mov rax,rdi
 add rax,r12
 jc jur_scalar_return
 mov DWORD PTR [rbx+32],3
 mov rax,03130474D494A4F42h
 cmp QWORD PTR [rsi],rax
 jne jur_scalar_return
 cmp DWORD PTR [rsi+8],128
 jne jur_scalar_return
 cmp DWORD PTR [rsi+12],1
 jne jur_scalar_return
 lea rcx,[rsi+16]
 call AcquireSRWLockShared
 ; Everything below, including the physical load, is inside the same lease.
 mov rax,03130474D494A4F42h
 cmp QWORD PTR [rsi],rax
 jne jur_scalar_unlock
 cmp DWORD PTR [rsi+8],128
 jne jur_scalar_unlock
 cmp DWORD PTR [rsi+12],1
 jne jur_scalar_unlock
 cmp QWORD PTR [rsi+120],0
 jne jur_scalar_unlock
 mov eax,DWORD PTR [rsi+28]
 dec eax
 cmp eax,1023
 ja jur_scalar_unlock
 inc eax
 mov r14,QWORD PTR [rsi+32]
 cmp r14,rax
 ja jur_scalar_unlock
 cmp DWORD PTR [rsi+24],1
 jne jur_scalar_not_ready
 mov r13,QWORD PTR [rsi+48]
jur_scalar_find:
 test r13,r13
 jz jur_scalar_end_list
 test r14,r14
 jz jur_scalar_unlock
 dec r14
 test r13b,7
 jnz jur_scalar_unlock
 cmp QWORD PTR [r13+8],0
 je jur_scalar_unlock
 cmp DWORD PTR [r13+60],0
 jne jur_scalar_unlock
 cmp QWORD PTR [r13+72],0
 jne jur_scalar_unlock
 mov rax,QWORD PTR [r13+16]
 test rax,rax
 jz jur_scalar_unlock
 mov rdx,QWORD PTR [r13+24]
 cmp rdx,28
 jb jur_scalar_unlock
 mov rcx,rax
 add rcx,rdx
 jc jur_scalar_unlock
 cmp QWORD PTR [r13+32],0
 je jur_scalar_unlock
 cmp QWORD PTR [r13+32],-1
 je jur_scalar_unlock
 cmp QWORD PTR [r13+40],0
 je jur_scalar_unlock
 mov r8,QWORD PTR [r13+64]
 cmp r8,28
 jb jur_scalar_unlock
 cmp r8,rdx
 ja jur_scalar_unlock
 cmp QWORD PTR [r13+48],0
 je jur_scalar_next
 cmp rdi,rax
 jb jur_scalar_next
 cmp rdi,rcx
 jae jur_scalar_next
 mov r8,rdi
 add r8,r12
 jc jur_scalar_unlock
 cmp r8,rcx
 ja jur_scalar_next
 ; No mapping byte is touched before all complete-record bounds checks.
 cmp ebp,2
 je jur_scalar_byte
 cmp ebp,3
 je jur_scalar_char
 cmp ebp,4
 je jur_scalar_short
 cmp ebp,5
 je jur_scalar_int
 mov rax,QWORD PTR [rdi]
 jmp jur_scalar_loaded
jur_scalar_byte:
 movsx rax,BYTE PTR [rdi]
 jmp jur_scalar_loaded
jur_scalar_char:
 movzx eax,WORD PTR [rdi]
 jmp jur_scalar_loaded
jur_scalar_short:
 movsx rax,WORD PTR [rdi]
 jmp jur_scalar_loaded
jur_scalar_int:
 movsxd rax,DWORD PTR [rdi]
jur_scalar_loaded:
 mov QWORD PTR [rbx+24],rax
 mov DWORD PTR [rbx+32],0
 jmp jur_scalar_unlock
jur_scalar_next:
 mov r13,QWORD PTR [r13]
 jmp jur_scalar_find
jur_scalar_end_list:
 test r14,r14
 jnz jur_scalar_unlock
 mov DWORD PTR [rbx+32],1
 jmp jur_scalar_unlock
jur_scalar_not_ready:
 mov DWORD PTR [rbx+32],4
jur_scalar_unlock:
 lea rcx,[rsi+16]
 call ReleaseSRWLockShared
jur_scalar_return:
 mov eax,DWORD PTR [rbx+32]
 jmp jur_scalar_done
jur_scalar_unsafe_job:
 mov eax,2
jur_scalar_done:
 add rsp,32
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
boom_jimage_owned_scalar_read ENDP
