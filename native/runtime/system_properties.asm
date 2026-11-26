; SystemProps.Raw Windows native platform properties. Handwritten MASM only.
; One heap-bound OS snapshot, fresh private String[] per call, retry after OOM.
; GC remains explicit/quiescent. The snapshot array is an ordinary static root.
option casemap:none
EXTERN GetCurrentThreadId:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
EXTERN GetCurrentDirectoryW:PROC
EXTERN GetTempPathW:PROC
EXTERN GetEnvironmentVariableW:PROC
EXTERN GetUserNameW:PROC
EXTERN GetUserDefaultLCID:PROC
EXTERN GetUserDefaultUILanguage:PROC
EXTERN GetLocaleInfoW:PROC
EXTERN GetACP:PROC
EXTERN GetConsoleCP:PROC
EXTERN GetStdHandle:PROC
EXTERN GetFileType:PROC
EXTERN GetSystemInfo:PROC
EXTERN GetWindowsDirectoryW:PROC
EXTERN GetFileAttributesW:PROC
EXTERN IsValidCodePage:PROC
EXTERN MultiByteToWideChar:PROC
EXTERN RtlGetVersion:PROC
EXTERN SHGetKnownFolderPath:PROC
EXTERN CoTaskMemFree:PROC
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN boom_reference_array_new:PROC
EXTERN boom_string_allocate:PROC
EXTERN boom_string_load:PROC
PUBLIC boom_platform_properties
.const
ALIGN 8
property_profile_guid DWORD 05E6C858Fh
    WORD 00E22h,04760h
    BYTE 09Ah,0FEh,0EAh,033h,017h,0B6h,071h,073h
property_username WORD 85,83,69,82,78,65,77,69,0
property_font_suffix WORD 92,70,79,78,84,83,92,83,105,109,83,117,110,49,56,48,51,48,46,116,116,99,0
.code
; platform(ctx RCX,argv RDX,pool R8)->fresh String[]/NULL.
; Pool80: magic0 ABI4 state8 owner12 heapCell16 stringPool24 arrayLayout32,
; cache-root cell40 rows48 count56 reserved60 fallback literal IDs64 boundHeap72.
boom_platform_properties PROC FRAME
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
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rbx,rcx
    mov rsi,r8
    cmp DWORD PTR [rbx],0
    jne properties_error
    test rsi,rsi
    jz properties_bad
    cmp DWORD PTR [rsi],050524F50h
    jne properties_bad
    cmp DWORD PTR [rsi+4],1
    je properties_abi_ready
    cmp DWORD PTR [rsi+4],2
    jne properties_bad
    cmp QWORD PTR [rsi+80],0
    je properties_bad
    cmp QWORD PTR [rsi+88],0
    je properties_bad
    cmp QWORD PTR [rsi+96],0
    je properties_bad
    cmp QWORD PTR [rsi+104],0
    je properties_bad
properties_abi_ready:
    cmp DWORD PTR [rsi+60],0
    jne properties_bad
    mov eax,DWORD PTR [rsi+56]
    test eax,eax
    jz properties_bad
    cmp eax,128
    ja properties_bad
    cmp QWORD PTR [rsi+40],0
    je properties_bad
    cmp QWORD PTR [rsi+48],0
    je properties_bad
    cmp QWORD PTR [rsi+64],0
    je properties_bad
    mov rcx,QWORD PTR [rsi+16]
    test rcx,rcx
    jz properties_bad
    mov rdx,QWORD PTR [rcx]
    test rdx,rdx
    jz properties_bad
    mov rax,QWORD PTR [rsi+72]
    test rax,rax
    jz properties_bind_first
    cmp rax,rdx
    jne properties_bad
    jmp properties_bound
properties_bind_first:
    xor eax,eax
    lock cmpxchg QWORD PTR [rsi+72],rdx
    test rax,rax
    jz properties_bound
    cmp rax,rdx
    jne properties_bad
properties_bound:
    call GetCurrentThreadId
    mov edi,eax
properties_state:
    mov eax,DWORD PTR [rsi+8]
    cmp eax,2
    je properties_clone
    cmp eax,1
    je properties_wait
    test eax,eax
    jnz properties_bad
    mov edx,1
    lock cmpxchg DWORD PTR [rsi+8],edx
    jne properties_state
    mov DWORD PTR [rsi+12],edi
    mov rcx,rbx
    mov rdx,rsi
    mov r8d,DWORD PTR [rsi+56]
    call property_array_new
    test rax,rax
    jz properties_build_failed
    mov r12,rax
    mov r10,QWORD PTR [rsi+40]
    mov QWORD PTR [r10],rax
    mov r13,QWORD PTR [rsi+48]
    xor r14d,r14d
