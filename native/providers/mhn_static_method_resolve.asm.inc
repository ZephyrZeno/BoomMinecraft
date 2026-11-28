; MHMR512/1: ordinary REF_invokeStatic metadata resolution.
; Original MemberName/MethodType layouts; RMN remains a zero-field Java object.
; Explicit/quiescent nonmoving heap only. No Java constructor for RMN.
.code
PUBLIC boom_mhn_mixed_resolve_external
PUBLIC boom_mhn_mixed_vm_info_external

; Routing never changes the supplied Context. Invalid/nonmethod/field inputs
; are sent to the exact old field handler with all original ABI arguments.
boom_mhn_mixed_resolve_external PROC
 xor r9d,r9d
 jmp mhmm_route
boom_mhn_mixed_resolve_external ENDP
boom_mhn_mixed_vm_info_external PROC
 mov r9d,1
 jmp mhmm_route
boom_mhn_mixed_vm_info_external ENDP
mhmm_route PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov rdi,r8
 mov DWORD PTR [rsp+32],r9d
mhmm_route_common:
 test rbx,rbx
 jz mhmm_route_legacy
 cmp DWORD PTR [rbx],0
 jne mhmm_route_legacy
 cmp QWORD PTR [rbx+16],0
 jne mhmm_route_legacy
 test rsi,rsi
 jz mhmm_route_legacy
 mov rdx,QWORD PTR [rsi]
 test rdx,rdx
 jz mhmm_route_legacy
 mov rcx,QWORD PTR [boom_heap_ptr]
 test rcx,rcx
 jz mhmm_route_legacy
 call boom_heap_contains
 test eax,eax
 jz mhmm_route_legacy
 mov r10,QWORD PTR [rsi]
 lea r11,boom_mhn_method_pool
 mov rax,QWORD PTR [r11+120]
 cmp QWORD PTR [r10-8],rax
 jne mhmm_route_legacy
 mov eax,DWORD PTR [r10-24]
 and eax,0FFFFFFFDh
 cmp eax,0B00B0001h
 jne mhmm_route_legacy
 mov ecx,DWORD PTR [r11+244]
 mov eax,DWORD PTR [r10+rcx]
 and eax,0F0F0000h
 cmp eax,06010000h
 jne mhmm_route_legacy
 mov rcx,rbx
 mov rdx,rsi
 lea r8,boom_mhn_method_pool
 mov r9d,DWORD PTR [rsp+32]
 call mhmm_service
 jmp mhmm_route_return
mhmm_route_legacy:
 mov rcx,rbx
 mov rdx,rsi
 mov r8,rdi
 cmp DWORD PTR [rsp+32],0
 jne mhmm_route_legacy_info
 call boom_mhn_resolve_external
 jmp mhmm_route_return
mhmm_route_legacy_info:
 call boom_mhn_member_vm_info_external
mhmm_route_return:
 add rsp,48
 pop rdi
 pop rsi
 pop rbx
 ret
mhmm_route ENDP

; RBX Context, R13 exact readonly pool. R12 receives the actual heap.
mhmm_pool_valid PROC PRIVATE
 xor eax,eax
 lea r10,boom_mhn_method_pool
 cmp r13,r10
 jne mhmm_pv_done
 cmp DWORD PTR [r13],04D48524Dh
 jne mhmm_pv_done
 cmp DWORD PTR [r13+4],1
 jne mhmm_pv_done
 cmp DWORD PTR [r13+8],512
 jne mhmm_pv_done
 mov ecx,16
mhmm_pv_ptr:
 cmp QWORD PTR [r13+rcx],0
 je mhmm_pv_done
 add ecx,8
 cmp ecx,208
 jb mhmm_pv_ptr
 cmp QWORD PTR [r13+216],0
 je mhmm_pv_done
 cmp QWORD PTR [r13+288],0
 je mhmm_pv_done
 cmp QWORD PTR [r13+296],0
 je mhmm_pv_done
 cmp DWORD PTR [r13+276],0
 jne mhmm_pv_done
 cmp QWORD PTR [r13+328],0
 je mhmm_pv_done
 mov ecx,336
