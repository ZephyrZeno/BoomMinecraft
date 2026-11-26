; Original normal Java Module native graph. JMOD112/1, existing normal JCLS roots.
; No Module is allocated here. Java fields are read from their verified source
; layout. Only existing JCLS bind services publish the same original Java oop.
; Graph Row64: defined0,open4,reads8,versionLength16,locationLength20,
; readAllUnnamed24,specificUnnamedReadBits28,mutations32,readsHigh40,symbols48.
; PackageState32: all0,allUnnamed4,qualifiedLow8,unnamedBits16,qualifiedHigh24.
; At most 128 named/JCLS identities, plus graph-only unnamed IDs128..130.
.const
jmd_package_prefix WORD 80,97,99,107,97,103,101,32
jmd_package_missing WORD 32,110,111,116,32,102,111,117,110,100,32,105,110,32,102,114,111,109,95,109,111,100,117,108,101,32
jmd_package_missing_unnamed WORD 32,110,111,116,32,102,111,117,110,100,32,105,110,32,109,111,100,117,108,101,32
jmd_invalid_package_prefix WORD 73,110,118,97,108,105,100,32,112,97,99,107,97,103,101,32,110,97,109,101,58,32
jmd_invalid_package_suffix WORD 32,102,111,114,32,109,111,100,117,108,101,58,32
.code

; Source String -> checked byte storage/UTF16 count/coder. No allocations.
; RCX oop, RDX Context32 -> RAX storage, EDX units, R8D 0/1 shift.
jmd_view PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rdx
 mov rsi,rcx
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz jmd_view_bad
 lea rax,JMD_STRING_LAYOUT
 cmp QWORD PTR [rsi-8],rax
 jne jmd_view_bad
 mov rcx,rsi
 mov rdx,rax
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jmd_view_zero
 mov rdi,QWORD PTR [rsi+JMD_STRING_VALUE]
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz jmd_view_bad
 cmp QWORD PTR [rdi-8],264
 jne jmd_view_bad
 cmp DWORD PTR [rdi-20],0
 jne jmd_view_bad
 movzx r8d,BYTE PTR [rsi+JMD_STRING_CODER]
 cmp r8d,1
 ja jmd_view_bad
 mov rdx,QWORD PTR [rdi-16]
 cmp rdx,07FFFFFFFh
 ja jmd_view_bad
 test r8d,r8d
 jz jmd_view_value
 test dl,1
 jnz jmd_view_bad
 shr edx,1
jmd_view_value:
 mov rax,rdi
 jmp jmd_view_done
jmd_view_bad:
 mov DWORD PTR [rbx],7
jmd_view_zero:
 xor eax,eax
 xor edx,edx
 xor r8d,r8d
jmd_view_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
jmd_view ENDP

; Context RBX, source RCX, constant UTF16 RDX, count R8D, normalize '.' R9D.
jmd_match PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rsi,rdx
 mov edi,r8d
 mov r12d,r9d
 mov rdx,rbx
 call jmd_view
 test rax,rax
 jz jmd_match_no
 cmp edx,edi
 jne jmd_match_no
 mov r13d,r8d
 xor r10d,r10d
jmd_match_loop:
 cmp r10d,edi
 jae jmd_match_yes
 mov r11,r10
 mov ecx,r13d
 shl r11,cl
 movzx edx,BYTE PTR [rax+r11]
 test r13d,r13d
 jz jmd_match_normalize
 movzx edx,WORD PTR [rax+r11]
jmd_match_normalize:
 test r12d,r12d
 jz jmd_match_compare
 cmp edx,46
 jne jmd_match_compare
 mov edx,47
jmd_match_compare:
 cmp dx,WORD PTR [rsi+r10*2]
 jne jmd_match_no
 inc r10d
 jmp jmd_match_loop
jmd_match_yes:
 mov eax,1
 jmp jmd_match_done
jmd_match_no:
 xor eax,eax
jmd_match_done:
 add rsp,40
 pop r13
 pop r12
 pop rdi
 pop rsi
 ret
jmd_match ENDP

; Context RBX. RCX String, RDX destination, R8D capacity, R9D normalize dot.
; Returns units or -1; a declared capacity boundary is a real context20 gap.
jmd_copy PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rsi,rdx
 mov edi,r8d
 mov r12d,r9d
 mov rdx,rbx
 call jmd_view
 test rax,rax
 jz jmd_copy_failed
 cmp edx,edi
 ja jmd_copy_gap
 mov r13d,edx
 xor r10d,r10d
jmd_copy_loop:
 cmp r10d,r13d
 jae jmd_copy_value
 mov r11,r10
 mov ecx,r8d
 shl r11,cl
 movzx edx,BYTE PTR [rax+r11]
 test r8d,r8d
 jz jmd_copy_normalize
 movzx edx,WORD PTR [rax+r11]
jmd_copy_normalize:
 test r12d,r12d
 jz jmd_copy_store
 cmp edx,46
 jne jmd_copy_store
 mov edx,47