properties_build_loop:
    cmp r14d,DWORD PTR [rsi+56]
    jae properties_publish
    cmp DWORD PTR [r13],r14d
    jne properties_build_bad
    cmp DWORD PTR [r13+12],0
    jne properties_build_bad
    mov rcx,rbx
    mov rdx,rsi
    mov r8d,DWORD PTR [r13+4]
    mov r9d,DWORD PTR [r13+8]
    call property_value
    cmp DWORD PTR [rbx],0
    jne properties_build_failed
    mov QWORD PTR [r12+r14*8],rax
    add r13,16
    inc r14d
    jmp properties_build_loop
properties_publish:
    mov DWORD PTR [rsi+12],0
    mov DWORD PTR [rsi+8],2
    lea rcx,[rsi+8]
    call WakeByAddressAll
    jmp properties_clone
properties_build_bad:
    mov DWORD PTR [rbx],7
properties_build_failed:
    mov r10,QWORD PTR [rsi+40]
    mov QWORD PTR [r10],0
    mov DWORD PTR [rsi+12],0
    mov DWORD PTR [rsi+8],0
    lea rcx,[rsi+8]
    call WakeByAddressAll
    jmp properties_error
properties_wait:
    cmp DWORD PTR [rsi+12],edi
    je properties_bad
    mov DWORD PTR [rsp+48],1
    lea rcx,[rsi+8]
    lea rdx,[rsp+48]
    mov r8d,4
    mov r9d,-1
    call WaitOnAddress
    jmp properties_state
properties_clone:
    mov r10,QWORD PTR [rsi+40]
    mov r12,QWORD PTR [r10]
    test r12,r12
    jz properties_bad
    mov rcx,rbx
    mov rdx,rsi
    mov r8d,DWORD PTR [rsi+56]
    call property_array_new
    test rax,rax
    jz properties_error
    mov r15,rax
    mov ecx,DWORD PTR [rsi+56]
    mov rdi,rax
    mov rsi,r12
    rep movsq
    mov rax,r15
    jmp properties_done
properties_bad:
    mov DWORD PTR [rbx],7
properties_error:
    xor eax,eax
properties_done:
    add rsp,64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_platform_properties ENDP

; ABI2 callbacks use normal source String/String[]; ABI1 remains unchanged.
property_array_new PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    cmp DWORD PTR [rdx+4],2
    jne property_array_legacy
    call QWORD PTR [rdx+80]
    jmp property_array_done
property_array_legacy:
    mov r9,rcx
    mov rcx,QWORD PTR [rdx+72]
    mov r10,rdx
    mov edx,r8d
    mov r8,QWORD PTR [r10+32]
    call boom_reference_array_new
property_array_done:
    add rsp,40
    ret
property_array_new ENDP

; fallback(ctx RCX,pool RDX,ordinal R8D) -> literal. Immutable compiler table.
property_fallback PROC
    mov r10,QWORD PTR [rdx+64]
    mov r8d,DWORD PTR [r10+r8*4]
    jmp property_literal
property_fallback ENDP
property_literal PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    cmp DWORD PTR [rdx+4],2
    jne property_literal_legacy
    call QWORD PTR [rdx+96]
    jmp property_literal_done
property_literal_legacy:
    mov r9,rcx
    mov r10,QWORD PTR [rdx+16]
    mov rcx,QWORD PTR [r10]
    mov rdx,QWORD PTR [rdx+24]
    call boom_string_load
property_literal_done:
    add rsp,40
    ret
property_literal ENDP

; copy(ctx,pool,UTF16 buffer R8,unit count R9D)->owned immutable String.
property_from_buffer PROC FRAME
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
    mov rsi,r8
    mov edi,r9d
    mov r12,rdx
    cmp DWORD PTR [r12+4],2
    jne property_copy_legacy
    mov rdx,r12
    mov r8,rsi
    mov r9d,edi
    call QWORD PTR [r12+88]
    jmp property_copy_done