mhmm_pv_reserved:
 cmp QWORD PTR [r13+rcx],0
 jne mhmm_pv_done
 add ecx,8
 cmp ecx,512
 jb mhmm_pv_reserved
 mov r10,QWORD PTR [r13+16]
 mov r12,QWORD PTR [r10]
 test r12,r12
 jz mhmm_pv_done
 cmp DWORD PTR [r12],048454150h
 jne mhmm_pv_done
 cmp DWORD PTR [r12+4],1
 jne mhmm_pv_done
 mov r10,QWORD PTR [r13+24]
 cmp DWORD PTR [r10],052545950h
 jne mhmm_pv_done
 cmp DWORD PTR [r10+4],2
 jne mhmm_pv_done
 mov ecx,DWORD PTR [r10+12]
 cmp DWORD PTR [r13+12],ecx
 ja mhmm_pv_done
 cmp DWORD PTR [r13+208],ecx
 ja mhmm_pv_done
 mov r10,QWORD PTR [r13+32]
 cmp DWORD PTR [r10],04A434C53h
 jne mhmm_pv_done
 cmp DWORD PTR [r10+4],1
 jne mhmm_pv_done
 cmp DWORD PTR [r10+12],ecx
 jne mhmm_pv_done
 mov r11,QWORD PTR [r13+16]
 cmp QWORD PTR [r10+48],r11
 jne mhmm_pv_done
 mov r10,QWORD PTR [r13+64]
 cmp DWORD PTR [r10],04E4D5448h
 jne mhmm_pv_done
 cmp DWORD PTR [r10+4],1
 jne mhmm_pv_done
 cmp DWORD PTR [r10+8],ecx
 jne mhmm_pv_done
 cmp DWORD PTR [r10+120],144
 jne mhmm_pv_done
 cmp DWORD PTR [r10+124],16
 jne mhmm_pv_done
 mov r10,QWORD PTR [r13+40]
 cmp DWORD PTR [r10],05246484Dh
 jne mhmm_pv_done
 mov ecx,DWORD PTR [r10+12]
 cmp ecx,DWORD PTR [r13+12]
 jne mhmm_pv_done
 mov eax,1
mhmm_pv_done:
 ret
mhmm_pool_valid ENDP

; RDX normal VM oop, R8 source layout; normal-domain check, not forged sandbox.
mhmm_check_object PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rsi,rdx
 mov rdi,r8
 mov rcx,r12
 call boom_heap_contains
 test eax,eax
 jz mhmm_co_bad
 mov rcx,rsi
 mov rdx,rdi
 mov r8,rbx
 call boom_object_check
 jmp mhmm_co_done
mhmm_co_bad:
 mov DWORD PTR [rbx],7
 xor eax,eax
mhmm_co_done:
 add rsp,40
 pop rdi
 pop rsi
 ret
mhmm_check_object ENDP

; R8D original source Class ID, RDX canonical Class mirror. No callbacks.
; Actual loader/module Java fields must match the actual JCLS root identities.
mhmm_class_source_ok PROC PRIVATE
 xor eax,eax
 cmp r8d,DWORD PTR [r13+208]
 jae mhmm_cs_done
 mov r10,r8
 shl r10,6
 add r10,QWORD PTR [r13+72]
 cmp DWORD PTR [r10+44],1
 jne mhmm_cs_done
 mov r11,QWORD PTR [r13+32]
 imul r9,r8,48
 add r9,QWORD PTR [r11+24]
 mov ecx,DWORD PTR [r9+16]
 cmp ecx,DWORD PTR [r10+8]
 jne mhmm_cs_done
 cmp ecx,DWORD PTR [r11+84]
 jae mhmm_cs_done
 mov r10,QWORD PTR [r11+56]
 mov r10,QWORD PTR [r10+rcx*8]
 test ecx,ecx
 jz mhmm_cs_loader
 test r10,r10
 jz mhmm_cs_done
mhmm_cs_loader:
 mov ecx,DWORD PTR [r13+256]
 cmp QWORD PTR [rdx+rcx],r10
 jne mhmm_cs_done
 mov ecx,DWORD PTR [r9+20]
 cmp ecx,DWORD PTR [r11+88]
 jae mhmm_cs_done
 mov r10,QWORD PTR [r11+64]
 mov r10,QWORD PTR [r10+rcx*8]
 test r10,r10
 jz mhmm_cs_done
 mov ecx,DWORD PTR [r13+260]
 cmp QWORD PTR [rdx+rcx],r10
 jne mhmm_cs_done
 mov eax,1
