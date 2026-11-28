; MHRO128/1, Record128, 4096 methods and an explicit 8192-QWORD oop bank.
; Native closed-image metadata owner. No Java callback, injected field or IO.
.data
ALIGN 8
PUBLIC boom_mhn_method_owner
PUBLIC boom_mhn_method_records
PUBLIC boom_mhn_resolved_method_roots
boom_mhn_method_owner BYTE 128 DUP(0)
ALIGN 8
boom_mhn_method_records BYTE 524288 DUP(0)
ALIGN 8
boom_mhn_resolved_method_roots QWORD 8192 DUP(0)
.code

; Only volatile registers. This module owns one exact native header and pool.
mhro_header_valid PROC PRIVATE
 xor eax,eax
 cmp DWORD PTR [rbx],04D48524Fh
 jne mhro_header_done
 cmp DWORD PTR [rbx+4],1
 jne mhro_header_done
 cmp DWORD PTR [rbx+8],128
 jne mhro_header_done
 cmp DWORD PTR [rbx+24],4096
 jne mhro_header_done
 cmp DWORD PTR [rbx+28],128
 jne mhro_header_done
 lea r10,boom_mhn_method_records
 cmp QWORD PTR [rbx+32],r10
 jne mhro_header_done
 lea r10,boom_mhn_resolved_method_roots
 cmp QWORD PTR [rbx+40],r10
 jne mhro_header_done
 lea r10,boom_mhn_method_owner_pool
 cmp QWORD PTR [rbx+48],r10
 jne mhro_header_done
 mov r11,QWORD PTR [r10+16]
 cmp QWORD PTR [rbx+56],r11
 jne mhro_header_done
 mov r11,QWORD PTR [r10+48]
 cmp QWORD PTR [rbx+64],r11
 jne mhro_header_done
 cmp QWORD PTR [rbx+96],r10
 jne mhro_header_done
 cmp QWORD PTR [rbx+104],8192
 jne mhro_header_done
 cmp QWORD PTR [rbx+112],0
 jne mhro_header_done
 cmp QWORD PTR [rbx+120],0
 jne mhro_header_done
 mov eax,1
mhro_header_done:
 ret
mhro_header_valid ENDP

; Open before Java/VM bootstrap. The heap cell can still contain NULL then.
PUBLIC boom_mhn_method_owner_open
boom_mhn_method_owner_open PROC FRAME
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
 mov rsi,rdx
 lea rax,boom_mhn_method_owner
 cmp rbx,rax
 jne mhro_open_bad_unlocked
 lea rax,boom_mhn_method_owner_pool
 cmp rsi,rax
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [rsi],04D485250h
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [rsi+4],1
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [rsi+8],128
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [rsi+12],4096
 jne mhro_open_bad_unlocked
 lea rax,boom_mhn_method_records
 cmp QWORD PTR [rsi+24],rax
 jne mhro_open_bad_unlocked
 lea rax,boom_mhn_resolved_method_roots
 cmp QWORD PTR [rsi+32],rax
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [rsi+40],128
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [rsi+44],8192
 jne mhro_open_bad_unlocked
 cmp QWORD PTR [rsi+16],0
 je mhro_open_bad_unlocked
 cmp QWORD PTR [rsi+48],0
 je mhro_open_bad_unlocked
 cmp QWORD PTR [rsi+56],0
 jne mhro_open_bad_unlocked
 mov ecx,64
