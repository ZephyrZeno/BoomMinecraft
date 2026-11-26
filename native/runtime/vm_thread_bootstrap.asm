; Normal-layout primordial VM thread. Java constructors are original AOT bodies.
; VTBP192/1: state8, capacity12, heapCell16, registryCell24, roots40*32,
; nativePool40, layouts48/56/64, classes72/80/88/96, VM.initLevelCell104,
; literalFn112/pool120/id128, eetop132/holder136/status140 offsets,
; constructors144/152/160/168, tidOffset176, reserved180..191.
; roots: Thread, system ThreadGroup, main ThreadGroup, ACC, main name.
; Call only before System phase 1 on the VM owner OS thread. There is no
; specialized Java constructor or omitted branch. Child/start/exit are separate.
option casemap:none
EXTERN boom_class_ensure32:PROC
EXTERN boom_object_new:PROC
EXTERN boom_threads_create:PROC
EXTERN boom_threads_attach:PROC
EXTERN boom_threads_detach:PROC
EXTERN boom_threads_destroy:PROC
EXTERN boom_thread_native_bind:PROC
PUBLIC boom_vm_thread_bootstrap
.code
; bootstrap(Context32, VTBP192*) -> main Thread oop / NULL.
boom_vm_thread_bootstrap PROC FRAME
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
 sub rsp,128
 .allocstack 128
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 xor r13d,r13d
 xor r14d,r14d
 xor r15d,r15d
 test rbx,rbx
 jz vtb_zero
 cmp DWORD PTR [rbx],0
 jne vtb_zero
 test rsi,rsi
 jz vtb_bad
 cmp DWORD PTR [rsi],056544250h
 jne vtb_bad
 cmp DWORD PTR [rsi+4],1
 jne vtb_bad
 cmp DWORD PTR [rsi+12],1
 jb vtb_bad
 cmp DWORD PTR [rsi+12],16384
 ja vtb_bad
 cmp DWORD PTR [rsi+180],0
 jne vtb_bad
 cmp QWORD PTR [rsi+184],0
 jne vtb_bad
 mov eax,16
vtb_check_pointers:
 cmp QWORD PTR [rsi+rax],0
 je vtb_bad
 add eax,8
 cmp eax,128
 jb vtb_check_pointers
 mov eax,144
vtb_check_constructors:
 cmp QWORD PTR [rsi+rax],0
 je vtb_bad
 add eax,8
 cmp eax,176
 jb vtb_check_constructors
 mov rdi,QWORD PTR [rsi+32]
 xor eax,eax
