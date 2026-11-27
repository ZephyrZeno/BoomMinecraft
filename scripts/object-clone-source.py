"""Original Object.clone source projection and reusable MASM renderers.

``index(summary, classes, selection, frame)`` resolves source declarations,
already selected Java callbacks, and the normal native Frame contract.
``native_assembly(metadata)`` and ``service_assembly(metadata)`` render the two
independent units. ``project``/the CLI write source artifacts only; they do not
assemble, link, register a provider, run a verifier, or execute Java.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'java/lang/Object'
POOL = 'boom_object_clone_pool'
SERVICE = 'boom_object_clone_service'
KERNEL = ROOT / 'native/providers/object_clone.asm.inc'
NAMES = {'java/lang/Object', 'java/lang/Cloneable', 'java/lang/CloneNotSupportedException',
         'java/lang/Class', 'java/lang/Throwable'}
KERNELS = ['heap.asm', 'runtime_types.asm', 'runtime_type_index.asm', 'objects.asm',
           'types.asm', 'exceptions.asm', 'java_classes.asm', 'classes32.asm', 'frames.asm']
POLICY = dict(fresh_allocation=True, exact_runtime_type=True, shallow_payload_copy=True,
              copy_object_header=False, call_constructor_for_clone=False,
              ordinary_object_requires_Cloneable=True, all_array_kinds_Cloneable=True,
              nonCloneable_exception='original_CloneNotSupportedException_String_constructor',
              exception_message='original_Class_getName', null_receiver='builtin_Context4',
              allocation_failure='builtin_Context3', invalid_VM_reference='builtin_Context7',
              existing_kind_or_pending_preserved=True, automatic_GC=False,
              GC_boundary='explicit_quiescent_only', persistent_oop_roots=[],
              runtime_type_capacity='dynamic_equal_RTYP_and_JCLS', registered=False)


def check(value, message):
    if not value:
        raise ValueError(message)


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=sha))


def checked(record):
    expected = record.get('digest', record)
    actual = artifact(record['path'])
    check(all(actual['digest'][key] == expected[key] for key in ('size', 'sha256')),
          'Original clone input changed: ' + record['path'])
    return Path(actual['path'])


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def module(name):
    spec = importlib.util.spec_from_file_location('object_clone_' + name.replace('-', '_'),
                                                 Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def index(summary, classes, selection, frame):
    """Bind an explicit original source selection; no epoch or numeric ID pins.

    ``summary`` is the original batch summary, ``classes`` its plan records,
    ``selection`` the selected Java closure, and ``frame`` a normal Frame-overlay
    manifest containing the original native declarations. Actual linked COFF
    slices and completed verification receipts belong to the consuming builder.
    """
    original = module('constructor-provider-source')
    raw_class = module('verify-translation-ir')
    owners = {c['name']: c for c in classes
              if c['origin']['loader'] == 'bootstrap' and c['name'] in NAMES}
    check(set(owners) == NAMES, 'Object.clone original source classes missing')
    check(all(c['origin']['source_id'] == 'jdk:java.base' and not c['origin'].get('generated')
              for c in owners.values()), 'Original java.base clone classes required')
    selected_classes = {c['class_id']: c for c in selection['selected_classes']}
    selected_methods = selection['selected_methods']
    roles, origins = {}, {}
    source = original.RawClasses(summary)
    try:
        for name, cls in owners.items():
            blob = source.read(cls)
            parsed = raw_class.Source(blob)
            check(parsed.name == name and len(parsed.methods) == len(cls['method_ids']) and
                  parsed.access == cls['access'] and parsed.fields == [
                      dict(f, constant_value=parsed.fields[i]['constant_value'])
                      for i, f in enumerate(cls['fields'])],
                  'Original clone Class declaration or inventory differs: ' + name)
            origins[name] = dict(class_id=cls['id'], origin=cls['origin'], access=parsed.access)
            specs = {
                OWNER: [('clone', '()Ljava/lang/Object;', 'clone')],
                'java/lang/Class': [('getName', '()Ljava/lang/String;', 'getName')],
                'java/lang/CloneNotSupportedException': [('<init>', '(Ljava/lang/String;)V', 'CNSE_String_ctor')]
            }.get(name, [])
            for method_name, descriptor, role in specs:
                matches = [(mid, method) for mid, method in zip(cls['method_ids'], parsed.methods)
                           if (method['name'], method['descriptor']) == (method_name, descriptor)]
                check(len(matches) == 1, 'Missing/ambiguous original clone method: ' + role)
                ident, method = matches[0]
                code = parsed.code(method)
                sha = hashlib.sha256(code['bytes']).hexdigest() if code else None
                row = dict(method=ident, class_id=cls['id'], owner=name, name=method_name,
                           descriptor=descriptor, access=method['access'], source_sha256=cls['origin']['sha256'],
                           code_sha256=sha, code_bytes=len(code['bytes']) if code else 0, symbol='boom_m' + str(ident))
                roles[role] = row
                if code:
                    expected = {key: row[key] for key in ('class_id', 'name', 'descriptor', 'code_sha256', 'source_sha256')}
                    check(selected_methods.get(str(ident)) == expected,
                          'Original clone Java callback must already be selected: ' + role)
    finally:
        source.close()
    clone = roles['clone']
    check(clone['access'] == 0x104 and clone['code_sha256'] is None,
          'Object.clone must be the original protected nonstatic native declaration')
    for name in (OWNER, 'java/lang/CloneNotSupportedException', 'java/lang/Class'):
        cls = owners[name]
        selected = selected_classes.get(cls['id'])
        check(selected and selected['source_sha256'] == cls['origin']['sha256'] and selected['diagnostic'] is None,
              'A selected normal clone callback Class descriptor is required: ' + name)
    declarations = frame['source']['original_native_declarations']
    matches = [row for row in declarations if row['id'] == clone['method']]
    check(len(matches) == 1, 'Original Object.clone native Frame declaration missing/ambiguous')
    native = matches[0]
    check(native['flags'] == 32 and native['class_id'] == clone['class_id'] and
          native['class_sha256'] == clone['source_sha256'] and native['class_name'] == OWNER and
          native['name'] == clone['name'] and native['descriptor'] == clone['descriptor'] and
          native['access'] == clone['access'], 'Available original Object.clone Frame32 differs')
    types = {}
    with zipfile.ZipFile(checked(summary['runtime_metadata']['index'])) as archive:
        wanted = {c['id'] for c in owners.values()}
        for line in archive.open('types.jsonl'):
            row = json.loads(line)
            if row['id'] in wanted:
                check(row['id'] not in types, 'Duplicate original clone TYPE')
                types[row['id']] = row
    for name, cls in owners.items():
        typ = types.get(cls['id'])
        check(typ and typ['name'] == name and typ['source_sha256'] == cls['origin']['sha256'],
              'Provided original clone TYPE differs: ' + name)
    cloneable, throwable = owners['java/lang/Cloneable']['id'], owners['java/lang/Throwable']['id']
    check(types[cloneable]['kind'] == 2 and types[cloneable]['marker_flags'] == 2,
          'Original Cloneable interface/array marker differs')
    return dict(schema=1, scope='original_Object_clone_source_roles_only', owner=clone['class_id'],
                original_classes=origins, roles=roles, methods=[dict(clone, operation=0)],
                Cloneable_type=types[cloneable], Throwable_type=types[throwable],
                exception_class=owners['java/lang/CloneNotSupportedException']['id'],
                original_native_declaration=native, context_bytes=32, native_Frame_ABI=3,
                native_Frame_row_changes=[], required_java_methods=sorted(
                    roles[key]['method'] for key in ('getName', 'CNSE_String_ctor')),
                pool_symbol=POOL, service_symbol=SERVICE, pool_bytes=96, pool_abi=1,
                required_classes=sorted(c['id'] for c in owners.values()), policy=POLICY,
                original_Java_Code_changed=False, additional_oop_roots=[], registered=False,
                runtime_acceptance_complete=False)


def data(metadata):
    cnse = metadata['exception_class']
    cloneable = metadata['Cloneable_type']['id']
    throwable = metadata['Throwable_type']['id']
    roles = metadata['roles']
    return (f'.const\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 04E4C434Fh,1,96,0\n'
            f' QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_t{cloneable},OFFSET boom_java_class_pool\n'
            f" QWORD OFFSET boom_class{cnse},OFFSET boom_layout{cnse},OFFSET {roles['CNSE_String_ctor']['symbol']},OFFSET {roles['getName']['symbol']}\n"
            f' QWORD OFFSET boom_t{throwable},0\n')


def native_imports(metadata):
    clone = metadata['roles']['clone']
    procedures = {'boom_class_ensure32', 'boom_trace_enter', 'boom_trace_leave', SERVICE}
    values = {'boom_class' + str(clone['class_id']), 'boom_trace_method' + str(clone['method']), 'boom_trace_pool', POOL}
    return procedures, values


def service_imports(metadata):
    roles = metadata['roles']
    procedures = {'boom_heap_contains', 'boom_runtime_row', 'boom_type_assignable', 'boom_heap_alloc',
                  'boom_java_class_load', 'boom_class_ensure32', 'boom_object_new', 'boom_exception_set32',
                  roles['getName']['symbol'], roles['CNSE_String_ctor']['symbol']}
    values = {'boom_heap_ptr', 'boom_runtime_type_map', 'boom_java_class_pool',
              'boom_t' + str(metadata['Cloneable_type']['id']), 'boom_t' + str(metadata['Throwable_type']['id']),
              'boom_class' + str(metadata['exception_class']), 'boom_layout' + str(metadata['exception_class'])}
    return procedures, values


def _imports(procedures, values):
    check(not procedures & values, 'Clone source symbol has conflicting procedure/data roles')
    return ''.join('EXTERN ' + name + ':' + ('PROC' if name in procedures else 'BYTE') + '\n'
                   for name in sorted(procedures | values))


def native_assembly(metadata):
    """Render the existing normal native Frame ABI, using original numeric IDs."""
    frames = module('verify-batch-frames')
    clone = metadata['roles']['clone']
    procedures, values = native_imports(metadata)
    return ('option casemap:none\n' + _imports(procedures, values) +
            'PUBLIC ' + clone['symbol'] + '\nPUBLIC ' + clone['symbol'] + '_native\n' +
            frames.native_adapter(clone['method'], clone['class_id'], POOL, SERVICE, 0) + '\nEND\n')


def service_assembly(metadata):
    """Render only source-bound readonly pool values and the reusable MASM core."""
    procedures, values = service_imports(metadata)
    return ('option casemap:none\n' + _imports(procedures, values) + data(metadata) +
            KERNEL.read_text(encoding='utf-8') + '\nEND\n')


def render(metadata):
    return {'object-clone-native': native_assembly(metadata), 'object-clone-service': service_assembly(metadata)}


def project(summary_file, classes_file, source_file, frame_file, source_verification=None):
    """Read explicit original input artifacts and return a source-only projection."""
    summary, selection, frame = map(read, (summary_file, source_file, frame_file))
    classes = [json.loads(line) for line in Path(classes_file).read_text(encoding='utf-8').splitlines()]
    summary_ref, source_ref = artifact(summary_file), artifact(source_file)
    check(selection['source_batch_summary_sha256'] == summary_ref['digest']['sha256'],
          'Clone source selection belongs to a different original batch')
    check(artifact(Path(selection['plan']) / 'classes.jsonl') == artifact(classes_file),
          'Clone source selection belongs to a different original class plan')
    if source_verification is not None:
        proof = read(source_verification)
        check(proof['verified'] is True and proof['closure_manifest_sha256'] == source_ref['digest']['sha256'],
              'Explicit completed source verification does not bind this selection')
    metadata = index(summary, classes, selection, frame)
    metadata['inputs'] = dict(batch_summary=summary_ref, original_class_plan=artifact(classes_file), source_selection=source_ref,
                             native_Frame_source=artifact(frame_file), kernel=artifact(KERNEL), renderer=artifact(__file__))
    metadata['source_full_verification'] = artifact(source_verification) if source_verification is not None else None
    metadata['machine_or_behavior_verified'] = False
    return metadata


def main(args):
    output = args.output.resolve()
    check(any(output.is_relative_to(ROOT / name) for name in ('.boom', 'target', 'dist')),
          'Clone source output must remain in project .boom, target, or dist')
    check(not output.exists(), 'Clone source output must be create-new')
    metadata = project(args.batch_summary, args.classes, args.source, args.frames, args.source_verification)
    assembly = render(metadata)
    output.mkdir(parents=True)
    files = {}
    for role, text in assembly.items():
        path = output / (role + '.asm')
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
        files[role] = artifact(path)
    metadata_file = output / 'metadata.json'
    with metadata_file.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(metadata, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(metadata=artifact(metadata_file), assembly=files,
                          machine_or_behavior_verified=False, registered=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('batch-summary', 'classes', 'source', 'frames', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--source-verification', type=Path)
    main(parser.parse_args())
