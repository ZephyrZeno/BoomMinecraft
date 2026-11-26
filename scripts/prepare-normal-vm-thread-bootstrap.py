"""Select untouched original constructors for the assembly VM owner-thread boot."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S = module('vm_thread_io', 'runtime-provider-source.py')
R = module('vm_thread_original', 'verify-batch-frames.py')
CONSTRUCTORS = (
    ('java/lang/ThreadGroup', '()V'),
    ('java/lang/ThreadGroup', '(Ljava/lang/ThreadGroup;Ljava/lang/String;IZ)V'),
    ('java/security/AccessControlContext', '([Ljava/security/ProtectionDomain;Z)V'),
    ('java/lang/Thread', '(Ljava/lang/ThreadGroup;Ljava/lang/String;ILjava/lang/Runnable;JLjava/security/AccessControlContext;)V'))
CLASS_NAMES = ('java/lang/Thread', 'java/lang/ThreadGroup', 'java/security/AccessControlContext',
               'java/lang/Thread$FieldHolder', 'jdk/internal/misc/VM', 'java/lang/String')


def append_source_roots(existing,additional,width):
    """Keep the VM prerequisites first; extra roots are source requests only."""
    result=list(existing)
    for row in additional:
        S.check(isinstance(row,(tuple,list)) and len(row)==width and
                all(isinstance(value,str) and value for value in row),'Invalid additional source root')
        row=tuple(row)
        if row not in result:result.append(row)
    return result


def prepare(batch, plan, runtime, output, profile, provider_paths, continue_system=False, construct_child=False, start_child=False, child_task_main_thread=False, system_phase2=False, system_phase3=False, server_help=False,
            *,extra_class_roots=(),extra_method_roots=()):
    S.check(not server_help or system_phase3,'Original server Main needs the complete original System initialization')
    S.check(not system_phase3 or system_phase2, 'Original phase 3 requires original module bootstrap')
    S.check(not system_phase2 or continue_system, 'Module bootstrap needs System phase 1')
    S.check(not start_child or construct_child, 'Starting a child requires original child construction')
    S.check(not child_task_main_thread or start_child, 'Runnable task verification requires a started child')
    batch, plan, runtime, output = map(lambda p: Path(p).resolve(), (batch, plan, runtime, output))
    S.check(output.is_relative_to(S.ART) and not output.exists(), 'Use a fresh VM bootstrap selection')
    summary = S.read(batch/'summary.json')
    classes = [json.loads(line) for line in (plan/'classes.jsonl').open(encoding='utf-8')]
    names = {c['name']: c for c in classes if c['origin']['loader'] == 'bootstrap'}
    owners = {name: names[name] for name in CLASS_NAMES}
    layouts = {}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['class_id'] in {c['id'] for c in owners.values()}:
                S.check(row['diagnostic'] is None and row['candidate'] is not None and
                        row['source_sha256'] == classes[row['class_id']]['origin']['sha256'], 'VM bootstrap layout/source differs')
                layouts[row['name']] = row['candidate']
    selected = []
    for name, descriptor in CONSTRUCTORS:
        owner = owners[name]
        raw_name, raw_methods = R.original_methods(S.original_class(summary, owner))
        matches = [(i, m) for i, m in zip(owner['method_ids'], raw_methods)
                   if (m['name'], m['descriptor']) == ('<init>', descriptor)]
        S.check(raw_name == name and len(matches) == 1 and matches[0][1]['code'] is not None,
                'VM bootstrap original constructor unavailable')
        i, method = matches[0]
        selected.append(dict(owner=name, descriptor=descriptor, method=i, symbol=f'boom_m{i}',
            class_id=owner['id'], class_sha256=owner['origin']['sha256'], code_sha256=hashlib.sha256(method['code'][0]).hexdigest()))
    vm = owners['jdk/internal/misc/VM']
    level = [i for i, f in enumerate(vm['fields']) if (f['name'], f['descriptor']) == ('initLevel', 'I') and f['access'] & 8]
    S.check(len(level) == 1, 'Original VM.initLevel field differs')
    literal = None
    with zipfile.ZipFile(S.checked(summary['string_literals']['index'])) as archive:
        for line in archive.open('canonical.jsonl'):
            row = json.loads(line)
            if row['utf16'] == list(map(ord, 'main')):
                S.check(literal is None, 'Canonical main name is ambiguous')
                literal = row['id']
    S.check(literal is not None, 'Canonical original main name missing')
    provider_module = module('vm_thread_provider_load', 'verify-runtime-provider-pack.py')
    packs = provider_module.load_packs(batch, plan, provider_paths)
    S.check(sum(p['manifest']['family'] == 'normal-thread-primitives-v1' for p in packs) == 1, 'Normal Thread primitive provider required')
    source = module('vm_thread_source_select', 'prepare-class-init-probe.py')
    model = module('vm_thread_global_model', 'diagnostic-closure.py')
    coff = module('vm_thread_coff', 'verify-batch-assembly.py')
    known, providers, identity = model.globals_index(batch, summary, runtime, coff, packs)
    p = S.read(profile)
    S.check(p['source_batch_summary_sha256'] == S.digest(batch/'summary.json')['sha256'], 'VM bootstrap Java profile source differs')
    class_roots = [('bootstrap', n) for n in ('java/lang/String', 'java/lang/System', 'java/lang/Class',
        'java/lang/reflect/Method', 'java/lang/Thread', 'java/lang/ThreadGroup', 'java/security/AccessControlContext', 'jdk/internal/misc/VM')]
    entries = [('bootstrap', n, '<init>', d) for n, d in CONSTRUCTORS]
    if construct_child:
        descriptor = ('(Ljava/lang/ThreadGroup;Ljava/lang/Runnable;Ljava/lang/String;)V'
                      if child_task_main_thread else '(Ljava/lang/ThreadGroup;Ljava/lang/String;)V')
        entries.append(('bootstrap', 'java/lang/Thread', '<init>', descriptor))
    if start_child:
        entries.append(('bootstrap', 'java/lang/Thread', 'start', '()V'))
    if continue_system:
        entries.append(('bootstrap', 'java/lang/System', 'initPhase1', '()V'))
    if system_phase2:
        entries.append(('bootstrap', 'java/lang/System', 'initPhase2', '(ZZ)I'))
    if system_phase3:
        entries.append(('bootstrap', 'java/lang/System', 'initPhase3', '()V'))
    if server_help:
        class_roots.append(('vanilla-application','net/minecraft/server/Main'))
        entries.append(('vanilla-application','net/minecraft/server/Main','main','([Ljava/lang/String;)V'))
    class_roots=append_source_roots(class_roots,extra_class_roots,2)
    entries=append_source_roots(entries,extra_method_roots,4)
    manifest = source.prepare(batch, plan, output, class_roots, entries,
        diagnostic=dict(admit_methods=p['admitted_methods'], admit_classes=p.get('admitted_classes', []),
            known_symbols=known, data_providers=providers, global_identity=identity,context_rows=system_phase2),
        provider_packs=provider_paths, verified_provider_packs=packs)
    if 'boom_java_string_literal_root_count' not in manifest['exports']:
        manifest['exports'].append('boom_java_string_literal_root_count')
    manifest['exports'].extend(f"boom_layout{owners[n]['id']}" for n in CLASS_NAMES[:3])
    # Selection is still being prepared here; no verification/execution receipt
    # exists yet. Complete the manifest before the independent build verifies it.
    (output/'closure.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    for row in selected:
        actual = manifest['selected_methods'].get(row['method'])
        S.check(actual is not None and actual['code_sha256'] == row['code_sha256'] and
                actual['source_sha256'] == row['class_sha256'], 'Original VM constructor was not selected intact')
    config = dict(schema=1, pool_bytes=192, pool_abi=1, pool_magic=0x56544250,
        image=str(output/'diagnostic-image.dll'), runtime=str(runtime), classes={n: c['id'] for n, c in owners.items()},
        layouts=layouts, constructors=selected, main_literal_id=literal, vm_level_symbol=f"boom_s{vm['id']}_{level[0]}",
        string_coder_offset=next(f['offset'] for f in layouts['java/lang/String']['fields'] if f['member']['name'] == 'coder'),
        prerequisite_classes=[r['class_id'] for r in manifest['requested_class_roots'][:4]],
        continue_System_phase1=continue_system,
        construct_child=construct_child,
        start_child=start_child,
        child_task_main_thread=child_task_main_thread,
        system_entry_symbol=next((r['symbol'] for r in manifest['requested_method_roots'] if
                                  r['owner']=='java/lang/System' and r['name']=='initPhase1'),None),
        constructor_specialization=False, constructor_branches_removed=False, fake_Thread_field_state=False,
        source_configuration_only=True, full_VM_bootstrap=False, game_started=False)
    if extra_class_roots or extra_method_roots:
        config['additional_source_class_roots']=[list(row) for row in extra_class_roots]
        config['additional_source_method_roots']=[list(row) for row in extra_method_roots]
        config['additional_source_roots_counted_as_execution']=False
    config['inputs'] = [S.artifact(p) for p in [Path(__file__), ROOT/'native/runtime/vm_thread_bootstrap.asm',
        ROOT/'tests/host/NormalVmThreadBootstrapProbe.cs', ROOT/'scripts/Run-NormalVmThreadBootstrap.ps1',
        output/'closure.json', output/'diagnostic.json', output/'initialization-closure.asm', runtime, runtime.with_name('runtime.json')]]
    S.write(output/'vm-thread-bootstrap.json', config)
    print(json.dumps(dict(source_Java_constructors=len(selected), original_branches_preserved=True,
        selected_Java_methods=len(manifest['selected_methods']), game_started=False)))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('batch', 'plan', 'runtime', 'output', 'profile'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--provider-pack', action='append', type=Path, required=True)
    p.add_argument('--continue-system-phase1', action='store_true')
    p.add_argument('--system-phase2', action='store_true')
    p.add_argument('--system-phase3', action='store_true')
    p.add_argument('--server-help', action='store_true')
    p.add_argument('--construct-child', action='store_true')
    p.add_argument('--start-child', action='store_true')
    p.add_argument('--child-task-main-thread', action='store_true')
    p.add_argument('--source-class',action='append',default=[],help='Additional original loader:class source root, not execution evidence')
    p.add_argument('--source-entry',action='append',default=[],help='Additional original loader:class:method:descriptor source root')
    a = p.parse_args()
    prepare(a.batch, a.plan, a.runtime, a.output, a.profile, a.provider_pack, a.continue_system_phase1 or a.system_phase2 or a.system_phase3 or a.server_help, a.construct_child, a.start_child, a.child_task_main_thread, a.system_phase2 or a.system_phase3 or a.server_help, a.system_phase3 or a.server_help, a.server_help,
        extra_class_roots=[tuple(value.split(':',1)) for value in a.source_class],
        extra_method_roots=[tuple(value.split(':',3)) for value in a.source_entry])
