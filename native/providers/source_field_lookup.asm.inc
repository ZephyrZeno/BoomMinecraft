; Native-only source field lookup. No Context, oop, allocation, class-init or callback.
; Win64 EAX lookup(FLUP80* RCX, originalClassID EDX, Query32* R8, Result32* R9).
; Query32: UTF16name*0,UTF16descriptor*8,nameUnits16D,descriptorUnits20D,reserved24Q0.
; Success Result32: holder0,id4,declSlot8,access12,typeID16,width20,kind24,res28.
; EAX0 found,1 completeMISS,2 unavailable catalogue/hierarchy,3 invalid arguments.
; Failed calls never change any Result byte. Metadata and native buffers trusted/live.
option casemap:none
PUBLIC boom_source_field_lookup
.code
boom_source_field_lookup PROC FRAME
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
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov r14d,edx
 mov r12,r8
 mov r13,r9
 test rbx,rbx
 jz flu_bad
 test r12,r12
 jz flu_bad
 test r13,r13
 jz flu_bad
 cmp DWORD PTR [rbx],050554C46h
 jne flu_bad
 cmp DWORD PTR [rbx+4],1
 jne flu_bad
 cmp DWORD PTR [rbx+8],80
 jb flu_bad
 cmp DWORD PTR [rbx+8],040000000h
 ja flu_bad
 cmp DWORD PTR [rbx+12],0
 je flu_bad
 cmp DWORD PTR [rbx+12],0100000h
 ja flu_bad
 cmp DWORD PTR [rbx+16],01000000h
 ja flu_bad
 cmp DWORD PTR [rbx+52],32
 jne flu_bad
 cmp DWORD PTR [rbx+56],40
 jne flu_bad
 cmp DWORD PTR [rbx+60],0
 jne flu_bad
 cmp QWORD PTR [rbx+64],0
 jne flu_bad
 cmp QWORD PTR [rbx+72],0
 jne flu_bad
 ; Full relative table extents use 64-bit arithmetic before any table access.
 mov r11d,DWORD PTR [rbx+8]
 mov eax,DWORD PTR [rbx+32]
 cmp eax,80
 jb flu_bad
 test eax,7
 jnz flu_bad
 mov r10d,DWORD PTR [rbx+12]
 shl r10,5
 add rax,r10
 cmp rax,r11
 ja flu_bad
 mov eax,DWORD PTR [rbx+36]
 cmp eax,80
 jb flu_bad
 test eax,7
 jnz flu_bad
 mov r10d,DWORD PTR [rbx+16]
 imul r10,r10,40
 add rax,r10
 cmp rax,r11
 ja flu_bad
 mov eax,DWORD PTR [rbx+40]
 cmp eax,80
 jb flu_bad
 test eax,3
 jnz flu_bad
 mov r10d,DWORD PTR [rbx+20]
 shl r10,2
 add rax,r10
 cmp rax,r11
 ja flu_bad
 mov eax,DWORD PTR [rbx+44]
 cmp eax,80
 jb flu_bad
 test eax,3
 jnz flu_bad
 mov r10d,DWORD PTR [rbx+24]
 shl r10,2
 add rax,r10
 cmp rax,r11
 ja flu_bad
 mov eax,DWORD PTR [rbx+48]
 cmp eax,80
 jb flu_bad
 test eax,1
 jnz flu_bad
 mov r10d,DWORD PTR [rbx+28]
 shl r10,1
 add rax,r10
 cmp rax,r11
 ja flu_bad
 cmp QWORD PTR [r12+24],0
 jne flu_bad
 cmp DWORD PTR [r12+16],65535
 ja flu_bad
 cmp DWORD PTR [r12+20],65535
 ja flu_bad
 cmp DWORD PTR [r12+16],0
 je flu_name_pointer_ready
 cmp QWORD PTR [r12],0
 je flu_bad
flu_name_pointer_ready:
 cmp DWORD PTR [r12+20],0
 je flu_descriptor_pointer_ready
 cmp QWORD PTR [r12+8],0
 je flu_bad
