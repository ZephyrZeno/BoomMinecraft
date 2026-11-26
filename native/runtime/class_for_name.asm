; Source-bound Class.forName0, entirely MASM. No JVM or host lookup callbacks.
; FNAM96/1: mirrors8,strings16,heapCell24,loaders32,catalog40,count48D,
; typeCount52D,initializers56,ready64,messageOffset72D,flags76D=0,res80/88=0.
; Catalog row32: UTF16*0,length8D,hash12D,initiator16D,typeId20D,
; flags24D (array1),reserved28D=0. Unknown linked type = FFFFFFFF.
; Rows sort by unsigned (initiator<<32)|hash. Hash collisions compare all units.
option casemap:none
EXTERN boom_heap_contains:PROC
EXTERN boom_string_view:PROC
EXTERN boom_string_allocate:PROC
EXTERN boom_mirror_typeid:PROC
EXTERN boom_mirror_load:PROC
EXTERN boom_class_loader_key:PROC
EXTERN boom_class_ensure32:PROC
EXTERN boom_exception_create:PROC
PUBLIC boom_class_for_name
.code
; find(pool RCX,initiator EDX,chars R8,length R9D)->row/NULL; no allocation.
for_name_find PROC FRAME
    sub rsp,56
    .allocstack 56
    .endprolog
    mov QWORD PTR [rsp],r8
    mov DWORD PTR [rsp+8],r9d
    mov QWORD PTR [rsp+16],rcx
    xor eax,eax
    xor r10d,r10d
for_name_hash:
    cmp r10d,r9d
    jae for_name_hash_done
    imul eax,eax,31
    movzx r11d,WORD PTR [r8+r10*2]
    add eax,r11d
    inc r10d
    jmp for_name_hash
for_name_hash_done:
    shl rdx,32
    or rdx,rax
    mov r8,rdx
    mov r11,QWORD PTR [rcx+40]
    mov edx,DWORD PTR [rcx+48]
    xor ecx,ecx
for_name_lower:
    cmp ecx,edx
    jae for_name_lower_done
    mov r10d,edx
    sub r10d,ecx
    shr r10d,1
    add r10d,ecx
    mov eax,r10d
    shl rax,5
    add rax,r11
    cmp QWORD PTR [rax+12],r8
    jb for_name_lower_right
    mov edx,r10d
    jmp for_name_lower
for_name_lower_right:
    lea ecx,[r10+1]
    jmp for_name_lower
for_name_lower_done:
    mov rdx,QWORD PTR [rsp+16]
    mov edx,DWORD PTR [rdx+48]
    mov eax,ecx
    shl rax,5
    add rax,r11
    mov QWORD PTR [rsp+24],r8
    mov DWORD PTR [rsp+32],edx
for_name_collision:
    cmp ecx,DWORD PTR [rsp+32]
    jae for_name_find_no
    mov r8,QWORD PTR [rsp+24]
    cmp QWORD PTR [rax+12],r8
    jne for_name_find_no
    mov r9d,DWORD PTR [rsp+8]
    cmp DWORD PTR [rax+8],r9d
    jne for_name_collision_next
    mov QWORD PTR [rsp+40],rcx
    mov rdx,QWORD PTR [rax]
    mov r8,QWORD PTR [rsp]
    xor ecx,ecx
for_name_compare:
    cmp ecx,r9d
    jae for_name_find_done
    movzx r10d,WORD PTR [r8+rcx*2]
    cmp WORD PTR [rdx+rcx*2],r10w
    jne for_name_compare_no
    inc ecx
    jmp for_name_compare
for_name_compare_no:
    mov rcx,QWORD PTR [rsp+40]
for_name_collision_next:
    inc ecx
    add rax,32
    jmp for_name_collision
for_name_find_no:
    xor eax,eax
for_name_find_done:
    add rsp,56
    ret
for_name_find ENDP

; (Context32,argv{name,initialize,loader,caller},FNAM96)->Class/NULL.
; EDX=1 means a real initializer failed; its original PC/method are preserved.
boom_class_for_name PROC
    xor r9d,r9d
    jmp for_name_resolve
boom_class_for_name ENDP
PUBLIC boom_class_find_bootstrap
boom_class_find_bootstrap PROC
    mov r9d,1
    jmp for_name_resolve