jmd_copy_store:
 mov WORD PTR [rsi+r10*2],dx
 inc r10d
 jmp jmd_copy_loop
jmd_copy_gap:
 mov DWORD PTR [rbx],20
jmd_copy_failed:
 mov eax,-1
 jmp jmd_copy_done
jmd_copy_value:
 mov eax,r13d
jmd_copy_done:
 add rsp,40
 pop r13
 pop r12
 pop rdi
 pop rsi
 ret
jmd_copy ENDP

; Context RBX/pool RSI; RCX loader -> 0 boot,1 platform,2 application,-1 gap.
; Null never touches ClassLoaders initialization. Non-null requires the actual
; original Java static publication; no constructor or state is synthesized.
jmd_loader PROC PRIVATE
 test rcx,rcx
 jz jmd_loader_boot
 mov rax,QWORD PTR [rsi+104]
 cmp DWORD PTR [rax+8],2
 jne jmd_loader_gap
 mov rax,QWORD PTR [rsi+88]
 cmp QWORD PTR [rax],rcx
 je jmd_loader_platform
 mov rax,QWORD PTR [rsi+96]
 cmp QWORD PTR [rax],rcx
 jne jmd_loader_gap
 mov eax,2
 ret
jmd_loader_platform:
 mov eax,1
 ret
jmd_loader_boot:
 xor eax,eax
 ret
jmd_loader_gap:
 mov DWORD PTR [rbx],20
 mov eax,-1
 ret
jmd_loader ENDP

; Context RBX/pool RSI, RCX normal nonnull Module -> graph ID or -1.
; 128..130 are loader-data identities for unnamed modules, not Java oops.
jmd_lookup PROC PRIVATE FRAME
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rdi,rcx
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz jmd_lookup_bad
 lea rax,JMD_MODULE_LAYOUT
 cmp QWORD PTR [rdi-8],rax
 jne jmd_lookup_wrong
 mov rcx,rdi
 mov rdx,rax
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jmd_lookup_no
jmd_lookup_named:
 xor r12d,r12d
jmd_lookup_loop:
 cmp r12d,JMD_COUNT
 jae jmd_lookup_loader_unnamed
 mov rax,r12
 shl rax,6
 add rax,QWORD PTR [rsi+24]
 cmp DWORD PTR [rax],1
 jne jmd_lookup_next
 mov rax,QWORD PTR [rsi+16]
 mov rax,QWORD PTR [rax+64]
 cmp QWORD PTR [rax+r12*8],rdi
 je jmd_lookup_value
jmd_lookup_next:
 inc r12d
 jmp jmd_lookup_loop
jmd_lookup_value:
 mov eax,r12d
 jmp jmd_lookup_done
jmd_lookup_loader_unnamed:
 ; HotSpot's injected ModuleEntry field is null until define. Its accessor
 ; falls back to this object's loader-data unnamed entry even for a named
 ; white-box Module; source Java isNamed alone cannot invent VM registration.
 mov rcx,QWORD PTR [rdi+JMD_MODULE_LOADER]
 call jmd_loader
 test eax,eax
 js jmd_lookup_no
 add eax,128
 jmp jmd_lookup_done
jmd_lookup_bad:
 mov DWORD PTR [rbx],7
jmd_lookup_no:
 mov eax,-1
 jmp jmd_lookup_done
jmd_lookup_wrong:
 mov eax,-2
jmd_lookup_done:
 add rsp,40
 pop r12
 pop rdi
 ret
jmd_lookup ENDP

; Context RBX/pool RSI, RCX source String, EDX module ID -> package index/-1.
jmd_package PROC PRIVATE FRAME
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rdi,rcx
 mov eax,edx
 shl rax,5
 add rax,QWORD PTR [rsi+32]
 mov r12d,DWORD PTR [rax+16]
 mov r13d,DWORD PTR [rax+20]
 add r13d,r12d
jmd_package_loop:
 cmp r12d,r13d
 jae jmd_package_no
 mov rax,r12
 shl rax,4
 add rax,QWORD PTR [rsi+40]
 mov rdx,QWORD PTR [rax]
 mov r8d,DWORD PTR [rax+8]
 mov r9d,1
 mov rcx,rdi
 call jmd_match
 cmp DWORD PTR [rbx],0
 jne jmd_package_no
 test eax,eax
 jnz jmd_package_value
 inc r12d
 jmp jmd_package_loop
jmd_package_value:
 mov eax,r12d
 jmp jmd_package_done
jmd_package_no:
 mov eax,-1
jmd_package_done:
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rdi
 ret
jmd_package ENDP

