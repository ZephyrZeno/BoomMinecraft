; Shadow owned Unsafe services. Generated normal receiver prefixes and ABI EQUs
; are inserted by unsafe-owned-memory-service-source.py. No Java oop is stored.
.data
ALIGN 8
PUBLIC boom_provider_owned_unsafe_pool
; UOWN32/1: magic0D,abi4D,Owner8Q,state16D,bytes20D,reserved24Q.
boom_provider_owned_unsafe_pool DWORD 04E574F55h,1
 QWORD 0
 DWORD 0,32
 QWORD 0
PUBLIC boom_owned_unsafe_counters
; normal calls,typed calls,busy retries,timeouts,release failures,RO fallbacks.
boom_owned_unsafe_counters QWORD 6 DUP(0)
.code

; Startup only, before Java; the same live Owner storage outlives every user.
PUBLIC boom_provider_owned_unsafe_bind
boom_provider_owned_unsafe_bind PROC
 mov eax,87
 lea r10,boom_provider_owned_unsafe_pool
 cmp DWORD PTR [r10],04E574F55h
 jne uob_return
 cmp DWORD PTR [r10+4],1
 jne uob_return
 cmp DWORD PTR [r10+20],32
 jne uob_return
 cmp QWORD PTR [r10+24],0
 jne uob_return
 cmp DWORD PTR [r10+16],2
 ja uob_return
 test rcx,rcx
 jz uob_return
 test cl,7
 jnz uob_return
 mov rdx,UOM_OWNER_MAGIC
 cmp QWORD PTR [rcx],rdx
 jne uob_return
 cmp DWORD PTR [rcx+8],128
 jne uob_return
 cmp DWORD PTR [rcx+12],1
 jne uob_return
 cmp DWORD PTR [rcx+24],1
 jne uob_return
 lea rdx,boom_provider_owned_unsafe_pool
 cmp DWORD PTR [rdx+16],1
 jne uob_publish
 mov eax,170
 cmp QWORD PTR [rdx+8],rcx
 jne uob_return
 xor eax,eax
 ret
uob_publish:
 mov QWORD PTR [rdx+8],rcx
 mov DWORD PTR [rdx+16],1
 xor eax,eax
uob_return:
 ret
boom_provider_owned_unsafe_bind ENDP

; After real core close and after all users. Never discard a live owner.
PUBLIC boom_provider_owned_unsafe_unbind
boom_provider_owned_unsafe_unbind PROC
 lea rdx,boom_provider_owned_unsafe_pool
 mov eax,87
 cmp DWORD PTR [rdx],04E574F55h
 jne uou_return
 cmp DWORD PTR [rdx+4],1
 jne uou_return
 cmp DWORD PTR [rdx+20],32
 jne uou_return
 cmp QWORD PTR [rdx+24],0
 jne uou_return
 cmp DWORD PTR [rdx+16],2
 ja uou_return
 xor eax,eax
 cmp DWORD PTR [rdx+16],1
 jne uou_return
 mov rcx,QWORD PTR [rdx+8]
 mov eax,170
 test rcx,rcx
 jz uou_return
 cmp DWORD PTR [rcx+24],3
 jne uou_return
 cmp QWORD PTR [rcx+32],0
 jne uou_return
 cmp QWORD PTR [rcx+40],0
 jne uou_return
 mov QWORD PTR [rdx+8],0
 mov DWORD PTR [rdx+16],2
 xor eax,eax
uou_return:
 ret
boom_provider_owned_unsafe_unbind ENDP

; (Job128*) -> real status. Core releases its lock before returning busy2.
; No Context is cleared, no lock is held across Sleep, no VM-stop token forged.
uom_retry_job PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 call GetTickCount64
 mov rsi,rax
uor_again:
 mov rcx,rbx
 call boom_native_memory_service
 cmp eax,2
 jne uor_done
 lock inc QWORD PTR [boom_owned_unsafe_counters+16]
 call GetTickCount64
 sub rax,rsi
 cmp rax,UOM_BUSY_MILLISECONDS
 jae uor_timeout
 mov ecx,1
 call Sleep
 jmp uor_again
