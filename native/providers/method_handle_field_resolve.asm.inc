PUBLIC mhf_check_object
PUBLIC mhf_field_record
PUBLIC mhf_missing_message
PUBLIC mhf_pool_valid
PUBLIC mhf_service
PUBLIC mhf_throw
PUBLIC mhf_throw_oop
PUBLIC mhfm_copy_dotted
; MHFR256/1. Original MemberName fields, no HotSpot injected fields.
; No lock, native borrow or Java callback is held across another callback.
; Native frame locals follow the existing explicit/quiescent GC discipline.
.code
PUBLIC boom_mhn_resolve_external
PUBLIC boom_mhn_object_field_offset_external
PUBLIC boom_mhn_static_field_offset_external
PUBLIC boom_mhn_static_field_base_external
PUBLIC boom_mhn_member_vm_info_external
boom_mhn_resolve_external PROC
 xor r9d,r9d
 jmp mhf_service
boom_mhn_resolve_external ENDP
boom_mhn_object_field_offset_external PROC
 mov r9d,1
 jmp mhf_service
boom_mhn_object_field_offset_external ENDP
boom_mhn_static_field_offset_external PROC
 mov r9d,2
 jmp mhf_service
boom_mhn_static_field_offset_external ENDP
boom_mhn_static_field_base_external PROC
 mov r9d,3
 jmp mhf_service
boom_mhn_static_field_base_external ENDP
boom_mhn_member_vm_info_external PROC
 mov r9d,4
 jmp mhf_service
boom_mhn_member_vm_info_external ENDP

; All metadata pointers are immutable source-bound native inputs.
; RBX original Context32, R13 exact readonly pool, R12 actual heap.
mhf_pool_valid PROC
 xor eax,eax
 cmp DWORD PTR [r13],05246484Dh
 jne mhfp_done
 cmp DWORD PTR [r13+4],1
 jne mhfp_done
 cmp DWORD PTR [r13+8],256
 jne mhfp_done
 cmp DWORD PTR [r13+164],0
 jne mhfp_done
 mov ecx,168
mhfp_reserved_a:
 cmp QWORD PTR [r13+rcx],0
 jne mhfp_done
 add ecx,8
 cmp ecx,192
 jb mhfp_reserved_a
 mov ecx,224
mhfp_reserved_b:
 cmp QWORD PTR [r13+rcx],0
 jne mhfp_done
 add ecx,8
 cmp ecx,256
 jb mhfp_reserved_b
 mov ecx,16
mhfp_pointers:
 cmp QWORD PTR [r13+rcx],0
 je mhfp_done
 add ecx,8
 cmp ecx,160
 jb mhfp_pointers
 mov r10,QWORD PTR [r13+16]
 mov r12,QWORD PTR [r10]
 test r12,r12
 jz mhfp_done
 cmp DWORD PTR [r12],048454150h
 jne mhfp_done
 cmp DWORD PTR [r12+4],1
 jne mhfp_done
 mov r10,QWORD PTR [r13+24]
 cmp DWORD PTR [r10],052545950h
 jne mhfp_done
 cmp DWORD PTR [r10+4],2
 jne mhfp_done
 mov ecx,DWORD PTR [r10+12]
 test ecx,ecx
 jz mhfp_done
 cmp ecx,0100000h
 ja mhfp_done
 cmp DWORD PTR [r13+12],ecx
 ja mhfp_done
 mov r10,QWORD PTR [r13+32]
 cmp DWORD PTR [r10],04A434C53h
 jne mhfp_done
 cmp DWORD PTR [r10+4],1
 jne mhfp_done
 cmp DWORD PTR [r10+12],ecx
 jne mhfp_done
 mov r11,QWORD PTR [r13+16]
 cmp QWORD PTR [r10+48],r11
 jne mhfp_done
 mov r10,QWORD PTR [r13+40]
 cmp DWORD PTR [r10],055464D50h
 jne mhfp_done
 mov eax,DWORD PTR [r10+4]
 dec eax
 cmp eax,1
 ja mhfp_no
 cmp DWORD PTR [r10+8],ecx
 jne mhfp_no
 cmp DWORD PTR [r10+108],64
 jne mhfp_no
 cmp QWORD PTR [r10+120],0
 jne mhfp_no
 mov r11,QWORD PTR [r13+16]
 cmp QWORD PTR [r10+16],r11
 jne mhfp_no
 mov r11,QWORD PTR [r13+24]
 cmp QWORD PTR [r10+32],r11
 jne mhfp_no
 mov r11,QWORD PTR [r13+32]
 cmp QWORD PTR [r10+24],r11
 jne mhfp_no
 mov r11,055464C4400000000h
 cmp DWORD PTR [r10+4],1
 je mhfp_tag
 mov r11,055464C3200000000h
