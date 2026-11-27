; Process-owned RW native regions. Called before Java and after every user.
; No Java class/method numbers, oops, Context writes or automatic GC.
.const
mm_report_name WORD 'b','o','o','m','-','n','a','t','i','v','e','-'
 WORD 'm','e','m','o','r','y','-','o','w','n','e','r','.','b','i','n',0
.data
ALIGN 8
PUBLIC boom_main_native_memory_owner
boom_main_native_memory_owner BYTE 128 DUP(0)
PUBLIC boom_main_native_memory_report
; NMWO320/1. Unsampled operation statuses remain FFFFFFFF.
boom_main_native_memory_report DWORD 04F574D4Eh,1,320,0
 DWORD 4 DUP(0FFFFFFFFh)
 BYTE 288 DUP(0)
mm_report_written DWORD 0
.code

PUBLIC boom_main_native_memory_prepare
boom_main_native_memory_prepare PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov eax,9
 test DWORD PTR [boom_main_native_memory_report+12],8
 jnz mmp_done
 xor eax,eax
 test DWORD PTR [boom_main_native_memory_report+12],4
 jnz mmp_done
 or DWORD PTR [boom_main_native_memory_report+12],1
 lea rcx,boom_main_native_memory_owner
 mov edx,128
 mov r8d,MM_CAPACITY
 mov r9,MM_BUDGET
 call boom_native_memory_init
 mov DWORD PTR [boom_main_native_memory_report+16],eax
 test eax,eax
 jnz mmp_done
 or DWORD PTR [boom_main_native_memory_report+12],2
 lea rcx,boom_main_native_memory_owner
 call boom_provider_owned_unsafe_bind
 mov DWORD PTR [boom_main_native_memory_report+20],eax
 test eax,eax
 jnz mmp_done
 or DWORD PTR [boom_main_native_memory_report+12],4
mmp_done:
 add rsp,32
 pop rbx
 ret
boom_main_native_memory_prepare ENDP

; Snapshot after all managed/native users, before core close frees its metadata.
mm_capture_before PROC PRIVATE
 lea r10,boom_main_native_memory_owner
 lea r11,boom_main_native_memory_report
 mov eax,DWORD PTR [r10+MMO_STATE]
 mov DWORD PTR [r11+32],eax
 mov rax,QWORD PTR [r10+MMO_LIVE]
 mov QWORD PTR [r11+40],rax
 mov rax,QWORD PTR [r10+MMO_ACTIVE]
 mov QWORD PTR [r11+56],rax
 mov rax,QWORD PTR [r10+MMO_LOGICAL_BYTES]
 mov QWORD PTR [r11+72],rax
 mov rax,QWORD PTR [r10+MMO_METADATA_BYTES]
 mov QWORD PTR [r11+88],rax
 mov rax,QWORD PTR [r10+MMO_BUDGET]
 mov QWORD PTR [r11+104],rax
 mov eax,DWORD PTR [r10+MMO_CAPACITY]
 mov DWORD PTR [r11+112],eax
 ret
mm_capture_before ENDP

mm_capture_after PROC PRIVATE
 lea r10,boom_main_native_memory_owner
 lea r11,boom_main_native_memory_report
 mov eax,DWORD PTR [r10+MMO_STATE]
 mov DWORD PTR [r11+36],eax
 mov rax,QWORD PTR [r10+MMO_LIVE]
 mov QWORD PTR [r11+48],rax
 mov rax,QWORD PTR [r10+MMO_ACTIVE]
 mov QWORD PTR [r11+64],rax
 mov rax,QWORD PTR [r10+MMO_LOGICAL_BYTES]
 mov QWORD PTR [r11+80],rax
 mov rax,QWORD PTR [r10+MMO_METADATA_BYTES]
 mov QWORD PTR [r11+96],rax
 mov eax,DWORD PTR [r10+MMO_OS_ERROR]
 mov DWORD PTR [r11+116],eax
 mov rax,QWORD PTR [r10+MMO_ALLOCATIONS]
 mov QWORD PTR [r11+120],rax
 mov rax,QWORD PTR [r10+MMO_FREES]
 mov QWORD PTR [r11+128],rax
 mov rax,QWORD PTR [r10+MMO_RESIZES]
 mov QWORD PTR [r11+136],rax
 mov rax,QWORD PTR [r10+MMO_SEQUENCE]
 mov QWORD PTR [r11+272],rax
 ret