PUBLIC boom_provider_module_definitions_service
boom_provider_module_definitions_service PROC FRAME
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
 sub rsp,208
 .allocstack 208
 .endprolog
 mov rbx,rcx
 mov rsi,r8
 mov r12,rdx
 mov r13d,r9d
 xor edi,edi
 mov DWORD PTR [rsp+136],-1
 test rbx,rbx
 jz jmd_service_done
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 lea rax,boom_provider_module_definitions_pool
 cmp rsi,rax
 jne jmd_service_bad
 cmp DWORD PTR [rsi],0444F4D4Ah
 jne jmd_service_bad
 cmp DWORD PTR [rsi+4],1
 jne jmd_service_bad
 cmp DWORD PTR [rsi+52],JMD_COUNT
 jne jmd_service_bad
 mov rax,QWORD PTR [rsi+16]
 cmp DWORD PTR [rax],04A434C53h
 jne jmd_service_bad
 cmp DWORD PTR [rax+4],1
 jne jmd_service_bad
 cmp DWORD PTR [rax+88],JMD_COUNT
 jne jmd_service_bad
 cmp r13d,4
 ja jmd_service_bad
 test r12,r12
 jz jmd_service_bad
 cmp r13d,2
 jne jmd_service_first
 cmp QWORD PTR [r12+16],0
 je jmd_error_null_to
jmd_service_first:
 cmp r13d,2
 je jmd_service_package_first
 cmp r13d,3
 jne jmd_service_get_first
jmd_service_package_first:
 cmp QWORD PTR [r12+8],0
 je jmd_error_null_package
jmd_service_get_first:
 mov r14,QWORD PTR [r12]
 test r14,r14
 jnz jmd_service_module
 test r13d,r13d
 jz jmd_error_null_define
 cmp r13d,4
 je jmd_error_null_module
 jmp jmd_error_null_from
jmd_service_module:
 cmp r13d,4
 jne jmd_service_module_type
 cmp QWORD PTR [r12+8],0
 je jmd_error_null_package
jmd_service_module_type:
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz jmd_service_bad
 lea rax,JMD_MODULE_LAYOUT
 cmp QWORD PTR [r14-8],rax
 jne jmd_error_wrong_module
 mov rcx,r14
 mov rdx,rax
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jmd_service_done
 test r13d,r13d
 jz jmd_define
 cmp r13d,1
 je jmd_mutate_lookup
 cmp QWORD PTR [r12+8],0
 je jmd_error_null_package
jmd_mutate_lookup:
 mov rcx,r14
 call jmd_lookup
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 cmp eax,-2
 je jmd_error_wrong_module
 test eax,eax
 js jmd_error_unregistered_from
 mov r14d,eax
 mov r15d,-1
 cmp r13d,1
 je jmd_reads_target
 cmp r14d,128
 jae jmd_service_done
 mov rax,r14
 shl rax,6
 add rax,QWORD PTR [rsi+24]
 cmp DWORD PTR [rax+4],0
 jne jmd_service_done
 cmp r13d,2
 jne jmd_export_package
 mov rcx,QWORD PTR [r12+16]
 call jmd_lookup
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 cmp eax,-2
 je jmd_error_wrong_module
 test eax,eax
 js jmd_error_invalid_to
 mov r15d,eax
jmd_export_package:
 mov rcx,QWORD PTR [r12+8]
 mov edx,r14d
 call jmd_package
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 test eax,eax
 js jmd_error_missing_package
 mov DWORD PTR [rsp+128],eax
 lea rcx,[rsi+8]
 call AcquireSRWLockExclusive
 mov eax,DWORD PTR [rsp+128]
 shl rax,5
 lea rdx,boom_module_definitions_package_states
 add rdx,rax
 cmp r13d,3
 je jmd_export_all
 cmp r13d,4
 je jmd_export_unnamed
 cmp r14d,r15d
 je jmd_mutate_unlock
 cmp r15d,128
 jae jmd_export_specific_unnamed
 cmp r15d,64
 jae jmd_export_named_high
 bts QWORD PTR [rdx+8],r15
 jmp jmd_mutate_unlock
jmd_export_named_high:
 sub r15d,64
 bts QWORD PTR [rdx+24],r15
 jmp jmd_mutate_unlock
jmd_export_all:
 mov DWORD PTR [rdx],1
 jmp jmd_mutate_unlock
jmd_export_unnamed:
 mov DWORD PTR [rdx+4],1
 jmp jmd_mutate_unlock
jmd_export_specific_unnamed:
 sub r15d,128
 bts DWORD PTR [rdx+16],r15d
 jmp jmd_mutate_unlock
jmd_reads_target:
 mov rcx,QWORD PTR [r12+8]
 test rcx,rcx
 jz jmd_reads_ready
 call jmd_lookup
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 cmp eax,-2
 je jmd_error_wrong_module
 test eax,eax
 js jmd_error_invalid_to
 mov r15d,eax
jmd_reads_ready:
 cmp r14d,128
 jae jmd_service_done
 cmp r14d,r15d
 je jmd_service_done
 lea rcx,[rsi+8]
 call AcquireSRWLockExclusive
 mov rax,r14
 shl rax,6
 add rax,QWORD PTR [rsi+24]
 test r15d,r15d
 js jmd_reads_all_unnamed
 cmp r15d,128
 jae jmd_reads_specific_unnamed
 cmp r15d,64
 jae jmd_reads_named_high
 bts QWORD PTR [rax+8],r15
 jmp jmd_mutate_unlock