mhfp_tag:
 cmp QWORD PTR [r10+112],r11
 jne mhfp_no
 mov eax,DWORD PTR [r10+12]
 dec eax
 cmp eax,0FFFFFEh
 ja mhfp_no
 shr eax,10
 inc eax
 cmp eax,DWORD PTR [r10+92]
 jne mhfp_no
 mov eax,1
 ret
mhfp_no:
 xor eax,eax
mhfp_done:
 ret
mhf_pool_valid ENDP

; Context already clean. RDX ordinary VM oop, R8 source layout.
; This is a normal heap-domain/header/layout check, not a forged-pointer sandbox.
mhf_check_object PROC FRAME
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
 jz mhfo_bad
 mov rcx,rsi
 mov rdx,rdi
 mov r8,rbx
 call boom_object_check
 jmp mhfo_done
mhfo_bad:
 mov DWORD PTR [rbx],7
 xor eax,eax
mhfo_done:
 add rsp,40
 pop rdi
 pop rsi
 ret
mhf_check_object ENDP

; RCX actual field ID, RDX Result32. Return validated exact UFMP Field64.
mhf_field_record PROC
 mov r10,QWORD PTR [r13+40]
 cmp ecx,DWORD PTR [r10+12]
 jae mhfr_bad
 mov r11d,ecx
 shr ecx,10
 mov rax,QWORD PTR [r10+80]
 mov rax,QWORD PTR [rax+rcx*8]
 test rax,rax
 jz mhfr_bad
 mov ecx,r11d
 and ecx,1023
 shl ecx,6
 add rax,rcx
 cmp DWORD PTR [rax+48],r11d
 jne mhfr_bad
 mov ecx,DWORD PTR [rdx]
 cmp DWORD PTR [rax],ecx
 jne mhfr_bad
 cmp ecx,DWORD PTR [r10+8]
 jae mhfr_bad
 mov r10,QWORD PTR [r10+72]
 lea r10,[r10+rcx*8]
 mov ecx,DWORD PTR [rax+4]
 cmp ecx,DWORD PTR [rdx+8]
 jne mhfr_bad
 cmp ecx,DWORD PTR [r10+4]
 jae mhfr_bad
 add ecx,DWORD PTR [r10]
 jc mhfr_bad
 cmp ecx,r11d
 jne mhfr_bad
 mov ecx,DWORD PTR [rdx+12]
 cmp ecx,0FFFFh
 ja mhfr_bad
 cmp DWORD PTR [rax+8],ecx
 jne mhfr_bad
 mov ecx,DWORD PTR [rdx+20]
 cmp DWORD PTR [rax+24],ecx
 jne mhfr_bad
 mov ecx,DWORD PTR [rdx+24]
 cmp DWORD PTR [rax+12],ecx
 jne mhfr_bad
 test ecx,ecx
 jz mhfr_bad
 cmp ecx,9
 ja mhfr_bad
 cmp QWORD PTR [rax+40],0
 jne mhfr_bad
 cmp DWORD PTR [rax+52],0
 jne mhfr_bad
 cmp QWORD PTR [rax+56],0
 jne mhfr_bad
 test DWORD PTR [rax+8],8
 jnz mhfr_static
 cmp QWORD PTR [rax+32],0
 je mhfr_bad
 ret
mhfr_static:
 cmp QWORD PTR [rax+32],0
 jne mhfr_bad
 ret
mhfr_bad:
 xor eax,eax
 ret
mhf_field_record ENDP

