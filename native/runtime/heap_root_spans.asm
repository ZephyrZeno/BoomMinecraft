; Quiescent root-region collection. Span16 {QWORD cells*, QWORD count}.
; Metadata and cells must remain stable until return. No guest allocation.
; Skip empty cells in MASM; do not copy millions of unresolved metadata slots.
; The existing heap marker validates all populated references and traces fields.
; Limits: 65536 regions, 16M cells/region, 64M cells total, 1M populated roots.
; Returns the existing collector's freed-object count, or -1 on invalid input/OOM.
option casemap:none
EXTERN boom_heap_collect:PROC
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
PUBLIC boom_heap_collect_spans
.code
boom_heap_collect_spans PROC FRAME
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
 mov rsi,rdx
 mov rdi,r8
 xor r14d,r14d
 test rbx,rbx
 jz hspan_bad
 cmp DWORD PTR [rbx],048454150h
 jne hspan_bad
 cmp DWORD PTR [rbx+4],1
 jne hspan_bad
 cmp rdi,65536
 ja hspan_bad
 test rdi,rdi
 jz hspan_empty
 test rsi,rsi
 jz hspan_bad
 mov rax,rdi
 shl rax,4
 add rax,rsi
 jc hspan_bad
 xor r12d,r12d
 xor r13d,r13d
 xor r10d,r10d
hspan_count_region:
 cmp r10,rdi
 jae hspan_allocate
 mov rax,r10
 shl rax,4
 mov r11,QWORD PTR [rsi+rax]
 mov rax,QWORD PTR [rsi+rax+8]
 cmp rax,01000000h
 ja hspan_bad
 add r12,rax
 cmp r12,04000000h
 ja hspan_bad
 test rax,rax
 jz hspan_count_next
 test r11,r11
 jz hspan_bad
 lea r8,[rax*8]
 add r8,r11
 jc hspan_bad
 xor edx,edx
hspan_count_cell:
 cmp rdx,rax
 jae hspan_count_next
 cmp QWORD PTR [r11+rdx*8],0
 je hspan_count_skip
 inc r13
 cmp r13,0100000h
 ja hspan_bad
hspan_count_skip:
 inc rdx
 jmp hspan_count_cell
hspan_count_next:
 inc r10
 jmp hspan_count_region
hspan_allocate:
 test r13,r13
 jz hspan_empty
 xor ecx,ecx
 lea rdx,[r13*8]
 mov r8d,03000h
 mov r9d,4
 call VirtualAlloc
 test rax,rax
 jz hspan_bad
 mov r14,rax
 xor r15d,r15d
 xor r10d,r10d
hspan_copy_region:
 cmp r10,rdi
 jae hspan_collect
 mov rax,r10
 shl rax,4
 mov r11,QWORD PTR [rsi+rax]
 mov rax,QWORD PTR [rsi+rax+8]
 cmp rax,01000000h
 ja hspan_bad
 test rax,rax
 jz hspan_copy_next
 test r11,r11
 jz hspan_bad
 xor edx,edx
hspan_copy_cell:
 cmp rdx,rax
 jae hspan_copy_next
 mov r8,QWORD PTR [r11+rdx*8]
 test r8,r8
 jz hspan_copy_skip
 cmp r15,r13
 jae hspan_bad
 mov QWORD PTR [r14+r15*8],r8
 inc r15
hspan_copy_skip:
 inc rdx
 jmp hspan_copy_cell
hspan_copy_next:
 inc r10
 jmp hspan_copy_region
hspan_collect:
 cmp r15,r13
 jne hspan_bad
 mov rcx,rbx
 mov rdx,r14
 mov r8,r15
 call boom_heap_collect
 jmp hspan_release
hspan_empty:
 mov rcx,rbx
 xor edx,edx
 xor r8d,r8d
 call boom_heap_collect
 jmp hspan_done
hspan_bad:
 mov rax,-1
hspan_release:
 mov QWORD PTR [rsp+32],rax
 test r14,r14
 jz hspan_restored
 mov rcx,r14
 xor edx,edx
 mov r8d,08000h
 call VirtualFree
hspan_restored:
 mov rax,QWORD PTR [rsp+32]
hspan_done:
 add rsp,48
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_heap_collect_spans ENDP
END
