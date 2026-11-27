"""Ignored source-bound Perf self/clock/long candidate, never a source V receipt."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'AGENTS.md').is_file())
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location('perf_candidate_' + name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


N = load('original', HERE / 'perf-source.py')
O = load('machine', ROOT / 'scripts/jimage-owner-candidate.py')
def declaration_contract(text):
    import re
    exports = re.findall(r'^\s*PUBLIC\s+([A-Za-z_][A-Za-z_0-9$?@]*)\s*$', text, re.M)
    imports = re.findall(r'^\s*EXTERN\s+([A-Za-z_][A-Za-z_0-9$?@]*):(PROC|BYTE)\s*$', text, re.M)
    check(len(exports) == len(set(exports)) and len(imports) == len({name for name, _ in imports}), 'Duplicate source symbol declarations')
    check(not set(exports).intersection(name for name, _ in imports), 'Source symbol cannot be both imported and exported')
    return dict(exports=sorted(exports), imports=sorted(name for name, _ in imports))


def actual_symbols(obj, text):
    expected = declaration_contract(text)
    machine = O.normalized_coff(obj)
    check(set(machine['exports']) == set(expected['exports']) and set(machine['imports']) == set(expected['imports']),
          'Actual COFF external definitions/imports differ from exact source PUBLIC/EXTERN declarations')
check, artifact, checked, read = N.check, N.artifact, N.checked, N.read
BACKENDS = ['perf_attach', 'perf_detach', 'perf_create_long', 'perf_create_bytes', 'perf_high_counter', 'perf_high_frequency']


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        if isinstance(value, str):
            f.write(value)
        else:
            json.dump(value, f, indent=2, ensure_ascii=True)
            f.write('\n')


def row_method(meta, owner, name, descriptor):
    [row] = [r for r in meta['source_classes'][owner]['methods'] if (r['name'], r['descriptor']) == (name, descriptor)]
    return row


def text_row(symbol, text):
    units = list(int.from_bytes(text.encode('utf-16-le')[i:i+2], 'little') for i in range(0, len(text.encode('utf-16-le')), 2))
    h = 0
    for unit in units:
        h = (31 * h + unit) & 0xffffffff
    return symbol + ' WORD ' + ','.join(map(str, units + [0])) + '\n', len(units), h


def backend(meta, kernel):
    cls = meta['source_classes']
    class_aliases = {'PERF_CLASS': N.OWNER, 'PERF_BUFFER_CLASS': 'java/nio/DirectByteBuffer',
        'PERF_IAE_CLASS': 'java/lang/IllegalArgumentException', 'PERF_NPE_CLASS': 'java/lang/NullPointerException',
        'PERF_OOME_CLASS': 'java/lang/OutOfMemoryError'}
    layout_aliases = {'PERF_BUFFER_LAYOUT': 'java/nio/DirectByteBuffer', 'PERF_STRING_LAYOUT': 'java/lang/String',
        'PERF_IAE_LAYOUT': 'java/lang/IllegalArgumentException', 'PERF_NPE_LAYOUT': 'java/lang/NullPointerException',
        'PERF_OOME_LAYOUT': 'java/lang/OutOfMemoryError'}
    calls = {
        'PERF_BUFFER_CTOR': ('java/nio/DirectByteBuffer', '<init>', '(JILjava/lang/Object;Ljava/lang/foreign/MemorySegment;)V'),
        'PERF_STRING_CHARS': ('java/lang/String', 'toCharArray', '()[C'),
        'PERF_IAE_CTOR': ('java/lang/IllegalArgumentException', '<init>', '()V'),
        'PERF_NPE_CTOR': ('java/lang/NullPointerException', '<init>', '()V'),
        'PERF_OOME_CTOR': ('java/lang/OutOfMemoryError', '<init>', '()V'),
        'PERF_IAE_MESSAGE_CTOR': ('java/lang/IllegalArgumentException', '<init>', '(Ljava/lang/String;)V')}
    procs = {'boom_native_memory_service', 'boom_class_ensure32', 'boom_object_new', 'boom_object_check',
        'boom_heap_contains', 'boom_primitive_heap_span', 'boom_java_property_copy', 'boom_exception_set32',
        'QueryPerformanceCounter', 'QueryPerformanceFrequency', 'GetCurrentProcessId'}
    data = {'boom_main_native_memory_owner', 'boom_heap_ptr', 'boom_runtime_type_map', 'boom_java_platform_properties_pool'}
    aliases = {}
    for alias, name in class_aliases.items():
        aliases[alias] = cls[name]['class_symbol']
        data.add(aliases[alias])
    for alias, name in layout_aliases.items():
        aliases[alias] = cls[name]['layout_symbol']
        data.add(aliases[alias])
    for alias, spec in calls.items():
        row = row_method(meta, *spec)
        check(row['selected_Java'], 'Original callback Code must already be selected')
        aliases[alias] = 'boom_m' + str(row['method'])
        procs.add(aliases[alias])
    throwable = cls['java/lang/Throwable']['class_record']['id']
    aliases['PERF_THROWABLE_TYPE'] = 'boom_t' + str(throwable)
    data.add(aliases['PERF_THROWABLE_TYPE'])
    for row in meta['registered_methods']:
        data.add('boom_trace_method' + str(row['method']))
    buffer = cls['java/nio/DirectByteBuffer']['normal_layout']['candidate']
    offsets = {}
    for key, desc, size in [('address', 'J', 8), ('capacity', 'I', 4)]:
        [field] = [f for f in buffer['fields'] if f['member']['owner'] == cls['java/nio/Buffer']['class_record']['id'] and
            (f['member']['name'], f['member']['descriptor']) == (key, desc)]
        [original] = [f for f in cls['java/nio/Buffer']['class_record']['fields'] if (f['name'], f['descriptor']) == (key, desc)]
        check(field['storage_bytes'] == size and not field['reference'] and not original['access'] & 8,
              'Only the exact inherited source Buffer scalar field may be read')
        offsets[key] = field['offset']
    text = 'option casemap:none\n'
    text += ''.join('EXTERN ' + p + ':PROC\n' for p in sorted(procs))
    text += ''.join('EXTERN ' + p + ':BYTE\n' for p in sorted(data))
    text += ''.join(a + ' TEXTEQU <' + b + '>\n' for a, b in sorted(aliases.items()))
    text += 'PERF_CLASS_ID EQU ' + str(cls[N.OWNER]['class_record']['id']) + '\n'
    text += ''.join('PERF_BUFFER_' + k.upper() + ' EQU ' + str(v) + '\n' for k, v in offsets.items())
    text += '.const\nALIGN 8\nperf_expected_backends QWORD ' + ','.join('OFFSET ' + p for p in BACKENDS) + '\n'
    literal_meta = []
    for i, row in enumerate(meta['registered_methods']):
        n, nl, nh = text_row('perf_registered_name' + str(i), row['name'])
        d, dl, dh = text_row('perf_registered_descriptor' + str(i), row['descriptor'])
        text += n + d
        literal_meta.append((nl, dl, nh, dh))
    message, units, _ = text_row('perf_duplicate_long', 'PerfLong name already exists')
    text += message + 'PERF_DUP_LONG_LENGTH EQU ' + str(units) + '\n'
    text += 'ALIGN 8\nperf_registration_rows LABEL BYTE\n'
    for i, (row, (nl, dl, nh, dh)) in enumerate(zip(meta['registered_methods'], literal_meta)):
        text += ' DWORD ' + ','.join(map(str, (row['method'], row['class_id'], row['access'], row['frame_flags']))) + '\n'
        text += ' QWORD OFFSET boom_trace_method' + str(row['method']) + ',OFFSET PERF_CLASS,OFFSET ' + BACKENDS[i] + ',OFFSET perf_registered_name' + str(i) + ',OFFSET perf_registered_descriptor' + str(i) + '\n'
        text += ' DWORD ' + ','.join(map(str, (nl, dl, nh, dh, i+1, 0))) + '\n'
    text += '.data\nALIGN 8\nPUBLIC ' + N.POOL + '\n' + N.POOL + ' LABEL BYTE\n'
    text += ' DWORD 046524550h,1,256,0,0,0,0,0\n QWORD 0,0,0,0,0,0,0\n DWORD 0,1024\n'
    text += ' QWORD OFFSET perf_registration_rows,OFFSET PERF_CLASS\n QWORD 6 DUP(0)\n QWORD 7 DUP(0)\n DWORD 0,0\n'
    text += ' QWORD 0,OFFSET perf_requests\n DWORD 256,6144\n QWORD 0\n'
    text += 'ALIGN 8\nperf_requests BYTE 1572864 DUP(0)\nALIGN 8\nperf_counter_names BYTE 2097152 DUP(0)\n'
    text += 'ALIGN 8\nperf_counter_info BYTE 32768 DUP(0)\n'
    text += Path(kernel).read_text(encoding='utf-8') + '\nEND\n'
    contract = declaration_contract(text)
    check(set(contract['imports']) == procs | data and set(contract['exports']) ==
        {N.POOL, N.SERVICE, 'boom_perf_owner_open', 'boom_perf_owner_close'}, 'Exact source ABI imports/exports differ')
    return text, contract


def assemble(text, output, assembler):
    output = Path(output)
    output.mkdir()
    asm, obj = output / 'unit.asm', output / 'unit.obj'
    write(asm, text)
    run = subprocess.run([str(assembler), '/nologo', '/c', '/Fo' + str(obj), str(asm)], capture_output=True)
    write(output / 'assembler.stdout', run.stdout.decode('utf-8', errors='replace'))
    write(output / 'assembler.stderr', run.stderr.decode('utf-8', errors='replace'))
    check(run.returncode == 0 and obj.is_file(), 'Real ML64 failed: ' + str(output))
    return dict(assembly=artifact(asm), object=artifact(obj), assembler=artifact(assembler), process_exit=run.returncode)


def binding_inputs(args):
    return {key: artifact(getattr(args, key)) for key in ['state', 'source', 'parent', 'abi', 'records_source', 'kernel', 'release']} | {'pinned_directory': str(Path(args.pinned).resolve())}


def model_from(inputs):
    return N.bind(checked(inputs['state']), checked(inputs['source']), checked(inputs['parent']), inputs['pinned_directory'],
        checked(inputs['abi']), checked(inputs['records_source']), checked(inputs['release']))


def capabilities():
    return dict(real_source_table_registration_count=6, actual_cache_dispatch=True,
        backend_operations=[0, 1, 2, 3, 5, 6], explicit_unsupported_operations=[4],
        attach_self_only=True, detach_original_self_buffer_only=True, maximum_counter_count=1024,
        maximum_name_UTF16_units=1024, main_region_bytes=1048576,
        nonself_attach_and_string_counter_backend='Context20; not claimed as implemented',
        backing='real existing MainRW Core op0/op2 and op8/op9 persistent leases',
        Java_callbacks_outside_all_locks_and_leases=True, no_new_Java_GC_root_bank=True,
        GC_scope='explicit quiescent nonmoving only; no automatic native stack scanning')


def expected_inputs(meta, inputs, assembler):
    return meta['inputs'] + [artifact(__file__), artifact(N.__file__), artifact(O.__file__), inputs['kernel'], artifact(assembler)]


def validate_kernel_and_ABI(inputs):
    check(inputs['kernel']['digest']['sha256'] == '9d18d278b01d92c3d197af701c2e0788eeb4bfdd9c545a9d433a8f37ac00ecfa', 'Reviewed pureASM Perf E implementation changed')
    check(inputs['abi']['digest']['sha256'] == '1d1f258e47d72290f9a9d2e5963d379376af6e07bd0d198fd3c5943b32c2a1a0', 'Frozen native wire ABI changed')


def build(args):
    output = Path(args.output).resolve()
    check(output.is_relative_to(ROOT / '.boom') and not output.exists(), 'Fresh isolated .boom output required')
    output.mkdir(parents=True)
    inputs = binding_inputs(args)
    validate_kernel_and_ABI(inputs)
    meta = model_from(inputs)
    write(output / 'model.json', meta)
    texts = [N.normal_frames(meta, list(range(7)))[0], backend(meta, checked(inputs['kernel']))[0]]
    units, machine = [], []
    for role, text in zip(['native', 'backend'], texts):
        actual = assemble(text, output / role, Path(args.assembler))
        canonical = assemble(text, output / ('canonical-' + role), Path(args.assembler))
        normalized = O.normalized_coff(checked(actual['object']))
        check(normalized == O.normalized_coff(checked(canonical['object'])), 'Complete nondebug canonical COFF mismatch: ' + role)
        contract = declaration_contract(text)
        actual_symbols(checked(actual['object']), text)
        units.append(dict(role=role, **actual, canonical_assembly=canonical['assembly'], canonical_object=canonical['object'],
            exports=contract['exports'], imports=contract['imports']))
        machine.append(dict(role=role, normalized=normalized, all_nondebug_bytes_flags_symbols_aux_relocations_unwind_equal=True))
    candidate = dict(schema=1, scope='unregistered_Perf_original7Frames_full6binding_clock_long_self_native_candidate',
        binding_inputs=inputs, source_model=artifact(output / 'model.json'), ABI=inputs['abi'], capabilities=capabilities(),
        operations=list(range(7)), native_methods=meta['native_methods'], units=units, complete_machine=machine,
        runtime=meta['runtime'], input_state=meta['input_state'], source_selection=meta['source_selection'],
        source_full_verification=meta['source_full_verification'], parent_overlay=meta['parent_overlay'],
        inputs=expected_inputs(meta, inputs, args.assembler),
        registered_formal_family=False, SourceV_repeated=False, guest_or_Main_executed=False, runtime_acceptance_complete=False)
    write(output / 'candidate.json', candidate)
    proof = dict(verified=True, scope='source_original_Class_Code_Frame_and_real_canonical_COFF_only_not_guest',
        candidate=artifact(output / 'candidate.json'), original_native_declarations=7, original_source_register_table_rows=6,
        actual_and_canonical_units=2, all_nondebug_bytes_flags_symbols_aux_relocations_unwind_equal=True,
        backend_operations=capabilities()['backend_operations'], explicit_unsupported_operations=[4],
        registered_or_executed=False, runtime_acceptance_complete=False)
    write(output / 'verification.json', proof)
    print(json.dumps(artifact(output / 'candidate.json')))


def verify(args):
    candidate = read(args.candidate)
    for row in candidate['inputs']:
        checked(row)
    check(candidate['schema'] == 1 and all(candidate[k] is False for k in ('registered_formal_family','SourceV_repeated','guest_or_Main_executed','runtime_acceptance_complete')), 'Candidate execution scope differs')
    validate_kernel_and_ABI(candidate['binding_inputs'])
    check(candidate['operations'] == list(range(7)) and candidate['capabilities'] == capabilities(), 'Exact implemented subset changed')
    meta = model_from(candidate['binding_inputs'])
    check(meta == read(checked(candidate['source_model'])), 'Fresh source model differs')
    check(len(candidate['units']) == len(candidate['complete_machine']) == 2 and [row['role'] for row in candidate['units']] == ['native','backend'], 'Exactly two ordered native/backend machine units required')
    check(candidate['inputs'] == expected_inputs(meta, candidate['binding_inputs'], checked(candidate['units'][0]['assembler'])) and
          candidate['units'][0]['assembler'] == candidate['units'][1]['assembler'], 'Required complete current input/assembler population differs')
    texts = [N.normal_frames(meta, list(range(7)))[0], backend(meta, checked(candidate['binding_inputs']['kernel']))[0]]
    output = Path(args.output).resolve()
    check(output.is_relative_to(ROOT / '.boom') and not output.exists(), 'Fresh isolated .boom verification output required')
    output.mkdir(parents=True)
    actuals = []
    for index, (text, row) in enumerate(zip(texts, candidate['units'])):
        check(text == checked(row['assembly']).read_text(encoding='utf-8') == checked(row['canonical_assembly']).read_text(encoding='utf-8'), 'Actual/canonical source is not fresh original projection')
        contract = declaration_contract(text)
        check(row['exports'] == contract['exports'] and row['imports'] == contract['imports'], 'Exact generated symbol metadata differs')
        actual_symbols(checked(row['object']), text)
        fresh = assemble(text, output / row['role'], checked(row['assembler']))
        normalized = O.normalized_coff(checked(row['object']))
        check(normalized == candidate['complete_machine'][index]['normalized'] == O.normalized_coff(checked(row['canonical_object'])) ==
            O.normalized_coff(checked(fresh['object'])), 'Full actual canonical/fresh machine differs')
        actuals.append(fresh)
    proof = dict(verified=True, scope='independent_fresh_source_and_complete_actual_canonical_COFF_only_not_guest',
        candidate=artifact(args.candidate), fresh_canonical=actuals, native_declarations=7, source_register_table=6,
        complete_machine_including_flags_symbols_aux_all_relocations_pdata_xdata=True,
        capabilities=capabilities(), SourceV_repeated=False, guest_executed=False, runtime_acceptance_complete=False)
    write(output / 'verification.json', proof)
    print(json.dumps(artifact(output / 'verification.json')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build')
    for key in ['state', 'source', 'parent', 'pinned', 'abi', 'records-source', 'kernel', 'release', 'output']:
        p.add_argument('--' + key, required=True)
    p.add_argument('--assembler', required=True)
    p = sub.add_parser('verify')
    p.add_argument('--candidate', required=True)
    p.add_argument('--output', required=True)
    args = parser.parse_args()
    (build if args.command == 'build' else verify)(args)
