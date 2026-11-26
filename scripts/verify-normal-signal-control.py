"""Reconstruct original Signal callbacks, lifecycle metadata, ASM and COFF."""
from pathlib import Path
import json
import zipfile


def verify(path, batch, plan, m, S, wrapper):
    identity, summary, classes = S.base(batch, plan)
    C = S.module('independent_normal_signal_control', 'normal-signal-control-source.py')
    meta = C.index(summary, classes, S)
    owner = classes[meta['methods'][0]['class_id']]
    S.check(m['base'] == identity and m['tool_sources'] == S.tools_identity(), 'Signal control source/tool identity differs')
    S.check((m['context_bytes'], m['pool_bytes'], m['pool_abi']) == (32,256,1), 'Signal control Context/pool ABI differs')
    S.check(m['assembled'] and not m['leaf_guest_services'] and m['all_native_frames'] is False and
        not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified',
            'all_family_natives_implemented','linked','executed','game_started','world_created')),
        'Signal control provider overclaims Java execution or complete signals')
    record = S.checked(m['normal_signal_control_metadata'])
    S.check(record.parent == path.parent and S.read(record) == meta, 'Signal control original metadata differs')
    S.check(m['methods'] == meta['methods'] and m['native_methods'] == 2 and m['owner_source'] == owner and
        m['owner_sources'] == [owner] and m['policy'] == C.POLICY, 'Signal control original natives/policy differ')
    S.check(m['required_class_ids'] == meta['required_class_ids'] and m['required_base_modules'] == ['properties'] and
        m['required_provider_families'] == ['normal-thread-primitives-v1','normal-thread-start-v1'] and
        m['required_java_methods'] == sorted(c['method'] for c in meta['upcalls']) and
        m.get('required_source_contracts',[]) == [], 'Signal control original callback/dependencies differ')
    S.check((m['pool_symbol'],m['service_symbol']) == ('boom_provider_signal_pool','boom_provider_signal_service') and
        m['allowed_foreign_imports'] == sorted(C.FOREIGN), 'Signal control symbols or OS imports differ')
    data, imports = C.data(meta)
    kernel, services = C.kernel(S)
    base_imports = {'boom_class_ensure32',f"boom_class{owner['id']}"}
    extra = (imports|services)-base_imports
    expected = 'option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+f"EXTERN boom_class{owner['id']}:BYTE\n"
    expected += ''.join(f"EXTERN {s}:{'PROC' if s in services else 'BYTE'}\n" for s in sorted(extra))
    expected += data+''.join(wrapper(row,m['pool_symbol'],m['service_symbol']) for row in meta['methods'])+kernel+'\nEND\n'
    asm,obj = S.checked(m['assembly']),S.checked(m['object'])
    S.check(asm.parent == path.parent and obj.parent == path.parent and asm.read_text(encoding='utf-8') == expected,
            'Signal control generated ASM differs')
    S.check(m['kernel_sha256'] == S.digest(S.ROOT/'native/providers/normal_signal_control.asm.inc')['sha256'] and
        m['runtime_kernel_sha256'] == {'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS},
        'Signal control imported runtime ABI changed')
    S.check(S.digest(m['assembler']['path']) == m['assembler']['digest'], 'Signal control assembler changed')
    coff = S.module('normal_signal_control_actual_coff', 'verify-batch-assembly.py')
    defined,undefined = coff.coff_symbols(obj,C.FOREIGN)
    S.check(defined == C.exports(meta['methods']) == set(m['exports']) and
        undefined == imports|services|base_imports == set(m['imports']), 'Signal control actual COFF differs')
    wanted = {row['method'] for row in meta['methods']}
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap',
                'vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing = {json.loads(line)['method'] for line in z.open('natives.jsonl' if key == 'frames' else 'methods.jsonl')}
        S.check(not wanted&existing, 'Signal control replaces an existing base native')
    return dict(schema=1,verified=True,scope='original_Signal_handle0_raise0_Java_callbacks_ASM_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],
        verifier_sha256=S.digest(Path(__file__))['sha256'],base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],
        source_native_methods=2,source_Java_upcalls=3,transport_config_abi=2,VM_BREAK_thread_dump=False,
        linked=False,executed=False,game_started=False,world_created=False)
