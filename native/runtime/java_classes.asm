; Normal source-layout Class mirrors, entirely MASM. Pool144 / Row48.
; load(Context32,pool,typeId), typeid(Context32,pool,Class oop).
; bind_loader/module(pool,id,oop,Context32), seal(pool,Context32).
; Strong roots and immutable type records belong to one bound heap lifetime.
; No represented-type payload is injected into Java fields. No Java clinit here.
; GC is explicit/quiescent; callers include Class/loader/module root cells.
option casemap:none
EXTERN boom_object_new:PROC
EXTERN boom_object_check:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_runtime_row:PROC
EXTERN boom_runtime_instanceof:PROC
EXTERN boom_type_assignable:PROC
PUBLIC boom_java_class_load
PUBLIC boom_java_class_typeid
PUBLIC boom_java_class_bind_loader
PUBLIC boom_java_class_bind_module
PUBLIC boom_java_class_seal
PUBLIC boom_java_class_query
PUBLIC boom_java_class_name
.code

; Metadata is trusted/live. Preserve RCX/RDX/R8/R9.
java_class_pool_valid PROC
 test rdx,rdx
 jz jcp_bad
 cmp DWORD PTR [rdx],04A434C53h
 jne jcp_bad
 cmp DWORD PTR [rdx+4],1
 jne jcp_bad
 mov eax,DWORD PTR [rdx+12]
 dec eax
 cmp eax,0FFFFFh
 ja jcp_bad
 cmp QWORD PTR [rdx+16],0
 je jcp_bad
 cmp QWORD PTR [rdx+24],0
 je jcp_bad
 cmp QWORD PTR [rdx+40],0
 je jcp_bad
 cmp QWORD PTR [rdx+48],0
 je jcp_bad
 cmp QWORD PTR [rdx+56],0
 je jcp_bad
 cmp QWORD PTR [rdx+64],0
 je jcp_bad
 cmp QWORD PTR [rdx+72],0
 je jcp_bad
 cmp QWORD PTR [rdx+112],0
 je jcp_bad
 cmp QWORD PTR [rdx+120],0
 je jcp_bad
 cmp QWORD PTR [rdx+128],0
 je jcp_bad
 cmp DWORD PTR [rdx+140],0
 jne jcp_bad
 cmp DWORD PTR [rdx+92],1
 ja jcp_bad
 mov eax,DWORD PTR [rdx+84]
 dec eax
 cmp eax,65535
 ja jcp_bad
 mov eax,DWORD PTR [rdx+88]
 dec eax
 cmp eax,65535
 ja jcp_bad
 mov eax,DWORD PTR [rdx+80]
 cmp eax,01FFFFFh
 ja jcp_bad
 lea r10d,[rax+1]
 test r10d,eax
 jnz jcp_bad
 mov eax,DWORD PTR [rdx+12]
 shl eax,1
 cmp r10d,eax
 jb jcp_bad
 mov eax,DWORD PTR [rdx+108]
 cmp eax,DWORD PTR [rdx+12]
 jae jcp_bad
 mov r10,QWORD PTR [rdx+32]
 test r10,r10
 jz jcp_bad
 cmp DWORD PTR [r10],04F424A43h
 jne jcp_bad
 cmp DWORD PTR [r10+4],2
 jne jcp_bad
 mov eax,DWORD PTR [r10+16]
 shl rax,3
 cmp rax,QWORD PTR [r10+8]
 ja jcp_bad
 mov r11d,DWORD PTR [rdx+96]
 test r11b,7
 jnz jcp_bad
 add r11,8
 cmp r11,rax
 ja jcp_bad
 mov r11d,DWORD PTR [rdx+100]
 test r11b,7
 jnz jcp_bad
 add r11,8
 cmp r11,rax
 ja jcp_bad
 mov r11d,DWORD PTR [rdx+104]
 test r11b,7
 jnz jcp_bad
 add r11,8
 cmp r11,rax
 ja jcp_bad
 mov eax,DWORD PTR [rdx+96]
 cmp eax,DWORD PTR [rdx+100]
 je jcp_bad
 cmp eax,DWORD PTR [rdx+104]
 je jcp_bad
 mov eax,DWORD PTR [rdx+100]
 cmp eax,DWORD PTR [rdx+104]
 je jcp_bad
 mov eax,1
 ret
