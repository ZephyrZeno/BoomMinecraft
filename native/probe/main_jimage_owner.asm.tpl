; Source-derived pure MASM process resource owner.
; New process-lifetime native owner. No Java fields/class states/root cells written.
; Prepare precedes ALL Java. Unload runs after all workers joined, with registry,
; literal roots, trace frames and heap alive. Resources close only after heap free.
option casemap:none
EXTERN boom_jimage_owner_init:PROC
EXTERN boom_jimage_owner_open:PROC
EXTERN boom_jimage_owner_release:PROC
EXTERN boom_jimage_owner_close:PROC
EXTERN boom_jimage_native_map_open:PROC
EXTERN boom_jimage_native_map_ready:PROC
EXTERN boom_jimage_native_map_close:PROC
EXTERN boom_provider_jimage_native_map_pool:BYTE
EXTERN boom_native_library_modules:BYTE
EXTERN boom_jimage_library_module:BYTE
EXTERN boom_native_library_pins:QWORD
EXTERN boom_provider_thread_registry:QWORD
EXTERN boom_java_string_literal_pool:BYTE
EXTERN boom_java_string_literal:PROC
EXTERN boom_trace_head:PROC
EXTERN boom_trace_pool:BYTE
EXTERN @UNLOAD_SYMBOL@:PROC
EXTERN CreateFileW:PROC
EXTERN WriteFile:PROC
EXTERN CloseHandle:PROC
EXTERN GetLastError:PROC
.const
ALIGN 2
PUBLIC boom_main_jimage_modules_key
boom_main_jimage_modules_key LABEL WORD
@MODULE_KEY_WORDS@
 WORD 0
ALIGN 8
; Module64 pointers and ORIGINAL source literal IDs, no synthetic Java receiver.
mj_module_rows QWORD OFFSET boom_jimage_library_module
 DWORD @JIMAGE_LITERAL@,3
 QWORD OFFSET boom_native_library_modules+64
 DWORD @NIO_LITERAL@,2
 QWORD OFFSET boom_native_library_modules
 DWORD @NET_LITERAL@,1
mj_report_name WORD 109,97,105,110,45,106,105,109,97,103,101,45,115,116,97,116,117,115,46,98,105,110,0
.data
ALIGN 8
PUBLIC boom_main_jimage_report
; 256/1: magic0D,ABI4D,bytes8D,lifecycleFlags12D (init1,map2,bridge4,
; pinsUnloaded8,resourcesClosed16); prepare16D,unload20D,bridgeClose24D,
; bootstrapRelease28D,ownerClose32D,originalContextPreserved36D;
; unloadCalls40Q,pinsBefore48Q,pinsAfter56Q,ownerLeasesBefore64Q,
; ownerLeasesAfter72Q,bridgeNodesBefore80Q,bridgeNodesAfter88Q,
; bridgeLeasesBefore96Q,bridgeLeasesAfter104Q,files112Q,maps120Q;
; original Context32 snapshot128,independent cleanup Context32@160;
; bootstrap view192Q,length200Q; reserved208..255. No Java oop root bank.
boom_main_jimage_report DWORD 04F4D494Ah,1,256,0
 DWORD 0FFFFFFFFh,0FFFFFFFFh,0FFFFFFFFh,0FFFFFFFFh
 DWORD 0FFFFFFFFh,0
 QWORD 11 DUP(0)
 QWORD 4 DUP(0)
 QWORD 4 DUP(0)
 QWORD 0,0
 BYTE 48 DUP(0)
.data?
ALIGN 8
PUBLIC boom_main_jimage_owner
boom_main_jimage_owner BYTE 128 DUP(?)
mj_bootstrap_job QWORD 8 DUP(?)
mj_release_job QWORD 8 DUP(?)
mj_report_written DWORD ?
.code