mhro_open_pointers:
 cmp QWORD PTR [rsi+rcx],0
 je mhro_open_bad_unlocked
 add ecx,8
 cmp ecx,104
 jb mhro_open_pointers
 cmp DWORD PTR [rsi+104],0
 je mhro_open_bad_unlocked
 cmp DWORD PTR [rsi+112],0
 je mhro_open_bad_unlocked
 cmp DWORD PTR [rsi+116],0
 jne mhro_open_bad_unlocked
 cmp QWORD PTR [rsi+120],0
 je mhro_open_bad_unlocked
 mov r10,QWORD PTR [rsi+80]
 cmp DWORD PTR [r10],04A434C53h
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [r10+4],1
 jne mhro_open_bad_unlocked
 mov r11,QWORD PTR [rsi+88]
 cmp DWORD PTR [r11],052545950h
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [r11+4],2
 jne mhro_open_bad_unlocked
 mov eax,DWORD PTR [r10+12]
 cmp eax,DWORD PTR [r11+12]
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [rsi+108],eax
 jae mhro_open_bad_unlocked
 cmp DWORD PTR [rsi+112],eax
 ja mhro_open_bad_unlocked
 mov r11,QWORD PTR [rsi+16]
 cmp QWORD PTR [r10+48],r11
 jne mhro_open_bad_unlocked
 mov r10,QWORD PTR [rsi+72]
 cmp DWORD PTR [r10],04F424A43h
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [r10+4],2
 jne mhro_open_bad_unlocked
 cmp QWORD PTR [r10+8],0
 jne mhro_open_bad_unlocked
 cmp DWORD PTR [r10+16],0
 jne mhro_open_bad_unlocked
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rbx],0
 je mhro_open_cold
 call mhro_header_valid
 test eax,eax
 jz mhro_open_bad
 cmp DWORD PTR [rbx+12],1
 jne mhro_open_bad
 xor edi,edi
 jmp mhro_open_unlock
mhro_open_cold:
 xor ecx,ecx
mhro_open_zero_header:
 cmp ecx,16
 je mhro_open_next_header
 cmp QWORD PTR [rbx+rcx],0
 jne mhro_open_bad
mhro_open_next_header:
 add ecx,8
 cmp ecx,128
 jb mhro_open_zero_header
 lea r10,boom_mhn_method_records
 mov ecx,65536
mhro_open_records_zero:
 cmp QWORD PTR [r10],0
 jne mhro_open_bad
 add r10,8
 dec ecx
 jnz mhro_open_records_zero
 lea r10,boom_mhn_resolved_method_roots
 mov ecx,8192
mhro_open_roots_zero:
 cmp QWORD PTR [r10],0
 jne mhro_open_bad
 add r10,8
 dec ecx
 jnz mhro_open_roots_zero
 mov DWORD PTR [rbx],04D48524Fh
 mov DWORD PTR [rbx+4],1
 mov DWORD PTR [rbx+8],128
 mov DWORD PTR [rbx+24],4096
 mov DWORD PTR [rbx+28],128
 lea rax,boom_mhn_method_records
 mov QWORD PTR [rbx+32],rax
 lea rax,boom_mhn_resolved_method_roots
 mov QWORD PTR [rbx+40],rax
 mov QWORD PTR [rbx+48],rsi
 mov rax,QWORD PTR [rsi+16]
 mov QWORD PTR [rbx+56],rax
 mov rax,QWORD PTR [rsi+48]
 mov QWORD PTR [rbx+64],rax
 mov QWORD PTR [rbx+88],1
 mov QWORD PTR [rbx+96],rsi
 mov QWORD PTR [rbx+104],8192
 mov DWORD PTR [rbx+12],1
 xor edi,edi
 jmp mhro_open_unlock
mhro_open_bad:
 mov edi,4
mhro_open_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp mhro_open_done
mhro_open_bad_unlocked:
 mov eax,4
mhro_open_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_mhn_method_owner_open ENDP

; An admission count spans callbacks, without holding SRW/Core leases.
PUBLIC boom_mhn_method_owner_enter
boom_mhn_method_owner_enter PROC FRAME
 push rbx
 .pushreg rbx
 push rdi
 .pushreg rdi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 lea rax,boom_mhn_method_owner
 cmp rbx,rax
 jne mhro_enter_bad_unlocked
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 call mhro_header_valid
 test eax,eax
 jz mhro_enter_bad
 mov edi,2
 cmp DWORD PTR [rbx+12],1
 jne mhro_enter_unlock
 cmp DWORD PTR [rbx+72],07FFFFFFFh
 jae mhro_enter_bad
 inc DWORD PTR [rbx+72]
 xor edi,edi
 jmp mhro_enter_unlock
