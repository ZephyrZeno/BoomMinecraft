; InetAddress.init JNI-cache boundary. Metadata/field IDs prepared by compiler.
; IADR80/1: state8D, fieldCount12D=5, ownerClass16, type0/1 24/32,
; packed layout0/1 40/48, rows56, reserved64/72. Row24 owner0D,width4D,
; offset8Q, originalFieldIndex16D, reference20D. No OOPs or heap allocation.
; Bootstrap metadata is pinned by image lifetime; this replaces JNI GlobalRefs.
option casemap:none
EXTERN GetCurrentThreadId:PROC
EXTERN SwitchToThread:PROC
EXTERN WSAStartup:PROC
EXTERN WSACleanup:PROC
EXTERN socket:PROC
EXTERN closesocket:PROC
EXTERN boom_heap_contains:PROC
EXTERN boom_string_view:PROC
PUBLIC boom_inet_address_init
PUBLIC boom_inet_address_available
.code
; (ctx RCX, unused argv RDX, cache R8). Existing Java errors stay untouched.
boom_inet_address_init PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov rsi,r8
    test rbx,rbx
    jz inet_done
    cmp DWORD PTR [rbx],0
    jne inet_done
    test rsi,rsi
    jz inet_bad
    cmp DWORD PTR [rsi],052444149h
    jne inet_bad
    cmp DWORD PTR [rsi+4],2
    je inet_family_metadata
    cmp DWORD PTR [rsi+4],1
    jne inet_bad
    cmp DWORD PTR [rsi+12],5
    jne inet_bad
    cmp QWORD PTR [rsi+64],0
    jne inet_bad
    cmp QWORD PTR [rsi+72],0
    jne inet_bad
    jmp inet_header_ready
inet_family_metadata:
    cmp QWORD PTR [rsi+72],4
    je inet_family4
    cmp QWORD PTR [rsi+72],6
    jne inet_bad
    cmp DWORD PTR [rsi+12],5
    jne inet_bad
    jmp inet_family_constructor
inet_family4:
    cmp DWORD PTR [rsi+12],0
    jne inet_bad
    mov rax,QWORD PTR [rsi+24]
    cmp rax,QWORD PTR [rsi+32]
    jne inet_bad
inet_family_constructor:
    ; Symbolic VM method identity; init caches it without invoking Java Code.
    mov rax,QWORD PTR [rsi+64]
    test rax,rax
    jz inet_bad
    cmp DWORD PTR [rax],044494D4Ah
    jne inet_bad
    cmp DWORD PTR [rax+4],1
    jne inet_bad
    mov rdx,QWORD PTR [rsi+24]
    cmp QWORD PTR [rax+8],rdx
    jne inet_bad
    cmp DWORD PTR [rax+16],65535
    jae inet_bad
    cmp DWORD PTR [rax+20],0
    jne inet_bad
    cmp QWORD PTR [rax+24],0
    jne inet_bad
inet_header_ready:
    mov eax,DWORD PTR [rsi+8]
    test eax,eax
    jz inet_state_ok
    cmp eax,2
    jne inet_bad
inet_state_ok:
    mov rax,QWORD PTR [rsi+16]
    test rax,rax
    jz inet_bad
    cmp DWORD PTR [rax],0434C4153h
    jne inet_bad
    cmp DWORD PTR [rax+4],2
    jne inet_bad
    mov ecx,DWORD PTR [rax+8]
    cmp ecx,2
    je inet_owner_ok
    cmp ecx,1
    jne inet_bad
    call GetCurrentThreadId
    mov rcx,QWORD PTR [rsi+16]
    cmp DWORD PTR [rcx+12],eax
    jne inet_bad
inet_owner_ok:
    xor ecx,ecx
inet_types:
    mov rax,QWORD PTR [rsi+rcx*8+24]
    test rax,rax
    jz inet_bad
    cmp DWORD PTR [rax],054595045h
    jne inet_bad
    cmp DWORD PTR [rax+4],1
    jne inet_bad
    cmp DWORD PTR [rax+8],1
    jne inet_bad
    inc ecx
    cmp ecx,2
    jb inet_types
    cmp DWORD PTR [rsi+12],0
    je inet_publish
    mov r10,QWORD PTR [rsi+56]
    test r10,r10
    jz inet_bad
    xor r11d,r11d
