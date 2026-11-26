; Original WindowsNativeDispatcher failures construct the source
; WindowsException(int) and publish that typed Throwable in Context32.
; The generator binds the NIO_* names to locked source symbols.
nio_raise_windows_error PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov esi,edx
 lea rcx,NIO_EXCEPTION_CLASS
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne nre_done
 mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,NIO_EXCEPTION_LAYOUT
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz nre_done
 mov rdi,rax
 mov QWORD PTR [rsp+32],rdi
 mov QWORD PTR [rsp+40],rsi
 mov rcx,rbx
 lea rdx,[rsp+32]
 call NIO_EXCEPTION_CTOR
 cmp DWORD PTR [rbx],0
 jne nre_done
 mov rcx,rbx
 mov rdx,rdi
 lea r8,boom_runtime_type_map
 lea r9,NIO_THROWABLE_TYPE
 call boom_exception_set32
nre_done:
 add rsp,48
 pop rdi
 pop rsi
 pop rbx
 ret
nio_raise_windows_error ENDP
