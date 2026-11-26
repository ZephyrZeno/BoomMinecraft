; Windows System.mapLibraryName. The original API counts UTF-16 code units,
; including embedded NULs. The shared source-layout factory returns a new String.
.const
ALIGN 2
mln_too_long WORD 110,97,109,101,32,116,111,111,32,108,111,110,103
.code
PUBLIC boom_provider_library_name_service
boom_provider_library_name_service PROC FRAME
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
 jz mln_zero
 cmp DWORD PTR [rbx],0
 jne mln_zero
 test r9d,r9d
 jnz mln_bad
 test r12,r12
 jz mln_bad
 cmp DWORD PTR [r12],050524F50h
 jne mln_bad
 cmp DWORD PTR [r12+4],2
 jne mln_bad
 test rdx,rdx
 jz mln_bad
 mov rdi,QWORD PTR [rdx]
 test rdi,rdi
 jz mln_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz mln_bad
 mov rcx,rdi
 lea rdx,MLN_STRING_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz mln_zero
 mov QWORD PTR [rsp+32],rdi
 mov rcx,rbx
 lea rdx,[rsp+32]
 call MLN_LENGTH
 cmp DWORD PTR [rbx],0
 jne mln_zero
 mov esi,eax
 cmp esi,240
 ja mln_long
 mov rcx,rbx
 lea rdx,[rsp+32]
 call MLN_CHARS
 cmp DWORD PTR [rbx],0
 jne mln_zero
 mov rdi,rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz mln_bad
 cmp QWORD PTR [rdi-8],261
 jne mln_bad
 cmp DWORD PTR [rdi-20],0
 jne mln_bad
 lea rax,[rsi*2]
 cmp QWORD PTR [rdi-16],rax
 jne mln_bad
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
 jmp mln_done
mln_long:
 lea rcx,MLN_ERROR_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne mln_zero
 mov rcx,rbx
 mov rdx,r12
 lea r8,mln_too_long
 mov r9d,13
 call boom_java_property_copy
 test rax,rax
 jz mln_zero
 mov QWORD PTR [rsp+40],rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,MLN_ERROR_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz mln_zero
 mov rdi,rax
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call MLN_ERROR_CTOR
 cmp DWORD PTR [rbx],0
 jne mln_zero
 mov rcx,rbx
 mov rdx,rdi
 lea r8,boom_runtime_type_map
 lea r9,MLN_THROWABLE_TYPE
 call boom_exception_set32
 jmp mln_zero
mln_null:
 mov DWORD PTR [rbx],4
 jmp mln_zero
mln_bad:
 mov DWORD PTR [rbx],7
mln_zero:
 xor eax,eax
mln_done:
 add rsp,552
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_library_name_service ENDP
