"""Preselect generated Java methods of source-proved classes, never executions.

This reduces repeated lazy-target rebuilds. It changes compilation selection,
not class initialization roots, native services or executed-admission evidence.
Every selected function still passes the existing independent image verifier.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
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


def package_classes(closure, summary, prefixes, inputs):
    requested = set()
    for value in prefixes:
        loader, separator, package = value.partition(':')
        check(separator and loader and re.fullmatch(r'[A-Za-z0-9_$]+(?:/[A-Za-z0-9_$]+)*', package),
              'Package selection requires loader:internal/package')
        requested.add((loader, package + '/'))
    if not requested:
        return {}, []
    plan = Path(closure['plan']).resolve()
    manifest = plan / 'summary.json'
    check(manifest.is_relative_to(ROOT/'.boom'), 'Package plan must be a project input')
    source = read(manifest)
    check(source['input_fingerprint'] == summary['input_fingerprint'] and closure['batch_ir_identity'] == summary['ir_identity'],
          'Package selection and bytecode batch have different input identities')
    record = source['artifacts']['classes']
    classes = Path(record['path']).resolve()
    check(classes.is_relative_to(ROOT/'.boom') and sha(classes) == record['digest']['sha256'] == closure['source_classes_sha256'],
          'Package selection class provenance changed')
    inputs.update({str(manifest): sha(manifest), str(classes): record['digest']['sha256']})
    chosen = {}
    with classes.open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if any(row['origin']['loader'] == loader and row['name'].startswith(package) for loader,package in requested):
                check(row['id'] not in chosen, 'Duplicate package class identity')
                chosen[row['id']] = row['origin']['sha256']
    check(chosen, 'Requested packages contain no classes in the verified plan')
    return chosen, sorted(loader + ':' + package[:-1] for loader,package in requested)


def preselect(batch, selection, profile, output, max_extra=16384, packages=()):
    batch, selection, profile, output = map(lambda p: Path(p).resolve(), (batch, selection, profile, output))
    check(all(p.is_relative_to(ROOT/'.boom') for p in (batch, selection, profile, output)) and not output.exists(),
          'Preselection requires project artifacts and a fresh output')
    check(1 <= max_extra <= 65536, 'Preselection method budget outside supported bounds')
    summary_path, closure_path, proof_path = batch/'summary.json', selection/'closure.json', selection/'selection-verification.json'
    summary, closure, proof, actual = read(summary_path), read(closure_path), read(proof_path), read(profile)
    inputs = {str(p): sha(p) for p in (summary_path, closure_path, proof_path, profile, selection/'initialization-closure.asm')}
    check(proof.get('verified') and proof.get('diagnostic_only') and not proof.get('source_closure_complete'),
          'Preselection needs an independently source-proved diagnostic selection')
    check(proof['closure_manifest_sha256'] == inputs[str(closure_path)], 'Source selection manifest changed')
    source_batch = Path(closure['batch']).resolve()
    source_summary_path = source_batch/'summary.json'
    check(source_batch.is_relative_to(ROOT/'.boom') and actual['source_batch_summary_sha256'] == inputs[str(summary_path)],
          'Preselection source batch differs')
    inputs[str(source_summary_path)] = sha(source_summary_path)
    source_summary = read(source_summary_path)
    check(closure['source_batch_summary_sha256'] == inputs[str(source_summary_path)] and
          closure['batch_ir_identity'] == source_summary['ir_identity'] == summary['ir_identity'] and
          source_summary['input_fingerprint'] == summary['input_fingerprint'],
          'Preselection original source input or IR changed')
    assembly = selection/'initialization-closure.asm'
    check(hashlib.sha256(assembly.read_text(encoding='utf-8').encode()).hexdigest() == proof['closure_assembly_sha256'],
          'Preselection source image assembly changed')
    wanted = {c['class_id']: c['source_sha256'] for c in closure['selected_classes']}
    priority, package_names = package_classes(closure, summary, packages, inputs)
    check(all(i not in wanted or wanted[i] == h for i,h in priority.items()),
          'Selected classes and package plan disagree about their source')
    wanted.update(priority)
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
    for owner, ids in sorted(candidates.items(), key=lambda item: (item[0] not in priority, item[0])):
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
    if package_names:
        result['source_only_preselection'].update(rule='generated_Java_methods_of_verified_selected_classes_and_packages',
            requested_packages=package_names, matching_package_classes=len(priority),
            selected_package_classes=sorted(set(owners).intersection(priority)))
    if source_batch != batch:
        result['source_only_preselection']['source_selection_reuse'] = dict(
            previous_batch=str(source_batch), previous_batch_summary_sha256=inputs[str(source_summary_path)],
            current_batch=str(batch), current_batch_summary_sha256=inputs[str(summary_path)],
            rule='same_input_and_IR_each_original_class_rechecked_in_current_archives',
            native_bindings_reused=False, source_initialization_roots_reused=False,
            current_selected_methods_previously_executed=False)
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
    p.add_argument('--package', action='append', default=[], help='Prefer all generated Java methods in loader:internal/package')
    a = p.parse_args()
    result = preselect(a.batch, a.selection, a.profile, a.output, a.max_extra_methods, a.package)
    print(json.dumps(result['source_only_preselection']))