mhmm_cs_done:
 ret
mhmm_class_source_ok ENDP

; CallerID ECX, selected holderID EDX, recognized modifiers R8D.
; 0 allowed/1 denied/2 unsupported unresolved nest/special accessor domain.
; A public member is allowed by Reflection::verify_member_access itself;
; the original Java Lookup performs its module/lookup capability checks.
mhmm_member_access PROC PRIVATE
 cmp ecx,edx
 je mhmm_ma_yes
 test r8d,1
 jnz mhmm_ma_yes
 mov r9,rcx
 shl r9,6
 add r9,QWORD PTR [r13+72]
 mov r10,rdx
 shl r10,6
 add r10,QWORD PTR [r13+72]
 test DWORD PTR [r9+52],1
 jnz mhmm_ma_yes
 test r8d,4
 jz mhmm_ma_package
 test DWORD PTR [r9+4],200h
 jnz mhmm_ma_package
 ; REF6 is static, therefore protected subclass receiver restriction is empty.
 mov eax,ecx
 xor r11d,r11d
mhmm_ma_super:
 cmp eax,edx
 je mhmm_ma_yes
 inc r11d
 cmp r11d,128
 ja mhmm_ma_unknown
 shl rax,6
 add rax,QWORD PTR [r13+72]
 cmp DWORD PTR [rax+44],1
 jne mhmm_ma_unknown
 mov eax,DWORD PTR [rax]
 cmp eax,-1
 jne mhmm_ma_super
mhmm_ma_package:
 test r8d,2
 jnz mhmm_ma_private
 mov eax,DWORD PTR [r9+12]
 cmp eax,DWORD PTR [r10+12]
 je mhmm_ma_yes
 jmp mhmm_ma_no
mhmm_ma_private:
 cmp DWORD PTR [r9+20],1
 jne mhmm_ma_unknown
 cmp DWORD PTR [r10+20],1
 jne mhmm_ma_unknown
 mov eax,DWORD PTR [r9+16]
 cmp eax,DWORD PTR [r10+16]
 je mhmm_ma_yes
mhmm_ma_no:
 mov eax,1
 ret
mhmm_ma_unknown:
 mov eax,2
 ret
mhmm_ma_yes:
 xor eax,eax
 ret
mhmm_member_access ENDP

; Exception row R8D/message row R9D. Successful callback restores the actual
; incoming PC/method/depth; a failing Java callback keeps its genuine error.
; Established native-frame quiescent-GC discipline; no automatic collection.
mhmm_throw PROC PRIVATE FRAME
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,112
 .allocstack 112
 .endprolog
 mov rsi,r8
 imul rsi,24
 add rsi,QWORD PTR [r13+192]
 mov rdi,r9
 shl rdi,4
 add rdi,QWORD PTR [r13+200]
 mov rax,QWORD PTR [rbx+4]
 mov QWORD PTR [rsp+80],rax
 mov eax,DWORD PTR [rbx+12]
 mov DWORD PTR [rsp+88],eax
 mov rcx,QWORD PTR [rsi]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz mhmm_th_done
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+184]
 mov r8,QWORD PTR [rdi]
 mov r9d,DWORD PTR [rdi+8]
 call boom_java_property_copy
 cmp DWORD PTR [rbx],0
 jne mhmm_th_done
 test rax,rax
 jz mhmm_th_bad
 mov QWORD PTR [rsp+48],rax
 mov rax,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rax]
 mov rdx,QWORD PTR [rsi+8]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz mhmm_th_done
 mov QWORD PTR [rsp+40],rax
 mov rcx,rbx
 lea rdx,[rsp+40]
 call QWORD PTR [rsi+16]
 cmp DWORD PTR [rbx],0
 jne mhmm_th_done
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [rbx+4],rax
 mov eax,DWORD PTR [rsp+88]
 mov DWORD PTR [rbx+12],eax
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+40]
 mov r8,QWORD PTR [r13+24]
 mov r9,QWORD PTR [r13+176]
 call boom_exception_set32
 jmp mhmm_th_done
mhmm_th_bad:
 mov DWORD PTR [rbx],7
mhmm_th_done:
 xor eax,eax
 add rsp,112
 pop r12
 pop rdi
 pop rsi
 ret
mhmm_throw ENDP

