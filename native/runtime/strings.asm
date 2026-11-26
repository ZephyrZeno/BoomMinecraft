; Bootstrap immutable UTF-16 strings. Handwritten MASM, no host runtime.
; String payload: char[] value QWORD0, hash DWORD8, hashComputed DWORD12.
; Its exact object layout has payload16/ref-prefix1/fields2. OpenJDK field layout
; is not exposed: unimplemented String constructors/methods and reflection reject.
; Pool ABI2 (56 bytes): magic0 abi4 lock8 count16 roots24 entries32 layout40 heap48.
; Entries ABI1 (16 bytes): immutable UTF16 pointer0, unit count DWORD8, reserved12.
; ABI3 extends this pool for dynamic interning; see string_dynamic.asm.
; All roots live with the module. GC remains quiescent and explicit.
option casemap:none
EXTERN boom_array_new:PROC
EXTERN boom_object_new:PROC
EXTERN boom_string_intern:PROC
EXTERN boom_unicode_equals_ci:PROC
EXTERN boom_string_allocate:PROC
EXTERN boom_heap_contains:PROC
PUBLIC boom_string_load
PUBLIC boom_string_intrinsic
PUBLIC boom_string_view
.code

; load(heap RCX,pool RDX,index R8D,Context16 R9)->String/NULL.
boom_string_load PROC FRAME
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
    sub rsp, 48
    .allocstack 48
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov rdi, r9
    test rbx, rbx
    jz string_pool_invalid
    cmp DWORD PTR [rbx], 048454150h
    jne string_pool_invalid
    cmp DWORD PTR [rbx+4], 1
    jne string_pool_invalid
    test rsi, rsi
    jz string_pool_invalid
    cmp DWORD PTR [rsi], 053545250h
    jne string_pool_invalid
    cmp DWORD PTR [rsi+4], 2
    je string_pool_abi_ok
    cmp DWORD PTR [rsi+4], 3
    jne string_pool_invalid
string_pool_abi_ok:
    cmp DWORD PTR [rsi+16], 65536
    ja string_pool_invalid
    cmp r8d, DWORD PTR [rsi+16]
    jae string_pool_invalid
    mov r12, QWORD PTR [rsi+24]
    test r12, r12
    jz string_pool_invalid
    lea r12, [r12+r8*8]
    mov r13, QWORD PTR [rsi+32]
    test r13, r13
    jz string_pool_invalid
    shl r8, 4
    add r13, r8
    cmp DWORD PTR [r13+8], 65535
    ja string_pool_invalid
    cmp QWORD PTR [r13], 0
    je string_pool_invalid
    mov rax, QWORD PTR [rsi+40]
    test rax, rax
    jz string_pool_invalid
    cmp DWORD PTR [rax], 04F424A43h
    jne string_pool_invalid
    cmp DWORD PTR [rax+4], 1
    jne string_pool_invalid
    cmp QWORD PTR [rax+8], 16
    jne string_pool_invalid
    cmp DWORD PTR [rax+16], 1
    jne string_pool_invalid
    cmp DWORD PTR [rax+20], 2
    jne string_pool_invalid
    ; Hot immutable roots need no lock. x86-64 aligned pointer publication keeps
    ; all earlier payload stores visible; the pool never changes heap or roots.
    cmp QWORD PTR [rsi+48], rbx
    jne string_pool_lock
    mov r15, QWORD PTR [r12]
    test r15, r15
    jnz string_pool_return
string_pool_lock:
    mov eax, 1
    xchg DWORD PTR [rsi+8], eax
    test eax, eax
    jz string_pool_owned
string_pool_spin:
    pause
    cmp DWORD PTR [rsi+8], 0
    jne string_pool_spin
    jmp string_pool_lock
string_pool_owned:
    mov rax, QWORD PTR [rsi+48]
    test rax, rax
    jz string_pool_bind
    cmp rax, rbx
    jne string_pool_wrong_heap
    jmp string_pool_bound
string_pool_bind:
    mov QWORD PTR [rsi+48], rbx
