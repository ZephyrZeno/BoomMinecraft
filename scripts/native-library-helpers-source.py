# Pure ASM templates copied unchanged from the executed lifecycle candidate.

def words(label,text):
    return label+' WORD '+','.join(str(ord(c)) for c in text)+'\n'

def helpers():
    null='NULL filename for native library'
    prefix,postfix='unsupported JNI version 0x',' required by '
    text='.const\n'+words('lib_name_net','net')+words('lib_name_nio','nio')
    text+=words('lib_null_filename',null)+words('lib_version_prefix',prefix)+words('lib_version_postfix',postfix)
    text+=words('lib_hex_digits','0123456789ABCDEF')+words('lib_prefer_v4','java.net.preferIPv4Stack')
    text+='''ALIGN 8
lib_error_rows QWORD OFFSET NLL_INTERNAL_CLASS,OFFSET NLL_INTERNAL_LAYOUT,OFFSET NLL_INTERNAL_CTOR
 QWORD OFFSET NLL_UNSAT_CLASS,OFFSET NLL_UNSAT_LAYOUT,OFFSET NLL_UNSAT_CTOR
.code
lib_new_module_name PROC PRIVATE
 mov r9d,3
 cmp r8d,1
 lea r8,lib_name_net
 je lib_module_name_ready
 lea r8,lib_name_nio
lib_module_name_ready:
 lea rdx,boom_java_platform_properties_pool
 jmp boom_java_property_copy
lib_new_module_name ENDP
lib_throw PROC PRIVATE FRAME
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
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov r13d,r8d
 imul r9d,r9d,24
 lea rsi,lib_error_rows
 add rsi,r9
 mov rcx,QWORD PTR [rsi]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne lib_throw_done
 mov rcx,rbx
 lea rdx,boom_java_platform_properties_pool
 mov r8,r12
 mov r9d,r13d
 call boom_java_property_copy
 test rax,rax
 jz lib_throw_done
 mov QWORD PTR [rsp+40],rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,QWORD PTR [rsi+8]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz lib_throw_done
 mov rdi,rax
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+16]
 cmp DWORD PTR [rbx],0
 jne lib_throw_done
 mov rcx,rbx
 mov rdx,rdi
 lea r8,boom_runtime_type_map
 lea r9,NLL_THROWABLE_TYPE
 call boom_exception_set32
lib_throw_done:
 add rsp,48
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
lib_throw ENDP
lib_raise_null_filename PROC PRIVATE
 lea rdx,lib_null_filename
 mov r8d,NLL_NULL_LENGTH
 xor r9d,r9d
 jmp lib_throw
lib_raise_null_filename ENDP
lib_raise_bad_version PROC PRIVATE FRAME
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
 sub rsp,192
 .allocstack 192
 .endprolog
 mov rbx,rcx
 mov r12d,edx
 mov r13d,r8d
 lea rdi,[rsp+32]
 lea rsi,lib_version_prefix
 mov ecx,NLL_PREFIX_LENGTH
 rep movsw
 mov ecx,8
 lea rsi,lib_hex_digits
lib_version_digit:
 rol r12d,4
 mov eax,r12d
 and eax,15
 mov ax,WORD PTR [rsi+rax*2]
 mov WORD PTR [rdi],ax
 add rdi,2
 dec ecx
 jnz lib_version_digit
 lea rsi,lib_version_postfix
 mov ecx,NLL_POSTFIX_LENGTH
 rep movsw
 lea rsi,lib_name_net
 cmp r13d,1
 je lib_version_name
 lea rsi,lib_name_nio
lib_version_name:
 mov ecx,3
 rep movsw
 mov rcx,rbx
 lea rdx,[rsp+32]
 mov r8d,NLL_VERSION_MESSAGE_LENGTH
 mov r9d,1
 call lib_throw
 add rsp,192
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
lib_raise_bad_version ENDP
lib_net_body PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,56
 .allocstack 56
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 lea rdx,boom_builtin_module_pool
 mov r8d,00010002h
 call boom_builtin_module_check
 test eax,eax
 jnz lib_net_unavailable
 cmp QWORD PTR [NLL_SYSTEM_PROPS],0
 je lib_net_unavailable
 mov rcx,rbx
 lea rdx,boom_java_platform_properties_pool
 lea r8,lib_prefer_v4
 mov r9d,NLL_PREFER_LENGTH
 call boom_java_property_copy
 test rax,rax
 jz lib_net_failed
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 lock inc QWORD PTR [boom_native_library_property_reads]
 call NLL_BOOLEAN_GET
 cmp DWORD PTR [rbx],0
 jne lib_net_failed
 cmp eax,1
 ja lib_net_unavailable
 mov edx,eax
 mov rcx,QWORD PTR [rsi+48]
 call boom_builtin_net_platform_start
 test eax,eax
 jnz lib_net_unavailable
 mov eax,00010002h
 jmp lib_net_done
lib_net_unavailable:
 cmp DWORD PTR [rbx],0
 jne lib_net_failed
 mov DWORD PTR [rbx],20
lib_net_failed:
 mov eax,-3
lib_net_done:
 add rsp,56
 pop rsi
 pop rbx
 ret
lib_net_body ENDP
lib_net_on_load PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 call lib_net_body
 cmp DWORD PTR [rbx],0
 jne lib_net_zero
 cmp eax,00010002h
 jne lib_net_zero
 mov eax,00010008h
 jmp lib_net_load_done
lib_net_zero:
 xor eax,eax
lib_net_load_done:
 add rsp,32
 pop rbx
 ret
lib_net_on_load ENDP
lib_net_close PROC PRIVATE
 mov rcx,QWORD PTR [rdx+48]
 jmp boom_builtin_net_platform_close
lib_net_close ENDP
lib_nio_on_load PROC PRIVATE
 lea rdx,boom_builtin_module_pool
 jmp boom_builtin_nio_on_load
lib_nio_on_load ENDP
lib_nio_close PROC PRIVATE
 xor eax,eax
 ret
lib_nio_close ENDP
'''
    values={'NLL_NULL_LENGTH':len(null),'NLL_PREFIX_LENGTH':len(prefix),'NLL_POSTFIX_LENGTH':len(postfix),
            'NLL_VERSION_MESSAGE_LENGTH':len(prefix)+8+len(postfix)+3,'NLL_PREFER_LENGTH':len('java.net.preferIPv4Stack')}
    for key,value in values.items():
        text=text.replace(key,str(value))
    return text
