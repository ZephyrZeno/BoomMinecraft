; A separate unregistered typed-memory dispatch. Original DLL is unchanged.
; Only five original plain native read tails are routed here. All other
; adapters, all heap operations and the original thread-ID domain are retained.
; JMAP80/1 owner8 is published by the actual bridge's open operation. The
; caller-owned owner allocation outlives all VM users and native reads.
.code
PUBLIC boom_java_unsafe_jimage_memory
boom_java_unsafe_jimage_memory PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 test rcx,rcx
 jz jur_bridge_original
 cmp DWORD PTR [rcx],0
 jne jur_bridge_original
 test rdx,rdx
 jz jur_bridge_original
 cmp QWORD PTR [rdx+8],0
 jne jur_bridge_original
 cmp r9d,2
 jb jur_bridge_original
 cmp r9d,6
 ja jur_bridge_original
 lea r10,boom_provider_jimage_native_map_pool
 cmp DWORD PTR [r10],050414D4Ah
 jne jur_bridge_original
 cmp DWORD PTR [r10+4],1
 jne jur_bridge_original
 cmp DWORD PTR [r10+24],1
 jne jur_bridge_original
 mov rax,QWORD PTR [r10+8]
 test rax,rax
 jz jur_bridge_original
 mov QWORD PTR [rsp+32],rax
 call boom_jimage_unsafe_memory_read
 add rsp,40
 ret
jur_bridge_original:
 add rsp,40
 jmp boom_java_unsafe_memory
boom_java_unsafe_jimage_memory ENDP

; The generated prefix below is the original UFMP/Unsafe receiver validator,
; including its original stack layout. There is no call-and-clear Context path.
PUBLIC boom_jimage_unsafe_memory_read
boom_jimage_unsafe_memory_read PROC
 test rcx,rcx
 jz jur_direct_original
 cmp DWORD PTR [rcx],0
 jne jur_direct_original
 test rdx,rdx
 jz jur_direct_original
 cmp QWORD PTR [rdx+8],0
 jne jur_direct_original
 cmp r9d,2
 jb jur_direct_original
 cmp r9d,6
 ja jur_direct_original
 jmp jur_validated_read
jur_direct_original:
 jmp boom_java_unsafe_memory
boom_jimage_unsafe_memory_read ENDP

jur_validated_read PROC PRIVATE FRAME
;@ORIGINAL_RECEIVER_PREFIX@
 ; The fifth argument is the same Owner128 whose JMAP bridge holds the lease.
 mov rax,QWORD PTR [rsp+224]
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [r12+16]
 mov QWORD PTR [rsp+40],rax
 mov DWORD PTR [rsp+48],r14d
 mov DWORD PTR [rsp+52],0
 mov QWORD PTR [rsp+56],0
 mov QWORD PTR [rsp+64],0
 mov QWORD PTR [rsp+72],0
 lea rcx,[rsp+32]
 call boom_jimage_owned_scalar_read
 test eax,eax
 jnz jur_old_domain
 mov rax,QWORD PTR [rsp+56]
 jmp jur_done
jur_old_domain:
 mov rcx,rbx
 mov rdx,r12
 mov r8,r13
 mov r9d,r14d
 add rsp,120
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 jmp boom_java_unsafe_memory
jur_unbound:
 mov DWORD PTR [rbx],20
 jmp jur_zero
jur_null:
 mov DWORD PTR [rbx],4
 jmp jur_zero
jur_bad:
 mov DWORD PTR [rbx],7
jur_zero:
 xor eax,eax
jur_done:
 add rsp,120
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
jur_validated_read ENDP
