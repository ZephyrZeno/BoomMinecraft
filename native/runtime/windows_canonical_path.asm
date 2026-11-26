; Read-only Windows path canonicalization. No CRT, Java heap, or global lock.
; canonical(inputUTF16, units, outputUTF16, capacityUnits, outputUnits*)
; driveDirectory(drive1to26, outputUTF16, capacityUnits, outputUnits*)
; Both return zero on success, a Win32 error otherwise. FFFFFFFFh is a
; logical pathname failure without an OS error. 8 is native scratch OOM.
; Capacity includes the NUL. Failure leaves output untouched and length zero.
; Buffers belong to the caller. Process CWD must remain stable during a call.
option casemap:none
EXTERN GetProcessHeap:PROC
EXTERN HeapAlloc:PROC
EXTERN HeapFree:PROC
EXTERN GetFullPathNameW:PROC
EXTERN GetCurrentDirectoryW:PROC
EXTERN GetDriveTypeW:PROC
EXTERN FindFirstFileW:PROC
EXTERN FindClose:PROC
EXTERN GetLastError:PROC
PUBLIC boom_windows_canonical_path
PUBLIC boom_windows_drive_directory

.code
boom_windows_drive_directory PROC FRAME
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
 sub rsp,608
 .allocstack 608
 .endprolog
 mov r12d,ecx
 mov rdi,rdx
 mov esi,r8d
 mov r13,r9
 test r13,r13
 jz wdd_bad
 mov DWORD PTR [r13],0
 test rdi,rdi
 jz wdd_bad
 test esi,esi
 jz wdd_short
 cmp r12d,1
 jb wdd_missing
 cmp r12d,26
 ja wdd_missing
 mov eax,r12d
 add eax,64
 mov WORD PTR [rsp+40],ax
 mov WORD PTR [rsp+42],58
 mov WORD PTR [rsp+44],92
 mov WORD PTR [rsp+46],0
 lea rcx,[rsp+40]
 call GetDriveTypeW
 cmp eax,1
 jbe wdd_missing
 mov WORD PTR [rsp+44],46
 lea rcx,[rsp+40]
 mov edx,260
 lea r8,[rsp+64]
 xor r9d,r9d
 call GetFullPathNameW
 test eax,eax
 jz wdd_os_error
 cmp eax,260
 jae wdd_long
 mov ebx,eax
 lea rdx,[rsp+64]
 movzx ecx,WORD PTR [rdx]
 or ecx,32
 sub ecx,97
 cmp ecx,25
 ja wdd_copy_check
 cmp WORD PTR [rdx+2],58
 jne wdd_copy_check
 add rdx,4
 sub ebx,2
wdd_copy_check:
 cmp ebx,esi
 jae wdd_short
 xor ecx,ecx
wdd_copy:
 mov ax,WORD PTR [rdx+rcx*2]
 mov WORD PTR [rdi+rcx*2],ax
 inc ecx
 cmp ecx,ebx
 jbe wdd_copy
 mov DWORD PTR [r13],ebx
 xor eax,eax
 jmp wdd_done
wdd_os_error:
 call GetLastError
 test eax,eax
 jnz wdd_done
wdd_missing:
 mov eax,15
 jmp wdd_done
wdd_long:
 mov eax,206
 jmp wdd_done
wdd_short:
 mov eax,122
 jmp wdd_done
wdd_bad:
 mov eax,87
wdd_done:
 add rsp,608
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_windows_drive_directory ENDP

boom_windows_canonical_path PROC FRAME
 push rbx
 .pushreg rbx
 push rbp
 .pushreg rbp
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
 sub rsp,760
 .allocstack 760
 .endprolog
 mov rdi,rcx
 mov r12d,edx
 mov r13,r8
 mov r14d,r9d
 mov rax,QWORD PTR [rsp+864]
 mov QWORD PTR [rsp+40],rax
 mov DWORD PTR [rsp+92],0
 xor ebx,ebx
 xor r15d,r15d
 test rax,rax
 jz wcp_bad
 mov DWORD PTR [rax],0
 test rdi,rdi
 jz wcp_bad
 test r13,r13
 jz wcp_bad
 test r14d,r14d
 jz wcp_short
 call GetProcessHeap
 test rax,rax
 jz wcp_oom
 mov rbx,rax
 mov rcx,rax
 xor edx,edx
 mov r8d,262176
 call HeapAlloc
 test rax,rax
 jz wcp_oom
 mov r15,rax
 lea rsi,[r15+65536]
 ; Respect the native C-string boundary, including an early embedded NUL.
 xor ecx,ecx
wcp_input:
 cmp ecx,r12d
 jae wcp_input_end
 cmp ecx,32767
 ja wcp_logical
 movzx eax,WORD PTR [rdi+rcx*2]
 test ax,ax
 jz wcp_input_end
 cmp ecx,32767
 jae wcp_logical
 cmp ax,42
 je wcp_logical
 cmp ax,63
 je wcp_logical
 mov WORD PTR [r15+rcx*2],ax
 inc ecx
 jmp wcp_input