; RCX Context32/RDX original argv, R8 exact512, R9D 0 resolve/1 VMInfo.
mhmm_service PROC PRIVATE FRAME
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
 sub rsp,1440
 .allocstack 1440
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 mov r13,r8
 mov DWORD PTR [rsp+360],r9d
 mov DWORD PTR [rsp+364],0
 mov DWORD PTR [rsp+356],0
 mov QWORD PTR [rsp+40],0
 test rbx,rbx
 jz mhmm_done
 cmp DWORD PTR [rbx],0
 jne mhmm_done
 cmp QWORD PTR [rbx+16],0
 jne mhmm_done
 mov rax,QWORD PTR [rbx+4]
 mov QWORD PTR [rsp+48],rax
 mov eax,DWORD PTR [rbx+12]
 mov DWORD PTR [rsp+56],eax
 test rsi,rsi
 jz mhmm_bad
 cmp DWORD PTR [rsp+360],1
 ja mhmm_bad
 call mhmm_pool_valid
 test eax,eax
 jz mhmm_bad
 mov rcx,QWORD PTR [r13+48]
 call boom_mhn_method_owner_enter
 test eax,eax
 jnz mhmm_unsupported
 mov DWORD PTR [rsp+364],1
 mov r14,QWORD PTR [rsi]
 test r14,r14
 jz mhmm_null
 mov rdx,r14
 mov r8,QWORD PTR [r13+120]
 call mhmm_check_object
 test rax,rax
 jz mhmm_done
 mov ecx,DWORD PTR [r13+244]
 mov eax,DWORD PTR [r14+rcx]
 mov DWORD PTR [rsp+60],eax
 and eax,0F0F0000h
 cmp eax,06010000h
 jne mhmm_unsupported
 mov ecx,DWORD PTR [r13+236]
 mov rdi,QWORD PTR [r14+rcx]
 test rdi,rdi
 jnz mhmm_existing
 cmp DWORD PTR [rsp+360],0
 jne mhmm_unsupported
 mov ecx,DWORD PTR [r13+224]
 mov rax,QWORD PTR [r14+rcx]
 mov QWORD PTR [rsp+64],rax
 test rax,rax
 jz mhmm_nothing
 mov ecx,DWORD PTR [r13+228]
 mov rax,QWORD PTR [r14+rcx]
 mov QWORD PTR [rsp+72],rax
 test rax,rax
 jz mhmm_nothing
 mov ecx,DWORD PTR [r13+232]
 mov rax,QWORD PTR [r14+rcx]
 mov QWORD PTR [rsp+80],rax
 test rax,rax
 jz mhmm_nothing
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 mov r8,QWORD PTR [rsp+64]
 call boom_java_class_typeid
 cmp eax,-1
 je mhmm_done
 mov DWORD PTR [rsp+88],eax
 cmp eax,DWORD PTR [r13+208]
 jae mhmm_unsupported
 mov r8d,eax
 mov rdx,QWORD PTR [rsp+64]
 call mhmm_class_source_ok
 test eax,eax
 jz mhmm_unsupported
 mov rdx,QWORD PTR [rsp+80]
 mov r8,QWORD PTR [r13+104]
 call mhmm_check_object
 test rax,rax
 jz mhmm_done
 mov ecx,DWORD PTR [r13+248]
 mov r8,QWORD PTR [rax+rcx]
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 call boom_java_class_typeid
 cmp eax,-1
 je mhmm_done
 mov DWORD PTR [rsp+180],eax
 cmp eax,DWORD PTR [r13+12]
 jae mhmm_unsupported
 mov rax,QWORD PTR [rsp+80]
 mov ecx,DWORD PTR [r13+252]
 mov rdi,QWORD PTR [rax+rcx]
 mov rcx,r12
 mov rdx,rdi
 call boom_heap_contains
 test eax,eax
 jz mhmm_bad
 mov rcx,rdi
 mov rdx,QWORD PTR [r13+24]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz mhmm_done
 mov ecx,DWORD PTR [r13+320]
 cmp DWORD PTR [rax+16],ecx
 jne mhmm_bad
 cmp DWORD PTR [rax+20],2
 jne mhmm_bad
 cmp DWORD PTR [rax+36],3
 jne mhmm_bad
 mov rax,QWORD PTR [rdi-16]
 test al,7
 jnz mhmm_bad
 shr rax,3
 cmp rax,255
 ja mhmm_unsupported
 cmp eax,DWORD PTR [rdi-20]
 jne mhmm_bad
 mov DWORD PTR [rsp+176],eax
 mov QWORD PTR [rsp+96],rdi
 lea rax,[rsp+400]
 mov QWORD PTR [rsp+184],rax
 xor r15d,r15d
