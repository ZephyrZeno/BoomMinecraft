"""Bind a staged normal String signal lookup kernel test to a proved image."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('normal_signal_test_io', ROOT/'scripts/runtime-provider-source.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def prepare(directory, accepted, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    S.check(directory.is_relative_to(S.ART) and output.is_relative_to(S.ART) and not output.exists(), 'Use a fresh isolated signal test record')
    proof_path = directory/'selection-verification.json'
    proof, closure = S.read(proof_path), S.read(directory/'closure.json')
    S.check(S.digest(proof_path)['sha256'] == accepted and proof['verified'] and proof['diagnostic_only'] and not proof['source_closure_complete'],
            'Explicitly accepted signal test image proof differs')
    asm = directory/'initialization-closure.asm'
    S.check(hashlib.sha256(asm.read_text(encoding='utf-8').encode()).hexdigest() == proof['closure_assembly_sha256'], 'Accepted Java assembly changed')
    _, summary, classes = S.base(closure['batch'], closure['plan'])
    C = S.module('normal_signal_test_contract', 'signal-lookup-source.py')
    metadata = C.index(summary, classes, S)
    runtime = Path(S.read(directory/'diagnostic.json')['global_provider_identity']['runtime_dll'])
    kernel = ROOT/'native/providers/signal_lookup.asm.inc'
    source = ('option casemap:none\nEXTERN boom_heap_contains:PROC\nEXTERN boom_object_check:PROC\n'
        '.data\nPUBLIC boom_heap_ptr\nboom_heap_ptr QWORD 0\n'
        'PUBLIC boom_java_string_literal_pool\nboom_java_string_literal_pool BYTE 80 DUP(0)\n'
        + C.data() + kernel.read_text(encoding='utf-8') + '\nEND\n')
    (output.parent/'signal.asm').write_text(source, encoding='utf-8')
    paths = [directory/'diagnostic-image.dll', proof_path, directory/'closure.json', asm, runtime,
             runtime.with_suffix('.lib'), Path(closure['batch'])/'summary.json',
             kernel, ROOT/'scripts/signal-lookup-source.py', Path(__file__),
             ROOT/'scripts/Test-NormalSignalLookupKernel.ps1', ROOT/'tests/host/NormalSignalLookupKernelProbe.cs',
             ROOT/'java/subset/dev/boom/signals/SignalNames.java', ROOT/'java/reference/SignalNamesReference.java']
    result = dict(schema=1, image=str(directory/'diagnostic-image.dll'), runtime=str(runtime), metadata=metadata,
                  inputs=[S.artifact(p) for p in paths], fixture_objects_and_String_pool_copy=True,
                  source_native_entries_executed=False, Java_initializers_executed=False, game_started=False)
    S.write(output, result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--accepted-verification-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    prepare(a.directory, a.accepted_verification_sha256, a.output)
    print(json.dumps(dict(source=str(a.output), source_native_entries_executed=False, game_started=False)))