PUBLIC boom_main_jimage_prepare
boom_main_jimage_prepare PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 test DWORD PTR [boom_main_jimage_report+12],4
 jnz mjp_ready
 cmp DWORD PTR [boom_main_jimage_report+12],0
 jne mjp_bad
 lea rcx,boom_main_jimage_owner
 mov edx,128
 mov r8d,32
 call boom_jimage_owner_init
 test eax,eax
 jnz mjp_failure
 or DWORD PTR [boom_main_jimage_report+12],1
 lea rax,boom_main_jimage_owner
 mov QWORD PTR [mj_bootstrap_job],rax
 lea rax,boom_main_jimage_modules_key
 mov QWORD PTR [mj_bootstrap_job+8],rax
 mov QWORD PTR [mj_bootstrap_job+16],@MODULE_UNITS@
 mov QWORD PTR [mj_bootstrap_job+56],@MODULE_BYTES@
 lea rcx,mj_bootstrap_job
 call boom_jimage_owner_open
 test eax,eax
 jnz mjp_failure
 or DWORD PTR [boom_main_jimage_report+12],2
 mov rax,QWORD PTR [mj_bootstrap_job+32]
 mov QWORD PTR [boom_main_jimage_report+192],rax
 mov rax,QWORD PTR [mj_bootstrap_job+40]
 mov QWORD PTR [boom_main_jimage_report+200],rax
 lea rcx,boom_provider_jimage_native_map_pool
 lea rdx,boom_main_jimage_owner
 call boom_jimage_native_map_open
 test eax,eax
 jnz mjp_failure
 or DWORD PTR [boom_main_jimage_report+12],4
mjp_ready:
 lea rcx,boom_provider_jimage_native_map_pool
 call boom_jimage_native_map_ready
 test eax,eax
 jnz mjp_failure
 mov DWORD PTR [boom_main_jimage_report+16],0
 xor eax,eax
 jmp mjp_done
mjp_bad:
 mov eax,87
mjp_failure:
 mov ebx,eax
 mov DWORD PTR [boom_main_jimage_report+16],eax
 ; No Java has run. Roll back only this newly owned native mapping/lease.
 call boom_main_jimage_resources_close
 mov eax,ebx
mjp_done:
 add rsp,32
 pop rbx
 ret
boom_main_jimage_prepare ENDP

PUBLIC boom_main_jimage_unload_modules
boom_main_jimage_unload_modules PROC FRAME
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
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 test rbx,rbx
 jz mju_bad
 ; The original diagnostic/pending exception Context is a read-only input.
 xor ecx,ecx
mju_save_context:
 mov rax,QWORD PTR [rbx+rcx*8]
 lea r10,boom_main_jimage_report+128
 mov QWORD PTR [r10+rcx*8],rax
 inc ecx
 cmp ecx,4
 jb mju_save_context
 mov rax,QWORD PTR [boom_native_library_pins]
 mov QWORD PTR [boom_main_jimage_report+48],rax
 mov rax,QWORD PTR [boom_main_jimage_owner+56]
 mov QWORD PTR [boom_main_jimage_report+64],rax
 mov rax,QWORD PTR [boom_provider_jimage_native_map_pool+40]
 mov QWORD PTR [boom_main_jimage_report+80],rax
 mov rax,QWORD PTR [boom_provider_jimage_native_map_pool+48]
 mov QWORD PTR [boom_main_jimage_report+96],rax
 test DWORD PTR [boom_main_jimage_report+12],8
 jnz mju_success
 cmp DWORD PTR [boom_main_jimage_report+160],0
 jne mju_unsupported
 xor edi,edi
 mov DWORD PTR [rsp+60],0
mju_next_module:
 cmp edi,3
 jae mju_check_pins
 mov eax,edi
 shl eax,4
 lea r12,mj_module_rows
 add r12,rax
 mov rsi,QWORD PTR [r12]
