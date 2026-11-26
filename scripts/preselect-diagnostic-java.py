"""Preselect generated Java methods of source-proved classes, never executions.

This reduces repeated lazy-target rebuilds. It changes compilation selection,
not class initialization roots, native services or executed-admission evidence.
Every selected function still passes the existing independent image verifier.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def check(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def preselect(batch, selection, profile, output, max_extra=16384):
    batch, selection, profile, output = map(lambda p: Path(p).resolve(), (batch, selection, profile, output))
    check(all(p.is_relative_to(ROOT/'.boom') for p in (batch, selection, profile, output)) and not output.exists(),
          'Preselection requires project artifacts and a fresh output')
    check(1 <= max_extra <= 65536, 'Preselection method budget outside supported bounds')
    summary_path, closure_path, proof_path = batch/'summary.json', selection/'closure.json', selection/'selection-verification.json'
    summary, closure, proof, actual = read(summary_path), read(closure_path), read(proof_path), read(profile)
    inputs = {str(p): sha(p) for p in (summary_path, closure_path, proof_path, profile, selection/'initialization-closure.asm')}
    check(proof.get('verified') and proof.get('diagnostic_only') and not proof.get('source_closure_complete'),
          'Preselection needs an independently source-proved diagnostic selection')
    check(Path(closure['batch']).resolve() == batch and closure['source_batch_summary_sha256'] == inputs[str(summary_path)] == actual['source_batch_summary_sha256'],
          'Preselection source batch differs')
    assembly = selection/'initialization-closure.asm'
    check(hashlib.sha256(assembly.read_text(encoding='utf-8').encode()).hexdigest() == proof['closure_assembly_sha256'],
          'Preselection source image assembly changed')
    wanted = {c['class_id']: c['source_sha256'] for c in closure['selected_classes']}
    original = set(actual['admitted_methods'])
    candidates = {}
    for shard in summary['shards']:
        archive_path = Path(shard['zip']['path']).resolve()
        check(archive_path.is_relative_to(ROOT/'.boom'), 'Preselection archive outside project')
        with zipfile.ZipFile(archive_path) as archive:
            names = [n for n in archive.namelist() if n.startswith('classes/') and n.endswith('.json') and int(Path(n).stem) in wanted]
            if not names:
                continue
            check(sha(archive_path) == shard['zip']['digest']['sha256'], 'Preselection source archive changed')
            inputs[str(archive_path)] = shard['zip']['digest']['sha256']
            for name in names:
                source = json.loads(archive.read(name))
                owner = source['class_id']
                check(source['source_sha256'] == wanted.pop(owner), 'Preselection original declaring class changed')
                candidates[owner] = [m['id'] for m in source['methods'] if m['assembly_emitted'] and
                    m['code_sha256'] is not None and m['stage'] == 'assembly_emitted_unlinked' and m['id'] not in original]
    check(not wanted, 'Preselection source classes are missing')
    chosen = set()
    owners = []
    for owner, ids in sorted(candidates.items()):
        if ids and len(chosen) + len(ids) <= max_extra:
            chosen.update(ids)
            owners.append(owner)
    for path, digest in inputs.items():
        check(sha(path) == digest, 'Preselection input changed: ' + path)
    result = dict(actual, admitted_methods=sorted(original | chosen))
    result['source_only_preselection'] = dict(rule='generated_Java_methods_of_source_proved_selected_classes',
        source_selection_directory=str(selection), source_selection_proof_sha256=inputs[str(proof_path)],
        original_executed_admission_methods=len(original), extra_generated_methods=len(chosen), class_ids=owners,
        max_extra_methods=max_extra, inputs_sha256=inputs, tool_sha256=sha(__file__),
        extra_methods_previously_executed=False, extra_class_initialization_roots=0,
        native_implementations_added=0, game_started=False)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('batch', type=Path)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--max-extra-methods', type=int, default=16384)
    a = p.parse_args()
    result = preselect(a.batch, a.selection, a.profile, a.output, a.max_extra_methods)
    print(json.dumps(result['source_only_preselection']))
