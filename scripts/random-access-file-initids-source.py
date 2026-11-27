"""Original RandomAccessFile.initIDs FieldID/Frame source projection only.

Official OpenJDK native reference and locked Azul class inputs are separate.
No file operation is implemented by this first, one-field registration slice.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

sys.dont_write_bytecode = True
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'AGENTS.md').is_file())
OWNER = 'java/io/RandomAccessFile'
POOL = 'boom_random_access_file_init_ids_pool'
SERVICE = 'boom_random_access_file_init_ids'
STREAM_POOL = 'boom_random_access_file_stream_pool'
KERNEL = ROOT / 'native/providers/random_access_file_init_ids.asm.inc'
PINNED = {
    'RandomAccessFile.c': '0348561d0686662f522416b909619a43cb5607c4d2e8a1de03acbcc6bc09ed58',
    'jni.cpp': '49f0d0c7507c23afa7c3cdf56a4c5ee0d5e5bd18e9e52fd98376d54ea52544b3',
}


def check(value, message):
    if not value:
        raise ValueError(message)


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=sha))


def checked(row):
    actual = artifact(row['path'])
    expected = row.get('digest', row)
    check(actual['digest'] == {k: expected[k] for k in ('size', 'sha256')}, 'Sealed RAF source changed: ' + row['path'])
    return Path(actual['path'])


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def module(name, path=None):
    path = Path(path) if path else ROOT / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location('raf_original_' + name.replace('-', '_'), path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def c_contract(pinned):
    sources = {name: artifact(Path(pinned) / name) for name in PINNED}
    check(all(row['digest']['sha256'] == PINNED[name] for name, row in sources.items()), 'Official exact-tag native source changed')
    text = Path(sources['RandomAccessFile.c']['path']).read_text()
    marker = 'Java_java_io_RandomAccessFile_initIDs'
    begin = text.index(marker)
    start = text.index('{', begin)
    end = text.index('\n}', start) + 2
    body = text[start + 1:end - 1]
    match = re.fullmatch(r'\s*(\w+)\s*=\s*\(\*env\)->GetFieldID\(env,\s*fdClass,\s*"([^"]+)",\s*"([^"]+)"\);\s*', body)
    check(match is not None and match.groups() == ('raf_fd', 'fd', 'Ljava/io/FileDescriptor;'), 'One exact original GetFieldID assignment required')
    check(re.search(r'^jfieldID\s+raf_fd\s*;', text, re.M), 'Original RAF native FieldID declaration missing')
    jni = Path(sources['jni.cpp']['path']).read_text()
    start_jni = jni.index('JNI_ENTRY(jfieldID, jni_GetFieldID')
    end_jni = jni.index('JNI_END', start_jni)
    jni_body = jni[start_jni:end_jni]
    check('k->initialize(CHECK_NULL);' in jni_body and jni_body.index('k->initialize(CHECK_NULL);') < jni_body.index('find_field'),
          'JNI GetFieldID normal initialization obligation changed')
    return dict(reference_repository='openjdk/jdk21u', reference_tag='jdk-21.0.13+3',
        sources=sources, native_source_lines=[text[:begin].count('\n') + 1, text[:end].count('\n') + 1],
        initIDs_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        sequence=[dict(kind='field', owner=OWNER, C_variable=match.group(1), name=match.group(2), descriptor=match.group(3))],
        JNI_GetFieldID_initializes_declaring_class=True, referenced_field_type_initialization_not_requested=True,
        native_API_calls=['GetFieldID'], Win32_API_calls=[], opens_or_reads_a_file=False)


def bind(state_file, source_file, parent_file, pinned, records_source, release_file):
    I, R = module('verify-translation-ir'), module('verify-batch-frames')
    W = module('normal_field_records', records_source)
    state, closure, parent = map(read, (state_file, source_file, parent_file))
    seal = read(checked(parent['source_seal']))
    check(artifact(state_file) == parent['input_state'] == seal['input_state'] and artifact(source_file) == seal['source_manifest'],
          'Exact current normal source/state required')
    objects = parent['objects']
    check(isinstance(objects, list) and objects and
          len({str(Path(row['path']).resolve()).casefold() for row in objects}) == len(objects),
          'Parent must provide one ordered occurrence of every linked source object')
    if 'actual_object_count' in parent:
        check(type(parent['actual_object_count']) is int and parent['actual_object_count'] == len(objects),
              'Parent declared object population differs from its actual object metadata')
    for name, sha in state['tool_sources'].items():
        check(artifact(ROOT / name)['digest']['sha256'] == sha, 'Current source epoch changed: ' + name)
    summary_file = Path(closure['batch']) / 'summary.json'
    summary, plan = read(summary_file), Path(closure['plan'])
    pinned = Path(pinned)
    pinned_C = pinned / 'RandomAccessFile.c' if pinned.is_dir() else pinned
    inputs = [artifact(p) for p in (state_file, source_file, parent_file, pinned_C, records_source, release_file,
        __file__, I.__file__, R.__file__, summary_file, plan / 'classes.jsonl')]
    inputs += [parent['source_seal'], seal['source_full_verification'], summary['unsafe_fields']['index'],
        summary['runtime_metadata']['index'], summary['layouts'], summary['frames']['original_system_catalog']]
    contract = c_contract(pinned_C.parent)
    inputs += list(contract['sources'].values())
    names = {OWNER, 'java/io/FileDescriptor'}
    classes = {}
    for line in (plan / 'classes.jsonl').open(encoding='utf-8'):
        row = json.loads(line)
        if row['name'] in names and row['origin']['loader'] == 'bootstrap':
            classes[row['name']] = row
    check(set(classes) == names, 'Original RAF/FileDescriptor classes unavailable')
    ids = {row['id'] for row in classes.values()}
    layouts = {}
    for line in checked(summary['layouts']).open(encoding='utf-8'):
        row = json.loads(line)
        if row['class_id'] in ids:
            layouts[row['class_id']] = row
    selected = {row['class_id']: row for row in closure['selected_classes']}
    image = checked(summary['frames']['original_system_catalog']).parent / 'image'
    original, native, clinit = {}, None, None
    jmod = Path(release_file).resolve().parent / 'jmods/java.base.jmod'
    release = Path(release_file).read_text()
    release_values = dict(re.findall(r'^([A-Z_]+)="([^"]*)"$', release, re.M))
    check(release_values.get('IMPLEMENTOR') == 'Azul Systems, Inc.' and release_values.get('OS_ARCH') == 'x86_64' and
          release_values.get('JAVA_RUNTIME_VERSION', '').endswith('+1-LTS'), 'Actual locked Azul +1 source release differs')
    with zipfile.ZipFile(jmod) as installed:
        for name, cls in classes.items():
            path = (image / cls['origin']['jar_entry']).resolve()
            check(path.is_relative_to(image.resolve()), 'Original class escaped locked image')
            item = artifact(path)
            check(item['digest']['sha256'] == cls['origin']['sha256'] and cls['id'] in selected and
                  selected[cls['id']]['source_sha256'] == cls['origin']['sha256'], 'Original normal selected class differs')
            raw = path.read_bytes()
            check(hashlib.sha256(installed.read('classes/' + name + '.class')).hexdigest() == item['digest']['sha256'],
                  'Installed Azul release does not contain the exact locked input class bytes')
            source = I.Source(raw)
            owner, annotations = R.original_methods(raw)
            check(owner == source.name == name and int.from_bytes(raw[6:8], 'big') == 65 and
                  cls['origin']['source_id'] == 'jdk:java.base' and not cls['origin'].get('generated') and
                  len(source.methods) == len(cls['method_ids']) == len(annotations) and
                  [{key: field[key] for key in ('name', 'descriptor', 'access')} for field in source.fields] == cls['fields'],
                  'Actual locked classfile inventory differs')
            shape = layouts[cls['id']]
            check(shape['diagnostic'] is None and shape['candidate'] is not None and shape['source_sha256'] == cls['origin']['sha256'],
                  'Actual normal source layout unavailable')
            methods = []
            for ident, method, annotation in zip(cls['method_ids'], source.methods, annotations):
                code = source.code(method)
                record = dict(method=ident, class_id=cls['id'], owner=name, name=method['name'], descriptor=method['descriptor'],
                    access=method['access'], class_sha256=item['digest']['sha256'], loader='bootstrap', source_id='jdk:java.base',
                    code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None,
                    frame_flags=R.flags(name, annotation, code is None, False, False))
                if code:
                    chosen = closure['selected_methods'].get(str(ident), {})
                    record.update(selected=chosen.get('code_sha256') == record['code_sha256'] and
                        chosen.get('source_sha256') == item['digest']['sha256'], original_Code_hex=code['bytes'].hex())
                if name == OWNER and method['name'] == 'initIDs':
                    native = record
                if name == OWNER and method['name'] == '<clinit>':
                    clinit = record
                methods.append(record)
            original[name] = dict(class_record=cls, normal_layout=shape, source=item, methods=methods,
                selected_normal_class=selected[cls['id']], class_symbol='boom_class' + str(cls['id']), layout_symbol='boom_layout' + str(cls['id']))
            inputs.append(item)
    inputs.append(artifact(jmod))
    check(native and native['access'] == 0x10a and native['descriptor'] == '()V' and native['code_sha256'] is None and
          native['frame_flags'] == 32 and clinit and clinit['selected'], 'Original private static native/class initializer contract differs')
    check(selected[native['class_id']]['initializer']['method'] == clinit['method'] and
          selected[native['class_id']]['initializer']['code_sha256'] == clinit['code_sha256'], 'Normal class initializer binding differs')
    owner = original[OWNER]
    wanted = contract['sequence'][0]
    field = None
    with zipfile.ZipFile(checked(summary['unsafe_fields']['index'])) as archive:
        for line in archive.open('fields.jsonl'):
            row = json.loads(line)
            if (row['class_id'], row['name'], row['descriptor']) == (native['class_id'], wanted['name'], wanted['descriptor']):
                check(field is None, 'Duplicate original RAF FieldID')
                field = row
    check(field and field['access'] == 0x12 and field['address_map'] == field['id'] and field['storage_bytes'] == 8 and field['reference'],
          'Original private final RAF.fd field differs')
    fmap = None
    with zipfile.ZipFile(checked(summary['runtime_metadata']['index'])) as archive:
        for line in archive.open('fields.jsonl'):
            row = json.loads(line)
            if row['id'] == field['id']:
                check(fmap is None, 'Duplicate original normal field-address record')
                fmap = row
    shape = owner['normal_layout']['candidate']
    [physical] = [f for f in shape['fields'] if f['member']['owner'] == field['class_id'] and f['member']['index'] == field['field_index']]
    check(fmap and fmap['declaring_class'] == field['class_id'] and fmap['storage_bytes'] == physical['storage_bytes'] == 8 and
          fmap['reference'] == physical['reference'] is True and physical['offset'] % 8 == 0 and physical['offset'] < shape['reference_prefix'] * 8 and
          dict(receiver_class=field['class_id'], offset=physical['offset']) in fmap['rows'], 'RAF normal field layout/receiver map differs')
    record = dict(wanted, class_id=field['class_id'], field=field, FMAP=fmap, offset=physical['offset'],
        symbol='boom_field_map' + str(field['id']), record_symbol='boom_batch_field_record' + str(field['id']), layout_symbol=owner['layout_symbol'])
    group = dict(name=OWNER, class_id=native['class_id'], first_field=0, field_count=1,
        class_symbol=owner['class_symbol'], layout_symbol=owner['layout_symbol'], payload_bytes=shape['payload_bytes'],
        reference_prefix=shape['reference_prefix'], layout_field_count=len(shape['fields']))
    frame = read(checked(closure['runtime_frame_overlay']['reference']['manifest']))
    inputs += [closure['runtime_frame_overlay']['reference']['manifest'], closure['runtime_frame_overlay']['reference']['verification'], frame['object']]
    targets = {'boom_trace_method' + str(native['method']): 32, record['symbol']: 19, record['record_symbol']: 32 + 8 * len(fmap['rows'])}
    targets.update({item['class_symbol']: 16 for item in original.values()})
    targets.update({item['layout_symbol']: 24 for item in original.values()})
    objects = [parent['objects'][0], frame['object']] + [r['object'] for r in summary['runtime_metadata']['units']]
    parent_objects = {row['path']: row for row in parent['objects']}
    actual = {}
    for obj in objects:
        check(obj['path'] in parent_objects and artifact(checked(obj)) == artifact(checked(parent_objects[obj['path']])),
              'Required original metadata object is not present in exact parent')
        inputs.append(obj)
        for name, value in W.coff_records(obj['path'], targets).items():
            check(name not in actual, 'Duplicate original Class/layout/FMAPPROC/Frame data')
            actual[name] = dict(value, object=obj)
    check(set(actual) == set(targets), 'Actual original RAF normal metadata missing')
    trace = actual['boom_trace_method' + str(native['method'])]
    raw = bytes.fromhex(trace['bytes'])
    check(struct.unpack_from('<II', raw) == (native['method'], 32) and struct.unpack_from('<I', raw, 20)[0] == native['class_id'] and
          [(r['offset'], r['type'], r['target']) for r in trace['relocations']] == [(8, 1, 'boom_t' + str(native['class_id']))],
          'Actual normal native Frame descriptor differs')
    for item in original.values():
        desc = bytes.fromhex(actual[item['class_symbol']]['bytes'])
        layout = bytes.fromhex(actual[item['layout_symbol']]['bytes'])
        shape = item['normal_layout']['candidate']
        check(struct.unpack_from('<II', desc) == (0x434c4153, 2) and struct.unpack_from('<IIQII', layout) ==
              (0x4f424a43, 2, shape['payload_bytes'], shape['reference_prefix'], len(shape['fields'])), 'Actual Class/layout bytes differ')
    addr = actual[record['symbol']]
    check(addr['section'] in ('.text', '.text$mn') and addr['bytes'] == '4c8d05000000004c8d0d00000000e900000000' and
          [(r['offset'], r['type'], r['target']) for r in addr['relocations']] ==
          [(3, 4, record['record_symbol']), (10, 4, 'boom_runtime_type_map'), (15, 4, 'boom_field_address')],
          'Actual normal RAF field-address PROC differs')
    value = actual[record['record_symbol']]
    raw = bytes.fromhex(value['bytes'])
    check(struct.unpack_from('<IIIIII', raw) == (0x464d4150, 1, len(fmap['rows']), 8, 1, 0), 'Actual field-map record header differs')
    [reloc] = value['relocations']
    check(reloc['offset'] == 24 and reloc['type'] == 1 and reloc['target_symbol']['section_id'] == value['symbol']['section_id'] and
          reloc['target_symbol']['value'] == value['symbol']['value'] + 32 and
          [dict(receiver_class=a, offset=b) for a, b in struct.iter_unpack('<II', raw[32:])] == fmap['rows'],
          'Actual full inline RAF receiver/offset rows differ')
    for row in inputs:
        checked(row)
    return dict(schema=1, scope='original_selected_RandomAccessFile_initIDs_one_FieldID_registration_only',
        input_state=artifact(state_file), source_selection=artifact(source_file), source_full_verification=seal['source_full_verification'],
        parent_overlay=artifact(parent_file), runtime=parent['runtime'], official_C=contract,
        locked_class_input_release=dict(artifact=artifact(release_file), values=release_values,
            exact_locked_class_bytes_match_java_base_jmod=True, official_native_reference_is_a_separate_build=True),
        owner=native['class_id'], methods=[native], original_clinit=clinit, source_classes=original,
        groups=[group], fields=[record], actual_source_records=actual,
        UFMP_summary={k: summary['unsafe_fields'][k] for k in ('abi', 'type_capacity', 'declared_fields', 'pages', 'name_units')},
        source_helpers={n: artifact(ROOT / 'scripts' / (n + '.py')) for n in ('verify-translation-ir', 'verify-batch-frames')},
        tool_sources=state['tool_sources'], required_classes=sorted(ids), required_java_methods=[],
        required_base_modules=['runtime_metadata', 'unsafe_fields', 'frames'], no_new_Java_Code_or_classes_required=True,
        class_initialization_by_normal_ensure32_required=True, referenced_FileDescriptor_initialization_not_added=True,
        proposed_pool=dict(magic='RFID', abi=1, bytes=128, classes=1, fields=1, registration_cells=1, cache_offset=64,
            private_FieldID_representation='exact normal source field-address PROC pointer; full source FieldID/FMAPPROC immutable rows retained',
            cache_contains_Java_oops=False, ready_only_after_field_and_stream_registration=True,
            existing_stream_kernel_pool=dict(symbol=STREAM_POOL, offset=80, bytes=32, published_offset=96)),
        future_IO=dict(actual_IO_implemented=False, stream_pool=STREAM_POOL, existing_kernel='boom_stream_descriptor',
            existing_stream_descriptor_accepts_exact_layout_only=True,
            inherited_RAF_receivers_must_use_cached_source_FMAPPROC=True,
            consumer_must_require_RFID_ready=True, FileDescriptor_own_initIDs_is_a_separate_existing_dependency=True),
        inputs=inputs, SourceV_repeated=False, guest_or_Main_executed=False, registered=False, runtime_acceptance_complete=False)


def normal_frames(meta):
    R = module('verify-batch-frames')
    row = meta['methods'][0]
    procs = {'boom_class_ensure32', 'boom_trace_enter', 'boom_trace_leave', SERVICE}
    data = {POOL, 'boom_trace_pool', 'boom_class' + str(meta['owner']), 'boom_trace_method' + str(row['method'])}
    text = 'option casemap:none\n' + ''.join('EXTERN ' + name + (':PROC\n' if name in procs else ':BYTE\n') for name in sorted(procs | data))
    exports = {'boom_m' + str(row['method']), 'boom_m' + str(row['method']) + '_native'}
    text += ''.join('PUBLIC ' + name + '\n' for name in sorted(exports)) + R.native_adapter(row['method'], meta['owner'], POOL, SERVICE, 0)
    return text + '\nEND\n', exports, procs | data


def registry(meta):
    [group], [record] = meta['groups'], meta['fields']
    field, ufmp = record['field'], meta['UFMP_summary']
    check(ufmp['abi'] == 2 and group['field_count'] == 1 and field['reference'] and field['storage_bytes'] == 8,
          'One original RAF reference field and source UFL2 metadata required')
    procs = {'boom_class_ensure32', 'boom_stream_fields_init', record['symbol']}
    data = {'boom_java_unsafe_field_pool', 'boom_java_unsafe_field_names', 'boom_java_unsafe_field_pages',
        'boom_java_unsafe_field_page' + str(field['id'] >> 10), record['record_symbol'], group['class_symbol'], group['layout_symbol']}
    text = 'option casemap:none\n' + ''.join('EXTERN ' + n + (':PROC\n' if n in procs else ':BYTE\n') for n in sorted(procs | data))
    constants = dict(RFID_CLASS_COUNT=1, RFID_FIELD_COUNT=1, RFID_POOL_BYTES=128, RFID_UFMP_ABI=ufmp['abi'],
        RFID_UFMP_TYPES=ufmp['type_capacity'], RFID_UFMP_FIELDS=ufmp['declared_fields'],
        RFID_UFMP_PAGES=ufmp['pages'], RFID_UFMP_NAME_UNITS=ufmp['name_units'])
    text += ''.join(name + ' EQU ' + str(value) + '\n' for name, value in constants.items())
    text += '.const\nALIGN 8\nrfid_groups LABEL BYTE\n'
    text += f" QWORD OFFSET {group['class_symbol']},OFFSET {group['layout_symbol']}\n DWORD 0,1\n QWORD {group['payload_bytes']}\n DWORD {group['reference_prefix']},{group['layout_field_count']}\n"
    units = [int.from_bytes(record['name'].encode('utf-16le')[i:i+2], 'little') for i in range(0, len(record['name'].encode('utf-16le')), 2)]
    text += f"ALIGN 8\nrfid_fields DWORD {field['class_id']},{field['field_index']},{field['id']},{field['kind']},8,1,{record['offset']},{len(units)}\n"
    text += f" QWORD OFFSET {record['symbol']},OFFSET {record['record_symbol']},OFFSET rfid_name,OFFSET rfid_rows\n"
    text += f" DWORD {len(record['FMAP']['rows'])},{field['access']}\n QWORD OFFSET boom_java_unsafe_field_page{field['id'] >> 10}\n"
    text += 'ALIGN 2\nrfid_name WORD ' + ','.join(map(str, units + [0])) + '\nALIGN 8\nrfid_rows LABEL DWORD\n'
    text += ''.join(f" DWORD {row['receiver_class']},{row['offset']}\n" for row in record['FMAP']['rows'])
    text += f"ALIGN 8\nrfid_stream_table DWORD 053465442h,1\n QWORD OFFSET {group['layout_symbol']}\n DWORD {record['offset']},8\n QWORD 0\n"
    text += '.data\nALIGN 8\nPUBLIC ' + POOL + '\n' + POOL + ' DWORD 044494652h,1,RFID_POOL_BYTES,0\n'
    text += ' DWORD 1,1,0,0\n QWORD OFFSET rfid_fields,OFFSET rfid_groups,OFFSET boom_java_unsafe_field_pool,0\n QWORD 0,0\n'
    text += 'PUBLIC ' + STREAM_POOL + '\n' + STREAM_POOL + ' DWORD 05346504Ch,1\n QWORD OFFSET rfid_stream_table,0,0\n QWORD 0,0\n'
    text += KERNEL.read_text() + '\nEND\n'
    return text, {POOL, SERVICE, STREAM_POOL}, procs | data
