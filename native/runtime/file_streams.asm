; Original FileInputStream/FileOutputStream fd field registration. MASM only.
; init(Context16 RCX,pool RDX); descriptor(Context16 RCX,stream RDX,pool R8).
; Pool32: magic0,ABI4,table8,published16,reserved24.
; Table32: magic0,ABI4,layout8,fdOffset16,width20,reserved24.
; Tables are immutable, module-owned; callers keep objects live until return.
option casemap:none
EXTERN boom_object_check:PROC
PUBLIC boom_stream_fields_init
PUBLIC boom_stream_descriptor
.code
stream_table_validate PROC
    test rcx,rcx
    jz stream_table_invalid
    cmp DWORD PTR [rcx],05346504Ch
    jne stream_table_invalid
    cmp DWORD PTR [rcx+4],1
    jne stream_table_invalid
    cmp QWORD PTR [rcx+24],0
    jne stream_table_invalid
    mov rcx,QWORD PTR [rcx+8]
    test rcx,rcx
    jz stream_table_invalid
    cmp DWORD PTR [rcx],053465442h
    jne stream_table_invalid
    cmp DWORD PTR [rcx+4],1
    jne stream_table_invalid
    cmp QWORD PTR [rcx+24],0
    jne stream_table_invalid
    cmp DWORD PTR [rcx+20],8
    jne stream_table_invalid
    mov rdx,QWORD PTR [rcx+8]
    test rdx,rdx
    jz stream_table_invalid
    cmp DWORD PTR [rdx],04F424A43h
    jne stream_table_invalid
    mov r8d,DWORD PTR [rdx+20]
    cmp r8d,65536
    ja stream_table_invalid
    mov r9d,DWORD PTR [rdx+16]
    test r9d,r9d
    jz stream_table_invalid
    cmp r9d,r8d
    ja stream_table_invalid
    cmp DWORD PTR [rdx+4],1
    je stream_table_slots
    cmp DWORD PTR [rdx+4],2
    jne stream_table_invalid
    mov eax,r8d
    sub eax,r9d
    lea rax,[rax+r9*8]
    cmp QWORD PTR [rdx+8],rax
    jb stream_table_invalid
    jmp stream_table_max
stream_table_slots:
    mov eax,r8d
    shl rax,3
    cmp QWORD PTR [rdx+8],rax
    jne stream_table_invalid
stream_table_max:
    shl r8,3
    cmp QWORD PTR [rdx+8],r8
    ja stream_table_invalid
    shl r9,3
    mov eax,DWORD PTR [rcx+16]
    test eax,7
    jnz stream_table_invalid
    cmp rax,r9
    jae stream_table_invalid
    add rax,8
    cmp rax,QWORD PTR [rdx+8]
    ja stream_table_invalid
    mov rax,rcx
    ret
stream_table_invalid:
    xor eax,eax
    ret
stream_table_validate ENDP

boom_stream_fields_init PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    cmp DWORD PTR [rbx],0
    jne stream_init_done
    mov rcx,rsi
    call stream_table_validate
    test rax,rax
    jz stream_init_invalid
    mov rdx,rax
    xor eax,eax
    lock cmpxchg QWORD PTR [rsi+16],rdx
    jz stream_init_done
    cmp rax,rdx
    je stream_init_done
stream_init_invalid:
    mov DWORD PTR [rbx],7
stream_init_done:
    xor eax,eax
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_stream_fields_init ENDP

boom_stream_descriptor PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    cmp DWORD PTR [rbx],0
    jne stream_get_error
    mov rcx,rdi
    call stream_table_validate
    test rax,rax
    jz stream_get_invalid
    mov rdx,QWORD PTR [rdi+16]
    test rdx,rdx
    jz stream_get_unregistered
    cmp rdx,rax
    jne stream_get_invalid
    mov rdi,rax
    mov rcx,rsi
    mov rdx,QWORD PTR [rdi+8]
    mov r8,rbx
    call boom_object_check
    cmp DWORD PTR [rbx],0
    jne stream_get_error
    mov eax,DWORD PTR [rdi+16]
    mov rax,QWORD PTR [rsi+rax]
    jmp stream_get_done
stream_get_unregistered:
    mov DWORD PTR [rbx],20
    jmp stream_get_error
stream_get_invalid:
    mov DWORD PTR [rbx],7
stream_get_error:
    xor eax,eax
stream_get_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_stream_descriptor ENDP
END
