"""Verify source-derived VM entry bindings, actual COFF and native PE imports."""
import argparse
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('verify_native_vm_entry_model', Path(__file__).with_name('vm-entry-source.py'))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
S = M.S


def verify(directory):
    directory = Path(directory).resolve()
    S.check(directory.is_relative_to(S.ART/'vm-entry-images'), 'Native entry evidence must stay in isolated project output')
    manifest = S.read(directory/'vm-entry.json')
    S.check(manifest['scope'] == 'native_assembly_process_original_VM_bootstrap_prefix_only' and
            not any(manifest[k] for k in ('VM_binding_configuration_fixture', 'managed_execution_host', 'jvm_fallback',
                'full_VM_bootstrap', 'game_started', 'world_created', 'source_Java_codegen_rerun', 'original_Java_assembly_changed')),
            'Native entry scope differs')
    for record in manifest['inputs']:
        S.check(S.artifact(record['path']) == record, 'Native entry input changed: '+record['path'])
    closure, proof, old = M.accepted(manifest['baseline_directory'], manifest['accepted_source_verification_sha256'])
    model = M.binding_model(closure, manifest['include_System_phase1'], manifest['construct_child'],
                            manifest.get('start_child', False), manifest.get('child_task_main_thread', False), manifest.get('signal_control', False), manifest.get('system_phase2',False))
    S.check(model == manifest['binding_model'] and M.source_objects(closure) == manifest['original_source_objects'],
            'Native entry binding or original source object identity differs')
    expected, imports = M.assembly(model)
    S.check(S.checked(manifest['assembly']).read_text(encoding='utf-8') == expected, 'Native binding/process MASM differs')
    coff = M.module('native_vm_entry_coff_check', 'verify-batch-assembly.py')
    objects = {Path(r['path']).stem: S.checked(r) for r in manifest['reassembled_objects']}
    reused=manifest.get('reused_closure_objects',[])
    if reused:
        provenance=M.module('verified_native_entry_object_provenance','diagnostic-objects.py')
        sealed=provenance.verify(manifest['baseline_directory'])
        S.check(sealed==proof.get('verified_assembly_objects') and sealed['assembler']==manifest['tools']['assembler'] and
                reused==[unit['object'] for unit in sealed['units']] and all(r in manifest['inputs'] for r in reused) and
                not manifest['selected_original_Java_reassembled'], 'Native entry reused unverified closure objects')
    S.check(set(objects) == ({'vm-entry'} if reused else {'initialization-closure','diagnostic-stops','vm-entry'}),
            'Native entry contains extra/missing objects')
    assembly_inputs=[r['path'] for r in reused+manifest['reassembled_objects']+manifest['original_source_objects']]
    rsp=S.checked(manifest['link_response']).read_text(encoding='utf-8').splitlines()
    S.check([line[1:-1] for line in rsp if line.startswith('"') and line.lower().endswith('.obj"')]==assembly_inputs,
            'Native entry link used a different COFF set')
    defined, undefined = coff.coff_symbols(objects['vm-entry'], allowed_foreign=M.FOREIGN | ({'Sleep','GetTickCount64'} if model['child_start'] or model.get('signal_reference') else set()))
    S.check(defined == M.EXPORTS and undefined == imports, 'Native entry actual COFF definitions/imports differ')
    if not manifest.get('original_assembly_read_in_place'):
        for n in ('initialization-closure','diagnostic-stops'):
            S.check((directory/(n+'.asm')).read_bytes() == (Path(manifest['baseline_directory'])/(n+'.asm')).read_bytes(),
                    'Reassembled original Java or diagnostic source changed')
    image, runtime = S.checked(manifest['executable']), S.checked(manifest['runtime'])
    S.check(S.digest(runtime)['sha256'] == S.digest(old['runtime'])['sha256'], 'Native runtime copy differs')
    parsed = M.pe(image)
    S.check(not parsed['dll'] and parsed['entry_rva'] != 0 and parsed['subsystem'] == 3, 'Native process entry is not a console EXE')
    modules = set(parsed['imports'])
    S.check('boom-runtime.dll' in modules and all(n in {'boom-runtime.dll', 'kernel32.dll'} or
            n.startswith('api-ms-win-') for n in modules), 'Native entry unexpectedly imports a managed/foreign runtime')
    S.check(M.FOREIGN <= set(parsed['imports'].get('kernel32.dll', [])), 'Native process owner Windows imports missing')
    S.check((manifest.get('execution_report_bytes',112),manifest.get('execution_report_abi',2)) ==
            M.report_layout(model), 'Native thread execution report ABI differs')
    runtime_modules = set(M.pe(runtime)['imports'])
    system_modules = {'kernel32.dll','kernelbase.dll','ntdll.dll','user32.dll','ws2_32.dll',
                      'bcrypt.dll','advapi32.dll','shell32.dll','ole32.dll'}
    S.check(all(n in system_modules or n.startswith('api-ms-win-') for n in runtime_modules),
            'Assembly runtime unexpectedly imports a managed/foreign runtime')
    exports = M.module('native_vm_entry_exports_check', 'diagnostic-closure.py').pe_exports(image)
    S.check(exports == set(closure['exports']) | M.EXPORTS, 'Native executable exports differ from selected source and VM entry')
    return dict(verified=True, scope='source_bound_native_VM_process_prefix_only',
        original_Java_methods=proof['Java_methods'], original_Java_source_unchanged=True,
        compiler_generated_VM_binding_pool=True, assembly_process_entry=True,
        managed_execution_host=False, VM_binding_configuration_fixture=False, jvm_fallback=False,
        native_import_modules=sorted(modules),runtime_import_modules=sorted(runtime_modules), executable_sha256=S.digest(image)['sha256'],
        source_manifest_sha256=S.digest(directory/'vm-entry.json')['sha256'],
        linked=True, execution_verified=False, full_VM_bootstrap=False, game_started=False, world_created=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    result = verify(a.directory)
    if a.output:
        S.write(a.output, result)
    print(__import__('json').dumps(result))
