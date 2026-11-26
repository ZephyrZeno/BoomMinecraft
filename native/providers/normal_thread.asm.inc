; Normal-source Thread entry adapter. The registry and all operations are MASM.
; Declaration inventory is 20; six source natives are bound, not all Thread APIs.
PUBLIC boom_provider_thread_service
PUBLIC boom_provider_thread_bind
.const
provider_thread_operations DWORD -1,4,5,17,2,15
.code
boom_provider_thread_service PROC
 test rcx,rcx
 jz provider_thread_zero
 cmp DWORD PTR [rcx],0
 jne provider_thread_zero
 test r9d,r9d
 jz provider_thread_register
 cmp r9d,5
 ja provider_thread_bad
 lea r10,provider_thread_operations
 mov r9d,DWORD PTR [r10+r9*4]
 jmp boom_thread_native_dispatch
provider_thread_register:
 lea rdx,provider_thread_table+16
 lea r10,provider_thread_import_cells
 xor r9d,r9d
provider_thread_publish:
 mov r11,QWORD PTR [r10+r9*8]
 mov r11,QWORD PTR [r11]
 test r11,r11
 jz provider_thread_bad
 xor eax,eax
 lock cmpxchg QWORD PTR [rdx+16],r11
 test rax,rax
 jz provider_thread_next
 cmp rax,r11
 jne provider_thread_bad
provider_thread_next:
 add rdx,32
 inc r9d
 cmp r9d,18
 jb provider_thread_publish
 mov rdx,r8
 jmp boom_thread_native_register
provider_thread_bad:
 mov DWORD PTR [rcx],7
provider_thread_zero:
 xor eax,eax
 ret
boom_provider_thread_service ENDP
; bind(registry or NULL)->status; caller serializes the borrowed VM lifetime.
boom_provider_thread_bind PROC
 lea rdx,boom_provider_thread_pool
 jmp boom_thread_native_bind
boom_provider_thread_bind ENDP
