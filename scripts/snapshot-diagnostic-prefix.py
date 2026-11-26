"""Freeze completed diagnostic rounds for source-verified selection reuse.

The original driver can keep running. Only finished, source-proved rounds are
recorded; this file neither resumes its process nor claims completed startup.
The existing seed verifier still checks the entire source/admission provenance.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import uuid


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / '.boom/diagnostic-startup'


def check(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def snapshot(directory, output=None):
    directory = Path(directory).resolve()
    check(directory.is_relative_to(DIAGNOSTICS) and directory.is_dir(),
          'Diagnostic prefix must come from this project diagnostic directory')
    output = Path(output).resolve() if output else directory / ('prefix-' + uuid.uuid4().hex + '.json')
    check(output.parent == directory and not output.exists(),
          'Prefix output must be a new file inside the original diagnostic directory')
    module_path = Path(__file__).with_name('update-diagnostic-profile.py')
    spec = importlib.util.spec_from_file_location('prefix_executed_admissions', module_path)
    admissions = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admissions)
    inputs = {}

    def record(path):
        path = Path(path).resolve()
        check(path.is_relative_to(ROOT / '.boom'), 'Prefix input outside project artifacts')
        inputs[str(path)] = digest(path)
        return read(path)

    seed_path = directory / 'seed.json'
    original_seed = record(seed_path) if seed_path.exists() else None
    methods = set(original_seed['admitted_methods']) if original_seed else set()
    classes = set(original_seed.get('admitted_classes', [])) if original_seed else set()
    first = None
    rounds = []
    for index, round_path in enumerate(sorted(directory.glob('round-*'))):
        check(round_path.name == f'round-{index:03}', 'Diagnostic prefix rounds are not contiguous')
        execution_path = round_path / 'execution.json'
        if not execution_path.exists():
            break
        execution = record(execution_path)
        proof = record(round_path / 'selection-verification.json')
        manifest = record(round_path / 'closure.json')
        check(proof.get('verified') and proof.get('diagnostic_only') and not proof.get('source_closure_complete'),
              'Completed round lacks a diagnostic source proof')
        check(execution.get('diagnostic_only') and not execution.get('game_started') and not execution.get('source_closure_complete'),
              'Prefix can only reuse development diagnostic execution')
        if first is None:
            first = manifest
            batch = Path(first['batch']).resolve()
            record(batch / 'summary.json')
            check(digest(batch / 'summary.json') == first['source_batch_summary_sha256'],
                  'Prefix source batch changed')
            if original_seed:
                check(original_seed['source_batch_summary_sha256'] == first['source_batch_summary_sha256'],
                      'Prefix seed belongs to another batch')
        for key in ('batch', 'plan', 'source_batch_summary_sha256', 'requested_class_roots', 'requested_method_roots'):
            check(manifest[key] == first[key], 'Prefix source or requested roots changed')
        rounds.append(dict(directory=str(round_path), execution=execution))
        if admissions.observed_ids(execution):
            admitted = admissions.update(batch, execution_path, methods, classes)
            methods = set(admitted['admitted_methods'])
            classes = set(admitted['admitted_classes'])
        else:
            break
    check(rounds, 'No completed diagnostic rounds to freeze')
    for path, sha in inputs.items():
        check(digest(path) == sha, 'Prefix input changed while snapshotting: ' + path)
    result = dict(schema=1, diagnostic_only=True, batch=str(batch), plan=first['plan'],
                  source_batch_summary_sha256=first['source_batch_summary_sha256'],
                  class_roots=[r['loader'] + ':' + r['name'] for r in first['requested_class_roots']],
                  entries=[':'.join(r[k] for k in ('loader', 'owner', 'name', 'descriptor'))
                           for r in first['requested_method_roots']],
                  admitted_methods=sorted(methods), admitted_classes=sorted(classes),
                  seed_evidence=dict(path=str(seed_path), sha256=inputs[str(seed_path)]) if original_seed else None,
                  rounds=rounds, stop_reason='snapshot_of_completed_diagnostic_rounds',
                  source_driver_terminal=False, prefix_inputs_sha256=inputs,
                  source_closure_complete=False, native_implementations_added=0,
                  game_started=False, world_created=False, full_game_ready=False)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    return output, result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    path, result = snapshot(args.directory, args.output)
    print(json.dumps(dict(prefix=str(path), completed_rounds=len(result['rounds']),
                          admitted_Java_methods=len(result['admitted_methods']),
                          native_implementations_added=0, game_started=False)))
