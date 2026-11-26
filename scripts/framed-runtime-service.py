"""Verify source-bound native frames and independently reconstruct small assembly service packs."""
from pathlib import Path
import json
import zipfile


FAMILIES = {
    'normal-file-input-readonly-v1': ('file-input-source.py','file_input','file_input_readonly.asm.inc'),
    'normal-unsafe-park-v1': ('unsafe-park-source.py','unsafe_park','unsafe_park.asm.inc'),
    'normal-module-definitions-v1': ('module-definitions-source.py','module_definitions','module_definitions_normal.asm.inc'),
    'normal-windows-canonical-v1': ('windows-canonical-source.py','windows_canonical','windows_canonical.asm.inc'),
    'normal-windows-file-queries-v1': ('windows-file-queries-source.py','windows_file_queries','windows_file_queries.asm.inc'),
    'normal-reference-referent-v1': ('reference-referent-source.py','reference_referent','reference_referent_get.asm.inc'),
    'normal-native-libraries-v1': ('native-library-source.py','native_library','native_library_lifecycle.asm.inc'),
    'normal-library-name-v1': ('library-name-source.py','library_name','library_name_normal.asm.inc'),
    'normal-class-loader-assertions-v1': ('class-loader-assertions-source.py','class_loader_assertions','class_loader_assertions.asm.inc'),
    'normal-boot-unnamed-module-v1': ('boot-unnamed-source.py','boot_unnamed','boot_unnamed_normal.asm.inc'),
    'normal-object-wait-v1': ('object-wait-source.py','object_wait','object_wait.asm.inc'),
    'normal-reference-processing-v1': ('reference-processing-source.py','reference_processing','reference_processing.asm.inc'),
    'normal-winnt-filesystem-v1': ('winnt-filesystem-source.py','winnt_filesystem','winnt_filesystem.asm.inc'),
}


def source_frame(batch, plan, frame, meta, S):
    S.check(frame is not None, 'Original source native frame overlay is required')
    frame = Path(frame).resolve()
    record = frame.with_name('verification.json')
    F = S.module('native_service_frame_contract','native-frame-overlay.py')
    S.check(F.verify(frame,batch,plan) == S.read(record), 'Source native frame proof differs')
    rows = {r['id']:r for r in S.read(frame)['source']['original_native_declarations']}
    for m in meta['methods']:
        r = rows.get(m['method'])
        S.check(r and r['flags'] & 32 and not r['flags'] & 128 and all(r[k] == m[k] for k in
                ('class_id','class_sha256','loader','source_id','name','descriptor','access')), 'Original native frame changed')
    return dict(manifest=S.artifact(frame),verification=S.artifact(record))


def verify(path, batch, plan, m, S):
    module, key, kernel = FAMILIES[m['family']]
    C = S.module('verify_'+key,module)
    identity, summary, classes = S.base(batch,plan)
    meta = C.index(summary,classes,S)
    owner, methods = classes[meta['owner']], meta['methods']
    owners = [classes[c] for c in sorted({m['class_id'] for m in methods})]
    S.check(m['base'] == identity and m['tool_sources'] == S.tools_identity() and m['native_methods'] == len(methods) and
            m['methods'] == methods and m['owner_source'] == owner and m['owner_sources'] == owners, 'Original native source differs')
    record = S.checked(m[key+'_metadata'])
    S.check(record.parent == path.parent and S.read(record) == meta and m['policy'] == C.POLICY and
            m['required_class_ids'] == meta['required_classes'] and m['required_base_modules'] == meta.get('required_base_modules',[]) and
            (m['context_bytes'],m['pool_bytes'],m['pool_abi']) == (32,meta['pool_bytes'],meta['pool_abi']) and
            (m['pool_symbol'],m['service_symbol']) == (C.POOL,C.SERVICE) and m['allowed_foreign_imports'] == sorted(C.FOREIGN),
            'Original native binding ABI/policy differs')
    S.check(m['assembled'] and m['native_entries_traced'] and not any(m[k] for k in ('all_native_frames','java_codegen_rerun',
            'base_Java_ASM_and_COFF_modified','all_family_natives_implemented','linked','executed','game_started','world_created')),
            'Native service evidence scope differs')
    S.check(m['leaf_guest_services'] is False and m['native_java_upcalls'] == (key in ('winnt_filesystem','object_wait','native_library','library_name','windows_canonical','windows_file_queries','module_definitions','file_input','unsafe_park')) and
            source_frame(batch,plan,S.checked(m['frame_overlay']['manifest']),meta,S) == m['frame_overlay'],
            'Original source frame configuration differs')
    roots=S.module('verified_physical_native_roots','provider-native-roots.py')
    physical_roots=roots.provider_projection(m,meta)
    proc, data = C.native_imports(meta)
    if key in ('object_wait','boot_unnamed','reference_referent','native_library','library_name','windows_canonical','windows_file_queries','module_definitions','file_input','unsafe_park'):
        S.check(m['required_java_methods']==meta.get('required_java_methods',[]) and
                m['required_provider_families']==meta.get('required_provider_families',[]),
                'Original required Java methods or service dependencies differ')
    declared = {f"boom_class{c['id']}" for c in owners} | {'boom_class_ensure32'}
    expected = 'option casemap:none\nEXTERN boom_class_ensure32:PROC\n' + ''.join(f"EXTERN boom_class{c['id']}:BYTE\n" for c in owners)
    expected += ''.join(f"EXTERN {n}:{'PROC' if n in proc else 'BYTE'}\n" for n in sorted(proc|data)) + C.data(meta)
    exports = C.CONTROL | {C.SERVICE}
    if C.POOL not in data:exports.add(C.POOL)
    R = S.module('verify_source_service_wrapper','verify-batch-frames.py')
    for row in methods:
        i = row['method']
        expected += f'.code\nPUBLIC boom_m{i}\nPUBLIC boom_m{i}_native\n'
        expected += R.native_adapter(i,row['class_id'],C.POOL,C.SERVICE,row['operation']).removeprefix('.code\n')
        exports.update((f'boom_m{i}',f'boom_m{i}_native'))
    kernel_path = S.ROOT/'native/providers'/kernel
    expected += kernel_path.read_text(encoding='utf-8') + '\nEND\n'
    asm,obj = S.checked(m['assembly']),S.checked(m['object'])
    S.check(asm.parent == path.parent and obj.parent == path.parent and asm.read_text(encoding='utf-8') == expected and
            S.digest(kernel_path)['sha256'] == m['kernel_sha256'] and
            m['runtime_kernel_sha256'] == {'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS} and
            S.digest(m['assembler']['path']) == m['assembler']['digest'], 'Generated assembly or runtime sources changed')
    coff = S.module('verify_native_service_coff','verify-batch-assembly.py')
    S.check(coff.coff_symbols(obj,C.FOREIGN) == (exports,proc|data|declared) and set(m['exports']) == exports and
            set(m['imports']) == proc|data|declared, 'Original native service COFF symbols differ')
    ids = {r['method'] for r in methods}
    for k in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap','vm_registration',
              'runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        with zipfile.ZipFile(summary[k]['index']['path']) as z:
            S.check(all(json.loads(l)['method'] not in ids for l in z.open('natives.jsonl' if k=='frames' else 'methods.jsonl')),
                    'Native service replaces a base provider')
    proof=dict(schema=1,verified=True,scope='original_'+key+'_source_frames_and_COFF',provider_manifest=str(path),
                provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
                base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],source_native_methods=len(methods),
                linked=False,executed=False,game_started=False,world_created=False)

    if physical_roots:proof['source_native_root_spans']=physical_roots
    return proof
