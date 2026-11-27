"""Source/Frame/COFF shadow adapters; memory services remain explicitly unbound.

This first stage can verify normal six-native adapters and the typed42 route
prefix without an unfrozen core implementation. It never links or runs a PE.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location('owned_unsafe_candidate_' + name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S = module('runtime-provider-source')
C = module('unsafe-owned-memory-source')
O = module('jimage-owner-candidate')
A = module('verify-batch-assembly')
RB = module('jimage-unsafe-read-candidate')
ART = S.ART / 'unsafe-owned-memory'


def checked(row):
    path = Path(row['path']).resolve()
    expected = row.get('digest', row)
    actual = S.digest(path)
    S.check(all(actual[key] == expected[key] for key in ('size', 'sha256')), 'Owned-memory source input changed: ' + str(path))
    return path


def contract(state_file, reference_file, selection_file, ro_copy_file, owner_abi_file):
    state_file, reference_file, selection_file, ro_copy_file, owner_abi_file = map(Path,
        (state_file, reference_file, selection_file, ro_copy_file, owner_abi_file))
    state = S.read(state_file)
    S.check(state['current_source_provider_verification_complete'] is True and
            state['status'] in ('accepted', 'pending_runtime_acceptance') and state['tool_sources'] == S.tools_identity(),
            'Actual current source-verified input state required')
    identity, summary, classes = S.base(Path(state['batch']), Path(state['plan']))
    S.check(identity['batch_summary']['digest']['sha256'] == state['batch_summary_sha256'] and
            identity['base_verification']['digest']['sha256'] == state['batch_verification_sha256'],
            'Original current batch/full-proof identity changed')
    reference = S.read(reference_file)
    meta = C.index(summary, classes, S)
    C.compare_reference(meta, reference, S)
    abi = S.read(owner_abi_file)
    S.check(abi['schema'] == 'boom-native-memory-owner-abi-v1' and abi['owner_bytes'] == abi['job_bytes'] == 128 and
            abi['source_model_sha256'] == S.digest(reference_file)['sha256'], 'Frozen source-backed owner ABI required')
    frame_path = Path(state['frame_manifest'])
    frame, frame_proof = S.read(frame_path), S.read(frame_path.with_name('verification.json'))
    NF = module('native-frame-overlay')
    S.check(frame['source']['base'] == identity and frame['tool_sources'] == NF.tools() and frame_proof['verified'] is True and
            frame_proof['manifest_sha256'] == S.digest(frame_path)['sha256'] and
            S.digest(frame_path.with_name('verification.json'))['sha256'] == state['frame_verification_sha256'],
            'Existing exact current normal-native Frame proof changed')
    declarations = {row['id']: row for row in frame['source']['original_native_declarations']}
    for row in meta['methods'] + meta['typed_methods']:
        actual = declarations[row['method']]
        S.check(actual['flags'] == row['frame_flags'] == 32 and all(actual[key] == row[key]
            for key in ('class_id', 'class_sha256', 'loader', 'source_id', 'name', 'descriptor', 'access')),
            'Dynamic original source declaration/native Frame differs')
    selection = S.read(selection_file)
    selection_proof = selection_file.with_name('selection-verification.json')
    proof = S.read(selection_proof)
    S.check(proof['verified'] is True and proof['closure_manifest_sha256'] == S.digest(selection_file)['sha256'] and
            selection['source_batch_summary_sha256'] == identity['batch_summary']['digest']['sha256'] and
            selection['source_classes_sha256'] == identity['source_classes']['digest']['sha256'],
            'Original verified source selection is not the same current batch/plan')
    selected = []
    for row in meta['original_Java']:
        actual = selection['selected_methods'].get(str(row['method']))
        S.check(actual and actual['code_sha256'] == row['code_sha256'] and actual['source_sha256'] == row['class_sha256'],
                'An original Java wrapper/check is not already selected: ' + row['name'] + row['descriptor'])
        selected.append(dict(method=row['method'], owner=row['owner'], name=row['name'], descriptor=row['descriptor'],
            code_sha256=row['code_sha256'], source_sha256=row['class_sha256']))
    runtime = Path(state['runtime']) / 'boom-runtime.dll'
    runtime_manifest = runtime.with_name('runtime.json')
    runtime_meta = S.read(runtime_manifest)
    S.check(S.digest(runtime)['sha256'] == state['runtime_sha256'] == runtime_meta['sha256'], 'Original runtime DLL changed')
    for name, record in meta['source_kernels'].items():
        S.check(runtime_meta['sources']['native/runtime/' + name] == record['digest']['sha256'], 'Normal heap/receiver kernel changed')
    ro_copy = S.read(ro_copy_file)
    ro_proof_file = ro_copy_file.with_name('verification.json')
    ro_proof = S.read(ro_proof_file)
    S.check(ro_proof['verified'] is True and ro_proof['candidate'] == S.artifact(ro_copy_file) and
            ro_copy['metadata']['input_state'] == S.artifact(state_file) and ro_copy['metadata']['base'] == identity and
            ro_copy['metadata']['source']['methods'][0]['method'] == next(row['method'] for row in meta['methods'] if row['name'] == 'copyMemory0'),
            'Original current RO copy fallback is not the same source declaration')
    for key in ('assembly', 'object', 'core_assembly', 'core_object'):
        checked(ro_copy[key])
    expected_copy_source = module('jimage-unsafe-copy-source').assembly(ro_copy['metadata']['source'])[0]
    S.check(checked(ro_copy['assembly']).read_text(encoding='utf-8') == expected_copy_source, 'Original RO copy service source changed')
    legacy = C.legacy_copy_service_assembly(ro_copy['metadata']['source'])
    return dict(base=identity, input_state=S.artifact(state_file), source=meta, reference_model=S.artifact(reference_file),
        owner_ABI=S.artifact(owner_abi_file), owner_ABI_scope=abi['status'], owner_kernel_bound=False,
        frame_overlay=dict(manifest=S.artifact(frame_path), verification=S.artifact(frame_path.with_name('verification.json'))),
        source_selection=dict(manifest=S.artifact(selection_file), verification=S.artifact(selection_proof), original_26_selected=selected),
        readonly_copy=dict(candidate=S.artifact(ro_copy_file), verification=S.artifact(ro_proof_file),
            assembly=ro_copy['assembly'], object=ro_copy['object'], core_object=ro_copy['core_object'], service_extraction=legacy[3]),
        runtime=S.artifact(runtime), runtime_manifest=S.artifact(runtime_manifest), tools=S.tools_identity(),
        sources={name: S.artifact(ROOT / name) for name in ('scripts/unsafe-owned-memory-source.py', 'scripts/unsafe-owned-memory-candidate.py')},
        pending_services=[C.POOL, C.SERVICE, C.TYPED_SERVICE], implemented_memory_services=0,
        no_new_full_Frame_or_SourceV=True, no_link_or_guest=True)


def typed_prefix_proof(original, variant, methods):
    before, symbols = RB.coff(original)
    after, actual_symbols = RB.coff(variant)
    routed = {'boom_m' + str(row['method']) + '_native' for row in methods if row['operation'] in C.PLAIN_OPERATIONS}
    defined = {name: row for name, row in symbols.items() if isinstance(row['section'], str)}
    S.check(len(defined) == 84 and all(actual_symbols.get(name) == row for name, row in defined.items()),
            'Original 42 wrappers/native aliases changed value/type')
    changed, sections = [], {}
    for name, section in before.items():
        if name.startswith('.debug'):
            continue
        target = after[name]
        S.check(section['data'] == target['data'] and section['flags'] == target['flags'],
                'Original typed instruction/data/unwind bytes or flags changed')
        S.check(len(section['relocations']) == len(target['relocations']), 'Typed relocation count changed')
        for old, new in zip(section['relocations'], target['relocations']):
            if old == new:
                continue
            candidates = [symbol for symbol in routed if defined[symbol]['value'] <= old['offset'] < defined[symbol]['value'] + 32]
            S.check(name in ('.text', '.text$mn') and len(candidates) == 1 and old['offset'] == new['offset'] and
                    old['kind'] == new['kind'] == 4 and old['target']['name'] == 'boom_java_unsafe_memory' and
                    new['target']['name'] == C.TYPED_SERVICE and section['data'][old['offset'] - 1] == 0xe9,
                    'Only the sixteen exact terminal plain primitive JMP relocations may change')
            changed.append(candidates[0])
        sections[name] = dict(bytes=len(section['data']), sha256=hashlib.sha256(section['data']).hexdigest(),
            flags=section['flags'], relocation_count=len(section['relocations']))
    S.check(len(routed) == 16 and sorted(changed) == sorted(routed), 'Exactly sixteen distinct plain primitive tails required')
    return dict(verified=True, original=S.artifact(original), variant=S.artifact(variant),
        all_42_method_wrapper_bytes_preserved=True, aliases=84, redirected_plain_tails=sorted(changed),
        untouched_reference_volatile_CAS_terminal_routes=26, all_original_heap_and_ThreadIdentifiers_support_required=True,
        actual_composition_service_available=False, sections=sections)


def compile_units(directory, metadata):
    directory.mkdir(parents=True)
    ro_copy = S.read(checked(metadata['readonly_copy']['candidate']))
    legacy = C.legacy_copy_service_assembly(ro_copy['metadata']['source'])
    entries = [('native-frames', C.normal_frames_assembly(metadata['source'])),
               ('typed-routes', C.typed_assembly(metadata['source'])), ('readonly-copy-service', legacy[:3])]
    records = {}
    for name, (text, exports, imports) in entries:
        assembly, obj = directory / (name + '.asm'), directory / (name + '.obj')
        assembly.write_text(text, encoding='utf-8', newline='\n')
        with (directory / (name + '.log')).open('xb') as log:
            subprocess.run([str(O.TOOLS / 'ml64.exe'), '/nologo', '/c', '/Fo' + str(obj), str(assembly)],
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        S.check(A.coff_symbols(obj) == (set(exports), set(imports)), 'Actual shadow native symbols differ: ' + name)
        records[name] = dict(assembly=S.artifact(assembly), object=S.artifact(obj), exports=sorted(exports), imports=sorted(imports))
    return records


def verify(file):
    file = Path(file).resolve()
    row = S.read(file)
    S.check(file.is_relative_to(ART), 'Isolated shadow candidate required')
    m = row['metadata']
    expected = contract(checked(m['input_state']), checked(m['reference_model']), checked(m['source_selection']['manifest']),
        checked(m['readonly_copy']['candidate']), checked(m['owner_ABI']))
    S.check(m == expected and row['assembler'] == S.artifact(O.TOOLS / 'ml64.exe'), 'Current source/Frame/tool projection changed')
    fresh = compile_units(ART / 'machine-checks' / uuid4().hex, expected)
    machine = {}
    for key in fresh:
        actual, canonical = row['units'][key], fresh[key]
        S.check(checked(actual['assembly']).read_text(encoding='utf-8') == checked(canonical['assembly']).read_text(encoding='utf-8') and
                actual['exports'] == canonical['exports'] and actual['imports'] == canonical['imports'], 'Canonical adapter source changed')
        parsed = O.normalized_coff(checked(actual['object']))
        S.check(parsed == O.normalized_coff(checked(canonical['object'])), 'Complete source adapter COFF differs: ' + key)
        machine[key] = dict(actual=actual['object'], canonical=canonical['object'],
            normalized_sha256=hashlib.sha256(json.dumps(parsed, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            complete_nondebug_bytes_flags_symbols_aux_relocations_unwind_equal=True)
    prefix = typed_prefix_proof(checked(m['source']['original_typed_unit']['object']),
        checked(row['units']['typed-routes']['object']), m['source']['typed_methods'])
    definitions = [name for unit in row['units'].values() for name in unit['exports']]
    S.check(len(definitions) == len(set(definitions)) == 97, 'Native/typed/legacy copy duplicate definitions')
    S.check(all('boom_m' + str(n['method']) in row['units']['native-frames']['exports'] for n in m['source']['methods']),
            'All six dynamic original native Frame adapters required')
    return dict(verified=True, scope='unregistered_source_Frame_and_COFF_only_owned_memory_adapters_unbound_services',
        candidate=S.artifact(file), machine=machine, typed_prefix=prefix, normal_native_adapters=6,
        original_Java_Code_verified=26, typed_wrappers=42, legacy_RO_copy_service_native_adapter_removed=True,
        memory_service_implementation=False, owner_kernel_linked=False, full_selection_reverified=False,
        PE_linked=False, original_Java_or_Main_executed=False, registered=False, game_started=False)


def build(args):
    output = args.output.resolve()
    S.check(output.is_relative_to(ART) and not output.exists(), 'Fresh isolated source-proof output required')
    for file, sha in ((args.reference, args.reference_sha256), (args.owner_abi, args.owner_abi_sha256)):
        S.check(S.digest(file)['sha256'] == sha, 'Explicit source/ABI pin differs')
    metadata = contract(args.state, args.reference, args.selection, args.ro_copy, args.owner_abi)
    units = compile_units(output, metadata)
    row = dict(schema=1, metadata=metadata, units=units, assembler=S.artifact(O.TOOLS / 'ml64.exe'),
        registered=False, service_implementation=False, linked=False, executed=False)
    file = output / 'candidate.json'
    S.write(file, row)
    S.write(output / 'verification.json', verify(file))
    print(json.dumps(dict(candidate=S.artifact(file), verification=S.artifact(output / 'verification.json'), linked=False, executed=False)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'verify'))
    parser.add_argument('--state', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--reference-sha256')
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--ro-copy', type=Path)
    parser.add_argument('--owner-abi', type=Path)
    parser.add_argument('--owner-abi-sha256')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--candidate', type=Path)
    args = parser.parse_args()
    build(args) if args.action == 'build' else print(json.dumps(verify(args.candidate), indent=2))
