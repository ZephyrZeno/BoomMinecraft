; Original sun.io.Win32ErrorMode native contract: low UINT input, unsigned UINT
; previous process mode widened to Java long. Actual Windows API; no host shim.
option casemap:none
EXTERN SetErrorMode:PROC
PUBLIC boom_windows_error_mode
.code
boom_windows_error_mode PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    test rcx,rcx
    jz windows_error_mode_none
    cmp DWORD PTR [rcx],0
    jne windows_error_mode_none
    test rdx,rdx
    jz windows_error_mode_bad
    mov ecx,DWORD PTR [rdx]
    call SetErrorMode
    mov eax,eax
    jmp windows_error_mode_done
windows_error_mode_bad:
    mov DWORD PTR [rcx],7
windows_error_mode_none:
    xor eax,eax
windows_error_mode_done:
    add rsp,40
    ret
boom_windows_error_mode ENDP
END