mhmm_parameter_ids:
 cmp r15d,DWORD PTR [rsp+176]
 jae mhmm_name
 mov rax,QWORD PTR [rsp+96]
 mov r8,QWORD PTR [rax+r15*8]
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 call boom_java_class_typeid
 cmp eax,-1
 je mhmm_done
 cmp eax,DWORD PTR [r13+12]
 jae mhmm_unsupported
 mov DWORD PTR [rsp+r15*4+400],eax
 inc r15d
 jmp mhmm_parameter_ids
mhmm_name:
 mov rdx,QWORD PTR [rsp+72]
 mov r8,QWORD PTR [r13+136]
 call mhmm_check_object
 test rax,rax
 jz mhmm_done
 mov ecx,DWORD PTR [r13+268]
 movzx edi,BYTE PTR [rax+rcx]
 cmp edi,1
 ja mhmm_bad
 mov ecx,DWORD PTR [r13+264]
 mov r15,QWORD PTR [rax+rcx]
 mov rcx,r12
 mov rdx,r15
 call boom_heap_contains
 test eax,eax
 jz mhmm_bad
 mov eax,DWORD PTR [r13+316]
 cmp QWORD PTR [r15-8],rax
 jne mhmm_bad
 cmp DWORD PTR [r15-20],0
 jne mhmm_bad
 mov rax,QWORD PTR [r15-16]
 cmp rax,131070
 ja mhmm_unsupported
 test edi,edi
 jz mhmm_name_count
 test al,1
 jnz mhmm_bad
 shr rax,1
mhmm_name_count:
 cmp rax,65535
 ja mhmm_unsupported
 mov QWORD PTR [rsp+160],r15
 mov DWORD PTR [rsp+168],eax
 mov DWORD PTR [rsp+172],edi
 mov rax,QWORD PTR [rsi+8]
 mov QWORD PTR [rsp+104],rax
 mov DWORD PTR [rsp+112],-1
 test rax,rax
 jz mhmm_lookup_ready
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 mov r8,rax
 call boom_java_class_typeid
 cmp eax,-1
 je mhmm_done
 mov DWORD PTR [rsp+112],eax
 mov r8d,eax
 mov rdx,QWORD PTR [rsp+104]
 call mhmm_class_source_ok
 test eax,eax
 jz mhmm_unsupported
mhmm_lookup_ready:
 mov QWORD PTR [rsp+192],0
 mov QWORD PTR [rsp+200],0
 mov QWORD PTR [rsp+208],0
 mov QWORD PTR [rsp+216],0
 mov rcx,r13
 lea rdx,[rsp+160]
 mov r8d,DWORD PTR [rsp+88]
 lea r9,[rsp+224]
 call mhmm_lookup
 cmp eax,1
 je mhmm_missing
 cmp eax,2
 je mhmm_unsupported
 test eax,eax
 jnz mhmm_bad
 cmp DWORD PTR [rsp+112],-1
 je mhmm_constraints
 mov ecx,DWORD PTR [rsp+112]
 mov edx,DWORD PTR [rsp+236]
 mov r8d,DWORD PTR [rsp+244]
 call mhmm_member_access
 cmp eax,2
 je mhmm_unsupported
 test eax,eax
 jnz mhmm_access_denied
mhmm_constraints:
 cmp QWORD PTR [rsp+104],0
 je mhmm_static_check
 test DWORD PTR [rsi+16],20h
 jnz mhmm_static_check
 mov eax,DWORD PTR [rsp+112]
 shl rax,6
 add rax,QWORD PTR [r13+72]
 mov eax,DWORD PTR [rax+8]
 cmp eax,2
 ja mhmm_unsupported
 imul eax,DWORD PTR [r13+12]
 shl rax,2
 add rax,QWORD PTR [r13+216]
 mov QWORD PTR [rsp+120],rax
 ; Compare each signature identity in both known source loader namespaces.
 mov rdi,QWORD PTR [rsp+224]
 mov edx,DWORD PTR [rdi+52]
 mov rax,QWORD PTR [rsp+120]
 cmp edx,DWORD PTR [r13+12]
 jae mhmm_unsupported
 mov eax,DWORD PTR [rax+rdx*4]
 cmp eax,edx
 jne mhmm_unsupported
 xor r15d,r15d
