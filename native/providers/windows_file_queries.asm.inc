; Seven original readonly WinNTFileSystem natives. No persistent native paths.
; WFQY40/1: heapCell8, published WNFS pool16, inherited File.path FMAP24,
; independent source PROP112/2 String factory32. Context32 + original argv.
.const
wfq_name_max_error WORD 67,111,117,108,100,32,110,111,116,32,103,101,116,32,109,97,120,105,109,117,109,32,99,111,109,112,111,110,101,110,116,32,108,101,110,103,116,104
.data
ALIGN 8
PUBLIC boom_windows_file_queries_owned_buffers
boom_windows_file_queries_owned_buffers QWORD 0
.code
PUBLIC boom_provider_windows_file_queries_service
boom_provider_windows_file_queries_service PROC FRAME
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
 sub rsp,176
 .allocstack 176
 .endprolog
 mov rbx,rcx
 mov rsi,r8
 mov r12,rdx
 mov r13d,r9d
 xor edi,edi
 mov QWORD PTR [rsp+96],0
 test rbx,rbx
 jz wfq_service_return
 cmp DWORD PTR [rbx],0
 jne wfq_service_return
 cmp r13d,6
 ja wfq_service_bad
 test rsi,rsi
 jz wfq_service_bad
 cmp DWORD PTR [rsi],059514657h
 jne wfq_service_bad
 cmp DWORD PTR [rsi+4],1
 jne wfq_service_bad
 cmp QWORD PTR [rsi+8],0
 je wfq_service_bad
 cmp QWORD PTR [rsi+32],0
 je wfq_service_bad
 cmp r13d,3
 je wfq_service_roots
 test r12,r12
 jz wfq_service_bad
 mov rdx,QWORD PTR [r12]
 test rdx,rdx
 jz wfq_service_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 call boom_heap_contains
 test eax,eax
 jz wfq_service_bad
 mov rcx,QWORD PTR [r12]
 lea rdx,WFQ_FS_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz wfq_service_zero
 mov DWORD PTR [rsp+128],0
 cmp r13d,4
 je wfq_service_selector
 cmp r13d,6
 jne wfq_service_argument
wfq_service_selector:
 mov eax,DWORD PTR [r12+16]
 mov DWORD PTR [rsp+128],eax
 cmp r13d,4
 jne wfq_service_argument
 cmp eax,2
 ja wfq_service_bad
wfq_service_argument:
 mov r15,QWORD PTR [r12+8]
 cmp r13d,5
 je wfq_service_string
 ; WNFS initIDs publishes the immutable original source FieldID, not a guessed
 ; receiver offset. Check that publication and use the generated inherited FMAP.
 mov rax,QWORD PTR [rsi+16]
 test rax,rax
 jz wfq_service_bad
 cmp DWORD PTR [rax],053464E57h
 jne wfq_service_bad
 cmp DWORD PTR [rax+4],1
 jne wfq_service_bad
 cmp DWORD PTR [rax+8],2
 jne wfq_service_bad
 mov rdx,QWORD PTR [rax+32]
 test rdx,rdx
 jz wfq_service_bad
 cmp rdx,QWORD PTR [rax+24]
 jne wfq_service_bad
 lea rcx,WFQ_FILE_LAYOUT
 cmp QWORD PTR [rdx],rcx
 jne wfq_service_bad
 cmp DWORD PTR [rdx+8],WFQ_PATH_OFFSET
 jne wfq_service_bad
 cmp DWORD PTR [rdx+12],WFQ_PATH_INDEX
 jne wfq_service_bad
 cmp DWORD PTR [rdx+16],WFQ_FILE_CLASS
 jne wfq_service_bad
 cmp DWORD PTR [rdx+20],8
 jne wfq_service_bad
 test r15,r15
 jz wfq_service_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r15
 call boom_heap_contains
 test eax,eax
 jz wfq_service_bad
 mov rcx,r15
 mov rdx,rbx
 call QWORD PTR [rsi+24]
 test rax,rax
 jz wfq_service_zero
 mov r15,QWORD PTR [rax]
 test r15,r15
 jz wfq_service_null
wfq_service_string:
 xor eax,eax
 mov QWORD PTR [rsp+88],rax
 test r15,r15
 jnz wfq_service_string_check
 cmp r13d,5
 je wfq_service_query
 jmp wfq_service_null
