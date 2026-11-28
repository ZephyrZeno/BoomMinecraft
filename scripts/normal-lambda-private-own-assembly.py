"""Source renderer for exact own-private Lambda calls and boolean captures.

body/generated module consume source-verified generated Class records and an
explicit old public dispatch-binding map. Existing public/static items delegate
byte-for-byte; private items require original handle7, normalized opcode182,
the exact own-private declaration and original hidden lookup-host identity.

The new path keeps normal trace Frames/Context PCs, argument casts, receiver-null
ordering and the original normal Java method envelope. It requests neither an
owner initializer nor virtual override selection. Boolean capture stores mask
the low bit and use BYTE memory, reads zero-extend BYTE memory, and value-argv
cells remain in original declaration order. Only actual reference slots are GC
oop-prefix fields. No business method body is implemented in this renderer.

The API returns assembly strings and proof metadata; it writes no files and
does not compile, link, execute, allocate IDs or admit a new source epoch.
The caller must retain the original prefix/policy receipt and obtain separate
source, complete object, root, parent-graph and runtime validation as applicable.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

PUBLIC=load('private_backend_unchanged_public_renderer',ROOT/'scripts/normal-lambda-instance-assembly.py')
OLD,C=PUBLIC.OLD,PUBLIC.C
check,pc_source=PUBLIC.check,PUBLIC.pc_source

def _private_template(g,sources,contract_module=None):
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
boom_batch_field_record{n} DWORD 0464D4150h,1,1,{field['storage_bytes']},{int(field['reference'])},0
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
        text+=f' mov rax,QWORD PTR [r12+{8*(i+1)}]\n'
        if field['reference']:text+=f' mov QWORD PTR [r14+{field["offset"]}],rax\n'
        else:text+=f' and eax,1\n mov BYTE PTR [r14+{field["offset"]}],al\n'
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
        if field['reference']:text+=ref_cast(factory,f'QWORD PTR [r12+{i*8}]',field['descriptor'],0)
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
        if field['reference']:text+=f' mov rax,QWORD PTR [r14+{field["offset"]}]\n'
        else:text+=f' movzx eax,BYTE PTR [r14+{field["offset"]}]\n'
        text+=f' mov QWORD PTR [rsp+{64+field["index"]*8}],rax\n'
    pc=5*argc
    for i,(erased,instantiated) in enumerate(zip(plan['sam_arguments'],plan['instantiated_arguments'])):
        pc+=2
        if erased!=instantiated:
            text+=ref_cast(sam,f'QWORD PTR [r12+{(i+1)*8}]',instantiated,pc);pc+=3
        else:text+=f' mov rax,QWORD PTR [r12+{(i+1)*8}]\n'
        text+=f' mov QWORD PTR [rsp+{64+(argc+i)*8}],rax\n'
    text+=set_pc(sam,pc)+f''' cmp QWORD PTR [rsp+64],0
 je lambda_m{sam['id']}_null
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


def actual_private_sam(g):
    ref=g['class_file'];blob=Path(ref['path']).read_bytes()
    check(len(blob)==ref['digest']['size'] and hashlib.sha256(blob).hexdigest()==ref['digest']['sha256'],'Actual private Class identity')
    raw=C.I.Source(blob);plan=g['contract']
    matches=[m for m in raw.methods if (m['name'],m['descriptor'])==(plan['sam_name'],plan['sam_descriptor'])]
    check(len(matches)==1,'One exact private generated SAM')
    method=next(m for m in g['methods'] if (m['name'],m['descriptor'])==(plan['sam_name'],plan['sam_descriptor']))
    code=raw.code(matches[0])['bytes'];ops=list(C.I.stream(code))
    check(method['code_length']==len(code) and method['code_sha256']==hashlib.sha256(code).hexdigest(),'Actual SAM Code identity')
    calls=[op for op in ops if op['opcode'] in (182,183,184,185)]
    check(len(calls)==1 and calls[0]['opcode']==182,'Private-own REF7 must normalize to invokevirtual182')
    member=raw.member(calls[0]['operand']['Constant'])
    check(member=={k:plan['implementation'][k] for k in ('owner','name','descriptor','interface')},'Actual private original MethodRef')
    return method,code,ops,calls[0]['pc']

def private_body(g,sources):
    plan=g['contract'];member=plan['implementation_member'];access=plan['private_access']
    check(plan['implementation']['reference_kind']==7 and plan['invocation']['normalized_reference_kind']==5
        and plan['invocation']['opcode']==182 and plan['normalized_invocation_kind']==5,'Explicit private normalization source rule')
    check(member['access']&7==2 and not member['access']&(8|0x100|0x400) and member['code_sha256']
        and member['class_id']==plan['host']['class_id']==access['lookup_host']['id']
        and member['class_sha256']==plan['host']['origin']['sha256']==access['lookup_host']['origin']['sha256']
        and access['private_method_non_overridable'] is True and access['hidden_nestmate'] is True
        and access['raw_NestHost_invented'] is False,'Exact own-private original host access and concrete member')
    check(plan['invocation']['declaring_owner_initialization_requested'] is False
        and plan['invocation']['virtual_override_selection_required'] is False,'No static initialization or override selection')
    fields=g['layout']['fields'];captures=plan['captures']
    check(len(fields)==len(captures) and [f['index'] for f in fields]==list(range(len(captures)))
        and [f['descriptor'] for f in fields]==captures,'Capture fields remain in original argument/declaration order')
    refs=[f for f in fields if f['reference']];scalars=[f for f in fields if not f['reference']]
    check(g['layout']['reference_prefix']==len(refs) and [f['offset'] for f in refs]==[8*i for i in range(len(refs))],
        'Only actual reference fields form the GC prefix')
    check(all(f['descriptor'].startswith(('L','[')) and f['storage_bytes']==8 for f in refs)
        and all(f['descriptor']=='Z' and f['storage_bytes']==1 for f in scalars)
        and [f['offset'] for f in scalars]==[8*len(refs)+i for i in range(len(scalars))]
        and g['layout']['payload_bytes']==8*len(refs)+len(scalars),'Exact byte boolean scalar tail; no QWORD overrun')
    ordinary=plan['ordinary_target']
    check(ordinary['CallerSensitive'] is False and ordinary['signature_polymorphic'] is False
        and ordinary['class_sha256']==member['class_sha256'],'No caller-sensitive or polymorphic private bridge')
    method,code,ops,invoke_pc=actual_private_sam(g);mid=method['id']
    text=_private_template(g,sources)
    start=f'boom_m{mid}_body PROC FRAME\n';stop=f'boom_m{mid}_body ENDP\n'
    check(text.count(start)==text.count(stop)==1,'Unique new private SAM')
    at=text.index(start);end=text.index(stop,at)+len(stop);sam=text[at:end]
    before=[op['pc'] for op in ops if op['opcode']==192 and op['pc']<invoke_pc]
    after=[op['pc'] for op in ops if op['opcode']==192 and op['pc']>invoke_pc]
    check(len(before)==sum(a!=b for a,b in zip(plan['sam_arguments'],plan['instantiated_arguments'])),'Actual argument checkcast sequence')
    old_pc=5*len(fields);mapping=[];cast=0
    for erased,instantiated in zip(plan['sam_arguments'],plan['instantiated_arguments']):
        old_pc+=2
        if erased!=instantiated:
            mapping.append((old_pc,before[cast],'argument_checkcast'));cast+=1;old_pc+=3
    mapping.append((old_pc,invoke_pc,'private_invoke'))
    result=plan['instantiated_result'];has_result_cast=result.startswith(('L','[')) and result!=plan['implementation_result']
    check(len(after)==int(has_result_cast),'Actual result checkcast sequence')
    if has_result_cast:mapping.append((old_pc+3,after[0],'result_checkcast'))
    edits=[]
    for old,new,role in mapping:
        before_text,after_text=pc_source(mid,old),pc_source(mid,new)
        check(sam.count(before_text)==1,'Unique existing private template PC: '+role)
        if old!=new:edits.append((sam.index(before_text),before_text,after_text,role))
    edits.sort()
    changed=sam
    for offset,before_text,after_text,role in reversed(edits):
        check(changed[offset:offset+len(before_text)]==before_text,'Actual source PC edit position')
        changed=changed[:offset]+after_text+changed[offset+len(before_text):]
    reverse=[];delta=0
    for offset,before_text,after_text,role in edits:
        reverse.append((offset+delta,after_text,before_text,role));delta+=len(after_text)-len(before_text)
    reconstructed=changed
    for offset,after_text,before_text,role in reversed(reverse):
        check(reconstructed[offset:offset+len(after_text)]==after_text,'Actual source PC inverse position')
        reconstructed=reconstructed[:offset]+before_text+reconstructed[offset+len(after_text):]
    check(reconstructed==sam,'Complete private SAM PC inverse')
    final=text[:at]+changed+text[end:]
    check(f'call boom_m{member["method"]}\n' in changed and f'lea rcx,boom_class{member["class_id"]}\n' not in changed
        and 'boom_batch_virtual_invoke' not in changed and 'boom_batch_call_' not in changed,'Exact normal private entry, no static ensure or ordinary dispatcher')
    return final,dict(reference_kind=7,normalized_reference_kind=5,actual_SAM_Code_sha256=hashlib.sha256(code).hexdigest(),
        actual_source_PC_mapping=[dict(template_pc=a,actual_pc=b,role=r) for a,b,r in mapping],
        target_original_normal_entry='boom_m'+str(member['method']),declaring_owner_initialization_requested=False,
        virtual_override_selection_required=False,private_non_overridable=True,
        receiver_null_guard_after_casts_at_actual_invocation_PC=True,
        capture_argument_order_preserved=True,reference_prefix_only_actual_oops=True,
        boolean_capture_storage_bytes=1,boolean_ctor_store_masks_low_bit=True,
        full_private_template_PC_inverse=True,template_source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_sha256=hashlib.sha256(final.encode()).hexdigest(),
        PC_edits=[dict(offset=o,before=b,after=a,role=r) for o,b,a,r in edits],
        original_Java_bodies_changed=False,business_logic_implemented_here=False,source_only=True)

def body(g,sources,binding):
    if g['contract']['implementation']['reference_kind']==7:
        check(binding is None,'Private-own bridge has no ordinary virtual binding')
        return private_body(g,sources)
    return PUBLIC.body(g,sources,binding)

def module(manifest,sources,bindings):
    parts=['.data?\nALIGN 8\nPUBLIC boom_lambda_failure_roots\nboom_lambda_failure_roots LABEL QWORD\n'];proofs=[]
    for g in manifest['generated']:
        kind=g['contract']['implementation']['reference_kind']
        binding=None if kind in (6,7) else bindings.get(g['contract']['binding_label'])
        text,proof=body(g,sources,binding);parts.append(text);proofs.append(dict(type_id=g['type_id'],**proof))
    parts.append(f'.const\nPUBLIC boom_lambda_failure_root_count\nboom_lambda_failure_root_count QWORD {len(manifest["generated"])}\n')
    return '\n'.join(parts),proofs
