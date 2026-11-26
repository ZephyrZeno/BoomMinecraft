; Native process owner for the source VM bootstrap prefix. No CLR/JVM/CRT.
; The compiler emits the binding pool and boom_vm_bootstrap_main separately.
; Report112/2: magic0,ABI4,flags8,Context16@12,diagState28,row32,reserved36,
; held64@40,monitorLock48,bootState52,live64@56,cleanup64,nativeStatus68,
; entryComplete72,phase1Called76,exitCode80,childConstructorComplete84,
; childId64@88,nextId64@96,mainId64@104. IDs are observations, never writes.
; Report144/3 adds sourceStart112,reaped116,runCompleted64@120,
; exitCompleted64@128,workerFailureState136,reserved140.
; Report208/4 keeps that prefix and adds signalOpened144,closed148,
; attached64@152,dispatchEntered64@160,exitCompleted64@168,detached64@176,
; failureState184,reserved188,dispatcherJavaId64@192,nativeError200,reserved204.
EXTERN boom_heap_create:PROC
EXTERN boom_heap_destroy:PROC
EXTERN boom_java_string_literals_bind_heap:PROC
EXTERN boom_threads_detach:PROC
EXTERN boom_threads_destroy:PROC
EXTERN boom_provider_thread_bind:PROC
EXTERN boom_release_trace_pool:PROC
EXTERN boom_provider_thread_registry:QWORD
EXTERN boom_diagnostic_pool:BYTE
EXTERN boom_provider_threads_pool:BYTE
EXTERN boom_provider_threads_close:PROC
EXTERN boom_provider_thread_priority_pool:BYTE
EXTERN boom_provider_signal_pool:BYTE
EXTERN boom_provider_signal_close:PROC
EXTERN CreateFileW:PROC
EXTERN WriteFile:PROC
EXTERN CloseHandle:PROC
EXTERN ExitProcess:PROC
.data?
ALIGN 8
PUBLIC boom_vm_entry_context
boom_vm_entry_context QWORD 4 DUP(?)
PUBLIC boom_vm_entry_report
boom_vm_entry_report BYTE VM_ENTRY_REPORT_BYTES DUP(?)
boom_vm_entry_written DWORD ?
IFDEF VM_ENTRY_NATIVE_ROOTS
ALIGN 8
; Native scratch vector, never an oop root bank. No collection is triggered.
vpe_native_root_vector QWORD 1048576 DUP(?)
ENDIF
.const
boom_vm_entry_report_name WORD 118,109,45,101,110,116,114,121,45,115,116,97,116,117,115,46,98,105,110,0
.code
PUBLIC boom_process_entry
boom_process_entry PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,80
 .allocstack 80
 .endprolog
 xor ebx,ebx
 mov DWORD PTR [rsp+72],0
 mov DWORD PTR [boom_vm_entry_report],052454D56h
 mov DWORD PTR [boom_vm_entry_report+4],VM_ENTRY_REPORT_ABI
 mov DWORD PTR [boom_vm_entry_report+80],70
IFDEF VM_ENTRY_NATIVE_ROOTS
 mov DWORD PTR [boom_vm_entry_report+460],0FFFFFFFFh
ENDIF
 mov ecx,134217728
 call boom_heap_create
 test rax,rax
 jz vpe_capture
 mov rbx,rax
 or DWORD PTR [boom_vm_entry_report+8],1
 mov rcx,rax
 call boom_java_string_literals_bind_heap
 cmp eax,1
 jne vpe_capture
 or DWORD PTR [boom_vm_entry_report+8],2
IFDEF VM_ENTRY_REFERENCE_PROCESSING
 lea rcx,boom_provider_reference_pool
 call boom_provider_reference_open
 test eax,eax
 jz vpe_reference_opened
 mov DWORD PTR [boom_vm_entry_report+376],eax
 mov DWORD PTR [rsp+72],eax
 jmp vpe_capture
