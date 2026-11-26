; Test callbacks/adapters only. Not a Java Signal implementation.
option casemap:none
EXTERN boom_signal_control_register:PROC
EXTERN boom_signal_control_raise:PROC
EXTERN boom_signal_control_close:PROC
EXTERN GetCurrentThreadId:PROC
EXTERN SetEvent:PROC
EXTERN WaitForSingleObject:PROC
PUBLIC boom_signal_test_dispatch
PUBLIC boom_signal_test_break
PUBLIC boom_signal_test_native
PUBLIC boom_signal_test_bind
PUBLIC boom_signal_test_register_job
PUBLIC boom_signal_test_raise_job
PUBLIC boom_signal_test_enter
PUBLIC boom_signal_test_exit
PUBLIC boom_signal_test_lifecycle_dispatch
.data
signal_test_user QWORD 0
.code
boom_signal_test_bind PROC
    mov QWORD PTR signal_test_user,rcx
    ret
boom_signal_test_bind ENDP
; Lifecycle-only User320 extends the legacy User256: enterCount256,
; exitCount264, enterTid272, exitTid276, enterError280, exitError284,
; gateEntered288, gateRelease296, active304. No legacy callback reads these.
signal_test_lifecycle_gate PROC PRIVATE FRAME
    push rbx
    .pushreg rbx
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,rcx
    mov rcx,QWORD PTR [rbx+288]
    test rcx,rcx
    jz signal_test_lifecycle_gate_ok
    call SetEvent
    mov rcx,QWORD PTR [rbx+296]
    mov edx,20000
    call WaitForSingleObject
    test eax,eax
    jz signal_test_lifecycle_gate_ok
    mov eax,87
    jmp signal_test_lifecycle_gate_done
signal_test_lifecycle_gate_ok:
    xor eax,eax
signal_test_lifecycle_gate_done:
    add rsp,32
    pop rbx
    ret
signal_test_lifecycle_gate ENDP
boom_signal_test_enter PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    lock inc QWORD PTR [rbx+256]
    call GetCurrentThreadId
    mov DWORD PTR [rbx+272],eax
    stmxcsr DWORD PTR [rsp+32]
    cmp DWORD PTR [rsp+32],01F80h
    je signal_test_enter_fp_ok
    lock inc QWORD PTR [rbx+192]
signal_test_enter_fp_ok:
    mov rcx,rbx
    call signal_test_lifecycle_gate
    test eax,eax
    jnz signal_test_enter_done
    mov eax,DWORD PTR [rbx+280]
    test eax,eax
    jnz signal_test_enter_done
    mov QWORD PTR [rbx+304],1
signal_test_enter_done:
    add rsp,48
    pop rbx
    ret
boom_signal_test_enter ENDP
boom_signal_test_exit PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,48
    .allocstack 48
    .endprolog
    mov rbx,rcx
    lock inc QWORD PTR [rbx+264]
    call GetCurrentThreadId
    mov DWORD PTR [rbx+276],eax
    stmxcsr DWORD PTR [rsp+32]
    cmp DWORD PTR [rsp+32],01F80h
    je signal_test_exit_fp_ok
    lock inc QWORD PTR [rbx+192]
signal_test_exit_fp_ok:
    mov rcx,rbx
    call signal_test_lifecycle_gate
    test eax,eax
    jnz signal_test_exit_done
    cmp QWORD PTR [rbx+304],1
    jne signal_test_exit_bad
    mov QWORD PTR [rbx+304],0
    mov eax,DWORD PTR [rbx+284]
    jmp signal_test_exit_done
signal_test_exit_bad:
    mov eax,87
signal_test_exit_done:
    add rsp,48
    pop rbx
    ret
boom_signal_test_exit ENDP
boom_signal_test_lifecycle_dispatch PROC
    cmp QWORD PTR [rcx+304],1
    jne signal_test_lifecycle_dispatch_bad
    jmp boom_signal_test_dispatch
