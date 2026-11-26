"""Execute original JDK narrow CAS over verified ABI2 field metadata.

The DLL reuses the independently verified selected Java COFF. Only the
derivation's field-pool object and the explicit assembly runtime are replaced.
Receiver storage is a fixture with real source layouts; this is not VM boot.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Barrier, get_native_id
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / '.boom'
P, U, Q = c.c_void_p, c.c_uint32, c.c_uint64
Context = Q * 4
TAG1, TAG2 = 0x55464c4400000000, 0x55464c3200000000


def check(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked(record):
    path = Path(record['path'])
    check(path.resolve().is_relative_to(ROOT) and path.stat().st_size == record['digest']['size'] and
          sha(path) == record['digest']['sha256'], 'Source artifact changed: ' + str(path))
    return path


def rows(record, name):
    with zipfile.ZipFile(checked(record)) as archive:
        return [json.loads(line) for line in archive.read(name).splitlines()]


def bind(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, args
    return fn


def address(dll, name):
    return c.addressof(c.c_byte.in_dll(dll, name))


def kind(context):
    return U.from_buffer(context).value


def cookie(id_):
    return TAG2 | ((id_ + 1) << 8) | 0x80


def signed(value, width):
    return value - (1 << (width * 8)) if value & (1 << (width * 8 - 1)) else value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('selection', 'batch', 'runtime'):
        parser.add_argument('--' + arg, type=Path, required=True)
    args = parser.parse_args()
    selection, batch, runtime = (p.resolve() for p in (args.selection, args.batch, args.runtime))
    check(os.name == 'nt' and c.sizeof(P) == 8 and all(p.is_relative_to(ART) for p in (selection, batch, runtime)),
          'Use project artifacts on Windows x64')
    proof = read(selection / 'selection-verification.json')
    check(proof['verified'] and proof['closure_manifest_sha256'] == sha(selection / 'closure.json'),
          'Selected original-source proof changed')
    closure = read(selection / 'closure.json')
    derivation = read(batch / 'unsafe-field-derivation.json')
    base = checked(derivation['accepted_base']['summary'])
    checked(derivation['accepted_base']['verification'])
    check(Path(closure['batch']).resolve() == base.parent and
          closure['source_batch_summary_sha256'] == sha(base), 'Fixture and derivation have different originals')
    verify = subprocess.run([sys.executable, str(ROOT / 'scripts/refresh-unsafe-field-batch.py'), 'verify',
        '--directory', str(batch), '--base-summary-sha256', sha(base),
        '--base-verification-sha256', derivation['accepted_base']['verification']['digest']['sha256']],
        capture_output=True)
    check(verify.returncode == 0, 'Field derivation verification failed: ' + verify.stderr.decode(errors='replace'))
    summary = read(batch / 'summary.json')
    rt_manifest = read(runtime / 'runtime.json')
    kernel_sha = sha(ROOT / 'native/runtime/java_unsafe_fields.asm')
    check(kernel_sha == derivation['kernel']['current']['digest']['sha256'] and
          kernel_sha in [v for k, v in rt_manifest['sources'].items() if k.endswith('java_unsafe_fields.asm')] and
          sha(runtime / 'boom-runtime.dll') == rt_manifest['sha256'], 'Runtime field kernel differs')
    fields = rows(summary['unsafe_fields']['index'], 'fields.jsonl')
    maps = {r['id']: r for r in rows(summary['runtime_metadata']['index'], 'fields.jsonl')}
    classes = {}
    plan = read(Path(derivation['plan']) / 'summary.json')
    with checked(plan['artifacts']['classes']).open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['origin']['loader'] == 'bootstrap':
                classes[row['name']] = row['id']
    module = next(f for f in fields if f['class_id'] == classes['java/lang/Module'] and f['name'] == 'enableNativeAccess')
    short = next(f for f in fields if f['class_id'] == classes['java/lang/Short'] and f['name'] == 'value')
    shifted = next(f for f in fields if f['kind'] in (1, 2) and f['id'] in maps and
                   len({r['offset'] % 4 for r in maps[f['id']]['rows']}) > 1)
    receivers = [(module, maps[module['id']]['rows'][0]), (short, maps[short['id']]['rows'][0])]
    lanes = set()
    for row in maps[shifted['id']]['rows']:
        if row['offset'] % 4 not in lanes:
            receivers.append((shifted, row)); lanes.add(row['offset'] % 4)
        if len(lanes) == 2:
            break
    check(len(receivers) == 4, 'Missing two source receivers with different physical byte lanes')
    out = ART / 'unsafe-carrier-tests' / uuid4().hex
    out.mkdir(parents=True)
    old_summary = read(base)
    old_object = str(Path(old_summary['unsafe_fields']['units'][2]['object']['path']))
    replacement = checked(summary['unsafe_fields']['units'][2]['object'])
    link = Path(derivation['assembler']['path']).with_name('link.exe')
    response = []
    replacements = 0
    for line in (selection / 'link.rsp').read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('/OUT:'):
            line = '/OUT:"' + str(out / 'diagnostic-image.dll') + '"'
        elif line.startswith('/IMPLIB:'):
            line = '/IMPLIB:"' + str(out / 'diagnostic-image.lib') + '"'
        elif line.strip('"') == old_object:
            line = '"' + str(replacement) + '"'; replacements += 1
        elif line.endswith('boom-runtime.lib"'):
            line = '"' + str(runtime / 'boom-runtime.lib') + '"'
        response.append(line)
    check(replacements == 1, 'Expected exactly one original field-pool replacement')
    methods = (113183, 113286, 113287, 113294, 113314, 42241)
    response.extend('/EXPORT:boom_m' + str(i) for i in methods)
    response.extend('/EXPORT:boom_layout' + str(i) + ',DATA' for i in sorted({r['receiver_class'] for _, r in receivers}))
    (out / 'link.rsp').write_text('\n'.join(response) + '\n', encoding='utf-8')
    linked = subprocess.run([str(link), '@' + str(out / 'link.rsp')], capture_output=True)
    (out / 'link.log').write_bytes(linked.stdout + linked.stderr)
    check(linked.returncode == 0, 'Original-source fixture link failed: ' + str(out / 'link.log'))
    shutil.copyfile(runtime / 'boom-runtime.dll', out / 'boom-runtime.dll')
    rt, image = c.CDLL(str(out / 'boom-runtime.dll')), c.CDLL(str(out / 'diagnostic-image.dll'))
    heap = bind(rt, 'boom_heap_create', P, Q)(128 << 20)
    check(heap and bind(image, 'boom_java_string_literals_bind_heap', U, P)(heap) == 1, 'Cannot bind fixture heap')
    ctx = Context()
    unsafe = bind(image, 'boom_m113183', P, P, P)(ctx, None)
    check(unsafe and kind(ctx) == 0, 'Original Unsafe.getUnsafe failed')
    pool = address(image, 'boom_java_unsafe_field_pool')
    check(U.from_address(pool + 4).value == 2 and Q.from_address(pool + 112).value == TAG2, 'Wrong runtime pool ABI')
    allocate = bind(rt, 'boom_object_new', P, P, P, P)
    memory = bind(rt, 'boom_java_unsafe_memory', Q, P, P, P, U)
    exchange = {1: bind(image, 'boom_m113286', Q, P, P), 2: bind(image, 'boom_m113294', Q, P, P)}
    fixtures, vectors = [], 0
    for field, row in receivers:
        oop = allocate(heap, address(image, 'boom_layout' + str(row['receiver_class'])), ctx)
        check(oop and kind(ctx) == 0, 'Original receiver layout allocation failed')
        payload = Q.from_address(oop - 16).value
        capacity = Q.from_address(oop - 32).value - 32
        references = U.from_address(oop - 20).value * 8
        check(references <= row['offset'] and row['offset'] + field['storage_bytes'] <= payload <= capacity,
              'Field not in actual scalar payload')
        c.memset(oop + references, 0xA7, capacity - references)
        width = field['storage_bytes']; mask = (1 << (8 * width)) - 1
        target = oop + row['offset']
        for old, new in ((0, 1), (1, mask), (mask, mask >> 1), (mask >> 1, 1 << (width * 8 - 1))):
            c.memmove(target, old.to_bytes(width, 'little'), width)
            before = c.string_at(oop - 32, capacity + 32)
            value = exchange[width](ctx, (Q * 5)(unsafe, oop, cookie(field['id']), signed(old, width), signed(new, width)))
            expected = bytearray(before); expected[32 + row['offset']:32 + row['offset'] + width] = new.to_bytes(width, 'little')
            check(kind(ctx) == 0 and value & mask == old and c.string_at(oop - 32, capacity + 32) == bytes(expected),
                  'Original narrow CAS changed adjacent storage, padding, or headers')
            unchanged = c.string_at(oop - 32, capacity + 32)
            value = exchange[width](ctx, (Q * 5)(unsafe, oop, cookie(field['id']), signed(old, width), 0))
            check(kind(ctx) == 0 and value & mask == new and c.string_at(oop - 32, capacity + 32) == unchanged,
                  'Original narrow CAS mismatch changed storage')
            vectors += 2
        fixtures.append((field, row, oop, capacity))
    field, row, oop, capacity = fixtures[0]
    check(Q.from_address(oop - 16).value == 65 and row['offset'] == 64, 'Expected the original Module tail regression')
    c.c_ubyte.from_address(oop + 64).value = 0
    result = bind(image, 'boom_m113314', Q, P, P)(ctx, (Q * 5)(unsafe, oop, cookie(field['id']), 0, 1))
    check(result == 1 and kind(ctx) == 0, 'Original Boolean CAS failed')
    result = bind(image, 'boom_m42241', Q, P, P)(ctx, (Q * 1)(oop))
    check(result == oop and kind(ctx) == 0, 'Original Module native-access initializer failed')
    # Fresh contexts retain the actual source error; no failing operation is cleared and retried.
    failures = 0
    for token, op in ((TAG1 | (field['id'] + 1), 0x25), (cookie(field['id']) - 1, 0x25),
                      (cookie(field['id']) + 8, 0x25), (cookie(field['id']), 0x29),
                      (cookie(field['id'] - 3), 0x25)):
        error = Context(); before = c.string_at(oop - 32, capacity + 32)
        memory(error, (Q * 5)(unsafe, oop, token, 0, 0), pool, op)
        check(kind(error) != 0 and c.string_at(oop - 32, capacity + 32) == before, 'Invalid view changed receiver storage')
        failures += 1
    for abi, tag in ((0, TAG2), (3, TAG2), (2, TAG1), (1, TAG2)):
        changed = c.create_string_buffer(c.string_at(pool, 128)); U.from_buffer(changed, 4).value = abi
        Q.from_buffer(changed, 112).value = tag; error = Context()
        memory(error, (Q * 5)(unsafe, oop, cookie(field['id']), 0, 0), changed, 0x25)
        check(kind(error) == 7, 'Mixed pool ABI and tag accepted'); failures += 1
    legacy = c.create_string_buffer(c.string_at(pool, 128)); U.from_buffer(legacy, 4).value = 1
    Q.from_buffer(legacy, 112).value = TAG1
    valid = Context(); result = memory(valid, (Q * 3)(unsafe, oop, TAG1 | (field['id'] + 1)), legacy, 0x21)
    check(kind(valid) == 0 and result == 1, 'ABI1 exact field access regressed')
    # Failed expected padding is an atomic mismatch. Nonzero desired padding
    # cannot be stored in the virtual carrier and must fail without a write.
    before = c.string_at(oop - 32, capacity + 32)
    valid = Context(); result = memory(valid, (Q * 5)(unsafe, oop, cookie(field['id']), 0x101, 0), pool, 0x45)
    check(kind(valid) == 0 and result == 0, 'Nonzero expected padding matched')
    error = Context(); memory(error, (Q * 5)(unsafe, oop, cookie(field['id']), 1, 0x101), pool, 0x45)
    check(kind(error) == 20 and c.string_at(oop - 32, capacity + 32) == before, 'Virtual padding was written')
    valid = Context()
    result = memory(valid, (Q * 5)(unsafe, oop, cookie(field['id']), 0xDEADBEEF00000001, 0xABCDEF0100000001), pool, 0x45)
    check(kind(valid) == 0 and result == 1 and c.string_at(oop - 32, capacity + 32) == before,
          'Non-significant Java int slot bits affected a virtual carrier')
    cas = bind(image, 'boom_m113287', Q, P, P); gate = Barrier(8, timeout=15)
    c.c_ubyte.from_address(oop + 64).value = 0
    def worker(_):
        context = Context(); retries = 0; gate.wait()
        for _ in range(256):
            while True:
                value = memory(context, (Q * 3)(unsafe, oop, cookie(field['id'])), pool, 0x22) & 255
                success = cas(context, (Q * 5)(unsafe, oop, cookie(field['id']), signed(value, 1), signed((value + 1) & 255, 1)))
                check(kind(context) == 0, 'Concurrent original Java CAS failed')
                if success:
                    break
                retries += 1
        check(U.from_buffer(context, 12).value == 0, 'Original Java frames leaked')
        return get_native_id(), retries
    with ThreadPoolExecutor(max_workers=8) as executor:
        workers = list(executor.map(worker, range(8)))
    check(len({tid for tid, _ in workers}) == 8 and c.c_ubyte.from_address(oop + 64).value == 0,
          'Concurrent byte increments lost updates: ' + str((workers, c.c_ubyte.from_address(oop + 64).value)))
    check(bind(rt, 'boom_heap_destroy', U, P)(heap) == 1, 'Fixture heap teardown failed')
    report = dict(passed=True, scope='original_Unsafe_Java_narrow_CAS_with_source_receiver_storage_fixtures',
        source_selection=str(selection), source_proof_sha256=sha(selection / 'selection-verification.json'),
        batch=str(batch), field_derivation_sha256=sha(batch / 'unsafe-field-derivation.json'),
        runtime_sha256=sha(runtime / 'boom-runtime.dll'), field_kernel_sha256=kernel_sha,
        original_byte_short_cases=vectors, source_receiver_layouts=len(fixtures), distinct_physical_byte_lanes=len(lanes),
        original_Module_payload_bytes=65, Module_tail_field_offset=64, wrong_view_and_ABI_checks=failures,
        legacy_exact_field_access=True, virtual_padding_preserved=True, parallel_OS_threads=8,
        original_Java_successful_contended_CAS=2048, contended_retries=sum(n for _, n in workers),
        original_Module_implAddEnableNativeAccess=True, frame_leaks=0,
        fixture_target_storage=True, full_VM_bootstrap=False, game_started=False)
    check(sha(ROOT / 'native/runtime/java_unsafe_fields.asm') == kernel_sha, 'Kernel changed during testing')
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (ART / 'latest-unsafe-carrier-test.txt').write_text(str(out), encoding='utf-8')
    print(json.dumps(dict(directory=str(out), **report)))


if __name__ == '__main__':
    main()
