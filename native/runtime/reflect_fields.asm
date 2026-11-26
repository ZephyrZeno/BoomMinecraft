; VM Field32: declaring Class ref0, immutable row8, image pool16, override24=0.
; FLDS96/1: heapCell8,mirrors16,strings24,typeMap32,layout40,rows48,
; rowCount56D,typeCount60D,typeTable64,ranges72,FieldType80,messageOffset88D,flags92D.
; Row64: owner0D,slot4D,modifiers8D,width12D,fieldType16D,nameLiteral20D,
; reserved24Q,staticCell32Q,nameData40Q,nameLength48D,nameHash52D,
; filtered56D,ownerNameHash60D. Static offset tokens: 424F4F4D:rowIndex.
option casemap:none
EXTERN boom_heap_contains:PROC
EXTERN boom_heap_alloc:PROC
EXTERN boom_mirror_typeid:PROC
EXTERN boom_mirror_load:PROC
EXTERN boom_string_view:PROC
EXTERN boom_string_load:PROC
EXTERN boom_string_fresh_literal:PROC
EXTERN boom_exception_create:PROC
PUBLIC boom_field_service
PUBLIC boom_field_static_address
PUBLIC boom_field_instance_address
.code
; Leaf metadata validation. Preserves argument registers, clobbers RAX/R10/R11.
field_pool_valid PROC
    test r9,r9
    jz field_pool_no
    cmp DWORD PTR [r9],053444C46h
    jne field_pool_no
    cmp DWORD PTR [r9+4],5
    je field_pool_cached
    cmp DWORD PTR [r9+4],4
    je field_pool_cached
    cmp DWORD PTR [r9+4],3
    je field_pool_cached
    cmp DWORD PTR [r9+4],2
    je field_pool_dynamic
    cmp DWORD PTR [r9+4],1
    jne field_pool_no
    jmp field_pool_common
field_pool_cached:
    cmp QWORD PTR [r9+128],0
    je field_pool_no
    cmp QWORD PTR [r9+136],0
    je field_pool_no
field_pool_dynamic:
    cmp QWORD PTR [r9+96],0
    je field_pool_no
    cmp QWORD PTR [r9+104],0
    je field_pool_no
    cmp QWORD PTR [r9+112],0
    je field_pool_no
    cmp DWORD PTR [r9+120],65536
    ja field_pool_no
    cmp DWORD PTR [r9+124],0
    jne field_pool_no
field_pool_common:
    cmp DWORD PTR [r9+92],0
    jne field_pool_no
    cmp DWORD PTR [r9+56],262144
    ja field_pool_no
    mov eax,DWORD PTR [r9+60]
    dec eax
    cmp eax,16383
    ja field_pool_no
    mov r10d,8
field_pool_ptrs:
    cmp QWORD PTR [r9+r10],0
    je field_pool_no
    add r10d,8
    cmp r10d,56
    jb field_pool_ptrs
    cmp QWORD PTR [r9+64],0
    je field_pool_no
    cmp QWORD PTR [r9+72],0
    je field_pool_no
    cmp QWORD PTR [r9+80],0
    je field_pool_no
    mov r10,QWORD PTR [r9+40]
    cmp DWORD PTR [r10],04F424A43h
    jne field_pool_no
    cmp DWORD PTR [r10+4],1
    jne field_pool_no
    cmp QWORD PTR [r10+8],32
    jne field_pool_no
    cmp DWORD PTR [r10+16],1
    jne field_pool_no
    cmp DWORD PTR [r10+20],4
    jne field_pool_no
    mov eax,1
    ret
field_pool_no:
    xor eax,eax
    ret
field_pool_valid ENDP

