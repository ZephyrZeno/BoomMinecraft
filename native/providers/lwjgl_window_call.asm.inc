; JNI.invokePPPP(IIJJJJ)J. Managed argv contains six eight-byte values, including
; the function pointer. Only the GLFW export registered by the owner is callable.
; Binding48: magic/ABI/reserved, immutable Spec24*, approved address, retained
; HMODULE, SRWLOCK. Spec24: file size/RVA, SHA-256 bytes*, ASCII export name*.
; Bind an already-loaded module once per binding and keep one loader reference
; for the VM image lifetime. Registration never calls code in the target DLL.
EXTERN GetModuleHandleExW:PROC
EXTERN GetModuleFileNameW:PROC
EXTERN FreeLibrary:PROC
EXTERN GetProcAddress:PROC
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN CreateFileW:PROC
EXTERN GetFileSizeEx:PROC
EXTERN CreateFileMappingW:PROC
EXTERN MapViewOfFile:PROC
EXTERN UnmapViewOfFile:PROC
EXTERN CloseHandle:PROC
EXTERN BCryptHash:PROC
PUBLIC boom_provider_lwjgl_window_bind
PUBLIC boom_provider_lwjgl_window_call

.code
boom_provider_lwjgl_window_bind PROC FRAME
    ; [rsp+0..55] outgoing arguments, +64 file size, +72 held module,
    ; +80 pool, +88 path, +96 file, +104 mapping, +112 view, +120 input,
    ; +128..159 digest, +160 result.
    sub rsp,168
    .allocstack 168
    .endprolog
    test rcx,rcx
    jz lw_bind_invalid
    test rdx,rdx
    jz lw_bind_invalid
    cmp DWORD PTR [rcx],314A574Ch
    jne lw_bind_invalid
    cmp DWORD PTR [rcx+4],1
    jne lw_bind_invalid
    mov rax,[rcx+16]
    test rax,rax
    jz lw_bind_invalid
    cmp DWORD PTR [rax],0
    je lw_bind_invalid
    cmp DWORD PTR [rax+4],0
    je lw_bind_invalid
    cmp QWORD PTR [rax+8],0
    je lw_bind_invalid
    cmp QWORD PTR [rax+16],0
    je lw_bind_invalid
    mov [rsp+80],rcx
    mov [rsp+120],rdx
    xor eax,eax
    mov [rsp+72],rax
    mov [rsp+88],rax
    mov [rsp+96],rax
    mov [rsp+104],rax
    mov [rsp+112],rax
    lea rcx,[rcx+40]
    call AcquireSRWLockExclusive
    mov rcx,[rsp+80]
    cmp QWORD PTR [rcx+24],0
    je lw_bind_hold
    mov rax,[rsp+120]
    cmp rax,[rcx+32]
    jne lw_bind_other
    xor eax,eax
    jmp lw_bind_finish
lw_bind_other:
    mov eax,170                     ; ERROR_BUSY
    jmp lw_bind_finish
lw_bind_hold:
    mov ecx,4                       ; GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
    mov rdx,[rsp+120]
    lea r8,[rsp+72]
    call GetModuleHandleExW
    test eax,eax
    jz lw_bind_no_module
    mov rax,[rsp+72]
    cmp rax,[rsp+120]               ; an arbitrary interior address is not HMODULE
    jne lw_bind_bad_image
    xor ecx,ecx
    mov edx,65536                   ; full 32K-character Windows path
    mov r8d,3000h
    mov r9d,4
    call VirtualAlloc
    test rax,rax
    jz lw_bind_no_memory
    mov [rsp+88],rax
    mov rcx,[rsp+72]
    mov rdx,rax
    mov r8d,32768
    call GetModuleFileNameW
    test eax,eax
    jz lw_bind_bad_image
    cmp eax,32768
    jae lw_bind_bad_image
    mov rcx,[rsp+88]
    mov edx,80000000h
    mov r8d,1                       ; FILE_SHARE_READ
    xor r9d,r9d
    mov QWORD PTR [rsp+32],3
    mov QWORD PTR [rsp+40],80h
    mov QWORD PTR [rsp+48],0
    call CreateFileW
    cmp rax,-1
    je lw_bind_bad_image
    mov [rsp+96],rax
    mov rcx,rax
    lea rdx,[rsp+64]
    call GetFileSizeEx
    test eax,eax
    jz lw_bind_bad_image
    mov r10,[rsp+80]
    mov r10,[r10+16]
    mov eax,[r10]
    cmp rax,[rsp+64]
    jne lw_bind_bad_image
    mov rcx,[rsp+96]
    xor edx,edx
    mov r8d,2                       ; PAGE_READONLY
    xor r9d,r9d
    mov QWORD PTR [rsp+32],0
    mov QWORD PTR [rsp+40],0
    call CreateFileMappingW
    test rax,rax
    jz lw_bind_bad_image
    mov [rsp+104],rax
    mov rcx,rax
    mov edx,4                       ; FILE_MAP_READ
    xor r8d,r8d
    xor r9d,r9d
    mov QWORD PTR [rsp+32],0
    call MapViewOfFile
    test rax,rax
    jz lw_bind_bad_image
    mov [rsp+112],rax
    mov ecx,41h                     ; BCRYPT_SHA256_ALG_HANDLE
    xor edx,edx
    xor r8d,r8d
    mov r9,rax
    mov eax,DWORD PTR [rsp+64]
    mov [rsp+32],rax
    lea rax,[rsp+128]
    mov [rsp+40],rax
    mov QWORD PTR [rsp+48],32
    call BCryptHash
    test eax,eax
    js lw_bind_bad_image
    mov r10,[rsp+80]
    mov r10,[r10+16]
    mov r11,[r10+8]
    xor edx,edx