uor_timeout:
 lock inc QWORD PTR [boom_owned_unsafe_counters+24]
 mov eax,2
uor_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
uom_retry_job ENDP

; (src,dst,bytes). Endpoints are already held/validated. Coherent unit width is
; the largest 8/4/2/1 alignment shared by both addresses and the byte count.
uom_copy_bytes PROC PRIVATE
 test r8,r8
 jz ucb_done
 cmp rcx,rdx
 je ucb_done
 mov r10,rcx
 mov r11,rdx
 mov rax,rcx
 or rax,rdx
 or rax,r8
 mov r9d,8
 test eax,7
 jz ucb_direction
 mov r9d,4
 test eax,3
 jz ucb_direction
 mov r9d,2
 test eax,1
 jz ucb_direction
 mov r9d,1
ucb_direction:
 cmp r11,r10
 jbe ucb_forward
 lea rax,[r10+r8]
 cmp r11,rax
 jae ucb_forward
 add r10,r8
 add r11,r8
ucb_backward:
 sub r10,r9
 sub r11,r9
 cmp r9d,8
 je ucb_back8
 cmp r9d,4
 je ucb_back4
 cmp r9d,2
 je ucb_back2
 mov al,BYTE PTR [r10]
 mov BYTE PTR [r11],al
 jmp ucb_back_next
ucb_back2:
 mov ax,WORD PTR [r10]
 mov WORD PTR [r11],ax
 jmp ucb_back_next
ucb_back4:
 mov eax,DWORD PTR [r10]
 mov DWORD PTR [r11],eax
 jmp ucb_back_next
ucb_back8:
 mov rax,QWORD PTR [r10]
 mov QWORD PTR [r11],rax
ucb_back_next:
 sub r8,r9
 jnz ucb_backward
 ret
ucb_forward:
 cmp r9d,8
 je ucb_forward8
 cmp r9d,4
 je ucb_forward4
 cmp r9d,2
 je ucb_forward2
 mov al,BYTE PTR [r10]
 mov BYTE PTR [r11],al
 jmp ucb_next
ucb_forward2:
 mov ax,WORD PTR [r10]
 mov WORD PTR [r11],ax
 jmp ucb_next
ucb_forward4:
 mov eax,DWORD PTR [r10]
 mov DWORD PTR [r11],eax
 jmp ucb_next
ucb_forward8:
 mov rax,QWORD PTR [r10]
 mov QWORD PTR [r11],rax
ucb_next:
 add r10,r9
 add r11,r9
 sub r8,r9
 jnz ucb_forward
ucb_done:
 ret
uom_copy_bytes ENDP

; (src,dst,bytes,elementWidth2/4/8), including exact in-place element reversal.
uom_swap_bytes PROC PRIVATE
 test r8,r8
 jz usb_done
 mov r10,rcx
 mov r11,rdx
 cmp r11,r10
 jbe usb_forward
 lea rax,[r10+r8]
 cmp r11,rax
 jae usb_forward
 add r10,r8
 add r11,r8
usb_backward:
 sub r10,r9
 sub r11,r9
 cmp r9d,8
 je usb_back8
 cmp r9d,4
 je usb_back4
 mov ax,WORD PTR [r10]
 rol ax,8
 mov WORD PTR [r11],ax
 jmp usb_back_next
usb_back4:
 mov eax,DWORD PTR [r10]
 bswap eax
 mov DWORD PTR [r11],eax
 jmp usb_back_next
usb_back8:
 mov rax,QWORD PTR [r10]
 bswap rax
 mov QWORD PTR [r11],rax
usb_back_next:
 sub r8,r9
 jnz usb_backward
 ret
usb_forward:
 cmp r9d,8
 je usb_forward8
 cmp r9d,4
 je usb_forward4
 mov ax,WORD PTR [r10]
 rol ax,8
 mov WORD PTR [r11],ax
 jmp usb_next
