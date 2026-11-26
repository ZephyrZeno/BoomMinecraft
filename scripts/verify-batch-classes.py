"""Prove source Class layouts, identities, literal targets, MASM and real COFF.

Does not certify Class initialization, registration, module bootstrap or a game.
"""
import importlib.util
import json
from pathlib import Path
import zipfile

SPECS=[('java/lang/Object','getClass','()Ljava/lang/Class;',0x111,0),
       ('java/lang/Class','isInterface','()Z',0x101,1),('java/lang/Class','isArray','()Z',0x101,2),
       ('java/lang/Class','isPrimitive','()Z',0x101,3),('java/lang/Class','isHidden','()Z',0x101,4),
       ('java/lang/Class','getSuperclass','()Ljava/lang/Class;',0x101,5),
       ('java/lang/Class','isAssignableFrom','(Ljava/lang/Class;)Z',0x101,6),('java/lang/Class','isInstance','(Ljava/lang/Object;)Z',0x101,7),
       ('java/lang/Class','initClassName','()Ljava/lang/String;',0x102,8)]

def check(value,message):
    if not value:raise ValueError(message)

def native_body(id_,op):
    if op==8:return f'.code\nboom_m{id_} PROC\n jmp boom_m{id_}_native\nboom_m{id_} ENDP\nboom_m{id_}_native PROC\n lea r8,boom_java_class_pool\n lea r9,boom_java_class_name_pool\n jmp boom_java_class_name\nboom_m{id_}_native ENDP\n'
    return f'.code\nboom_m{id_} PROC\n jmp boom_m{id_}_native\nboom_m{id_} ENDP\nboom_m{id_}_native PROC\n lea r8,boom_java_class_pool\n mov r9d,{op}\n jmp boom_java_class_query\nboom_m{id_}_native ENDP\n'

def literal_body(label,id_):return f'.code\n{label} PROC\n lea rdx,boom_java_class_pool\n mov r8d,{id_}\n jmp boom_java_class_load\n{label} ENDP\n'

def shape_model(classes,layouts,include_names=True):
    def source(name):
        found=[c for c in classes if c['name']==name and c['origin']['loader']=='bootstrap']
        check(len(found)==1,'Missing/ambiguous original Class dependency');c=found[0]
        check(c['origin']['source_id']=='jdk:java.base' and c['origin'].get('generated') is None,'Class VM field requires original java.base source')
        return c
    c,m,l=map(source,('java/lang/Class','java/lang/Module','java/lang/ClassLoader'))
    check(c['access']==0x31 and c['superclass']=='java/lang/Object','Normal Class source identity differs')
    def slot(owner,name,desc,access):
        declarations=[f for f in owner['fields'] if (f['name'],f['descriptor'])==(name,desc)]
        check(len(declarations)==1 and declarations[0]['access']==access,'Source Class VM field declaration differs')
        slots=[f for f in layouts[owner['id']]['fields'] if (f['member']['owner'],f['member']['name'],f['member']['descriptor'])==(owner['id'],name,desc)]
        check(len(slots)==1 and slots[0]['reference'] and slots[0]['storage_bytes']==8,'Normal VM field physical slot differs')
        return slots[0]['offset']
    layout=layouts[c['id']]
    result=dict(class_id=c['id'],class_sha256=c['origin']['sha256'],payload_bytes=layout['payload_bytes'],reference_prefix=layout['reference_prefix'],fields=len(layout['fields']),
        loader_offset=slot(c,'classLoader','Ljava/lang/ClassLoader;',0x12),module_offset=slot(c,'module','Ljava/lang/Module;',0x82),
        component_offset=slot(c,'componentType','Ljava/lang/Class;',0x12),loader_type=l['id'],module_type=m['id'],module_loader_offset=slot(m,'loader','Ljava/lang/ClassLoader;',0x12))
    if include_names:result['name_offset']=slot(c,'name','Ljava/lang/String;',0x82)
    return result


