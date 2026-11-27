; Original RandomAccessFile.initIDs: exact source RAF.fd FieldID registration.
; Win64(Context32 RCX, argv RDX, exact RFID128 pool R8, operation0 R9D).
; Only RAF declaring-class initialization is requested by JNI GetFieldID.
; Cached PROC/table pointers contain no Java oops; source fields/states unchanged.
; Source-only wrappers before/after this native remain original selected Code.
.code
rfid_validate_field PROC PRIVATE
 ; RSI trusted immutable source row, R13 exact local pool. Volatile regs only.
 lea r10,boom_java_unsafe_field_pool
 mov ecx,DWORD PTR [rsi+8]
 cmp ecx,RFID_UFMP_FIELDS
 jae rfv_bad
 mov eax,ecx
 shr eax,10
 lea rdx,boom_java_unsafe_field_pages
 mov rdx,QWORD PTR [rdx+rax*8]
 cmp rdx,QWORD PTR [rsi+72]
 jne rfv_bad
 and ecx,1023
 shl ecx,6
 lea r11,[rdx+rcx]
 mov eax,DWORD PTR [rsi]
 cmp DWORD PTR [r11],eax
 jne rfv_bad
 mov eax,DWORD PTR [rsi+4]
 cmp DWORD PTR [r11+4],eax
 jne rfv_bad
 mov eax,DWORD PTR [rsi+68]
 cmp DWORD PTR [r11+8],eax
 jne rfv_bad
 mov eax,DWORD PTR [rsi+12]
 cmp DWORD PTR [r11+12],eax
 jne rfv_bad
 mov eax,DWORD PTR [rsi+16]
 cmp DWORD PTR [r11+24],eax
 jne rfv_bad
 mov eax,DWORD PTR [rsi+20]
 cmp DWORD PTR [r11+28],eax
 jne rfv_bad
 mov rax,QWORD PTR [rsi+32]
 cmp QWORD PTR [r11+32],rax
 jne rfv_bad
 cmp QWORD PTR [r11+40],0
 jne rfv_bad
 mov eax,DWORD PTR [rsi+8]
 cmp DWORD PTR [r11+48],eax
 jne rfv_bad
 cmp DWORD PTR [r11+52],0
 jne rfv_bad
 cmp QWORD PTR [r11+56],0
 jne rfv_bad
 mov ecx,DWORD PTR [r11+20]
 cmp ecx,DWORD PTR [rsi+28]
 jne rfv_bad
 test ecx,ecx
 jz rfv_bad
 mov eax,DWORD PTR [r11+16]
 mov edx,eax
 add edx,ecx
 jc rfv_bad
 cmp edx,RFID_UFMP_NAME_UNITS
 ja rfv_bad
 lea r10,boom_java_unsafe_field_names
 lea r10,[r10+rax*2]
 mov rdx,QWORD PTR [rsi+48]
rfv_name:
 mov ax,WORD PTR [r10]
 cmp ax,WORD PTR [rdx]
 jne rfv_bad
 add r10,2
 add rdx,2
 dec ecx
 jnz rfv_name
 mov r10,QWORD PTR [rsi+40]
 cmp DWORD PTR [r10],0464D4150h
 jne rfv_bad
 cmp DWORD PTR [r10+4],1
 jne rfv_bad
 mov ecx,DWORD PTR [rsi+64]
 test ecx,ecx
 jz rfv_bad
 cmp DWORD PTR [r10+8],ecx
 jne rfv_bad
 mov eax,DWORD PTR [rsi+16]
 cmp DWORD PTR [r10+12],eax
 jne rfv_bad
 mov eax,DWORD PTR [rsi+20]
 cmp DWORD PTR [r10+16],eax
 jne rfv_bad
 cmp DWORD PTR [r10+20],0
 jne rfv_bad
 lea r11,[r10+32]
 cmp QWORD PTR [r10+24],r11
 jne rfv_bad
 mov rdx,QWORD PTR [rsi+56]
rfv_rows:
 mov rax,QWORD PTR [r11]
 cmp rax,QWORD PTR [rdx]
 jne rfv_bad
 add r11,8
 add rdx,8
 dec ecx
 jnz rfv_rows
 mov eax,1
 ret
rfv_bad:
 xor eax,eax
 ret
rfid_validate_field ENDP