usb_forward4:
 mov eax,DWORD PTR [r10]
 bswap eax
 mov DWORD PTR [r11],eax
 jmp usb_next
usb_forward8:
 mov rax,QWORD PTR [r10]
 bswap rax
 mov QWORD PTR [r11],rax
usb_next:
 add r10,r9
 add r11,r9
 sub r8,r9
 jnz usb_forward
usb_done:
 ret
uom_swap_bytes ENDP

; Normal six-native service ABI is independent of the core Job ABI.
PUBLIC boom_provider_owned_unsafe_service
boom_provider_owned_unsafe_service PROC
 test rcx,rcx
 jz uom_gate_zero
 cmp DWORD PTR [rcx],0
 jne uom_gate_zero
 test rdx,rdx
 jz uom_gate_bad
 lea rax,boom_provider_owned_unsafe_pool
 cmp r8,rax
 jne uom_gate_bad
 cmp DWORD PTR [r8],04E574F55h
 jne uom_gate_bad
 cmp DWORD PTR [r8+4],1
 jne uom_gate_bad
 cmp DWORD PTR [r8+20],32
 jne uom_gate_bad
 cmp QWORD PTR [r8+24],0
 jne uom_gate_bad
 cmp DWORD PTR [r8+16],2
 ja uom_gate_bad
 cmp r9d,5
 ja uom_gate_bad
 jmp uom_validated_native
uom_gate_bad:
 mov DWORD PTR [rcx],7
uom_gate_zero:
 xor eax,eax
 ret
boom_provider_owned_unsafe_service ENDP

uom_validated_native PROC PRIVATE FRAME
;@NATIVE_RECEIVER_PREFIX@
 lock inc QWORD PTR [boom_owned_unsafe_counters]
 mov QWORD PTR [rsp+304],0
 mov QWORD PTR [rsp+312],0
 mov esi,DWORD PTR [rsp+288]
 cmp esi,3
 je uom_set
 ja uom_copy
 UOM_CLEAR_JOB 32
 call uom_owner
 mov r14,rax
 test r14,r14
 jz uom_unbound
 mov QWORD PTR [rsp+32+UOMJ_OWNER],r14
 mov DWORD PTR [rsp+32+UOMJ_OP],esi
 mov rax,QWORD PTR [r12+8]
 test esi,esi
 jnz uom_address_op
 mov QWORD PTR [rsp+32+UOMJ_BYTES],rax
 jmp uom_alloc_call
uom_address_op:
 mov QWORD PTR [rsp+32+UOMJ_ADDRESS],rax
 cmp esi,1
 jne uom_free_call
 mov rax,QWORD PTR [r12+16]
 mov QWORD PTR [rsp+32+UOMJ_BYTES],rax
uom_alloc_call:
 lea rcx,[rsp+32]
 call uom_retry_job
 test eax,eax
 jz uom_result
 cmp eax,4
 je uom_zero
 cmp eax,7
 je uom_zero
 jmp uom_core_error
uom_free_call:
 lea rcx,[rsp+32]
 call uom_retry_job
 test eax,eax
 jnz uom_core_error
 jmp uom_zero
uom_result:
 mov rax,QWORD PTR [rsp+32+UOMJ_RESULT]
 jmp uom_done

uom_set:
 mov r15,QWORD PTR [r12+24]
 test r15,r15
 js uom_bad
 mov rdx,QWORD PTR [r12+8]
 test rdx,rdx
 jz uom_set_native
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov r8,QWORD PTR [r12+16]
 mov r9,r15
 lea rax,[rsp+320]
 mov QWORD PTR [rsp+32],rax
 call boom_primitive_heap_span
 test eax,eax
 jnz uom_bad
 mov rdi,QWORD PTR [rsp+320]
 mov rax,QWORD PTR [r12+32]
 and eax,255
 mov rdx,0101010101010101h
 imul rax,rdx
 mov rcx,r15
 mov rdx,rdi
 or rdx,rcx
 test edx,7
 jz uom_fill8
 test edx,3
 jz uom_fill4
 test edx,1
 jz uom_fill2
 rep stosb
 jmp uom_zero
