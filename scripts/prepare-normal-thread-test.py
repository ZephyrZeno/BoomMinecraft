"""Capture a source-proved Thread primitive image without claiming construction."""
import argparse
import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('normal_thread_test_io', ROOT/'scripts/runtime-provider-source.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def prepare(directory, accepted, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    S.check(directory.is_relative_to(S.ART) and output.is_relative_to(S.ART) and not output.exists(), 'Use a fresh isolated Thread test record')
    proof_path = directory/'selection-verification.json'
    proof, closure = S.read(proof_path), S.read(directory/'closure.json')
    S.check(S.digest(proof_path)['sha256'] == accepted and proof['verified'] and proof['diagnostic_only'] and not proof['source_closure_complete'],
            'Accepted Thread source proof differs')
    assembly = directory/'initialization-closure.asm'
    S.check(hashlib.sha256(assembly.read_text(encoding='utf-8').encode()).hexdigest() == proof['closure_assembly_sha256'], 'Accepted Thread source assembly changed')
    references = closure['runtime_provider_packs']
    packs = [S.read(S.checked(r['manifest'])) for r in references]
    matches = [m for m in packs if m['family'] == 'normal-thread-primitives-v1']
    S.check(len(matches) == 1, 'Normal Thread primitive provider missing')
    provider = matches[0]
    S.check(provider['tool_sources'] == S.tools_identity(), 'Normal Thread tools changed')
    metadata_path = S.checked(provider['normal_thread_metadata'])
    metadata, owner = S.read(metadata_path), provider['owner_source']
    roots = [r['class_id'] for r in closure['requested_class_roots']]
    S.check(metadata['thread_class'] in roots, 'Normal Thread initializer is not a requested source root')
    static_fields = {}
    for name, descriptor in [('NEW_THREAD_BINDINGS', 'Ljava/lang/Object;'), ('EMPTY_STACK_TRACE', '[Ljava/lang/StackTraceElement;')]:
        found = [i for i, f in enumerate(owner['fields']) if (f['name'], f['descriptor']) == (name, descriptor) and f['access'] & 0x18 == 0x18]
        S.check(len(found) == 1, 'Original Thread initializer field differs')
        static_fields[name] = f"boom_s{owner['id']}_{found[0]}"
    runtime = Path(S.read(directory/'diagnostic.json')['global_provider_identity']['runtime_dll'])
    paths = [directory/p for p in ('closure.json', 'diagnostic.json', 'selection-verification.json', 'initialization-closure.asm',
        'initialization-closure.obj', 'diagnostic-stops.obj', 'diagnostic-image.dll')]
    paths.extend(Path(p) for p in closure['objects'])
    paths.extend((runtime, metadata_path, Path(__file__), ROOT/'scripts/Test-NormalThreadSource.ps1', ROOT/'tests/host/NormalThreadSourceProbe.cs'))
    for reference in references:
        paths.extend((S.checked(reference['manifest']), S.checked(reference['verification'])))
    result = dict(schema=1, image=str(directory/'diagnostic-image.dll'), runtime=str(runtime), metadata=metadata,
        roots=[r for r in roots if r != metadata['thread_class']], native_symbols={str(r['operation']): f"boom_m{r['method']}" for r in provider['methods']},
        static_fields=static_fields, inputs=[S.artifact(p) for p in dict.fromkeys(paths)],
        VM_preconstructor_peer_fixtures=True, original_Thread_constructors_executed=False, full_VM_bootstrap=False, game_started=False)
    S.write(output, result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--accepted-verification-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    prepare(a.directory, a.accepted_verification_sha256, a.output)