; R8D exception row, R9D message row. Original Java constructors, no locks.
mhf_throw PROC FRAME
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,88
 .allocstack 88
 .endprolog
 mov esi,r8d
 mov edi,r9d
 imul rsi,rsi,24
 add rsi,QWORD PTR [r13+128]
 shl rdi,4
 add rdi,QWORD PTR [r13+144]
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+136]
 mov r8,QWORD PTR [rdi]
 mov r9d,DWORD PTR [rdi+8]
 call boom_java_property_copy
 cmp DWORD PTR [rbx],0
 jne mhft_done
 test rax,rax
 jz mhft_bad
 mov QWORD PTR [rsp+64],rax
 mov rcx,QWORD PTR [rsi]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz mhft_done
 mov rcx,r12
 mov rdx,QWORD PTR [rsi+8]
 mov r8,rbx
 call boom_object_new
 cmp DWORD PTR [rbx],0
 jne mhft_done
 test rax,rax
 jz mhft_oom
 mov QWORD PTR [rsp+72],rax
 mov QWORD PTR [rsp+32],rax
 mov rax,QWORD PTR [rsp+64]
 mov QWORD PTR [rsp+40],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+16]
 cmp DWORD PTR [rbx],0
 jne mhft_done
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+72]
 mov r8,QWORD PTR [r13+24]
 mov r9,QWORD PTR [r13+120]
 call boom_exception_set32
 jmp mhft_done
mhft_bad:
 mov DWORD PTR [rbx],7
 jmp mhft_done
mhft_oom:
 mov DWORD PTR [rbx],3
mhft_done:
 xor eax,eax
 add rsp,88
 pop rdi
 pop rsi
 ret
mhf_throw ENDP

; Exact source-field miss message, assembled from source descriptors and the
; original name's UTF16 char[]. Scratch storage is a real VM char[] allocation,
; not an unmanaged native lease or a Java field/class-state substitution.
.const
mhfm_class WORD 67,108,97,115,115,32
mhfm_middle WORD 32,100,111,101,115,32,110,111,116,32,104,97,118,101,32,109,101,109,98,101,114,32,102,105,101,108,100,32,39
mhfm_primitive_codes WORD 90,66,67,83,73,74,70,68,86
ALIGN 8
mhfm_primitives LABEL BYTE
 QWORD OFFSET mhfm_boolean
 DWORD 7,0
 QWORD OFFSET mhfm_byte
 DWORD 4,0
 QWORD OFFSET mhfm_char
 DWORD 4,0
 QWORD OFFSET mhfm_short
 DWORD 5,0
 QWORD OFFSET mhfm_int
 DWORD 3,0
 QWORD OFFSET mhfm_long
 DWORD 4,0
 QWORD OFFSET mhfm_float
 DWORD 5,0
 QWORD OFFSET mhfm_double
 DWORD 6,0
 QWORD OFFSET mhfm_void
 DWORD 4,0
mhfm_boolean WORD 98,111,111,108,101,97,110
mhfm_byte WORD 98,121,116,101
mhfm_char WORD 99,104,97,114
mhfm_short WORD 115,104,111,114,116
mhfm_int WORD 105,110,116
mhfm_long WORD 108,111,110,103
mhfm_float WORD 102,108,111,97,116
mhfm_double WORD 100,111,117,98,108,101
mhfm_void WORD 118,111,105,100
.code
; EAX original symbolic owner type ID, EDX canonical field type ID,
; R8 validated original name char[] -> normal Java String, or Context failure.
; RBX/R12/R13 retain original Context, heap and readonly pool.
mhf_missing_message PROC FRAME
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,152
 .allocstack 152
 .endprolog
 cmp eax,DWORD PTR [r13+12]
 jae mhfm_bad
 cmp edx,DWORD PTR [r13+12]
 jae mhfm_bad
 mov r14,r8
 test r14,r14
 jz mhfm_bad
 shl rax,4
 add rax,QWORD PTR [r13+56]
 test DWORD PTR [rax+12],1
 jz mhfm_bad
 mov rsi,QWORD PTR [rax]
 mov ecx,DWORD PTR [rax+8]
 cmp ecx,3
 jb mhfm_bad
 cmp WORD PTR [rsi],76
 jne mhfm_bad
 cmp WORD PTR [rsi+rcx*2-2],59
 jne mhfm_bad
 add rsi,2
 sub ecx,2
 mov QWORD PTR [rsp+48],rsi
 mov DWORD PTR [rsp+56],ecx
 mov eax,edx
 shl rax,4
 add rax,QWORD PTR [r13+56]
 test DWORD PTR [rax+12],1
 jz mhfm_bad
 mov rsi,QWORD PTR [rax]
 mov ecx,DWORD PTR [rax+8]
 xor r15d,r15d