boom_class_find_bootstrap ENDP
for_name_resolve PROC FRAME
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
    sub rsp,96
    .allocstack 96
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    mov DWORD PTR [rsp+72],r9d
    test rbx,rbx
    jz for_name_zero
    cmp DWORD PTR [rbx],0
    jne for_name_zero
    test rsi,rsi
    jz for_name_bad
    test rdi,rdi
    jz for_name_bad
    cmp DWORD PTR [rdi],04D414E46h
    jne for_name_bad
    cmp DWORD PTR [rdi+4],1
    jne for_name_bad
    cmp DWORD PTR [rdi+76],0
    jne for_name_bad
    cmp QWORD PTR [rdi+80],0
    jne for_name_bad
    cmp QWORD PTR [rdi+88],0
    jne for_name_bad
    mov ecx,8
for_name_pool_ptrs:
    cmp QWORD PTR [rdi+rcx],0
    je for_name_bad
    add ecx,8
    cmp ecx,48
    jb for_name_pool_ptrs
    cmp QWORD PTR [rdi+56],0
    je for_name_bad
    cmp QWORD PTR [rdi+64],0
    je for_name_bad
    mov eax,DWORD PTR [rdi+48]
    dec eax
    cmp eax,1048575
    ja for_name_bad
    mov eax,DWORD PTR [rdi+52]
    dec eax
    cmp eax,16383
    ja for_name_bad
    inc eax
    mov rdx,QWORD PTR [rdi+8]
    cmp eax,DWORD PTR [rdx+12]
    jne for_name_bad
    mov rax,QWORD PTR [rdi+24]
    mov r12,QWORD PTR [rax]
    test r12,r12
    jz for_name_bad
    mov rax,QWORD PTR [rdx+48]
    test rax,rax
    jz for_name_heap_ok
    cmp rax,r12
    jne for_name_bad
for_name_heap_ok:
    mov rdx,QWORD PTR [rsi]
    mov QWORD PTR [rsp+48],rdx
    test rdx,rdx
    jz for_name_null
    mov rcx,r12
    call boom_heap_contains
    test eax,eax
    jz for_name_bad
    mov rax,QWORD PTR [rdi+16]
    cmp DWORD PTR [rax],053545250h
    jne for_name_bad
    cmp DWORD PTR [rax+4],3
    jne for_name_bad
    mov rax,QWORD PTR [rax+40]
    mov rdx,QWORD PTR [rsp+48]
    cmp QWORD PTR [rdx-8],rax
    jne for_name_bad
    cmp QWORD PTR [rdx-16],16
    jne for_name_bad
    cmp DWORD PTR [rdx-20],1
    jne for_name_bad
    mov rdx,QWORD PTR [rdx]
    mov rcx,r12
    call boom_heap_contains
    test eax,eax
    jz for_name_bad
    mov rcx,QWORD PTR [rsp+48]
    mov rdx,QWORD PTR [rdi+16]
    mov rdx,QWORD PTR [rdx+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne for_name_zero
    mov r13,rax
    mov r14d,edx
    mov QWORD PTR [rsp+56],r13
    mov DWORD PTR [rsp+64],r14d
    cmp DWORD PTR [rsp+72],0
    jne for_name_bootstrap_loader
    mov eax,DWORD PTR [rsi+8]
    mov DWORD PTR [rsp+32],eax
    mov rdx,QWORD PTR [rsi+16]
    jmp for_name_loader_ready
for_name_bootstrap_loader:
    mov DWORD PTR [rsp+32],0
    xor edx,edx
for_name_loader_ready:
    mov rcx,rbx
    mov r8,QWORD PTR [rdi+32]
    call boom_class_loader_key
    cmp DWORD PTR [rbx],0
    jne for_name_zero
    mov r15d,eax
    cmp DWORD PTR [rsp+72],0
    jne for_name_caller_ok
    mov rdx,QWORD PTR [rsi+24]
    test rdx,rdx
    jz for_name_caller_ok
    mov rcx,r12
    call boom_heap_contains
    test eax,eax
    jz for_name_bad
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi+24]
    mov r8,QWORD PTR [rdi+8]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne for_name_zero
for_name_caller_ok:
    mov rcx,rdi
    mov edx,r15d
    mov r8,r13
    mov r9d,r14d
    call for_name_find
    test rax,rax
    jz for_name_missing
    cmp DWORD PTR [rax+28],0
    jne for_name_bad
    cmp DWORD PTR [rax+24],1
    ja for_name_bad
    mov ecx,DWORD PTR [rax+20]
    cmp ecx,-1
    je for_name_unlinked
    cmp ecx,DWORD PTR [rdi+52]
    jae for_name_bad
    mov DWORD PTR [rsp+36],ecx
    cmp DWORD PTR [rsp+32],0
    je for_name_mirror
    cmp DWORD PTR [rax+24],1
    je for_name_mirror
    mov rdx,QWORD PTR [rdi+64]
    cmp BYTE PTR [rdx+rcx],1
    jne for_name_unlinked
    mov rdx,QWORD PTR [rdi+56]
    mov rcx,QWORD PTR [rdx+rcx*8]
    test rcx,rcx
    jz for_name_bad
    mov rdx,rbx
    call boom_class_ensure32
    test eax,eax
    jz for_name_mirror
    xor eax,eax
    mov edx,1
    jmp for_name_done
