; Normal source-layout String.intern. All execution is MASM.
; Pool96: magic/ABI0/4, lock8,count12,capacity16,reserved20,heapCell24,
; StringLayout32,value/coder/hash/zero offsets40/44/48/52,literalPool56,
; NamePool64*64,dynamicRootCell72,ContextBytes80,strongPolicy84,reserved88.
; Known UTF16 entries use the existing literal/name publication states, so
; intern-before-ldc/getName adopts the caller instead of allocating a copy.
; Dynamic open-addressed tables are heap blocks: reference prefix cap*8,
; followed by cap DWORD hashes. One declared strong root retains the table.
; This ABI deliberately uses strong retention. Weak intern/unloading and active
; roots/safepoints are not implemented. Allocation failures do not invoke GC.
option casemap:none
EXTERN boom_heap_contains:PROC
EXTERN boom_heap_alloc:PROC
EXTERN boom_object_check:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
EXTERN WakeByAddressSingle:PROC
PUBLIC boom_java_string_intern
.code

; view(ctx,pool,oop,out32) -> bool. out: bytes0,len8,coder12,hash16,oop24.
ji_view PROC FRAME
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
 mov r12,r9
 test rdi,rdi
 jz jiv_null
 mov rcx,QWORD PTR [rsi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz jiv_bad
 mov rcx,rdi
 mov rdx,QWORD PTR [rsi+32]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jiv_zero
 mov eax,DWORD PTR [rsi+44]
 movzx r13d,BYTE PTR [rdi+rax]
 cmp r13d,1
 ja jiv_bad
 mov eax,DWORD PTR [rsi+40]
 mov rdi,QWORD PTR [rdi+rax]
 mov rcx,QWORD PTR [rsi+24]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz jiv_bad
 cmp QWORD PTR [rdi-8],264
 jne jiv_bad
 cmp DWORD PTR [rdi-20],0
 jne jiv_bad
 mov rax,QWORD PTR [rdi-16]
 cmp rax,07FFFFFFFh
 ja jiv_bad
 test r13d,r13d
 jz jiv_length
 test al,1
 jnz jiv_bad
 shr eax,1
jiv_length:
 mov QWORD PTR [r12],rdi
 mov DWORD PTR [r12+8],eax
 mov DWORD PTR [r12+12],r13d
 xor r10d,r10d
 xor r11d,r11d
jiv_hash:
 cmp r10d,DWORD PTR [r12+8]
 jae jiv_ready
 test r13d,r13d
 jnz jiv_word
 movzx edx,BYTE PTR [rdi+r10]
 jmp jiv_add
jiv_word:
 movzx edx,WORD PTR [rdi+r10*2]
jiv_add:
 imul r11d,r11d,31
 add r11d,edx
 inc r10d
 jmp jiv_hash
jiv_ready:
 mov DWORD PTR [r12+16],r11d
 mov eax,1
 jmp jiv_done
jiv_null:
 mov DWORD PTR [rbx],4
 jmp jiv_zero
jiv_bad:
 mov DWORD PTR [rbx],7
jiv_zero:
 xor eax,eax
jiv_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
ji_view ENDP

; equal(viewA,viewB) -> bool; no allocation or guest callbacks.
ji_equal PROC FRAME
 sub rsp,24
 .allocstack 24
 .endprolog
 mov eax,DWORD PTR [rcx+8]
 cmp eax,DWORD PTR [rdx+8]
 jne jie_no
 mov DWORD PTR [rsp],eax
 mov eax,DWORD PTR [rcx+12]
 mov DWORD PTR [rsp+4],eax
 mov eax,DWORD PTR [rdx+12]
 mov DWORD PTR [rsp+8],eax
 mov r10,QWORD PTR [rcx]
 mov r11,QWORD PTR [rdx]
 xor eax,eax
jie_next:
 cmp eax,DWORD PTR [rsp]
 jae jie_yes
 cmp DWORD PTR [rsp+4],0
 jne jie_a_word
 movzx edx,BYTE PTR [r10+rax]
 jmp jie_b
jie_a_word:
 movzx edx,WORD PTR [r10+rax*2]
jie_b:
 cmp DWORD PTR [rsp+8],0
 jne jie_b_word
 movzx ecx,BYTE PTR [r11+rax]
 jmp jie_cmp
jie_b_word:
 movzx ecx,WORD PTR [r11+rax*2]
jie_cmp:
 cmp edx,ecx
 jne jie_no
 inc eax
 jmp jie_next
jie_yes:
 mov eax,1
 jmp jie_done
jie_no:
 xor eax,eax
jie_done:
 add rsp,24
 ret
ji_equal ENDP

; bind(ctx,pool96,staticPool80,heap) -> bool. Source metadata is immutable.
ji_bind_static PROC
 test r8,r8
 jz jib_bad
 cmp DWORD PTR [r8],04A534C50h
 jne jib_bad
 cmp DWORD PTR [r8+4],1
 jne jib_bad
 mov eax,DWORD PTR [r8+8]
 dec eax
 cmp eax,0FFFFFh
 ja jib_bad
 cmp DWORD PTR [r8+72],1
 ja jib_bad
 cmp QWORD PTR [r8+16],0
 je jib_bad
 cmp QWORD PTR [r8+24],0
 je jib_bad
 cmp QWORD PTR [r8+32],0
 je jib_bad
 mov rax,QWORD PTR [r8+40]
 cmp rax,QWORD PTR [rdx+32]
 jne jib_bad
 mov eax,DWORD PTR [r8+48]
 cmp eax,DWORD PTR [rdx+40]
 jne jib_bad
 mov eax,DWORD PTR [r8+52]
 cmp eax,DWORD PTR [rdx+44]
 jne jib_bad
 mov eax,DWORD PTR [r8+56]
 cmp eax,DWORD PTR [rdx+48]
 jne jib_bad
 mov eax,DWORD PTR [r8+60]
 cmp eax,DWORD PTR [rdx+52]
 jne jib_bad
 xor eax,eax
 lock cmpxchg QWORD PTR [r8+64],r9
 je jib_yes
 cmp rax,r9
 jne jib_bad
jib_yes:
 mov eax,1
 ret
jib_bad:
 mov DWORD PTR [rcx],7
 xor eax,eax
 ret
ji_bind_static ENDP

; find(staticPool80,view32) -> sorted UTF16 canonical ID / FFFFFFFF.
ji_find_static PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 xor edi,edi
 mov r12d,DWORD PTR [rbx+8]
jif_search:
 cmp edi,r12d
 jae jif_none
 lea r8d,[rdi+r12]
 shr r8d,1
 mov rax,QWORD PTR [rbx+16]
 cmp DWORD PTR [rbx+72],0
 je jif_flat
 mov ecx,r8d
 shr ecx,8
 mov rax,QWORD PTR [rax+rcx*8]
 mov ecx,r8d
 and ecx,255
 jmp jif_entry
jif_flat:
 mov ecx,r8d
jif_entry:
 shl rcx,4
 add rax,rcx
 mov r10,QWORD PTR [rax]
 mov r9d,DWORD PTR [rax+8]
 mov r11,QWORD PTR [rsi]
 xor ecx,ecx
jif_char:
 cmp ecx,DWORD PTR [rsi+8]
 jae jif_length
 cmp ecx,r9d
 jae jif_greater
 cmp DWORD PTR [rsi+12],0
 jne jif_word
 movzx edx,BYTE PTR [r11+rcx]
 jmp jif_compare
jif_word:
 movzx edx,WORD PTR [r11+rcx*2]
jif_compare:
 cmp dx,WORD PTR [r10+rcx*2]
 jb jif_smaller
 ja jif_greater
 inc ecx
 jmp jif_char
jif_length:
 cmp ecx,r9d
 jb jif_smaller
 mov eax,r8d
 jmp jif_done
jif_smaller:
 mov r12d,r8d
 jmp jif_search
jif_greater:
 lea edi,[r8+1]
 jmp jif_search
jif_none:
 mov eax,0FFFFFFFFh
jif_done:
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
ji_find_static ENDP

; adopt(ctx,staticPool80,id,callerOOP) -> canonical OOP. Shares factory states.
ji_adopt PROC FRAME
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
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov edi,r8d
 mov r12,r9
 mov r13,QWORD PTR [rsi+24]
 mov eax,edi
 shl rax,4
 add r13,rax
 mov r14,QWORD PTR [rsi+32]
 lea r14,[r14+rdi*4]
jia_retry:
 mov rax,QWORD PTR [r13]
 test rax,rax
 jnz jia_done
 xor eax,eax
 mov edx,1
 lock cmpxchg DWORD PTR [r14],edx
 je jia_publish
 cmp eax,1
 jne jia_bad
 mov DWORD PTR [rsp+32],1
 mov rcx,r14
 lea rdx,[rsp+32]
 mov r8d,4
 mov r9d,-1
 call WaitOnAddress
 jmp jia_retry
jia_publish:
 mov QWORD PTR [r13+8],0
 mov QWORD PTR [r13],r12
 mov DWORD PTR [r14],2
 mov rcx,r14
 call WakeByAddressAll
 mov rax,r12
 jmp jia_done
jia_bad:
 mov DWORD PTR [rbx],7
 xor eax,eax
jia_done:
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
ji_adopt ENDP

; grow(ctx,pool96,heap,newCapacity) -> table/NULL; caller owns intern lock.
ji_grow PROC FRAME
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
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov r12d,r9d
 mov rax,QWORD PTR [rsi+72]
 mov r13,QWORD PTR [rax]
 mov r14d,DWORD PTR [rsi+16]
 cmp r12d,0100000h
 ja jig_oom
 mov rcx,rdi
 mov edx,r12d
 imul rdx,12
 mov r8d,r12d
 mov r9d,04A494E54h
 call boom_heap_alloc
 test rax,rax
 jz jig_oom
 mov r15,rax
 xor r10d,r10d
jig_next:
 cmp r10d,r14d
 jae jig_publish
 mov rdx,QWORD PTR [r13+r10*8]
 test rdx,rdx
 jz jig_skip
 mov eax,r14d
 shl rax,3
 lea rax,[r13+rax]
 mov r9d,DWORD PTR [rax+r10*4]
 lea r8d,[r12-1]
 and r8d,r9d
jig_probe:
 cmp QWORD PTR [r15+r8*8],0
 je jig_slot
 inc r8d
 lea eax,[r12-1]
 and r8d,eax
 jmp jig_probe
jig_slot:
 mov QWORD PTR [r15+r8*8],rdx
 mov eax,r12d
 shl rax,3
 lea rax,[r15+rax]
 mov DWORD PTR [rax+r8*4],r9d
jig_skip:
 inc r10d
 jmp jig_next
jig_publish:
 mov rax,QWORD PTR [rsi+72]
 mov QWORD PTR [rax],r15
 mov DWORD PTR [rsi+16],r12d
 mov rax,r15
 jmp jig_done
jig_oom:
 mov DWORD PTR [rbx],3
 xor eax,eax
jig_done:
 add rsp,32
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
ji_grow ENDP

boom_java_string_intern PROC FRAME
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
 sub rsp,128
 .allocstack 128
 .endprolog
 mov rbx,rcx
 mov rsi,r8
 mov DWORD PTR [rsp+112],0
 test rbx,rbx
 jz jin_zero
 cmp DWORD PTR [rbx],0
 jne jin_zero
 test rdx,rdx
 jz jin_bad
 mov rdi,QWORD PTR [rdx]
 test rdi,rdi
 jz jin_null
 test rsi,rsi
 jz jin_bad
 cmp DWORD PTR [rsi],04A494E50h
 jne jin_bad
 cmp DWORD PTR [rsi+4],1
 jne jin_bad
 cmp DWORD PTR [rsi+20],0
 jne jin_bad
 cmp DWORD PTR [rsi+80],32
 jne jin_bad
 cmp DWORD PTR [rsi+84],1
 jne jin_bad
 cmp QWORD PTR [rsi+88],0
 jne jin_bad
 cmp QWORD PTR [rsi+24],0
 je jin_bad
 cmp QWORD PTR [rsi+32],0
 je jin_bad
 cmp QWORD PTR [rsi+72],0
 je jin_bad
 mov rax,QWORD PTR [rsi+32]
 cmp DWORD PTR [rax],04F424A43h
 jne jin_bad
 cmp DWORD PTR [rax+4],2
 jne jin_bad
 cmp DWORD PTR [rax+16],1
 jne jin_bad
 cmp DWORD PTR [rax+20],4
 jne jin_bad
 cmp DWORD PTR [rsi+40],0
 jne jin_bad
 mov rdx,QWORD PTR [rax+8]
 cmp rdx,14
 jb jin_bad
 cmp rdx,32
 ja jin_bad
 mov eax,DWORD PTR [rsi+44]
 cmp eax,8
 jb jin_bad
 cmp rax,rdx
 jae jin_bad
 mov rax,QWORD PTR [rsi+24]
 mov r12,QWORD PTR [rax]
 test r12,r12
 jz jin_unbound
 mov rcx,rbx
 mov rdx,rsi
 mov r8,rdi
 lea r9,[rsp+32]
 call ji_view
 test eax,eax
 jz jin_zero
 mov QWORD PTR [rsp+56],rdi
 mov rcx,rbx
 mov rdx,rsi
 mov r8,QWORD PTR [rsi+56]
 mov r9,r12
 call ji_bind_static
 test eax,eax
 jz jin_zero
 mov rax,QWORD PTR [rsi+64]
 test rax,rax
 jz jin_bad
 cmp DWORD PTR [rax],04A434E50h
 jne jin_bad
 cmp DWORD PTR [rax+4],1
 jne jin_bad
 mov rdx,QWORD PTR [rax+32]
 cmp rdx,QWORD PTR [rsi+32]
 jne jin_bad
 mov r8,QWORD PTR [rax+24]
 mov rcx,rbx
 mov rdx,rsi
 mov r9,r12
 call ji_bind_static
 test eax,eax
 jz jin_zero
 mov r13,QWORD PTR [rsi+56]
 mov rcx,r13
 lea rdx,[rsp+32]
 call ji_find_static
 cmp eax,0FFFFFFFFh
 jne jin_static
 mov rax,QWORD PTR [rsi+64]
 mov r13,QWORD PTR [rax+24]
 mov rcx,r13
 lea rdx,[rsp+32]
 call ji_find_static
 cmp eax,0FFFFFFFFh
 je jin_lock
jin_static:
 mov r8d,eax
 mov rcx,rbx
 mov rdx,r13
 mov r9,rdi
 call ji_adopt
 test rax,rax
 jz jin_zero
 mov r15,rax
 mov rcx,rbx
 mov rdx,rsi
 mov r8,rax
 lea r9,[rsp+64]
 call ji_view
 test eax,eax
 jz jin_zero
 lea rcx,[rsp+32]
 lea rdx,[rsp+64]
 call ji_equal
 test eax,eax
 jz jin_bad
 mov rax,r15
 jmp jin_done
jin_lock:
 xor eax,eax
 mov edx,1
 lock cmpxchg DWORD PTR [rsi+8],edx
 je jin_owned
jin_contended:
 mov eax,2
 xchg DWORD PTR [rsi+8],eax
 test eax,eax
 jz jin_owned
 mov DWORD PTR [rsp+116],2
 lea rcx,[rsi+8]
 lea rdx,[rsp+116]
 mov r8d,4
 mov r9d,-1
 call WaitOnAddress
 jmp jin_contended
jin_owned:
 mov DWORD PTR [rsp+112],1
 mov r13d,DWORD PTR [rsi+16]
 mov rax,QWORD PTR [rsi+72]
 mov r14,QWORD PTR [rax]
 test r13d,r13d
 jnz jin_validate_table
 test r14,r14
 jnz jin_bad
 cmp DWORD PTR [rsi+12],0
 jne jin_bad
 mov r9d,64
 jmp jin_grow
jin_validate_table:
 cmp r13d,64
 jb jin_bad
 cmp r13d,0100000h
 ja jin_bad
 lea eax,[r13-1]
 test eax,r13d
 jnz jin_bad
 mov eax,r13d
 imul eax,3
 shr eax,2
 cmp DWORD PTR [rsi+12],eax
 ja jin_bad
 mov rcx,r12
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz jin_bad
 cmp QWORD PTR [r14-8],04A494E54h
 jne jin_bad
 cmp DWORD PTR [r14-20],r13d
 jne jin_bad
 mov eax,r13d
 imul rax,12
 cmp QWORD PTR [r14-16],rax
 jne jin_bad
jin_search:
 lea r15d,[r13-1]
 and r15d,DWORD PTR [rsp+48]
 mov DWORD PTR [rsp+108],0
jin_probe:
 mov r8,QWORD PTR [r14+r15*8]
 test r8,r8
 jz jin_empty
 mov eax,r13d
 shl rax,3
 lea rax,[r14+rax]
 mov eax,DWORD PTR [rax+r15*4]
 cmp eax,DWORD PTR [rsp+48]
 jne jin_next
 mov rcx,rbx
 mov rdx,rsi
 lea r9,[rsp+64]
 call ji_view
 test eax,eax
 jz jin_zero
 lea rcx,[rsp+32]
 lea rdx,[rsp+64]
 call ji_equal
 test eax,eax
 jnz jin_found
jin_next:
 inc r15d
 lea eax,[r13-1]
 and r15d,eax
 inc DWORD PTR [rsp+108]
 cmp DWORD PTR [rsp+108],r13d
 jb jin_probe
 jmp jin_bad
jin_found:
 mov rax,QWORD PTR [r14+r15*8]
 jmp jin_done
jin_empty:
 mov eax,DWORD PTR [rsi+12]
 inc eax
 shl eax,2
 imul edx,r13d,3
 cmp eax,edx
 ja jin_expand
 mov QWORD PTR [r14+r15*8],rdi
 mov eax,r13d
 shl rax,3
 lea rax,[r14+rax]
 mov edx,DWORD PTR [rsp+48]
 mov DWORD PTR [rax+r15*4],edx
 inc DWORD PTR [rsi+12]
 mov rax,rdi
 jmp jin_done
jin_expand:
 lea r9d,[r13*2]
jin_grow:
 mov rcx,rbx
 mov rdx,rsi
 mov r8,r12
 call ji_grow
 test rax,rax
 jz jin_zero
 mov r14,rax
 mov r13d,DWORD PTR [rsi+16]
 jmp jin_search
jin_null:
 mov DWORD PTR [rbx],4
 jmp jin_zero
jin_unbound:
 mov DWORD PTR [rbx],20
 jmp jin_zero
jin_bad:
 mov DWORD PTR [rbx],7
jin_zero:
 xor eax,eax
jin_done:
 cmp DWORD PTR [rsp+112],0
 je jin_return
 mov QWORD PTR [rsp+120],rax
 xor edx,edx
 xchg DWORD PTR [rsi+8],edx
 cmp edx,2
 jne jin_unlocked
 lea rcx,[rsi+8]
 call WakeByAddressSingle
jin_unlocked:
 mov rax,QWORD PTR [rsp+120]
jin_return:
 add rsp,128
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_string_intern ENDP
END