mhfm_rank:
 test ecx,ecx
 jz mhfm_bad
 cmp WORD PTR [rsi],91
 jne mhfm_base
 inc r15d
 cmp r15d,255
 ja mhfm_bad
 add rsi,2
 dec ecx
 jmp mhfm_rank
mhfm_base:
 cmp WORD PTR [rsi],76
 jne mhfm_primitive
 cmp ecx,3
 jb mhfm_bad
 cmp WORD PTR [rsi+rcx*2-2],59
 jne mhfm_bad
 add rsi,2
 sub ecx,2
 jmp mhfm_type_ready
mhfm_primitive:
 cmp ecx,1
 jne mhfm_bad
 movzx edx,WORD PTR [rsi]
 lea r10,mhfm_primitive_codes
 xor eax,eax
mhfm_primitive_find:
 cmp dx,WORD PTR [r10+rax*2]
 je mhfm_primitive_found
 inc eax
 cmp eax,9
 jb mhfm_primitive_find
 jmp mhfm_bad
mhfm_primitive_found:
 shl rax,4
 lea r10,mhfm_primitives
 add r10,rax
 mov rsi,QWORD PTR [r10]
 mov ecx,DWORD PTR [r10+8]
mhfm_type_ready:
 mov QWORD PTR [rsp+64],rsi
 mov DWORD PTR [rsp+72],ecx
 mov DWORD PTR [rsp+76],r15d
 mov rax,QWORD PTR [r14-16]
 test al,1
 jnz mhfm_bad
 shr rax,1
 cmp rax,65535
 ja mhfm_bad
 mov DWORD PTR [rsp+80],eax
 add eax,DWORD PTR [rsp+56]
 add eax,DWORD PTR [rsp+72]
 lea eax,[rax+r15*2+37]
 ; 6 (Class ) + 29 ( middle) + one space + one closing quote.
 cmp eax,200000
 ja mhfm_bad
 mov QWORD PTR [rsp+88],rax
 mov r10,QWORD PTR [r13+32]
 mov eax,DWORD PTR [r13+220]
 cmp eax,DWORD PTR [r10+12]
 jae mhfm_bad
 imul rax,rax,48
 add rax,QWORD PTR [r10+24]
 mov r8,QWORD PTR [rax]
 mov QWORD PTR [rsp+32],rbx
 mov rcx,r12
 lea rdx,[rsp+88]
 mov r9d,1
 call boom_typed_multi_new
 cmp DWORD PTR [rbx],0
 jne mhfm_zero
 test rax,rax
 jz mhfm_oom
 mov QWORD PTR [rsp+96],rax
 mov rdi,rax
 lea rsi,mhfm_class
 mov ecx,6
 rep movsw
 mov rsi,QWORD PTR [rsp+48]
 mov ecx,DWORD PTR [rsp+56]
 call mhfm_copy_dotted
 lea rsi,mhfm_middle
 mov ecx,29
 rep movsw
 mov rsi,QWORD PTR [rsp+64]
 mov ecx,DWORD PTR [rsp+72]
 call mhfm_copy_dotted
 mov ecx,DWORD PTR [rsp+76]
mhfm_brackets:
 test ecx,ecx
 jz mhfm_name
 mov DWORD PTR [rdi],005D005Bh
 add rdi,4
 dec ecx
 jmp mhfm_brackets
mhfm_name:
 mov WORD PTR [rdi],32
 add rdi,2
 mov rsi,r14
 mov ecx,DWORD PTR [rsp+80]
 rep movsw
 mov WORD PTR [rdi],39
 add rdi,2
 mov rax,rdi
 sub rax,QWORD PTR [rsp+96]
 shr rax,1
 cmp rax,QWORD PTR [rsp+88]
 jne mhfm_bad
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+136]
 mov r8,QWORD PTR [rsp+96]
 mov r9d,DWORD PTR [rsp+88]
 call boom_java_property_copy
 jmp mhfm_done
