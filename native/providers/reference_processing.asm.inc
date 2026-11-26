; RPRC80/1 per image. VM alone opens, requests stop, joins its workers and closes.
; state8, TLS index12, heap cell16, transport24, wait calls32, normal wakes40,
; stop tokens issued48, stops consumed56, released acquisitions64, first error72.
; Context+24 always belongs to the Java VM exception plan.
.code
rpr_valid PROC PRIVATE
 xor eax,eax
 test rcx,rcx
 jz rpr_valid_done
 cmp DWORD PTR [rcx],043525052h
 jne rpr_valid_done
 cmp DWORD PTR [rcx+4],1
 jne rpr_valid_done
 cmp QWORD PTR [rcx+16],0
 je rpr_valid_done
 cmp DWORD PTR [rcx+8],6
 ja rpr_valid_done
 inc eax
rpr_valid_done:
 ret
rpr_valid ENDP

; Called before starting Java workers. Owner operations return a Win32 status.
PUBLIC boom_provider_reference_open
boom_provider_reference_open PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 call rpr_valid
 test eax,eax
 jz rpr_open_bad
 mov rax,QWORD PTR [rbx+16]
 mov rsi,QWORD PTR [rax]
 test rsi,rsi
 jz rpr_open_bad
 xor eax,eax
 mov edx,1
 lock cmpxchg DWORD PTR [rbx+8],edx
 jne rpr_open_busy
 call TlsAlloc
 cmp eax,-1
 je rpr_open_failed
 mov DWORD PTR [rbx+12],eax
 mov rcx,rsi
 call boom_reference_pending_create
 test rax,rax
 jz rpr_open_free_tls
 mov QWORD PTR [rbx+24],rax
 mov DWORD PTR [rbx+8],2
 xor eax,eax
 jmp rpr_open_done
rpr_open_free_tls:
 call GetLastError
 mov esi,eax
 mov ecx,DWORD PTR [rbx+12]
 call TlsFree
 mov DWORD PTR [rbx+12],-1
 jmp rpr_open_rollback
rpr_open_failed:
 call GetLastError
 mov esi,eax
rpr_open_rollback:
 mov DWORD PTR [rbx+8],0
 mov eax,esi
 test eax,eax
 jnz rpr_open_done
 mov eax,8
 jmp rpr_open_done
rpr_open_bad:
 mov eax,87
 jmp rpr_open_done
rpr_open_busy:
 mov eax,170
rpr_open_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_provider_reference_open ENDP

PUBLIC boom_provider_reference_stop
boom_provider_reference_stop PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 call rpr_valid
 test eax,eax
 jz rpr_stop_bad
 mov eax,2
 mov edx,3
 lock cmpxchg DWORD PTR [rbx+8],edx
 je rpr_stop_call
 cmp eax,4
 jne rpr_stop_bad
 xor eax,eax
 jmp rpr_stop_done
rpr_stop_call:
 mov rcx,QWORD PTR [rbx+24]
 call boom_reference_pending_stop
 test eax,eax
 jnz rpr_stop_failed
 mov DWORD PTR [rbx+8],4
 jmp rpr_stop_done
rpr_stop_failed:
 mov DWORD PTR [rbx+8],2
 jmp rpr_stop_done
rpr_stop_bad:
 mov eax,87
rpr_stop_done:
 add rsp,32
 pop rbx
 ret
boom_provider_reference_stop ENDP

PUBLIC boom_provider_reference_close
boom_provider_reference_close PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 call rpr_valid
 test eax,eax
 jz rpr_close_bad
 cmp DWORD PTR [rbx+8],4
 jne rpr_close_bad
 mov rax,QWORD PTR [rbx+48]
 cmp rax,QWORD PTR [rbx+56]
 jne rpr_close_busy
 mov rcx,QWORD PTR [rbx+24]
 call boom_reference_pending_destroy
 mov esi,eax
 test eax,eax
 jz rpr_close_tls
 ; Destruction can report a handle error after unlinking the transport.
 mov rcx,QWORD PTR [rbx+24]
 call boom_reference_pending_stopping
 cmp eax,-1
 jne rpr_close_result
rpr_close_tls:
 mov QWORD PTR [rbx+24],0
 mov DWORD PTR [rbx+8],6
 mov ecx,DWORD PTR [rbx+12]
 call TlsFree
 mov DWORD PTR [rbx+12],-1
 test eax,eax
 jnz rpr_close_result
 test esi,esi
 jnz rpr_close_result
 call GetLastError
 mov esi,eax
 test eax,eax
 jnz rpr_close_result
 mov esi,87
rpr_close_result:
 mov eax,esi
 jmp rpr_close_done
rpr_close_bad:
 mov eax,87
 jmp rpr_close_done
rpr_close_busy:
 mov eax,170
rpr_close_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_provider_reference_close ENDP

