"""Exercise the source Reference service and the real native shutdown boundary."""
import argparse
import ctypes as c
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from threading import Barrier, Event
import time
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
P, U, Q = c.c_void_p, c.c_uint32, c.c_uint64
Context = Q * 4


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def require(value, description):
    if not value:
        raise ValueError(description)


def bind(dll, name, result, *args):
    f = getattr(dll, name)
    f.restype, f.argtypes = result, args
    return f


def run(runtime, out, assembler, linker, kernel32, selection=None):
    C = module('reference-processing-source')
    runtime = runtime.resolve()
    lib = runtime / 'boom-runtime.dll'
    metadata = json.loads((runtime / 'runtime.json').read_bytes())
    require(metadata['sha256'] == sha(lib) and all(
        metadata['sources']['native/runtime/' + n] == sha(ROOT / 'native/runtime' / n) for n in C.KERNELS),
        'Reference runtime sources differ')
    if selection is None:
        imports = ''.join(f'EXTERN {s}:PROC\n' for s in sorted(C.PROCEDURES))
        source = ('option casemap:none\n' + imports + '.data\nPUBLIC boom_heap_ptr\nboom_heap_ptr QWORD 0\n' +
                  C.data() + (ROOT / 'native/providers/reference_processing.asm.inc').read_text(encoding='utf-8') + '\nEND\n')
        asm, obj, dll = out/'provider.asm', out/'provider.obj', out/'provider.dll'
        asm.write_text(source, encoding='utf-8')
        exports = C.CONTROL | {C.POOL, C.SERVICE, 'boom_heap_ptr'}
        with (out/'build.log').open('wb') as log:
            subprocess.run([str(assembler), '/nologo', '/c', '/Fo' + str(obj), str(asm)], check=True, stdout=log, stderr=subprocess.STDOUT)
            subprocess.run([str(linker), '/nologo', '/dll', '/noentry', '/machine:x64', '/out:' + str(dll),
                            *(f'/export:{s}' for s in sorted(exports)), str(obj), str(runtime/'boom-runtime.lib'),
                            str(kernel32)], check=True, stdout=log, stderr=subprocess.STDOUT)
        require(module('verify-batch-assembly').coff_symbols(obj, C.FOREIGN) == (exports, C.PROCEDURES),
                'Actual provider COFF imports/exports differ')
        require(module('diagnostic-closure').pe_exports(dll) == exports, 'Actual provider DLL exports differ')
    else:
        selection = selection.resolve()
        proof = json.loads((selection/'selection-verification.json').read_bytes())
        closure = json.loads((selection/'closure.json').read_bytes())
        require(proof['verified'] and proof['closure_manifest_sha256'] == sha(selection/'closure.json'),
                'Original source image changed')
        packs = [json.loads(Path(r['manifest']['path']).read_bytes()) for r in closure['runtime_provider_packs']]
        [pack] = [p for p in packs if p['family'] == 'normal-reference-processing-v1']
        dll = selection/'diagnostic-image.dll'
    with os.add_dll_directory(str(runtime)):
        rt, image = c.CDLL(str(lib)), c.CDLL(str(dll))
    pool = c.addressof(c.c_ubyte.in_dll(image, C.POOL))
    heap_cell = P.from_address(P.from_address(pool+16).value)
    owner = {s: bind(image, 'boom_provider_reference_'+s, U, P) for s in ('open', 'stop', 'close')}
    boundary = bind(image, 'boom_provider_reference_boundary', U, P, P)
    if selection is None:
        kernel = bind(image, C.SERVICE, Q, P, P, P, U)
        def guest(ctx, op):
            return kernel(ctx, None, pool, op)
    else:
        entries = {m['operation']: bind(image, f"boom_m{m['method']}", Q, P, P) for m in pack['methods']}
        def guest(ctx, op):
            return entries[op](ctx, None)
    read_count = lambda offset: Q.from_address(pool + offset).value
    heap = bind(rt, 'boom_heap_create', P, Q)(64 << 20)
    require(heap, 'Cannot create isolated native heap')
    if selection is None:
        heap_cell.value = heap
    else:
        require(bind(image, 'boom_java_string_literals_bind_heap', U, P)(heap) == 1 and heap_cell.value == heap,
                'Original static heap binding failed')
    require(owner['open'](pool) == 0 and owner['open'](pool) == 170 and owner['close'](pool) == 87, 'Pool lifecycle differs')
    transport = P.from_address(pool+24).value
    allocate = bind(rt, 'boom_heap_alloc', P, P, Q, U, U)
    head = allocate(heap, 24, 0, 11)
    publish = bind(rt, 'boom_reference_pending_publish', U, P, P)
    enter = bind(rt, 'boom_monitor_enter', U, P, P, P)
    ctx = Context()
    require(head and guest(ctx, 1) == 0 and guest(ctx, 0) == 0 and U.from_buffer(ctx).value == 0, 'Empty native queue differs')
    def await_count(n):
        deadline = time.monotonic() + 5
        while read_count(32) < n and time.monotonic() < deadline:
            time.sleep(.001)
        require(read_count(32) >= n, 'Original wait call did not enter')
    with ThreadPoolExecutor(max_workers=1) as executor:
        wait_context = Context()
        future = executor.submit(guest, wait_context, 2)
        try:
            await_count(1)
            require(not future.done() and publish(transport, head) == 0, 'Empty wait or actual publication failed')
            require(future.result(timeout=5) == 0 and U.from_buffer(wait_context).value == 0 and
                    guest(ctx, 1) == 1 and guest(ctx, 0) == head and guest(ctx, 1) == 0, 'Wait consumed the batch or returned the wrong head')
        finally:
            if not future.done():
                owner['stop'](pool)
    count = 8
    ready = Barrier(count+1, timeout=7); released = Event()
    contexts = [Context() for _ in range(count)]
    # Every waiter owns a different monitor. The exact Context and OS thread
    # that received the stop must release it, after its Java frames have left.
    objects = [allocate(heap, 24, 0, 11) for _ in contexts]
    def waiter(pair):
        index, worker = pair
        require(enter(heap, objects[index], worker) == 0, 'Cannot acquire worker monitor')
        guest(worker, 2)
        require(U.from_buffer(worker).value == 0xb002, 'VM stop was reported as a Java return')
        worker[3] = 0x14670000 + index
        ready.wait()
        require(released.wait(7), 'Test did not release shutdown workers')
        other = Context(0xb002, 0, 0, worker[3])
        require(boundary(other, pool) == 0 and other[0] == 0xb002, 'Issuing thread consumed a different Context')
        prior = worker[1]
        worker[1] = prior | (1 << 32)
        require(boundary(worker, pool) == 0, 'Live Java frame consumed a stop')
        worker[1] = prior
        require(boundary(worker, pool) == 1 and worker[0] == 0 and worker[1] == 0 and worker[3] == 0x14670000+index,
                'Authenticated stop did not restore the unwound Context')
        require(boundary(worker, pool) == 0, 'Stop token was reusable')
    with ThreadPoolExecutor(max_workers=count) as executor:
        futures = [executor.submit(waiter, pair) for pair in enumerate(contexts)]
        try:
            await_count(1 + count)
            require(owner['stop'](pool) == 0 and owner['stop'](pool) == 0, 'VM stop failed')
            ready.wait()
            fake = Context(0xb002, 0, 0, 0)
            require(boundary(fake, pool) == 0 and fake[0] == 0xb002 and
                    all(boundary(w, pool) == 0 for w in contexts), 'Wrong issuing thread or Context consumed a stop')
            require(owner['close'](pool) == 170, 'VM destroyed a live cancellation token')
        finally:
            if not released.is_set():
                owner['stop'](pool)
                released.set()
        for future in futures:
            future.result(timeout=8)
    require([read_count(k) for k in (32,40,48,56,64)] == [count+1, 1, count, count, count] and
            U.from_address(pool+72).value == 0, 'Reference wait/teardown counters differ')
    require(owner['close'](pool) == 0 and not P.from_address(pool+24).value, 'Reference transport did not close')
    if selection is not None:
        require(bind(image, 'boom_release_trace_pool', U)() == 0, 'Source native frames remained')
    require(bind(rt, 'boom_heap_destroy', U, P)(heap) == 1, 'Native heap still owns a monitor or frame')
    return dict(passed=True, scope='original_framed_Reference_natives' if selection else 'assembly_Reference_bridge_and_native_runtime',
                real_blocking_wait=True, pending_head_returned=True, normal_wakes=1, cancelled_OS_workers=count,
                wrong_Context_and_wrong_OS_thread_rejected=True, owned_monitors_released=count, runtime_sha256=sha(lib),
                image_sha256=sha(dll), game_started=False, run_directory=str(out))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','assembler','linker','kernel32','selection'):
        p.add_argument('--'+name,type=Path,required=name=='runtime')
    a=p.parse_args()
    if a.selection is None and not all((a.assembler,a.linker,a.kernel32)):
        p.error('Assembler, linker and kernel32 import library are required for the standalone bridge')
    out=ROOT/'.boom/reference-processing-tests'/uuid4().hex
    out.mkdir(parents=True)
    result=run(a.runtime,out,a.assembler,a.linker,a.kernel32,a.selection)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (ROOT/'.boom/latest-reference-processing-test.txt').write_text(str(out),encoding='utf-8')
    print(json.dumps(result))
