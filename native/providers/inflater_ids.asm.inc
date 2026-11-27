; Source-driven JNI GetFieldID registration for the two original int fields.
; Context32 RCX, original argv RDX (unused), trusted INFL256 R8. R9 unused.
; Native-pointer cache only: no Java oop roots, no class-state/Java-field writes.
; Normal class initialization and every field validation occur outside SRW.
.code
inid_validate_field PROC PRIVATE
 ; RSI read-only source row80. No call, only Win64 volatile regs changed.
 mov ecx,DWORD PTR [rsi+8]
 cmp ecx,INID_UFMP_FIELDS
 jae iniv_bad
 mov eax,ecx
 shr eax,10
 lea rdx,boom_java_unsafe_field_pages
 mov rdx,QWORD PTR [rdx+rax*8]
 cmp rdx,QWORD PTR [rsi+72]
 jne iniv_bad
 and ecx,1023
 shl ecx,6
 lea r11,[rdx+rcx]
 mov eax,DWORD PTR [rsi]
 cmp DWORD PTR [r11],eax
 jne iniv_bad
 mov eax,DWORD PTR [rsi+4]
 cmp DWORD PTR [r11+4],eax
 jne iniv_bad
 mov eax,DWORD PTR [rsi+68]
 cmp DWORD PTR [r11+8],eax
 jne iniv_bad
 mov eax,DWORD PTR [rsi+12]
 cmp DWORD PTR [r11+12],eax
 jne iniv_bad
 mov eax,DWORD PTR [rsi+16]
 cmp DWORD PTR [r11+24],eax
 jne iniv_bad
 mov eax,DWORD PTR [rsi+20]
 cmp DWORD PTR [r11+28],eax
 jne iniv_bad
 mov rax,QWORD PTR [rsi+32]
 cmp QWORD PTR [r11+32],rax
 jne iniv_bad
 cmp QWORD PTR [r11+40],0
 jne iniv_bad
 mov eax,DWORD PTR [rsi+8]
 cmp DWORD PTR [r11+48],eax
 jne iniv_bad
 cmp DWORD PTR [r11+52],0
 jne iniv_bad
 cmp QWORD PTR [r11+56],0
 jne iniv_bad
 mov ecx,DWORD PTR [r11+20]
 cmp ecx,DWORD PTR [rsi+28]
 jne iniv_bad
 test ecx,ecx
 jz iniv_bad
 mov eax,DWORD PTR [r11+16]
 mov edx,eax
 add edx,ecx
 jc iniv_bad
 cmp edx,INID_UFMP_NAME_UNITS
 ja iniv_bad
 lea r10,boom_java_unsafe_field_names
 lea r10,[r10+rax*2]
 mov rdx,QWORD PTR [rsi+48]
iniv_name:
 mov ax,WORD PTR [r10]
 cmp ax,WORD PTR [rdx]
 jne iniv_bad
 add r10,2
 add rdx,2
 dec ecx
 jnz iniv_name
 mov r10,QWORD PTR [rsi+40]
 cmp DWORD PTR [r10],0464D4150h
 jne iniv_bad
 cmp DWORD PTR [r10+4],1
 jne iniv_bad
 mov ecx,DWORD PTR [rsi+64]
 test ecx,ecx
 jz iniv_bad
 cmp DWORD PTR [r10+8],ecx
 jne iniv_bad
 cmp DWORD PTR [r10+12],4
 jne iniv_bad
 cmp DWORD PTR [r10+16],0
 jne iniv_bad
 cmp DWORD PTR [r10+20],0
 jne iniv_bad
 lea r11,[r10+32]
 cmp QWORD PTR [r10+24],r11
 jne iniv_bad
 mov rdx,QWORD PTR [rsi+56]
iniv_rows:
 mov rax,QWORD PTR [r11]
 cmp rax,QWORD PTR [rdx]
 jne iniv_bad
 add r11,8
 add rdx,8
 dec ecx
 jnz iniv_rows
 mov eax,1
 ret
iniv_bad:
 xor eax,eax
 ret
inid_validate_field ENDP