inet_rows:
    mov ecx,DWORD PTR [r10]
    cmp ecx,1
    ja inet_bad
    mov rax,QWORD PTR [rsi+rcx*8+40]
    test rax,rax
    jz inet_bad
    cmp DWORD PTR [rax],04F424A43h
    jne inet_bad
    cmp DWORD PTR [rax+4],2
    jne inet_bad
    mov edx,DWORD PTR [rax+16]
    cmp edx,DWORD PTR [rax+20]
    ja inet_bad
    shl rdx,3
    cmp rdx,QWORD PTR [rax+8]
    ja inet_bad
    mov rcx,QWORD PTR [r10+8]
    mov r8d,DWORD PTR [r10+4]
    add r8,rcx
    jc inet_bad
    cmp r8,QWORD PTR [rax+8]
    ja inet_bad
    cmp DWORD PTR [r10+20],1
    ja inet_bad
    je inet_ref
    mov eax,DWORD PTR [r10+4]
    cmp eax,1
    je inet_primitive_width_ok
    cmp eax,4
    jne inet_bad
inet_primitive_width_ok:
    dec eax
    test ecx,eax
    jnz inet_bad
    cmp rcx,rdx
    jb inet_bad
    jmp inet_row_next
inet_ref:
    cmp DWORD PTR [r10+4],8
    jne inet_bad
    test ecx,7
    jnz inet_bad
    cmp r8,rdx
    ja inet_bad
inet_row_next:
    add r10,24
    inc r11d
    cmp r11d,DWORD PTR [rsi+12]
    jb inet_rows
inet_publish:
    mov eax,2
    xchg DWORD PTR [rsi+8],eax
    jmp inet_done
inet_bad:
    mov DWORD PTR [rbx],7
inet_done:
    xor eax,eax
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_inet_address_init ENDP

; (ctx RCX, unused argv RDX, IPAV64/1 pool R8, query R9D: IPv4=0/IPv6=1).
; Pool: state8D (cold0,busy1,ready2,failed3), errorKind12D,
; prefer4 Java static-cell16Q, STRP3 pool24Q, IADR cache32Q,
; IPv4/IPv6 results40/44D, probePairs48D, prefer4 snapshot52D,
; WSAStartup error56D, reserved60D. No Java allocation or external contact.
; A single ASM owner probes both address families. The property is the original
; InetAddress Java initializer's snapshot; later System.setProperty is ignored.
; Temporary Winsock ownership is balanced here. Full libnet lifecycle, DNS and
; TCP/UDP operations remain separate, unsupported runtime work.
boom_inet_address_available PROC FRAME
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
    sub rsp,448
    .allocstack 448
    .endprolog
    mov rbx,rcx
    mov rsi,r8
    mov edi,r9d
    mov DWORD PTR [rsp+440],edi
    test rbx,rbx
    jz ipav_done
    cmp DWORD PTR [rbx],0
    jne ipav_done
    test rsi,rsi
    jz ipav_bad
    cmp edi,1
    ja ipav_bad
    cmp DWORD PTR [rsi],056415049h
    jne ipav_bad
    cmp DWORD PTR [rsi+4],1
    jne ipav_bad
    cmp DWORD PTR [rsi+60],0
    jne ipav_bad
    mov r8,QWORD PTR [rsi+32]
    test r8,r8
    jz ipav_bad
    cmp DWORD PTR [r8+4],1
    jne ipav_bad
    cmp DWORD PTR [r8+8],2
    jne ipav_bad
    call boom_inet_address_init
    cmp DWORD PTR [rbx],0
    jne ipav_done