mm_capture_after ENDP

; Context32* is observed byte for byte and never passed to another function.
; Busy/failed core close keeps the actual owner bound; nothing reports closed.
PUBLIC boom_main_native_memory_close
boom_main_native_memory_close PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,32
 .allocstack 32
 .endprolog
 mov eax,87
 test rcx,rcx
 jz mmc_done
 mov rbx,rcx
 lea rdi,boom_main_native_memory_report
 xor ecx,ecx
mmc_snapshot:
 mov rax,QWORD PTR [rbx+rcx*8]
 mov QWORD PTR [rdi+rcx*8+160],rax
 inc ecx
 cmp ecx,4
 jb mmc_snapshot
 call mm_capture_before
 or DWORD PTR [boom_main_native_memory_report+12],8
 xor esi,esi
 test DWORD PTR [boom_main_native_memory_report+12],2
 jz mmc_after
 lea rcx,boom_main_native_memory_owner
 call boom_native_memory_close
 mov DWORD PTR [boom_main_native_memory_report+24],eax
 mov esi,eax
 test eax,eax
 jnz mmc_after
 or DWORD PTR [boom_main_native_memory_report+12],16
 call boom_provider_owned_unsafe_unbind
 mov DWORD PTR [boom_main_native_memory_report+28],eax
 mov esi,eax
 test eax,eax
 jnz mmc_after
 or DWORD PTR [boom_main_native_memory_report+12],32
mmc_after:
 call mm_capture_after
 mov DWORD PTR [rdi+144],1
 xor ecx,ecx
mmc_compare:
 mov rax,QWORD PTR [rbx+rcx*8]
 mov QWORD PTR [rdi+rcx*8+192],rax
 cmp rax,QWORD PTR [rdi+rcx*8+160]
 je mmc_same_qword
 mov DWORD PTR [rdi+144],0
 test esi,esi
 jnz mmc_same_qword
 mov esi,13
mmc_same_qword:
 inc ecx
 cmp ecx,4
 jb mmc_compare
 cmp DWORD PTR [rdi+144],1
 jne mmc_status
 or DWORD PTR [rdi+12],64
mmc_status:
 mov DWORD PTR [rdi+148],esi
 mov eax,esi
mmc_done:
 add rsp,32
 pop rdi
 pop rsi
 pop rbx
 ret
boom_main_native_memory_close ENDP

PUBLIC boom_main_native_memory_write_report
boom_main_native_memory_write_report PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,64
 .allocstack 64
 .endprolog
 lea r10,boom_owned_unsafe_counters
 lea r11,boom_main_native_memory_report
 xor ecx,ecx
mmw_counter:
 mov rax,QWORD PTR [r10+rcx*8]
 mov QWORD PTR [r11+rcx*8+224],rax
 inc ecx
 cmp ecx,6
 jb mmw_counter
 lea rcx,mm_report_name
 mov edx,040000000h
 mov r8d,1
 xor r9d,r9d
 mov DWORD PTR [rsp+32],1
 mov DWORD PTR [rsp+40],128
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 je mmw_os_error
 mov rbx,rax
 mov rcx,rax
 lea rdx,boom_main_native_memory_report
 mov r8d,320
 lea r9,mm_report_written
 mov QWORD PTR [rsp+32],0
 call WriteFile
 test eax,eax
 jz mmw_write_failed
 cmp DWORD PTR [mm_report_written],320
 jne mmw_short_write
 mov rcx,rbx
 call CloseHandle
 test eax,eax
 jz mmw_os_error
 xor eax,eax
 jmp mmw_done
mmw_write_failed:
 call GetLastError
 test eax,eax
 jnz mmw_save_error
mmw_short_write:
 mov eax,29
mmw_save_error:
 mov DWORD PTR [rsp+56],eax
 mov rcx,rbx
 call CloseHandle
 mov eax,DWORD PTR [rsp+56]
 jmp mmw_done
mmw_os_error:
 call GetLastError
 test eax,eax
 jnz mmw_done
 mov eax,31
mmw_done:
 add rsp,64
 pop rbx
 ret
boom_main_native_memory_write_report ENDP
