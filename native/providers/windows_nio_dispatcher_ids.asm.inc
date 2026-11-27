; Normal initIDs registration. The generator supplies only locked source rows.
; Win64(Context32 RCX, argv RDX, exact WNID224 pool R8, operation0 R9D).
; No Java oop/field/state writes. All seven initialization obligations go through
; the original boom_class_ensure32. Native cache publication contains only the
; actual normal field-address PROC pointers, never Java objects.
.code
wnid_validate_field PROC PRIVATE
 ; RSI trusted immutable source row, R13 exact local pool. Volatile regs only.
 lea r10,boom_java_unsafe_field_pool
 mov ecx,DWORD PTR [rsi+8]
 cmp ecx,WNID_UFMP_FIELDS
 jae wvf_bad
 mov eax,ecx
 shr eax,10
 lea rdx,boom_java_unsafe_field_pages
 mov rdx,QWORD PTR [rdx+rax*8]
 cmp rdx,QWORD PTR [rsi+72]
 jne wvf_bad
 and ecx,1023
 shl ecx,6
 lea r11,[rdx+rcx]
 mov eax,DWORD PTR [rsi]
 cmp DWORD PTR [r11],eax
 jne wvf_bad
 mov eax,DWORD PTR [rsi+4]
 cmp DWORD PTR [r11+4],eax
 jne wvf_bad
 cmp DWORD PTR [r11+8],2
 jne wvf_bad
 mov eax,DWORD PTR [rsi+12]
 cmp DWORD PTR [r11+12],eax
 jne wvf_bad
 mov eax,DWORD PTR [rsi+16]
 cmp DWORD PTR [r11+24],eax
 jne wvf_bad
 mov eax,DWORD PTR [rsi+20]
 cmp DWORD PTR [r11+28],eax
 jne wvf_bad
 mov rax,QWORD PTR [rsi+32]
 cmp QWORD PTR [r11+32],rax
 jne wvf_bad
 cmp QWORD PTR [r11+40],0
 jne wvf_bad
 mov eax,DWORD PTR [rsi+8]
 cmp DWORD PTR [r11+48],eax
 jne wvf_bad
 cmp DWORD PTR [r11+52],0
 jne wvf_bad
 cmp QWORD PTR [r11+56],0
 jne wvf_bad
 mov ecx,DWORD PTR [r11+20]
 cmp ecx,DWORD PTR [rsi+28]
 jne wvf_bad
 test ecx,ecx
 jz wvf_bad
 mov eax,DWORD PTR [r11+16]
 mov edx,eax
 add edx,ecx
 jc wvf_bad
 cmp edx,WNID_UFMP_NAME_UNITS
 ja wvf_bad
 lea r10,boom_java_unsafe_field_names
 lea r10,[r10+rax*2]
 mov rdx,QWORD PTR [rsi+48]
wvf_name:
 mov ax,WORD PTR [r10]
 cmp ax,WORD PTR [rdx]
 jne wvf_bad
 add r10,2
 add rdx,2
 dec ecx
 jnz wvf_name
 mov r10,QWORD PTR [rsi+40]
 cmp DWORD PTR [r10],0464D4150h
 jne wvf_bad
 cmp DWORD PTR [r10+4],1
 jne wvf_bad
 mov ecx,DWORD PTR [rsi+64]
 test ecx,ecx
 jz wvf_bad
 cmp DWORD PTR [r10+8],ecx
 jne wvf_bad
 mov eax,DWORD PTR [rsi+16]
 cmp DWORD PTR [r10+12],eax
 jne wvf_bad
 mov eax,DWORD PTR [rsi+20]
 cmp DWORD PTR [r10+16],eax
 jne wvf_bad
 cmp DWORD PTR [r10+20],0
 jne wvf_bad
 lea r11,[r10+32]
 cmp QWORD PTR [r10+24],r11
 jne wvf_bad
 mov rdx,QWORD PTR [rsi+56]
wvf_rows:
 mov rax,QWORD PTR [r11]
 cmp rax,QWORD PTR [rdx]
 jne wvf_bad
 add r11,8
 add rdx,8
 dec ecx
 jnz wvf_rows
 mov eax,1
 ret
wvf_bad:
 xor eax,eax
 ret
wnid_validate_field ENDP