vpe_reference_opened:
 lea rax,boom_provider_reference_pool
 mov QWORD PTR [boom_provider_threads_control_binding+8],rax
 lea rax,boom_provider_reference_boundary
 mov QWORD PTR [boom_provider_threads_control_binding],rax
 mov DWORD PTR [boom_vm_entry_report+320],1
ENDIF
 lea rcx,boom_vm_entry_context
 xor edx,edx
 call boom_vm_bootstrap_main
 cmp DWORD PTR [boom_vm_entry_context],0
 jne vpe_capture
 cmp DWORD PTR [boom_vm_thread_bootstrap_pool+8],2
 jne vpe_capture
IFDEF VM_ENTRY_SYSTEM_PHASE2
 lea rcx,boom_vm_entry_context
 lea rdx,boom_vm_entry_report
 call boom_vm_call_system_phase2
 test eax,eax
 jz vpe_capture
ENDIF
IFDEF VM_ENTRY_SYSTEM_PHASE3
 lea rcx,boom_vm_entry_context
 lea rdx,boom_vm_entry_report
 call boom_vm_call_system_phase3
 test eax,eax
 jz vpe_capture
ENDIF
IFDEF VM_ENTRY_GAME_MAIN
 lea rcx,boom_vm_entry_context
 lea rdx,boom_vm_entry_report
 call boom_vm_call_game_main
 test eax,eax
 jz vpe_capture
ENDIF
 mov DWORD PTR [boom_vm_entry_report+72],1
 mov DWORD PTR [boom_vm_entry_report+80],0
vpe_capture:
IFDEF VM_ENTRY_SYSTEM_PHASE2
 ; Copy the main thread's own state before worker failures are joined.
 mov rax,QWORD PTR [boom_vm_entry_context]
 mov QWORD PTR [boom_vm_entry_report+296],rax
 mov rax,QWORD PTR [boom_vm_entry_context+8]
 mov QWORD PTR [boom_vm_entry_report+304],rax
ENDIF
IFDEF VM_ENTRY_MAIN_SOURCE_ROW
 cmp DWORD PTR [boom_vm_entry_context],0B001h
 jne vpe_main_row_done
 lea rcx,boom_vm_entry_context
 lea rdx,boom_diagnostic_context_map
 call boom_diagnostic_context_map_row
 mov DWORD PTR [boom_vm_entry_report+312],eax
vpe_main_row_done:
 mov eax,DWORD PTR [boom_diagnostic_context_map+28]
 mov DWORD PTR [boom_vm_entry_report+316],eax
ENDIF
IFDEF VM_ENTRY_REFERENCE_PROCESSING
 cmp DWORD PTR [boom_vm_entry_report+320],1
 jne vpe_reference_stop_done
 lea rcx,boom_vm_entry_context
 lea rdx,boom_provider_reference_pool
 call boom_provider_reference_boundary
 lea rcx,boom_provider_reference_pool
 call boom_provider_reference_stop
 test eax,eax
 jz vpe_reference_stopped
 mov DWORD PTR [boom_vm_entry_report+376],eax
 mov DWORD PTR [rsp+72],eax
 jmp vpe_reference_stop_done
vpe_reference_stopped:
 mov DWORD PTR [boom_vm_entry_report+324],1
IFDEF VM_ENTRY_OBJECT_WAIT
 cmp DWORD PTR [boom_vm_entry_report+400],1
 jne vpe_reference_stop_done
 lea rcx,boom_provider_object_wait_pool
 call boom_provider_object_wait_stop
 test eax,eax
 jz vpe_wait_stopped
 mov DWORD PTR [boom_vm_entry_report+412],eax
 mov DWORD PTR [rsp+72],eax
 jmp vpe_reference_stop_done
vpe_wait_stopped:
 mov DWORD PTR [boom_vm_entry_report+404],1