mju_module_again:
 cmp QWORD PTR [rsi+16],0
 jne mju_has_pin
 ; Cold rows can be skipped without any Java call or registry requirement.
 cmp DWORD PTR [rsi+12],0
 jne mju_busy
 cmp DWORD PTR [rsi+24],0
 jne mju_busy
 cmp DWORD PTR [rsi+28],0
 jne mju_busy
 inc edi
 jmp mju_next_module
mju_has_pin:
 cmp DWORD PTR [rsi],0444F4D42h
 jne mju_bad
 cmp DWORD PTR [rsi+4],1
 jne mju_bad
 mov eax,DWORD PTR [rsi+28]
 cmp eax,1
 je mju_ready_refs
 cmp eax,2
 jne mju_busy
 jmp mju_validate_owners
mju_ready_refs:
 cmp DWORD PTR [rsi+12],1
 jb mju_bad
mju_validate_owners:
 mov rax,QWORD PTR [boom_provider_thread_registry]
 test rax,rax
 jz mju_busy
 ; The standard entry has joined platform/signal workers. Reject any
 ; independently attached thread still borrowing this same registry.
 cmp DWORD PTR [rax+24],1
 jne mju_busy
 lea rcx,boom_trace_pool
 lea rdx,boom_main_jimage_report+160
 call boom_trace_head
 cmp DWORD PTR [boom_main_jimage_report+160],0
 jne mju_unsupported
 test rax,rax
 jnz mju_busy
 inc DWORD PTR [rsp+60]
 cmp DWORD PTR [rsp+60],65536
 ja mju_busy
 lea rcx,boom_main_jimage_report+160
 lea rdx,boom_java_string_literal_pool
 mov r8d,DWORD PTR [r12+8]
 call boom_java_string_literal
 cmp DWORD PTR [boom_main_jimage_report+160],0
 jne mju_unsupported
 test rax,rax
 jz mju_bad
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],1
 mov rax,QWORD PTR [rsi+16]
 mov QWORD PTR [rsp+48],rax
 mov r13d,DWORD PTR [rsi+12]
 lea rcx,boom_main_jimage_report+160
 lea rdx,[rsp+32]
 ; Actual original unload adapter enters its normal source native Frame8.
 ; Literal creation uses the original source bank and ordinary ASM factory.
 call @UNLOAD_SYMBOL@
 inc QWORD PTR [boom_main_jimage_report+40]
 cmp DWORD PTR [boom_main_jimage_report+160],0
 jne mju_unsupported
 cmp QWORD PTR [rsi+16],0
 je mju_module_again
 cmp DWORD PTR [rsi+12],r13d
 jae mju_busy
 jmp mju_module_again
mju_check_pins:
 cmp QWORD PTR [boom_native_library_pins],0
 jne mju_busy
 or DWORD PTR [boom_main_jimage_report+12],8
mju_success:
 xor edx,edx
 jmp mju_compare_context
mju_busy:
 mov edx,170
 jmp mju_compare_context
mju_unsupported:
 mov edx,20
 jmp mju_compare_context
mju_bad:
 mov edx,87
mju_compare_context:
 test rbx,rbx
 jz mju_context_failed
 xor ecx,ecx
mju_compare_qword:
 mov rax,QWORD PTR [rbx+rcx*8]
 lea r10,boom_main_jimage_report+128
 cmp rax,QWORD PTR [r10+rcx*8]
 jne mju_context_failed
 inc ecx
 cmp ecx,4
 jb mju_compare_qword
 mov DWORD PTR [boom_main_jimage_report+36],1
 jmp mju_capture
mju_context_failed:
 mov DWORD PTR [boom_main_jimage_report+36],0
 mov edx,87
mju_capture:
 mov DWORD PTR [boom_main_jimage_report+20],edx
 mov rax,QWORD PTR [boom_native_library_pins]
 mov QWORD PTR [boom_main_jimage_report+56],rax
 mov eax,edx
 add rsp,64
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_main_jimage_unload_modules ENDP