jmd_reads_named_high:
 sub r15d,64
 bts QWORD PTR [rax+40],r15
 jmp jmd_mutate_unlock
jmd_reads_all_unnamed:
 mov DWORD PTR [rax+24],1
 jmp jmd_mutate_unlock
jmd_reads_specific_unnamed:
 sub r15d,128
 bts DWORD PTR [rax+28],r15d
jmd_mutate_unlock:
 lea rcx,[rsi+8]
 call ReleaseSRWLockExclusive
 jmp jmd_service_done

jmd_define:
 mov QWORD PTR [rsp+64],r14
 mov rcx,QWORD PTR [r14+JMD_MODULE_NAME]
 test rcx,rcx
 jz jmd_error_null_name
 mov rdx,rbx
 call jmd_view
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 test edx,edx
 jz jmd_error_empty_name
 xor r15d,r15d
jmd_define_find:
 cmp r15d,JMD_COUNT
 jae jmd_service_gap
 mov rax,r15
 shl rax,5
 add rax,QWORD PTR [rsi+32]
 cmp DWORD PTR [rax+24],0
 je jmd_define_next
 mov rdx,QWORD PTR [rax]
 mov r8d,DWORD PTR [rax+8]
 xor r9d,r9d
 mov rcx,QWORD PTR [r14+JMD_MODULE_NAME]
 call jmd_match
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 test eax,eax
 jnz jmd_define_found
jmd_define_next:
 inc r15d
 jmp jmd_define_find
jmd_define_found:
 mov rax,r15
 shl rax,5
 add rax,QWORD PTR [rsi+32]
 mov QWORD PTR [rsp+72],rax
 mov DWORD PTR [rsp+124],0
 mov rcx,QWORD PTR [r14+JMD_MODULE_LOADER]
 test r15d,r15d
 jnz jmd_define_loader
 test rcx,rcx
 jz jmd_define_base_loader_valid
 mov DWORD PTR [rsp+124],1
jmd_define_base_loader_valid:
 xor eax,eax
 jmp jmd_define_loader_ready
jmd_define_loader:
 call jmd_loader
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
jmd_define_loader_ready:
 mov rdx,QWORD PTR [rsp+72]
 cmp eax,DWORD PTR [rdx+12]
 jne jmd_service_gap
 mov DWORD PTR [rsp+100],eax
 cmp DWORD PTR [r12+8],1
 ja jmd_service_bad
 call GetProcessHeap
 test rax,rax
 jz jmd_service_oom
 mov QWORD PTR [rsp+80],rax
 mov rcx,rax
 mov edx,8
 mov r8d,32768
 call HeapAlloc
 test rax,rax
 jz jmd_service_oom
 mov rdi,rax
 lock inc QWORD PTR [boom_module_definitions_owned_buffers]
 mov DWORD PTR [rsp+88],-1
 mov DWORD PTR [rsp+92],-1
 mov rcx,QWORD PTR [r12+16]
 test rcx,rcx
 jz jmd_define_location
 mov rdx,rdi
 mov r8d,4096
 xor r9d,r9d
 call jmd_copy
 mov DWORD PTR [rsp+88],eax
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
jmd_define_location:
 mov rcx,QWORD PTR [r12+24]
 test rcx,rcx
 jz jmd_define_packages
 lea rdx,[rdi+8192]
 mov r8d,4096
 xor r9d,r9d
 call jmd_copy
 mov DWORD PTR [rsp+92],eax
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
jmd_define_packages:
 mov DWORD PTR [rsp+96],0
 mov DWORD PTR [rsp+104],0
 mov DWORD PTR [rsp+108],0
 mov DWORD PTR [rsp+172],0
 mov r14,QWORD PTR [r12+32]
 test r14,r14
 jz jmd_define_package_complete
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz jmd_service_bad
 mov rcx,r14
 lea rdx,boom_runtime_type_map
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz jmd_service_done
 cmp DWORD PTR [rax+20],2
 jne jmd_service_bad
 mov eax,DWORD PTR [r14-20]
 cmp eax,8192
 ja jmd_service_gap
 mov DWORD PTR [rsp+96],eax
jmd_define_package_loop:
 mov eax,DWORD PTR [rsp+104]
 cmp eax,DWORD PTR [rsp+96]
 jae jmd_define_package_complete
 mov rcx,QWORD PTR [r14+rax*8]
 test rcx,rcx
 jz jmd_error_bad_package
 mov QWORD PTR [rsp+144],rcx
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,QWORD PTR [rsp+144]
 call boom_heap_contains
 test eax,eax
 jz jmd_service_bad
 mov rax,QWORD PTR [rsp+144]
 lea rcx,JMD_STRING_LAYOUT
 cmp QWORD PTR [rax-8],rcx
 jne jmd_error_bad_package
 mov rcx,rax
 mov edx,r15d
 call jmd_package
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 test eax,eax
 js jmd_define_package_unknown
 lea rdx,[rdi+16384]
 bts QWORD PTR [rdx],rax
 jc jmd_define_package_duplicate
 inc DWORD PTR [rsp+108]
