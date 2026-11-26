"""Independent source, identity, collision, and initialization proof for FNAM96."""
import hashlib,json,runpy,sys
from pathlib import Path
helpers=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
p=read(sys.argv[1]);base=Path(sys.argv[2]);jdk=read(base);modules=read(sys.argv[3]);plan=p['class_for_name'];types=p['mirror_types'];keys=p['class_loaders']['keys']
assert p['schema']>=65 and not p['full_game_ready'] and plan['abi']==1
assert plan['vm_metadata_fixture'] and plan['bindings']==[]
assert not any(plan[k] for k in ['dynamic_class_definition_complete','dynamic_array_metadata_complete','security_manager_supported','automatic_gc'])
assert plan['origin']==jdk['classes']['java.lang.Class'] and plan['module_fingerprint']==modules['fingerprint']
assert plan['native_source_sha256']==sha(Path('native/runtime/class_for_name.asm').read_bytes())
raw=(base.parent/'image/java.base/java/lang/Class.class').read_bytes();assert sha(raw)==plan['origin']['sha256']
method=next(m for m in helpers['parse'](raw)['methods'] if m[1:3]==('forName0',plan['descriptor']))
assert method[0]==0x10a and not any(n=='Code' for n,_ in method[3])
source={(s['origin']['loader'],s['class_name']):s for s in p['sources'] if s.get('origin')}
cache={}
def definition(i):
    t=types[i];o=t['origin'];key=(t['key']['loader'],t['key']['name'])
    if key not in cache:
        if key in source:
            s=source[key];assert s['origin']==o;raw=Path(s['path']).read_bytes()
        else:
            assert o['source_id'].startswith('jdk:');module=o['source_id'].split(':',1)[1]
            raw=(base.parent/'image'/module/(t['key']['name']+'.class')).read_bytes()
        assert sha(raw)==o['sha256'];cache[key]=helpers['parse'](raw)
    return cache[key]
primitive={'Boolean':'boolean','Byte':'byte','Char':'char','Short':'short','Int':'int','Long':'long','Float':'float','Double':'double','Void':'void'}
codes={'boolean':'Z','byte':'B','char':'C','short':'S','int':'I','long':'J','float':'F','double':'D'}
def name(i):
    t=types[i]
    if t['kind']=='class':return t['key']['name'].replace('/','.')
    if t['kind']=='primitive':return primitive[t['value']]
    component=types[t['component']];n=name(t['component'])
    return '['+('L'+n+';' if component['kind']=='class' else n if component['kind']=='array' else codes[n])
def loader(i):
    t=types[i]
    return t['key']['loader'] if t['kind']=='class' else 'bootstrap' if t['kind']=='primitive' else loader(t['component'])
rows=plan['catalog'];assert rows==sorted(rows,key=lambda r:(r['initiator'],r['hash'],r['name']))
assert len({(r['initiator'],r['name']) for r in rows})==len(rows)
index={}
for r in rows:
    h=0
    units=r['name'].encode('utf-16-le',errors='surrogatepass')
    for i in range(0,len(units),2):h=(h*31+int.from_bytes(units[i:i+2],'little'))&0xffffffff
    assert h==r['hash'] and 0<=r['initiator']<len(keys) and r['array']==r['name'].startswith('[')
    assert '$$BoomJdk$' not in r['name'] and '$$BoomLambda$' not in r['name']
    if keys[r['initiator']]=='bootstrap':assert r['defining_loader']=='bootstrap'
    if r['type_id'] is not None:assert name(r['type_id'])==r['name'] and loader(r['type_id'])==r['defining_loader']
    index[keys[r['initiator']],r['name']]=r
app='explicit-application';a=index[app,'dev.boom.lookup.Aa'];b=index[app,'dev.boom.lookup.BB'];assert a['hash']==b['hash'] and a['type_id']!=b['type_id']
assert ('bootstrap','dev.boom.lookup.Aa') not in index
assert index[app,'java.lang.String']['defining_loader']=='bootstrap'
assert index[app,'[Ldev.boom.lookup.ArrayTarget;']['type_id'] is not None
nodes=plan['initializers'];symbols={(s['class_name'],s['method']) for s in p['symbols']}
def defaults(i,seen,result):
    if i in seen:return
    seen.add(i);t=types[i]
    for parent in t['interfaces']:defaults(parent,seen,result)
    if any(n not in ('<init>','<clinit>') and access&0x40a==0 for access,n,d,attrs in definition(i)['methods']):result.append(i)
slots=[]
for i,n in enumerate(nodes):
    if types[i]['kind']!='class':assert n is None;continue
    assert n['type_id']==i;t=types[i];c=definition(i)
    own=any(m[1]=='<clinit>' for m in c['methods']);assert n['linked_body']==(not own or (t['key']['name'],'<clinit>') in symbols)
    deps=[]
    if not t['access']&0x200:
        if t['superclass'] is not None:deps.append(t['superclass'])
        seen=set()
        for parent in t['interfaces']:defaults(parent,seen,deps)
    assert n['dependencies']==deps and n['ready']==(n['linked_body'] and all(nodes[d]['ready'] for d in deps))
    if n['synthetic_slot'] is not None:slots.append(n['synthetic_slot'])
assert sorted(slots)==list(range(plan['synthetic_roots']))
print(json.dumps(dict(passed=True,catalog_rows=len(rows),source_classes=len(cache),source_native_declaration_verified=True,hash_collisions_retained=True,initialization_dependencies_source_verified=True,source_class_forName_Java_executed=False,VM_metadata_fixture=True,game_started=False)))
