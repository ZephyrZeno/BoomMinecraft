; ScopedMemoryAccess original native registration. SCNP32/1: state8,
; count12=1,target16,reserved24. The close handshake is not implemented yet.
option casemap:none
PUBLIC boom_scoped_native_register
PUBLIC boom_scoped_close_unavailable
.code
; register(Context32 RCX,pool RDX)->void. Preserve preexisting exceptions.
boom_scoped_native_register PROC
    test rcx,rcx
    jz scoped_register_zero
    cmp DWORD PTR [rcx],0
    jne scoped_register_zero
    test rdx,rdx
    jz scoped_register_bad
    cmp DWORD PTR [rdx],0504E4353h
    jne scoped_register_bad
    cmp DWORD PTR [rdx+4],1
    jne scoped_register_bad
    cmp DWORD PTR [rdx+12],1
    jne scoped_register_bad
    cmp QWORD PTR [rdx+24],0
    jne scoped_register_bad
    lea rax,boom_scoped_close_unavailable
    cmp QWORD PTR [rdx+16],rax
    jne scoped_register_bad
    mov eax,DWORD PTR [rdx+8]
    test eax,eax
    jz scoped_register_publish
    cmp eax,2
    jne scoped_register_bad
scoped_register_publish:
    mov eax,2
    xchg DWORD PTR [rdx+8],eax
scoped_register_zero:
    xor eax,eax
    ret
scoped_register_bad:
    mov DWORD PTR [rcx],7
    jmp scoped_register_zero
boom_scoped_native_register ENDP

; Never report a session safe to close without the actual VM handshake.
boom_scoped_close_unavailable PROC
    test rcx,rcx
    jz scoped_close_zero
    cmp DWORD PTR [rcx],0
    jne scoped_close_zero
    mov DWORD PTR [rcx],20
scoped_close_zero:
    xor eax,eax
    ret
boom_scoped_close_unavailable ENDP
END
