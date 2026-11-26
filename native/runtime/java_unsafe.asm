; Normal-source Unsafe bootstrap services, Context32, Windows x64 MASM.
; JUNS80: magic0 ABI4 state8 bindingCount12 ClassPool16 RuntimeMap24
; heapCell32 sourceUnsafeLayout40 Binding24*48 arrayScales*56
; typeCount64 sourceUnsafeId68 constantCells*72 (five QWORD cell pointers).
; Binding24: operation0 method4 nativeEntry8 access16 reserved20.
; Supported subset: register, array base/scale, fullFence. No fake memory API.
option casemap:none
EXTERN boom_heap_contains:PROC
EXTERN boom_runtime_row:PROC
EXTERN boom_java_class_typeid:PROC
EXTERN GetNativeSystemInfo:PROC
PUBLIC boom_java_unsafe
PUBLIC boom_java_unsafe_constants
.code
; Internal immutable metadata validation. R13 pool; clobbers volatile registers.
ju_pool_valid PROC
 xor eax,eax
 test r13,r13
 jz ju_pool_done
 cmp DWORD PTR [r13],04A554E53h
 jne ju_pool_done
 cmp DWORD PTR [r13+4],1
 jne ju_pool_done
 cmp DWORD PTR [r13+12],3
 jne ju_pool_done
 mov ecx,DWORD PTR [r13+8]
 test ecx,ecx
 jz ju_pool_state_ok
 cmp ecx,2
 jne ju_pool_done
ju_pool_state_ok:
 mov ecx,DWORD PTR [r13+64]
 dec ecx
 cmp ecx,0FFFFFh
 ja ju_pool_done
 mov ecx,DWORD PTR [r13+68]
 cmp ecx,DWORD PTR [r13+64]
 jae ju_pool_done
 mov r10,QWORD PTR [r13+16]
 test r10,r10
 jz ju_pool_done
 cmp DWORD PTR [r10],04A434C53h
 jne ju_pool_done
 cmp DWORD PTR [r10+4],1
 jne ju_pool_done
 mov ecx,DWORD PTR [r10+12]
 cmp ecx,DWORD PTR [r13+64]
 jne ju_pool_done
 mov r10,QWORD PTR [r13+24]
 test r10,r10
 jz ju_pool_done
 cmp DWORD PTR [r10],052545950h
 jne ju_pool_done
 cmp DWORD PTR [r10+4],2
 jne ju_pool_done
 mov ecx,DWORD PTR [r10+12]
 cmp ecx,DWORD PTR [r13+64]
 jne ju_pool_done
 cmp QWORD PTR [r13+32],0
 je ju_pool_done
 cmp QWORD PTR [r13+40],0
 je ju_pool_done
 cmp QWORD PTR [r13+48],0
 je ju_pool_done
 cmp QWORD PTR [r13+56],0
 je ju_pool_done
 mov r10,QWORD PTR [r13+72]
 test r10,r10
 jz ju_pool_done
 xor ecx,ecx
ju_pool_cells:
 cmp QWORD PTR [r10+rcx*8],0
 je ju_pool_done
 inc ecx
 cmp ecx,5
 jb ju_pool_cells
 mov eax,1
ju_pool_done:
 ret
ju_pool_valid ENDP