wcp_input_end:
 mov WORD PTR [r15+rcx*2],0
 mov DWORD PTR [rsp+64],ecx
 test ecx,ecx
 jz wcp_empty
 mov rcx,r15
 mov edx,32768
 mov r8,rsi
 xor r9d,r9d
 call GetFullPathNameW
 jmp wcp_full_result
wcp_empty:
 mov ecx,32768
 mov rdx,rsi
 call GetCurrentDirectoryW
wcp_full_result:
 test eax,eax
 jz wcp_os_error
 cmp eax,32768
 jae wcp_logical
 mov DWORD PTR [rsp+68],eax
 ; Match the source native's 1024 / input-length + current-dir budget.
 cmp DWORD PTR [rsp+64],2
 jbe wcp_cwd_budget
 cmp WORD PTR [r15+2],58
 jne wcp_cwd_budget
 cmp WORD PTR [r15+4],92
 je wcp_cwd_budget
 movzx ecx,WORD PTR [r15]
 or ecx,32
 sub ecx,96
 cmp ecx,1
 jb wcp_no_drive_budget
 cmp ecx,26
 ja wcp_no_drive_budget
 lea rdx,[r15+196608]
 mov r8d,260
 lea r9,[rsp+100]
 call boom_windows_drive_directory
 test eax,eax
 jnz wcp_no_drive_budget
 mov eax,DWORD PTR [rsp+100]
 add eax,2
 jmp wcp_budget_ready
wcp_no_drive_budget:
 xor eax,eax
 jmp wcp_budget_ready
wcp_cwd_budget:
 xor ecx,ecx
 xor edx,edx
 call GetCurrentDirectoryW
 test eax,eax
 jz wcp_os_error
 dec eax
wcp_budget_ready:
 add eax,DWORD PTR [rsp+64]
 mov ebp,1024
 cmp eax,ebp
 cmova ebp,eax
 cmp DWORD PTR [rsp+68],ebp
 jae wcp_logical
 ; Prohibit trailing runs of dots after full-path dot/dot-dot collapse.
 xor ecx,ecx
 cmp DWORD PTR [rsp+68],4
 jbe wcp_dots
 cmp DWORD PTR [rsi],005C005Ch
 jne wcp_dots
 cmp DWORD PTR [rsi+4],005C002Eh
 jne wcp_dots
 mov ecx,4
wcp_dots:
 movzx eax,WORD PTR [rsi+rcx*2]
 test ax,ax
 jz wcp_prefix
 inc ecx
 cmp ax,46
 jne wcp_dots
wcp_dot_run:
 movzx eax,WORD PTR [rsi+rcx*2]
 cmp ax,46
 jne wcp_dot_end
 inc ecx
 jmp wcp_dot_run
wcp_dot_end:
 test ax,ax
 jz wcp_logical
 cmp ax,92
 je wcp_logical
 inc ecx
 jmp wcp_dots
wcp_prefix:
 lea rdi,[r15+131072]
 lea r12,[rsp+144]
 movzx eax,WORD PTR [rsi]
 or eax,32
 sub eax,97
 cmp eax,25
 ja wcp_unc_prefix
 cmp WORD PTR [rsi+2],58
 jne wcp_unc_prefix
 cmp WORD PTR [rsi+4],92
 jne wcp_unc_prefix
 and WORD PTR [rsi],0FFDFh
 mov eax,DWORD PTR [rsi]
 mov DWORD PTR [rdi],eax
 mov DWORD PTR [rsp+80],2
 mov DWORD PTR [rsp+84],2
 jmp wcp_component
wcp_unc_prefix:
 cmp DWORD PTR [rsi],005C005Ch
 jne wcp_logical
 mov ecx,2
wcp_unc_host:
 movzx eax,WORD PTR [rsi+rcx*2]
 test ax,ax
 jz wcp_logical
 inc ecx
 cmp ax,92
 jne wcp_unc_host
wcp_unc_share:
 movzx eax,WORD PTR [rsi+rcx*2]
 test ax,ax
 jz wcp_copy_unc
 cmp ax,92
 je wcp_copy_unc
 inc ecx
 jmp wcp_unc_share
wcp_copy_unc:
 mov DWORD PTR [rsp+80],ecx
 mov DWORD PTR [rsp+84],ecx
 xor edx,edx
wcp_unc_copy_loop:
 cmp edx,ecx
 jae wcp_component
 mov ax,WORD PTR [rsi+rdx*2]
 mov WORD PTR [rdi+rdx*2],ax
 inc edx
 jmp wcp_unc_copy_loop
wcp_component:
 mov ecx,DWORD PTR [rsp+80]
 cmp WORD PTR [rsi+rcx*2],0
 je wcp_finish
 cmp WORD PTR [rsi+rcx*2],92
 jne wcp_logical
 lea edx,[rcx+1]
wcp_component_end:
 movzx eax,WORD PTR [rsi+rdx*2]
 test ax,ax
 jz wcp_query
 cmp ax,92
 je wcp_query
 inc edx
 jmp wcp_component_end
