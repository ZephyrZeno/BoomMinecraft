"""Link production Class mirrors and unchanged original Class field getters."""
import argparse
import importlib.util
import json
from pathlib import Path
import zipfile

def prepare(batch,plan,output):
    batch,plan,output=Path(batch),Path(plan),Path(output);s=json.loads((batch/'summary.json').read_text(encoding='utf-8'));assert s['schema']>=10
    spec=importlib.util.spec_from_file_location('normal_class_closure',Path(__file__).with_name('prepare-class-init-probe.py'));selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
    methods=[('bootstrap','java/lang/Class',name,desc) for name,desc in [('getComponentType','()Ljava/lang/Class;'),('getClassLoader0','()Ljava/lang/ClassLoader;'),('getModule','()Ljava/lang/Module;'),('isInstance','(Ljava/lang/Object;)Z')]]
    if s['schema']>=11:methods.append(('bootstrap','java/lang/Class','getName','()Ljava/lang/String;'))
    closure=selector.prepare(batch,plan,output,[],methods)
    with zipfile.ZipFile(s['class_literals']['index']['path']) as z:rows=list(map(json.loads,z.read('types.jsonl').splitlines()))
    with zipfile.ZipFile(s['runtime_metadata']['index']['path']) as z:types={r['id']:r for r in map(json.loads,z.read('types.jsonl').splitlines())}
    (output/'types.tsv').write_text(''.join(f"{r['type_id']}\t{types[r['type_id']]['kind']}\t{r['component'] if r['component'] is not None else -1}\t{r['superclass'] if r['superclass'] is not None else -1}\t{r['loader']}\t{r['module']}\t{types[r['type_id']]['name']}\n" for r in rows),encoding='utf-8')
    names={t['name']:t['id'] for t in types.values() if t['defining_loader']=='bootstrap'}
    keys=s['class_literals']['loader_keys'];assert set(keys)<=set(('bootstrap','platform','vanilla-application'))
    (output/'loaders.tsv').write_text(''.join(f'{id_}\t{names["jdk/internal/loader/ClassLoaders$PlatformClassLoader" if key=="platform" else "jdk/internal/loader/ClassLoaders$AppClassLoader"]}\n' for id_,key in enumerate(keys) if id_),encoding='ascii')
    closure.update(Class_source_shape=s['class_literals']['source_shape'],source_types=len(rows),Class_getters={m['name']:m['symbol'] for m in closure['requested_method_roots']})
    (output/'closure.json').write_text(json.dumps(closure,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(source_types=len(rows),original_Java_methods=len(closure['selected_methods']))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch',type=Path);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();prepare(a.batch,a.plan,a.output)
