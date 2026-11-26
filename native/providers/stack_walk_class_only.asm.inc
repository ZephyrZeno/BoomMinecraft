; Original Class-only getCallerClass protocol, Context32 + actual TracePool3.
; SWCP144/1: constantsAgree8,maxNodes12,heapCell16,trace24,JCLS32,
; registryCell40,typeMap48,walkerType56,ClassArrayType64,skipIds72,count80,
; threadFMAP88,modeFMAP96,scopeFMAP104,continuationFMAP112,doStackWalk120,
; BaseVirtualThreadType128,CallerClassFinderType136.
; Active record128 lives on its owning native stack, never at a caller address:
; next0,generation8,OSid16,Context24,receiver32,mode40,originalBuffer48,
; Thread56,cursor64,nativeHead72,currentBuffer80,busy88,hops92,
; skip96,count100,start104,end108,pool112,JavaResult120.
; No lock is held while filling mirrors or calling intact original Java.
.data
ALIGN 8
sw_lock QWORD 0
sw_head QWORD 0
sw_generation QWORD 1
PUBLIC boom_stack_walk_active_count
boom_stack_walk_active_count QWORD 0
PUBLIC boom_stack_walk_counters
; checks0,firstCalls8,fetchCalls16,ClassMirrors24,unsupported32,badToken40,
; cleaned48,maximumActive56. These are observations, never Java success counts.
boom_stack_walk_counters QWORD 8 DUP(0)
.code

; Private convention: RBX Context, RSI pool, R12 active record.
sw_valid PROC PRIVATE
 test rsi,rsi
 jz sw_valid_bad
 cmp DWORD PTR [rsi],053574350h
 jne sw_valid_bad
 cmp DWORD PTR [rsi+4],1
 jne sw_valid_bad
 cmp DWORD PTR [rsi+8],1
 jne sw_valid_bad
 cmp DWORD PTR [rsi+12],128
 jne sw_valid_bad
 cmp DWORD PTR [rsi+84],0
 jne sw_valid_bad
 mov eax,DWORD PTR [rsi+80]
 dec eax
 cmp eax,63
 ja sw_valid_bad
 mov eax,16
sw_valid_pointer:
 cmp QWORD PTR [rsi+rax],0
 je sw_valid_bad
 add eax,8
 cmp eax,80
 jb sw_valid_pointer
 mov eax,88
sw_valid_field:
 cmp QWORD PTR [rsi+rax],0
 je sw_valid_bad
 add eax,8
 cmp eax,144
 jb sw_valid_field
 mov eax,1
 ret
sw_valid_bad:
 mov DWORD PTR [rbx],7
 xor eax,eax
 ret
sw_valid ENDP