string_pool_bound:
    mov r15, QWORD PTR [r12]
    test r15, r15
    jnz string_pool_unlock
    mov rcx, rbx
    mov edx, DWORD PTR [r13+8]
    mov r8d, 5
    mov r9, rdi
    call boom_array_new
    test rax, rax
    jz string_pool_failed
    mov r14, rax
    mov rcx, rbx
    mov rdx, QWORD PTR [rsi+40]
    mov r8, rdi
    call boom_object_new
    test rax, rax
    jz string_pool_failed
    mov r15, rax
    mov QWORD PTR [rsp+32], rsi
    mov QWORD PTR [rsp+40], rdi
    mov ecx, DWORD PTR [r13+8]
    mov rsi, QWORD PTR [r13]
    mov rdi, r14
    rep movsw
    mov rsi, QWORD PTR [rsp+32]
    mov rdi, QWORD PTR [rsp+40]
    mov QWORD PTR [r15], r14
    ; Publish only after the immutable payload and zero hash state are complete.
    mov QWORD PTR [r12], r15
    jmp string_pool_unlock
string_pool_failed:
    xor r15d, r15d
    jmp string_pool_unlock
string_pool_wrong_heap:
    mov DWORD PTR [rdi], 7
    xor r15d, r15d
string_pool_unlock:
    mov DWORD PTR [rsi+8], 0
string_pool_return:
    mov rax, r15
    jmp string_pool_done
string_pool_invalid:
    mov DWORD PTR [rdi], 7
    xor eax, eax
string_pool_done:
    add rsp, 48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_load ENDP

; private value(String RCX,expected layout RDX,context R8)->char[] RAX,length EDX.
; All nonnull values are trusted typed heap pointers, not arbitrary addresses.
boom_string_view PROC
    test rcx, rcx
    jz string_value_null
    test rdx, rdx
    jz string_value_invalid
    cmp DWORD PTR [rdx], 04F424A43h
    jne string_value_invalid
    cmp DWORD PTR [rdx+4], 1
    jne string_value_invalid
    cmp QWORD PTR [rdx+8], 16
    jne string_value_invalid
    cmp DWORD PTR [rdx+16], 1
    jne string_value_invalid
    cmp DWORD PTR [rdx+20], 2
    jne string_value_invalid
    mov eax, DWORD PTR [rcx-24]
    and eax, 0FFFFFFFDh
    cmp eax, 0B00B0001h
    jne string_value_invalid
    cmp QWORD PTR [rcx-8], rdx
    jne string_value_invalid
    cmp QWORD PTR [rcx-16], 16
    jne string_value_invalid
    cmp DWORD PTR [rcx-20], 1
    jne string_value_invalid
    mov rax, QWORD PTR [rcx]
    test rax, rax
    jz string_value_invalid
    mov edx, DWORD PTR [rax-24]
    and edx, 0FFFFFFFDh
    cmp edx, 0B00B0001h
    jne string_value_invalid
    cmp QWORD PTR [rax-8], 261
    jne string_value_invalid
    cmp DWORD PTR [rax-20], 0
    jne string_value_invalid
    mov rdx, QWORD PTR [rax-16]
    test dl, 1
    jnz string_value_invalid
    ; The entire current Java heap is bounded to one GiB.
    cmp rdx, 07FFFFFFFh
    ja string_value_invalid
    shr edx, 1
    ret
string_value_null:
    mov DWORD PTR [r8], 4
    jmp string_value_fail
string_value_invalid:
    mov DWORD PTR [r8], 7
string_value_fail:
    xor eax, eax
    xor edx, edx
    ret
boom_string_view ENDP

; intrinsic(Context16 RCX,argv64 RDX,pool R8,operation R9D)->RAX.
; operations: length0 empty1 charAt2 hash3 equals4 compare5 toString6 intern7 equalsCI8,
; code-point indexOf9/from10, substring11/range12, lastIndexOf13/from14;
; string indexOf15/from16 and lastIndexOf17/from18 (UTF-16 unit indices), trim19,
; codePointAt20 combines a valid surrogate pair at its UTF-16 unit index;
; regionMatches21 / boolean regionMatches22 compare bounded UTF-16 regions.
; coder23 is the source-checked, package-only UTF16 storage property.
; ABI2 programs create only literals; ABI3 also supports immutable dynamic values.
boom_string_intrinsic PROC FRAME
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
    sub rsp, 48
    .allocstack 48
    .endprolog
    mov rbx, rcx
    mov rsi, rdx
    mov r12d, r9d
    test r8, r8
    jz string_operation_invalid
    cmp DWORD PTR [r8], 053545250h
    jne string_operation_invalid
    cmp DWORD PTR [r8+4], 2
    je string_operation_abi_ok
    cmp DWORD PTR [r8+4], 3
    jne string_operation_invalid