def names_model(types,literals=None):
    primitives=dict(Z='boolean',B='byte',C='char',S='short',I='int',J='long',F='float',D='double',V='void')
    requested={}
    for id_,t in types.items():
        text=primitives[t['name']] if t['kind']==0 else t['name'].replace('/','.')
        encoded=text.encode('utf-16-le',errors='surrogatepass')
        units=tuple(int.from_bytes(encoded[i:i+2],'little') for i in range(0,len(encoded),2))
        check(0<len(units)<=65535,'Class name UTF16 budget exceeded');requested[id_]=units
    canonical=sorted(set(requested.values()));ids={s:i for i,s in enumerate(canonical)}
    def hash_(units):
        h=0
        for unit in units:h=(31*h+unit)&0xffffffff
        return h
    return [dict(type_id=id_,canonical=ids[units]) for id_,units in sorted(requested.items())], [dict(id=i,utf16=list(s),java_hash=hash_(s),literal=(literals or {}).get(s)) for i,s in enumerate(canonical)]


def names_body(shape,capacity,string,names,canonical):
    count=len(canonical);c=string['class_id'];indices={r['type_id']:r['canonical'] for r in names}
    parts=[f".data\nALIGN 8\nPUBLIC boom_java_class_name_pool\nboom_java_class_name_pool DWORD 04A434E50h,1,{shape['name_offset']},{capacity}\n QWORD OFFSET java_class_name_indices,OFFSET java_class_name_literals,OFFSET boom_layout{c},OFFSET boom_java_string_literal\n QWORD OFFSET boom_java_string_literal_pool,OFFSET java_class_name_aliases\njava_class_name_literals DWORD 04A534C50h,1,{count},1\n QWORD OFFSET java_class_name_entries,OFFSET boom_java_class_name_roots,OFFSET java_class_name_states,OFFSET boom_layout{c}\n DWORD {string['value_offset']},{string['coder_offset']},{string['hash_offset']},{string['hash_is_zero_offset']}\n QWORD 0\n DWORD 0,0\n.const\nPUBLIC boom_java_class_name_root_count\nboom_java_class_name_root_count QWORD {count*2}\njava_class_name_indices LABEL DWORD\n"]
    parts.extend(f' DWORD {indices.get(i,0xffffffff)}\n' for i in range(capacity))
    parts.append('java_class_name_aliases LABEL DWORD\n')
    parts.extend(f" DWORD {r['literal'] if r['literal'] is not None else 0xffffffff}\n" for r in canonical)
    parts.append('ALIGN 8\njava_class_name_entries LABEL BYTE\n')
    parts.extend(f" QWORD OFFSET java_class_name_text_{r['id']}\n DWORD {len(r['utf16'])},0{r['java_hash']:08X}h\n" for r in canonical)
    for r in canonical:
        parts.append(f"ALIGN 2\njava_class_name_text_{r['id']} LABEL WORD\n")
        for i in range(0,len(r['utf16']),16):parts.append(' WORD '+','.join(f'0{v:04X}h' for v in r['utf16'][i:i+16])+'\n')
    parts.append(f'.data?\nALIGN 8\nPUBLIC boom_java_class_name_roots\nboom_java_class_name_roots QWORD {count*2} DUP(?)\njava_class_name_states DWORD {count} DUP(?)\n.code\n')
    return ''.join(parts)

