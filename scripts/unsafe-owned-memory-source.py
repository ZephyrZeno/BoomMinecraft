"""Original Unsafe allocation declarations and a shadow owned-memory route model.

The normal Frame and typed-adapter ABI is already source-verified. This module
does not invent an allocation Owner/Job ABI or implement a memory service.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'jdk/internal/misc/Unsafe'
POOL = 'boom_provider_owned_unsafe_pool'
SERVICE = 'boom_provider_owned_unsafe_service'
TYPED_SERVICE = 'boom_java_unsafe_owned_domains'
SPECS = (
    ('allocateMemory0', '(J)J'),
    ('reallocateMemory0', '(JJ)J'),
    ('freeMemory0', '(J)V'),
    ('setMemory0', '(Ljava/lang/Object;JJB)V'),
    ('copyMemory0', '(Ljava/lang/Object;JLjava/lang/Object;JJ)V'),
    ('copySwapMemory0', '(Ljava/lang/Object;JLjava/lang/Object;JJJ)V'),
)
JAVA_NAMES = {
    'getAddress', 'putAddress', 'checkSize', 'checkNativeAddress', 'checkOffset',
    'checkPointer', 'checkPrimitiveArray', 'checkPrimitivePointer', 'alignToHeapWordSize',
    'allocateMemory', 'allocateMemoryChecks', 'reallocateMemory', 'reallocateMemoryChecks',
    'setMemory', 'setMemoryChecks', 'copyMemory', 'copyMemoryChecks',
    'copySwapMemory', 'copySwapMemoryChecks', 'freeMemory', 'freeMemoryChecks',
}
PLAIN_OPERATIONS = frozenset(kind + action * 16 for kind in range(1, 9) for action in (0, 1))
OLD_RO_OPERATIONS = frozenset((2, 3, 4, 5, 6))
THREAD_COUNTER_OPERATIONS = (6, 38, 70, 86)
ARGV = {
    'allocateMemory0': dict(receiver=0, bytes=8),
    'reallocateMemory0': dict(receiver=0, address=8, bytes=16),
    'freeMemory0': dict(receiver=0, address=8),
    'setMemory0': dict(receiver=0, base=8, offset=16, bytes=24, value=32),
    'copyMemory0': dict(receiver=0, source_base=8, source_offset=16, destination_base=24, destination_offset=32, bytes=40),
    'copySwapMemory0': dict(receiver=0, source_base=8, source_offset=16, destination_base=24, destination_offset=32, bytes=40, element_bytes=48),
}


def module(name):
    spec = importlib.util.spec_from_file_location('owned_unsafe_source_' + name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


I = module('verify-translation-ir')
R = module('verify-batch-frames')
G = module('verify-batch-unsafe-memory')
SC = module('jimage-unsafe-read-source')


def _references(source, code):
    result = []
    for ins in I.stream(code):
        operand = ins['operand']
        constant = operand.get('Constant') if isinstance(operand, dict) else None
        if ins['opcode'] == 0xb9:
            constant = operand['Interface']['constant']
        if constant is not None:
            symbol = source.symbol(constant)
            if 'Method' in symbol or 'Field' in symbol:
                result.append(dict(pc=ins['pc'], opcode=ins['opcode'], symbol=symbol))
    return result


def index(summary, classes, S):
    [cls] = [row for row in classes if row['name'] == OWNER and row['origin']['loader'] == 'bootstrap']
    raw = S.original_class(summary, cls)
    source = I.Source(raw)
    owner_name, annotated = R.original_methods(raw)
    S.check(source.name == owner_name == OWNER and cls['origin']['source_id'] == 'jdk:java.base' and
            not cls['origin'].get('generated') and len(source.methods) == len(annotated) == len(cls['method_ids']) and
            int.from_bytes(raw[6:8], 'big') == 65, 'Original JDK21 Unsafe declaration inventory required')
    records, java = {}, []
    for ident, method, annotation in zip(cls['method_ids'], source.methods, annotated):
        code = source.code(method)
        row = dict(method=ident, class_id=cls['id'], class_sha256=cls['origin']['sha256'],
            loader='bootstrap', source_id='jdk:java.base', owner=OWNER,
            name=method['name'], descriptor=method['descriptor'], access=method['access'])
        key = (method['name'], method['descriptor'])
        S.check(key not in records, 'Duplicate original Unsafe method identity')
        if code is None:
            row.update(code_sha256=None, frame_flags=R.flags(OWNER, annotation, True, False, False))
        else:
            S.check(annotation['code'] and annotation['code'][0] == code['bytes'], 'Independent original Code parsers disagree')
            row.update(code_sha256=hashlib.sha256(code['bytes']).hexdigest(), original_Code_hex=code['bytes'].hex(),
                source_references=_references(source, code['bytes']))
            if method['name'] in JAVA_NAMES:
                java.append(row)
        records[key] = row
    natives = []
    for operation, (name, descriptor) in enumerate(SPECS):
        row = records[name, descriptor]
        S.check(row['access'] == 0x102 and row['code_sha256'] is None and row['frame_flags'] == 32,
                'Exact original private native Frame declaration required: ' + name)
        natives.append(dict(row, operation=operation, argv_slots=ARGV[name]))
    S.check(len(java) == 26 and len({row['method'] for row in java}) == 26, 'Exact original 26 Java wrappers/checks required')
    typed, unit_rows = [], []
    for name, descriptor, access, operation in G.specs():
        row = records[name, descriptor]
        S.check(row['access'] == access and row['code_sha256'] is None and row['frame_flags'] == 32,
                'Original typed42 native source/flags differ')
        typed.append(dict(row, operation=operation, kind=operation & 15, action=operation >> 4,
            routed_to_composition=operation in PLAIN_OPERATIONS, existing_RO_read=operation in OLD_RO_OPERATIONS))
        unit_rows.append(dict(method=row['method'], class_id=cls['id'], class_sha256=cls['origin']['sha256'],
            name=name, descriptor=descriptor, access=access, operation=operation, assembly_unit=0))
    with zipfile.ZipFile(S.checked(summary['unsafe_memory']['index'])) as archive:
        S.check(archive.namelist() == ['methods.jsonl'] and
                [json.loads(line) for line in archive.read('methods.jsonl').splitlines()] == unit_rows,
                'Original typed42 source-index projection differs')
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as archive:
        names = {'Z', 'B', 'C', 'S', 'I', 'J', 'F', 'D'}
        types = {row['name']: row for line in archive.open('types.jsonl')
            if (row := json.loads(line))['name'] in names | {'[' + name for name in names}}
    arrays = []
    # JVM newarray atype, source descriptor, physical element-byte shift.
    for atype, name, shift in ((4, 'Z', 0), (5, 'C', 1), (6, 'F', 2), (7, 'D', 3),
                               (8, 'B', 0), (9, 'S', 1), (10, 'I', 2), (11, 'J', 3)):
        primitive, array = types[name], types['[' + name]
        S.check(primitive['kind'] == 0 and primitive['marker_flags'] == 'ZBCSIJFD'.index(name) and
                array['kind'] == 3 and array['parent_component'] == primitive['id'],
                'Actual primitive-array runtime type identity differs')
        arrays.append(dict(descriptor='[' + name, type_id=array['id'], component_id=primitive['id'],
            atype=atype, heap_tag=256 + atype, element_shift=shift, element_bytes=1 << shift,
            reference_prefix_slots=0, array_base_offset=0))
    bootstrap = (ROOT / 'native/runtime/java_unsafe.asm').read_text(encoding='utf-8')
    array_source = (ROOT / 'native/runtime/arrays.asm').read_text(encoding='utf-8')
    S.check('cmp DWORD PTR [rsp+32],2\n je ju_done\n ; Normal array payload starts at oop+0, independently validated above.\n xor eax,eax\n jmp ju_done' in bootstrap,
            'Actual normal Unsafe arrayBaseOffset contract changed')
    S.check('array_shifts BYTE 0,0,0,0,0,1,2,3,0,1,2,3,3' in array_source and
            'lea r9, [r12+256]' in array_source, 'Actual primitive-array tag/physical width contract changed')
    kernels = {name: S.artifact(ROOT / 'native/runtime' / name)
        for name in ('java_unsafe_fields.asm', 'java_unsafe.asm', 'arrays.asm', 'heap.asm', 'objects.asm')}
    S.check(kernels['java_unsafe.asm']['digest']['sha256'] == summary['unsafe_bootstrap']['kernel_sha256'],
            'Original Unsafe bootstrap kernel changed')
    _, prefix, validator, _, _ = SC.prefix_source()
    for name, record in kernels.items():
        if name in ('java_unsafe_fields.asm', 'heap.asm', 'objects.asm'):
            S.check(summary['unsafe_memory']['kernel_sha256']['native/runtime/' + name] == record['digest']['sha256'],
                    'Original typed-memory receiver/heap kernel changed')
    return dict(schema=1, owner=cls['id'], owner_name=OWNER, source_class=cls, methods=natives,
        original_Java=java, typed_methods=typed, primitive_arrays=arrays, Context_bytes=32,
        plain_operations=sorted(PLAIN_OPERATIONS), original_RO_operations=sorted(OLD_RO_OPERATIONS),
        original_ThreadIdentifiers_null_base_operations=list(THREAD_COUNTER_OPERATIONS),
        source_kernels=kernels, original_receiver_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),
        original_UFMP_validator_sha256=hashlib.sha256(validator.encode()).hexdigest(),
        original_typed_unit=summary['unsafe_memory']['units'][0],
        required_base_modules=['runtime_metadata', 'class_literals', 'unsafe_fields', 'unsafe_memory', 'unsafe_bootstrap', 'frames'],
        required_classes=[cls['id']], required_java_methods=[],
        normal_native_adapter_contract=dict(Context='RCX', argv='RDX', service_binding_pool='R8', semantic_operation='R9D',
            native_pool_symbol=POOL, native_service_symbol=SERVICE, typed_service_symbol=TYPED_SERVICE,
            Owner_or_Job_ABI_defined=False, service_implementation_present=False),
        policy=dict(original_26_Java_Code_preserved=True, original_normal_Frame8_used=True,
            original_42_receiver_class_adapters_preserved=True, primitive_plain_null_base_routes=16,
            additional_plain_tail_routes_over_RO_variant=11, untouched_nonplain_or_reference_tails=26,
            original_heap_and_all_4_ThreadIdentifiers_domains_must_remain=True,
            existing_5_RO_reads_and_RO_to_heap_byte_copy_must_remain=True,
            new_RW_reference_atomic_volatile_support=False, JIMAGE_writes=False, unknown_raw_address_access=False,
            native_owner_has_no_Java_oops=True, automatic_GC=False,
            native_pointer_negative_values_are_not_a_JDK_Java_validation_claim=True,
            primitive_heap_endpoint_checks=['HeapContains', 'refs==0', 'atype4..11', 'normal payload base0',
                'length<<shift overflow', 'offset+bytes overflow', 'complete physical byte range'],
            copyMemory0_exactly_one_definition=True, pending_Context_all32_bytes_preserved=True),
        registered=False, native_service_implemented=False, executed=False, game_started=False)


def compare_reference(meta, reference, S):
    """Compare source identity; local plan/class/method numbers are not a schema."""
    for actual_key, reference_key in (('methods', 'allocation_set_copy_native_declarations'),
                                     ('original_Java', 'original_Java_wrappers_and_checks'),
                                     ('typed_methods', 'original_typed42_native_inventory')):
        actual = {(row['owner'], row['name'], row['descriptor']): row for row in meta[actual_key]}
        expected = {(row['owner'], row['name'], row['descriptor']): row for row in reference[reference_key]}
        S.check(set(actual) == set(expected), 'Locked semantic source identity coverage changed')
        for key, row in actual.items():
            S.check(all(row[name] == expected[key][name] for name in ('class_sha256', 'loader', 'source_id', 'access', 'code_sha256')),
                    'Original declaration/Code identity changed: ' + str(key))


def normal_frames_assembly(meta):
    procs = {'boom_class_ensure32', 'boom_trace_enter', 'boom_trace_leave', SERVICE}
    data = {POOL, 'boom_class' + str(meta['owner']), 'boom_trace_pool'} | {
        'boom_trace_method' + str(row['method']) for row in meta['methods']}
    text = 'option casemap:none\n' + ''.join('EXTERN ' + name + (':PROC\n' if name in procs else ':BYTE\n')
        for name in sorted(procs | data))
    exports = set()
    for row in meta['methods']:
        names = {'boom_m' + str(row['method']) + suffix for suffix in ('', '_native')}
        exports |= names
        text += ''.join('PUBLIC ' + name + '\n' for name in sorted(names))
        text += R.native_adapter(row['method'], meta['owner'], POOL, SERVICE, row['operation'])
    return text + '\nEND\n', exports, procs | data


def typed_assembly(meta):
    exports = {'boom_m' + str(row['method']) + suffix for row in meta['typed_methods'] for suffix in ('', '_native')}
    imports = {'boom_java_unsafe_field_pool', 'boom_class' + str(meta['owner']),
        'boom_class_ensure32', 'boom_java_unsafe_memory', TYPED_SERVICE}
    data = {'boom_java_unsafe_field_pool', 'boom_class' + str(meta['owner'])}
    text = 'option casemap:none\n' + ''.join('EXTERN ' + name + (':BYTE\n' if name in data else ':PROC\n') for name in sorted(imports))
    for row in meta['typed_methods']:
        body = G.body(row)
        if row['operation'] in PLAIN_OPERATIONS:
            assert body.count(' jmp boom_java_unsafe_memory\n') == 1
            body = body.replace(' jmp boom_java_unsafe_memory\n', ' jmp ' + TYPED_SERVICE + '\n', 1)
        text += ''.join('PUBLIC boom_m' + str(row['method']) + suffix + '\n' for suffix in ('', '_native')) + body
    return text + '\nEND\n', exports, imports


def legacy_copy_service_assembly(copy_metadata):
    """Retain the proven old RO service, removing only its now-shared adapter.

    This is a source extraction, not a new native definition or RW extension.
    Its actual canonical COFF must be checked separately before composition.
    """
    C = module('jimage-unsafe-copy-source')
    text, exports, imports = C.assembly(copy_metadata)
    [row] = copy_metadata['methods']
    ident = row['method']
    declarations = f'PUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
    adapter = R.native_adapter(ident, copy_metadata['owner'], 'boom_java_unsafe_field_pool', C.SERVICE, 0).removeprefix('.code\n')
    assert text.count(declarations) == text.count(adapter) == 1
    result = text.replace(declarations, '', 1).replace(adapter, '', 1)
    kept = set(imports)
    for name in sorted(imports):
        declaration = re.search(r'(?m)^EXTERN ' + re.escape(name) + r':(?:PROC|BYTE)\n', result)
        assert declaration is not None
        without = result[:declaration.start()] + result[declaration.end():]
        if re.search(r'\b' + re.escape(name) + r'\b', without) is None:
            result = without
            kept.remove(name)
    assert re.findall(r'(?m)^PUBLIC (\w+)$', result) == [C.SERVICE]
    assert f'boom_m{ident} PROC' not in result and f'boom_m{ident}_native PROC' not in result
    proof = dict(original_full_assembly_sha256=hashlib.sha256(text.encode()).hexdigest(),
        exact_removed_adapter_sha256=hashlib.sha256(adapter.encode()).hexdigest(),
        exact_removed_public_text=declarations, only_original_service_and_validator_retained=True,
        removed_unused_EXTERNS=sorted(set(imports) - kept), duplicate_copy_native_definition=False,
        old_readonly_service_semantics_changed=False)
    return result, {C.SERVICE}, kept, proof
