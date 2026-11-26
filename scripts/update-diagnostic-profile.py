"""Admit emitted Java from source rows actually reached by a native process."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def observed_ids(event):
    if 'source_admission_rows' in event:
        return event['source_admission_rows']
    fault = event.get('fault')
    return [fault.get('id')] if fault and fault['category'] in (1, 5) else []


def verified_context_faults(path, event):
    # Resolve observable row numbers independently from the native report and
    # the original diagnostic table. A JSON row alone cannot admit a target.
    root = path.parent
    image = Path((root / 'native-execution-directory.txt').read_text(encoding='utf-8-sig').strip()).resolve()
    images = Path(__file__).resolve().parents[1] / '.boom/vm-entry-images'
    if not image.is_relative_to(images):
        raise ValueError('Source admission requires an isolated native process image')
    binary = (image / 'vm-entry-status.bin').read_bytes()
    native_proof = (image / 'verification.json').read_bytes()
    native_manifest = (image / 'vm-entry.json').read_bytes()
    proof = (root / 'selection-verification.json').read_bytes()
    table = (root / 'diagnostic.json').read_bytes()
    sha = lambda data: hashlib.sha256(data).hexdigest()
    verified = json.loads(proof)
    entry = json.loads(native_proof)
    inputs = json.loads(native_manifest)
    if (sha(binary) != event['native_report_sha256'] or sha(native_proof) != event['source_verification_sha256'] or
            not entry.get('verified') or entry.get('source_manifest_sha256') != sha(native_manifest) or
            Path(inputs['baseline_directory']).resolve() != root.resolve() or
            inputs['accepted_source_verification_sha256'] != sha(proof) or
            not verified.get('verified') or not verified.get('diagnostic_only') or
            sha(table) != verified['diagnostic_manifest_sha256'] or len(binary) not in (320,384,400,448)):
        raise ValueError('Native report or verified source admission table changed')
    words = struct.unpack_from('<80I', binary)
    if (words[0] != 0x52454d56 or (words[1],len(binary)) not in ((8,320),(9,384),(10,400),(11,448)) or
            words[7] != 2 or not words[8]):
        raise ValueError('Native report has no published diagnostic source row')
    primary, first = words[78], words[8]
    if primary and words[74] != 0xb001:
        raise ValueError('Main source row has no native diagnostic context')
    if (event.get('first_row'), event.get('main_source_row')) != (first, primary):
        raise ValueError('Native and reported source row numbers differ')
    table_rows = json.loads(table)['rows']
    def resolve(i):
        if not 0 < i <= len(table_rows) or table_rows[i - 1]['id'] != i:
            raise ValueError('Native source admission row does not exist')
        return table_rows[i - 1]
    faults = [resolve(i) for i in dict.fromkeys((primary or first, first))]
    if event.get('fault') != faults[0] or event.get('first_process_fault') != resolve(first):
        raise ValueError('Published source row differs from verified native selection')
    eligible = [f for f in faults if f['category'] in (1, 5)]
    if [f['id'] for f in eligible] != observed_ids(event):
        raise ValueError('Source admission rows are missing or were never observed')
    return eligible


def admit_target(s, f, admitted, admitted_classes, execution_hash):
    if f['category']==5:
        with zipfile.ZipFile(s['class_state']['index']['path']) as z:states={r['class_id']:r for r in map(json.loads,z.read('classes.jsonl').splitlines())}
        state=states.get(f['class_id'])
        if state is None or state!=f.get('initialization') or state['diagnostic'] is not None or state['source_sha256']!=f['source_sha256'] or f['symbol']!='boom_batch_initialize_'+str(state['class_id']):raise ValueError('Reached initialization source identity changed')
        selected=set(admitted_classes);selected.add(f['class_id'])
        return dict(admitted_methods=sorted(admitted),admitted_classes=sorted(selected),rule='executed_source_class_initialization',reached_method=None,
            source_class_id=f['class_id'],source_sha256=f['source_sha256'],execution_sha256=execution_hash,native_implementations_added=0,diagnostic_only=True)
    target=f['method'];name=f"classes/{f['class_id']:06}.json";source=None
    for shard in s['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as z:
            if name in z.namelist():source=json.loads(z.read(name));break
    if source is None or source['source_sha256']!=f['source_sha256']:raise ValueError('Reached diagnostic class identity changed')
    m=next((m for m in source['methods'] if m['id']==target['id']),None)
    if m is None or not m['assembly_emitted'] or any(m[k]!=v for k,v in target.items()):raise ValueError('Reached target is not the original generated Java method')
    selected=set(admitted);selected.update(m['id'] for m in source['methods'] if m['assembly_emitted'])
    return dict(admitted_methods=sorted(selected),admitted_classes=sorted(admitted_classes),rule='executed_class_existing_Java_methods',reached_method=target['id'],
        source_class_id=f['class_id'],source_sha256=f['source_sha256'],execution_sha256=execution_hash,
        native_implementations_added=0,diagnostic_only=True)


def update(batch, execution, admitted, admitted_classes=()):
    path = Path(execution)
    data = path.read_bytes()
    event = json.loads(data)
    if not event.get('diagnostic_only') or not observed_ids(event):
        raise ValueError('Admission requires an executed unselected source target')
    faults = verified_context_faults(path, event) if 'source_admission_rows' in event else [event['fault']]
    summary = json.loads((Path(batch) / 'summary.json').read_bytes())
    execution_hash = hashlib.sha256(data).hexdigest()
    owners = {}
    last = None
    for fault in faults:
        last = admit_target(summary, fault, admitted, admitted_classes, execution_hash)
        owners.update({str(i): fault['class_id'] for i in set(last['admitted_methods']).difference(admitted)})
        admitted, admitted_classes = last['admitted_methods'], last['admitted_classes']
    if len(faults) > 1:
        last.update(rule='independently_observed_native_source_rows',
                    reached_source_rows=[f['id'] for f in faults], method_admission_owners=owners)
    return last


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('--execution',type=Path,required=True);p.add_argument('--admitted',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    profile=json.loads(a.admitted.read_text(encoding='utf-8'));s=Path(a.batch)/'summary.json'
    if profile['source_batch_summary_sha256']!=hashlib.sha256(s.read_bytes()).hexdigest():raise ValueError('Admitted profile belongs to a different batch')
    r=update(a.batch,a.execution,profile['admitted_methods'],profile.get('admitted_classes',[]));a.output.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(reached_method=r['reached_method'],admitted=len(r['admitted_methods']),admitted_classes=len(r['admitted_classes']))))