string_operation_abi_ok:
    mov QWORD PTR [rsp+32], r8
    mov rdi, QWORD PTR [r8+40]
    cmp r12d, 26
    ja string_operation_invalid
    mov r15, QWORD PTR [rsi]
    mov rcx, r15
    mov rdx, rdi
    mov r8, rbx
    call boom_string_view
    cmp DWORD PTR [rbx], 0
    jne string_operation_failed
    mov r13, rax
    mov r14d, edx
    cmp r12d, 24
    jae string_copy_bytes
    cmp r12d, 23
    je string_coder
    cmp r12d, 21
    jae string_region_matches
    cmp r12d, 20
    je string_code_point_at
    cmp r12d, 19
    je string_trim
    cmp r12d, 0
    je string_length
    cmp r12d, 1
    je string_empty
    cmp r12d, 2
    je string_char_at
    cmp r12d, 3
    je string_hash
    cmp r12d, 8
    je string_compare_ignore_case
    cmp r12d, 9
    je string_index_of_codepoint
    cmp r12d, 10
    je string_index_of_codepoint
    cmp r12d, 15
    jae string_index_string
    cmp r12d, 13
    jae string_last_index_of_codepoint
    cmp r12d, 11
    jae string_substring
    cmp r12d, 5
    jbe string_compare_or_equals
    cmp r12d, 7
    jne string_return_receiver
    mov r8, QWORD PTR [rsp+32]
    cmp DWORD PTR [r8+4], 3
    jne string_return_receiver
    mov rcx, rbx
    mov rdx, rsi
    call boom_string_intern
    jmp string_operation_done
string_return_receiver:
    mov rax, r15
    jmp string_operation_done
string_length:
    mov eax, r14d
    jmp string_operation_done
string_coder:
    mov eax, 1
    jmp string_operation_done
; Package-only byte copies. This VM stores all Strings as little-endian
; UTF16 and exposes coder=1. Destination offsets are char indexes, shifted
; with Java int semantics before the equivalent arraycopy bounds checks.
string_copy_bytes:
    mov r15,QWORD PTR [rsi+8]
    test r15,r15
    jz string_copy_null
    mov rax,QWORD PTR [rsp+32]
    mov rcx,QWORD PTR [rax+48]
    test rcx,rcx
    jz string_operation_invalid
    mov rdx,r15
    call boom_heap_contains
    test eax,eax
    jz string_operation_invalid
    cmp QWORD PTR [r15-8],264
    jne string_copy_type
    cmp DWORD PTR [r15-20],0
    jne string_operation_invalid
    cmp r12d,25
    je string_copy_range
    cmp DWORD PTR [rsi+24],1
    jne string_operation_invalid
    xor r8d,r8d
    mov eax,DWORD PTR [rsi+16]
    shl eax,1
    movsxd r9,eax
    lea ecx,[r14d*2]
    jmp string_copy_bounds
string_copy_range:
    cmp DWORD PTR [rsi+32],1
    jne string_operation_invalid
    mov eax,DWORD PTR [rsi+16]
    shl eax,1
    movsxd r8,eax
    mov eax,DWORD PTR [rsi+24]
    shl eax,1
    movsxd r9,eax
    mov ecx,DWORD PTR [rsi+40]
    shl ecx,1
    movsxd rcx,ecx
string_copy_bounds:
    test r8,r8
    js string_copy_bounds_error
    test r9,r9
    js string_copy_bounds_error
    test rcx,rcx
    js string_copy_bounds_error
    lea rax,[r8+rcx]
    mov edx,r14d
    shl rdx,1
    cmp rax,rdx
    ja string_copy_bounds_error
    lea rax,[r9+rcx]
    cmp rax,QWORD PTR [r15-16]
    ja string_copy_bounds_error
    lea rsi,[r13+r8]
    lea rdi,[r15+r9]
    rep movsb
    xor eax,eax
    jmp string_operation_done
