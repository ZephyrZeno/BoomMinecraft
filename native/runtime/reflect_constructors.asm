; VM-owned Constructor32: declaring Class ref0, metadata row8, image pool16,
; override/reserved24Q=0. Metadata descriptor is immutable, no host callbacks.
; CCTR160/1: heapCell8,mirrors16,strings24,typeMap32,layout40,rows48,
; rowCount56D,typeCount60D,ranges64,names72,typeTable80,Class[]tag88,
; ConstructorType96,ClassType104,boxes112,messageOffset120D,targetOffset124D.
; Row96: owner0D,slot4D,modifiers8D,nargs12D,params16Q,exceptions24Q,
; nexceptions32D,flags36D (abstract1,enum2),reserved40..71,
; factory72Q,classState80Q,nameLiteral88D,nameHash92D.
; Site32 CCSP/1: global8,access16,caller24D,operation28D.
option casemap:none
EXTERN boom_heap_contains:PROC
EXTERN boom_heap_alloc:PROC
EXTERN boom_object_new:PROC
EXTERN boom_runtime_type:PROC
EXTERN boom_mirror_typeid:PROC
EXTERN boom_mirror_load:PROC
EXTERN boom_type_assignable:PROC
EXTERN boom_string_allocate:PROC
EXTERN boom_string_load:PROC
EXTERN boom_string_fresh_literal:PROC
EXTERN boom_exception_create:PROC
EXTERN boom_class_ensure32:PROC
PUBLIC boom_constructor_service
.code
; (ctx RCX,argv RDX,site R8,operation R9D)->result, EDX1 preserves nested PC.
boom_constructor_service PROC FRAME
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
    sub rsp,2320
    .allocstack 2320
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov rdi,r8
    mov r15d,r9d
    mov DWORD PTR [rsp+156],0
    mov DWORD PTR [rsp+168],0
    test rbx,rbx
    jz ctor_zero
    cmp DWORD PTR [rbx],0
    jne ctor_zero
    test rsi,rsi
    jz ctor_bad
    test rdi,rdi
    jz ctor_bad
    cmp DWORD PTR [rdi],050534343h
    jne ctor_bad
    cmp DWORD PTR [rdi+4],1
    jne ctor_bad
    cmp r15d,13
    ja ctor_bad
    cmp DWORD PTR [rdi+28],r15d
    jne ctor_bad
    mov r12,QWORD PTR [rdi+8]
    test r12,r12
    jz ctor_bad
    cmp DWORD PTR [r12],052544343h
    jne ctor_bad
    cmp DWORD PTR [r12+4],2
    je ctor_pool_abi_ok
    cmp DWORD PTR [r12+4],1
    jne ctor_bad
ctor_pool_abi_ok:
    mov eax,DWORD PTR [r12+56]
    cmp eax,262144
    ja ctor_bad
    mov eax,DWORD PTR [r12+60]
    dec eax
    cmp eax,16383
    ja ctor_bad
    inc eax
    cmp DWORD PTR [rdi+24],eax
    jae ctor_bad
    mov ecx,8
ctor_pool_reserved:
    cmp QWORD PTR [r12+rcx],0
    je ctor_bad
    add ecx,8
    cmp ecx,56
    jb ctor_pool_reserved
    mov ecx,64
ctor_pool_more:
    cmp QWORD PTR [r12+rcx],0
    je ctor_bad
    add ecx,8
    cmp ecx,120
    jb ctor_pool_more
    mov ecx,128