property_copy_legacy:
    mov r10,QWORD PTR [r12+16]
    mov rcx,QWORD PTR [r10]
    mov rdx,QWORD PTR [r12+24]
    mov r8d,edi
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz property_copy_done
    mov rbx,rax
    mov ecx,edi
    mov rdi,QWORD PTR [rax]
    rep movsw
    mov rax,rbx
property_copy_done:
    add rsp,40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
property_from_buffer ENDP

; decimal(unsigned ECX,UTF16 destination RDX)->unit count EAX; no calls.
property_decimal PROC
    mov r9,rdx
    mov eax,ecx
    xor r8d,r8d
    mov r10d,10
property_decimal_digits:
    xor edx,edx
    div r10d
    add dx,48
    mov WORD PTR [r9+r8*2],dx
    inc r8d
    test eax,eax
    jnz property_decimal_digits
    xor eax,eax
    lea edx,[r8-1]
property_decimal_reverse:
    cmp eax,edx
    jae property_decimal_done
    movzx r10d,WORD PTR [r9+rax*2]
    movzx r11d,WORD PTR [r9+rdx*2]
    mov WORD PTR [r9+rax*2],r11w
    mov WORD PTR [r9+rdx*2],r10w
    inc eax
    dec edx
    jmp property_decimal_reverse
property_decimal_done:
    mov eax,r8d
    ret
property_decimal ENDP

; value(ctx RCX,pool RDX,query R8D,argument R9D)->String/NULL.
; Query-local buffers fit in 704 bytes, below a Windows guard-page interval.
property_value PROC FRAME
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
    sub rsp,704
    .allocstack 704
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov r12d,r8d
    mov r13d,r9d
    mov QWORD PTR [rsp+80],0
    test r12d,r12d
    jz property_value_null
    cmp r12d,1
    je property_value_literal
    cmp r12d,5
    jb property_value_measure
    je property_value_home
    cmp r12d,6
    je property_value_version_query
    cmp r12d,7
    je property_value_version_query
    cmp r12d,8
    je property_value_locale
    cmp r12d,9
    je property_value_acp
    cmp r12d,10
    je property_value_console
    cmp r12d,11
    je property_value_version_query
    cmp r12d,12
    je property_value_isa
    jmp property_value_bad
property_value_isa:
    lea rcx,[rsp+96]
    call GetSystemInfo
    cmp WORD PTR [rsp+96],9
    jne property_value_null
    jmp property_value_literal
property_value_literal:
    mov rcx,rbx
    mov rdx,rsi
    mov r8d,r13d
    call property_literal
    jmp property_value_done
property_value_measure:
    xor ecx,ecx
    xor edx,edx
    cmp r12d,2
    je property_value_cwd_size
    cmp r12d,3
    je property_value_temp_size
    lea rcx,property_username
    xor r8d,r8d
    call GetEnvironmentVariableW
    test eax,eax
    jnz property_value_capacity
    mov DWORD PTR [rsp+48],0
    xor ecx,ecx
    lea rdx,[rsp+48]
    call GetUserNameW
    mov eax,DWORD PTR [rsp+48]
    mov r12d,12
    test eax,eax
    jz property_value_unknown
    jmp property_value_capacity
property_value_cwd_size:
    call GetCurrentDirectoryW
    jmp property_value_capacity
property_value_temp_size:
    call GetTempPathW
property_value_capacity:
    test eax,eax
    jz property_value_io
    cmp eax,32768
    ja property_value_io
    mov r15d,eax
    cmp DWORD PTR [rsi+4],2
    je property_value_source_capacity
    mov rcx,QWORD PTR [rsi+16]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rsi+24]
    mov r8d,r15d
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz property_value_done
    mov r14,rax
    jmp property_value_capacity_ready
property_value_source_capacity:
    xor ecx,ecx
    lea rdx,[r15*2]
    mov r8d,03000h
    mov r9d,4
    call VirtualAlloc
    test rax,rax
    jz property_value_source_oom
    mov QWORD PTR [rsp+80],rax
    lea r14,[rsp+80]
property_value_capacity_ready:
    cmp r12d,2
    je property_value_cwd_fill
    cmp r12d,3
    je property_value_temp_fill
    cmp r12d,12
    je property_value_name_fill
    lea rcx,property_username
    mov rdx,QWORD PTR [r14]
    mov r8d,r15d
    call GetEnvironmentVariableW
    jmp property_value_filled
