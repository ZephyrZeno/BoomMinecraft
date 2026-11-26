; Source-verified FileDescriptor fields and Windows standard handles. MASM only.
; service(Context16 RCX,argv RDX,pool R8,op R9D)->Java result.
; 0 initIDs,1 getHandle(int),2 getAppend(int); runtime IO:3 write,4 read,5 sync.
; Pool32: magic0 ABI4 table8 published16 reserved24.
; Table48: magic0 ABI4 layout8; (offset,width) fd16,handle24,append32;reserved40.
; IO argv: descriptor0,byte[]8,offset16,length24,append32. sync uses argv[0].
; IO buffers stay in the live heap; explicit GC requires all callers quiescent.
option casemap:none
EXTERN GetStdHandle:PROC
EXTERN ReadFile:PROC
EXTERN WriteFile:PROC
EXTERN FlushFileBuffers:PROC
EXTERN GetLastError:PROC
EXTERN boom_object_check:PROC
PUBLIC boom_fd_service
.code
; validate(pool RCX)->table/NULL, volatile registers only.
fd_validate PROC
    test rcx,rcx
    jz fd_invalid_table
    cmp DWORD PTR [rcx],04644504Ch
    jne fd_invalid_table
    cmp DWORD PTR [rcx+4],1
    jne fd_invalid_table
    cmp QWORD PTR [rcx+24],0
    jne fd_invalid_table
    mov rcx,QWORD PTR [rcx+8]
    test rcx,rcx
    jz fd_invalid_table
    cmp DWORD PTR [rcx],046445442h
    jne fd_invalid_table
    cmp DWORD PTR [rcx+4],1
    jne fd_invalid_table
    cmp QWORD PTR [rcx+40],0
    jne fd_invalid_table
    mov rdx,QWORD PTR [rcx+8]
    test rdx,rdx
    jz fd_invalid_table
    cmp DWORD PTR [rdx],04F424A43h
    jne fd_invalid_table
    mov r8d,DWORD PTR [rdx+20]
    cmp r8d,65536
    ja fd_invalid_table
    mov r9d,DWORD PTR [rdx+16]
    cmp r9d,r8d
    ja fd_invalid_table
    cmp DWORD PTR [rdx+4],1
    je fd_slots
    cmp DWORD PTR [rdx+4],2
    jne fd_invalid_table
    mov eax,r8d
    sub eax,r9d
    lea rax,[rax+r9*8]
    cmp QWORD PTR [rdx+8],rax
    jb fd_invalid_table
    jmp fd_payload_max
fd_slots:
    mov eax,r8d
    shl rax,3
    cmp QWORD PTR [rdx+8],rax
    jne fd_invalid_table
fd_payload_max:
    shl r8,3
    cmp QWORD PTR [rdx+8],r8
    ja fd_invalid_table
    shl r9,3
    cmp DWORD PTR [rcx+28],8
    jne fd_invalid_table
    mov eax,DWORD PTR [rcx+20]
    cmp eax,4
    je fd_width_ok
    cmp eax,8
    jne fd_invalid_table
fd_width_ok:
    mov eax,DWORD PTR [rcx+36]
    cmp eax,1
    je fd_fields
    cmp eax,8
    jne fd_invalid_table
fd_fields:
    xor r10d,r10d
fd_field_loop:
    mov r8d,DWORD PTR [rcx+r10+16]
    cmp r8,r9
    jb fd_invalid_table
    mov r11d,DWORD PTR [rcx+r10+20]
    mov eax,r11d
    dec eax
    test r8d,eax
    jnz fd_invalid_table
    add r8,r11
    cmp r8,QWORD PTR [rdx+8]
    ja fd_invalid_table
    add r10d,8
    cmp r10d,24
    jb fd_field_loop
    mov r8d,DWORD PTR [rcx+16]
    mov r9d,DWORD PTR [rcx+20]
    add r9,r8
    mov r10d,DWORD PTR [rcx+24]
    lea r11,[r10+8]
    cmp r9,r10
    jbe fd_overlap_append
    cmp r11,r8
    ja fd_invalid_table
fd_overlap_append:
    mov edx,DWORD PTR [rcx+32]
    mov eax,DWORD PTR [rcx+36]
    add rax,rdx
    cmp rax,r8
    jbe fd_overlap_handle
    cmp rdx,r9
    jb fd_invalid_table
fd_overlap_handle:
    cmp rax,r10
    jbe fd_table_ok
    cmp rdx,r11
    jb fd_invalid_table
fd_table_ok:
    mov rax,rcx
    ret
fd_invalid_table:
    xor eax,eax
    ret
fd_validate ENDP