jmd_define_package_duplicate:
 inc DWORD PTR [rsp+104]
 jmp jmd_define_package_loop
jmd_define_package_unknown:
 mov rcx,QWORD PTR [rsp+144]
 lea rdx,[rdi+17408]
 mov r8d,4096
 mov r9d,1
 call jmd_copy
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 mov DWORD PTR [rsp+168],eax
 test eax,eax
 jz jmd_error_invalid_package
 xor ecx,ecx
jmd_define_package_syntax:
 movzx edx,WORD PTR [rdi+rcx*2+17408]
 cmp edx,59
 je jmd_error_invalid_package
 cmp edx,91
 je jmd_error_invalid_package
 cmp edx,47
 jne jmd_define_package_syntax_next
 test ecx,ecx
 jz jmd_error_invalid_package
 lea edx,[rcx+1]
 cmp edx,DWORD PTR [rsp+168]
 jae jmd_error_invalid_package
 cmp WORD PTR [rdi+rcx*2+17410],47
 je jmd_error_invalid_package
jmd_define_package_syntax_next:
 inc ecx
 cmp ecx,DWORD PTR [rsp+168]
 jb jmd_define_package_syntax
 mov DWORD PTR [rsp+172],1
 jmp jmd_define_package_duplicate
jmd_define_package_complete:
 cmp DWORD PTR [rsp+124],0
 jne jmd_error_base_loader
 lea rcx,[rsi+8]
 call AcquireSRWLockExclusive
 mov rax,r15
 shl rax,6
 add rax,QWORD PTR [rsi+24]
 cmp DWORD PTR [rax],0
 jne jmd_define_duplicate
 cmp DWORD PTR [rsp+172],0
 jne jmd_define_profile_gap
 mov rax,QWORD PTR [rsp+72]
 mov ecx,DWORD PTR [rsp+108]
 cmp ecx,DWORD PTR [rax+20]
 jne jmd_define_profile_gap
 mov r14,QWORD PTR [rsp+64]
 mov edx,DWORD PTR [rsp+100]
 test edx,edx
 jz jmd_define_bind_module
 mov rcx,QWORD PTR [rsi+16]
 mov r8,QWORD PTR [r14+JMD_MODULE_LOADER]
 mov r9,rbx
 call boom_java_class_bind_loader
 test eax,eax
 jz jmd_define_unlock
 cmp DWORD PTR [rsp+100],2
 jne jmd_define_bind_module
 ; The application's original ClassLoader constructor already created its
 ; unnamed Module. Bind that same object to the existing JCLS unnamed slot.
 ; Inherited layout compaction is handled by the original generated FMAP.
 mov rcx,QWORD PTR [r14+JMD_MODULE_LOADER]
 mov rdx,rbx
 call JMD_UNNAMED_FIELD
 test rax,rax
 jz jmd_define_unlock
 mov r8,QWORD PTR [rax]
 test r8,r8
 jz jmd_define_app_unnamed_gap
 mov QWORD PTR [rsp+176],r8
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r8
 call boom_heap_contains
 test eax,eax
 jz jmd_define_app_unnamed_bad
 mov rcx,QWORD PTR [rsp+176]
 lea rdx,JMD_MODULE_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jmd_define_unlock
 cmp QWORD PTR [rax+JMD_MODULE_NAME],0
 jne jmd_define_app_unnamed_bad
 mov rcx,QWORD PTR [r14+JMD_MODULE_LOADER]
 cmp QWORD PTR [rax+JMD_MODULE_LOADER],rcx
 jne jmd_define_app_unnamed_bad
 mov rcx,QWORD PTR [rsi+16]
 mov edx,JMD_APP_UNNAMED
 mov r8,rax
 mov r9,rbx
 call boom_java_class_bind_module
 test eax,eax
 jz jmd_define_unlock
jmd_define_bind_module:
 mov rcx,QWORD PTR [rsi+16]
 mov edx,r15d
 mov r8,r14
 mov r9,rbx
 call boom_java_class_bind_module
 test eax,eax
 jz jmd_define_unlock
 test r15d,r15d
 jnz jmd_define_symbols
 mov rcx,QWORD PTR [rsi+16]
 mov rdx,rbx
 call boom_java_class_seal
 test eax,eax
 jz jmd_define_unlock
jmd_define_symbols:
 mov rax,r15
 shl rax,14
 lea rdx,jmod_symbol_copies
 add rdx,rax
 mov r8d,DWORD PTR [rsp+88]
 test r8d,r8d
 js jmd_define_location_symbols
 xor ecx,ecx
jmd_define_version_copy:
 cmp ecx,r8d
 jae jmd_define_location_symbols
 mov ax,WORD PTR [rdi+rcx*2]
 mov WORD PTR [rdx+rcx*2],ax
 inc ecx
 jmp jmd_define_version_copy
