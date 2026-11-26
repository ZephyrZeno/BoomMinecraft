"""Independently reconstruct source type/field plans and inspect MASM/COFF."""
from collections import defaultdict
import json
from pathlib import Path
import re
import zipfile


def check(value,message):
    if not value: raise ValueError(message)


def source_model(classes):
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    packages={}
    for c in classes:
        if c['origin']['source_id'].startswith('jdk:'):
            package=c['name'].rpartition('/')[0]
            loader=c['origin']['loader']
            check(package not in packages or packages[package]==loader,'Conflicting source system package')
            packages[package]=loader
    def lookup(loader,name):
        package=name.rpartition('/')[0]
        if package in packages: return names.get((packages[package],name))
        order=['bootstrap']
        if loader!='bootstrap': order.append('platform')
        if loader not in order: order.append(loader)
        return next((names[(key,name)] for key in order if (key,name) in names),None)
    ancestry,parents,busy={}, {},set()
    def ancestors(id_,depth=0):
        if id_ in ancestry: return ancestry[id_]
        if id_ in busy or depth>=128: raise ValueError('Incomplete source hierarchy')
        c=classes[id_]; flags=c['access']
        check(not c.get('parse_error') and not flags&0x8000,'Invalid source class')
        interface=bool(flags&0x200)
        check(not interface or flags&0x410==0x400,'Invalid source interface')
        busy.add(id_)
        try:
            parent=lookup(c['origin']['loader'],c['superclass']) if c['superclass'] else None
            is_object=(c['origin']['loader'],c['name'])==('bootstrap','java/lang/Object')
            check((not c['superclass'] and parent is None and not interface) if is_object else parent is not None,
                  'Missing source superclass')
            values={id_}
            if parent is not None:
                check(not classes[parent]['access']&0x210,'Invalid source superclass kind')
                check(not interface or (classes[parent]['origin']['loader'],classes[parent]['name'])==('bootstrap','java/lang/Object'),
                      'Invalid interface superclass')
                values.update(ancestors(parent,depth+1))
            seen=set()
            for name in c['interfaces']:
                target=lookup(c['origin']['loader'],name)
                check(target is not None and target not in seen and classes[target]['access']&0x200,'Missing/invalid source interface')
                seen.add(target);values.update(ancestors(target,depth+1))
            ancestry[id_]=values;parents[id_]=parent
            return values
        finally: busy.remove(id_)
    omitted=[]
    for id_ in range(len(classes)):
        try: ancestors(id_)
        except ValueError: omitted.append(id_)
    return lookup,ancestry,parents,omitted


def physical_fields(classes,parents,id_):
    chain=[];current=id_
    while current is not None:
        check(len(chain)<128,'Excessive physical inheritance')
        chain.append(current);current=parents[current]
    fields=[]
    for owner in reversed(chain):
        for index,field in enumerate(classes[owner]['fields']):
            if field['access']&8: continue
            desc=field['descriptor'];reference=desc.startswith(('L','['))
            size=8 if reference else {'Z':1,'B':1,'C':2,'S':2,'I':4,'F':4,'J':8,'D':8}.get(desc)
            check(size is not None,'Invalid source field descriptor')
            fields.append(dict(owner=owner,index=index,size=size,reference=reference,name=field['name'],descriptor=desc))
    fields.sort(key=lambda f:(not f['reference'],-f['size']))
    check(len(fields)<=65536,'Excessive field count')
    cursor=0
    for field in fields:
        cursor=(cursor+field['size']-1)&~(field['size']-1);field['offset']=cursor;cursor+=field['size']
    return fields,cursor,sum(f['reference'] for f in fields)