lw_bind_compare:
    mov rax,[rsp+rdx+128]
    cmp rax,[r11+rdx]
    jne lw_bind_bad_image
    add edx,8
    cmp edx,32
    jb lw_bind_compare
    mov rcx,[rsp+72]
    mov rdx,[r10+16]
    call GetProcAddress
    test rax,rax
    jz lw_bind_no_export
    mov rcx,[rsp+80]
    mov r10,[rcx+16]
    mov r11d,[r10+4]                ; locked, executable non-forwarded PE export
    mov rdx,[rsp+72]
    add r11,rdx
    cmp rax,r11
    jne lw_bind_bad_image
    mov [rcx+32],rdx
    mov QWORD PTR [rsp+72],0        ; transfer loader reference before publication
    xchg QWORD PTR [rcx+24],rax
    xor eax,eax
    jmp lw_bind_finish
lw_bind_no_memory:
    mov eax,8
    jmp lw_bind_finish
lw_bind_no_module:
    mov eax,126
    jmp lw_bind_finish
lw_bind_no_export:
    mov eax,127
    jmp lw_bind_finish
lw_bind_bad_image:
    mov eax,13                      ; ERROR_INVALID_DATA
lw_bind_finish:
    mov [rsp+160],eax
    mov rcx,[rsp+112]
    test rcx,rcx
    jz lw_bind_mapping
    call UnmapViewOfFile
lw_bind_mapping:
    mov rcx,[rsp+104]
    test rcx,rcx
    jz lw_bind_file
    call CloseHandle
lw_bind_file:
    mov rcx,[rsp+96]
    test rcx,rcx
    jz lw_bind_path
    call CloseHandle
lw_bind_path:
    mov rcx,[rsp+88]
    test rcx,rcx
    jz lw_bind_unlock
    xor edx,edx
    mov r8d,8000h
    call VirtualFree
lw_bind_unlock:
    mov rcx,[rsp+80]
    add rcx,40
    call ReleaseSRWLockExclusive
    ; A rejected caller can give us the last loader reference. Release the
    ; binding lock before FreeLibrary, which is allowed to run a DLL callback.
    mov rcx,[rsp+72]
    test rcx,rcx
    jz lw_bind_result
    call FreeLibrary
lw_bind_result:
    mov eax,[rsp+160]
    add rsp,168
    ret
lw_bind_invalid:
    mov eax,87
    add rsp,168
    ret
boom_provider_lwjgl_window_bind ENDP

boom_provider_lwjgl_window_call PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    test rcx,rcx
    jz lw_call_zero
    cmp DWORD PTR [rcx],0
    jne lw_call_zero
    test r9d,r9d
    jnz lw_call_invalid
    test rdx,rdx
    jz lw_call_invalid
    test r8,r8
    jz lw_call_invalid
    cmp DWORD PTR [r8],314A574Ch
    jne lw_call_invalid
    cmp DWORD PTR [r8+4],1
    jne lw_call_invalid
    mov r11,[r8+24]
    test r11,r11
    jz lw_call_unbound
    cmp r11,[rdx+40]
    jne lw_call_unbound
    mov r10,rdx
    mov ecx,[r10]
    mov edx,[r10+8]
    mov r8,[r10+16]
    mov r9,[r10+24]
    mov rax,[r10+32]
    mov [rsp+32],rax
    call r11
    add rsp,40
    ret
lw_call_invalid:
    mov DWORD PTR [rcx],7
    jmp lw_call_zero
lw_call_unbound:
    mov DWORD PTR [rcx],20
lw_call_zero:
    xor eax,eax
    add rsp,40
    ret
boom_provider_lwjgl_window_call ENDP
