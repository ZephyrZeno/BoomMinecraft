; Development probe only: the persistent MASM pool invokes this ABI directly.
option casemap:none
EXTERN boom_fd_service:PROC
PUBLIC boom_entry
.code
boom_entry PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    mov r8,QWORD PTR [rdx+40]
    mov r9d,3
    call boom_fd_service
    add rsp,40
    ret
boom_entry ENDP
END
