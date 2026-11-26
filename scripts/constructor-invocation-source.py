"""Source metadata and selected call sites for normal Constructor invocation."""
import importlib.util
import json
from pathlib import Path
import zipfile


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


C=module('invocation_original_constructors','constructor-provider-source.py')
R=module('invocation_original_native_methods','verify-batch-frames.py')
check=C.check
SPECS=(('jdk/internal/reflect/DirectConstructorHandleAccessor$NativeAccessor','newInstance0'),
       ('jdk/internal/reflect/NativeConstructorAccessorImpl','newInstance0'))
DESCRIPTOR='(Ljava/lang/reflect/Constructor;[Ljava/lang/Object;)Ljava/lang/Object;'
KERNELS=('constructor_widen.asm.inc','constructor_unbox.asm.inc','constructor_callsite.asm.inc','constructor_invoke.asm.inc')
HELPERS={'boom_constructor_widen','boom_constructor_unbox','boom_constructor_callsite'}


def contracts(summary,classes,S):
    names={(c['origin']['loader'],c['name']):c for c in classes};result=[]
    for owner,name in SPECS:
        c=names['bootstrap',owner]
        check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Invocation native requires original bootstrap declaration')
        actual,raw=R.original_methods(S.original_class(summary,c))
        check(actual==owner and len(raw)==len(c['method_ids']),'Invocation original native inventory differs')
        found=[(i,m) for i,m in zip(c['method_ids'],raw) if (m['name'],m['descriptor'])==(name,DESCRIPTOR)]
        check(len(found)==1 and found[0][1]['access']==0x10a and found[0][1]['code'] is None,'Invocation source native access/Code differs')
        result.append(dict(method=found[0][0],class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',owner=owner,
            source_id='jdk:java.base',name=name,descriptor=DESCRIPTOR,access=0x10a,operation=0))
    return result


