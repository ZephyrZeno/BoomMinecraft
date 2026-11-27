; Standalone native helper over the frozen normal heap/primitive-array ABI.
; RCX trusted live heap; RDX candidate oop; R8 byte offset; R9 byte length;
; fifth argument: trusted writable QWORD outAddress*. Failure never writes out.
; No Java fields, Context, allocations, safepoints or owner dependencies.
EXTERN boom_heap_contains:PROC
PUBLIC boom_primitive_heap_span
.const
phs_shifts BYTE 0,1,2,3,0,1,2,3 ; atype4..11, tag260..267
.code
boom_primitive_heap_span PROC FRAME
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
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov r12,r8
 mov r13,r9
 mov rdi,QWORD PTR [rsp+112]
 test rbx,rbx
 jz phs_bad_argument
 test rsi,rsi
 jz phs_bad_argument
 test rdi,rdi
 jz phs_bad_argument
 test r12,r12
 js phs_bad_argument
 test r13,r13
 js phs_bad_argument
 ; Heap is a caller-owned live handle; unlike oop, it is not an untrusted
 ; absolute address. The immutable arena fields delimit every header read.
 cmp DWORD PTR [rbx],048454150h
 jne phs_bad_argument
 cmp DWORD PTR [rbx+4],1
 jne phs_bad_argument
 mov rax,QWORD PTR [rbx+16]
 cmp rax,32
 jb phs_bad_argument
 cmp rax,040000000h
 ja phs_bad_argument
 test al,15
 jnz phs_bad_argument
 mov r10,rbx
 add r10,128
 jc phs_bad_argument
 mov r11,r10
 add r11,rax
 jc phs_bad_argument
 cmp r11,QWORD PTR [rbx+24]
 jne phs_bad_argument
 mov rax,r10
 add rax,32
 cmp rsi,rax
 jb phs_not_owned_direct
 cmp rsi,r11
 ja phs_not_owned_direct
 test rsi,15
 jnz phs_not_owned_direct
 ; Same lock word/protocol as frozen heap_lock. No heap operation that takes
 ; this lock is called below; boom_heap_contains is a leaf read-only check.
phs_lock:
 mov eax,1
 xchg DWORD PTR [rbx+8],eax
 test eax,eax
 jz phs_locked
phs_spin:
 pause
 cmp DWORD PTR [rbx+8],0
 jne phs_spin
 jmp phs_lock
phs_locked:
 mov rdx,rsi
 sub rdx,32
 ; The candidate's header-like payload bytes cannot establish membership.
 ; Walk only real block starts from the immutable arena origin.
phs_walk:
 cmp r10,rdx
 je phs_exact_block
 ja phs_not_owned
 mov rax,r11
 sub rax,r10
 cmp rax,32
 jb phs_bad_shape
 mov rax,QWORD PTR [r10]
 cmp rax,32
 jb phs_bad_shape
 test al,15
 jnz phs_bad_shape
 add r10,rax
 jc phs_bad_shape
 cmp r10,r11
 ja phs_bad_shape
 jmp phs_walk
phs_exact_block:
 mov rcx,rbx
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz phs_not_owned
 cmp DWORD PTR [rsi-20],0
 jne phs_bad_shape
 mov rax,QWORD PTR [rsi-8]
 sub rax,260
 cmp rax,7
 ja phs_bad_shape
 lea r10,phs_shifts
 movzx ecx,BYTE PTR [r10+rax]
 mov r10,QWORD PTR [rsi-16] ; physical payload bytes, NOT logical length
 mov rax,r10
 shr rax,cl
 cmp rax,07FFFFFFFh
 ja phs_bad_shape
 shl rax,cl
 cmp rax,r10
 jne phs_bad_shape ; physical byte count must be divisible by element width
 mov rax,r12
 add rax,r13
 jo phs_overflow
 jc phs_overflow
 cmp rax,r10
 ja phs_bounds
 ; Equality is legal only with a zero remaining span, including empty arrays.
 mov rax,rsi
 add rax,r12
 jc phs_overflow
 mov QWORD PTR [rdi],rax
 xor eax,eax
 jmp phs_unlock
phs_bad_shape:
 mov eax,13
 jmp phs_unlock
phs_not_owned:
 mov eax,487
 jmp phs_unlock
phs_bounds:
 mov eax,122
 jmp phs_unlock
phs_overflow:
 mov eax,534
phs_unlock:
 mov DWORD PTR [rbx+8],0
 jmp phs_done
phs_bad_argument:
 mov eax,87
 jmp phs_done
phs_not_owned_direct:
 mov eax,487
phs_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_primitive_heap_span ENDP
