"""Select original System initialization with the generated native family."""
import argparse
import importlib.util
import json
from pathlib import Path

def prepare(batch,plan,output):
    batch,output=Path(batch),Path(output)
    summary=json.loads((batch/'summary.json').read_text(encoding='utf-8'))
    spec=importlib.util.spec_from_file_location('source_init_selector',Path(__file__).with_name('prepare-class-init-probe.py'))
    selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
    methods=[('bootstrap','java/lang/System',name,desc) for name,desc in
             [('currentTimeMillis','()J'),('nanoTime','()J'),('arraycopy','(Ljava/lang/Object;ILjava/lang/Object;II)V')]]
    if summary['schema']>=9:methods.extend(('bootstrap','java/lang/System',name,desc) for name,desc in
        [('setIn0','(Ljava/io/InputStream;)V'),('setOut0','(Ljava/io/PrintStream;)V'),('setErr0','(Ljava/io/PrintStream;)V')])
    closure=selector.prepare(batch,plan,output,[('bootstrap','java/lang/System')],methods)
    arrays=list(map(json.loads,Path(summary['array_types']['path']).read_text(encoding='utf-8').splitlines()))
    (output/'arrays.tsv').write_text(''.join(f"{a['descriptor']}\t{a['id']}\n" for a in arrays if a['defining_loader']=='bootstrap'),encoding='utf-8')
    system=summary['system_natives']['class_id']
    source=json.loads((Path(plan)/'summary.json').read_text(encoding='utf-8'))
    classes=list(map(json.loads,(Path(plan)/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    object_id=next(c['id'] for c in classes if (c['origin']['loader'],c['name'])==('bootstrap','java/lang/Object'))
    closure['system_class']=system;closure['object_class']=object_id
    (output/'closure.json').write_text(json.dumps(closure,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(source_classes=len(closure['selected_classes']),source_Java_methods=len(closure['selected_methods']),
                         source_native_methods=len(closure['selected_native_methods']))))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch',type=Path);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.batch,args.plan,args.output)