string_copy_null:
    mov DWORD PTR [rbx],4
    jmp string_operation_failed
string_copy_type:
    mov DWORD PTR [rbx],6
    jmp string_operation_failed
string_copy_bounds_error:
    mov DWORD PTR [rbx],5
    jmp string_operation_failed
string_empty:
    xor eax, eax
    test r14d, r14d
    sete al
    jmp string_operation_done
string_char_at:
    mov ecx, DWORD PTR [rsi+8]
    test ecx, ecx
    js string_index_error
    cmp ecx, r14d
    jae string_index_error
    movzx eax, WORD PTR [r13+rcx*2]
    jmp string_operation_done
string_code_point_at:
    mov ecx, DWORD PTR [rsi+8]
    test ecx, ecx
    js string_index_error
    cmp ecx, r14d
    jae string_index_error
    movzx eax, WORD PTR [r13+rcx*2]
    mov edx, eax
    sub edx, 0D800h
    cmp edx, 03FFh
    ja string_operation_done
    inc ecx
    cmp ecx, r14d
    jae string_operation_done
    movzx edx, WORD PTR [r13+rcx*2]
    sub edx, 0DC00h
    cmp edx, 03FFh
    ja string_operation_done
    sub eax, 0D800h
    shl eax, 10
    lea eax, [rax+rdx+10000h]
    jmp string_operation_done
string_index_error:
    mov DWORD PTR [rbx], 11
    jmp string_operation_failed
string_region_matches:
    cmp r12d, 22
    je string_region_boolean
    xor r12d, r12d
    jmp string_region_offsets
string_region_boolean:
    mov r12d, DWORD PTR [rsi+8]
    add rsi, 8
string_region_offsets:
    ; Mirror Java's short-circuit checks before dereferencing the other String.
    movsxd rcx, DWORD PTR [rsi+8]
    test rcx, rcx
    js string_false
    movsxd rdx, DWORD PTR [rsi+24]
    test rdx, rdx
    js string_false
    movsxd r15, DWORD PTR [rsi+32]
    mov eax, r14d
    sub rax, r15
    cmp rcx, rax
    jg string_false
    mov rcx, QWORD PTR [rsi+16]
    mov rdx, rdi
    mov r8, rbx
    call boom_string_view
    cmp DWORD PTR [rbx], 0
    jne string_operation_failed
    mov r10, rax
    mov eax, edx
    sub rax, r15
    movsxd rcx, DWORD PTR [rsi+24]
    cmp rcx, rax
    jg string_false
    test r15d, r15d
    jle string_true
    movsxd rcx, DWORD PTR [rsi+8]
    lea rcx, [r13+rcx*2]
    movsxd rdx, DWORD PTR [rsi+24]
    lea rdx, [r10+rdx*2]
    mov r8d, r15d
    test r12d, r12d
    jz string_region_exact
    call boom_unicode_equals_ci
    jmp string_operation_done
string_region_exact:
    mov rsi, rcx
    mov rdi, rdx
    mov ecx, r8d
    repe cmpsw
    sete al
    movzx eax, al
    jmp string_operation_done
string_hash:
    cmp DWORD PTR [r15+12], 0
    jne string_cached_hash
    xor eax, eax
    xor ecx, ecx
string_hash_loop:
    cmp ecx, r14d
    jae string_hash_publish
    imul eax, eax, 31
    movzx edx, WORD PTR [r13+rcx*2]
    add eax, edx
    inc ecx
    jmp string_hash_loop
string_hash_publish:
    mov DWORD PTR [r15+8], eax
    mov DWORD PTR [r15+12], 1
    jmp string_operation_done
string_cached_hash:
    mov eax, DWORD PTR [r15+8]
    jmp string_operation_done
string_index_of_codepoint:
    mov r8d, DWORD PTR [rsi+8]
    cmp r8d, 010FFFFh
    ja string_index_not_found
    xor r9d, r9d
    cmp r12d, 10
    jne string_index_start
    mov r9d, DWORD PTR [rsi+16]
    test r9d, r9d
    jns string_index_start
    xor r9d, r9d
string_index_start:
    cmp r9d, r14d
    jae string_index_not_found
    cmp r8d, 0FFFFh
    ja string_index_supplementary
