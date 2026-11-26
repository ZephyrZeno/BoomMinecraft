; Native process termination, MASM only. Original Java runs shutdown hooks and
; owns Shutdown.halt's monitor. BeforeHalt records an event; this VM has no JFR.
; SHUT32/1: eventCount8Q, lastStatus16D, haltRequested20D,reserved24Q.
option casemap:none
EXTERN ExitProcess:PROC
PUBLIC boom_shutdown_native
.code
; (ctx,argv,pool,operation0before/1halt)->void. Halt never returns successfully.
boom_shutdown_native PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    test rcx,rcx
    jz shutdown_return
    cmp DWORD PTR [rcx],0
    jne shutdown_return
    test r8,r8
    jz shutdown_bad
    cmp DWORD PTR [r8],053485554h
    jne shutdown_bad
    cmp DWORD PTR [r8+4],1
    jne shutdown_bad
    cmp QWORD PTR [r8+24],0
    jne shutdown_bad
    cmp DWORD PTR [r8+20],1
    ja shutdown_bad
    test r9d,r9d
    jz shutdown_event
    cmp r9d,1
    jne shutdown_bad
    test rdx,rdx
    jz shutdown_bad
    mov eax,DWORD PTR [rdx]
    mov DWORD PTR [r8+16],eax
    mov edx,1
    xchg DWORD PTR [r8+20],edx
    mov ecx,eax
    call ExitProcess
    int 3
shutdown_event:
    lock inc QWORD PTR [r8+8]
    jmp shutdown_return
shutdown_bad:
    mov DWORD PTR [rcx],7
shutdown_return:
    xor eax,eax
    add rsp,40
    ret
boom_shutdown_native ENDP
END