def identities(classes,types,bootstrap_unnamed_slot=None):
    loaders=['bootstrap']+sorted({t['defining_loader'] for t in types.values()}-{'bootstrap'});loader_ids={s:i for i,s in enumerate(loaders)}
    keys=set()
    for t in types.values():
        if t['kind'] not in (1,2):continue
        origin=classes[t['id']]['origin'];check(origin.get('generated') is None,'Hidden/generated class needs explicit generation metadata')
        keys.add((t['defining_loader'],origin['source_id'][4:] if origin['source_id'].startswith('jdk:') else None))
    base=('bootstrap','java.base');keys.discard(base)
    keys=[base]+sorted(keys,key=lambda k:(k[0],k[1] is not None,k[1] or ''))
    if bootstrap_unnamed_slot is not None:
        boot=('bootstrap',None)
        if boot not in keys:keys.append(boot)
        check(type(bootstrap_unnamed_slot) is int and keys.index(boot)==bootstrap_unnamed_slot,
              'Declared bootstrap unnamed module slot differs from stable source module IDs')
    check(len(keys)<=65536,'Class module identity budget exceeded')
    mods=[dict(id=i,name=n,loader=loader_ids[l]) for i,(l,n) in enumerate(keys)];mod_ids={key:i for i,key in enumerate(keys)}
    rows={};object_id=next(c['id'] for c in classes if (c['origin']['loader'],c['name'])==('bootstrap','java/lang/Object'))
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    for t in types.values():
        if t['kind']==3:continue
        loader=loader_ids[t['defining_loader']];module=0;access=major=0;parent=None
        if t['kind']:
            c=classes[t['id']];s=c['origin']['source_id'];module=mod_ids[t['defining_loader'],s[4:] if s.startswith('jdk:') else None]
            access=c['access'];major=c['origin']['java_class_major']
            if t['kind']==1 and c.get('superclass'):
                # The type model already independently resolved the source parent.
                parent=t['parent_component'];check(parent is not None and classes[parent]['name']==c['superclass'],'Class mirror parent differs')
        rows[t['id']]=dict(type_id=t['id'],component=None,superclass=parent,loader=loader,module=module,flags=int(loader==0 and module==0),raw_access=access,major=major)
    for t in sorted((t for t in types.values() if t['kind']==3),key=lambda t:len(t['name'])-len(t['name'].lstrip('['))):
        component=t['parent_component'];check(component in rows,'Unprovided source Class array component');r=rows[component]
        check(loaders[r['loader']]==t['defining_loader'],'Class array defining loader differs')
        rows[t['id']]=dict(type_id=t['id'],component=component,superclass=object_id,loader=r['loader'],module=r['module'],flags=int(r['loader']==0 and r['module']==0),raw_access=0,major=0)
    return loaders,mods,rows


def named_module_identities(root,batch,plan,classes,loaders,modules):
    """Derive extra no-type module keys from locked original descriptors, never flags."""
    if not (root/'named-module-derivation.json').is_file():return modules
    spec=importlib.util.spec_from_file_location('class_named_module_source',Path(__file__).with_name('refresh-named-module-batch.py'))
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    original=dict(batch,class_literals=dict(batch['class_literals'],loader_keys=loaders,modules=modules))
    additions,_=model.source_graph(original,plan,classes=classes)
    check(additions and len(modules)+len(additions)<=65536,'Named Class module identity budget exceeded')
    return modules+additions

def pool_body(shape,capacity,loaders,modules,rows,reverse):
    c=shape['class_id'];roots=capacity+len(loaders)+len(modules)
    parts=[f".data\nALIGN 8\nPUBLIC boom_java_class_pool\nboom_java_class_pool DWORD 04A434C53h,1,0,{capacity}\n QWORD OFFSET boom_java_class_roots,OFFSET boom_java_class_records,OFFSET boom_layout{c},OFFSET boom_runtime_type_map,OFFSET boom_heap_ptr,OFFSET boom_java_class_loader_roots,OFFSET boom_java_class_module_roots,OFFSET boom_java_class_reverse\n DWORD {reverse-1},{len(loaders)},{len(modules)},1\n DWORD {shape['loader_offset']},{shape['module_offset']},{shape['component_offset']},{c}\n QWORD OFFSET boom_t{shape['loader_type']},OFFSET boom_t{shape['module_type']},OFFSET boom_java_class_module_loaders\n DWORD {shape['module_loader_offset']},0\n.const\nPUBLIC boom_java_class_root_count\nboom_java_class_root_count QWORD {roots}\nboom_java_class_module_loaders LABEL DWORD\n"]
    parts.extend(f" DWORD {m['loader']}\n" for m in modules)
    parts.append(f'.data?\nALIGN 8\nPUBLIC boom_java_class_roots\nboom_java_class_roots LABEL QWORD\n QWORD {capacity} DUP(?)\nPUBLIC boom_java_class_loader_roots\nboom_java_class_loader_roots QWORD {len(loaders)} DUP(?)\nPUBLIC boom_java_class_module_roots\nboom_java_class_module_roots QWORD {len(modules)} DUP(?)\nboom_java_class_reverse QWORD {reverse*2} DUP(?)\n.const\nALIGN 8\nPUBLIC boom_java_class_records\nboom_java_class_records LABEL BYTE\n')
    for id_ in range(capacity):
        if id_ not in rows:parts.append(' QWORD 0\n DWORD 0,0,0,0,0,0,0,0\n QWORD 0\n');continue
        r=rows[id_];component=0xffffffff if r['component'] is None else r['component'];parent=0xffffffff if r['superclass'] is None else r['superclass']
        parts.append(f" QWORD OFFSET boom_t{id_}\n DWORD {component},{parent},{r['loader']},{r['module']},{r['flags']},{r['raw_access']},{r['major']},0\n QWORD 0\n")
    return ''.join(parts)