; Validate normal CallerClassFinder and its read-only inherited FMAPs.
; RCX receiver -> real current Thread, saved to record56. No Java fields written.
sw_receiver PROC PRIVATE FRAME
 push rdi
 .pushreg rdi
 push r13
 .pushreg r13
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rdi,rcx
 mov rcx,QWORD PTR [rsi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz sw_receiver_bad
 mov rcx,rdi
 mov rdx,QWORD PTR [rsi+48]
 mov r8,rbx
 call boom_runtime_type
 test rax,rax
 jz sw_receiver_done
 cmp rax,QWORD PTR [rsi+136]
 jne sw_receiver_unsupported
 mov rcx,rdi
 mov rdx,rbx
 call QWORD PTR [rsi+88]
 test rax,rax
 jz sw_receiver_done
 mov r13,QWORD PTR [rax]
 mov rcx,QWORD PTR [rsi+40]
 mov rcx,QWORD PTR [rcx]
 call boom_threads_current
 test rax,rax
 jz sw_receiver_unsupported
 cmp rax,r13
 jne sw_receiver_bad
 mov QWORD PTR [r12+56],rax
 mov rcx,rax
 mov rdx,QWORD PTR [rsi+48]
 mov r8,rbx
 call boom_runtime_type
 test rax,rax
 jz sw_receiver_done
 mov rcx,rax
 mov rdx,QWORD PTR [rsi+128]
 call boom_type_assignable
 test eax,eax
 jnz sw_receiver_unsupported
 mov rcx,rdi
 mov rdx,rbx
 call QWORD PTR [rsi+96]
 test rax,rax
 jz sw_receiver_done
 cmp QWORD PTR [rax],SW_SUPPORTED_MODE
 jne sw_receiver_unsupported
 mov rcx,rdi
 mov rdx,rbx
 call QWORD PTR [rsi+104]
 test rax,rax
 jz sw_receiver_done
 cmp QWORD PTR [rax],0
 jne sw_receiver_unsupported
 mov rcx,rdi
 mov rdx,rbx
 call QWORD PTR [rsi+112]
 test rax,rax
 jz sw_receiver_done
 cmp QWORD PTR [rax],0
 jne sw_receiver_unsupported
 mov eax,1
 jmp sw_receiver_done
sw_receiver_bad:
 mov DWORD PTR [rbx],7
 xor eax,eax
 jmp sw_receiver_done
sw_receiver_unsupported:
 mov DWORD PTR [rbx],20
 lock inc QWORD PTR [boom_stack_walk_counters+32]
 xor eax,eax
sw_receiver_done:
 add rsp,40
 pop r13
 pop rdi
 ret
sw_receiver ENDP

; (Class[] RCX, signed count EDX, start R8D) -> valid. Preserve slot0/slot1.
sw_buffer PROC PRIVATE FRAME
 push rdi
 .pushreg rdi
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rdi,rcx
 mov r13d,edx
 mov r14d,r8d
 cmp r14d,SW_BUFFER_START
 jl sw_buffer_bad
 cmp r13d,1048576
 jg sw_buffer_bad
 mov rcx,QWORD PTR [rsi+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz sw_buffer_bad
 mov rcx,rdi
 mov rdx,QWORD PTR [rsi+48]
 mov r8,rbx
 call boom_runtime_type
 test rax,rax
 jz sw_buffer_done
 cmp rax,QWORD PTR [rsi+64]
 jne sw_buffer_unsupported
 mov rax,QWORD PTR [rdi-16]
 test al,7
 jnz sw_buffer_bad
 shr rax,3
 cmp eax,DWORD PTR [rdi-20]
 jne sw_buffer_bad
 cmp r14,rax
 ja sw_buffer_bad
 test r13d,r13d
 jle sw_buffer_good
 mov edx,r13d
 add rdx,r14
 cmp rdx,rax
 ja sw_buffer_bad
sw_buffer_good:
 mov eax,1
 jmp sw_buffer_done
sw_buffer_unsupported:
 mov DWORD PTR [rbx],20
 lock inc QWORD PTR [boom_stack_walk_counters+32]
 xor eax,eax
 jmp sw_buffer_done
sw_buffer_bad:
 mov DWORD PTR [rbx],7
 xor eax,eax
sw_buffer_done:
 add rsp,32
 pop r14
 pop r13
 pop rdi
 ret
sw_buffer ENDP

; RDI Node -> validated MethodRow or0. Other Contexts delimit an embedding.
sw_node PROC PRIVATE
 test rdi,rdi
 jz sw_node_none
 cmp DWORD PTR [rdi],04652414Dh
 jne sw_node_bad
 cmp DWORD PTR [rdi+4],2
 jne sw_node_bad
 mov r10,QWORD PTR [rsi+24]
 cmp QWORD PTR [rdi+40],r10
 jne sw_node_bad
 cmp QWORD PTR [rdi+32],rbx
 jne sw_node_none
 test DWORD PTR [rdi+28],0FFFFFFFEh
 jnz sw_node_bad
 mov rax,QWORD PTR [rdi+16]
 mov r11,rax
 sub r11,QWORD PTR [r10+24]
 jc sw_node_bad
 test r11b,31
 jnz sw_node_bad
 shr r11,5
 mov edx,DWORD PTR [r10+16]
 cmp r11,rdx
 jae sw_node_bad
 test DWORD PTR [rax+4],0FFFFFF00h
 jnz sw_node_bad
 cmp QWORD PTR [rax+24],0
 jne sw_node_bad
 test DWORD PTR [rax+4],132
 jnz sw_node_unsupported
 mov r10,QWORD PTR [rsi+32]
 mov r11d,DWORD PTR [rax+20]
 cmp r11d,DWORD PTR [r10+12]
 jae sw_node_bad
 imul r11,48
 add r11,QWORD PTR [r10+24]
 mov rdx,QWORD PTR [rax+8]
 test rdx,rdx
 jz sw_node_bad
 cmp QWORD PTR [r11],rdx
 jne sw_node_bad
 test DWORD PTR [rax+4],32
 jnz sw_node_native
 mov edx,DWORD PTR [rax+16]
 dec edx
 cmp edx,65534
 ja sw_node_bad
 inc edx
 cmp DWORD PTR [rdi+24],edx
 jae sw_node_bad
 ret
sw_node_native:
 cmp DWORD PTR [rax+16],0
 jne sw_node_bad
 cmp DWORD PTR [rdi+24],0
 jne sw_node_bad
 ret
sw_node_unsupported:
 mov DWORD PTR [rbx],20
 lock inc QWORD PTR [boom_stack_walk_counters+32]
 jmp sw_node_none
sw_node_bad:
 mov DWORD PTR [rbx],7
sw_node_none:
 xor eax,eax
 ret
sw_node ENDP

; Advance the last decoded node exactly once. Never follow a cycle indefinitely.
sw_advance PROC PRIVATE
 cmp DWORD PTR [r12+92],128
 jae sw_advance_limit
 inc DWORD PTR [r12+92]
 mov rdi,QWORD PTR [rdi+8]
 ret
sw_advance_limit:
 mov DWORD PTR [rbx],20
 lock inc QWORD PTR [boom_stack_walk_counters+32]
 xor edi,edi
 ret
sw_advance ENDP

; Fill Class mirrors, leaving cursor on the final decoded frame for next batch.
sw_fill PROC PRIVATE FRAME
 push rdi
 .pushreg rdi
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rdi,QWORD PTR [r12+64]
 mov r13,QWORD PTR [r12+80]
 mov r14d,DWORD PTR [r12+100]
 mov r15d,DWORD PTR [r12+104]
sw_fill_loop:
 call sw_node
 test rax,rax
 jz sw_fill_end
 test DWORD PTR [rax+4],16
 jnz sw_fill_hidden
 cmp r15d,DWORD PTR [r12+104]
 jne sw_fill_class
 test DWORD PTR [rax+4],8
 jnz sw_fill_sensitive
sw_fill_class:
 mov r8d,DWORD PTR [rax+20]
 mov rcx,rbx
 mov rdx,QWORD PTR [rsi+32]
 call boom_java_class_load
 cmp DWORD PTR [rbx],0
 jne sw_fill_end
 test rax,rax
 jz sw_fill_bad
 mov QWORD PTR [r13+r15*8],rax
 lock inc QWORD PTR [boom_stack_walk_counters+24]
 inc r15d
 dec r14d
 jz sw_fill_done
sw_fill_hidden:
 call sw_advance
 cmp DWORD PTR [rbx],0
 jne sw_fill_end
 jmp sw_fill_loop
sw_fill_sensitive:
 mov DWORD PTR [rbx],20
 lock inc QWORD PTR [boom_stack_walk_counters+32]
 jmp sw_fill_end
sw_fill_bad:
 mov DWORD PTR [rbx],7
sw_fill_end:
 xor edi,edi
sw_fill_done:
 mov QWORD PTR [r12+64],rdi
 mov DWORD PTR [r12+108],r15d
 mov eax,r15d
 add rsp,40
 pop r15
 pop r14
 pop r13
 pop rdi
 ret
sw_fill ENDP

; Publish an owned opaque generation, never interpret an untrusted anchor pointer.
sw_link PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 call GetCurrentThreadId
 mov DWORD PTR [r12+16],eax
 lea rcx,sw_lock
 call AcquireSRWLockExclusive
 mov rax,QWORD PTR [sw_generation]
 test rax,rax
 jle sw_link_exhausted
 mov QWORD PTR [r12+8],rax
 inc QWORD PTR [sw_generation]
 mov rax,QWORD PTR [sw_head]
 mov QWORD PTR [r12],rax
 mov QWORD PTR [sw_head],r12
 inc QWORD PTR [boom_stack_walk_active_count]
 mov rax,QWORD PTR [boom_stack_walk_active_count]
 cmp rax,QWORD PTR [boom_stack_walk_counters+56]
 jbe sw_link_release
 mov QWORD PTR [boom_stack_walk_counters+56],rax
 jmp sw_link_release
sw_link_exhausted:
 mov DWORD PTR [rbx],20
 lock inc QWORD PTR [boom_stack_walk_counters+32]
sw_link_release:
 lea rcx,sw_lock
 call ReleaseSRWLockExclusive
 add rsp,40
 ret
sw_link ENDP

; Invalidate on all callback paths, including a pending source Throwable/stop.
sw_unlink PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 lea rcx,sw_lock
 call AcquireSRWLockExclusive
 lea rax,sw_head
sw_unlink_find:
 mov rdx,QWORD PTR [rax]
 test rdx,rdx
 jz sw_unlink_missing
 cmp rdx,r12
 je sw_unlink_found
 mov rax,rdx
 jmp sw_unlink_find
sw_unlink_found:
 mov rdx,QWORD PTR [r12]
 mov QWORD PTR [rax],rdx
 dec QWORD PTR [boom_stack_walk_active_count]
 inc QWORD PTR [boom_stack_walk_counters+48]
 mov QWORD PTR [r12+8],0
 jmp sw_unlink_release
sw_unlink_missing:
 cmp DWORD PTR [rbx],0
 jne sw_unlink_release
 mov DWORD PTR [rbx],7
sw_unlink_release:
 lea rcx,sw_lock
 call ReleaseSRWLockExclusive
 mov rax,QWORD PTR [r12+48]
 mov rdx,QWORD PTR [r12+56]
 cmp QWORD PTR [rax],rdx
 je sw_unlink_clear
 cmp DWORD PTR [rbx],0
 jne sw_unlink_clear
 mov DWORD PTR [rbx],7
sw_unlink_clear:
 mov QWORD PTR [rax],0
 add rsp,40
 ret
sw_unlink ENDP

PUBLIC boom_provider_stack_walk_service
boom_provider_stack_walk_service PROC FRAME
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
 sub rsp,288
 .allocstack 288
 .endprolog
 mov rbx,rcx
 mov rdi,rdx
 mov rsi,r8
 mov r13d,r9d
 test rbx,rbx
 jz sw_service_zero
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 call sw_valid
 test eax,eax
 jz sw_service_zero
 test r13d,r13d
 jz sw_service_check
 cmp r13d,2
 ja sw_service_bad
 test rdi,rdi
 jz sw_service_bad
 lea r12,[rsp+128]
 pxor xmm0,xmm0
 movdqu XMMWORD PTR [r12],xmm0
 movdqu XMMWORD PTR [r12+16],xmm0
 movdqu XMMWORD PTR [r12+32],xmm0
 movdqu XMMWORD PTR [r12+48],xmm0
 movdqu XMMWORD PTR [r12+64],xmm0
 movdqu XMMWORD PTR [r12+80],xmm0
 movdqu XMMWORD PTR [r12+96],xmm0
 movdqu XMMWORD PTR [r12+112],xmm0
 mov QWORD PTR [r12+24],rbx
 mov QWORD PTR [r12+112],rsi
 cmp QWORD PTR [rdi+8],SW_SUPPORTED_MODE
 jne sw_service_unsupported
 mov QWORD PTR [r12+40],SW_SUPPORTED_MODE
 mov rcx,QWORD PTR [rdi]
 mov QWORD PTR [r12+32],rcx
 call sw_receiver
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 test eax,eax
 jz sw_service_bad
 cmp r13d,2
 je sw_service_fetch

 ; callStackWalk(receiver,mode,skip,scope,cont,count,start,Class[]).
 cmp QWORD PTR [rdi+24],0
 jne sw_service_unsupported
 cmp QWORD PTR [rdi+32],0
 jne sw_service_unsupported
 mov eax,DWORD PTR [rdi+16]
 test eax,eax
 js sw_service_bad
 mov DWORD PTR [r12+96],eax
 mov edx,DWORD PTR [rdi+40]
 test edx,edx
 jle sw_service_bad
 mov DWORD PTR [r12+100],edx
 mov r8d,DWORD PTR [rdi+48]
 mov DWORD PTR [r12+104],r8d
 mov rcx,QWORD PTR [rdi+56]
 mov QWORD PTR [r12+48],rcx
 mov QWORD PTR [r12+80],rcx
 call sw_buffer
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 mov rax,QWORD PTR [r12+48]
 cmp QWORD PTR [rax],0
 jne sw_service_bad
 mov rcx,QWORD PTR [rsi+24]
 mov rdx,rbx
 call boom_trace_head
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 mov rdi,rax
 mov QWORD PTR [r12+72],rax
 call sw_node
 test rax,rax
 jz sw_service_bad
 cmp DWORD PTR [rax],SW_NATIVE_FIRST
 jne sw_service_bad
sw_service_skip_prefix:
 call sw_node
 test rax,rax
 jz sw_service_prefix_end
 mov edx,DWORD PTR [rax+20]
 xor ecx,ecx
 mov r10,QWORD PTR [rsi+72]
sw_service_skip_type:
 cmp ecx,DWORD PTR [rsi+80]
 jae sw_service_skip_frames
 cmp edx,DWORD PTR [r10+rcx*4]
 je sw_service_skip_one
 inc ecx
 jmp sw_service_skip_type
sw_service_skip_one:
 call sw_advance
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 jmp sw_service_skip_prefix
sw_service_prefix_end:
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 xor edi,edi
sw_service_skip_frames:
 mov r14d,DWORD PTR [r12+96]
sw_service_skip_loop:
 test rdi,rdi
 jz sw_service_first_fill
 test r14d,r14d
 jz sw_service_first_fill
 call sw_node
 test rax,rax
 jz sw_service_skip_end
 call sw_advance
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 dec r14d
 jmp sw_service_skip_loop
sw_service_skip_end:
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 xor edi,edi
sw_service_first_fill:
 mov QWORD PTR [r12+64],rdi
 mov r14,rdi
 call sw_fill
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 test r14,r14
 jz sw_service_first_ready
 cmp eax,DWORD PTR [r12+104]
 je sw_service_unsupported
sw_service_first_ready:
 call sw_link
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 mov rax,QWORD PTR [r12+56]
 mov rdx,QWORD PTR [r12+48]
 mov QWORD PTR [rdx],rax
 mov rax,QWORD PTR [r12+32]
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [r12+8]
 mov QWORD PTR [rsp+40],rax
 mov eax,DWORD PTR [r12+96]
 mov QWORD PTR [rsp+48],rax
 mov eax,DWORD PTR [r12+100]
 mov QWORD PTR [rsp+56],rax
 mov eax,DWORD PTR [r12+104]
 mov QWORD PTR [rsp+64],rax
 mov eax,DWORD PTR [r12+108]
 mov QWORD PTR [rsp+72],rax
 lock inc QWORD PTR [boom_stack_walk_counters+8]
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+120]
 mov QWORD PTR [r12+120],rax
 call sw_unlink
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 mov rax,QWORD PTR [r12+120]
 jmp sw_service_done

sw_service_fetch:
 ; Private fetch(receiver,mode,opaque anchor,count,start,Class[]).
 mov r14,rdi
 mov rcx,QWORD PTR [rsi+24]
 mov rdx,rbx
 call boom_trace_head
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 mov rdi,rax
 call sw_node
 test rax,rax
 jz sw_service_bad
 cmp DWORD PTR [rax],SW_NATIVE_FETCH
 jne sw_service_bad
 call GetCurrentThreadId
 mov r15d,eax
 lea rcx,sw_lock
 call AcquireSRWLockExclusive
 mov rdi,QWORD PTR [sw_head]
sw_service_find_token:
 test rdi,rdi
 jz sw_service_bad_token
 mov rax,QWORD PTR [r14+16]
 cmp QWORD PTR [rdi+8],rax
 jne sw_service_next_token
 cmp DWORD PTR [rdi+16],r15d
 jne sw_service_bad_token
 cmp QWORD PTR [rdi+24],rbx
 jne sw_service_bad_token
 cmp QWORD PTR [rdi+112],rsi
 jne sw_service_bad_token
 mov rax,QWORD PTR [r14]
 cmp QWORD PTR [rdi+32],rax
 jne sw_service_bad_token
 mov rax,QWORD PTR [r12+56]
 cmp QWORD PTR [rdi+56],rax
 jne sw_service_bad_token
 cmp QWORD PTR [rdi+40],SW_SUPPORTED_MODE
 jne sw_service_bad_token
 cmp DWORD PTR [rdi+88],0
 jne sw_service_bad_token
 mov DWORD PTR [rdi+88],1
 mov r12,rdi
 lea rcx,sw_lock
 call ReleaseSRWLockExclusive
 mov edx,DWORD PTR [r14+24]
 mov r8d,DWORD PTR [r14+32]
 mov rcx,QWORD PTR [r14+40]
 mov QWORD PTR [rsp+88],rcx
 call sw_buffer
 cmp DWORD PTR [rbx],0
 jne sw_service_fetch_finish
 mov rax,QWORD PTR [rsp+88]
 mov rdx,QWORD PTR [r12+56]
 cmp QWORD PTR [rax],rdx
 jne sw_service_fetch_bad
 mov QWORD PTR [r12+80],rax
 mov eax,DWORD PTR [r14+32]
 mov DWORD PTR [r12+104],eax
 mov DWORD PTR [r12+108],eax
 mov edx,DWORD PTR [r14+24]
 mov DWORD PTR [r12+100],edx
 test edx,edx
 jle sw_service_fetch_finish
 mov rdi,QWORD PTR [r12+64]
 test rdi,rdi
 jz sw_service_fetch_finish
 call sw_advance
 mov QWORD PTR [r12+64],rdi
 cmp DWORD PTR [rbx],0
 jne sw_service_fetch_finish
 call sw_fill
 jmp sw_service_fetch_finish
sw_service_fetch_bad:
 mov DWORD PTR [rbx],7
sw_service_fetch_finish:
 lock inc QWORD PTR [boom_stack_walk_counters+16]
 mov DWORD PTR [r12+88],0
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 mov eax,DWORD PTR [r12+108]
 jmp sw_service_done
sw_service_next_token:
 mov rdi,QWORD PTR [rdi]
 jmp sw_service_find_token
sw_service_bad_token:
 lea rcx,sw_lock
 call ReleaseSRWLockExclusive
 lock inc QWORD PTR [boom_stack_walk_counters+40]
 jmp sw_service_bad
sw_service_check:
 lock inc QWORD PTR [boom_stack_walk_counters]
 mov eax,1
 jmp sw_service_done
sw_service_unsupported:
 mov DWORD PTR [rbx],20
 lock inc QWORD PTR [boom_stack_walk_counters+32]
 jmp sw_service_zero
sw_service_bad:
 cmp DWORD PTR [rbx],0
 jne sw_service_zero
 mov DWORD PTR [rbx],7
sw_service_zero:
 xor eax,eax
sw_service_done:
 add rsp,288
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_stack_walk_service ENDP