wfq_service_string_check:
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r15
 call boom_heap_contains
 test eax,eax
 jz wfq_service_bad
 mov rcx,r15
 lea rdx,WFQ_STRING_LAYOUT
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz wfq_service_zero
 mov QWORD PTR [rsp+64],r15
 mov rcx,rbx
 lea rdx,[rsp+64]
 call WFQ_LENGTH
 cmp DWORD PTR [rbx],0
 jne wfq_service_zero
 test eax,eax
 js wfq_service_bad
 mov r15d,eax
 mov rcx,rbx
 lea rdx,[rsp+64]
 call WFQ_CHARS
 cmp DWORD PTR [rbx],0
 jne wfq_service_zero
 mov QWORD PTR [rsp+72],rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rax
 call boom_heap_contains
 test eax,eax
 jz wfq_service_bad
 mov r12,QWORD PTR [rsp+72]
 cmp QWORD PTR [r12-8],261
 jne wfq_service_bad
 cmp DWORD PTR [r12-20],0
 jne wfq_service_bad
 mov eax,r15d
 shl rax,1
 cmp QWORD PTR [r12-16],rax
 jne wfq_service_bad
 lea r8,[rax+32]
 mov QWORD PTR [rsp+104],r8
 add r8,65632
 mov QWORD PTR [rsp+144],r8
 call GetProcessHeap
 test rax,rax
 jz wfq_service_oom
 mov r14,rax
 mov rcx,rax
 xor edx,edx
 mov r8,QWORD PTR [rsp+144]
 call HeapAlloc
 test rax,rax
 jz wfq_service_oom
 mov rdi,rax
 lock inc QWORD PTR [boom_windows_file_queries_owned_buffers]
 xor ecx,ecx
wfq_service_copy:
 cmp ecx,r15d
 jae wfq_service_copied
 mov ax,WORD PTR [r12+rcx*2]
 test ax,ax
 jz wfq_service_copied
 mov WORD PTR [rdi+rcx*2],ax
 inc ecx
 jmp wfq_service_copy
wfq_service_copied:
 mov WORD PTR [rdi+rcx*2],0
 mov DWORD PTR [rsp+132],ecx
 mov QWORD PTR [rsp+88],rdi
 cmp r13d,5
 je wfq_service_query
 mov edx,ecx
 mov rcx,rdi
 mov r8,QWORD PTR [rsp+104]
 add r8,rdi
 call wfq_nt_path
 mov QWORD PTR [rsp+88],rax
wfq_service_query:
 mov rcx,QWORD PTR [rsp+88]
 mov edx,r13d
 mov r8d,DWORD PTR [rsp+128]
 call wfq_query
 mov QWORD PTR [rsp+96],rax
 test edx,edx
 jnz wfq_service_throw
 jmp wfq_service_done
wfq_service_roots:
 call GetLogicalDrives
 mov QWORD PTR [rsp+96],rax
 jmp wfq_service_done
wfq_service_throw:
 ; Only getNameMax0 throws for Windows lookup errors. Capture the API's
 ; actual code before any cleanup, then follow jni_util_md's trim sequence.
 mov DWORD PTR [rsp+136],edx
 test rdi,rdi
 jnz wfq_service_error_buffer
 call GetProcessHeap
 test rax,rax
 jz wfq_service_oom
 mov r14,rax
 mov rcx,rax
 xor edx,edx
 mov r8d,1024
 call HeapAlloc
 test rax,rax
 jz wfq_service_oom
 mov rdi,rax
 lock inc QWORD PTR [boom_windows_file_queries_owned_buffers]
wfq_service_error_buffer:
 mov r8d,DWORD PTR [rsp+136]
 cmp r8d,-1
 je wfq_service_default_error
 mov ecx,01200h
 xor edx,edx
 xor r9d,r9d
 mov QWORD PTR [rsp+32],rdi
 mov DWORD PTR [rsp+40],256
 mov QWORD PTR [rsp+48],0
 call FormatMessageW
 cmp eax,256
 jae wfq_service_bad
 mov r8,rdi
 mov r9d,eax
 cmp eax,3
 jbe wfq_service_make_error
 cmp WORD PTR [rdi+rax*2-2],10
 jne wfq_service_trim_cr
 dec eax
wfq_service_trim_cr:
 cmp WORD PTR [rdi+rax*2-2],13
 jne wfq_service_trim_period
 dec eax
wfq_service_trim_period:
 cmp WORD PTR [rdi+rax*2-2],46
 jne wfq_service_error_count
 dec eax
wfq_service_error_count:
 mov r9d,eax
 jmp wfq_service_make_error
