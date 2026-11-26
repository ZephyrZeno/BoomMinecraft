"""Reconstruct original file native/field identities and inspect actual COFF."""
from pathlib import Path
import zipfile
import json


def verify(path,batch,plan,m,S,wrapper):
    identity,summary,classes=S.base(batch,plan)
    S.check(m['base']==identity and m['tool_sources']==S.tools_identity(),'File bootstrap base/tool identity differs')
    S.check((m['context_bytes'],m['pool_bytes'],m['pool_abi'])==(32,48,1),'File bootstrap ABI differs')
    S.check(m['assembled'] and m['leaf_guest_services'] and not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified','all_family_natives_implemented','linked','executed','game_started','world_created')),
            'File bootstrap source/execution scope differs')
    C=S.module('independent_original_file_bootstrap','file-bootstrap-source.py')
    methods=C.contracts(summary,classes,S);metadata=C.index(summary,classes,S)
    S.check(m['methods']==methods and m['native_methods']==6,'File native source inventory differs')
    owners=[classes[i] for i in sorted({r['class_id'] for r in methods})]
    S.check(m['owner_sources']==owners and m['owner_source']==classes[methods[0]['class_id']],'File native original owners differ')
    record=S.checked(m['file_bootstrap_metadata'])
    S.check(record.parent==path.parent and S.read(record)==metadata,'File field metadata differs from original layouts')
    data,metadata_imports=C.data(metadata);services={'boom_stream_fields_init','boom_fd_service'}
    imports={'boom_class_ensure32'}|{f"boom_class{c['id']}" for c in owners}
    expected='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+''.join(f"EXTERN boom_class{c['id']}:BYTE\n" for c in owners)
    extra=(metadata_imports|services)-imports;imports|=extra
    expected+=''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))+data
    expected+=''.join(wrapper(r,'boom_provider_file_bootstrap_pool','boom_provider_file_bootstrap_service') for r in methods)
    kernel=S.ROOT/'native/providers/file_bootstrap.asm.inc';expected+=kernel.read_text(encoding='utf-8')+'\nEND\n'
    S.check(m['policy']==dict(normal_source_layouts=True,source_field_registration=True,standard_handles='Windows_GetStdHandle',append='Windows_false',byte_order='native_DWORD_memory_probe',file_IO_natives=False),'File bootstrap Windows execution policy differs')
    S.check(m['required_class_ids']==sorted(c['id'] for c in owners) and m['required_base_modules']==[],'File bootstrap source dependencies differ')
    S.check(m['pool_symbol']=='boom_provider_file_bootstrap_pool' and m['service_symbol']=='boom_provider_file_bootstrap_service','File bootstrap source symbols differ')
    S.check(m['kernel_sha256']==S.digest(kernel)['sha256'] and m['runtime_kernel_sha256']=={'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS},'File bootstrap imported kernel ABI changed')
    asm=S.checked(m['assembly']);obj=S.checked(m['object'])
    S.check(asm.parent==path.parent and obj.parent==path.parent and asm.read_text(encoding='utf-8')==expected,'File bootstrap generated ASM differs')
    S.check(S.digest(m['assembler']['path'])==m['assembler']['digest'],'File bootstrap assembler changed')
    exports={m['pool_symbol'],m['service_symbol']}|{f"boom_m{r['method']}{suffix}" for r in methods for suffix in ('','_native')}
    coff=S.module('file_bootstrap_actual_coff','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    S.check(defined==exports==set(m['exports']) and undefined==imports==set(m['imports']),'File bootstrap actual COFF definitions/imports differ')
    wanted={r['method'] for r in methods}
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap','vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing={json.loads(l)['method'] for l in z.read('natives.jsonl' if key=='frames' else 'methods.jsonl').splitlines()}
        S.check(not wanted&existing,'File bootstrap replaces an existing base native')
    return dict(schema=1,verified=True,scope='original_file_field_registration_and_Windows_standard_handle_ASM_and_actual_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],native_methods=6,context_bytes=32,pool_abi=1,
        java_codegen_rerun=False,base_Java_ASM_and_COFF_modified=False,file_IO_natives_provided=False,source_initializer_executed=False,
        runtime_linkage_closure_verified=False,linked=False,executed=False,game_started=False,world_created=False)
