; Original Object.notify/notifyAll share the registered per-heap Java wait set.
.code
PUBLIC boom_provider_object_notification_service
boom_provider_object_notification_service PROC
 test rcx,rcx
 jz object_notification_zero
 cmp DWORD PTR [rcx],0
 jne object_notification_zero
 cmp r9d,1
 ja object_notification_bad
 test rdx,rdx
 jz object_notification_bad
 test r8,r8
 jz object_notification_bad
 cmp DWORD PTR [r8],059464E4Fh
 jne object_notification_bad
 cmp DWORD PTR [r8+4],1
 jne object_notification_bad
 cmp QWORD PTR [r8+8],0
 je object_notification_bad
 cmp QWORD PTR [r8+16],0
 jne object_notification_bad
 cmp QWORD PTR [r8+24],0
 jne object_notification_bad
 mov r10,rcx
 mov r11d,r9d
 mov rcx,QWORD PTR [r8+8]
 mov rcx,QWORD PTR [rcx]
 mov rdx,QWORD PTR [rdx]
 mov r8,r10
 test r11d,r11d
 jz object_notification_one
 jmp boom_monitor_notify_all
object_notification_one:
 jmp boom_monitor_notify
object_notification_bad:
 mov DWORD PTR [rcx],7
object_notification_zero:
 xor eax,eax
 ret
boom_provider_object_notification_service ENDP
