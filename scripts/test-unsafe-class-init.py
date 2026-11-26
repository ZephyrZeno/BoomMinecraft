"""Development FFI test of the native service against an original source image."""
import argparse
import ctypes as c
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import zipfile

P = c.c_void_p
U32 = c.c_uint32
U64 = c.c_uint64
Context = U64 * 4
Args = P * 2


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def func(dll, name, result, *args):
    f = getattr(dll, name)
    f.restype, f.argtypes = result, args
    return f


def address(dll, name):
    return c.addressof(c.c_ubyte.in_dll(dll, name))


def ptr(addr, offset):
    return P.from_address(addr + offset).value


def word(addr, offset):
    return U32.from_address(addr + offset).value


def clear_status(context):
    return word(c.addressof(context), 0) == 0 and word(c.addressof(context), 12) == 0


def run(runtime_dir, directory, kernel):
    proof = json.loads((directory / 'selection-verification.json').read_bytes())
    closure = directory / 'closure.json'
    check(proof['verified'] and proof['closure_manifest_sha256'] == digest(closure), 'Source closure receipt differs')
    selection = json.loads(closure.read_bytes())
    states = {r['name']: r for r in selection['selected_classes']}
    batch = json.loads((Path(selection['batch']) / 'summary.json').read_bytes())
    with zipfile.ZipFile(batch['runtime_metadata']['index']['path']) as z:
        ids = {t['name']: t['id'] for line in z.open('types.jsonl') if (t := json.loads(line))['defining_loader'] == 'bootstrap'}
    rt_file = runtime_dir / 'boom-runtime.dll'
    check(digest(rt_file) == json.loads((runtime_dir / 'runtime.json').read_bytes())['sha256'], 'Runtime DLL changed')
    image_file = directory / 'diagnostic-image.dll'
    with os.add_dll_directory(str(runtime_dir)):
        rt, image = c.CDLL(str(rt_file)), c.CDLL(str(image_file))
        code = c.CDLL(str(kernel)) if kernel else image
    cp = address(image, 'boom_java_class_pool')
    unsafe_id = ids['jdk/internal/misc/Unsafe']
    if kernel:
        # Only the provider's pool is a fixture. Its four pointers all refer to
        # original source image data. No native frame wrapper is tested here.
        layout_map = ptr(cp, 40)
        table = ptr(layout_map, 16)
        layout = next(ptr(table + i * 40, 0) for i in range(word(layout_map, 8))
                      if word(table + i * 40, 16) == unsafe_id and word(table + i * 40, 20) == 0)
        fixture_pool = (U64 * 6)(0x15543494e, word(cp, 12), cp, address(image, 'boom_java_class_initialization_map'),
                                 ptr(cp, 48), layout)
        pool = c.addressof(fixture_pool)
    else:
        check(selection.get('all_source_initializer_map'), 'Image did not link the all-source initializer map')
        pool = address(image, 'boom_provider_unsafe_class_init_pool')
        manifests = (json.loads(Path(r['manifest']['path']).read_bytes()) for r in selection['runtime_provider_packs'])
        members = [m for m in manifests if m['family'] == 'normal-unsafe-class-initialization-v1']
        check(len(members) == 1, 'Image does not contain the original Unsafe provider')
        entry = {r['operation']: func(image, f"boom_m{r['method']}", U64, P, P) for r in members[0]['methods']}
    check(ptr(pool, 16) == cp and word(pool, 8) == word(cp, 12), 'Class pool mismatch')
    service = func(code, 'boom_provider_unsafe_class_init', U64, P, P, P, U32)
    load_class = func(rt, 'boom_java_class_load', P, P, P, U32)
    allocate = func(rt, 'boom_object_new', P, P, P, P)
    destroy = func(rt, 'boom_heap_destroy', U32, P)
    release = func(image, 'boom_release_trace_pool', U32)
    heap = func(rt, 'boom_heap_create', P, U64)(64 << 20)
    check(heap, 'Heap allocation failed')
    try:
        check(func(image, 'boom_java_string_literals_bind_heap', U32, P)(heap) == 1, 'Heap bind failed')
        ctx = Context()
        receiver = allocate(heap, ptr(pool, 40), ctx)
        check(receiver and clear_status(ctx), 'Source Unsafe receiver allocation failed')

        def mirror(name):
            value = load_class(ctx, cp, ids[name])
            check(value and clear_status(ctx), f'Class mirror failed for {name}, context={list(ctx)}')
            return value

        def invoke(op, context, argv):
            return service(context, argv, pool, op) if kernel else entry[op](context, argv)

        for name in ('I', 'V', '[I'):
            args = Args(receiver, mirror(name))
            check(invoke(1, ctx, args) == 0 and invoke(0, ctx, args) == 0 and clear_status(ctx), f'Primitive/array failed: {name}')
        target = 'java/util/concurrent/atomic/AtomicInteger'
        state = states[target]
        descriptor = address(image, f"boom_class{state['class_id']}")
        args = Args(receiver, mirror(target))
        check(state['initializer'] and word(descriptor, 8) == 0 and invoke(1, ctx, args) == 1 and
              word(descriptor, 8) == 0 and clear_status(ctx), 'Query initialized a cold original class')
        gate = Barrier(8, timeout=15)

        def initialize(_):
            worker = Context()
            gate.wait()
            check(invoke(0, worker, args) == 0 and clear_status(worker), f'Contended initialization failed {list(worker)}')
            check(invoke(1, worker, args) == 0 and clear_status(worker), 'Initialized state was not published')

        with ThreadPoolExecutor(8) as workers:
            list(workers.map(initialize, range(8)))
        field = next(f['index'] for f in state['fields'] if f['name'] == 'U')
        check(word(descriptor, 8) == 2 and ptr(address(image, f"boom_s{state['class_id']}_{field}"), 0),
              'AtomicInteger initializer did not publish its original static Unsafe reference')
        interface = states['java/lang/Runnable']
        descriptor = address(image, f"boom_class{interface['class_id']}")
        args = Args(receiver, mirror(interface['name']))
        check(invoke(1, ctx, args) == int(word(descriptor, 8) != 2) and invoke(0, ctx, args) == 0 and
              word(descriptor, 8) == 2 and clear_status(ctx), 'Interface initialization differs')
        for argv, expected in ((Args(None, args[1]), 4), (Args(receiver, None), 4),
                               (Args(args[1], args[1]), 7), (Args(receiver, receiver), 7)):
            failure = Context()
            check(service(failure, argv, pool, 0) == 0 and failure[0] == expected, 'Invalid receiver/mirror error differs')
        pending = Context(99, 0, 0, 123)
        check(service(pending, args, pool, 1) == 0 and list(pending) == [99, 0, 0, 123], 'Pending context changed')
        init_map = ptr(pool, 24)
        cold_name = next(name for name, i in ids.items() if name.startswith('java/lang/') and
                         not ptr(init_map, i * 16) and ptr(init_map, i * 16 + 8))
        missing = Context()
        check(invoke(1, missing, Args(receiver, mirror(cold_name))) == 0 and word(c.addressof(missing), 0) == 0xb001,
              'Missing descriptor was reported as an initialized class')
        check(release() == 0, 'Java/native frames remained active')
    finally:
        check(destroy(heap) == 1, 'Heap destruction failed')
    return dict(passed=True, scope='ASM_service_with_original_source_class_data' if kernel else 'original_framed_native_wrappers_and_ASM_service',
                parallel_OS_threads=8, original_class_initializer=target, original_static_reference_written=True,
                primitive_void_array_and_interface_checked=True, null_type_and_pending_errors_checked=True,
                unselected_descriptor_produced_source_stop=True,
                runtime_sha256=digest(rt_file), image_sha256=digest(image_file), source_closure_sha256=digest(closure),
                standalone_kernel_sha256=digest(kernel) if kernel else None, heap_and_frames_released=True, game_started=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'directory', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--kernel', type=Path)
    opts = parser.parse_args()
    output = opts.output.resolve()
    check(output.is_relative_to(Path(__file__).resolve().parents[1] / '.boom') and not output.exists(), 'Use a fresh project test receipt')
    report = run(opts.runtime.resolve(), opts.directory.resolve(), opts.kernel.resolve() if opts.kernel else None)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report))
