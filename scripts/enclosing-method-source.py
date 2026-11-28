"""Original Class EnclosingMethod catalogue, normal metadata and MASM renderers.

parse_enclosing/project_class reuse the original Class/MUTF8 source reader.
catalog rebuilds a dense directory from explicit original inputs and optional
source-hashed generated Class bytes. metadata binds normal Class/Frame/layout
semantics; render emits two source units. No API compiles, registers or executes
Java, and an existing full source proof remains separate from behavior evidence.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tomllib

FRAGMENT = 'native/providers/enclosing_method.asm.inc'
ABI_FILE = 'native-config/enclosing-method-abi.json'
POOL = 'boom_enclosing_method_pool'
SERVICE = 'boom_enclosing_method_service'
OWNER = 'java/lang/Class'
NATIVE = ('getEnclosingMethod0', '()[Ljava/lang/Object;')
STATUS = {'absent': 0, 'with_method': 1, 'class_only': 2, 'unsupported': 3}
MODULES = {}


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


def module(name, root=None):
    base = installed_root() if root is None else Path(root).resolve()
    key = (str(base), name)
    if key in MODULES:
        return MODULES[key]
    spec = importlib.util.spec_from_file_location('enclosing_' + name.replace('-', '_'), base / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    MODULES[key] = result
    return result


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=sha))


def checked(value):
    actual = artifact(value['path'])
    check(all(actual['digest'][key] == value['digest'][key] for key in ('size', 'sha256')),
          'Explicit source artifact changed: ' + value['path'])
    return Path(actual['path'])


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def parse_enclosing(data, *, expected_name=None, root=None):
    """Decode the original four-byte attribute using the existing Class parser."""
    parsed = module('verify-translation-ir', root).Source(data)
    check(expected_name is None or parsed.name == expected_name, 'Original enclosing Class name differs')
    attributes = [body for name, body in parsed.attrs if name == 'EnclosingMethod']
    check(len(attributes) <= 1, 'Duplicate original EnclosingMethod attribute')
    if not attributes:
        return dict(status='absent', original_attribute_hex=None, enclosing_class_name=None,
                    class_index=0, method_index=0, method_name=None, method_descriptor=None)
    [body] = attributes
    check(len(body) == 4, 'EnclosingMethod attribute payload must be exactly four bytes')
    owner, method = struct.unpack('>HH', body)
    check(owner != 0, 'EnclosingMethod requires a nonzero original Class constant')
    holder = parsed.class_name(owner)
    name = descriptor = None
    if method:
        check(0 < method < len(parsed.cp) and parsed.cp[method][0] == 12,
              'EnclosingMethod method_index must reference NameAndType')
        name_index, descriptor_index = parsed.cp[method][1]
        name, descriptor = parsed.text(name_index), parsed.text(descriptor_index)
        check(descriptor.startswith('(') and ')' in descriptor,
              'EnclosingMethod descriptor must be a method descriptor')
    return dict(status='with_method' if method else 'class_only', original_attribute_hex=body.hex(),
                enclosing_class_name=holder, class_index=owner, method_index=method,
                method_name=name, method_descriptor=descriptor)


def project_class(data, type_id, loader, resolve, original_sha, metadata_available,
                  selected=False, *, expected_name=None, root=None):
    """Project one hash-checked Class using its actual defining-loader resolver."""
    check(hashlib.sha256(data).hexdigest() == original_sha, 'Original enclosing Class SHA differs')
    parsed = parse_enclosing(data, expected_name=expected_name, root=root)
    holder = resolve(loader, 'L' + parsed['enclosing_class_name'] + ';') if parsed['enclosing_class_name'] else None
    status = parsed['status'] if metadata_available else 'unsupported'
    if parsed['status'] != 'absent' and holder is None:
        status = 'unsupported'
    return dict(type_id=type_id, status=status, raw_attribute_status=parsed['status'], holder_type_id=holder,
                method_name=parsed['method_name'], method_descriptor=parsed['method_descriptor'], original_Class_SHA=original_sha,
                original_attribute_hex=parsed['original_attribute_hex'], loader_key=loader, metadata_available=metadata_available,
                selected_original_Java_Class=selected, enclosing_class_name=parsed['enclosing_class_name'],
                original_class_index=parsed['class_index'], original_method_index=parsed['method_index'])


def catalog(summary, classes, selection, generated_expansion=None, *, type_inputs=None, root=None):
    """Rebuild the original catalogue; unknown metadata is never a null result.

    type_inputs, when supplied, is the ordinary constructor source API tuple
    (types,runtime,available,resolve). Its resolver retains original loader
    namespaces. Otherwise it is derived from summary's hash-bound type archive.
    Every original/generated raw Class is checked before parsing. A corrupt
    source input raises; unavailable normal metadata is an explicit status3.
    """
    classes = list(classes)
    check([row['id'] for row in classes] == list(range(len(classes))), 'Original Class plan is not dense')
    C = module('constructor-provider-source', root)
    if type_inputs is None:
        type_inputs = C.inputs(summary, classes)
    types, _, available, resolve = type_inputs
    capacity = summary['runtime_metadata']['type_capacity']
    check(len(classes) <= capacity, 'Original type capacity is smaller than the Class plan')
    type_map = {row['id']: row for row in types}
    selected = {row['class_id'] for row in selection['selected_classes']}
    entries = [dict(type_id=ident, status='absent' if ident in available else 'unsupported', holder_type_id=None,
                    method_name=None, method_descriptor=None, original_Class_SHA=type_map.get(ident, {}).get('source_sha256'),
                    original_attribute_hex=None, loader_key=type_map.get(ident, {}).get('defining_loader'),
                    metadata_available=ident in available, type_kind=type_map.get(ident, {}).get('kind'),
                    scope='primitive_or_array' if ident >= len(classes) else 'original_class_pending')
               for ident in range(capacity)]
    attributes = []
    reader = C.RawClasses(summary)
    try:
        for cls in classes:
            row = project_class(reader.read(cls), cls['id'], cls['origin']['loader'], resolve, cls['origin']['sha256'],
                                cls['id'] in available and not cls.get('parse_error') and not cls['access'] & 0x8000,
                                cls['id'] in selected, expected_name=cls['name'], root=root)
            row.update(name=cls['name'], source_id=cls['origin']['source_id'], scope='original_locked_Class')
            entries[cls['id']] = row
            if row['original_attribute_hex'] is not None:
                attributes.append(row)
    finally:
        reader.close()
    generated_proofs = []
    if generated_expansion is not None:
        generated = generated_expansion['generated']
        check(generated_expansion['appended_ranges']['types'] == [capacity, capacity + len(generated)],
              'Generated types must be the exact explicit appended range')
        for cls in generated:
            source = checked(cls['class_file'])
            row = project_class(source.read_bytes(), cls['type_id'], cls['origin']['loader'], resolve,
                                cls['origin']['sha256'], True, False, expected_name=cls['type']['name'], root=root)
            row.update(name=cls['type']['name'], source_id=cls['origin']['source_id'], scope='actual_generated_Class',
                       source_class_file=cls['class_file'], original_Java_class_selection_not_claimed=True)
            check(cls['type_id'] == len(entries), 'Generated type ID does not match appended source order')
            entries.append(row)
            generated_proofs.append(dict(type_id=cls['type_id'], original_generated_bytes=cls['class_file'],
                                         raw_EnclosingMethod=row['original_attribute_hex'], status=row['status']))
    counts = dict(entries=len(entries), original_classes=len(classes), original_type_capacity=capacity,
                  original_available_types=len(types), generated_classes=len(generated_proofs), current_type_capacity=len(entries),
                  statuses=dict(Counter(row['status'] for row in entries)), original_Class_attributes=len(attributes),
                  attribute_loader_counts=dict(Counter(row['loader_key'] for row in attributes)), explicit_projection_errors=0)
    return dict(schema=1, entries=entries, generated_Class_proofs=generated_proofs, counts=counts,
                class_lookup_uses_actual_source_namespace=True, no_unknown_namespace_tail_assumed_null=True,
                original_Class_raw_sha_verified=True, machine_or_behavior_verified=False)


def metadata(summary, classes, selection, frame, layouts, directory=None, *,
             generated_expansion=None, type_inputs=None, root=None):
    classes = list(classes)
    C, I = module('constructor-provider-source', root), module('verify-translation-ir', root)
    check(selection['source_input_fingerprint'] == summary['input_fingerprint'] and
          selection['source_frame_abi'] == summary['frames']['abi'] == frame['pool_abi'] == 3 and
          frame['method_row_bytes'] == 32, 'Source/native Frame ABI identity differs')
    check(all(frame['source']['base_frame_index']['digest'][key] == summary['frames']['index']['digest'][key]
              for key in ('size', 'sha256')), 'Original normal Frame index differs from source batch')
    check([row['id'] for row in classes] == list(range(len(classes))), 'Original Class plan is not dense')
    names = {(row['origin']['loader'], row['name']): row for row in classes}
    cls, string = [names['bootstrap', name] for name in (OWNER, 'java/lang/String')]
    selected = {row['class_id']: row for row in selection['selected_classes']}
    for original in (cls, string):
        chosen = selected.get(original['id'])
        check(chosen and chosen['diagnostic'] is None and chosen['source_sha256'] == original['origin']['sha256'],
              'Normally selected original Class descriptor required: ' + original['name'])
    raw = C.RawClasses(summary)
    native = None
    try:
        parsed = I.Source(raw.read(cls))
        check(parsed.name == OWNER and len(parsed.methods) == len(cls['method_ids']), 'Original java.lang.Class declarations differ')
        for ident, member in zip(cls['method_ids'], parsed.methods):
            if (member['name'], member['descriptor']) == NATIVE:
                check(native is None and member['access'] == 0x102 and parsed.code(member) is None,
                      'Original private instance native declaration required')
                native = dict(method=ident, class_id=cls['id'], owner=OWNER, name=NATIVE[0], descriptor=NATIVE[1],
                              access=member['access'], class_sha256=cls['origin']['sha256'], code_sha256=None, operation=0)
        parsed_string = I.Source(raw.read(string))
        check(parsed_string.name == string['name'] and
              [{key: field[key] for key in ('name', 'descriptor', 'access')} for field in parsed_string.fields] == string['fields'],
              'Original String field declarations differ')
    finally:
        raw.close()
    check(native is not None, 'Original native getEnclosingMethod0 missing')
    declarations = [row for row in frame['source']['original_native_declarations'] if row['id'] == native['method']]
    check(len(declarations) == 1, 'Original native Frame declaration is missing or ambiguous')
    declaration = declarations[0]
    check(declaration['flags'] == 32 and all(declaration[key] == native[key] for key in
          ('class_id', 'name', 'descriptor', 'access', 'class_sha256')), 'Original normal native Frame32 differs')
    check([row for row in frame['source']['rows'] if row[0] == native['method']] ==
          [[native['method'], 32, cls['id'], 0]], 'Original normal native Frame source row differs')
    string_layouts = [row for row in layouts if row['class_id'] == string['id']]
    check(len(string_layouts) == 1 and string_layouts[0]['diagnostic'] is None and string_layouts[0]['candidate'],
          'Original normal packed String layout required')
    layout = string_layouts[0]

    def field_offset(name, descriptor, width, reference):
        rows = [row for row in layout['candidate']['fields'] if (row['member']['owner'], row['member']['name'], row['member']['descriptor']) ==
                (string['id'], name, descriptor)]
        check(len(rows) == 1 and rows[0]['storage_bytes'] == width and rows[0]['reference'] is reference,
              'Original normal String field storage differs: ' + name)
        return rows[0]['offset']

    if type_inputs is None:
        type_inputs = C.inputs(summary, classes)
    types, runtime, available, _ = type_inputs
    by_name = {(row['defining_loader'], row['name']): row for row in types}
    by_type = {row['type_id']: row for row in runtime}
    arrays = {name: by_type[by_name['bootstrap', name]['id']] for name in ('[Ljava/lang/Object;', '[B')}
    check(arrays['[B']['primitive_tag'] == 264 and arrays['[Ljava/lang/Object;']['tag_symbol'], 'Original array heap ABI differs')
    if directory is None:
        directory = catalog(summary, classes, selection, generated_expansion, type_inputs=type_inputs, root=root)
    entries = directory['entries']
    check(len(entries) >= summary['runtime_metadata']['type_capacity'] and
          [row['type_id'] for row in entries] == list(range(len(entries))), 'Source-proven enclosing directory must be dense')
    rows = []
    for entry in entries:
        status = STATUS[entry['status']]
        holder, name, descriptor = (entry.get(key) for key in ('holder_type_id', 'method_name', 'method_descriptor'))
        if status in (1, 2):
            check(type(holder) is int and 0 <= holder < len(entries), 'Enclosing holder source identity is unavailable')
            check(entry['original_attribute_hex'] and len(bytes.fromhex(entry['original_attribute_hex'])) == 4,
                  'Real EnclosingMethod attribute bytes required')
        if status == 1:
            check(isinstance(name, str) and name and isinstance(descriptor, str) and descriptor,
                  'Original enclosing NameAndType text required')
            I.descriptor(descriptor)
            check(len(name.encode('utf-16-le', 'surrogatepass')) // 2 <= 65535 and
                  len(descriptor.encode('utf-16-le', 'surrogatepass')) // 2 <= 65535,
                  'Original enclosing text exceeds the Class constant size bound')
        elif status in (0, 2):
            check(name is None and descriptor is None, 'Absent/class-only/unsupported row must not invent method text')
        if entry['type_id'] < len(classes):
            check(entry['original_Class_SHA'] == classes[entry['type_id']]['origin']['sha256'] and
                  entry['loader_key'] == classes[entry['type_id']]['origin']['loader'],
                  'Directory original Class/loader identity differs')
        rows.append(dict(type_id=entry['type_id'], status=status, holder_type_id=holder if status in (1, 2) else 0xffffffff,
                         name=name, descriptor=descriptor))
    return dict(schema=1, methods=[native], original_native_declaration=declaration,
                original_native_declarations=[declaration], source_type_capacity=len(entries), original_class_count=len(classes),
                rows=rows, String_class=string['id'], String_layout=layout,
                string_value_offset=field_offset('value', '[B', 8, True),
                string_coder_offset=field_offset('coder', 'B', 1, False), compact_strings=summary['string_literals']['compact_strings'],
                arrays=arrays, pool_bytes=128, pool_abi=1, row_bytes=32,
                represented_or_enclosing_Class_initialized=False, String_ensure_before_temporary_oops=True,
                noncollecting_native_calls_after_temporary_allocation=True, automatic_or_concurrent_GC_supported=False,
                additional_oop_roots=[], original_Java_Code_changed=False, registered_pack=False)


def data(meta):
    text = ['.const\nALIGN 8\nPUBLIC ' + POOL + '\n',
            f"{POOL} DWORD 0454E434Dh,1,{meta['source_type_capacity']},32\n",
            ' QWORD OFFSET boom_java_class_pool,OFFSET boom_heap_ptr,OFFSET encm_rows\n',
            f" QWORD OFFSET boom_layout{meta['String_class']},OFFSET boom_class{meta['String_class']},OFFSET {meta['arrays']['[Ljava/lang/Object;']['tag_symbol']}\n",
            f" QWORD {meta['arrays']['[B']['primitive_tag']}\n",
            f" DWORD {meta['string_value_offset']},{meta['string_coder_offset']},{int(meta['compact_strings'])},128\n",
            f" DWORD {meta['original_class_count']},0\n QWORD 0,0,0,0\nALIGN 8\nencm_rows LABEL BYTE\n"]
    payload = []
    for row in meta['rows']:
        text.append(f" DWORD {row['status']},{row['holder_type_id']}\n")
        if row['status'] == 1:
            prefix = 'encm_' + str(row['type_id']) + '_'
            text.append(f" QWORD OFFSET {prefix}name,OFFSET {prefix}descriptor\n")
            name, descriptor = [row[key].encode('utf-16-le', 'surrogatepass') for key in ('name', 'descriptor')]
            text.append(f" DWORD {len(name)//2},{len(descriptor)//2}\n")
            for key, content in [('name', name), ('descriptor', descriptor)]:
                payload.append('ALIGN 2\n' + prefix + key + ' LABEL BYTE\n')
                for offset in range(0, len(content), 16):
                    payload.append(' BYTE ' + ','.join(map(str, content[offset:offset+16])) + '\n')
        else:
            text.append(' QWORD 0,0\n DWORD 0,0\n')
    return ''.join(text + payload)


def native_assembly(meta, *, root=None):
    [native] = meta['methods']
    procedures = {'boom_class_ensure32', 'boom_trace_enter', 'boom_trace_leave', SERVICE}
    values = {'boom_trace_pool', POOL, 'boom_class' + str(native['class_id']), 'boom_trace_method' + str(native['method'])}
    text = 'option casemap:none\n' + ''.join('EXTERN ' + name + ':' + ('PROC' if name in procedures else 'BYTE') + '\n'
                                             for name in sorted(procedures | values))
    return text + f"PUBLIC boom_m{native['method']}\nPUBLIC boom_m{native['method']}_native\n" + module('verify-batch-frames', root).native_adapter(
        native['method'], native['class_id'], POOL, SERVICE, 0) + '\nEND\n'


def fragment_path():
    return Path(__file__).resolve().parents[1] / FRAGMENT


def service_assembly(meta, fragment=None):
    procedures = {'boom_heap_alloc', 'boom_object_new', 'boom_java_class_typeid', 'boom_java_class_load', 'boom_class_ensure32'}
    values = {'boom_java_class_pool', 'boom_heap_ptr', 'boom_layout' + str(meta['String_class']),
              'boom_class' + str(meta['String_class']), meta['arrays']['[Ljava/lang/Object;']['tag_symbol']}
    return 'option casemap:none\n' + ''.join('EXTERN ' + name + ':' + ('PROC' if name in procedures else 'BYTE') + '\n'
                                             for name in sorted(procedures | values)) + data(meta) + (
        fragment_path().read_text(encoding='utf-8') if fragment is None else fragment) + '\nEND\n'


def render(meta, *, fragment=None, root=None):
    return {'enclosing-method-native': native_assembly(meta, root=root),
            'enclosing-method-service': service_assembly(meta, fragment)}


def frame_row_physical(path, method, class_id):
    """Read the actual normal Row32 and sole declaring-TYPE relocation."""
    raw = Path(path).read_bytes()
    machine, count, _, sym_at, symbols, optional, _ = struct.unpack_from('<HHIIIHH', raw)
    check(machine == 0x8664 and optional == 0, 'Original Frame requires AMD64 COFF')
    strings = sym_at + 18 * symbols

    def symbol(index):
        name, value, section, kind, storage, aux = struct.unpack_from('<8sIhHBB', raw, sym_at + 18 * index)
        if name[:4] == b'\0' * 4:
            start = strings + struct.unpack_from('<I', name, 4)[0]
            name = raw[start:raw.index(0, start)]
        else:
            name = name.rstrip(b'\0')
        return dict(name=name.decode(), value=value, section=section, type=kind, storage=storage, aux=aux)

    index, target = 0, None
    while index < symbols:
        row = symbol(index)
        if row['name'] == 'boom_trace_method' + str(method):
            target = row
            break
        index += row['aux'] + 1
    check(target and target['storage'] == 2 and 0 < target['section'] <= count,
          'Actual original normal native Frame symbol missing')
    section = struct.unpack_from('<8sIIIIIIHHI', raw, 20 + (target['section'] - 1) * 40)
    _, _, _, size, start, relocations, _, relocation_count, _, flags = section
    offset = target['value']
    check(offset + 32 <= size, 'Actual normal native Frame escapes its section')
    actual = raw[start + offset:start + offset + 32]
    check(actual == struct.pack('<IIQIIQ', method, 32, 0, 0, class_id, 0),
          'Actual native Row32 must retain original method/class/flags/code')
    if flags & 0x1000000:
        total, index, kind = struct.unpack_from('<IIH', raw, relocations)
        check(relocation_count == 65535 and index == kind == 0 and total > 65535,
              'Invalid actual Frame relocation overflow')
        relocation_count, relocations = total - 1, relocations + 10
    hits = []
    for index in range(relocation_count):
        address, symbol_index, kind = struct.unpack_from('<IIH', raw, relocations + 10 * index)
        if offset <= address < offset + 32:
            hits.append(dict(offset=address - offset, type=kind, target=symbol(symbol_index)['name']))
    check(hits == [dict(offset=8, type=1, target='boom_t' + str(class_id))],
          'Actual Frame declaring TYPE relocation differs')
    return dict(object=artifact(path), symbol=target['name'], section=section[0].rstrip(b'\0').decode(),
                offset=offset, actual32=actual.hex(), relocations=hits, normal_Frame32_verified=True)


def project(summary_file, classes_file, selection_file, frame_file, layouts_file, runtime_types_file, *,
            generated_expansion_file=None, source_verification=None):
    """Project explicit input files; never run SourceV or a native assembler."""
    summary, selection, frame = map(read, (summary_file, selection_file, frame_file))
    paths = dict(summary=summary_file, classes=classes_file, selection=selection_file, frame=frame_file,
                 layouts=layouts_file, runtime_types=runtime_types_file)
    references = {name: artifact(path) for name, path in paths.items()}
    check(selection['source_batch_summary_sha256'] == references['summary']['digest']['sha256'] and
          selection['source_classes_sha256'] == references['classes']['digest']['sha256'],
          'Explicit selected source/summary/original Class plan differs')
    for name, original in [('layouts', summary['layouts']), ('runtime_types', summary['runtime_metadata']['index'])]:
        check(all(references[name]['digest'][key] == original['digest'][key] for key in ('size', 'sha256')) and
              Path(paths[name]).resolve() == checked(original), 'Explicit original runtime/layout source differs: ' + name)
    if source_verification is not None:
        proof = read(source_verification)
        check(proof.get('verified') is True and proof['closure_manifest_sha256'] == references['selection']['digest']['sha256'],
              'Existing complete source verification must bind this exact selection')
    with Path(classes_file).open(encoding='utf-8') as stream:
        classes = [json.loads(line) for line in stream]
    expansion = read(generated_expansion_file) if generated_expansion_file is not None else None
    type_inputs = module('constructor-provider-source').inputs(summary, classes)
    directory = catalog(summary, classes, selection, expansion, type_inputs=type_inputs)
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
                physical_original_Frame=frame_row_physical(checked(frame['object']), native['method'], native['class_id']),
                directory_counts=directory['counts'], machine_or_behavior_verified=False)
    meta['source_library_dependencies'] = {
        name: artifact(installed_root() / 'scripts' / (name + '.py')) for name in
        ('constructor-provider-source', 'verify-translation-ir', 'verify-batch-frames',
         'verify-batch-metadata', 'system-class-inputs')}
    return meta, directory


def output_target(value):
    target, base = Path(value).resolve(), installed_root()
    check(any(target.is_relative_to(base / name) for name in ('.boom', 'target', 'dist')),
          'Generated source output must stay in this installed project .boom, target or dist')
    check(not target.exists(), 'Generated source output must be create-new')
    return target


def main(args):
    # Output is checked before reading source inputs or creating any files.
    # The CLI has no repository-root override.
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
