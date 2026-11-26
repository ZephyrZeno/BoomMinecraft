; Normal source-declared field cookies. Context32, Windows x64, no allocation.
; UFMP128: magic/ABI0/4,typeCount8,fieldCount12,heapCell16,ClassPool24,
; RuntimeMap32,UnsafeLayout40,UnsafeBootstrap48,StringLayout56,names64,
; classRanges72,fieldPages80,nameUnits88,pageCount92,valueOff96,coderOff100,
; UnsafeId104,recordBytes108,cookieTag112,reserved120. Pages hold 1024 rows.
; Field64: class0,index4,access8,kind12,nameOffset16,nameLen20,width24,
; flags28(ref1/static2),addressFunction32,reserved40,id48,reserved52/56.
; ABI1 cookies are UFLD:globalID+1. ABI2 uses UFL2:((globalID+1)<<8)|80h.
; Each ABI2 field has its own virtual byte slot, independent of its position
; in a receiver. Original JDK byte/short CAS may align that slot to a DWORD;
; its virtual carrier has zero high bits and touches only the actual field.
option casemap:none
EXTERN boom_heap_contains:PROC
EXTERN boom_object_check:PROC
EXTERN boom_runtime_row:PROC
EXTERN boom_java_class_typeid:PROC
EXTERN boom_threads_id_memory:PROC
PUBLIC boom_java_unsafe_field
PUBLIC boom_java_unsafe_field_address
PUBLIC boom_java_unsafe_memory
.const
uf_widths BYTE 1,1,2,2,4,8,4,8,8
.code
; R13 pool -> boolean, volatile registers only. Metadata must be live/trusted.
uf_pool_valid PROC
 xor eax,eax
 test r13,r13
 jz uf_pool_done
 cmp DWORD PTR [r13],055464D50h
 jne uf_pool_done
 mov ecx,DWORD PTR [r13+4]
 dec ecx
 cmp ecx,1
 ja uf_pool_done
 mov ecx,DWORD PTR [r13+8]
 dec ecx
 cmp ecx,0FFFFFh
 ja uf_pool_done
 mov ecx,DWORD PTR [r13+12]
 dec ecx
 cmp ecx,0FFFFFEh
 ja uf_pool_done
 shr ecx,10
 inc ecx
 cmp ecx,DWORD PTR [r13+92]
 jne uf_pool_done
 mov ecx,DWORD PTR [r13+88]
 dec ecx
 cmp ecx,0FFFFFFh
 ja uf_pool_done
 cmp DWORD PTR [r13+108],64
 jne uf_pool_done
 mov r10,055464C4400000000h
 cmp DWORD PTR [r13+4],1
 je uf_pool_tag_ready
 mov r10,055464C3200000000h
uf_pool_tag_ready:
 cmp QWORD PTR [r13+112],r10
 jne uf_pool_done
 cmp QWORD PTR [r13+120],0
 jne uf_pool_done
 mov ecx,16
uf_pool_pointers:
 cmp QWORD PTR [r13+rcx],0
 je uf_pool_done
 add ecx,8
 cmp ecx,88
 jb uf_pool_pointers
 mov r10,QWORD PTR [r13+24]
 cmp DWORD PTR [r10],04A434C53h
 jne uf_pool_done
 cmp DWORD PTR [r10+4],1
 jne uf_pool_done
 mov ecx,DWORD PTR [r13+8]
 cmp ecx,DWORD PTR [r10+12]
 jne uf_pool_done
 mov r10,QWORD PTR [r13+32]
 cmp DWORD PTR [r10],052545950h
 jne uf_pool_done
 cmp DWORD PTR [r10+4],2
 jne uf_pool_done
 cmp ecx,DWORD PTR [r10+12]
 jne uf_pool_done
 cmp DWORD PTR [r13+104],ecx
 jae uf_pool_done
 mov r10,QWORD PTR [r13+48]
 cmp DWORD PTR [r10],04A554E53h
 jne uf_pool_done
 cmp DWORD PTR [r10+4],1
 jne uf_pool_done
 mov r11,QWORD PTR [r13+16]
 cmp r11,QWORD PTR [r10+32]
 jne uf_pool_done
 mov r11,QWORD PTR [r13+40]
 cmp r11,QWORD PTR [r10+40]
 jne uf_pool_done
 mov r10,QWORD PTR [r13+56]
 cmp DWORD PTR [r10],04F424A43h
 jne uf_pool_done
 cmp DWORD PTR [r10+4],2
 jne uf_pool_done
 mov ecx,DWORD PTR [r13+96]
 test cl,7
 jnz uf_pool_done
 add rcx,8
 mov r11d,DWORD PTR [r10+16]
 shl r11,3
 cmp rcx,r11
 ja uf_pool_done
 mov ecx,DWORD PTR [r13+100]
 cmp rcx,QWORD PTR [r10+8]
 jae uf_pool_done
 cmp rcx,r11
 jb uf_pool_done
 mov eax,1
