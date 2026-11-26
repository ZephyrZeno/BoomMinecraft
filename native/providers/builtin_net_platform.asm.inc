; Internal Windows platform lifetime for a source-bound builtin net module.
; This is not JNI_OnLoad and does not read or invent Java property values.
; NETM80/2: SRW8,state16,users20,ownedWSA24,preferV4_28,IPv4_32,IPv6_36,
; reuseport40,reserved44,startupCount48,cleanupCount56,probeSocket64,
; probePending72,reserved76. States: closed0, ready1, failed-owned2.
; start(pool, actual preferIPv4Stack BOOL), acquire/release/close(pool) -> status.
; Callers lease this owner while using Winsock. Each successful startup owns
; exactly one process-local Winsock reference until close; probes close sockets.
EXTERN AcquireSRWLockExclusive:PROC
EXTERN ReleaseSRWLockExclusive:PROC
EXTERN WSAStartup:PROC
EXTERN WSACleanup:PROC
EXTERN WSAGetLastError:PROC
EXTERN socket:PROC
EXTERN closesocket:PROC
PUBLIC boom_builtin_net_platform_start
PUBLIC boom_builtin_net_platform_acquire
PUBLIC boom_builtin_net_platform_release
PUBLIC boom_builtin_net_platform_close
.code
net_platform_valid PROC PRIVATE
 test rcx,rcx
 jz np_invalid
 cmp DWORD PTR [rcx],04D54454Eh
 jne np_invalid
 cmp DWORD PTR [rcx+4],2
 jne np_invalid
 cmp DWORD PTR [rcx+44],0
 jne np_invalid
 cmp DWORD PTR [rcx+76],0
 jne np_invalid
 mov eax,1
 ret
np_invalid:
 xor eax,eax
 ret
net_platform_valid ENDP

boom_builtin_net_platform_start PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 sub rsp,552
 .allocstack 552
 .endprolog
 mov rbx,rcx
 mov esi,edx
 call net_platform_valid
 test eax,eax
 jz nps_invalid
 cmp esi,1
 ja nps_invalid
 lea rcx,[rbx+8]
 call AcquireSRWLockExclusive
 mov r12d,87
 cmp DWORD PTR [rbx+16],0
 je nps_cold
 mov r12d,21
 cmp DWORD PTR [rbx+16],2
 je nps_unlock
 mov r12d,87
 cmp DWORD PTR [rbx+16],1
 jne nps_unlock
 cmp DWORD PTR [rbx+24],1
 jne nps_unlock
 cmp DWORD PTR [rbx+72],0
 jne nps_unlock
 cmp QWORD PTR [rbx+64],0
 jne nps_unlock
 mov r12d,183
 cmp DWORD PTR [rbx+28],esi
 jne nps_unlock
 xor r12d,r12d
 jmp nps_unlock
nps_cold:
 cmp DWORD PTR [rbx+20],0
 jne nps_unlock
 cmp DWORD PTR [rbx+24],0
 jne nps_unlock
 cmp QWORD PTR [rbx+64],0
 jne nps_unlock
 cmp DWORD PTR [rbx+72],0
 jne nps_unlock
 mov ecx,0202h
 lea rdx,[rsp+32]
 call WSAStartup
 mov r12d,eax
 test eax,eax
 jnz nps_unlock
 inc QWORD PTR [rbx+48]
 mov DWORD PTR [rbx+24],1
 ; Every partially initialized owner is failed-owned until both probes finish.
 mov DWORD PTR [rbx+16],2
 mov DWORD PTR [rbx+28],esi
 mov QWORD PTR [rbx+32],0
 mov DWORD PTR [rbx+40],0
 xor edi,edi
 mov DWORD PTR [rsp+544],0
 mov ecx,2
 mov edx,1
 xor r8d,r8d
 call socket
 cmp rax,-1
 je nps_probe_v6
 mov QWORD PTR [rbx+64],rax
 mov DWORD PTR [rbx+72],1
 mov rcx,rax
 call closesocket
 test eax,eax
 jnz nps_probe_close_failed
 mov QWORD PTR [rbx+64],0
 mov DWORD PTR [rbx+72],0
 mov edi,1
nps_probe_v6:
 ; Probe IPv6 even when the Java property later restricts its availability.
 mov ecx,23
 mov edx,1
 xor r8d,r8d
 call socket
 cmp rax,-1
 je nps_publish
 mov QWORD PTR [rbx+64],rax
 mov DWORD PTR [rbx+72],1
 mov rcx,rax
 call closesocket
 test eax,eax
 jnz nps_probe_close_failed
 mov QWORD PTR [rbx+64],0
 mov DWORD PTR [rbx+72],0
 mov DWORD PTR [rsp+544],1
nps_publish:
 mov DWORD PTR [rbx+28],esi
 mov DWORD PTR [rbx+32],edi
 mov eax,DWORD PTR [rsp+544]
 test esi,esi
 jz nps_v6_result
 xor eax,eax