; (Context RCX, QWORD argv* RDX, Pool R8, operation R9D) -> Java result.
boom_java_unsafe PROC FRAME
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
 mov r12,rdx
 mov r13,r8
 mov DWORD PTR [rsp+32],r9d
 test rbx,rbx
 jz ju_zero
 cmp DWORD PTR [rbx],0
 jne ju_zero
 call ju_pool_valid
 test eax,eax
 jz ju_bad
 cmp DWORD PTR [rsp+32],0
 je ju_register
 cmp DWORD PTR [r13+8],2
 jne ju_unbound
 test r12,r12
 jz ju_bad
 mov rsi,QWORD PTR [r12]
 test rsi,rsi
 jz ju_null
 mov rcx,QWORD PTR [r13+32]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz ju_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+24]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz ju_zero
 mov ecx,DWORD PTR [rax+16]
 cmp ecx,DWORD PTR [r13+68]
 jne ju_bad
 mov rcx,QWORD PTR [r13+40]
 cmp QWORD PTR [rsi-8],rcx
 jne ju_bad
 cmp DWORD PTR [rsp+32],3
 je ju_fence
 cmp DWORD PTR [rsp+32],1
 jb ju_bad
 cmp DWORD PTR [rsp+32],2
 ja ju_bad
 mov r8,QWORD PTR [r12+8]
 test r8,r8
 jz ju_null
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+16]
 call boom_java_class_typeid
 cmp eax,0FFFFFFFFh
 je ju_zero
 cmp eax,DWORD PTR [r13+64]
 jae ju_bad
 mov r10,QWORD PTR [r13+16]
 mov r10,QWORD PTR [r10+24]
 mov ecx,eax
 imul rcx,48
 mov r10,QWORD PTR [r10+rcx]
 test r10,r10
 jz ju_bad
 cmp DWORD PTR [r10+8],3
 jne ju_bad
 mov r10,QWORD PTR [r13+56]
 mov eax,DWORD PTR [r10+rax*4]
 test eax,eax
 jz ju_bad
 cmp eax,8
 ja ju_bad
 lea ecx,[rax-1]
 test eax,ecx
 jnz ju_bad
 cmp DWORD PTR [rsp+32],2
 je ju_done
 ; Normal array payload starts at oop+0, independently validated above.
 xor eax,eax
 jmp ju_done
ju_fence:
 mfence
 jmp ju_zero
ju_register:
 ; Confirm the immutable supplied AOT binding subset, then publish readiness.
 mov rsi,QWORD PTR [r13+48]
 mov edi,1
ju_register_row:
 cmp DWORD PTR [rsi],edi
 jne ju_bad
 cmp DWORD PTR [rsi+4],0FFFFFFFFh
 je ju_bad
 cmp QWORD PTR [rsi+8],0
 je ju_bad
 cmp DWORD PTR [rsi+20],0
 jne ju_bad
 mov eax,0102h
 cmp edi,3
 jne ju_register_flags
 mov eax,0101h
ju_register_flags:
 cmp DWORD PTR [rsi+16],eax
 jne ju_bad
 add rsi,24
 inc edi
 cmp edi,3
 jbe ju_register_row
 xor eax,eax
 mov edx,2
 lock cmpxchg DWORD PTR [r13+8],edx
 test eax,eax
 jz ju_zero
 cmp eax,2
 je ju_zero
 jmp ju_bad
ju_unbound:
 mov DWORD PTR [rbx],20
 jmp ju_zero
ju_null:
 mov DWORD PTR [rbx],4
 jmp ju_zero
ju_bad:
 mov DWORD PTR [rbx],7
ju_zero:
 xor eax,eax
ju_done:
 add rsp,48
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_unsafe ENDP

; Post-original-<clinit> VM injection, before class readiness publication.
; (Context RCX, Pool RDX). Writeback is disabled until its API is implemented.
boom_java_unsafe_constants PROC FRAME
 push rbx
 .pushreg rbx
 push r13
 .pushreg r13
 sub rsp,88
 .allocstack 88
 .endprolog
 mov rbx,rcx
 mov r13,rdx
 test rbx,rbx
 jz ju_constants_done
 cmp DWORD PTR [rbx],0
 jne ju_constants_done
 call ju_pool_valid
 test eax,eax
 jz ju_constants_bad
 lea rcx,[rsp+32]
 call GetNativeSystemInfo
 mov edx,DWORD PTR [rsp+36]
 test edx,edx
 jz ju_constants_bad
 lea eax,[rdx-1]
 test eax,edx
 jnz ju_constants_bad
 mov r10,QWORD PTR [r13+72]
 mov rax,QWORD PTR [r10]
 mov QWORD PTR [rax],8
 mov rax,QWORD PTR [r10+8]
 mov QWORD PTR [rax],rdx
 mov rax,QWORD PTR [r10+16]
 mov QWORD PTR [rax],0
 mov rax,QWORD PTR [r10+24]
 mov QWORD PTR [rax],1
 mov rax,QWORD PTR [r10+32]
 mov QWORD PTR [rax],0
 jmp ju_constants_done
ju_constants_bad:
 mov DWORD PTR [rbx],7
ju_constants_done:
 xor eax,eax
 add rsp,88
 pop r13
 pop rbx
 ret
boom_java_unsafe_constants ENDP
END
