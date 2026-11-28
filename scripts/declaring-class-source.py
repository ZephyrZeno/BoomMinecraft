"""Original declaring-Class catalogue, normal metadata and MASM source API.

original_nesting/cataloque use the maintained original Class/MUTF8 readers and
enclosing source API. catalogue rebuilds own/reciprocal relationships using
actual defining-loader resolution; metadata binds normal Frames and callbacks.
project accepts explicit files, including runtime types and optional generated
Class expansion/full Source verification. No API assembles or executes Java.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tomllib

MODULES = {}
FRAGMENT = 'native/providers/declaring_class.asm.inc'
ABI_FILE = 'native-config/declaring-class-abi.json'
POOL = 'boom_declaring_class_pool'
SERVICE = 'boom_declaring_class_service'
OWNER = 'java/lang/Class'
NATIVE = ('getDeclaringClass0', '()Ljava/lang/Class;')


def check(value, message):
    if not value:
        raise ValueError(message)


def installed_root():
    for path in Path(__file__).resolve().parents:
        cargo = path / 'Cargo.toml'
        if (cargo.is_file() and (path / 'scripts/constructor-provider-source.py').is_file()
                and (path / 'native/runtime/java_classes.asm').is_file()):
            with cargo.open('rb') as stream:
                package = tomllib.load(stream).get('package', {})
            if package.get('name') == 'boom-minecraft':
                return path
    raise ValueError('Installed project source/tool root not found')


def module(name):
    if name not in MODULES:
        spec = importlib.util.spec_from_file_location('declaring_' + name.replace('-', '_'), installed_root() / 'scripts' / (name + '.py'))
        value = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(value)
        MODULES[name] = value
    return MODULES[name]


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=sha))


def checked(value):
    actual = artifact(value['path'])
    check(all(actual['digest'][key] == value['digest'][key] for key in ('size', 'sha256')),
          'Explicit original source changed: ' + value['path'])
    return Path(actual['path'])


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def class_descriptor(name):
    return name if name.startswith('[') else 'L' + name + ';'


def original_nesting(data, expected_name):
    """Use the existing raw Class/MUTF8 reader, retaining ordered entries."""
    I = module('verify-translation-ir')
    parsed = I.Source(data)
    check(parsed.name == expected_name, 'Original nesting Class name differs')
    attributes = [body for name, body in parsed.attrs if name == 'InnerClasses']
    check(len(attributes) <= 1, 'Duplicate original InnerClasses attribute')
    rows = []
    if attributes:
        reader = I.Reader(attributes[0])
        for _ in range(reader.u2()):
            inner, outer, name, flags = [reader.u2() for _ in range(4)]
            rows.append(dict(inner_name=parsed.class_name(inner) if inner else None, outer_name=parsed.class_name(outer) if outer else None,
                             simple_name=parsed.text(name) if name else None, access=flags,
                             inner_index=inner, outer_index=outer, name_index=name))
        check(reader.position == len(attributes[0]), 'Original InnerClasses attribute length differs')
    own = [row for row in rows if row['inner_name'] == expected_name]
    check(len(own) <= 1, 'Duplicate own InnerClasses entry')
    enclosing = module('enclosing-method-source').parse_enclosing(data, expected_name=expected_name)
    return dict(name=expected_name, entries=rows, own=own[0] if own else None,
                enclosing=enclosing, original_InnerClasses=attributes[0].hex() if attributes else None)


def catalogue(summary, classes, selection, generated_expansion=None, *, type_inputs=None):
    """Resolve nesting in actual namespaces, including reverse Class identity."""
    C = module('constructor-provider-source')
    classes = list(classes)
    check([row['id'] for row in classes] == list(range(len(classes))), 'Original Class plan must be dense')
    if type_inputs is None:
        type_inputs = C.inputs(summary, classes)
    types, runtime, available, resolve = type_inputs
    capacity = summary['runtime_metadata']['type_capacity']
    selected = {row['class_id'] for row in selection['selected_classes']}
    raw = C.RawClasses(summary)
    nesting, identities = {}, {}
    try:
        for cls in classes:
            nesting[cls['id']] = original_nesting(raw.read(cls), cls['name'])
            identities[cls['id']] = dict(type_id=cls['id'], name=cls['name'], loader=cls['origin']['loader'],
                Class_SHA=cls['origin']['sha256'], available=cls['id'] in available and not cls.get('parse_error') and not cls['access'] & 0x8000,
                source_selected=cls['id'] in selected)
    finally:
        raw.close()
    generated = generated_expansion['generated'] if generated_expansion is not None else []
    if generated_expansion is not None:
        check(generated_expansion['appended_ranges']['types'] == [capacity, capacity + len(generated)],
              'Generated Classes must append the exact explicit source type range')
    for cls in generated:
        data = checked(cls['class_file']).read_bytes()
        check(hashlib.sha256(data).hexdigest() == cls['origin']['sha256'], 'Actual generated Class SHA differs')
        check(cls['type_id'] == capacity + len(identities) - len(classes), 'Generated Class IDs must append in source order')
        nesting[cls['type_id']] = original_nesting(data, cls['type']['name'])
        identities[cls['type_id']] = dict(type_id=cls['type_id'], name=cls['type']['name'], loader=cls['origin']['loader'],
            Class_SHA=cls['origin']['sha256'], available=True, source_selected=False, generated_Class=cls['class_file'])
    entries = []
    for ident in range(capacity + len(generated)):
        if ident not in identities:
            entries.append(dict(type_id=ident, status=0 if ident in available else 3, outer_type=None,
                                member=False, error=None, reason='non-instance' if ident in available else 'unavailable type'))
            continue
        source = identities[ident]
        record = nesting[ident]
        own = record['own']
        own_resolved = resolve(source['loader'], class_descriptor(own['inner_name'])) if own else None
        own_matches = own is not None and own_resolved == ident
        # The explicit own InnerClasses outer wins over EnclosingMethod.
        member = bool(own_matches and own['outer_name'])
        outer_name = own['outer_name'] if member else (
            record['enclosing']['enclosing_class_name'] if own_matches else None)
        status, outer, error, reason = 0, None, None, 'no outer'
        if not source['available']:
            status, reason = 3, 'unavailable instance metadata'
        elif own is not None and own_resolved is None:
            status, reason = 3, 'unavailable own InnerClasses Class resolution'
        elif outer_name is not None:
            outer = resolve(source['loader'], class_descriptor(outer_name))
            if outer is None:
                status, reason = 3, 'unavailable enclosing Class resolution'
            elif outer not in identities:
                status, reason = 4, 'outer is not an instance class'
                error = outer_name.replace('/', '.') + ' and ' + source['name'].replace('/', '.') + ' disagree on InnerClasses attribute'
            elif not identities[outer]['available']:
                status, reason = 3, 'unavailable outer instance metadata'
            else:
                reverse = nesting[outer]
                outer_source = identities[outer]
                matched = unresolved = False
                for row in reverse['entries']:
                    if row['inner_name'] != source['name']:
                        continue
                    if member:
                        if row['outer_name'] != outer_source['name']:
                            continue
                        other_outer = resolve(outer_source['loader'], class_descriptor(row['outer_name']))
                        if other_outer is None:
                            unresolved = True
                            break
                        if other_outer != outer:
                            continue
                    elif row['outer_name'] is not None:
                        continue
                    other_inner = resolve(outer_source['loader'], class_descriptor(row['inner_name']))
                    if other_inner is None:
                        unresolved = True
                        break
                    if other_inner != ident:
                        continue
                    matched = True
                    break
                if matched:
                    status, reason = (1, 'consistent member') if member else (2, 'consistent nonmember')
                elif unresolved:
                    status, reason = 3, 'unavailable reciprocal Class resolution'
                else:
                    status, reason = 4, 'reverse InnerClasses identity mismatch'
                    error = outer_source['name'].replace('/', '.') + ' and ' + source['name'].replace('/', '.') + ' disagree on InnerClasses attribute'
        entries.append(dict(type_id=ident, status=status, outer_type=outer, member=member, error=error, reason=reason,
                            original_Class=source, original_InnerClasses=record['original_InnerClasses'],
                            original_EnclosingMethod=record['enclosing']['original_attribute_hex'], outer_source_name=outer_name))
    from collections import Counter
    return dict(schema=1, entries=entries, counts=dict(types=len(entries), original_classes=len(classes), generated_classes=len(generated),
                statuses=dict(Counter(row['status'] for row in entries)), reasons=dict(Counter(row['reason'] for row in entries))))


def metadata(summary, classes, selection, frame, layouts, directory, *, type_inputs=None):
    classes = list(classes)
    C, I = module('constructor-provider-source'), module('verify-translation-ir')
    check(selection['source_input_fingerprint'] == summary['input_fingerprint'] and
          selection['source_frame_abi'] == summary['frames']['abi'] == frame['pool_abi'] == 3 and
          frame['method_row_bytes'] == 32, 'Normal source/Frame ABI identity differs')
    check(all(frame['source']['base_frame_index']['digest'][key] == summary['frames']['index']['digest'][key]
              for key in ('size', 'sha256')), 'Original Frame index differs from source batch')
    names = {(row['origin']['loader'], row['name']): row for row in classes}
    owners = {name: names['bootstrap', name] for name in
              (OWNER, 'java/lang/String', 'java/lang/IncompatibleClassChangeError', 'java/lang/Throwable')}
    selected = {row['class_id']: row for row in selection['selected_classes']}
    for name in (OWNER, 'java/lang/String', 'java/lang/IncompatibleClassChangeError'):
        original = owners[name]
        check(original['id'] in selected and selected[original['id']]['diagnostic'] is None and
              selected[original['id']]['source_sha256'] == original['origin']['sha256'],
              'Normally selected Class descriptor required: ' + name)
    wanted = {row['id'] for row in owners.values()}
    normal_layouts = {row['class_id']: row for row in layouts if row['class_id'] in wanted}
    for name in ('java/lang/String', 'java/lang/IncompatibleClassChangeError'):
        layout = normal_layouts[owners[name]['id']]
        check(layout['diagnostic'] is None and layout['candidate'], 'Normal source object layout required: ' + name)
    native = constructor = None
    reader = C.RawClasses(summary)
    try:
        for name in (OWNER, 'java/lang/IncompatibleClassChangeError'):
            original = owners[name]
            parsed = I.Source(reader.read(original))
            check(parsed.name == name and len(parsed.methods) == len(original['method_ids']), 'Original declaration ordering differs')
            for ident, member in zip(original['method_ids'], parsed.methods):
                signature = (member['name'], member['descriptor'])
                code = parsed.code(member)
                if name == OWNER and signature == NATIVE:
                    check(native is None and member['access'] == 0x102 and code is None, 'Original private native declaration required')
                    native = dict(method=ident, class_id=original['id'], owner=name, name=signature[0], descriptor=signature[1],
                                  access=member['access'], class_sha256=original['origin']['sha256'], code_sha256=None, operation=0)
                if name == 'java/lang/IncompatibleClassChangeError' and signature == ('<init>', '(Ljava/lang/String;)V'):
                    check(constructor is None and code is not None, 'Original ICCE(String) Code required')
                    constructor = dict(method=ident, class_id=original['id'], owner=name, name=signature[0], descriptor=signature[1],
                                       source_sha256=original['origin']['sha256'], code_sha256=hashlib.sha256(code['bytes']).hexdigest())
                    check(selection['selected_methods'].get(str(ident)) == {key: constructor[key] for key in
                          ('class_id', 'name', 'descriptor', 'source_sha256', 'code_sha256')} and
                          selection['selected_function_sha256'].get('boom_m' + str(ident) + '_body'),
                          'Original ICCE(String) must already be genuinely selected/provided')
    finally:
        reader.close()
    check(native and constructor, 'Original native or selected typed-error constructor missing')
    declarations = [row for row in frame['source']['original_native_declarations'] if row['id'] == native['method']]
    check(len(declarations) == 1, 'Original normal native Frame declaration missing or ambiguous')
    declaration = declarations[0]
    check(declaration['flags'] == 32 and all(declaration[key] == native[key] for key in
          ('class_id', 'class_sha256', 'name', 'descriptor', 'access')), 'Original native Frame32 declaration differs')
    check([row for row in frame['source']['rows'] if row[0] == native['method']] ==
          [[native['method'], 32, native['class_id'], 0]], 'Original native MethodRow32 source differs')
    string = owners['java/lang/String']
    string_fields = normal_layouts[string['id']]['candidate']['fields']

    def offset(name, descriptor, width, reference):
        rows = [row for row in string_fields if (row['member']['owner'], row['member']['name'], row['member']['descriptor']) ==
                (string['id'], name, descriptor)]
        check(len(rows) == 1 and rows[0]['storage_bytes'] == width and rows[0]['reference'] is reference,
              'Original packed String field storage differs: ' + name)
        return rows[0]['offset']

    if type_inputs is None:
        type_inputs = C.inputs(summary, classes)
    types, runtime, _, _ = type_inputs
    by_name = {(row['defining_loader'], row['name']): row for row in types}
    by_type = {row['type_id']: row for row in runtime}
    byte_array = by_type[by_name['bootstrap', '[B']['id']]
    check(byte_array['primitive_tag'] == 264, 'Original byte-array heap ABI differs')
    return dict(schema=1, methods=[native], original_native_declaration=declaration, original_native_declarations=[declaration],
                rows=directory['entries'], directory_counts=directory['counts'],
                Class_class=owners[OWNER]['id'], String_class=string['id'], String_layout=normal_layouts[string['id']],
                ICCE_class=owners['java/lang/IncompatibleClassChangeError']['id'],
                ICCE_layout=normal_layouts[owners['java/lang/IncompatibleClassChangeError']['id']], ICCE_constructor=constructor,
                Throwable_type=owners['java/lang/Throwable']['id'], string_value_offset=offset('value', '[B', 8, True),
                string_coder_offset=offset('coder', 'B', 1, False), compact_strings=summary['string_literals']['compact_strings'],
                byte_array_tag=byte_array['primitive_tag'], pool_bytes=160, pool_abi=1, row_bytes=32,
                additional_oop_roots=[], original_Java_Code_changed=False, registered_pack=False,
                represented_or_declaring_Class_initialized=False, automatic_or_concurrent_GC_supported=False,
                invalid_Classfile_admission_is_not_implemented_by_this_native=True)


def data(meta):
    text = ['.const\nALIGN 8\nPUBLIC ' + POOL + '\n',
            f"{POOL} DWORD 044434C52h,1,{len(meta['rows'])},32\n",
            ' QWORD OFFSET boom_java_class_pool,OFFSET boom_heap_ptr,OFFSET dclr_rows\n',
            f" QWORD OFFSET boom_class{meta['ICCE_class']},OFFSET boom_layout{meta['ICCE_class']},OFFSET boom_m{meta['ICCE_constructor']['method']}\n",
            f" QWORD OFFSET boom_t{meta['Throwable_type']},OFFSET boom_runtime_type_map,OFFSET boom_layout{meta['String_class']},OFFSET boom_class{meta['String_class']}\n",
            f" DWORD {meta['string_value_offset']},{meta['string_coder_offset']},{int(meta['compact_strings'])},160,{meta['directory_counts']['original_classes']},0\n",
            ' QWORD 0,0,0,0,0\nALIGN 8\ndclr_rows LABEL BYTE\n']
    messages = []
    for row in meta['rows']:
        target = row['outer_type'] if row['outer_type'] is not None else 0xffffffff
        text.append(f" DWORD {row['status']},{target}\n")
        if row['status'] == 4:
            label = 'dclr_error_' + str(row['type_id'])
            encoded = row['error'].encode('utf-16-le', 'surrogatepass')
            check(len(encoded) // 2 <= 65535, 'Native error message exceeds supported source String bound')
            text.append(f" QWORD OFFSET {label}\n DWORD {len(encoded)//2},{int(row['reason']=='outer is not an instance class')}\n QWORD 0\n")
            messages.append('ALIGN 2\n' + label + ' LABEL BYTE\n')
            for at in range(0, len(encoded), 16):
                messages.append(' BYTE ' + ','.join(map(str, encoded[at:at+16])) + '\n')
        else:
            text.append(' QWORD 0\n DWORD 0,0\n QWORD 0\n')
    return ''.join(text + messages)


def native_assembly(meta):
    [native] = meta['methods']
    procedures = {'boom_class_ensure32', 'boom_trace_enter', 'boom_trace_leave', SERVICE}
    values = {'boom_trace_pool', POOL, 'boom_class' + str(native['class_id']), 'boom_trace_method' + str(native['method'])}
    text = 'option casemap:none\n' + ''.join('EXTERN ' + name + ':' + ('PROC' if name in procedures else 'BYTE') + '\n'
                                             for name in sorted(procedures | values))
    return text + f"PUBLIC boom_m{native['method']}\nPUBLIC boom_m{native['method']}_native\n" + module('verify-batch-frames').native_adapter(
        native['method'], native['class_id'], POOL, SERVICE, 0) + '\nEND\n'


def fragment_path():
    return Path(__file__).resolve().parents[1] / FRAGMENT


def service_assembly(meta, fragment=None):
    procedures = {'boom_heap_alloc', 'boom_object_new', 'boom_java_class_typeid', 'boom_java_class_load',
                  'boom_class_ensure32', 'boom_exception_set32', 'boom_m' + str(meta['ICCE_constructor']['method'])}
    values = {'boom_java_class_pool', 'boom_heap_ptr', 'boom_runtime_type_map', 'boom_class' + str(meta['ICCE_class']),
              'boom_layout' + str(meta['ICCE_class']), 'boom_t' + str(meta['Throwable_type']),
              'boom_class' + str(meta['String_class']), 'boom_layout' + str(meta['String_class'])}
    return 'option casemap:none\n' + ''.join('EXTERN ' + name + ':' + ('PROC' if name in procedures else 'BYTE') + '\n'
                                             for name in sorted(procedures | values)) + data(meta) + (
        fragment_path().read_text(encoding='utf-8') if fragment is None else fragment) + '\nEND\n'


def render(meta, fragment=None):
    return {'declaring-class-native': native_assembly(meta), 'declaring-class-service': service_assembly(meta, fragment)}


def project(summary_file, classes_file, selection_file, frame_file, layouts_file, runtime_types_file, *,
            generated_expansion_file=None, source_verification=None):
    """Rebuild raw nesting and source only; an existing fullV link is optional."""
    summary, selection, frame = map(read, (summary_file, selection_file, frame_file))
    paths = dict(summary=summary_file, classes=classes_file, selection=selection_file, frame=frame_file,
                 layouts=layouts_file, runtime_types=runtime_types_file)
    references = {name: artifact(path) for name, path in paths.items()}
    check(selection['source_batch_summary_sha256'] == references['summary']['digest']['sha256'] and
          selection['source_classes_sha256'] == references['classes']['digest']['sha256'],
          'Explicit selected source/summary/original Class plan differs')
    for name, original in [('layouts', summary['layouts']), ('runtime_types', summary['runtime_metadata']['index'])]:
        check(all(references[name]['digest'][key] == original['digest'][key] for key in ('size', 'sha256')) and
              Path(paths[name]).resolve() == checked(original), 'Explicit original runtime/layout input differs: ' + name)
    if source_verification is not None:
        proof = read(source_verification)
        check(proof.get('verified') is True and proof['closure_manifest_sha256'] == references['selection']['digest']['sha256'],
              'Existing completed full source verification must bind this exact selection')
    with Path(classes_file).open(encoding='utf-8') as stream:
        classes = [json.loads(line) for line in stream]
    expansion = read(generated_expansion_file) if generated_expansion_file is not None else None
    type_inputs = module('constructor-provider-source').inputs(summary, classes)
    directory = catalogue(summary, classes, selection, expansion, type_inputs=type_inputs)
    with Path(layouts_file).open(encoding='utf-8') as stream:
        meta = metadata(summary, classes, selection, frame, (json.loads(line) for line in stream),
                        directory, type_inputs=type_inputs)
    [native] = meta['methods']
    references.update(source_library=artifact(__file__), fragment=artifact(fragment_path()),
                      ABI=artifact(Path(__file__).resolve().parents[1] / ABI_FILE))
    if generated_expansion_file is not None:
        references['generated_expansion'] = artifact(generated_expansion_file)
    meta.update(inputs=references, source_manifest=references['selection'],
                source_full_verification=artifact(source_verification) if source_verification is not None else None,
                source_admission_verified=source_verification is not None,
                physical_original_Frame=module('enclosing-method-source').frame_row_physical(
                    checked(frame['object']), native['method'], native['class_id']),
                machine_or_behavior_verified=False,
                original_ICCE_source_count=sum(row['status'] == 4 for row in directory['entries']),
                ICCE_branch_AOT_behavior_verified=False, invalid_Classfile_admission_implemented=False)
    meta['source_library_dependencies'] = {
        name: artifact(installed_root() / 'scripts' / (name + '.py')) for name in
        ('constructor-provider-source', 'verify-translation-ir', 'verify-batch-frames',
         'verify-batch-metadata', 'system-class-inputs', 'enclosing-method-source')}
    return meta, directory


def output_target(value):
    target, base = Path(value).resolve(), installed_root()
    check(any(target.is_relative_to(base / name) for name in ('.boom', 'target', 'dist')),
          'Generated source output must stay in this installed project .boom, target or dist')
    check(not target.exists(), 'Generated source output must be create-new')
    return target


def main(args):
    # Reject invalid output before reading any source model or creating files.
    # The CLI cannot change the installed repository root.
    output = output_target(args.output)
    meta, directory = project(args.summary, args.classes, args.selection, args.frames, args.layouts, args.runtime_types,
                              generated_expansion_file=args.generated_expansion, source_verification=args.source_verification)
    assembly = render(meta)
    output.mkdir(parents=True)
    for name, value in [('source.json', meta), ('catalog.json', directory)]:
        with (output / name).open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
    for role, text in assembly.items():
        with (output / (role + '.asm')).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    print(json.dumps(dict(source_model=artifact(output / 'source.json'), catalog=artifact(output / 'catalog.json'),
                          source_only=True, machine_or_behavior_verified=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('summary', 'classes', 'selection', 'frames', 'layouts', 'runtime-types', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--generated-expansion', type=Path)
    parser.add_argument('--source-verification', type=Path)
    main(parser.parse_args())
