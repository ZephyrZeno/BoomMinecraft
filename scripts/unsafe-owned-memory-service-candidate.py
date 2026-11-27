"""Compose six real Unsafe services with frozen RW/heap kernels; no PE/guest."""
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
    spec = importlib.util.spec_from_file_location('owned_composite_' + name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S = module('runtime-provider-source')
B = module('unsafe-owned-memory-candidate')
C = module('unsafe-owned-memory-service-source')
NM = module('native-memory-owner-candidate')
O = module('jimage-owner-candidate')
A = module('verify-batch-assembly')
ART = S.ART / 'unsafe-owned-memory'
checked = B.checked


def machine_hash(path):
    return hashlib.sha256(json.dumps(O.normalized_coff(path), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def contract(adapters_file, owner_file, heap_source, heap_object, heap_proof_file, heap_abi_file):
    adapters_file, owner_file, heap_source, heap_object, heap_proof_file, heap_abi_file = map(Path,
        (adapters_file, owner_file, heap_source, heap_object, heap_proof_file, heap_abi_file))
    adapters = S.read(adapters_file)
    adapter_proof_file = adapters_file.with_name('verification.json')
    proof = S.read(adapter_proof_file)
    S.check(proof['verified'] is True and proof['candidate'] == S.artifact(adapters_file) and
            proof['scope'] == 'unregistered_source_Frame_and_COFF_only_owned_memory_adapters_unbound_services',
            'Exact successful source/Frame/typed-prefix adapter proof required')
    state = S.read(checked(adapters['metadata']['input_state']))
    S.check(state['tool_sources'] == S.tools_identity() == adapters['metadata']['tools'], 'Original source namespace changed')
    for row in adapters['metadata']['sources'].values():
        checked(row)
    original = adapters['metadata']
    fresh_adapter_metadata = B.contract(checked(original['input_state']), checked(original['reference_model']),
        checked(original['source_selection']['manifest']), checked(original['readonly_copy']['candidate']),
        checked(original['owner_ABI']))
    S.check(original == fresh_adapter_metadata,
            'Adapter metadata is not the current independently derived Source/Frame/Code projection')
    for unit in adapters['units'].values():
        checked(unit['assembly']); checked(unit['object'])
    abi = S.read(checked(adapters['metadata']['owner_ABI']))
    owner, owner_proof = S.read(owner_file), S.read(owner_file.with_name('verification.json'))
    S.check(owner_proof['verified'] is True and checked(owner_proof['candidate']) == owner_file.resolve() and
            owner['ABI'] == NM.ABI and owner['sources'] == NM.sources(), 'Current frozen RW owner source/canonical proof differs')
    for row in owner['sources'].values():
        checked(row)
    checked(owner['object']); checked(owner['assembly'])
    S.check(checked(owner['assembly']).read_text(encoding='utf-8') == NM.assembly(), 'RW owner assembly differs from exact source producer')
    names = {'owner': 'owner_q', 'address': 'address_q', 'bytes': 'bytes_q', 'other': 'other_q', 'value': 'value_q',
        'result': 'result_q', 'token': 'lease_token_q', 'generation': 'generation_q', 'width': 'width_d',
        'flags': 'flags_d', 'op': 'op_d', 'status': 'status_d', 'os_error': 'os_error_d', 'completed': 'completed_q'}
    S.check(owner['ABI']['owner_magic'] == abi['owner_magic'] and owner['ABI']['owner_bytes'] == abi['owner_bytes'] == 128 and
            owner['ABI']['job_bytes'] == abi['job_bytes'] == 128 and
            all(owner['ABI']['job_offsets'][key] == abi['job_offsets'][value] for key, value in names.items()),
            'The frozen shadow adapter ABI and published owner ABI differ')
    hp, ha = S.read(heap_proof_file), S.read(heap_abi_file)
    S.check(hp['verified'] is True and hp['all_input_hashes_unchanged'] is True and
            hp['SourceV_or_native_VM_V_or_Main_executed'] is False and
            hp['ABI']['digest'] == S.digest(heap_abi_file) and
            ha['symbol'] == 'boom_primitive_heap_span' and ha['source_ArrayBaseOffset'] == 0 and
            ha['header_payload_bytes_offset'] == -16 and ha['failed_output_unchanged'] is True,
            'Frozen exact primitive-heap endpoint proof/ABI differs')
    for row in hp['inputs']:
        checked(row)
    checked(hp['ABI'])
    S.check(any(row['path'] == str(heap_source.resolve()) and row['digest'] == S.digest(heap_source) for row in hp['inputs']),
            'Actual primitive span source was not part of its frozen independent proof')
    # Its complete actual/canonical machine proof supplies the real object;
    # the object path itself is never a source of the expected EXTERN contract.
    S.check(A.coff_symbols(heap_object) == ({'boom_primitive_heap_span'}, {'boom_heap_contains'}), 'Primitive span COFF declarations differ')
    [heap_machine] = [row for row in hp['complete_COFF'] if row['name'] == 'primitive_heap_span']
    S.check(heap_machine['object'] == S.artifact(heap_object) and heap_machine['complete_normalized_COFF_equal'] is True and
            O.normalized_coff(heap_object) == heap_machine['normalized'], 'Actual primitive span complete machine proof differs')
    legacy = S.read(checked(adapters['metadata']['readonly_copy']['candidate']))
    scalar_file = legacy['metadata']['source_scalar_receiver_validator']
    checked(scalar_file)
    return dict(adapter_candidate=S.artifact(adapters_file), adapter_verification=S.artifact(adapter_proof_file),
        input_state=adapters['metadata']['input_state'], source_selection=adapters['metadata']['source_selection'],
        service_source=C.metadata(abi, S), adapter_source=adapters['metadata']['source'],
        owner=dict(candidate=S.artifact(owner_file), verification=S.artifact(owner_file.with_name('verification.json')),
            source=owner['sources']['kernel'], assembly=owner['assembly'], object=owner['object'], ABI=owner['ABI']),
        heap_span=dict(source=S.artifact(heap_source), object=S.artifact(heap_object),
            verification=S.artifact(heap_proof_file), ABI=S.artifact(heap_abi_file)),
        runtime=adapters['metadata']['runtime'], tools=S.tools_identity(),
        readonly_fallback=dict(candidate=adapters['metadata']['readonly_copy']['candidate'],
            core_object=adapters['metadata']['readonly_copy']['core_object'],
            service_only_object=adapters['units']['readonly-copy-service']['object'],
            duplicate_original_copy_native_removed=True),
        producer=S.artifact(__file__), registered=False, Java_or_SourceV_recompiled=False,
        no_Runtime_DLL_changes=True, actual_Java_execution=False)


def sources(metadata):
    adapters = S.read(checked(metadata['adapter_candidate']))
    model = adapters['metadata']['source']
    ro = S.read(checked(adapters['metadata']['readonly_copy']['candidate']))
    abi = S.read(checked(adapters['metadata']['owner_ABI']))
    return {
        'native-frames': B.C.normal_frames_assembly(model),
        'typed-routes': B.C.typed_assembly(model),
        'readonly-copy-service': B.C.legacy_copy_service_assembly(ro['metadata']['source'])[:3],
        'owned-services': C.assembly(abi),
        'owned-core': (NM.assembly(), set(NM.EXPORTS), set(NM.IMPORTS)),
        'primitive-heap-span': (checked(metadata['heap_span']['source']).read_text(encoding='utf-8'),
            {'boom_primitive_heap_span'}, {'boom_heap_contains'}),
    }


def assemble(directory, expected_sources):
    directory.mkdir(parents=True)
    result = {}
    for name, (text, exports, imports) in expected_sources.items():
        asm, obj = directory / (name + '.asm'), directory / (name + '.obj')
        asm.write_text(text, encoding='utf-8', newline='\n')
        with (directory / (name + '.log')).open('xb') as log:
            subprocess.run([str(O.TOOLS / 'ml64.exe'), '/nologo', '/c', '/Fo' + str(obj), str(asm)],
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        foreign = {symbol for symbol in imports if not symbol.startswith('boom_')}
        S.check(A.coff_symbols(obj, allowed_foreign=foreign) == (set(exports), set(imports)), 'Actual source declaration mismatch: ' + name)
        result[name] = dict(assembly=S.artifact(asm), object=S.artifact(obj), exports=sorted(exports), imports=sorted(imports))
    return result


def verify(file):
    file = Path(file).resolve(); row = S.read(file)
    S.check(file.is_relative_to(ART), 'Isolated composed service candidate required')
    m = row['metadata']
    expected = contract(checked(m['adapter_candidate']), checked(m['owner']['candidate']), checked(m['heap_span']['source']),
        checked(m['heap_span']['object']), checked(m['heap_span']['verification']), checked(m['heap_span']['ABI']))
    S.check(m == expected and row['assembler'] == S.artifact(O.TOOLS / 'ml64.exe'), 'Current composed source/kernel metadata changed')
    expected_sources = sources(expected)
    fresh = assemble(ART / 'machine-checks' / uuid4().hex, expected_sources)
    comparisons = {}
    all_exports = []
    for name, canonical in fresh.items():
        actual = row['units'][name]
        text, exports, imports = expected_sources[name]
        S.check(checked(actual['assembly']).read_text(encoding='utf-8') == text and actual['exports'] == sorted(exports) and actual['imports'] == sorted(imports),
                'Actual composed source/extern/public differs: ' + name)
        parsed = O.normalized_coff(checked(actual['object']))
        S.check(parsed == O.normalized_coff(checked(canonical['object'])), 'Complete source/canonical COFF differs: ' + name)
        comparisons[name] = dict(actual=actual['object'], canonical=canonical['object'],
            normalized_sha256=machine_hash(checked(actual['object'])), complete_bytes_flags_symbols_aux_relocations_unwind_equal=True)
        all_exports += actual['exports']
    S.check(len(all_exports) == len(set(all_exports)), 'Composite memory/RO services have duplicate exported definitions')
    prefix = B.typed_prefix_proof(checked(m['adapter_source']['original_typed_unit']['object']),
        checked(row['units']['typed-routes']['object']), m['adapter_source']['typed_methods'])
    return dict(verified=True, scope='unregistered_six_Unsafe_services_and_typed16_composite_source_Frame_complete_COFF_only',
        candidate=S.artifact(file), complete_machine=comparisons, typed_original_prefix=prefix,
        native_declarations=6, original_Java_Code=26, actual_service_implementation_COFF=True,
        real_RW_core_and_heap_span_COFF=True, duplicate_copyMemory0_definition=False,
        external_RO_bridge_and_VM_bindings_not_linked=True, PE_linked=False,
        original_Java_or_Main_executed=False, SourceV_repeated=False, Runtime_DLL_modified=False,
        registered=False, runtime_accepted=False, game_started=False)


def build(args):
    output = args.output.resolve()
    S.check(output.is_relative_to(ART) and not output.exists(), 'Fresh isolated composed service output required')
    metadata = contract(args.adapters, args.owner, args.heap_source, args.heap_object, args.heap_proof, args.heap_abi)
    units = assemble(output, sources(metadata))
    candidate = output / 'candidate.json'
    S.write(candidate, dict(schema=1, metadata=metadata, units=units, assembler=S.artifact(O.TOOLS / 'ml64.exe'),
        registered=False, linked=False, executed=False, game_started=False))
    S.write(output / 'verification.json', verify(candidate))
    print(json.dumps(dict(candidate=S.artifact(candidate), verification=S.artifact(output / 'verification.json'), linked=False, executed=False)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'verify'))
    parser.add_argument('--adapters', type=Path)
    parser.add_argument('--owner', type=Path)
    parser.add_argument('--heap-source', type=Path)
    parser.add_argument('--heap-object', type=Path)
    parser.add_argument('--heap-proof', type=Path)
    parser.add_argument('--heap-abi', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--candidate', type=Path)
    args = parser.parse_args()
    build(args) if args.action == 'build' else print(json.dumps(verify(args.candidate), indent=2))