ENDIF
vpe_reference_stop_done:
ENDIF
IF VM_ENTRY_SIGNAL_REQUESTED
 ; Close/join while the heap, source classes, frame pool and registry still
 ; exist. A worker source diagnostic must reach the report before capture.
 lea rcx,boom_vm_entry_context
 lea rdx,boom_provider_signal_pool
 call boom_provider_signal_close
 test eax,eax
 jz vpe_signal_close_success
 mov DWORD PTR [rsp+72],eax
 jmp vpe_signal_close_observed
vpe_signal_close_success:
 cmp DWORD PTR [boom_provider_signal_pool+8],4
 jne vpe_signal_close_observed
 mov DWORD PTR [boom_vm_signal_closed],1
vpe_signal_close_observed:
 mov eax,DWORD PTR [boom_vm_signal_opened]
 mov DWORD PTR [boom_vm_entry_report+144],eax
 mov eax,DWORD PTR [boom_vm_signal_closed]
 mov DWORD PTR [boom_vm_entry_report+148],eax
 mov rax,QWORD PTR [boom_provider_signal_pool+208]
 mov QWORD PTR [boom_vm_entry_report+152],rax
 mov rax,QWORD PTR [boom_provider_signal_pool+184]
 mov QWORD PTR [boom_vm_entry_report+160],rax
 mov rax,QWORD PTR [boom_provider_signal_pool+200]
 mov QWORD PTR [boom_vm_entry_report+168],rax
 mov rax,QWORD PTR [boom_provider_signal_pool+216]
 mov QWORD PTR [boom_vm_entry_report+176],rax
 mov eax,DWORD PTR [boom_provider_signal_pool+168]
 mov DWORD PTR [boom_vm_entry_report+184],eax
 mov rax,QWORD PTR [boom_provider_signal_pool+152]
 mov QWORD PTR [boom_vm_entry_report+192],rax
 mov eax,DWORD PTR [boom_provider_signal_pool+12]
 mov DWORD PTR [boom_vm_entry_report+200],eax
ENDIF
IF VM_ENTRY_START_REQUESTED OR VM_ENTRY_SIGNAL_REQUESTED
 ; A source worker can still be unwinding its first diagnostic. Reap outside
 ; the pool lock, and retain all VM memory if any worker cannot be joined.
 call GetTickCount64
 add rax,20000
 mov QWORD PTR [rsp+56],rax
vpe_threads_close_loop:
 lea rcx,boom_provider_threads_pool
 call boom_provider_threads_close
 test eax,eax
 jz vpe_threads_closed
 cmp eax,170
 jne vpe_threads_close_failed
 call GetTickCount64
 cmp rax,QWORD PTR [rsp+56]
 jae vpe_threads_close_timeout
 mov ecx,1
 call Sleep
 jmp vpe_threads_close_loop
vpe_threads_close_timeout:
 mov eax,170
vpe_threads_close_failed:
 mov DWORD PTR [rsp+72],eax
vpe_threads_closed:
 cmp DWORD PTR [boom_vm_entry_context],0
 jne vpe_worker_context_done
 cmp DWORD PTR [boom_provider_threads_pool+120],2
 jne vpe_worker_context_done
 mov r10,QWORD PTR [boom_provider_threads_pool+224]
 mov r11d,DWORD PTR [boom_vm_entry_context+12]
 mov rax,QWORD PTR [r10]
 mov QWORD PTR [boom_vm_entry_context],rax
 mov rax,QWORD PTR [r10+8]
 mov QWORD PTR [boom_vm_entry_context+8],rax
 mov rax,QWORD PTR [r10+16]
 mov QWORD PTR [boom_vm_entry_context+16],rax
 mov rax,QWORD PTR [r10+24]
 mov QWORD PTR [boom_vm_entry_context+24],rax
 mov DWORD PTR [boom_vm_entry_context+12],r11d
vpe_worker_context_done:
ENDIF
IFDEF VM_ENTRY_REFERENCE_PROCESSING
 cmp DWORD PTR [rsp+72],0
 jne vpe_reference_capture
 cmp DWORD PTR [boom_vm_entry_report+324],1
 jne vpe_reference_capture
