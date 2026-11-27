; Component owner around the ordinary source-derived VM bootstrap.
; No Java fields, class state, properties or GC root cells are written here.
; RPR precedes bootstrap; the original bootstrap opens OWAI/Parker/Signal.
option casemap:none
EXTERN boom_provider_reference_pool:BYTE
EXTERN boom_provider_reference_open:PROC
EXTERN boom_provider_reference_boundary:PROC
EXTERN boom_provider_reference_stop:PROC
EXTERN boom_provider_reference_close:PROC
EXTERN boom_provider_threads_control_binding:BYTE
EXTERN boom_vm_bootstrap_main:PROC
EXTERN boom_vm_entry_report:BYTE
EXTERN boom_vm_signal_opened:BYTE
EXTERN boom_vm_signal_closed:BYTE
EXTERN boom_provider_signal_pool:BYTE
EXTERN boom_provider_signal_close:PROC
EXTERN boom_provider_object_wait_pool:BYTE
EXTERN boom_provider_object_wait_stop:PROC
EXTERN boom_provider_object_wait_close:PROC
EXTERN boom_provider_unsafe_park_pool:BYTE
EXTERN boom_provider_unsafe_park_close:PROC
EXTERN boom_provider_threads_pool:BYTE
EXTERN boom_provider_threads_close:PROC
EXTERN boom_provider_thread_registry:BYTE
EXTERN boom_provider_thread_bind:PROC
EXTERN boom_threads_detach:PROC
EXTERN boom_threads_destroy:PROC
EXTERN GetTickCount64:PROC
EXTERN Sleep:PROC
.data
ALIGN 8
PUBLIC boom_jimage_component_owner_status
; RPR-open0D, workers-joined4D, closed8D, last cleanup status12D.
boom_jimage_component_owner_status DWORD 0,0,0,0
.code
PUBLIC boom_jimage_component_owner_open
boom_jimage_component_owner_open PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 lea rcx,boom_provider_reference_pool
 call boom_provider_reference_open
 test eax,eax
 jnz jco_failure
 mov DWORD PTR [boom_jimage_component_owner_status],1
 lea rax,boom_provider_reference_pool
 mov QWORD PTR [boom_provider_threads_control_binding+8],rax
 lea rax,boom_provider_reference_boundary
 mov QWORD PTR [boom_provider_threads_control_binding],rax
 mov rcx,rbx
 call boom_vm_bootstrap_main
 jmp jco_return
jco_failure:
 mov DWORD PTR [boom_jimage_component_owner_status+12],eax
 mov DWORD PTR [rbx],7
 xor eax,eax
jco_return:
 add rsp,32
 pop rbx
 ret
boom_jimage_component_owner_open ENDP

; Shared stop then Signal close/join, then all platform workers joined.
; Keep OWAI/Parker/RPR/main FLS alive for explicit quiescent component GC.
PUBLIC boom_jimage_component_quiesce
boom_jimage_component_quiesce PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 cmp DWORD PTR [boom_jimage_component_owner_status],0
 je jcq_success
 cmp DWORD PTR [boom_jimage_component_owner_status+4],1
 je jcq_success
 mov rcx,rbx
 lea rdx,boom_provider_reference_pool
 call boom_provider_reference_boundary
 lea rcx,boom_provider_reference_pool
 call boom_provider_reference_stop
 test eax,eax
 jnz jcq_done
 cmp DWORD PTR [boom_vm_entry_report+400],1
 jne jcq_signal
 lea rcx,boom_provider_object_wait_pool
 call boom_provider_object_wait_stop
 test eax,eax
 jnz jcq_done
jcq_signal:
 mov rcx,rbx
 lea rdx,boom_provider_signal_pool
 call boom_provider_signal_close
 test eax,eax
 jnz jcq_done
 cmp DWORD PTR [boom_vm_signal_opened],1
 jne jcq_join
 mov DWORD PTR [boom_vm_signal_closed],1
jcq_join:
 call GetTickCount64
 add rax,20000
 mov QWORD PTR [rsp+32],rax
jcq_loop:
 lea rcx,boom_provider_threads_pool
 call boom_provider_threads_close
 test eax,eax
 jz jcq_joined
 cmp eax,170
 jne jcq_done
 call GetTickCount64
 cmp rax,QWORD PTR [rsp+32]
 jae jcq_timeout
 mov ecx,1
 call Sleep
 jmp jcq_loop
jcq_timeout:
 mov eax,170
 jmp jcq_done
jcq_joined:
 mov DWORD PTR [boom_jimage_component_owner_status+4],1
jcq_success:
 xor eax,eax
jcq_done:
 mov DWORD PTR [boom_jimage_component_owner_status+12],eax
 add rsp,48
 pop rbx
 ret
boom_jimage_component_quiesce ENDP

; Java calls have ended. Never free a wait/gate/root owner before worker join.
PUBLIC boom_jimage_component_owner_close
boom_jimage_component_owner_close PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 cmp DWORD PTR [boom_jimage_component_owner_status+8],1
 je jcc_success
 cmp DWORD PTR [boom_jimage_component_owner_status],0
 je jcc_success
 call boom_jimage_component_quiesce
 test eax,eax
 jnz jcc_done
 cmp DWORD PTR [boom_vm_entry_report+448],1
 jne jcc_wait
 lea rcx,boom_provider_unsafe_park_pool
 call boom_provider_unsafe_park_close
 test eax,eax
 jnz jcc_done
 mov DWORD PTR [boom_vm_entry_report+452],1
jcc_wait:
 cmp DWORD PTR [boom_vm_entry_report+400],1
 jne jcc_reference
 lea rcx,boom_provider_object_wait_pool
 call boom_provider_object_wait_close
 test eax,eax
 jnz jcc_done
 mov DWORD PTR [boom_vm_entry_report+408],1
jcc_reference:
 lea rcx,boom_provider_reference_pool
 call boom_provider_reference_close
 test eax,eax
 jnz jcc_done
 mov QWORD PTR [boom_provider_threads_control_binding],0
 mov QWORD PTR [boom_provider_threads_control_binding+8],0
 mov rsi,QWORD PTR [boom_provider_thread_registry]
 test rsi,rsi
 jz jcc_closed
 mov rcx,rsi
 call boom_threads_detach
 test eax,eax
 jnz jcc_done
 xor ecx,ecx
 call boom_provider_thread_bind
 test eax,eax
 jnz jcc_done
 mov rcx,rsi
 call boom_threads_destroy
 test eax,eax
 jnz jcc_done
jcc_closed:
 mov DWORD PTR [boom_jimage_component_owner_status+8],1
jcc_success:
 xor eax,eax
jcc_done:
 mov DWORD PTR [boom_jimage_component_owner_status+12],eax
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_jimage_component_owner_close ENDP
END
