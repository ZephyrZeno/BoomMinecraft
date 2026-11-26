"""Reconstruct constructor metadata from locked originals and check actual COFF."""
from pathlib import Path
import json
import zipfile

def verify(path,batch,plan,m,S,wrapper):
    identity,summary,classes=S.base(batch,plan)
    S.check(m['base']==identity and m['tool_sources']==S.tools_identity(),'Constructor provider base/tool identity differs')
    S.check(m['context_bytes']==32 and m['pool_bytes']==160 and m['pool_abi']==1,'Constructor provider ABI differs')
    S.check(m['assembled'] and not m['leaf_guest_services'] and m['native_java_upcalls'] and not m['all_native_frames'],
        'Constructor initializer upcall/frame scope differs')
    S.check(not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified','all_family_natives_implemented','linked','executed','game_started','world_created')),
        'Constructor provider overclaims compilation/execution scope')
    owner=next(c for c in classes if (c['origin']['loader'],c['name'])==('bootstrap','java/lang/Class'))
    S.check(owner['origin']['source_id']=='jdk:java.base' and not owner['origin'].get('generated'),'Constructor native requires original bootstrap Class')
    parser=S.module('constructor_native_original_parser','verify-batch-frames.py')
    name,raw=parser.original_methods(S.original_class(summary,owner))
    S.check(name==owner['name'] and len(raw)==len(owner['method_ids']),'Constructor source native inventory differs')
    found=[(i,r) for i,r in zip(owner['method_ids'],raw) if (r['name'],r['descriptor'])==('getDeclaredConstructors0','(Z)[Ljava/lang/reflect/Constructor;')]
    S.check(len(found)==1 and found[0][1]['access']==0x102 and found[0][1]['code'] is None,'Constructor source native changed')
    method=dict(method=found[0][0],class_id=owner['id'],class_sha256=owner['origin']['sha256'],loader='bootstrap',owner=owner['name'],
        source_id='jdk:java.base',name=found[0][1]['name'],descriptor=found[0][1]['descriptor'],access=0x102,operation=0)
    S.check(m['methods']==[method] and m['native_methods']==1 and m['owner_source']==owner and m['owner_sources']==[owner],
        'Constructor native source contract differs')
    C=S.module('constructor_independent_original_source','constructor-provider-source.py')
    expected_metadata=C.index(summary,classes)
    metadata_path=S.checked(m['constructor_metadata'])
    S.check(metadata_path.parent==path.parent and S.read(metadata_path)==expected_metadata,'Constructor metadata differs from original class bytes/layouts')
    S.check(m['constructor_records']==len(expected_metadata['records']) and m['unavailable_constructor_records']==sum(r['unavailable'] for r in expected_metadata['records']),
        'Constructor metadata coverage differs')
    data,metadata_imports=C.data(expected_metadata)
    service_imports={'boom_heap_alloc','boom_object_new','boom_java_class_typeid','boom_java_class_load'}
    imports={'boom_class_ensure32',f"boom_class{owner['id']}"}|metadata_imports|service_imports
    expected=f"option casemap:none\nEXTERN boom_class_ensure32:PROC\nEXTERN boom_class{owner['id']}:BYTE\n"
    extra=imports-{'boom_class_ensure32',f"boom_class{owner['id']}"}
    expected+=''.join(f"EXTERN {n}:{'PROC' if n in service_imports else 'BYTE'}\n" for n in sorted(extra))
    expected+=data+wrapper(method,'boom_provider_constructor_pool','boom_provider_constructor_service')
    kernel=S.ROOT/'native/providers/constructors.asm.inc';expected+=kernel.read_text(encoding='utf-8')+'\nEND\n'
    S.check(m['policy']==dict(normal_source_layouts=True,metadata_from_original_classes=True,nonmoving_heap_abi=1,dynamic_redefinition=False),
        'Constructor execution policy differs')
    S.check(m['required_class_ids']==[owner['id'],expected_metadata['constructor_class'],expected_metadata['string_class']] and m['required_base_modules']==['class_literals'],
        'Constructor source initialization dependencies differ')
    S.check(m['pool_symbol']=='boom_provider_constructor_pool' and m['service_symbol']=='boom_provider_constructor_service',
        'Constructor provider symbols differ')
    S.check(m['kernel_sha256']==S.digest(kernel)['sha256'],'Constructor ASM kernel changed')
    kernels=['classes32.asm','java_classes.asm','objects.asm','heap.asm']
    S.check(m['runtime_kernel_sha256']=={'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in kernels},
        'Constructor imported runtime ABI differs')
    assembly=S.checked(m['assembly']);obj=S.checked(m['object'])
    S.check(assembly.parent==path.parent and obj.parent==path.parent and assembly.read_text(encoding='utf-8')==expected,
        'Constructor source ASM differs')
    S.check(S.digest(m['assembler']['path'])==m['assembler']['digest'],'Constructor assembler changed')
    coff=S.module('constructor_actual_coff_verifier','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    exports={'boom_provider_constructor_pool','boom_provider_constructor_service',f"boom_m{method['method']}",f"boom_m{method['method']}_native"}
    S.check(defined==exports==set(m['exports']) and undefined==imports==set(m['imports']),'Constructor actual COFF imports/definitions differ')
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap','vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing={json.loads(l)['method'] for l in z.read('natives.jsonl' if key=='frames' else 'methods.jsonl').splitlines()}
        S.check(method['method'] not in existing,'Constructor provider replaces a base implementation')
    return dict(schema=1,verified=True,scope='normal_source_constructor_metadata_all_locked_classes_and_native_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],native_methods=1,context_bytes=32,pool_abi=1,
        constructor_records=m['constructor_records'],unavailable_constructor_records=m['unavailable_constructor_records'],
        java_codegen_rerun=False,base_Java_ASM_and_COFF_modified=False,source_initializer_executed=False,
        runtime_linkage_closure_verified=False,linked=False,executed=False,all_native_frames=False,game_started=False,world_created=False)