jcp_bad:
 xor eax,eax
 ret
java_class_pool_valid ENDP

; name(Context32,argv,ClassPool144,NamePool64) -> normal Java String.
; NamePool64: magic/ABI 0/4, Class.name offset8, type capacity12,
;             type->canonical DWORD indices16, StringLiteralPool80*24,
;             final source String layout32, ASM literal factory callback40.
;             original String literal pool48, canonical-name->literal IDs56.
; The name factory has its own explicitly published strong root region.
boom_java_class_name PROC FRAME
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
 mov rsi,r8
 mov rdi,r9
 test rbx,rbx
 jz jname_zero
 cmp DWORD PTR [rbx],0
 jne jname_zero
 test rdx,rdx
 jz jname_bad
 mov r12,QWORD PTR [rdx]
 mov rdx,rsi
 mov r8,r12
 call boom_java_class_typeid
 cmp eax,0FFFFFFFFh
 je jname_zero
 mov r13d,eax
 test rdi,rdi
 jz jname_bad
 cmp DWORD PTR [rdi],04A434E50h
 jne jname_bad
 cmp DWORD PTR [rdi+4],1
 jne jname_bad
 mov eax,DWORD PTR [rdi+12]
 cmp eax,DWORD PTR [rsi+12]
 jne jname_bad
 cmp r13d,eax
 jae jname_bad
 cmp QWORD PTR [rdi+16],0
 je jname_bad
 cmp QWORD PTR [rdi+32],0
 je jname_bad
 cmp QWORD PTR [rdi+40],0
 je jname_bad
 mov r15d,DWORD PTR [rdi+8]
 test r15b,7
 jnz jname_bad
 mov rax,QWORD PTR [rsi+32]
 mov eax,DWORD PTR [rax+16]
 shl rax,3
 lea rdx,[r15+8]
 cmp rdx,rax
 ja jname_bad
 cmp r15d,DWORD PTR [rsi+96]
 je jname_bad
 cmp r15d,DWORD PTR [rsi+100]
 je jname_bad
 cmp r15d,DWORD PTR [rsi+104]
 je jname_bad
 mov rax,QWORD PTR [r12+r15]
 test rax,rax
 jnz jname_cached
 mov r14,QWORD PTR [rdi+24]
 test r14,r14
 jz jname_bad
 cmp DWORD PTR [r14],04A534C50h
 jne jname_bad
 cmp DWORD PTR [r14+4],1
 jne jname_bad
 mov rdx,QWORD PTR [rdi+16]
 mov r13d,DWORD PTR [rdx+r13*4]
 cmp r13d,DWORD PTR [r14+8]
 jae jname_bad
 mov rdx,QWORD PTR [rdi+56]
 test rdx,rdx
 jz jname_bad
 mov eax,DWORD PTR [rdx+r13*4]
 cmp eax,0FFFFFFFFh
 je jname_selected
 mov r13d,eax
 mov r14,QWORD PTR [rdi+48]
 test r14,r14
 jz jname_bad
 cmp DWORD PTR [r14],04A534C50h
 jne jname_bad
 cmp DWORD PTR [r14+4],1
 jne jname_bad
 cmp r13d,DWORD PTR [r14+8]
 jae jname_bad
jname_selected:
 mov rcx,QWORD PTR [rsi+48]
 mov rcx,QWORD PTR [rcx]
 xor eax,eax
 lock cmpxchg QWORD PTR [r14+64],rcx
 je jname_heap_bound
 cmp rax,rcx
 jne jname_bad
jname_heap_bound:
 mov rcx,rbx
 mov rdx,r14
 mov r8d,r13d
 call QWORD PTR [rdi+40]
 test rax,rax
 jz jname_zero
 cmp DWORD PTR [rbx],0
 jne jname_zero
 mov rdx,rax
 xor eax,eax
 lock cmpxchg QWORD PTR [r12+r15],rdx
 cmovz rax,rdx
jname_cached:
 mov r12,rax
 mov rcx,QWORD PTR [rsi+48]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r12
 call boom_heap_contains
 test eax,eax
 jz jname_bad
 mov rcx,r12
 mov rdx,QWORD PTR [rdi+32]
 mov r8,rbx
 call boom_object_check
 jmp jname_done
jname_bad:
 mov DWORD PTR [rbx],7
jname_zero:
 xor eax,eax