mhro_enter_bad:
 mov edi,4
mhro_enter_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp mhro_enter_done
mhro_enter_bad_unlocked:
 mov eax,4
mhro_enter_done:
 add rsp,40
 pop rdi
 pop rbx
 ret
boom_mhn_method_owner_enter ENDP

PUBLIC boom_mhn_method_owner_leave
boom_mhn_method_owner_leave PROC FRAME
 push rbx
 .pushreg rbx
 push rdi
 .pushreg rdi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 lea rax,boom_mhn_method_owner
 cmp rbx,rax
 jne mhro_leave_bad_unlocked
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 call mhro_header_valid
 test eax,eax
 jz mhro_leave_bad
 cmp DWORD PTR [rbx+72],0
 je mhro_leave_bad
 dec DWORD PTR [rbx+72]
 xor edi,edi
 jmp mhro_leave_unlock
mhro_leave_bad:
 mov edi,4
mhro_leave_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp mhro_leave_done
mhro_leave_bad_unlocked:
 mov eax,4
mhro_leave_done:
 add rsp,40
 pop rdi
 pop rbx
 ret
boom_mhn_method_owner_leave ENDP

; Commit64: methodID0/holder4/slot8/flags12,row16,entry24(currently0),
; holderMirror32,candidateRMN40,sourceEpoch48,resultRMN56.
; Native trusted caller validates ordinary oops outside this publication lock.
PUBLIC boom_mhn_method_owner_intern
boom_mhn_method_owner_intern PROC FRAME
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
 mov rsi,rdx
 lea rax,boom_mhn_method_owner
 cmp rbx,rax
 jne mhro_intern_bad_unlocked
 test rsi,rsi
 jz mhro_intern_bad_unlocked
 cmp QWORD PTR [rsi+56],0
 jne mhro_intern_bad_unlocked
 cmp QWORD PTR [rsi+24],0
 jne mhro_intern_bad_unlocked
 cmp QWORD PTR [rsi+32],0
 je mhro_intern_bad_unlocked
 cmp QWORD PTR [rsi+40],0
 je mhro_intern_bad_unlocked
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 call mhro_header_valid
 test eax,eax
 jz mhro_intern_bad
 mov edi,2
 mov eax,DWORD PTR [rbx+12]
 dec eax
 cmp eax,1
 ja mhro_intern_unlock
 cmp DWORD PTR [rbx+72],0
 je mhro_intern_bad
 mov r12,QWORD PTR [rbx+48]
 mov edi,5
 mov rax,QWORD PTR [rsi+48]
 cmp rax,QWORD PTR [rbx+64]
 jne mhro_intern_unlock
 mov eax,DWORD PTR [rsi]
 cmp eax,DWORD PTR [r12+104]
 jae mhro_intern_bad
 mov ecx,DWORD PTR [rsi+4]
 cmp ecx,DWORD PTR [r12+112]
 jae mhro_intern_bad
 mov r10,QWORD PTR [r12+96]
 mov edx,DWORD PTR [rsi+8]
 cmp edx,DWORD PTR [r10+rcx*8+4]
 jae mhro_intern_bad
 add edx,DWORD PTR [r10+rcx*8]
 jc mhro_intern_bad
 cmp eax,edx
 jne mhro_intern_bad
 mov r10,QWORD PTR [r12+120]
 cmp DWORD PTR [r10],04E4D5448h
 jne mhro_intern_bad
 cmp DWORD PTR [r10+4],1
 jne mhro_intern_bad
 cmp DWORD PTR [r10+120],144
 jne mhro_intern_bad
 mov r11,QWORD PTR [rsi+16]
 sub r11,QWORD PTR [r10+40]
 jc mhro_intern_bad
 mov eax,DWORD PTR [r10+12]
 imul rax,144
 cmp r11,rax
 jae mhro_intern_bad
 mov rax,r11
 xor edx,edx
 mov ecx,144
 div rcx
 test rdx,rdx
 jnz mhro_intern_bad
 mov r10,QWORD PTR [rsi+16]
 mov eax,DWORD PTR [rsi+4]
 cmp eax,DWORD PTR [r10]
 jne mhro_intern_bad
 mov eax,DWORD PTR [rsi+8]
 cmp eax,DWORD PTR [r10+4]
 jne mhro_intern_bad
 mov eax,DWORD PTR [rsi+12]
 mov edx,eax
 and edx,0FFEFFFFFh
 mov ecx,DWORD PTR [r10+8]
 and ecx,0FFFFh
 or ecx,06010000h
 cmp edx,ecx
 jne mhro_intern_bad
 test eax,8
 jz mhro_intern_bad
 mov r13,-1
 xor r12d,r12d
