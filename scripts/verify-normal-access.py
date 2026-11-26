"""Source layouts/frame views and actual COFF for normal access contexts."""
from pathlib import Path
import zipfile
import json


def verify(path, batch, plan, m, S, wrapper):
    identity, summary, classes = S.base(batch, plan)
    S.check(m['base'] == identity and m['tool_sources'] == S.tools_identity(), 'Normal access base/tool identity differs')
    S.check((m['context_bytes'], m['pool_bytes'], m['pool_abi']) == (32, 192, 2), 'Normal access pool/context ABI differs')
    S.check((m['pool_symbol'],m['service_symbol']) == ('boom_provider_access_pool','boom_provider_access_service') and
            m['all_native_frames'] is False, 'Normal access symbols/frame scope differ')
    S.check(m['assembled'] and not any(m[k] for k in ('leaf_guest_services', 'java_codegen_rerun',
        'base_Java_ASM_and_COFF_modified', 'all_family_natives_implemented', 'linked', 'executed', 'game_started', 'world_created')),
        'Normal access provider overclaims execution or source scope')
    C = S.module('normal_access_current_source', 'normal-access-source.py')
    F = S.module('normal_access_original_frame_metadata', 'native-frame-overlay.py')
    reference = m['frame_overlay']
    overlay_path = S.checked(reference['manifest'])
    proof = F.verify(overlay_path, batch, plan)
    S.check(S.read(S.checked(reference['verification'])) == proof, 'Normal access native frame provenance differs')
    metadata = C.index(summary, classes, S.read(overlay_path), S)
    record = S.checked(m['normal_access_metadata'])
    S.check(record.parent == path.parent and S.read(record) == metadata, 'Normal access source frame/layout/domain metadata differs')
    methods = metadata['methods'];owner = classes[metadata['access_class']]
    S.check(m['methods'] == methods and m['native_methods'] == 3 and m['owner_source'] == owner and
            m['owner_sources'] == [owner] and m['policy'] == C.POLICY, 'Normal AccessController original declarations/policy differ')
    S.check(m['required_class_ids'] == sorted([owner['id'], metadata['context_class'], metadata['thread_class'],
        metadata['domain_class'], next(c['id'] for c in classes if c['name'] == 'java/lang/Class' and c['origin']['loader'] == 'bootstrap')]) and
        m['required_base_modules'] == ['class_literals'] and m['required_provider_families'] == ['normal-thread-primitives-v1'],
        'Normal access source initialization/dependency scope differs')
    data, imports = C.data(metadata);kernel, services = C.kernel()
    base_imports = {'boom_class_ensure32', f"boom_class{owner['id']}"}
    extra = (imports | services)-base_imports
    expected = 'option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+f"EXTERN boom_class{owner['id']}:BYTE\n"
    expected += ''.join(f"EXTERN {s}:{'PROC' if s in services else 'BYTE'}\n" for s in sorted(extra))
    expected += data+''.join(wrapper(r, 'boom_provider_access_pool', 'boom_provider_access_service') for r in methods)+kernel+'\nEND\n'
    asm, obj = S.checked(m['assembly']), S.checked(m['object'])
    S.check(asm.parent == path.parent and obj.parent == path.parent and asm.read_text(encoding='utf-8') == expected,
            'Normal access generated ASM differs from source contracts')
    S.check(m['kernel_sha256'] == S.digest(S.ROOT/'native/providers/normal_access.asm.inc')['sha256'] and
            m['runtime_kernel_sha256'] == {'native/runtime/'+p: S.digest(S.ROOT/'native/runtime'/p)['sha256'] for p in C.KERNELS},
            'Normal access imported runtime/source kernel changed')
    S.check(S.digest(m['assembler']['path']) == m['assembler']['digest'], 'Normal access assembler changed')
    exports = {'boom_provider_access_pool', 'boom_provider_access_service', 'boom_provider_access_bind_domain',
        'boom_provider_access_domain_roots', 'boom_provider_access_domain_root_count', 'boom_provider_access_domain_bound'} | {
        f"boom_m{r['method']}{suffix}" for r in methods for suffix in ('', '_native')}
    imports |= services | base_imports
    coff = S.module('normal_access_actual_coff', 'verify-batch-assembly.py')
    defined, undefined = coff.coff_symbols(obj)
    S.check(defined == exports == set(m['exports']) and undefined == imports == set(m['imports']),
            'Normal access actual COFF definitions/imports differ')
    wanted = {r['method'] for r in methods}
    for key in ('system_natives', 'class_literals', 'string_intern', 'properties', 'class_bootstrap', 'unsafe_bootstrap',
                'vm_registration', 'runtime_resources', 'bitcasts', 'unsafe_fields', 'unsafe_memory', 'class_lookup', 'frames'):
        with zipfile.ZipFile(summary[key]['index']['path']) as z:
            existing = {json.loads(line)['method'] for line in z.open('natives.jsonl' if key == 'frames' else 'methods.jsonl')}
        S.check(not wanted & existing, 'Normal access provider overrides an existing base native')
    return dict(schema=1, verified=True, scope='normal_AccessController_source_layout_frame_domain_ASM_COFF_only',
        provider_manifest=str(path), provider_manifest_sha256=S.digest(path)['sha256'],
        verifier_sha256=S.digest(Path(__file__))['sha256'], base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],
        source_native_methods=3, source_frame_rows=len(metadata['frame_rows']), source_type_capacity=metadata['type_capacity'],
        application_domains_require_explicit_binding=True, linked=False, executed=False, game_started=False, world_created=False)