mhfm_bad:
 mov DWORD PTR [rbx],7
 jmp mhfm_zero
mhfm_oom:
 mov DWORD PTR [rbx],3
mhfm_zero:
 xor eax,eax
mhfm_done:
 add rsp,152
 pop r15
 pop r14
 pop rdi
 pop rsi
 ret
mhf_missing_message ENDP

; Source-valid native UTF16 views. No stack frame or outbound calls.
mhfm_copy_dotted PROC
 test ecx,ecx
 jz mhfm_copy_done
mhfm_copy_next:
 mov ax,WORD PTR [rsi]
 cmp ax,47
 jne mhfm_copy_store
 mov ax,46
mhfm_copy_store:
 mov WORD PTR [rdi],ax
 add rsi,2
 add rdi,2
 dec ecx
 jnz mhfm_copy_next
mhfm_copy_done:
 ret
mhfm_copy_dotted ENDP

; R8D original exception index, R9 original normal String oop. No locks.
mhf_throw_oop PROC FRAME
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,72
 .allocstack 72
 .endprolog
 mov esi,r8d
 imul rsi,rsi,24
 add rsi,QWORD PTR [r13+128]
 mov rdi,r9
 mov rcx,QWORD PTR [rsi]
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz mhfmo_done
 mov rcx,r12
 mov rdx,QWORD PTR [rsi+8]
 mov r8,rbx
 call boom_object_new
 cmp DWORD PTR [rbx],0
 jne mhfmo_done
 test rax,rax
 jz mhfmo_oom
 mov QWORD PTR [rsp+56],rax
 mov QWORD PTR [rsp+32],rax
 mov QWORD PTR [rsp+40],rdi
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+16]
 cmp DWORD PTR [rbx],0
 jne mhfmo_done
 mov rcx,rbx
 mov rdx,QWORD PTR [rsp+56]
 mov r8,QWORD PTR [r13+24]
 mov r9,QWORD PTR [r13+120]
 call boom_exception_set32
 jmp mhfmo_done
mhfmo_oom:
 mov DWORD PTR [rbx],3
mhfmo_done:
 xor eax,eax
 add rsp,72
 pop rdi
 pop rsi
 ret
mhf_throw_oop ENDP

mhf_service PROC FRAME
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
 sub rsp,384
 .allocstack 384
 .endprolog
 mov rbx,rcx
 lea r13,boom_mhn_field_pool
 mov QWORD PTR [rsp+40],0
 mov QWORD PTR [rsp+48],rdx
 mov DWORD PTR [rsp+144],r9d
 mov DWORD PTR [rsp+88],0
 mov DWORD PTR [rsp+92],0
 mov QWORD PTR [rsp+80],0
 test rbx,rbx
 jz mhf_done
 cmp DWORD PTR [rbx],0
 jne mhf_done
 cmp QWORD PTR [rbx+16],0
 jne mhf_done
 test rdx,rdx
 jz mhf_bad
 cmp r9d,4
 ja mhf_bad
 call mhf_pool_valid
 test eax,eax
 jz mhf_bad
 mov rax,QWORD PTR [rsp+48]
 mov r14,QWORD PTR [rax]
 test r14,r14
 jnz mhf_member
 cmp DWORD PTR [rsp+144],4
 je mhf_done
 cmp DWORD PTR [rsp+144],0
 je mhf_null_resolve
 jmp mhf_unresolved_error
mhf_null_resolve:
 xor r8d,r8d
 xor r9d,r9d
 call mhf_throw
 jmp mhf_done
mhf_member:
 mov rdx,r14
 mov r8,QWORD PTR [r13+64]
 call mhf_check_object
 test rax,rax
 jz mhf_done
 cmp DWORD PTR [rsp+144],0
 je mhf_class_checked
 cmp DWORD PTR [rsp+144],4
 je mhf_class_checked
 mov ecx,DWORD PTR [r13+192]
 cmp QWORD PTR [r14+rcx],0
 je mhf_unresolved_error