PUBLIC boom_random_access_file_init_ids
boom_random_access_file_init_ids PROC FRAME
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
 jz rfi_done
 cmp DWORD PTR [rbx],0
 jne rfi_done
 cmp QWORD PTR [rbx+16],0
 jne rfi_done
 cmp QWORD PTR [rbx+24],0
 jne rfi_done
 lea rax,boom_random_access_file_init_ids_pool
 cmp r13,rax
 jne rfi_argument
 test r9d,r9d
 jnz rfi_unsupported
 cmp DWORD PTR [r13],044494652h
 jne rfi_argument
 cmp DWORD PTR [r13+4],1
 jne rfi_argument
 cmp DWORD PTR [r13+8],RFID_POOL_BYTES
 jne rfi_argument
 cmp DWORD PTR [r13+16],RFID_CLASS_COUNT
 jne rfi_argument
 cmp DWORD PTR [r13+20],RFID_FIELD_COUNT
 jne rfi_argument
 cmp DWORD PTR [r13+28],0
 jne rfi_argument
 lea rax,rfid_fields
 cmp QWORD PTR [r13+32],rax
 jne rfi_argument
 lea rax,rfid_groups
 cmp QWORD PTR [r13+40],rax
 jne rfi_argument
 lea r10,boom_java_unsafe_field_pool
 cmp QWORD PTR [r13+48],r10
 jne rfi_argument
 cmp QWORD PTR [r13+56],0
 jne rfi_argument
 cmp QWORD PTR [r13+72],0
 jne rfi_argument
 cmp QWORD PTR [r13+112],0
 jne rfi_argument
 cmp QWORD PTR [r13+120],0
 jne rfi_argument
 cmp DWORD PTR [r10],055464D50h
 jne rfi_unsupported
 cmp DWORD PTR [r10+4],RFID_UFMP_ABI
 jne rfi_unsupported
 cmp DWORD PTR [r10+8],RFID_UFMP_TYPES
 jne rfi_unsupported
 cmp DWORD PTR [r10+12],RFID_UFMP_FIELDS
 jne rfi_unsupported
 cmp DWORD PTR [r10+88],RFID_UFMP_NAME_UNITS
 jne rfi_unsupported
 cmp DWORD PTR [r10+92],RFID_UFMP_PAGES
 jne rfi_unsupported
 cmp DWORD PTR [r10+108],64
 jne rfi_unsupported
 mov rax,055464C3200000000h
 cmp QWORD PTR [r10+112],rax
 jne rfi_unsupported
 lea rax,boom_java_unsafe_field_names
 cmp QWORD PTR [r10+64],rax
 jne rfi_unsupported
 lea rax,boom_java_unsafe_field_pages
 cmp QWORD PTR [r10+80],rax
 jne rfi_unsupported
 lea rdi,rfid_groups
 xor r14d,r14d
rfi_class:
 mov rcx,QWORD PTR [rdi]
 cmp DWORD PTR [rcx],0434C4153h
 jne rfi_unsupported
 cmp DWORD PTR [rcx+4],2
 jne rfi_unsupported
 mov rdx,rbx
 call boom_class_ensure32
 test eax,eax
 jnz rfi_ensure_failed
 cmp DWORD PTR [rbx],0
 jne rfi_done
 cmp QWORD PTR [rbx+16],0
 jne rfi_done
 cmp QWORD PTR [rbx+24],0
 jne rfi_done
 mov r10,QWORD PTR [rdi+8]
 cmp DWORD PTR [r10],04F424A43h
 jne rfi_unsupported
 cmp DWORD PTR [r10+4],2
 jne rfi_unsupported
 mov rax,QWORD PTR [rdi+24]
 cmp QWORD PTR [r10+8],rax
 jne rfi_unsupported
 mov eax,DWORD PTR [rdi+32]
 cmp DWORD PTR [r10+16],eax
 jne rfi_unsupported
 mov eax,DWORD PTR [rdi+36]
 cmp DWORD PTR [r10+20],eax
 jne rfi_unsupported
 mov r12d,DWORD PTR [rdi+16]
 mov eax,DWORD PTR [rdi+20]
 mov DWORD PTR [rsp+32],eax
rfi_field:
 imul rax,r12,80
 lea rsi,rfid_fields
 add rsi,rax
 call rfid_validate_field
 test eax,eax
 jz rfi_unsupported
 inc r12d
 dec DWORD PTR [rsp+32]
 jnz rfi_field
 add rdi,40
 inc r14d
 cmp r14d,RFID_CLASS_COUNT
 jb rfi_class
 ; Only publication is locked. No class initialization or callback runs here.
rfi_lock:
 mov eax,1
 xchg DWORD PTR [r13+24],eax
 test eax,eax
 jz rfi_locked
rfi_spin:
 pause
 cmp DWORD PTR [r13+24],0
 jne rfi_spin
 jmp rfi_lock
rfi_locked:
 cmp DWORD PTR [r13+12],1
 ja rfi_bad_locked
 ; No Java callback/class initialization runs under this publication lock.
 ; Reuse the real existing stream-table kernel's exact-table CAS; no old NFIO
 ; input/output slot is reused. A nonzero Context never publishes outer ready.
 mov rcx,rbx
 lea rdx,boom_random_access_file_stream_pool
 call boom_stream_fields_init
 cmp DWORD PTR [rbx],0
 jne rfi_stream_failed_locked
 xor r12d,r12d
 lea rsi,rfid_fields
 lea rdi,[r13+64]
rfi_publish:
 mov rax,QWORD PTR [rsi+32]
 cmp DWORD PTR [r13+12],0
 je rfi_store
 cmp QWORD PTR [rdi],rax
 jne rfi_bad_locked
 jmp rfi_next
rfi_store:
 mov QWORD PTR [rdi],rax
rfi_next:
 add rsi,80
 add rdi,8
 inc r12d
 cmp r12d,RFID_FIELD_COUNT
 jb rfi_publish
 mov DWORD PTR [r13+12],1
 mov DWORD PTR [r13+24],0
 jmp rfi_done
rfi_stream_failed_locked:
 mov DWORD PTR [r13+24],0
 jmp rfi_done
rfi_bad_locked:
 mov DWORD PTR [r13+24],0
 jmp rfi_unsupported
rfi_ensure_failed:
 cmp DWORD PTR [rbx],0
 jne rfi_done
 cmp QWORD PTR [rbx+16],0
 jne rfi_done
 cmp QWORD PTR [rbx+24],0
 jne rfi_done
rfi_unsupported:
 mov DWORD PTR [rbx],20
 jmp rfi_done
rfi_argument:
 mov DWORD PTR [rbx],7
rfi_done:
 xor eax,eax
 add rsp,40
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_random_access_file_init_ids ENDP