def verify(root,batch,plan,artifact,coff_symbols,file_digest):
    root,plan=Path(root),Path(plan);summary=batch['runtime_metadata']
    check(summary['abi']==2,'Unsupported metadata ABI')
    for key in ('linked','class_initialization_provided','java_constructors_executed','automatic_gc'):
        check(summary[key] is False,'Metadata claims unverified execution')
    source=json.loads((plan/'summary.json').read_text(encoding='utf-8'))
    check(file_digest(plan/'classes.jsonl')==source['artifacts']['classes']['digest'],'Source class plan changed')
    classes=[json.loads(line) for line in (plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()]
    check([c['id'] for c in classes]==list(range(len(classes))),'Invalid source class identities')
    lookup,ancestry,parents,omitted=source_model(classes)
    check(omitted==summary['omitted_classes'],'Unresolved hierarchy coverage differs')
    string_id=lookup('bootstrap','java/lang/String');check(string_id==summary['string_layout_owned_by_literal_module'],'String layout ownership differs')
    layouts={row['class_id']:row for row in map(json.loads,artifact(root,batch['layouts']).read_text(encoding='utf-8').splitlines())}
    arrays=list(map(json.loads,artifact(root,batch['array_types']).read_text(encoding='utf-8').splitlines()))
    check([a['id'] for a in arrays]==list(range(len(classes),len(classes)+len(arrays))),'Invalid array identities')
    array_index={(a['defining_loader'],a['descriptor']):a['id'] for a in arrays}
    primitive_start=len(classes)+len(arrays);primitives='ZBCSIJFDV'
    expected_types={};expected_layouts={};expected_fields={};runtime=[]
    field_base=[];field_capacity=0
    for c in classes: field_base.append(field_capacity);field_capacity+=len(c['fields'])
    for c in classes:
        id_=c['id']
        if id_ in omitted: continue
        loader=c['origin']['loader'];name=c['name'];interface=bool(c['access']&0x200)
        expected_types[id_]=dict(id=id_,kind=2 if interface else 1,
            marker_flags=({'java/lang/Object':1,'java/lang/Cloneable':2,'java/io/Serializable':4}.get(name,0) if loader=='bootstrap' else 0),
            parent_component=parents[id_],ancestors=sorted(ancestry[id_]-{id_}),defining_loader=loader,name=name,source_sha256=c['origin']['sha256'])
        if interface: continue
        try: fields,payload,refs=physical_fields(classes,parents,id_)
        except ValueError:
            check(layouts[id_]['candidate'] is None,'Invalid source layout accepted');continue
        candidate=layouts[id_]['candidate']
        check(candidate is not None and candidate['payload_bytes']==payload and candidate['reference_prefix']==refs
              and len(candidate['fields'])==len(fields),'Compact layout differs from source fields')
        for expected,actual in zip(fields,candidate['fields']):
            check((expected['owner'],expected['index'],expected['offset'],expected['size'],expected['reference'])==
                  (actual['member']['owner'],actual['member']['index'],actual['offset'],actual['storage_bytes'],actual['reference']),
                  'Physical source field identity differs')
            if expected['owner']==string_id: continue
            field_id=field_base[expected['owner']]+expected['index']
            record=expected_fields.setdefault(field_id,dict(id=field_id,declaring_class=expected['owner'],declaring_field=expected['index'],
                storage_bytes=expected['size'],reference=expected['reference'],rows=[]))
            record['rows'].append(dict(receiver_class=id_,offset=expected['offset']))
        expected_layouts[id_]=(payload,refs,len(fields))
        runtime.append(dict(tag_symbol=f'boom_layout{id_}',primitive_tag=None,type_id=id_,kind=0,payload_bytes=payload,reference_prefix=refs,shift=0))
    for index,name in enumerate(primitives):
        id_=primitive_start+index;expected_types[id_]=dict(id=id_,kind=0,marker_flags=index,parent_component=None,
            ancestors=[],defining_loader='bootstrap',name=name,source_sha256=None)
    omitted_arrays=[]
    for a in sorted(arrays,key=lambda a:len(a['descriptor'])-len(a['descriptor'].lstrip('['))):
        text=a['descriptor'][1:];loader=a['defining_loader']
        component=(array_index.get((loader,text)) if text.startswith('[') else
                   lookup(loader,text[1:-1]) if text.startswith('L') else primitive_start+primitives.index(text))
        if component not in expected_types: omitted_arrays.append(a['id']);continue
        id_=a['id'];primitive=expected_types[component]['kind']==0
        expected_types[id_]=dict(id=id_,kind=3,marker_flags=0,parent_component=component,ancestors=[],
            defining_loader=loader,name=a['descriptor'],source_sha256=None)
        index=component-primitive_start if primitive else 0
        runtime.append(dict(tag_symbol=None if primitive else f'boom_t{id_}',primitive_tag=[260,264,261,265,266,267,262,263][index] if primitive else None,
            type_id=id_,kind=1 if primitive else 2,payload_bytes=0,reference_prefix=0,shift=[0,0,1,1,2,3,2,3][index] if primitive else 3))
    runtime.sort(key=lambda r:r['type_id'])
    check(sorted(omitted_arrays)==summary['omitted_arrays'],'Unresolved array coverage differs')
    with zipfile.ZipFile(artifact(root,summary['index'],'runtime-metadata')) as bundle:
        check(sorted(bundle.namelist())==['fields.jsonl','runtime.jsonl','types.jsonl'],'Unexpected metadata index')
        values={name:[json.loads(line) for line in bundle.read(name).splitlines()] for name in bundle.namelist()}
    check(values['types.jsonl']==[expected_types[id_] for id_ in sorted(expected_types)],'Runtime types differ from source hierarchy')
    check(values['fields.jsonl']==[expected_fields[id_] for id_ in sorted(expected_fields)],'Runtime field maps differ from source layouts')
    check(values['runtime.jsonl']==runtime,'Runtime tag rows differ from source layouts/arrays')
    check(summary['provided_types']==len(expected_types) and summary['runtime_rows']==len(runtime)
          and summary['provided_field_maps']==len(expected_fields) and summary['layouts']==len(expected_layouts)
          and summary['receiver_offsets']==sum(len(m['rows']) for m in expected_fields.values())
          and summary['field_capacity']==field_capacity and summary['type_capacity']==primitive_start+9,'Metadata counts differ')
    slots=1
    while slots<max(16,len(runtime)*2): slots*=2
    check(summary['hash_slots']==slots,'Runtime hash capacity differs')
    definitions,imports=set(),set();seen_types=set();seen_layouts=set();seen_maps=set();seen_thunks=set()
    registry_seen=set();runtime_seen=False
    for id_,unit in enumerate(summary['units']):
        check(unit['id']==id_ and unit['object'] and not unit['assembler_diagnostic'],'Missing metadata COFF object')
        text=artifact(root,unit['assembly'],'runtime-metadata').read_text(encoding='utf-8')
        defined,undefined=coff_symbols(artifact(root,unit['object'],'runtime-metadata'))
        check(not definitions&defined,'Duplicate metadata COFF definition');definitions.update(defined);imports.update(undefined)
        for match in re.finditer(r'boom_t(\d+) DWORD 054595045h,1,(\d+),(\d+)\n QWORD ([^\n]+)\n DWORD (\d+),0\n',text):
            id_=int(match[1]);check(id_ not in seen_types and id_ in expected_types,'Unexpected/duplicate type descriptor');seen_types.add(id_)
            ty=expected_types[id_];component,ancestors=match[4].split(',')
            check((int(match[2]),int(match[3]),component,ancestors,int(match[5]))==
                  (ty['kind'],ty['marker_flags'],f"OFFSET boom_t{ty['parent_component']}" if ty['parent_component'] is not None else '0',
                   f'OFFSET boom_ancestors{id_}' if ty['ancestors'] else '0',len(ty['ancestors'])),'Encoded type descriptor differs')
            if ty['ancestors']:
                check(f'boom_ancestors{id_} LABEL QWORD\n'+''.join(f' QWORD OFFSET boom_t{a}\n' for a in ty['ancestors']) in text,'Encoded ancestors differ')
        for match in re.finditer(r'boom_layout(\d+) DWORD 04F424A43h,2\n QWORD (\d+)\n DWORD (\d+),(\d+)\n',text):
            id_=int(match[1]);check(id_!=string_id and id_ not in seen_layouts,'Duplicate/owned String layout');seen_layouts.add(id_)
            check(expected_layouts.get(id_)==tuple(map(int,match.groups()[1:])),'Encoded layout differs')
        for match in re.finditer(r'boom_batch_field_record(\d+) DWORD 0464D4150h,1,(\d+),(\d+),(\d+),0\n QWORD OFFSET boom_batch_field_rows\1\nboom_batch_field_rows\1 LABEL DWORD\n((?: DWORD \d+,\d+\n)+)',text):
            id_=int(match[1]);check(id_ not in seen_maps and id_ in expected_fields,'Unexpected/duplicate field map');seen_maps.add(id_);field=expected_fields[id_]
            check(tuple(map(int,match.groups()[1:4]))==(len(field['rows']),field['storage_bytes'],int(field['reference'])),'Encoded field map header differs')
            check(match[5]==''.join(f" DWORD {r['receiver_class']},{r['offset']}\n" for r in field['rows']),'Encoded field offsets differ')
        for match in re.finditer(r'boom_field_map(\d+) PROC\n lea r8,boom_batch_field_record\1\n lea r9,boom_runtime_type_map\n jmp boom_field_address\nboom_field_map\1 ENDP',text):
            id_=int(match[1]);check(id_ not in seen_thunks,'Duplicate field thunk');seen_thunks.add(id_)
        for registry,capacity,records,prefix in [('boom_batch_type_descriptors',primitive_start+9,expected_types,'boom_t'),
                                                 ('boom_batch_field_records',field_capacity,expected_fields,'boom_batch_field_record')]:
            match=re.search(rf'{registry} LABEL QWORD\n((?: QWORD [^\n]+\n)+)',text)
            if match:
                check(registry not in registry_seen,'Duplicate metadata registry');registry_seen.add(registry)
                check(match[1]==''.join(f' QWORD OFFSET {prefix}{i}\n' if i in records else ' QWORD 0\n' for i in range(capacity)),
                      'Encoded metadata registry differs')
        if 'boom_batch_runtime_rows LABEL BYTE\n' in text:
            check(not runtime_seen,'Duplicate runtime tag table');runtime_seen=True
            encoded='boom_batch_runtime_rows LABEL BYTE\n'
            for row in runtime:
                tag=f"OFFSET {row['tag_symbol']}" if row['tag_symbol'] else str(row['primitive_tag'])
                encoded+=(f" QWORD {tag},OFFSET boom_t{row['type_id']}\n DWORD {row['type_id']},{row['kind']}\n"
                          f" QWORD {row['payload_bytes']}\n DWORD {row['reference_prefix']},{row['shift']}\n")
            check(encoded in text,'Encoded runtime tag rows differ')
        if 'boom_runtime_type_map DWORD' in text:
            check(f"boom_runtime_type_map DWORD 052545950h,2,{len(runtime)},{primitive_start+9}\n QWORD OFFSET boom_batch_runtime_rows,0,OFFSET boom_batch_runtime_slots\n DWORD {slots-1},0" in text
                  and f'boom_batch_runtime_slots QWORD {slots} DUP(?)' in text,'Encoded runtime map differs')
    check(seen_types==set(expected_types) and seen_layouts==set(expected_layouts)-{string_id}
          and seen_maps==seen_thunks==set(expected_fields) and runtime_seen and len(registry_seen)==2,'Metadata emission coverage differs')
    required={f'boom_t{i}' for i in expected_types}|{f'boom_layout{i}' for i in expected_layouts if i!=string_id}
    required|={f'boom_field_map{i}' for i in expected_fields}|{f'boom_batch_field_record{i}' for i in expected_fields}
    required.update(('boom_runtime_type_map','boom_batch_type_descriptors','boom_batch_field_records','boom_batch_runtime_rows'))
    check(definitions==required,'Metadata COFF exports differ from source-backed records/functions')
    check(imports-definitions=={f'boom_layout{string_id}','boom_field_address'},'Unexpected unresolved metadata dependency')
    return dict(verified=True,scope='source_type_layout_field_plans_encoded_MASM_and_real_COFF_only',
                provided_types=len(expected_types),runtime_rows=len(runtime),field_maps=len(expected_fields),
                receiver_offsets=summary['receiver_offsets'],omitted_classes=len(omitted),omitted_arrays=len(omitted_arrays),
                linked=False,game_started=False),definitions,imports
