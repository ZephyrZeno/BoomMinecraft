"""Link an assembly-owned native VM prefix from accepted original Java ASM."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess

spec = importlib.util.spec_from_file_location('native_vm_entry_model', Path(__file__).with_name('vm-entry-source.py'))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
S = M.S


def build(directory, accepted_sha, output, assembler, linker, synchronization, kernel32, include_system, construct_child=False, start_child=False, child_task_main_thread=False, signal_control=False, system_phase2=False, parallel_assembly=False, system_phase3=False, server_help=False):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    S.check(output.is_relative_to(S.ART/'vm-entry-images') and not output.exists(), 'Use a fresh native entry output directory')
    closure, proof, old = M.accepted(directory, accepted_sha)
    selected_families={S.read(S.checked(closure['runtime_provider_packs'][i]['manifest']))['family']
        for i in closure.get('selected_runtime_provider_packs',[])}
    winsock='normal-native-libraries-v1' in selected_families
    model = M.binding_model(closure, include_system, construct_child, start_child, child_task_main_thread, signal_control, system_phase2, system_phase3, server_help)
    original_objects = M.source_objects(closure)
    runtime = Path(old['runtime']).resolve()
    runtime_metadata = S.read(runtime.with_name('runtime.json'))
    S.check(S.digest(runtime)['sha256'] == runtime_metadata['sha256'] and
            all(runtime_metadata[k] is False for k in ('java_runtime', 'rust_runtime', 'c_runtime')),
            'Native VM entry needs the source-built assembly runtime')
    for p, h in runtime_metadata['sources'].items():
        S.check(S.digest(S.ROOT/p)['sha256'] == h, 'Assembly runtime source changed: '+p)
    runtime_lib = runtime.with_suffix('.lib')
    inputs = original_objects + [S.artifact(directory/n) for n in
        ('closure.json', 'diagnostic.json', 'selection-verification.json', 'vm-thread-bootstrap.json',
         'initialization-closure.asm', 'diagnostic-stops.asm')]
    if (directory/'execution.json').exists():
        inputs.append(S.artifact(directory/'execution.json'))
    inputs += [S.artifact(p) for p in (runtime, runtime_lib, runtime.with_name('runtime.json'),
        assembler, linker, synchronization, kernel32, Path(__file__), M.ROOT/'scripts/vm-entry-source.py',
        M.ROOT/'scripts/runtime-provider-source.py', M.ROOT/'scripts/provider-tool-manifest.py',
        M.ROOT/'scripts/run-vm-entry.py', M.ROOT/'scripts/decode-vm-entry-report.py',
        M.ROOT/'scripts/verify-vm-entry.py', M.ROOT/'scripts/canonical-link-response.py', M.ROOT/'native/entry/vm_process.asm.inc')]
    winsock_libraries=[]
    if winsock:
        winsock_libraries=[S.artifact(Path(kernel32).with_name('ws2_32.lib'))]
        inputs.extend(winsock_libraries)
    if model['lifecycle_reference']:
        inputs += [model['lifecycle_reference']['manifest'],model['lifecycle_reference']['metadata']]
    if model.get('signal_reference'):
        inputs += [model['signal_reference']['manifest'],model['signal_reference']['metadata']]
    if model.get('reference_processing'):
        inputs += [model['reference_processing']['manifest'],model['reference_processing']['metadata']]
    if model.get('object_wait'):
        inputs += [model['object_wait']['manifest'],model['object_wait']['metadata']]
    if model.get('winnt_filesystem'):
        inputs += [model['winnt_filesystem']['manifest'],model['winnt_filesystem']['metadata']]
    if model.get('provider_native_root_spans'):
        inputs += [S.artifact(M.ROOT/'scripts/provider-native-roots.py'),S.artifact(M.ROOT/'native/kernels/provider_native_root_snapshot.asm.inc')]
        for key in ('unsafe_park','file_input'):
            if model.get(key):inputs += [model[key]['manifest'],model[key]['metadata']]
    if system_phase2:
        inputs += [S.artifact(M.ROOT/p) for p in ('scripts/vm-system-phase2.py','native/entry/system_phase2.asm.inc')]
    if system_phase3:
        inputs += [S.artifact(M.ROOT/p) for p in ('scripts/vm-system-phase3.py','native/entry/system_phase3.asm.inc')]
    if server_help:
        inputs += [S.artifact(M.ROOT/p) for p in ('scripts/vm-game-entry.py','native/entry/game_main.asm.inc')]
        inputs.append(M.native_input_artifact(model['game_entry']['source_archive']))
    output.mkdir(parents=True)
    source, imports = M.assembly(model)
    (output/'vm-entry.asm').write_text(source, encoding='utf-8')
    tools = dict(assembler=S.artifact(assembler), linker=S.artifact(linker))
    provenance=M.module('native_entry_object_provenance','diagnostic-objects.py')
    inputs.append(S.artifact(Path(provenance.__file__)))
    reused=[]
    sealed=proof.get('verified_assembly_objects')
    if parallel_assembly:
        S.check(sealed and sealed.get('schema')==2,'Build the accepted source selection with -ParallelAssembly first')
    if sealed and sealed['assembler']==tools['assembler']:
        try:eligible=provenance.verify(directory)==sealed
        except (OSError,ValueError,KeyError,TypeError):eligible=False
        if eligible:
            reused=[unit['object'] for unit in sealed['units']]
            inputs.extend([S.artifact(directory/provenance.RECEIPT),*reused])
            if sealed.get('schema')==2:
                inputs.extend(unit['assembly'] for unit in sealed['units'])
                receipt=S.read(directory/provenance.RECEIPT)
                inputs.extend(unit['parallel_receipt'] for unit in receipt['units'] if 'parallel_receipt' in unit)
    if sealed and sealed.get('schema')==2:
        S.check(bool(reused),'Parallel source provenance changed; implicit monolithic recompilation is forbidden')
    objects = []
    for name in (('vm-entry',) if reused else (*provenance.UNITS,'vm-entry')):
        obj = output/(name+'.obj')
        asm=(output if name=='vm-entry' else directory)/(name+'.asm')
        with (output/(name+'-assembler.log')).open('wb') as log:
            r = subprocess.run([str(assembler), '/nologo', '/c', '/Fo'+str(obj), str(asm)], stdout=log, stderr=subprocess.STDOUT)
        S.check(r.returncode == 0, 'Native entry assembly failed: '+name)
        objects.append(S.artifact(obj))
    target = output/'boom-vm-entry.exe'
    rsp = ['/NOLOGO', '/MACHINE:X64', '/SUBSYSTEM:CONSOLE', '/ENTRY:boom_process_entry', '/NODEFAULTLIB',
           '/DYNAMICBASE', '/NXCOMPAT', '/HIGHENTROPYVA', '/BREPRO', '/STACK:8388608', '/OUT:"'+str(target)+'"']
    link_objects = [r['path'] for r in reused+objects+original_objects]
    rsp += ['"'+p+'"' for p in link_objects+[str(runtime_lib), str(synchronization), str(kernel32)]+[r['path'] for r in winsock_libraries]]
    rsp += ['/EXPORT:'+s for s in sorted(set(closure['exports']) | M.entry_exports(model))]
    (output/'link.rsp').write_text('\n'.join(rsp)+'\n', encoding='utf-8')
    with (output/'link.log').open('wb') as log:
        r = subprocess.run([str(linker), '@'+str(output/'link.rsp')], stdout=log, stderr=subprocess.STDOUT)
    S.check(r.returncode == 0, 'Native VM entry link failed; inspect link.log')
    shutil.copyfile(runtime, output/'boom-runtime.dll')
    for record in inputs:
        S.check(S.artifact(record['path']) == record, 'Native VM link input changed: '+record['path'])
    data = dict(schema=1, scope='native_assembly_process_original_VM_bootstrap_prefix_only',
        baseline_directory=str(directory), accepted_source_verification_sha256=accepted_sha,
        include_System_phase1=include_system, construct_child=construct_child, start_child=start_child,
        child_task_main_thread=child_task_main_thread,
        signal_control=signal_control,
        system_phase2=system_phase2, system_phase3=system_phase3, server_help=server_help, execution_report_bytes=M.report_layout(model)[0],
        execution_report_abi=M.report_layout(model)[1],
        binding_model=model, original_source_objects=original_objects,
        inputs=inputs, tools=tools, reassembled_objects=objects, reused_closure_objects=reused, original_assembly_read_in_place=True,
        assembly=S.artifact(output/'vm-entry.asm'), executable=S.artifact(target),
        runtime=S.artifact(output/'boom-runtime.dll'), link_response=S.artifact(output/'link.rsp'),
        source_Java_codegen_rerun=False, original_Java_assembly_changed=False, selected_original_Java_reassembled=not bool(reused),
        VM_binding_configuration_fixture=False, managed_execution_host=False, jvm_fallback=False,
        linked=True, executed=False, full_VM_bootstrap=False, game_started=False, world_created=False)
    if sealed and sealed.get('schema')==2:data['source_assembly_mode']='parallel_source_groups'
    if winsock:data['supplemental_system_import_libraries']=winsock_libraries
    S.write(output/'vm-entry.json', data)
    print(target)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('directory', 'output', 'assembler', 'linker', 'synchronization', 'kernel32'):
        p.add_argument('--'+n, type=Path, required=True)
    p.add_argument('--accepted-verification-sha256', required=True)
    p.add_argument('--constructor-only', action='store_true')
    p.add_argument('--construct-child', action='store_true')
    p.add_argument('--start-child', action='store_true')
    p.add_argument('--child-task-main-thread', action='store_true')
    p.add_argument('--signal-control', action='store_true')
    p.add_argument('--system-phase2', action='store_true')
    p.add_argument('--system-phase3', action='store_true')
    p.add_argument('--server-help', action='store_true')
    p.add_argument('--parallel-assembly',action='store_true')
    a = p.parse_args()
    build(a.directory, a.accepted_verification_sha256, a.output, a.assembler, a.linker, a.synchronization, a.kernel32, not a.constructor_only, a.construct_child, a.start_child, a.child_task_main_thread, a.signal_control or a.system_phase2 or a.system_phase3 or a.server_help, a.system_phase2 or a.system_phase3 or a.server_help,a.parallel_assembly,a.system_phase3 or a.server_help,a.server_help)
