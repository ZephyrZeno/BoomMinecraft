"""Reconstruct the original Thread primitive provider and inspect its COFF."""
from pathlib import Path
import json
import zipfile


def verify(path, batch, plan, m, S, wrapper):
    identity, summary, classes = S.base(batch, plan)
    S.check(m['base'] == identity and m['tool_sources'] == S.tools_identity(), 'Normal Thread base/tool identity differs')
    S.check((m['context_bytes'], m['pool_bytes'], m['pool_abi']) == (32, 80, 1), 'Normal Thread native ABI differs')
    S.check(m['assembled'] and m['leaf_guest_services'] and not any(m[k] for k in
        ('java_codegen_rerun', 'base_Java_ASM_and_COFF_modified', 'all_family_natives_implemented', 'linked', 'executed', 'game_started', 'world_created')),
        'Normal Thread provider overclaims construction or lifecycle')
    C = S.module('independent_normal_thread_contracts', 'normal-thread-source.py')
    metadata = C.index(summary, classes, S)
    methods = metadata['methods']
    owner = classes[metadata['thread_class']]
    S.check(m['methods'] == methods and m['native_methods'] == 6 and m['owner_source'] == owner and m['owner_sources'] == [owner],
            'Original Thread primitive declarations differ')
    record = S.checked(m['normal_thread_metadata'])
    S.check(record.parent == path.parent and S.read(record) == metadata, 'Normal Thread source inventory or capabilities differ')
    data, imports = C.data(metadata)
    services = {'boom_thread_native_register', 'boom_thread_native_dispatch', 'boom_thread_native_bind'}
    extra = imports | services
    expected = 'option casemap:none\nEXTERN boom_class_ensure32:PROC\n' + f"EXTERN boom_class{owner['id']}:BYTE\n"
    expected += ''.join(f"EXTERN {n}:{'QWORD' if n.startswith('__imp_') else 'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))
    expected += data + ''.join(wrapper(r, 'boom_provider_thread_pool', 'boom_provider_thread_service') for r in methods)
    kernel = S.ROOT/'native/providers/normal_thread.asm.inc'
    expected += kernel.read_text(encoding='utf-8') + '\nEND\n'
    S.check(m['policy'] == dict(normal_source_layouts=True, original_native_inventory=20, registered_table_slots=18,
        executable_slots=5, canonical_target_addresses_from_IAT=True, platform_threads_only=True,
        Java_constructors=False, Java_thread_start=False, virtual_threads=False, VM_id_address_atomics=False), 'Normal Thread partial service policy differs')
    S.check(m['required_class_ids'] == sorted([metadata['thread_class'], metadata['virtual_base_class']]) and m['required_base_modules'] == [],
            'Normal Thread source dependencies differ')
    S.check(m['pool_symbol'] == 'boom_provider_thread_pool' and m['service_symbol'] == 'boom_provider_thread_service', 'Normal Thread symbols differ')
    S.check(m['kernel_sha256'] == S.digest(kernel)['sha256'] and m['runtime_kernel_sha256'] ==
        {'native/runtime/' + name: S.digest(S.ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS}, 'Normal Thread imported kernel changed')
    asm, obj = S.checked(m['assembly']), S.checked(m['object'])
    S.check(asm.parent == path.parent and obj.parent == path.parent and asm.read_text(encoding='utf-8') == expected, 'Normal Thread generated ASM differs')
    S.check(S.digest(m['assembler']['path']) == m['assembler']['digest'], 'Normal Thread assembler changed')
    exports = {'boom_provider_thread_pool', 'boom_provider_thread_service', 'boom_provider_thread_bind', 'boom_provider_thread_registry'} | {
        f"boom_m{r['method']}{suffix}" for r in methods for suffix in ('', '_native')}
    imports |= services | {'boom_class_ensure32', f"boom_class{owner['id']}"}
    coff = S.module('normal_thread_actual_coff', 'verify-batch-assembly.py')
    defined, undefined = coff.coff_symbols(obj)
    S.check(defined == exports == set(m['exports']) and undefined == imports == set(m['imports']), 'Normal Thread actual COFF differs')
    wanted = {r['method'] for r in methods}
    for key in ('system_natives', 'class_literals', 'string_intern', 'properties', 'class_bootstrap', 'unsafe_bootstrap',
                'vm_registration', 'runtime_resources', 'bitcasts', 'unsafe_fields', 'unsafe_memory', 'class_lookup', 'frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as archive:
            existing = {json.loads(line)['method'] for line in archive.read('natives.jsonl' if key == 'frames' else 'methods.jsonl').splitlines()}
        S.check(not wanted & existing, 'Normal Thread replaces an existing base native')
    return dict(schema=1, verified=True, scope='original_Thread_registration_and_five_platform_primitives_ASM_and_COFF_only',
        provider_manifest=str(path), provider_manifest_sha256=S.digest(path)['sha256'], verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'], native_methods=6,
        original_native_declarations=20, registered_table_slots=18, executable_slots=5, canonical_target_addresses_from_IAT=True,
        Java_constructors_executed=False, Java_thread_start=False, virtual_threads=False, VM_id_address_atomics=False,
        java_codegen_rerun=False, base_Java_ASM_and_COFF_modified=False, linked=False, executed=False, game_started=False, world_created=False)
