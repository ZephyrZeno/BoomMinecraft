"""Reconstruct original Thread lifecycle bindings, ASM and actual COFF."""
from pathlib import Path
import zipfile
import json


def verify(path, batch, plan, m, S, wrapper):
    identity, summary, classes = S.base(batch, plan)
    S.check(m['base'] == identity and m['tool_sources'] == S.tools_identity(), 'Thread start base/tool identity differs')
    S.check((m['context_bytes'], m['pool_bytes'], m['pool_abi']) == (32, 256, 1), 'Thread start pool/Context ABI differs')
    S.check(m['assembled'] and m['all_native_frames'] is False and not any(m[k] for k in
        ('leaf_guest_services', 'java_codegen_rerun', 'base_Java_ASM_and_COFF_modified',
         'all_family_natives_implemented', 'linked', 'executed', 'game_started', 'world_created')),
        'Thread start provider overclaims execution or complete Thread support')
    C = S.module('normal_thread_start_independent_source', 'normal-thread-start-source.py')
    meta = C.index(summary, classes, S)
    record = S.checked(m['normal_thread_start_metadata'])
    S.check(record.parent == path.parent and S.read(record) == meta, 'Thread start source metadata differs')
    owner = classes[meta['thread_class']]
    S.check(m['methods'] == meta['methods'] and m['native_methods'] == 1 and
            m['owner_source'] == owner and m['owner_sources'] == [owner] and m['policy'] == C.POLICY,
            'Thread start original declaration/policy differs')
    S.check(m['required_class_ids'] == sorted(meta[k] for k in
        ('thread_class', 'holder_class', 'virtual_class', 'throwable_class', 'runnable_class')) and
        m['required_base_modules'] == [] and m['required_provider_families'] == ['normal-thread-primitives-v1','normal-thread-priority-v1'],
        'Thread start normal source dependencies differ')
    S.check(m['required_java_methods'] == sorted(c['method'] for c in meta['upcalls'] if c['name'] != 'runWith') and
            m['required_source_contracts'] == [meta['run_contract']['label']],
            'Thread start source callback/dispatch requirements differ')
    S.check(m['allowed_foreign_imports'] == sorted(C.FOREIGN), 'Thread start OS import allowlist differs')
    S.check((m['pool_symbol'], m['service_symbol']) == ('boom_provider_threads_pool', 'boom_provider_threads_service'),
            'Thread start source binding symbols differ')
    data, imports = C.data(meta)
    kernel, services = C.kernel()
    base_imports = {'boom_class_ensure32', f"boom_class{owner['id']}"}
    extra = (imports | services)-base_imports
    expected = 'option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+f"EXTERN boom_class{owner['id']}:BYTE\n"
    expected += ''.join(f"EXTERN {s}:{'PROC' if s in services else 'BYTE'}\n" for s in sorted(extra))
    expected += data+''.join(wrapper(row, m['pool_symbol'], m['service_symbol']) for row in meta['methods'])+kernel+'\nEND\n'
    asm, obj = S.checked(m['assembly']), S.checked(m['object'])
    S.check(asm.parent == path.parent and obj.parent == path.parent and asm.read_text(encoding='utf-8') == expected,
            'Thread start generated ASM differs from original source contracts')
    S.check(m['kernel_sha256'] == S.digest(S.ROOT/'native/providers/normal_thread_start.asm.inc')['sha256'] and
            m['runtime_kernel_sha256'] == {'native/runtime/'+p: S.digest(S.ROOT/'native/runtime'/p)['sha256'] for p in C.KERNELS},
            'Thread start imported source/runtime kernel changed')
    S.check(S.digest(m['assembler']['path']) == m['assembler']['digest'], 'Thread start assembler changed')
    coff = S.module('thread_start_actual_coff', 'verify-batch-assembly.py')
    defined, undefined = coff.coff_symbols(obj, C.FOREIGN)
    S.check(defined == C.exports(meta['methods']) == set(m['exports']) and
            undefined == imports | services | base_imports == set(m['imports']), 'Thread start actual COFF differs')
    wanted = {row['method'] for row in meta['methods']}
    for key in ('system_natives', 'class_literals', 'string_intern', 'properties', 'class_bootstrap',
                'unsafe_bootstrap', 'vm_registration', 'runtime_resources', 'bitcasts',
                'unsafe_fields', 'unsafe_memory', 'class_lookup', 'frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as archive:
            existing = {json.loads(line)['method'] for line in archive.open('natives.jsonl' if key == 'frames' else 'methods.jsonl')}
        S.check(not wanted & existing, 'Thread start replaces an existing base native')
    return dict(schema=1, verified=True, scope='normal_Thread_start0_source_upcalls_field_maps_ASM_COFF_only',
        provider_manifest=str(path), provider_manifest_sha256=S.digest(path)['sha256'],
        verifier_sha256=S.digest(Path(__file__))['sha256'], base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],
        source_native_methods=1, source_Java_callbacks=3, source_virtual_dispatch_contracts=1,
        normal_field_maps=len(meta['fields']), Thread_start_executed=False, linked=False,
        executed=False, game_started=False, world_created=False)
