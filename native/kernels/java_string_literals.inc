; Source-layout Java String literals. No JVM, C runtime, or legacy String object.
; literal(Context32 RCX, pool RDX, canonical index R8D) -> String oop / NULL.
; Pool80: magic0 ABI4 count8 compact12 entries16 roots24 states32 layout40,
;         valueOffset48 coderOffset52 hashOffset56 zeroOffset60 heap64 paged72.
; paged=1: entries points to 256-entry pages; paged=0: flat Entry16 array.
; Entry16: UTF16 pointer0 length8 hash12. Root16: canonical oop0 temporary byte[]8.
; States: 0 unresolved, 1 constructing, 2 published. Immutable source metadata.
; Caller keeps metadata/heap alive and includes both root cells in explicit GC.
; Existing pending errors survive unchanged. This service does not run Java clinit.
option casemap:none
EXTERN boom_array_new:PROC
EXTERN boom_object_new:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
PUBLIC boom_java_string_literal
.code
boom_java_string_literal PROC FRAME
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
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    test rbx,rbx
    jz java_literal_return_null
    cmp DWORD PTR [rbx],0
    jne java_literal_return_null
    test rsi,rsi
    jz java_literal_bad
    cmp DWORD PTR [rsi],04A534C50h
    jne java_literal_bad
    cmp DWORD PTR [rsi+4],1
    jne java_literal_bad
    cmp DWORD PTR [rsi+8],0100000h
    ja java_literal_bad
    cmp DWORD PTR [rsi+12],1
    ja java_literal_bad
    cmp DWORD PTR [rsi+72],1
    ja java_literal_bad
    cmp r8d,DWORD PTR [rsi+8]
    jae java_literal_index
    cmp QWORD PTR [rsi+64],0
    je java_literal_bad
    mov r10,QWORD PTR [rsi+40]
    test r10,r10
    jz java_literal_bad
    cmp DWORD PTR [r10],04F424A43h
    jne java_literal_bad
    cmp DWORD PTR [r10+4],2
    jne java_literal_bad
    cmp DWORD PTR [r10+16],1
    jne java_literal_bad
    cmp DWORD PTR [r10+20],4
    jne java_literal_bad
    cmp QWORD PTR [r10+8],14
    jb java_literal_bad
    cmp QWORD PTR [r10+8],32
    ja java_literal_bad
    cmp DWORD PTR [rsi+48],0
    jne java_literal_bad
    mov r11d,DWORD PTR [rsi+56]
    cmp r11d,8
    jb java_literal_bad
    test r11b,3
    jnz java_literal_bad
    lea eax,[r11+4]
    cmp rax,QWORD PTR [r10+8]
    ja java_literal_bad
    mov edx,DWORD PTR [rsi+52]
    cmp edx,8
    jb java_literal_bad
    cmp rdx,QWORD PTR [r10+8]
    jae java_literal_bad
    cmp edx,r11d
    jb java_literal_coder_outside_hash
    cmp edx,eax
    jb java_literal_bad
java_literal_coder_outside_hash:
    mov ecx,DWORD PTR [rsi+60]
    cmp ecx,8
    jb java_literal_bad
    cmp rcx,QWORD PTR [r10+8]
    jae java_literal_bad
    cmp ecx,edx
    je java_literal_bad
    cmp ecx,r11d
    jb java_literal_zero_outside_hash
    cmp ecx,eax
    jb java_literal_bad
java_literal_zero_outside_hash:
    mov eax,r8d
    shl rax,4
    mov rdi,QWORD PTR [rsi+16]
    mov r12,QWORD PTR [rsi+24]
    mov r13,QWORD PTR [rsi+32]
    test rdi,rdi
    jz java_literal_bad
    test r12,r12
    jz java_literal_bad
    test r13,r13
    jz java_literal_bad
    add r12,rax
    cmp DWORD PTR [rsi+72],0
    je java_literal_flat_entry
    mov eax,r8d
    shr eax,8
    mov rdi,QWORD PTR [rdi+rax*8]
    test rdi,rdi
    jz java_literal_bad
    mov eax,r8d
    and eax,255
    shl rax,4
