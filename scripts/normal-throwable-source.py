"""Normal Throwable receiver layouts for the assembly ABI3 backtrace service."""
import importlib.util
import json
from pathlib import Path
import zipfile


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('normal_throwable_source_io','runtime-provider-source.py')
R=module('normal_throwable_original_native','verify-batch-frames.py')
FIELDS=(('backtrace','Ljava/lang/Object;',0x82),('depth','I',0x82),('stackTrace','[Ljava/lang/StackTraceElement;',2))
KERNELS=['classes32.asm','objects.asm','types.asm','arrays.asm','heap.asm','frames.asm']


def contracts(summary,classes):
    owners=[c for c in classes if c['name']=='java/lang/Throwable' and c['origin']['loader']=='bootstrap']
    S.check(len(owners)==1,'Original Throwable source owner is ambiguous')
    c=owners[0]
    S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Throwable native requires original java.base')
    owner,methods=R.original_methods(S.original_class(summary,c))
    S.check(owner==c['name'] and len(methods)==len(c['method_ids']),'Throwable original method inventory differs')
    natives=[(i,m) for i,m in zip(c['method_ids'],methods) if (m['name'],m['descriptor'])==('fillInStackTrace','(I)Ljava/lang/Throwable;')]
    S.check(len(natives)==1 and natives[0][1]['access']==0x102 and natives[0][1]['code'] is None,'Original Throwable native declaration differs')
    return [dict(method=natives[0][0],class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',source_id='jdk:java.base',
        owner=owner,name='fillInStackTrace',descriptor='(I)Ljava/lang/Throwable;',access=0x102,operation=0)]


def receiver_rows(classes,types,runtime,layouts):
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    root=names['bootstrap','java/lang/Throwable'];source=classes[root]
    S.check(source['origin']['source_id']=='jdk:java.base' and not source['origin'].get('generated'),'Throwable root must be original java.base')
    root_fields={}
    for name,desc,access in FIELDS:
        matches=[(i,f) for i,f in enumerate(source['fields']) if (f['name'],f['descriptor'],f['access'])==(name,desc,access)]
        S.check(len(matches)==1,'Original Throwable field contract differs: '+name);root_fields[name]=(matches[0][0],desc,access)
    bytype={t['id']:t for t in types};bylayout={l['class_id']:l for l in layouts};memo={};busy=set()
    def throwable(id_,depth=0):
        if id_ in memo:return memo[id_]
        S.check(id_ not in busy and depth<128,'Invalid normal Throwable ancestry')
        t=bytype[id_];c=classes[id_]
        S.check(t['kind']==1 and not c['access']&0x200 and (t['name'],t['defining_loader'],t['source_sha256'])==
                (c['name'],c['origin']['loader'],c['origin']['sha256']),'Normal class identity differs from Throwable source plan')
        busy.add(id_)
        try:
            parent=t['parent_component']
            if parent is None:S.check(c['name']=='java/lang/Object' and not c['superclass'],'Normal class lacks its source parent')
            else:S.check(parent in bytype and bytype[parent]['kind']==1 and bytype[parent]['name']==c['superclass'],'Normal class parent differs from original declaration')
            value=id_==root or (parent is not None and throwable(parent,depth+1));memo[id_]=value
            S.check((root in t['ancestors'])==(value and id_!=root),'Normal Throwable ancestry table differs')
            return value
        finally:busy.remove(id_)
    rows=[]
    for shape in runtime:
        if shape['kind']!=0 or bytype[shape['type_id']]['kind']!=1 or not throwable(shape['type_id']):continue
        id_=shape['type_id'];layout=bylayout[id_];candidate=layout['candidate']
        S.check(candidate is not None and layout['diagnostic'] is None and shape['tag_symbol']==f'boom_layout{id_}' and
                (shape['payload_bytes'],shape['reference_prefix'])==(candidate['payload_bytes'],candidate['reference_prefix']),
                'Normal Throwable physical shape differs')
        offsets={}
        for name,(index,desc,access) in root_fields.items():
            matches=[f for f in candidate['fields'] if f['member']==dict(owner=root,index=index,name=name,descriptor=desc,access=access)]
            S.check(len(matches)==1,'Normal Throwable inherited field is missing: '+name)
            field=matches[0];width=4 if desc=='I' else 8;offset=field['offset'];reference=desc!='I'
            S.check(field['storage_bytes']==width and field['reference']==reference and offset%width==0 and
                    offset+width<=candidate['payload_bytes'] and (offset<8*candidate['reference_prefix'])==reference,
                    'Normal Throwable inherited field bounds differ')
            offsets[name]=offset
        S.check(offsets['backtrace']!=offsets['stackTrace'],'Normal Throwable reference fields overlap')
        rows.append(dict(class_id=id_,source_sha256=layout['source_sha256'],backtrace=offsets['backtrace'],depth=offsets['depth'],depth_width=4,stack_trace=offsets['stackTrace']))
    S.check(any(r['class_id']==root for r in rows),'Original Throwable receiver is unavailable')
    return root,sorted(rows,key=lambda r:r['class_id'])


def index(summary,classes):
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as z:
        types=[json.loads(l) for l in z.read('types.jsonl').splitlines()]
        runtime=[json.loads(l) for l in z.read('runtime.jsonl').splitlines()]
    layouts=[json.loads(l) for l in S.checked(summary['layouts']).read_text(encoding='utf-8').splitlines()]
    root,rows=receiver_rows(classes,types,runtime,layouts);native=contracts(summary,classes)[0]
    S.check(native['class_id']==root,'Throwable native and receiver root identities differ')
    return dict(schema=1,root=root,rows=rows,native=native,trace_pool_abi=3,max_backtrace_frames=128,
        Java_StackTraceElement_materialization=False,stack_roots=False,automatic_gc=False,game_started=False)


def data(meta):
    root=meta['root'];imports={'boom_trace_pool','boom_heap_ptr',f'boom_t{root}'}|{f"boom_layout{r['class_id']}" for r in meta['rows']}|{f"boom_t{r['class_id']}" for r in meta['rows']}
    parts=[f".const\nALIGN 8\nPUBLIC boom_normal_throwable_pool\nboom_normal_throwable_pool DWORD 05048544Eh,1,{len(meta['rows'])},0\n QWORD OFFSET normal_throwable_receivers,OFFSET boom_trace_pool,OFFSET boom_heap_ptr,OFFSET boom_t{root},0,0\nnormal_throwable_receivers LABEL BYTE\n"]
    for r in meta['rows']:
        parts.append(f" QWORD OFFSET boom_layout{r['class_id']}\n DWORD {r['backtrace']},{r['depth']},{r['depth_width']},{r['stack_trace']}\n QWORD 0,OFFSET boom_t{r['class_id']},0\n")
    return ''.join(parts),imports


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();_,summary,classes=S.base(a.batch,a.plan);meta=index(summary,classes);S.write(a.output,meta)
    print(json.dumps(dict(receiver_layouts=len(meta['rows']),source_native_binding_provided=False,game_started=False)))