wfq_service_default_error:
 lea r8,wfq_name_max_error
 mov r9d,38
wfq_service_make_error:
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+32]
 call boom_java_property_copy
 test rax,rax
 jz wfq_service_zero
 mov QWORD PTR [rsp+120],rax
 lea rcx,WFQ_ERROR_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne wfq_service_zero
 mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,WFQ_ERROR_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz wfq_service_zero
 mov QWORD PTR [rsp+112],rax
 mov rcx,rbx
 lea rdx,[rsp+112]
 call WFQ_ERROR_CTOR
 cmp DWORD PTR [rbx],0
 jne wfq_service_zero
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+112]
 lea r8,boom_runtime_type_map
 lea r9,WFQ_THROWABLE_TYPE
 call boom_exception_set32
 jmp wfq_service_zero
wfq_service_null:
 mov DWORD PTR [rbx],4
 jmp wfq_service_zero
wfq_service_bad:
 mov DWORD PTR [rbx],7
 jmp wfq_service_zero
wfq_service_oom:
 mov DWORD PTR [rbx],3
wfq_service_zero:
 mov QWORD PTR [rsp+96],0
wfq_service_done:
 test rdi,rdi
 jz wfq_service_return
 mov rcx,r14
 xor edx,edx
 mov r8,rdi
 call HeapFree
 test eax,eax
 jz wfq_service_free_failed
 lock dec QWORD PTR [boom_windows_file_queries_owned_buffers]
 jmp wfq_service_return
wfq_service_free_failed:
 cmp DWORD PTR [rbx],0
 jne wfq_service_return
 mov DWORD PTR [rbx],20
 mov QWORD PTR [rsp+96],0
wfq_service_return:
 mov rax,QWORD PTR [rsp+96]
 add rsp,176
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_windows_file_queries_service ENDP

; fileToNTPath's threshold and prefixing, with a fixed process cwd during the
; call. Raw input is retained if the absolute Windows path cannot be produced.
; RCX=NUL-terminated raw path, EDX=effective length, R8=65632 scratch bytes.
wfq_nt_path PROC PRIVATE FRAME
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
 sub rsp,96
 .allocstack 96
 .endprolog
 mov rbx,rcx
 mov edi,edx
 lea rsi,[r8+32]
 test edi,edi
 jz wfq_nt_raw
 cmp edi,2
 jbe wfq_nt_relative
 cmp DWORD PTR [rbx],005C005Ch
 je wfq_nt_absolute
 cmp WORD PTR [rbx+2],58
 jne wfq_nt_relative
 cmp WORD PTR [rbx+4],92
 je wfq_nt_absolute
 ; Drive-relative paths use that drive's real cwd, not this drive's cwd.
 movzx eax,WORD PTR [rbx]
 and eax,0FFDFh
 sub eax,65
 cmp eax,25
 ja wfq_nt_no_directory
 mov ax,WORD PTR [rbx]
 mov WORD PTR [rsp+64],ax
 mov DWORD PTR [rsp+66],005C003Ah
 mov WORD PTR [rsp+70],0
 lea rcx,[rsp+64]
 call GetDriveTypeW
 cmp eax,1
 jbe wfq_nt_no_directory
 mov WORD PTR [rsp+68],46
 mov WORD PTR [rsp+70],0
 lea rcx,[rsp+64]
 mov edx,32768
 mov r8,rsi
 xor r9d,r9d
 call GetFullPathNameW
 cmp eax,32768
 jae wfq_nt_no_directory
 jmp wfq_nt_directory_length
wfq_nt_relative:
 xor ecx,ecx
 xor edx,edx
 call GetCurrentDirectoryW
 test eax,eax
 jz wfq_nt_no_directory
 dec eax
 jmp wfq_nt_directory_length
wfq_nt_no_directory:
 xor eax,eax
wfq_nt_directory_length:
 add rax,rdi
 inc rax
 cmp rax,247
 jbe wfq_nt_raw
 jmp wfq_nt_full
wfq_nt_absolute:
 cmp edi,247
 jbe wfq_nt_raw
wfq_nt_full:
 mov rcx,rbx
 mov edx,32768
 mov r8,rsi
 xor r9d,r9d
 call GetFullPathNameW
 test eax,eax
 jz wfq_nt_raw
 cmp eax,32768
 jae wfq_nt_raw
 cmp DWORD PTR [rsi],005C005Ch
 jne wfq_nt_drive_prefix
 cmp DWORD PTR [rsi+4],005C003Fh
 je wfq_nt_ready
 lea rax,[rsi-12]
 mov rdx,005C003F005C005Ch
 mov QWORD PTR [rax],rdx
 mov rdx,005C0043004E0055h
 mov QWORD PTR [rax+8],rdx
 jmp wfq_nt_done