jname_done:
 add rsp,32
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_class_name ENDP

; All creation and identity updates use this lock. The heap has its own lock.
java_class_lock PROC
 mov eax,1
 xchg DWORD PTR [rdx+8],eax
 test eax,eax
 jz jcl_locked
jcl_spin:
 pause
 cmp DWORD PTR [rdx+8],0
 jne jcl_spin
 jmp java_class_lock
jcl_locked:
 ret
java_class_lock ENDP

; insert(pool RCX,oop RDX,typeId R8D); oop is published after type ID.
java_class_insert PROC
 mov r9,rdx
 shr r9,4
 mov rax,r9
 shr rax,19
 xor r9,rax
 and r9d,DWORD PTR [rcx+80]
 xor r11d,r11d
jci_probe:
 mov rax,r9
 shl rax,4
 add rax,QWORD PTR [rcx+72]
 cmp QWORD PTR [rax],0
 je jci_empty
 inc r9d
 and r9d,DWORD PTR [rcx+80]
 inc r11d
 cmp r11d,DWORD PTR [rcx+80]
 jbe jci_probe
 xor eax,eax
 ret
jci_empty:
 mov DWORD PTR [rax+8],r8d
 mov QWORD PTR [rax],rdx
 mov eax,1
 ret
java_class_insert ENDP

boom_java_class_load PROC FRAME
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
 sub rsp,1120
 .allocstack 1120
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov edi,r8d
 mov DWORD PTR [rsp+48],r8d
 test rbx,rbx
 jz jload_zero
 cmp DWORD PTR [rbx],0
 jne jload_zero
 call java_class_pool_valid
 test eax,eax
 jz jload_bad
 cmp edi,DWORD PTR [rsi+12]
 jae jload_bad
 mov rax,QWORD PTR [rsi+48]
 mov r12,QWORD PTR [rax]
 test r12,r12
 jz jload_unbound
 cmp DWORD PTR [r12],048454150h
 jne jload_bad
 cmp DWORD PTR [r12+4],1
 jne jload_bad
 mov r13,QWORD PTR [rsi+24]
 mov r14,QWORD PTR [rsi+16]
 mov rax,QWORD PTR [r14+rdi*8]
 test rax,rax
 jnz jload_done
 mov rdx,rsi
 call java_class_lock
 xor r15d,r15d
jload_walk:
 cmp edi,DWORD PTR [rsi+12]
 jae jload_locked_bad
 cmp QWORD PTR [r14+rdi*8],0
 jne jload_build
 cmp r15d,256
 jae jload_locked_bad
 mov DWORD PTR [rsp+r15*4+64],edi
 inc r15d
 imul rax,rdi,48
 lea r10,[r13+rax]
 mov r11,QWORD PTR [r10]
 test r11,r11
 jz jload_locked_bad
 cmp DWORD PTR [r11],054595045h
 jne jload_locked_bad
 cmp DWORD PTR [r11+4],1
 jne jload_locked_bad
 cmp DWORD PTR [r11+8],3
 jne jload_build
 mov edi,DWORD PTR [r10+8]
 jmp jload_walk
jload_build:
 test r15d,r15d
 jz jload_success
 dec r15d
 mov edi,DWORD PTR [rsp+r15*4+64]
 cmp QWORD PTR [r14+rdi*8],0
 jne jload_build
 imul rax,rdi,48
 lea r10,[r13+rax]
 mov eax,DWORD PTR [r10+16]
 cmp eax,DWORD PTR [rsi+84]
 jae jload_locked_bad
 mov r11,QWORD PTR [rsi+56]
 mov r11,QWORD PTR [r11+rax*8]
 test eax,eax
 jnz jload_loader_nonboot
 test r11,r11
 jnz jload_locked_bad
 jmp jload_loader_ready
jload_loader_nonboot:
 test r11,r11
 jz jload_locked_unbound
jload_loader_ready:
 mov QWORD PTR [rsp+32],r11
 mov eax,DWORD PTR [r10+20]
 cmp eax,DWORD PTR [rsi+88]
 jae jload_locked_bad
 mov r11,QWORD PTR [rsi+64]
 mov r11,QWORD PTR [r11+rax*8]
 test r11,r11
 jnz jload_module_ready
 test eax,eax
 jnz jload_locked_unbound
 test DWORD PTR [r10+24],1
 jz jload_locked_unbound
 test DWORD PTR [rsi+92],1
 jz jload_locked_unbound