uom_fill2:
 shr rcx,1
 rep stosw
 jmp uom_zero
uom_fill4:
 shr rcx,2
 rep stosd
 jmp uom_zero
uom_fill8:
 shr rcx,3
 rep stosq
 jmp uom_zero
uom_set_native:
 UOM_CLEAR_JOB 32
 call uom_owner
 mov r14,rax
 test r14,r14
 jz uom_unbound
 mov QWORD PTR [rsp+32+UOMJ_OWNER],r14
 mov rax,QWORD PTR [r12+16]
 mov QWORD PTR [rsp+32+UOMJ_ADDRESS],rax
 mov QWORD PTR [rsp+32+UOMJ_BYTES],r15
 mov rax,QWORD PTR [r12+32]
 mov QWORD PTR [rsp+32+UOMJ_VALUE],rax
 mov DWORD PTR [rsp+32+UOMJ_OP],5
 lea rcx,[rsp+32]
 call uom_retry_job
 test eax,eax
 jnz uom_core_error
 jmp uom_zero

uom_copy:
 mov r15,QWORD PTR [r12+40]
 test r15,r15
 js uom_bad
 xor ebp,ebp
 cmp esi,5
 jne uom_copy_width_ok
 mov rbp,QWORD PTR [r12+48]
 cmp rbp,2
 je uom_swap_width_ok
 cmp rbp,4
 je uom_swap_width_ok
 cmp rbp,8
 jne uom_bad
uom_swap_width_ok:
 lea rax,[rbp-1]
 test rax,r15
 jnz uom_bad
uom_copy_width_ok:
 mov rdx,QWORD PTR [r12+8]
 test rdx,rdx
 jz uom_copy_source_native
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov r8,QWORD PTR [r12+16]
 mov r9,r15
 lea rax,[rsp+320]
 mov QWORD PTR [rsp+32],rax
 call boom_primitive_heap_span
 test eax,eax
 jnz uom_bad
 mov rsi,QWORD PTR [rsp+320]
 cmp QWORD PTR [r12+24],0
 je uom_heap_to_native
 jmp uom_validate_destination_heap
uom_copy_source_native:
 cmp QWORD PTR [r12+24],0
 je uom_native_to_native
 xor esi,esi
uom_validate_destination_heap:
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [r12+24]
 mov r8,QWORD PTR [r12+32]
 mov r9,r15
 lea rax,[rsp+320]
 mov QWORD PTR [rsp+32],rax
 call boom_primitive_heap_span
 test eax,eax
 jnz uom_bad
 mov rdi,QWORD PTR [rsp+320]
 cmp QWORD PTR [r12+8],0
 jne uom_copy_external
 UOM_CLEAR_JOB 32
 call uom_owner
 mov r14,rax
 test r14,r14
 jz uom_try_RO_copy
 mov QWORD PTR [rsp+32+UOMJ_OWNER],r14
 mov rax,QWORD PTR [r12+16]
 mov QWORD PTR [rsp+32+UOMJ_ADDRESS],rax
 mov QWORD PTR [rsp+32+UOMJ_BYTES],r15
 mov DWORD PTR [rsp+32+UOMJ_FLAGS],1
 mov DWORD PTR [rsp+32+UOMJ_OP],8
 lea rcx,[rsp+32]
 call uom_retry_job
 cmp eax,1
 je uom_try_RO_copy
 cmp eax,9
 je uom_try_RO_copy
 test eax,eax
 jnz uom_core_error
 mov rsi,QWORD PTR [rsp+32+UOMJ_RESULT]
 jmp uom_borrowed
