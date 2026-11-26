; No mapped archive, no archive dumping, no class-list recording.
; Java CDS <clinit> and every caller initializer execute normally.
; service(Context16 RCX,argv RDX,profile R8,op R9D)->0.
; Profile32: magic0 ABI4 flags8 reserved12 mirrorPool16 reserved24.
; op0 validates a Class mirror, leaving its static state untouched;
; op1/2/3 report the actual disabled flags; op4 is the non-dumping seed0.
option casemap:none
EXTERN boom_mirror_typeid:PROC
PUBLIC boom_cds_service
.code
boom_cds_service PROC FRAME
    sub rsp, 40
    .allocstack 40
    .endprolog
    test rcx, rcx
    jz cds_done
    cmp DWORD PTR [rcx], 0
    jne cds_done
    test r8, r8
    jz cds_invalid
    cmp DWORD PTR [r8], 043445350h
    jne cds_invalid
    cmp DWORD PTR [r8+4], 1
    jne cds_invalid
    cmp QWORD PTR [r8+8], 0
    jne cds_invalid
    cmp QWORD PTR [r8+16], 0
    je cds_invalid
    cmp QWORD PTR [r8+24], 0
    jne cds_invalid
    cmp r9d, 4
    ja cds_invalid
    test r9d, r9d
    jnz cds_done
    test rdx, rdx
    jz cds_invalid
    mov rdx, QWORD PTR [rdx]
    mov r8, QWORD PTR [r8+16]
    call boom_mirror_typeid
    jmp cds_done
cds_invalid:
    mov DWORD PTR [rcx], 7
cds_done:
    xor eax, eax
    add rsp, 40
    ret
boom_cds_service ENDP
END
