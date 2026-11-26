"""Extract source-bound test addresses; no guest initialization on the host."""
import argparse
import json
from pathlib import Path
import zipfile


def prepare(directory):
    closure=json.loads((directory/'closure.json').read_text(encoding='utf-8'))
    summary=json.loads((Path(closure['batch'])/'summary.json').read_text(encoding='utf-8'))
    module=summary['unsafe_bootstrap']
    selected={c['class_id'] for c in closure['selected_classes']}
    for id_ in (module['class_id'],module['constants_class_id']):
        if id_ not in selected:raise ValueError('Probe source class state was not selected')
    with zipfile.ZipFile(module['index']['path']) as z:methods=[json.loads(l) for l in z.read('methods.jsonl').splitlines()]
    if [m['operation'] for m in methods]!=[0,1,2,3]:raise ValueError('Probe native operation order differs')
    with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as z:types=[json.loads(l) for l in z.read('types.jsonl').splitlines()]
    arrays=['[Z','[B','[S','[C','[I','[J','[F','[D','[Ljava/lang/Object;','[[I']
    ids=[]
    for array in arrays:
        found=[r['id'] for r in types if r['name']==array and r['kind']==3 and r['defining_loader']=='bootstrap']
        if len(found)!=1:raise ValueError('Missing unique source array identity: '+array)
        ids.append(found[0])
    cls=None
    with (Path(closure['plan'])/'classes.jsonl').open(encoding='utf-8') as source:
        for line in source:
            row=json.loads(line)
            if row['id']==module['class_id']:cls=row;break
    if not cls or cls['name']!='jdk/internal/misc/Unsafe' or cls['origin']['sha256']!=module['class_sha256']:
        raise ValueError('Unsafe probe original class identity differs')
    scale=dict(BOOLEAN=1,BYTE=1,SHORT=2,CHAR=2,INT=4,LONG=8,FLOAT=4,DOUBLE=8,OBJECT=8)
    names=[];values=[]
    for i,f in enumerate(cls['fields']):
        n=f['name'];value=None
        if n.startswith('ARRAY_') and n.endswith('_BASE_OFFSET'):value=0
        elif n.startswith('ARRAY_') and n.endswith('_INDEX_SCALE'):value=scale[n[6:-12]]
        elif n=='ADDRESS_SIZE':value=8
        elif n=='INVALID_FIELD_OFFSET':value=-1
        if value is not None:names.append(f"boom_s{cls['id']}_{i}");values.append(value)
    if len(names)!=20:raise ValueError('Unsafe source static probe coverage differs')
    return dict(native_names=[f"boom_m{m['method']}_native" for m in methods],array_types=ids,array_names=arrays,
                scales=[1,1,2,2,4,8,4,8,8,8],static_names=names,static_values=values)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    a.output.write_text(json.dumps(prepare(a.directory),indent=2)+'\n',encoding='utf-8')