jload_module_ready:
 mov QWORD PTR [rsp+40],r11
 xor r11d,r11d
 mov rax,QWORD PTR [r10]
 cmp DWORD PTR [rax+8],3
 jne jload_component_ready
 mov eax,DWORD PTR [r10+8]
 cmp eax,DWORD PTR [rsi+12]
 jae jload_locked_bad
 mov r11,QWORD PTR [r14+rax*8]
 test r11,r11
 jz jload_locked_bad
jload_component_ready:
 mov QWORD PTR [rsp+56],r11
 mov rcx,r12
 mov rdx,QWORD PTR [rsi+32]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz jload_locked_zero
 mov QWORD PTR [rsp+1104],rax
 mov ecx,DWORD PTR [rsi+96]
 mov r9,QWORD PTR [rsp+32]
 mov QWORD PTR [rax+rcx],r9
 mov ecx,DWORD PTR [rsi+100]
 mov r9,QWORD PTR [rsp+40]
 mov QWORD PTR [rax+rcx],r9
 mov ecx,DWORD PTR [rsi+104]
 mov r9,QWORD PTR [rsp+56]
 mov QWORD PTR [rax+rcx],r9
 mov rcx,rsi
 mov rdx,rax
 mov r8d,edi
 call java_class_insert
 test eax,eax
 jz jload_locked_bad
 mov rax,QWORD PTR [rsp+1104]
 mov QWORD PTR [r14+rdi*8],rax
 jmp jload_build
jload_success:
 mov edi,DWORD PTR [rsp+48]
 mov rax,QWORD PTR [r14+rdi*8]
 mov DWORD PTR [rsi+8],0
 jmp jload_done
jload_locked_unbound:
 mov DWORD PTR [rbx],20
 jmp jload_locked_zero
jload_locked_bad:
 mov DWORD PTR [rbx],7
jload_locked_zero:
 mov DWORD PTR [rsi+8],0
 jmp jload_zero
jload_unbound:
 mov DWORD PTR [rbx],20
 jmp jload_zero
jload_bad:
 mov DWORD PTR [rbx],7
jload_zero:
 xor eax,eax
jload_done:
 add rsp,1120
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_class_load ENDP

boom_java_class_typeid PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 test rbx,rbx
 jz jtype_none
 cmp DWORD PTR [rbx],0
 jne jtype_none
 call java_class_pool_valid
 test eax,eax
 jz jtype_bad
 test rdi,rdi
 jz jtype_null
 mov rcx,QWORD PTR [rsi+48]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz jtype_bad
 mov rcx,rdi
 mov rdx,QWORD PTR [rsi+32]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz jtype_none
 mov r9,rdi
 shr r9,4
 mov rax,r9
 shr rax,19
 xor r9,rax
 and r9d,DWORD PTR [rsi+80]
 xor r11d,r11d
jtype_probe:
 mov rax,r9
 shl rax,4
 add rax,QWORD PTR [rsi+72]
 cmp QWORD PTR [rax],rdi
 je jtype_found
 cmp QWORD PTR [rax],0
 je jtype_bad
 inc r9d
 and r9d,DWORD PTR [rsi+80]
 inc r11d
 cmp r11d,DWORD PTR [rsi+80]
 jbe jtype_probe
 jmp jtype_bad
jtype_found:
 mov eax,DWORD PTR [rax+8]
 cmp eax,DWORD PTR [rsi+12]
 jae jtype_bad
 mov r10,QWORD PTR [rsi+16]
 cmp QWORD PTR [r10+rax*8],rdi
 jne jtype_bad
 jmp jtype_done
jtype_null:
 mov DWORD PTR [rbx],4
 jmp jtype_none
jtype_bad:
 mov DWORD PTR [rbx],7
jtype_none:
 mov eax,0FFFFFFFFh
jtype_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_class_typeid ENDP

; Identity binding validates the same heap, normal source type and module loader.
boom_java_class_bind_loader PROC
 xor r10d,r10d
 jmp java_class_bind
boom_java_class_bind_loader ENDP
boom_java_class_bind_module PROC
 mov r10d,1
 jmp java_class_bind