ctor_pool_zero:
    cmp QWORD PTR [r12+rcx],0
    jne ctor_bad
    add ecx,8
    cmp ecx,160
    jb ctor_pool_zero
    mov rax,QWORD PTR [r12+8]
    mov rax,QWORD PTR [rax]
    test rax,rax
    jz ctor_bad
    mov QWORD PTR [rsp+104],rax
    mov rax,QWORD PTR [rsi]
    mov QWORD PTR [rsp+184],rax
    test rax,rax
    jz ctor_null
    cmp r15d,1
    jbe ctor_lookup
    ; Validate the entire opaque Constructor object before reading its token.
    mov rcx,QWORD PTR [rsp+104]
    mov rdx,rax
    call boom_heap_contains
    test eax,eax
    jz ctor_bad
    mov rax,QWORD PTR [rsp+184]
    mov rdx,QWORD PTR [r12+40]
    cmp QWORD PTR [rax-8],rdx
    jne ctor_bad
    cmp QWORD PTR [rax-16],32
    jne ctor_bad
    cmp DWORD PTR [rax-20],1
    jne ctor_bad
    cmp QWORD PTR [rax+16],r12
    jne ctor_bad
    cmp QWORD PTR [rax+24],0
    jne ctor_bad
    mov r13,QWORD PTR [rax+8]
    mov rax,r13
    sub rax,QWORD PTR [r12+48]
    jc ctor_bad
    xor edx,edx
    mov ecx,96
    div rcx
    test rdx,rdx
    jnz ctor_bad
    cmp eax,DWORD PTR [r12+56]
    jae ctor_bad
    mov r14d,eax
    mov rax,QWORD PTR [rsp+184]
    mov rdx,QWORD PTR [rax]
    mov rcx,QWORD PTR [rsp+104]
    call boom_heap_contains
    test eax,eax
    jz ctor_bad
    mov rax,QWORD PTR [rsp+184]
    mov rdx,QWORD PTR [rax]
    mov rcx,rbx
    mov r8,QWORD PTR [r12+16]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne ctor_zero
    cmp eax,DWORD PTR [r13]
    jne ctor_bad
    cmp r15d,2
    je ctor_invoke
    cmp r15d,3
    je ctor_declaring
    cmp r15d,4
    je ctor_parameters
    cmp r15d,5
    je ctor_exceptions
    cmp r15d,6
    je ctor_modifiers
    cmp r15d,7
    je ctor_count
    cmp r15d,8
    je ctor_varargs
    cmp r15d,9
    je ctor_synthetic
    cmp r15d,10
    je ctor_name
    cmp r15d,11
    je ctor_equals
    cmp r15d,13
    je ctor_to_string
    mov eax,DWORD PTR [r13+92]
    jmp ctor_done
ctor_to_string:
    cmp DWORD PTR [r12+4],2
    jne ctor_bad
    mov rcx,QWORD PTR [rsp+104]
    mov rdx,QWORD PTR [r12+24]
    mov r8d,DWORD PTR [r13+40]
    mov r9,rbx
    call boom_string_fresh_literal
    jmp ctor_done
ctor_declaring:
    mov rax,QWORD PTR [rsp+184]
    mov rax,QWORD PTR [rax]
    jmp ctor_done
ctor_modifiers:
    mov eax,DWORD PTR [r13+8]
    jmp ctor_done
ctor_count:
    mov eax,DWORD PTR [r13+12]
    jmp ctor_done
ctor_varargs:
    mov eax,DWORD PTR [r13+8]
    shr eax,7
    and eax,1
    jmp ctor_done
ctor_synthetic:
    mov eax,DWORD PTR [r13+8]
    shr eax,12
    and eax,1
    jmp ctor_done
ctor_name:
    mov rcx,QWORD PTR [rsp+104]
    mov rdx,QWORD PTR [r12+24]
    mov r8d,DWORD PTR [r13+88]
    mov r9,rbx
    call boom_string_load
    jmp ctor_done
ctor_equals:
    mov rdx,QWORD PTR [rsi+8]
    test rdx,rdx
    jz ctor_zero
    mov QWORD PTR [rsp+88],rdx
    mov rcx,QWORD PTR [rsp+104]
    call boom_heap_contains
    test eax,eax
    jz ctor_bad
    mov rax,QWORD PTR [rsp+88]
    mov rdx,QWORD PTR [r12+40]
    cmp QWORD PTR [rax-8],rdx
    jne ctor_zero
    cmp QWORD PTR [rax-16],32
    jne ctor_bad
    cmp DWORD PTR [rax-20],1
    jne ctor_bad
    cmp QWORD PTR [rax+16],r12
    jne ctor_bad
    cmp QWORD PTR [rax+24],0
    jne ctor_bad
    cmp QWORD PTR [rax+8],r13
    sete al
    movzx eax,al
    jmp ctor_done
ctor_parameters:
    mov eax,DWORD PTR [r13+12]
    mov rdx,QWORD PTR [r13+16]
    jmp ctor_class_array
ctor_exceptions:
    mov eax,DWORD PTR [r13+32]
    mov rdx,QWORD PTR [r13+24]
