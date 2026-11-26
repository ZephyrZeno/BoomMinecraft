; Source-layout primitive wrapper unboxing for constructor invocation, ASM only.
; (Context32 RCX,boxed Object RDX,targetKind R8D,BoxPool48 R9)->slot bits RAX.
; BCNV48/1: magic0 ABI4 count8D=8 rowBytes12D=24 heapCell16Q map24Q
; rows32Q reserved40Q=0. Row24: classId0D kind4D layout8Q offset16D width20D.
; Normal objects are checked in the real heap and source runtime type map.
EXTERN boom_heap_contains:PROC
EXTERN boom_runtime_row:PROC
EXTERN boom_constructor_widen:PROC
PUBLIC boom_constructor_unbox
.const
constructor_unbox_widths BYTE 1,1,2,2,4,8,4,8
.code
boom_constructor_unbox PROC FRAME
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
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r9
 mov r12d,r8d
 test rbx,rbx
 jz cu_zero
 cmp DWORD PTR [rbx],0
 jne cu_zero
 cmp r12d,7
 ja cu_bad
 test rdi,rdi
 jz cu_bad
 cmp DWORD PTR [rdi],0564E4342h
 jne cu_bad
 cmp DWORD PTR [rdi+4],1
 jne cu_bad
 cmp DWORD PTR [rdi+8],8
 jne cu_bad
 cmp DWORD PTR [rdi+12],24
 jne cu_bad
 cmp QWORD PTR [rdi+40],0
 jne cu_bad
 cmp QWORD PTR [rdi+24],0
 je cu_bad
 cmp QWORD PTR [rdi+32],0
 je cu_bad
 mov rax,QWORD PTR [rdi+16]
 test rax,rax
 jz cu_bad
 mov rcx,QWORD PTR [rax]
 test rcx,rcx
 jz cu_bad
 test rsi,rsi
 jz cu_argument
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz cu_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [rdi+24]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz cu_zero
 cmp DWORD PTR [rbx],0
 jne cu_zero
 cmp DWORD PTR [rax+20],0
 jne cu_argument
 mov r13,QWORD PTR [rdi+32]
 mov r10,QWORD PTR [rax]
 mov r11d,DWORD PTR [rax+16]
 mov ecx,8
cu_find:
 cmp QWORD PTR [r13+8],r10
 je cu_found
 add r13,24
 dec ecx
 jnz cu_find
 jmp cu_argument
cu_found:
 cmp DWORD PTR [r13],r11d
 jne cu_bad
 mov edx,DWORD PTR [r13+4]
 cmp edx,7
 ja cu_bad
 lea r10,constructor_unbox_widths
 movzx r11d,BYTE PTR [r10+rdx]
 cmp r11d,DWORD PTR [r13+20]
 jne cu_bad
 mov eax,DWORD PTR [r13+16]
 lea r10,[rax+r11]
 cmp r10,QWORD PTR [rsi-16]
 ja cu_bad
 add rax,rsi
 cmp r11d,1
 je cu_byte
 cmp r11d,2
 je cu_word
 cmp r11d,4
 je cu_dword
 mov r9,QWORD PTR [rax]
 jmp cu_convert
cu_byte:
 movzx r9d,BYTE PTR [rax]
 jmp cu_convert
cu_word:
 movzx r9d,WORD PTR [rax]
 jmp cu_convert
cu_dword:
 mov r9d,DWORD PTR [rax]
cu_convert:
 mov rcx,rbx
 mov r8d,r12d
 call boom_constructor_widen
 jmp cu_done
cu_argument:
 mov DWORD PTR [rbx],18
 jmp cu_zero
cu_bad:
 mov DWORD PTR [rbx],7
cu_zero:
 xor eax,eax
cu_done:
 add rsp,48
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_constructor_unbox ENDP