def verify(root,batch,plan,inventory,requests,available,artifact,coff_symbols,file_digest):
    root,plan=Path(root),Path(plan);s=batch['class_literals']
    check((s['abi'],s['context_bytes'])==(1,32),'Invalid normal Class ABI')
    for flag in ('class_initialization_executed','class_native_registration_provided','module_bootstrap_completed','automatic_gc','linked'):
        check(s[flag] is False,'Class generator claims unverified bootstrap/runtime behavior')
    classes=list(map(json.loads,(plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    layouts={r['class_id']:r['candidate'] for r in map(json.loads,artifact(root,batch['layouts']).read_text(encoding='utf-8').splitlines())}
    with zipfile.ZipFile(artifact(root,batch['runtime_metadata']['index'],'runtime-metadata')) as z:types={r['id']:r for r in map(json.loads,z.read('types.jsonl').splitlines())}
    with_names=batch['schema']>=11
    bootstrap_unnamed_slot=s.get('bootstrap_unnamed_module_slot')
    check('bootstrap_unnamed_module_slot' not in s or type(bootstrap_unnamed_slot) is int,
          'Bootstrap unnamed module slot must be an explicit integer')
    shape=shape_model(classes,layouts,with_names);loaders,modules,rows=identities(classes,types,bootstrap_unnamed_slot);capacity=batch['runtime_metadata']['type_capacity'];reverse=1
    modules=named_module_identities(root,batch,plan,classes,loaders,modules)
    while reverse<capacity*2:reverse*=2
    check(s['source_shape']==shape and s['loader_keys']==loaders and s['modules']==modules,'Normal Class layout/loader/module source differs')
    check((s['type_capacity'],s['provided_types'],s['root_cells'],s['reverse_slots'])==(capacity,len(rows),capacity+len(loaders)+len(modules),reverse),'Class mirror registry counts differ')
    with zipfile.ZipFile(artifact(root,s['index'],'class-literals')) as z:
        check(z.namelist()==['types.jsonl','sites.jsonl','methods.jsonl']+(['names.jsonl','canonical_names.jsonl'] if with_names else []),'Unexpected Class module index')
        originals={r['type_id']:r for r in map(json.loads,z.read('types.jsonl').splitlines())};sites=list(map(json.loads,z.read('sites.jsonl').splitlines()));methods=list(map(json.loads,z.read('methods.jsonl').splitlines()))
        if with_names:
            with zipfile.ZipFile(artifact(root,batch['string_literals']['index'],'string-literals')) as literals_bundle:
                literals={tuple(r['utf16']):r['id'] for r in map(json.loads,literals_bundle.read('canonical.jsonl').splitlines())}
            names,canonical=names_model(types,literals)
            check(list(map(json.loads,z.read('names.jsonl').splitlines()))==names and list(map(json.loads,z.read('canonical_names.jsonl').splitlines()))==canonical,'Class name source identities/UTF16 differ')
            string=batch['string_literals']['source_layout']
            check(s['name_factory']==dict(abi=1,types=len(types),canonical_names=len(canonical),source_literal_aliases=sum(r['literal'] is not None for r in canonical),root_cells=len(canonical)*2,source_string_class=string['class_id'],source_string_sha256=string['source_sha256'],general_string_intern=False),'Class name factory metadata differs')
    check(originals==rows,'Normal Class represented-type identities differ')
    expected=[]
    for owner,name,desc,access,op in (SPECS if with_names else SPECS[:8]):
        c=next(c for c in classes if (c['origin']['loader'],c['name'])==('bootstrap',owner))
        ids=[id_ for id_ in c['method_ids'] if inventory[id_][1:3]==(name,desc)]
        check(c['origin']['source_id']=='jdk:java.base' and c['origin'].get('generated') is None and len(ids)==1 and inventory[ids[0]][8]==access and inventory[ids[0]][4] is None,'Class core native source signature/access/Code differs')
        expected.append(dict(method=ids[0],class_id=c['id'],class_sha256=c['origin']['sha256'],name=name,descriptor=desc,access=access,operation=op,assembly_unit=0))
    check(methods==expected and s['source_native_methods']==len(expected),'Class native implementation coverage differs')
    check([r['label'] for r in sites]==sorted(requests.class_literals),'Class constant site coverage differs')
    spec=importlib.util.spec_from_file_location('class_literal_source_lookup',Path(__file__).with_name('verify-batch-metadata.py'));model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    lookup,_,_,_=model.source_model(classes);array_index={(t['defining_loader'],t['name']):t['id'] for t in types.values() if t['kind']==3}
    body=pool_body(shape,capacity,loaders,modules,rows,reverse)+(names_body(shape,capacity,string,names,canonical) if with_names else '')+''.join(native_body(m['method'],m['operation']) for m in methods)
    for row in sites:
        request=requests.class_literals[row['label']];check({k:row[k] for k in request['site']}==request['site'] and row['caller_methods']==sorted(request['methods']),'Class constant binding differs')
        value=requests.constants[row['caller_class']][str(row['constant'])];check(set(value)=={'Class'},'Class literal constant kind differs');name=value['Class'];loader=classes[row['caller_class']]['origin']['loader']
        if name.startswith('['):
            element=name.lstrip('[');component=lookup(loader,element[1:-1]) if element.startswith('L') else None
            defining=classes[component]['origin']['loader'] if component is not None else 'bootstrap';target=array_index.get((defining,name))
        else:target=lookup(loader,name)
        check(target==row['type_id'],'Class literal represented type differs from source constant')
        provided=target in rows;check(row['assembly_unit']==(0 if provided else None) and row['diagnostic']==(None if provided else 'Source Class type metadata unavailable'),'Class literal availability differs')
        if provided:body+=literal_body(row['label'],target)
    check(s['literal_sites']==len(sites) and s['generated_sites']==sum(r['assembly_unit'] is not None for r in sites),'Class literal summary coverage differs')
    check(set(s['kernel_sha256'])=={'native/runtime/java_classes.asm'},'Class native kernel dependencies differ')
    project=Path(__file__).resolve().parents[1]
    for p,digest in s['kernel_sha256'].items():check(file_digest(project/p)['sha256']==digest,'Class native kernel changed')
    check(len(s['units'])==1,'Unexpected normal Class data unit count');u=s['units'][0]
    text=artifact(root,u['assembly'],'class-literals').read_text(encoding='utf-8');check(text.partition('.code\n')[2][:-5]==body and text.endswith('\nEND\n'),'Normal Class MASM differs from independent source model')
    check(u['object'] is not None and not u['assembler_diagnostic'],'Class module assembly failed')
    defined,undefined=coff_symbols(artifact(root,u['object'],'class-literals'))
    required={r['label'] for r in sites if r['assembly_unit'] is not None}|{f"boom_m{m['method']}{suffix}" for m in methods for suffix in ('','_native')}|{'boom_java_class_pool','boom_java_class_root_count','boom_java_class_roots','boom_java_class_loader_roots','boom_java_class_module_roots','boom_java_class_records'}
    if with_names:required.update(('boom_java_class_name_pool','boom_java_class_name_root_count','boom_java_class_name_roots'))
    check(defined==required,'Normal Class COFF definitions differ')
    needed={f'boom_t{id_}' for id_ in rows}|{f"boom_layout{shape['class_id']}",'boom_runtime_type_map','boom_heap_ptr'}
    if with_names:needed.update((f"boom_layout{string['class_id']}",'boom_java_string_literal','boom_java_string_literal_pool'))
    check(needed<=available and undefined==needed|{'boom_java_class_load','boom_java_class_query'}|({'boom_java_class_name'} if with_names else set()),'Class module references unprovided metadata or unknown services')
    return dict(verified=True,scope='source_Class_fields_loader_module_identities_literals_native_signatures_MASM_and_COFF_only',provided_types=len(rows),literal_sites=len(sites),native_methods=len(methods),class_initialization_executed=False,game_started=False),defined,undefined,{m['method'] for m in methods}
