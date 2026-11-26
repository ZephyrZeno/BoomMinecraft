; VM-owned frozen native-image key/value properties, handwritten MASM.
; Returns a fresh String[] with immutable rooted literals and a final null key.
; No JVM/CRT calls, host environment parsing, or automatic GC.
option casemap:none
EXTERN boom_reference_array_new:PROC
EXTERN boom_string_load:PROC
PUBLIC boom_vm_properties
.code
; (ctx RCX, ignored argv RDX, pool R8) -> String[] / NULL.
; Pool64: magic0 ABI4 pairCount8 reserved12 heapCell16 stringPool24,
; arrayLayout32 rows40 boundHeap48 reserved56. Each row: keyID,valueID DWORD.
boom_vm_properties PROC FRAME
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
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,r8
    cmp DWORD PTR [rbx],0
    jne vm_properties_error
    test rsi,rsi
    jz vm_properties_bad
    cmp DWORD PTR [rsi],0564D5052h
    jne vm_properties_bad
    cmp DWORD PTR [rsi+4],1
    je vm_properties_abi_ready
    cmp DWORD PTR [rsi+4],2
    jne vm_properties_bad
    cmp QWORD PTR [rsi+80],0
    je vm_properties_bad
    cmp QWORD PTR [rsi+96],0
    je vm_properties_bad
    cmp QWORD PTR [rsi+104],0
    je vm_properties_bad
vm_properties_abi_ready:
    cmp DWORD PTR [rsi+12],0
    jne vm_properties_bad
    cmp QWORD PTR [rsi+56],0
    jne vm_properties_bad
    mov eax,DWORD PTR [rsi+8]
    test eax,eax
    jz vm_properties_bad
    cmp eax,2048
    ja vm_properties_bad
    mov rdi,QWORD PTR [rsi+24]
    test rdi,rdi
    jz vm_properties_bad
    cmp DWORD PTR [rsi+4],2
    je vm_properties_source_pool
    cmp DWORD PTR [rdi],053545250h
    jne vm_properties_bad
    cmp DWORD PTR [rdi+4],3
    jne vm_properties_bad
    jmp vm_properties_pool_ready
vm_properties_source_pool:
    cmp DWORD PTR [rdi],04A534C50h
    jne vm_properties_bad
    cmp DWORD PTR [rdi+4],1
    jne vm_properties_bad
vm_properties_pool_ready:
    cmp QWORD PTR [rsi+32],0
    je vm_properties_bad
    mov r13,QWORD PTR [rsi+40]
    test r13,r13
    jz vm_properties_bad
    mov rax,QWORD PTR [rsi+16]
    test rax,rax
    jz vm_properties_bad
    mov r12,QWORD PTR [rax]
    test r12,r12
    jz vm_properties_bad
    cmp DWORD PTR [r12],048454150h
    jne vm_properties_bad
    cmp DWORD PTR [r12+4],1
    jne vm_properties_bad
    mov rax,QWORD PTR [rdi+48]
    cmp DWORD PTR [rsi+4],2
    jne vm_properties_string_heap_ready
    mov rax,QWORD PTR [rdi+64]
vm_properties_string_heap_ready:
    test rax,rax
    jz vm_properties_bind
    cmp rax,r12
    jne vm_properties_bad
vm_properties_bind:
    xor eax,eax
    lock cmpxchg QWORD PTR [rsi+48],r12
    test rax,rax
    jz vm_properties_bound
    cmp rax,r12
    jne vm_properties_bad
vm_properties_bound:
    ; Validate every immutable literal index before allocating the result.
    mov ecx,DWORD PTR [rsi+8]
    shl ecx,1
    xor edx,edx
vm_properties_validate:
    mov eax,DWORD PTR [r13+rdx*4]
    cmp DWORD PTR [rsi+4],2
    je vm_properties_validate_source
    cmp eax,DWORD PTR [rdi+16]
    jmp vm_properties_validate_index
vm_properties_validate_source:
    cmp eax,DWORD PTR [rdi+8]
vm_properties_validate_index:
    jae vm_properties_bad
    inc edx
    cmp edx,ecx
    jb vm_properties_validate
    lea edx,[rcx+1]
    cmp DWORD PTR [rsi+4],2
    je vm_properties_source_array
    mov rcx,r12
    mov r8,QWORD PTR [rsi+32]
    mov r9,rbx
    call boom_reference_array_new
    jmp vm_properties_array_ready
vm_properties_source_array:
    mov r8d,edx
    mov rcx,rbx
    mov rdx,rsi
    call QWORD PTR [rsi+80]
vm_properties_array_ready:
    test rax,rax
    jz vm_properties_error
    mov r14,rax
    xor edi,edi
vm_properties_fill:
    cmp DWORD PTR [rsi+4],2
    je vm_properties_source_literal
    mov rcx,r12
    mov rdx,QWORD PTR [rsi+24]
    mov r8d,DWORD PTR [r13+rdi*4]
    mov r9,rbx
    call boom_string_load
    jmp vm_properties_literal_ready
vm_properties_source_literal:
    mov rcx,rbx
    mov rdx,rsi
    mov r8d,DWORD PTR [r13+rdi*4]
    call QWORD PTR [rsi+96]
vm_properties_literal_ready:
    cmp DWORD PTR [rbx],0
    jne vm_properties_error
    mov QWORD PTR [r14+rdi*8],rax
    inc edi
    mov eax,DWORD PTR [rsi+8]
    shl eax,1
    cmp edi,eax
    jb vm_properties_fill
    mov rax,r14
    jmp vm_properties_done
vm_properties_bad:
    mov DWORD PTR [rbx],7
vm_properties_error:
    xor eax,eax
vm_properties_done:
    add rsp,40
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_vm_properties ENDP
END
