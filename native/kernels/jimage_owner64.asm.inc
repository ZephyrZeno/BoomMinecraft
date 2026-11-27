; Caller-owned JIMG128/1, real readonly Windows mappings and exact UTF16 keys.
; Pool: magic0Q bytes8D abi12D lock16Q state24D capacity28D entries32Q,
; sequence40Q head48Q leases56Q mappedBytes64Q files72Q maps80Q,
; openCalls88Q lookups96Q misses104Q releases112Q reserved120Q.
; Record80 + UTF16 key: next0 token8 view16 bytes24 file32 map40 refs48,
; units56D reserved60D indexBytes64Q reserved72Q key80.
; Job64: pool0 path8 units16 token24 view32 length40 status48D winerr52D
; expectedSize56Q(open only). init/close use the pool directly.
; 0=success 1=miss 2=busy 3=arguments 4=OS failure 5=invalid pool
; 6=unknown/unleased token 7=capacity/generation exhaustion 8=bad path
; 9=closed 10=invalid image/header/expected size 11=unsupported endian
; 12=OS cleanup incomplete; only release/close remain available.
; Lookup/open acquire a lease. A successful Java view retains that lease
; through VM shutdown. Release cannot unmap; close requires all leases gone.
JIO_BYTES EQU 128
JIO_MAGIC EQU 03130474D494A4F42h
JIO_RECORD EQU 80
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN CreateFileW:PROC
EXTERN GetFileSizeEx:PROC
EXTERN CreateFileMappingW:PROC
EXTERN MapViewOfFile:PROC
EXTERN UnmapViewOfFile:PROC
EXTERN CloseHandle:PROC
EXTERN GetLastError:PROC
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
.code

PUBLIC boom_jimage_owner_init
boom_jimage_owner_init PROC FRAME
 push rdi
 .pushreg rdi
 .endprolog
 test rcx,rcx
 jz jio_init_args
 test rcx,7
 jnz jio_init_args
 cmp edx,JIO_BYTES
 jne jio_init_args
 test r8d,r8d
 jz jio_init_args
 cmp r8d,1024
 ja jio_init_args
 mov rax,rcx
 add rax,JIO_BYTES
 jc jio_init_args
 mov r10,1
 cmp QWORD PTR [rcx],0
 je jio_init_zero_check
 mov rax,JIO_MAGIC
 cmp QWORD PTR [rcx],rax
 jne jio_init_pool
 cmp DWORD PTR [rcx+8],JIO_BYTES
 jne jio_init_pool
 cmp DWORD PTR [rcx+12],1
 jne jio_init_pool
 cmp DWORD PTR [rcx+24],2
 jne jio_init_busy
 cmp QWORD PTR [rcx+32],0
 jne jio_init_pool
 cmp QWORD PTR [rcx+48],0
 jne jio_init_pool
 cmp QWORD PTR [rcx+56],0
 jne jio_init_pool
 cmp QWORD PTR [rcx+64],0
 jne jio_init_pool
 cmp QWORD PTR [rcx+72],0
 jne jio_init_pool
 cmp QWORD PTR [rcx+80],0
 jne jio_init_pool
 mov r10,QWORD PTR [rcx+40]
 test r10,r10
 jz jio_init_pool
 jmp jio_init_clear
jio_init_zero_check:
 xor eax,eax
jio_init_zero_loop:
 cmp QWORD PTR [rcx+rax],0
 jne jio_init_pool
 add eax,8
 cmp eax,JIO_BYTES
 jb jio_init_zero_loop
jio_init_clear:
 mov r11,rcx
 mov rdi,rcx
 xor eax,eax
 mov ecx,JIO_BYTES/8
 rep stosq
 mov rax,JIO_MAGIC
 mov QWORD PTR [r11],rax
 mov DWORD PTR [r11+8],JIO_BYTES
 mov DWORD PTR [r11+12],1
 mov DWORD PTR [r11+24],1
 mov DWORD PTR [r11+28],r8d
 mov QWORD PTR [r11+40],r10
 xor eax,eax
 jmp jio_init_done
jio_init_args:
 mov eax,3
 jmp jio_init_done
jio_init_pool:
 mov eax,5
 jmp jio_init_done
jio_init_busy:
 mov eax,2
jio_init_done:
 pop rdi
 ret
boom_jimage_owner_init ENDP

