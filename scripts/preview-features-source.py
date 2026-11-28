"""Original PreviewFeatures declarations and immutable VM-option MASM source.

metadata() reads explicit original Class, selection and normal Frame inputs.
render() emits the normal native adapter and a readonly startup-option query.
project() optionally binds an existing complete source verification. These APIs
do not assemble, select Java, execute a VM, or admit preview classfiles.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import tomllib

OWNER = 'jdk/internal/misc/PreviewFeatures'
POOL = 'boom_preview_features_pool'
SERVICE = 'boom_preview_features_service'
FRAGMENT = 'native/providers/preview_features.asm.inc'
ABI_FILE = 'native-config/preview-features-abi.json'
ROLES = ('preview-features-native', 'preview-features-option')


def check(value, message):
    if not value:
        raise ValueError(message)


def installed_root():
    """Find this installed repository using tracked source and Cargo markers."""
    for path in Path(__file__).resolve().parents:
        cargo = path / 'Cargo.toml'
        if (cargo.is_file() and
                (path / 'scripts/constructor-provider-source.py').is_file() and
                (path / 'src/compiler/classfile.rs').is_file()):
            with cargo.open('rb') as stream:
                package = tomllib.load(stream).get('package', {})
            if package.get('name') == 'boom-minecraft':
                return path
    raise ValueError('Installed project source/tool root not found')


def module(name, root=None):
    base = installed_root() if root is None else Path(root).resolve()
    spec = importlib.util.spec_from_file_location(
        'preview_features_' + name.replace('-', '_'), base / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=sha))


def checked(row):
    value = artifact(row['path'])
    check(all(value['digest'][key] == row['digest'][key] for key in ('size', 'sha256')),
          'Explicit original input changed: ' + row['path'])
    return Path(value['path'])


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def startup_options(options):
    """Require an explicit boolean VM option with immutable image semantics."""
    check(options.get('schema') == 'closed-image-VM-options-v1' and
          type(options.get('enable_preview')) is bool and
          options.get('immutable_after_VM_start') is True,
          'Explicit immutable boolean VM preview option required')
    check(options.get('preview_classfile_loading_supported') is False and
          options.get('querying_enabled_does_not_admit_preview_classfiles') is True and
          options.get('game_arguments_are_not_VM_options') is True,
          'VM-option query must not admit preview classfiles or reinterpret game arguments')
    check(options.get('Java_VM_option') == '--enable-preview' and
          isinstance(options.get('configuration_source'), str) and
          options['configuration_source'].strip(),
          'Explicit VM startup configuration provenance required')
    # Copy the option data: later caller mutation cannot alter the projection.
    return json.loads(json.dumps(options))


def metadata(summary, classes, selection, frame, options, *, root=None):
    """Derive method identities and original Java cache operations from Class.

    Inputs are decoded JSON values. Raw Class bytes are read only from the
    hash-bound original archives named by summary. No Java state is written.
    Full source-proof and machine/behavior acceptance are separate file-level
    bindings, not facts inferred from metadata or successful source rendering.
    """
    options = startup_options(options)
    check(selection['source_input_fingerprint'] == summary['input_fingerprint'] and
          selection['source_frame_abi'] == summary['frames']['abi'] == frame['pool_abi'] == 3 and
          frame['method_row_bytes'] == 32, 'Original source/Frame ABI identity differs')
    check(all(frame['source']['base_frame_index']['digest'][key] ==
              summary['frames']['index']['digest'][key] for key in ('size', 'sha256')),
          'Original normal Frame index differs from source batch')
    classes = list(classes)
    matches = [c for c in classes if (c['origin']['loader'], c['name']) == ('bootstrap', OWNER)]
    check(len(matches) == 1, 'Original bootstrap PreviewFeatures Class must be unique')
    cls = matches[0]
    C, I = module('constructor-provider-source', root), module('verify-translation-ir', root)
    raw = C.RawClasses(summary)
    try:
        data = raw.read(cls)
    finally:
        raw.close()
    parsed = I.Source(data)
    check(parsed.name == OWNER and len(parsed.methods) == len(cls['method_ids']),
          'Original PreviewFeatures method declarations differ')
    check([{key: field[key] for key in ('name', 'descriptor', 'access')} for field in parsed.fields]
          == cls['fields'], 'Whole original PreviewFeatures field declarations differ')
    minor, major = struct.unpack_from('>HH', data, 4)
    check(45 <= major <= 65 and minor != 65535,
          'This projection requires original non-preview Class inputs up to Java 21')
    native = declaration = cache = None
    java = []
    for mid, member in zip(cls['method_ids'], parsed.methods):
        code = parsed.code(member)
        signature = (member['name'], member['descriptor'])
        if signature == ('isPreviewEnabled', '()Z'):
            check(native is None and member['access'] == 0x10a and code is None,
                  'Original private static native preview declaration required')
            rows = [row for row in frame['source']['original_native_declarations'] if row['id'] == mid]
            check(len(rows) == 1, 'Original normal native Frame declaration missing or ambiguous')
            declaration = rows[0]
            check(declaration['flags'] == 32 and all(declaration[key] == value for key, value in
                  [('class_id', cls['id']), ('class_sha256', cls['origin']['sha256']),
                   ('name', member['name']), ('descriptor', '()Z'), ('access', member['access'])]),
                  'Original normal native Frame32 declaration differs')
            rows = [row for row in frame['source']['rows'] if row[0] == mid]
            check(rows == [[mid, 32, cls['id'], 0]], 'Original native Frame must retain flags32/code0')
            native = dict(method=mid, class_id=cls['id'], owner=OWNER, name=member['name'],
                          descriptor='()Z', access=member['access'], class_sha256=cls['origin']['sha256'],
                          code_sha256=None, operation=0)
        if signature in (('isEnabled', '()Z'), ('<clinit>', '()V')):
            check(code is not None, 'Original Java getter and initializer Code required')
            record = dict(method=mid, class_id=cls['id'], name=member['name'],
                          descriptor=member['descriptor'], source_sha256=cls['origin']['sha256'],
                          code_sha256=hashlib.sha256(code['bytes']).hexdigest())
            keys = ('class_id', 'name', 'descriptor', 'source_sha256', 'code_sha256')
            check(selection['selected_methods'].get(str(mid)) == {key: record[key] for key in keys}
                  and selection['selected_function_sha256'].get('boom_m' + str(mid) + '_body'),
                  'Original Java callback must already be selected with a provided body: ' + member['name'])
            calls = []
            for operation in I.stream(code['bytes']):
                if operation['opcode'] in (0xb2, 0xb3, 0xb8):
                    calls.append(dict(pc=operation['pc'], opcode=operation['opcode'],
                                      **parsed.member(operation['operand']['Constant'])))
            java.append(dict(record, calls=calls))
            if signature == ('<clinit>', '()V'):
                writes = [row for row in calls if row['opcode'] == 0xb3 and
                          row['owner'] == OWNER and row['descriptor'] == 'Z']
                check(len(writes) == 1, 'Original initializer must publish one boolean cache')
                cache = writes[0]
    check(native is not None and len(java) == 2 and cache is not None,
          'Original native/getter/initializer/cache source is incomplete')
    [initializer] = [row for row in java if row['name'] == '<clinit>']
    [getter] = [row for row in java if row['name'] == 'isEnabled']
    check(any(row['opcode'] == 0xb8 and (row['owner'], row['name'], row['descriptor']) ==
              (OWNER, 'isPreviewEnabled', '()Z') for row in initializer['calls']),
          'Original initializer must invoke the original native option query')
    check(any(row['opcode'] == 0xb2 and (row['owner'], row['name'], row['descriptor']) ==
              (OWNER, cache['name'], 'Z') for row in getter['calls']),
          'Original getter must read the original Java cache')
    fields = [row for row in cls['fields'] if (row['name'], row['descriptor']) == (cache['name'], 'Z')]
    check(len(fields) == 1 and fields[0]['access'] == 0x1a,
          'Original Java cache must remain private static final')
    selected = [row for row in selection['selected_classes'] if row['class_id'] == cls['id']]
    check(len(selected) == 1 and selected[0]['source_sha256'] == cls['origin']['sha256']
          and selected[0]['diagnostic'] is None, 'Original Class must already be normally selected')
    return dict(schema=1, methods=[native], original_native_declaration=declaration,
                original_native_declarations=[declaration],
                original_Class=dict(class_id=cls['id'], name=OWNER, sha256=cls['origin']['sha256'],
                                    minor=minor, major=major), original_Java=java,
                Java_cache=dict(fields[0], initializer=initializer['method'], getter=getter['method']),
                pool_abi=1, pool_bytes=16, enable_preview=options['enable_preview'], configuration=options,
                additional_oop_roots=[], original_Java_Code_changed=False, registered_pack=False,
                preview_classfile_execution_supported=False, machine_or_behavior_verified=False)


def native_assembly(meta, *, root=None):
    [native] = meta['methods']
    frames = module('verify-batch-frames', root)
    procedures = {'boom_class_ensure32', 'boom_trace_enter', 'boom_trace_leave', SERVICE}
    values = {POOL, 'boom_trace_pool', 'boom_class' + str(native['class_id']),
              'boom_trace_method' + str(native['method'])}
    text = 'option casemap:none\n' + ''.join(
        'EXTERN ' + name + ':' + ('PROC' if name in procedures else 'BYTE') + '\n'
        for name in sorted(procedures | values))
    return (text + f"PUBLIC boom_m{native['method']}\nPUBLIC boom_m{native['method']}_native\n"
            + frames.native_adapter(native['method'], native['class_id'], POOL, SERVICE, 0) + '\nEND\n')


def _fragment_path(root=None):
    if root is not None:
        return Path(root).resolve() / FRAGMENT
    # A reviewed source package and the installed scripts/ layout share this
    # relative location. It is a source file, never a prebuilt binary blob.
    return Path(__file__).resolve().parents[1] / FRAGMENT


def _abi_path():
    return Path(__file__).resolve().parents[1] / ABI_FILE


def service_assembly(meta, *, fragment=None, root=None):
    flag = meta['enable_preview']
    check(type(flag) is bool, 'Rendered immutable preview option must be boolean')
    if fragment is None:
        fragment = _fragment_path(root).read_text(encoding='utf-8')
    return ('option casemap:none\n.const\nALIGN 4\nPUBLIC ' + POOL + '\n' + POOL +
            ' DWORD 050525657h,1,16,' + str(int(flag)) + '\n' + fragment + '\nEND\n')


def render(meta, *, fragment=None, root=None):
    return {ROLES[0]: native_assembly(meta, root=root),
            ROLES[1]: service_assembly(meta, fragment=fragment, root=root)}


def frame_row_physical(path, method, class_id):
    """Read the exact normal native Row32 and its declaring-TYPE relocation."""
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
    _, _, _, size, at, relocations, _, relocation_count, _, flags = section
    offset = target['value']
    check(offset + 32 <= size, 'Actual normal native Frame escapes its section')
    actual = raw[at + offset:at + offset + 32]
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


def compiler_policy(root=None):
    base = installed_root() if root is None else Path(root).resolve()
    files = [base / 'src/compiler/classfile.rs', base / 'src/bytecode.rs']
    for path in files:
        text = path.read_text(encoding='utf-8')
        check(re.search(r'\(45\s*\.\.=\s*65\)\.contains\(&major\)', text) and
              re.search(r'minor\s*!=\s*65535', text),
              'Current frontend non-preview Java 21 input boundary differs')
    return dict(frontend=artifact(files[0]), archive_input=artifact(files[1]), max_major=65,
                preview_minor_65535_rejected=True, changed_by_native_query=False)


def project(summary_file, classes_file, selection_file, frame_file, options_file, *,
            source_verification=None):
    """Bind explicit source artifacts without running any source verification."""
    summary, selection, frame, options = map(read, (summary_file, selection_file, frame_file, options_file))
    summary_ref, classes_ref, source_ref = map(artifact, (summary_file, classes_file, selection_file))
    check(selection['source_batch_summary_sha256'] == summary_ref['digest']['sha256'] and
          selection['source_classes_sha256'] == classes_ref['digest']['sha256'],
          'Explicit selected source/summary/original Class plan differs')
    if source_verification is not None:
        proof = read(source_verification)
        check(proof.get('verified') is True and
              proof['closure_manifest_sha256'] == source_ref['digest']['sha256'],
              'Existing complete source verification must bind this selection')
    with Path(classes_file).open(encoding='utf-8') as stream:
        value = metadata(summary, (json.loads(line) for line in stream), selection, frame, options)
    [native] = value['methods']
    value.update(source_manifest=source_ref,
                 source_full_verification=artifact(source_verification) if source_verification is not None else None,
                 source_admission_verified=source_verification is not None,
                 startup_configuration=artifact(options_file),
                 physical_original_Frame=frame_row_physical(checked(frame['object']), native['method'], native['class_id']),
                 compiler_preview_classfile_policy=compiler_policy())
    value['inputs'] = {key: artifact(path) for key, path in dict(
        summary=summary_file, classes=classes_file, selection=selection_file, frame=frame_file,
        options=options_file, source_library=__file__, fragment=_fragment_path(), ABI=_abi_path()).items()}
    value['source_library_dependencies'] = {
        name: artifact(installed_root() / 'scripts' / (name + '.py')) for name in
        ('constructor-provider-source', 'verify-translation-ir', 'verify-batch-frames', 'system-class-inputs')}
    return value


def output_target(value):
    target, base = Path(value).resolve(), installed_root()
    check(any(target.is_relative_to(base / name) for name in ('.boom', 'target', 'dist')),
          'Generated source output must stay in this installed project .boom, target or dist')
    check(not target.exists(), 'Generated source output must be create-new')
    return target


def main(args):
    # Reject an invalid destination before project input reads or mkdir. The
    # CLI cannot override the installed repository root to escape this boundary.
    output = output_target(args.output)
    value = project(args.summary, args.classes, args.selection, args.frames, args.options,
                    source_verification=args.source_verification)
    assembly = render(value)
    output.mkdir(parents=True)
    with (output / 'source.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    emitted = {}
    for role, text in assembly.items():
        path = output / (role + '.asm')
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
        emitted[role] = artifact(path)
    print(json.dumps(dict(source_model=artifact(output / 'source.json'), assembly=emitted,
                          source_only=True, machine_or_behavior_verified=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('summary', 'classes', 'selection', 'frames', 'options', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-verification', type=Path)
    main(parser.parse_args())
