"""Reconstruct original priority declaration, field maps, ASM and actual COFF."""
from pathlib import Path
import json
import zipfile


def verify(path,batch,plan,m,S,wrapper):
    identity,summary,classes=S.base(batch,plan)
    C=S.module('independent_normal_thread_priority','normal-thread-priority-source.py');meta=C.index(summary,classes,S)
    owner=classes[meta['thread_class']]
    S.check(m['base']==identity and m['tool_sources']==S.tools_identity(),'Thread priority source/tool identity differs')
    S.check((m['context_bytes'],m['pool_bytes'],m['pool_abi'])==(32,80,1) and m['assembled'] and m['leaf_guest_services'] and
        m['all_native_frames'] is False and not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified',
            'all_family_natives_implemented','linked','executed','game_started','world_created')),'Thread priority ABI or scope differs')
    record=S.checked(m['normal_thread_priority_metadata'])
    S.check(record.parent==path.parent and S.read(record)==meta and m['methods']==meta['methods'] and m['native_methods']==1 and
        m['owner_source']==owner and m['owner_sources']==[owner],'Thread priority original source metadata differs')
    S.check(m['policy']==C.POLICY and m['required_class_ids']==sorted(meta[k] for k in ('thread_class','holder_class','virtual_class')) and
        m['required_base_modules']==[] and m['required_provider_families']==['normal-thread-primitives-v1'],
        'Thread priority source policy/dependencies differ')
    S.check((m['pool_symbol'],m['service_symbol'])==('boom_provider_thread_priority_pool','boom_provider_thread_priority_service'),
        'Thread priority binding symbols differ')
    data,imports=C.data(meta);kernel,services=C.kernel(S)
    base_imports={'boom_class_ensure32',f"boom_class{owner['id']}"};extra=(imports|services)-base_imports
    expected='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+f"EXTERN boom_class{owner['id']}:BYTE\n"
    expected+=''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))
    expected+=data+''.join(wrapper(row,m['pool_symbol'],m['service_symbol']) for row in meta['methods'])+kernel+'\nEND\n'
    asm,obj=S.checked(m['assembly']),S.checked(m['object'])
    S.check(asm.parent==path.parent and obj.parent==path.parent and asm.read_text(encoding='utf-8')==expected,
            'Thread priority generated assembly differs')
    S.check(m['kernel_sha256']==S.digest(S.ROOT/'native/providers/normal_thread_priority.asm.inc')['sha256'] and
        m['runtime_kernel_sha256']=={'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS},
        'Thread priority imported runtime kernel changed')
    S.check(S.digest(m['assembler']['path'])==m['assembler']['digest'],'Thread priority assembler changed')
    coff=S.module('thread_priority_actual_coff','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    S.check(defined==C.exports(meta['methods'])==set(m['exports']) and undefined==imports|services|base_imports==set(m['imports']),
            'Thread priority actual COFF differs')
    wanted={r['method'] for r in meta['methods']}
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap',
                'vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing={json.loads(line)['method'] for line in z.open('natives.jsonl' if key=='frames' else 'methods.jsonl')}
        S.check(not wanted&existing,'Thread priority replaces an existing base native')
    return dict(schema=1,verified=True,scope='original_Thread_priority_and_startup_field_maps_ASM_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],
        verifier_sha256=S.digest(Path(__file__))['sha256'],base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],
        source_native_methods=1,normal_field_maps=2,original_Thread_setPriority0_executed=False,
        linked=False,executed=False,game_started=False,world_created=False)
