"""Reconstruct the original normal-String Windows Signal lookup provider."""
from pathlib import Path
import json
import zipfile


def verify(path, batch, plan, m, S, wrapper):
    identity, summary, classes = S.base(batch, plan)
    S.check(m['base'] == identity and m['tool_sources'] == S.tools_identity(), 'Signal lookup base/tool identity differs')
    S.check((m['context_bytes'], m['pool_bytes'], m['pool_abi']) == (32, 32, 1), 'Signal lookup ABI differs')
    S.check(m['assembled'] and m['leaf_guest_services'] and not any(m[k] for k in
            ('java_codegen_rerun', 'base_Java_ASM_and_COFF_modified', 'all_family_natives_implemented', 'linked', 'executed', 'game_started', 'world_created')),
            'Signal lookup source/execution scope differs')
    C = S.module('independent_normal_signal_lookup', 'signal-lookup-source.py')
    metadata = C.index(summary, classes, S)
    methods = [metadata['lookup']]
    owner = classes[methods[0]['class_id']]
    names = {(c['origin']['loader'], c['name']): c['id'] for c in classes}
    S.check(m['methods'] == methods and m['native_methods'] == 1 and m['owner_source'] == owner and m['owner_sources'] == [owner],
            'Signal lookup original native inventory differs')
    record = S.checked(m['signal_lookup_metadata'])
    S.check(record.parent == path.parent and S.read(record) == metadata, 'Signal lookup original metadata differs')
    services = {'boom_heap_contains', 'boom_object_check'}
    data_imports = {'boom_heap_ptr', 'boom_java_string_literal_pool'}
    expected = 'option casemap:none\nEXTERN boom_class_ensure32:PROC\n' + f"EXTERN boom_class{owner['id']}:BYTE\n"
    expected += ''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(services | data_imports))
    expected += C.data() + wrapper(methods[0], 'boom_provider_signal_lookup_pool', 'boom_provider_signal_lookup_service')
    kernel = S.ROOT/'native/providers/signal_lookup.asm.inc'
    expected += kernel.read_text(encoding='utf-8') + '\nEND\n'
    S.check(m['policy'] == dict(normal_source_layouts=True, platform='Windows', case_sensitive=True, unknown_signal=-1,
            handler_installation=False, signal_raise=False, Java_signal_dispatch=False), 'Signal lookup partial service policy differs')
    S.check(m['required_class_ids'] == sorted([owner['id'], names['bootstrap', 'java/lang/String']]) and m['required_base_modules'] == ['class_literals'],
            'Signal lookup source dependencies differ')
    S.check(m['pool_symbol'] == 'boom_provider_signal_lookup_pool' and m['service_symbol'] == 'boom_provider_signal_lookup_service',
            'Signal lookup source symbols differ')
    S.check(m['kernel_sha256'] == S.digest(kernel)['sha256'] and m['runtime_kernel_sha256'] ==
            {'native/runtime/' + n: S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS}, 'Signal lookup imported runtime changed')
    asm, obj = S.checked(m['assembly']), S.checked(m['object'])
    S.check(asm.parent == path.parent and obj.parent == path.parent and asm.read_text(encoding='utf-8') == expected,
            'Signal lookup generated ASM differs')
    S.check(S.digest(m['assembler']['path']) == m['assembler']['digest'], 'Signal lookup assembler changed')
    exports = {m['pool_symbol'], m['service_symbol']} | {f"boom_m{methods[0]['method']}{suffix}" for suffix in ('', '_native')}
    imports = {'boom_class_ensure32', f"boom_class{owner['id']}"} | services | data_imports
    coff = S.module('normal_signal_lookup_actual_coff', 'verify-batch-assembly.py')
    defined, undefined = coff.coff_symbols(obj)
    S.check(defined == exports == set(m['exports']) and undefined == imports == set(m['imports']), 'Signal lookup actual COFF differs')
    for key in ('system_natives', 'class_literals', 'string_intern', 'properties', 'class_bootstrap', 'unsafe_bootstrap',
                'vm_registration', 'runtime_resources', 'bitcasts', 'unsafe_fields', 'unsafe_memory', 'class_lookup', 'frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as archive:
            existing = {json.loads(line)['method'] for line in archive.read('natives.jsonl' if key == 'frames' else 'methods.jsonl').splitlines()}
        S.check(methods[0]['method'] not in existing, 'Signal lookup replaces an existing base native')
    return dict(schema=1, verified=True, scope='original_Signal_findSignal0_normal_String_ASM_and_actual_COFF_only',
        provider_manifest=str(path), provider_manifest_sha256=S.digest(path)['sha256'], verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'], native_methods=1, context_bytes=32, pool_abi=1,
        handler_installation=False, signal_raise=False, Java_signal_dispatch=False,
        java_codegen_rerun=False, base_Java_ASM_and_COFF_modified=False, source_initializer_executed=False,
        runtime_linkage_closure_verified=False, linked=False, executed=False, game_started=False, world_created=False)