boom_java_class_bind_module ENDP
java_class_bind PROC FRAME
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
 mov rsi,rcx
 mov edi,edx
 mov r12,r8
 mov rbx,r9
 mov r13d,r10d
 test rbx,rbx
 jz jbind_zero
 cmp DWORD PTR [rbx],0
 jne jbind_zero
 mov rdx,rsi
 call java_class_pool_valid
 test eax,eax
 jz jbind_bad
 mov eax,DWORD PTR [rsi+84]
 mov r14,QWORD PTR [rsi+56]
 mov r15,QWORD PTR [rsi+112]
 test r13d,r13d
 jz jbind_table_ready
 mov eax,DWORD PTR [rsi+88]
 mov r14,QWORD PTR [rsi+64]
 mov r15,QWORD PTR [rsi+120]
jbind_table_ready:
 cmp edi,eax
 jae jbind_bad
 test r13d,r13d
 jnz jbind_nonnull
 test edi,edi
 jnz jbind_nonnull
 test r12,r12
 jnz jbind_bad
 cmp QWORD PTR [r14],0
 jne jbind_bad
 mov eax,1
 jmp jbind_done
jbind_nonnull:
 test r12,r12
 jz jbind_bad
 mov rcx,QWORD PTR [rsi+48]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r12
 call boom_heap_contains
 test eax,eax
 jz jbind_bad
 mov rcx,r12
 mov rdx,QWORD PTR [rsi+40]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz jbind_zero
 mov r10,rax
 test r13d,r13d
 jz jbind_type
 mov eax,DWORD PTR [rsi+136]
 test al,7
 jnz jbind_bad
 mov edx,DWORD PTR [r10+32]
 shl rdx,3
 lea ecx,[eax+8]
 cmp rcx,rdx
 ja jbind_bad
 mov r11,QWORD PTR [rsi+128]
 mov edx,DWORD PTR [r11+rdi*4]
 cmp edx,DWORD PTR [rsi+84]
 jae jbind_bad
 mov r11,QWORD PTR [rsi+56]
 mov r11,QWORD PTR [r11+rdx*8]
 test edx,edx
 jz jbind_loader_bound
 test r11,r11
 jz jbind_unbound
jbind_loader_bound:
 cmp QWORD PTR [r12+rax],r11
 jne jbind_bad
jbind_type:
 mov rcx,QWORD PTR [r10+8]
 mov rdx,r15
 call boom_type_assignable
 test eax,eax
 jz jbind_bad
 mov rdx,rsi
 call java_class_lock
 mov rax,QWORD PTR [r14+rdi*8]
 test rax,rax
 jz jbind_publish
 cmp rax,r12
 jne jbind_locked_bad
jbind_publish:
 mov QWORD PTR [r14+rdi*8],r12
 test r13d,r13d
 jz jbind_success
 xor r11d,r11d
 mov r10,QWORD PTR [rsi+24]
 mov r14,QWORD PTR [rsi+16]
jbind_patch:
 cmp r11d,DWORD PTR [rsi+12]
 jae jbind_success
 cmp DWORD PTR [r10+20],edi
 jne jbind_next
 mov rax,QWORD PTR [r14+r11*8]
 test rax,rax
 jz jbind_next
 mov ecx,DWORD PTR [rsi+100]
 mov QWORD PTR [rax+rcx],r12
jbind_next:
 add r10,48
 inc r11d
 jmp jbind_patch
jbind_success:
 mov DWORD PTR [rsi+8],0
 mov eax,1
 jmp jbind_done
jbind_locked_bad:
 mov DWORD PTR [rsi+8],0
 jmp jbind_bad
jbind_unbound:
 mov DWORD PTR [rbx],20
 jmp jbind_zero
jbind_bad:
 mov DWORD PTR [rbx],7
jbind_zero:
 xor eax,eax
jbind_done:
 add rsp,32
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
java_class_bind ENDP

boom_java_class_seal PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rsi,rcx
 mov rbx,rdx
 test rbx,rbx
 jz jseal_zero
 cmp DWORD PTR [rbx],0
 jne jseal_zero
 mov rdx,rsi
 call java_class_pool_valid
 test eax,eax
 jz jseal_bad
 mov rdx,rsi
 call java_class_lock
 mov rax,QWORD PTR [rsi+64]
 cmp QWORD PTR [rax],0
 je jseal_unbound
 mov DWORD PTR [rsi+92],0
 mov DWORD PTR [rsi+8],0
 mov eax,1
 jmp jseal_done
