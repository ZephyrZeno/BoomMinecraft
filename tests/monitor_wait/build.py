"""Build and independently run the isolated AMD64 wait-set candidate."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KERNEL = ROOT/'native/runtime/object_wait.asm'
EXPORTS = ['boom_monitor_wait' + s for s in ('', '_open', '_close', '_notify', '_notify_all', '_interrupt', '_stop', '_stopping')]
IMPORTS = {'boom-runtime.dll': {'boom_heap_contains', 'boom_threads_current'},
           'kernel32.dll': {'GetLastError', 'Sleep', 'QueryPerformanceFrequency', 'AcquireSRWLockExclusive',
                            'ReleaseSRWLockExclusive', 'VirtualAlloc', 'VirtualFree', 'GetCurrentThreadId', 'QueryPerformanceCounter'},
           'api-ms-win-core-synch-l1-2-0.dll': {'WaitOnAddress','WakeByAddressSingle','WakeByAddressAll'}}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, filename):
    spec=importlib.util.spec_from_file_location(name, ROOT/'scripts'/filename)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def invoke(args, log, seconds=55):
    with log.open('wb') as stream:
        p = subprocess.run([str(a) for a in args], stdout=stream, stderr=subprocess.STDOUT, timeout=seconds)
    if p.returncode:
        raise RuntimeError(f'{log} (exit {p.returncode})\n{log.read_text(errors="replace")[-2500:]}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--msvc', type=Path, default=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64'))
    parser.add_argument('--sdk', type=Path, default=Path('C:/Program Files (x86)/Windows Kits/10/Lib/10.0.26100.0/um/x64'))
    parser.add_argument('--source-state', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'.boom/monitor-wait-kernel-tests')
    parser.add_argument('--build-only', action='store_true')
    args = parser.parse_args()
    rt = args.runtime.resolve()
    runtime_sha = digest(rt / 'boom-runtime.dll')
    if runtime_sha != json.loads((rt / 'runtime.json').read_bytes())['sha256']:
        raise ValueError('runtime hash')
    out = args.output.resolve() / uuid.uuid4().hex
    out.mkdir(parents=True)
    for kind in ('production', 'test'):
        name = 'monitor-wait-' + kind
        obj = out / (name + '.obj')
        flags = ['/DMONITOR_WAIT_TEST'] if kind == 'test' else []
        invoke([args.msvc/'ml64.exe', '/nologo', '/c', *flags, '/Fo'+str(obj), KERNEL], out/(kind+'-assembler.log'))
        objs = [obj]
        ex = list(EXPORTS)
        if kind == 'test':
            probe = out/'test-mapper.obj'
            invoke([args.msvc/'ml64.exe', '/nologo', '/c', '/Fo'+str(probe), HERE/'probe_mapper.asm'], out/'test-mapper.log')
            objs.append(probe)
            ex.extend(['boom_test_interrupt_field', 'boom_test_monitor_wait_counts'])
        dll = out/(name+'.dll')
        invoke([args.msvc/'link.exe', '/nologo', '/dll', '/machine:x64', '/noentry', '/dynamicbase', '/nxcompat', '/brepro',
                '/out:'+str(dll), *['/export:'+s for s in ex], *objs, rt/'boom-runtime.lib',
                args.sdk/'kernel32.lib', args.sdk/'synchronization.lib'], out/(kind+'-linker.log'))
        if kind == 'production':
            invoke([args.msvc/'dumpbin.exe','/imports',dll], out/'production-imports.log')
            invoke([args.msvc/'dumpbin.exe','/exports',dll], out/'production-exports.log')
            invoke([args.msvc/'dumpbin.exe','/symbols',obj], out/'production-coff.log')
            body=(out/'production-exports.log').read_text()
            if set(EXPORTS) != {line.split()[-1] for line in body.splitlines() if ' boom_monitor_wait' in line}:
                raise ValueError('Production PE exports differ')
            required=set.union(*IMPORTS.values())
            defs,refs=module('mwait_coff','verify-batch-assembly.py').coff_symbols(obj,required)
            if defs!=set(EXPORTS) or refs!=required:
                raise ValueError('Production AMD64 COFF definitions or imports differ')
            pe=module('mwait_pe','vm-entry-source.py').pe(dll)
            read_imports={name.lower():set(symbols) for name,symbols in pe['imports'].items()}
            if read_imports!=IMPORTS or not pe['dll'] or pe['machine']!=0x8664 or pe['entry_rva']!=0:
                raise ValueError('Production PE imports, machine or entry differ')
    print(out, flush=True)
    if args.build_only:
        return
    invoke([sys.executable, '-u', HERE/'test_wait.py', rt, out], out/'test.log', 90)
    result = json.loads((out/'observations.json').read_bytes())
    if args.source_state:
        invoke([sys.executable, '-u', HERE/'test_original_wait.py', args.source_state.resolve(), out], out/'source-test.log', 35)
        result['original_image'] = json.loads((out/'original-image-observations.json').read_bytes())
    result.update(runtime_sha256=runtime_sha, assembly_sha256=digest(KERNEL),
                  production_coff_sha256=digest(out/'monitor-wait-production.obj'),
                  production_dll_sha256=digest(out/'monitor-wait-production.dll'),
                  production_exports=sorted(EXPORTS), production_imports={name:sorted(symbols) for name,symbols in IMPORTS.items()})
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
