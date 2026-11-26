; TPRP80/1: heapCell8,runtimeMap16,registryCell24,ThreadType32,VirtualType40,
; normal holder/priority field functions48/56,startApplications64,reserved72.
EXTERN boom_heap_contains:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_threads_current:PROC
EXTERN boom_threads_set_priority:PROC
PUBLIC boom_provider_thread_priority_service
PUBLIC boom_provider_thread_priority_start
.code
; (Context32,source oop,pool)->valid platform Thread boolean.
tp_object PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 test rdi,rdi
 jz tp_object_bad
 cmp DWORD PTR [rdi],050525054h
 jne tp_object_bad
 cmp DWORD PTR [rdi+4],1
 jne tp_object_bad
 cmp QWORD PTR [rdi+72],0
 jne tp_object_bad
 mov eax,8
tp_object_pointer:
 cmp QWORD PTR [rdi+rax],0
 je tp_object_bad
 add eax,8
 cmp eax,64
 jb tp_object_pointer
 test rsi,rsi
 jz tp_object_null
 mov rcx,QWORD PTR [rdi+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz tp_object_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [rdi+16]
 mov r8,rbx
 call boom_runtime_type
 cmp DWORD PTR [rbx],0
 jne tp_object_zero
 mov r12,rax
 mov rcx,rax
 mov rdx,QWORD PTR [rdi+32]
 call boom_type_assignable
 test eax,eax
 jz tp_object_bad
 mov rcx,r12
 mov rdx,QWORD PTR [rdi+40]
 call boom_type_assignable
 test eax,eax
 jnz tp_object_virtual
 mov eax,1
 jmp tp_object_done
tp_object_virtual:
 mov DWORD PTR [rbx],20
 jmp tp_object_zero
tp_object_null:
 mov DWORD PTR [rbx],1
 jmp tp_object_zero
tp_object_bad:
 mov DWORD PTR [rbx],7
tp_object_zero:
 xor eax,eax
tp_object_done:
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
tp_object ENDP

; Source Java has already stored holder.priority. This changes OS scheduling.
boom_provider_thread_priority_service PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 test rbx,rbx
 jz tp_service_zero
 cmp DWORD PTR [rbx],0
 jne tp_service_zero
 test r9d,r9d
 jnz tp_service_bad
 test rsi,rsi
 jz tp_service_bad
 mov r12d,DWORD PTR [rsi+8]
 lea eax,[r12-1]
 cmp eax,9
 ja tp_service_bad
 mov rdx,QWORD PTR [rsi]
 call tp_object
 test eax,eax
 jz tp_service_zero
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rsi]
 mov r8d,r12d
 call boom_threads_set_priority
 test eax,eax
 jz tp_service_zero
tp_service_bad:
 mov DWORD PTR [rbx],7
tp_service_zero:
 xor eax,eax
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_thread_priority_service ENDP

; (Context32,source Thread). Called on the attached worker before Java run.
boom_provider_thread_priority_start PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 lea rdi,boom_provider_thread_priority_pool
 test rbx,rbx
 jz tp_start_done
 cmp DWORD PTR [rbx],0
 jne tp_start_done
 mov r8,rdi
 call tp_object
 test eax,eax
 jz tp_start_done
 mov rcx,QWORD PTR [rdi+24]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_current
 cmp rax,rsi
 jne tp_start_bad
 mov rcx,rsi
 mov rdx,rbx
 call QWORD PTR [rdi+48]
 test rax,rax
 jz tp_start_done
 mov rcx,QWORD PTR [rax]
 test rcx,rcx
 jz tp_start_bad
 mov rdx,rbx
 call QWORD PTR [rdi+56]
 test rax,rax
 jz tp_start_done
 movsxd rax,DWORD PTR [rax]
 mov QWORD PTR [rsp+32],rsi
 mov QWORD PTR [rsp+40],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 mov r8,rdi
 xor r9d,r9d
 call boom_provider_thread_priority_service
 cmp DWORD PTR [rbx],0
 jne tp_start_done
 lock inc QWORD PTR [rdi+64]
 jmp tp_start_done
tp_start_bad:
 mov DWORD PTR [rbx],7
tp_start_done:
 xor eax,eax
 add rsp,64
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_thread_priority_start ENDP
