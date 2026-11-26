"""Bind the normal Class monitor regression to the actual System entry path."""
import argparse
import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('system_signal_monitor_io', ROOT/'scripts/runtime-provider-source.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def prepare(directory, accepted, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    S.check(directory.is_relative_to(S.ART) and output.is_relative_to(S.ART) and not output.exists(), 'Use a fresh isolated monitor test')
    proof_path = directory/'selection-verification.json'
    proof, closure, diagnostic = S.read(proof_path), S.read(directory/'closure.json'), S.read(directory/'diagnostic.json')
    S.check(S.digest(proof_path)['sha256'] == accepted and proof['verified'] and proof['diagnostic_only'] and not proof['source_closure_complete'],
            'Accepted System source proof differs')
    text = (directory/'initialization-closure.asm').read_text(encoding='utf-8')
    S.check(hashlib.sha256(text.encode()).hexdigest() == proof['closure_assembly_sha256'], 'Accepted System Java assembly changed')
    entries = closure['requested_method_roots']
    S.check(len(entries) == 1 and (entries[0]['loader'], entries[0]['owner'], entries[0]['name'], entries[0]['descriptor']) ==
            ('bootstrap', 'java/lang/System', 'initPhase1', '()V'), 'Monitor test requires the original System entry')
    references = closure['runtime_provider_packs']
    manifests = [S.read(S.checked(p['manifest'])) for p in references]
    matches = [p for p in manifests if p['family'] == 'normal-signal-lookup-v1']
    S.check(len(matches) == 1, 'System monitor test requires the original Signal lookup binding')
    provider = matches[0]
    S.check(provider['tool_sources'] == S.tools_identity(), 'Signal provider tools changed')
    owner = provider['owner_source']
    parser = S.module('system_signal_original_methods', 'verify-batch-frames.py')
    summary = S.read(Path(closure['batch'])/'summary.json')
    name, methods = parser.original_methods(S.original_class(summary, owner))
    candidates = [(i, m) for i, m in zip(owner['method_ids'], methods) if (m['name'], m['descriptor']) ==
        ('handle', '(Ljdk/internal/misc/Signal;Ljdk/internal/misc/Signal$Handler;)Ljdk/internal/misc/Signal$Handler;')]
    S.check(name == 'jdk/internal/misc/Signal' and len(candidates) == 1, 'Original synchronized Signal.handle differs')
    method, raw = candidates[0]
    code_sha = hashlib.sha256(raw['code'][0]).hexdigest() if raw['code'] else None
    selected = closure['selected_methods'].get(str(method))
    S.check(raw['access'] == 0x29 and selected is not None and selected['code_sha256'] == code_sha and
            selected['source_sha256'] == owner['origin']['sha256'], 'Original Signal.handle body is not selected')
    envelope = S.module('system_signal_monitor_envelope', 'verify-normal-monitors.py').expected(method, owner['id'])
    S.check(envelope in text, 'System Signal monitor does not use the canonical normal Class envelope')
    metadata = S.read(S.checked(provider['signal_lookup_metadata']))
    missing = next(m for m in metadata['unavailable_natives'] if m['name'] == 'handle0')
    rows = [r for r in diagnostic['rows'] if r['category'] == 2 and r.get('method', {}).get('id') == missing['method']]
    S.check(len(rows) == 1, 'System monitor test needs the explicit handle0 diagnostic frontier')
    paths = [directory/p for p in ('closure.json', 'diagnostic.json', 'selection-verification.json', 'initialization-closure.asm',
        'initialization-closure.obj', 'diagnostic-stops.obj', 'diagnostic-image.dll')]
    runtime = Path(diagnostic['global_provider_identity']['runtime_dll'])
    paths.extend(Path(p) for p in closure['objects'])
    paths.extend((runtime, Path(__file__), ROOT/'scripts/Test-SystemSignalMonitor.ps1', ROOT/'tests/host/SystemSignalMonitorProbe.cs',
                  ROOT/'scripts/verify-normal-monitors.py'))
    for reference in references:
        paths.extend((S.checked(reference['manifest']), S.checked(reference['verification'])))
    result = dict(schema=1, image=str(directory/'diagnostic-image.dll'), runtime=str(runtime), entry=entries[0]['symbol'],
        roots=[r['class_id'] for r in closure['requested_class_roots']], monitor_class=owner['id'], monitor_method=method,
        monitor_source_sha256=owner['origin']['sha256'], monitor_code_sha256=code_sha,
        expected_stop_row=rows[0]['id'], expected_stop_native=missing, inputs=[S.artifact(p) for p in dict.fromkeys(paths)],
        full_VM_bootstrap=False, game_started=False)
    S.write(output, result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--accepted-verification-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    prepare(a.directory, a.accepted_verification_sha256, a.output)