ipav_acquire:
    mov eax,DWORD PTR [rsi+8]
    cmp eax,2
    je ipav_result
    cmp eax,3
    je ipav_failed
    cmp eax,1
    je ipav_wait
    test eax,eax
    jnz ipav_bad
    mov edx,1
    lock cmpxchg DWORD PTR [rsi+8],edx
    jne ipav_acquire
    xor r12d,r12d
    mov rax,QWORD PTR [rsi+16]
    test rax,rax
    jz ipav_owner_bad
    mov r13,QWORD PTR [rax]
    mov rdi,QWORD PTR [rsi+24]
    test rdi,rdi
    jz ipav_owner_bad
    cmp DWORD PTR [rdi],053545250h
    jne ipav_owner_bad
    cmp DWORD PTR [rdi+4],3
    jne ipav_owner_bad
    test r13,r13
    jz ipav_preference_ready
    mov rcx,QWORD PTR [rdi+48]
    mov rdx,r13
    call boom_heap_contains
    test eax,eax
    jz ipav_owner_bad
    cmp QWORD PTR [r13-16],16
    jne ipav_owner_bad
    cmp DWORD PTR [r13-20],1
    jne ipav_owner_bad
    mov rcx,QWORD PTR [rdi+48]
    mov rdx,QWORD PTR [r13]
    call boom_heap_contains
    test eax,eax
    jz ipav_owner_bad
    mov rcx,r13
    mov rdx,QWORD PTR [rdi+40]
    mov r8,rbx
    call boom_string_view
    cmp DWORD PTR [rbx],0
    jne ipav_owner_reset
    cmp edx,4
    jne ipav_preference_ready
    movzx ecx,WORD PTR [rax]
    or ecx,32
    cmp ecx,116
    jne ipav_preference_ready
    movzx ecx,WORD PTR [rax+2]
    or ecx,32
    cmp ecx,114
    jne ipav_preference_ready
    movzx ecx,WORD PTR [rax+4]
    or ecx,32
    cmp ecx,117
    jne ipav_preference_ready
    movzx ecx,WORD PTR [rax+6]
    or ecx,32
    cmp ecx,101
    sete r12b
ipav_preference_ready:
    ; Preserve the query separately: RDI was used as the STRP pointer above.
    mov DWORD PTR [rsi+52],r12d
    mov ecx,0202h
    lea rdx,[rsp+32]                ; WSADATA x64: 408 bytes
    call WSAStartup
    test eax,eax
    jnz ipav_startup_failed
    mov DWORD PTR [rsi+40],0
    mov DWORD PTR [rsi+44],0
    mov ecx,2                       ; AF_INET
    mov edx,1                       ; SOCK_STREAM
    xor r8d,r8d
    call socket
    cmp rax,-1
    je ipav_probe6
    mov rcx,rax
    call closesocket
    mov DWORD PTR [rsi+40],1
ipav_probe6:
    mov ecx,23                      ; Windows AF_INET6
    mov edx,1
    xor r8d,r8d
    call socket
    cmp rax,-1
    je ipav_cleanup
    mov rcx,rax
    call closesocket
    xor r12d,1
    mov DWORD PTR [rsi+44],r12d
ipav_cleanup:
    call WSACleanup
    inc DWORD PTR [rsi+48]
    mov eax,2
    xchg DWORD PTR [rsi+8],eax
    jmp ipav_ready_result
ipav_wait:
    pause
    call SwitchToThread
    jmp ipav_acquire
ipav_startup_failed:
    mov DWORD PTR [rsi+56],eax
    mov DWORD PTR [rsi+12],20
    mov eax,3
    xchg DWORD PTR [rsi+8],eax
ipav_failed:
    cmp DWORD PTR [rsi+12],20
    jne ipav_bad
    mov DWORD PTR [rbx],20
    jmp ipav_done
ipav_owner_bad:
    mov DWORD PTR [rbx],7
ipav_owner_reset:
    xor eax,eax
    xchg DWORD PTR [rsi+8],eax
    jmp ipav_done
ipav_bad:
    mov DWORD PTR [rbx],7
ipav_done:
    xor eax,eax
    jmp ipav_epilog
ipav_result:
    ; The entry query is saved in the stack slot before any RDI reuse.
ipav_ready_result:
    mov edi,DWORD PTR [rsp+440]
    mov eax,DWORD PTR [rsi+rdi*4+40]
ipav_epilog:
    add rsp,448
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    ret
boom_inet_address_available ENDP
END