mhf_class_checked:
 mov ecx,DWORD PTR [r13+212]
 mov eax,DWORD PTR [r14+rcx]
 mov DWORD PTR [rsp+64],eax
 shr eax,24
 and eax,15
 mov DWORD PTR [rsp+148],eax
 dec eax
 cmp eax,3
 ja mhf_non_field
 mov eax,DWORD PTR [rsp+64]
 and eax,0F0000h
 cmp eax,40000h
 jne mhf_non_field
 mov ecx,DWORD PTR [r13+192]
 mov rax,QWORD PTR [r14+rcx]
 mov QWORD PTR [rsp+96],rax
 test rax,rax
 jz mhf_nothing
 mov ecx,DWORD PTR [r13+196]
 mov rax,QWORD PTR [r14+rcx]
 mov QWORD PTR [rsp+104],rax
 test rax,rax
 jz mhf_nothing
 mov ecx,DWORD PTR [r13+200]
 mov rax,QWORD PTR [r14+rcx]
 mov QWORD PTR [rsp+112],rax
 test rax,rax
 jz mhf_nothing
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 mov r8,QWORD PTR [rsp+96]
 call boom_java_class_typeid
 cmp eax,-1
 je mhf_done
 mov DWORD PTR [rsp+68],eax
 cmp eax,DWORD PTR [r13+160]
 jae mhf_unsupported
 ; Symbolic String and MethodType type forms are outside this field domain.
 mov rcx,r12
 mov rdx,QWORD PTR [rsp+112]
 call boom_heap_contains
 test eax,eax
 jz mhf_bad
 mov rcx,QWORD PTR [rsp+112]
 mov rdx,QWORD PTR [r13+24]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz mhf_done
 mov r10,QWORD PTR [r13+32]
 mov r11d,DWORD PTR [r10+108]
 cmp DWORD PTR [rax+16],r11d
 jne mhf_unsupported
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 mov r8,QWORD PTR [rsp+112]
 call boom_java_class_typeid
 cmp eax,-1
 je mhf_done
 mov DWORD PTR [rsp+72],eax
 cmp eax,DWORD PTR [r13+12]
 jae mhf_unsupported
 mov rcx,rax
 shl rcx,4
 add rcx,QWORD PTR [r13+56]
 test DWORD PTR [rcx+12],1
 jz mhf_unsupported
mhf_descriptor:
 mov rax,QWORD PTR [rcx]
 mov QWORD PTR [rsp+192],rax
 mov eax,DWORD PTR [rcx+8]
 mov DWORD PTR [rsp+204],eax
 mov QWORD PTR [rsp+208],0
 mov rdx,QWORD PTR [rsp+104]
 mov r8,QWORD PTR [r13+80]
 call mhf_check_object
 test rax,rax
 jz mhf_done
 mov rax,QWORD PTR [rsp+104]
 mov QWORD PTR [rsp+272],rax
 mov rcx,rbx
 lea rdx,[rsp+272]
 call QWORD PTR [r13+96]
 cmp DWORD PTR [rbx],0
 jne mhf_done
 test rax,rax
 jz mhf_bad
 mov r15,rax
 mov QWORD PTR [rsp+120],rax
 mov rcx,r12
 mov rdx,r15
 call boom_heap_contains
 test eax,eax
 jz mhf_bad
 mov rcx,r15
 mov rdx,QWORD PTR [r13+24]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz mhf_done
 mov ecx,DWORD PTR [r13+220]
 cmp DWORD PTR [rax+16],ecx
 jne mhf_bad
 cmp DWORD PTR [rax+20],1
 jne mhf_bad
 cmp DWORD PTR [rax+36],1
 jne mhf_bad
 mov rax,QWORD PTR [r15-16]
 test al,1
 jnz mhf_bad
 shr rax,1
 cmp rax,65535
 ja mhf_unsupported
 mov QWORD PTR [rsp+184],r15
 mov DWORD PTR [rsp+200],eax
 cmp DWORD PTR [rsp+144],0
 jne mhf_lookup
 mov rax,QWORD PTR [rsp+48]
 mov r10,QWORD PTR [rax+8]
 mov QWORD PTR [rsp+80],r10
 mov ecx,DWORD PTR [rax+16]
 mov DWORD PTR [rsp+92],ecx
 mov ecx,DWORD PTR [rax+24]
 mov DWORD PTR [rsp+88],ecx
 test r10,r10
 jz mhf_lookup
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 mov r8,r10
 call boom_java_class_typeid
 cmp eax,-1
 je mhf_done
 mov DWORD PTR [rsp+76],eax