jmd_define_location_symbols:
 mov r8d,DWORD PTR [rsp+92]
 test r8d,r8d
 js jmd_define_publish
 xor ecx,ecx
jmd_define_location_copy:
 cmp ecx,r8d
 jae jmd_define_publish
 mov ax,WORD PTR [rdi+rcx*2+8192]
 mov WORD PTR [rdx+rcx*2+8192],ax
 inc ecx
 jmp jmd_define_location_copy
jmd_define_publish:
 mov rax,r15
 shl rax,6
 add rax,QWORD PTR [rsi+24]
 mov QWORD PTR [rax+48],rdx
 mov ecx,DWORD PTR [r12+8]
 test r15d,r15d
 jnz jmd_define_open_flag
 xor ecx,ecx
jmd_define_open_flag:
 mov DWORD PTR [rax+4],ecx
 mov ecx,DWORD PTR [rsp+88]
 mov DWORD PTR [rax+16],ecx
 mov ecx,DWORD PTR [rsp+92]
 mov DWORD PTR [rax+20],ecx
 mov DWORD PTR [rax],1
 inc QWORD PTR [rax+32]
 jmp jmd_define_unlock
jmd_define_duplicate:
 mov eax,r15d
 add eax,15
 test r15d,r15d
 jnz jmd_define_duplicate_code
 mov eax,6
jmd_define_duplicate_code:
 mov DWORD PTR [rsp+136],eax
 jmp jmd_define_unlock
jmd_define_profile_gap:
 mov DWORD PTR [rbx],20
 jmp jmd_define_unlock
jmd_define_app_unnamed_gap:
 mov DWORD PTR [rbx],20
 jmp jmd_define_unlock
jmd_define_app_unnamed_bad:
 mov DWORD PTR [rbx],7
jmd_define_unlock:
 lea rcx,[rsi+8]
 call ReleaseSRWLockExclusive
 cmp DWORD PTR [rsp+136],-1
 jne jmd_service_error
 jmp jmd_service_done

jmd_error_null_define:
 xor eax,eax
 jmp jmd_service_error_code
jmd_error_wrong_module:
 mov eax,1
 jmp jmd_service_error_code
jmd_error_null_name:
 mov eax,2
 jmp jmd_service_error_code
jmd_error_empty_name:
 mov eax,3
 jmp jmd_service_error_code
jmd_error_base_loader:
 mov eax,4
 jmp jmd_service_error_code
jmd_error_bad_package:
 mov eax,5
 jmp jmd_service_error_code
jmd_error_null_from:
 mov eax,7
 jmp jmd_service_error_code
jmd_error_unregistered_from:
 mov eax,8
 cmp r13d,1
 je jmd_service_error_code
 mov eax,9
 cmp r13d,4
 jne jmd_service_error_code
 mov eax,13
 jmp jmd_service_error_code
jmd_error_null_to:
 mov eax,10
 jmp jmd_service_error_code
jmd_error_invalid_to:
 mov eax,11
 jmp jmd_service_error_code
jmd_error_null_package:
 mov eax,12
 jmp jmd_service_error_code
jmd_error_null_module:
 mov eax,14
jmd_service_error_code:
 mov DWORD PTR [rsp+136],eax
jmd_service_error:
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 mov eax,DWORD PTR [rsp+136]
 shl rax,4
 lea rdx,jmod_error_messages
 add rdx,rax
 mov r8,QWORD PTR [rdx]
 mov r9d,DWORD PTR [rdx+8]
 mov eax,DWORD PTR [rdx+12]
 mov DWORD PTR [rsp+140],eax
 jmp jmd_service_make_error
jmd_error_invalid_package:
 ; The syntax rejection precedes duplicate-definition checks, as in modules.cpp.
 ; The normalized input is already in the bounded native temporary buffer.
 lea r10,jmd_invalid_package_prefix
 xor ecx,ecx
jmd_invalid_prefix_copy:
 mov ax,WORD PTR [r10+rcx*2]
 mov WORD PTR [rdi+rcx*2],ax
 inc ecx
 cmp ecx,22
 jb jmd_invalid_prefix_copy
 mov r9d,22
 xor ecx,ecx
jmd_invalid_package_copy:
 cmp ecx,DWORD PTR [rsp+168]
 jae jmd_invalid_suffix_start
 mov ax,WORD PTR [rdi+rcx*2+17408]
 mov WORD PTR [rdi+r9*2],ax
 inc ecx
 inc r9d
 jmp jmd_invalid_package_copy
jmd_invalid_suffix_start:
 lea r10,jmd_invalid_package_suffix
 lea rdx,[rdi+r9*2]
 xor ecx,ecx
jmd_invalid_suffix_copy:
 mov ax,WORD PTR [r10+rcx*2]
 mov WORD PTR [rdx+rcx*2],ax
 inc ecx
 cmp ecx,13
 jb jmd_invalid_suffix_copy
 add r9d,13
 mov rax,r15
 shl rax,5
 add rax,QWORD PTR [rsi+32]
 mov r10,QWORD PTR [rax]
 mov r11d,DWORD PTR [rax+8]
 jmp jmd_missing_copy_known_name