nps_v6_result:
 mov DWORD PTR [rbx+36],eax
 ; The locked Windows implementation reports no SO_REUSEPORT support.
 mov DWORD PTR [rbx+40],0
 mov DWORD PTR [rbx+16],1
 xor r12d,r12d
 jmp nps_unlock
nps_probe_close_failed:
 call WSAGetLastError
 mov r12d,eax
 test r12d,r12d
 jnz nps_unlock
 mov r12d,31
 ; Keep the actual failed socket and Winsock reference for explicit close.
 ; Cleanup cannot retire an unclosed probe when another owner remains active.
nps_unlock:
 lea rcx,[rbx+8]
 call ReleaseSRWLockExclusive
 mov eax,r12d
 jmp nps_done
nps_invalid:
 mov eax,87
nps_done:
 add rsp,552
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_builtin_net_platform_start ENDP

boom_builtin_net_platform_acquire PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 call net_platform_valid
 test eax,eax
 jz npa_invalid
 lea rcx,[rbx+8]
 call AcquireSRWLockExclusive
 mov esi,21
 cmp DWORD PTR [rbx+16],1
 jne npa_unlock
 cmp DWORD PTR [rbx+24],1
 jne npa_unlock
 cmp DWORD PTR [rbx+72],0
 jne npa_unlock
 cmp QWORD PTR [rbx+64],0
 jne npa_unlock
 mov esi,534
 cmp DWORD PTR [rbx+20],-1
 je npa_unlock
 inc DWORD PTR [rbx+20]
 xor esi,esi
npa_unlock:
 lea rcx,[rbx+8]
 call ReleaseSRWLockExclusive
 mov eax,esi
 jmp npa_done
npa_invalid:
 mov eax,87
npa_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_builtin_net_platform_acquire ENDP

boom_builtin_net_platform_release PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 call net_platform_valid
 test eax,eax
 jz npr_invalid
 lea rcx,[rbx+8]
 call AcquireSRWLockExclusive
 mov esi,87
 cmp DWORD PTR [rbx+16],1
 jne npr_unlock
 cmp DWORD PTR [rbx+24],1
 jne npr_unlock
 cmp DWORD PTR [rbx+20],0
 je npr_unlock
 dec DWORD PTR [rbx+20]
 xor esi,esi
npr_unlock:
 lea rcx,[rbx+8]
 call ReleaseSRWLockExclusive
 mov eax,esi
 jmp npr_done
npr_invalid:
 mov eax,87
npr_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_builtin_net_platform_release ENDP

boom_builtin_net_platform_close PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,40
 .allocstack 40
 .endprolog
 mov rbx,rcx
 call net_platform_valid
 test eax,eax
 jz npc_invalid
 lea rcx,[rbx+8]
 call AcquireSRWLockExclusive
 mov esi,170
 cmp DWORD PTR [rbx+20],0
 jne npc_unlock
 mov esi,87
 cmp DWORD PTR [rbx+16],0
 je npc_cold
 cmp DWORD PTR [rbx+16],1
 je npc_owned
 cmp DWORD PTR [rbx+16],2
 jne npc_unlock
npc_owned:
 cmp DWORD PTR [rbx+24],1
 jne npc_unlock
 mov DWORD PTR [rbx+16],2
 mov QWORD PTR [rbx+32],0
 mov DWORD PTR [rbx+40],0
 cmp DWORD PTR [rbx+72],0
 je npc_no_probe
 cmp DWORD PTR [rbx+72],1
 jne npc_unlock
 mov rcx,QWORD PTR [rbx+64]
 call closesocket
 test eax,eax
 jnz npc_os_failed
 mov QWORD PTR [rbx+64],0
 mov DWORD PTR [rbx+72],0
npc_no_probe:
 cmp QWORD PTR [rbx+64],0
 jne npc_unlock
 call WSACleanup
 test eax,eax
 jnz npc_os_failed
 inc QWORD PTR [rbx+56]
 mov QWORD PTR [rbx+16],0
 mov QWORD PTR [rbx+24],0
 mov QWORD PTR [rbx+32],0
 mov DWORD PTR [rbx+40],0
 mov QWORD PTR [rbx+64],0
 mov DWORD PTR [rbx+72],0
 jmp npc_success
npc_cold:
 cmp DWORD PTR [rbx+24],0
 jne npc_unlock
 cmp QWORD PTR [rbx+64],0
 jne npc_unlock
 cmp DWORD PTR [rbx+72],0
 jne npc_unlock
npc_success:
 xor esi,esi
 jmp npc_unlock
npc_os_failed:
 call WSAGetLastError
 mov esi,eax
 test esi,esi
 jnz npc_unlock
 mov esi,31
npc_unlock:
 lea rcx,[rbx+8]
 call ReleaseSRWLockExclusive
 mov eax,esi
 jmp npc_done
npc_invalid:
 mov eax,87
npc_done:
 add rsp,40
 pop rsi
 pop rbx
 ret
boom_builtin_net_platform_close ENDP
