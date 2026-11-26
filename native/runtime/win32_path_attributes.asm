; Read-only Windows metadata for a normalized, NUL-terminated UTF-16 path.
; RCX = path, EDX = flags (1 follows links, 2 requires handle information),
; R8 = writable 48-byte result. Returns a Win32 error, or zero on success.
; The caller owns both buffers. On failure the destination is untouched.
; Result: DWORD attributes, reparseTag; QWORD creation, access, write (Win32
; FILETIME ticks), size; DWORD kinds, reserved. Kinds mirror BasicFileAttributes:
; regular=1, directory=2, symbolicLink=4, other=8 (a junction may set 2 and 8).
; The kernel does not access Java objects or carry mutable state between calls.
option casemap:none
EXTERN GetFileAttributesExW:PROC
EXTERN GetLastError:PROC
EXTERN FindFirstFileW:PROC
EXTERN FindClose:PROC
EXTERN CreateFileW:PROC
EXTERN GetFileInformationByHandle:PROC
EXTERN DeviceIoControl:PROC
EXTERN CloseHandle:PROC
EXTERN LocalAlloc:PROC
EXTERN LocalFree:PROC
PUBLIC boom_win32_path_attributes
PUBLIC boom_win32_raw_file_attributes

.code
; The JNI GetFileAttributesEx0 contract returns the first lookup's unmodified
; 36-byte WIN32_FILE_ATTRIBUTE_DATA, including the reparse bit. The caller
; supplies trusted buffers (guest provenance is checked by its own adapter).
; RCX=path, RDX=result36 -> DWORD Win32 error. Success fully populates result.
boom_win32_raw_file_attributes PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 mov r8,rdx
 xor edx,edx
 call GetFileAttributesExW
 test eax,eax
 jz wra_error
 xor eax,eax
 jmp wra_done
wra_error:
 call GetLastError
wra_done:
 add rsp,40
 ret
boom_win32_raw_file_attributes ENDP

boom_win32_path_attributes PROC FRAME
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
 ; 64: dynamic reparse buffer, 72: bytes returned, 80: Win32 structure
 ; (36-byte attributes, 52-byte handle information or 592-byte find data).
 sub rsp,672
 .allocstack 672
 .endprolog
 mov rbx,rcx
 mov esi,edx
 mov rdi,r8
 mov eax,87                         ; ERROR_INVALID_PARAMETER
 test rbx,rbx
 jz wpa_done
 test rdi,rdi
 jz wpa_done
 cmp esi,3
 ja wpa_done
 xor r13d,r13d                      ; ordinary files have no reparse tag
 xor r15d,r15d                      ; no deferred socket-open error
 test esi,2
 jnz wpa_open_flags
 lea rdx,[rsp+80]
 call boom_win32_raw_file_attributes
 test eax,eax
 jnz wpa_fast_error
 test DWORD PTR [rsp+80],400h       ; FILE_ATTRIBUTE_REPARSE_POINT
 jz wpa_publish
 jmp wpa_open_flags

wpa_fast_error:
 cmp eax,32                         ; ERROR_SHARING_VIOLATION
 jne wpa_done
 ; WindowsFileAttributes.get allows a directory-entry query for a sharing
 ; violation on a non-root path. Preserve the first error if it cannot help.
 mov rdx,rbx
wpa_find_end:
 movzx ecx,WORD PTR [rdx]
 test ecx,ecx
 jz wpa_find_tail
 add rdx,2
 jmp wpa_find_end
wpa_find_tail:
 cmp rdx,rbx
 je wpa_done
 movzx ecx,WORD PTR [rdx-2]
 cmp ecx,5Ch
 je wpa_done
 cmp ecx,3Ah
 je wpa_done
 mov rcx,rbx
 lea rdx,[rsp+80]
 call FindFirstFileW
 cmp rax,-1
 je wpa_sharing_error
 mov rcx,rax
 call FindClose
 test DWORD PTR [rsp+80],400h
 jz wpa_publish
wpa_sharing_error:
 mov eax,32
 jmp wpa_done

wpa_open_flags:
 mov r10d,02000000h                 ; FILE_FLAG_BACKUP_SEMANTICS
 test esi,1
 jnz wpa_open
wpa_open_reparse:
 mov r10d,02200000h                 ; also FILE_FLAG_OPEN_REPARSE_POINT
