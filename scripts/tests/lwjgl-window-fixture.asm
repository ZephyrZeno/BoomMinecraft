; Headless Win64 ABI probe. This DLL has no entry point and imports no libraries.
option casemap:none
PUBLIC glfwCreateWindow
PUBLIC differentFunction
PUBLIC observedCalls
PUBLIC alignmentFailures
PUBLIC unexpectedCalls
.data
ALIGN 8
observedCalls QWORD 0
alignmentFailures QWORD 0
unexpectedCalls QWORD 0
.code
glfwCreateWindow PROC
    mov rax,rsp
    and eax,15
    cmp eax,8
    jne misaligned
    ; The caller owns all four shadow slots. Save and read back the arguments.
    mov [rsp+8],rcx
    mov [rsp+16],rdx
    mov [rsp+24],r8
    mov [rsp+32],r9
    lock inc QWORD PTR observedCalls
    mov eax,DWORD PTR [rsp+8]
    rol rax,11
    mov edx,DWORD PTR [rsp+16]
    xor rax,rdx
    ror rax,7
    xor rax,[rsp+24]
    rol rax,17
    xor rax,[rsp+32]
    rol rax,23
    xor rax,[rsp+40]
    ret
misaligned:
    lock inc QWORD PTR alignmentFailures
    xor eax,eax
    ret
glfwCreateWindow ENDP
differentFunction PROC
    lock inc QWORD PTR unexpectedCalls
    xor eax,eax
    ret
differentFunction ENDP
END
