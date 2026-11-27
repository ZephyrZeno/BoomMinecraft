; OCLN96/1 normal Object.clone. Source-bound readonly callbacks; no Java state
; substitutions. Win64(Context32*,argv{actual oop},exact pool,operation0)->oop.
; Native locals require the existing explicit/quiescent GC discipline.
.code
PUBLIC boom_object_clone_service
boom_object_clone_service PROC FRAME
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
 sub rsp,160
 .allocstack 160
 .endprolog
 mov rbx,rcx
 mov r13,r8
 mov QWORD PTR [rsp+56],0
 test rbx,rbx
 jz ocl_done
 cmp DWORD PTR [rbx],0
 jne ocl_done
 cmp QWORD PTR [rbx+16],0
 jne ocl_done
 test rdx,rdx
 jz ocl_bad
 lea rax,boom_object_clone_pool
 cmp r13,rax
 jne ocl_bad
 test r9d,r9d
 jnz ocl_bad
 cmp DWORD PTR [r13],04E4C434Fh
 jne ocl_bad
 cmp DWORD PTR [r13+4],1
 jne ocl_bad
 cmp DWORD PTR [r13+8],96
 jne ocl_bad
 cmp DWORD PTR [r13+12],0
 jne ocl_bad
 cmp QWORD PTR [r13+88],0
 jne ocl_bad
 mov rsi,QWORD PTR [rdx]
 test rsi,rsi
 jz ocl_null
 mov rax,QWORD PTR [r13+16]
 test rax,rax
 jz ocl_bad
 mov r12,QWORD PTR [rax]
 test r12,r12
 jz ocl_bad
 cmp DWORD PTR [r12],048454150h
 jne ocl_bad
 cmp DWORD PTR [r12+4],1
 jne ocl_bad
 mov r10,QWORD PTR [r13+24]
 test r10,r10
 jz ocl_bad
 cmp DWORD PTR [r10],052545950h
 jne ocl_bad
 mov eax,DWORD PTR [r10+4]
 cmp eax,1
 je ocl_map_abi_ready
 cmp eax,2
 jne ocl_bad
ocl_map_abi_ready:
 mov eax,DWORD PTR [r10+12]
 dec eax
 cmp eax,0FFFFFh
 ja ocl_bad
 inc eax
 mov r11,QWORD PTR [r13+40]
 test r11,r11
 jz ocl_bad
 cmp DWORD PTR [r11],04A434C53h
 jne ocl_bad
 cmp DWORD PTR [r11+4],1
 jne ocl_bad
 cmp DWORD PTR [r11+12],eax
 jne ocl_bad
 mov rax,QWORD PTR [r13+16]
 cmp QWORD PTR [r11+48],rax
 jne ocl_bad
 mov rax,QWORD PTR [r13+32]
 test rax,rax
 jz ocl_bad
 cmp DWORD PTR [rax],054595045h
 jne ocl_bad
 cmp DWORD PTR [rax+4],1
 jne ocl_bad
 cmp DWORD PTR [rax+8],2
 jne ocl_bad
 test DWORD PTR [rax+12],2
 jz ocl_bad
 mov rcx,r12
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz ocl_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+24]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz ocl_done
 mov r14,rax
 cmp DWORD PTR [r14+20],2
 ja ocl_bad
 mov rcx,QWORD PTR [r14+8]
 mov rdx,QWORD PTR [r13+32]
 call boom_type_assignable
 test eax,eax
 jz ocl_not_cloneable
 ; The runtime row and domain guard validated the full source header, payload,
 ; reference prefix, and array length. Allocate a new block with the same tag.
 ; Header/identity/monitor/GC state is initialized by heap_alloc, never copied.
 mov r15,QWORD PTR [rsi-16]
 mov rcx,r12
 mov rdx,r15
 mov r8d,DWORD PTR [rsi-20]
 mov r9,QWORD PTR [rsi-8]
 call boom_heap_alloc
 test rax,rax
 jz ocl_oom
 mov QWORD PTR [rsp+56],rax
 mov rdi,rax
 mov rcx,r15
 shr rcx,3
 rep movsq
 test r15b,4
 jz ocl_copy_word
 mov eax,DWORD PTR [rsi]
 mov DWORD PTR [rdi],eax
 add rsi,4
 add rdi,4
ocl_copy_word:
 test r15b,2
 jz ocl_copy_byte
 mov ax,WORD PTR [rsi]
 mov WORD PTR [rdi],ax
 add rsi,2
 add rdi,2
ocl_copy_byte:
 test r15b,1
 jz ocl_done
 mov al,BYTE PTR [rsi]
 mov BYTE PTR [rdi],al
 jmp ocl_done
ocl_not_cloneable:
 ; All arrays are Cloneable. A malformed marker must never become a Java
 ; CloneNotSupportedException for an otherwise valid array.
 cmp DWORD PTR [r14+20],0
 jne ocl_bad
 cmp QWORD PTR [r13+48],0
 je ocl_bad
 cmp QWORD PTR [r13+56],0
 je ocl_bad
 cmp QWORD PTR [r13+64],0
 je ocl_bad
 cmp QWORD PTR [r13+72],0
 je ocl_bad
 cmp QWORD PTR [r13+80],0
 je ocl_bad
 ; A real normal Class mirror and the original Class.getName provide the
 ; original runtime class name used by CloneNotSupportedException(String).
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+40]
 mov r8d,DWORD PTR [r14+16]
 call boom_java_class_load
 cmp DWORD PTR [rbx],0
 jne ocl_done
 test rax,rax
 jz ocl_bad
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [r13+72]
 cmp DWORD PTR [rbx],0
 jne ocl_done
 test rax,rax
 jz ocl_bad
 mov QWORD PTR [rsp+80],rax
 mov rcx,QWORD PTR [r13+48]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz ocl_done
 mov rcx,r12
 mov rdx,QWORD PTR [r13+56]
 mov r8,rbx
 call boom_object_new
 cmp DWORD PTR [rbx],0
 jne ocl_done
 test rax,rax
 jz ocl_oom
 mov QWORD PTR [rsp+72],rax
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [rsp+40],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [r13+64]
 cmp DWORD PTR [rbx],0
 jne ocl_done
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+72]
 mov r8,QWORD PTR [r13+24]
 mov r9,QWORD PTR [r13+80]
 call boom_exception_set32
 jmp ocl_done
ocl_null:
 mov DWORD PTR [rbx],4
 jmp ocl_done
ocl_oom:
 mov DWORD PTR [rbx],3
 jmp ocl_done
ocl_bad:
 mov DWORD PTR [rbx],7
ocl_done:
 mov rax,QWORD PTR [rsp+56]
 add rsp,160
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_object_clone_service ENDP