uf_pool_done:
 ret
uf_pool_valid ENDP

; R13 pool, ECX field ID -> row or NULL. All row identities stay source-bound.
uf_record PROC
 mov r9d,ecx
 cmp ecx,DWORD PTR [r13+12]
 jae uf_record_bad
 mov eax,ecx
 shr eax,10
 mov r10,QWORD PTR [r13+80]
 mov r10,QWORD PTR [r10+rax*8]
 test r10,r10
 jz uf_record_bad
 and ecx,1023
 shl ecx,6
 add r10,rcx
 cmp DWORD PTR [r10+48],r9d
 jne uf_record_bad
 cmp QWORD PTR [r10+40],0
 jne uf_record_bad
 cmp DWORD PTR [r10+52],0
 jne uf_record_bad
 cmp QWORD PTR [r10+56],0
 jne uf_record_bad
 mov eax,DWORD PTR [r10]
 cmp eax,DWORD PTR [r13+8]
 jae uf_record_bad
 mov r11,QWORD PTR [r13+72]
 lea r11,[r11+rax*8]
 mov eax,DWORD PTR [r11]
 add eax,DWORD PTR [r10+4]
 jc uf_record_bad
 cmp eax,r9d
 jne uf_record_bad
 mov eax,DWORD PTR [r10+4]
 cmp eax,DWORD PTR [r11+4]
 jae uf_record_bad
 cmp DWORD PTR [r10+8],0FFFFh
 ja uf_record_bad
 mov eax,DWORD PTR [r10+12]
 dec eax
 cmp eax,8
 ja uf_record_bad
 lea r11,uf_widths
 movzx ecx,BYTE PTR [r11+rax]
 cmp ecx,DWORD PTR [r10+24]
 jne uf_record_bad
 xor ecx,ecx
 cmp eax,8
 sete cl
 mov edx,DWORD PTR [r10+8]
 and edx,8
 shr edx,2
 or ecx,edx
 cmp ecx,DWORD PTR [r10+28]
 jne uf_record_bad
 mov ecx,DWORD PTR [r10+20]
 dec ecx
 cmp ecx,65534
 ja uf_record_bad
 inc ecx
 mov eax,DWORD PTR [r10+16]
 add rax,rcx
 mov ecx,DWORD PTR [r13+88]
 cmp rax,rcx
 ja uf_record_bad
 mov rax,r10
 ret
uf_record_bad:
 xor eax,eax
 ret
uf_record ENDP

; Native objectFieldOffset1(Context32,argv*,pool,op0) -> opaque long cookie.
; argv = Unsafe receiver, canonical Class mirror, normal Java String.
boom_java_unsafe_field PROC FRAME
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
 mov r12,rdx
 mov r13,r8
 mov DWORD PTR [rsp+32],r9d
 test rbx,rbx
 jz uf_zero
 cmp DWORD PTR [rbx],0
 jne uf_zero
 call uf_pool_valid
 test eax,eax
 jz uf_bad
 cmp DWORD PTR [rsp+32],0
 jne uf_bad
 mov r10,QWORD PTR [r13+48]
 cmp DWORD PTR [r10+8],2
 jne uf_unbound
 test r12,r12
 jz uf_bad
 mov rsi,QWORD PTR [r12]
 test rsi,rsi
 jz uf_null
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz uf_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+40]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz uf_zero
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+32]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz uf_zero
 mov ecx,DWORD PTR [r13+104]
 cmp ecx,DWORD PTR [rax+16]
 jne uf_bad
 mov r8,QWORD PTR [r12+8]
 test r8,r8
 jz uf_null
 mov rcx,rbx
 mov rdx,QWORD PTR [r13+24]
 call boom_java_class_typeid
 cmp eax,0FFFFFFFFh
 je uf_zero
 cmp eax,DWORD PTR [r13+8]
 jae uf_bad
 mov DWORD PTR [rsp+40],eax
 mov rsi,QWORD PTR [r12+16]
 test rsi,rsi
 jz uf_null
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz uf_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+56]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz uf_zero
 mov ecx,DWORD PTR [r13+100]
 movzx edi,BYTE PTR [rsi+rcx]
 cmp edi,1
 ja uf_bad
 mov DWORD PTR [rsp+32],edi
 mov ecx,DWORD PTR [r13+96]
 mov r14,QWORD PTR [rsi+rcx]
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz uf_bad
 cmp QWORD PTR [r14-8],264
 jne uf_bad
 cmp DWORD PTR [r14-20],0
 jne uf_bad
 mov r15,QWORD PTR [r14-16]
 cmp r15,07FFFFFFFh
 ja uf_bad
 test edi,edi
 jz uf_name_ready
 test r15b,1
 jnz uf_bad
 shr r15,1