ctor_class_array:
    cmp eax,65535
    ja ctor_bad
    mov DWORD PTR [rsp+112],eax
    mov QWORD PTR [rsp+176],rdx
    mov r8d,eax
    lea rdx,[rax*8]
    mov rcx,QWORD PTR [rsp+104]
    mov r9,QWORD PTR [r12+88]
    call boom_heap_alloc
    test rax,rax
    jz ctor_oom
    mov QWORD PTR [rsp+120],rax
    mov DWORD PTR [rsp+144],0
ctor_class_array_loop:
    mov ecx,DWORD PTR [rsp+144]
    cmp ecx,DWORD PTR [rsp+112]
    jae ctor_class_array_done
    mov rax,QWORD PTR [rsp+176]
    mov r8d,DWORD PTR [rax+rcx*4]
    cmp r8d,DWORD PTR [r12+60]
    jae ctor_bad
    mov rcx,QWORD PTR [rsp+104]
    mov rdx,QWORD PTR [r12+16]
    mov r9,rbx
    call boom_mirror_load
    cmp DWORD PTR [rbx],0
    jne ctor_zero
    mov ecx,DWORD PTR [rsp+144]
    mov rdx,QWORD PTR [rsp+120]
    mov QWORD PTR [rdx+rcx*8],rax
    inc DWORD PTR [rsp+144]
    jmp ctor_class_array_loop
ctor_class_array_done:
    mov rax,QWORD PTR [rsp+120]
    jmp ctor_done
ctor_lookup:
    mov rcx,QWORD PTR [rsp+104]
    mov rdx,QWORD PTR [rsp+184]
    call boom_heap_contains
    test eax,eax
    jz ctor_bad
    mov rcx,rbx
    mov rdx,QWORD PTR [rsp+184]
    mov r8,QWORD PTR [r12+16]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne ctor_zero
    cmp eax,DWORD PTR [r12+60]
    jae ctor_bad
    mov r14d,eax
    mov DWORD PTR [rsp+80],eax
    mov rax,QWORD PTR [rsi+8]
    mov QWORD PTR [rsp+88],rax
    mov DWORD PTR [rsp+112],0
    test rax,rax
    jz ctor_lookup_validated
    mov rcx,QWORD PTR [rsp+104]
    mov rdx,rax
    call boom_heap_contains
    test eax,eax
    jz ctor_bad
    mov rcx,QWORD PTR [rsp+88]
    mov rdx,QWORD PTR [r12+32]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne ctor_zero
    cmp DWORD PTR [rax+8],3
    jne ctor_bad
    mov rdx,QWORD PTR [r12+104]
    cmp QWORD PTR [rax+16],rdx
    jne ctor_bad
    mov rax,QWORD PTR [rsp+88]
    mov edx,DWORD PTR [rax-20]
    mov DWORD PTR [rsp+112],edx
    mov DWORD PTR [rsp+144],0
ctor_lookup_parameters:
    mov ecx,DWORD PTR [rsp+144]
    cmp ecx,DWORD PTR [rsp+112]
    jae ctor_lookup_validated
    mov rax,QWORD PTR [rsp+88]
    mov rdx,QWORD PTR [rax+rcx*8]
    test rdx,rdx
    jz ctor_lookup_null_parameter
    mov QWORD PTR [rsp+176],rdx
    mov rcx,QWORD PTR [rsp+104]
    call boom_heap_contains
    test eax,eax
    jz ctor_bad
    mov rcx,rbx
    mov rdx,QWORD PTR [rsp+176]
    mov r8,QWORD PTR [r12+16]
    call boom_mirror_typeid
    cmp DWORD PTR [rbx],0
    jne ctor_zero
    jmp ctor_lookup_parameter_id
ctor_lookup_null_parameter:
    mov eax,-1
ctor_lookup_parameter_id:
    mov ecx,DWORD PTR [rsp+144]
    cmp ecx,254
    jae ctor_lookup_parameter_next
    mov DWORD PTR [rsp+rcx*4+256],eax
ctor_lookup_parameter_next:
    inc DWORD PTR [rsp+144]
    jmp ctor_lookup_parameters
