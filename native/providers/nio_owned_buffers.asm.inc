; NIOB56/2: heap cell8, Unsafe layout16, SRW lifetime lock24, allocations32,
; live count40, original WindowsException(int) materializer48.
; Node: next0, payload bytes8, SRW query lock16, reserved24, native memory32.
; Queries share the lifetime lock and lock their two nodes in address order.
; Independent path/output buffers can enter Win32 at the same time.
EXTERN LocalAlloc:PROC
EXTERN LocalFree:PROC
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN AcquireSRWLockShared:PROC
EXTERN ReleaseSRWLockShared:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_object_check:PROC
EXTERN boom_win32_raw_file_attributes:PROC
PUBLIC boom_nio_buffer_service
.code

; Trusted pool, candidate address, minimum bytes, with lock held. Return the
; remaining extent and node in R10, or zero. No end-pointer addition is needed.
nio_extent PROC PRIVATE
 mov r10,QWORD PTR [rcx+32]
ne_next:
 test r10,r10
 jz ne_zero
 lea r11,[r10+32]
 mov rax,rdx
 sub rax,r11
 jc ne_skip
 mov r11,QWORD PTR [r10+8]
 sub r11,rax
 jbe ne_skip
 cmp r11,r8
 jb ne_skip
 mov rax,r11
 ret
ne_skip:
 mov r10,QWORD PTR [r10]
 jmp ne_next
ne_zero:
 xor eax,eax
 ret
nio_extent ENDP

; Source adapter ABI (Context32, packed Java arguments, NIOB56, operation).
; 0 allocateMemory0, 1 freeMemory0, 2 copyMemory0 (normal char[] -> owned),
; 3 GetFileAttributesEx0, 4/5/6 owned null-base getInt/getLong/putChar.
; The latter are composed with the existing heap/VM-counter Unsafe service.
boom_nio_buffer_service PROC FRAME
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
 mov rsi,rdx
 mov rdi,r8
 mov r12d,r9d
 test rbx,rbx
 jz nb_zero
 cmp DWORD PTR [rbx],0
 jne nb_zero
 test rsi,rsi
 jz nb_bad
 test rdi,rdi
 jz nb_bad
 cmp DWORD PTR [rdi],0424F494Eh
 jne nb_bad
 cmp DWORD PTR [rdi+4],2
 jne nb_bad
 cmp r12d,6
 ja nb_bad
 cmp r12d,3
 je nb_query_lock
 mov rcx,QWORD PTR [rdi+8]
 test rcx,rcx
 jz nb_bad
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rsi]
 call boom_heap_contains
 test eax,eax
 jz nb_bad
 mov rcx,QWORD PTR [rsi]
 mov rdx,QWORD PTR [rdi+16]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz nb_zero
 lea rcx,[rdi+24]
 call AcquireSRWLockExclusive
 jmp nb_locked
nb_query_lock:
 lea rcx,[rdi+24]
 call AcquireSRWLockShared
nb_locked:
 xor r14d,r14d
 xor r15d,r15d
 cmp r12d,0
 je nb_allocate
 cmp r12d,1
 je nb_free
 cmp r12d,2
 je nb_copy
 cmp r12d,3
 je nb_query
 cmp QWORD PTR [rsi+8],0
 jne nb_unsupported
 mov r13,QWORD PTR [rsi+16]
 mov rcx,rdi
 mov rdx,r13
 mov r8d,4
 cmp r12d,4
 je nb_scalar
 mov r8d,8
 cmp r12d,5
 je nb_scalar
 mov r8d,2
nb_scalar:
 call nio_extent
 test rax,rax
 jz nb_unsupported
 cmp r12d,5
 je nb_long
 cmp r12d,6
 je nb_char
 mov r14d,DWORD PTR [r13]
 jmp nb_unlock
nb_long:
 mov r14,QWORD PTR [r13]
 jmp nb_unlock
nb_char:
 mov ax,WORD PTR [rsi+24]
 mov WORD PTR [r13],ax
 jmp nb_unlock

nb_allocate:
 mov r13,QWORD PTR [rsi+8]
 test r13,r13
 js nb_unsupported
 jz nb_unlock
 ; The Java allocateMemory wrapper aligns and checks the signed request.
 ; Returning zero on allocation failure lets that original wrapper throw OOME.
 lea rdx,[r13+32]
 xor ecx,ecx
 call LocalAlloc
 test rax,rax
 jz nb_unlock
 mov rdx,QWORD PTR [rdi+32]
 mov QWORD PTR [rax],rdx
 mov QWORD PTR [rax+8],r13
 mov QWORD PTR [rax+16],0
 mov QWORD PTR [rax+24],0
 mov QWORD PTR [rdi+32],rax
 inc QWORD PTR [rdi+40]
 lea r14,[rax+32]
 jmp nb_unlock
nb_free:
 mov r13,QWORD PTR [rsi+8]
 test r13,r13
 jz nb_unlock
 lea rdx,[rdi+32]
nb_free_next:
 mov rcx,QWORD PTR [rdx]
 test rcx,rcx
 jz nb_unsupported
 lea rax,[rcx+32]
 cmp rax,r13
 je nb_free_found
 mov rdx,rcx
 jmp nb_free_next