wfq_nt_drive_prefix:
 lea rax,[rsi-8]
 mov rdx,005C003F005C005Ch
 mov QWORD PTR [rax],rdx
 jmp wfq_nt_done
wfq_nt_ready:
 mov rax,rsi
 jmp wfq_nt_done
wfq_nt_raw:
 mov rax,rbx
wfq_nt_done:
 add rsp,96
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
wfq_nt_path ENDP

; Original getFileInformation, preserving the failed lookup's last-error when
; CloseHandle succeeds. RCX path, RDX writable BY_HANDLE_FILE_INFORMATION52.
wfq_information PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,72
 .allocstack 72
 .endprolog
 mov rsi,rdx
 mov edx,80h
 mov r8d,7
 xor r9d,r9d
 mov DWORD PTR [rsp+32],3
 mov DWORD PTR [rsp+40],02000000h
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 je wfq_information_failed
 mov rbx,rax
 mov rcx,rax
 mov rdx,rsi
 call GetFileInformationByHandle
 mov edi,eax
 call GetLastError
 mov r12d,eax
 mov rcx,rbx
 call CloseHandle
 test eax,eax
 jz wfq_information_result
 mov ecx,r12d
 call SetLastError
wfq_information_result:
 mov eax,edi
 jmp wfq_information_done
wfq_information_failed:
 xor eax,eax
wfq_information_done:
 add rsp,72
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
wfq_information ENDP

wfq_unix_attributes PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,176
 .allocstack 176
 .endprolog
 mov edi,-1
 mov edx,80h
 mov r8d,7
 xor r9d,r9d
 mov DWORD PTR [rsp+32],3
 mov DWORD PTR [rsp+40],02200000h
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 je wfq_unix_done
 mov rbx,rax
 mov rcx,rax
 lea rdx,[rsp+64]
 call GetFileInformationByHandle
 test eax,eax
 jz wfq_unix_close
 test DWORD PTR [rsp+64],400h
 jz wfq_unix_close
 mov rcx,rbx
 mov edx,0900A8h
 xor r8d,r8d
 xor r9d,r9d
 lea rax,[rsp+128]
 mov QWORD PTR [rsp+32],rax
 mov DWORD PTR [rsp+40],28
 lea rax,[rsp+160]
 mov QWORD PTR [rsp+48],rax
 mov QWORD PTR [rsp+56],0
 call DeviceIoControl
 test eax,eax
 jz wfq_unix_close
 cmp DWORD PTR [rsp+128],080000023h
 jne wfq_unix_close
 mov edi,DWORD PTR [rsp+64]
wfq_unix_close:
 mov rcx,rbx
 call CloseHandle
wfq_unix_done:
 mov eax,edi
 add rsp,176
 pop rdi
 pop rsi
 pop rbx
 ret
wfq_unix_attributes ENDP

; Exact legacy getFinalAttributes: sharing OR access denied fallback, optional
; target handle following, and AF_UNIX only after an initial successful query.
wfq_attributes PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,656
 .allocstack 656
 .endprolog
 mov rbx,rcx
 mov esi,-1
 lea rdx,[rsp+64]
 call boom_query_raw_file_attributes
 test eax,eax
 jnz wfq_attributes_fallback
 mov esi,DWORD PTR [rsp+64]
 test esi,400h
 jz wfq_attributes_done
 mov rcx,rbx
 lea rdx,[rsp+64]
 call wfq_information
 test eax,eax
 jnz wfq_attributes_information
 mov esi,-1
 call GetLastError
 cmp eax,1920
 jne wfq_attributes_done
 mov rcx,rbx
 call wfq_unix_attributes
 mov esi,eax
 jmp wfq_attributes_done
wfq_attributes_information:
 mov esi,DWORD PTR [rsp+64]
 jmp wfq_attributes_done
wfq_attributes_fallback:
 cmp eax,32
 je wfq_attributes_find
 cmp eax,5
 jne wfq_attributes_done
wfq_attributes_find:
 mov rcx,rbx
 lea rdx,[rsp+64]
 call FindFirstFileW
 cmp rax,-1
 je wfq_attributes_done
 mov rdi,rax
 mov esi,DWORD PTR [rsp+64]
 test esi,400h
 jz wfq_attributes_close
 mov rcx,rbx
 lea rdx,[rsp+64]
 call wfq_information
 mov esi,-1
 test eax,eax
 jz wfq_attributes_close
 mov esi,DWORD PTR [rsp+64]
