; Explicit QUIESCENT nonmoving root snapshot, no scheduler/collector/liveness guess.
; DWORD snapshot(Span16* table,DWORD spans,QWORD* out,DWORD capacity,QWORD* count).
; Span16 = {aligned native address,number of QWORD oop cells}. The directory is
; metadata, never itself an oop root. Table/arrays must stay valid and unchanged.
; Success copies every nonzero oop, retaining duplicates, then publishes count.
; 87 invalid protocol/overlap,122 insufficient capacity. On either failure both
; output vector and count remain unchanged. No allocation, host callback or lock.
; This is NOT an automatic collector or a concurrent safepoint implementation.
.code
PUBLIC boom_provider_native_roots_snapshot
boom_provider_native_roots_snapshot PROC FRAME
 push rbx
 .pushreg rbx
 push rbp
 .pushreg rbp
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
 sub rsp,56
 .allocstack 56
 .endprolog
 mov rbx,rcx
 mov ebp,edx
 mov rsi,r8
 mov edi,r9d
 mov r12,QWORD PTR [rsp+160]
 mov eax,87
 cmp ebp,4096
 ja pnrs_done
 cmp edi,1048576
 ja pnrs_done
 test r12,r12
 jz pnrs_done
 test r12,7
 jnz pnrs_done
 mov r13,r12
 add r13,8
 jc pnrs_done
 test rbx,7
 jnz pnrs_done
 test ebp,ebp
 jz pnrs_table_valid
 test rbx,rbx
 jz pnrs_done
pnrs_table_valid:
 mov r14d,ebp
 shl r14,4
 add r14,rbx
 jc pnrs_done
 test edi,edi
 jz pnrs_out_valid
 test rsi,rsi
 jz pnrs_done
pnrs_out_valid:
 test rsi,7
 jnz pnrs_done
 mov r15d,edi
 shl r15,3
 add r15,rsi
 jc pnrs_done
 ; Output vector and its publication cell cannot alias the directory.
 test ebp,ebp
 jz pnrs_table_disjoint
 cmp r12,r14
 jae pnrs_count_table_disjoint
 cmp rbx,r13
 jb pnrs_done
pnrs_count_table_disjoint:
 test edi,edi
 jz pnrs_table_disjoint
 cmp rsi,r14
 jae pnrs_table_disjoint
 cmp rbx,r15
 jb pnrs_done
pnrs_table_disjoint:
 test edi,edi
 jz pnrs_outputs_disjoint
 cmp r12,r15
 jae pnrs_outputs_disjoint
 cmp rsi,r13
 jb pnrs_done
pnrs_outputs_disjoint:
 xor r10d,r10d
 xor r11d,r11d
pnrs_validate:
 cmp r10d,ebp
 jae pnrs_capacity
 mov rcx,r10
 shl rcx,4
 mov r8,QWORD PTR [rbx+rcx]
 mov r9,QWORD PTR [rbx+rcx+8]
 cmp r9,1048576
 ja pnrs_invalid
 test r9,r9
 jz pnrs_next_span
 test r8,r8
 jz pnrs_invalid
 test r8,7
 jnz pnrs_invalid
 mov rdx,r9
 shl rdx,3
 add rdx,r8
 jc pnrs_invalid
 ; Neither root cells nor output may overlap the metadata or each other.
 cmp r8,r14
 jae pnrs_root_table_disjoint
 cmp rbx,rdx
 jb pnrs_invalid
pnrs_root_table_disjoint:
 cmp r12,rdx
 jae pnrs_root_count_disjoint
 cmp r8,r13
 jb pnrs_invalid
pnrs_root_count_disjoint:
 test edi,edi
 jz pnrs_count_values
 cmp rsi,rdx
 jae pnrs_count_values
 cmp r8,r15
 jb pnrs_invalid
pnrs_count_values:
 xor ecx,ecx
pnrs_count_loop:
 cmp rcx,r9
 jae pnrs_next_span
 cmp QWORD PTR [r8+rcx*8],0
 je pnrs_count_next
 inc r11
pnrs_count_next:
 inc rcx
 jmp pnrs_count_loop
pnrs_next_span:
 inc r10d
 jmp pnrs_validate
pnrs_capacity:
 cmp r11,rdi
 ja pnrs_small
 mov QWORD PTR [rsp+32],r11
 xor r10d,r10d
 xor r11d,r11d
pnrs_copy_span:
 cmp r10d,ebp
 jae pnrs_publish
 mov rcx,r10
 shl rcx,4
 mov r8,QWORD PTR [rbx+rcx]
 mov r9,QWORD PTR [rbx+rcx+8]
 xor ecx,ecx
pnrs_copy_loop:
 cmp rcx,r9
 jae pnrs_copy_next_span
 mov rax,QWORD PTR [r8+rcx*8]
 test rax,rax
 jz pnrs_copy_next
 ; A caller that violates quiescence must still never overrun the output.
 cmp r11,rdi
 jae pnrs_small
 mov QWORD PTR [rsi+r11*8],rax
 inc r11
pnrs_copy_next:
 inc rcx
 jmp pnrs_copy_loop
pnrs_copy_next_span:
 inc r10d
 jmp pnrs_copy_span
pnrs_publish:
 cmp r11,QWORD PTR [rsp+32]
 jne pnrs_invalid
 mov QWORD PTR [r12],r11
 xor eax,eax
 jmp pnrs_done
pnrs_small:
 mov eax,122
 jmp pnrs_done
pnrs_invalid:
 mov eax,87
pnrs_done:
 add rsp,56
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_provider_native_roots_snapshot ENDP