mhro_intern_scan:
 mov r10,r12
 shl r10,7
 add r10,QWORD PTR [rbx+32]
 cmp DWORD PTR [r10],0
 je mhro_intern_free
 cmp DWORD PTR [r10],1
 je mhro_intern_temporary
 cmp DWORD PTR [r10],2
 jne mhro_intern_bad
 mov eax,DWORD PTR [r10+16]
 cmp eax,DWORD PTR [rsi]
 jne mhro_intern_next
 mov rax,QWORD PTR [r10+32]
 cmp rax,QWORD PTR [rsi+48]
 jne mhro_intern_stale
 mov eax,DWORD PTR [r10+20]
 cmp eax,DWORD PTR [rsi+4]
 jne mhro_intern_bad
 mov eax,DWORD PTR [r10+28]
 cmp eax,DWORD PTR [rsi+12]
 jne mhro_intern_bad
 mov r11,QWORD PTR [rbx+40]
 mov rax,r12
 shl rax,4
 add r11,rax
 mov rdx,QWORD PTR [rsi+32]
 cmp QWORD PTR [r11+8],rdx
 jne mhro_intern_bad
 mov rax,QWORD PTR [r11]
 test rax,rax
 jz mhro_intern_bad
 mov QWORD PTR [rsi+56],rax
 xor edi,edi
 jmp mhro_intern_unlock
mhro_intern_temporary:
 cmp DWORD PTR [r10+4],2
 jne mhro_intern_bad
 mov rax,QWORD PTR [rbx+64]
 cmp QWORD PTR [r10+32],rax
 jne mhro_intern_bad
 jmp mhro_intern_next
mhro_intern_free:
 cmp r13,-1
 jne mhro_intern_next
 xor ecx,ecx
mhro_intern_free_zero:
 cmp QWORD PTR [r10+rcx],0
 jne mhro_intern_bad
 add ecx,8
 cmp ecx,128
 jb mhro_intern_free_zero
 mov r13,r12
