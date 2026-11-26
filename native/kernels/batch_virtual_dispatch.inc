; Source-generated closed-image dispatch. Guest execution is exclusively MASM.
; invoke(Context32 RCX, argv RDX, Dispatch40 R8, Constraints16 R9).
; Constraints16: symbolic owner TypeDesc*0, protected/array receiver TypeDesc*8.
; Dispatch40: VDSP0,abi4,count8,reserved12,Row16*16,arrayTarget24,error32,pad36.
; Row16: source receiver class ID0,error4,selected method envelope*8.
; Immutable tables belong to one loader/transform/layout generation.
boom_batch_virtual_invoke PROC FRAME
 sub rsp,88
 .allocstack 88
 .endprolog
 mov QWORD PTR [rsp+48],rcx
 mov QWORD PTR [rsp+56],rdx
 mov QWORD PTR [rsp+64],r8
 mov QWORD PTR [rsp+72],r9
 test rcx,rcx
 jz batch_virtual_zero
 cmp DWORD PTR [rcx],0
 jne batch_virtual_zero
 test rdx,rdx
 jz batch_virtual_bad
 test r8,r8
 jz batch_virtual_bad
 cmp DWORD PTR [r8],056445350h
 jne batch_virtual_bad
 cmp DWORD PTR [r8+4],1
 jne batch_virtual_bad
 cmp DWORD PTR [r8+8],0100000h
 ja batch_virtual_bad
 test r9,r9
 jz batch_virtual_bad
 mov r8,rcx
 mov rcx,QWORD PTR [rdx]
 lea rdx,boom_runtime_type_map
 call boom_runtime_row
 test rax,rax
 jz batch_virtual_zero
 mov QWORD PTR [rsp+80],rax
 mov rcx,QWORD PTR [rax+8]
 mov rdx,QWORD PTR [rsp+72]
 mov rdx,QWORD PTR [rdx]
 call boom_type_assignable
 test eax,eax
 jz batch_virtual_incompatible
 mov r10,QWORD PTR [rsp+72]
 mov rdx,QWORD PTR [r10+8]
 cmp rdx,QWORD PTR [r10]
 je batch_virtual_constraints_ready
 mov rax,QWORD PTR [rsp+80]
 mov rcx,QWORD PTR [rax+8]
 call boom_type_assignable
 test eax,eax
 jz batch_virtual_incompatible
batch_virtual_constraints_ready:
 mov rax,QWORD PTR [rsp+80]
 mov r10,QWORD PTR [rsp+64]
 cmp DWORD PTR [rax+20],0
 jne batch_virtual_array
 mov r9d,DWORD PTR [rax+16]
 mov r11,QWORD PTR [r10+16]
 mov edx,DWORD PTR [r10+8]
 test edx,edx
 jz batch_virtual_incompatible
 test r11,r11
 jz batch_virtual_bad
 xor ecx,ecx
batch_virtual_search:
 cmp ecx,edx
 jae batch_virtual_incompatible
 lea r8d,[rcx+rdx]
 shr r8d,1
 mov eax,r8d
 shl rax,4
 add rax,r11
 cmp r9d,DWORD PTR [rax]
 je batch_virtual_found
 jb batch_virtual_lower
 lea ecx,[r8+1]
 jmp batch_virtual_search
batch_virtual_lower:
 mov edx,r8d
 jmp batch_virtual_search
batch_virtual_found:
 mov edx,DWORD PTR [rax+4]
 test edx,edx
 jnz batch_virtual_error
 mov rax,QWORD PTR [rax+8]
 jmp batch_virtual_target
batch_virtual_array:
 cmp DWORD PTR [rax+20],2
 ja batch_virtual_bad
 mov edx,DWORD PTR [r10+32]
 test edx,edx
 jnz batch_virtual_error
 mov rax,QWORD PTR [r10+24]
batch_virtual_target:
 test rax,rax
 jz batch_virtual_bad
 mov rcx,QWORD PTR [rsp+48]
 mov rdx,QWORD PTR [rsp+56]
 add rsp,88
 jmp rax
batch_virtual_incompatible:
 mov edx,13
 jmp batch_virtual_error
batch_virtual_bad:
 mov edx,7
batch_virtual_error:
 mov rcx,QWORD PTR [rsp+48]
 mov DWORD PTR [rcx],edx
batch_virtual_zero:
 xor eax,eax
 add rsp,88
 ret
boom_batch_virtual_invoke ENDP
