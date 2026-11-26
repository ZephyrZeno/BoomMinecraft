; VM identity hash for live, typed references in the nonmoving Heap1.
; The caller checks runtime type/access. No object fields, locks or allocations.
; Pointer reuse after an object's lifetime is allowed; hashes need not be unique.
; A moving heap must preserve identities before adopting this ABI.
option casemap:none
PUBLIC boom_identity_hash
.code
; hash(Context16/32 RCX,reference RDX)->nonnegative Java int; NULL -> 0.
boom_identity_hash PROC
    xor eax,eax
    test rcx,rcx
    jz identity_hash_done
    cmp DWORD PTR [rcx],0
    jne identity_hash_done
    test rdx,rdx
    jz identity_hash_done
    mov rax,rdx
    shr rax,32
    xor eax,edx
    mov r10d,eax
    shr r10d,16
    xor eax,r10d
    imul eax,eax,07FEB352Dh
    mov r10d,eax
    shr r10d,15
    xor eax,r10d
    mov r10d,0846CA68Bh
    imul eax,r10d
    mov r10d,eax
    shr r10d,16
    xor eax,r10d
    and eax,07FFFFFFFh
    jnz identity_hash_done
    inc eax
identity_hash_done:
    ret
boom_identity_hash ENDP
END
