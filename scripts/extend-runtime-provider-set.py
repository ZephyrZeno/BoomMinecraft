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


def equivalent_named_batch(previous_batch, batch, plan, full_sha):
    """Reuse original payload only after a fresh, current full named-batch proof."""
    N=module('refresh-named-module-batch');Q=module('rebase-runtime-provider-inputs')
    before,after=(S.read(p/'summary.json') for p in (previous_batch,batch))
    old_full,new_full=(S.read(p/'verification.json') for p in (previous_batch,batch))
    S.check(isinstance(full_sha,str) and len(full_sha)==64 and
            S.digest(batch/'verification.json')['sha256']==full_sha,'Explicit fresh full-batch checksum differs')
    _,lineage=N.verified_resolver(batch,after,plan)
    Q.same_summary(before,after);Q.same_full_coverage(old_full,new_full)
    old_derived,new_derived=(S.read(p/N.PROOF) for p in (previous_batch,batch))
    old_scope=old_full['named_module_derivation']
    S.check(old_scope['summary']==N.artifact(previous_batch/'summary.json') and
            old_scope['derivation']==N.artifact(previous_batch/N.PROOF) and
            old_scope['parent']==old_derived['parent_inputs'] and
            old_scope['source_graph']==old_derived['source_graph']['inputs'],
            'Accepted named-batch full proof no longer binds its original derivation')
    for key in ('parent_inputs','parent_derivation','requested_modules','source_graph','appended',
                'declaration_changes','binary_equivalence'):
        S.check(old_derived[key]==new_derived[key], 'Equivalent batch changes its original source graph or append: '+key)
    [old_unit]=before['class_literals']['units'];[new_unit]=after['class_literals']['units']
    old_asm,old_obj=(N.checked(old_unit[k]) for k in ('assembly','object'))
    new_asm,new_obj=(N.checked(new_unit[k]) for k in ('assembly','object'))
    S.check(S.digest(old_asm)==S.digest(new_asm),'Equivalent named-batch assembly bytes changed')
    binary=N.binary_equivalence(old_obj,new_obj,before['class_literals'],after['class_literals'])
    S.check(binary['BSS_added_bytes']==0 and
            binary['indexed_symbol_contract']['rdata_symbol_shift']==0 and
            binary['indexed_symbol_contract']['BSS_symbol_shift']==0,
            'Equivalent named-batch COFF data or symbol layout changed')
    return dict(scope='same_original_named_batch_freshly_fully_verified_current_tools',
        previous_summary=N.artifact(previous_batch/'summary.json'),
        previous_full_verification=N.artifact(previous_batch/'verification.json'),
        previous_derivation=N.artifact(previous_batch/N.PROOF),current=lineage,
        binary_equivalence=binary,original_Java_and_metadata_unchanged=True,
        current_provider_models_must_reverify=True,runtime_acceptance_proven=False)


def extend(state_file, families, assembler, output, workers=2, *, batch_override=None, regenerate=(),
           equivalent_batch_verification_sha256=None):
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
    original_families = {p: S.read(p)['family'] for p in paths}
    existing = set(original_families.values())
    registry = S.read(ROOT / 'native-config/runtime-providers.json')
    S.check((families or regenerate or equivalent_batch_verification_sha256 is not None) and len(families) == len(set(families)) and
            set(families) <= set(registry['families']) and not existing.intersection(families),
            'Additional families must be registered, unique, and absent from the accepted set')
    S.check(len(regenerate) == len(set(regenerate)) and set(regenerate) <= existing,
            'Regenerated families must be unique existing inputs')
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
    previous_batch = batch
    batch_lineage = None
    S.check(batch_override is not None or equivalent_batch_verification_sha256 is None,
            'Equivalent full verification requires an explicit replacement batch')
    if batch_override is not None:
        batch = Path(batch_override).resolve()
        S.check(batch.is_relative_to(S.ART) and batch != previous_batch,
                'An explicit batch override must be a different verified project batch')
        old_identity = S.base(previous_batch, plan)[0]
        new_identity = S.base(batch, plan)[0]
        R.compatible_base(old_identity, new_identity)
        if equivalent_batch_verification_sha256 is not None:
            batch_lineage=equivalent_named_batch(previous_batch,batch,plan,equivalent_batch_verification_sha256)
            source_inputs.append(S.artifact(previous_batch/'named-module-derivation.json'))
            for summary in (S.read(previous_batch/'summary.json'),S.read(batch/'summary.json')):
                [unit]=summary['class_literals']['units']
                source_inputs.extend(S.artifact(unit[k]['path']) for k in ('assembly','object'))
        else:
            resolver = module('closure-batch-artifacts')
            assembly_model = module('verify-batch-assembly')
            batch_lineage = resolver.configure(assembly_model, batch, S.read(batch / 'summary.json'), plan)
            S.check(batch_lineage and batch_lineage.get('scope') == 'parent_verified_batch_plus_source_reconstructed_named_JCLS_unit' and
                    Path(batch_lineage['parent']['summary']['path']).resolve() == previous_batch / 'summary.json' and
                    batch_lineage['parent']['summary']['digest']['sha256'] == previous['batch_summary_sha256'],
                    'Batch override requires certified named-module lineage from the accepted source batch')
        source_inputs.extend((S.artifact(batch / 'summary.json'), S.artifact(batch / 'verification.json')))
        source_inputs.append(S.artifact(batch / 'named-module-derivation.json'))
    build_families = [*regenerate, *families]
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
                    regenerated_families=list(regenerate), batch=str(batch), previous_batch=str(previous_batch),
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
        retained = [p for p in paths if original_families[p] not in regenerate]
        current = R.refresh_packs(retained, batch, plan, overlay, packs / 'revalidated')
        current_by_family = {S.read(p)['family']: p for p in current}
        generated = {}
        publish('building_additional_families')
        # A pure equivalent-batch migration still verifies every retained pack.
        # No worker is started when there are no additional/regenerated families.
        with ThreadPoolExecutor(max_workers=max(1,min(workers, len(build_families)))) as executor:
            pending = {executor.submit(build_one, family): family for family in build_families}
            for future in as_completed(pending):
                family = pending[future]
                generated[family] = future.result()
                progress['generated_verified_families'] = sorted(generated)
                publish('family_ready_' + family)
        all_paths = [generated[original_families[p]] if original_families[p] in regenerate
                     else current_by_family[original_families[p]] for p in paths]
        all_paths.extend(generated[family] for family in families)
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
                     regenerated_existing_families=list(regenerate), added_families=list(families),
                     previous_batch=str(previous_batch),
                     batch_source_lineage=batch_lineage,
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
    parser.add_argument('--family', action='append', default=[])
    parser.add_argument('--regenerate-family', action='append', default=[])
    parser.add_argument('--batch', type=Path, help='A separately verified compatible derived batch')
    parser.add_argument('--equivalent-batch-verification-sha256',
                        help='Require a freshly fully verified replacement with identical original named-batch payload')
    parser.add_argument('--assembler', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--output', type=Path,
                        default=S.ART / 'formal-native-transitions' / ('native-' + uuid4().hex))
    args = parser.parse_args()
    print(extend(args.state, args.family, args.assembler, args.output, args.workers,
                 batch_override=args.batch, regenerate=args.regenerate_family,
                 equivalent_batch_verification_sha256=args.equivalent_batch_verification_sha256))