; Private static native ABI (Context32, argv, pool, operation), no Java arguments.
PUBLIC boom_provider_reference_service
boom_provider_reference_service PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov rsi,r8
 mov edi,r9d
 test rbx,rbx
 jz rpr_service_zero
 cmp DWORD PTR [rbx],0
 jne rpr_service_zero
 cmp edi,2
 ja rpr_service_bad
 mov rcx,rsi
 call rpr_valid
 test eax,eax
 jz rpr_service_bad
 mov eax,DWORD PTR [rsi+8]
 sub eax,2
 cmp eax,2
 ja rpr_service_unbound
 mov rcx,QWORD PTR [rsi+24]
 test rcx,rcx
 jz rpr_service_unbound
 mov QWORD PTR [rsp+32],0
 lea rdx,[rsp+32]
 test edi,edi
 jz rpr_service_get
 cmp edi,1
 je rpr_service_has
 lock inc QWORD PTR [rsi+32]
 call boom_reference_pending_wait
 test eax,eax
 jnz rpr_service_status
 lock inc QWORD PTR [rsi+40]
 jmp rpr_service_zero
rpr_service_get:
 call boom_reference_pending_get
 jmp rpr_service_status
rpr_service_has:
 call boom_reference_pending_has
rpr_service_status:
 test eax,eax
 jz rpr_service_value
 cmp eax,995
 jne rpr_service_error
 mov eax,DWORD PTR [rsi+8]
 sub eax,3
 cmp eax,1
 ja rpr_service_bad
 mov rcx,QWORD PTR [rsi+24]
 call boom_reference_pending_stopping
 cmp eax,1
 jne rpr_service_bad
 mov ecx,DWORD PTR [rsi+12]
 call TlsGetValue
 test rax,rax
 jnz rpr_service_bad
 mov ecx,DWORD PTR [rsi+12]
 mov rdx,rbx
 call TlsSetValue
 test eax,eax
 jz rpr_service_tls_error
 lock inc QWORD PTR [rsi+48]
 mov DWORD PTR [rbx],0B002h
 jmp rpr_service_zero
rpr_service_tls_error:
 call GetLastError
rpr_service_error:
 mov edx,eax
 xor eax,eax
 lock cmpxchg DWORD PTR [rsi+72],edx
rpr_service_bad:
 mov DWORD PTR [rbx],7
 jmp rpr_service_zero
rpr_service_unbound:
 mov DWORD PTR [rbx],20
 jmp rpr_service_zero
rpr_service_value:
 mov rax,QWORD PTR [rsp+32]
 jmp rpr_service_done
rpr_service_zero:
 xor eax,eax
rpr_service_done:
 add rsp,48
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_reference_service ENDP

; Only a fully unwound call on the issuing OS thread may consume B002. A B001
; diagnostic releases that thread's locks, retaining its source stop and VM plan.
PUBLIC boom_provider_reference_boundary
boom_provider_reference_boundary PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 test rbx,rbx
 jz rpr_boundary_zero
 cmp DWORD PTR [rbx+12],0
 jne rpr_boundary_zero
 cmp QWORD PTR [rbx+16],0
 jne rpr_boundary_zero
 mov eax,DWORD PTR [rbx]
 sub eax,0B001h
 cmp eax,1
 ja rpr_boundary_zero
 mov edi,eax
 mov rcx,rsi
 call rpr_valid
 test eax,eax
 jz rpr_boundary_zero
 mov eax,DWORD PTR [rsi+8]
 sub eax,2
 cmp eax,2
 ja rpr_boundary_zero
 test edi,edi
 jz rpr_boundary_release
 test eax,eax
 jz rpr_boundary_zero
 mov ecx,DWORD PTR [rsi+12]
 call TlsGetValue
 cmp rax,rbx
 jne rpr_boundary_zero
 mov rcx,QWORD PTR [rsi+24]
 call boom_reference_pending_stopping
 cmp eax,1
 jne rpr_boundary_zero
rpr_boundary_release:
 mov rcx,QWORD PTR [rsi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rbx
 lea r8,[rsp+32]
 mov r9d,edi
 call boom_monitor_abort_owned
 test eax,eax
 jnz rpr_boundary_error
 mov rax,QWORD PTR [rsp+32]
 lock add QWORD PTR [rsi+64],rax
 test edi,edi
 jz rpr_boundary_zero
 mov ecx,DWORD PTR [rsi+12]
 xor edx,edx
 call TlsSetValue
 test eax,eax
 jz rpr_boundary_tls_error
 lock inc QWORD PTR [rsi+56]
 mov QWORD PTR [rbx],0
 mov DWORD PTR [rbx+8],0
 mov eax,1
 jmp rpr_boundary_done
rpr_boundary_tls_error:
 call GetLastError
rpr_boundary_error:
 mov edx,eax
 xor eax,eax
 lock cmpxchg DWORD PTR [rsi+72],edx
rpr_boundary_zero:
 xor eax,eax
rpr_boundary_done:
 add rsp,48
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_reference_boundary ENDP
