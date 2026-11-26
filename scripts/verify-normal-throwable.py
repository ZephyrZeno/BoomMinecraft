"""Check original Throwable layouts, a real native frame and the actual COFF."""
from pathlib import Path
import json
import zipfile


def verify(path,batch,plan,m,S):
    identity,summary,classes=S.base(batch,plan)
    S.check(m['base']==identity and m['tool_sources']==S.tools_identity(),'Normal Throwable base/tool identity differs')
    S.check((m['context_bytes'],m['pool_bytes'],m['pool_abi'])==(32,64,1),'Normal Throwable pool/context ABI differs')
    S.check(m['assembled'] and m['leaf_guest_services'] and m['native_entries_traced'] and not m['all_native_frames'],
            'Normal Throwable native frame/scope differs')
    S.check(not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified','all_family_natives_implemented','linked','executed','game_started','world_created')),
            'Normal Throwable provider overclaims execution scope')
    C=S.module('independent_normal_throwable_source','normal-throwable-source.py')
    methods=C.contracts(summary,classes);metadata=C.index(summary,classes)
    S.check(m['methods']==methods and m['native_methods']==1,'Normal Throwable source native inventory differs')
    owner=classes[metadata['root']]
    S.check(m['owner_source']==owner and m['owner_sources']==[owner],'Normal Throwable original owner differs')
    record=S.checked(m['normal_throwable_metadata'])
    S.check(record.parent==path.parent and S.read(record)==metadata,'Normal Throwable inherited field metadata differs')
    F=S.module('normal_throwable_original_native_frame','native-frame-overlay.py')
    frame_path=S.checked(m['frame_overlay']['manifest']);receipt=S.checked(m['frame_overlay']['verification'])
    proof=F.verify(frame_path,batch,plan)
    S.check(S.read(receipt)==proof,'Normal Throwable original native frame receipt differs')
    rows={r['id']:r for r in S.read(frame_path)['source']['original_native_declarations']}
    row=rows.get(methods[0]['method'])
    S.check(row is not None and row['class_id']==owner['id'] and row['flags']&32 and not row['flags']&128,
            'Normal Throwable original native frame is unavailable')
    data,data_imports=C.data(metadata)
    services={'boom_object_check','boom_type_assignable','boom_array_new','boom_trace_head','boom_heap_contains','boom_trace_enter','boom_trace_leave'}
    imports={'boom_class_ensure32',f"boom_class{owner['id']}"}
    extra=(data_imports|services|{f"boom_trace_method{methods[0]['method']}"})-imports
    expected='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+f"EXTERN boom_class{owner['id']}:BYTE\n"
    expected+=''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))+data
    imports|=extra
    R=S.module('normal_throwable_traced_source_adapter','verify-batch-frames.py')
    i=methods[0]['method']
    expected+=f'.code\nPUBLIC boom_m{i}\nPUBLIC boom_m{i}_native\n'+R.native_adapter(i,owner['id'],'boom_normal_throwable_pool','boom_normal_throwable_fill',0)[len('.code\n'):]
    kernel=S.ROOT/'native/providers/normal_throwable.asm.inc'
    expected+=kernel.read_text(encoding='utf-8')+'\nEND\n'
    S.check(m['policy']==dict(normal_source_layouts=True,trace_pool_abi=3,max_backtrace_frames=128,backtrace_OOM_suppressed=True,
        Java_StackTraceElement_materialization=False,implicit_exception_factory=False,stack_roots=False,automatic_gc=False),
        'Normal Throwable bounded backtrace policy differs')
    S.check(m['required_class_ids']==[owner['id']] and m['required_base_modules']==[],
            'Normal Throwable class/module dependencies differ')
    S.check(m['pool_symbol']=='boom_normal_throwable_pool' and m['service_symbol']=='boom_normal_throwable_fill',
            'Normal Throwable source symbols differ')
    S.check(m['kernel_sha256']==S.digest(kernel)['sha256'] and m['runtime_kernel_sha256']==
            {'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS},'Normal Throwable imported runtime changed')
    asm=S.checked(m['assembly']);obj=S.checked(m['object'])
    S.check(asm.parent==path.parent and obj.parent==path.parent and asm.read_text(encoding='utf-8')==expected,
            'Normal Throwable generated ASM differs from source contracts')
    S.check(S.digest(m['assembler']['path'])==m['assembler']['digest'],'Normal Throwable assembler changed')
    exports={m['pool_symbol'],m['service_symbol'],f'boom_m{i}',f'boom_m{i}_native'}
    coff=S.module('normal_throwable_actual_coff','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    S.check(defined==exports==set(m['exports']) and undefined==imports==set(m['imports']),
            'Normal Throwable actual COFF definitions/imports differ')
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap','vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing={json.loads(l)['method'] for l in z.read('natives.jsonl' if key=='frames' else 'methods.jsonl').splitlines()}
        S.check(i not in existing,'Normal Throwable replaces an existing base native')
    return dict(schema=1,verified=True,scope='original_Throwable_receiver_layouts_native_frame_bounded_backtrace_ASM_and_actual_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],native_methods=1,context_bytes=32,pool_abi=1,
        normal_receiver_layouts=len(metadata['rows']),max_backtrace_frames=128,Java_StackTraceElement_materialization=False,
        implicit_exception_factory=False,all_native_frames=False,stack_roots=False,automatic_gc=False,
        java_codegen_rerun=False,base_Java_ASM_and_COFF_modified=False,source_initializer_executed=False,
        runtime_linkage_closure_verified=False,linked=False,executed=False,game_started=False,world_created=False)
