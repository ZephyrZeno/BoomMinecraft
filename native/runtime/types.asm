; Loader identity is descriptor identity. Compiler emits immutable descriptors.
; ABI 1, 40 bytes: magic0 ABI4 kind8 flags12 parent/component16 ancestors24 count32.
; kind: primitive0 class1 interface2 array3. Array marker flags on trusted class
; metadata only: bootstrap Object1 Cloneable2 Serializable4.
; assignable(source RCX,target RDX)->EAX 0/1. Null values handled by caller.
; All pointers must belong to a live validated metadata module; not a raw-pointer validator.
option casemap:none
PUBLIC boom_type_assignable
.code
boom_type_assignable PROC
    mov r11d, 256
type_again:
    test rcx, rcx
    jz type_no
    test rdx, rdx
    jz type_no
    cmp DWORD PTR [rcx], 054595045h
    jne type_no
    cmp DWORD PTR [rdx], 054595045h
    jne type_no
    cmp DWORD PTR [rcx+4], 1
    jne type_no
    cmp DWORD PTR [rdx+4], 1
    jne type_no
    mov eax, DWORD PTR [rcx+8]
    mov r8d, DWORD PTR [rdx+8]
    cmp eax, 3
    ja type_no
    cmp r8d, 3
    ja type_no
    cmp rcx, rdx
    je type_yes
    test eax, eax
    jz type_no
    test r8d, r8d
    jz type_no
    cmp eax, 3
    je type_array
    cmp r8d, 3
    je type_no
    mov r8d, DWORD PTR [rcx+32]
    cmp r8d, 4096
    ja type_no
    mov r9, QWORD PTR [rcx+24]
    test r8d, r8d
    jz type_no
    test r9, r9
    jz type_no
type_ancestor:
    cmp QWORD PTR [r9], rdx
    je type_yes
    add r9, 8
    dec r8d
    jnz type_ancestor
    jmp type_no
type_array:
    cmp r8d, 3
    jne type_array_marker
    ; Primitive component identity is handled by the next pass's equality check.
    mov rcx, QWORD PTR [rcx+16]
    mov rdx, QWORD PTR [rdx+16]
    dec r11d
    jnz type_again
    jmp type_no
type_array_marker:
    test DWORD PTR [rdx+12], 7
    jnz type_yes
type_no:
    xor eax, eax
    ret
type_yes:
    mov eax, 1
    ret
boom_type_assignable ENDP
END