string_index_unit_loop:
    cmp WORD PTR [r13+r9*2], r8w
    je string_index_found
    inc r9d
    cmp r9d, r14d
    jb string_index_unit_loop
    jmp string_index_not_found
string_index_supplementary:
    sub r8d, 10000h
    mov r10d, r8d
    and r10d, 03FFh
    add r10d, 0DC00h
    shr r8d, 10
    add r8d, 0D800h
    mov r11d, r14d
    dec r11d
string_index_pair_loop:
    cmp r9d, r11d
    jae string_index_not_found
    cmp WORD PTR [r13+r9*2], r8w
    jne string_index_pair_next
    cmp WORD PTR [r13+r9*2+2], r10w
    je string_index_found
string_index_pair_next:
    inc r9d
    jmp string_index_pair_loop
string_index_found:
    mov eax, r9d
    jmp string_operation_done
string_index_not_found:
    mov eax, -1
    jmp string_operation_done

string_last_index_of_codepoint:
    mov r8d,DWORD PTR [rsi+8]
    cmp r8d,010FFFFh
    ja string_index_not_found
    mov r9d,r14d
    dec r9d
    cmp r12d,14
    jne string_last_index_start
    mov eax,DWORD PTR [rsi+16]
    cmp r9d,eax
    cmovg r9d,eax
string_last_index_start:
    test r9d,r9d
    js string_index_not_found
    cmp r8d,0FFFFh
    ja string_last_index_supplementary
string_last_index_unit_loop:
    cmp WORD PTR [r13+r9*2],r8w
    je string_index_found
    dec r9d
    jns string_last_index_unit_loop
    jmp string_index_not_found
string_last_index_supplementary:
    mov eax,r14d
    sub eax,2
    cmp r9d,eax
    cmovg r9d,eax
    test r9d,r9d
    js string_index_not_found
    sub r8d,10000h
    mov r10d,r8d
    and r10d,03FFh
    add r10d,0DC00h
    shr r8d,10
    add r8d,0D800h
string_last_index_pair_loop:
    cmp WORD PTR [r13+r9*2],r8w
    jne string_last_index_pair_next
    cmp WORD PTR [r13+r9*2+2],r10w
    je string_index_found
string_last_index_pair_next:
    dec r9d
    jns string_last_index_pair_loop
    jmp string_index_not_found

string_index_string:
    mov rcx,QWORD PTR [rsi+8]
    mov rdx,rdi
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne string_operation_failed
    mov r10,rax
    mov r11d,edx
    cmp r12d,17
    jae string_search_backwards
    xor r9d,r9d
    cmp r12d,16
    jne string_search_forward_start
    mov r9d,DWORD PTR [rsi+16]
    test r9d,r9d
    jns string_search_forward_start
    xor r9d,r9d
string_search_forward_start:
    test r11d,r11d
    jnz string_search_forward_nonempty
    cmp r9d,r14d
    cmovg r9d,r14d
    jmp string_index_found
string_search_forward_nonempty:
    mov eax,r14d
    sub eax,r11d
    js string_index_not_found
    cmp r9d,eax
    jg string_index_not_found
    mov DWORD PTR [rsp+40],eax
    jmp string_search_compare
string_search_backwards:
    mov r9d,r14d
    cmp r12d,18
    jne string_search_backward_start
    mov r9d,DWORD PTR [rsi+16]
string_search_backward_start:
    test r9d,r9d
    js string_index_not_found
    mov eax,r14d
    sub eax,r11d
    js string_index_not_found
    cmp r9d,eax
    cmovg r9d,eax
string_search_compare:
    xor ecx,ecx
string_search_compare_loop:
    cmp ecx,r11d
    jae string_index_found
    lea edx,[r9+rcx]
    movzx eax,WORD PTR [r13+rdx*2]
    cmp ax,WORD PTR [r10+rcx*2]
    jne string_search_next
    inc ecx
    jmp string_search_compare_loop
string_search_next:
    cmp r12d,17
    jae string_search_previous
    inc r9d
    cmp r9d,DWORD PTR [rsp+40]
    jle string_search_compare
    jmp string_index_not_found
string_search_previous:
    dec r9d
    jns string_search_compare
    jmp string_index_not_found