mhmm_constraint_param:
 cmp r15d,DWORD PTR [rsp+176]
 jae mhmm_static_check
 mov rax,QWORD PTR [rdi+16]
 mov edx,DWORD PTR [rax+r15*4]
 cmp edx,DWORD PTR [r13+12]
 jae mhmm_unsupported
 mov rax,QWORD PTR [rsp+120]
 mov eax,DWORD PTR [rax+rdx*4]
 cmp eax,edx
 jne mhmm_unsupported
 inc r15d
 jmp mhmm_constraint_param
mhmm_static_check:
 test DWORD PTR [rsp+244],8
 jz mhmm_not_static
 ; The target holder mirror is loaded (not initialized) before RMN allocation.
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 mov r8d,DWORD PTR [rsp+236]
 call boom_java_class_load
 cmp DWORD PTR [rbx],0
 jne mhmm_done
 test rax,rax
 jz mhmm_bad
 mov QWORD PTR [rsp+128],rax
 mov rdx,rax
 mov r8d,DWORD PTR [rsp+236]
 call mhmm_class_source_ok
 test eax,eax
 jz mhmm_unsupported
 ; All callbacks occur before creating the fresh RMN candidate.
 mov rcx,QWORD PTR [r13+160]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz mhmm_done
 cmp DWORD PTR [rbx],0
 jne mhmm_done
 mov eax,DWORD PTR [rsp+232]
 mov DWORD PTR [rsp+256],eax
 mov eax,DWORD PTR [rsp+236]
 mov DWORD PTR [rsp+260],eax
 mov eax,DWORD PTR [rsp+240]
 mov DWORD PTR [rsp+264],eax
 mov eax,DWORD PTR [rsp+244]
 mov DWORD PTR [rsp+268],eax
 mov rax,QWORD PTR [rsp+224]
 mov QWORD PTR [rsp+272],rax
 mov QWORD PTR [rsp+280],0
 mov rax,QWORD PTR [rsp+128]
 mov QWORD PTR [rsp+288],rax
 mov rax,QWORD PTR [r13+56]
 mov rax,QWORD PTR [rax+48]
 mov QWORD PTR [rsp+304],rax
 mov QWORD PTR [rsp+312],0
 mov rcx,r12
 mov rdx,QWORD PTR [r13+168]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz mhmm_done
 mov QWORD PTR [rsp+296],rax
 ; No Java callback occurs between object_new and this strong-root commit.
 mov rcx,QWORD PTR [r13+48]
 lea rdx,[rsp+256]
 call boom_mhn_method_owner_intern
 test eax,eax
 jnz mhmm_unsupported
 mov rdi,QWORD PTR [rsp+312]
 test rdi,rdi
 jz mhmm_bad
 mov ecx,DWORD PTR [r13+224]
 mov rax,QWORD PTR [rsp+128]
 mov QWORD PTR [r14+rcx],rax
 mov ecx,DWORD PTR [r13+236]
 mov QWORD PTR [r14+rcx],rdi
 mov ecx,DWORD PTR [r13+244]
 mov eax,DWORD PTR [rsp+268]
 mov DWORD PTR [r14+rcx],eax
 ; name/type/resolution remain exactly the original Java values.
 mov QWORD PTR [rsp+40],r14
 jmp mhmm_restore_success
mhmm_existing:
 mov rdx,rdi
 mov r8,QWORD PTR [r13+168]
 call mhmm_check_object
 test rax,rax
 jz mhmm_done
 mov rcx,QWORD PTR [r13+48]
 mov rdx,rdi
 call boom_mhn_method_owner_find
 test rax,rax
 jz mhmm_unsupported
 mov edx,DWORD PTR [rax+28]
 cmp edx,DWORD PTR [rsp+60]
 jne mhmm_unsupported
 mov QWORD PTR [rsp+136],rax
 cmp DWORD PTR [rsp+360],1
 je mhmm_vm_info
 mov QWORD PTR [rsp+40],r14
 jmp mhmm_restore_success