uf_name_ready:
 mov eax,DWORD PTR [rsp+40]
 mov r10,QWORD PTR [r13+72]
 mov esi,DWORD PTR [r10+rax*8]
 mov edi,DWORD PTR [r10+rax*8+4]
 add rdi,rsi
 mov eax,DWORD PTR [r13+12]
 cmp rdi,rax
 ja uf_bad
uf_find:
 cmp rsi,rdi
 jae uf_missing
 mov ecx,esi
 call uf_record
 test rax,rax
 jz uf_bad
 cmp DWORD PTR [rax+20],r15d
 jne uf_next
 mov ecx,DWORD PTR [rax+16]
 mov rdx,QWORD PTR [r13+64]
 lea rdx,[rdx+rcx*2]
 xor ecx,ecx
uf_compare:
 cmp ecx,r15d
 jae uf_found
 cmp DWORD PTR [rsp+32],0
 jne uf_compare_word
 movzx eax,BYTE PTR [r14+rcx]
 jmp uf_compare_unit
uf_compare_word:
 movzx eax,WORD PTR [r14+rcx*2]
uf_compare_unit:
 cmp ax,WORD PTR [rdx+rcx*2]
 jne uf_next
 inc ecx
 jmp uf_compare
uf_next:
 inc esi
 jmp uf_find
uf_found:
 lea eax,[rsi+1]
 cmp DWORD PTR [r13+4],1
 je uf_found_tag
 shl eax,8
 or eax,80h
uf_found_tag:
 or rax,QWORD PTR [r13+112]
 jmp uf_done
uf_missing:
 mov DWORD PTR [rbx],23
 jmp uf_zero
uf_unbound:
 mov DWORD PTR [rbx],20
 jmp uf_zero
uf_null:
 mov DWORD PTR [rbx],4
 jmp uf_zero
uf_bad:
 mov DWORD PTR [rbx],7
uf_zero:
 xor eax,eax
uf_done:
 add rsp,48
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_unsafe_field ENDP

; address(Context32 RCX,pool RDX,object R8,cookie R9) -> checked address.
; No static/base/off-heap/array address is silently accepted by this helper.
boom_java_unsafe_field_address PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r13
 .pushreg r13
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov r13,rdx
 mov rsi,r8
 mov rdi,r9
 test rbx,rbx
 jz ufa_zero
 cmp DWORD PTR [rbx],0
 jne ufa_zero
 call uf_pool_valid
 test eax,eax
 jz ufa_bad
 mov r10,QWORD PTR [r13+48]
 cmp DWORD PTR [r10+8],2
 jne ufa_unbound
 test rsi,rsi
 jz ufa_null
 mov rax,rdi
 xor rax,QWORD PTR [r13+112]
 shr rax,32
 test rax,rax
 jnz ufa_bad
 mov ecx,edi
 cmp DWORD PTR [r13+4],1
 je ufa_decode_id
 mov eax,ecx
 and eax,255
 cmp eax,80h                    ; this helper resolves the exact field anchor
 jne ufa_bad
 shr ecx,8
ufa_decode_id:
 sub ecx,1
 jc ufa_bad
 call uf_record
 test rax,rax
 jz ufa_bad
 test DWORD PTR [rax+28],2
 jnz ufa_unbound
 mov rdi,QWORD PTR [rax+32]
 test rdi,rdi
 jz ufa_unbound
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz ufa_bad
 mov rcx,rsi
 mov rdx,rbx
 call rdi
 jmp ufa_done
ufa_unbound:
 mov DWORD PTR [rbx],20
 jmp ufa_zero
ufa_null:
 mov DWORD PTR [rbx],4
 jmp ufa_zero