PUBLIC boom_main_jimage_resources_close
boom_main_jimage_resources_close PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 test DWORD PTR [boom_main_jimage_report+12],16
 jnz mjc_success
 test DWORD PTR [boom_main_jimage_report+12],4
 jz mjc_bootstrap
 cmp DWORD PTR [boom_main_jimage_report+24],0
 je mjc_bootstrap
 lea rcx,boom_provider_jimage_native_map_pool
 call boom_jimage_native_map_close
 mov DWORD PTR [boom_main_jimage_report+24],eax
 test eax,eax
 jnz mjc_done
mjc_bootstrap:
 test DWORD PTR [boom_main_jimage_report+12],2
 jz mjc_owner
 cmp DWORD PTR [boom_main_jimage_report+28],0
 je mjc_owner
 lea rax,boom_main_jimage_owner
 mov QWORD PTR [mj_release_job],rax
 mov rax,QWORD PTR [mj_bootstrap_job+24]
 test rax,rax
 jz mjc_bad
 mov QWORD PTR [mj_release_job+24],rax
 lea rcx,mj_release_job
 call boom_jimage_owner_release
 mov DWORD PTR [boom_main_jimage_report+28],eax
 test eax,eax
 jnz mjc_done
 mov QWORD PTR [mj_bootstrap_job+24],0
mjc_owner:
 test DWORD PTR [boom_main_jimage_report+12],1
 jz mjc_success
 cmp DWORD PTR [boom_main_jimage_report+32],0
 je mjc_success
 lea rcx,boom_main_jimage_owner
 call boom_jimage_owner_close
 mov DWORD PTR [boom_main_jimage_report+32],eax
 test eax,eax
 jnz mjc_done
mjc_success:
 or DWORD PTR [boom_main_jimage_report+12],16
 xor eax,eax
 jmp mjc_done
mjc_bad:
 mov eax,87
mjc_done:
 mov ebx,eax
 mov rax,QWORD PTR [boom_main_jimage_owner+56]
 mov QWORD PTR [boom_main_jimage_report+72],rax
 mov rax,QWORD PTR [boom_provider_jimage_native_map_pool+40]
 mov QWORD PTR [boom_main_jimage_report+88],rax
 mov rax,QWORD PTR [boom_provider_jimage_native_map_pool+48]
 mov QWORD PTR [boom_main_jimage_report+104],rax
 mov rax,QWORD PTR [boom_main_jimage_owner+72]
 mov QWORD PTR [boom_main_jimage_report+112],rax
 mov rax,QWORD PTR [boom_main_jimage_owner+80]
 mov QWORD PTR [boom_main_jimage_report+120],rax
 mov eax,ebx
 add rsp,32
 pop rbx
 ret
boom_main_jimage_resources_close ENDP

PUBLIC boom_main_jimage_write_report
boom_main_jimage_write_report PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,64
 .allocstack 64
 .endprolog
 lea rcx,mj_report_name
 mov edx,040000000h
 mov r8d,1
 xor r9d,r9d
 mov DWORD PTR [rsp+32],1
 mov DWORD PTR [rsp+40],128
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 je mjw_os_error
 mov rbx,rax
 mov rcx,rax
 lea rdx,boom_main_jimage_report
 mov r8d,256
 lea r9,mj_report_written
 mov QWORD PTR [rsp+32],0
 call WriteFile
 test eax,eax
 jz mjw_close_error
 cmp DWORD PTR [mj_report_written],256
 jne mjw_close_error
 mov rcx,rbx
 call CloseHandle
 test eax,eax
 jz mjw_os_error
 xor eax,eax
 jmp mjw_done
mjw_close_error:
 mov rcx,rbx
 call CloseHandle
mjw_os_error:
 call GetLastError
 test eax,eax
 jnz mjw_done
 mov eax,31
mjw_done:
 add rsp,64
 pop rbx
 ret
boom_main_jimage_write_report ENDP
END