nb_free_found:
 mov rax,QWORD PTR [rcx]
 mov QWORD PTR [rdx],rax
 dec QWORD PTR [rdi+40]
 call LocalFree
 jmp nb_unlock

nb_copy:
 ; The locked WindowsNativeDispatcher uses exactly the normal char[] payload
 ; and a null destination base. Its own Java code copies the terminating NUL
 ; separately. The source backend's primitive-array base offset is zero.
 cmp QWORD PTR [rsi+24],0
 jne nb_unsupported
 mov r13,QWORD PTR [rsi+8]
 mov rcx,QWORD PTR [rdi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r13
 call boom_heap_contains
 test eax,eax
 jz nb_unsupported
 cmp QWORD PTR [r13-8],261
 jne nb_unsupported
 cmp DWORD PTR [r13-20],0
 jne nb_unsupported
 mov rcx,QWORD PTR [r13-16]
 mov rax,QWORD PTR [rsi+16]
 sub rcx,rax
 jc nb_unsupported
 cmp rcx,QWORD PTR [rsi+40]
 jb nb_unsupported
 add r13,rax
 mov rcx,rdi
 mov rdx,QWORD PTR [rsi+32]
 mov r8,QWORD PTR [rsi+40]
 call nio_extent
 test rax,rax
 jz nb_unsupported
 mov rcx,QWORD PTR [rsi+40]
 mov rdx,QWORD PTR [rsi+32]
nb_copy_next:
 test rcx,rcx
 jz nb_unlock
 mov al,BYTE PTR [r13]
 mov BYTE PTR [rdx],al
 inc r13
 inc rdx
 dec rcx
 jmp nb_copy_next

nb_query:
 mov r13,QWORD PTR [rsi]
 test r13b,1
 jnz nb_unsupported
 mov rcx,rdi
 mov rdx,r13
 mov r8d,2
 call nio_extent
 shr rax,1
 jz nb_unsupported
 mov QWORD PTR [rsp+72],rax
 mov QWORD PTR [rsp+80],r10
 mov rcx,rdi
 mov rdx,QWORD PTR [rsi+8]
 mov r8d,36
 call nio_extent
 test rax,rax
 jz nb_unsupported
 mov rax,QWORD PTR [rsp+80]
 cmp rax,r10
 jb nb_query_ordered
 ja nb_query_reverse
 xor r10d,r10d
 jmp nb_query_ordered
nb_query_reverse:
 xchg rax,r10
 mov QWORD PTR [rsp+80],rax
nb_query_ordered:
 mov QWORD PTR [rsp+88],r10
 lea rcx,[rax+16]
 call AcquireSRWLockExclusive
 mov rcx,QWORD PTR [rsp+88]
 test rcx,rcx
 jz nb_query_scan
 add rcx,16
 call AcquireSRWLockExclusive
nb_query_scan:
 mov rax,QWORD PTR [rsp+72]
 mov rdx,r13
nb_terminator:
 cmp WORD PTR [rdx],0
 je nb_query_os
 add rdx,2
 dec rax
 jnz nb_terminator
 mov DWORD PTR [rbx],20
 jmp nb_query_release
nb_query_os:
 mov rcx,r13
 lea rdx,[rsp+32]
 call boom_win32_raw_file_attributes
 mov r15d,eax
 test eax,eax
 jnz nb_query_release
 mov rdx,QWORD PTR [rsi+8]
 movups xmm0,XMMWORD PTR [rsp+32]
 movups xmm1,XMMWORD PTR [rsp+48]
 mov eax,DWORD PTR [rsp+64]
 movups XMMWORD PTR [rdx],xmm0
 movups XMMWORD PTR [rdx+16],xmm1
 mov DWORD PTR [rdx+32],eax
nb_query_release:
 mov rcx,QWORD PTR [rsp+88]
 test rcx,rcx
 jz nb_query_release_first
 add rcx,16
 call ReleaseSRWLockExclusive
nb_query_release_first:
 mov rcx,QWORD PTR [rsp+80]
 add rcx,16
 call ReleaseSRWLockExclusive
 jmp nb_unlock
nb_unsupported:
 mov DWORD PTR [rbx],20
nb_unlock:
 lea rcx,[rdi+24]
 cmp r12d,3
 je nb_unlock_query
 call ReleaseSRWLockExclusive
 jmp nb_unlocked
nb_unlock_query:
 call ReleaseSRWLockShared
nb_unlocked:
 test r15d,r15d
 jz nb_return
 ; Heap allocation/Java callbacks can reenter native code. Release the SRW
 ; lock first. A candidate without the original exception path must block.
 mov rax,QWORD PTR [rdi+48]
 test rax,rax
 jz nb_no_exception
 mov rcx,rbx
 mov edx,r15d
 call rax
 cmp DWORD PTR [rbx],0
 jne nb_zero
nb_no_exception:
 mov DWORD PTR [rbx],20
 jmp nb_zero
nb_return:
 mov rax,r14
 jmp nb_done
nb_bad:
 mov DWORD PTR [rbx],7
nb_zero:
 xor eax,eax
nb_done:
 add rsp,96
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_nio_buffer_service ENDP
