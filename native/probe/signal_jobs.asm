; Test adapter only: raw VM lookup jobs, not Java Signal invocation.
option casemap:none
EXTERN boom_signal_find:PROC
PUBLIC boom_signal_probe_bind
PUBLIC boom_signal_probe_job
.data
ALIGN 8
signal_probe_pool QWORD 0
.code
boom_signal_probe_bind PROC
    mov rax,rcx
    xchg QWORD PTR [signal_probe_pool],rax
    xor eax,eax
    ret
boom_signal_probe_bind ENDP
boom_signal_probe_job PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    mov r8,QWORD PTR [signal_probe_pool]
    call boom_signal_find
    add rsp,40
    ret
boom_signal_probe_job ENDP
END
