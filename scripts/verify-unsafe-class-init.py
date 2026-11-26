"""Verify the locked Unsafe class source, native frames, generated adapter and actual COFF."""
import json
from pathlib import Path
import zipfile


def verify(path, batch, plan, m, S):
    identity, summary, classes = S.base(batch, plan)
    C = S.module('verified_unsafe_class_init', 'unsafe-class-init-source.py')
    meta = C.index(summary, classes, S)
    owner = classes[meta['owner']]
    methods = meta['methods']
    S.check(m['base'] == identity and m['tool_sources'] == S.tools_identity() and m['methods'] == methods and
            m['native_methods'] == len(methods) and m['owner_sources'] == [owner] and m['owner_source'] == owner,
            'Unsafe original source/identity differs')
    S.check((m['context_bytes'], m['pool_bytes'], m['pool_abi']) == (32, 48, 1) and
            (m['pool_symbol'], m['service_symbol']) == (C.POOL, C.SERVICE) and m['policy'] == C.POLICY and
            m['required_class_ids'] == [owner['id']] and m['required_base_modules'] == C.MODULES,
            'Unsafe class initialization ABI/dependencies differ')
    S.check(m['assembled'] and m['native_entries_traced'] and m['native_java_upcalls'] and not any(m[k] for k in
            ('leaf_guest_services', 'all_native_frames', 'java_codegen_rerun', 'base_Java_ASM_and_COFF_modified',
             'all_family_natives_implemented', 'linked', 'executed', 'game_started', 'world_created')),
            'Unsafe class initialization evidence scope differs')
    record = S.checked(m['unsafe_class_init_metadata'])
    S.check(record.parent == path.parent and S.read(record) == meta, 'Unsafe class initialization metadata changed')
    reference = C.source_frame(batch, plan, S.checked(m['frame_overlay']['manifest']), meta, S)
    S.check(reference == m['frame_overlay'], 'Unsafe frame reference differs')
    procs, data = C.native_imports(meta)
    imports = {f"boom_class{owner['id']}", 'boom_class_ensure32'} | procs | data
    expected = 'option casemap:none\nEXTERN boom_class_ensure32:PROC\n' + f"EXTERN boom_class{owner['id']}:BYTE\n"
    expected += ''.join(f"EXTERN {n}:{'PROC' if n in procs else 'BYTE'}\n" for n in sorted(procs | data))
    expected += C.data(meta)
    R = S.module('unsafe_class_init_frame_adapter', 'verify-batch-frames.py')
    exports = {C.POOL, C.SERVICE}
    for row in methods:
        i = row['method']
        exports.update((f'boom_m{i}', f'boom_m{i}_native'))
        expected += f'.code\nPUBLIC boom_m{i}\nPUBLIC boom_m{i}_native\n'
        expected += R.native_adapter(i, owner['id'], C.POOL, C.SERVICE, row['operation']).removeprefix('.code\n')
    kernel = S.ROOT / 'native/providers/unsafe_class_initialization.asm.inc'
    expected += kernel.read_text(encoding='utf-8') + '\nEND\n'
    asm, obj = S.checked(m['assembly']), S.checked(m['object'])
    S.check(asm.parent == path.parent and obj.parent == path.parent and asm.read_text(encoding='utf-8') == expected and
            m['kernel_sha256'] == S.digest(kernel)['sha256'] and m['runtime_kernel_sha256'] ==
            {'native/runtime/' + n: S.digest(S.ROOT / 'native/runtime' / n)['sha256'] for n in C.KERNELS},
            'Unsafe class initialization MASM or runtime inputs changed')
    S.check(S.digest(m['assembler']['path']) == m['assembler']['digest'], 'Unsafe provider assembler changed')
    coff = S.module('unsafe_class_init_verified_coff', 'verify-batch-assembly.py')
    S.check(coff.coff_symbols(obj) == (exports, imports) and set(m['exports']) == exports and set(m['imports']) == imports,
            'Unsafe class initialization COFF symbols differ')
    ids = {r['method'] for r in methods}
    for key in ('system_natives', 'class_literals', 'string_intern', 'properties', 'class_bootstrap', 'unsafe_bootstrap',
                'vm_registration', 'runtime_resources', 'bitcasts', 'unsafe_fields', 'unsafe_memory', 'class_lookup', 'frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            rows = z.open('natives.jsonl' if key == 'frames' else 'methods.jsonl')
            S.check(all(json.loads(line)['method'] not in ids for line in rows), 'Unsafe replaces an existing base native')
    return dict(schema=1, verified=True, scope='original_Unsafe_class_initialization_source_ASM_COFF',
                provider_manifest=str(path), provider_manifest_sha256=S.digest(path)['sha256'],
                verifier_sha256=S.digest(Path(__file__))['sha256'], base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],
                source_native_methods=len(methods), linked=False, executed=False, game_started=False, world_created=False)
