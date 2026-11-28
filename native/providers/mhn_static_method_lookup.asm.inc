; Original classfile name/descriptor lookup over the already linked NMTH rows.
; No Context, Java oop mutation, allocation, callback or class initialization.
.code

; EAX 0 mismatch/1 equal/2 unsupported descriptor, ECX/RDX type IDs, R8 pool.
mhmm_type_text_equal PROC PRIVATE
 mov eax,2
 cmp ecx,DWORD PTR [r8+12]
 jae mhmm_te_done
 cmp edx,DWORD PTR [r8+12]
 jae mhmm_te_done
 mov r9,QWORD PTR [r8+40]
 mov r9,QWORD PTR [r9+56]
 shl rcx,4
 shl rdx,4
 add rcx,r9
 add rdx,r9
 test DWORD PTR [rcx+12],1
 jz mhmm_te_done
 test DWORD PTR [rdx+12],1
 jz mhmm_te_done
 mov r9d,DWORD PTR [rcx+8]
 xor eax,eax
 cmp r9d,DWORD PTR [rdx+8]
 jne mhmm_te_done
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdx]
 test rcx,rcx
 jz mhmm_te_bad
 test rdx,rdx
 jz mhmm_te_bad
mhmm_te_loop:
 test r9d,r9d
 jz mhmm_te_equal
 mov ax,WORD PTR [rcx]
 cmp ax,WORD PTR [rdx]
 jne mhmm_te_no
 add rcx,2
 add rdx,2
 dec r9d
 jmp mhmm_te_loop
mhmm_te_equal:
 mov eax,1
 ret
mhmm_te_no:
 xor eax,eax
 ret
mhmm_te_bad:
 mov eax,2
mhmm_te_done:
 ret
mhmm_type_text_equal ENDP

; row144/query64/pool512 -> 0 mismatch,1 match,2 unresolved signature type.
mhmm_row_matches PROC PRIVATE FRAME
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
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 xor eax,eax
 mov ecx,DWORD PTR [rsi+8]
 cmp ecx,DWORD PTR [rbx+48]
 jne mhmm_rm_done
 mov r10,QWORD PTR [rsi]
 mov r11,QWORD PTR [rbx+40]
 test r11,r11
 jz mhmm_rm_unknown
 xor r9d,r9d
mhmm_rm_name:
 cmp r9d,DWORD PTR [rsi+8]
 jae mhmm_rm_params
 mov edx,r9d
 mov ecx,DWORD PTR [rsi+12]
 shl rdx,cl
 movzx ecx,BYTE PTR [r10+rdx]
 cmp DWORD PTR [rsi+12],0
 je mhmm_rm_name_compare
 movzx ecx,WORD PTR [r10+rdx]
mhmm_rm_name_compare:
 cmp cx,WORD PTR [r11+r9*2]
 jne mhmm_rm_no
 inc r9d
 jmp mhmm_rm_name
mhmm_rm_params:
 mov ecx,DWORD PTR [rsi+16]
 cmp ecx,DWORD PTR [rbx+12]
 jne mhmm_rm_no
 mov ecx,DWORD PTR [rsi+20]
 mov edx,DWORD PTR [rbx+52]
 mov r8,rdi
 call mhmm_type_text_equal
 cmp eax,1
 jne mhmm_rm_done
 xor r12d,r12d
 mov r13,QWORD PTR [rbx+16]
mhmm_rm_parameter:
 cmp r12d,DWORD PTR [rsi+16]
 jae mhmm_rm_yes
 test r13,r13
 jz mhmm_rm_unknown
 mov rax,QWORD PTR [rsi+24]
 mov ecx,DWORD PTR [rax+r12*4]
 mov edx,DWORD PTR [r13+r12*4]
 mov r8,rdi
 call mhmm_type_text_equal
 cmp eax,1
 jne mhmm_rm_done
 inc r12d
 jmp mhmm_rm_parameter
mhmm_rm_unknown:
 mov eax,2
 jmp mhmm_rm_done
mhmm_rm_no:
 xor eax,eax
 jmp mhmm_rm_done
mhmm_rm_yes:
 mov eax,1
mhmm_rm_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
mhmm_row_matches ENDP

; Pool512*, query64*, startClassID, result32*.
; Result32 {rowQ0, MethodID8,holder12,declslot16,canonicalFlags20,reservedQ24}.
; Class own/super lookup is complete. Matching inherited interface methods are
; explicitly unsupported (no guessed maximally-specific/default selection).
; Interface own static methods are supported; Object public instance match is
; returned so ordinary later staticness checking produces ICCE.
mhmm_lookup PROC PRIVATE FRAME
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
 sub rsp,80
 .allocstack 80
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov edi,r8d
 mov r12,r9
 mov DWORD PTR [rsp+32],edi
 mov DWORD PTR [rsp+36],0
 mov DWORD PTR [rsp+40],0
 cmp edi,DWORD PTR [rbx+208]
 jae mhmm_lu_unsupported
 mov eax,edi
 shl rax,6
 add rax,QWORD PTR [rbx+72]
 test DWORD PTR [rax+4],200h
 jz mhmm_lu_class
 mov DWORD PTR [rsp+36],1