PUBLIC boom_inflater_ids_register
boom_inflater_ids_register PROC FRAME
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
 mov rbx,rcx
 test rbx,rbx
 jz ini_done
 cmp DWORD PTR [rbx],0
 jne ini_done
 cmp QWORD PTR [rbx+16],0
 jne ini_done
 cmp QWORD PTR [rbx+24],0
 jne ini_done
 lea r13,boom_provider_inflater_pool
 cmp r8,r13
 jne ini_argument
 cmp DWORD PTR [r13],04C464E49h
 jne ini_argument
 cmp DWORD PTR [r13+4],2
 jne ini_argument
 lea rax,boom_heap_ptr
 cmp QWORD PTR [r13+8],rax
 jne ini_argument
 lea rax,boom_java_platform_properties_pool
 cmp QWORD PTR [r13+88],rax
 jne ini_argument
 lea rax,boom_inflater_owner_records
 cmp QWORD PTR [r13+120],rax
 jne ini_argument
 cmp DWORD PTR [r13+128],256
 jne ini_argument
 cmp DWORD PTR [r13+132],34608
 jne ini_argument
 cmp DWORD PTR [r13+144],256
 jne ini_argument
 cmp QWORD PTR [r13+160],65536
 jne ini_argument
 lea rax,boom_inflater_expected_fields
 cmp QWORD PTR [r13+168],rax
 jne ini_argument
 lea rax,boom_java_unsafe_field_pool
 cmp QWORD PTR [r13+176],rax
 jne ini_argument
 lea rax,boom_runtime_type_map
 cmp QWORD PTR [r13+184],rax
 jne ini_argument
 lea rax,INID_CLASS
 cmp QWORD PTR [r13+192],rax
 jne ini_argument
 cmp QWORD PTR [r13+200],0
 jne ini_argument
 cmp QWORD PTR [r13+208],0
 jne ini_argument
 cmp QWORD PTR [r13+216],0
 jne ini_argument
 cmp QWORD PTR [r13+224],0
 jne ini_argument
 cmp QWORD PTR [r13+232],0
 jne ini_argument
 cmp QWORD PTR [r13+240],0
 jne ini_argument
 cmp QWORD PTR [r13+248],0
 jne ini_argument
 lea r10,boom_java_unsafe_field_pool
 cmp DWORD PTR [r10],055464D50h
 jne ini_unsupported
 cmp DWORD PTR [r10+4],2
 jne ini_unsupported
 cmp DWORD PTR [r10+8],INID_UFMP_TYPES
 jne ini_unsupported
 cmp DWORD PTR [r10+12],INID_UFMP_FIELDS
 jne ini_unsupported
 cmp DWORD PTR [r10+88],INID_UFMP_NAME_UNITS
 jne ini_unsupported
 cmp DWORD PTR [r10+92],INID_UFMP_PAGES
 jne ini_unsupported
 cmp DWORD PTR [r10+108],64
 jne ini_unsupported
 mov rax,055464C3200000000h
 cmp QWORD PTR [r10+112],rax
 jne ini_unsupported
 lea rax,boom_java_unsafe_field_names
 cmp QWORD PTR [r10+64],rax
 jne ini_unsupported
 lea rax,boom_java_unsafe_field_pages
 cmp QWORD PTR [r10+80],rax
 jne ini_unsupported
 lea rcx,INID_CLASS
 cmp DWORD PTR [rcx],0434C4153h
 jne ini_unsupported
 cmp DWORD PTR [rcx+4],2
 jne ini_unsupported
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz ini_ensure_failed
 cmp DWORD PTR [rbx],0
 jne ini_done
 cmp QWORD PTR [rbx+16],0
 jne ini_done
 cmp QWORD PTR [rbx+24],0
 jne ini_done
 lea r10,INID_LAYOUT
 cmp DWORD PTR [r10],04F424A43h
 jne ini_unsupported
 cmp DWORD PTR [r10+4],2
 jne ini_unsupported
 cmp QWORD PTR [r10+8],INID_PAYLOAD
 jne ini_unsupported
 cmp DWORD PTR [r10+16],INID_REFS
 jne ini_unsupported
 cmp DWORD PTR [r10+20],INID_LAYOUT_FIELDS
 jne ini_unsupported
 lea rsi,boom_inflater_expected_fields
 mov r12d,2
ini_fields:
 call inid_validate_field
 test eax,eax
 jz ini_unsupported
 add rsi,80
 dec r12d
 jnz ini_fields
 ; JNI class initialization and all validation ended before publication lock.
 lea rcx,[r13+16]
 call AcquireSRWLockExclusive
 cmp QWORD PTR [r13+64],0
 je ini_cold
 cmp QWORD PTR [r13+64],2
 jne ini_bad_locked
 lea rsi,boom_inflater_expected_fields
 mov rax,QWORD PTR [rsi+32]
 cmp QWORD PTR [r13+72],rax
 jne ini_bad_locked
 mov rax,QWORD PTR [rsi+112]
 cmp QWORD PTR [r13+80],rax
 jne ini_bad_locked
 jmp ini_unlock
ini_cold:
 cmp QWORD PTR [r13+72],0
 jne ini_bad_locked
 cmp QWORD PTR [r13+80],0
 jne ini_bad_locked
 lea rsi,boom_inflater_expected_fields
 mov rax,QWORD PTR [rsi+32]
 mov QWORD PTR [r13+72],rax
 mov rax,QWORD PTR [rsi+112]
 mov QWORD PTR [r13+80],rax
 mov eax,2
 xchg QWORD PTR [r13+64],rax
ini_unlock:
 lea rcx,[r13+16]
 call ReleaseSRWLockExclusive
 jmp ini_done
ini_bad_locked:
 lea rcx,[r13+16]
 call ReleaseSRWLockExclusive
 jmp ini_unsupported
ini_ensure_failed:
 cmp DWORD PTR [rbx],0
 jne ini_done
 cmp QWORD PTR [rbx+16],0
 jne ini_done
 cmp QWORD PTR [rbx+24],0
 jne ini_done
ini_unsupported:
 mov DWORD PTR [rbx],20
 jmp ini_done
ini_argument:
 mov DWORD PTR [rbx],7
ini_done:
 xor eax,eax
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_inflater_ids_register ENDP
