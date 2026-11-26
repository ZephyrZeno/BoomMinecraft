"""Reconstruct original Object notification bindings, exact MASM and COFF."""
from pathlib import Path
import json
import zipfile


def verify(path,batch,plan,m,S,wrapper):
    identity,summary,classes=S.base(batch,plan)
    C=S.module('independent_object_notification','object-notification-source.py');meta=C.index(summary,classes,S)
    owner=classes[meta['methods'][0]['class_id']]
    S.check(m['base']==identity and m['tool_sources']==S.tools_identity(),'Object notification source/tool identity differs')
    S.check((m['context_bytes'],m['pool_bytes'],m['pool_abi'])==(32,32,1) and m['assembled'] and m['leaf_guest_services'] and
        m['all_native_frames'] is False and not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified',
            'all_family_natives_implemented','linked','executed','game_started','world_created')),'Object notification ABI or scope differs')
    record=S.checked(m['object_notification_metadata'])
    S.check(record.parent==path.parent and S.read(record)==meta and m['methods']==meta['methods'] and m['native_methods']==2 and
        m['owner_source']==owner and m['owner_sources']==[owner],'Object notification original source metadata differs')
    S.check(m['policy']==C.POLICY and m['required_class_ids']==[owner['id']] and m['required_base_modules']==[] and
        (m['pool_symbol'],m['service_symbol'])==('boom_provider_object_notification_pool','boom_provider_object_notification_service'),
        'Object notification binding policy differs')
    kernel=S.ROOT/'native/providers/object_notification.asm.inc'
    expected='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+f"EXTERN boom_class{owner['id']}:BYTE\n"
    expected+='EXTERN boom_monitor_notify:PROC\nEXTERN boom_monitor_notify_all:PROC\nEXTERN boom_heap_ptr:BYTE\n'+C.data()
    expected+=''.join(wrapper(r,m['pool_symbol'],m['service_symbol']) for r in meta['methods'])+kernel.read_text(encoding='utf-8')+'\nEND\n'
    asm,obj=S.checked(m['assembly']),S.checked(m['object'])
    S.check(asm.parent==path.parent and obj.parent==path.parent and asm.read_text(encoding='utf-8')==expected,
        'Object notification generated assembly differs')
    S.check(m['kernel_sha256']==S.digest(kernel)['sha256'] and m['runtime_kernel_sha256']=={
        'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS},'Object notification runtime kernel differs')
    S.check(S.digest(m['assembler']['path'])==m['assembler']['digest'],'Object notification assembler changed')
    coff=S.module('object_notification_actual_coff','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    exports={m['pool_symbol'],m['service_symbol']}|{f"boom_m{r['method']}{s}" for r in meta['methods'] for s in ('','_native')}
    imports={'boom_class_ensure32',f"boom_class{owner['id']}",'boom_heap_ptr','boom_monitor_notify','boom_monitor_notify_all'}
    S.check(defined==exports==set(m['exports']) and undefined==imports==set(m['imports']),'Object notification actual COFF differs')
    wanted={r['method'] for r in meta['methods']}
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap',
                'vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing={json.loads(line)['method'] for line in z.open('natives.jsonl' if key=='frames' else 'methods.jsonl')}
        S.check(not wanted&existing,'Object notification replaces an existing base native')
    return dict(schema=1,verified=True,scope='original_Object_notify_notifyAll_empty_wait_set_ASM_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],source_native_methods=2,
        Object_wait_implemented=False,linked=False,executed=False,game_started=False,world_created=False)
