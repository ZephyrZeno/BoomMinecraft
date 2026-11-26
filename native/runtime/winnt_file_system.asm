; WinNTFileSystem.initIDs. WFSI48/1: FileLayout8,pathOffset16,
; finalPathTarget24,kernelModule32,state40,reserved44. State0/1/2.
; Native callers provide immutable, source-verified VM layout metadata.
option casemap:none
EXTERN __imp_CreateFileW:QWORD
EXTERN GetModuleHandleExW:PROC
EXTERN GetProcAddress:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
PUBLIC boom_winfs_init
.const
winfs_final_path_name BYTE 'GetFinalPathNameByHandleW',0
.code
boom_winfs_init PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,56
    .allocstack 56
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    test rbx,rbx
    jz winfs_init_zero
    cmp DWORD PTR [rbx],0
    jne winfs_init_zero
    test rsi,rsi
    jz winfs_init_bad
    cmp DWORD PTR [rsi],049534657h
    jne winfs_init_bad
    cmp DWORD PTR [rsi+4],1
    jne winfs_init_bad
    cmp DWORD PTR [rsi+44],0
    jne winfs_init_bad
    mov rax,QWORD PTR [rsi+8]
    test rax,rax
    jz winfs_init_bad
    cmp DWORD PTR [rax],04F424A43h
    jne winfs_init_bad
    cmp DWORD PTR [rax+4],2
    jne winfs_init_bad
    mov rdx,QWORD PTR [rsi+16]
    test dl,7
    jnz winfs_init_bad
    mov ecx,DWORD PTR [rax+16]
    cmp ecx,4096
    ja winfs_init_bad
    cmp ecx,DWORD PTR [rax+20]
    ja winfs_init_bad
    shl rcx,3
    cmp rcx,QWORD PTR [rax+8]
    ja winfs_init_bad
    cmp rdx,rcx
    jae winfs_init_bad
    add rdx,8
    cmp rdx,QWORD PTR [rax+8]
    ja winfs_init_bad
winfs_init_state:
    mov eax,DWORD PTR [rsi+40]
    cmp eax,2
    je winfs_init_zero
    cmp eax,1
    je winfs_init_wait
    test eax,eax
    jnz winfs_init_bad
    mov edx,1
    lock cmpxchg DWORD PTR [rsi+40],edx
    jne winfs_init_state
    mov QWORD PTR [rsp+40],0
    mov ecx,6 ; FROM_ADDRESS | UNCHANGED_REFCOUNT
    mov rdx,QWORD PTR [__imp_CreateFileW]
    lea r8,[rsp+40]
    call GetModuleHandleExW
    test eax,eax
    jz winfs_init_publish
    mov rcx,QWORD PTR [rsp+40]
    mov QWORD PTR [rsi+32],rcx
    lea rdx,winfs_final_path_name
    call GetProcAddress
    mov QWORD PTR [rsi+24],rax
winfs_init_publish:
    mov DWORD PTR [rsi+40],2
    lea rcx,[rsi+40]
    call WakeByAddressAll
    jmp winfs_init_zero
winfs_init_wait:
    mov DWORD PTR [rsp+32],1
    lea rcx,[rsi+40]
    lea rdx,[rsp+32]
    mov r8d,4
    mov r9d,-1
    call WaitOnAddress
    jmp winfs_init_state
winfs_init_bad:
    mov DWORD PTR [rbx],7
winfs_init_zero:
    xor eax,eax
    add rsp,56
    pop rsi
    pop rbx
    ret
boom_winfs_init ENDP
END