mhf_lookup:
 mov rcx,QWORD PTR [r13+48]
 mov edx,DWORD PTR [rsp+68]
 lea r8,[rsp+184]
 lea r9,[rsp+152]
 call boom_source_field_lookup
 cmp eax,1
 je mhf_missing
 cmp eax,2
 je mhf_unsupported
 test eax,eax
 jnz mhf_bad
 mov eax,DWORD PTR [rsp+72]
 cmp DWORD PTR [rsp+168],eax
 jne mhf_unsupported
 mov ecx,DWORD PTR [rsp+156]
 lea rdx,[rsp+152]
 call mhf_field_record
 test rax,rax
 jz mhf_bad
 mov QWORD PTR [rsp+240],rax
 ; A stable virtual byte token, never a naked packed Java offset.
 mov eax,DWORD PTR [rsp+156]
 inc eax
 mov r10,QWORD PTR [r13+40]
 cmp DWORD PTR [r10+4],1
 je mhf_cookie
 shl eax,8
 or eax,80h
mhf_cookie:
 or rax,QWORD PTR [r10+112]
 mov QWORD PTR [rsp+136],rax
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+32]
 mov r8d,DWORD PTR [rsp+152]
 call boom_java_class_load
 cmp DWORD PTR [rbx],0
 jne mhf_done
 test rax,rax
 jz mhf_bad
 mov QWORD PTR [rsp+128],rax
 cmp DWORD PTR [rsp+144],0
 jne mhf_consume
 cmp QWORD PTR [rsp+80],0
 je mhf_constraints_ok
 test DWORD PTR [rsp+92],20h
 jnz mhf_constraints_ok
 mov ecx,DWORD PTR [r13+216]
 mov r10,QWORD PTR [rsp+80]
 mov r10,QWORD PTR [r10+rcx]
 cmp r10,QWORD PTR [rax+rcx]
 jne mhf_unsupported
 test r10,r10
 jnz mhf_constraints_ok
 ; A NULL loader is trustworthy for source bootstrap types only. It must not
 ; make two not-yet-bound application mirrors look like bootstrap identities.
 mov eax,DWORD PTR [rsp+76]
 cmp eax,DWORD PTR [r13+12]
 jae mhf_unsupported
 shl rax,4
 add rax,QWORD PTR [r13+56]
 cmp DWORD PTR [rax+12],101h
 jne mhf_unsupported
 mov eax,DWORD PTR [rsp+152]
 shl rax,4
 add rax,QWORD PTR [r13+56]
 cmp DWORD PTR [rax+12],101h
 jne mhf_unsupported
mhf_constraints_ok:
 mov eax,DWORD PTR [rsp+164]
 and eax,50DFh
 or eax,40000h
 mov edx,1
 test eax,8
 jz mhf_actual_kind
 inc edx
mhf_actual_kind:
 cmp DWORD PTR [rsp+148],3
 jb mhf_set_kind
 add edx,2
mhf_set_kind:
 shl edx,24
 or eax,edx
 test eax,10h
 jz mhf_flags_ready
 test eax,8
 jnz mhf_trusted_final
 mov ecx,DWORD PTR [rsp+152]
 cmp ecx,DWORD PTR [r13+160]
 jae mhf_unsupported
 mov r10,QWORD PTR [r13+152]
 cmp BYTE PTR [r10+rcx],0
 je mhf_flags_ready
mhf_trusted_final:
 or eax,200000h
mhf_flags_ready:
 ; No write to resolution, name or type, and no target class initializer call.
 mov ecx,DWORD PTR [r13+212]
 mov DWORD PTR [r14+rcx],eax
 mov ecx,DWORD PTR [r13+204]
 mov QWORD PTR [r14+rcx],0
 mov ecx,DWORD PTR [r13+192]
 mov rax,QWORD PTR [rsp+128]
 mov QWORD PTR [r14+rcx],rax
 mov QWORD PTR [rsp+40],r14
 jmp mhf_done