IFDEF VM_ENTRY_UNSAFE_PARK
 ; This block is after the existing successful worker join/error guard.
 cmp DWORD PTR [boom_vm_entry_report+448],1
 jne vpe_after_park_close
 lea rcx,boom_provider_unsafe_park_pool
 call boom_provider_unsafe_park_close
 test eax,eax
 jz vpe_park_closed
 mov DWORD PTR [boom_vm_entry_report+456],eax
 mov DWORD PTR [rsp+72],eax
 jmp vpe_reference_capture
vpe_park_closed:
 mov DWORD PTR [boom_vm_entry_report+452],1
vpe_after_park_close:
ENDIF
IFDEF VM_ENTRY_OBJECT_WAIT
 cmp DWORD PTR [boom_vm_entry_report+404],1
 jne vpe_after_wait_close
 lea rcx,boom_provider_object_wait_pool
 call boom_provider_object_wait_close
 test eax,eax
 jz vpe_wait_closed
 mov DWORD PTR [boom_vm_entry_report+412],eax
 mov DWORD PTR [rsp+72],eax
 jmp vpe_reference_capture
vpe_wait_closed:
 mov DWORD PTR [boom_vm_entry_report+408],1
vpe_after_wait_close:
ENDIF
 lea rcx,boom_provider_reference_pool
 call boom_provider_reference_close
 test eax,eax
 jz vpe_reference_closed
 mov DWORD PTR [boom_vm_entry_report+376],eax
 mov DWORD PTR [rsp+72],eax
 jmp vpe_reference_capture
vpe_reference_closed:
 mov QWORD PTR [boom_provider_threads_control_binding],0
 mov QWORD PTR [boom_provider_threads_control_binding+8],0
 mov DWORD PTR [boom_vm_entry_report+328],1
vpe_reference_capture:
IFDEF VM_ENTRY_OBJECT_WAIT
 mov rax,QWORD PTR [boom_provider_object_wait_pool+96]
 mov QWORD PTR [boom_vm_entry_report+416],rax
 mov rax,QWORD PTR [boom_provider_object_wait_pool+104]
 mov QWORD PTR [boom_vm_entry_report+424],rax
 mov rax,QWORD PTR [boom_provider_object_wait_pool+112]
 mov QWORD PTR [boom_vm_entry_report+432],rax
 mov rax,QWORD PTR [boom_provider_object_wait_pool+120]
 mov QWORD PTR [boom_vm_entry_report+440],rax
ENDIF
 mov eax,DWORD PTR [boom_provider_reference_pool+72]
 mov DWORD PTR [boom_vm_entry_report+332],eax
 test eax,eax
 jz vpe_reference_counts
 mov DWORD PTR [rsp+72],eax
vpe_reference_counts:
 mov rax,QWORD PTR [boom_provider_reference_pool+32]
 mov QWORD PTR [boom_vm_entry_report+336],rax
 mov rax,QWORD PTR [boom_provider_reference_pool+40]
 mov QWORD PTR [boom_vm_entry_report+344],rax
 mov rax,QWORD PTR [boom_provider_reference_pool+48]
 mov QWORD PTR [boom_vm_entry_report+352],rax
 mov rax,QWORD PTR [boom_provider_reference_pool+56]
 mov QWORD PTR [boom_vm_entry_report+360],rax
 mov rax,QWORD PTR [boom_provider_reference_pool+64]
 mov QWORD PTR [boom_vm_entry_report+368],rax
 mov eax,DWORD PTR [boom_provider_reference_pool+8]
 mov DWORD PTR [boom_vm_entry_report+380],eax
