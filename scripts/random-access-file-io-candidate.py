"""Build two source-bound RAF RO6 objects and verify their full native contract.

The original shared FIS/FD.close0 prefix is protected separately from complete
new-object canonical verification. No Java selection, runtime rebuild, PE link,
guest execution, or provider registration is performed.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

N = module('RFIO_source', HERE / 'random-access-file-io-source.py')
O = module('RFIO_complete_COFF', HERE / 'jimage-owner-candidate.py')
P = module('RFIO_original_prefix', HERE / 'native-coff-prefix.py')
NR = module('RFIO_physical_roots', HERE / 'provider-native-roots.py')
RI = module('RFIO_formal_initIDs', HERE / 'random-access-file-initids-candidate.py')
check, artifact, checked, read = N.check, N.artifact, N.checked, N.read
OPERATIONS = [0, 1, 2, 3, 4, 5]

def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')

def fresh(path):
    path = Path(path).resolve()
    check(path.is_relative_to(ROOT / '.boom') and not path.exists(), 'Use a fresh isolated candidate/proof output')
    path.mkdir(parents=True);return path

def producers():
    rows = {key: artifact(path) for key, path in (('candidate', __file__), ('source', N.__file__),
        ('kernel', N.KERNEL), ('COFF_reader', O.__file__), ('prefix', P.__file__), ('physical_roots', NR.__file__))}
    rows.update({'initIDs_' + key: value for key, value in RI.producers().items()})
    return rows

def sources(meta):
    text, exports, imports = N.normal_frames(meta, OPERATIONS)
    original_path = checked(meta['existing_FIS_assembly']);raw = original_path.read_bytes()
    old = raw.decode('utf-8')
    check(old.encode('utf-8') == raw and '\r' not in old and old.endswith('END\n'), 'Exact original LF assembly prefix required')
    body = Path(N.KERNEL).read_bytes().decode('utf-8')
    check(body.count('boom_provider_random_access_file_service PROC FRAME') == 1 and
          body.count('boom_random_access_file_io_drain PROC FRAME') == 1, 'Complete RO6 service/drain required')
    fid = meta['original_RAF_Class_and_FieldID_source']['fields'][0]['symbol']
    header = ('\n; Explicit source-derived appended RFIO bindings; old entire source is unchanged.\n'
        'EXTERN boom_random_access_file_init_ids_pool:BYTE\nEXTERN ' + fid + ':PROC\nRFIO_RAF_FD_MAP TEXTEQU <' + fid + '>\n')
    combined = old[:-4] + header + body + '\nEND\n'
    P.source_prefix(original_path, original_path)
    normalized = O.normalized_coff(checked(meta['existing_FIS_object']))
    combined_exports = set(normalized['exports']) | {N.POOL, N.SERVICE, 'boom_random_access_file_io_drain'}
    combined_imports = set(normalized['imports']) | {'boom_random_access_file_init_ids_pool', fid}
    return dict(native=(text, exports, imports), combined=(combined, combined_exports, combined_imports))

def assemble(directory, assembler, texts):
    result = {}
    for name, (text, exports, imports) in texts.items():
        asm, obj = directory / (name + '.asm'), directory / (name + '.obj')
        with asm.open('x', encoding='utf-8', newline='\n') as stream:stream.write(text)
        with (directory / (name + '.log')).open('xb') as log:
            process = subprocess.run([str(assembler), '/nologo', '/c', '/Fo' + str(obj), str(asm)],
                stdout=log, stderr=subprocess.STDOUT, timeout=120)
        write(directory / (name + '-status.json'), dict(natural_exit_code=process.returncode))
        check(process.returncode == 0, 'Actual MASM failure preserved: ' + name)
        normalized = O.normalized_coff(obj)
        check(set(normalized['exports']) == exports and set(normalized['imports']) == imports,
              'Actual declarations or native import domain differs: ' + name)
        result[name] = dict(assembly=artifact(asm), object=artifact(obj), exports=sorted(exports), imports=sorted(imports))
    return result

def verify(candidate_file, output):
    candidate_file = Path(candidate_file).resolve();before = artifact(candidate_file);candidate = read(candidate_file)
    check(candidate['schema'] == 1 and candidate['family'] == 'source-random-access-file-readonly-candidate' and
          candidate['producers'] == producers() and candidate['operations'] == OPERATIONS and
          all(candidate[key] is False for key in ('registered', 'linked', 'executed', 'game_started', 'runtime_acceptance_complete')),
          'Current original source candidate/scope differs')
    for row in candidate['inputs']:checked(row)
    args = candidate['binding_inputs']
    meta = N.bind(checked(args['state']), checked(args['source']), checked(args['parent']),
        args['pinned_directory'], checked(args['records_source']), checked(args['abi']))
    check(meta == candidate['metadata'] == read(checked(candidate['model'])), 'Independent current source/Frame/Code projection differs')
    texts = sources(meta)
    check(set(candidate['units']) == set(texts) == {'native', 'combined'}, 'Exactly two runtime-facing objects required')
    output = fresh(output)
    canonical_dir = output / 'canonical';canonical_dir.mkdir()
    canonical = assemble(canonical_dir, checked(candidate['assembler']), texts)
    machines = {}
    for name, (text, exports, imports) in texts.items():
        actual = candidate['units'][name]
        check(checked(actual['assembly']).read_bytes() == text.encode('utf-8') and
              actual['exports'] == sorted(exports) and actual['imports'] == sorted(imports), 'Canonical source or declared native ABI differs: ' + name)
        actual_machine = O.normalized_coff(checked(actual['object']))
        check(actual_machine == O.normalized_coff(checked(canonical[name]['object'])),
              'Actual/fresh canonical full sections/flags/symbolaux/relocations/unwind differ: ' + name)
        machines[name] = dict(actual=actual['object'], canonical_assembly=canonical[name]['assembly'], canonical_object=canonical[name]['object'],
            normalized=actual_machine, normalized_sha256=hashlib.sha256(json.dumps(actual_machine, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            all_nondebug_bytes_flags_symbols_aux_relocations_unwind_equal=True)
    # The parent may retain a historical initIDs candidate artifact. Its Python
    # producers are never loaded. Current formal source regenerates both unit
    # texts, and these fresh canonical witnesses check its linked objects.
    init_dir = output / 'initIDs-canonical';init_dir.mkdir()
    init_canonical = assemble(init_dir, checked(candidate['assembler']), RI.sources(meta['original_RAF_Class_and_FieldID_source']))
    init_machine = {}
    for name, expected in init_canonical.items():
        actual = meta['original_initIDs_units'][name]
        check(O.normalized_coff(checked(actual['object'])) == O.normalized_coff(checked(expected['object'])),
              'Formal initIDs source does not reproduce the original linked machine contract: ' + name)
        init_machine[name] = dict(actual=actual['object'], canonical=expected, complete_COFF_equal=True)
    unit = candidate['units']['combined']
    prefix = P.verify(checked(meta['existing_FIS_assembly']), checked(meta['existing_FIS_object']), checked(unit['assembly']), checked(unit['object']))
    write(output / 'prefix-verification.json', prefix)
    legacy = read(checked(meta['existing_FIS_provider']))
    roots = NR.verify_object(checked(unit['object']), legacy['native_root_spans'], assembly=checked(unit['assembly']))
    check(len(roots) == 1 and roots[0]['symbol'] == 'boom_file_input_owner_roots' and roots[0]['count'] == 4096 and
          roots[0]['bytes'] == 32768 and roots[0]['initial_zero'] and roots[0]['physical_QWORD_span_verified'],
          'The unchanged physical4096 FD-root bank differs')
    write(output / 'root-proof.json', roots)
    for row in candidate['inputs']:checked(row)
    checked(before)
    proof = dict(schema=1, verified=True, scope='unregistered_original_RAF_RO6_source_native_Frame_and_whole_composite_COFF_only',
        candidate=before, verifier=artifact(__file__), producers=producers(), complete_machine=machines,
        original_initIDs_complete_machine=init_machine, prefix_verification=artifact(output / 'prefix-verification.json'),
        physical_root_proof=artifact(output / 'root-proof.json'),
        original_native_inventory=9, supplied_operations=OPERATIONS, normal_native_adapters=6,
        original_FD_close0_Frame_and_owner_prefix_byteexact=True, physical_shared_FD_root_cells=4096, additional_Java_oop_roots=0,
        explicit_nonmoving_quiescent_GC_scope=True, source_V_repeated=False, PE_linked=False,
        behavioral_verified=False, guest_or_JVM_or_Main_executed=False, registered=False,
        runtime_acceptance_complete=False, game_started=False)
    path = output / 'verification.json';write(path, proof);return path

def build(args):
    check(args.assembler.is_file() and args.assembler.name.lower() == 'ml64.exe', 'Explicit installed x64 MASM required')
    binding = {key: artifact(value) for key, value in (('state', args.state), ('source', args.source), ('parent', args.parent),
        ('records_source', args.records_source), ('abi', args.abi))}
    binding['pinned_directory'] = str(args.pinned.resolve())
    meta = N.bind(args.state, args.source, args.parent, args.pinned, args.records_source, args.abi)
    inputs = list(meta['inputs']) + list(producers().values()) + [artifact(args.assembler)]
    inputs += [artifact(ROOT / name) for name in read(args.state)['tool_sources']]
    output = fresh(args.output)
    try:
        write(output / 'model.json', meta)
        units = assemble(output, args.assembler.resolve(), sources(meta))
        for row in inputs:checked(row)
        candidate = output / 'candidate.json'
        write(candidate, dict(schema=1, family='source-random-access-file-readonly-candidate', producers=producers(),
            binding_inputs=binding, metadata=meta, model=artifact(output / 'model.json'), units=units,
            operations=OPERATIONS, assembler=artifact(args.assembler), inputs=inputs + [artifact(output / 'model.json')],
            original_FD_close0_replaced=False, additional_Java_oop_roots=0,
            registered=False, linked=False, executed=False, game_started=False, runtime_acceptance_complete=False))
        proof = verify(candidate, output / 'independent')
        write(output / 'verification.json', read(proof))
        print(json.dumps(dict(candidate=artifact(candidate), verification=artifact(output / 'verification.json')), indent=2))
    except BaseException as error:
        write(output / 'first-failure.json', dict(error=repr(error), guest_executed=False, original_inputs_changed=False));raise

def main():
    parser = argparse.ArgumentParser(description=__doc__);sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('build')
    for name in ('state', 'source', 'parent', 'pinned', 'records-source', 'abi', 'assembler', 'output'):p.add_argument('--' + name, type=Path, required=True)
    p = sub.add_parser('verify');p.add_argument('--candidate', type=Path, required=True);p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'build':build(args)
    else:print(json.dumps(artifact(verify(args.candidate, args.output)), indent=2))

if __name__ == '__main__':main()
