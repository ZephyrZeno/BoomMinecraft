"""Explicit original Field metadata projection and normal MASM emitters.

index(summary, classes, selection, frame, layouts, abi=None) consumes original
input models. project(...) binds explicit input paths and an optional completed
Source verification. render(metadata, fragment=None) emits two source units;
these functions do not assemble, select new Java, run a VM or register a pack.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ABI_FILE=ROOT/'native-config/normal-fields-abi.json'
FRAGMENT=ROOT/'native/providers/normal_fields.asm.inc'
MODULES={}


def check(value,message):
    if not value:raise ValueError(message)


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=sha))


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def checked(record):
    actual=artifact(record['path']);expected=record.get('digest',record)
    check(all(actual['digest'][k]==expected[k] for k in ('size','sha256')),'Original input changed: '+record['path'])
    return Path(actual['path'])


def module(name):
    if name in MODULES:return MODULES[name]
    spec=importlib.util.spec_from_file_location('normal_field_'+name.replace('-','_'),ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);MODULES[name]=value;return value


def original_fields(data):
    C=module('constructor-provider-source');CP=module('normal-constant-pool-source');pool=CP.parse_class_pool(data)
    reader=C.RAW.Reader(data[10+len(pool['raw']):]);entries=pool['entries']
    def utf(i):check(entries[i][0]==1,'Original field UTF8 missing');return entries[i][2]
    def clazz(i):check(entries[i][0]==7,'Original class constant missing');return utf(entries[i][2])
    def attrs():
        result={}
        for _ in range(reader.number(2)):
            name=utf(reader.number(2));payload=reader.take(reader.number(4));check(name not in result,'Duplicate original attribute');result[name]=payload
        return result
    access=reader.number(2);name=clazz(reader.number(2));reader.number(2);reader.take(2*reader.number(2));fields=[]
    for slot in range(reader.number(2)):
        flags=reader.number(2);fieldname=utf(reader.number(2));descriptor=utf(reader.number(2));a=attrs();signature=None
        if 'Signature' in a:
            check(len(a['Signature'])==2,'Invalid original field Signature attribute');signature=utf(int.from_bytes(a['Signature'],'big'))
        fields.append(dict(slot=slot,name=fieldname,descriptor=descriptor,access=flags,signature=signature,
            annotations=a['RuntimeVisibleAnnotations'].hex() if 'RuntimeVisibleAnnotations' in a else None,
            type_annotations=a['RuntimeVisibleTypeAnnotations'].hex() if 'RuntimeVisibleTypeAnnotations' in a else None))
    for _ in range(reader.number(2)):reader.take(6);attrs()
    attributes=attrs();reader.end();return name,access,fields,attributes


def index(summary,classes,selection,frame,layouts,abi=None):
    """Recover the full original field catalogue, independently of Java selection."""
    abi=read(ABI_FILE) if abi is None else abi
    check(abi['schema']==1 and abi['pool_symbol']=='boom_normal_field_pool' and abi['service_symbol']=='boom_normal_field_service' and
          abi['pool']['bytes']==192 and abi['pool']['abi']==1 and int(abi['pool']['magic'],0)==0x4e464c44 and len(abi['constructor_argv'])==9,
          'Unsupported normal Field source/pool ABI')
    check([c['id'] for c in classes]==list(range(len(classes))),'Original Class plan must be dense')
    C,I=module('constructor-provider-source'),module('verify-translation-ir')
    types,runtime,available,resolve=C.inputs(summary,classes);raw=C.RawClasses(summary)
    names={(c['origin']['loader'],c['name']):c for c in classes};owners={n:names['bootstrap',n] for n in
        ('java/lang/Class','java/lang/reflect/Field','java/lang/String','java/lang/reflect/AccessibleObject','java/lang/Record')}
    field=owners['java/lang/reflect/Field'];native=None;ctor=None;records=[];ranges=[]
    selected={r['class_id']:r for r in selection['selected_classes']}
    with zipfile.ZipFile(C.artifact(summary['unsafe_fields']['index'])) as archive:ufmp=[json.loads(line) for line in archive.open('fields.jsonl')]
    ufmp_by_slot={(f['class_id'],f['field_index']):f for f in ufmp}
    check(len(ufmp_by_slot)==len(ufmp),'Duplicate source field slot')
    try:
        for cls in classes:
            first=len(records);status=1 if cls['id'] in available else 3
            if cls.get('parse_error') or cls['access']&0x8000 or cls['origin'].get('generated'):status=3
            else:
                blob=raw.read(cls);name,access,fields,attributes=original_fields(blob)
                check(name==cls['name'] and access==cls['access'] and len(fields)==len(cls['fields']) and
                      [{k:f[k] for k in ('name','descriptor','access')} for f in fields]==cls['fields'],
                      'Original Class field declarations differ '+cls['name'])
                record='Record' in attributes and bool(access&0x10) and cls['superclass']=='java/lang/Record'
                for row in fields:
                    u=ufmp_by_slot[cls['id'],row['slot']];type_id=resolve(cls['origin']['loader'],row['descriptor'])
                    check(all(row[k]==u[k] for k in ('name','descriptor','access')) and u['class_sha256']==cls['origin']['sha256'],'Original UFMP field identity differs')
                    records.append(dict(row,owner=cls['id'],source_sha256=cls['origin']['sha256'],loader=cls['origin']['loader'],
                        field_type=type_id,unavailable=type_id is None,modifiers=row['access']&0x50df,
                        trusted_final=bool(row['access']&0x10 and (row['access']&8 or record)),UFMP_field=u['id']))
            ranges.append(dict(type_id=cls['id'],first=first,count=len(records)-first,status=status))
        for name in ('java/lang/Class','java/lang/reflect/Field'):
            cls=owners[name];parsed=I.Source(raw.read(cls))
            for mid,m in zip(cls['method_ids'],parsed.methods):
                if name=='java/lang/Class' and (m['name'],m['descriptor'])==('getDeclaredFields0','(Z)[Ljava/lang/reflect/Field;'):
                    check(m['access']==0x102 and parsed.code(m) is None,'Original getDeclaredFields0 declaration differs')
                    native=dict(method=mid,class_id=cls['id'],owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],class_sha256=cls['origin']['sha256'],operation=0)
                if name=='java/lang/reflect/Field' and m['name']=='<init>' and m['descriptor']=='(Ljava/lang/Class;Ljava/lang/String;Ljava/lang/Class;IZILjava/lang/String;[B)V':
                    code=parsed.code(m);check(code is not None,'Original Field constructor missing')
                    ctor=dict(method=mid,class_id=cls['id'],owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],source_sha256=cls['origin']['sha256'],
                        code_sha256=hashlib.sha256(code['bytes']).hexdigest())
                    check(selection['selected_methods'].get(str(mid))=={k:ctor[k] for k in ('class_id','name','descriptor','source_sha256','code_sha256')},
                        'Original Field constructor must already be selected')
                    body=selection['selected_function_sha256'].get('boom_m'+str(mid)+'_body')
                    check(isinstance(body,str) and len(body)==64,'Original Field constructor backend body must already be provided')
    finally:raw.close()
    check(native and ctor,'Original native/Field constructor not resolved')
    decl=next(r for r in frame['source']['original_native_declarations'] if r['id']==native['method'])
    check(decl['flags']==32 and all(decl[k]==native[v] for k,v in [('class_id','class_id'),('class_sha256','class_sha256'),('name','name'),('descriptor','descriptor'),('access','access')]),'Original native Frame32 differs')
    for cls in (owners['java/lang/Class'],field,owners['java/lang/String']):check(selected[cls['id']]['diagnostic'] is None,'Normal selected reflection Class required')
    capacity=summary['runtime_metadata']['type_capacity']
    for tid in range(len(classes),capacity):ranges.append(dict(type_id=tid,first=len(records),count=0,status=1 if tid in available else 3))
    wanted_ids={c['id'] for c in owners.values()}
    layout_by_id={layout['class_id']:layout for layout in layouts if layout['class_id'] in wanted_ids}
    normal=layout_by_id[field['id']]['candidate'];check(normal and layout_by_id[field['id']]['diagnostic'] is None,'Normal Field layout required')
    string=owners['java/lang/String'];sfields=layout_by_id[string['id']]['candidate']['fields']
    def offset(name,desc):
        matches=[f for f in sfields if (f['member']['owner'],f['member']['name'],f['member']['descriptor'])==(string['id'],name,desc)]
        check(len(matches)==1,'Original normal String field missing');return matches[0]['offset']
    byname={(t['defining_loader'],t['name']):t for t in types};byruntime={r['type_id']:r for r in runtime}
    arrays={n:byruntime[byname['bootstrap',n]['id']] for n in ('[Ljava/lang/reflect/Field;','[B')}
    return dict(schema=1,methods=[native],constructor=ctor,owner=native['class_id'],field_class=field['id'],string_class=string['id'],
        type_capacity=capacity,original_class_count=len(classes),records=records,ranges=ranges,arrays=arrays,
        Field_layout=layout_by_id[field['id']],String_layout=layout_by_id[string['id']],
        string_value_offset=offset('value','[B'),string_coder_offset=offset('coder','B'),compact_strings=summary['string_literals']['compact_strings'],
        original_native_declaration=decl,pool_bytes=192,pool_abi=1,row_bytes=96,range_bytes=16,
        required_java_methods=[ctor['method']],required_classes=sorted(c['id'] for c in owners.values()),
        represented_Class_initialization=False,native_filterFields=False,Field_get_set_or_annotation_parser_implemented=False,
        additional_oop_roots=[],automatic_GC=False,registered_pack=False,original_Java_Code_changed=False)


def data(meta):
    field,string=meta['field_class'],meta['string_class'];arrays=meta['arrays']
    text=['.const\nALIGN 8\nPUBLIC boom_normal_field_pool\n',f"boom_normal_field_pool DWORD 04E464C44h,1,{meta['type_capacity']},{len(meta['records'])}\n",
        ' QWORD OFFSET boom_java_class_pool,OFFSET boom_heap_ptr,OFFSET normal_field_ranges,OFFSET normal_field_rows\n',
        f" QWORD OFFSET boom_layout{field},OFFSET {arrays['[Ljava/lang/reflect/Field;']['tag_symbol']},0,OFFSET boom_layout{string}\n",
        f" QWORD OFFSET boom_class{field},OFFSET boom_m{meta['constructor']['method']},OFFSET boom_java_string_intern_pool\n",
        f" DWORD {meta['string_value_offset']},{meta['string_coder_offset']}\n QWORD {arrays['[B']['primitive_tag']}\n",
        f" DWORD 96,16,9,{int(meta['compact_strings'])}\n QWORD 0,0,0,0,0,0,0\nALIGN 8\nnormal_field_ranges LABEL BYTE\n"]
    text.extend(f" DWORD {r['first']},{r['count']},{r['status']},0\n" for r in meta['ranges']);text+=['ALIGN 8\nnormal_field_rows LABEL BYTE\n'];payload=[]
    for i,r in enumerate(meta['records']):
        prefix='normal_field_'+str(i)+'_';sig=r['signature'].encode('utf-16-le','surrogatepass') if r['signature'] is not None else None
        name=r['name'].encode('utf-16-le','surrogatepass');ann=bytes.fromhex(r['annotations']) if r['annotations'] is not None else None
        typ=bytes.fromhex(r['type_annotations']) if r['type_annotations'] is not None else None
        ptr=lambda n,v:'OFFSET '+prefix+n if v is not None else '0'
        text.append(f" DWORD {r['owner']},{r['slot']},{r['modifiers']},{r['field_type'] if r['field_type'] is not None else 0xffffffff}\n")
        text.append(f" QWORD OFFSET {prefix}name\n DWORD {len(name)//2},{int(r['unavailable'])}\n")
        for key,value,unit in [('signature',sig,2),('annotations',ann,1),('type_annotations',typ,1)]:
            text.append(f" QWORD {ptr(key,value)}\n DWORD {len(value or b'')//unit},{int(value is not None)}\n")
        text.append(f" DWORD {int(r['trusted_final'])},{r['UFMP_field']}\n QWORD 0\n")
        for key,value in [('name',name),('signature',sig),('annotations',ann),('type_annotations',typ)]:
            if value is None:continue
            payload.append(prefix+key+' LABEL BYTE\n')
            for at in range(0,len(value),16):payload.append(' BYTE '+','.join(map(str,value[at:at+16]))+'\n')
            if not value:payload.append(' BYTE 0\n')
    return ''.join(text+payload)


def native_assembly(meta):
    decl=meta['methods'][0];F=module('verify-batch-frames')
    proc={'boom_class_ensure32','boom_trace_enter','boom_trace_leave','boom_normal_field_service'}
    dat={'boom_trace_pool','boom_normal_field_pool','boom_class'+str(decl['class_id']),'boom_trace_method'+str(decl['method'])}
    text='option casemap:none\n'+''.join('EXTERN '+n+':'+('PROC' if n in proc else 'BYTE')+'\n' for n in sorted(proc|dat))
    return text+f"PUBLIC boom_m{decl['method']}\nPUBLIC boom_m{decl['method']}_native\n"+F.native_adapter(decl['method'],decl['class_id'],'boom_normal_field_pool','boom_normal_field_service',0)+'\nEND\n'


def service_assembly(meta,fragment=None):
    proc={'boom_heap_alloc','boom_object_new','boom_java_class_load','boom_java_class_typeid','boom_class_ensure32','boom_java_string_intern',
          'boom_m'+str(meta['constructor']['method'])}
    dat={'boom_heap_ptr','boom_java_class_pool','boom_java_string_intern_pool','boom_layout'+str(meta['field_class']),
         'boom_layout'+str(meta['string_class']),'boom_class'+str(meta['field_class']),meta['arrays']['[Ljava/lang/reflect/Field;']['tag_symbol']}
    return 'option casemap:none\n'+''.join('EXTERN '+n+':'+('PROC' if n in proc else 'BYTE')+'\n' for n in sorted(proc|dat))+data(meta)+(FRAGMENT.read_text(encoding='utf-8') if fragment is None else fragment)+'\nEND\n'


def render(metadata,fragment=None):
    """Emit the existing normal native Frame and immutable metadata/service unit."""
    return {'normal-fields-native':native_assembly(metadata),'normal-fields-service':service_assembly(metadata,fragment)}


def project(summary_file,classes_file,selection_file,frame_file,layouts_file,source_verification=None):
    paths=[Path(p).resolve() for p in (summary_file,classes_file,selection_file,frame_file,layouts_file)]
    summary,selection,frame=map(read,(paths[0],paths[2],paths[3]))
    check(selection['source_batch_summary_sha256']==artifact(paths[0])['digest']['sha256'] and
          selection['source_classes_sha256']==artifact(paths[1])['digest']['sha256'] and paths[4]==checked(summary['layouts']),
          'Explicit original source/plan/layout identities differ')
    if source_verification is not None:
        proof=read(source_verification)
        check(proof['verified'] is True and proof['closure_manifest_sha256']==artifact(paths[2])['digest']['sha256'],
              'Completed Source verification does not bind the selected original source')
    classes=[json.loads(line) for line in paths[1].open(encoding='utf-8')]
    layouts=[json.loads(line) for line in paths[4].open(encoding='utf-8')]
    metadata=index(summary,classes,selection,frame,layouts)
    metadata['inputs']={k:artifact(p) for k,p in dict(summary=paths[0],classes=paths[1],selection=paths[2],frame=paths[3],layouts=paths[4],
        ABI=ABI_FILE,source_renderer=__file__,fragment=FRAGMENT).items()}
    metadata['source_manifest']=artifact(paths[2])
    metadata['source_full_verification']=artifact(source_verification) if source_verification is not None else None
    return metadata


def main(args):
    output=args.output.resolve()
    check(any(output.is_relative_to(ROOT/name) for name in ('.boom','target','dist')),'Output must stay in project .boom, target or dist')
    check(not output.exists(),'Source output must be create-new')
    metadata=project(args.summary,args.classes,args.selection,args.frame,args.layouts,args.source_verification)
    sources=render(metadata);output.mkdir(parents=True)
    with (output/'metadata.json').open('x',encoding='utf-8',newline='\n') as stream:json.dump(metadata,stream,indent=2);stream.write('\n')
    for role,text in sources.items():
        with (output/(role+'.asm')).open('x',encoding='utf-8',newline='\n') as stream:stream.write(text)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('summary','classes','selection','frame','layouts','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-verification',type=Path);main(p.parse_args())