ENDIF
IFDEF VM_ENTRY_WINNT_FILESYSTEM
 mov eax,DWORD PTR [boom_provider_winnt_file_pool+8]
 mov DWORD PTR [boom_vm_entry_report+384],eax
 mov rcx,QWORD PTR [boom_provider_winnt_file_pool+24]
 xor eax,eax
 cmp rcx,QWORD PTR [boom_provider_winnt_file_pool+32]
 sete al
 mov DWORD PTR [boom_vm_entry_report+388],eax
 xor eax,eax
 cmp QWORD PTR [boom_provider_winnt_file_pool+40],0
 setne al
 mov DWORD PTR [boom_vm_entry_report+392],eax
 mov eax,DWORD PTR [rcx+16]
 mov DWORD PTR [boom_vm_entry_report+396],eax
ENDIF
 mov rax,QWORD PTR [boom_vm_entry_context]
 mov QWORD PTR [boom_vm_entry_report+12],rax
 mov rax,QWORD PTR [boom_vm_entry_context+8]
 mov QWORD PTR [boom_vm_entry_report+20],rax
 mov eax,DWORD PTR [boom_diagnostic_pool+8]
 mov DWORD PTR [boom_vm_entry_report+28],eax
 mov eax,DWORD PTR [boom_diagnostic_pool+32]
 mov DWORD PTR [boom_vm_entry_report+32],eax
 mov eax,DWORD PTR [boom_vm_thread_bootstrap_pool+8]
 mov DWORD PTR [boom_vm_entry_report+52],eax
 mov eax,DWORD PTR [boom_vm_system_phase1_called]
 mov DWORD PTR [boom_vm_entry_report+76],eax
 mov eax,DWORD PTR [boom_vm_child_constructor_completed]
 mov DWORD PTR [boom_vm_entry_report+84],eax
 mov ecx,DWORD PTR [boom_vm_thread_bootstrap_pool+176]
 mov r10,QWORD PTR [boom_vm_thread_root_cells]
 test r10,r10
 jz vpe_capture_child
 mov rax,QWORD PTR [r10+rcx]
 mov QWORD PTR [boom_vm_entry_report+104],rax
vpe_capture_child:
IF VM_ENTRY_CHILD_REQUESTED
 mov r10,QWORD PTR [boom_vm_thread_root_cells+40]
 test r10,r10
 jz vpe_capture_counter
 mov rax,QWORD PTR [r10+rcx]
 mov QWORD PTR [boom_vm_entry_report+88],rax
ENDIF
vpe_capture_counter:
 mov r10,QWORD PTR [boom_provider_thread_registry]
 test r10,r10
 jz vpe_capture_exit
 mov rax,QWORD PTR [r10+32]
 mov QWORD PTR [boom_vm_entry_report+96],rax
vpe_capture_exit:
IF VM_ENTRY_START_REQUESTED
 mov eax,DWORD PTR [boom_vm_child_start_completed]
 mov DWORD PTR [boom_vm_entry_report+112],eax
 mov eax,DWORD PTR [boom_vm_child_reaped]
 mov DWORD PTR [boom_vm_entry_report+116],eax
ENDIF
IF VM_ENTRY_START_REQUESTED OR VM_ENTRY_SIGNAL_REQUESTED
 mov rax,QWORD PTR [boom_provider_threads_pool+184]
 mov QWORD PTR [boom_vm_entry_report+120],rax
 mov rax,QWORD PTR [boom_provider_threads_pool+208]
 mov QWORD PTR [boom_vm_entry_report+128],rax
 mov eax,DWORD PTR [boom_provider_threads_pool+120]
 mov DWORD PTR [boom_vm_entry_report+136],eax
 cmp eax,2
 jne vpe_no_worker_context
 mov r10,QWORD PTR [boom_provider_threads_pool+224]
 mov rax,QWORD PTR [r10]
 mov QWORD PTR [boom_vm_entry_report+240],rax
 mov rax,QWORD PTR [r10+8]
 mov QWORD PTR [boom_vm_entry_report+248],rax
 mov rax,QWORD PTR [r10+16]
 mov QWORD PTR [boom_vm_entry_report+256],rax
 mov rax,QWORD PTR [r10+24]
 mov QWORD PTR [boom_vm_entry_report+264],rax