uom_heap_to_native:
 UOM_CLEAR_JOB 32
 call uom_owner
 mov r14,rax
 test r14,r14
 jz uom_unbound
 mov QWORD PTR [rsp+32+UOMJ_OWNER],r14
 mov rax,QWORD PTR [r12+32]
 mov QWORD PTR [rsp+32+UOMJ_ADDRESS],rax
 mov QWORD PTR [rsp+32+UOMJ_BYTES],r15
 mov DWORD PTR [rsp+32+UOMJ_FLAGS],2
 mov DWORD PTR [rsp+32+UOMJ_OP],8
 lea rcx,[rsp+32]
 call uom_retry_job
 test eax,eax
 jnz uom_core_error
 mov rdi,QWORD PTR [rsp+32+UOMJ_RESULT]
uom_borrowed:
 mov rax,QWORD PTR [rsp+32+UOMJ_TOKEN]
 mov QWORD PTR [rsp+304],rax
uom_copy_external:
 mov rcx,rsi
 mov rdx,rdi
 mov r8,r15
 test ebp,ebp
 jz uom_copy_plain
 mov r9d,ebp
 call uom_swap_bytes
 jmp uom_release
uom_copy_plain:
 call uom_copy_bytes
uom_release:
 cmp QWORD PTR [rsp+304],0
 je uom_zero
 UOM_CLEAR_JOB 32
 mov QWORD PTR [rsp+32+UOMJ_OWNER],r14
 mov rax,QWORD PTR [rsp+304]
 mov QWORD PTR [rsp+32+UOMJ_TOKEN],rax
 mov DWORD PTR [rsp+32+UOMJ_OP],9
 lea rcx,[rsp+32]
 call uom_retry_job
 test eax,eax
 jz uom_zero
 lock inc QWORD PTR [boom_owned_unsafe_counters+32]
 jmp uom_unbound
uom_native_to_native:
 UOM_CLEAR_JOB 32
 call uom_owner
 mov r14,rax
 test r14,r14
 jz uom_unbound
 mov QWORD PTR [rsp+32+UOMJ_OWNER],r14
 mov rax,QWORD PTR [r12+16]
 mov QWORD PTR [rsp+32+UOMJ_ADDRESS],rax
 mov rax,QWORD PTR [r12+32]
 mov QWORD PTR [rsp+32+UOMJ_OTHER],rax
 mov QWORD PTR [rsp+32+UOMJ_BYTES],r15
 mov DWORD PTR [rsp+32+UOMJ_WIDTH],ebp
 mov eax,6
 test ebp,ebp
 jz uom_core_copy_op
 mov eax,7
uom_core_copy_op:
 mov DWORD PTR [rsp+32+UOMJ_OP],eax
 lea rcx,[rsp+32]
 call uom_retry_job
 test eax,eax
 jnz uom_core_error
 jmp uom_zero
uom_try_RO_copy:
 test ebp,ebp
 jnz uom_unbound
 lock inc QWORD PTR [boom_owned_unsafe_counters+40]
 mov rcx,rbx
 mov rdx,r12
 mov r8,r13
 xor r9d,r9d
 UOM_UNWIND 328
 jmp boom_provider_jimage_copy_service
uom_core_error:
 cmp eax,3
 je uom_bad
 cmp eax,5
 je uom_bad
uom_unbound:
 mov DWORD PTR [rbx],20
 jmp uom_zero
uom_null:
 mov DWORD PTR [rbx],4
 jmp uom_zero
uom_bad:
 mov DWORD PTR [rbx],7
uom_zero:
 xor eax,eax
uom_done:
 UOM_UNWIND 328
 ret
uom_validated_native ENDP

; Private same-frame helper: Owner pointer only, no status or Context mutation.
uom_owner PROC PRIVATE
 lea r10,boom_provider_owned_unsafe_pool
 xor eax,eax
 cmp DWORD PTR [r10],04E574F55h
 jne uoo_done
 cmp DWORD PTR [r10+4],1
 jne uoo_done
 cmp DWORD PTR [r10+20],32
 jne uoo_done
 cmp QWORD PTR [r10+24],0
 jne uoo_done
 cmp DWORD PTR [r10+16],1
 jne uoo_done
 mov rax,QWORD PTR [r10+8]