mhmm_vm_info:
 ; Original native order: fresh Object[2], then initialize/allocate fresh Long.
 ; A preparing record explicitly roots the array across Long.ensure.
 mov rcx,QWORD PTR [r13+48]
 lea rdx,[rsp+368]
 call boom_mhn_method_scratch_acquire
 test eax,eax
 jnz mhmm_unsupported
 mov DWORD PTR [rsp+356],1
 mov QWORD PTR [rsp+320],2
 ; typed_multi_new fifth argument is Context32 at call stack +32.
 mov QWORD PTR [rsp+32],rbx
 mov rcx,r12
 lea rdx,[rsp+320]
 mov r8,QWORD PTR [r13+296]
 mov r9d,1
 call boom_typed_multi_new
 cmp DWORD PTR [rbx],0
 jne mhmm_done
 test rax,rax
 jz mhmm_bad
 mov QWORD PTR [rsp+344],rax
 mov rcx,QWORD PTR [r13+48]
 lea rdx,[rsp+368]
 mov r8,rax
 xor r9d,r9d
 call boom_mhn_method_scratch_set
 test eax,eax
 jnz mhmm_unsupported
 mov rcx,QWORD PTR [r13+288]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz mhmm_done
 cmp DWORD PTR [rbx],0
 jne mhmm_done
 mov rcx,r12
 mov rdx,QWORD PTR [r13+328]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz mhmm_done
 mov ecx,DWORD PTR [r13+324]
 mov QWORD PTR [rax+rcx],-2
 mov QWORD PTR [rsp+336],rax
 mov rcx,QWORD PTR [r13+48]
 lea rdx,[rsp+368]
 mov r8,QWORD PTR [rsp+344]
 mov r9,rax
 call boom_mhn_method_scratch_set
 test eax,eax
 jnz mhmm_unsupported
 mov rax,QWORD PTR [rsp+344]
 mov rdx,QWORD PTR [rsp+336]
 mov QWORD PTR [rax],rdx
 mov QWORD PTR [rax+8],r14
 mov QWORD PTR [rsp+40],rax
 jmp mhmm_restore_success
mhmm_missing:
 cmp DWORD PTR [rsi+24],1
 je mhmm_done
 mov r8d,2
 mov r9d,3
 jmp mhmm_error
mhmm_access_denied:
 cmp DWORD PTR [rsi+24],1
 je mhmm_done
 mov r8d,3
 mov r9d,4
 jmp mhmm_error
mhmm_not_static:
 cmp DWORD PTR [rsi+24],1
 je mhmm_done
 mov r8d,4
 mov r9d,5
 jmp mhmm_error
mhmm_null:
 xor r8d,r8d
 xor r9d,r9d
 jmp mhmm_error
mhmm_nothing:
 mov r8d,1
 mov r9d,2
mhmm_error:
 call mhmm_throw
 jmp mhmm_done
mhmm_restore_success:
 mov rax,QWORD PTR [rsp+48]
 mov QWORD PTR [rbx+4],rax
 mov eax,DWORD PTR [rsp+56]
 mov DWORD PTR [rbx+12],eax
 jmp mhmm_done
mhmm_bad:
 mov DWORD PTR [rbx],7
 jmp mhmm_done
mhmm_unsupported:
 cmp DWORD PTR [rbx],0
 jne mhmm_done
 mov DWORD PTR [rbx],20
mhmm_done:
 cmp DWORD PTR [rsp+356],0
 je mhmm_done_scratch
 mov rcx,QWORD PTR [r13+48]
 lea rdx,[rsp+368]
 call boom_mhn_method_scratch_release
 test eax,eax
 jz mhmm_done_scratch
 cmp DWORD PTR [rbx],0
 jne mhmm_done_scratch
 mov DWORD PTR [rbx],20
mhmm_done_scratch:
 cmp DWORD PTR [rsp+364],0
 je mhmm_return
 mov rcx,QWORD PTR [r13+48]
 call boom_mhn_method_owner_leave
 test eax,eax
 jz mhmm_return
 cmp DWORD PTR [rbx],0
 jne mhmm_return
 mov DWORD PTR [rbx],20
mhmm_return:
 xor eax,eax
 test rbx,rbx
 jz mhmm_epilog
 cmp DWORD PTR [rbx],0
 jne mhmm_epilog
 mov rax,QWORD PTR [rsp+40]
mhmm_epilog:
 add rsp,1440
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
mhmm_service ENDP
