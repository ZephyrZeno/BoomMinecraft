"""Original nine RAF IO declarations/Frames/fields and existing FIS callbacks.

This model does not implement an IO service or change FD.close0 ownership.
normal_frames requires an explicit implemented-operation subset supplied by the
independently verified service consumer. No unsupported native stub is emitted.
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
POOL = 'boom_provider_random_access_file_pool'
SERVICE = 'boom_provider_random_access_file_service'
KERNEL = ROOT / 'native/providers/raf_io_shared.asm.inc'
SPECS = [('open0', '(Ljava/lang/String;I)V', 0), ('read0', '()I', 1), ('readBytes0', '([BII)I', 2),
    ('getFilePointer', '()J', 3), ('seek0', '(J)V', 4), ('length0', '()J', 5),
    ('write0', '(I)V', 6), ('writeBytes0', '([BII)V', 7), ('setLength0', '(J)V', 8)]
PINNED = {
    'RandomAccessFile.c': '0348561d0686662f522416b909619a43cb5607c4d2e8a1de03acbcc6bc09ed58',
    'io_util.c': 'a191fba799a2f902763b8a59d5cb5df9fa5f55ca788bb4eaf22a098e05e25415',
    'io_util_md.c': 'f3630be207d35aafdd60edb8c8db0ed23e84d7092f374138cee27761a6bfdaa7',
    'io_util_md.h': '94b8e577df754524fe61dc2672bd1ed19f634defbe87afe3a05116a624ac074f',
    'io_util.h': 'ff1c363e3edecb164d2f7112dbb33996d2a1221f337264308546c57780a3a5c3',
    'FileDescriptor_md.c': '9a3342c9c65c83ece5afa193e1d24e8abec1f1ce8d742933ff5c4db994aec272',
    'jni_util_md.c': '7a7adff4a3631fa5476d1f1dc54260ea0fccc535bbb149fb72fee21ac59d38a5',
    'exceptions.cpp': 'e61beb362eda911e9f59a57bd4b2abf26e6745ce86431536d1c44aeb9c866ed4',
}


def check(value, message):
    if not value:
        raise ValueError(message)


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=digest))


def checked(row):
    got, expected = artifact(row['path']), row.get('digest', row)
    check(got['digest'] == {key: expected[key] for key in ('size', 'sha256')}, 'Source input changed: ' + row['path'])
    return Path(got['path'])


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def module(name, path=None):
    path = Path(path) if path else ROOT / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location('raf_io_' + name.replace('-', '_'), path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def original_C(pinned):
    files = {name: artifact(Path(pinned) / name) for name in PINNED}
    check(all(row['digest']['sha256'] == PINNED[name] for name, row in files.items()), 'Exact official native reference source changed')
    text = Path(files['RandomAccessFile.c']['path']).read_text()
    result = []
    for name, descriptor, operation in SPECS:
        begin = text.index('Java_java_io_RandomAccessFile_' + name + '(')
        a = text.index('{', begin)
        b, depth = a, 1
        while depth:
            b += 1
            depth += (text[b] == '{') - (text[b] == '}')
        result.append(dict(name=name, descriptor=descriptor, operation=operation,
            source_lines=[text[:begin].count('\n') + 1, text[:b].count('\n') + 1],
            body_sha256=hashlib.sha256(text[a:b + 1].encode()).hexdigest()))
    exceptions = Path(files['exceptions.cpp']['path']).read_text()
    check('if (message == nullptr)' in exceptions and 'signature = vmSymbols::void_method_signature();' in exceptions and
          'signature = vmSymbols::string_void_signature();' in exceptions, 'Null-message/default exception constructor rule changed')
    return dict(tag='jdk-21.0.13+3', files=files, native_functions=result,
        original_Class_inputs_are_separately_locked_Azul_plus1=True,
        null_JNU_exception_message_uses_original_noarg_constructor=True,
        nonnull_message_uses_original_String_constructor=True,
        open_mode_bits=dict(O_RDONLY=1, O_RDWR=2, O_SYNC=4, O_DSYNC=8, O_TEMPORARY=16),
        close_is_original_FileDescriptor_close0_not_a_RAF_native=True,
        read_bytes_null_bounds_zero_order=True, write_bytes_null_bounds_zero_order=True,
        byte_read_unsigned_and_EOF_minus1=True, write_append_always_false=True,
        seek_closed_before_negative_and_no_EOF_clamp=True,
        setLength_uses_SetFileInformationByHandle_FileEndOfFileInfo_and_min_restored_position=True)


def bind(state_file, source_file, parent_file, pinned, records_source, service_abi_file):
    state, closure, parent = map(read, (state_file, source_file, parent_file))
    service_abi = read(service_abi_file)
    check(service_abi['symbols']['quiet_drain'] == 'boom_random_access_file_io_drain' and
          service_abi['owner']['slot_offsets'] == dict(state_D=0, borrow_D=4, owned_HANDLE_Q=8, IO_SRW_Q=16, reserved_Q=24) and
          service_abi['owner']['states'] == dict(free=0, open=1, closing=2, failed_owned=3, opening=4) and
          service_abi['native_internal_job96']['offsets'] == dict(Context_Q=0, FD_Q=8, slot_Q=16, index_D=24, state_D=28,
              owned_HANDLE_Q=32, result_Q=40, flags_D=48, status_D=52, captured_OS_error_D=56, reserved_D=60,
              reserved_Q64=64, reserved_Q72=72, reserved_Q80=80, reserved_Q88=88) and
          service_abi['native_internal_job96']['status'] == dict(ok=0, miss=1, busy=2, argument=3, OS=4, invariant=5,
              capacity=7, closed=9, cleanup_retained=12) and
          service_abi['callbacks']['fir_throw_kinds'] == dict(IOException=0, FileNotFoundException=1, NullPointerException=2, IndexOutOfBoundsException=3),
          'Original shared-owner/Job96/exception wire offsets differ')
    argv = [dict(RAF_receiver=0, path_String=8, mode_int=16), dict(RAF_receiver=0),
        dict(RAF_receiver=0, byte_array=8, offset_int=16, length_int=24), dict(RAF_receiver=0),
        dict(RAF_receiver=0, position_long=8), dict(RAF_receiver=0), dict(RAF_receiver=0, byte_int=8),
        dict(RAF_receiver=0, byte_array=8, offset_int=16, length_int=24), dict(RAF_receiver=0, length_long=8)]
    check(all(service_abi['operations'][str(i)]['argv_Q_offsets'] == value for i, value in enumerate(argv)),
          'Original native argument wire offsets differ')
    check(service_abi['schema'] == 'RAF-RO-shared-NFIO-service-ABI-v1' and
          service_abi['symbols']['pool'] == POOL and service_abi['symbols']['service'] == SERVICE and
          service_abi['pool_magic'] == 'RFIO' and service_abi['pool_abi'] == 1 and service_abi['pool_bytes'] == 64 and
          service_abi['supported_mask'] == 0x3f and service_abi['admission_states'] == dict(ready=0, draining=1, closed=2) and
          service_abi['implementation_or_Main_acceptance_claimed'] is False,
          'Exact readonly shared-owner service interface required; interface is not implementation proof')
    check(service_abi['pool_offsets'] == dict(magic_D0=0, abi_D1=4, bytes_D64=8, admission_state_D=12,
          supported_mask_D=16, active_calls_D=20, legacy_capacity_D4096=24, reserved_D0=28,
          old_FIS_property_pool_Q=32, original_RFID128_pool_Q=40, old_FD_bootstrap_NFIO_pool_Q=48, reserved_Q0=56),
          'Service pool wire offsets differ')
    check(set(service_abi['operations']) == {str(op) for _, _, op in SPECS} and
          all(service_abi['operations'][str(op)]['name'] == name and
          service_abi['operations'][str(op)]['supported'] is (op < 6) for name, _, op in SPECS) and
          service_abi['open_domain']['mode'] == 1 and service_abi['open_domain']['temporary_or_RW_or_sync_or_delete_modes_claimed'] is False,
          'Readonly operation/mode domain differs')
    seal = read(checked(parent['source_seal']))
    objects = parent['objects']
    check(isinstance(objects, list) and objects and
          len({str(Path(row['path']).resolve()).casefold() for row in objects}) == len(objects),
          'One ordered occurrence of every linked parent object is required')
    if 'actual_object_count' in parent:
        check(type(parent['actual_object_count']) is int and parent['actual_object_count'] == len(objects),
              'Parent declared object population differs from its actual objects')
    check(artifact(state_file) == parent['input_state'] == seal['input_state'] and
          artifact(source_file) == seal['source_manifest'], 'Exact current original source/state required')
    for name, digest in state['tool_sources'].items():
        check(artifact(ROOT / name)['digest']['sha256'] == digest, 'Current117 source tools changed: ' + name)
    init_file = checked(parent['random_access_file_candidate'])
    init = read(init_file)
    B = module('random-access-file-initids-candidate')
    check(init['schema'] == 1 and init['family'] == 'source-random-access-file-initids-candidate',
          'Original RAF initIDs source candidate required')
    args = init['binding_inputs']
    base = B.N.bind(checked(args['state']), checked(args['source_selection']), checked(args['parent_overlay']),
        args['pinned_directory'], records_source, checked(args['release']))
    check(args['field_records_source'] == artifact(records_source), 'RAF normal field-record source differs')
    original_init_model = read(checked(parent['random_access_file_model']))
    scopes = {'original_dedicated_server_Main_RandomAccessFile_initIDs_one_FieldID_registration_only',
        'original_selected_RandomAccessFile_initIDs_one_FieldID_registration_only'}
    check(base['scope'] == 'original_selected_RandomAccessFile_initIDs_one_FieldID_registration_only' and
          init['metadata']['scope'] in scopes and original_init_model['scope'] == init['metadata']['scope'],
          'Original/formal initIDs source scope differs')
    semantic = lambda value: {key: item for key, item in value.items() if key not in ('inputs', 'scope')}
    check(semantic(base) == semantic(init['metadata']) == semantic(original_init_model),
          'Formal initIDs reprojection changed original class/field/Frame/Code semantics')
    init_sources = B.sources(base)
    check(base['input_state'] == parent['input_state'] and
          base['source_selection'] == seal['source_manifest'] and base['source_full_verification'] == seal['source_full_verification'] and
          base['runtime']['digest'] == parent['runtime']['digest'], 'Exact source/FieldID/Frame/runtime crosschain differs')
    check(set(init['units']) == set(init_sources) == {'native', 'registry'}, 'Two original initIDs objects required')
    for name, unit in init['units'].items():
        expected, exports, imports = init_sources[name]
        check(parent['objects'].count(unit['object']) == 1, 'Actual initialized RAF object must remain linked exactly once')
        check(checked(unit['assembly']).read_bytes() == expected.encode('utf-8') and
              unit['exports'] == sorted(exports) and unit['imports'] == sorted(imports),
              'Formal initIDs generator differs from original linked unit')
        checked(unit['object'])
    C = original_C(pinned)
    I, R, W = module('verify-translation-ir'), module('verify-batch-frames'), module('field_COFF', records_source)
    summary_file = Path(closure['batch']) / 'summary.json'
    summary, plan = read(summary_file), Path(closure['plan'])
    inputs = [artifact(p) for p in (state_file, source_file, parent_file, records_source, service_abi_file, __file__, summary_file,
        I.__file__, R.__file__, plan / 'classes.jsonl')]
    inputs += list(C['files'].values()) + list(B.producers().values()) + list(base['inputs']) + [parent['random_access_file_candidate'],
        parent['random_access_file_model'], parent['source_seal'], seal['source_full_verification']]
    inputs += [unit[key] for unit in init['units'].values() for key in ('assembly', 'object')]
    methods = []
    for name, descriptor, operation in SPECS:
        [row] = [r for r in base['source_classes'][OWNER]['methods'] if (r['name'], r['descriptor']) == (name, descriptor)]
        check(row['access'] == (0x101 if name == 'getFilePointer' else 0x102) and row['code_sha256'] is None and row['frame_flags'] == 32,
              'Original instance-native declaration/Frame differs')
        methods.append(dict(row, operation=operation))
    [provider_ref] = [row for row in seal['providers'] if row['family'] == 'normal-file-input-readonly-v1']
    check(provider_ref['selected'] is True, 'Shared FIS owner was not selected in the original source')
    provider_file = checked(provider_ref['manifest'])
    provider = read(provider_file)
    provider_proof_file = checked(provider_ref['verification'])
    provider_proof = read(provider_proof_file)
    check(provider_proof['verified'] is True and
          provider_proof['provider_manifest_sha256'] == artifact(provider_file)['digest']['sha256'],
          'Selected shared FIS provider receipt differs')
    check(provider['family'] == 'normal-file-input-readonly-v1' and parent['objects'].count(provider['object']) == 1 and
          provider['tool_sources'] == state['tool_sources'], 'Exact current FIS native owner/close provider required')
    fis_model_file = checked(provider['file_input_metadata'])
    fis = read(fis_model_file)
    check(any(row['owner'] == 'java/io/FileDescriptor' and row['name'] == 'close0' and row['descriptor'] == '()V'
        for row in fis['methods']), 'One original FD.close0 source owner required')
    inputs += [artifact(provider_file), artifact(provider_proof_file), provider['assembly'], provider['object'], artifact(fis_model_file)]
    inputs += [artifact(ROOT / 'native/providers/file_input_readonly.asm.inc'), artifact(ROOT / 'native/runtime/file_streams.asm'),
        artifact(ROOT / 'native/runtime/file_descriptors.asm')]
    image = checked(summary['frames']['original_system_catalog']).parent / 'image'
    wanted = {row['owner'] for row in fis['original_java']} | {'java/lang/OutOfMemoryError'}
    classes = {}
    for line in (plan / 'classes.jsonl').open(encoding='utf-8'):
        row = json.loads(line)
        if row['name'] in wanted and row['origin']['loader'] == 'bootstrap':
            classes[row['name']] = row
    check(set(classes) == wanted, 'Original callback source classes unavailable')
    callbacks, sources = [], {}
    for name, cls in classes.items():
        source_file_class = image / cls['origin']['jar_entry']
        raw, raw_artifact = source_file_class.read_bytes(), artifact(source_file_class)
        check(raw_artifact['digest']['sha256'] == cls['origin']['sha256'], 'Original callback class changed')
        source = I.Source(raw)
        check(source.name == name and len(source.methods) == len(cls['method_ids']), 'Original callback method inventory differs')
        sources[name] = dict(class_record=cls, original_class=raw_artifact)
        inputs.append(raw_artifact)
        for ident, method in zip(cls['method_ids'], source.methods):
            code = source.code(method)
            key = (name, method['name'], method['descriptor'])
            expected = next((row for row in fis['original_java'] if (row['owner'], row['name'], row['descriptor']) == key), None)
            if expected is None and key != ('java/lang/OutOfMemoryError', '<init>', '()V'):
                continue
            check(code is not None, 'Original Java callback Code missing')
            sha = hashlib.sha256(code['bytes']).hexdigest()
            chosen = closure['selected_methods'].get(str(ident), {})
            record = dict(owner=name, method=ident, class_id=cls['id'], class_sha256=cls['origin']['sha256'], name=method['name'],
                descriptor=method['descriptor'], access=method['access'], code_sha256=sha,
                selected=chosen.get('code_sha256') == sha and chosen.get('source_sha256') == cls['origin']['sha256'])
            if expected:
                check(all(record[k] == expected[k] for k in ('owner', 'method', 'class_id', 'class_sha256', 'name', 'descriptor', 'access', 'code_sha256')) and
                      record['selected'], 'Existing original FIS callback Code is not current/selected')
            callbacks.append(record)
    # Project all native-owned FD scalar fields from original source and the
    # actual normal FMAPPROC records. RAF.fd itself is retained from RFID.
    fd = base['source_classes']['java/io/FileDescriptor']
    fd_id = fd['class_record']['id']
    fields, maps = {}, {}
    with zipfile.ZipFile(checked(summary['unsafe_fields']['index'])) as archive:
        for line in archive.open('fields.jsonl'):
            row = json.loads(line)
            if row['class_id'] == fd_id and (row['name'], row['descriptor']) in {('fd', 'I'), ('handle', 'J'), ('append', 'Z')}:
                fields[row['name']] = row
    with zipfile.ZipFile(checked(summary['runtime_metadata']['index'])) as archive:
        for line in archive.open('fields.jsonl'):
            row = json.loads(line)
            if row['id'] in {f['id'] for f in fields.values()}:
                maps[row['id']] = row
    check(set(fields) == {'fd', 'handle', 'append'}, 'Original three FD native fields missing')
    fd_fields, targets = [], {'boom_trace_method' + str(row['method']): 32 for row in methods}
    for name, width in [('fd', 4), ('handle', 8), ('append', 1)]:
        field = fields[name]
        fmap = maps[field['id']]
        [physical] = [f for f in fd['normal_layout']['candidate']['fields'] if f['member']['owner'] == fd_id and
            f['member']['index'] == field['field_index']]
        check(field['access'] == 2 and field['storage_bytes'] == physical['storage_bytes'] == fmap['storage_bytes'] == width and
              not field['reference'] and not physical['reference'] and not fmap['reference'] and field['address_map'] == field['id'] and
              dict(receiver_class=fd_id, offset=physical['offset']) in fmap['rows'], 'Original FD scalar field source/layout differs')
        record = dict(field=field, FMAP=fmap, offset=physical['offset'], symbol='boom_field_map' + str(field['id']),
            record_symbol='boom_batch_field_record' + str(field['id']))
        fd_fields.append(record)
        targets.update({record['symbol']: 19, record['record_symbol']: 32 + len(fmap['rows']) * 8})
    frame = read(checked(closure['runtime_frame_overlay']['reference']['manifest']))
    objects = [frame['object']] + [unit['object'] for unit in summary['runtime_metadata']['units']]
    inputs += [closure['runtime_frame_overlay']['reference']['manifest'], closure['runtime_frame_overlay']['reference']['verification']]
    actual = {}
    for obj in objects:
        linked = [row for row in parent['objects'] if Path(row['path']).resolve() == Path(obj['path']).resolve()]
        check(len(linked) == 1 and artifact(checked(obj)) == artifact(checked(linked[0])),
              'Required original native Frame/field COFF is not linked in exact parent')
        inputs.append(obj)
        for name, value in W.coff_records(obj['path'], targets).items():
            check(name not in actual, 'Duplicate source Frame/FMAPPROC')
            actual[name] = dict(value, object=obj)
    check(set(actual) == set(targets), 'Actual original native Frames/FD field maps unavailable')
    for method in methods:
        value = actual['boom_trace_method' + str(method['method'])]
        raw = bytes.fromhex(value['bytes'])
        check(struct.unpack_from('<II', raw) == (method['method'], 32) and struct.unpack_from('<I', raw, 20)[0] == method['class_id'] and
              [(r['offset'], r['type'], r['target']) for r in value['relocations']] == [(8, 1, 'boom_t' + str(method['class_id']))],
              'Actual original native Frame record differs')
    for record in fd_fields:
        addr, data = actual[record['symbol']], actual[record['record_symbol']]
        raw = bytes.fromhex(data['bytes'])
        f, rows = record['field'], record['FMAP']['rows']
        check(struct.unpack_from('<IIIIII', raw) == (0x464d4150, 1, len(rows), f['storage_bytes'], 0, 0) and
              [dict(receiver_class=a, offset=b) for a, b in struct.iter_unpack('<II', raw[32:])] == rows,
              'Actual FD field-map bytes/receiver offsets differ')
        [reloc] = data['relocations']
        check(reloc['offset'] == 24 and reloc['type'] == 1 and reloc['target_symbol']['section_id'] == data['symbol']['section_id'] and
              reloc['target_symbol']['value'] == data['symbol']['value'] + 32, 'Actual FD inline row relocation differs')
        check(addr['bytes'] == '4c8d05000000004c8d0d00000000e900000000' and
              [(r['offset'], r['type'], r['target']) for r in addr['relocations']] == [(3, 4, record['record_symbol']),
              (10, 4, 'boom_runtime_type_map'), (15, 4, 'boom_field_address')], 'Actual FD field-address PROC differs')
    old_asm = checked(provider['assembly']).read_text(encoding='utf-8')
    macros = {}
    for line in old_asm.splitlines():
        found = re.fullmatch(r'([A-Z][A-Z_0-9]*)\s+(TEXTEQU|EQU)\s+(.+)', line)
        if found:
            macros[found.group(1)] = dict(kind=found.group(2), value=found.group(3))
    for key, record in [('FIR_FD_INT', fd_fields[0]), ('FIR_FD_HANDLE', fd_fields[1]), ('FIR_FD_APPEND', fd_fields[2])]:
        check(macros[key]['value'] == str(record['offset']), 'Existing FIS native field macro differs')
    check('fir_throw PROC PRIVATE FRAME' in old_asm and 'fir_path PROC PRIVATE FRAME' in old_asm and
          old_asm.count('boom_m' + str(next(r['method'] for r in fis['methods'] if r['owner'] == 'java/io/FileDescriptor' and r['name'] == 'close0')) + ' PROC') == 1,
          'Original private helper/single FD.close0 Frame source missing')
    for item in inputs:
        checked(item)
    return dict(schema=1, scope='unregistered_original_RAF_nine_IO_native_source_field_callback_Frame_projection_only',
        input_state=artifact(state_file), source_selection=artifact(source_file), source_full_verification=seal['source_full_verification'],
        parent_overlay=artifact(parent_file), runtime=parent['runtime'], owner=base['owner'],
        service_ABI_source=artifact(service_abi_file), declared_service_ABI=service_abi,
        native_inventory=methods, official_C=C, original_RAF_Class_and_FieldID_source=base,
        formal_initIDs_producers=B.producers(), original_initIDs_units=init['units'],
        original_initIDs_input=parent['random_access_file_candidate'],
        original_initIDs_model=parent['random_access_file_model'],
        existing_FIS_provider=artifact(provider_file), existing_FIS_model=artifact(fis_model_file),
        existing_FIS_assembly=provider['assembly'], existing_FIS_object=provider['object'], existing_FIS_macros=macros,
        original_FD_fields=fd_fields, actual_original_Frame_and_field_records=actual, original_java_callbacks=callbacks,
        extra_callback_source_classes=sources, no_new_Java_Code_or_classes_for_existing_FIS_callbacks=True,
        required_base_modules=['runtime_metadata', 'unsafe_fields', 'frames', 'properties'],
        proposed_service=dict(symbol=SERVICE, pool=POOL, bytes=64, abi=1, ready=0, draining=1, closed=2,
            supported_mask_offset=16, active_offset=20, capacity_offset=24, capacity=4096,
            property_pool_offset=32, RFID_pool_offset=40, NFIO_pool_offset=48,
            first_consumer_support_mask=0x3f, first_consumer_readonly_FILE_TYPE_DISK_only=True, device_path_blacklist_or_strict_regular_file_test=False,
            unsupported_RW_mode_sets_Context20=True, supported_operations_are_not_verified_by_this_projection=True),
        shared_exception_helper=dict(symbol='fir_throw', visibility='private_same_composite_object',
            ABI='ctxRCX,PROP112poolRDX,kindR8D(IOE0/FNF1/NPE2/IOBE3),capturedWinErrorR9D; stack pathString/defaultUTF16/defaultUnits',
            original_Java_constructors_retained=True, must_release_every_OS_lock_and_native_borrow_before_Java=True,
            new_helper_or_temporary_root_bank_added=False,
            retains_existing_explicit_quiescent_GC_scope=True, does_not_claim_automatic_stack_root_scanning=True,
            exact_all_original_OOM_sites_not_proven=True),
        original_FD_close0_Frame_and_existing_FIS_prefix_must_remain_byteexact=True,
        no_new_native_close0_definition=True, no_new_Java_oop_root_bank=True,
        source_V_repeated=False, service_implementation_verified=False, guest_or_Main_executed=False,
        registered=False, runtime_acceptance_complete=False, inputs=inputs)


def normal_frames(meta, operations):
    """Emit only the independently implemented operations requested by consumer.

    The actual service/owner proof must bind this operation list separately.
    This producer deliberately has no default selecting all nine declarations.
    """
    operations = list(operations)
    check(operations and len(operations) == len(set(operations)) and all(type(op) is int and 0 <= op < 9 for op in operations),
          'A nonempty explicit unique implemented-operation subset is required')
    mask = meta['proposed_service']['first_consumer_support_mask']
    check(all(mask & (1 << op) for op in operations), 'An operation outside this service support mask cannot get a native Frame')
    R = module('verify-batch-frames')
    rows = [row for row in meta['native_inventory'] if row['operation'] in operations]
    check({row['operation'] for row in rows} == set(operations), 'Native service operation/declaration mismatch')
    procs = {SERVICE, 'boom_class_ensure32', 'boom_trace_enter', 'boom_trace_leave'}
    data = {POOL, 'boom_trace_pool'} | {'boom_class' + str(row['class_id']) for row in rows} | {'boom_trace_method' + str(row['method']) for row in rows}
    text = 'option casemap:none\n' + ''.join('EXTERN ' + n + (':PROC\n' if n in procs else ':BYTE\n') for n in sorted(procs | data))
    exports = set()
    for row in rows:
        names = {'boom_m' + str(row['method']), 'boom_m' + str(row['method']) + '_native'}
        exports |= names
        text += ''.join('PUBLIC ' + n + '\n' for n in sorted(names)) + R.native_adapter(row['method'], row['class_id'], POOL, SERVICE, row['operation'])
    return text + '\nEND\n', exports, procs | data
