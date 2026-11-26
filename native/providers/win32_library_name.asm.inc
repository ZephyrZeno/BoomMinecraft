; Windows System.mapLibraryName. The original API counts UTF-16 code units,
; including embedded NULs. The shared source-layout factory returns a new String.
.const
ALIGN 2
map_name_too_long WORD 110,97,109,101,32,116,111,111,32,108,111,110,103
.code
PUBLIC boom_win32_library_name
boom_win32_library_name PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,552
 .allocstack 552
 .endprolog
 mov rbx,rcx
 mov r12,r8
 test rbx,rbx
 jz map_name_zero
 cmp DWORD PTR [rbx],0
 jne map_name_zero
 test r9d,r9d
 jnz map_name_bad
 test r12,r12
 jz map_name_bad
 cmp DWORD PTR [r12],050524F50h
 jne map_name_bad
 cmp DWORD PTR [r12+4],2
 jne map_name_bad
 test rdx,rdx
 jz map_name_bad
 mov rdi,QWORD PTR [rdx]
 test rdi,rdi
 jz map_name_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz map_name_bad
 mov rcx,rdi
 lea rdx,LIB_NAME_STRING_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz map_name_zero
 mov QWORD PTR [rsp+32],rdi
 mov rcx,rbx
 lea rdx,[rsp+32]
 call LIB_NAME_LENGTH
 cmp DWORD PTR [rbx],0
 jne map_name_zero
 mov esi,eax
 cmp esi,240
 ja map_name_long
 mov rcx,rbx
 lea rdx,[rsp+32]
 call LIB_NAME_CHARS
 cmp DWORD PTR [rbx],0
 jne map_name_zero
 mov rdi,rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz map_name_bad
 cmp QWORD PTR [rdi-8],261
 jne map_name_bad
 cmp DWORD PTR [rdi-20],0
 jne map_name_bad
 lea rax,[rsi*2]
 cmp QWORD PTR [rdi-16],rax
 jne map_name_bad
 mov r9d,esi
 add r9d,4
 mov ecx,esi
 mov rsi,rdi
 lea rdi,[rsp+48]
 rep movsw
 mov DWORD PTR [rdi],0064002Eh
 mov DWORD PTR [rdi+4],006C006Ch
 mov rcx,rbx
 mov rdx,r12
 lea r8,[rsp+48]
 call boom_java_property_copy
 jmp map_name_done
map_name_long:
 lea rcx,LIB_NAME_ERROR_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne map_name_zero
 mov rcx,rbx
 mov rdx,r12
 lea r8,map_name_too_long
 mov r9d,13
 call boom_java_property_copy
 test rax,rax
 jz map_name_zero
 mov QWORD PTR [rsp+40],rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,LIB_NAME_ERROR_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz map_name_zero
 mov rdi,rax
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call LIB_NAME_ERROR_CTOR
 cmp DWORD PTR [rbx],0
 jne map_name_zero
 mov rcx,rbx
 mov rdx,rdi
 lea r8,boom_runtime_type_map
 lea r9,LIB_NAME_THROWABLE_TYPE
 call boom_exception_set32
 jmp map_name_zero
map_name_null:
 mov DWORD PTR [rbx],4
 jmp map_name_zero
map_name_bad:
 mov DWORD PTR [rbx],7
map_name_zero:
 xor eax,eax
map_name_done:
 add rsp,552
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_win32_library_name ENDP