ctor_lookup_validated:
    cmp DWORD PTR [rsp+112],254
    ja ctor_missing
    mov rax,QWORD PTR [r12+64]
    mov ecx,DWORD PTR [rax+r14*8]
    cmp ecx,-1
    je ctor_unlinked
    mov edx,DWORD PTR [rax+r14*8+4]
    mov DWORD PTR [rsp+160],edx
    mov eax,ecx
    imul rax,96
    add rax,QWORD PTR [r12+48]
    mov r13,rax
ctor_lookup_rows:
    cmp DWORD PTR [rsp+160],0
    je ctor_missing
    cmp DWORD PTR [r13],r14d
    jne ctor_bad
    cmp r15d,1
    jne ctor_lookup_any
    test DWORD PTR [r13+8],1
    jz ctor_lookup_next
ctor_lookup_any:
    mov eax,DWORD PTR [rsp+112]
    cmp DWORD PTR [r13+12],eax
    jne ctor_lookup_next
    mov rdx,QWORD PTR [r13+16]
    xor ecx,ecx
ctor_lookup_match:
    cmp ecx,DWORD PTR [rsp+112]
    jae ctor_lookup_found
    mov eax,DWORD PTR [rsp+rcx*4+256]
    cmp DWORD PTR [rdx+rcx*4],eax
    jne ctor_lookup_next
    inc ecx
    jmp ctor_lookup_match
ctor_lookup_next:
    add r13,96
    dec DWORD PTR [rsp+160]
    jmp ctor_lookup_rows
ctor_lookup_found:
    mov rcx,QWORD PTR [rsp+104]
    mov rdx,QWORD PTR [r12+40]
    mov r8,rbx
    call boom_object_new
    test rax,rax
    jz ctor_zero
    mov rdx,QWORD PTR [rsp+184]
    mov QWORD PTR [rax],rdx
    mov QWORD PTR [rax+8],r13
    mov QWORD PTR [rax+16],r12
    mov QWORD PTR [rax+24],0
    jmp ctor_done
ctor_missing:
    ; Class.methodToString uses Class.getName, including raw array names.
    mov eax,DWORD PTR [rsp+80]
    shl rax,4
    add rax,QWORD PTR [r12+72]
    mov r14,rax
    mov eax,DWORD PTR [rax+8]
    add rax,9
    mov QWORD PTR [rsp+128],rax
    mov DWORD PTR [rsp+144],0
ctor_missing_size:
    mov ecx,DWORD PTR [rsp+144]
    cmp ecx,DWORD PTR [rsp+112]
    jae ctor_missing_allocate
    call ctor_missing_name
    add QWORD PTR [rsp+128],rcx
    jc ctor_oom
    cmp DWORD PTR [rsp+144],0
    je ctor_missing_size_next
    inc QWORD PTR [rsp+128]
ctor_missing_size_next:
    inc DWORD PTR [rsp+144]
    jmp ctor_missing_size
ctor_missing_allocate:
    mov r8,QWORD PTR [rsp+128]
    cmp r8,07FFFFFFFh
    ja ctor_oom
    mov rcx,QWORD PTR [rsp+104]
    mov rdx,QWORD PTR [r12+24]
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz ctor_zero
    mov QWORD PTR [rsp+200],rax
    mov rdi,QWORD PTR [rax]
    mov rsi,QWORD PTR [r14]
    mov ecx,DWORD PTR [r14+8]
    rep movsw
    mov WORD PTR [rdi],02Eh
    mov WORD PTR [rdi+2],03Ch
    mov WORD PTR [rdi+4],069h
    mov WORD PTR [rdi+6],06Eh
    mov WORD PTR [rdi+8],069h
    mov WORD PTR [rdi+10],074h
    mov WORD PTR [rdi+12],03Eh
    mov WORD PTR [rdi+14],028h
    add rdi,16
    mov DWORD PTR [rsp+144],0
ctor_missing_copy:
    mov ecx,DWORD PTR [rsp+144]
    cmp ecx,DWORD PTR [rsp+112]
    jae ctor_missing_close
    cmp ecx,0
    je ctor_missing_copy_name
    mov WORD PTR [rdi],02Ch
    add rdi,2
ctor_missing_copy_name:
    call ctor_missing_name
    mov rsi,rax
    rep movsw
    inc DWORD PTR [rsp+144]
    jmp ctor_missing_copy
