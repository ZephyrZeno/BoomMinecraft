"""Original Perf JNI registration table/Class/Code/Frame source projection.

Official +3 native source and actual locked Azul +1 class inputs stay distinct.
No native execution or a claim of complete PerfData/remote-VM support here.
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
OWNER = 'jdk/internal/perf/Perf'
POOL = 'boom_provider_perf_pool'
SERVICE = 'boom_provider_perf_service'
KERNEL = ROOT / 'native/providers/perf_self.asm.inc'
ABI = ROOT / 'native-config/perf-self-abi.json'
PINNED = {'perf.cpp': '89aee187e89482938e324a208f7f858ab4672bd2b43c856cf9e35d748a1ba371',
    'perfMemory.cpp': '4559257840fea1c218e5689ab0d52ae12e8d3699bf00c8ae509479bd641c4014',
    'perfMemory.hpp': '5ffb20c8bba534cb3763dcf5ae499b780f8608a6f54940956b18f2248745252f',
    'perfData.cpp': 'e539c942725c6c691deba6733eb85f922d3e9d884c1a8ef58a92a5e358d39924',
    'perfData.hpp': 'e92e4b36ab6b817bb2b3312a7c37ada76355d07687eb44156c3968156614693f',
    'nativeLookup.cpp': '1a62a8aadd1cac5c229aea62abd9bb7dae349171de7ef0a4ec436bcd492f6d8e',
    'os_windows.cpp': 'b26b9c90f267a0e127a2539dd4b5923a7b4d9715b03ffd69dac3ce5fba558796',
    'perfMemory_windows.cpp': '8c2c739e627cb57ad3a0e23dd9ef67ce005eba1101ac9f55e112828143e86f6a',
    'Perf.java': 'bf5bdeadfd1b4a5001d3944d5567a3702a844d8ca0a403e14bb11c1c2510c730'}


def check(value, message):
    if not value:
        raise ValueError(message)


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=sha))


def checked(row):
    expected = row.get('digest', row)
    check(artifact(row['path'])['digest'] == {key: expected[key] for key in ('size', 'sha256')}, 'Source bytes changed: ' + row['path'])
    return Path(row['path']).resolve()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def module(name, path=None):
    spec = importlib.util.spec_from_file_location('perf_original_' + name.replace('-', '_'), path or ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def original_table(pinned):
    files = {name: artifact(Path(pinned) / name) for name in PINNED}
    check(all(row['digest']['sha256'] == PINNED[name] for name, row in files.items()), 'Exact official OpenJDK +3 source changed')
    text = Path(files['perf.cpp']['path']).read_text()
    definitions = dict(re.findall(r'^#define\s+(BB|JLS|CL_ARGS|CBA_ARGS)\s+(.+)$', text, re.M))

    def expand(expression, depth=0):
        check(depth < 8, 'C descriptor macro cycle')
        parts = re.findall(r'"([^"]*)"|([A-Za-z_]\w*)', expression)
        check(parts, 'Empty native descriptor expression')
        out = ''
        for literal, name in parts:
            if name == 'CC':
                continue
            if name:
                check(name in definitions, 'Unknown original native descriptor macro')
                out += expand(definitions[name], depth + 1)
            else:
                out += literal
        return out

    a = text.index('static JNINativeMethod perfmethods[]')
    b = text.index('\n};', a)
    rows = [dict(name=name, descriptor=expand(signature), C_backend=target, operation=i + 1)
        for i, (name, signature, target) in enumerate(re.findall(r'\{CC\s+"([^"]+)"\s*,\s*(.*?)\s*,\s*FN_PTR\((\w+)\)\}', text[a:b]))]
    check(len(rows) == 6 and [r['name'] for r in rows] == ['attach0', 'detach', 'createLong', 'createByteArray', 'highResCounter', 'highResFrequency'],
          'Exact original six-method native registration table differs')
    register = text[text.index('JVM_ENTRY(void, JVM_RegisterPerfMethods'):]
    check('env->RegisterNatives(perfclass, perfmethods, sizeof(perfmethods)/sizeof(JNINativeMethod))' in register and
          'guarantee(ok == 0, "register perf natives")' in register, 'Original full registration contract differs')
    lookup = Path(files['nativeLookup.cpp']['path']).read_text()
    check(re.search(r'Java_jdk_internal_perf_Perf_registerNatives"\s*,\s*nullptr,\s*FN_PTR\(JVM_RegisterPerfMethods\)', lookup),
          'Original special native lookup binding differs')
    clock = Path(files['os_windows.cpp']['path']).read_text()
    check('return as_long(count) - initial_performance_count;' in clock and 'return performance_frequency;' in clock,
          'Windows source clock epoch/frequency changed')
    return dict(repository='openjdk/jdk21u', tag='jdk-21.0.13+3', files=files, registered_methods=rows,
        original_register_function='JVM_RegisterPerfMethods', special_native_lookup='Java_jdk_internal_perf_Perf_registerNatives',
        register_all6_and_require_RegisterNatives_result0=True,
        source_clock='QueryPerformanceCounter minus VM startup initial_performance_count; cached actual QPF frequency')


def bind(state_file, source_file, parent_file, pinned, abi_file, records_source, release_file):
    state, closure, parent = map(read, (state_file, source_file, parent_file))
    seal = read(checked(parent['source_seal']))
    check(artifact(state_file) == parent['input_state'] == seal['input_state'] and artifact(source_file) == seal['source_manifest'],
          'Exact normal source/state seal required')
    objects = parent['objects']
    check(isinstance(objects, list) and objects and len({str(Path(row['path']).resolve()).casefold() for row in objects}) == len(objects),
          'Parent must name exactly one ordered occurrence of each actual object')
    if 'actual_object_count' in parent:
        check(type(parent['actual_object_count']) is int and parent['actual_object_count'] == len(objects), 'Parent actual object population differs')
    proof = read(checked(seal['source_full_verification']))
    check(proof['verified'] is True and proof['closure_manifest_sha256'] == artifact(source_file)['digest']['sha256'],
          'Existing full source proof must bind these exact original source bytes')
    check(artifact(checked(parent['runtime']))['digest']['sha256'] == state['runtime_sha256'], 'Actual same source-state runtime bytes required')
    for name, sha in state['tool_sources'].items():
        check(artifact(ROOT / name)['digest']['sha256'] == sha, 'Current source epoch changed')
    C = original_table(pinned)
    abi = read(abi_file)
    check(abi['schema'] == 'PERF-native-AOT-self-owner-ABI-v1' and abi['pool']['bytes'] == 256 and
          abi['symbols']['pool'] == POOL and abi['symbols']['service'] == SERVICE, 'Perf native entry/owner ABI differs')
    I, R, W = module('verify-translation-ir'), module('verify-batch-frames'), module('field_COFF', records_source)
    summary_file = Path(closure['batch']) / 'summary.json'
    summary, plan = read(summary_file), Path(closure['plan'])
    image = checked(summary['frames']['original_system_catalog']).parent / 'image'
    names = {OWNER, 'jdk/internal/perf/PerfCounter', 'jdk/internal/perf/PerfCounter$CoreCounters', 'java/nio/DirectByteBuffer',
        'java/nio/Buffer', 'java/lang/String', 'java/lang/Throwable', 'java/lang/IllegalArgumentException',
        'java/lang/NullPointerException', 'java/lang/OutOfMemoryError', 'java/io/IOException'}
    classes = {}
    for line in (plan / 'classes.jsonl').open(encoding='utf-8'):
        row = json.loads(line)
        if row['name'] in names and row['origin']['loader'] == 'bootstrap':
            classes[row['name']] = row
    check(set(classes) == names, 'Original Perf/backend callback classes unavailable')
    ids = {r['id'] for r in classes.values()}
    layouts = {}
    for line in checked(summary['layouts']).open(encoding='utf-8'):
        row = json.loads(line)
        if row['class_id'] in ids:
            layouts[row['class_id']] = row
    selected = {row['class_id']: row for row in closure['selected_classes']}
    sources = {}
    inputs = [artifact(p) for p in (state_file, source_file, parent_file, abi_file, records_source, __file__, I.__file__, R.__file__,
        summary_file, plan / 'classes.jsonl', release_file)]
    inputs += list(C['files'].values()) + [parent['source_seal'], seal['source_full_verification'], summary['layouts'],
        summary['frames']['original_system_catalog']]
    release_file = Path(release_file).resolve()
    values = dict(re.findall(r'^([A-Z_]+)="([^"]*)"$', release_file.read_text(), re.M))
    check(values.get('JAVA_VERSION', '').split('.')[:3] == ['21','0','13'] and values.get('OS_ARCH') == 'x86_64' and values.get('IMPLEMENTOR'),
          'Explicit installed JDK21.0.13 x64 original Class reference required')
    jmod = release_file.parent / 'jmods/java.base.jmod'
    inputs.append(artifact(jmod))
    with zipfile.ZipFile(jmod) as installed:
        installed_hashes = {name: hashlib.sha256(installed.read('classes/' + name + '.class')).hexdigest() for name in classes}
    for name, cls in classes.items():
        path = image / cls['origin']['jar_entry']
        check(path.resolve().is_relative_to(image.resolve()), 'Original class escaped locked image')
        raw = path.read_bytes()
        source = I.Source(raw)
        check(installed_hashes[name] == hashlib.sha256(raw).hexdigest(), 'Installed release and locked original Class bytes differ')
        _, annotations = R.original_methods(raw)
        check(hashlib.sha256(raw).hexdigest() == cls['origin']['sha256'] and source.name == name and
              int.from_bytes(raw[6:8], 'big') == 65 and cls['origin']['source_id'] == 'jdk:java.base' and
              len(source.methods) == len(cls['method_ids']) and len(annotations) == len(cls['method_ids']), 'Original Class inventory differs')
        check(cls['id'] in selected and selected[cls['id']]['source_sha256'] == cls['origin']['sha256'] and
              layouts[cls['id']]['candidate'] is not None and layouts[cls['id']]['diagnostic'] is None, 'Normal selected source class/layout required')
        methods = []
        for ident, method, annotation in zip(cls['method_ids'], source.methods, annotations):
            code = source.code(method)
            digest = hashlib.sha256(code['bytes']).hexdigest() if code else None
            choice = closure['selected_methods'].get(str(ident), {})
            methods.append(dict(method=ident, class_id=cls['id'], class_sha256=cls['origin']['sha256'], loader='bootstrap', source_id='jdk:java.base',
                owner=name, name=method['name'], descriptor=method['descriptor'], access=method['access'], code_sha256=digest,
                frame_flags=R.flags(name, annotation, code is None, False, False), selected_Java=bool(code and choice.get('code_sha256') == digest and
                    choice.get('source_sha256') == cls['origin']['sha256']), original_Code_hex=code['bytes'].hex() if code else None))
        sources[name] = dict(class_record=cls, original_Class=artifact(path), methods=methods, normal_layout=layouts[cls['id']],
            selected_source_class=selected[cls['id']], class_symbol='boom_class' + str(cls['id']), layout_symbol='boom_layout' + str(cls['id']))
        inputs.append(artifact(path))
        initializers = [r for r in methods if r['name'] == '<clinit>' and r['code_sha256'] is not None]
        if initializers:
            [initializer] = initializers
            check(initializer['selected_Java'] and selected[cls['id']]['initializer']['method'] == initializer['method'] and
                  selected[cls['id']]['initializer']['code_sha256'] == initializer['code_sha256'], 'Original required class initializer Code is not selected')

    def method(owner, name, descriptor):
        [row] = [r for r in sources[owner]['methods'] if (r['name'], r['descriptor']) == (name, descriptor)]
        return row

    native = [dict(method(OWNER, 'registerNatives', '()V'), operation=0)]
    native += [dict(method(OWNER, row['name'], row['descriptor']), operation=row['operation'], C_backend=row['C_backend']) for row in C['registered_methods']]
    check(all(r['code_sha256'] is None and r['frame_flags'] == 32 and r['access'] ==
          (0x10a if r['operation'] == 0 else 0x102 if r['operation'] in (1, 2) else 0x101) for r in native),
          'Exact original seven native declarations/Frame flags differ')
    check({(r['name'], r['descriptor']) for r in sources[OWNER]['methods'] if r['code_sha256'] is None and r['access'] & 0x100} ==
          {(r['name'], r['descriptor']) for r in native}, 'Original native inventory contains an unregistered extra/missing method')
    clinit = method(OWNER, '<clinit>', '()V')
    check(clinit['selected_Java'], 'Original register-before-instance class initializer must stay selected')
    callbacks = [method('java/nio/DirectByteBuffer', '<init>', '(JILjava/lang/Object;Ljava/lang/foreign/MemorySegment;)V'),
        method('java/lang/String', 'length', '()I'), method('java/lang/String', 'toCharArray', '()[C'),
        method('java/lang/IllegalArgumentException', '<init>', '()V'), method('java/lang/IllegalArgumentException', '<init>', '(Ljava/lang/String;)V'),
        method('java/lang/NullPointerException', '<init>', '()V'), method('java/lang/OutOfMemoryError', '<init>', '()V'),
        method('java/lang/OutOfMemoryError', '<init>', '(Ljava/lang/String;)V'), method('java/io/IOException', '<init>', '(Ljava/lang/String;)V')]
    check(all(r['selected_Java'] for r in callbacks), 'Required ordinary original backend Java callback is not selected')
    frame = read(checked(closure['runtime_frame_overlay']['reference']['manifest']))
    wanted = {'boom_trace_method' + str(row['method']): 32 for row in native}
    actual = W.coff_records(checked(frame['object']), wanted)
    check(set(actual) == set(wanted), 'Actual original seven native Frame descriptors missing')
    for row in native:
        item = actual['boom_trace_method' + str(row['method'])]
        raw = bytes.fromhex(item['bytes'])
        check(struct.unpack_from('<II', raw) == (row['method'], 32) and struct.unpack_from('<I', raw, 20)[0] == row['class_id'] and
              [(r['offset'], r['type'], r['target']) for r in item['relocations']] == [(8, 1, 'boom_t' + str(row['class_id']))],
              'Actual original native Frame binding differs')
    inputs += [closure['runtime_frame_overlay']['reference']['manifest'], closure['runtime_frame_overlay']['reference']['verification'], frame['object']]
    # Direct constructor callbacks require the real normal Throwable backend.
    selected_packs = [closure['runtime_provider_packs'][index] for index in closure['selected_runtime_provider_packs']]
    selected_throwable = []
    for pack in selected_packs:
        manifest = read(checked(pack['manifest']))
        if manifest['family'] == 'normal-throwable-v1':
            selected_throwable.append(pack)
    check(len(selected_throwable) == 1, 'Exactly one selected normal Throwable provider dependency is required')
    [throwable_pack] = selected_throwable
    check(read(checked(throwable_pack['verification']))['verified'] is True, 'Existing Throwable provider source receipt is not verified')
    check(summary.get('properties', {}).get('pool_abi') == 2 and summary['properties'].get('units'), 'Source property String factory ABI2 is required')
    # A JSLP80 string pool is not the PORP112 factory argument. Bind the real
    # selected module, actual data bytes, and source callback relocations.
    pools = []
    for unit in summary['properties']['units']:
        obj = checked(unit['object'])
        records = W.coff_records(obj, {'boom_java_platform_properties_pool':112, 'boom_java_properties_string_pool':80})
        if 'boom_java_platform_properties_pool' not in records:
            continue
        check('boom_java_properties_string_pool' in records, 'Selected property module lacks its actual StringPool')
        factory, strings = records['boom_java_platform_properties_pool'], records['boom_java_properties_string_pool']
        check(any(artifact(checked(row)) == artifact(obj) for row in objects), 'Required property module is not an actual parent link object')
        check(struct.unpack_from('<IIII', bytes.fromhex(factory['bytes'])) == (0x50524f50,2,0,0) and
              struct.unpack_from('<II', bytes.fromhex(strings['bytes'])) == (0x4a534c50,1), 'Actual PORP112 ABI2/StringPool80 ABI1 roles differ')
        relocs = {r['offset']:r for r in factory['relocations']}
        check(len(relocs) == len(factory['relocations']) and set(relocs) == {16,24,32,40,48,64,80,88,96,104} and
              all(r['type'] == 1 for r in relocs.values()), 'Actual property factory data relocation shape differs')
        for offset,target in [(16,'boom_heap_ptr'),(80,'boom_java_property_array'),(88,'boom_java_property_copy'),(96,'boom_java_property_literal')]:
            check(relocs[offset]['target'] == target, 'Actual source property callback relocation differs')
        check(relocs[24]['target_symbol']['section_id'] == strings['symbol']['section_id'] and
              relocs[24]['target_symbol']['value'] == strings['symbol']['value'], 'Factory must reference exactly the real same-object StringPool')
        pools.append(dict(symbol='boom_java_platform_properties_pool',ABI=2,bytes=112,object=artifact(obj),
            assembly=unit['assembly'],actual_factory=factory,actual_StringPool=strings,
            StringPool_is_nested_argument_at24_not_the_factory_argument=True))
        inputs += [unit['assembly'],unit['object']]
    check(len(pools) == 1, 'Exactly one actual selected property factory module required')
    [property_factory] = pools
    inputs += [throwable_pack['manifest'], throwable_pack['verification']]
    inputs += [artifact(ROOT / name) for name in state['tool_sources']]
    for row in inputs:
        checked(row)
    return dict(schema=1, scope='original_Perf_full_native_registration_source_Class_Code_Frame_and_backend_requirements_projection_only',
        input_state=artifact(state_file), source_selection=artifact(source_file), source_full_verification=seal['source_full_verification'],
        parent_overlay=artifact(parent_file), runtime=parent['runtime'], official_native_source=C, ABI=artifact(abi_file),
        actual_class_reference=dict(release=artifact(release_file), release_values=values, java_base_jmod=artifact(jmod), original_Class_bytes_match=True),
        required_provider_families=['normal-throwable-v1'], required_base_modules=['properties','runtime_metadata'],
        native_owner_requirement='external actual ready pureASM Owner128 and Core Job128 op0/op2/op8/op9; lifecycle open before Java, close after quiescence before VM destruction',
        property_String_factory=property_factory, tool_sources=state['tool_sources'], source_classes=sources, native_methods=native, registered_methods=native[1:], original_clinit=clinit,
        original_callbacks=callbacks, actual_native_Frame_records=actual, original_Frame_object=frame['object'],
        required_classes=sorted(ids), required_Java_methods=[r['method'] for r in callbacks],
        no_new_Java_selection_required=True, no_Java_fields_or_original_Code_changed=True,
        backend_implementation_verified=False, registered=False, SourceV_repeated=False, guest_or_Main_executed=False,
        runtime_acceptance_complete=False, inputs=inputs)


def normal_frames(meta, operations):
    operations = list(operations)
    check(operations and len(operations) == len(set(operations)) and all(type(op) is int and 0 <= op <= 6 for op in operations),
          'Explicit actual backend operation subset required')
    R = module('verify-batch-frames')
    rows = [r for r in meta['native_methods'] if r['operation'] in operations]
    procs = {'boom_class_ensure32', 'boom_trace_enter', 'boom_trace_leave', SERVICE}
    data = {POOL, 'boom_trace_pool'} | {'boom_class' + str(r['class_id']) for r in rows} | {'boom_trace_method' + str(r['method']) for r in rows}
    text = 'option casemap:none\n' + ''.join('EXTERN ' + name + (':PROC\n' if name in procs else ':BYTE\n') for name in sorted(procs | data))
    exports = set()
    for row in rows:
        names = {'boom_m' + str(row['method']), 'boom_m' + str(row['method']) + '_native'}
        exports |= names
        text += ''.join('PUBLIC ' + name + '\n' for name in sorted(names)) + R.native_adapter(row['method'], row['class_id'], POOL, SERVICE, row['operation'])
    return text + '\nEND\n', exports, procs | data
