"""Source projection and MASM emitters for the original field MemberName ABI.

``index(summary, classes, selection, frame, layouts)`` accepts explicit original
input models. ``render(metadata, lookup_payload)`` emits five source units and
does not assemble, register a provider, verify a VM, or execute Java. All numeric
Java identities, packed offsets and callbacks come from those original inputs.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ABI_FILE=ROOT/'native-config/method-handle-field-abi.json'
FRAGMENTS={
    'registration':ROOT/'native/providers/method_handle_bindings.asm.inc',
    'field':ROOT/'native/providers/method_handle_field_resolve.asm.inc',
    'lookup':ROOT/'native/providers/source_field_lookup.asm.inc'}
POOL='boom_mhn_bindings_pool'
SERVICE='boom_mhn_bindings_service'


def check(value,message):
    if not value:raise ValueError(message)


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=sha))


def checked(record):
    actual=artifact(record['path']);check(all(actual['digest'][k]==record['digest'][k] for k in ('size','sha256')),'Original source input changed: '+record['path'])
    if 'sha1' in record['digest']:
        with Path(actual['path']).open('rb') as stream:check(hashlib.file_digest(stream,'sha1').hexdigest()==record['digest']['sha1'],'Original source SHA1 changed')
    return Path(actual['path'])


def module(name):
    spec=importlib.util.spec_from_file_location('mhn_field_'+name.replace('-','_'),Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def units(text):return list(struct.unpack('<'+'H'*(len(text.encode('utf-16-le','surrogatepass'))//2),text.encode('utf-16-le','surrogatepass')))


def word_data(label,text):
    data=units(text)
    return label+' LABEL WORD\n'+''.join(' WORD '+','.join(map(str,data[i:i+16]))+'\n' for i in range(0,len(data),16))


def _class_attributes(data,C,CP):
    cp=CP.parse_class_pool(data);reader=C.RAW.Reader(data[10+len(cp['raw']):]);entries=cp['entries']
    def attrs():
        result={}
        for _ in range(reader.number(2)):
            entry=entries[reader.number(2)];check(entry[0]==1,'Original attribute UTF8 missing');result[entry[2]]=reader.take(reader.number(4))
        return result
    access=reader.number(2);reader.take(4);reader.take(2*reader.number(2))
    for _ in range(2):
        for _ in range(reader.number(2)):reader.take(6);attrs()
    result=attrs();reader.end();return access,result


def index(summary,classes,selection,frame,layouts):
    """Project an explicit original namespace, without current-epoch constants."""
    abi=json.loads(ABI_FILE.read_text(encoding='utf-8-sig'))
    C,I,CP=map(module,('constructor-provider-source','verify-translation-ir','normal-constant-pool-source'))
    check([c['id'] for c in classes]==list(range(len(classes))),'Original Class plan must be dense')
    native_specs=[abi['registrar']]+abi['native_table']
    callback_specs={
      'java/lang/String':[('toCharArray','()[C','toCharArray')],
      'java/lang/Long':[('valueOf','(J)Ljava/lang/Long;','Long_valueOf')],
      'java/lang/InternalError':[('<init>','(Ljava/lang/String;)V','InternalError_ctor')],
      'java/lang/IllegalArgumentException':[('<init>','(Ljava/lang/String;)V','IAE_ctor')],
      'java/lang/NoSuchFieldError':[('<init>','(Ljava/lang/String;)V','NSFE_ctor')]}
    wanted=set(callback_specs)|{r['owner'] for r in native_specs}|{'java/lang/invoke/MemberName','java/lang/Class','java/lang/Throwable','java/lang/Object'}
    owners={c['name']:c for c in classes if c['name'] in wanted and c['origin']['loader']=='bootstrap'}
    check(set(owners)==wanted,'Original java.base MHN/field callback classes missing')
    check(all(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated') for c in owners.values()),'Original locked java.base inputs required')
    selected_classes={c['class_id']:c for c in selection['selected_classes']}
    declarations={r['id']:r for r in frame['source']['original_native_declarations']}
    roles={};methods={};raw=C.RawClasses(summary)
    types,runtime,available,resolve=C.inputs(summary,classes)
    record=[0]*len(classes)
    try:
        for name,cls in owners.items():
            data=raw.read(cls);parsed=I.Source(data)
            check(parsed.name==name and parsed.access==cls['access'] and len(parsed.methods)==len(cls['method_ids']) and
                  hashlib.sha256(data).hexdigest()==cls['origin']['sha256'],'Original Class differs: '+name)
            check([{k:f[k] for k in ('name','descriptor','access')} for f in parsed.fields]==cls['fields'],
                  'Original Class field declarations differ: '+name)
            methods[name]={}
            for ident,method in zip(cls['method_ids'],parsed.methods):
                code=parsed.code(method)
                row=dict(method=ident,class_id=cls['id'],owner=name,name=method['name'],descriptor=method['descriptor'],access=method['access'],
                    source_sha256=cls['origin']['sha256'],code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None,symbol='boom_m'+str(ident))
                methods[name][method['name'],method['descriptor']]=row
            for mn,desc,role in callback_specs.get(name,[]):
                row=methods[name][mn,desc]
                check(row['code_sha256'] is not None and selection['selected_methods'].get(str(row['method']))==
                      {k:row[k] for k in ('class_id','name','descriptor','source_sha256','code_sha256')},'Original Java callback is not selected: '+role)
                roles[role]=row
            if name!='java/lang/invoke/MethodHandle':
                chosen=selected_classes.get(cls['id']);check(chosen and chosen['source_sha256']==cls['origin']['sha256'] and chosen['diagnostic'] is None,
                    'Normal source Class descriptor required: '+name)
        H=module('verify-batch-metadata');lookup,_,_,_=H.source_model(classes)
        record_type=next(c['id'] for c in classes if c['name']=='java/lang/Record' and c['origin']['loader']=='bootstrap')
        for cls in classes:
            if cls.get('superclass')!='java/lang/Record':continue
            data=raw.read(cls);access,attrs=_class_attributes(data,C,CP)
            check(access==cls['access'],'Original Record header changed')
            record[cls['id']]=int('Record' in attrs and bool(access&0x10) and lookup(cls['origin']['loader'],'java/lang/Record')==record_type)
    finally:raw.close()
    rows=[];registrar=None
    for spec in native_specs:
        original=dict(methods[spec['owner']][spec['name'],spec['descriptor']]);decl=declarations.get(original['method'])
        check(original['code_sha256'] is None and original['access']&0x100 and not original['access']&0x400 and decl and
              all(decl[k]==original[v] for k,v in (('id','method'),('class_id','class_id'),('name','name'),('descriptor','descriptor'),('access','access'),('class_sha256','source_sha256'))),
              'Original native declaration/Frame differs: '+spec['name'])
        flags=decl['flags'];check(flags==32 or (flags==96 and spec['owner']=='java/lang/invoke/MethodHandle' and
            spec['name'] in ('invoke','invokeExact') and 'Ljava/lang/invoke/MethodHandle$PolymorphicSignature;' in decl['annotations']),
            'Original normal native flags differ')
        original.update(operation=spec['operation'],frame_flags=flags)
        if spec['operation']==0:registrar=original
        else:original.update(handler=spec['handler'],support=int(spec['handler']!='boom_mhn_unsupported'));rows.append(original)
    check(registrar is not None and len(rows)==len(abi['native_table']) and len({r['method'] for r in rows})==len(rows),'Original native binding population differs')
    original_layouts={r['class_id']:r for r in layouts};wanted_ids={owners[n]['id'] for n in ('java/lang/invoke/MemberName','java/lang/Class','java/lang/String')}
    fields={};maps={}
    with zipfile.ZipFile(checked(summary['unsafe_fields']['index'])) as archive:
        for line in archive.open('fields.jsonl'):
            row=json.loads(line)
            if row['class_id'] in wanted_ids:fields[row['class_id'],row['field_index']]=row
    with zipfile.ZipFile(checked(summary['runtime_metadata']['index'])) as archive:
        for line in archive.open('fields.jsonl'):
            row=json.loads(line)
            if row['declaring_class'] in wanted_ids:maps[row['id']]=row
    projected={}
    for name in ('java/lang/invoke/MemberName','java/lang/Class','java/lang/String'):
        cls=owners[name];layout=original_layouts[cls['id']];items=[]
        for f in layout['candidate']['fields']:
            member=f['member'];u=fields[member['owner'],member['index']];address=maps.get(u['address_map'])
            if address is None:
                shape=summary['string_literals']['source_layout']
                check(name=='java/lang/String' and cls['id']==shape['class_id'],
                      'Missing FMAPPROC outside the explicit normal String module ownership')
                owned=[m for m in shape['field_maps'] if m['declaring_field']==member['index']]
                check(len(owned)==1 and owned[0]['symbol']=='boom_field_map'+str(u['address_map']),
                      'Original String literal-module field-map identity differs')
                address=dict(id=u['address_map'],rows=[dict(receiver_class=cls['id'],offset=owned[0]['offset'])])
            actual=[r for r in address['rows'] if r['receiver_class']==cls['id']]
            check(len(actual)==1 and actual[0]['offset']==f['offset'] and u['storage_bytes']==f['storage_bytes'] and
                  all(member[k]==u[k] for k in ('name','descriptor')),'Original packed layout/UFMP/FMAPPROC row differs')
            items.append(dict(name=member['name'],descriptor=member['descriptor'],offset=f['offset'],bytes=f['storage_bytes'],reference=u['reference'],
                              field_map='boom_field_map'+str(address['id']),UFMP_id=u['id']))
        projected[name]=dict(class_id=cls['id'],class_sha256=cls['origin']['sha256'],payload_bytes=layout['candidate']['payload_bytes'],
                             reference_prefix=layout['candidate']['reference_prefix'],fields=items)
    check(projected['java/lang/invoke/MemberName']['payload_bytes']==44 and projected['java/lang/invoke/MemberName']['reference_prefix']==5,
        'This native kernel requires the source MemberName 44-byte/five-ref ABI')
    descriptors=[dict(type_id=i,descriptor='',provided=False,name=None,loader=None) for i in range(max(t['id'] for t in types)+1)]
    for t in types:
        name=t['name'];descriptors[t['id']]=dict(type_id=t['id'],descriptor=name if name.startswith('[') or t['kind']==0 else 'L'+name+';',
            provided=True,name=name,loader=t['defining_loader'])
    field=dict(roles=roles,original_classes={n:dict(class_id=c['id'],origin=c['origin']) for n,c in owners.items()},layouts=projected,
        descriptors=descriptors,record_class_bits=record,original_class_count=len(classes),
        char_array_type=next(t['id'] for t in types if t['name']=='[C'),Object_array_type=next(t['id'] for t in types if t['name']=='[Ljava/lang/Object;'))
    payload,lookup_model=project_lookup(summary,classes,types,available,resolve)
    return dict(schema=1,registration=dict(rows=rows,registrar=registrar),field=field,lookup=lookup_model,
        lookup_payload_sha256=hashlib.sha256(payload).hexdigest(),additional_oop_roots=[],registered_pack=False,
        full_MethodHandle_support=False,machine_or_behavior_verified=False,original_Java_Code_changed=False),payload


def _imports(procedures,data):
    check(not procedures&data,'Conflicting native procedure/data declaration')
    return ''.join('EXTERN '+name+':'+('PROC' if name in procedures else 'BYTE')+'\n' for name in sorted(procedures|data))


def _binding_rows(meta):
    text=''
    for i,row in enumerate(meta['rows']):
        text+=f" DWORD {row['method']},{row['class_id']},{row['operation']},{row['support']}\n"
        text+=f" QWORD OFFSET boom_m{row['method']}_native,OFFSET {row['handler']},OFFSET boom_trace_method{row['method']}\n"
        text+=f" QWORD OFFSET mhr_name{i},OFFSET mhr_descriptor{i}\n DWORD {len(units(row['name']))},{len(units(row['descriptor']))}\n"
    return text


def registration_data(meta):
    count=len(meta['rows']);text=f'MHRG_NATIVE_COUNT EQU {count}\n.data?\nALIGN 8\nPUBLIC boom_mhn_bindings_cells\nboom_mhn_bindings_cells BYTE {count*24} DUP(?)\n'
    text+='.data\nALIGN 8\nPUBLIC boom_mhn_bindings_pool\nboom_mhn_bindings_pool DWORD 04752484Dh,1,128,0\n'
    text+=' QWORD 0,OFFSET boom_mhn_bindings_input_rows,OFFSET boom_mhn_bindings_expected_rows,OFFSET boom_mhn_bindings_cells\n'
    text+=f' DWORD {count},{count}\n QWORD OFFSET boom_trace_pool\n DWORD 3,64\n QWORD 0,0,0,0,0,0,0\n'
    text+='.const\nALIGN 8\nboom_mhn_bindings_input_rows LABEL BYTE\nboom_mhn_bindings_expected_rows LABEL BYTE\n'+_binding_rows(meta)
    for i,row in enumerate(meta['rows']):text+=word_data('mhr_name'+str(i),row['name'])+word_data('mhr_descriptor'+str(i),row['descriptor'])
    return text


def native_assembly(metadata):
    meta=metadata['registration'];methods=[meta['registrar']]+meta['rows'];R=module('verify-batch-frames')
    procedures={'boom_class_ensure32','boom_trace_enter','boom_trace_leave',SERVICE}
    data={POOL,'boom_trace_pool'}|{'boom_class'+str(m['class_id']) for m in methods}|{'boom_trace_method'+str(m['method']) for m in methods}
    text='option casemap:none\n'+_imports(procedures,data)
    for row in methods:text+=f"PUBLIC boom_m{row['method']}\nPUBLIC boom_m{row['method']}_native\n"+R.native_adapter(row['method'],row['class_id'],POOL,SERVICE,row['operation'])
    return text+'\nEND\n'


def registration_assembly(metadata):
    meta=metadata['registration'];procedures={'AcquireSRWLockExclusive','ReleaseSRWLockExclusive','AcquireSRWLockShared','ReleaseSRWLockShared'}
    procedures|={r['handler'] for r in meta['rows'] if r['support']}|{'boom_m'+str(r['method'])+'_native' for r in meta['rows']}
    data={'boom_trace_pool'}|{'boom_trace_method'+str(r['method']) for r in meta['rows']}
    return 'option casemap:none\n'+_imports(procedures,data)+registration_data(meta)+FRAGMENTS['registration'].read_text(encoding='utf-8')+'\nEND\n'


def field_assembly(metadata):
    meta=metadata['field'];roles=meta['roles'];classes=meta['original_classes'];cid=lambda name:classes[name]['class_id']
    procedures={'boom_heap_contains','boom_object_check','boom_runtime_row','boom_java_class_typeid','boom_java_class_load','boom_source_field_lookup',
        'boom_java_property_copy','boom_class_ensure32','boom_object_new','boom_exception_set32','boom_typed_multi_new'}|{r['symbol'] for r in roles.values()}
    data={'boom_heap_ptr','boom_runtime_type_map','boom_java_class_pool','boom_java_unsafe_field_pool','boom_source_field_lookup_index',
        'boom_java_platform_properties_pool','boom_t'+str(meta['Object_array_type']),
        'boom_t'+str(cid('java/lang/Throwable')),'boom_t'+str(cid('java/lang/invoke/MemberName')),'boom_t'+str(cid('java/lang/String')),
        'boom_layout'+str(cid('java/lang/invoke/MemberName')),'boom_layout'+str(cid('java/lang/String'))}
    for name in ('java/lang/InternalError','java/lang/IllegalArgumentException','java/lang/NoSuchFieldError'):data|={'boom_class'+str(cid(name)),'boom_layout'+str(cid(name))}
    fragment=FRAGMENTS['field'].read_text(encoding='utf-8');head,fragment=fragment.split('; MHFR256/1.',1)
    text='option casemap:none\n'+head+_imports(procedures,data)+'.const\nALIGN 8\nPUBLIC boom_mhn_field_pool\n'
    text+='boom_mhn_field_pool DWORD 05246484Dh,1,256,'+str(len(meta['descriptors']))+'\n'
    text+=' QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_java_class_pool,OFFSET boom_java_unsafe_field_pool\n QWORD OFFSET boom_source_field_lookup_index,OFFSET mhf_descriptors\n'
    text+=f" QWORD OFFSET boom_layout{cid('java/lang/invoke/MemberName')},OFFSET boom_t{cid('java/lang/invoke/MemberName')},OFFSET boom_layout{cid('java/lang/String')},OFFSET boom_t{cid('java/lang/String')}\n"
    text+=f" QWORD OFFSET {roles['toCharArray']['symbol']},OFFSET {roles['Long_valueOf']['symbol']},OFFSET boom_t{meta['Object_array_type']},OFFSET boom_t{cid('java/lang/Throwable')}\n"
    text+=' QWORD OFFSET mhf_exceptions,OFFSET boom_java_platform_properties_pool,OFFSET mhf_messages,OFFSET mhf_record_classes\n'
    text+=f" DWORD {meta['original_class_count']},0\n QWORD 0,0,0\n"
    fields={f['name']:f for f in meta['layouts']['java/lang/invoke/MemberName']['fields']}
    text+=' DWORD '+','.join(str(fields[n]['offset']) for n in ('clazz','name','type','method','resolution','flags'))+'\n'
    loader=next(f['offset'] for f in meta['layouts']['java/lang/Class']['fields'] if f['name']=='classLoader')
    text+=f" DWORD {loader},{meta['char_array_type']}\n QWORD 0,0,0,0\nALIGN 8\nmhf_exceptions LABEL QWORD\n"
    for name,role in [('java/lang/InternalError','InternalError_ctor'),('java/lang/IllegalArgumentException','IAE_ctor'),('java/lang/NoSuchFieldError','NSFE_ctor')]:
        text+=f" QWORD OFFSET boom_class{cid(name)},OFFSET boom_layout{cid(name)},OFFSET {roles[role]['symbol']}\n"
    messages=['mname is null','obsolete MemberName format','nothing to resolve','field resolution failed','non-static field required','static field required','mname not resolved']
    text+='ALIGN 8\nmhf_messages LABEL BYTE\n'
    for i,msg in enumerate(messages):text+=f' QWORD OFFSET mhf_message{i}\n DWORD {len(units(msg))},0\n'
    for i,msg in enumerate(messages):
        text+=word_data('mhf_message'+str(i),msg) if i!=6 else 'mhf_message6 WORD '+','.join(map(str,units(msg)))+'\n'
    text+='ALIGN 8\nmhf_record_classes LABEL BYTE\n'
    for i in range(0,len(meta['record_class_bits']),16):text+=' BYTE '+','.join(map(str,meta['record_class_bits'][i:i+16]))+'\n'
    strings={}
    for item in meta['descriptors']:strings.setdefault(item['descriptor'],len(strings))
    text+='ALIGN 8\nmhf_descriptors LABEL BYTE\n'
    for item in meta['descriptors']:
        status=int(item['provided'])|({'bootstrap':1,'platform':2,'app':3}.get(item['loader'],0)<<8)
        text+=f" QWORD OFFSET mhf_descriptor{strings[item['descriptor']]}\n DWORD {len(units(item['descriptor']))},{status}\n"
    for descriptor,ident in strings.items():text+=word_data('mhf_descriptor'+str(ident),descriptor)
    return text+'; MHFR256/1.'+fragment+'\nEND\n'


def render(metadata,lookup_payload):
    check(hashlib.sha256(lookup_payload).hexdigest()==metadata['lookup_payload_sha256'],'Ordered lookup payload differs from source projection')
    return {'mhn-bindings-native':native_assembly(metadata),'mhn-bindings-table':registration_assembly(metadata),
        'mhn-field-resolver':field_assembly(metadata),'source-field-lookup-code':FRAGMENTS['lookup'].read_text(encoding='utf-8'),
        'source-field-lookup-index':lookup_data_source(lookup_payload)}


def project(summary_file,classes_file,selection_file,frame_file,layouts_file,source_verification=None):
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
    summary,selection,frame=map(read,(summary_file,selection_file,frame_file))
    classes=[json.loads(line) for line in Path(classes_file).open(encoding='utf-8')]
    layouts=[json.loads(line) for line in Path(layouts_file).open(encoding='utf-8')]
    check(selection['source_batch_summary_sha256']==artifact(summary_file)['digest']['sha256'] and
          selection['source_classes_sha256']==artifact(classes_file)['digest']['sha256'] and
          Path(layouts_file).resolve()==checked(summary['layouts']),'Explicit original source/plan/layout identities differ')
    if source_verification is not None:
        proof=read(source_verification);check(proof['verified'] is True and proof['closure_manifest_sha256']==artifact(selection_file)['digest']['sha256'],
            'Explicit completed full SourceV does not bind the selected original source')
    model,payload=index(summary,classes,selection,frame,layouts)
    model['inputs']={k:artifact(p) for k,p in dict(batch_summary=summary_file,classes=classes_file,selection=selection_file,frame=frame_file,layouts=layouts_file,
        ABI=ABI_FILE,source_renderer=__file__,**FRAGMENTS).items()}
    model['source_manifest']=artifact(selection_file);model['source_full_verification']=artifact(source_verification) if source_verification else None
    return model,payload


def main(args):
    output=args.output.resolve()
    check(any(output.is_relative_to(ROOT/name) for name in ('.boom','target','dist')),'Output must stay in project .boom, target or dist')
    check(not output.exists(),'Source output must be create-new')
    model,payload=project(args.batch_summary,args.classes,args.selection,args.frames,args.layouts,args.source_verification)
    sources=render(model,payload);output.mkdir(parents=True)
    with (output/'model.json').open('x',encoding='utf-8') as stream:json.dump(model,stream,indent=2);stream.write('\n')
    for role,text in sources.items():
        with (output/(role+'.asm')).open('x',encoding='utf-8',newline='\n') as stream:stream.write(text)


# The ordered field-index projection and inline readonly data writer follow.
# Their inputs are explicit source models, with no current-epoch coordinator.


def _lookup_require(condition, message):
    if not condition:
        raise ValueError(message)


def _lookup_artifact(record):
    path = Path(record['path'])
    expected = record.get('digest', record)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    _lookup_require(path.stat().st_size == expected['size'] and digest == expected['sha256'],
                    'Explicit source field index identity changed')
    return path


def _lookup_class_names(classes):
    # Preserve the existing original source loader/package resolution rules.
    # This produces identities only, never a sorted field-resolution ancestry.
    names = {(row['origin']['loader'], row['name']): row['id'] for row in classes}
    packages = {}
    for row in classes:
        if row['origin']['source_id'].startswith('jdk:'):
            package = row['name'].rpartition('/')[0]
            loader = row['origin']['loader']
            _lookup_require(package not in packages or packages[package] == loader,
                            'Conflicting original source system package')
            packages[package] = loader
    def lookup(loader, name):
        package = name.rpartition('/')[0]
        if package in packages:
            return names.get((packages[package], name))
        order = ['bootstrap']
        if loader != 'bootstrap':
            order.append('platform')
        if loader not in order:
            order.append(loader)
        return next((names[(key, name)] for key in order if (key, name) in names), None)
    return lookup


def project_lookup(summary, classes, types, available, resolve):
    """Return FLUP80 bytes and structural metadata, with no ambient inputs.

    classes are the dense original raw-Class plan; types/available/resolve are
    the caller's existing source-loader context. The immutable original field
    catalogue is independent of any subsequently appended generated namespace.
    Caller-loader constraints and access checks are not performed by this index.
    """
    _lookup_require([row['id'] for row in classes] == list(range(len(classes))),
                    'Original source class IDs are not dense')
    _lookup_require({row['id'] for row in types} == set(available),
                    'Source type rows and available identities differ')
    lookup = _lookup_class_names(classes)
    fields=[]
    with zipfile.ZipFile(_lookup_artifact(summary['unsafe_fields']['index'])) as archive:
        for line in archive.open('fields.jsonl'):fields.append(json.loads(line))
    _lookup_require([f['id'] for f in fields]==list(range(len(fields))),'Original UFMP IDs changed')
    declared=[[] for _ in classes]
    for field in fields:
        cls=classes[field['class_id']];raw=cls['fields'][field['field_index']]
        _lookup_require(all(raw[k]==field[k] for k in ('name','descriptor','access')) and cls['origin']['sha256']==field['class_sha256'],
              'Original UFMP field is not its exact Class declaration')
        declared[cls['id']].append(field)
    status=[int(c['id'] in available and not c.get('parse_error') and not c['access']&0x8000) for c in classes]
    parents=[];interfaces=[]
    for cls in classes:
        loader=cls['origin']['loader']
        parent=lookup(loader,cls['superclass']) if cls['superclass'] else None
        parents.append(parent if parent is not None else 0xffffffff)
        interfaces.append([lookup(loader,name) for name in cls['interfaces']])
    # Preserve source first-visit resolution order. Sorting the ancestor set is
    # forbidden; dedup first visits cannot hide a later match of the same query.
    orders=[];maximum=0
    for cls in classes:
        order=[];seen=set();active=set()
        def visit(ident):
            if ident is None:order.append(0xffffffff);return
            _lookup_require(ident not in active,'Cycle in provided source field hierarchy')
            if ident in seen:return
            seen.add(ident);order.append(ident)
            if not status[ident]:return
            active.add(ident)
            for iface in interfaces[ident]:visit(iface)
            if parents[ident]!=0xffffffff:visit(parents[ident])
            elif classes[ident]['superclass']:order.append(0xffffffff)
            active.remove(ident)
        visit(cls['id']);orders.append(order);maximum=max(maximum,len(order))
    strings=bytearray();interned={}
    def intern(text):
        raw=text.encode('utf-16-le','surrogatepass')
        if raw not in interned:interned[raw]=len(strings)//2;strings.extend(raw)
        return interned[raw],len(raw)//2
    classrows=[];fieldrows=[];ifaces=[];search=[]
    for cls in classes:
        ident=cls['id'];first=len(fieldrows)
        _lookup_require([(f['field_index']) for f in declared[ident]]==sorted(f['field_index'] for f in declared[ident]),'Original declared field order changed')
        for f in declared[ident]:
            no,nl=intern(f['name']);do,dl=intern(f['descriptor']);tid=resolve(cls['origin']['loader'],f['descriptor'])
            fieldrows.append((no,nl,do,dl,f['id'],f['field_index'],f['access'],0xffffffff if tid is None else tid,f['storage_bytes'],f['kind']))
        firstiface=len(ifaces);ifaces.extend(0xffffffff if i is None else i for i in interfaces[ident])
        firstsearch=len(search);search.extend(orders[ident])
        classrows.append((first,len(declared[ident]),firstiface,len(interfaces[ident]),parents[ident],firstsearch,len(orders[ident]),status[ident]))
    chunks=[b''.join(struct.pack('<8I',*r) for r in classrows),b''.join(struct.pack('<10I',*r) for r in fieldrows),
            b''.join(struct.pack('<I',v) for v in ifaces),b''.join(struct.pack('<I',v) for v in search),bytes(strings)]
    offsets=[];cursor=80;payload=bytearray(80)
    for raw in chunks:
        padding=(-cursor)%8;payload.extend(bytes(padding));cursor+=padding;offsets.append(cursor);payload.extend(raw);cursor+=len(raw)
    _lookup_require(cursor<0x40000000,'Readonly source lookup exceeds supported image size')
    header=(0x50554c46,1,cursor,len(classes),len(fields),len(ifaces),len(search),len(strings)//2,*offsets,32,40,0)
    _lookup_require(len(header)==16,'FLUP80 header shape differs')
    struct.pack_into('<16I',payload,0,*header)
    model=dict(schema=1,runtime_metadata=summary['runtime_metadata']['index'],UFMP=summary['unsafe_fields']['index'],
        class_count=len(classes),field_count=len(fields),direct_interface_count=len(ifaces),search_holder_count=len(search),UTF16_units=len(strings)//2,
        maximum_holders_per_query=maximum,total_bytes=cursor,offsets=dict(zip(('classes','fields','interfaces','search','UTF16'),offsets)),
        ordered_interfaces_original=True,no_TypeDesc_ancestor_sort=True,first_visit_dedup_equivalent_for_immutable_first_match=True,
        unsupported_class_count=status.count(0),no_global_RTYP_or_JCLS_capacity_eq_guard=True,
        per_chunk_sha256=[hashlib.sha256(c).hexdigest() for c in chunks],payload_sha256=hashlib.sha256(payload).hexdigest(),
        scope='original declared Class/UFMP prefix; generated/array classes outside original catalogue explicitly unsupported',
        lookup_only_text_descriptor_not_caller_loader_constraints=True,Java_state_or_heap_modified=False)
    return bytes(payload),model


def data_source(payload):
    lines=['option casemap:none','.const','ALIGN 16','PUBLIC boom_source_field_lookup_index','boom_source_field_lookup_index LABEL BYTE']
    n=len(payload)//4
    for offset in range(0,n,16):
        values=struct.unpack_from('<'+'I'*min(16,n-offset),payload,offset*4);lines.append(' DWORD '+','.join(map(str,values)))
    if len(payload)%4:_lookup_require(len(payload)%4==2,'Odd UTF16 metadata size');lines.append(' WORD '+str(int.from_bytes(payload[-2:],'little')))
    lines.append('END');return '\n'.join(lines)+'\n'


# Name expected by the consolidated source helper.
lookup_data_source = data_source


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('batch-summary','classes','selection','frames','layouts'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source-verification',type=Path);parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