flu_descriptor_pointer_ready:
 cmp r14d,DWORD PTR [rbx+12]
 jae flu_unsupported
 mov eax,r14d
 shl rax,5
 mov ecx,DWORD PTR [rbx+32]
 add rax,rcx
 add rax,rbx
 cmp DWORD PTR [rax+28],1
 jne flu_unsupported
 mov r15d,DWORD PTR [rax+20]
 mov ecx,DWORD PTR [rax+24]
 add ecx,r15d
 jc flu_bad
 cmp ecx,DWORD PTR [rbx+24]
 ja flu_bad
 mov DWORD PTR [rsp+32],ecx
 ; Holder order is the source-projected first-visit DFS: own, interfaces in
 ; raw classfile order recursively, superclass recursively. It is not RTYP ancestry.
flu_holder_loop:
 cmp r15d,DWORD PTR [rsp+32]
 jae flu_missing
 mov ecx,DWORD PTR [rbx+44]
 lea rax,[rbx+rcx]
 mov r14d,DWORD PTR [rax+r15*4]
 inc r15d
 cmp r14d,DWORD PTR [rbx+12]
 jae flu_unsupported
 mov eax,r14d
 shl rax,5
 mov ecx,DWORD PTR [rbx+32]
 add rax,rcx
 add rax,rbx
 cmp DWORD PTR [rax+28],1
 jne flu_unsupported
 mov edi,DWORD PTR [rax]
 mov ecx,DWORD PTR [rax+4]
 add ecx,edi
 jc flu_bad
 cmp ecx,DWORD PTR [rbx+16]
 ja flu_bad
 mov DWORD PTR [rsp+36],ecx
flu_field_loop:
 cmp edi,DWORD PTR [rsp+36]
 jae flu_holder_loop
 mov eax,edi
 imul rax,rax,40
 mov ecx,DWORD PTR [rbx+36]
 add rax,rcx
 lea rsi,[rbx+rax]
 inc edi
 mov eax,DWORD PTR [rsi+4]
 cmp eax,DWORD PTR [r12+16]
 jne flu_field_loop
 mov eax,DWORD PTR [rsi+12]
 cmp eax,DWORD PTR [r12+20]
 jne flu_field_loop
 mov eax,DWORD PTR [rsi]
 mov ecx,DWORD PTR [rsi+4]
 add rcx,rax
 mov edx,DWORD PTR [rbx+28]
 cmp rcx,rdx
 ja flu_bad
 mov edx,DWORD PTR [rbx+48]
 lea r9,[rbx+rdx]
 lea r9,[r9+rax*2]
 mov r8,QWORD PTR [r12]
 xor ecx,ecx
flu_name_loop:
 cmp ecx,DWORD PTR [r12+16]
 jae flu_name_equal
 movzx eax,WORD PTR [r8+rcx*2]
 cmp ax,WORD PTR [r9+rcx*2]
 jne flu_field_loop
 inc ecx
 jmp flu_name_loop
flu_name_equal:
 mov eax,DWORD PTR [rsi+8]
 mov ecx,DWORD PTR [rsi+12]
 add rcx,rax
 mov edx,DWORD PTR [rbx+28]
 cmp rcx,rdx
 ja flu_bad
 mov edx,DWORD PTR [rbx+48]
 lea r9,[rbx+rdx]
 lea r9,[r9+rax*2]
 mov r8,QWORD PTR [r12+8]
 xor ecx,ecx
flu_descriptor_loop:
 cmp ecx,DWORD PTR [r12+20]
 jae flu_found
 movzx eax,WORD PTR [r8+rcx*2]
 cmp ax,WORD PTR [r9+rcx*2]
 jne flu_field_loop
 inc ecx
 jmp flu_descriptor_loop
flu_found:
 mov DWORD PTR [r13],r14d
 mov eax,DWORD PTR [rsi+16]
 mov DWORD PTR [r13+4],eax
 mov eax,DWORD PTR [rsi+20]
 mov DWORD PTR [r13+8],eax
 mov eax,DWORD PTR [rsi+24]
 mov DWORD PTR [r13+12],eax
 mov eax,DWORD PTR [rsi+28]
 mov DWORD PTR [r13+16],eax
 mov eax,DWORD PTR [rsi+32]
 mov DWORD PTR [r13+20],eax
 mov eax,DWORD PTR [rsi+36]
 mov DWORD PTR [r13+24],eax
 mov DWORD PTR [r13+28],0
 xor eax,eax
 jmp flu_done
flu_missing:
 mov eax,1
 jmp flu_done
flu_unsupported:
 mov eax,2
 jmp flu_done
flu_bad:
 mov eax,3
flu_done:
 add rsp,48
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_source_field_lookup ENDP
END