; (ctx,argv,pool,op): Declared0,Name1,Type2,Modifiers3,DeclaringClass4,
; UnsafeOffset5,UnsafeBase6,Equals7,Hash8,Synthetic9,EnumConstant10.
boom_field_service PROC FRAME
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
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    mov r15d,r9d
    mov DWORD PTR [rsp+52],0
    test rbx,rbx
    jz field_zero
    cmp DWORD PTR [rbx],0
    jne field_zero
    test rsi,rsi
    jz field_bad
    cmp r15d,13
    ja field_bad
    mov r9,rdi
    call field_pool_valid
    test eax,eax
    jz field_bad
    cmp r15d,11
    je field_register_dispatch
    cmp r15d,13
    je field_internal_lookup
    test r15d,r15d
    jz field_lookup
    mov r12,QWORD PTR [rsi]
    cmp r15d,5
    je field_unsafe_argument
    cmp r15d,6
    jne field_token
field_unsafe_argument:
    mov r12,QWORD PTR [rsi+8]
field_token:
    test r12,r12
    jz field_null
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,r12
    call boom_heap_contains
    test eax,eax
    jz field_bad
    mov rax,QWORD PTR [rdi+40]
    cmp QWORD PTR [r12-8],rax
    jne field_bad
    cmp QWORD PTR [r12-16],32
    jne field_bad
    cmp DWORD PTR [r12-20],1
    jne field_bad
    cmp QWORD PTR [r12+16],rdi
    jne field_bad
    cmp QWORD PTR [r12+24],0
    jne field_bad
    mov r13,QWORD PTR [r12+8]
    mov rax,r13
    sub rax,QWORD PTR [rdi+48]
    jc field_bad
    test al,63
    jnz field_bad
    shr rax,6
    mov ecx,DWORD PTR [rdi+56]
    cmp rax,rcx
    jae field_bad
    mov QWORD PTR [rsp+32],rax
    mov rcx,rbx
    mov rdx,QWORD PTR [r12]
    mov r8,QWORD PTR [rdi+16]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne field_zero
    cmp eax,DWORD PTR [r13]
    jne field_bad
    cmp DWORD PTR [r13+56],0
    jne field_bad
    cmp r15d,1
    je field_name
    cmp r15d,2
    je field_type
    cmp r15d,3
    je field_modifiers
    cmp r15d,4
    je field_declaring
    cmp r15d,7
    je field_equals
    cmp r15d,8
    je field_hash
    cmp r15d,9
    je field_synthetic
    cmp r15d,10
    je field_enum
    cmp r15d,12
    je field_to_string
    test DWORD PTR [r13+8],8
    jz field_argument
    cmp QWORD PTR [r13+32],0
    je field_unsupported
    cmp r15d,6
    je field_declaring
    mov rax,0424F4F4D00000000h
    or rax,QWORD PTR [rsp+32]
    jmp field_done
field_name:
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rdi+24]
    mov r8d,DWORD PTR [r13+20]
    mov r9,rbx
    call boom_string_load
    jmp field_done
field_to_string:
    cmp DWORD PTR [rdi+4],4
    jb field_bad
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rdi+24]
    mov r8d,DWORD PTR [r13+24]
    mov r9,rbx
    call boom_string_fresh_literal
    jmp field_done
field_type:
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rdi+16]
    mov r8d,DWORD PTR [r13+16]
    mov r9,rbx
    call boom_mirror_load
    jmp field_done
field_modifiers:
    mov eax,DWORD PTR [r13+8]
    jmp field_done
field_declaring:
    mov rax,QWORD PTR [r12]
    jmp field_done
field_synthetic:
    mov eax,DWORD PTR [r13+8]
    shr eax,12
    and eax,1
    jmp field_done
field_enum:
    mov eax,DWORD PTR [r13+8]
    shr eax,14
    and eax,1
    jmp field_done
field_hash:
    mov eax,DWORD PTR [r13+52]
    xor eax,DWORD PTR [r13+60]
    jmp field_done