; RCX pool -> EAX header status. Accessible caller-owned memory is required.
jio_check_pool PROC PRIVATE
 test rcx,rcx
 jz jio_check_bad
 test rcx,7
 jnz jio_check_bad
 mov rax,rcx
 add rax,JIO_BYTES
 jc jio_check_bad
 mov rax,JIO_MAGIC
 cmp QWORD PTR [rcx],rax
 jne jio_check_bad
 cmp DWORD PTR [rcx+8],JIO_BYTES
 jne jio_check_bad
 cmp DWORD PTR [rcx+12],1
 jne jio_check_bad
 cmp QWORD PTR [rcx+120],0
 jne jio_check_bad
 mov eax,DWORD PTR [rcx+28]
 dec eax
 cmp eax,1023
 ja jio_check_bad
 mov eax,DWORD PTR [rcx+24]
 cmp eax,1
 je jio_check_ok
 cmp eax,2
 je jio_check_closed
 cmp eax,3
 jne jio_check_bad
 mov eax,12
 ret
jio_check_closed:
 mov eax,9
 ret
jio_check_ok:
 xor eax,eax
 ret
jio_check_bad:
 mov eax,5
 ret
jio_check_pool ENDP

; RBX Job64; preserve release token in R12 before clearing outputs.
; Validates address intervals before publishing job fields; no path overread.
jio_job PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 test rbx,rbx
 jz jio_job_unsafe
 test rbx,7
 jnz jio_job_unsafe
 mov rax,rbx
 add rax,64
 jc jio_job_unsafe
 mov rdi,QWORD PTR [rbx]
 test rdi,rdi
 jz jio_job_unsafe
 mov rdx,rdi
 add rdx,JIO_BYTES
 jc jio_job_unsafe
 cmp rdi,rax
 jae jio_job_clear
 cmp rdx,rbx
 ja jio_job_unsafe
jio_job_clear:
 mov QWORD PTR [rbx+24],0
 mov QWORD PTR [rbx+32],0
 mov QWORD PTR [rbx+40],0
 mov QWORD PTR [rbx+48],0
 mov rcx,rdi
 call jio_check_pool
 test eax,eax
 jnz jio_job_publish
 xor eax,eax
 jmp jio_job_done
jio_job_publish:
 mov DWORD PTR [rbx+48],eax
 jmp jio_job_done
jio_job_unsafe:
 mov eax,3
jio_job_done:
 add rsp,40
 ret
jio_job ENDP

; Validates caller input key and complete key/job/pool disjointness.
; RBX job,RDI pool -> RSI key,RBP units,EAX status.
jio_key PROC PRIVATE
 mov rsi,QWORD PTR [rbx+8]
 mov rbp,QWORD PTR [rbx+16]
 test rsi,rsi
 jz jio_key_bad
 test rbp,rbp
 jz jio_key_bad
 cmp rbp,32767
 ja jio_key_bad
 lea r8,[rbp*2]
 add r8,rsi
 jc jio_key_bad
 lea r9,[rbx+64]
 cmp rsi,r9
 jae jio_key_pool
 cmp r8,rbx
 ja jio_key_bad
jio_key_pool:
 lea r9,[rdi+JIO_BYTES]
 cmp rsi,r9
 jae jio_key_scan
 cmp r8,rdi
 ja jio_key_bad
jio_key_scan:
 xor ecx,ecx
jio_key_loop:
 cmp WORD PTR [rsi+rcx*2],0
 je jio_key_nul
 inc rcx
 cmp rcx,rbp
 jb jio_key_loop
 xor eax,eax
 ret
jio_key_nul:
 mov eax,8
 ret
jio_key_bad:
 mov eax,3
 ret
jio_key ENDP

; Pool exclusively locked; RSI/RBP caller key -> R14 matching entry or NULL.
jio_find PROC PRIVATE
 mov r14,QWORD PTR [rdi+48]
jio_find_loop:
 test r14,r14
 jz jio_find_done
 cmp ebp,DWORD PTR [r14+56]
 jne jio_find_next
 xor ecx,ecx
jio_find_units:
 movzx eax,WORD PTR [rsi+rcx*2]
 cmp ax,WORD PTR [r14+rcx*2+JIO_RECORD]
 jne jio_find_next
 inc rcx
 cmp rcx,rbp
 jb jio_find_units
 ret
