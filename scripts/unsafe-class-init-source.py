"""Bind original private Unsafe class initialization natives to frozen mirror IDs."""
OWNER = 'jdk/internal/misc/Unsafe'
POOL = 'boom_provider_unsafe_class_init_pool'
SERVICE = 'boom_provider_unsafe_class_init'
SPECS = [('ensureClassInitialized0', '(Ljava/lang/Class;)V'),
         ('shouldBeInitialized0', '(Ljava/lang/Class;)Z')]
KERNELS = ['classes32.asm', 'exceptions.asm', 'frames.asm', 'java_classes.asm', 'objects.asm', 'heap.asm']
MODULES = ['class_literals', 'class_initialization_map']
POLICY = dict(normal_source_layouts=True, original_class_initializers=True, canonical_Class_mirrors=True,
              ordinary_classes_and_interfaces=True, primitive_and_array_initialization=False,
              query_runs_initializer=False, source_native_frames=True, dynamic_class_loading=False)


def index(summary, classes, S):
    owners = [c for c in classes if c['name'] == OWNER and c['origin']['loader'] == 'bootstrap']
    S.check(len(owners) == 1, 'Missing or ambiguous original Unsafe')
    owner = owners[0]
    origin = owner['origin']
    S.check(origin['source_id'] == 'jdk:java.base' and not origin.get('generated') and owner['access'] == 0x31,
            'Unsafe must be the original final bootstrap class')
    reader = S.module('unsafe_class_init_original', 'verify-batch-frames.py')
    name, raw = reader.original_methods(S.original_class(summary, owner))
    S.check(name == OWNER and len(raw) == len(owner['method_ids']), 'Unsafe class inventory differs')
    methods = []
    for op, (name, descriptor) in enumerate(SPECS):
        matches = [(i, m) for i, m in zip(owner['method_ids'], raw)
                   if (m['name'], m['descriptor']) == (name, descriptor)]
        S.check(len(matches) == 1 and matches[0][1]['access'] == 0x102 and matches[0][1]['code'] is None,
                'Unsafe private native declaration differs')
        methods.append(dict(method=matches[0][0], class_id=owner['id'], class_sha256=origin['sha256'],
                            loader='bootstrap', source_id='jdk:java.base', owner=OWNER, name=name,
                            descriptor=descriptor, access=0x102, operation=op))
    capacity = summary['class_literals']['type_capacity']
    S.check(0 < capacity <= 0x100000 and capacity == summary['class_lookup']['type_capacity'] and
            summary['class_lookup']['initialization_record_bytes'] == 16 and summary['class_literals']['abi'] == 1,
            'Unsafe mirror/initialization ABI differs')
    return dict(schema=1, methods=methods, type_capacity=capacity, owner=owner['id'],
                source_transform_chain='original_locked_no_transforms')


def data(metadata):
    layout = f"boom_layout{metadata['owner']}"
    return (f".const\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 05543494Eh,1,{metadata['type_capacity']},0\n"
            f" QWORD OFFSET boom_java_class_pool,OFFSET boom_java_class_initialization_map,OFFSET boom_heap_ptr,OFFSET {layout}\n")


def native_imports(metadata):
    procedures = {'boom_java_class_typeid', 'boom_heap_contains', 'boom_object_check', 'boom_trace_enter', 'boom_trace_leave'}
    data_symbols = {'boom_java_class_pool', 'boom_java_class_initialization_map', 'boom_heap_ptr',
                    'boom_trace_pool', f"boom_layout{metadata['owner']}"}
    data_symbols.update(f"boom_trace_method{m['method']}" for m in metadata['methods'])
    return procedures, data_symbols


def source_frame(batch, plan, frame, metadata, S):
    from pathlib import Path
    S.check(frame is not None, 'Unsafe class initialization requires the source native frame overlay')
    frame = Path(frame).resolve()
    receipt = frame.with_name('verification.json')
    F = S.module('unsafe_class_init_frames', 'native-frame-overlay.py')
    S.check(F.verify(frame, batch, plan) == S.read(receipt), 'Unsafe native frame proof differs')
    rows = {r['id']: r for r in S.read(frame)['source']['original_native_declarations']}
    for m in metadata['methods']:
        r = rows.get(m['method'])
        S.check(r and r['class_id'] == m['class_id'] and r['flags'] & 32 and not r['flags'] & 128,
                'Unsafe original native frame missing')
    return dict(manifest=S.artifact(frame), verification=S.artifact(receipt))