field_equals:
    mov r14,QWORD PTR [rsi+8]
    test r14,r14
    jz field_zero
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,r14
    call boom_heap_contains
    test eax,eax
    jz field_bad
    mov rax,QWORD PTR [rdi+40]
    cmp QWORD PTR [r14-8],rax
    jne field_zero
    cmp QWORD PTR [r14-16],32
    jne field_bad
    cmp QWORD PTR [r14+16],rdi
    jne field_bad
    cmp QWORD PTR [r14+24],0
    jne field_bad
    cmp QWORD PTR [r14+8],r13
    sete al
    movzx eax,al
    jmp field_done
field_internal_lookup:
    cmp DWORD PTR [rdi+4],5
    jb field_unsupported
    mov DWORD PTR [rsp+52],1
    add rsi,8
field_lookup:
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi]
    mov r8,QWORD PTR [rdi+16]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne field_zero
    cmp eax,DWORD PTR [rdi+60]
    jae field_bad
    mov r14d,eax
    cmp DWORD PTR [rsp+52],0
    je field_lookup_name
    mov rax,QWORD PTR [rdi+64]
    mov rax,QWORD PTR [rax+r14*8]
    cmp DWORD PTR [rax+8],1
    je field_lookup_name
    cmp DWORD PTR [rax+8],2
    jne field_unsupported