mhro_intern_next:
 inc r12d
 cmp r12d,4096
 jb mhro_intern_scan
 mov edi,3
 cmp r13,-1
 je mhro_intern_unlock
 mov r11,QWORD PTR [rbx+40]
 mov rax,r13
 shl rax,4
 add r11,rax
 cmp QWORD PTR [r11],0
 jne mhro_intern_bad
 cmp QWORD PTR [r11+8],0
 jne mhro_intern_bad
 mov rax,QWORD PTR [rbx+88]
 test rax,rax
 jz mhro_intern_bad
 cmp rax,-1
 je mhro_intern_bad
 inc QWORD PTR [rbx+88]
 mov r10,r13
 shl r10,7
 add r10,QWORD PTR [rbx+32]
 mov QWORD PTR [r10+8],rax
 mov eax,DWORD PTR [rsi]
 mov DWORD PTR [r10+16],eax
 mov eax,DWORD PTR [rsi+4]
 mov DWORD PTR [r10+20],eax
 mov eax,DWORD PTR [rsi+8]
 mov DWORD PTR [r10+24],eax
 mov eax,DWORD PTR [rsi+12]
 mov DWORD PTR [r10+28],eax
 mov rax,QWORD PTR [rsi+48]
 mov QWORD PTR [r10+32],rax
 mov rax,QWORD PTR [rsi+16]
 mov QWORD PTR [r10+40],rax
 mov DWORD PTR [r10+4],1
 mov eax,r13d
 shl eax,1
 mov DWORD PTR [r10+64],eax
 inc eax
 mov DWORD PTR [r10+68],eax
 mov rax,QWORD PTR [rsi+40]
 mov QWORD PTR [r11],rax
 mov QWORD PTR [rsi+56],rax
 mov rax,QWORD PTR [rsi+32]
 mov QWORD PTR [r11+8],rax
 mov DWORD PTR [r10],2
 inc DWORD PTR [rbx+76]
 xor edi,edi
 jmp mhro_intern_unlock
mhro_intern_stale:
 mov edi,5
 jmp mhro_intern_unlock
mhro_intern_bad:
 mov edi,4
mhro_intern_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp mhro_intern_done
mhro_intern_bad_unlocked:
 mov eax,4
mhro_intern_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_mhn_method_owner_intern ENDP

; Requires a successful owner_enter until the returned native row is consumed.
PUBLIC boom_mhn_method_owner_find
boom_mhn_method_owner_find PROC FRAME
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
 mov rsi,rdx
 xor edi,edi
 lea rax,boom_mhn_method_owner
 cmp rbx,rax
 jne mhro_find_done
 test rsi,rsi
 jz mhro_find_done
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 call mhro_header_valid
 test eax,eax
 jz mhro_find_unlock
 cmp DWORD PTR [rbx+72],0
 je mhro_find_unlock
 mov eax,DWORD PTR [rbx+12]
 dec eax
 cmp eax,1
 ja mhro_find_unlock
 xor ecx,ecx
 mov r11,QWORD PTR [rbx+40]
mhro_find_scan:
 cmp QWORD PTR [r11],rsi
 je mhro_find_match
 add r11,16
 inc ecx
 cmp ecx,4096
 jb mhro_find_scan
 jmp mhro_find_unlock
mhro_find_match:
 mov rdi,rcx
 shl rdi,7
 add rdi,QWORD PTR [rbx+32]
 cmp DWORD PTR [rdi],2
 jne mhro_find_reject
 mov rax,QWORD PTR [rbx+64]
 cmp QWORD PTR [rdi+32],rax
 je mhro_find_unlock
mhro_find_reject:
 xor edi,edi
mhro_find_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
mhro_find_done:
 mov rax,rdi
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_mhn_method_owner_find ENDP

; Called only after external Java/thread/monitor quiescence, before root snapshot.
; Preflight every row and root before clearing anything. Busy retains all roots.
PUBLIC boom_mhn_method_owner_close
boom_mhn_method_owner_close PROC FRAME
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
 lea rax,boom_mhn_method_owner
 cmp rbx,rax
 jne mhro_close_bad_unlocked
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 cmp DWORD PTR [rbx],0
 je mhro_close_cold
 call mhro_header_valid
 test eax,eax
 jz mhro_close_bad
 cmp DWORD PTR [rbx+12],3
 je mhro_close_ok
 mov DWORD PTR [rbx+12],2
 mov edi,2
 cmp DWORD PTR [rbx+72],0
 jne mhro_close_unlock
 cmp DWORD PTR [rbx+80],0
 jne mhro_close_unlock
 xor r12d,r12d
 xor r13d,r13d
 mov rsi,QWORD PTR [rbx+32]
 mov rdi,QWORD PTR [rbx+40]