string_trim:
    ; JDK trim removes only U+0000..U+0020; Unicode whitespace is different.
    xor r9d, r9d
    mov r8d, r14d
string_trim_leading:
    cmp r9d, r8d
    jae string_trim_bounds
    cmp WORD PTR [r13+r9*2], 20h
    ja string_trim_trailing
    inc r9d
    jmp string_trim_leading
string_trim_trailing:
    cmp r9d, r8d
    jae string_trim_bounds
    lea ecx, [r8-1]
    cmp WORD PTR [r13+rcx*2], 20h
    ja string_trim_bounds
    dec r8d
    jmp string_trim_trailing
string_trim_bounds:
    test r9d, r9d
    jnz string_substring_copy
    cmp r8d, r14d
    je string_return_receiver
    jmp string_substring_copy
string_substring:
    mov r9d, DWORD PTR [rsi+8]
    mov r8d, r14d
    cmp r12d, 12
    jne string_substring_bounds
    mov r8d, DWORD PTR [rsi+16]
string_substring_bounds:
    test r9d, r9d
    js string_index_error
    cmp r8d, r14d
    ja string_index_error
    cmp r9d, r8d
    ja string_index_error
    test r9d, r9d
    jnz string_substring_copy
    cmp r8d, r14d
    je string_return_receiver
string_substring_copy:
    mov DWORD PTR [rsp+40], r9d
    sub r8d, r9d
    mov r12d, r8d
    test r8d, r8d
    jz string_substring_empty
    mov rdx, QWORD PTR [rsp+32]
    mov rcx, QWORD PTR [rdx+48]
    mov r9, rbx
    call boom_string_allocate
    test rax, rax
    jz string_operation_failed
    mov r15, rax
    mov ecx, DWORD PTR [rsp+40]
    lea rsi, [r13+rcx*2]
    mov rdi, QWORD PTR [rax]
    mov ecx, r12d
    rep movsw
    mov rax, r15
    jmp string_operation_done
string_substring_empty:
    ; The compiler inserts the canonical empty literal into this pool.
    mov rdx, QWORD PTR [rsp+32]
    mov r10, QWORD PTR [rdx+32]
    mov r11d, DWORD PTR [rdx+16]
    xor r8d, r8d
string_substring_empty_find:
    cmp r8d, r11d
    jae string_operation_invalid
    cmp DWORD PTR [r10+8], 0
    je string_substring_empty_load
    add r10, 16
    inc r8d
    jmp string_substring_empty_find
string_substring_empty_load:
    mov rcx, QWORD PTR [rdx+48]
    mov r9, rbx
    call boom_string_load
    jmp string_operation_done

string_compare_ignore_case:
    mov rcx, QWORD PTR [rsi+8]
    cmp rcx, r15
    je string_true
    test rcx, rcx
    jz string_false
    mov rdx, rdi
    mov r8, rbx
    call boom_string_view
    cmp DWORD PTR [rbx], 0
    jne string_operation_failed
    cmp edx, r14d
    jne string_false
    mov rcx, r13
    mov rdx, rax
    mov r8d, r14d
    call boom_unicode_equals_ci
    jmp string_operation_done
string_compare_or_equals:
    mov rcx, QWORD PTR [rsi+8]
    cmp r12d, 4
    jne string_other_value
    cmp rcx, r15
    je string_true
    test rcx, rcx
    jz string_false
    cmp QWORD PTR [rcx-8], rdi
    jne string_false
string_other_value:
    mov rdx, rdi
    mov r8, rbx
    call boom_string_view
    cmp DWORD PTR [rbx], 0
    jne string_operation_failed
    mov r10, rax
    mov r11d, edx
    cmp r12d, 4
    jne string_comparison_start
    cmp r14d, r11d
    jne string_false
string_comparison_start:
    mov r8d, r14d
    cmp r8d, r11d
    cmova r8d, r11d
    xor ecx, ecx
string_comparison_loop:
    cmp ecx, r8d
    jae string_common_prefix
    movzx eax, WORD PTR [r13+rcx*2]
    movzx edx, WORD PTR [r10+rcx*2]
    sub eax, edx
    jnz string_difference
    inc ecx
    jmp string_comparison_loop
