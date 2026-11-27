"""Original Class/CP projection and MASM emitters for reference-instance CAS.

``index(summary, classes, selection, diagnostic, layouts, frame, abi=None)``
accepts explicit original input models. It selects only eligible original
signature-polymorphic CP sites and already provided static Java implementations.
``render(metadata, fragment=None)`` returns two source units without compiling,
registering a provider, changing Java selection, or executing Java.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ABI_FILE=ROOT/'native-config/varhandle-reference-cas-abi.json'
FRAGMENT=ROOT/'native/providers/varhandle_reference_cas.asm.inc'

def check(ok,message):
    if not ok:raise ValueError(message)

def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=sha))

def checked(record):
    actual=artifact(record['path']);expected=record.get('digest',record)
    check(all(actual['digest'][k]==expected[k] for k in ('size','sha256')),'Original input changed: '+record['path'])
    return Path(actual['path'])

def module(name):
    spec=importlib.util.spec_from_file_location('reference_cas_'+name.replace('-','_'),ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def reference_parameters(descriptor):
    if not descriptor.startswith('(') or not descriptor.endswith(')Z'):return None
    text=descriptor[1:-2];items=re.findall(r'\[*(?:L[^;]+;|[ZBCSIJFD])',text)
    return items if ''.join(items)==text and len(items)==3 and all(x.startswith(('L','[')) for x in items) else None

def index(summary,classes,selection,diagnostic,layouts,frame,abi=None):
    """Project original declarations, eligible CP sites, Class identities and fields."""
    abi=json.loads(ABI_FILE.read_text(encoding='utf-8-sig')) if abi is None else abi
    check(abi['schema']==1 and abi['pool']==dict(magic='VRCB',abi=1,bytes=160,site_row_bytes=32,dispatch_row_bytes=64),
        'Unsupported source bridge ABI')
    C,I=map(module,('constructor-provider-source','verify-translation-ir'))
    check([c['id'] for c in classes]==list(range(len(classes))),'Original Class plan must be dense')
    types,_,_,resolve=C.inputs(summary,classes);kinds={r['id']:r['kind'] for r in types}
    lookup={c['name']:c for c in classes if c['origin']['loader']=='bootstrap'}
    selected_classes={c['class_id']:c for c in selection['selected_classes']};layout_by_id={r['class_id']:r for r in layouts}
    raw_reader=C.RawClasses(summary);raws={};method_tables={}
    def original(ident):
        if ident not in raws:
            cls=classes[ident];data=raw_reader.read(cls);raw=I.Source(data)
            check(hashlib.sha256(data).hexdigest()==cls['origin']['sha256'] and raw.name==cls['name'] and len(raw.methods)==len(cls['method_ids']),
                'Original Class or declaration order differs')
            check([{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==cls['fields'],'Original field declarations differ')
            raws[ident]=raw;method_tables[ident]={(m['name'],m['descriptor']):(mid,m) for mid,m in zip(cls['method_ids'],raw.methods)}
        return raws[ident]
    def provided(owner,name,desc):
        cls=lookup[owner];raw=original(cls['id']);mid,method=method_tables[cls['id']][name,desc];code=raw.code(method)
        expected=dict(class_id=cls['id'],name=name,descriptor=desc,code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None,source_sha256=cls['origin']['sha256'])
        body=selection['selected_function_sha256'].get('boom_m'+str(mid)+'_body')
        check(code is not None and selection['selected_methods'].get(str(mid))==expected and isinstance(body,str) and len(body)==64,
            'Original Java callback is not selected/provided: '+owner+'.'+name+desc)
        chosen=selected_classes.get(cls['id']);check(chosen and chosen['diagnostic'] is None and chosen['source_sha256']==cls['origin']['sha256'],
            'Original normal callback Class is not selected')
        return dict(method=mid,symbol='boom_m'+str(mid),owner=owner,access=method['access'],**expected,provided_backend_body_sha256=body)
    native_declarations={r['id']:r for r in frame['source']['original_native_declarations']}
    try:
        operations=[];families=[]
        for op in abi['operations']:
            check(op['id']==1 and op['opcode']==182 and op['coordinates']=='three_reference_arguments' and op['return_descriptor']=='Z',
                'This ABI activates only the verified reference CAS argument shape')
            cls=lookup[op['owner']];raw=original(cls['id']);mid,method=method_tables[cls['id']][op['name'],op['native_descriptor']]
            decl=native_declarations.get(mid)
            check(raw.code(method) is None and method['access']&0x180==0x180 and decl and decl['class_id']==cls['id'] and
                decl['name']==op['name'] and decl['descriptor']==op['native_descriptor'] and decl['access']==method['access'] and
                decl['class_sha256']==cls['origin']['sha256'] and decl['flags']&32,'Original signature-polymorphic declaration/Frame differs')
            operations.append(dict(**op,native_method=mid,original_native_declaration=decl))
            for spec in op['active_families']:
                target=provided(spec['owner'],spec['method'],spec['descriptor']);check(target['access']&8,'Family target must be an original static Java implementation')
                families.append(dict(operation=op['id'],spec=spec,target=target,layout=layout_by_id[target['class_id']]))
        sites=[]
        for row in diagnostic['rows']:
            binding=row.get('binding') or {};op=next((o for o in operations if binding.get('resolved_method')==o['native_method']),None)
            if not op or row['category']!=3 or row['kind']!='signature_polymorphic_native' or binding.get('implemented') or str(binding.get('caller_method')) not in selection['selected_methods']:continue
            parameters=reference_parameters(binding['descriptor'])
            if parameters is None:continue
            cid=binding['caller_class'];cls=classes[cid];raw=original(cid);cp=raw.member(binding['constant'])
            check(binding['opcode']==op['opcode'] and cp['owner']==op['owner'] and cp['name']==op['name'] and cp['descriptor']==binding['descriptor'] and
                row['source_sha256']==cls['origin']['sha256'],'Original signature CP binding differs')
            occurrences=[]
            for mid,method in zip(cls['method_ids'],raw.methods):
                selected=selection['selected_methods'].get(str(mid))
                if not selected:continue
                code=raw.code(method);check(code is not None and selected['code_sha256']==hashlib.sha256(code['bytes']).hexdigest() and
                    selected['class_id']==cid and selected['source_sha256']==cls['origin']['sha256'],'Selected original caller Code differs')
                for ins in I.stream(code['bytes']):
                    if ins['opcode']==op['opcode'] and ins['operand']['Constant']==binding['constant']:
                        body=selection['selected_function_sha256'].get('boom_m'+str(mid)+'_body')
                        check(isinstance(body,str) and len(body)==64,'Original caller backend body is not provided')
                        occurrences.append(dict(method=mid,pc=ins['pc'],code_sha256=selected['code_sha256'],provided_backend_body_sha256=body))
            check(any(r['method']==binding['caller_method'] for r in occurrences),'Diagnostic caller does not contain the original CP invocation')
            type_ids=[resolve(cls['origin']['loader'],d) for d in parameters]
            check(all(i is not None and kinds[i] in (1,2,3) for i in type_ids),'Original coordinate Class/array resolution failed')
            sites.append(dict(**binding,row=row['id'],index=len(sites),operation=op['id'],argument_descriptors=parameters,argument_type_ids=type_ids,
                original_CP_member=cp,original_Class_sha256=cls['origin']['sha256'],original_selected_occurrences=occurrences))
        check(sites and len({s['label'] for s in sites})==len(sites),'No eligible sites or duplicate original labels')
        wanted_owners={f['member']['owner'] for family in families for f in family['layout']['candidate']['fields']}
        fields={};maps={}
        with zipfile.ZipFile(checked(summary['unsafe_fields']['index'])) as z:
            for line in z.open('fields.jsonl'):
                row=json.loads(line)
                if row['class_id'] in wanted_owners:fields[row['class_id'],row['field_index']]=row
        with zipfile.ZipFile(checked(summary['runtime_metadata']['index'])) as z:
            for line in z.open('fields.jsonl'):
                row=json.loads(line)
                if row['declaring_class'] in wanted_owners:maps[row['id']]=row
        dispatch=[]
        for family in families:
            clsid=family['target']['class_id'];actual_fields={}
            for field in family['layout']['candidate']['fields']:
                member=field['member'];owner_raw=original(member['owner']);decl=owner_raw.fields[member['index']]
                check(all(decl[k]==member[k] for k in ('name','descriptor','access')),'Original packed field declaration differs')
                u=fields[member['owner'],member['index']];fmap=maps[u['address_map']];receiver,=[r for r in fmap['rows'] if r['receiver_class']==clsid]
                check(u['name']==member['name'] and u['descriptor']==member['descriptor'] and u['storage_bytes']==field['storage_bytes'] and
                    receiver['offset']==field['offset'],'Actual UFMP/FMAPPROC receiver layout differs')
                actual_fields[member['name']]=dict(field=field,UFMP=u,receiver=receiver,source_address_function='boom_field_map'+str(u['address_map']))
            spec=family['spec'];f={k:actual_fields[v] for k,v in spec['fields'].items()}
            check(f['exact']['field']['storage_bytes']==1 and f['exact']['field']['member']['descriptor']=='Z' and
                all(f[k]['field']['storage_bytes']==8 and f[k]['field']['member']['descriptor']=='Ljava/lang/Class;' for k in ('receiver_class','field_class')),
                'Active reference family fields do not match the shared dispatch ABI')
            dispatch.append(dict(operation=family['operation'],name='compareAndSet',runtime_class=clsid,target=family['target']['symbol'],
                layout='boom_layout'+str(clsid),exact_field_address=f['exact']['source_address_function'],receiver_class_field_address=f['receiver_class']['source_address_function'],
                field_class_field_address=f['field_class']['source_address_function'],original_Java_target=family['target'],source_fields=f))
        check(len(dispatch)==1,'Only the tested one-row active family is enabled by this source policy')
        w=abi['wrong_method_type'];wmt=provided(w['owner'],'<init>',w['constructor']);throwable=resolve('bootstrap','Ljava/lang/Throwable;')
        check(throwable is not None,'Original Throwable TYPE missing')
        u=abi['existing_unsafe'];uc=lookup[u['owner']];ur=original(uc['id']);uid,um=method_tables[uc['id']][u['method'],u['descriptor']]
        unsafe=selection['selected_Unsafe_memory_natives'].get(str(uid))
        check(ur.code(um) is None and unsafe and unsafe['class_id']==uc['id'] and unsafe['class_sha256']==uc['origin']['sha256'] and
            unsafe['name']==u['method'] and unsafe['descriptor']==u['descriptor'] and unsafe['operation']==u['packed_operation'],
            'Existing selected Unsafe reference CAS provider differs')
        d=dispatch[0];symbols=dict(heap_cell='boom_heap_ptr',runtime_map='boom_runtime_type_map',class_pool='boom_java_class_pool',
            WMT_class='boom_class'+str(wmt['class_id']),WMT_layout='boom_layout'+str(wmt['class_id']),WMT_ctor=wmt['symbol'],Throwable_type='boom_t'+str(throwable),
            target=d['target'],layout=d['layout'],exact_field_address=d['exact_field_address'],receiver_class_field_address=d['receiver_class_field_address'],field_class_field_address=d['field_class_field_address'])
        return dict(schema=1,ABI=abi,sites=sites,dispatch=dispatch,symbols=symbols,original_WMT_constructor=wmt,existing_Unsafe_native=unsafe,
            original_native_declarations=[o['original_native_declaration'] for o in operations],additional_oop_roots=[],registered_pack=False,
            original_Java_Code_or_Frame_rows_modified=False,all_MethodHandle_or_VarHandle_family_supported=False,Java_or_Main_executed=False)
    finally:raw_reader.close()

def render(metadata,fragment=None):
    """Emit ordinary Win64 tail sites and the immutable operation/family service."""
    symbols=metadata['symbols'];sites=metadata['sites'];dispatch=metadata['dispatch'][0]
    native=['; Verified original CP sites. Tail bridges add no Java frame.','option casemap:none',
        'EXTERN boom_varhandle_reference_cas:PROC','EXTERN boom_varhandle_reference_cas_pool:BYTE','EXTERN boom_varhandle_reference_cas_sites:BYTE']
    for row in sites:
        native+=['PUBLIC '+row['label'],'.code',row['label']+' PROC FRAME',' .endprolog',
            ' lea r8,boom_varhandle_reference_cas_pool',' lea r9,boom_varhandle_reference_cas_sites+'+str(row['index']*32),
            ' jmp boom_varhandle_reference_cas',row['label']+' ENDP']
    native+=['END','']
    imports={'boom_heap_contains':'PROC','boom_runtime_row':'PROC','boom_object_check':'PROC','boom_java_class_typeid':'PROC',
        'boom_class_ensure32':'PROC','boom_object_new':'PROC','boom_exception_set32':'PROC'}
    for name in symbols.values():imports[name]='PROC' if name in (dispatch['target'],dispatch['exact_field_address'],dispatch['receiver_class_field_address'],
        dispatch['field_class_field_address'],symbols['WMT_ctor']) else 'BYTE'
    source=['; Immutable Source model for one active operation/runtime-family row.','option casemap:none']
    source+=['EXTERN '+name+':'+kind for name,kind in sorted(imports.items())]
    source+=['PUBLIC boom_varhandle_reference_cas_pool','PUBLIC boom_varhandle_reference_cas_sites','PUBLIC boom_varhandle_reference_cas_dispatch',
        '.const','ALIGN 8','boom_varhandle_reference_cas_pool DWORD 042435256h,1,160,'+str(len(sites)),
        ' QWORD '+','.join(symbols[k] for k in ('heap_cell','runtime_map','class_pool')),
        ' QWORD boom_varhandle_reference_cas_sites,boom_varhandle_reference_cas_dispatch',' DWORD 1,32,64,0',
        ' QWORD '+','.join(symbols[k] for k in ('WMT_class','WMT_layout','WMT_ctor','Throwable_type')),
        ' QWORD 7 DUP(0)','ALIGN 8','boom_varhandle_reference_cas_sites LABEL BYTE']
    for row in sites:source+=[' DWORD '+','.join(str(n) for n in [row['caller_class'],row['constant'],row['opcode'],row['operation'],*row['argument_type_ids'],1])]
    source+=['ALIGN 8','boom_varhandle_reference_cas_dispatch DWORD 1,'+str(dispatch['runtime_class']),
        ' QWORD '+','.join(dispatch[k] for k in ('target','layout','exact_field_address','receiver_class_field_address','field_class_field_address')),
        ' DWORD 3,1,1,0',FRAGMENT.read_text(encoding='utf-8') if fragment is None else fragment,'END','']
    return dict(zip(('varhandle-reference-cas-sites','varhandle-reference-cas-service'),('\n'.join(native),'\n'.join(source))))

def project(summary_file,classes_file,selection_file,diagnostic_file,layouts_file,frame_file,source_verification=None,abi=None):
    paths=[Path(p).resolve() for p in (summary_file,classes_file,selection_file,diagnostic_file,layouts_file,frame_file)]
    summary,selection,diagnostic,frame=[json.loads(paths[i].read_text(encoding='utf-8-sig')) for i in (0,2,3,5)]
    check(selection['source_batch_summary_sha256']==artifact(paths[0])['digest']['sha256'] and
        selection['source_classes_sha256']==artifact(paths[1])['digest']['sha256'] and paths[4]==checked(summary['layouts']),
        'Explicit original source/plan/layout identities differ')
    classes=[json.loads(l) for l in paths[1].open(encoding='utf-8')];layouts=[json.loads(l) for l in paths[4].open(encoding='utf-8')]
    metadata=index(summary,classes,selection,diagnostic,layouts,frame,abi=abi)
    metadata.update(source_manifest=artifact(paths[2]),original_source_inputs=[artifact(p) for p in paths])
    if source_verification is not None:
        proof=Path(source_verification).resolve();value=json.loads(proof.read_text(encoding='utf-8-sig'))
        check(value['verified'] and value['closure_manifest_sha256']==artifact(paths[2])['digest']['sha256'],'Existing complete Source verification differs')
        metadata['source_full_verification']=artifact(proof)
    return metadata

def main(args):
    output=args.output.resolve()
    check(any(output.is_relative_to(ROOT/name) for name in ('.boom','target','dist')),'Output must stay in project .boom, target or dist')
    check(not output.exists(),'Fresh source-only output required')
    metadata=project(args.summary,args.classes,args.selection,args.diagnostic,args.layouts,args.frame,args.source_verification)
    output.mkdir(parents=True)
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    for role,text in render(metadata).items():(output/(role+'.asm')).write_text(text,encoding='utf-8',newline='\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('summary','classes','selection','diagnostic','layouts','frame','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-verification',type=Path);main(p.parse_args())