mhro_close_preflight:
 cmp DWORD PTR [rsi],0
 je mhro_close_free
 cmp DWORD PTR [rsi],2
 jne mhro_close_bad
 cmp DWORD PTR [rsi+4],1
 jne mhro_close_bad
 cmp QWORD PTR [rsi+8],0
 je mhro_close_bad
 cmp QWORD PTR [rdi],0
 je mhro_close_bad
 cmp QWORD PTR [rdi+8],0
 je mhro_close_bad
 mov rax,QWORD PTR [rbx+64]
 cmp QWORD PTR [rsi+32],rax
 jne mhro_close_bad
 mov eax,r12d
 shl eax,1
 cmp DWORD PTR [rsi+64],eax
 jne mhro_close_bad
 inc eax
 cmp DWORD PTR [rsi+68],eax
 jne mhro_close_bad
 cmp QWORD PTR [rsi+48],0
 jne mhro_close_bad
 cmp QWORD PTR [rsi+56],0
 jne mhro_close_bad
 cmp DWORD PTR [rsi+72],0
 jne mhro_close_bad
 cmp DWORD PTR [rsi+76],0
 jne mhro_close_bad
 mov ecx,80
mhro_close_live_reserved:
 cmp QWORD PTR [rsi+rcx],0
 jne mhro_close_bad
 add ecx,8
 cmp ecx,128
 jb mhro_close_live_reserved
 inc r13d
 jmp mhro_close_next
mhro_close_free:
 cmp QWORD PTR [rdi],0
 jne mhro_close_bad
 cmp QWORD PTR [rdi+8],0
 jne mhro_close_bad
 xor ecx,ecx
mhro_close_free_zero:
 cmp QWORD PTR [rsi+rcx],0
 jne mhro_close_bad
 add ecx,8
 cmp ecx,128
 jb mhro_close_free_zero
mhro_close_next:
 add rsi,128
 add rdi,16
 inc r12d
 cmp r12d,4096
 jb mhro_close_preflight
 cmp r13d,DWORD PTR [rbx+76]
 jne mhro_close_bad
 xor eax,eax
 mov rdi,QWORD PTR [rbx+40]
 mov ecx,8192
 rep stosq
 mov rdi,QWORD PTR [rbx+32]
 mov ecx,65536
 rep stosq
 mov DWORD PTR [rbx+76],0
 mov DWORD PTR [rbx+84],0
 mov DWORD PTR [rbx+12],3
 jmp mhro_close_ok
mhro_close_cold:
 ; Failed open performs no native allocation/publication. A pristine cold
 ; owner is closeable, but no other header/root/record data may be discarded.
 xor ecx,ecx
mhro_close_cold_header:
 cmp ecx,16
 je mhro_close_cold_next
 cmp QWORD PTR [rbx+rcx],0
 jne mhro_close_bad
mhro_close_cold_next:
 add ecx,8
 cmp ecx,128
 jb mhro_close_cold_header
 lea r10,boom_mhn_method_records
 mov ecx,65536
mhro_close_cold_records:
 cmp QWORD PTR [r10],0
 jne mhro_close_bad
 add r10,8
 dec ecx
 jnz mhro_close_cold_records
 lea r10,boom_mhn_resolved_method_roots
 mov ecx,8192
mhro_close_cold_roots:
 cmp QWORD PTR [r10],0
 jne mhro_close_bad
 add r10,8
 dec ecx
 jnz mhro_close_cold_roots
mhro_close_ok:
 xor edi,edi
 jmp mhro_close_unlock
mhro_close_bad:
 mov DWORD PTR [rbx+12],4
 mov DWORD PTR [rbx+84],4
 mov edi,4
mhro_close_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp mhro_close_done
mhro_close_bad_unlocked:
 mov eax,4