PUBLIC boom_windows_nio_dispatcher_init_ids
boom_windows_nio_dispatcher_init_ids PROC FRAME
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
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 mov r13,r8
 test rbx,rbx
 jz wni_done
 cmp DWORD PTR [rbx],0
 jne wni_done
 cmp QWORD PTR [rbx+24],0
 jne wni_done
 lea rax,boom_windows_nio_dispatcher_pool
 cmp r13,rax
 jne wni_argument
 test r9d,r9d
 jnz wni_unsupported
 cmp DWORD PTR [r13],044494E57h
 jne wni_argument
 cmp DWORD PTR [r13+4],1
 jne wni_argument
 cmp DWORD PTR [r13+8],WNID_POOL_BYTES
 jne wni_argument
 cmp DWORD PTR [r13+16],WNID_CLASS_COUNT
 jne wni_argument
 cmp DWORD PTR [r13+20],WNID_FIELD_COUNT
 jne wni_argument
 cmp DWORD PTR [r13+28],0
 jne wni_argument
 lea rax,wnid_fields
 cmp QWORD PTR [r13+32],rax
 jne wni_argument
 lea rax,wnid_groups
 cmp QWORD PTR [r13+40],rax
 jne wni_argument
 lea r10,boom_java_unsafe_field_pool
 cmp QWORD PTR [r13+48],r10
 jne wni_argument
 cmp QWORD PTR [r13+56],0
 jne wni_argument
 cmp DWORD PTR [r10],055464D50h
 jne wni_unsupported
 cmp DWORD PTR [r10+4],WNID_UFMP_ABI
 jne wni_unsupported
 cmp DWORD PTR [r10+8],WNID_UFMP_TYPES
 jne wni_unsupported
 cmp DWORD PTR [r10+12],WNID_UFMP_FIELDS
 jne wni_unsupported
 cmp DWORD PTR [r10+88],WNID_UFMP_NAME_UNITS
 jne wni_unsupported
 cmp DWORD PTR [r10+92],WNID_UFMP_PAGES
 jne wni_unsupported
 cmp DWORD PTR [r10+108],64
 jne wni_unsupported
 mov rax,055464C3200000000h
 cmp QWORD PTR [r10+112],rax
 jne wni_unsupported
 lea rax,boom_java_unsafe_field_names
 cmp QWORD PTR [r10+64],rax
 jne wni_unsupported
 lea rax,boom_java_unsafe_field_pages
 cmp QWORD PTR [r10+80],rax
 jne wni_unsupported
 lea rdi,wnid_groups
 xor r14d,r14d
wni_class:
 mov rcx,QWORD PTR [rdi]
 cmp DWORD PTR [rcx],0434C4153h
 jne wni_unsupported
 cmp DWORD PTR [rcx+4],2
 jne wni_unsupported
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz wni_ensure_failed
 cmp DWORD PTR [rbx],0
 jne wni_done
 cmp QWORD PTR [rbx+24],0
 jne wni_done
 mov r10,QWORD PTR [rdi+8]
 cmp DWORD PTR [r10],04F424A43h
 jne wni_unsupported
 cmp DWORD PTR [r10+4],2
 jne wni_unsupported
 mov rax,QWORD PTR [rdi+24]
 cmp QWORD PTR [r10+8],rax
 jne wni_unsupported
 mov eax,DWORD PTR [rdi+32]
 cmp DWORD PTR [r10+16],eax
 jne wni_unsupported
 mov eax,DWORD PTR [rdi+36]
 cmp DWORD PTR [r10+20],eax
 jne wni_unsupported
 mov r12d,DWORD PTR [rdi+16]
 mov eax,DWORD PTR [rdi+20]
 mov DWORD PTR [rsp+32],eax
wni_field:
 imul rax,r12,80
 lea rsi,wnid_fields
 add rsi,rax
 call wnid_validate_field
 test eax,eax
 jz wni_unsupported
 inc r12d
 dec DWORD PTR [rsp+32]
 jnz wni_field
 add rdi,40
 inc r14d
 cmp r14d,WNID_CLASS_COUNT
 jb wni_class
 ; Only publication is locked. No class initialization or callback runs here.
wni_lock:
 mov eax,1
 xchg DWORD PTR [r13+24],eax
 test eax,eax
 jz wni_locked
wni_spin:
 pause
 cmp DWORD PTR [r13+24],0
 jne wni_spin
 jmp wni_lock
wni_locked:
 cmp DWORD PTR [r13+12],1
 ja wni_bad_locked
 xor r12d,r12d
 lea rsi,wnid_fields
 lea rdi,[r13+64]
wni_publish:
 mov rax,QWORD PTR [rsi+32]
 cmp DWORD PTR [r13+12],0
 je wni_store
 cmp QWORD PTR [rdi],rax
 jne wni_bad_locked
 jmp wni_next
wni_store:
 mov QWORD PTR [rdi],rax
wni_next:
 add rsi,80
 add rdi,8
 inc r12d
 cmp r12d,WNID_FIELD_COUNT
 jb wni_publish
 mov DWORD PTR [r13+12],1
 mov DWORD PTR [r13+24],0
 jmp wni_done
wni_bad_locked:
 mov DWORD PTR [r13+24],0
 jmp wni_unsupported
wni_ensure_failed:
 cmp DWORD PTR [rbx],0
 jne wni_done
 cmp QWORD PTR [rbx+24],0
 jne wni_done
wni_unsupported:
 mov DWORD PTR [rbx],20
 jmp wni_done
wni_argument:
 mov DWORD PTR [rbx],7
wni_done:
 xor eax,eax
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_windows_nio_dispatcher_init_ids ENDP
