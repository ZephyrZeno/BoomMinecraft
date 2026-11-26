"""MASM for normal generated lambda ctor/factory/SAM methods, not a guest host."""


def module(manifest,sources):
    C=sources_module(sources);parts=['.data?\nALIGN 8\nPUBLIC boom_lambda_failure_roots\nboom_lambda_failure_roots LABEL QWORD\n']
    for generated in manifest['generated']:parts.append(body(generated,sources,C))
    parts.append(f'.const\nPUBLIC boom_lambda_failure_root_count\nboom_lambda_failure_root_count QWORD {len(manifest["generated"])}\n')
    return '\n'.join(parts)


def sources_module(sources):
    # The source module supplies only build-time descriptor/type operations.
    import sys
    return sys.modules[type(sources).__module__] if type(sources).__module__ in sys.modules else None


def body(g,sources,contract_module=None):
    plan=g['contract'];ident=g['type_id'];methods={m['name']:m for m in g['methods']}
    ctor=methods['<init>'];factory=methods['$capture'];sam=methods[plan['sam_name']]
    bootstrap=plan['bootstrap_member']['class_id'];impl=plan['implementation_member'];object_ctor=g['object_constructor']
    captures=g['layout']['fields'];argc=len(captures)
    text=f'''.const
ALIGN 8
PUBLIC boom_layout{ident}
boom_layout{ident} DWORD 04F424A43h,2
 QWORD {g['layout']['payload_bytes']}
 DWORD {g['layout']['reference_prefix']},{argc}
ALIGN 8
PUBLIC boom_t{ident}
boom_t{ident} DWORD 054595045h,1,1,0
 QWORD OFFSET boom_t{g['type']['parent_component']},OFFSET boom_ancestors{ident}
 DWORD {len(g['type']['ancestors'])},0
boom_ancestors{ident} LABEL QWORD
'''
    text+=''.join(f' QWORD OFFSET boom_t{n}\n' for n in g['type']['ancestors'])
    for field in captures:
        n=field['id'];text+=f'''ALIGN 8
PUBLIC boom_batch_field_record{n}
boom_batch_field_record{n} DWORD 0464D4150h,1,1,8,1,0
 QWORD OFFSET boom_batch_field_rows{n}
boom_batch_field_rows{n} DWORD {ident},{field['offset']}
.code
PUBLIC boom_field_map{n}
boom_field_map{n} PROC
 lea r8,boom_batch_field_record{n}
 lea r9,boom_runtime_type_map
 jmp boom_field_address
boom_field_map{n} ENDP
.const
'''
    text+=f'''.data?
ALIGN 8
PUBLIC boom_lambda_failure_root{ident}
boom_lambda_failure_root{ident} QWORD ?
.data
ALIGN 8
PUBLIC boom_class{ident}
boom_class{ident} DWORD 0434C4153h,2,0,0
 QWORD OFFSET boom_lambda_initialize{ident}
 DWORD {ident},0
 QWORD 0,0,0,OFFSET boom_lambda_failure_root{ident}
.code
boom_lambda_initialize{ident} PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 lea rcx,boom_class{g['type']['parent_component']}
 mov rdx,rbx
 call boom_class_ensure32
'''
    for ancestor in g['type']['ancestors']:
        record=sources.types[ancestor]
        if record['kind']!=2:continue
        declared=sources.raw(sources.classes[ancestor]).methods
        if not any(m['name'] not in ('<clinit>','<init>') and not m['access']&(8|2|0x400) for m in declared):continue
        text+=f''' cmp DWORD PTR [rbx],0
 jne boom_lambda_initialize{ident}_done
 lea rcx,boom_class{ancestor}
 mov rdx,rbx
 call boom_class_ensure32
'''
    text+=f'''boom_lambda_initialize{ident}_done:
 mov eax,DWORD PTR [rbx]
 add rsp,32
 pop rbx
 ret
boom_lambda_initialize{ident} ENDP
PUBLIC {plan['binding_label']}
{plan['binding_label']} PROC
 jmp boom_m{factory['id']}
{plan['binding_label']} ENDP
'''
    def prologue(method):
        n=method['id']
        return f'''.code
PUBLIC boom_m{n}
boom_m{n} PROC
 jmp boom_m{n}_body
boom_m{n} ENDP
PUBLIC boom_m{n}_body
boom_m{n}_body PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,352
 .allocstack 352
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov QWORD PTR [rsp+256],0
 mov QWORD PTR [rsp+320],0
 test rbx,rbx
 jz lambda_m{n}_exit
 cmp DWORD PTR [rbx],0
 jne lambda_m{n}_exit
 cmp DWORD PTR [rbx+12],128
 jae lambda_m{n}_stack_limit
 inc DWORD PTR [rbx+12]
 lea rcx,boom_trace_pool
 lea rdx,[rsp+256]
 lea r8,boom_trace_method{n}
 mov r9,rbx
 call boom_trace_enter
 test eax,eax
 jnz lambda_m{n}_throw
'''
    def set_pc(method,pc):
        return f' mov DWORD PTR [rsp+280],{pc}\n mov DWORD PTR [rbx+4],{pc}\n mov DWORD PTR [rbx+8],{method["id"]}\n'
    def epilogue(method):
        n=method['id']
        return f''' jmp lambda_m{n}_done
lambda_m{n}_bad:
 mov DWORD PTR [rbx],7
 jmp lambda_m{n}_throw
lambda_m{n}_null:
 mov DWORD PTR [rbx],4
lambda_m{n}_throw:
 mov QWORD PTR [rsp+320],0
lambda_m{n}_done:
 lea rcx,boom_trace_pool
 lea rdx,[rsp+256]
 mov r8,rbx
 call boom_trace_leave
 dec DWORD PTR [rbx+12]
 jmp lambda_m{n}_exit
lambda_m{n}_stack_limit:
 mov DWORD PTR [rbx],10
 mov DWORD PTR [rbx+4],0
 mov DWORD PTR [rbx+8],{n}
lambda_m{n}_exit:
 mov rax,QWORD PTR [rsp+320]
 add rsp,352
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
boom_m{n}_body ENDP
'''
    def checked_receiver(method):
        n=method['id']
        return f''' test r12,r12
 jz lambda_m{n}_bad
 mov r14,QWORD PTR [r12]
 test r14,r14
 jz lambda_m{n}_null
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,r14
 call boom_heap_contains
 test eax,eax
 jz lambda_m{n}_bad
 mov rcx,r14
 lea rdx,boom_layout{ident}
 mov r8,rbx
 call boom_object_check
 test rax,rax
 jz lambda_m{n}_throw
'''
    casts=[0]
    def ref_cast(method,operand,target,pc):
        target_id=sources.ty(plan['host']['origin']['loader'],target)['id']
        casts[0]+=1;label=f'lambda_cast_{method["id"]}_{casts[0]}'
        return set_pc(method,pc)+f''' mov rax,{operand}
 mov QWORD PTR [rsp+328],rax
 test rax,rax
 jz {label}_owned
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,rax
 call boom_heap_contains
 test eax,eax
 jz lambda_m{method['id']}_bad
{label}_owned:
 mov rcx,QWORD PTR [rsp+328]
 lea rdx,boom_runtime_type_map
 lea r8,boom_t{target_id}
 mov r9,rbx
 call boom_runtime_cast
 cmp DWORD PTR [rbx],0
 jne lambda_m{method['id']}_throw
'''
    # Constructor executes the original Object constructor then initializes
    # reference fields. The actual generated classfile remains the source map.
    text+=prologue(ctor)+checked_receiver(ctor)+set_pc(ctor,1)+f''' mov QWORD PTR [rsp+64],r14
 mov rcx,rbx
 lea rdx,[rsp+64]
 call boom_m{object_ctor['method']}
 cmp DWORD PTR [rbx],0
 jne lambda_m{ctor['id']}_throw
'''
    for i,field in enumerate(captures):
        text+=f' mov rax,QWORD PTR [r12+{8*(i+1)}]\n mov QWORD PTR [r14+{field["offset"]}],rax\n'
    text+=epilogue(ctor)
    text+=prologue(factory)+set_pc(factory,0)+f''' lea rcx,boom_class{bootstrap}
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne lambda_m{factory['id']}_throw
 lea rcx,boom_class{ident}
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne lambda_m{factory['id']}_throw
'''
    if captures:text+=f' test r12,r12\n jz lambda_m{factory["id"]}_bad\n'
    for i,field in enumerate(captures):
        text+=ref_cast(factory,f'QWORD PTR [r12+{i*8}]',field['descriptor'],0)
    text+=f''' mov rcx,QWORD PTR [boom_heap_ptr]
 lea rdx,boom_layout{ident}
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz lambda_m{factory['id']}_throw
 mov r14,rax
 mov QWORD PTR [rsp+64],rax
'''
    for i in range(argc):text+=f' mov rax,QWORD PTR [r12+{i*8}]\n mov QWORD PTR [rsp+{72+i*8}],rax\n'
    text+=set_pc(factory,4+2*argc)+f''' mov rcx,rbx
 lea rdx,[rsp+64]
 call boom_m{ctor['id']}
 cmp DWORD PTR [rbx],0
 jne lambda_m{factory['id']}_throw
 mov QWORD PTR [rsp+320],r14
'''+epilogue(factory)
    text+=prologue(sam)+checked_receiver(sam)
    for field in captures:
        text+=f' mov rax,QWORD PTR [r14+{field["offset"]}]\n mov QWORD PTR [rsp+{64+field["index"]*8}],rax\n'
    pc=5*argc
    for i,(erased,instantiated) in enumerate(zip(plan['sam_arguments'],plan['instantiated_arguments'])):
        pc+=2
        if erased!=instantiated:
            text+=ref_cast(sam,f'QWORD PTR [r12+{(i+1)*8}]',instantiated,pc);pc+=3
        else:text+=f' mov rax,QWORD PTR [r12+{(i+1)*8}]\n'
        text+=f' mov QWORD PTR [rsp+{64+(argc+i)*8}],rax\n'
    text+=set_pc(sam,pc)+f''' lea rcx,boom_class{impl['class_id']}
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne lambda_m{sam['id']}_throw
 mov rcx,rbx
 lea rdx,[rsp+64]
 call boom_m{impl['method']}
 cmp DWORD PTR [rbx],0
 jne lambda_m{sam['id']}_throw
'''
    result=plan['instantiated_result']
    if result.startswith(('L','[')) and result!=plan['implementation_result']:
        text+=ref_cast(sam,'rax',result,pc+3)
    if result!='V':text+=' mov QWORD PTR [rsp+320],rax\n'
    text+=epilogue(sam)
    return text