mhmm_lu_class:
 inc DWORD PTR [rsp+40]
 cmp DWORD PTR [rsp+40],128
 ja mhmm_lu_unsupported
 mov eax,edi
 shl rax,6
 add rax,QWORD PTR [rbx+72]
 cmp DWORD PTR [rax+44],1
 jne mhmm_lu_unsupported
 mov QWORD PTR [rsp+48],rax
 mov r10,QWORD PTR [rbx+64]
 cmp edi,DWORD PTR [r10+8]
 jae mhmm_lu_bad
 mov eax,edi
 shl rax,4
 add rax,QWORD PTR [r10+32]
 cmp DWORD PTR [rax+8],1
 jne mhmm_lu_unsupported
 cmp DWORD PTR [rax+12],0
 jne mhmm_lu_bad
 mov r13d,DWORD PTR [rax]
 mov r14d,DWORD PTR [rax+4]
 add r14d,r13d
 jc mhmm_lu_bad
 cmp r14d,DWORD PTR [r10+12]
 ja mhmm_lu_bad
mhmm_lu_row:
 cmp r13d,r14d
 jae mhmm_lu_parent
 mov rax,r13
 imul rax,144
 mov r10,QWORD PTR [rbx+64]
 add rax,QWORD PTR [r10+40]
 mov r15,rax
 cmp DWORD PTR [r15],edi
 jne mhmm_lu_bad
 cmp DWORD PTR [rsp+36],2
 jne mhmm_lu_match
 ; Only a public nonstatic Object method participates in interface resolution.
 mov eax,DWORD PTR [r15+8]
 and eax,9
 cmp eax,1
 jne mhmm_lu_next
mhmm_lu_match:
 mov rcx,r15
 mov rdx,rsi
 mov r8,rbx
 call mhmm_row_matches
 cmp eax,2
 je mhmm_lu_unsupported
 test eax,eax
 jnz mhmm_lu_found
mhmm_lu_next:
 inc r13d
 jmp mhmm_lu_row
mhmm_lu_parent:
 cmp DWORD PTR [rsp+36],2
 je mhmm_lu_interfaces
 cmp DWORD PTR [rsp+36],1
 jne mhmm_lu_normal_parent
 mov DWORD PTR [rsp+36],2
 mov edi,DWORD PTR [rbx+280]
 jmp mhmm_lu_class
mhmm_lu_normal_parent:
 mov rax,QWORD PTR [rsp+48]
 mov edi,DWORD PTR [rax]
 cmp edi,-1
 je mhmm_lu_interfaces
 cmp edi,DWORD PTR [rbx+208]
 jae mhmm_lu_bad
 jmp mhmm_lu_class
mhmm_lu_interfaces:
 mov eax,DWORD PTR [rsp+32]
 shl rax,6
 add rax,QWORD PTR [rbx+72]
 mov edi,DWORD PTR [rax+24]
 mov eax,DWORD PTR [rax+28]
 add eax,edi
 jc mhmm_lu_bad
 cmp eax,DWORD PTR [rbx+272]
 ja mhmm_lu_bad
 mov DWORD PTR [rsp+64],eax
mhmm_lu_interface_next:
 cmp edi,DWORD PTR [rsp+64]
 jae mhmm_lu_miss
 mov rax,QWORD PTR [rbx+80]
 mov eax,DWORD PTR [rax+rdi*4]
 inc edi
 cmp eax,DWORD PTR [rbx+208]
 jae mhmm_lu_bad
 mov edx,eax
 shl rdx,6
 add rdx,QWORD PTR [rbx+72]
 cmp DWORD PTR [rdx+44],1
 jne mhmm_lu_unsupported
 mov r10,QWORD PTR [rbx+64]
 shl rax,4
 add rax,QWORD PTR [r10+32]
 cmp DWORD PTR [rax+8],1
 jne mhmm_lu_unsupported
 mov r13d,DWORD PTR [rax]
 mov r14d,DWORD PTR [rax+4]
 add r14d,r13d
 jc mhmm_lu_bad
 cmp r14d,DWORD PTR [r10+12]
 ja mhmm_lu_bad
mhmm_lu_interface_row:
 cmp r13d,r14d
 jae mhmm_lu_interface_next
 mov rax,r13
 imul rax,144
 mov r10,QWORD PTR [rbx+64]
 add rax,QWORD PTR [r10+40]
 mov rcx,rax
 test DWORD PTR [rcx+8],0Ah
 jnz mhmm_lu_interface_skip
 mov rdx,rsi
 mov r8,rbx
 call mhmm_row_matches
 test eax,eax
 jnz mhmm_lu_unsupported
mhmm_lu_interface_skip:
 inc r13d
 jmp mhmm_lu_interface_row
mhmm_lu_found:
 mov r10,QWORD PTR [rbx+88]
 mov eax,DWORD PTR [r15]
 mov edx,DWORD PTR [r15+4]
 cmp edx,DWORD PTR [r10+rax*8+4]
 jae mhmm_lu_bad
 add edx,DWORD PTR [r10+rax*8]
 jc mhmm_lu_bad
 cmp edx,DWORD PTR [rbx+212]
 jae mhmm_lu_bad
 mov QWORD PTR [r12],r15
 mov DWORD PTR [r12+8],edx
 mov DWORD PTR [r12+12],eax
 mov eax,DWORD PTR [r15+4]
 mov DWORD PTR [r12+16],eax
 mov eax,DWORD PTR [r15+8]
 and eax,01DFFh
 or eax,06010000h
 mov r10,QWORD PTR [rbx+96]
 cmp BYTE PTR [r10+rdx],0
 je mhmm_lu_flags
 or eax,100000h
mhmm_lu_flags:
 mov DWORD PTR [r12+20],eax
 mov QWORD PTR [r12+24],0
 xor eax,eax
 jmp mhmm_lu_done
mhmm_lu_miss:
 mov eax,1
 jmp mhmm_lu_done
mhmm_lu_unsupported:
 mov eax,2
 jmp mhmm_lu_done
mhmm_lu_bad:
 mov eax,3
mhmm_lu_done:
 add rsp,80
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
mhmm_lookup ENDP
