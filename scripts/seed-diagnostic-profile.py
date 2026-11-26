"""Reuse executed Java selection across source-identical batches, never natives."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def check(value,message):
    if not value:raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def identity(old,new):
    check(all(old[k]==new[k] for k in ('input_fingerprint','ir_identity')),'Selection seed source input/IR differs')


def compatible_methods(old,new,ids):
    check(old['class_id']==new['class_id'] and old['source_sha256']==new['source_sha256'],'Selection seed class identity differs')
    a={m['id']:m for m in old['methods']};b={m['id']:m for m in new['methods']}
    for i in ids:
        check(i in a and i in b,'Selection seed method missing')
        for m in (a[i],b[i]):
            check(m['assembly_emitted'] and m['code_sha256'] is not None and m['stage']=='assembly_emitted_unlinked',
                  'Selection seed cannot supply native/failed methods')
        check(all(a[i][k]==b[i][k] for k in ('name','descriptor','code_sha256')),'Selection seed original Code differs')


class SeedSources:
    """Index each ZIP directory once per replay; retain only fields used in source comparison."""
    def __init__(self):
        self.members = {}
        self.classes = {}
        self.verified = {}

    def read(self, summary, ids):
        pending = {f'classes/{i:06}.json': i for i in ids}
        found = {}
        for shard in summary['shards']:
            if not pending:
                break
            record = shard['zip']
            path = Path(record['path']).resolve()
            check(path.is_relative_to(ROOT/'.boom'), 'Seed source artifact outside project')
            if path not in self.members:
                with zipfile.ZipFile(path) as z:
                    self.members[path] = set(z.namelist())
            wanted = pending.keys() & self.members[path]
            if not wanted:
                continue
            expected = record['digest']['sha256']
            if path not in self.verified:
                self.verified[path] = digest(path)
            check(self.verified[path] == expected, 'Seed source class archive changed')
            missing = [name for name in wanted if (path, name) not in self.classes]
            if missing:
                with zipfile.ZipFile(path) as z:
                    for name in missing:
                        row = json.loads(z.read(name))
                        check(row['class_id'] == pending[name], 'Seed source archive class ID differs')
                        methods = [{k: m[k] for k in ('id','name','descriptor','code_sha256','assembly_emitted','stage')}
                                   for m in row['methods']]
                        self.classes[path, name] = dict(class_id=row['class_id'], source_sha256=row['source_sha256'], methods=methods)
            for name in wanted:
                found[pending.pop(name)] = self.classes[path, name]
        check(not pending, 'Missing source class for selection seed')
        return found

    def verify(self):
        for path, expected in self.verified.items():
            check(digest(path) == expected, 'Seed source class archive changed during replay')


def root_extension(old,new,allowed):
    if old==new:return None
    check(allowed and len(set(new))==len(new),'Seed requested class roots differ')
    at=0
    for root in new:
        if at<len(old) and root==old[at]:at+=1
    check(at==len(old),'Seed root extension must retain existing roots and order')
    return dict(previous_class_roots=old,requested_class_roots=new,additional_class_roots=[r for r in new if r not in old],
                scope='reuse_source_verified_Java_selection_only_new_roots_must_execute',full_VM_bootstrap=False)


def entry_reuse(old,new,allowed):
    if old==new:return None
    check(allowed and new and len(set(new))==len(new),'Seed requested roots/entries differ')
    return dict(previous_entries=old,requested_entries=new,
                scope='reuse_source_verified_Java_selection_only_new_entries_must_execute',
                new_entries_previously_executed=False,full_VM_bootstrap=False)


def seed(batch,previous,classes,entries,_depth=0,allow_additional_classes=False,allow_different_entries=False):
    sources=SeedSources()
    result=_seed(batch,previous,classes,entries,_depth,allow_additional_classes,allow_different_entries,sources)
    sources.verify()
    return result


def _seed(batch,previous,classes,entries,_depth,allow_additional_classes,allow_different_entries,sources):
    check(_depth<128,'Selection seed chain exceeds budget')
    batch=Path(batch).resolve();previous=Path(previous).resolve()
    check(batch.is_relative_to(ROOT/'.boom') and previous.parent.is_relative_to(ROOT/'.boom/diagnostic-startup'),
          'Seed inputs must remain inside project artifacts')
    old=json.loads(previous.read_text(encoding='utf-8'));old_batch=Path(old['batch']).resolve()
    check(old_batch.is_relative_to(ROOT/'.boom'),'Previous seed batch outside project')
    check(old['diagnostic_only'] and not old['source_closure_complete'] and not old['game_started'],'Seed is not a development diagnostic')
    entry_change=entry_reuse(old['entries'],entries,allow_different_entries)
    extension=root_extension(old['class_roots'],classes,allow_additional_classes)
    old_summary=json.loads((old_batch/'summary.json').read_text(encoding='utf-8'))
    new_summary=json.loads((batch/'summary.json').read_text(encoding='utf-8'));identity(old_summary,new_summary)
    check(old['source_batch_summary_sha256']==digest(old_batch/'summary.json'),'Seed previous batch changed')
    spec=importlib.util.spec_from_file_location('seed_executed_admissions',Path(__file__).with_name('update-diagnostic-profile.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    admitted=set();admitted_classes=set();owners={};proofs=[]
    evidence=old.get('seed_evidence')
    # v107 resumed results omitted this metadata but retained the original seed.
    # Recover it only through the same recursive provenance check below.
    if evidence is None and (previous.parent/'seed.json').exists():
        path=previous.parent/'seed.json';evidence=dict(path=str(path),sha256=digest(path))
    if evidence:
        path=Path(evidence['path']).resolve()
        check(path.is_relative_to(previous.parent) and digest(path)==evidence['sha256'],'Previous selection seed changed')
        original_seed=json.loads(path.read_text(encoding='utf-8'))
        base=_seed(old_batch,Path(original_seed['previous_result']),old['class_roots'],old['entries'],_depth+1,
                  allow_additional_classes='requested_root_extension' in original_seed,
                  allow_different_entries='requested_entry_change' in original_seed,sources=sources)
        check(base==original_seed,'Previous selection seed provenance differs')
        check(base['source_batch_summary_sha256']==old['source_batch_summary_sha256'],'Previous seed batch differs')
        admitted.update(base['admitted_methods']);proofs.extend(base['executed_admission_proofs'])
        admitted_classes.update(base.get('admitted_classes',[]))
        for owner,ids in base['source_classes'].items():
            for i in ids:owners[i]=int(owner)
    for round_ in old['rounds']:
        p=Path(round_['directory']).resolve();check(p.is_relative_to(previous.parent),'Seed round outside previous diagnostic')
        execution=json.loads((p/'execution.json').read_text(encoding='utf-8'))
        check(execution==round_['execution'],'Seed execution record changed')
        proof=json.loads((p/'selection-verification.json').read_text(encoding='utf-8'))
        check(proof['verified'] and proof['diagnostic_only'] and not proof['source_closure_complete'],'Seed lacks diagnostic source proof')
        manifest=json.loads((p/'closure.json').read_text(encoding='utf-8'))
        check(manifest['source_batch_summary_sha256']==old['source_batch_summary_sha256'],'Seed round batch differs')
        if not m.observed_ids(execution):continue
        update=m.update(old_batch,p/'execution.json',admitted,admitted_classes);next_=set(update['admitted_methods'])
        admitted_classes.update(update.get('admitted_classes',[]))
        for i in next_-admitted:
            owners[i]=update['method_admission_owners'][str(i)] if 'method_admission_owners' in update else update['source_class_id']
        admitted=next_;proofs.append(dict(execution=str(p/'execution.json'),sha256=digest(p/'execution.json')))
    check(sorted(admitted)==old['admitted_methods'],'Seed profile is not derived from its executed Java targets')
    check(sorted(admitted_classes)==old.get('admitted_classes',[]),'Seed class initialization profile lacks execution evidence')
    by_owner={}
    for i in sorted(admitted):by_owner.setdefault(owners[i],[]).append(i)
    needed=set(by_owner)|admitted_classes
    previous_classes=sources.read(old_summary,needed)
    current_classes=sources.read(new_summary,needed)
    for id_ in admitted_classes:
        a=previous_classes[id_];b=current_classes[id_]
        check(a['class_id']==b['class_id']==id_ and a['source_sha256']==b['source_sha256'],'Seed original initialization class changed')
    for id_,ids in by_owner.items():
        compatible_methods(previous_classes[id_],current_classes[id_],ids)
    result=dict(source_batch_summary_sha256=digest(batch/'summary.json'),admitted_methods=sorted(admitted),
                rule='source_verified_cross_batch_executed_Java_classes',previous_result=str(previous),previous_result_sha256=digest(previous),
                source_input_fingerprint=new_summary['input_fingerprint'],ir_identity=new_summary['ir_identity'],executed_admission_proofs=proofs,
                source_classes={str(c):by_owner[c] for c in sorted(by_owner)},
                native_implementations_added=0,diagnostic_only=True,game_started=False)
    if admitted_classes:result['admitted_classes']=sorted(admitted_classes)
    if extension is not None:result['requested_root_extension']=extension
    if entry_change is not None:result['requested_entry_change']=entry_change
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('--previous',required=True,type=Path)
    p.add_argument('--class-root',action='append',default=[]);p.add_argument('--entry',action='append',default=[]);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--allow-additional-class-roots',action='store_true');p.add_argument('--allow-different-entries',action='store_true');a=p.parse_args()
    r=seed(a.batch,a.previous,a.class_root,a.entry,allow_additional_classes=a.allow_additional_class_roots,allow_different_entries=a.allow_different_entries);a.output.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(admitted=len(r['admitted_methods']),native_implementations_added=0)))
