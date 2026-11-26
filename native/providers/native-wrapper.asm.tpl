.code
PUBLIC boom_m{method}
boom_m{method} PROC FRAME
 sub rsp,56
 .allocstack 56
 .endprolog
 mov QWORD PTR [rsp+32],rcx
 mov QWORD PTR [rsp+40],rdx
 test rcx,rcx
 jz boom_m{method}_provider_zero
 cmp DWORD PTR [rcx],0
 jne boom_m{method}_provider_zero
 lea rcx,boom_class{class_id}
 mov rdx,QWORD PTR [rsp+32]
 call boom_class_ensure32
 test eax,eax
 jnz boom_m{method}_provider_zero
 mov rcx,QWORD PTR [rsp+32]
 mov rdx,QWORD PTR [rsp+40]
 call boom_m{method}_native
 add rsp,56
 ret
boom_m{method}_provider_zero:
 xor eax,eax
 add rsp,56
 ret
boom_m{method} ENDP
PUBLIC boom_m{method}_native
boom_m{method}_native PROC
 lea r8,{pool}
 mov r9d,{operation}
 jmp {service}
boom_m{method}_native ENDP