ctor_missing_close:
    mov WORD PTR [rdi],029h
    mov rcx,rbx
    mov edx,26
    xor r8d,r8d
    xor r9d,r9d
    call boom_exception_create
    test rax,rax
    jz ctor_zero
    mov ecx,DWORD PTR [r12+120]
    mov rdx,QWORD PTR [rsp+200]
    mov QWORD PTR [rax+rcx],rdx
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp ctor_zero
ctor_invoke:
    mov rax,QWORD PTR [rdi+16]
    test rax,rax
    jz ctor_bad
    cmp BYTE PTR [rax+r14],0
    jne ctor_access
    test DWORD PTR [r13+36],2
    jnz ctor_argument
    test DWORD PTR [r13+36],1
    jnz ctor_abstract
    cmp QWORD PTR [r13+72],0
    je ctor_unlinked
    mov rcx,QWORD PTR [r13+80]
    test rcx,rcx
    jz ctor_bad
    mov rdx,rbx
    call boom_class_ensure32
    test eax,eax
    jnz ctor_propagate
    mov rax,QWORD PTR [rsi+8]
    mov QWORD PTR [rsp+88],rax
    mov DWORD PTR [rsp+112],0
    test rax,rax
    jz ctor_invoke_count
    mov rcx,QWORD PTR [rsp+104]
    mov rdx,rax
    call boom_heap_contains
    test eax,eax
    jz ctor_bad
    mov rcx,QWORD PTR [rsp+88]
    mov rdx,QWORD PTR [r12+32]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne ctor_zero
    cmp DWORD PTR [rax+8],3
    jne ctor_bad
    mov rax,QWORD PTR [rax+16]
    cmp DWORD PTR [rax+8],0
    je ctor_bad
    mov rax,QWORD PTR [rsp+88]
    mov eax,DWORD PTR [rax-20]
    mov DWORD PTR [rsp+112],eax
ctor_invoke_count:
    mov eax,DWORD PTR [rsp+112]
    cmp eax,DWORD PTR [r13+12]
    jne ctor_argument
    cmp eax,254
    ja ctor_unlinked
    stmxcsr DWORD PTR [rsp+148]
    mov eax,DWORD PTR [rsp+148]
    and eax,0FFFF1F80h
    or eax,01F80h
    mov DWORD PTR [rsp+152],eax
    ldmxcsr DWORD PTR [rsp+152]
    mov DWORD PTR [rsp+156],1
    mov DWORD PTR [rsp+144],0
ctor_invoke_args:
    mov ecx,DWORD PTR [rsp+144]
    cmp ecx,DWORD PTR [rsp+112]
    jae ctor_invoke_call
    mov rax,QWORD PTR [r13+16]
    mov edx,DWORD PTR [rax+rcx*4]
    cmp edx,DWORD PTR [r12+60]
    jae ctor_bad
    mov rax,QWORD PTR [r12+80]
    mov r14,QWORD PTR [rax+rdx*8]
    mov rax,QWORD PTR [rsp+88]
    mov rdx,QWORD PTR [rax+rcx*8]
    mov QWORD PTR [rsp+224],rdx
    cmp DWORD PTR [r14+8],0
    je ctor_invoke_primitive
    test rdx,rdx
    jz ctor_invoke_store
    mov rcx,QWORD PTR [rsp+104]
    call boom_heap_contains
    test eax,eax
    jz ctor_bad
    mov rcx,QWORD PTR [rsp+224]
    mov rdx,QWORD PTR [r12+32]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne ctor_zero
    mov rcx,rax
    mov rdx,r14
    call boom_type_assignable
    test eax,eax
    jz ctor_argument_cast
    mov rdx,QWORD PTR [rsp+224]
    jmp ctor_invoke_store
ctor_invoke_primitive:
    test rdx,rdx
    jz ctor_argument_null
    mov rcx,QWORD PTR [rsp+104]
    call boom_heap_contains
    test eax,eax
    jz ctor_bad
    mov rcx,QWORD PTR [rsp+224]
    mov rdx,QWORD PTR [r12+32]
    mov r8,rbx
    call boom_runtime_type
    cmp DWORD PTR [rbx],0
    jne ctor_zero
    mov r10,QWORD PTR [r12+112]
    xor ecx,ecx
