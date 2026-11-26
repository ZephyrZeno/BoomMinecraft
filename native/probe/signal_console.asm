; Isolated CLI tests. The parent creates a separate initially hidden console.
; No desktop interaction, key injection, account access or game execution.
option casemap:none
EXTERN boom_signal_control_create:PROC
EXTERN boom_signal_control_close:PROC
EXTERN boom_signal_control_register:PROC
EXTERN boom_signal_control_raise:PROC
EXTERN CreateEventW:PROC
EXTERN SetEvent:PROC
EXTERN CloseHandle:PROC
EXTERN WaitForSingleObject:PROC
EXTERN SetConsoleCtrlHandler:PROC
EXTERN GenerateConsoleCtrlEvent:PROC
EXTERN GetCurrentThreadId:PROC
EXTERN ExitProcess:PROC
PUBLIC signal_console_main
PUBLIC signal_default_2
PUBLIC signal_default_4
PUBLIC signal_default_6
PUBLIC signal_default_8
PUBLIC signal_default_11
PUBLIC signal_default_15
PUBLIC signal_default_22
.data
ALIGN 8
signal_console_config DWORD 053474346h,1
    QWORD OFFSET signal_console_dispatch,OFFSET signal_console_break,0,0,0
signal_console_control QWORD 0
signal_console_event QWORD 0
signal_console_ints QWORD 0
signal_console_breaks QWORD 0
signal_console_thread DWORD 0
signal_console_error DWORD 0
.code
signal_console_main PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,48
    .allocstack 48
    .endprolog
    call GetCurrentThreadId
    mov DWORD PTR signal_console_thread,eax
    xor ecx,ecx
    xor edx,edx
    call SetConsoleCtrlHandler
    test eax,eax
    jz signal_console_fail_1
    xor ecx,ecx
    xor edx,edx
    xor r8d,r8d
    xor r9d,r9d
    call CreateEventW
    test rax,rax
    jz signal_console_fail_1
    mov QWORD PTR signal_console_event,rax
    lea rcx,signal_console_config
    call boom_signal_control_create
    test rax,rax
    jz signal_console_fail_2
    mov QWORD PTR signal_console_control,rax
    mov rcx,rax
    mov edx,2
    mov r8d,1
    call boom_signal_control_register
    test rax,rax
    jnz signal_console_fail_3
    xor ecx,ecx
    xor edx,edx
    call GenerateConsoleCtrlEvent
    test eax,eax
    jz signal_console_fail_4
    mov rcx,QWORD PTR signal_console_event
    mov edx,250
    call WaitForSingleObject
    cmp eax,258
    jne signal_console_fail_5
    mov rcx,QWORD PTR signal_console_control
    mov edx,2
    mov r8d,2
    call boom_signal_control_register
    cmp rax,1
    jne signal_console_fail_3
    mov ebx,2
signal_console_c_loop:
    xor ecx,ecx
    xor edx,edx
    call GenerateConsoleCtrlEvent
    test eax,eax
    jz signal_console_fail_4
    mov rcx,QWORD PTR signal_console_event
    mov edx,10000
    call WaitForSingleObject
    test eax,eax
    jnz signal_console_fail_5
    dec ebx
    jnz signal_console_c_loop
    mov ecx,1
    xor edx,edx
    call GenerateConsoleCtrlEvent
    test eax,eax
    jz signal_console_fail_4
    mov rcx,QWORD PTR signal_console_event
    mov edx,10000
    call WaitForSingleObject
    test eax,eax
    jnz signal_console_fail_5
    mov rcx,QWORD PTR signal_console_control
    call boom_signal_control_close
    test eax,eax
    jnz signal_console_fail_6
    cmp QWORD PTR signal_console_ints,2
    jne signal_console_fail_7
    cmp QWORD PTR signal_console_breaks,1
    jne signal_console_fail_7
    cmp DWORD PTR signal_console_error,0
    jne signal_console_fail_7
    mov rcx,QWORD PTR signal_console_event
    call CloseHandle
    xor ecx,ecx
    jmp signal_console_exit
signal_console_fail_1:
    mov ecx,71
    jmp signal_console_exit
signal_console_fail_2:
    mov ecx,72
    jmp signal_console_exit
signal_console_fail_3:
    mov ecx,73
    jmp signal_console_exit
signal_console_fail_4:
    mov ecx,74
    jmp signal_console_exit
signal_console_fail_5:
    mov ecx,75
    jmp signal_console_exit
signal_console_fail_6:
    mov ecx,76
    jmp signal_console_exit
signal_console_fail_7:
    mov ecx,77
signal_console_exit:
    call ExitProcess
    int 3
signal_console_main ENDP
signal_console_dispatch PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    cmp edx,2
    je signal_console_callback_int
    cmp edx,21
    jne signal_console_callback_bad
    lock inc QWORD PTR signal_console_breaks
    jmp signal_console_callback_check
signal_console_callback_int:
    lock inc QWORD PTR signal_console_ints
signal_console_callback_check:
    stmxcsr DWORD PTR [rsp+32]
    cmp DWORD PTR [rsp+32],01F80h
    jne signal_console_callback_bad
    call GetCurrentThreadId
    cmp eax,DWORD PTR signal_console_thread
    jne signal_console_callback_signal
signal_console_callback_bad:
    mov DWORD PTR signal_console_error,1
signal_console_callback_signal:
    mov rcx,QWORD PTR signal_console_event
    call SetEvent
    xor eax,eax
    add rsp,40
    ret
signal_console_dispatch ENDP
signal_console_break PROC
    cmp edx,21
    je signal_console_break_ok
    mov DWORD PTR signal_console_error,1
signal_console_break_ok:
    jmp signal_console_dispatch
signal_console_break ENDP
signal_default_2 PROC
    mov edx,2
    jmp signal_default_common
signal_default_2 ENDP
signal_default_4 PROC
    mov edx,4
    jmp signal_default_common
signal_default_4 ENDP
signal_default_6 PROC
    mov edx,6
    jmp signal_default_common
signal_default_6 ENDP
signal_default_8 PROC
    mov edx,8
    jmp signal_default_common
signal_default_8 ENDP
signal_default_11 PROC
    mov edx,11
    jmp signal_default_common
signal_default_11 ENDP
signal_default_15 PROC
    mov edx,15
    jmp signal_default_common
signal_default_15 ENDP
signal_default_22 PROC
    mov edx,22
    jmp signal_default_common
signal_default_22 ENDP
signal_default_common PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,32
    .allocstack 32
    .endprolog
    mov ebx,edx
    lea rcx,signal_console_config
    call boom_signal_control_create
    test rax,rax
    jz signal_default_failed
    mov rcx,rax
    mov edx,ebx
    call boom_signal_control_raise
signal_default_failed:
    mov ecx,79
    call ExitProcess
    int 3
signal_default_common ENDP
END