for_name_mirror:
    mov rcx,r12
    mov rdx,QWORD PTR [rdi+8]
    mov r8d,DWORD PTR [rsp+36]
    mov r9,rbx
    call boom_mirror_load
    xor edx,edx
    jmp for_name_done
for_name_missing:
    cmp DWORD PTR [rsp+72],0
    jne for_name_zero
    ; A valid array whose component exists needs dynamic array metadata. Until
    ; that service is linked, distinguish it from an actually absent class.
    cmp r14d,2
    jb for_name_not_found
    cmp WORD PTR [r13],05Bh
    jne for_name_not_found
    xor ecx,ecx
for_name_rank:
    cmp ecx,r14d
    jae for_name_not_found
    cmp WORD PTR [r13+rcx*2],05Bh
    jne for_name_component
    inc ecx
    cmp ecx,255
    ja for_name_not_found
    jmp for_name_rank
for_name_component:
    movzx eax,WORD PTR [r13+rcx*2]
    cmp eax,04Ch
    je for_name_reference_array
    lea edx,[rcx+1]
    cmp edx,r14d
    jne for_name_not_found
    cmp eax,042h
    je for_name_unlinked
    cmp eax,043h
    je for_name_unlinked
    cmp eax,044h
    je for_name_unlinked
    cmp eax,046h
    je for_name_unlinked
    cmp eax,049h
    je for_name_unlinked
    cmp eax,04Ah
    je for_name_unlinked
    cmp eax,053h
    je for_name_unlinked
    cmp eax,05Ah
    je for_name_unlinked
    jmp for_name_not_found
for_name_reference_array:
    lea eax,[r14-1]
    cmp WORD PTR [r13+rax*2],03Bh
    jne for_name_not_found
    inc ecx
    sub eax,ecx
    jle for_name_not_found
    lea r8,[r13+rcx*2]
    mov r9d,eax
    mov QWORD PTR [rsp+56],r8
    mov DWORD PTR [rsp+64],r9d
    mov rcx,rdi
    mov edx,r15d
    call for_name_find
    test rax,rax
    jnz for_name_unlinked
for_name_not_found:
    mov rcx,rbx
    mov edx,19
    xor r8d,r8d
    mov r9d,2
    call boom_exception_create
    test rax,rax
    jz for_name_zero
    mov QWORD PTR [rsp+80],rax
    mov rdx,QWORD PTR [rsp+48]
    test r15d,r15d
    jz for_name_message_copy
    cmp r13,QWORD PTR [rsp+56]
    je for_name_message_ready
for_name_message_copy:
    mov rcx,r12
    mov rdx,QWORD PTR [rdi+16]
    mov r8d,DWORD PTR [rsp+64]
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz for_name_zero
    mov rdx,rax
    mov r10,QWORD PTR [rax]
    mov r8,QWORD PTR [rsp+56]
    mov r9d,DWORD PTR [rsp+64]
    xor ecx,ecx
for_name_message_units:
    cmp ecx,r9d
    jae for_name_message_ready
    movzx eax,WORD PTR [r8+rcx*2]
    test r15d,r15d
    jnz for_name_message_unit
    cmp eax,02Eh
    jne for_name_message_unit
    mov eax,02Fh
for_name_message_unit:
    mov WORD PTR [r10+rcx*2],ax
    inc ecx
    jmp for_name_message_units
for_name_message_ready:
    mov rax,QWORD PTR [rsp+80]
    mov ecx,DWORD PTR [rdi+72]
    test ecx,7
    jnz for_name_bad
    mov r10d,DWORD PTR [rax-20]
    shl r10,3
    cmp rcx,r10
    jae for_name_bad
    mov QWORD PTR [rax+rcx],rdx
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp for_name_zero
for_name_null:
    cmp DWORD PTR [rsp+72],0
    jne for_name_zero
    mov DWORD PTR [rbx],4
    jmp for_name_zero
for_name_unlinked:
    mov DWORD PTR [rbx],20
    jmp for_name_zero
for_name_bad:
    mov DWORD PTR [rbx],7
for_name_zero:
    xor eax,eax
    xor edx,edx
for_name_done:
    add rsp,96
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
for_name_resolve ENDP
END
