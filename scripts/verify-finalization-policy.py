"""Verify the original policy declaration, immutable configuration and actual COFF."""
from pathlib import Path
import json
import zipfile


def verify(path,batch,plan,m,S,wrapper):
    identity,summary,classes=S.base(batch,plan)
    C=S.module('independent_finalization_policy','finalization-policy-source.py');meta=C.index(summary,classes,S)
    owner=classes[meta['methods'][0]['class_id']]
    S.check(m['base']==identity and m['tool_sources']==S.tools_identity(),'Finalization policy source/tool identity differs')
    S.check((m['context_bytes'],m['pool_bytes'],m['pool_abi'])==(32,32,1) and m['assembled'] and m['leaf_guest_services'] and
        m['all_native_frames'] is False and not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified',
            'all_family_natives_implemented','linked','executed','game_started','world_created')),'Finalization policy ABI or scope differs')
    record=S.checked(m['finalization_policy_metadata'])
    S.check(record.parent==path.parent and S.read(record)==meta and m['methods']==meta['methods'] and m['native_methods']==1 and
        m['owner_source']==owner and m['owner_sources']==[owner],'Finalization policy original source metadata differs')
    S.check(m['policy']==C.POLICY and m['required_class_ids']==[owner['id']] and m['required_base_modules']==[] and
        (m['pool_symbol'],m['service_symbol'])==('boom_provider_finalization_policy_pool','boom_provider_finalization_policy_service'),
        'Finalization policy binding policy differs')
    kernel=S.ROOT/'native/providers/finalization_policy.asm.inc'
    expected='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+f"EXTERN boom_class{owner['id']}:BYTE\n"+C.data()
    expected+=''.join(wrapper(r,m['pool_symbol'],m['service_symbol']) for r in meta['methods'])+kernel.read_text(encoding='utf-8')+'\nEND\n'
    asm,obj=S.checked(m['assembly']),S.checked(m['object'])
    S.check(asm.parent==path.parent and obj.parent==path.parent and asm.read_text(encoding='utf-8')==expected,
        'Finalization policy generated assembly differs')
    S.check(m['kernel_sha256']==S.digest(kernel)['sha256'] and m['runtime_kernel_sha256']=={
        'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS},'Finalization policy runtime kernel differs')
    S.check(S.digest(m['assembler']['path'])==m['assembler']['digest'],'Finalization policy assembler changed')
    coff=S.module('finalization_policy_actual_coff','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    exports={m['pool_symbol'],m['service_symbol']}|{f"boom_m{r['method']}{s}" for r in meta['methods'] for s in ('','_native')}
    imports={'boom_class_ensure32',f"boom_class{owner['id']}"}
    S.check(defined==exports==set(m['exports']) and undefined==imports==set(m['imports']),'Finalization policy actual COFF differs')
    wanted={r['method'] for r in meta['methods']}
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap',
                'vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing={json.loads(line)['method'] for line in z.open('natives.jsonl' if key=='frames' else 'methods.jsonl')}
        S.check(not wanted&existing,'Finalization policy replaces an existing base native')
    return dict(schema=1,verified=True,scope='original_Finalizer_default_enabled_policy_query_ASM_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],source_native_methods=1,
        finalizer_registration_implemented=False,automatic_reference_processing=False,
        linked=False,executed=False,game_started=False,world_created=False)