field_lookup_name:
    mov r12,QWORD PTR [rsi+8]
    test r12,r12
    jz field_null
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,r12
    call boom_heap_contains
    test eax,eax
    jz field_bad
    cmp QWORD PTR [r12-16],16
    jne field_bad
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [r12]
    call boom_heap_contains
    test eax,eax
    jz field_bad
    mov rcx,r12
    mov rdx,QWORD PTR [rdi+24]
    mov rdx,QWORD PTR [rdx+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne field_zero
    mov QWORD PTR [rsp+40],rax
    mov DWORD PTR [rsp+48],edx
field_scan_begin:
    cmp DWORD PTR [rsp+52],0
    jne field_scan_ranges
    cmp DWORD PTR [rdi+4],3
    je field_scan_ranges
    cmp DWORD PTR [rdi+4],2
    jne field_scan_ranges
    mov rax,QWORD PTR [rdi+104]
    mov eax,DWORD PTR [rax+r14*4]
    cmp eax,2
    je field_scan_wait
    cmp eax,1
    ja field_bad
    mov DWORD PTR [rsp+32],eax
field_scan_ranges:
    mov rax,QWORD PTR [rdi+72]
    mov ecx,DWORD PTR [rax+r14*8]
    mov r15d,DWORD PTR [rax+r14*8+4]
    cmp ecx,-1
    je field_unindexed
    mov eax,ecx
    add rax,r15
    mov edx,DWORD PTR [rdi+56]
    cmp rax,rdx
    ja field_bad
    shl rcx,6
    add rcx,QWORD PTR [rdi+48]
    mov r13,rcx
    cmp DWORD PTR [rsp+52],0
    jne field_find
    cmp DWORD PTR [rdi+4],3
    jb field_find
field_cache_begin:
    mov r11,QWORD PTR [rdi+136]
    lea r11,[r11+r14*4]
    mov eax,DWORD PTR [r11]
    cmp eax,2
    je field_find
    cmp eax,1
    je field_cache_wait
    test eax,eax
    jnz field_bad
    mov edx,1
    lock cmpxchg DWORD PTR [r11],edx
    jne field_cache_begin
    mov QWORD PTR [rsp+56],r11
field_cache_copy_begin:
    mov rax,QWORD PTR [rdi+104]
    mov r8d,DWORD PTR [rax+r14*4]
    cmp r8d,2
    je field_cache_copy_wait
    cmp r8d,1
    ja field_cache_bad
    mov rax,r13
    sub rax,QWORD PTR [rdi+48]
    shr rax,6
    mov ecx,r15d
    mov r9,QWORD PTR [rdi+96]
    mov r10,QWORD PTR [rdi+128]
field_cache_copy:
    test ecx,ecx
    jz field_cache_copy_done
    mov edx,DWORD PTR [r9+rax*4]
    cmp edx,1
    ja field_cache_bad
    mov DWORD PTR [r10+rax*4],edx
    inc rax
    dec ecx
    jmp field_cache_copy
field_cache_copy_done:
    mov rax,QWORD PTR [rdi+104]
    cmp DWORD PTR [rax+r14*4],r8d
    jne field_cache_copy_begin
    mov r11,QWORD PTR [rsp+56]
    mov eax,2
    xchg DWORD PTR [r11],eax
    jmp field_find
field_cache_bad:
    mov r11,QWORD PTR [rsp+56]
    xor eax,eax
    xchg DWORD PTR [r11],eax
    jmp field_bad
field_cache_wait:
    pause
    jmp field_cache_begin
field_cache_copy_wait:
    pause
    jmp field_cache_copy_begin
field_find:
    test r15d,r15d
    jz field_missing
    cmp DWORD PTR [r13],r14d
    jne field_bad
    cmp DWORD PTR [rsp+52],0
    jne field_find_length
    cmp DWORD PTR [rdi+4],2
    jae field_dynamic_flag
    cmp DWORD PTR [r13+56],0
    jne field_find_next
    jmp field_find_length
field_dynamic_flag:
    mov rax,r13
    sub rax,QWORD PTR [rdi+48]
    shr rax,6
    mov rdx,QWORD PTR [rdi+96]
    cmp DWORD PTR [rdi+4],3
    jb field_flag_source_ready
    mov rdx,QWORD PTR [rdi+128]
field_flag_source_ready:
    mov eax,DWORD PTR [rdx+rax*4]
    cmp eax,1
    ja field_bad
    test eax,eax
    jnz field_find_next
field_find_length:
    mov eax,DWORD PTR [rsp+48]
    cmp eax,DWORD PTR [r13+48]
    jne field_find_next
    mov r10,QWORD PTR [rsp+40]
    mov r11,QWORD PTR [r13+40]
    test r11,r11
    jz field_bad
    xor ecx,ecx
field_compare:
    cmp ecx,eax
    jae field_allocate
    movzx edx,WORD PTR [r10+rcx*2]
    cmp dx,WORD PTR [r11+rcx*2]
    jne field_find_next
    inc ecx
    jmp field_compare
field_find_next:
    add r13,64
    dec r15d
    jmp field_find
field_unindexed:
    mov rax,QWORD PTR [rdi+64]
    mov rax,QWORD PTR [rax+r14*8]
    cmp DWORD PTR [rax+8],1
    je field_unsupported
    cmp DWORD PTR [rax+8],2
    je field_unsupported
    jmp field_missing
field_allocate:
    cmp DWORD PTR [rsp+52],0
    jne field_internal_offset
    cmp DWORD PTR [rdi+4],2
    jne field_allocate_ready
    mov rax,QWORD PTR [rdi+104]
    mov eax,DWORD PTR [rax+r14*4]
    cmp eax,DWORD PTR [rsp+32]
    jne field_scan_begin
field_allocate_ready:
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov edx,32
    mov r8d,1
    mov r9,QWORD PTR [rdi+40]
    call boom_heap_alloc
    test rax,rax
    jz field_oom
    mov rcx,QWORD PTR [rsi]
    mov QWORD PTR [rax],rcx
    mov QWORD PTR [rax+8],r13
    mov QWORD PTR [rax+16],rdi
    jmp field_done
field_internal_offset:
    mov rdx,r13
    sub rdx,QWORD PTR [rdi+48]
    shr rdx,6
    mov rax,0424F4F4900000000h
    test DWORD PTR [r13+8],8
    jz field_internal_offset_ready
    mov rax,0424F4F4D00000000h
field_internal_offset_ready:
    or rax,rdx
    jmp field_done
field_missing:
    cmp DWORD PTR [rsp+52],0
    jne field_internal_missing
    cmp DWORD PTR [rdi+4],2
    jne field_missing_ready
    mov rax,QWORD PTR [rdi+104]
    mov eax,DWORD PTR [rax+r14*4]
    cmp eax,DWORD PTR [rsp+32]
    jne field_scan_begin
field_missing_ready:
    mov rcx,rbx
    mov edx,28
    xor r8d,r8d
    mov r9d,1
    call boom_exception_create
    test rax,rax
    jz field_zero
    mov ecx,DWORD PTR [rdi+88]
    test ecx,7
    jnz field_bad
    mov edx,DWORD PTR [rax-20]
    shl rdx,3
    add rcx,8
    cmp rcx,rdx
    ja field_bad
    sub rcx,8
    mov rdx,QWORD PTR [rsi+8]
    mov QWORD PTR [rax+rcx],rdx
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp field_zero
field_internal_missing:
    mov rcx,rbx
    mov edx,23
    xor r8d,r8d
    mov r9d,1
    call boom_exception_create
    test rax,rax
    jz field_zero
    mov ecx,DWORD PTR [rdi+88]
    test ecx,7
    jnz field_bad
    mov edx,DWORD PTR [rax-20]
    shl rdx,3
    add rcx,8
    cmp rcx,rdx
    ja field_bad
    mov QWORD PTR [rax+rcx-8],0
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp field_zero
field_scan_wait:
    pause
    jmp field_scan_begin
field_register_dispatch:
    mov rcx,rbx
    mov rdx,rsi
    mov r8,rdi
    call boom_field_filter_register
    jmp field_done
field_null:
    mov DWORD PTR [rbx],4
    jmp field_zero
field_argument:
    mov DWORD PTR [rbx],18
    jmp field_zero
field_unsupported:
    mov DWORD PTR [rbx],20
    jmp field_zero
field_bad:
    mov DWORD PTR [rbx],7
    jmp field_zero
field_oom:
    mov DWORD PTR [rbx],3
field_zero:
    xor eax,eax
field_done:
    xor edx,edx
    add rsp,64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_field_service ENDP

; (ctx RCX,Class base RDX,opaque offset R8,FLDS pool R9)->cell RAX,width EDX.
; It does not initialize a class, allocate, or perform an atomic operation itself.
boom_field_static_address PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    push rdi
    .pushreg rdi
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    mov rsi,r9
    mov rdi,r8
    test rbx,rbx
    jz field_address_zero
    cmp DWORD PTR [rbx],0
    jne field_address_zero
    call field_pool_valid
    test eax,eax
    jz field_address_bad
    mov rax,rdi
    shr rax,32
    cmp eax,0424F4F4Dh
    jne field_address_argument
    mov edi,edi
    cmp edi,DWORD PTR [rsi+56]
    jae field_address_argument
    mov r8,QWORD PTR [rsi+16]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne field_address_zero
    shl rdi,6
    add rdi,QWORD PTR [rsi+48]
    cmp eax,DWORD PTR [rdi]
    jne field_address_argument
    test DWORD PTR [rdi+8],8
    jz field_address_argument
    mov eax,DWORD PTR [rdi+16]
    cmp eax,DWORD PTR [rsi+60]
    jae field_address_bad
    mov rcx,QWORD PTR [rsi+64]
    mov rax,QWORD PTR [rcx+rax*8]
    test rax,rax
    jz field_address_bad
    cmp DWORD PTR [rax],054595045h
    jne field_address_bad
    cmp DWORD PTR [rax+4],1
    jne field_address_bad
    cmp DWORD PTR [rax+8],0
    jne field_address_argument
    mov r8d,DWORD PTR [rax+12]
    mov edx,DWORD PTR [rdi+12]
    cmp edx,1
    je field_address_cell
    cmp edx,4
    je field_address_cell
    cmp edx,8
    jne field_address_argument
field_address_cell:
    mov rax,QWORD PTR [rdi+32]
    test rax,rax
    jz field_address_unsupported
    test al,7
    jnz field_address_bad
    jmp field_address_done
field_address_argument:
    mov DWORD PTR [rbx],18
    jmp field_address_zero
field_address_unsupported:
    mov DWORD PTR [rbx],20
    jmp field_address_zero
field_address_bad:
    mov DWORD PTR [rbx],7
field_address_zero:
    xor eax,eax
    xor edx,edx
field_address_done:
    add rsp,32
    pop rdi
    pop rsi
    pop rbx
    ret
boom_field_static_address ENDP

; (ctx RCX,object RDX,BOOI:row cookie R8,pool R9)->cell RAX,width EDX,
; primitive code R8D. The map selects the offset for the actual receiver,
; because adding reference fields in a subclass can move primitive fields.
boom_field_instance_address PROC FRAME
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
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    mov rsi,r9
    mov rdi,rdx
    mov r12,r8
    test rbx,rbx
    jz field_instance_zero
    cmp DWORD PTR [rbx],0
    jne field_instance_zero
    call field_pool_valid
    test eax,eax
    jz field_instance_bad
    cmp DWORD PTR [rsi+4],5
    jb field_instance_unsupported
    mov rax,r12
    shr rax,32
    cmp eax,0424F4F49h
    jne field_instance_argument
    mov r12d,r12d
    cmp r12d,DWORD PTR [rsi+56]
    jae field_instance_argument
    shl r12,6
    add r12,QWORD PTR [rsi+48]
    test DWORD PTR [r12+8],8
    jnz field_instance_argument
    mov eax,DWORD PTR [r12+16]
    cmp eax,DWORD PTR [rsi+60]
    jae field_instance_bad
    mov r13,QWORD PTR [rsi+64]
    mov r13,QWORD PTR [r13+rax*8]
    cmp DWORD PTR [r13],054595045h
    jne field_instance_bad
    cmp DWORD PTR [r13+4],1
    jne field_instance_bad
    cmp DWORD PTR [r13+8],0
    jne field_instance_unsupported
    mov r14d,DWORD PTR [r12+12]
    cmp r14d,1
    je field_instance_width
    cmp r14d,2
    je field_instance_width
    cmp r14d,4
    je field_instance_width
    cmp r14d,8
    jne field_instance_bad
field_instance_width:
    cmp QWORD PTR [r12+32],0
    je field_instance_unsupported
    test rdi,rdi
    jz field_instance_null
    mov rcx,QWORD PTR [rsi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,rdi
    call boom_heap_contains
    test eax,eax
    jz field_instance_bad
    mov rcx,rdi
    mov rdx,rbx
    call QWORD PTR [r12+32]
    cmp DWORD PTR [rbx],0
    jne field_instance_zero
    test rax,rax
    jz field_instance_bad
    mov ecx,DWORD PTR [rdi-20]
    shl rcx,3
    add rcx,rdi
    cmp rax,rcx
    jb field_instance_bad
    mov rcx,rax
    add rcx,r14
    jc field_instance_bad
    mov rdx,QWORD PTR [rdi-16]
    add rdx,rdi
    jc field_instance_bad
    cmp rcx,rdx
    ja field_instance_bad
    lea ecx,[r14d-1]
    test eax,ecx
    jnz field_instance_bad
    mov edx,r14d
    mov r8d,DWORD PTR [r13+12]
    jmp field_instance_done
field_instance_null:
    mov DWORD PTR [rbx],4
    jmp field_instance_zero
field_instance_argument:
    mov DWORD PTR [rbx],18
    jmp field_instance_zero
field_instance_unsupported:
    mov DWORD PTR [rbx],20
    jmp field_instance_zero
field_instance_bad:
    mov DWORD PTR [rbx],7
field_instance_zero:
    xor eax,eax
    xor edx,edx
    xor r8d,r8d
field_instance_done:
    add rsp,32
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_field_instance_address ENDP


; Runtime activation of source-proven Set.of(two String literals) registrations.
; FREG64: method0D,PC4D,target8D,count12D=2,Set12layout16Q,
; e0/e1 offsets24/28D,names32Q (two {UTF16*,lengthD,zeroD}),rows40Q,
; rowCount48D,reserved52D=0,Set12 TypeDesc56Q. No Java callbacks/allocations.
boom_field_filter_register PROC FRAME
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
    sub rsp,64
    .allocstack 64
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    test rbx,rbx
    jz freg_zero
    cmp DWORD PTR [rbx],0
    jne freg_zero
    test rsi,rsi
    jz freg_bad
    mov r9,rdi
    call field_pool_valid
    test eax,eax
    jz freg_bad
    cmp DWORD PTR [rdi+4],2
    jb freg_unsupported
    mov r12,QWORD PTR [rdi+112]
    mov ecx,DWORD PTR [rdi+120]
freg_site:
    test ecx,ecx
    jz freg_bad
    mov eax,DWORD PTR [rbx+8]
    cmp eax,DWORD PTR [r12]
    jne freg_site_next
    mov eax,DWORD PTR [rbx+4]
    cmp eax,DWORD PTR [r12+4]
    je freg_site_found
freg_site_next:
    add r12,64
    dec ecx
    jmp freg_site
freg_site_found:
    cmp DWORD PTR [r12+12],2
    jne freg_bad
    cmp DWORD PTR [r12+52],0
    jne freg_bad
    mov r14d,DWORD PTR [r12+8]
    cmp r14d,DWORD PTR [rdi+60]
    jae freg_bad
    mov rcx,rbx
    mov rdx,QWORD PTR [rsi]
    mov r8,QWORD PTR [rdi+16]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne freg_zero
    cmp eax,r14d
    jne freg_bad
    mov r15,QWORD PTR [rsi+8]
    test r15,r15
    jz freg_null
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,r15
    call boom_heap_contains
    test eax,eax
    jz freg_bad
    mov rax,QWORD PTR [r12+16]
    test rax,rax
    jz freg_bad
    cmp DWORD PTR [rax],04F424A43h
    jne freg_bad
    cmp DWORD PTR [rax+4],2
    jne freg_bad
    cmp QWORD PTR [rax+8],16
    jne freg_bad
    cmp DWORD PTR [rax+16],2
    jne freg_bad
    cmp QWORD PTR [r15-8],rax
    jne freg_bad
    cmp QWORD PTR [r15-16],16
    jne freg_bad
    cmp DWORD PTR [r15-20],2
    jne freg_bad
    xor r13d,r13d
freg_element:
    mov eax,DWORD PTR [r12+r13*4+24]
    cmp eax,8
    ja freg_bad
    test al,7
    jnz freg_bad
    mov rax,QWORD PTR [r15+rax]
    mov QWORD PTR [rsp+32],rax
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,rax
    call boom_heap_contains
    test eax,eax
    jz freg_bad
    mov rax,QWORD PTR [rsp+32]
    cmp QWORD PTR [rax-16],16
    jne freg_bad
    cmp DWORD PTR [rax-20],1
    jne freg_bad
    mov rcx,QWORD PTR [rdi+8]
    mov rcx,QWORD PTR [rcx]
    mov rdx,QWORD PTR [rax]
    call boom_heap_contains
    test eax,eax
    jz freg_bad
    mov rcx,QWORD PTR [rsp+32]
    mov rdx,QWORD PTR [rdi+24]
    mov rdx,QWORD PTR [rdx+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne freg_zero
    mov r10,QWORD PTR [r12+32]
    test r10,r10
    jz freg_bad
    mov ecx,r13d
    shl rcx,4
    add r10,rcx
    cmp edx,DWORD PTR [r10+8]
    jne freg_bad
    cmp DWORD PTR [r10+12],0
    jne freg_bad
    mov r11,QWORD PTR [r10]
    test r11,r11
    jz freg_bad
    xor ecx,ecx
freg_compare:
    cmp ecx,edx
    jae freg_element_next
    movzx r8d,WORD PTR [rax+rcx*2]
    cmp r8w,WORD PTR [r11+rcx*2]
    jne freg_bad
    inc ecx
    jmp freg_compare
freg_element_next:
    inc r13d
    cmp r13d,2
    jb freg_element
    mov ecx,DWORD PTR [r12+48]
    cmp ecx,DWORD PTR [rdi+56]
    ja freg_bad
    mov r10,QWORD PTR [r12+40]
    test r10,r10
    jz freg_bad
    xor r13d,r13d
freg_validate_rows:
    cmp r13d,ecx
    jae freg_claim
    mov eax,DWORD PTR [r10+r13*4]
    cmp eax,DWORD PTR [rdi+56]
    jae freg_bad
    shl rax,6
    add rax,QWORD PTR [rdi+48]
    cmp DWORD PTR [rax],r14d
    jne freg_bad
    inc r13d
    jmp freg_validate_rows
freg_claim:
    mov r15,QWORD PTR [rdi+104]
    lea r15,[r15+r14*4]
    xor eax,eax
    mov edx,2
    lock cmpxchg DWORD PTR [r15],edx
    test eax,eax
    jz freg_publish
    cmp eax,1
    je freg_duplicate
    cmp eax,2
    jne freg_bad
freg_claim_wait:
    pause
    cmp DWORD PTR [r15],2
    je freg_claim_wait
    cmp DWORD PTR [r15],1
    jne freg_bad
    jmp freg_duplicate
freg_publish:
    mov r10,QWORD PTR [r12+40]
    mov r11,QWORD PTR [rdi+96]
    mov ecx,DWORD PTR [r12+48]
    xor r13d,r13d
freg_publish_row:
    cmp r13d,ecx
    jae freg_published
    mov eax,DWORD PTR [r10+r13*4]
    mov DWORD PTR [r11+rax*4],1
    inc r13d
    jmp freg_publish_row
freg_published:
    mov eax,1
    xchg DWORD PTR [r15],eax
    jmp freg_zero
freg_null:
    mov DWORD PTR [rbx],4
    jmp freg_zero
freg_duplicate:
    mov DWORD PTR [rbx],18
    jmp freg_zero
freg_unsupported:
    mov DWORD PTR [rbx],20
    jmp freg_zero
freg_bad:
    mov DWORD PTR [rbx],7
freg_zero:
    xor eax,eax
    xor edx,edx
    add rsp,64
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_field_filter_register ENDP
; Selected Member/Object virtual calls. Dispatch has already checked the
; receiver's VM type; the service revalidates its owning pool and metadata row.
PUBLIC boom_field_virtual
boom_field_virtual PROC
    test rcx,rcx
    jz field_virtual_zero
    cmp DWORD PTR [rcx],0
    jne field_virtual_zero
    test rdx,rdx
    jz field_virtual_bad
    cmp r9d,1
    jb field_virtual_bad
    cmp r9d,12
    ja field_virtual_bad
    cmp r9d,11
    je field_virtual_bad
    cmp r9d,5
    je field_virtual_bad
    cmp r9d,6
    je field_virtual_bad
    mov rax,QWORD PTR [rdx]
    test rax,rax
    jz field_virtual_null
    cmp QWORD PTR [rax-16],32
    jne field_virtual_bad
    cmp DWORD PTR [rax-20],1
    jne field_virtual_bad
    mov r8,QWORD PTR [rax+16]
    jmp boom_field_service
field_virtual_null:
    mov DWORD PTR [rcx],4
    jmp field_virtual_zero
field_virtual_bad:
    mov DWORD PTR [rcx],7
field_virtual_zero:
    xor eax,eax
    xor edx,edx
    ret
boom_field_virtual ENDP
END