mhro_close_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_mhn_method_owner_close ENDP

; Scratch32 {indexD,res0D,generationQ,exactRootPairQ,res0Q}. Temporary roots
; share the registered bank; no extra hidden oop storage or callback lock.
; RBX exact owner, RSI Scratch32 -> EAX1, R10 Record128, R11 root pair.
mhro_scratch_validate PROC PRIVATE
 xor eax,eax
 cmp DWORD PTR [rbx+72],0
 je mhro_sv_done
 cmp DWORD PTR [rbx+80],0
 je mhro_sv_done
 mov ecx,DWORD PTR [rbx+12]
 dec ecx
 cmp ecx,1
 ja mhro_sv_done
 cmp DWORD PTR [rsi+4],0
 jne mhro_sv_done
 cmp QWORD PTR [rsi+24],0
 jne mhro_sv_done
 mov ecx,DWORD PTR [rsi]
 cmp ecx,4096
 jae mhro_sv_done
 mov r10,rcx
 shl r10,7
 add r10,QWORD PTR [rbx+32]
 cmp DWORD PTR [r10],1
 jne mhro_sv_done
 cmp DWORD PTR [r10+4],2
 jne mhro_sv_done
 mov rdx,QWORD PTR [rsi+8]
 test rdx,rdx
 jz mhro_sv_done
 cmp QWORD PTR [r10+8],rdx
 jne mhro_sv_done
 mov rdx,QWORD PTR [rbx+64]
 cmp QWORD PTR [r10+32],rdx
 jne mhro_sv_done
 mov r11,rcx
 shl r11,4
 add r11,QWORD PTR [rbx+40]
 cmp QWORD PTR [rsi+16],r11
 jne mhro_sv_done
 shl ecx,1
 cmp DWORD PTR [r10+64],ecx
 jne mhro_sv_done
 inc ecx
 cmp DWORD PTR [r10+68],ecx
 jne mhro_sv_done
 cmp QWORD PTR [r10+16],0
 jne mhro_sv_done
 cmp QWORD PTR [r10+24],0
 jne mhro_sv_done
 cmp QWORD PTR [r10+40],0
 jne mhro_sv_done
 cmp QWORD PTR [r10+48],0
 jne mhro_sv_done
 cmp QWORD PTR [r10+56],0
 jne mhro_sv_done
 mov ecx,72
mhro_sv_zero:
 cmp QWORD PTR [r10+rcx],0
 jne mhro_sv_done
 add ecx,8
 cmp ecx,128
 jb mhro_sv_zero
 mov eax,1
mhro_sv_done:
 ret
mhro_scratch_validate ENDP

PUBLIC boom_mhn_method_scratch_acquire
boom_mhn_method_scratch_acquire PROC FRAME
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
 mov rsi,rdx
 lea rax,boom_mhn_method_owner
 cmp rbx,rax
 jne mhro_sa_bad_unlocked
 test rsi,rsi
 jz mhro_sa_bad_unlocked
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 call mhro_header_valid
 test eax,eax
 jz mhro_sa_bad
 cmp DWORD PTR [rbx+72],0
 je mhro_sa_bad
 mov eax,DWORD PTR [rbx+12]
 dec eax
 cmp eax,1
 ja mhro_sa_closed
 xor edx,edx
mhro_sa_scan:
 mov r10,rdx
 shl r10,7
 add r10,QWORD PTR [rbx+32]
 cmp DWORD PTR [r10],0
 je mhro_sa_free
 inc edx
 cmp edx,4096
 jb mhro_sa_scan
 mov edi,3
 jmp mhro_sa_unlock
mhro_sa_free:
 xor ecx,ecx
