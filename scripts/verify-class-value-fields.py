"""Check the Class-owned field, original ClassValue accessor, and GC layout."""
import hashlib,json,sys
from pathlib import Path
helper=Path(__file__).with_name('verify-literal-regex.py');prefix=helper.read_text(encoding='utf-8').split('\np=load(sys.argv[1]);',1)[0]
ns={'__file__':str(helper)};exec(compile(prefix,str(helper),'exec'),ns)
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
p=load(sys.argv[1]);base=Path(sys.argv[2]);jdk=load(base);plan=p['class_queries'];sidecar=plan['class_value_map'];types=p['mirror_types'];assert p['schema']==80 and sidecar['abi']==1 and not p['full_game_ready']
assert types[sidecar['value_type']]['key']==dict(loader='bootstrap',name='java/lang/ClassValue$ClassValueMap')
assert plan['native_source_sha256']==sha(Path('native/runtime/class_queries.asm').read_bytes())
sources={s['class_name']:s for s in p['sources']}
for name in ['java/lang/Class','java/lang/ClassValue','java/lang/ClassValue$ClassValueMap']:
 origin=jdk['classes'][name.replace('/','.')];raw=(base.parent/'image/java.base'/(name+'.class')).read_bytes();assert sha(raw)==origin['sha256']
 if name in sources:assert sources[name]['origin']==origin and Path(sources[name]['path']).read_bytes()==raw
 if name=='java/lang/Class':clazz=ns['original'](raw)
 if name=='java/lang/ClassValue':value=ns['original'](raw);value_origin=origin
 if name.endswith('$ClassValueMap'):mapping=ns['original'](raw)
m=next(m for m in value['methods'] if m[1:3]==('getCacheCarefully','(Ljava/lang/Class;)[Ljava/lang/ClassValue$Entry;'));body,tail=ns['code'](m);assert m[0]==10 and body[:2]==b'\x2a\xb4'
cp=value['constants'];constant=int.from_bytes(body[2:4],'big');tag,ref=cp[constant];nt=cp[ref[1]][1];assert tag==9 and cp[cp[ref[0]][1]][1]=='java/lang/Class' and (cp[nt[0]][1],cp[nt[1]][1])==('classValueMap','Ljava/lang/ClassValue$ClassValueMap;')
bindings=[b for b in plan['bindings'] if b['kind']=='ClassValueLoad'];assert bindings and all(b['caller']==value_origin and b['constant']==constant for b in bindings)
symbols={(s['class_name'],s['method']) for s in p['symbols']};assert ('java/lang/ClassValue','getCacheCarefully') in symbols and ('java/lang/ClassValue$ClassValueMap','getCache') in symbols
layout=next(v['layout'] for v in p['object_layouts'] if v['class_name']=='java/lang/ClassValue$ClassValueMap');field=next(f for f in layout['fields'] if f['name']=='cacheArray' and f['declaring_class']=='java/lang/ClassValue$ClassValueMap');assert field['descriptor']=='[Ljava/lang/ClassValue$Entry;' and field['offset']+8<=layout['reference_prefix_fields']*8
print(json.dumps(dict(passed=True,read_call_sites=len(bindings),original_Java_accessors_linked=True,cache_field_in_GC_reference_prefix=True)))
