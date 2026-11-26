; Frozen class resources, entirely MASM. No JVM or host callback during execution.
; bytes(heap RCX,pool RDX,argv R8,Context16 R9)->fresh byte[] / NULL.
; argv = Class mirror, String name, source-verified caller binding ID.
; Pool80: magic0 abi4 pathState8 providerCount12 providers16 anchors24
; anchorCount32 callerCount36 callers40 packId48 packBytes56 mirrors64 path72.
; Provider40: module0 reserved4 count8 reserved12 entries16 packages24 count32 r36.
; Entry40: UTF16 name0 length8 reserved12 offset16 bytes24 SHA256*32.
; Package16: UTF16 name0 length8 access12 (1=unqualified,2=java.base qualified).
; Anchor16: UTF16 package prefix0 length8 domain12 (0=classpath,provider+1=module).
; Path buffer is module-owned immutable after publication, 32768 UTF16 units.
; The sidecar is located beside the executing image, not relative to the CWD.
; File handles close on every path. Payload SHA256 uses the Windows CNG service.
; Query scratch arrays are ordinary budgeted heap objects. GC is still explicit
; and quiescent; automatic collection needs stack/runtime temporary root maps.
option casemap:none
EXTERN GetModuleHandleExW:PROC
EXTERN GetModuleFileNameW:PROC
EXTERN CreateFileW:PROC
EXTERN GetFileSizeEx:PROC
EXTERN SetFilePointerEx:PROC
EXTERN ReadFile:PROC
EXTERN CloseHandle:PROC
EXTERN BCryptHash:PROC
EXTERN boom_array_new:PROC
EXTERN boom_mirror_typeid:PROC
EXTERN boom_string_view:PROC
PUBLIC boom_resource_bytes
.const
resource_filename WORD 114,101,115,111,117,114,99,101,115,46,112,97,99,107,0
.code

; Exact unsigned UTF16 search; rows have common name-pointer0/length8 fields.
; search(query RCX,length EDX,rows R8,count R9D,stride R10D)->row/NULL.
resource_search PROC
    push rbx
    push rsi
    push rdi
    push r12
    push r13
    push r14
    push r15
    mov rbx, rcx
    mov edi, edx
    mov rsi, r8
    xor r12d, r12d
    mov r13d, r9d
    mov r15d, r10d
resource_search_next:
    cmp r12d, r13d
    jae resource_search_none
    lea r9d, [r12+r13]
    shr r9d, 1
    mov eax, r9d
    imul rax, r15
    lea r14, [rsi+rax]
    mov r10, QWORD PTR [r14]
    mov r11d, DWORD PTR [r14+8]
    mov r8d, edi
    cmp r8d, r11d
    cmova r8d, r11d
    xor eax, eax
resource_search_chars:
    cmp eax, r8d
    jae resource_search_lengths
    movzx ecx, WORD PTR [rbx+rax*2]
    movzx edx, WORD PTR [r10+rax*2]
    cmp ecx, edx
    jb resource_search_less
    ja resource_search_greater
    inc eax
    jmp resource_search_chars
resource_search_lengths:
    cmp edi, r11d
    jb resource_search_less
    ja resource_search_greater
    mov rax, r14
    jmp resource_search_done
resource_search_less:
    mov r13d, r9d
    jmp resource_search_next
resource_search_greater:
    lea r12d, [r9+1]
    jmp resource_search_next
resource_search_none:
    xor eax, eax
resource_search_done:
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
resource_search ENDP

; allowed(provider RCX,name RDX,length R8D,allowed-open-bits R9D)->0/1.
; Resource names ending in .class and resources outside module packages are open.
resource_allowed PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push r12
    .pushreg r12
    sub rsp, 40
    .allocstack 40
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov edi, r8d
    mov r12d, r9d
    cmp edi, 6
    jb resource_allowed_package
    lea eax, [rdi-6]
    lea r10, [rsi+rax*2]
    mov rax, 0061006C0063002Eh
    cmp QWORD PTR [r10], rax
    jne resource_allowed_package
    cmp DWORD PTR [r10+8], 00730073h
    je resource_allowed_yes
resource_allowed_package:
    mov edx, edi
resource_package_slash:
    test edx, edx
    jz resource_allowed_yes
    dec edx
    cmp WORD PTR [rsi+rdx*2], 47
    jne resource_package_slash
    mov rcx, rsi
    mov r8, QWORD PTR [rbx+24]
    mov r9d, DWORD PTR [rbx+32]
    mov r10d, 16
    call resource_search
    test rax, rax
    jz resource_allowed_yes
    mov eax, DWORD PTR [rax+12]
    and eax, r12d
    setnz al
    movzx eax, al
    jmp resource_allowed_done