property_value_name_fill:
    mov DWORD PTR [rsp+48],r15d
    mov rcx,QWORD PTR [r14]
    lea rdx,[rsp+48]
    call GetUserNameW
    test eax,eax
    jz property_value_unknown
    mov eax,DWORD PTR [rsp+48]
    dec eax
    jmp property_value_filled
property_value_cwd_fill:
    mov ecx,r15d
    mov rdx,QWORD PTR [r14]
    call GetCurrentDirectoryW
    jmp property_value_filled
property_value_temp_fill:
    mov ecx,r15d
    mov rdx,QWORD PTR [r14]
    call GetTempPathW
property_value_filled:
    test eax,eax
    jz property_value_io
    cmp eax,r15d
    jae property_value_io
    cmp DWORD PTR [rsi+4],2
    je property_value_source_filled
    mov r10,QWORD PTR [r14]
    mov ecx,eax
    shl rcx,1
    ; Keep physical allocation accounting; publish only the actual logical units.
    mov QWORD PTR [r10-16],rcx
    mov rax,r14
    jmp property_value_done
property_value_source_filled:
    mov rcx,rbx
    mov rdx,rsi
    mov r8,QWORD PTR [r14]
    mov r9d,eax
    call property_from_buffer
    jmp property_value_done
property_value_source_oom:
    mov DWORD PTR [rbx],3
    jmp property_value_null
property_value_unknown:
    mov r8d,1
    jmp property_value_fallback
property_value_home:
    mov QWORD PTR [rsp+56],0
    lea rcx,property_profile_guid
    xor edx,edx
    xor r8d,r8d
    lea r9,[rsp+56]
    call SHGetKnownFolderPath
    test eax,eax
    js property_value_home_default
    mov r14,QWORD PTR [rsp+56]
    test r14,r14
    jz property_value_home_default
    xor r15d,r15d
property_value_home_length:
    cmp WORD PTR [r14+r15*2],0
    je property_value_home_copy
    inc r15d
    cmp r15d,32768
    jb property_value_home_length
    mov DWORD PTR [rbx],21
    xor edi,edi
    jmp property_value_home_free
property_value_home_copy:
    mov rcx,rbx
    mov rdx,rsi
    mov r8,r14
    mov r9d,r15d
    call property_from_buffer
    mov rdi,rax
property_value_home_free:
    mov rcx,r14
    call CoTaskMemFree
    mov rax,rdi
    jmp property_value_done
property_value_home_default:
    mov r8d,2
    jmp property_value_fallback
property_value_version_query:
    lea rdi,[rsp+96]
    xor eax,eax
    mov ecx,36
    rep stosq
    mov DWORD PTR [rsp+96],284
    lea rcx,[rsp+96]
    call RtlGetVersion
    test eax,eax
    jnz property_value_io
    cmp r12d,6
    je property_value_os_name
    cmp r12d,11
    je property_value_os_patch
    mov ecx,DWORD PTR [rsp+100]
    lea rdx,[rsp+400]
    call property_decimal
    mov r14d,eax
    mov WORD PTR [rsp+r14*2+400],46
    inc r14d
    mov ecx,DWORD PTR [rsp+104]
    lea rdx,[rsp+r14*2+400]
    call property_decimal
    lea r9d,[r14+rax]
    lea r8,[rsp+400]
    jmp property_value_buffer
property_value_os_patch:
    xor r9d,r9d
property_value_patch_length:
    cmp WORD PTR [rsp+r9*2+116],0
    je property_value_patch_copy
    inc r9d
    cmp r9d,128
    jb property_value_patch_length
    jmp property_value_bad
property_value_patch_copy:
    lea r8,[rsp+116]
    jmp property_value_buffer
property_value_os_name:
    mov r8d,12
    cmp DWORD PTR [rsp+100],10
    jne property_value_os_6
    cmp DWORD PTR [rsp+104],0
    jne property_value_fallback
    cmp BYTE PTR [rsp+378],1
    jne property_value_os_server
    mov r8d,15
    cmp DWORD PTR [rsp+108],22000
    jb property_value_fallback
    mov r8d,16
    jmp property_value_fallback
property_value_os_server:
    mov r8d,19
    cmp DWORD PTR [rsp+108],17763
    jb property_value_fallback
    mov r8d,20
    cmp DWORD PTR [rsp+108],20348
    jb property_value_fallback
    mov r8d,21
    cmp DWORD PTR [rsp+108],26040
    jb property_value_fallback
    mov r8d,22
    jmp property_value_fallback