string_common_prefix:
    cmp r12d, 4
    je string_true
    mov eax, r14d
    sub eax, r11d
    jmp string_operation_done
string_difference:
    cmp r12d, 4
    jne string_operation_done
string_false:
    xor eax, eax
    jmp string_operation_done
string_true:
    mov eax, 1
    jmp string_operation_done
string_operation_invalid:
    mov DWORD PTR [rbx], 7
string_operation_failed:
    xor eax, eax
string_operation_done:
    add rsp, 48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_intrinsic ENDP
; Fresh result for immutable reflection text precomputed from frozen class
; metadata. Keeps metadata formatting out of hot paths without interning the
; returned object. Arguments match boom_string_load(heap,pool,index,ctx).
PUBLIC boom_string_fresh_literal
boom_string_fresh_literal PROC FRAME
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
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,r9
    mov rsi,rcx
    mov rdi,rdx
    call boom_string_load
    test rax,rax
    jz string_fresh_done
    mov r12,QWORD PTR [rax]
    mov r13,QWORD PTR [r12-16]
    mov rcx,rsi
    mov rdx,rdi
    mov r8d,r13d
    shr r8d,1
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz string_fresh_done
    mov rcx,r13
    mov rsi,r12
    mov rdi,QWORD PTR [rax]
    rep movsb
string_fresh_done:
    add rsp,32
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_fresh_literal ENDP
; Public getChars(ctx32,argv{String,begin,end,char[],dstBegin},pool3,
; plan{magic,abi,messageOffset,reserved,factory}). Both range checks follow String /
; Preconditions. The error path formats signed decimal integers without Locale.
PUBLIC boom_string_get_chars
.const
getchars_range WORD 82,97,110,103,101,32,91
getchars_comma WORD 44,32
getchars_plus WORD 32,43,32
getchars_tail WORD 41,32,111,117,116,32,111,102,32,98,111,117,110,100,115,32,102,111,114,32,108,101,110,103,116,104,32
.code
; EAX signed int, RDI output cursor, R10 temporary 24-byte buffer.
; Uses only volatile registers, returns the updated RDI.
getchars_decimal PROC
    movsxd rax,eax
    test rax,rax
    jns getchars_magnitude
    mov WORD PTR [rdi],45
    add rdi,2
    neg rax
getchars_magnitude:
    lea rcx,[r10+24]
    mov r8,rcx
    mov r9d,10
getchars_digit:
    xor edx,edx
    div r9
    add edx,48
    sub rcx,2
    mov WORD PTR [rcx],dx
    test rax,rax
    jnz getchars_digit
getchars_digits_copy:
    movzx eax,WORD PTR [rcx]
    mov WORD PTR [rdi],ax
    add rdi,2
    add rcx,2
    cmp rcx,r8
    jb getchars_digits_copy
    ret