resource_allowed_yes:
    mov eax, 1
resource_allowed_done:
    add rsp, 40
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
resource_allowed ENDP

resource_path PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp, 56
    .allocstack 56
    .endprolog
    mov rbx, rcx
resource_path_state:
    mov eax, DWORD PTR [rbx+8]
    cmp eax, 2
    je resource_path_yes
    cmp eax, 3
    je resource_path_no
    cmp eax, 1
    je resource_path_wait
    xor eax, eax
    mov edx, 1
    lock cmpxchg DWORD PTR [rbx+8], edx
    jne resource_path_state
    mov ecx, 6 ; FROM_ADDRESS | UNCHANGED_REFCOUNT
    mov rdx, rbx
    lea r8, [rsp+40]
    call GetModuleHandleExW
    test eax, eax
    jz resource_path_fail
    mov rsi, QWORD PTR [rbx+72]
    mov rcx, QWORD PTR [rsp+40]
    mov rdx, rsi
    mov r8d, 32768
    call GetModuleFileNameW
    test eax, eax
    jz resource_path_fail
    cmp eax, 32768
    jae resource_path_fail
    mov ecx, eax
resource_path_separator:
    test ecx, ecx
    jz resource_path_fail
    dec ecx
    cmp WORD PTR [rsi+rcx*2], 92
    je resource_path_append
    cmp WORD PTR [rsi+rcx*2], 47
    jne resource_path_separator
resource_path_append:
    inc ecx
    lea eax, [rcx+15]
    cmp eax, 32768
    ja resource_path_fail
    lea rdx, resource_filename
    xor eax, eax
resource_path_copy:
    movzx r8d, WORD PTR [rdx+rax*2]
    mov WORD PTR [rsi+rcx*2], r8w
    inc ecx
    inc eax
    test r8d, r8d
    jnz resource_path_copy
    mov eax, 2
    xchg DWORD PTR [rbx+8], eax
resource_path_yes:
    mov eax, 1
    jmp resource_path_done
resource_path_wait:
    pause
    jmp resource_path_state
resource_path_fail:
    mov eax, 3
    xchg DWORD PTR [rbx+8], eax
resource_path_no:
    xor eax, eax
resource_path_done:
    add rsp, 56
    pop rsi
    pop rbx
    ret
resource_path ENDP

boom_resource_bytes PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    push rbp
    .pushreg rbp
    push r12
    .pushreg r12
    push r13
    .pushreg r13
    push r14
    .pushreg r14
    push r15
    .pushreg r15
    sub rsp, 232
    .allocstack 232
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov r12, r8
    mov rdi, r9
    xor r13d, r13d
    mov r14, -1
    test rdi, rdi
    jz resource_noctx
    cmp DWORD PTR [rdi], 0
    jne resource_done
    test rbx, rbx
    jz resource_bad
    test rsi, rsi
    jz resource_bad
    test r12, r12
    jz resource_bad
    cmp DWORD PTR [rbx], 048454150h
    jne resource_bad
    cmp DWORD PTR [rbx+4], 1
    jne resource_bad
    cmp DWORD PTR [rsi], 052455350h
    jne resource_bad
    cmp DWORD PTR [rsi+4], 1
    jne resource_bad
    cmp DWORD PTR [rsi+12], 4096
    ja resource_bad
    cmp DWORD PTR [rsi+32], 16384
    ja resource_bad
    cmp DWORD PTR [rsi+36], 1024
    ja resource_bad
    cmp QWORD PTR [rsi+56], 64
    jb resource_bad
    mov eax, 080000000h
    cmp QWORD PTR [rsi+56], rax
    ja resource_bad
    mov rax, QWORD PTR [r12+16]
    mov edx, DWORD PTR [rsi+36]
    cmp rax, rdx
    jae resource_bad
    mov rcx, QWORD PTR [rsi+40]
    test rcx, rcx
    jz resource_bad
    mov eax, DWORD PTR [rcx+rax*4]
    mov DWORD PTR [rsp+188], eax
    mov rcx, rdi
    mov rdx, QWORD PTR [r12]
    mov r8, QWORD PTR [rsi+64]
    call boom_mirror_typeid
    cmp eax, -1
    je resource_done
    cmp eax, DWORD PTR [rsi+32]
    jae resource_bad
    mov rdx, QWORD PTR [rsi+64]
    cmp QWORD PTR [rdx+48], rbx
    jne resource_bad
    shl rax, 4
    mov rbp, QWORD PTR [rsi+24]
    test rbp, rbp
    jz resource_bad
    add rbp, rax
    mov eax, DWORD PTR [rbp+12]
    cmp eax, DWORD PTR [rsi+12]
    ja resource_bad
    mov DWORD PTR [rsp+184], eax
    mov rcx, QWORD PTR [r12+8]
    mov rdx, QWORD PTR [rsi+64]
    mov rdx, QWORD PTR [rdx+40]
    mov rdx, QWORD PTR [rdx+40]
    mov r8, rdi
    call boom_string_view
    cmp DWORD PTR [rdi], 0
    jne resource_done
    mov r12, rax
    mov r15d, edx
    mov r8d, DWORD PTR [rbp+8]
    test edx, edx
    jz resource_relative
    cmp WORD PTR [r12], 47
    jne resource_relative
    add r12, 2
    dec r15d
    xor r8d, r8d