def index(summary,classes):
    source_inputs=C.inputs(summary,classes)
    constructors=C.index(summary,classes,source_inputs);types,runtime,available,_=source_inputs
    bytype={t['id']:t for t in types};shapes={r['type_id']:r for r in runtime if r['kind']==0}
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    ids={r['method'] for r in constructors['records']};methods={}
    with zipfile.ZipFile(C.artifact(summary['frames']['index'])) as z:
        for line in z.open('methods.jsonl'):
            m=json.loads(line)
            if m['id'] in ids:methods[m['id']]=m
    with zipfile.ZipFile(C.artifact(summary['class_state']['index'])) as z:
        states={r['class_id']:r for line in z.open('classes.jsonl') if (r:=json.loads(line))}
    records=[]
    for r in constructors['records']:
        m=methods[r['method']];owner=r['owner'];c=classes[owner]
        check((m['class_id'],m['class_sha256'],m['name'],m['descriptor'])==(owner,r['source_sha256'],'<init>',r['descriptor']),
              'Constructor invocation target differs from original frame Code identity')
        valid=owner in shapes and not r['unavailable'] and states[owner]['diagnostic'] is None
        params=[]
        for type_id in r['parameters']:
            if type_id is None:params.append(dict(type_id=None,kind=None));continue
            t=bytype[type_id];kind='ZBCSIJFD'.index(t['name']) if t['kind']==0 and t['name'] in 'ZBCSIJFD' else 8
            params.append(dict(type_id=type_id,kind=kind))
        records.append(dict(owner=owner,slot=r['slot'],method=r['method'],modifiers=r['modifiers'],descriptor=r['descriptor'],
            source_sha256=r['source_sha256'],code_sha256=m['code_sha256'],target_emitted=m['assembly_emitted'],available=valid,
            parameters=params,noninstantiable=bool(c['access']&0x600 or owner==names['bootstrap','java/lang/Class'])))
    box_specs=list(zip(('Boolean','Byte','Character','Short','Integer','Long','Float','Double'),'ZBCSIJFD',(1,1,2,2,4,8,4,8)))
    box_ids={names['bootstrap','java/lang/'+name] for name,_,_ in box_specs};layouts={}
    with C.artifact(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            r=json.loads(line)
            if r['class_id'] in box_ids:layouts[r['class_id']]=r
    boxes=[]
    for kind,(name,desc,width) in enumerate(box_specs):
        id_=names['bootstrap','java/lang/'+name];layout=layouts[id_]
        check(id_ in shapes and layout['candidate'] is not None and layout['diagnostic'] is None,'Invocation boxing source layout unavailable')
        fields=[f for f in layout['candidate']['fields'] if (f['member']['owner'],f['member']['name'],f['member']['descriptor'])==(id_,'value',desc)]
        check(len(fields)==1 and fields[0]['storage_bytes']==width,'Invocation boxing source field differs')
        boxes.append(dict(class_id=id_,kind=kind,offset=fields[0]['offset'],width=width))
    return dict(schema=1,type_capacity=constructors['type_capacity'],records=records,boxes=boxes,
        constructor_class=constructors['constructor_class'],source_transform_chain='original_locked_no_transforms',
        exception_wrapping_complete=False,source_native_bindings_executed=False,game_started=False)


def data(m):
    imports={'boom_provider_constructor_pool','boom_java_class_pool','boom_heap_ptr','boom_runtime_type_map',
             'boom_provider_constructor_selected_sites'}|{f"boom_layout{b['class_id']}" for b in m['boxes']}
    parts=[f".const\nALIGN 8\nPUBLIC boom_provider_constructor_invoke_pool\nboom_provider_constructor_invoke_pool DWORD 04B56494Eh,1,{m['type_capacity']},{len(m['records'])}\n",
        ' QWORD OFFSET boom_provider_constructor_pool,OFFSET boom_java_class_pool,OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map\n',
        ' QWORD OFFSET provider_cinvoke_records,OFFSET boom_provider_constructor_selected_sites,OFFSET provider_cinvoke_boxes,OFFSET provider_cinvoke_call_pool\n QWORD 0,0\n',
        'ALIGN 8\nprovider_cinvoke_boxes DWORD 0564E4342h,1,8,24\n QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET provider_cinvoke_box_rows,0\nprovider_cinvoke_box_rows LABEL BYTE\n']
    parts.extend(f" DWORD {b['class_id']},{b['kind']}\n QWORD OFFSET boom_layout{b['class_id']}\n DWORD {b['offset']},{b['width']}\n" for b in m['boxes'])
    parts.append('ALIGN 8\nprovider_cinvoke_call_pool DWORD 056494350h,1\n QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET provider_cinvoke_boxes,0,0\nprovider_cinvoke_records LABEL BYTE\n')
    parts.extend(f" DWORD {r['owner']},{r['slot']},{r['method']},{r['modifiers']},{len(r['parameters'])},{int(r['available'])}\n QWORD 0\n" for r in m['records'])
    return ''.join(parts),imports


def selected_sites(m,selected_classes,selected_methods):
    """An unready site is a genuine class/method diagnostic callback, never a ctor."""
    classes=set(selected_classes);methods={int(i) for i in selected_methods};parts=[];pending_methods=set();pending_classes=set();ready=[]
    parts.append('.const\nALIGN 8\nPUBLIC boom_provider_constructor_selected_sites\nboom_provider_constructor_selected_sites LABEL QWORD\n')
    for i,r in enumerate(m['records']):
        if not r['available']:parts.append(' QWORD 0,0\n')
        elif r['owner'] not in classes:
            parts.append(f" QWORD 0,OFFSET boom_batch_initialize_{r['owner']}\n");pending_classes.add(r['owner'])
        elif r['method'] not in methods:
            parts.append(f" QWORD 0,OFFSET boom_m{r['method']}\n");pending_methods.add(r['method'])
        else:parts.append(f' QWORD OFFSET provider_cinvoke_site{i},0\n');ready.append(i)
    for i in ready:
        r=m['records'][i];owner=r['owner'];params=r['parameters']
        parts.append(f"ALIGN 8\nprovider_cinvoke_site{i} DWORD 0564E4943h,1,{owner},{len(params)},{int(r['noninstantiable'])},0\n QWORD OFFSET boom_layout{owner},OFFSET boom_class{owner},OFFSET boom_m{r['method']},{'OFFSET provider_cinvoke_params'+str(i) if params else '0'}\n DWORD {r['method']},0\n")
        if params:
            parts.append(f'provider_cinvoke_params{i} LABEL BYTE\n')
            parts.extend(f" DWORD {p['kind']},{p['type_id']}\n QWORD {('OFFSET boom_t'+str(p['type_id'])) if p['kind']==8 else '0'}\n" for p in params)
    return ''.join(parts),pending_methods,pending_classes,ready


def kernel_text(root):
    """Combine internal ASM helpers in one object without duplicate EXTERNs."""
    texts=[];imports=set()
    for name in KERNELS:
        text=(Path(root)/'native/providers'/name).read_text(encoding='utf-8')
        for line in text.splitlines(keepends=True):
            if line.startswith('EXTERN '):imports.add(line.split()[1].split(':')[0])
            else:texts.append(line)
        texts.append('\n')
    return ''.join(texts),imports-HELPERS
