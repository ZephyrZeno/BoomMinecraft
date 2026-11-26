"""Refresh accepted native inputs and build additional registered ASM families.

The resulting state is pending runtime acceptance. This does not run the game,
replace Java methods, or change the original accepted directories.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location('extend_native_' + name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S = module('runtime-provider-source')
R = module('revalidate-runtime-provider-cache')


def extend(state_file, families, assembler, output, workers=2):
    state_file, assembler, output = map(lambda p: Path(p).resolve(), (state_file, assembler, output))
    S.check(state_file.is_relative_to(S.ART), 'Use an accepted project state')
    S.check(output.is_relative_to(S.ART / 'formal-native-transitions') and not output.exists(),
            'Use a fresh project formal-native-transitions directory')
    S.check(1 <= workers <= 8, 'Native family workers must be in 1..8')
    previous = S.read(state_file)
    S.check(previous['status'] == 'accepted' and previous['runtime_acceptance_complete'],
            'An accepted, scoped runtime checkpoint is required')
    S.check(all(Path(previous[key]).resolve().is_relative_to(S.ART)
                for key in ('batch', 'plan', 'runtime', 'providers', 'frame_manifest')),
            'Accepted source, runtime, and provider inputs must remain in project .boom')
    paths = [Path(p).resolve() for p in S.read(previous['providers'])]
    S.check(len(paths) == previous['provider_count'] == len(set(paths)) and
            all(p.is_relative_to(S.ART) for p in paths), 'Incomplete or external accepted provider list')
    sealed = {Path(row['manifest']['path']).resolve(): row for row in previous['providers_verified']}
    S.check(set(sealed) == set(paths), 'Accepted provider records differ from the actual list')
    source_inputs = [S.artifact(state_file), S.artifact(previous['providers'])]
    for path in paths:
        row = sealed[path]
        S.check(S.artifact(path) == row['manifest'] and
                S.artifact(path.with_name('verification.json')) == row['verification'],
                'An accepted provider input changed')
        source_inputs.extend((row['manifest'], row['verification']))
    existing = {S.read(p)['family'] for p in paths}
    registry = S.read(ROOT / 'native-config/runtime-providers.json')
    S.check(families and len(families) == len(set(families)) and
            set(families) <= set(registry['families']) and not existing.intersection(families),
            'Additional families must be registered, unique, and absent from the accepted set')
    S.check(len(existing) == len(paths), 'The accepted input repeats a family')
    batch, plan, runtime = (Path(previous[k]).resolve() for k in ('batch', 'plan', 'runtime'))
    for path, key in ((batch / 'summary.json', 'batch_summary_sha256'),
                      (batch / 'verification.json', 'batch_verification_sha256'),
                      (Path(previous['frame_manifest']).with_name('verification.json'), 'frame_verification_sha256'),
                      (runtime / 'boom-runtime.dll', 'runtime_sha256')):
        record = S.artifact(path)
        S.check(record['digest']['sha256'] == previous[key], 'Accepted source or runtime changed: ' + key)
        source_inputs.append(record)
    source_inputs.append(S.artifact(previous['frame_manifest']))
    runtime_metadata = S.read(runtime / 'runtime.json')
    S.check(runtime_metadata['implementation_language'] == 'x86-64 MASM assembly' and
            runtime_metadata['sha256'] == previous['runtime_sha256'], 'Assembly runtime metadata differs')
    source_inputs.append(S.artifact(runtime / 'runtime.json'))
    snapshot, own_tool, assembler_record = S.tools_identity(), S.artifact(Path(__file__)), S.artifact(assembler)
    frame = S.ART / 'native-frame-overlays' / output.name
    packs = S.ART / 'runtime-providers' / output.name
    S.check(not frame.exists() and not packs.exists(), 'Frame/provider transition destinations already exist')
    output.mkdir(parents=True)
    packs.mkdir(parents=True)
    journal = output / 'progress.json'
    started = time.monotonic()
    progress = dict(schema=1, status='running', pid=os.getpid(), source_state=source_inputs[0],
                    run=str(output), frame=str(frame), packs=str(packs), added_families=list(families),
                    runtime_acceptance_complete=False, game_started=False)

    def unchanged():
        S.check(S.tools_identity() == snapshot and S.artifact(Path(__file__)) == own_tool and
                S.artifact(assembler) == assembler_record, 'A transition tool changed during execution')
        for record in source_inputs:
            S.check(S.artifact(record['path']) == record, 'An original accepted input changed during execution')

    def publish(stage):
        unchanged()
        progress.update(stage=stage, elapsed_seconds=round(time.monotonic() - started, 3))
        temporary = journal.with_name('progress-' + uuid4().hex + '.tmp')
        S.write(temporary, progress)
        temporary.replace(journal)
        print(json.dumps(dict(stage=stage, journal=str(journal))), flush=True)

    def build_one(family):
        directory = packs / 'new-families' / family
        common = ['--output', str(directory)]
        commands = [
            [sys.executable, str(ROOT / 'scripts/build-runtime-provider-pack.py'),
             '--batch', str(batch), '--plan', str(plan), '--family', family,
             '--frame-overlay', str(frame / 'overlay.json'), *common],
            [str(assembler), '/nologo', '/c', '/Fo' + str(directory / 'provider.obj'),
             str(directory / 'provider.asm')],
            [sys.executable, str(ROOT / 'scripts/build-runtime-provider-pack.py'),
             '--seal', '--assembler', str(assembler), *common],
            [sys.executable, str(ROOT / 'scripts/verify-runtime-provider-pack.py'),
             str(directory / 'provider.json'), '--batch', str(batch), '--plan', str(plan),
             '--output', str(directory / 'verification.json')],
        ]
        for stage, command in enumerate(commands):
            log = output / (family + '.' + str(stage) + '.log')
            with log.open('xb') as stream:
                result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=stream, timeout=900,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            S.check(result.returncode == 0, 'Native family generation/verification failed: ' + str(log))
        return directory / 'provider.json'

    try:
        publish('refreshing_source_frames')
        overlay = R.refresh_frames(Path(previous['frame_manifest']), batch, plan, frame)
        publish('revalidating_original_provider_caches')
        current = R.refresh_packs(paths, batch, plan, overlay, packs / 'revalidated')
        generated = {}
        publish('building_additional_families')
        with ThreadPoolExecutor(max_workers=min(workers, len(families))) as executor:
            pending = {executor.submit(build_one, family): family for family in families}
            for future in as_completed(pending):
                family = pending[future]
                generated[family] = future.result()
                progress['generated_verified_families'] = sorted(generated)
                publish('family_ready_' + family)
        all_paths = [*current, *(generated[family] for family in families)]
        records, ids, exports = [], set(), set()
        all_families = existing | set(families)
        for path in all_paths:
            manifest, proof = S.read(path), S.read(path.with_name('verification.json'))
            S.check(proof['verified'] and proof['provider_manifest_sha256'] == S.digest(path)['sha256'] and
                    manifest['tool_sources'] == snapshot, 'Current provider receipt or source namespace changed')
            new_ids = {row['method'] for row in manifest['methods']}
            S.check(not ids.intersection(new_ids) and not exports.intersection(manifest['exports']),
                    'Overlapping native declarations or exported symbols')
            S.check(set(manifest.get('required_provider_families', [])) <= all_families,
                    'A required native family is missing')
            S.check(all(runtime_metadata['sources'].get(name) == sha
                        for name, sha in manifest.get('runtime_kernel_sha256', {}).items()),
                    'A provider requires kernels absent from the actual assembly runtime')
            ids.update(new_ids)
            exports.update(manifest['exports'])
            records.append(dict(family=manifest['family'], manifest=S.artifact(path),
                                verification=S.artifact(path.with_name('verification.json'))))
        unchanged()
        directory = packs / 'candidate'
        directory.mkdir()
        S.write(directory / 'providers.json', [str(p) for p in all_paths])
        state = dict(schema=1, status='pending_runtime_acceptance',
                     scope='current_source_ASM_COFF_provider_inputs_not_runtime_acceptance',
                     batch=str(batch), plan=str(plan), runtime=str(runtime), frame=str(frame), frame_manifest=str(overlay),
                     providers=str(directory / 'providers.json'), provider_count=len(all_paths),
                     reused_provider_count=len(current), generated_provider_count=len(generated),
                     run=str(output), source_state=source_inputs[0], tool_sources=snapshot,
                     transition_tool=own_tool, providers_verified=records,
                     batch_summary_sha256=S.digest(batch / 'summary.json')['sha256'],
                     batch_verification_sha256=S.digest(batch / 'verification.json')['sha256'],
                     runtime_sha256=previous['runtime_sha256'],
                     frame_verification_sha256=S.digest(frame / 'verification.json')['sha256'],
                     original_Java_ASM_and_COFF_regenerated=False,
                     reused_provider_ASM_and_COFF_bytes_unchanged=True, shared_runtime_kernel_modified=False,
                     current_source_provider_verification_complete=True, runtime_acceptance_complete=False,
                     accepted_provider_set_published=False, elapsed_seconds=round(time.monotonic() - started, 3),
                     game_started=False, world_created=False)
        target = output / 'pending-state.json'
        S.write(target, state)
        progress.update(status='pending_runtime_acceptance', candidate_state=str(target))
        publish('pending_state_ready')
        return target
    except BaseException as error:
        progress.update(status='failed', error=repr(error), elapsed_seconds=round(time.monotonic() - started, 3))
        S.write(output / 'failure.json', progress)
        temporary = journal.with_name('progress-failed-' + uuid4().hex + '.tmp')
        S.write(temporary, progress)
        temporary.replace(journal)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--family', action='append', required=True)
    parser.add_argument('--assembler', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--output', type=Path,
                        default=S.ART / 'formal-native-transitions' / ('native-' + uuid4().hex))
    args = parser.parse_args()
    print(extend(args.state, args.family, args.assembler, args.output, args.workers))