ctor_box_find:
    cmp ecx,8
    jae ctor_argument_cast
    cmp QWORD PTR [r10],rax
    je ctor_box_found
    add r10,32
    inc ecx
    jmp ctor_box_find
ctor_box_found:
    mov rdx,QWORD PTR [rsp+224]
    mov eax,DWORD PTR [r10+8]
    add rdx,rax
    mov r11d,DWORD PTR [r14+12]
    mov ecx,DWORD PTR [r10+16]
    cmp ecx,7
    ja ctor_bad
    cmp r11d,7
    ja ctor_bad
    cmp ecx,0
    je ctor_box_boolean
    cmp ecx,1
    je ctor_box_byte
    cmp ecx,2
    je ctor_box_char
    cmp ecx,3
    je ctor_box_short
    cmp ecx,4
    je ctor_box_int
    cmp ecx,6
    je ctor_box_float
    mov rax,QWORD PTR [rdx]
    jmp ctor_box_value
ctor_box_float:
    mov eax,DWORD PTR [rdx]
    jmp ctor_box_value
ctor_box_boolean:
    movzx eax,BYTE PTR [rdx]
    and eax,1
    jmp ctor_box_value
ctor_box_byte:
    movsx eax,BYTE PTR [rdx]
    jmp ctor_box_value
ctor_box_char:
    movzx eax,WORD PTR [rdx]
    jmp ctor_box_value
ctor_box_short:
    movsx eax,WORD PTR [rdx]
    jmp ctor_box_value
ctor_box_int:
    mov eax,DWORD PTR [rdx]
ctor_box_value:
    cmp ecx,r11d
    je ctor_box_converted
    test ecx,ecx
    jz ctor_argument_cast
    cmp r11d,3
    jb ctor_argument_cast
    je ctor_box_to_short
    cmp r11d,4
    je ctor_box_to_int
    cmp r11d,5
    je ctor_box_to_long
    cmp r11d,6
    je ctor_box_to_float
    cmp r11d,7
    jne ctor_argument_cast
    cmp ecx,6
    ja ctor_argument_cast
    je ctor_box_float_double
    cmp ecx,5
    je ctor_box_long_double
    cvtsi2sd xmm0,eax
    movq rax,xmm0
    jmp ctor_box_converted
ctor_box_long_double:
    cvtsi2sd xmm0,rax
    movq rax,xmm0
    jmp ctor_box_converted
ctor_box_float_double:
    movd xmm0,eax
    cvtss2sd xmm0,xmm0
    movq rax,xmm0
    jmp ctor_box_converted
ctor_box_to_short:
    cmp ecx,1
    jne ctor_argument_cast
    jmp ctor_box_converted
ctor_box_to_int:
    cmp ecx,3
    ja ctor_argument_cast
    jmp ctor_box_converted
ctor_box_to_long:
    cmp ecx,4
    ja ctor_argument_cast
    movsxd rax,eax
    jmp ctor_box_converted
ctor_box_to_float:
    cmp ecx,5
    ja ctor_argument_cast
    je ctor_box_long_float
    cvtsi2ss xmm0,eax
    movd eax,xmm0
    jmp ctor_box_converted
ctor_box_long_float:
    cvtsi2ss xmm0,rax
    movd eax,xmm0
ctor_box_converted:
    mov rdx,rax
ctor_invoke_store:
    mov ecx,DWORD PTR [rsp+144]
    mov QWORD PTR [rsp+rcx*8+256],rdx
    inc DWORD PTR [rsp+144]
    jmp ctor_invoke_args
ctor_invoke_call:
    mov rcx,rbx
    lea rdx,[rsp+256]
    call QWORD PTR [r13+72]
    cmp DWORD PTR [rbx],0
    je ctor_done
    cmp edx,2
    jne ctor_propagate
    cmp DWORD PTR [rbx],16
    jne ctor_propagate
    mov rax,QWORD PTR [rbx+16]
    test rax,rax
    jz ctor_bad
    mov QWORD PTR [rsp+192],rax
    mov DWORD PTR [rbx],0
    mov QWORD PTR [rbx+16],0
    mov rcx,rbx
    mov edx,27
    xor r8d,r8d
    mov r9d,2
    call boom_exception_create
    test rax,rax
    jz ctor_zero
    mov ecx,DWORD PTR [r12+124]
    mov rdx,QWORD PTR [rsp+192]
    mov QWORD PTR [rax+rcx],rdx
    mov ecx,DWORD PTR [r12+120]
    mov QWORD PTR [rax+rcx],0
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp ctor_zero
ctor_access:
    mov DWORD PTR [rbx],25
    jmp ctor_zero