mhf_consume:
 ; Original Java only asks offsets of resolved MemberNames. No new native
 ; binding cell is invented in the empty ResolvedMethodName Java payload.
 mov ecx,DWORD PTR [r13+208]
 cmp QWORD PTR [r14+rcx],0
 jne mhf_unsupported
 mov eax,DWORD PTR [rsp+144]
 cmp eax,4
 je mhf_info
 cmp eax,1
 jne mhf_static_required
 test DWORD PTR [rsp+164],8
 jnz mhf_nonstatic_error
 jmp mhf_return_cookie
mhf_static_required:
 test DWORD PTR [rsp+164],8
 jz mhf_static_error
 cmp eax,3
 je mhf_return_base
mhf_return_cookie:
 mov rax,QWORD PTR [rsp+136]
 mov QWORD PTR [rsp+40],rax
 jmp mhf_done
mhf_return_base:
 mov rax,QWORD PTR [rsp+128]
 mov QWORD PTR [rsp+40],rax
 jmp mhf_done
mhf_info:
 mov rax,QWORD PTR [rsp+136]
 mov QWORD PTR [rsp+272],rax
 mov rcx,rbx
 lea rdx,[rsp+272]
 call QWORD PTR [r13+104]
 cmp DWORD PTR [rbx],0
 jne mhf_done
 test rax,rax
 jz mhf_bad
 mov QWORD PTR [rsp+232],rax
 mov QWORD PTR [rsp+336],2
 mov QWORD PTR [rsp+32],rbx
 mov rcx,r12
 lea rdx,[rsp+336]
 mov r8,QWORD PTR [r13+112]
 mov r9d,1
 call boom_typed_multi_new
 cmp DWORD PTR [rbx],0
 jne mhf_done
 test rax,rax
 jz mhf_oom
 mov r10,QWORD PTR [rsp+232]
 mov QWORD PTR [rax],r10
 mov r10,QWORD PTR [rsp+128]
 mov QWORD PTR [rax+8],r10
 mov QWORD PTR [rsp+40],rax
 jmp mhf_done
mhf_non_field:
 cmp DWORD PTR [rsp+144],0
 je mhf_non_field_resolve
 cmp DWORD PTR [rsp+144],4
 je mhf_unsupported
 cmp DWORD PTR [rsp+144],1
 je mhf_nonstatic_error
 jmp mhf_static_error
mhf_non_field_resolve:
 mov eax,DWORD PTR [rsp+64]
 shr eax,24
 and eax,15
 dec eax
 cmp eax,8
 jbe mhf_unsupported
 xor r8d,r8d
 mov r9d,1
 call mhf_throw
 jmp mhf_done
mhf_nothing:
 mov r8d,1
 mov r9d,2
 call mhf_throw
 jmp mhf_done
mhf_missing:
 cmp DWORD PTR [rsp+144],0
 jne mhf_unsupported
 ; The spec bit must be loaded even when void was rejected before lookup.
 mov rax,QWORD PTR [rsp+48]
 cmp DWORD PTR [rax+24],0
 jne mhf_done
 mov eax,DWORD PTR [rsp+68]
 mov edx,DWORD PTR [rsp+72]
 mov r8,QWORD PTR [rsp+120]
 call mhf_missing_message
 cmp DWORD PTR [rbx],0
 jne mhf_done
 test rax,rax
 jz mhf_bad
 mov r9,rax
 mov r8d,2
 call mhf_throw_oop
 jmp mhf_done
mhf_unresolved_error:
 xor r8d,r8d
 mov r9d,6
 call mhf_throw
 jmp mhf_done
mhf_nonstatic_error:
 xor r8d,r8d
 mov r9d,4
 call mhf_throw
 jmp mhf_done
mhf_static_error:
 xor r8d,r8d
 mov r9d,5
 call mhf_throw
 jmp mhf_done
mhf_unsupported:
 mov DWORD PTR [rbx],20
 jmp mhf_done
mhf_bad:
 mov DWORD PTR [rbx],7
 jmp mhf_done
mhf_oom:
 mov DWORD PTR [rbx],3
mhf_done:
 mov rax,QWORD PTR [rsp+40]
 add rsp,384
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
mhf_service ENDP