jseal_unbound:
 mov DWORD PTR [rsi+8],0
 mov DWORD PTR [rbx],20
 jmp jseal_zero
jseal_bad:
 mov DWORD PTR [rbx],7
jseal_zero:
 xor eax,eax
jseal_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_java_class_seal ENDP

; Query operations: getClass0, isInterface1, isArray2, isPrimitive3, isHidden4,
; getSuperclass5, isAssignableFrom6, isInstance7. All are instance natives.
boom_java_class_query PROC FRAME
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
 mov rsi,r8
 mov rdi,rdx
 mov r12d,r9d
 test rbx,rbx
 jz jquery_zero
 cmp DWORD PTR [rbx],0
 jne jquery_zero
 test rdi,rdi
 jz jquery_bad
 cmp r12d,7
 ja jquery_bad
 mov rdx,rsi
 call java_class_pool_valid
 test eax,eax
 jz jquery_bad
 test r12d,r12d
 jnz jquery_class
 mov rdx,QWORD PTR [rdi]
 test rdx,rdx
 jz jquery_null
 mov rcx,QWORD PTR [rsi+48]
 mov rcx,QWORD PTR [rcx]
 call boom_heap_contains
 test eax,eax
 jz jquery_bad
 mov rcx,QWORD PTR [rdi]
 mov rdx,QWORD PTR [rsi+40]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz jquery_zero
 mov r8d,DWORD PTR [rax+16]
 mov rcx,rbx
 mov rdx,rsi
 call boom_java_class_load
 jmp jquery_done
jquery_class:
 mov rcx,rbx
 mov rdx,rsi
 mov r8,QWORD PTR [rdi]
 call boom_java_class_typeid
 cmp eax,0FFFFFFFFh
 je jquery_zero
 imul rax,48
 add rax,QWORD PTR [rsi+24]
 mov r13,rax
 mov r10,QWORD PTR [rax]
 cmp r12d,5
 jae jquery_relations
 mov eax,DWORD PTR [r10+8]
 cmp r12d,1
 je jquery_interface
 cmp r12d,2
 je jquery_array
 cmp r12d,3
 je jquery_primitive
 mov eax,DWORD PTR [r13+24]
 shr eax,1
 and eax,1
 jmp jquery_done
jquery_interface:
 cmp eax,2
 sete al
 movzx eax,al
 jmp jquery_done
jquery_array:
 cmp eax,3
 sete al
 movzx eax,al
 jmp jquery_done
jquery_primitive:
 test eax,eax
 sete al
 movzx eax,al
 jmp jquery_done
jquery_relations:
 cmp r12d,5
 jne jquery_assignable
 mov r8d,DWORD PTR [r13+12]
 cmp r8d,0FFFFFFFFh
 je jquery_zero
 mov rcx,rbx
 mov rdx,rsi
 call boom_java_class_load
 jmp jquery_done
jquery_assignable:
 cmp r12d,6
 jne jquery_instance
 mov rcx,rbx
 mov rdx,rsi
 mov r8,QWORD PTR [rdi+8]
 call boom_java_class_typeid
 cmp eax,0FFFFFFFFh
 je jquery_zero
 imul rax,48
 add rax,QWORD PTR [rsi+24]
 mov rcx,QWORD PTR [rax]
 mov rdx,QWORD PTR [r13]
 call boom_type_assignable
 jmp jquery_done
jquery_instance:
 cmp DWORD PTR [r10+8],0
 je jquery_zero
 mov rdx,QWORD PTR [rdi+8]
 test rdx,rdx
 jz jquery_zero
 mov rcx,QWORD PTR [rsi+48]
 mov rcx,QWORD PTR [rcx]
 call boom_heap_contains
 test eax,eax
 jz jquery_bad
 mov rcx,QWORD PTR [rdi+8]
 mov rdx,QWORD PTR [rsi+40]
 mov r8,QWORD PTR [r13]
 mov r9,rbx
 call boom_runtime_instanceof
 jmp jquery_done
jquery_null:
 mov DWORD PTR [rbx],4
 jmp jquery_zero
jquery_bad:
 mov DWORD PTR [rbx],7
jquery_zero:
 xor eax,eax
jquery_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_class_query ENDP
END
