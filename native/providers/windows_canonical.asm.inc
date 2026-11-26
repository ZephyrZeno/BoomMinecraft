; Original WinNTFileSystem canonicalize0/getDriveDirectory source bindings.
; Context32/argv, independent read-only PROP112/2 String factory pool.
; op0 argv {WinNTFileSystem,String}, op1 {WinNTFileSystem,signed drive}.
; Native output allocation is private to this call, always released before return.
.const
wcan_bad_pathname WORD 66,97,100,32,112,97,116,104,110,97,109,101
.data
ALIGN 8
PUBLIC boom_windows_canonical_owned_buffers
boom_windows_canonical_owned_buffers QWORD 0
.code
PUBLIC boom_provider_windows_canonical_service
boom_provider_windows_canonical_service PROC FRAME
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
 mov rsi,r8
 mov r12,rdx
 mov r15d,r9d
 xor edi,edi
 mov QWORD PTR [rsp+104],0
 test rbx,rbx
 jz wcan_zero
 cmp DWORD PTR [rbx],0
 jne wcan_zero
 cmp r15d,1
 ja wcan_bad
 test rsi,rsi
 jz wcan_bad
 cmp DWORD PTR [rsi],050524F50h
 jne wcan_bad
 cmp DWORD PTR [rsi+4],2
 jne wcan_bad
 test r12,r12
 jz wcan_bad
 mov rdx,QWORD PTR [r12]
 test rdx,rdx
 jz wcan_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 call boom_heap_contains
 test eax,eax
 jz wcan_bad
 mov rcx,QWORD PTR [r12]
 lea rdx,WCAN_FS_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz wcan_zero
 test r15d,r15d
 jnz wcan_allocate
 mov r13,QWORD PTR [r12+8]
 test r13,r13
 jz wcan_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r13
 call boom_heap_contains
 test eax,eax
 jz wcan_bad
 mov rcx,r13
 lea rdx,WCAN_STRING_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz wcan_zero
 mov QWORD PTR [rsp+72],r13
 mov rcx,rbx
 lea rdx,[rsp+72]
 call WCAN_LENGTH
 cmp DWORD PTR [rbx],0
 jne wcan_zero
 mov r13d,eax
 test eax,eax
 js wcan_bad
 mov rcx,rbx
 lea rdx,[rsp+72]
 call WCAN_CHARS
 cmp DWORD PTR [rbx],0
 jne wcan_zero
 mov r12,rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r12
 call boom_heap_contains
 test eax,eax
 jz wcan_bad
 cmp QWORD PTR [r12-8],261
 jne wcan_bad
 cmp DWORD PTR [r12-20],0
 jne wcan_bad
 mov eax,r13d
 shl rax,1
 cmp QWORD PTR [r12-16],rax
 jne wcan_bad
wcan_allocate:
 call GetProcessHeap
 test rax,rax
 jz wcan_oom
 mov r14,rax
 mov rcx,rax
 xor edx,edx
 mov r8d,65536
 call HeapAlloc
 test rax,rax
 jz wcan_oom
 mov rdi,rax
 lock inc QWORD PTR [boom_windows_canonical_owned_buffers]
 mov DWORD PTR [rsp+64],0
 test r15d,r15d
 jnz wcan_drive
 mov rcx,r12
 mov edx,r13d
 mov r8,rdi
 mov r9d,32768
 lea rax,[rsp+64]
 mov QWORD PTR [rsp+32],rax
 call boom_windows_canonical_path
 jmp wcan_primitive_done
wcan_drive:
 mov ecx,DWORD PTR [r12+8]
 mov rdx,rdi
 mov r8d,32768
 lea r9,[rsp+64]
 call boom_windows_drive_directory
wcan_primitive_done:
 test eax,eax
 jz wcan_publish
 cmp eax,8
 je wcan_oom
 test r15d,r15d
 jnz wcan_zero
 cmp eax,-1
 je wcan_default_message
 mov r8d,eax
 mov ecx,01200h
 xor edx,edx
 xor r9d,r9d
 mov QWORD PTR [rsp+32],rdi
 mov DWORD PTR [rsp+40],256
 mov QWORD PTR [rsp+48],0
 call FormatMessageW
 cmp eax,256
 jae wcan_bad
 cmp eax,3
 jbe wcan_system_message
 cmp WORD PTR [rdi+rax*2-2],10
 jne wcan_trim_CR
 dec eax
wcan_trim_CR:
 cmp WORD PTR [rdi+rax*2-2],13
 jne wcan_trim_period
 dec eax
wcan_trim_period:
 cmp WORD PTR [rdi+rax*2-2],46
 jne wcan_system_message
 dec eax
wcan_system_message:
 mov r8,rdi
 mov r9d,eax
 jmp wcan_throw
wcan_default_message:
 lea r8,wcan_bad_pathname
 mov r9d,12
wcan_throw:
 mov rcx,rbx
 mov rdx,rsi
 call boom_java_property_copy
 test rax,rax
 jz wcan_zero
 mov QWORD PTR [rsp+88],rax
 lea rcx,WCAN_ERROR_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne wcan_zero
 mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,WCAN_ERROR_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz wcan_zero
 mov QWORD PTR [rsp+80],rax
 mov rcx,rbx
 lea rdx,[rsp+80]
 call WCAN_ERROR_CTOR
 cmp DWORD PTR [rbx],0
 jne wcan_zero
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+80]
 lea r8,boom_runtime_type_map
 lea r9,WCAN_THROWABLE_TYPE
 call boom_exception_set32
 jmp wcan_zero
wcan_publish:
 mov r9d,DWORD PTR [rsp+64]
 cmp r9d,32768
 jae wcan_bad
 cmp WORD PTR [rdi+r9*2],0
 jne wcan_bad
 mov rcx,rbx
 mov rdx,rsi
 mov r8,rdi
 call boom_java_property_copy
 mov QWORD PTR [rsp+104],rax
 jmp wcan_done
wcan_null:
 mov DWORD PTR [rbx],4
 jmp wcan_zero
wcan_bad:
 mov DWORD PTR [rbx],7
 jmp wcan_zero
wcan_oom:
 mov DWORD PTR [rbx],3
wcan_zero:
 mov QWORD PTR [rsp+104],0
wcan_done:
 test rdi,rdi
 jz wcan_return
 mov rcx,r14
 xor edx,edx
 mov r8,rdi
 call HeapFree
 test eax,eax
 jz wcan_release_failed
 lock dec QWORD PTR [boom_windows_canonical_owned_buffers]
 jmp wcan_return
wcan_release_failed:
 cmp DWORD PTR [rbx],0
 jne wcan_return
 mov DWORD PTR [rbx],20
 mov QWORD PTR [rsp+104],0
wcan_return:
 mov rax,QWORD PTR [rsp+104]
 add rsp,128
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_windows_canonical_service ENDP