resource_relative:
    mov DWORD PTR [rsp+208], r8d
    mov edx, r15d
    add edx, r8d
    jc resource_bad
    test edx, edx
    js resource_bad
    mov DWORD PTR [rsp+212], edx
    ; Absolute names (and default-package relative names) already have the exact
    ; immutable UTF16 view; avoid allocating a duplicate query array.
    cmp DWORD PTR [rsp+208], 0
    jne resource_query_allocate
    mov QWORD PTR [rsp+176], r12
    jmp resource_lookup_start
resource_query_allocate:
    mov rcx, rbx
    mov r8d, 5
    mov r9, rdi
    call boom_array_new
    test rax, rax
    jz resource_done
    mov QWORD PTR [rsp+176], rax
    mov r10, QWORD PTR [rbp]
    xor ecx, ecx
resource_copy_prefix:
    cmp ecx, DWORD PTR [rsp+208]
    jae resource_copy_name_start
    movzx edx, WORD PTR [r10+rcx*2]
    mov WORD PTR [rax+rcx*2], dx
    inc ecx
    jmp resource_copy_prefix
resource_copy_name_start:
    lea r10, [rax+rcx*2]
    xor ecx, ecx
resource_copy_name:
    cmp ecx, r15d
    jae resource_lookup_start
    movzx edx, WORD PTR [r12+rcx*2]
    mov WORD PTR [r10+rcx*2], dx
    inc ecx
    jmp resource_copy_name
resource_lookup_start:
    mov r12, QWORD PTR [rsp+176]
    mov r15d, DWORD PTR [rsp+212]
    mov DWORD PTR [rsp+192], 0
    mov eax, DWORD PTR [rsp+184]
    test eax, eax
    jz resource_provider_next
    dec eax
    mov DWORD PTR [rsp+192], eax
resource_provider_next:
    mov eax, DWORD PTR [rsp+192]
    cmp eax, DWORD PTR [rsi+12]
    jae resource_done
    imul rax, 40
    mov rbp, QWORD PTR [rsi+16]
    test rbp, rbp
    jz resource_bad
    add rbp, rax
    cmp DWORD PTR [rbp], 1
    ja resource_bad
    cmp DWORD PTR [rbp], 0
    je resource_provider_search
    mov ecx, DWORD PTR [rsp+184]
    test ecx, ecx
    jz resource_parent_access
    cmp ecx, DWORD PTR [rsp+188]
    je resource_provider_search
    mov r9d, 1
    cmp DWORD PTR [rsp+188], 0
    je resource_check_access
    mov r9d, 3
    jmp resource_check_access
resource_parent_access:
    mov r9d, 1
resource_check_access:
    mov rcx, rbp
    mov rdx, r12
    mov r8d, r15d
    call resource_allowed
    test eax, eax
    jz resource_provider_skip
resource_provider_search:
    mov rcx, r12
    mov edx, r15d
    mov r8, QWORD PTR [rbp+16]
    mov r9d, DWORD PTR [rbp+8]
    cmp r9d, 262144
    ja resource_bad
    mov r10d, 40
    call resource_search
    test rax, rax
    jnz resource_found
resource_provider_skip:
    cmp DWORD PTR [rsp+184], 0
    jne resource_done
    inc DWORD PTR [rsp+192]
    jmp resource_provider_next
resource_found:
    ; The pinned JDK's JarURLConnection URL decoding rejects surrogate code
    ; units encoded by ParseUtil.encodePath. Module-reader opens do not use it.
    cmp DWORD PTR [rbp], 0
    jne resource_found_valid
    xor ecx, ecx
resource_jar_url_name:
    cmp ecx, r15d
    jae resource_found_valid
    movzx edx, WORD PTR [r12+rcx*2]
    sub edx, 0D800h
    cmp edx, 07FFh
    jbe resource_bad_jar_url
    inc ecx
    jmp resource_jar_url_name