property_value_os_6:
    cmp DWORD PTR [rsp+100],6
    jne property_value_fallback
    cmp DWORD PTR [rsp+104],2
    jb property_value_fallback
    cmp DWORD PTR [rsp+104],3
    ja property_value_fallback
    mov r8d,DWORD PTR [rsp+104]
    add r8d,11
    cmp BYTE PTR [rsp+378],1
    je property_value_fallback
    add r8d,4
    jmp property_value_fallback
property_value_locale:
    call GetUserDefaultLCID
    mov edi,eax
    test r13d,4
    jnz property_value_locale_selected
    call GetUserDefaultUILanguage
    movzx eax,ax
    mov ecx,edi
    and ecx,03FFh
    mov edx,eax
    and edx,03FFh
    cmp ecx,edx
    je property_value_locale_selected
    and edi,0FFFF0000h
    or edi,eax
property_value_locale_selected:
    and r13d,3
    ; Norwegian legacy language/country/variant normalization in the JDK contract.
    mov ecx,edi
    mov edx,059h
    lea r8,[rsp+96]
    mov r9d,86
    call GetLocaleInfoW
    test eax,eax
    jnz property_value_locale_language_ready
    mov ecx,edi
    mov edx,067h
    lea r8,[rsp+96]
    mov r9d,86
    call GetLocaleInfoW
    test eax,eax
    jz property_value_locale_default
property_value_locale_language_ready:
    cmp WORD PTR [rsp+96],110
    jne property_value_locale_normal
    cmp WORD PTR [rsp+100],0
    jne property_value_locale_normal
    cmp WORD PTR [rsp+98],98
    je property_value_norwegian
    cmp WORD PTR [rsp+98],110
    jne property_value_locale_normal
property_value_norwegian:
    cmp r13d,0
    je property_value_norwegian_country
    cmp r13d,1
    je property_value_norwegian_language
    cmp r13d,3
    jne property_value_empty
    cmp WORD PTR [rsp+98],110
    jne property_value_empty
    mov r8d,7
    jmp property_value_fallback
property_value_norwegian_country:
    mov r8d,6
    jmp property_value_fallback
property_value_norwegian_language:
    mov r8d,5
    jmp property_value_fallback
property_value_locale_normal:
    cmp r13d,3
    je property_value_empty
    cmp r13d,2
    je property_value_locale_script
    cmp r13d,1
    je property_value_locale_copy
    mov ecx,edi
    mov edx,05Ah
    lea r8,[rsp+96]
    mov r9d,86
    call GetLocaleInfoW
    test eax,eax
    jnz property_value_locale_copy
    mov ecx,edi
    mov edx,068h
    lea r8,[rsp+96]
    mov r9d,86
    call GetLocaleInfoW
    test eax,eax
    jz property_value_empty
property_value_locale_copy:
    lea r9d,[eax-1]
    lea r8,[rsp+96]
    jmp property_value_buffer
property_value_locale_script:
    mov ecx,edi
    mov edx,05Ch
    lea r8,[rsp+96]
    mov r9d,86
    call GetLocaleInfoW
    cmp eax,6
    jb property_value_empty
    xor ecx,ecx
property_value_script_find:
    movzx edx,WORD PTR [rsp+rcx*2+96]
    cmp edx,45
    je property_value_script_dash
    sub edx,97
    cmp edx,25
    ja property_value_empty
    inc ecx
    cmp ecx,80
    jb property_value_script_find
    jmp property_value_empty
property_value_script_dash:
    inc ecx
    cmp ecx,80
    jae property_value_empty
    movzx edx,WORD PTR [rsp+rcx*2+96]
    cmp edx,45
    je property_value_script_dash
    sub edx,65
    cmp edx,25
    ja property_value_empty
    lea r8,[rsp+rcx*2+96]
    mov ecx,1
property_value_script_lower:
    movzx edx,WORD PTR [r8+rcx*2]
    sub edx,97
    cmp edx,25
    ja property_value_empty
    inc ecx
    cmp ecx,4
    jb property_value_script_lower
    movzx edx,WORD PTR [r8+8]
    sub edx,97
    cmp edx,25
    jbe property_value_empty
    mov r9d,4
    jmp property_value_buffer
property_value_locale_default:
    cmp r13d,0
    je property_value_locale_us
    cmp r13d,1
    jne property_value_empty
    mov r8d,3
    jmp property_value_fallback
property_value_locale_us:
    mov r8d,4
    jmp property_value_fallback
