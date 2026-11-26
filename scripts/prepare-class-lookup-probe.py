"""Prepare source-bound name lookup and executed initialization admission cases."""
import argparse
import json
from pathlib import Path
import zipfile

def rows(z,n):return [json.loads(l) for l in z.read(n).splitlines()]
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    s=json.loads((a.batch/'summary.json').read_text());assert s['schema']>=22
    classes=[json.loads(l) for l in (a.plan/'classes.jsonl').read_text().splitlines()];owners={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    with zipfile.ZipFile(s['class_lookup']['index']['path']) as z:methods=rows(z,'methods.jsonl');names=rows(z,'names.jsonl')
    with zipfile.ZipFile(s['class_state']['index']['path']) as z:states={r['class_id']:r for r in rows(z,'classes.jsonl')}
    entries=[f"bootstrap:{'java/lang/Class' if m['operation']==0 else 'java/lang/ClassLoader'}:{m['name']}:{m['descriptor']}" for m in methods]
    requested=[('java/lang/Class','forName','(Ljava/lang/String;ZLjava/lang/ClassLoader;)Ljava/lang/Class;'),('java/lang/Enum','name','()Ljava/lang/String;'),('java/lang/Enum','ordinal','()I')]
    symbols=[]
    for owner,name,desc in requested:
        cls=owners[('bootstrap',owner)];source=None
        for shard in s['shards']:
            with zipfile.ZipFile(shard['zip']['path']) as z:
                n=f'classes/{cls:06}.json'
                if n in z.namelist():source=json.loads(z.read(n));break
        m=next(m for m in source['methods'] if m['name']==name and m['descriptor']==desc);assert m['assembly_emitted'] and m['code_sha256']
        entries.append(f'bootstrap:{owner}:{name}:{desc}');symbols.append('boom_m'+str(m['id']))
    enums=[]
    for name in ['java/lang/Thread$State']:
        i=owners[('bootstrap',name)];enums.append(dict(class_id=i,name=name.replace('/','.'),fields=[dict(index=f['index'],name=f['name']) for f in states[i]['fields'] if f['access']&0x4000]))
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'names.tsv').write_text(''.join(f"{n['type_id']}\t{n['flags']}\t{''.join(f'{u:04x}' for u in n['utf16'])}\n" for n in names))
    (a.output/'enum-fields.tsv').write_text(''.join(f"{r['class_id']}\t{r['name']}\t{f['index']}\t{f['name']}\n" for r in enums for f in r['fields']))
    stable=['java.lang.Object','java.lang.String','java.lang.Class','java.util.concurrent.atomic.AtomicInteger','java.lang.Thread$State','java.nio.file.AccessMode','java.nio.file.StandardCopyOption','sun.nio.cs.UTF_8']
    stable+=['['*d+t for d in range(1,4) for t in ['Z','B','C','S','I','J','F','D','Ljava.lang.Object;','Ljava.lang.String;']]
    actual={''.join(chr(u) for u in n['utf16']) for n in names if n['flags']&1};stable=[n for n in stable if n in actual]
    (a.output/'oracle-cases.txt').write_text('\n'.join(stable+['missing.Type','java/lang/String','java.lang.String[]','int','void','missing.中文'])+'\n',encoding='utf-8')
    source=dict(batch=str(a.batch.resolve()),plan=str(a.plan.resolve()),source_input_fingerprint=s['input_fingerprint'],entries=entries,
        native_for_name='boom_m'+str(next(m['method'] for m in methods if m['operation']==0)),native_bootstrap='boom_m'+str(next(m['method'] for m in methods if m['operation']==1)),
        Java_entry_symbols=symbols,enums=enums,names=len(names),provided_names=sum(bool(n['flags']&1) for n in names),fixture_String_inputs=True,
        enum_initializers_admitted_by_fixture=False,game_started=False)
    (a.output/'source.json').write_text(json.dumps(source,indent=2)+'\n');print(json.dumps(dict(names=len(names),source_entries=len(entries))))