java_literal_flat_entry:
    add rdi,rax
    mov eax,r8d
    lea r13,[r13+rax*4]
    cmp DWORD PTR [rdi+8],65535
    ja java_literal_bad
    cmp DWORD PTR [rdi+8],0
    je java_literal_retry
    cmp QWORD PTR [rdi],0
    je java_literal_bad
java_literal_retry:
    mov rax,QWORD PTR [r12]
    test rax,rax
    jnz java_literal_done
    xor eax,eax
    mov edx,1
    lock cmpxchg DWORD PTR [r13],edx
    je java_literal_construct
    cmp eax,1
    jne java_literal_bad
    mov DWORD PTR [rsp+36],1
    mov rcx,r13
    lea rdx,[rsp+36]
    mov r8d,4
    mov r9d,-1
    call WaitOnAddress
    jmp java_literal_retry
java_literal_construct:
    mov eax,DWORD PTR [rdi+8]
    mov DWORD PTR [rsp+32],eax
    mov r15d,1
    cmp DWORD PTR [rsi+12],0
    je java_literal_allocate_bytes
    mov r10,QWORD PTR [rdi]
    xor eax,eax
java_literal_scan_latin:
    cmp eax,DWORD PTR [rsp+32]
    jae java_literal_latin
    cmp WORD PTR [r10+rax*2],255
    ja java_literal_allocate_bytes
    inc eax
    jmp java_literal_scan_latin
java_literal_latin:
    xor r15d,r15d
java_literal_allocate_bytes:
    mov rcx,QWORD PTR [rsi+64]
    mov edx,DWORD PTR [rsp+32]
    mov ecx,r15d
    shl edx,cl
    mov rcx,QWORD PTR [rsi+64]
    mov r8d,8
    mov r9,rbx
    call boom_array_new
    test rax,rax
    jz java_literal_failed
    mov r14,rax
    mov QWORD PTR [r12+8],rax
    mov r10,QWORD PTR [rdi]
    xor eax,eax
    test r15d,r15d
    jnz java_literal_copy_utf16
java_literal_copy_latin:
    cmp eax,DWORD PTR [rsp+32]
    jae java_literal_allocate_string
    movzx edx,WORD PTR [r10+rax*2]
    mov BYTE PTR [r14+rax],dl
    inc eax
    jmp java_literal_copy_latin
java_literal_copy_utf16:
    cmp eax,DWORD PTR [rsp+32]
    jae java_literal_allocate_string
    mov dx,WORD PTR [r10+rax*2]
    mov WORD PTR [r14+rax*2],dx
    inc eax
    jmp java_literal_copy_utf16
java_literal_allocate_string:
    mov rcx,QWORD PTR [rsi+64]
    mov rdx,QWORD PTR [rsi+40]
    mov r8,rbx
    call boom_object_new
    test rax,rax
    jz java_literal_failed
    mov ecx,DWORD PTR [rsi+48]
    mov QWORD PTR [rax+rcx],r14
    mov ecx,DWORD PTR [rsi+52]
    mov BYTE PTR [rax+rcx],r15b
    mov edx,DWORD PTR [rdi+12]
    mov ecx,DWORD PTR [rsi+56]
    mov DWORD PTR [rax+rcx],edx
    test edx,edx
    sete dl
    mov ecx,DWORD PTR [rsi+60]
    mov BYTE PTR [rax+rcx],dl
    ; Publish fields before the root. Aligned MOV is release/acquire on x86-64.
    mov QWORD PTR [r12],rax
    mov QWORD PTR [r12+8],0
    mov DWORD PTR [r13],2
    mov QWORD PTR [rsp+40],rax
    mov rcx,r13
    call WakeByAddressAll
    mov rax,QWORD PTR [rsp+40]
    jmp java_literal_done
java_literal_failed:
    mov QWORD PTR [r12+8],0
    mov DWORD PTR [r13],0
    mov rcx,r13
    call WakeByAddressAll
    jmp java_literal_return_null
java_literal_index:
    mov DWORD PTR [rbx],5
    jmp java_literal_return_null
java_literal_bad:
    mov DWORD PTR [rbx],7
java_literal_return_null:
    xor eax,eax
java_literal_done:
    add rsp,64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_java_string_literal ENDP
