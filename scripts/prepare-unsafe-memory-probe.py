"""Source-bound typed heap memory fixtures and explicit original atomic entries."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(z,n):return [json.loads(l) for l in z.read(n).splitlines()]

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    s=read(a.batch/'summary.json');plan=read(a.plan/'summary.json');assert s['schema']>=21 and s['input_fingerprint']==plan['input_fingerprint']
    raw=Path(plan['artifacts']['classes']['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==plan['artifacts']['classes']['digest']['sha256']
    classes=[json.loads(l) for l in raw.splitlines()];owners={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    with zipfile.ZipFile(s['unsafe_memory']['index']['path']) as z:methods=rows(z,'methods.jsonl')
    with zipfile.ZipFile(s['unsafe_fields']['index']['path']) as z:fields=rows(z,'fields.jsonl')
    with zipfile.ZipFile(s['runtime_metadata']['index']['path']) as z:
        types=rows(z,'types.jsonl');maps={r['id']:r for r in rows(z,'fields.jsonl')};runtime={r['type_id']:r for r in rows(z,'runtime.jsonl')}
    chosen={}
    for f in fields:
        c=classes[f['class_id']]
        if f['kind'] in chosen or f['access']&8 or f['address_map'] is None or c['origin']['loader']!='bootstrap' or c['origin']['source_id']!='jdk:java.base' or c['access']&0x8600:continue
        if f['id'] not in maps:continue
        actual=next((r for r in maps[f['id']]['rows'] if r['receiver_class']==f['class_id']),None)
        if actual and f['class_id'] in runtime:chosen[f['kind']]=dict(f,offset=actual['offset'])
    assert set(chosen)==set(range(1,10))
    obj=owners[('bootstrap','java/lang/Object')];atomic=owners[('bootstrap','java/util/concurrent/atomic/AtomicInteger')]
    array=next(t['id'] for t in types if t['name']=='[Ljava/lang/Object;' and t['defining_loader']=='bootstrap')
    unsafe=methods[0]['class_id']
    with zipfile.ZipFile(s['class_state']['index']['path']) as z:states={r['class_id']:r for r in rows(z,'classes.jsonl')}
    single=next(r['index'] for r in states[unsafe]['fields'] if r['name']=='theUnsafe')
    atomic_value=next(f['id'] for f in fields if f['class_id']==atomic and f['name']=='value' and not f['access']&8)
    signatures=[('<init>','(I)V'),('get','()I'),('compareAndSet','(II)Z'),('getAndIncrement','()I')];definitions=None
    for shard in s['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as z:
            name=f'classes/{atomic:06}.json'
            if name in z.namelist():definitions=read_def=json.loads(z.read(name));break
    assert definitions
    entries=[];entry_symbols=[]
    for name,desc in signatures:
        m=next(m for m in definitions['methods'] if (m['name'],m['descriptor'])==(name,desc));assert m['assembly_emitted'] and m['code_sha256']
        entries.append(f'bootstrap:java/util/concurrent/atomic/AtomicInteger:{name}:{desc}');entry_symbols.append('boom_m'+str(m['id']))
    roots=['bootstrap:jdk/internal/misc/Unsafe','bootstrap:java/util/concurrent/atomic/AtomicInteger']
    for m in methods:entries.append(f"bootstrap:jdk/internal/misc/Unsafe:{m['name']}:{m['descriptor']}")
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'fields.tsv').write_text(''.join(f"{kind}\t{f['id']}\t{f['class_id']}\t{f['storage_bytes']}\t{f['offset']}\n" for kind,f in sorted(chosen.items())))
    (a.output/'methods.tsv').write_text(''.join(f"{m['operation']}\tboom_m{m['method']}\n" for m in methods))
    # Raw vectors are shared with the JVM development oracle. No numeric object
    # pointers or VM-specific field offsets cross the oracle boundary.
    patterns=[0,1,2,0x7f,0x80,0xff,0x7fff,0x8000,0xffff,0x7fffffff,0x80000000,0xffffffff,
        0x7f800000,0xff800000,0x7fc12345,0x7f812345,0x8000000000000000,0x7ff0000000000000,
        0xfff0000000000000,0x7ff8123456789abc,0x7ff0123456789abc,0xffffffffffffffff]
    value=0x9e3779b97f4a7c15
    for _ in range(512):
        value^=(value<<13)&0xffffffffffffffff;value^=value>>7;value^=(value<<17)&0xffffffffffffffff;patterns.append(value)
    (a.output/'vectors.tsv').write_text(''.join(f'{kind}\t{n:016x}\n' for kind in range(1,9) for n in patterns))
    loader_count=len(s['class_literals']['loader_keys']);module_count=len(s['class_literals']['modules'])
    result=dict(batch=str(a.batch.resolve()),plan=str(a.plan.resolve()),source_input_fingerprint=s['input_fingerprint'],unsafe_class=unsafe,unsafe_singleton=single,
        atomic_class=atomic,atomic_value_field=atomic_value,object_class=obj,reference_array=array,class_roots=roots,entries=entries,entry_symbols=entry_symbols,
        loader_roots=loader_count,module_roots=module_count,scalar_vectors=8*len(patterns),native_methods=42,fixture_target_storage=True,
        off_heap=False,static_field_base=False,game_started=False)
    (a.output/'source.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(native_methods=42,scalar_vectors=result['scalar_vectors'])))