uoo_done:
 ret
uom_owner ENDP

; New plain null-base domain; every other original typed route stays original.
PUBLIC boom_java_unsafe_owned_domains
boom_java_unsafe_owned_domains PROC
 test rcx,rcx
 jz uot_gate_old
 cmp DWORD PTR [rcx],0
 jne uot_gate_old
 test rdx,rdx
 jz uot_gate_old
 cmp QWORD PTR [rdx+8],0
 jne uot_gate_old
 mov eax,r9d
 shr eax,4
 cmp eax,1
 ja uot_gate_old
 mov eax,r9d
 and eax,15
 dec eax
 cmp eax,7
 ja uot_gate_old
 jmp uot_validated
uot_gate_old:
 jmp boom_java_unsafe_jimage_memory
boom_java_unsafe_owned_domains ENDP

uot_validated PROC PRIVATE FRAME
;@TYPED_RECEIVER_PREFIX@
 lock inc QWORD PTR [boom_owned_unsafe_counters+8]
 ; Preserve the exact live ThreadIdentifiers Long-load domain even if the
 ; independent RW owner is closed. The original DLL revalidates under its lock.
 cmp r14d,6
 jne uot_owner
 test r15d,r15d
 jnz uot_owner
 mov rcx,QWORD PTR [boom_provider_thread_registry]
 call boom_threads_id_address
 test rax,rax
 jz uot_owner
 cmp rax,QWORD PTR [r12+16]
 je uot_old
uot_owner:
 call uom_owner
 mov rsi,rax
 test rsi,rsi
 jz uot_old
 UOM_CLEAR_JOB 32
 mov QWORD PTR [rsp+32+UOMJ_OWNER],rsi
 mov rax,QWORD PTR [r12+16]
 mov QWORD PTR [rsp+32+UOMJ_ADDRESS],rax
 mov QWORD PTR [rsp+32+UOMJ_BYTES],rbp
 mov DWORD PTR [rsp+32+UOMJ_WIDTH],ebp
 mov eax,3
 test r15d,r15d
 jz uot_op_ready
 mov eax,4
 mov rdx,QWORD PTR [r12+24]
 cmp r14d,1
 jne uot_value_ready
 and edx,1
uot_value_ready:
 mov QWORD PTR [rsp+32+UOMJ_VALUE],rdx
uot_op_ready:
 mov DWORD PTR [rsp+32+UOMJ_OP],eax
 lea rcx,[rsp+32]
 call uom_retry_job
 cmp eax,1
 je uot_old
 cmp eax,9
 je uot_old
 test eax,eax
 jnz uot_core_error
 test r15d,r15d
 jnz uot_zero
 mov rax,QWORD PTR [rsp+32+UOMJ_RESULT]
 cmp r14d,1
 je uot_boolean
 cmp r14d,2
 je uot_byte
 cmp r14d,4
 je uot_short
 cmp r14d,5
 jne uot_done
 movsxd rax,eax
 jmp uot_done
uot_boolean:
 test eax,eax
 setne al
 movzx eax,al
 jmp uot_done
uot_byte:
 movsx rax,al
 jmp uot_done
uot_short:
 movsx rax,ax
 jmp uot_done
uot_old:
 mov rcx,rbx
 mov rdx,r12
 mov r8,r13
 mov r9d,r15d
 shl r9d,4
 or r9d,r14d
 UOM_UNWIND 328
 jmp boom_java_unsafe_jimage_memory
uot_core_error:
 cmp eax,3
 je uot_bad
 cmp eax,5
 je uot_bad
uot_unbound:
 mov DWORD PTR [rbx],20
 jmp uot_zero
uot_null:
 mov DWORD PTR [rbx],4
 jmp uot_zero
uot_bad:
 mov DWORD PTR [rbx],7
uot_zero:
 xor eax,eax
uot_done:
 UOM_UNWIND 328
 ret
uot_validated ENDP
