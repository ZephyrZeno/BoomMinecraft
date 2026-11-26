; Reflection primitive argument widening, entirely ASM.
; (Context32 RCX,sourceKind EDX,targetKind R8D,valueBits R9)->slot bits RAX.
; Kinds: Z0 B1 C2 S3 I4 J5 F6 D7. No heap access or Java callbacks.
; I-family results occupy the low DWORD; J/D occupy the full QWORD.
; Java conversions use round-to-nearest with gradual underflow, preserving the
; caller's complete MXCSR, including its previous exception status flags.
PUBLIC boom_constructor_widen
.code
boom_constructor_widen PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 test rcx,rcx
 jz cw_zero
 cmp DWORD PTR [rcx],0
 jne cw_zero
 cmp edx,7
 ja cw_bad
 cmp r8d,7
 ja cw_bad
 stmxcsr DWORD PTR [rsp+32]
 mov DWORD PTR [rsp+36],01F80h
 ldmxcsr DWORD PTR [rsp+36]
 mov rax,r9
 cmp edx,0
 je cw_boolean
 cmp edx,1
 je cw_byte
 cmp edx,2
 je cw_char
 cmp edx,3
 je cw_short
 cmp edx,4
 je cw_int
 cmp edx,6
 je cw_float
 jmp cw_value
cw_boolean:
 and eax,1
 jmp cw_value
cw_byte:
 movsx eax,r9b
 jmp cw_value
cw_char:
 movzx eax,r9w
 jmp cw_value
cw_short:
 movsx eax,r9w
 jmp cw_value
cw_int:
 mov eax,r9d
 jmp cw_value
cw_float:
 mov eax,r9d
cw_value:
 cmp edx,r8d
 je cw_done
 test edx,edx
 jz cw_argument
 cmp r8d,3
 jb cw_argument
 je cw_to_short
 cmp r8d,4
 je cw_to_int
 cmp r8d,5
 je cw_to_long
 cmp r8d,6
 je cw_to_float
 ; target D7. Only integer kinds and F6 can widen here.
 cmp edx,6
 ja cw_argument
 je cw_float_double
 cmp edx,5
 je cw_long_double
 cvtsi2sd xmm0,eax
 movq rax,xmm0
 jmp cw_done
cw_float_double:
 movd xmm0,eax
 cvtss2sd xmm0,xmm0
 movq rax,xmm0
 jmp cw_done
cw_long_double:
 cvtsi2sd xmm0,rax
 movq rax,xmm0
 jmp cw_done
cw_to_short:
 cmp edx,1
 jne cw_argument
 jmp cw_done
cw_to_int:
 cmp edx,3
 ja cw_argument
 jmp cw_done
cw_to_long:
 cmp edx,4
 ja cw_argument
 movsxd rax,eax
 jmp cw_done
cw_to_float:
 cmp edx,5
 ja cw_argument
 je cw_long_float
 cvtsi2ss xmm0,eax
 movd eax,xmm0
 jmp cw_done
cw_long_float:
 cvtsi2ss xmm0,rax
 movd eax,xmm0
 jmp cw_done
cw_argument:
 mov DWORD PTR [rcx],18
 xor eax,eax
cw_done:
 ldmxcsr DWORD PTR [rsp+32]
 add rsp,40
 ret
cw_bad:
 mov DWORD PTR [rcx],7
cw_zero:
 xor eax,eax
 add rsp,40
 ret
boom_constructor_widen ENDP
