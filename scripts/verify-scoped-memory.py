"""Validate the two original native declarations and real registration COFF."""
from pathlib import Path
import json
import zipfile


def verify(path,batch,plan,m,S,wrapper):
    identity,summary,classes=S.base(batch,plan)
    S.check(m['base']==identity and m['tool_sources']==S.tools_identity(),'Scoped registration base/tool identity differs')
    S.check((m['context_bytes'],m['pool_bytes'],m['pool_abi'])==(32,32,1),'Scoped registration ABI differs')
    S.check(m['assembled'] and m['leaf_guest_services'] and not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified','all_family_natives_implemented','linked','executed','game_started','world_created')),
            'Scoped registration overclaims source/execution scope')
    C=S.module('independent_scoped_memory_original_source','scoped-memory-source.py');metadata=C.index(summary,classes,S)
    methods=[metadata['registration']];owner=classes[methods[0]['class_id']]
    S.check(m['methods']==methods and m['native_methods']==1 and m['owner_source']==owner and m['owner_sources']==[owner],
            'Scoped registration original declaration differs')
    record=S.checked(m['scoped_memory_metadata'])
    S.check(record.parent==path.parent and S.read(record)==metadata,'Scoped registration native inventory differs')
    expected='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+f"EXTERN boom_class{owner['id']}:BYTE\n"
    services={'boom_scoped_native_register','__imp_boom_scoped_close_unavailable'}
    expected+=''.join(f"EXTERN {n}:{'QWORD' if n.startswith('__imp_') else 'PROC'}\n" for n in sorted(services))+C.data()
    expected+=wrapper(methods[0],'boom_provider_scoped_memory_pool','boom_provider_scoped_memory_service')
    kernel=S.ROOT/'native/providers/scoped_memory.asm.inc';expected+=kernel.read_text(encoding='utf-8')+'\nEND\n'
    S.check(m['policy']==dict(original_native_inventory=True,registered_entries=1,close_target='explicit_UnsatisfiedLinkError',
        target_address_policy='canonical_runtime_export_from_IAT',close_scope_implemented=False,thread_handshake_implemented=False),'Scoped registration partial service policy differs')
    S.check(m['required_class_ids']==[owner['id']] and m['required_base_modules']==[],'Scoped registration dependencies differ')
    S.check(m['pool_symbol']=='boom_provider_scoped_memory_pool' and m['service_symbol']=='boom_provider_scoped_memory_service',
            'Scoped registration pool/service symbols differ')
    S.check(m['kernel_sha256']==S.digest(kernel)['sha256'] and m['runtime_kernel_sha256']==
            {'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS},'Scoped registration runtime changed')
    asm=S.checked(m['assembly']);obj=S.checked(m['object'])
    S.check(asm.parent==path.parent and obj.parent==path.parent and asm.read_text(encoding='utf-8')==expected,
            'Scoped registration generated ASM differs')
    S.check(S.digest(m['assembler']['path'])==m['assembler']['digest'],'Scoped registration assembler changed')
    exports={m['pool_symbol'],m['service_symbol']}|{f"boom_m{methods[0]['method']}{suffix}" for suffix in ('','_native')}
    imports={'boom_class_ensure32',f"boom_class{owner['id']}"}|services
    coff=S.module('scoped_registration_actual_coff','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    S.check(defined==exports==set(m['exports']) and undefined==imports==set(m['imports']),'Scoped registration actual COFF differs')
    i=methods[0]['method']
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap','vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing={json.loads(l)['method'] for l in z.read('natives.jsonl' if key=='frames' else 'methods.jsonl').splitlines()}
        S.check(i not in existing,'Scoped registration replaces an existing base native')
    return dict(schema=1,verified=True,scope='original_ScopedMemoryAccess_registration_ASM_and_actual_COFF_only_close_unavailable',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],native_methods=1,context_bytes=32,pool_abi=1,
        registered_entries=1,close_scope_implemented=False,thread_handshake_implemented=False,
        java_codegen_rerun=False,base_Java_ASM_and_COFF_modified=False,source_initializer_executed=False,
        runtime_linkage_closure_verified=False,linked=False,executed=False,game_started=False,world_created=False)