signal_test_lifecycle_dispatch_bad:
    mov eax,87
    ret
boom_signal_test_lifecycle_dispatch ENDP
; User256: counters[23]@0, break_count184, bad_fp192, failure_signal200,
; last_tid204, entered208, release216, native_count224, control232,
; reenter_mode240, nested_close_error244, callback_close_error248.
boom_signal_test_dispatch PROC FRAME
    push rbx
    .pushreg rbx
    push rsi
    .pushreg rsi
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rbx,rcx
    mov esi,edx
    cmp esi,23
    jae signal_test_bad
    stmxcsr DWORD PTR [rsp+32]
    cmp DWORD PTR [rsp+32],01F80h
    je signal_test_fp_ok
    lock inc QWORD PTR [rbx+192]
signal_test_fp_ok:
    lock inc QWORD PTR [rbx+rsi*8]
    call GetCurrentThreadId
    mov DWORD PTR [rbx+204],eax
    cmp DWORD PTR [rbx+240],3
    jne signal_test_gate
    mov rcx,QWORD PTR [rbx+232]
    call boom_signal_control_close
    mov DWORD PTR [rbx+248],eax
signal_test_gate:
    mov rcx,QWORD PTR [rbx+208]
    test rcx,rcx
    jz signal_test_result
    call SetEvent
    mov rcx,QWORD PTR [rbx+216]
    mov edx,20000
    call WaitForSingleObject
    test eax,eax
    jnz signal_test_bad
signal_test_result:
    xor eax,eax
    cmp esi,DWORD PTR [rbx+200]
    jne signal_test_done
    mov eax,12345
    jmp signal_test_done
signal_test_bad:
    mov eax,87
signal_test_done:
    add rsp,40
    pop rsi
    pop rbx
    ret
boom_signal_test_dispatch ENDP
boom_signal_test_break PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    lock inc QWORD PTR [rcx+184]
    call boom_signal_test_dispatch
    add rsp,40
    ret
boom_signal_test_break ENDP
boom_signal_test_native PROC FRAME
    push rbx
    .pushreg rbx
    sub rsp,32
    .allocstack 32
    .endprolog
    mov rbx,QWORD PTR signal_test_user
    lock inc QWORD PTR [rbx+224]
    cmp DWORD PTR [rbx+240],1
    jne signal_test_native_close
    mov edx,ecx
    mov rcx,QWORD PTR [rbx+232]
    mov r8d,2
    call boom_signal_control_register
    jmp signal_test_native_done
signal_test_native_close:
    cmp DWORD PTR [rbx+240],4
    jne signal_test_native_check_close
    mov rcx,QWORD PTR [rbx+208]
    call SetEvent
    mov rcx,QWORD PTR [rbx+216]
    mov edx,20000
    call WaitForSingleObject
    jmp signal_test_native_done
signal_test_native_check_close:
    cmp DWORD PTR [rbx+240],2
    jne signal_test_native_done
    mov rcx,QWORD PTR [rbx+232]
    call boom_signal_control_close
    mov DWORD PTR [rbx+244],eax
signal_test_native_done:
    add rsp,32
    pop rbx
    ret
boom_signal_test_native ENDP
; Numeric pool jobs: input {control,signal,value}; result = raw service return.
boom_signal_test_register_job PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rcx,QWORD PTR [rdx]
    mov r8,QWORD PTR [rdx+16]
    mov edx,DWORD PTR [rdx+8]
    call boom_signal_control_register
    add rsp,40
    ret
boom_signal_test_register_job ENDP
boom_signal_test_raise_job PROC FRAME
    sub rsp,40
    .allocstack 40
    .endprolog
    mov rcx,QWORD PTR [rdx]
    mov edx,DWORD PTR [rdx+8]
    call boom_signal_control_raise
    add rsp,40
    ret
boom_signal_test_raise_job ENDP
END
