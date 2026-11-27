"""Normal original Unsafe(Field) source projection and MASM renderers.

Explicit original summary, class plan, Java selection, normal Frame and packed
layouts are required. This unregistered provider returns UFMP cookies and does
not implement static Unsafe memory. Running this tool emits source only.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

POOL='boom_unsafe_reflected_field_pool'
SERVICE='boom_unsafe_reflected_field_service'
KERNEL='unsafe_reflected_fields.asm.inc'
OWNER='jdk/internal/misc/Unsafe'
FIELD='java/lang/reflect/Field'
IAE='java/lang/IllegalArgumentException'
THROWABLE='java/lang/Throwable'
OPERATIONS={('objectFieldOffset0','(Ljava/lang/reflect/Field;)J'):0,
    ('staticFieldOffset0','(Ljava/lang/reflect/Field;)J'):1,
    ('staticFieldBase0','(Ljava/lang/reflect/Field;)Ljava/lang/Object;'):2}


def check(condition,message):
    if not condition:raise ValueError(message)


def project_root(value=None):
    return Path(value).resolve() if value is not None else installed_root()


def installed_root():
    # Tracked tool/kernel markers support an ignored source-package review
    # copy as well as the installed scripts location. No CLI root override.
    for path in Path(__file__).resolve().parents:
        if (path/'scripts/constructor-provider-source.py').is_file() and (path/'native/runtime/java_unsafe_fields.asm').is_file():
            return path
    raise ValueError('Installed project tool and runtime source root not found')


def module(name,root=None):
    path=project_root(root)/'scripts'/(name+'.py')
    spec=importlib.util.spec_from_file_location('unsafe_reflected_'+name.replace('-','_'),path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=sha))


def metadata(summary,classes,selection,frame,layouts,root=None):
    """Read original native declarations/normal Field offsets, never Java state.

    All inputs are decoded JSON values. layouts may be an iterable of original
    packed layout rows. The original catalogue/class readers verify raw bytes
    against the supplied summary and plan; no execution or source admission is
    performed. Native capacities are validated dynamically by the MASM service.
    """
    C,I=module('constructor-provider-source',root),module('verify-translation-ir',root)
    check(selection['source_input_fingerprint']==summary['input_fingerprint'] and
        selection['source_frame_abi']==summary['frames']['abi']==frame['pool_abi']==3 and
        frame['method_row_bytes']==32,'Selected source and original Frame ABI/batch identity differ')
    for key in ('size','sha256'):
        check(frame['source']['base_frame_index']['digest'][key]==summary['frames']['index']['digest'][key],
            'Original normal Frame index differs from source batch')
    classes=list(classes);names={(c['origin']['loader'],c['name']):c for c in classes}
    check(len(names)==len(classes),'Duplicate original Class identity')
    owners={name:names['bootstrap',name] for name in (OWNER,FIELD,IAE,THROWABLE)}
    identities={c['id'] for c in owners.values()};layout_rows={r['class_id']:r for r in layouts if r['class_id'] in identities}
    check(identities<=set(layout_rows),'Required original normal packed layouts missing')
    selected={r['class_id']:r for r in selection['selected_classes']}
    for name in (OWNER,FIELD,IAE):
        cls=owners[name];check(cls['id'] in selected and selected[cls['id']]['diagnostic'] is None,
            'Required original Class descriptor is not selected normally: '+name)
        check(layout_rows[cls['id']]['diagnostic'] is None and layout_rows[cls['id']]['candidate'],
            'Required original normal object layout missing: '+name)
    raw=C.RawClasses(summary);methods=[];declarations=[];constructor=None
    try:
        for name in (OWNER,FIELD,IAE,THROWABLE):
            cls=owners[name];data=raw.read(cls);parsed=I.Source(data)
            check(parsed.name==name and len(parsed.methods)==len(cls['method_ids']),'Original native/callback Class identity differs')
            check([{key:field[key] for key in ('name','descriptor','access')} for field in parsed.fields]==cls['fields'],
                'Whole raw original Class field declarations or their class-local slots differ: '+name)
            for mid,member in zip(cls['method_ids'],parsed.methods):
                signature=(member['name'],member['descriptor']);code=parsed.code(member)
                if name==OWNER and signature in OPERATIONS:
                    check(member['access']==0x102 and code is None,'Original private instance native must retain CodeNone')
                    matches=[r for r in frame['source']['original_native_declarations'] if r['id']==mid]
                    check(len(matches)==1,'Original normal native Frame missing')
                    decl=matches[0]
                    check(decl['flags']==32 and all(decl[k]==v for k,v in
                        [('class_id',cls['id']),('class_sha256',cls['origin']['sha256']),('name',member['name']),
                         ('descriptor',member['descriptor']),('access',member['access'])]),'Original native Frame32 differs')
                    declarations.append(decl)
                    methods.append(dict(method=mid,class_id=cls['id'],owner=name,name=member['name'],descriptor=member['descriptor'],
                        access=member['access'],class_sha256=cls['origin']['sha256'],operation=OPERATIONS[signature],code_sha256=None))
                if name==IAE and signature==('<init>','()V'):
                    check(code is not None,'Original IllegalArgumentException() Code missing')
                    row=dict(method=mid,class_id=cls['id'],owner=name,name=member['name'],descriptor=member['descriptor'],access=member['access'],
                        source_sha256=cls['origin']['sha256'],code_sha256=hashlib.sha256(code['bytes']).hexdigest(),code_hex=code['bytes'].hex(),
                        symbol='boom_m'+str(mid),selected=True)
                    check(selection['selected_methods'].get(str(mid))=={k:row[k] for k in
                        ('class_id','name','descriptor','source_sha256','code_sha256')},'Original selected Java error constructor differs')
                    check(selection['selected_function_sha256'].get('boom_m'+str(mid)+'_body'),
                        'Original Java error constructor must have a selected emitted normal body')
                    check(constructor is None,'Duplicate original error constructor');constructor=row
    finally:raw.close()
    check(len(methods)==3 and sorted(m['operation'] for m in methods)==[0,1,2] and constructor,'Three native operations and actual Java constructor required')
    field=owners[FIELD];field_layout=layout_rows[field['id']];wanted={'clazz':'Ljava/lang/Class;','slot':'I','modifiers':'I'}
    offsets={};ufmp_rows={}
    with zipfile.ZipFile(C.artifact(summary['unsafe_fields']['index'])) as archive:
        for line in archive.open('fields.jsonl'):
            row=json.loads(line)
            if row['class_id']==field['id']:ufmp_rows[row['field_index']]=row
    for name,descriptor in wanted.items():
        matches=[r for r in field_layout['candidate']['fields'] if r['member']['owner']==field['id'] and
            (r['member']['name'],r['member']['descriptor'])==(name,descriptor)]
        check(len(matches)==1,'Original packed Field member missing: '+name);row=matches[0]
        original=field['fields'][row['member']['index']];ufmp=ufmp_rows[row['member']['index']]
        check((original['name'],original['descriptor'])==(name,descriptor) and
            (ufmp['name'],ufmp['descriptor'],ufmp['class_sha256'])==(name,descriptor,field['origin']['sha256']),
            'Original normal Field declaration and UFMP row identity differ')
        check(row['storage_bytes']==(8 if name=='clazz' else 4) and row['reference']==(name=='clazz'),
            'Original normal Field storage kind differs')
        offsets[name]=row['offset']
    return dict(methods=methods,original_native_declarations=declarations,unsafe_class=owners[OWNER]['id'],field_class=field['id'],
        IAE_class=owners[IAE]['id'],Throwable_class=owners[THROWABLE]['id'],IAE_constructor=constructor,
        Field_layout=field_layout,IAE_layout=layout_rows[owners[IAE]['id']],clazz_offset=offsets['clazz'],slot_offset=offsets['slot'],
        modifiers_offset=offsets['modifiers'],source_native_operations=3,pool_bytes=128,pool_abi=1,dynamic_namespace_capacity=True,
        UFMP=summary['unsafe_fields']['index'],original_Java_Code_changed=False,additional_oop_roots=[],target_Class_initialized=False,
        unsupported_static_memory_consumer_retained=True,automatic_concurrent_GC=False,
        private_invalid_Field_or_slot_is_not_JDK_oracle_domain=True,registered_pack=False)


project=metadata


def pool_assembly(meta):
    text=' .const\nALIGN 8\nPUBLIC '+POOL+'\n'+POOL+' DWORD 05546524Fh,1,128,7\n'
    text+=f" QWORD OFFSET boom_java_unsafe_field_pool,OFFSET boom_layout{meta['field_class']},OFFSET boom_class{meta['IAE_class']},OFFSET boom_layout{meta['IAE_class']}\n"
    text+=f" QWORD OFFSET boom_m{meta['IAE_constructor']['method']},OFFSET boom_t{meta['Throwable_class']}\n"
    return text+f" DWORD {meta['clazz_offset']},{meta['slot_offset']},{meta['modifiers_offset']},{meta['field_class']}\n QWORD 0,0,0,0,0,0\n"


def native_assembly(meta,root=None):
    F=module('verify-batch-frames',root)
    procedures={'boom_class_ensure32','boom_trace_enter','boom_trace_leave',SERVICE}
    data={'boom_trace_pool',POOL,'boom_class'+str(meta['unsafe_class'])}|{'boom_trace_method'+str(m['method']) for m in meta['methods']}
    text='option casemap:none\n'+''.join('EXTERN '+n+':'+('PROC' if n in procedures else 'BYTE')+'\n' for n in sorted(procedures|data))
    for row in meta['methods']:
        text+=f"PUBLIC boom_m{row['method']}\nPUBLIC boom_m{row['method']}_native\n"
        text+=F.native_adapter(row['method'],row['class_id'],POOL,SERVICE,row['operation'])
    return text+'\nEND\n'


def service_assembly(meta,kernel=None,root=None):
    procedures={'boom_heap_contains','boom_object_check','boom_runtime_row','boom_java_class_typeid',
        'boom_class_ensure32','boom_object_new','boom_exception_set32','boom_m'+str(meta['IAE_constructor']['method'])}
    data={'boom_java_unsafe_field_pool','boom_layout'+str(meta['field_class']),'boom_layout'+str(meta['IAE_class']),
        'boom_class'+str(meta['IAE_class']),'boom_t'+str(meta['Throwable_class'])}
    text='option casemap:none\n'+''.join('EXTERN '+n+':'+('PROC' if n in procedures else 'BYTE')+'\n' for n in sorted(procedures|data))
    kernel=Path(kernel) if kernel is not None else project_root(root)/'native/providers'/KERNEL
    return text+pool_assembly(meta)+kernel.read_text(encoding='utf-8')+'\nEND\n'


def output_target(value):
    target=Path(value).resolve();root=installed_root()
    check(any(target.is_relative_to(root/name) for name in ('.boom','target','dist')),'Generated source output must be under project .boom, target, or dist')
    check(not target.exists(),'Generated source output must be create-new')
    return target


def json_file(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main(args):
    root=installed_root()
    # Reject an illegal output before reading any project source/model inputs.
    out=output_target(args.output)
    kernel=Path(__file__).resolve().parents[1]/'native/providers'/KERNEL
    summary=json_file(args.summary);selection=json_file(args.selection);frame=json_file(args.frame)
    check(artifact(args.summary)['digest']['sha256']==selection['source_batch_summary_sha256'] and
        artifact(args.classes)['digest']['sha256']==selection['source_classes_sha256'],
        'Explicit summary/class bytes differ from selected source')
    source_verification=json_file(args.full_verification)
    check(source_verification['verified'] is True and
        source_verification['closure_manifest_sha256']==artifact(args.selection)['digest']['sha256'],
        'Explicit full source verification must bind exact selected source bytes')
    classes=[json.loads(line) for line in Path(args.classes).open(encoding='utf-8')]
    layout_file=Path(args.layouts) if args.layouts is not None else Path(summary['layouts']['path'])
    check(all(artifact(layout_file)['digest'][key]==summary['layouts']['digest'][key] for key in ('size','sha256')),
        'Explicit packed layouts differ from source summary')
    layouts=[json.loads(line) for line in layout_file.open(encoding='utf-8')]
    meta=metadata(summary,classes,selection,frame,layouts,root)
    native=native_assembly(meta,root);service=service_assembly(meta,kernel,root)
    inputs=[artifact(path) for path in (Path(__file__),args.summary,args.classes,args.selection,args.full_verification,args.frame,layout_file,kernel)]
    inputs += [artifact(root/'scripts'/(name+'.py')) for name in ('constructor-provider-source','verify-translation-ir','verify-batch-frames','system-class-inputs')]
    out.mkdir(parents=True)
    for name,text in (('native.asm',native),('service.asm',service)):
        with (out/name).open('x',encoding='utf-8',newline='\n') as stream:stream.write(text)
    model=dict(schema=1,verified_source_projection_only=True,metadata=meta,methods=meta['methods'],original_native_declarations=meta['original_native_declarations'],
        inputs=inputs,native_assembly=artifact(out/'native.asm'),service_assembly=artifact(out/'service.asm'),
        original_Java_Code_changed=False,additional_oop_roots=[],registered_pack=False,runtime_accepted=False,
        Java_or_Main_or_JVM_or_SourceV_executed=False)
    with (out/'source.json').open('x',encoding='utf-8',newline='\n') as stream:json.dump(model,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(source_model=artifact(out/'source.json'),native_assembly=model['native_assembly'],service_assembly=model['service_assembly'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('summary','classes','selection','full-verification','frame'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--layouts',type=Path)
    parser.add_argument('--output',type=Path,required=True);main(parser.parse_args())