property_value_acp:
    call GetACP
    xor r13d,r13d
    jmp property_value_encoding
property_value_console:
    mov ecx,-11
    test r13d,r13d
    jz property_value_console_handle
    mov ecx,-12
property_value_console_handle:
    call GetStdHandle
    test rax,rax
    jz property_value_null
    cmp rax,-1
    je property_value_null
    mov rcx,rax
    call GetFileType
    cmp eax,2
    jne property_value_null
    call GetConsoleCP
    mov r13d,1
property_value_encoding:
    mov r14d,eax
    cmp eax,65001
    je property_value_utf8
    test r13d,r13d
    jnz property_value_console_encoding
    test eax,eax
    jz property_value_utf8
    cmp eax,936
    je property_value_gbk
    cmp eax,54936
    je property_value_gb18030
    cmp eax,874
    je property_value_ms_encoding
    cmp eax,932
    je property_value_ms_encoding
    cmp eax,949
    je property_value_ms_encoding
    cmp eax,1361
    je property_value_ms_encoding
    cmp eax,950
    jne property_value_cp_encoding
    mov WORD PTR [rsp+64],041FAh
    mov ecx,0
    xor edx,edx
    lea r8,[rsp+64]
    mov r9d,2
    lea rax,[rsp+68]
    mov QWORD PTR [rsp+32],rax
    mov QWORD PTR [rsp+40],1
    call MultiByteToWideChar
    cmp eax,1
    jne property_value_ms_encoding
    cmp WORD PTR [rsp+68],092DBh
    jne property_value_ms_encoding
    mov r8d,11
    jmp property_value_fallback
property_value_console_encoding:
    cmp r14d,874
    jb property_value_cp_encoding
    cmp r14d,950
    ja property_value_cp_encoding
    mov WORD PTR [rsp+400],109
    mov WORD PTR [rsp+402],115
    jmp property_value_encoding_digits
property_value_ms_encoding:
    mov WORD PTR [rsp+400],77
    mov WORD PTR [rsp+402],83
    jmp property_value_encoding_digits
property_value_cp_encoding:
    mov WORD PTR [rsp+400],67
    cmp r13d,0
    je property_value_cp_second
    mov WORD PTR [rsp+400],99
property_value_cp_second:
    mov WORD PTR [rsp+402],112
property_value_encoding_digits:
    mov ecx,r14d
    lea rdx,[rsp+404]
    call property_decimal
    lea r9d,[rax+2]
    lea r8,[rsp+400]
    jmp property_value_buffer
property_value_gbk:
    mov ecx,54936
    call IsValidCodePage
    test eax,eax
    jz property_value_gbk_default
    lea rcx,[rsp+96]
    mov edx,261
    call GetWindowsDirectoryW
    test eax,eax
    jz property_value_gbk_default
    cmp eax,238
    jae property_value_gbk_default
    lea rdx,[rsp+rax*2+96]
    lea rcx,property_font_suffix
property_value_font_copy:
    mov ax,WORD PTR [rcx]
    mov WORD PTR [rdx],ax
    add rcx,2
    add rdx,2
    test ax,ax
    jnz property_value_font_copy
    lea rcx,[rsp+96]
    call GetFileAttributesW
    cmp eax,-1
    je property_value_gbk_default
    test eax,16
    jz property_value_gb18030
property_value_gbk_default:
    mov r8d,9
    jmp property_value_fallback
property_value_gb18030:
    mov r8d,10
    jmp property_value_fallback
property_value_utf8:
    mov r8d,8
    jmp property_value_fallback
property_value_empty:
    xor r8d,r8d
property_value_fallback:
    mov rcx,rbx
    mov rdx,rsi
    call property_fallback
    jmp property_value_done
property_value_buffer:
    mov rcx,rbx
    mov rdx,rsi
    call property_from_buffer
    jmp property_value_done
property_value_io:
    mov DWORD PTR [rbx],21
    jmp property_value_null
property_value_bad:
    mov DWORD PTR [rbx],7
property_value_null:
    xor eax,eax
property_value_done:
    mov QWORD PTR [rsp+88],rax
    mov rcx,QWORD PTR [rsp+80]
    test rcx,rcx
    jz property_value_clean
    xor edx,edx
    mov r8d,08000h
    call VirtualFree
property_value_clean:
    mov rax,QWORD PTR [rsp+88]
    add rsp,704
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
property_value ENDP
END
