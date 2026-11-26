"""Source System setters plus original input constructor/read methods.

Input instance Java methods are selected directly. Its assertion-dependent class
initializer is deliberately outside this unit test and remains a boot dependency.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import zipfile

def prepare(batch,plan,output):
    batch,plan,output=Path(batch),Path(plan),Path(output)
    summary=json.loads((batch/'summary.json').read_text(encoding='utf-8'));assert summary['schema']>=9
    spec=importlib.util.spec_from_file_location('source_stream_selector',Path(__file__).with_name('prepare-class-init-probe.py'))
    selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
    methods=[('bootstrap','java/lang/System',name,desc) for name,desc in [('setIn0','(Ljava/io/InputStream;)V'),('setOut0','(Ljava/io/PrintStream;)V'),('setErr0','(Ljava/io/PrintStream;)V')]]
    methods.extend(('bootstrap','java/io/ByteArrayInputStream',name,desc) for name,desc in [('<init>','([B)V'),('read','()I'),('available','()I'),('reset','()V')])
    closure=selector.prepare(batch,plan,output,[('bootstrap','java/lang/System')],methods)
    classes=list(map(json.loads,(plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as bundle:
        types=list(map(json.loads,bundle.read('types.jsonl').splitlines()))
        runtime={r['type_id']:r for r in map(json.loads,bundle.read('runtime.jsonl').splitlines())}
    receiver_rows=[]
    for t in types:
        id_=t['id']
        if t['kind']!=1 or id_ not in runtime or classes[id_]['access']&0x600:continue
        mask=sum(1<<slot['operation'] for slot in summary['system_natives']['stream_slots'] if slot['type_id']==id_ or slot['type_id'] in t['ancestors'])
        if mask:receiver_rows.append((id_,mask))
    (output/'receivers.tsv').write_text(''.join(f'{id_}\t{mask}\n' for id_,mask in receiver_rows),encoding='ascii')
    arrays=list(map(json.loads,Path(summary['array_types']['path']).read_text(encoding='utf-8').splitlines()))
    byte_array=next(a['id'] for a in arrays if (a['defining_loader'],a['descriptor'])==('bootstrap','[B'))
    closure.update(system_class=summary['system_natives']['class_id'],stream_slots=summary['system_natives']['stream_slots'],byte_array=byte_array,
        input_class=names['bootstrap','java/io/ByteArrayInputStream'],print_class=names['bootstrap','java/io/PrintStream'],object_class=names['bootstrap','java/lang/Object'],
        receiver_shapes=len(receiver_rows),input_class_initialization_executed=False)
    (output/'closure.json').write_text(json.dumps(closure,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(source_methods=len(closure['selected_methods']),receiver_shapes=len(receiver_rows))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch',type=Path);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.batch,args.plan,args.output)