jio_find_next:
 mov r14,QWORD PTR [r14]
 jmp jio_find_loop
jio_find_done:
 ret
jio_find ENDP

; An exclusively locked entry is leased before its address is published.
jio_lease PROC PRIVATE
 cmp QWORD PTR [r14+48],-1
 je jio_lease_full
 cmp QWORD PTR [rdi+56],-1
 je jio_lease_full
 inc QWORD PTR [r14+48]
 inc QWORD PTR [rdi+56]
 mov rax,QWORD PTR [r14+8]
 mov QWORD PTR [rbx+24],rax
 mov rax,QWORD PTR [r14+16]
 mov QWORD PTR [rbx+32],rax
 mov rax,QWORD PTR [r14+24]
 mov QWORD PTR [rbx+40],rax
 xor eax,eax
 ret
jio_lease_full:
 mov eax,7
 ret
jio_lease ENDP

; R14 node,RDI owner, exclusively locked. On failure retain every resource
; not actually released and return EAX12/EDX Win32 error for a later retry.
; Success frees the node. The caller retains its next pointer separately.
jio_record_close PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rcx,QWORD PTR [r14+16]
 test rcx,rcx
 jz jio_record_map
 call UnmapViewOfFile
 test eax,eax
 jz jio_record_error
 mov QWORD PTR [r14+16],0
 mov rax,QWORD PTR [r14+24]
 sub QWORD PTR [rdi+64],rax
jio_record_map:
 mov rcx,QWORD PTR [r14+40]
 test rcx,rcx
 jz jio_record_file
 call CloseHandle
 test eax,eax
 jz jio_record_error
 mov QWORD PTR [r14+40],0
 dec QWORD PTR [rdi+80]
jio_record_file:
 mov rcx,QWORD PTR [r14+32]
 test rcx,rcx
 jz jio_record_free
 call CloseHandle
 test eax,eax
 jz jio_record_error
 mov QWORD PTR [r14+32],0
 dec QWORD PTR [rdi+72]
jio_record_free:
 mov rcx,r14
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
 test eax,eax
 jz jio_record_error
 xor eax,eax
 jmp jio_record_done
jio_record_error:
 call GetLastError
 mov edx,eax
 mov eax,12
jio_record_done:
 add rsp,40
 ret
jio_record_close ENDP

PUBLIC boom_jimage_owner_open
PUBLIC boom_jimage_owner_lookup
PUBLIC boom_jimage_owner_release
boom_jimage_owner_open PROC
 xor edx,edx
 jmp jio_service
boom_jimage_owner_open ENDP
boom_jimage_owner_lookup PROC
 mov edx,1
 jmp jio_service
boom_jimage_owner_lookup ENDP
boom_jimage_owner_release PROC
 mov edx,2
 jmp jio_service
boom_jimage_owner_release ENDP

jio_service PROC PRIVATE FRAME
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
 sub rsp,168
 .allocstack 168
 .endprolog
 mov rbx,rcx
 mov r13d,edx
 xor r15d,r15d
 xor r14d,r14d
 test rbx,rbx
 jz jio_service_null
 mov r12,QWORD PTR [rbx+24]
 call jio_job
 test eax,eax
 jz jio_service_valid
 cmp eax,12
 jne jio_service_return
 cmp r13d,2
 jne jio_service_return
jio_service_valid:
 cmp r13d,2
 je jio_release_args
 call jio_key
 test eax,eax
 jnz jio_service_publish
 cmp r13d,0
 je jio_lock
 cmp QWORD PTR [rbx+56],0
 jne jio_service_args
 jmp jio_lock
jio_release_args:
 test r12,r12
 jz jio_service_args
 cmp QWORD PTR [rbx+8],0
 jne jio_service_args
 cmp QWORD PTR [rbx+16],0
 jne jio_service_args
 cmp QWORD PTR [rbx+56],0
 jne jio_service_args
jio_lock:
 lea rcx,[rdi+16]
 call AcquireSRWLockExclusive
 mov r15d,1
 mov rcx,rdi
 call jio_check_pool
 test eax,eax
 jz jio_service_locked
 cmp eax,12
 jne jio_service_publish
 cmp r13d,2
 jne jio_service_publish
