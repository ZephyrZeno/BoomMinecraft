"""Original Thread registration and platform primitives over normal source oops.

The existing assembly registry owns OS-thread peers. Java construction, start,
interrupts, virtual threads and arbitrary native-address atomics stay separate.
"""
import importlib.util
import json
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location('normal_thread_original_methods', Path(__file__).with_name('verify-batch-frames.py'))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
OWNER = 'java/lang/Thread'
LEGACY = (
    ('start0', '()V', 0x102), ('setPriority0', '(I)V', 0x102), ('yield0', '()V', 0x10a),
    ('sleep0', '(J)V', 0x10a), ('currentCarrierThread', '()Ljava/lang/Thread;', 0x108),
    ('currentThread', '()Ljava/lang/Thread;', 0x109), ('setCurrentThread', '(Ljava/lang/Thread;)V', 0x100),
    ('interrupt0', '()V', 0x102), ('holdsLock', '(Ljava/lang/Object;)Z', 0x109),
    ('getThreads', '()[Ljava/lang/Thread;', 0x10a),
    ('dumpThreads', '([Ljava/lang/Thread;)[[Ljava/lang/StackTraceElement;', 0x10a),
    ('getStackTrace0', '()Ljava/lang/Object;', 0x102), ('setNativeName', '(Ljava/lang/String;)V', 0x102),
    ('scopedValueCache', '()[Ljava/lang/Object;', 0x108), ('setScopedValueCache', '([Ljava/lang/Object;)V', 0x108),
    ('getNextThreadIdOffset', '()J', 0x10a), ('findScopedValueBindings', '()Ljava/lang/Object;', 0x108),
    ('ensureMaterializedForStackWalk', '(Ljava/lang/Object;)V', 0x108))
SUPPORTED = (('registerNatives', '()V', 0x10a, None),
    ('currentCarrierThread', '()Ljava/lang/Thread;', 0x108, 4),
    ('currentThread', '()Ljava/lang/Thread;', 0x109, 5),
    ('ensureMaterializedForStackWalk', '(Ljava/lang/Object;)V', 0x108, 17),
    ('yield0', '()V', 0x10a, 2), ('getNextThreadIdOffset', '()J', 0x10a, 15))
KERNELS = ['classes32.asm', 'thread_natives.asm', 'thread_registry.asm', 'runtime_types.asm', 'runtime_type_index.asm', 'types.asm', 'objects.asm', 'heap.asm']


def index(summary, classes, S):
    names = {(c['origin']['loader'], c['name']): c for c in classes}
    owner = names['bootstrap', OWNER]
    S.check(owner['origin']['source_id'] == 'jdk:java.base' and not owner['origin'].get('generated') and owner['access'] == 0x21,
            'Thread primitives require the original bootstrap class')
    name, raw = R.original_methods(S.original_class(summary, owner))
    S.check(name == OWNER and len(raw) == len(owner['method_ids']), 'Original Thread method inventory differs')
    natives = {(m['name'], m['descriptor']): (i, m) for i, m in zip(owner['method_ids'], raw) if m['access'] & 0x100}
    expected = {(n, d) for n, d, _ in LEGACY} | {('registerNatives', '()V'), ('clearInterruptEvent', '()V')}
    S.check(set(natives) == expected and len(natives) == 20, 'Actual Thread native inventory differs, including clearInterruptEvent')
    declarations = []
    for operation, (name, descriptor, access, slot) in enumerate(SUPPORTED):
        i, raw_method = natives[name, descriptor]
        S.check(raw_method['access'] == access and raw_method['code'] is None, 'Original Thread native flags/Code differ: ' + name)
        declarations.append(dict(method=i, class_id=owner['id'], class_sha256=owner['origin']['sha256'], loader='bootstrap',
            source_id='jdk:java.base', owner=OWNER, name=name, descriptor=descriptor, access=access, operation=operation))
    rows = []
    for slot, (name, descriptor, access) in enumerate(LEGACY):
        i, method = natives[name, descriptor]
        S.check(method['access'] == access and method['code'] is None, 'Thread registry slot differs from original source')
        rows.append(dict(slot=slot, method=i, name=name, descriptor=descriptor, access=access, executable=bool(0x28034 & (1 << slot))))
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as archive:
        available = {r['id']: r for line in archive.read('types.jsonl').splitlines() if (r := json.loads(line))}
    virtual = names['bootstrap', 'java/lang/BaseVirtualThread']
    for cls in (owner, virtual):
        t = available.get(cls['id'])
        S.check(t is not None and t['kind'] == 1 and t['source_sha256'] == cls['origin']['sha256'], 'Normal Thread type identity unavailable')
    return dict(schema=1, methods=declarations, registration_slots=rows, original_native_declarations=20,
        original_unregistered_declarations=[dict(method=natives['clearInterruptEvent', '()V'][0], name='clearInterruptEvent', descriptor='()V', access=0x10a)],
        thread_class=owner['id'], virtual_base_class=virtual['id'], table_abi=1, pool_abi=1, pool_bytes=80,
        executable_slot_mask=0x28034, supported_source_native_methods=6, normal_source_layouts=True, platform_threads_only=True,
        Java_constructors_executed=False, source_Thread_start_implemented=False, virtual_threads_implemented=False,
        VM_id_address_atomic_access_implemented=False, source_transform_chain='original_locked_no_transforms', game_started=False)


def data(metadata):
    out = '.const\n'
    for row in metadata['registration_slots']:
        for key in ('name', 'descriptor'):
            value = row[key].encode('ascii') + b'\0'
            out += f"provider_thread_{key}{row['slot']} LABEL BYTE\n"
            for at in range(0, len(value), 16):
                out += ' BYTE ' + ','.join(map(str, value[at:at + 16])) + '\n'
    out += 'ALIGN 8\nprovider_thread_import_cells LABEL QWORD\n'
    out += ''.join(f' QWORD OFFSET __imp_boom_thread_native_{i}\n' for i in range(18))
    out += '.data\nALIGN 8\nprovider_thread_table DWORD 0544E4154h,1,18,028034h\n'
    for row in metadata['registration_slots']:
        i = row['slot']
        out += f" QWORD OFFSET provider_thread_name{i},OFFSET provider_thread_descriptor{i},0\n DWORD {row['access']},{int(row['executable'])}\n"
    out += ('.data\nALIGN 8\nPUBLIC boom_provider_thread_registry\nboom_provider_thread_registry QWORD 0\n'
            'PUBLIC boom_provider_thread_pool\nboom_provider_thread_pool DWORD 0544E504Ch,1,0,0\n'
            f" QWORD OFFSET provider_thread_table,OFFSET boom_layout{metadata['thread_class']},OFFSET boom_runtime_type_map,"
            f"OFFSET boom_t{metadata['thread_class']},OFFSET boom_t{metadata['virtual_base_class']},"
            'OFFSET boom_provider_thread_registry,OFFSET boom_heap_ptr,0\n')
    imports = {'boom_runtime_type_map', 'boom_heap_ptr', f"boom_layout{metadata['thread_class']}",
        f"boom_t{metadata['thread_class']}", f"boom_t{metadata['virtual_base_class']}"} | {f'__imp_boom_thread_native_{i}' for i in range(18)}
    return out, imports
