"""Bind the signal transport ABI test to a proved normal-source frame pool."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('normal_signal_frames_io', ROOT/'scripts/runtime-provider-source.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def prepare(directory, accepted, runtime, output):
    directory, runtime, output = map(lambda p: Path(p).resolve(), (directory, runtime, output))
    S.check(all(p.is_relative_to(S.ART) for p in (directory, runtime, output)) and not output.exists(), 'Use fresh isolated signal frame evidence')
    proof_path = directory/'selection-verification.json'
    proof, closure = S.read(proof_path), S.read(directory/'closure.json')
    S.check(S.digest(proof_path)['sha256'] == accepted and proof['verified'] and proof['diagnostic_only'] and not proof['source_closure_complete'],
            'Explicitly accepted normal source frame proof differs')
    assembly = directory/'initialization-closure.asm'
    S.check(hashlib.sha256(assembly.read_text(encoding='utf-8').encode()).hexdigest() == proof['closure_assembly_sha256'] and closure['source_frame_abi'] == 3,
            'Accepted normal source frame assembly differs')
    metadata = S.read(runtime/'runtime.json')
    S.check(S.digest(runtime/'boom-runtime.dll')['sha256'] == metadata['sha256'], 'New signal ABI runtime binary changed')
    sources = [ROOT/p for p in metadata['sources']]
    for path in sources:
        S.check(S.digest(path)['sha256'] == metadata['sources'][path.relative_to(ROOT).as_posix()], 'New runtime source differs: ' + str(path))
    paths = [proof_path, directory/'closure.json', assembly, directory/'diagnostic-image.dll', runtime/'runtime.json',
             runtime/'boom-runtime.dll', runtime/'boom-runtime.lib', Path(__file__), ROOT/'scripts/Test-NormalSignalFrames.ps1',
             ROOT/'tests/host/NormalSignalFramesProbe.cs', ROOT/'native/probe/signal_control_probe.asm',
             ROOT/'scripts/Build-SignalControlProbe.ps1'] + sources
    result = dict(schema=1, image=str(directory/'diagnostic-image.dll'), runtime=str(runtime/'boom-runtime.dll'),
        inputs=[S.artifact(p) for p in paths], source_Java_executed=False, source_native_entries_executed=False,
        copied_source_TracePool_metadata=True, assembly_callback_fixtures=True, game_started=False)
    S.write(output, result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--accepted-verification-sha256', required=True)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    prepare(a.directory, a.accepted_verification_sha256, a.runtime, a.output)
    print(json.dumps(dict(source=str(a.output), game_started=False)))