jio_service_locked:
 cmp r13d,2
 je jio_release_locked
 call jio_find
 cmp r13d,0
 je jio_open_locked
 inc QWORD PTR [rdi+96]
 test r14,r14
 jnz jio_found
 inc QWORD PTR [rdi+104]
 mov eax,1
 jmp jio_service_publish
jio_found:
 call jio_lease
 jmp jio_service_publish
jio_release_locked:
 inc QWORD PTR [rdi+112]
 mov r14,QWORD PTR [rdi+48]
jio_release_find:
 test r14,r14
 jz jio_service_token
 cmp QWORD PTR [r14+8],r12
 je jio_release_found
 mov r14,QWORD PTR [r14]
 jmp jio_release_find
jio_release_found:
 cmp QWORD PTR [r14+48],0
 je jio_service_token
 cmp QWORD PTR [rdi+56],0
 je jio_service_pool
 dec QWORD PTR [r14+48]
 dec QWORD PTR [rdi+56]
 xor eax,eax
 jmp jio_service_publish
jio_open_locked:
 inc QWORD PTR [rdi+88]
 test r14,r14
 jz jio_open_new
 mov rax,QWORD PTR [rbx+56]
 test rax,rax
 jz jio_found
 cmp QWORD PTR [r14+24],rax
 jne jio_service_image
 jmp jio_found
jio_open_new:
 cmp QWORD PTR [rdi+56],-1
 je jio_service_full
 mov eax,DWORD PTR [rdi+28]
 cmp QWORD PTR [rdi+32],rax
 jae jio_service_full
 cmp QWORD PTR [rdi+40],-1
 je jio_service_full
 xor ecx,ecx
 lea rdx,[rbp*2+JIO_RECORD+2]
 mov r8d,03000h
 mov r9d,4
 call VirtualAlloc
 test rax,rax
 jz jio_service_OS
 mov r14,rax
 mov DWORD PTR [r14+56],ebp
 xor ecx,ecx
jio_copy_key:
 movzx eax,WORD PTR [rsi+rcx*2]
 mov WORD PTR [r14+rcx*2+JIO_RECORD],ax
 inc rcx
 cmp rcx,rbp
 jb jio_copy_key
 lea rcx,[r14+JIO_RECORD]
 mov edx,080000000h
 mov r8d,1
 xor r9d,r9d
 mov QWORD PTR [rsp+32],3
 mov QWORD PTR [rsp+40],080h
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 je jio_open_OS_cleanup
 mov QWORD PTR [r14+32],rax
 inc QWORD PTR [rdi+72]
 mov rcx,rax
 lea rdx,[rsp+128]
 call GetFileSizeEx
 test eax,eax
 jz jio_open_OS_cleanup
 mov rax,QWORD PTR [rsp+128]
 cmp rax,28
 jl jio_open_bad_image
 mov rdx,QWORD PTR [rbx+56]
 test rdx,rdx
 jz jio_open_size_ok
 cmp rax,rdx
 jne jio_open_bad_image
jio_open_size_ok:
 mov QWORD PTR [r14+24],rax
 add rax,QWORD PTR [rdi+64]
 jc jio_open_full_cleanup
 mov rcx,QWORD PTR [r14+32]
 xor edx,edx
 mov r8d,2
 xor r9d,r9d
 mov QWORD PTR [rsp+32],0
 mov QWORD PTR [rsp+40],0
 call CreateFileMappingW
 test rax,rax
 jz jio_open_OS_cleanup
 mov QWORD PTR [r14+40],rax
 inc QWORD PTR [rdi+80]
 mov rcx,rax
 mov edx,4
 xor r8d,r8d
 xor r9d,r9d
 mov QWORD PTR [rsp+32],0
 call MapViewOfFile
 test rax,rax
 jz jio_open_OS_cleanup
 mov QWORD PTR [r14+16],rax
 mov rdx,QWORD PTR [r14+24]
 add QWORD PTR [rdi+64],rdx
 cmp DWORD PTR [rax],0CAFEDADAh
 je jio_open_header
 cmp DWORD PTR [rax],0DADAFECAh
 je jio_open_endian
 jmp jio_open_bad_image
