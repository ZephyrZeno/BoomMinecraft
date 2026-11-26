"""Read immutable original class metadata for normal-layout reflection providers."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

def check(ok,message):
    if not ok:raise ValueError(message)

def artifact(record):
    p=Path(record['path'])
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    check(p.stat().st_size==record['digest']['size'] and h==record['digest']['sha256'],'Constructor base metadata artifact changed')
    return p

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

RAW=module('constructor_raw_reader','verify-batch-frames.py')
SYSTEM=module('constructor_locked_system_inputs','system-class-inputs.py')

class RawClasses:
    def __init__(self,summary):
        self.summary=summary;self.archives={}
        self.system=SYSTEM.SystemClasses(artifact(summary['frames']['original_system_catalog']))
    def close(self):
        self.system.close()
        for z in self.archives.values():z.close()
    def read(self,c):
        o=c['origin'];entry=o['jar_entry']
        if o['source_id'].startswith('jdk:'):
            data=self.system.read(o)
        else:
            key=o['source_id']
            if key not in self.archives:
                a=self.summary['frames']['original_input_files'][key];p=Path(a['path'])
                with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
                check(p.stat().st_size==a['digest']['size'] and h==a['digest']['sha256'],'Original constructor source archive changed')
                self.archives[key]=zipfile.ZipFile(p)
            data=self.archives[key].read(entry)
        check(hashlib.sha256(data).hexdigest()==o['sha256'],'Original constructor class changed')
        return data

def methods(data):
    """Keep raw reflection attributes, including absent versus present-empty."""
    raw=RAW;r=raw.Reader(data)
    check(r.number(4)==0xcafebabe,'Constructor source class magic differs');r.take(4)
    count=r.number(2);cp=[None]*count;i=1
    while i<count:
        tag=r.number(1)
        if tag==1:cp[i]=raw.modified_utf8(r.take(r.number(2)))
        elif tag in (3,4):r.take(4)
        elif tag in (5,6):r.take(8);i+=1
        elif tag in (7,8,16,19,20):cp[i]=r.number(2)
        elif tag in (9,10,11,12,17,18):r.take(4)
        elif tag==15:r.take(3)
        else:raise ValueError('Unknown original constructor constant tag')
        i+=1
    def utf(i):
        check(0<i<count and isinstance(cp[i],str),'Constructor attribute UTF8 missing');return cp[i]
    def clazz(i):
        check(0<i<count and isinstance(cp[i],int),'Constructor attribute class missing');return utf(cp[i])
    def attrs():
        result={}
        for _ in range(r.number(2)):
            name=utf(r.number(2));payload=r.take(r.number(4))
            check(name not in result,'Duplicate constructor source attribute');result[name]=payload
        return result
    r.number(2);owner=clazz(r.number(2));r.number(2);r.take(2*r.number(2))
    for _ in range(r.number(2)):r.take(6);attrs()
    result=[]
    for slot in range(r.number(2)):
        access=r.number(2);name=utf(r.number(2));desc=utf(r.number(2));a=attrs()
        e=raw.Reader(a.get('Exceptions',b'\0\0'));exceptions=[clazz(e.number(2)) for _ in range(e.number(2))];e.end()
        signature=None
        if 'Signature' in a:
            x=raw.Reader(a['Signature']);signature=utf(x.number(2));x.end()
        result.append(dict(slot=slot,name=name,descriptor=desc,access=access,signature=signature,exceptions=exceptions,
            annotations=a.get('RuntimeVisibleAnnotations',b'').hex(),parameter_annotations=a.get('RuntimeVisibleParameterAnnotations',b'').hex(),
            type_annotations=a.get('RuntimeVisibleTypeAnnotations',b'').hex(),parameters=a.get('MethodParameters',b'').hex()))
    attrs();r.end();return owner,result

def parameter_names(desc):
    check(desc.startswith('(') and desc.endswith(')V'),'Constructor descriptor must return void')
    end=len(desc)-2;at=1;result=[]
    while at<end:
        begin=at
        while at<end and desc[at]=='[':at+=1
        check(at<end,'Truncated constructor parameter')
        if desc[at]=='L':
            start=at;at=desc.find(';',at+1);check(at>start+1 and at<end,'Unterminated constructor parameter');at+=1
        else:
            check(desc[at] in 'ZBCSIJFD','Invalid constructor parameter primitive');at+=1
        result.append(desc[begin:at])
    check(at==end,'Invalid constructor parameter end');return result

def inputs(summary,classes):
    with zipfile.ZipFile(artifact(summary['runtime_metadata']['index'])) as z:
        types=[json.loads(l) for l in z.read('types.jsonl').splitlines()]
        runtime=[json.loads(l) for l in z.read('runtime.jsonl').splitlines()]
    hierarchy=module('constructor_original_hierarchy','verify-batch-metadata.py')
    lookup,_,_,_=hierarchy.source_model(classes)
    names={(t['defining_loader'],t['name']):t['id'] for t in types};available={t['id'] for t in types}
    primitives=dict(zip('ZBCSIJFDV',('boolean','byte','char','short','int','long','float','double','void')))
    def resolve(loader,desc):
        rank=len(desc)-len(desc.lstrip('['));base=desc[rank:]
        if base.startswith('L') and base.endswith(';'):
            id_=lookup(loader,base[1:-1]);defining=classes[id_]['origin']['loader'] if id_ is not None else None
            name=desc if rank else base[1:-1]
        else:
            check(base in primitives and (not rank or base!='V'),'Invalid reflection type descriptor')
            defining='bootstrap';name=desc if rank else base
        id_=names.get((defining,name));return id_ if id_ in available else None
    return types,runtime,available,resolve

def index(summary,classes,source_inputs=None):
    types,runtime,available,resolve=inputs(summary,classes) if source_inputs is None else source_inputs;source=RawClasses(summary)
    records=[];ranges=[]
    try:
        for c in classes:
            first=len(records);status=1 if c['id'] in available else 3
            if c.get('parse_error') or c['access']&0x8000:status=3
            else:
                owner,raw=methods(source.read(c));check(owner==c['name'] and len(raw)==len(c['method_ids']),'Constructor original inventory differs')
                for m in raw:
                    if m['name']!='<init>':continue
                    check(not m['access']&0x108,'Constructor cannot be static or native')
                    params=[resolve(c['origin']['loader'],d) for d in parameter_names(m['descriptor'])]
                    exceptions=[resolve(c['origin']['loader'],'L'+n+';') for n in m['exceptions']]
                    records.append(dict(owner=c['id'],source_sha256=c['origin']['sha256'],loader=c['origin']['loader'],
                        method=c['method_ids'][m['slot']],slot=m['slot'],descriptor=m['descriptor'],modifiers=m['access']&0x1dff,
                        parameters=params,exceptions=exceptions,unavailable=any(v is None for v in params+exceptions),
                        signature=m['signature'],annotations=m['annotations'],parameter_annotations=m['parameter_annotations'],
                        type_annotations=m['type_annotations'],method_parameters=m['parameters']))
            ranges.append(dict(type_id=c['id'],first=first,count=len(records)-first,status=status))
    finally:source.close()
    class_count=len(classes);capacity=summary['runtime_metadata']['type_capacity']
    for id_ in range(class_count,capacity):ranges.append(dict(type_id=id_,first=len(records),count=0,status=1 if id_ in available else 3))
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    wanted={names['bootstrap',n] for n in ('java/lang/reflect/Constructor','java/lang/String','java/lang/reflect/Executable','java/lang/reflect/AccessibleObject')}
    layouts={}
    with artifact(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            r=json.loads(line)
            if r['class_id'] in wanted:
                check(r['candidate'] is not None and r['diagnostic'] is None,'Reflection source layout missing');layouts[str(r['class_id'])]=r
    ctor=names['bootstrap','java/lang/reflect/Constructor'];string=names['bootstrap','java/lang/String']
    def offset(id_,owner,name,desc):
        fields=layouts[str(id_)]['candidate']['fields'];matches=[f for f in fields if (f['member']['owner'],f['member']['name'],f['member']['descriptor'])==(owner,name,desc)]
        check(len(matches)==1,'Reflection source field missing');return matches[0]['offset']
    fields=[('clazz','Ljava/lang/Class;'),('parameterTypes','[Ljava/lang/Class;'),('exceptionTypes','[Ljava/lang/Class;'),
            ('signature','Ljava/lang/String;'),('annotations','[B'),('parameterAnnotations','[B'),('slot','I'),('modifiers','I')]
    offsets=[offset(ctor,ctor,n,d) for n,d in fields]
    type_names={(t['defining_loader'],t['name']):t['id'] for t in types}
    arrays={n:next(r for r in runtime if r['type_id']==type_names['bootstrap',n]) for n in ('[Ljava/lang/reflect/Constructor;','[Ljava/lang/Class;','[B')}
    return dict(schema=1,type_capacity=capacity,records=records,ranges=ranges,layouts=layouts,constructor_class=ctor,string_class=string,
        field_offsets=offsets,string_value_offset=offset(string,string,'value','[B'),string_coder_offset=offset(string,string,'coder','B'),arrays=arrays,
        source_transform_chain='original_locked_no_transforms',dynamic_redefinition=False,all_native_frames=False,automatic_gc=False,game_started=False)

def data(m):
    """Only immutable metadata; no Java bodies or host callbacks."""
    ctor=m['constructor_class'];string=m['string_class'];arrays=m['arrays']
    imports={'boom_java_class_pool','boom_heap_ptr',f'boom_layout{ctor}',f'boom_layout{string}',f'boom_class{ctor}',
        arrays['[Ljava/lang/reflect/Constructor;']['tag_symbol'],arrays['[Ljava/lang/Class;']['tag_symbol']}
    parts=['.const\nALIGN 8\nPUBLIC boom_provider_constructor_pool\n',
        f"boom_provider_constructor_pool DWORD 04E435452h,1,{m['type_capacity']},{len(m['records'])}\n",
        ' QWORD OFFSET boom_java_class_pool,OFFSET boom_heap_ptr,OFFSET provider_ctor_ranges,OFFSET provider_ctor_rows\n',
        f" QWORD OFFSET boom_layout{ctor},OFFSET {arrays['[Ljava/lang/reflect/Constructor;']['tag_symbol']},OFFSET {arrays['[Ljava/lang/Class;']['tag_symbol']},OFFSET boom_layout{string}\n",
        f" QWORD OFFSET boom_class{ctor},OFFSET provider_ctor_offsets\n DWORD {m['string_value_offset']},{m['string_coder_offset']}\n QWORD {arrays['[B']['primitive_tag']}\n DWORD 16,80,8,0,1,0\n QWORD 0,0,0\n",
        'provider_ctor_offsets DWORD '+','.join(map(str,m['field_offsets']))+'\nALIGN 8\nprovider_ctor_ranges LABEL BYTE\n']
    parts.extend(f" DWORD {r['first']},{r['count']},{r['status']},0\n" for r in m['ranges'])
    parts.append('ALIGN 8\nprovider_ctor_rows LABEL BYTE\n')
    for i,r in enumerate(m['records']):
        sig=r['signature'].encode('utf-16-le','surrogatepass') if r['signature'] is not None else b''
        ann=bytes.fromhex(r['annotations']);par=bytes.fromhex(r['parameter_annotations'])
        ptr=lambda kind,present:f'OFFSET provider_ctor_{kind}{i}' if present else '0'
        parts.append(f" DWORD {r['owner']},{r['slot']},{r['modifiers']},{len(r['parameters'])}\n QWORD {ptr('params',r['parameters'])},{ptr('exceptions',r['exceptions'])}\n DWORD {len(r['exceptions'])},{int(r['unavailable'])}\n QWORD {ptr('signature',sig)}\n DWORD {len(sig)//2},{len(ann)}\n QWORD {ptr('annotations',ann)}\n DWORD {len(par)},0\n QWORD {ptr('parameter_annotations',par)}\n")
    for i,r in enumerate(m['records']):
        for kind in ('parameters','exceptions'):
            if r[kind]:parts.append(f"provider_ctor_{'params' if kind=='parameters' else kind}{i} DWORD "+','.join(str(v if v is not None else 0xffffffff) for v in r[kind])+'\n')
        payloads={'signature':r['signature'].encode('utf-16-le','surrogatepass') if r['signature'] is not None else b'',
            'annotations':bytes.fromhex(r['annotations']),'parameter_annotations':bytes.fromhex(r['parameter_annotations'])}
        for kind,b in payloads.items():
            if not b:continue
            parts.append(f'provider_ctor_{kind}{i} LABEL BYTE\n')
            parts.extend(' BYTE '+','.join(map(str,b[n:n+32]))+'\n' for n in range(0,len(b),32))
    return ''.join(parts),imports