ctor_abstract:
    mov DWORD PTR [rbx],24
    jmp ctor_zero
ctor_argument_null:
    mov edx,4
    jmp ctor_argument_cause
ctor_argument_cast:
    mov edx,12
ctor_argument_cause:
    mov rcx,rbx
    xor r8d,r8d
    xor r9d,r9d
    call boom_exception_create
    test rax,rax
    jz ctor_zero
    mov rcx,rbx
    mov edx,18
    mov r8,rax
    xor r9d,r9d
    call boom_exception_create
    test rax,rax
    jz ctor_zero
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp ctor_zero
ctor_argument:
    mov DWORD PTR [rbx],18
    jmp ctor_zero
ctor_unlinked:
    mov DWORD PTR [rbx],20
    jmp ctor_zero
ctor_oom:
    mov DWORD PTR [rbx],3
    jmp ctor_zero
ctor_null:
    mov DWORD PTR [rbx],4
    jmp ctor_zero
ctor_bad:
    mov DWORD PTR [rbx],7
    jmp ctor_zero
ctor_propagate:
    mov DWORD PTR [rsp+168],1
ctor_zero:
    xor eax,eax
ctor_done:
    cmp DWORD PTR [rsp+156],0
    je ctor_no_fp_restore
    ldmxcsr DWORD PTR [rsp+148]
ctor_no_fp_restore:
    mov edx,DWORD PTR [rsp+168]
    add rsp,2320
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_constructor_service ENDP
; Missing-name helper uses its caller's fixed frame (RSP+8).
; returns immutable UTF16 RAX, length ECX. All nonvolatile registers preserved.
ctor_missing_name PROC
    mov ecx,DWORD PTR [rsp+152]
    mov rax,QWORD PTR [rsp+96]
    mov rax,QWORD PTR [rax+rcx*8]
    test rax,rax
    jz ctor_missing_null_name
    mov eax,DWORD PTR [rax]
    shl rax,4
    add rax,QWORD PTR [r12+72]
    mov ecx,DWORD PTR [rax+8]
    mov rax,QWORD PTR [rax]
    ret
ctor_missing_null_name:
    lea rax,ctor_null_name
    mov ecx,4
    ret
ctor_missing_name ENDP
.code
; Metadata-only virtual calls need no access site. The immutable pool belongs
; to the receiver; the regular service validates it and the complete token.
PUBLIC boom_constructor_virtual
boom_constructor_virtual PROC FRAME
    sub rsp,72
    .allocstack 72
    .endprolog
    test rcx,rcx
    jz ctor_virtual_zero
    cmp DWORD PTR [rcx],0
    jne ctor_virtual_zero
    test rdx,rdx
    jz ctor_virtual_bad
    cmp r9d,3
    jb ctor_virtual_bad
    cmp r9d,13
    ja ctor_virtual_bad
    mov rax,QWORD PTR [rdx]
    test rax,rax
    jz ctor_virtual_null
    cmp QWORD PTR [rax-16],32
    jne ctor_virtual_bad
    cmp DWORD PTR [rax-20],1
    jne ctor_virtual_bad
    mov rax,QWORD PTR [rax+16]
    mov DWORD PTR [rsp+32],050534343h
    mov DWORD PTR [rsp+36],1
    mov QWORD PTR [rsp+40],rax
    mov QWORD PTR [rsp+48],0
    mov DWORD PTR [rsp+56],0
    mov DWORD PTR [rsp+60],r9d
    lea r8,[rsp+32]
    call boom_constructor_service
    jmp ctor_virtual_done
ctor_virtual_null:
    mov DWORD PTR [rcx],4
    jmp ctor_virtual_zero
ctor_virtual_bad:
    mov DWORD PTR [rcx],7
ctor_virtual_zero:
    xor eax,eax
    xor edx,edx
ctor_virtual_done:
    add rsp,72
    ret
boom_constructor_virtual ENDP
.const
ctor_null_name WORD 06Eh,075h,06Ch,06Ch
END
