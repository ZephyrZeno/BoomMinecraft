; Normal stream/descriptor field registration and Windows standard handles.
; NFIO48/1: magic0 ABI4 inputPool8 outputPool16 descriptorPool24 res32/40=0.
; ops: 0 input.initIDs,1 output.initIDs,2 fd.initIDs,3 fd.getHandle,4 fd.getAppend,
; 5 StringUTF16.isBigEndian (observed native DWORD byte order).
; Source-bound registration tables are published atomically by the existing ASM
; stream/descriptor kernels. File reads, writes, opens and closes are separate.
EXTERN boom_stream_fields_init:PROC
EXTERN boom_fd_service:PROC
PUBLIC boom_provider_file_bootstrap_service
.code
boom_provider_file_bootstrap_service PROC
 test rcx,rcx
 jz file_bootstrap_zero
 cmp DWORD PTR [rcx],0
 jne file_bootstrap_zero
 test r8,r8
 jz file_bootstrap_bad
 cmp DWORD PTR [r8],04F49464Eh
 jne file_bootstrap_bad
 cmp DWORD PTR [r8+4],1
 jne file_bootstrap_bad
 cmp QWORD PTR [r8+32],0
 jne file_bootstrap_bad
 cmp QWORD PTR [r8+40],0
 jne file_bootstrap_bad
 cmp r9d,5
 ja file_bootstrap_bad
 je file_bootstrap_byte_order
 cmp r9d,1
 ja file_bootstrap_descriptor
 mov eax,r9d
 mov rdx,QWORD PTR [r8+rax*8+8]
 jmp boom_stream_fields_init
file_bootstrap_descriptor:
 sub r9d,2
 mov r8,QWORD PTR [r8+24]
 jmp boom_fd_service
file_bootstrap_byte_order:
 ; Windows x64 callers reserve 32 bytes of shadow space above our return PC.
 mov DWORD PTR [rsp+8],01020304h
 xor eax,eax
 cmp BYTE PTR [rsp+8],1
 sete al
 ret
file_bootstrap_bad:
 mov DWORD PTR [rcx],7
file_bootstrap_zero:
 xor eax,eax
 ret
boom_provider_file_bootstrap_service ENDP
