; Original Win32ErrorMode low UINT -> previous unsigned UINT widened to J64.
.code
PUBLIC boom_provider_windows_startup_service
boom_provider_windows_startup_service PROC
 test rcx,rcx
 jz provider_windows_startup_zero
 cmp DWORD PTR [rcx],0
 jne provider_windows_startup_zero
 test r9d,r9d
 jnz provider_windows_startup_bad
 jmp boom_windows_error_mode
provider_windows_startup_bad:
 mov DWORD PTR [rcx],7
provider_windows_startup_zero:
 xor eax,eax
 ret
boom_provider_windows_startup_service ENDP