vpe_no_worker_context:
 mov rax,QWORD PTR [boom_provider_thread_priority_pool+64]
 mov QWORD PTR [boom_vm_entry_report+208],rax
 mov rax,QWORD PTR [boom_provider_threads_pool+168]
 mov QWORD PTR [boom_vm_entry_report+216],rax
 mov rax,QWORD PTR [boom_provider_threads_pool+176]
 mov QWORD PTR [boom_vm_entry_report+224],rax
 mov rax,QWORD PTR [boom_provider_threads_pool+216]
 mov QWORD PTR [boom_vm_entry_report+232],rax
ENDIF
 cmp DWORD PTR [boom_vm_entry_context],0B001h
 jne vpe_heap_stats
 mov DWORD PTR [boom_vm_entry_report+80],86
vpe_heap_stats:
 test rbx,rbx
 jz vpe_report
 mov rax,QWORD PTR [rbx+56]
 mov QWORD PTR [boom_vm_entry_report+56],rax
 mov rax,QWORD PTR [rbx+112]
 mov QWORD PTR [boom_vm_entry_report+40],rax
 mov eax,DWORD PTR [rbx+104]
 mov DWORD PTR [boom_vm_entry_report+48],eax
IF VM_ENTRY_START_REQUESTED OR VM_ENTRY_SIGNAL_REQUESTED
 mov eax,DWORD PTR [rsp+72]
 test eax,eax
 jz vpe_all_workers_joined
 mov DWORD PTR [boom_vm_entry_report+68],eax
 cmp DWORD PTR [boom_vm_entry_report+80],86
 je vpe_report
 mov DWORD PTR [boom_vm_entry_report+80],70
 jmp vpe_report
vpe_all_workers_joined:
ENDIF
IFDEF VM_ENTRY_NATIVE_ROOTS
 ; Every worker has joined. Read complete source/native banks into ASM scratch.
 ; This records a bounded snapshot only; pending exceptions/active frames are
 ; not collected here and no game state is changed by this process owner.
 lea rcx,vpe_native_root_vector
 mov edx,1048576
 lea r8,[boom_vm_entry_report+504]
 call boom_provider_native_roots_full_snapshot
 mov DWORD PTR [boom_vm_entry_report+460],eax
 test eax,eax
 jnz vpe_native_owner_error
IFDEF VM_ENTRY_UNSAFE_PARK
 mov eax,DWORD PTR [boom_provider_unsafe_park_pool+12]
 mov DWORD PTR [boom_vm_entry_report+464],eax
 mov rax,QWORD PTR [boom_unsafe_park_counters+72]
 cmp rax,16384
 ja vpe_native_owner_busy
 mov DWORD PTR [boom_vm_entry_report+468],eax
 xor ecx,ecx
 xor edx,edx
 lea r8,boom_unsafe_park_gate_roots
vpe_park_roots_count:
 cmp QWORD PTR [r8+rcx*8],0
 je vpe_park_root_empty
 inc rdx
vpe_park_root_empty:
 inc ecx
 cmp ecx,16384
 jb vpe_park_roots_count
 mov QWORD PTR [boom_vm_entry_report+472],rdx
 or eax,DWORD PTR [boom_vm_entry_report+464]
 or rax,rdx
 jnz vpe_native_owner_busy
 mov ecx,DWORD PTR [boom_vm_entry_report+448]
 cmp ecx,1
 ja vpe_native_owner_busy
 cmp ecx,DWORD PTR [boom_vm_entry_report+452]
 jne vpe_native_owner_busy
ENDIF
IFDEF VM_ENTRY_FILE_INPUT
 mov rax,QWORD PTR [boom_file_input_live_handles]
 mov QWORD PTR [boom_vm_entry_report+480],rax
 mov rax,QWORD PTR [boom_file_input_owned_buffers]
 mov QWORD PTR [boom_vm_entry_report+488],rax
 xor ecx,ecx
 xor edx,edx
 lea r8,boom_file_input_owner_roots