ufa_bad:
 mov DWORD PTR [rbx],7
ufa_zero:
 xor eax,eax
ufa_done:
 add rsp,40
 pop r13
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_unsafe_field_address ENDP

; Typed heap memory, same UFMP128 metadata, raw managed argument/result slots.
; op=(action<<4)|kind, kind 1..9 uses Field64 kinds. actions: plain get0,
; put1, volatile get2, put3, compareAndSet4, compareAndExchange5 (I/J/ref only).
; argv: Unsafe receiver, object/array, field cookie/array byte offset, value or
; expected, desired. Null base/off-heap and static cookies stay unprovided.
; No GC can run concurrently: the current collector contract is quiescence.
boom_java_unsafe_memory PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push rbp
 .pushreg rbp
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
 mov r12,rdx
 mov r13,r8
 mov r14d,r9d
 and r14d,15
 mov r15d,r9d
 shr r15d,4
 mov DWORD PTR [rsp+32],0        ; ABI2 displacement within a declared field
 mov DWORD PTR [rsp+48],0        ; narrow field projected into a DWORD carrier
 test rbx,rbx
 jz um_zero
 cmp DWORD PTR [rbx],0
 jne um_zero
 call uf_pool_valid
 test eax,eax
 jz um_bad
 mov eax,r14d
 dec eax
 cmp eax,8
 ja um_bad
 cmp r15d,5
 ja um_bad
 cmp r15d,4
 jb um_width
 cmp r14d,5
 je um_width
 cmp r14d,6
 je um_width
 cmp r14d,9
 jne um_bad
um_width:
 lea r10,uf_widths
 movzx ebp,BYTE PTR [r10+rax]
 mov r10,QWORD PTR [r13+48]
 cmp DWORD PTR [r10+8],2
 jne um_unbound
 test r12,r12
 jz um_bad
 mov rsi,QWORD PTR [r12]
 test rsi,rsi
 jz um_null
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz um_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+40]
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz um_zero
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+32]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz um_zero
 mov ecx,DWORD PTR [r13+104]
 cmp ecx,DWORD PTR [rax+16]
 jne um_bad
 mov rsi,QWORD PTR [r12+8]
 test rsi,rsi
 jz um_vm_counter
 mov rax,QWORD PTR [r12+16]
 xor rax,QWORD PTR [r13+112]
 shr rax,32
 test rax,rax
 jnz um_array
 mov ecx,DWORD PTR [r12+16]
 cmp DWORD PTR [r13+4],1
 je um_decode_id
 mov eax,ecx
 and eax,255
 sub eax,80h
 cmp eax,7                      ; unsigned rejects negative displacement too
 ja um_bad
 mov DWORD PTR [rsp+32],eax
 shr ecx,8
um_decode_id:
 sub ecx,1
 jc um_bad
 call uf_record
 test rax,rax
 jz um_bad
 test DWORD PTR [rax+28],2
 jnz um_unbound
 cmp DWORD PTR [r13+4],2
 je um_virtual_field
 cmp ebp,DWORD PTR [rax+24]
 jne um_bad
 cmp r14d,9
 je um_field_reference
 test DWORD PTR [rax+28],1
 jnz um_bad
 jmp um_field_address
um_field_reference:
 test DWORD PTR [rax+28],1
 jz um_bad
 jmp um_field_address
um_virtual_field:
 cmp r14d,9
 je um_virtual_reference
 test DWORD PTR [rax+28],1       ; primitive views never read GC reference slots
 jnz um_bad
 mov ecx,DWORD PTR [rsp+32]
 mov edx,ecx
 add edx,ebp
 cmp edx,DWORD PTR [rax+24]
 jbe um_field_address
 ; A source byte/short field is a complete virtual DWORD for the JDK's
 ; original compareAndExchangeByte/Short Java loop. Physical padding and
 ; adjacent fields are not part of this carrier, even at an object tail.
 test ecx,ecx
 jnz um_bad
 cmp r14d,5
 jne um_bad
 mov ecx,DWORD PTR [rax+24]
 cmp ecx,1
 je um_narrow_carrier
 cmp ecx,2
 jne um_bad
um_narrow_carrier:
 mov ebp,ecx
 mov DWORD PTR [rsp+48],1
 jmp um_field_address
um_virtual_reference:
 cmp DWORD PTR [rsp+32],0
 jne um_bad
 cmp DWORD PTR [rax+24],8
 jne um_bad
 test DWORD PTR [rax+28],1
 jz um_bad
