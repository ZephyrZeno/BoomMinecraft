"""Build/verify an unregistered pure-MASM writable native memory owner.

This component has no Java IDs, Java Context, oop roots, VM integration or
runtime acceptance. Inputs and output artifacts are create-new and sealed.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64')
SDK = Path('C:/Program Files (x86)/Windows Kits/10/Lib/10.0.26100.0/um/x64/kernel32.lib')
EXPORTS = sorted('boom_native_memory_' + name for name in ('init', 'service', 'close'))
IMPORTS = sorted(('VirtualAlloc', 'VirtualFree', 'GetLastError', 'AcquireSRWLockExclusive', 'ReleaseSRWLockExclusive'))
ABI = dict(version=1, owner_bytes=128, job_bytes=128, record_bytes=64, lease_bytes=32,
    calling_convention='Windows_x64', owner_magic='0x3130574D4E4F4F42',
    owner_offsets=dict(magic=0, bytes=8, abi=12, srw=16, state=24, capacity=28, live=32,
        active=40, logical_bytes=48, budget=56, records=64, leases=72, metadata_bytes=80,
        sequence=88, allocations=96, frees=104, resizes=112, os_error=120, lease_capacity=124),
    job_offsets=dict(owner=0, address=8, bytes=16, other=24, value=32, result=40,
        token=48, generation=56, width=64, flags=68, op=72, status=76, os_error=80, completed=88),
    operations=dict(allocate=0, resize=1, free=2, read_plain=3, write_plain=4, fill=5,
        copy=6, copy_swap=7, borrow=8, release=9),
    status_codes=dict(ok=0, domain_miss=1, busy=2, arguments=3, allocation_OS=4,
        invalid_owner=5, capacity_budget_token=7, closed=9, cleanup_pending=12),
    owner_states=dict(ready=1, draining=2, closed=3),
    record_states=dict(free=0, live=1, cleanup_pending=2),
    initialization='single_threaded_zero_or_closed_owner', lease_capacity_multiplier=16,
    zero_allocation_is_null=True, exact_base_for_free_resize=True,
    peak_old_plus_new_budget_for_resize=True, busy_preserves_resources=True,
    close_requires_no_leases=True, cleanup_failure_retains_regions=True,
    unknown_address_access=False, Java_oop_roots=False, atomic_volatile=False,
    stale_raw_address_ABA_fully_prevented=False, multicore_performance_claim=False)


def check(value, message):
    if not value:
        raise ValueError(message)


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), size=path.stat().st_size, sha256=sha)


def checked(row):
    check(artifact(row['path']) == row, 'Sealed memory owner input changed: ' + row['path'])
    return Path(row['path'])


def write(path, row):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(row, indent=2, sort_keys=True) + '\n')


def reader():
    spec = importlib.util.spec_from_file_location('native_memory_owner_coff_reader', ROOT / 'scripts/jimage-owner-candidate.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def kernel_path(kernel=None):
    return Path(kernel).resolve() if kernel is not None else ROOT / 'native/kernels/native_memory_owner64.asm.inc'


def sources(kernel=None):
    return dict(kernel=artifact(kernel_path(kernel)), producer=artifact(__file__),
        complete_COFF_reader=artifact(ROOT / 'scripts/jimage-owner-candidate.py'))


def assembly(kernel=None):
    text = kernel_path(kernel).read_text(encoding='utf-8')
    check(not any(line.strip().upper() == 'END' for line in text.splitlines()) and 'option casemap:' not in text.lower(),
        'Memory owner include must not redefine the translation unit')
    return 'option casemap:none\n' + text + '\nEND\n'


def response(obj, image, library):
    return '\n'.join(['/NOLOGO', '/DLL', '/NOENTRY', '/NODEFAULTLIB', '/MACHINE:X64',
        '/INCREMENTAL:NO', '/DYNAMICBASE', '/NXCOMPAT', '/BREPRO', '/OUT:"' + str(image) + '"',
        *['/EXPORT:' + name for name in EXPORTS], '"' + str(obj) + '"', '"' + str(library) + '"']) + '\n'


def compile_image(output, kernel, assembler, linker, library):
    output.mkdir(parents=True)
    source, obj, image, rsp = (output / name for name in ('owner.asm', 'owner.obj', 'owner.dll', 'link.rsp'))
    with source.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(assembly(kernel))
    with rsp.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(response(obj, image, library))
    with (output / 'assembler.log').open('xb') as log:
        subprocess.run([str(assembler), '/nologo', '/c', '/Fo' + str(obj), str(source)],
            stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    with (output / 'linker.log').open('xb') as log:
        subprocess.run([str(linker), '@' + str(rsp)], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    return source, obj, image, rsp


def verify(candidate, kernel=None):
    path = Path(candidate).resolve()
    check(path.is_relative_to(ROOT / '.boom'), 'Isolated memory owner candidate required')
    row = json.loads(path.read_text(encoding='utf-8'))
    before = sources(kernel)
    check(row['schema'] == 1 and row['ABI'] == ABI and row['sources'] == before,
        'Memory owner source/ABI/complete-reader differs')
    check(all(row.get(key) is False for key in ('registered', 'runtime_accepted', 'guest_Java_executed', 'game_started')),
        'Memory owner component scope differs')
    source, obj, image, rsp = (checked(row[key]) for key in ('assembly', 'object', 'image', 'response'))
    assembler, linker, library = (checked(row[key]) for key in ('assembler', 'linker', 'kernel32'))
    check(source.read_text(encoding='utf-8') == assembly(kernel) and
        rsp.read_text(encoding='utf-8') == response(obj, image, library), 'Exact canonical owner ASM or LINK response differs')
    fresh = ROOT / '.boom/native-memory-owner/machine-checks' / uuid4().hex
    _, canonical_obj, canonical_image, _ = compile_image(fresh, kernel_path(kernel), assembler, linker, library)
    O = reader()
    actual, canonical = O.normalized_coff(obj), O.normalized_coff(canonical_obj)
    check(actual == canonical, 'All native instruction/flags/symbol-aux/relocation/unwind bytes differ from canonical')
    check(actual['exports'] == EXPORTS and actual['imports'] == IMPORTS, 'Unexpected actual memory owner imports/exports')
    check(all(not value['size'] for key, value in actual['sections'].items() if key in ('.data', '.bss')),
        'Mutable production owner globals forbidden')
    check(image.read_bytes() == canonical_image.read_bytes(), 'Complete canonical owner PE differs')
    check(sources(kernel) == before, 'Owner source changed during complete machine verification')
    for key in ('assembly', 'object', 'image', 'response', 'assembler', 'linker', 'kernel32'):
        checked(row[key])
    return dict(verified=True, scope='unregistered_pure_MASM_native_memory_core_complete_COFF_and_PE_only',
        candidate=artifact(path), sources=before,
        normalized_COFF_sha256=hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest(),
        complete_PE_sha256=artifact(image)['sha256'], actual_exports=EXPORTS, actual_Win32_imports=IMPORTS,
        complete_header_flags_symbols_aux_relocations_unwind_verified=True, mutable_globals=False,
        guest_Java_executed=False, registered=False, runtime_accepted=False, game_started=False)


def build(output, kernel=None, assembler=TOOLS / 'ml64.exe', linker=TOOLS / 'link.exe', library=SDK):
    output = Path(output).resolve()
    check(output.is_relative_to(ROOT / '.boom') and not output.exists(), 'Create-new isolated .boom output required')
    kernel = kernel_path(kernel)
    before = sources(kernel)
    assembler, linker, library = (Path(item).resolve() for item in (assembler, linker, library))
    tools = dict(assembler=artifact(assembler), linker=artifact(linker), kernel32=artifact(library))
    source, obj, image, rsp = compile_image(output, kernel, assembler, linker, library)
    check(sources(kernel) == before, 'Memory owner input changed during build')
    for item in tools.values():
        checked(item)
    path = output / 'candidate.json'
    write(path, dict(schema=1, scope='build_only_native_core_no_VM_integration', ABI=ABI,
        sources=before, assembly=artifact(source), object=artifact(obj), image=artifact(image), response=artifact(rsp),
        **tools, registered=False, runtime_accepted=False, guest_Java_executed=False, game_started=False))
    write(output / 'verification.json', verify(path, kernel))
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'verify'))
    parser.add_argument('--root', type=Path, default=ROOT, help='Workspace root; supports ignored publication review')
    parser.add_argument('--kernel', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--assembler', type=Path, default=TOOLS / 'ml64.exe')
    parser.add_argument('--linker', type=Path, default=TOOLS / 'link.exe')
    parser.add_argument('--kernel32', type=Path, default=SDK)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    if args.action == 'build':
        print(build(args.output, args.kernel, args.assembler, args.linker, args.kernel32))
    else:
        print(json.dumps(verify(args.candidate, args.kernel), indent=2))
