"""Prepare source-bound field lookup and receiver-layout fixtures, not a game."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(z,name):return [json.loads(l) for l in z.read(name).splitlines()]
def hex16(s):return s.encode('utf-16le','surrogatepass').hex()
def prepare(batch,plan,output):
    summary=read(batch/'summary.json');source=read(plan/'summary.json')
    assert summary['schema']>=20 and summary['input_fingerprint']==source['input_fingerprint']
    artifact=source['artifacts']['classes'];raw=Path(artifact['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==artifact['digest']['sha256']
    classes=[json.loads(l) for l in raw.splitlines()];owners={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    with zipfile.ZipFile(summary['unsafe_fields']['index']['path']) as z:fields=rows(z,'fields.jsonl');methods=rows(z,'methods.jsonl')
    with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as z:
        types={r['id']:r for r in rows(z,'types.jsonl')};maps=rows(z,'fields.jsonl')
    cases=[r for r in fields if classes[r['class_id']]['origin']['loader']=='bootstrap'
        and classes[r['class_id']]['origin']['source_id']=='jdk:java.base' and r['class_id'] in types]
    by_id={r['id']:r for r in cases};output.mkdir(parents=True,exist_ok=False)
    def line(r):
        c=classes[r['class_id']]
        return '\t'.join(map(str,(r['id'],r['class_id'],r['access'],r['kind'],r['storage_bytes'],int(r['address_map'] is not None),hex16(r['name']),c['name'])))+'\n'
    (output/'cases.tsv').write_text(''.join(line(r) for r in cases),encoding='ascii')
    samples=[];inherited=None
    def concrete(id_):
        c=classes[id_]
        return id_ in types and types[id_]['kind']==1 and c['origin']['loader']=='bootstrap' and c['origin']['source_id']=='jdk:java.base' and not c['access']&0x8600
    for m in maps:
        if m['id'] not in by_id:continue
        possible=[r for r in m['rows'] if concrete(r['receiver_class'])]
        if not possible:continue
        chosen=[possible[0]]
        shifted=next((r for r in possible[1:] if r['offset']!=possible[0]['offset']),None)
        if shifted:chosen.append(shifted)
        for r in chosen:
            samples.append([m['id'],r['receiver_class'],r['offset'],m['storage_bytes'],int(m['reference']),int(r['offset']!=possible[0]['offset'])])
            declaration=by_id[m['id']]
            if inherited is None and r['receiver_class']!=declaration['class_id'] and not any(f['name']==declaration['name'] for f in classes[r['receiver_class']]['fields']):
                inherited=[m['id'],r['receiver_class']]
        if len(samples)>=512:break
    assert samples and any(r[5] for r in samples) and inherited
    (output/'addresses.tsv').write_text(''.join('\t'.join(map(str,r))+'\n' for r in samples),encoding='ascii')
    oracle_owners={'java/lang/String','java/lang/Integer','java/lang/Long','java/lang/Double',
        'java/lang/Float','java/util/ArrayList','java/util/HashMap','java/util/concurrent/atomic/AtomicInteger','java/util/concurrent/atomic/AtomicBoolean'}
    oracle=[r for r in cases if classes[r['class_id']]['name'] in oracle_owners]
    (output/'oracle-cases.tsv').write_text(''.join(line(r) for r in oracle),encoding='ascii')
    # AtomicBoolean uses VarHandle in this input; its initializer is a separate
    # unimplemented mechanism, not a consumer of objectFieldOffset1.
    atomic=[owners[('bootstrap','java/util/concurrent/atomic/AtomicInteger')]]
    with zipfile.ZipFile(summary['class_state']['index']['path']) as z:states={r['class_id']:r for r in rows(z,'classes.jsonl')}
    wanted=set(atomic);definitions={}
    for shard in summary['shards']:
        if not wanted:break
        with zipfile.ZipFile(shard['zip']['path']) as z:
            for id_ in list(wanted):
                name=f'classes/{id_:06}.json'
                if name in z.namelist():definitions[id_]=read_class=json.loads(z.read(name));wanted.remove(id_)
    assert not wanted
    entries=[];symbols=[]
    for id_,arg,result in zip(atomic,('I',),('I',)):
        c=classes[id_]
        for name,desc in (('<init>',f'({arg})V'),('get',f'(){result}')):
            m=next(m for m in definitions[id_]['methods'] if (m['name'],m['descriptor'])==(name,desc))
            assert m['assembly_emitted'] and m['code_sha256']
            entries.append(f"bootstrap:{c['name']}:{name}:{desc}");symbols.append('boom_m'+str(m['id']))
    value_ids=[next(r['id'] for r in cases if r['class_id']==id_ and r['name']=='value' and not r['access']&8) for id_ in atomic]
    value_cells=[next(f['index'] for f in states[id_]['fields'] if f['name']=='VALUE') for id_ in atomic]
    unsafe=methods[0]['class_id'];single=next(f['index'] for f in states[unsafe]['fields'] if f['name']=='theUnsafe')
    result=dict(batch=str(batch.resolve()),plan=str(plan.resolve()),source_input_fingerprint=summary['input_fingerprint'],
        field_native='boom_m'+str(methods[0]['method']),unsafe_class=unsafe,unsafe_singleton=single,atomic_classes=atomic,
        atomic_value_fields=value_ids,atomic_value_cells=value_cells,entries=entries,entry_symbols=symbols,
        class_roots=['bootstrap:jdk/internal/misc/Unsafe']+['bootstrap:'+classes[i]['name'] for i in atomic],
        bootstrap_field_cases=len(cases),address_fixtures=len(samples),relocated_fixtures=sum(r[5] for r in samples),
        JVM_lookup_cases=len(oracle),inherited_non_declaration=inherited,fixture_String_inputs=True,
        target_constructors_executed_by_preparation=False,game_started=False)
    (output/'source.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=prepare(a.batch,a.plan,a.output);print(json.dumps({k:r[k] for k in ('bootstrap_field_cases','address_fixtures','relocated_fixtures','JVM_lookup_cases')}))
