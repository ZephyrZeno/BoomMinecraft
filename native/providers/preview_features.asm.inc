; PRVW16/1 immutable VM startup option query. No Java state or host callbacks.
.code
PUBLIC boom_preview_features_service
boom_preview_features_service PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 test rcx,rcx
 jz prvw_zero
 cmp DWORD PTR [rcx],0
 jne prvw_zero
 cmp QWORD PTR [rcx+16],0
 jne prvw_zero
 test r8,r8
 jz prvw_bad
 test r9d,r9d
 jnz prvw_bad
 cmp DWORD PTR [r8],050525657h
 jne prvw_bad
 cmp DWORD PTR [r8+4],1
 jne prvw_bad
 cmp DWORD PTR [r8+8],16
 jne prvw_bad
 mov eax,DWORD PTR [r8+12]
 cmp eax,1
 ja prvw_bad
 jmp prvw_done
prvw_bad:
 mov DWORD PTR [rcx],7
prvw_zero:
 xor eax,eax
prvw_done:
 add rsp,40
 ret
boom_preview_features_service ENDP