wfq_attributes_close:
 mov rcx,rdi
 call FindClose
wfq_attributes_done:
 mov eax,esi
 add rsp,656
 pop rdi
 pop rsi
 pop rbx
 ret
wfq_attributes ENDP

; RCX trusted native path (NULL only for nameMax), EDX operation, R8D selector.
; RAX java result; EDX actual Windows failure only for getNameMax0.
wfq_query PROC PRIVATE FRAME
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
 sub rsp,2800
 .allocstack 2800
 .endprolog
 mov rbx,rcx
 mov esi,edx
 mov r13d,r8d
 xor edi,edi
 mov DWORD PTR [rsp+72],0
 cmp esi,5
 je wfq_query_name_max
 cmp esi,4
 je wfq_query_space
 cmp esi,6
 je wfq_query_access
 cmp esi,2
 je wfq_query_length
 cmp esi,1
 je wfq_query_mtime
 ; isReservedDeviceNameW uses an exact nine-unit GetFullPathName buffer.
 mov edx,9
 lea r8,[rsp+80]
 lea r9,[rsp+104]
 call GetFullPathNameW
 cmp eax,7
 je wfq_query_device_candidate
 cmp eax,8
 jne wfq_query_attributes
wfq_query_device_candidate:
 cmp DWORD PTR [rsp+80],005C005Ch
 jne wfq_query_attributes
 cmp DWORD PTR [rsp+84],005C002Eh
 jne wfq_query_attributes
 movzx r8d,WORD PTR [rsp+88]
 movzx r9d,WORD PTR [rsp+90]
 movzx r10d,WORD PTR [rsp+92]
 and r8d,0FFDFh
 and r9d,0FFDFh
 and r10d,0FFDFh
 cmp eax,8
 je wfq_query_device_four
 shl r9,16
 shl r10,32
 or r8,r9
 or r8,r10
 mov rax,004E004F0043h
 cmp r8,rax
 je wfq_query_done
 mov rax,004E00520050h
 cmp r8,rax
 je wfq_query_done
 mov rax,005800550041h
 cmp r8,rax
 je wfq_query_done
 mov rax,004C0055004Eh
 cmp r8,rax
 je wfq_query_done
 jmp wfq_query_attributes
wfq_query_device_four:
 movzx eax,WORD PTR [rsp+94]
 sub eax,49
 cmp eax,8
 ja wfq_query_attributes
 cmp r8d,67
 jne wfq_query_device_lpt
 cmp r9d,79
 jne wfq_query_attributes
 cmp r10d,77
 je wfq_query_done
 jmp wfq_query_attributes
wfq_query_device_lpt:
 cmp r8d,76
 jne wfq_query_attributes
 cmp r9d,80
 jne wfq_query_attributes
 cmp r10d,84
 je wfq_query_done
wfq_query_attributes:
 mov rcx,rbx
 call wfq_attributes
 cmp eax,-1
 je wfq_query_done
 mov edi,3
 test eax,10h
 jz wfq_query_hidden
 mov edi,5
wfq_query_hidden:
 test eax,2
 jz wfq_query_done
 or edi,8
 jmp wfq_query_done
wfq_query_mtime:
 mov rcx,rbx
 xor edx,edx
 mov r8d,7
 xor r9d,r9d
 mov DWORD PTR [rsp+32],3
 mov DWORD PTR [rsp+40],02000000h
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 je wfq_query_done
 mov r12,rax
 mov rcx,rax
 xor edx,edx
 xor r8d,r8d
 lea r9,[rsp+80]
 call GetFileTime
 test eax,eax
 jz wfq_query_close
 mov rax,QWORD PTR [rsp+80]
 xor edx,edx
 mov ecx,10000
 div rcx
 mov rcx,11644473600000
 sub rax,rcx
 mov rdi,rax
 jmp wfq_query_close
wfq_query_length:
 mov rcx,rbx
 lea rdx,[rsp+80]
 call boom_query_raw_file_attributes
 test eax,eax
 jnz wfq_query_length_failed
 test DWORD PTR [rsp+80],400h
 jnz wfq_query_length_target
wfq_query_length_raw:
 mov edi,DWORD PTR [rsp+108]
 shl rdi,32
 mov eax,DWORD PTR [rsp+112]
 or rdi,rax
 jmp wfq_query_done
