; One private BootLoader native. Its caller is original BootLoader.<clinit>.
; R8 is the image's normal JCLS/1 pool. The appended module root belongs to
; its ordinary contiguous GC span. The Java static and this slot hold one oop.
EXTERN GetCurrentThreadId:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_object_check:PROC
EXTERN boom_java_class_bind_module:PROC
PUBLIC boom_boot_unnamed_normal
.code
boom_boot_unnamed_normal PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rdi,r8
 test rbx,rbx
 jz bun_done
 cmp DWORD PTR [rbx],0
 jne bun_done
 test rdx,rdx
 jz bun_bad
 test r9d,r9d
 jnz bun_bad
 mov rsi,QWORD PTR [rdx]
 test rsi,rsi
 jz bun_null
 lea rax,boom_java_class_pool
 cmp rdi,rax
 jne bun_bad
 cmp DWORD PTR [rdi],04A434C53h
 jne bun_bad
 cmp DWORD PTR [rdi+4],1
 jne bun_bad
 cmp DWORD PTR [rdi+88],BUN_MODULES
 jne bun_bad
 mov rax,QWORD PTR [rdi+128]
 test rax,rax
 jz bun_bad
 cmp DWORD PTR [rax+BUN_SLOT*4],0
 jne bun_bad
 mov rax,QWORD PTR [rdi+48]
 lea rcx,boom_heap_ptr
 cmp rax,rcx
 jne bun_bad
 cmp QWORD PTR [BUN_STATIC],rsi
 jne bun_bad
 lea rax,BUN_OWNER
 cmp DWORD PTR [rax],0434C4153h
 jne bun_bad
 cmp DWORD PTR [rax+4],2
 jne bun_bad
 cmp DWORD PTR [rax+8],1
 je bun_initializer
 cmp DWORD PTR [rax+8],2
 jne bun_bad
 ; Completed initialization permits re-checking the published identity only.
 mov rax,QWORD PTR [rdi+64]
 test rax,rax
 jz bun_bad
 cmp QWORD PTR [rax+BUN_SLOT*8],rsi
 jne bun_bad
 jmp bun_object
bun_initializer:
 call GetCurrentThreadId
 lea rcx,BUN_OWNER
 cmp DWORD PTR [rcx+12],eax
 jne bun_bad
bun_object:
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz bun_bad
 mov rcx,rsi
 lea rdx,BUN_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz bun_done
 cmp QWORD PTR [rsi+BUN_LAYER],0
 jne bun_bad
 cmp QWORD PTR [rsi+BUN_NAME],0
 jne bun_bad
 cmp QWORD PTR [rsi+BUN_LOADER],0
 jne bun_bad
 cmp QWORD PTR [rsi+BUN_DESCRIPTOR],0
 jne bun_bad
 cmp BYTE PTR [rsi+BUN_ENABLE],1
 jne bun_bad
 mov rcx,rdi
 mov edx,BUN_SLOT
 mov r8,rsi
 mov r9,rbx
 call boom_java_class_bind_module
 jmp bun_done
bun_null:
 mov DWORD PTR [rbx],4
 jmp bun_done
bun_bad:
 mov DWORD PTR [rbx],7
bun_done:
 xor eax,eax
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_boot_unnamed_normal ENDP