vtb_check_roots:
 cmp QWORD PTR [rdi+rax*8],0
 jne vtb_bad
 inc eax
 cmp eax,5
 jb vtb_check_roots
 mov rax,QWORD PTR [rsi+24]
 cmp QWORD PTR [rax],0
 jne vtb_bad
 mov rax,QWORD PTR [rsi+16]
 mov r12,QWORD PTR [rax]
 test r12,r12
 jz vtb_bad
 xor eax,eax
 mov ecx,1
 lock cmpxchg DWORD PTR [rsi+8],ecx
 jne vtb_bad
 ; Original VM initialization preserves level zero until System advances it.
 mov rcx,QWORD PTR [rsi+96]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne vtb_fail
 mov rax,QWORD PTR [rsi+104]
 cmp DWORD PTR [rax],0
 jne vtb_fail
 mov rcx,QWORD PTR [rsi+72]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne vtb_fail
 mov rcx,QWORD PTR [rsi+80]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne vtb_fail
 mov rcx,QWORD PTR [rsi+88]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne vtb_fail
 ; Canonical normal String, allocated by the existing literal ASM service.
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+120]
 mov r8d,DWORD PTR [rsi+128]
 call QWORD PTR [rsi+112]
 cmp DWORD PTR [rbx],0
 jne vtb_fail
 test rax,rax
 jz vtb_fail
 mov QWORD PTR [rdi+32],rax
 ; system ThreadGroup: execute the original private ()V constructor.
 mov rcx,r12
 mov rdx,QWORD PTR [rsi+56]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz vtb_fail
 mov QWORD PTR [rdi+8],rax
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+144]
 cmp DWORD PTR [rbx],0
 jne vtb_fail
 ; main ThreadGroup uses the original VM/package constructor, including
 ; synchronizedAddStrong; no manually fabricated group hierarchy.
 mov rcx,r12
 mov rdx,QWORD PTR [rsi+56]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz vtb_fail
 mov QWORD PTR [rdi+16],rax
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [rdi+8]
 mov QWORD PTR [rsp+40],rax
 mov rax,QWORD PTR [rdi+32]
 mov QWORD PTR [rsp+48],rax
 mov QWORD PTR [rsp+56],10
 mov QWORD PTR [rsp+64],0
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+152]
 cmp DWORD PTR [rbx],0
 jne vtb_fail
 ; Explicit authorized bootstrap ACC from the original ([PD;Z)V ctor.
 mov rcx,r12
 mov rdx,QWORD PTR [rsi+64]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz vtb_fail
 mov QWORD PTR [rdi+24],rax
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],0
 mov QWORD PTR [rsp+48],1
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+160]
 cmp DWORD PTR [rbx],0
 jne vtb_fail
 mov rcx,r12
 mov edx,DWORD PTR [rsi+12]
 call boom_threads_create
 test rax,rax
 jz vtb_fail
 mov r14,rax
 mov rcx,rax
 mov rdx,QWORD PTR [rsi+40]
 call boom_thread_native_bind
 test eax,eax
 jnz vtb_fail
 mov rcx,r12
 mov rdx,QWORD PTR [rsi+48]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz vtb_fail
 mov r13,rax
 mov QWORD PTR [rdi],rax
 mov rcx,r14
 mov rdx,rax
 mov r8d,1
 call boom_threads_attach
 test rax,rax
 jz vtb_fail
 mov r15d,1
 mov ecx,DWORD PTR [rsi+132]
 mov QWORD PTR [r13+rcx],rax
 ; currentThread()==this now selects the original attaching branch. The
 ; untouched bytecode assigns tid=1 while VM.initLevel()<1.
 mov QWORD PTR [rsp+32],r13
 mov rax,QWORD PTR [rdi+16]
 mov QWORD PTR [rsp+40],rax
 mov rax,QWORD PTR [rdi+32]
 mov QWORD PTR [rsp+48],rax
 mov QWORD PTR [rsp+56],0
 mov QWORD PTR [rsp+64],0
 mov QWORD PTR [rsp+72],0
 mov rax,QWORD PTR [rdi+24]
 mov QWORD PTR [rsp+80],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+168]
 cmp DWORD PTR [rbx],0
 jne vtb_fail
 mov ecx,DWORD PTR [rsi+176]
 cmp QWORD PTR [r13+rcx],1
 jne vtb_fail
 mov ecx,DWORD PTR [rsi+136]
 mov rax,QWORD PTR [r13+rcx]
 test rax,rax
 jz vtb_fail
 ; VM publication after Java construction: JVMTI RUNNABLE=4.
 mov ecx,DWORD PTR [rsi+140]
 mov DWORD PTR [rax+rcx],4
 mov DWORD PTR [rsi+8],2
 mov rax,r13
 jmp vtb_done
vtb_fail:
 cmp DWORD PTR [rbx],0
 jne vtb_cleanup
 mov DWORD PTR [rbx],7
vtb_cleanup:
 test r15d,r15d
 jz vtb_unbind
 mov rcx,r14
 call boom_threads_detach
 mov ecx,DWORD PTR [rsi+132]
 mov QWORD PTR [r13+rcx],0
vtb_unbind:
 test r14,r14
 jz vtb_failed_state
 xor ecx,ecx
 mov rdx,QWORD PTR [rsi+40]
 call boom_thread_native_bind
 mov rcx,r14
 call boom_threads_destroy
vtb_failed_state:
 mov DWORD PTR [rsi+8],-1
 jmp vtb_zero
vtb_bad:
 mov DWORD PTR [rbx],7
vtb_zero:
 xor eax,eax
vtb_done:
 add rsp,128
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_vm_thread_bootstrap ENDP
END
