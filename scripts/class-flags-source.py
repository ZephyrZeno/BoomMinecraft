"""Original class access flags and reflection modifiers for a frozen type universe."""
import json
import zipfile
from pathlib import Path
import importlib.util

spec=importlib.util.spec_from_file_location('flags_original_class_io',Path(__file__).with_name('constructor-provider-source.py'))
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
check=C.check

def original(data):
    r=C.RAW.Reader(data);check(r.number(4)==0xcafebabe,'Class flags source magic differs');r.take(4)
    count=r.number(2);cp=[None]*count;i=1
    while i<count:
        tag=r.number(1)
        if tag==1:cp[i]=C.RAW.modified_utf8(r.take(r.number(2)))
        elif tag in (3,4):r.take(4)
        elif tag in (5,6):r.take(8);i+=1
        elif tag in (7,8,16,19,20):cp[i]=r.number(2)
        elif tag in (9,10,11,12,17,18):r.take(4)
        elif tag==15:r.take(3)
        else:raise ValueError('Unknown class flags constant tag')
        i+=1
    def utf(i):
        check(0<i<count and isinstance(cp[i],str),'Class flags UTF8 missing');return cp[i]
    def clazz(i):
        check(0<i<count and isinstance(cp[i],int),'Class flags class constant missing');return utf(cp[i])
    def attrs():
        result={}
        for _ in range(r.number(2)):
            name=utf(r.number(2));payload=r.take(r.number(4));check(name not in result,'Duplicate class flags attribute');result[name]=payload
        return result
    header=r.number(2);name=clazz(r.number(2));r.number(2);r.take(2*r.number(2))
    for _ in range(2):
        for _ in range(r.number(2)):r.take(6);attrs()
    attributes=attrs();r.end();synthetic='Synthetic' in attributes
    if synthetic:check(attributes['Synthetic']==b'','Invalid original Synthetic attribute')
    inner=None
    if 'InnerClasses' in attributes:
        a=C.RAW.Reader(attributes['InnerClasses'])
        for _ in range(a.number(2)):
            target=a.number(2);a.number(2);a.number(2);flags=a.number(2)
            if target and clazz(target)==name and inner is None:inner=flags
        a.end()
    raw=(header&0x7631)|(0x1000 if synthetic else 0)
    modifiers=((raw if inner is None else inner)&~0x20)&0x7fff
    return dict(name=name,header_access=header,synthetic_attribute=synthetic,inner_access=inner,raw_flags=raw,modifiers=modifiers)

def index(summary,classes):
    with zipfile.ZipFile(C.artifact(summary['runtime_metadata']['index'])) as z:types=[json.loads(l) for l in z.read('types.jsonl').splitlines()]
    available={t['id']:t for t in types};source=C.RawClasses(summary);originals={}
    try:
        for c in classes:
            if c['id'] not in available:continue
            check(not c.get('parse_error') and not c['access']&0x8000,'Available class flags source is invalid')
            o=original(source.read(c));check(o['name']==c['name'] and o['header_access']==c['access'],'Class flags original source header differs')
            originals[c['id']]=dict(o,class_id=c['id'],source_sha256=c['origin']['sha256'],loader=c['origin']['loader'])
    finally:source.close()
    capacity=summary['runtime_metadata']['type_capacity'];rows=[]
    for id_ in range(capacity):
        t=available.get(id_)
        raw=modifiers=state=0
        if t is not None:
            state=1
            if t['kind']==0:raw=modifiers=0x411
            elif t['kind'] in (1,2):raw=originals[id_]['raw_flags'];modifiers=originals[id_]['modifiers']
            else:
                check(t['kind']==3,'Unknown source class flags type kind');bottom=t;seen=set()
                while bottom['kind']==3:
                    check(bottom['id'] not in seen and len(seen)<255,'Invalid source class flags array component chain')
                    seen.add(bottom['id']);check(bottom['parent_component'] in available,'Missing class flags array component')
                    bottom=available[bottom['parent_component']]
                raw=0 # HotSpot array Klass access flags, distinct from modifiers.
                modifiers=0x410|(1 if bottom['kind']==0 else originals[bottom['id']]['modifiers']&7)
        rows.append(dict(type_id=id_,raw_flags=raw,modifiers=modifiers,state=state))
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    return dict(schema=1,type_capacity=capacity,provided_types=len(available),original_classes=list(originals.values()),rows=rows,
        class_class=names['bootstrap','java/lang/Class'],reflection_class=names['bootstrap','jdk/internal/reflect/Reflection'],
        source_transform_chain='original_locked_no_transforms',dynamic_redefinition=False,game_started=False)

def data(m):
    parts=[f".const\nALIGN 8\nPUBLIC boom_provider_class_flags_pool\nboom_provider_class_flags_pool DWORD 04A434647h,1,{m['type_capacity']},16\n QWORD OFFSET boom_java_class_pool,OFFSET provider_class_flags_rows\nprovider_class_flags_rows LABEL BYTE\n"]
    parts.extend(f" DWORD {r['raw_flags']},{r['modifiers']},{r['state']},0\n" for r in m['rows'])
    return ''.join(parts)
