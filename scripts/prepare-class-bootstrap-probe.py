"""Select original Class plus seven primitive-wrapper initializers, no stubs."""
import argparse
import importlib.util
import json
from pathlib import Path
import zipfile

WRAPPERS=[('Boolean','boolean'),('Byte','byte'),('Short','short'),('Integer','int'),('Long','long'),('Double','double'),('Void','void')]


def prepare(batch,plan,output):
    batch,plan,output=map(Path,(batch,plan,output))
    spec=importlib.util.spec_from_file_location('class_bootstrap_source_closure',Path(__file__).with_name('prepare-class-init-probe.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    roots=[('bootstrap','java/lang/Class')]+[('bootstrap','java/lang/'+n) for n,t in WRAPPERS]
    methods=[('bootstrap','java/lang/Class','getName','()Ljava/lang/String;'),
             ('bootstrap','java/lang/Class','getComponentType','()Ljava/lang/Class;')]
    closure=m.prepare(batch,plan,output,roots,methods)
    closure['exports'].append('boom_java_string_literal_root_count')
    (output/'closure.json').write_text(json.dumps(closure,indent=2)+'\n',encoding='utf-8')
    s=json.loads((batch/'summary.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(s['class_bootstrap']['index']['path']) as z:
        natives=[json.loads(l) for l in z.read('methods.jsonl').splitlines()]
        primitives=[json.loads(l) for l in z.read('primitives.jsonl').splitlines()]
    with zipfile.ZipFile(s['class_literals']['index']['path']) as z:
        core=[json.loads(l) for l in z.read('methods.jsonl').splitlines()]
    classes=[json.loads(l) for l in (plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()]
    cls=next(c for c in classes if c['name']=='java/lang/Class' and c['origin']['loader']=='bootstrap')
    field=lambda c,n:next(i for i,f in enumerate(c['fields']) if f['name']==n)
    cases=[]
    for n,t in WRAPPERS:
        c=next(c for c in classes if c['name']=='java/lang/'+n and c['origin']['loader']=='bootstrap')
        cases.append(dict(name=t,class_id=c['id'],type_field=field(c,'TYPE')))
    selected=closure['requested_method_roots']
    result=dict(class_id=cls['id'],natives=natives,core_natives=core,primitives=primitives,wrappers=cases,
        empty_class_field=field(cls,'EMPTY_CLASS_ARRAY'),serial_fields_field=field(cls,'serialPersistentFields'),
        getName=next(m['symbol'] for m in selected if m['name']=='getName'),
        getComponentType=next(m['symbol'] for m in selected if m['name']=='getComponentType'),
        source_initializers_are_original=True,fixture_only=False,full_Class_native_registration_complete=False,
        assertion_Java_wrapper_executed=False,String_class_initialization_executed=False,game_started=False)
    (output/'bootstrap-probe.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (output/'natives.tsv').write_text(''.join(f"{r['operation']}\tboom_m{r['method']}\n" for r in natives),encoding='ascii')
    (output/'core.tsv').write_text(''.join(f"{r['operation']}\tboom_m{r['method']}\n" for r in core),encoding='ascii')
    (output/'primitives.tsv').write_text(''.join(f"{r['name']}\t{r['type_id']}\n" for r in primitives),encoding='ascii')
    (output/'wrappers.tsv').write_text(''.join(f"{r['name']}\tboom_class{r['class_id']}\tboom_s{r['class_id']}_{r['type_field']}\n" for r in cases),encoding='ascii')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=prepare(a.batch,a.plan,a.output);print(json.dumps(dict(source_Class=r['class_id'],wrapper_initializers=len(r['wrappers']),fixture_only=False)))