um_field_address:
 mov rcx,rbx
 mov rdx,r13
 mov r8,rsi
 mov r9,QWORD PTR [r12+16]
 cmp DWORD PTR [r13+4],1
 je um_anchor_ready
 and r9,-256
 or r9,80h
um_anchor_ready:
 call boom_java_unsafe_field_address
 test rax,rax
 jz um_zero
 mov rdi,rax
 mov eax,DWORD PTR [rsp+32]
 add rdi,rax
 jmp um_address_ready
um_array:
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 mov rdx,rsi
 call boom_heap_contains
 test eax,eax
 jz um_bad
 mov rcx,rsi
 mov rdx,QWORD PTR [r13+32]
 mov r8,rbx
 call boom_runtime_row
 test rax,rax
 jz um_zero
 cmp r14d,9
 je um_reference_array
 cmp DWORD PTR [rax+20],1
 jne um_unbound
 cmp DWORD PTR [rsi-20],0
 jne um_bad
 jmp um_array_range
um_reference_array:
 cmp DWORD PTR [rax+20],2
 jne um_bad
 mov ecx,DWORD PTR [rsi-20]
 shl rcx,3
 cmp rcx,QWORD PTR [rsi-16]
 jne um_bad
um_array_range:
 mov rdi,QWORD PTR [r12+16]
 test rdi,rdi
 js um_bad
 cmp rdi,QWORD PTR [rsi-16]
 ja um_bad
 lea rax,[rdi+rbp]
 cmp rax,QWORD PTR [rsi-16]
 ja um_bad
 cmp r14d,9
 jne um_array_address
 test dil,7
 jnz um_bad
um_array_address:
 add rdi,rsi
um_address_ready:
 ; Scalar plain byte views may be unaligned; atomic/volatile access must be
 ; naturally aligned. Unsupported unaligned atomic views fail explicitly.
 cmp r15d,2
 jb um_reference_inputs
 lea eax,[rbp-1]
 test rdi,rax
 jnz um_unbound
um_reference_inputs:
 cmp r14d,9
 jne um_operation
 cmp r15d,4
 jae um_both_references
 cmp r15d,1
 je um_one_reference
 cmp r15d,3
 jne um_operation
um_one_reference:
 mov DWORD PTR [rsp+32],24
 jmp um_check_reference
um_both_references:
 mov DWORD PTR [rsp+32],32
um_check_reference:
 mov ecx,DWORD PTR [rsp+32]
 mov rdx,QWORD PTR [r12+rcx]
 test rdx,rdx
 jz um_reference_next
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 call boom_heap_contains
 test eax,eax
 jz um_bad
um_reference_next:
 cmp DWORD PTR [rsp+32],32
 jne um_operation
 mov DWORD PTR [rsp+32],24
 jmp um_check_reference
um_operation:
 cmp r15d,4
 jae um_compare_exchange
 cmp r15d,1
 je um_store
 cmp r15d,3
 je um_store
 test r15d,r15d
 jz um_load
 ; Conservative sequential consistency before optimizing memory barriers.
 mfence
um_load:
 cmp ebp,8
 je um_load8
 cmp ebp,4
 je um_load4
 cmp ebp,2
 je um_load2
 movzx eax,BYTE PTR [rdi]
 jmp um_loaded
um_load2:
 movzx eax,WORD PTR [rdi]
 jmp um_loaded
um_load4:
 mov eax,DWORD PTR [rdi]
 jmp um_loaded
um_load8:
 mov rax,QWORD PTR [rdi]
um_loaded:
 cmp r15d,2
 jne um_normalize
 mfence
um_normalize:
 cmp r14d,1
 je um_boolean
 cmp r14d,2
 je um_byte
 cmp r14d,4
 je um_short
 cmp r14d,5
 je um_int
 cmp r14d,9
 je um_result_reference
 jmp um_done
um_boolean:
 test eax,eax
 setne al
 movzx eax,al
 jmp um_done
um_byte:
 movsx rax,al
 jmp um_done
um_short:
 movsx rax,ax
 jmp um_done
um_int:
 movsxd rax,eax
 jmp um_done
um_result_reference:
 test rax,rax
 jz um_done
 mov QWORD PTR [rsp+40],rax
 mov rdx,rax
 mov rcx,QWORD PTR [r13+16]
 mov rcx,QWORD PTR [rcx]
 call boom_heap_contains
 test eax,eax
 jz um_bad
 mov rax,QWORD PTR [rsp+40]
 jmp um_done
