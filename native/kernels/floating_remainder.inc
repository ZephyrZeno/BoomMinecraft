; Exact binary long division for Java frem/drem. Inputs and result are raw bits.
; Uses only volatile integer registers; does not touch MXCSR or x87 state.
; All NaN results use a positive canonical quiet NaN. No C runtime dependency.
option casemap:none
.code

BOOM_FREM_BODY MACRO fraction, infinity, fraction_mask, quiet_nan, sign_bit
LOCAL invalid_result, return_x, return_zero, x_subnormal, x_ready
LOCAL y_subnormal, y_ready, reduce_loop, shift_remainder, last_subtract
LOCAL normalize_result, subnormal_result, return_result
    mov rdx, r8
    shr rdx, sign_bit
    shl rdx, sign_bit
    btr r8, sign_bit
    btr r9, sign_bit
    mov rax, infinity
    cmp r8, rax
    jae invalid_result
    cmp r9, rax
    ja invalid_result
    je return_x
    test r9, r9
    jz invalid_result
    cmp r8, r9
    jb return_x
    je return_zero

    mov r10, r8
    shr r10, fraction
    test r10d, r10d
    jz x_subnormal
    mov rax, fraction_mask
    and r8, rax
    bts r8, fraction
    jmp x_ready
x_subnormal:
    bsr rax, r8
    mov ecx, fraction
    sub ecx, eax
    mov r10d, 1
    sub r10d, ecx
    shl r8, cl
x_ready:
    mov r11, r9
    shr r11, fraction
    test r11d, r11d
    jz y_subnormal
    mov rax, fraction_mask
    and r9, rax
    bts r9, fraction
    jmp y_ready
y_subnormal:
    bsr rax, r9
    mov ecx, fraction
    sub ecx, eax
    mov r11d, 1
    sub r11d, ecx
    shl r9, cl
y_ready:
    cmp r10d, r11d
    jle last_subtract
reduce_loop:
    cmp r8, r9
    jb shift_remainder
    sub r8, r9
    jz return_zero
shift_remainder:
    shl r8, 1
    dec r10d
    cmp r10d, r11d
    jg reduce_loop
last_subtract:
    cmp r8, r9
    jb normalize_result
    sub r8, r9
    jz return_zero
normalize_result:
    bsr rax, r8
    mov ecx, fraction
    sub ecx, eax
    shl r8, cl
    sub r10d, ecx
    test r10d, r10d
    jle subnormal_result
    btr r8, fraction
    mov eax, r10d
    shl rax, fraction
    or rax, r8
    jmp return_result
subnormal_result:
    mov ecx, 1
    sub ecx, r10d
    shr r8, cl
return_x:
    mov rax, r8
return_result:
    or rax, rdx
    ret
return_zero:
    mov rax, rdx
    ret
invalid_result:
    mov rax, quiet_nan
    ret
ENDM

boom_frem64 PROC
    mov r8, rcx
    mov r9, rdx
    BOOM_FREM_BODY 52, 07FF0000000000000h, 000FFFFFFFFFFFFFh, 07FF8000000000000h, 63
boom_frem64 ENDP

boom_frem32 PROC
    mov r8d, ecx
    mov r9d, edx
    BOOM_FREM_BODY 23, 07F800000h, 0007FFFFFh, 07FC00000h, 31
boom_frem32 ENDP