wpa_open:
 mov rcx,rbx
 mov edx,80h                        ; FILE_READ_ATTRIBUTES
 mov r8d,7                          ; share read, write, delete
 xor r9d,r9d
 mov QWORD PTR [rsp+32],3           ; OPEN_EXISTING
 mov QWORD PTR [rsp+40],r10
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 jne wpa_handle
 call GetLastError
 test r15d,r15d
 jnz wpa_socket_error
 cmp eax,1920                       ; ERROR_CANT_ACCESS_FILE
 jne wpa_done
 test esi,1
 jz wpa_done
 ; WindowsPath.openForReadAttributeAccess retries a Unix socket without
 ; following the reparse point and accepts only IO_REPARSE_TAG_AF_UNIX.
 mov r15d,eax
 jmp wpa_open_reparse

wpa_handle:
 mov r12,rax
 mov rcx,rax
 lea rdx,[rsp+80]
 call GetFileInformationByHandle
 test eax,eax
 jz wpa_handle_error
 ; BY_HANDLE_FILE_INFORMATION places its size pair after the volume serial.
 ; Move high/low to match WIN32_FILE_ATTRIBUTE_DATA and WIN32_FIND_DATAW.
 mov rax,QWORD PTR [rsp+112]
 mov QWORD PTR [rsp+108],rax
 xor r14d,r14d
 test DWORD PTR [rsp+80],400h
 jz wpa_close
 xor ecx,ecx                        ; LMEM_FIXED
 mov edx,16384                      ; MAXIMUM_REPARSE_DATA_BUFFER_SIZE
 call LocalAlloc
 test rax,rax
 jz wpa_no_memory
 mov QWORD PTR [rsp+64],rax
 mov rcx,r12
 mov edx,0900A8h                    ; FSCTL_GET_REPARSE_POINT
 xor r8d,r8d
 xor r9d,r9d
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],16384
 lea rax,[rsp+72]
 mov QWORD PTR [rsp+48],rax
 mov QWORD PTR [rsp+56],0
 call DeviceIoControl
 test eax,eax
 jz wpa_reparse_error
 cmp DWORD PTR [rsp+72],8
 jb wpa_short_reparse
 mov rax,QWORD PTR [rsp+64]
 mov r13d,DWORD PTR [rax]
 jmp wpa_free
wpa_short_reparse:
 mov r14d,13                        ; ERROR_INVALID_DATA
 jmp wpa_free
wpa_reparse_error:
 call GetLastError
 mov r14d,eax
wpa_free:
 mov rcx,QWORD PTR [rsp+64]
 call LocalFree
 jmp wpa_close
wpa_no_memory:
 mov r14d,8                         ; ERROR_NOT_ENOUGH_MEMORY
 jmp wpa_close
wpa_handle_error:
 call GetLastError
 mov r14d,eax
wpa_close:
 mov rcx,r12
 call CloseHandle
 test r15d,r15d
 jz wpa_check_handle
 cmp r13d,080000023h                ; IO_REPARSE_TAG_AF_UNIX
 jne wpa_socket_error
wpa_check_handle:
 mov eax,r14d
 test eax,eax
 jnz wpa_done
 jmp wpa_publish
wpa_socket_error:
 mov eax,r15d
 jmp wpa_done

wpa_publish:
 mov ecx,DWORD PTR [rsp+80]
 mov DWORD PTR [rdi],ecx
 mov DWORD PTR [rdi+4],r13d
 mov rax,QWORD PTR [rsp+84]
 mov QWORD PTR [rdi+8],rax
 mov rax,QWORD PTR [rsp+92]
 mov QWORD PTR [rdi+16],rax
 mov rax,QWORD PTR [rsp+100]
 mov QWORD PTR [rdi+24],rax
 mov eax,DWORD PTR [rsp+108]
 shl rax,32
 mov edx,DWORD PTR [rsp+112]
 or rax,rdx
 mov QWORD PTR [rdi+32],rax
 mov eax,4
 cmp r13d,0A000000Ch                ; IO_REPARSE_TAG_SYMLINK
 je wpa_store_kind
 xor eax,eax
 test ecx,10h                       ; FILE_ATTRIBUTE_DIRECTORY
 setnz al
 add eax,eax
 xor edx,edx
 test ecx,440h                      ; FILE_ATTRIBUTE_DEVICE or REPARSE_POINT
 setnz dl
 lea eax,[rax+rdx*8]
 test eax,eax
 jnz wpa_store_kind
 inc eax
wpa_store_kind:
 mov QWORD PTR [rdi+40],rax         ; includes zero reserved DWORD
 xor eax,eax
wpa_done:
 add rsp,672
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_win32_path_attributes ENDP
END