boom_fd_service PROC FRAME
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
    sub rsp,112
    .allocstack 112
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov r12,r8
    mov r13d,r9d
    test rbx,rbx
    jz fd_zero
    cmp DWORD PTR [rbx],0
    jne fd_zero
    mov rcx,r12
    call fd_validate
    test rax,rax
    jz fd_bad
    mov rdi,rax
    cmp r13d,5
    ja fd_bad
    test r13d,r13d
    jz fd_register
    mov rax,QWORD PTR [r12+16]
    test rax,rax
    jz fd_unregistered
    cmp rax,rdi
    jne fd_bad
    test rsi,rsi
    jz fd_bad
    cmp r13d,1
    je fd_std_handle
    cmp r13d,2
    je fd_zero
    cmp r13d,5
    je fd_object
    mov r14,QWORD PTR [rsi+8]
    test r14,r14
    jz fd_null
    mov eax,DWORD PTR [r14-24]
    and eax,0FFFFFFFDh
    cmp eax,0B00B0001h
    jne fd_bad
    cmp QWORD PTR [r14-8],264
    jne fd_array_type
    cmp DWORD PTR [r14-20],0
    jne fd_bad
    movsxd rax,DWORD PTR [rsi+16]
    movsxd r15,DWORD PTR [rsi+24]
    test rax,rax
    js fd_bounds
    test r15,r15
    js fd_bounds
    lea rdx,[rax+r15]
    cmp rdx,QWORD PTR [r14-16]
    ja fd_bounds
    test r15,r15
    jz fd_zero
    add r14,rax
fd_object:
    mov rcx,QWORD PTR [rsi]
    mov rdx,QWORD PTR [rdi+8]
    mov r8,rbx
    call boom_object_check
    test rax,rax
    jz fd_zero
    mov QWORD PTR [rsp+56],rax
    mov edx,DWORD PTR [rdi+24]
    mov rax,QWORD PTR [rax+rdx]
    mov QWORD PTR [rsp+48],rax
    cmp r13d,5
    je fd_sync
    cmp r13d,4
    je fd_read
fd_write:
    mov rax,QWORD PTR [rsp+56]
    mov edx,DWORD PTR [rdi+24]
    mov rcx,QWORD PTR [rax+rdx]
    mov rdx,r14
    mov r8d,r15d
    lea r9,[rsp+40]
    mov DWORD PTR [rsp+40],0
    xor eax,eax
    cmp DWORD PTR [rsi+32],0
    je fd_write_ready
    mov QWORD PTR [rsp+64],0
    mov QWORD PTR [rsp+72],0
    mov QWORD PTR [rsp+80],-1
    mov QWORD PTR [rsp+88],0
    lea rax,[rsp+64]
fd_write_ready:
    mov QWORD PTR [rsp+32],rax
    call WriteFile
    test eax,eax
    jz fd_io_error
    mov eax,DWORD PTR [rsp+40]
    test eax,eax
    jz fd_io_error
    cmp rax,r15
    ja fd_io_error
    add r14,rax
    sub r15,rax
    jnz fd_write
    jmp fd_zero
fd_read:
    mov rcx,QWORD PTR [rsp+48]
    mov rdx,r14
    mov r8d,r15d
    lea r9,[rsp+40]
    mov DWORD PTR [rsp+40],0
    mov QWORD PTR [rsp+32],0
    call ReadFile
    test eax,eax
    jnz fd_read_count
    call GetLastError
    cmp eax,109
    je fd_eof
    jmp fd_io_error
fd_read_count:
    mov eax,DWORD PTR [rsp+40]
    test eax,eax
    jz fd_eof
    cmp rax,r15
    ja fd_io_error
    jmp fd_done
fd_eof:
    mov eax,-1
    jmp fd_done
fd_sync:
    mov rcx,QWORD PTR [rsp+48]
    call FlushFileBuffers
    test eax,eax
    jnz fd_zero
    call GetLastError
    cmp eax,5
    je fd_zero
    mov DWORD PTR [rbx],22
    jmp fd_zero
fd_std_handle:
    mov ecx,DWORD PTR [rsi]
    cmp ecx,2
    ja fd_no_handle
    neg ecx
    sub ecx,10
    call GetStdHandle
    jmp fd_done
fd_no_handle:
    mov rax,-1
    jmp fd_done
fd_register:
    xor eax,eax
    lock cmpxchg QWORD PTR [r12+16],rdi
    jz fd_zero
    cmp rax,rdi
    je fd_zero
fd_bad:
    mov DWORD PTR [rbx],7
    jmp fd_zero
fd_unregistered:
    mov DWORD PTR [rbx],20
    jmp fd_zero
fd_array_type:
    mov DWORD PTR [rbx],6
    jmp fd_zero
fd_null:
    mov DWORD PTR [rbx],4
    jmp fd_zero
fd_bounds:
    mov DWORD PTR [rbx],5
    jmp fd_zero
fd_io_error:
    mov DWORD PTR [rbx],21
fd_zero:
    xor eax,eax
fd_done:
    add rsp,112
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_fd_service ENDP
END