jmd_error_missing_package:
 ; Keep the missing package distinction: validation cannot pretend an export
 ; succeeded simply because the target exists. UTF16 error text is bounded.
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 call GetProcessHeap
 test rax,rax
 jz jmd_service_oom
 mov QWORD PTR [rsp+80],rax
 mov rcx,rax
 xor edx,edx
 mov r8d,32768
 call HeapAlloc
 test rax,rax
 jz jmd_service_oom
 mov rdi,rax
 lock inc QWORD PTR [boom_module_definitions_owned_buffers]
 lea rax,jmd_package_prefix
 xor ecx,ecx
jmd_missing_prefix:
 mov dx,WORD PTR [rax+rcx*2]
 mov WORD PTR [rdi+rcx*2],dx
 inc ecx
 cmp ecx,8
 jb jmd_missing_prefix
 mov rcx,QWORD PTR [r12+8]
 lea rdx,[rdi+16]
 mov r8d,4096
 mov r9d,1
 call jmd_copy
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 lea r9d,[eax+8]
 lea r10,jmd_package_missing
 mov r11d,26
 cmp r13d,4
 jne jmd_missing_suffix
 lea r10,jmd_package_missing_unnamed
 mov r11d,21
jmd_missing_suffix:
 xor ecx,ecx
 lea rdx,[rdi+r9*2]
jmd_missing_suffix_loop:
 mov ax,WORD PTR [r10+rcx*2]
 mov WORD PTR [rdx+rcx*2],ax
 inc ecx
 cmp ecx,r11d
 jb jmd_missing_suffix_loop
 add r9d,r11d
 mov rax,r14
 shl rax,5
 add rax,QWORD PTR [rsi+32]
 mov r10,QWORD PTR [rax]
 mov r11d,DWORD PTR [rax+8]
jmd_missing_copy_known_name:
 lea rdx,[rdi+r9*2]
 xor ecx,ecx
jmd_missing_name_loop:
 cmp ecx,r11d
 jae jmd_missing_message_ready
 mov ax,WORD PTR [r10+rcx*2]
 mov WORD PTR [rdx+rcx*2],ax
 inc ecx
 jmp jmd_missing_name_loop
jmd_missing_message_ready:
 add r9d,r11d
 mov r8,rdi
 mov DWORD PTR [rsp+140],1
jmd_service_make_error:
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+64]
 call boom_java_property_copy
 test rax,rax
 jz jmd_service_done
 mov QWORD PTR [rsp+120],rax
 mov eax,DWORD PTR [rsp+140]
 imul rax,24
 lea rdx,jmod_error_types
 add rdx,rax
 mov QWORD PTR [rsp+160],rdx
 mov rcx,QWORD PTR [rdx]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 mov rax,QWORD PTR [rsp+160]
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,QWORD PTR [rax+8]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz jmd_service_done
 mov QWORD PTR [rsp+112],rax
 mov rcx,rbx
 lea rdx,[rsp+112]
 mov rax,QWORD PTR [rsp+160]
 call QWORD PTR [rax+16]
 cmp DWORD PTR [rbx],0
 jne jmd_service_done
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+112]
 lea r8,boom_runtime_type_map
 lea r9,JMD_THROWABLE_TYPE
 call boom_exception_set32
 jmp jmd_service_done
jmd_service_oom:
 mov DWORD PTR [rbx],3
 jmp jmd_service_done
jmd_service_bad:
 mov DWORD PTR [rbx],7
 jmp jmd_service_done
jmd_service_gap:
 mov DWORD PTR [rbx],20
jmd_service_done:
 test rdi,rdi
 jz jmd_service_return
 mov rcx,QWORD PTR [rsp+80]
 xor edx,edx
 mov r8,rdi
 call HeapFree
 test eax,eax
 jz jmd_service_free_error
 lock dec QWORD PTR [boom_module_definitions_owned_buffers]
 jmp jmd_service_return
jmd_service_free_error:
 cmp DWORD PTR [rbx],0
 jne jmd_service_return
 mov DWORD PTR [rbx],20
jmd_service_return:
 xor eax,eax
 add rsp,208
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_module_definitions_service ENDP

; Read-only graph predicates for the normal VM module access boundary and
; development observations. They never allocate a Module or infer Java fields.
; can_read(Context32,from,to) -> boolean; NULL to queries all-unnamed permission.
PUBLIC boom_module_definitions_can_read
boom_module_definitions_can_read PROC FRAME
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
 lea rsi,boom_provider_module_definitions_pool
 mov rdi,r8
 test rbx,rbx
 jz jmd_can_read_zero
 cmp DWORD PTR [rbx],0
 jne jmd_can_read_zero
 mov rcx,rdx
 call jmd_lookup
 test eax,eax
 js jmd_can_read_bad
 mov r12d,eax
 mov r13d,-1
 test rdi,rdi
 jz jmd_can_read_ready
 mov rcx,rdi
 call jmd_lookup
 test eax,eax
 js jmd_can_read_bad
 mov r13d,eax