wcp_query:
 mov DWORD PTR [rsp+88],edx
 mov WORD PTR [rsp+76],ax
 mov WORD PTR [rsi+rdx*2],0
 mov rcx,rsi
 cmp edx,259
 jbe wcp_query_call
 lea r8,[r15+196608]
 mov DWORD PTR [r8],005C005Ch
 mov DWORD PTR [r8+4],005C003Fh
 mov ecx,4
 xor edx,edx
 cmp DWORD PTR [rsi],005C005Ch
 jne wcp_extended_copy
 cmp DWORD PTR [rsi+4],005C003Fh
 je wcp_query_original
 mov DWORD PTR [r8+8],004E0055h
 mov DWORD PTR [r8+12],005C0043h
 mov ecx,8
 mov edx,2
wcp_extended_copy:
 mov ax,WORD PTR [rsi+rdx*2]
 mov WORD PTR [r8+rcx*2],ax
 inc ecx
 inc edx
 test ax,ax
 jnz wcp_extended_copy
 mov rcx,r8
 jmp wcp_query_call
wcp_query_original:
 mov rcx,rsi
wcp_query_call:
 mov rdx,r12
 call FindFirstFileW
 mov r8,rax
 mov ecx,DWORD PTR [rsp+88]
 mov ax,WORD PTR [rsp+76]
 mov WORD PTR [rsi+rcx*2],ax
 cmp r8,-1
 je wcp_lookup_failed
 mov rcx,r8
 call FindClose
 xor ecx,ecx
wcp_name_length:
 cmp ecx,260
 jae wcp_logical
 cmp WORD PTR [r12+rcx*2+44],0
 je wcp_copy_name
 inc ecx
 jmp wcp_name_length
wcp_copy_name:
 mov edx,DWORD PTR [rsp+84]
 lea eax,[rdx+rcx+1]
 cmp eax,ebp
 jae wcp_logical
 cmp eax,32768
 jae wcp_logical
 mov WORD PTR [rdi+rdx*2],92
 inc edx
 xor r8d,r8d
wcp_name_copy_loop:
 cmp r8d,ecx
 jae wcp_name_copied
 mov ax,WORD PTR [r12+r8*2+44]
 mov WORD PTR [rdi+rdx*2],ax
 inc r8d
 inc edx
 jmp wcp_name_copy_loop
wcp_name_copied:
 mov DWORD PTR [rsp+84],edx
 mov eax,DWORD PTR [rsp+88]
 mov DWORD PTR [rsp+80],eax
 jmp wcp_component
wcp_lookup_failed:
 call GetLastError
 cmp eax,2
 je wcp_copy_suffix
 cmp eax,3
 je wcp_copy_suffix
 cmp eax,5
 je wcp_copy_suffix
 cmp eax,18
 je wcp_copy_suffix
 cmp eax,53
 je wcp_copy_suffix
 cmp eax,65
 je wcp_copy_suffix
 cmp eax,67
 je wcp_copy_suffix
 cmp eax,267
 je wcp_copy_suffix
 cmp eax,1231
 jne wcp_error_code
wcp_copy_suffix:
 mov ecx,DWORD PTR [rsp+80]
 mov edx,DWORD PTR [rsp+84]
 mov eax,DWORD PTR [rsp+68]
 sub eax,ecx
 add eax,edx
 cmp eax,ebp
 jae wcp_logical
 cmp eax,32768
 jae wcp_logical
wcp_suffix_loop:
 mov ax,WORD PTR [rsi+rcx*2]
 test ax,ax
 jz wcp_suffix_done
 mov WORD PTR [rdi+rdx*2],ax
 inc ecx
 inc edx
 jmp wcp_suffix_loop
wcp_suffix_done:
 mov DWORD PTR [rsp+84],edx
wcp_finish:
 mov ecx,DWORD PTR [rsp+84]
 cmp ecx,r14d
 jae wcp_short
 mov WORD PTR [rdi+rcx*2],0
 xor edx,edx
wcp_publish:
 mov ax,WORD PTR [rdi+rdx*2]
 mov WORD PTR [r13+rdx*2],ax
 inc edx
 cmp edx,ecx
 jbe wcp_publish
 mov rax,QWORD PTR [rsp+40]
 mov DWORD PTR [rax],ecx
 jmp wcp_cleanup
wcp_os_error:
 call GetLastError
wcp_error_code:
 test eax,eax
 jz wcp_logical
 mov DWORD PTR [rsp+92],eax
 jmp wcp_cleanup
wcp_bad:
 mov DWORD PTR [rsp+92],87
 jmp wcp_cleanup
wcp_short:
 mov DWORD PTR [rsp+92],122
 jmp wcp_cleanup
wcp_logical:
 mov DWORD PTR [rsp+92],0FFFFFFFFh
 jmp wcp_cleanup
wcp_oom:
 mov DWORD PTR [rsp+92],8
wcp_cleanup:
 test r15,r15
 jz wcp_done
 mov rcx,rbx
 xor edx,edx
 mov r8,r15
 call HeapFree
wcp_done:
 mov eax,DWORD PTR [rsp+92]
 add rsp,760
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_windows_canonical_path ENDP
END
