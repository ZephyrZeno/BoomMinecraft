; WNFS64/1. The static JNI field ID is an immutable source Field record with
; the declared File layout, path offset, field index, class ID and width.
.code
PUBLIC boom_provider_winnt_file_service
boom_provider_winnt_file_service PROC FRAME
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
 mov rsi,r8
 test rbx,rbx
 jz wf_done
 cmp DWORD PTR [rbx],0
 jne wf_done
 test r9d,r9d
 jnz wf_bad
 test rsi,rsi
 jz wf_bad
 cmp DWORD PTR [rsi],053464E57h
 jne wf_bad
 cmp DWORD PTR [rsi+4],1
 jne wf_bad
 cmp DWORD PTR [rsi+8],2
 je wf_done
 cmp DWORD PTR [rsi+12],0
 jne wf_bad
 mov rcx,QWORD PTR [rsi+16]
 mov rdi,QWORD PTR [rsi+24]
 test rcx,rcx
 jz wf_bad
 test rdi,rdi
 jz wf_bad
 cmp DWORD PTR [rcx],0434C4153h
 jne wf_bad
 cmp DWORD PTR [rcx+4],2
 jne wf_bad
 mov eax,DWORD PTR [rcx+24]
 cmp eax,DWORD PTR [rdi+16]
 jne wf_bad
 mov rdx,QWORD PTR [rdi]
 test rdx,rdx
 jz wf_bad
 cmp DWORD PTR [rdx],04F424A43h
 jne wf_bad
 cmp DWORD PTR [rdx+4],2
 jne wf_bad
 cmp DWORD PTR [rdi+20],8
 jne wf_bad
 mov eax,DWORD PTR [rdi+8]
 test al,7
 jnz wf_bad
 lea r8,[rax+8]
 cmp r8,QWORD PTR [rdx+8]
 ja wf_bad
 shr eax,3
 cmp eax,DWORD PTR [rdx+16]
 jae wf_bad
 ; GetFieldID initializes File. A recursive request on the initializing OS
 ; thread must take the ordinary class-initialization path as well.
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne wf_done
 mov QWORD PTR [rsp+32],0
 mov ecx,6
 mov rdx,QWORD PTR [__imp_CreateFileW]
 lea r8,[rsp+32]
 call GetModuleHandleExW
 test eax,eax
 jz wf_no_optional
 mov rcx,QWORD PTR [rsp+32]
 lea rdx,rpr_final_path_name
 call GetProcAddress
 mov rdx,rax
 jmp wf_publish
wf_no_optional:
 xor edx,edx
wf_publish:
 xor eax,eax
 mov ecx,1
 lock cmpxchg DWORD PTR [rsi+8],ecx
 jne wf_observe
 mov QWORD PTR [rsi+32],rdi
 mov QWORD PTR [rsi+40],rdx
 mov DWORD PTR [rsi+8],2
 jmp wf_done
wf_observe:
 cmp eax,2
 je wf_done
 cmp eax,1
 jne wf_bad
 pause
 mov eax,DWORD PTR [rsi+8]
 jmp wf_observe
wf_bad:
 mov DWORD PTR [rbx],7
wf_done:
 xor eax,eax
 add rsp,48
 pop rdi
 pop rsi
 pop rbx
 ret
boom_provider_winnt_file_service ENDP