um_store:
 mov rdx,QWORD PTR [r12+24]
 cmp DWORD PTR [rsp+48],0
 je um_store_input_ready
 mov edx,edx                    ; a Java int slot has only 32 significant bits
 mov ecx,ebp
 shl ecx,3
 mov rax,rdx
 shr rax,cl
 test rax,rax
 jnz um_unbound                 ; the virtual carrier's padding stays zero
um_store_input_ready:
 cmp r14d,1
 jne um_store_width
 and edx,1
um_store_width:
 cmp r15d,3
 je um_store_volatile
 cmp ebp,8
 je um_store8
 cmp ebp,4
 je um_store4
 cmp ebp,2
 je um_store2
 mov BYTE PTR [rdi],dl
 jmp um_zero
um_store2:
 mov WORD PTR [rdi],dx
 jmp um_zero
um_store4:
 mov DWORD PTR [rdi],edx
 jmp um_zero
um_store8:
 mov QWORD PTR [rdi],rdx
 jmp um_zero
um_store_volatile:
 cmp ebp,8
 je um_xchg8
 cmp ebp,4
 je um_xchg4
 cmp ebp,2
 je um_xchg2
 xchg BYTE PTR [rdi],dl
 jmp um_zero
um_xchg2:
 xchg WORD PTR [rdi],dx
 jmp um_zero
um_xchg4:
 xchg DWORD PTR [rdi],edx
 jmp um_zero
um_xchg8:
 xchg QWORD PTR [rdi],rdx
 jmp um_zero
um_compare_exchange:
 mov rax,QWORD PTR [r12+24]
 mov rdx,QWORD PTR [r12+32]
 cmp DWORD PTR [rsp+48],0
 je um_compare_width
 mov eax,eax
 mov edx,edx
 mov ecx,ebp
 shl ecx,3
 mov r9,rax
 shr r9,cl
 test r9,r9
 jnz um_virtual_compare_mismatch
 mov r9,rdx
 shr r9,cl
 test r9,r9
 jnz um_unbound
um_compare_width:
 cmp ebp,1
 je um_cmpxchg1
 cmp ebp,2
 je um_cmpxchg2
 cmp ebp,4
 jne um_cmpxchg8
 lock cmpxchg DWORD PTR [rdi],edx
 jmp um_exchanged
um_cmpxchg8:
 lock cmpxchg QWORD PTR [rdi],rdx
 jmp um_exchanged
um_cmpxchg1:
 lock cmpxchg BYTE PTR [rdi],dl
 movzx eax,al                   ; MOVZX preserves the CMPXCHG ZF
 jmp um_exchanged
um_cmpxchg2:
 lock cmpxchg WORD PTR [rdi],dx
 movzx eax,ax
 jmp um_exchanged
um_virtual_compare_mismatch:
 ; Nonzero expected padding cannot match the virtual zero bits. A locked
 ; same-value CAS reads the actual field without changing any byte, while
 ; retaining the ordering of the normal compare/exchange path.
 cmp ebp,1
 jne um_virtual_compare_mismatch2
 lock cmpxchg BYTE PTR [rdi],al
 movzx eax,al
 jmp um_virtual_mismatch_observed
um_virtual_compare_mismatch2:
 lock cmpxchg WORD PTR [rdi],ax
 movzx eax,ax
um_virtual_mismatch_observed:
 cmp r15d,4
 je um_zero
 jmp um_done
um_exchanged:
 ; Preserve the instruction's ZF until the boolean result is captured.
 setz dl
 cmp r15d,4
 jne um_normalize
 movzx eax,dl
 jmp um_done
um_vm_counter:
 ; Only normal Long reads/CAS/exchange can address the live VM-owned counter.
 ; Receiver validation above is shared with the unchanged heap memory domain.
 cmp r14d,6
 jne um_unbound
 mov rcx,rbx
 mov rdx,r12
 mov r8d,r15d
 mov r9,QWORD PTR [r13+16]
 mov r9,QWORD PTR [r9]
 call boom_threads_id_memory
 jmp um_done
um_unbound:
 mov DWORD PTR [rbx],20
 jmp um_zero
um_null:
 mov DWORD PTR [rbx],4
 jmp um_zero
um_bad:
 mov DWORD PTR [rbx],7
um_zero:
 xor eax,eax
um_done:
 add rsp,56
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rdi
 pop rsi
 pop rbx
 ret
boom_java_unsafe_memory ENDP
END
