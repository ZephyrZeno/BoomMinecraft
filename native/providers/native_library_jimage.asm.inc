; An additional restricted self module. The original net/nio service remains
; byte-for-byte in this object; no external JDK DLL/JNI address is resolved.
.code
PUBLIC boom_native_library_with_jimage_service

; Exact source String classifier. R8D=6 basename or10 mapped name. This reads
; the normal FMAP value/coder and real byte[] without an extra Java allocation.
; Embedded NUL terminates this platform name, as in the original library API.
jlib_source_name PROC PRIVATE FRAME
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
 mov r12d,r8d
 test rsi,rsi
 jz jls_no
 mov rcx,QWORD PTR [boom_heap_ptr]
 call boom_heap_contains
 test eax,eax
 jz jls_bad
 mov rcx,rsi
 lea rdx,NLL_STRING_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jls_no
 movzx edi,BYTE PTR [rsi+JLIB_STRING_CODER]
 cmp edi,1
 ja jls_bad
 mov rsi,QWORD PTR [rsi+JLIB_STRING_VALUE]
 test rsi,rsi
 jz jls_bad
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz jls_bad
 cmp QWORD PTR [rsi-8],264
 jne jls_bad
 cmp DWORD PTR [rsi-20],0
 jne jls_bad
 mov rax,QWORD PTR [rsi-16]
 test edi,edi
 jz jls_units
 test al,1
 jnz jls_bad
 shr rax,1
jls_units:
 cmp rax,r12
 jb jls_no
 mov QWORD PTR [rsp+32],rax
 xor ecx,ecx
 lea r10,jlib_name
jls_next:
 cmp ecx,r12d
 jae jls_suffix
 test edi,edi
 jnz jls_utf16
 movzx edx,BYTE PTR [rsi+rcx]
 jmp jls_compare
jls_utf16:
 movzx edx,WORD PTR [rsi+rcx*2]
jls_compare:
 cmp edx,127
 ja jls_unsupported
 test edx,edx
 jz jls_no
 cmp ecx,6
 jae jls_matched_unit
 cmp dx,WORD PTR [r10+rcx*2]
 jne jls_no
jls_matched_unit:
 inc ecx
 jmp jls_next
jls_suffix:
 cmp rcx,QWORD PTR [rsp+32]
 je jls_yes
 test edi,edi
 jnz jls_NUL16
 cmp BYTE PTR [rsi+rcx],0
 je jls_yes
 jmp jls_no
jls_NUL16:
 cmp WORD PTR [rsi+rcx*2],0
 jne jls_no
jls_yes:
 mov eax,1
 jmp jls_return
jls_bad:
 mov DWORD PTR [rbx],7
 jmp jls_no
jls_unsupported:
 mov DWORD PTR [rbx],20
jls_no:
 xor eax,eax
jls_return:
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
jlib_source_name ENDP

jlib_new_module_name PROC PRIVATE
 lea rdx,boom_java_platform_properties_pool
 lea r8,jlib_name
 mov r9d,6
 jmp boom_java_property_copy
jlib_new_module_name ENDP

jlib_raise_bad_version PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,200
 .allocstack 200
 .endprolog
 mov rbx,rcx
 mov r12d,edx
 lea rdi,[rsp+32]
 lea rsi,lib_version_prefix
 mov ecx,26
 rep movsw
 mov ecx,8
 lea rsi,lib_hex_digits
jlv_digit:
 rol r12d,4
 mov eax,r12d
 and eax,15
 mov ax,WORD PTR [rsi+rax*2]
 mov WORD PTR [rdi],ax
 add rdi,2
 dec ecx
 jnz jlv_digit
 lea rsi,lib_version_postfix
 mov ecx,13
 rep movsw
 lea rsi,jlib_name
 mov ecx,6
 rep movsw
 mov rcx,rbx
 lea rdx,[rsp+32]
 mov r8d,53
 mov r9d,1
 call lib_throw
 add rsp,200
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
jlib_raise_bad_version ENDP

; This is our restricted ASM module's actual internal readiness callback.
; It is not an original C jimage JNI_OnLoad and does not expose a JNI table.
jlib_on_load PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 lea rdx,boom_builtin_module_pool
 mov r8d,00010002h
 call boom_builtin_module_check
 test eax,eax
 jnz jlo_failure
 lea rcx,boom_provider_jimage_native_map_pool
 call boom_jimage_native_map_ready
 test eax,eax
 jnz jlo_failure
 mov eax,00010008h
 jmp jlo_return
jlo_failure:
 cmp DWORD PTR [rbx],0
 jne jlo_zero
 mov DWORD PTR [rbx],20
jlo_zero:
 xor eax,eax
jlo_return:
 add rsp,32
 pop rbx
 ret
jlib_on_load ENDP

; Module pin lifetime and VM-owned map/view lifetime are separate real owners.
jlib_on_close PROC PRIVATE
 xor eax,eax
 ret
jlib_on_close ENDP

; Four original source natives keep their ordinary frames/owner ensure. Only
; these adapter tail targets change. Unknown names retain the old net/nio stop.
boom_native_library_with_jimage_service PROC FRAME
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
 mov r12d,r9d
 test rbx,rbx
 jz jroute_zero
 cmp DWORD PTR [rbx],0
 jne jroute_zero
 test rsi,rsi
 jz jroute_original
 test rdi,rdi
 jz jroute_original
 cmp DWORD PTR [rdi],042494C4Eh
 jne jroute_original
 cmp DWORD PTR [rdi+4],1
 jne jroute_original
 cmp DWORD PTR [rdi+8],2
 jne jroute_original
 cmp DWORD PTR [rdi+12],64
 jne jroute_original
 cmp r12d,3
 ja jroute_original
 je jroute_entry
 mov rdx,QWORD PTR [rsi]
 mov r8d,6
 cmp r12d,1
 jne jroute_not_load
 mov rdx,QWORD PTR [rsi+8]
jroute_not_load:
 test r12d,r12d
 jnz jroute_name
 mov r8d,10
jroute_name:
 mov rcx,rbx
 call jlib_source_name
 cmp DWORD PTR [rbx],0
 jne jroute_zero
 test eax,eax
 jz jroute_original
 jmp jroute_jimage
jroute_entry:
 ; The self image HMODULE can also equal net/nio pins. All standard JNI
 ; entry requests are explicitly unsupported in both restricted services.
 mov rax,QWORD PTR [rsi]
 test rax,rax
 jz jroute_original
 lea rcx,boom_jimage_library_pool+24
 call AcquireSRWLockExclusive
 mov rax,QWORD PTR [rsi]
 cmp QWORD PTR [boom_jimage_library_module+16],rax
 sete BYTE PTR [rsp+32]
 lea rcx,boom_jimage_library_pool+24
 call ReleaseSRWLockExclusive
 cmp BYTE PTR [rsp+32],0
 je jroute_original
jroute_jimage:
 mov rcx,rbx
 mov rdx,rsi
 lea r8,boom_jimage_library_pool
 mov r9d,r12d
 call boom_jimage_native_library_service
 jmp jroute_return
jroute_original:
 mov rcx,rbx
 mov rdx,rsi
 mov r8,rdi
 mov r9d,r12d
 call boom_native_library_service
 jmp jroute_return
jroute_zero:
 xor eax,eax
jroute_return:
 add rsp,40
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_native_library_with_jimage_service ENDP
