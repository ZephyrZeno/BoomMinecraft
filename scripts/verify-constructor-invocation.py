"""Reconstruct original native/constructor metadata and check actual ASM/COFF."""
from pathlib import Path
import zipfile
import json


def verify(path,batch,plan,m,S):
    identity,summary,classes=S.base(batch,plan)
    S.check(m['base']==identity and m['tool_sources']==S.tools_identity(),'Invocation provider base/tool identity differs')
    S.check((m['context_bytes'],m['pool_bytes'],m['pool_abi'])==(32,96,1),'Invocation Context/pool ABI differs')
    S.check(m['assembled'] and not m['leaf_guest_services'] and m['native_java_upcalls'] and m['native_entries_traced'] and not m['all_native_frames'],
            'Invocation native upcall/frame scope differs')
    S.check(not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified','all_family_natives_implemented','linked','executed','game_started','world_created','exception_wrapping_complete')),
            'Invocation provider overclaims execution or exception coverage')
    C=S.module('independent_constructor_invocation_source','constructor-invocation-source.py')
    methods=C.contracts(summary,classes,S);metadata=C.index(summary,classes)
    S.check(m['methods']==methods and m['native_methods']==len(methods),'Invocation source native declarations differ')
    owners=[classes[i] for i in sorted({r['class_id'] for r in methods})]
    S.check(m['owner_sources']==owners and m['owner_source']==classes[methods[0]['class_id']],'Invocation original declaration owners differ')
    data_path=S.checked(m['constructor_invocation_metadata'])
    S.check(data_path.parent==path.parent and S.read(data_path)==metadata and m['constructor_records']==len(metadata['records']),
            'Invocation metadata differs from original constructors/Code/layouts')
    F=S.module('invocation_independent_frame_overlay','native-frame-overlay.py')
    frame_path=S.checked(m['frame_overlay']['manifest']);frame_receipt=S.checked(m['frame_overlay']['verification'])
    proof=F.verify(frame_path,batch,plan)
    S.check(S.read(frame_receipt)==proof,'Invocation native frame overlay differs')
    native_rows={r['id']:r for r in S.read(frame_path)['source']['original_native_declarations']}
    for method in methods:
        row=native_rows.get(method['method'])
        S.check(row is not None and row['class_id']==method['class_id'] and row['flags']&32 and not row['flags']&128,
                'Invocation entry has no original normal native frame')
    data,data_imports=C.data(metadata);kernel,kernel_imports=C.kernel_text(S.ROOT)
    imports={'boom_class_ensure32'}|{f"boom_class{r['class_id']}" for r in methods}
    expected='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+''.join(f"EXTERN boom_class{c['id']}:BYTE\n" for c in owners)
    extra=(data_imports|kernel_imports|{'boom_trace_enter','boom_trace_leave','boom_trace_pool'}|
           {f"boom_trace_method{r['method']}" for r in methods})-imports
    procs=kernel_imports|{'boom_trace_enter','boom_trace_leave'}
    expected+=''.join(f"EXTERN {name}:{'PROC' if name in procs else 'BYTE'}\n" for name in sorted(extra))+data;imports|=extra
    R=S.module('invocation_original_traced_adapter','verify-batch-frames.py')
    for r in methods:
        i=r['method'];expected+=f'.code\nPUBLIC boom_m{i}\nPUBLIC boom_m{i}_native\n'+R.native_adapter(i,r['class_id'],m['pool_symbol'],m['service_symbol'],0)[len('.code\n'):]
    expected+=kernel+'\nEND\n'
    S.check(m['pool_symbol']=='boom_provider_constructor_invoke_pool' and m['service_symbol']=='boom_provider_constructor_invoke_service',
            'Invocation source pool/service symbols differ')
    S.check(m['policy']==dict(normal_source_layouts=True,source_constructor_bodies=True,selected_diagnostic_upcalls=True,
        exception_wrapping_complete=False,dynamic_redefinition=False),'Invocation execution policy differs')
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    required=sorted({r['class_id'] for r in methods}|{metadata['constructor_class'],names['bootstrap','java/lang/Class']})
    S.check(m['required_class_ids']==required and m['required_base_modules']==['class_literals'] and m['required_provider_families']==['normal-constructors-v1'],
            'Invocation class/provider dependency differs')
    S.check(m['kernel_sources']=={'native/providers/'+n:S.digest(S.ROOT/'native/providers'/n)['sha256'] for n in C.KERNELS},'Invocation ASM helper source changed')
    S.check(m['kernel_sha256']==S.digest(S.ROOT/'native/providers/constructor_invoke.asm.inc')['sha256'],'Invocation selector ASM changed')
    kernels=['classes32.asm','java_classes.asm','objects.asm','heap.asm','runtime_types.asm','runtime_type_index.asm','frames.asm']
    S.check(m['runtime_kernel_sha256']=={'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in kernels},'Invocation imported runtime ABI changed')
    asm=S.checked(m['assembly']);obj=S.checked(m['object'])
    S.check(asm.parent==path.parent and obj.parent==path.parent and asm.read_text(encoding='utf-8')==expected,'Invocation generated ASM differs')
    S.check(S.digest(m['assembler']['path'])==m['assembler']['digest'],'Invocation assembler changed')
    exports={m['pool_symbol'],m['service_symbol']}|C.HELPERS|{f"boom_m{r['method']}{suffix}" for r in methods for suffix in ('','_native')}
    coff=S.module('invocation_actual_coff','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    S.check(defined==exports==set(m['exports']) and undefined==imports==set(m['imports']),'Invocation actual COFF imports/definitions differ')
    wanted={r['method'] for r in methods}
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap','vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing={json.loads(l)['method'] for l in z.read('natives.jsonl' if key=='frames' else 'methods.jsonl').splitlines()}
        S.check(not wanted&existing,'Invocation provider overlaps base source natives')
    return dict(schema=1,verified=True,scope='normal_source_constructor_selector_callsite_metadata_ASM_and_actual_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],native_methods=2,context_bytes=32,pool_abi=1,
        constructor_records=len(metadata['records']),java_codegen_rerun=False,base_Java_ASM_and_COFF_modified=False,
        exception_wrapping_complete=False,all_native_frames=False,source_initializer_executed=False,runtime_linkage_closure_verified=False,
        linked=False,executed=False,game_started=False,world_created=False)