jmd_can_read_ready:
 cmp r12d,128
 jae jmd_can_read_one
 test r13d,r13d
 jz jmd_can_read_one
 cmp r12d,r13d
 je jmd_can_read_one
 lea rcx,[rsi+8]
 call AcquireSRWLockShared
 mov rax,r12
 shl rax,6
 add rax,QWORD PTR [rsi+24]
 xor edi,edi
 test r13d,r13d
 js jmd_can_read_unnamed
 cmp r13d,128
 jae jmd_can_read_unnamed
 cmp r13d,64
 jae jmd_can_read_named_high
 bt QWORD PTR [rax+8],r13
 setc dil
 jmp jmd_can_read_unlock
jmd_can_read_named_high:
 sub r13d,64
 bt QWORD PTR [rax+40],r13
 setc dil
 jmp jmd_can_read_unlock
jmd_can_read_unnamed:
 cmp DWORD PTR [rax+24],0
 jne jmd_can_read_locked_one
 test r13d,r13d
 js jmd_can_read_unlock
 sub r13d,128
 bt DWORD PTR [rax+28],r13d
 setc dil
 jmp jmd_can_read_unlock
jmd_can_read_locked_one:
 mov edi,1
jmd_can_read_unlock:
 lea rcx,[rsi+8]
 call ReleaseSRWLockShared
 mov eax,edi
 jmp jmd_can_read_done
jmd_can_read_bad:
 cmp DWORD PTR [rbx],0
 jne jmd_can_read_zero
 mov DWORD PTR [rbx],7
 jmp jmd_can_read_zero
jmd_can_read_one:
 mov eax,1
 jmp jmd_can_read_done
jmd_can_read_zero:
 xor eax,eax
jmd_can_read_done:
 add rsp,48
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_module_definitions_can_read ENDP

; is_exported(Context32,from,package,to) -> boolean; NULL to is unqualified.
PUBLIC boom_module_definitions_is_exported
boom_module_definitions_is_exported PROC FRAME
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
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 lea rsi,boom_provider_module_definitions_pool
 mov rdi,r8
 mov r15,r9
 test rbx,rbx
 jz jmd_is_exported_zero
 cmp DWORD PTR [rbx],0
 jne jmd_is_exported_zero
 test rdi,rdi
 jz jmd_is_exported_bad
 mov rcx,rdx
 call jmd_lookup
 test eax,eax
 js jmd_is_exported_bad
 mov r12d,eax
 cmp eax,128
 jae jmd_is_exported_one
 mov rcx,rdi
 mov edx,r12d
 call jmd_package
 cmp DWORD PTR [rbx],0
 jne jmd_is_exported_zero
 test eax,eax
 js jmd_is_exported_zero
 mov r14d,eax
 mov r13d,-1
 test r15,r15
 jz jmd_is_exported_ready
 mov rcx,r15
 call jmd_lookup
 test eax,eax
 js jmd_is_exported_bad
 mov r13d,eax
 cmp r13d,r12d
 je jmd_is_exported_one
jmd_is_exported_ready:
 lea rcx,[rsi+8]
 call AcquireSRWLockShared
 mov rax,r12
 shl rax,6
 add rax,QWORD PTR [rsi+24]
 cmp DWORD PTR [rax+4],0
 jne jmd_is_exported_locked_one
 mov rax,r14
 shl rax,5
 lea rdx,boom_module_definitions_package_states
 add rdx,rax
 cmp DWORD PTR [rdx],0
 jne jmd_is_exported_locked_one
 xor edi,edi
 test r13d,r13d
 js jmd_is_exported_unlock
 cmp r13d,128
 jae jmd_is_exported_unnamed
 cmp r13d,64
 jae jmd_is_exported_named_high
 bt QWORD PTR [rdx+8],r13
 setc dil
 jmp jmd_is_exported_unlock
jmd_is_exported_named_high:
 sub r13d,64
 bt QWORD PTR [rdx+24],r13
 setc dil
 jmp jmd_is_exported_unlock
jmd_is_exported_unnamed:
 cmp DWORD PTR [rdx+4],0
 jne jmd_is_exported_locked_one
 sub r13d,128
 bt DWORD PTR [rdx+16],r13d
 setc dil
 jmp jmd_is_exported_unlock
jmd_is_exported_locked_one:
 mov edi,1
jmd_is_exported_unlock:
 lea rcx,[rsi+8]
 call ReleaseSRWLockShared
 mov eax,edi
 jmp jmd_is_exported_done
jmd_is_exported_bad:
 cmp DWORD PTR [rbx],0
 jne jmd_is_exported_zero
 mov DWORD PTR [rbx],7
 jmp jmd_is_exported_zero
jmd_is_exported_one:
 mov eax,1
 jmp jmd_is_exported_done
jmd_is_exported_zero:
 xor eax,eax
jmd_is_exported_done:
 add rsp,48
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_module_definitions_is_exported ENDP
