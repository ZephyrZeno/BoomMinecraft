; Source CDS policy: no archive mapped, no dumping, no class-list recording.
; Profile32/2: magic0 ABI4 flags8 reserved12 normal-ClassPool16 reserved24.
; Context32/argv/profile/op -> raw result. Original Java clinit always runs.
; op0 validates a canonical normal Class without initializing the target.
; op1/2/3 report disabled facilities; op4 is the specified non-dumping seed.
PUBLIC boom_provider_cds_service
.code
boom_provider_cds_service PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 test rcx,rcx
 jz provider_cds_done
 cmp DWORD PTR [rcx],0
 jne provider_cds_done
 test r8,r8
 jz provider_cds_bad
 cmp DWORD PTR [r8],043445350h
 jne provider_cds_bad
 cmp DWORD PTR [r8+4],2
 jne provider_cds_bad
 cmp QWORD PTR [r8+8],0
 jne provider_cds_bad
 cmp QWORD PTR [r8+16],0
 je provider_cds_bad
 cmp QWORD PTR [r8+24],0
 jne provider_cds_bad
 cmp r9d,4
 ja provider_cds_bad
 test r9d,r9d
 jnz provider_cds_done
 test rdx,rdx
 jz provider_cds_bad
 mov r10,QWORD PTR [rdx]
 mov rdx,QWORD PTR [r8+16]
 mov r8,r10
 call boom_java_class_typeid
 jmp provider_cds_done
provider_cds_bad:
 mov DWORD PTR [rcx],7
provider_cds_done:
 xor eax,eax
 add rsp,40
 ret
boom_provider_cds_service ENDP