resource_found_valid:
    mov rbp, rax
    cmp QWORD PTR [rbp+16], 64
    jb resource_bad
    cmp QWORD PTR [rbp+24], 67108864
    ja resource_bad
    mov rax, QWORD PTR [rbp+16]
    add rax, QWORD PTR [rbp+24]
    jc resource_bad
    cmp rax, QWORD PTR [rsi+56]
    ja resource_bad
    mov rcx, rsi
    call resource_path
    test eax, eax
    jz resource_bad
    mov rcx, QWORD PTR [rsi+72]
    mov edx, 080000000h
    mov r8d, 1
    xor r9d, r9d
    mov QWORD PTR [rsp+32], 3
    mov QWORD PTR [rsp+40], 080h
    mov QWORD PTR [rsp+48], 0
    call CreateFileW
    cmp rax, -1
    je resource_bad
    mov r14, rax
    mov rcx, r14
    lea rdx, [rsp+72]
    call GetFileSizeEx
    test eax, eax
    jz resource_bad
    mov rax, QWORD PTR [rsp+72]
    cmp rax, QWORD PTR [rsi+56]
    jne resource_bad
    mov rcx, r14
    lea rdx, [rsp+80]
    mov r8d, 64
    lea r9, [rsp+64]
    mov QWORD PTR [rsp+32], 0
    call ReadFile
    test eax, eax
    jz resource_bad
    cmp DWORD PTR [rsp+64], 64
    jne resource_bad
    mov rax, 0315345524D4F4F42h
    cmp QWORD PTR [rsp+80], rax
    jne resource_bad
    cmp DWORD PTR [rsp+88], 1
    jne resource_bad
    cmp DWORD PTR [rsp+92], 64
    jne resource_bad
    mov rax, QWORD PTR [rsp+96]
    cmp rax, QWORD PTR [rsi+56]
    jne resource_bad
    cmp QWORD PTR [rsp+136], 0
    jne resource_bad
    mov r10, QWORD PTR [rsi+48]
    xor ecx, ecx
resource_header_hash:
    mov rax, QWORD PTR [r10+rcx*8]
    cmp QWORD PTR [rsp+104+rcx*8], rax
    jne resource_bad
    inc ecx
    cmp ecx, 4
    jb resource_header_hash
    mov rcx, r14
    mov rdx, QWORD PTR [rbp+16]
    xor r8d, r8d
    xor r9d, r9d
    call SetFilePointerEx
    test eax, eax
    jz resource_bad
    mov rcx, rbx
    mov edx, DWORD PTR [rbp+24]
    mov r8d, 8
    mov r9, rdi
    call boom_array_new
    test rax, rax
    jz resource_done
    mov r13, rax
    cmp QWORD PTR [rbp+24], 0
    je resource_payload_hash
    mov rcx, r14
    mov rdx, r13
    mov r8d, DWORD PTR [rbp+24]
    lea r9, [rsp+64]
    mov QWORD PTR [rsp+32], 0
    call ReadFile
    test eax, eax
    jz resource_io_failure
    mov eax, DWORD PTR [rsp+64]
    cmp rax, QWORD PTR [rbp+24]
    jne resource_bad
resource_payload_hash:
    mov ecx, 041h ; Windows 10 BCRYPT_SHA256_ALG_HANDLE pseudo-handle
    xor edx, edx
    xor r8d, r8d
    mov r9, r13
    mov rax, QWORD PTR [rbp+24]
    mov QWORD PTR [rsp+32], rax
    lea rax, [rsp+144]
    mov QWORD PTR [rsp+40], rax
    mov QWORD PTR [rsp+48], 32
    call BCryptHash
    test eax, eax
    js resource_bad
    mov r10, QWORD PTR [rbp+32]
    xor ecx, ecx
resource_payload_check:
    mov rax, QWORD PTR [r10+rcx*8]
    cmp QWORD PTR [rsp+144+rcx*8], rax
    jne resource_bad
    inc ecx
    cmp ecx, 4
    jb resource_payload_check
    jmp resource_done
resource_io_failure:
    jmp resource_bad
resource_bad:
    mov DWORD PTR [rdi], 7
    xor r13d, r13d
    jmp resource_done
resource_bad_jar_url:
    mov DWORD PTR [rdi], 18
    xor r13d, r13d
resource_done:
    cmp r14, -1
    je resource_return
    mov rcx, r14
    call CloseHandle
resource_return:
    mov rax, r13
    jmp resource_epilogue
resource_noctx:
    xor eax, eax
resource_epilogue:
    add rsp, 232
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rdi
    pop rsi
    pop rbx
    ret
boom_resource_bytes ENDP
END
