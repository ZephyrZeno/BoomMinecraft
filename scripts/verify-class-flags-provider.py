"""Rebuild class flags from original bytes, then check assembly and actual COFF."""
from pathlib import Path
import json
import zipfile

def verify(path,batch,plan,m,S,wrapper):
    identity,summary,classes=S.base(batch,plan)
    S.check(m['base']==identity and m['tool_sources']==S.tools_identity(),'Class flags provider base/tool identity differs')
    S.check((m['context_bytes'],m['pool_bytes'],m['pool_abi'])==(32,32,1),'Class flags provider ABI differs')
    S.check(m['assembled'] and m['leaf_guest_services'] and not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified','all_family_natives_implemented','linked','executed','game_started','world_created')),
        'Class flags provider overclaims execution scope')
    byname={(c['origin']['loader'],c['name']):c for c in classes};parser=S.module('flags_raw_native_parser','verify-batch-frames.py')
    declarations=[];owners=[]
    for owner,name,desc,access,op in [('jdk/internal/reflect/Reflection','getClassAccessFlags','(Ljava/lang/Class;)I',0x109,0),('java/lang/Class','getModifiers','()I',0x101,1)]:
        c=byname['bootstrap',owner];S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Class flags native requires original bootstrap source')
        actual,raw=parser.original_methods(S.original_class(summary,c));S.check(actual==owner and len(raw)==len(c['method_ids']),'Class flags original native inventory differs')
        found=[(i,r) for i,r in zip(c['method_ids'],raw) if (r['name'],r['descriptor'])==(name,desc)]
        S.check(len(found)==1 and found[0][1]['code'] is None and found[0][1]['access']==access,'Class flags original native changed')
        declarations.append(dict(method=found[0][0],class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',owner=owner,source_id='jdk:java.base',name=name,descriptor=desc,access=access,operation=op));owners.append(c)
    S.check(m['methods']==declarations and m['native_methods']==2 and m['owner_source']==owners[0] and m['owner_sources']==sorted(owners,key=lambda c:c['id']),
        'Class flags declaration contracts differ')
    C=S.module('flags_independent_original_metadata','class-flags-source.py');metadata=C.index(summary,classes)
    metadata_path=S.checked(m['class_flags_metadata'])
    S.check(metadata_path.parent==path.parent and S.read(metadata_path)==metadata,'Class flags metadata differs from original classes/InnerClasses')
    S.check(m['provided_types']==metadata['provided_types'] and m['type_capacity']==metadata['type_capacity'],'Class flags coverage differs')
    expected='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+''.join(f"EXTERN boom_class{c['id']}:BYTE\n" for c in sorted(owners,key=lambda c:c['id']))
    expected+='EXTERN boom_java_class_typeid:PROC\nEXTERN boom_java_class_pool:BYTE\n'+C.data(metadata)
    expected+=''.join(wrapper(r,'boom_provider_class_flags_pool','boom_provider_class_flags_service') for r in declarations)
    kernel=S.ROOT/'native/providers/class_flags.asm.inc';expected+=kernel.read_text(encoding='utf-8')+'\nEND\n'
    S.check(m['policy']==dict(original_class_flags=True,reflection_inner_class_modifiers=True,arrays_raw_flags_zero=True,dynamic_redefinition=False),'Class flags policy differs')
    S.check(m['required_class_ids']==sorted(c['id'] for c in owners) and m['required_base_modules']==['class_literals'],'Class flags source initialization dependencies differ')
    S.check(m['pool_symbol']=='boom_provider_class_flags_pool' and m['service_symbol']=='boom_provider_class_flags_service','Class flags service/pool symbols differ')
    S.check(m['kernel_sha256']==S.digest(kernel)['sha256'],'Class flags ASM kernel changed')
    S.check(m['runtime_kernel_sha256']=={'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in ('classes32.asm','java_classes.asm')},'Class flags runtime ABI differs')
    assembly=S.checked(m['assembly']);obj=S.checked(m['object'])
    S.check(assembly.parent==path.parent and obj.parent==path.parent and assembly.read_text(encoding='utf-8')==expected,'Class flags generated source differs')
    S.check(S.digest(m['assembler']['path'])==m['assembler']['digest'],'Class flags assembler changed')
    coff=S.module('flags_actual_coff','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    exports={'boom_provider_class_flags_pool','boom_provider_class_flags_service'}|{f"boom_m{r['method']}{suffix}" for r in declarations for suffix in ('','_native')}
    imports={'boom_class_ensure32','boom_java_class_typeid','boom_java_class_pool'}|{f"boom_class{c['id']}" for c in owners}
    S.check(defined==exports==set(m['exports']) and undefined==imports==set(m['imports']),'Class flags actual COFF imports/definitions differ')
    wanted={r['method'] for r in declarations}
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap','vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing={json.loads(l)['method'] for l in z.read('natives.jsonl' if key=='frames' else 'methods.jsonl').splitlines()}
        S.check(not wanted&existing,'Class flags provider overlaps base natives')
    return dict(schema=1,verified=True,scope='original_class_raw_flags_and_inner_array_reflection_modifiers_all_source_types_and_native_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],native_methods=2,context_bytes=32,pool_abi=1,
        provided_types=metadata['provided_types'],type_capacity=metadata['type_capacity'],java_codegen_rerun=False,base_Java_ASM_and_COFF_modified=False,
        source_initializer_executed=False,runtime_linkage_closure_verified=False,linked=False,executed=False,game_started=False,world_created=False)