wfq_query_length_target:
 mov rcx,rbx
 lea rdx,[rsp+80]
 call wfq_information
 test eax,eax
 jz wfq_query_done
 mov edi,DWORD PTR [rsp+112]
 shl rdi,32
 mov eax,DWORD PTR [rsp+116]
 or rdi,rax
 jmp wfq_query_done
wfq_query_length_failed:
 cmp eax,32
 jne wfq_query_done
 mov rcx,rbx
 lea rdx,[rsp+80]
 call FindFirstFileW
 cmp rax,-1
 je wfq_query_done
 mov r12,rax
 test DWORD PTR [rsp+80],400h
 jnz wfq_query_find_close
 mov rcx,rbx
 mov r8,rbx
wfq_query_input_tail:
 movzx eax,WORD PTR [rcx]
 test eax,eax
 jz wfq_query_find_tail_start
 add rcx,2
 cmp eax,92
 jne wfq_query_input_tail
 mov r8,rcx
 jmp wfq_query_input_tail
wfq_query_find_tail_start:
 lea rcx,[rsp+124]
 mov r9,rcx
wfq_query_find_tail:
 movzx eax,WORD PTR [rcx]
 test eax,eax
 jz wfq_query_length_compare
 add rcx,2
 cmp eax,92
 jne wfq_query_find_tail
 mov r9,rcx
 jmp wfq_query_find_tail
wfq_query_length_compare:
 movzx eax,WORD PTR [r8]
 cmp ax,WORD PTR [r9]
 jne wfq_query_find_close
 test eax,eax
 jz wfq_query_length_found
 add r8,2
 add r9,2
 jmp wfq_query_length_compare
wfq_query_length_found:
 test DWORD PTR [rsp+108],080000000h
 jnz wfq_query_find_close
 mov edi,DWORD PTR [rsp+108]
 shl rdi,32
 mov eax,DWORD PTR [rsp+112]
 or rdi,rax
wfq_query_find_close:
 mov rcx,r12
 call FindClose
 jmp wfq_query_done
wfq_query_access:
 mov rcx,rbx
 call GetFileAttributesW
 cmp eax,-1
 je wfq_query_done
 test eax,400h
 jz wfq_query_access_flags
 mov rcx,rbx
 lea rdx,[rsp+80]
 call wfq_information
 test eax,eax
 jz wfq_query_done
 mov eax,DWORD PTR [rsp+80]
wfq_query_access_flags:
 cmp r13d,4
 je wfq_query_access_true
 cmp r13d,1
 je wfq_query_access_true
 cmp r13d,2
 jne wfq_query_done
 test eax,10h
 jnz wfq_query_access_true
 test eax,1
 jnz wfq_query_done
wfq_query_access_true:
 mov edi,1
 jmp wfq_query_done
wfq_query_space:
 mov rcx,rbx
 lea rdx,[rsp+704]
 mov r8d,1024
 call GetVolumePathNameW
 test eax,eax
 jz wfq_query_done
 lea rcx,[rsp+704]
 lea rdx,[rsp+80]
 lea r8,[rsp+88]
 lea r9,[rsp+96]
 call GetDiskFreeSpaceExW
 test eax,eax
 jz wfq_query_done
 mov rdi,QWORD PTR [rsp+88]
 test r13d,r13d
 jz wfq_query_done
 mov rdi,QWORD PTR [rsp+96]
 cmp r13d,1
 je wfq_query_done
 mov rdi,QWORD PTR [rsp+80]
 jmp wfq_query_done
wfq_query_name_max:
 xor edx,edx
 xor r8d,r8d
 xor r9d,r9d
 lea rax,[rsp+80]
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],0
 mov QWORD PTR [rsp+48],0
 mov DWORD PTR [rsp+56],0
 call GetVolumeInformationW
 test eax,eax
 jz wfq_query_name_max_error
 mov edi,DWORD PTR [rsp+80]
 jmp wfq_query_done
wfq_query_name_max_error:
 call GetLastError
 test eax,eax
 jnz wfq_query_name_max_save_error
 mov eax,-1
wfq_query_name_max_save_error:
 mov DWORD PTR [rsp+72],eax
 jmp wfq_query_done
wfq_query_close:
 mov rcx,r12
 call CloseHandle
wfq_query_done:
 mov rax,rdi
 mov edx,DWORD PTR [rsp+72]
 add rsp,2800
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
wfq_query ENDP