jio_open_header:
 cmp DWORD PTR [rax+4],010000h
 jne jio_open_bad_image
 mov edx,DWORD PTR [rax+16]
 lea rdx,[rdx*8+28]
 mov ecx,DWORD PTR [rax+20]
 add rdx,rcx
 mov ecx,DWORD PTR [rax+24]
 add rdx,rcx
 cmp rdx,QWORD PTR [r14+24]
 ja jio_open_bad_image
 mov QWORD PTR [r14+64],rdx
 mov rcx,QWORD PTR [rdi+40]
 mov QWORD PTR [r14+8],rcx
 inc QWORD PTR [rdi+40]
 mov rcx,QWORD PTR [rdi+48]
 mov QWORD PTR [r14],rcx
 mov QWORD PTR [rdi+48],r14
 inc QWORD PTR [rdi+32]
 call jio_lease
 jmp jio_service_publish
jio_open_OS_cleanup:
 call GetLastError
 mov DWORD PTR [rbx+52],eax
 mov r12d,4
 jmp jio_open_cleanup
jio_open_bad_image:
 mov r12d,10
 jmp jio_open_cleanup
jio_open_endian:
 mov r12d,11
 jmp jio_open_cleanup
jio_open_full_cleanup:
 mov r12d,7
jio_open_cleanup:
 call jio_record_close
 test eax,eax
 jnz jio_open_cleanup_pending
 mov eax,r12d
 jmp jio_service_publish
jio_open_cleanup_pending:
 mov DWORD PTR [rbx+52],edx
 mov rax,QWORD PTR [rdi+48]
 mov QWORD PTR [r14],rax
 mov QWORD PTR [rdi+48],r14
 mov DWORD PTR [rdi+24],3
 mov eax,12
 jmp jio_service_publish
jio_service_OS:
 call GetLastError
 mov DWORD PTR [rbx+52],eax
 mov eax,4
 jmp jio_service_publish
jio_service_null:
 mov eax,3
 jmp jio_service_return
jio_service_args:
 mov eax,3
 jmp jio_service_publish
jio_service_token:
 mov eax,6
 jmp jio_service_publish
jio_service_pool:
 mov eax,5
 jmp jio_service_publish
jio_service_full:
 mov eax,7
 jmp jio_service_publish
jio_service_image:
 mov eax,10
jio_service_publish:
 mov DWORD PTR [rbx+48],eax
 test r15d,r15d
 jz jio_service_return
 lea rcx,[rdi+16]
 call ReleaseSRWLockExclusive
 mov eax,DWORD PTR [rbx+48]
jio_service_return:
 add rsp,168
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
jio_service ENDP

PUBLIC boom_jimage_owner_close
boom_jimage_owner_close PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rdi,rcx
 call jio_check_pool
 test eax,eax
 jz jio_close_lock
 cmp eax,12
 jne jio_close_done
jio_close_lock:
 lea rcx,[rdi+16]
 call AcquireSRWLockExclusive
 mov rcx,rdi
 call jio_check_pool
 test eax,eax
 jz jio_close_leases
 cmp eax,12
 jne jio_close_unlock
jio_close_leases:
 cmp QWORD PTR [rdi+56],0
 jne jio_close_busy
 mov rbx,QWORD PTR [rdi+48]
 mov DWORD PTR [rdi+24],3
jio_close_loop:
 test rbx,rbx
 jz jio_close_empty
 mov rsi,QWORD PTR [rbx]
 mov r15,QWORD PTR [rbx+8]
 mov r14,rbx
 call jio_record_close
 test eax,eax
 jnz jio_close_unlock
 mov QWORD PTR [rdi+48],rsi
 test r15,r15
 jz jio_close_next
 dec QWORD PTR [rdi+32]
jio_close_next:
 mov rbx,rsi
 jmp jio_close_loop
jio_close_empty:
 mov QWORD PTR [rdi+32],0
 mov QWORD PTR [rdi+48],0
 mov QWORD PTR [rdi+64],0
 mov QWORD PTR [rdi+72],0
 mov QWORD PTR [rdi+80],0
 mov DWORD PTR [rdi+24],2
 xor eax,eax
 jmp jio_close_unlock
jio_close_busy:
 mov eax,2
jio_close_unlock:
 mov ebx,eax
 lea rcx,[rdi+16]
 call ReleaseSRWLockExclusive
 mov eax,ebx
jio_close_done:
 add rsp,32
 pop r15
 pop r14
 pop rdi
 pop rsi
 pop rbx
 ret
boom_jimage_owner_close ENDP