vpe_io_roots_count:
 cmp QWORD PTR [r8+rcx*8],0
 je vpe_io_root_empty
 inc rdx
vpe_io_root_empty:
 inc ecx
 cmp ecx,4096
 jb vpe_io_roots_count
 mov QWORD PTR [boom_vm_entry_report+496],rdx
 or rax,QWORD PTR [boom_vm_entry_report+480]
 or rax,rdx
 jnz vpe_native_owner_busy
ENDIF
 jmp vpe_native_owners_clear
vpe_native_owner_busy:
 mov eax,170
vpe_native_owner_error:
 ; Keep all VM memory alive for process teardown if a native owner remains.
 mov DWORD PTR [boom_vm_entry_report+68],eax
 cmp DWORD PTR [boom_vm_entry_report+80],86
 je vpe_report
 mov DWORD PTR [boom_vm_entry_report+80],70
 jmp vpe_report
vpe_native_owners_clear:
ENDIF
 ; This is process teardown for an incomplete bootstrap, not Thread.exit.
 mov rcx,QWORD PTR [boom_provider_thread_registry]
 test rcx,rcx
 jz vpe_registry_clean
 mov QWORD PTR [rsp+64],rcx
 call boom_threads_detach
 test eax,eax
 jnz vpe_registry_error
 xor ecx,ecx
 call boom_provider_thread_bind
 test eax,eax
 jnz vpe_registry_error
 ; bind(NULL) cleared the source registry cell. Keep the borrowed pointer
 ; across the unbind in the local stack, not in the now-cleared cell.
 mov rcx,QWORD PTR [rsp+64]
 call boom_threads_destroy
 test eax,eax
 jnz vpe_registry_error
vpe_registry_clean:
 or DWORD PTR [boom_vm_entry_report+64],2
 jmp vpe_frames
vpe_registry_error:
 mov DWORD PTR [boom_vm_entry_report+68],eax
vpe_frames:
 call boom_release_trace_pool
 test eax,eax
 jnz vpe_frame_error
 or DWORD PTR [boom_vm_entry_report+64],4
 jmp vpe_heap_free
vpe_frame_error:
 mov DWORD PTR [boom_vm_entry_report+68],eax
vpe_heap_free:
 test DWORD PTR [boom_vm_entry_report+64],2
 jz vpe_report
 mov rcx,rbx
 call boom_heap_destroy
 cmp eax,1
 jne vpe_report
 or DWORD PTR [boom_vm_entry_report+64],1
vpe_report:
 ; CREATE_NEW prevents a repeated process run from replacing prior evidence.
 lea rcx,boom_vm_entry_report_name
 mov edx,040000000h
 mov r8d,1
 xor r9d,r9d
 mov DWORD PTR [rsp+32],1
 mov DWORD PTR [rsp+40],128
 mov QWORD PTR [rsp+48],0
 call CreateFileW
 cmp rax,-1
 je vpe_io_failed
 mov rbx,rax
 mov rcx,rax
 lea rdx,boom_vm_entry_report
 mov r8d,VM_ENTRY_REPORT_BYTES
 lea r9,boom_vm_entry_written
 mov QWORD PTR [rsp+32],0
 call WriteFile
 test eax,eax
 jz vpe_close_failed
 cmp DWORD PTR [boom_vm_entry_written],VM_ENTRY_REPORT_BYTES
 jne vpe_close_failed
 mov rcx,rbx
 call CloseHandle
 mov ecx,DWORD PTR [boom_vm_entry_report+80]
 call ExitProcess
 int 3
vpe_close_failed:
 mov rcx,rbx
 call CloseHandle
vpe_io_failed:
 mov ecx,74
 call ExitProcess
 int 3
boom_process_entry ENDP