mhro_sa_zero:
 cmp QWORD PTR [r10+rcx],0
 jne mhro_sa_bad
 add ecx,8
 cmp ecx,128
 jb mhro_sa_zero
 mov r11,rdx
 shl r11,4
 add r11,QWORD PTR [rbx+40]
 cmp QWORD PTR [r11],0
 jne mhro_sa_bad
 cmp QWORD PTR [r11+8],0
 jne mhro_sa_bad
 mov rax,QWORD PTR [rbx+88]
 test rax,rax
 jz mhro_sa_bad
 cmp rax,-1
 je mhro_sa_bad
 inc QWORD PTR [rbx+88]
 mov QWORD PTR [r10+8],rax
 mov QWORD PTR [rsi+8],rax
 mov rax,QWORD PTR [rbx+64]
 mov QWORD PTR [r10+32],rax
 lea ecx,[rdx*2]
 mov DWORD PTR [r10+64],ecx
 inc ecx
 mov DWORD PTR [r10+68],ecx
 mov DWORD PTR [r10+4],2
 mov DWORD PTR [r10],1
 inc DWORD PTR [rbx+80]
 mov DWORD PTR [rsi],edx
 mov DWORD PTR [rsi+4],0
 mov QWORD PTR [rsi+16],r11
 mov QWORD PTR [rsi+24],0
 xor edi,edi
 jmp mhro_sa_unlock
mhro_sa_closed:
 mov edi,2
 jmp mhro_sa_unlock
mhro_sa_bad:
 mov edi,4
mhro_sa_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp mhro_sa_done
mhro_sa_bad_unlocked:
 mov eax,4
mhro_sa_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_mhn_method_scratch_acquire ENDP

; No Java call between ordinary heap allocation and this root publication.
PUBLIC boom_mhn_method_scratch_set
boom_mhn_method_scratch_set PROC FRAME
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
 mov rsi,rdx
 mov r12,r8
 mov r13,r9
 lea rax,boom_mhn_method_owner
 cmp rbx,rax
 jne mhro_ss_bad_unlocked
 test rsi,rsi
 jz mhro_ss_bad_unlocked
 test r12,r12
 jz mhro_ss_bad_unlocked
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 call mhro_header_valid
 test eax,eax
 jz mhro_ss_bad
 call mhro_scratch_validate
 test eax,eax
 jz mhro_ss_bad
 mov QWORD PTR [r11],r12
 mov QWORD PTR [r11+8],r13
 xor edi,edi
 jmp mhro_ss_unlock
mhro_ss_bad:
 mov edi,4
mhro_ss_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp mhro_ss_done
mhro_ss_bad_unlocked:
 mov eax,4
mhro_ss_done:
 add rsp,32
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_mhn_method_scratch_set ENDP

; Finally cleanup, independent of the caller's Context.kind/pending state.
PUBLIC boom_mhn_method_scratch_release
boom_mhn_method_scratch_release PROC FRAME
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
 mov rsi,rdx
 lea rax,boom_mhn_method_owner
 cmp rbx,rax
 jne mhro_sr_bad_unlocked
 test rsi,rsi
 jz mhro_sr_bad_unlocked
 lea rcx,[rbx+16]
 call AcquireSRWLockExclusive
 call mhro_header_valid
 test eax,eax
 jz mhro_sr_bad
 call mhro_scratch_validate
 test eax,eax
 jz mhro_sr_bad
 mov QWORD PTR [r11],0
 mov QWORD PTR [r11+8],0
 xor eax,eax
 mov rdi,r10
 mov ecx,16
 rep stosq
 mov rdi,rsi
 mov ecx,4
 rep stosq
 dec DWORD PTR [rbx+80]
 xor edi,edi
 jmp mhro_sr_unlock
mhro_sr_bad:
 mov edi,4
mhro_sr_unlock:
 lea rcx,[rbx+16]
 call ReleaseSRWLockExclusive
 mov eax,edi
 jmp mhro_sr_done
mhro_sr_bad_unlocked:
 mov eax,4
mhro_sr_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_mhn_method_scratch_release ENDP