getchars_decimal ENDP
boom_string_get_chars PROC FRAME
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
    sub rsp,352
    .allocstack 352
    .endprolog
    mov rbx,rcx
    mov rsi,rdx
    mov r12,r8
    test rbx,rbx
    jz getchars_done
    cmp DWORD PTR [rbx],0
    jne getchars_done
    test r9,r9
    jz getchars_bad
    cmp DWORD PTR [r9],047434852h
    jne getchars_bad
    cmp DWORD PTR [r9+4],1
    jne getchars_bad
    cmp DWORD PTR [r9+12],0
    jne getchars_bad
    mov eax,DWORD PTR [r9+8]
    mov DWORD PTR [rsp+32],eax
    mov rax,QWORD PTR [r9+16]
    test rax,rax
    jz getchars_bad
    mov QWORD PTR [rsp+344],rax
    test rsi,rsi
    jz getchars_bad
    test r12,r12
    jz getchars_bad
    cmp DWORD PTR [r12],053545250h
    jne getchars_bad
    cmp DWORD PTR [r12+4],3
    jne getchars_bad
    cmp QWORD PTR [r12+48],0
    je getchars_bad
    mov rdx,QWORD PTR [rsi]
    test rdx,rdx
    jz getchars_null
    mov rcx,QWORD PTR [r12+48]
    call boom_heap_contains
    test eax,eax
    jz getchars_bad
    mov rcx,QWORD PTR [rsi]
    mov rdx,QWORD PTR [r12+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne getchars_done
    mov r13,rax
    mov r14d,edx
    mov DWORD PTR [rsp+48],edx
    mov eax,DWORD PTR [rsi+8]
    mov edx,DWORD PTR [rsi+16]
    mov DWORD PTR [rsp+40],eax
    mov DWORD PTR [rsp+44],edx
    mov DWORD PTR [rsp+36],0
    test eax,eax
    js getchars_bounds
    cmp eax,edx
    jg getchars_bounds
    cmp edx,r14d
    jg getchars_bounds
    sub edx,eax
    mov DWORD PTR [rsp+52],edx
    mov r15,QWORD PTR [rsi+24]
    test r15,r15
    jz getchars_null
    mov rcx,QWORD PTR [r12+48]
    mov rdx,r15
    call boom_heap_contains
    test eax,eax
    jz getchars_bad
    cmp QWORD PTR [r15-8],261
    jne getchars_bad
    cmp DWORD PTR [r15-20],0
    jne getchars_bad
    mov rax,QWORD PTR [r15-16]
    test rax,1
    jnz getchars_bad
    shr rax,1
    cmp rax,07FFFFFFFh
    ja getchars_bad
    mov DWORD PTR [rsp+48],eax
    mov edx,DWORD PTR [rsi+32]
    mov DWORD PTR [rsp+40],edx
    mov ecx,DWORD PTR [rsp+52]
    mov DWORD PTR [rsp+44],ecx
    mov DWORD PTR [rsp+36],1
    test edx,edx
    js getchars_bounds
    cmp edx,eax
    jg getchars_bounds
    sub eax,edx
    cmp ecx,eax
    jg getchars_bounds
    mov eax,DWORD PTR [rsi+8]
    lea rsi,[r13+rax*2]
    lea rdi,[r15+rdx*2]
    rep movsw
    jmp getchars_done
getchars_bounds:
    lea rdi,[rsp+64]
    lea rsi,getchars_range
    mov ecx,7
    rep movsw
    mov eax,DWORD PTR [rsp+40]
    lea r10,[rsp+320]
    call getchars_decimal
    lea rsi,getchars_comma
    mov ecx,2
    rep movsw
    cmp DWORD PTR [rsp+36],0
    je getchars_second
    mov eax,DWORD PTR [rsp+40]
    lea r10,[rsp+320]
    call getchars_decimal
    lea rsi,getchars_plus
    mov ecx,3
    rep movsw
getchars_second:
    mov eax,DWORD PTR [rsp+44]
    lea r10,[rsp+320]
    call getchars_decimal
    lea rsi,getchars_tail
    mov ecx,27
    rep movsw
    mov eax,DWORD PTR [rsp+48]
    lea r10,[rsp+320]
    call getchars_decimal
    lea rax,[rsp+64]
    sub rdi,rax
    shr rdi,1
    mov r8d,edi
    mov rcx,QWORD PTR [r12+48]
    mov rdx,r12
    mov r9,rbx
    call boom_string_allocate
    test rax,rax
    jz getchars_done
    mov QWORD PTR [rsp+56],rax
    mov rdi,QWORD PTR [rax]
    lea rsi,[rsp+64]
    mov rcx,QWORD PTR [rdi-16]
    shr rcx,1
    rep movsw
    mov rcx,rbx
    mov edx,11
    xor r8d,r8d
    mov r9d,1
    call QWORD PTR [rsp+344]
    test rax,rax
    jz getchars_done
    mov ecx,DWORD PTR [rsp+32]
    test ecx,7
    jnz getchars_bad
    mov edx,DWORD PTR [rax-20]
    shl rdx,3
    add rcx,8
    cmp rcx,rdx
    ja getchars_bad
    mov rdx,QWORD PTR [rsp+56]
    mov QWORD PTR [rax+rcx-8],rdx
    mov QWORD PTR [rbx+16],rax
    mov DWORD PTR [rbx],16
    jmp getchars_done
getchars_bad:
    mov DWORD PTR [rbx],7
    jmp getchars_done
getchars_null:
    mov DWORD PTR [rbx],4
getchars_done:
    xor eax,eax
    add rsp,352
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_string_get_chars ENDP
END
