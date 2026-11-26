; Generated large Java frames use this special prologue ABI, like __chkstk.
; RAX = allocation bytes, preserved; only R10/R11/flags are clobbered.
; Touch every intervening page before the caller changes RSP. No host callbacks,
; argument register damage, stack allocation or fabricated Java frame.
option casemap:none
PUBLIC boom_stack_probe
.code
boom_stack_probe PROC
 lea r11,[rsp+8]
 mov r10,rax
stack_probe_page:
 cmp r10,4096
 jbe stack_probe_last
 sub r11,4096
 test BYTE PTR [r11],0
 sub r10,4096
 jmp stack_probe_page
stack_probe_last:
 sub r11,r10
 test BYTE PTR [r11],0
 ret
boom_stack_probe ENDP
END
