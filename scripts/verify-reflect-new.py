"""Independent raw classfile checks for constructor bodies and access decisions."""
import hashlib,json,runpy,struct,sys
from pathlib import Path
helpers=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
parse,Reader=helpers['parse'],helpers['Reader']
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
p=load(sys.argv[1]);base=Path(sys.argv[2]);jdk=load(base);modules=Path(sys.argv[3]);snapshot=load(modules);plan=p['reflect_new']
assert p['schema']>=64 and not p['full_game_ready'] and plan['abi']==1
assert not plan['original_java_class_method_executed'] and not plan['dynamic_class_loading_complete'] and not plan['automatic_gc']
assert not plan['reflective_stack_frames_complete'] and not plan['security_manager_supported']
assert plan['class_origin']==jdk['classes']['java.lang.Class']
module=snapshot['modules']['java.base'];assert plan['module_descriptor_sha256']==module['sha256']
assert plan['module_snapshot_fingerprint']==snapshot['fingerprint']
assert sha((modules.parent/'image/java.base/module-info.class').read_bytes())==module['sha256']
sources={(s['origin']['loader'],s['origin']['binary_name']):s for s in p['sources'] if s.get('origin')}
cache={}
def original(origin):
    key=(origin['loader'],origin['binary_name'])
    if key in cache:return cache[key]
    if key in sources:raw=Path(sources[key]['path']).read_bytes()
    else:
        assert origin['source_id']=='jdk:java.base'
        raw=(base.parent/'image/java.base'/Path(origin['binary_name'].replace('.','/')+'.class')).read_bytes()
    assert sha(raw)==origin['sha256']
    c=parse(raw);r=Reader(c['cp']);cp={};i=1
    while i<c['count']:
        tag=r.u1()
        if tag==1:v=r.take(r.u2()).decode('utf-8',errors='replace')
        elif tag in (7,8,16,19,20):v=r.u2()
        elif tag in (9,10,11,12,17,18):v=(r.u2(),r.u2())
        elif tag in (3,4):v=r.take(4)
        elif tag in (5,6):v=r.take(8)
        elif tag==15:v=(r.u1(),r.u2())
        else:raise AssertionError('Unknown constant')
        cp[i]=(tag,v);i+=2 if tag in (5,6) else 1
    def class_name(index):return cp[cp[index][1]][1]
    c['constants']=cp;c['class_name']=class_name
    cache[key]=c;return c
def code(method):
    raw=next(b for n,b in method[3] if n=='Code');return raw[8:8+struct.unpack('>I',raw[4:8])[0]]
cls=original(plan['class_origin']);m=next(m for m in cls['methods'] if m[1:3]==('newInstance','()Ljava/lang/Object;'))
assert m[0]==1 and sha(code(m))==plan['original_code_sha256']
assert sha(Path('native/runtime/reflect_new.asm').read_bytes())==plan['native_source_sha256']
types=p['mirror_types'];class_id=plan['class_type'];assert types[class_id]['key']['name']=='java/lang/Class'
by_name={(t['key']['loader'],t['origin']['binary_name']):t for t in types if t['kind']=='class'}
def nest(t):
    o=t['origin'];own=o['binary_name'];c=original(o);host=next((b for n,b in c['attrs'] if n=='NestHost'),None)
    if not host:return own
    name=c['class_name'](struct.unpack('>H',host)[0]).replace('/','.')
    h=by_name.get((o['loader'],name))
    if not h or name.rpartition('.')[0]!=own.rpartition('.')[0]:return own
    hc=original(h['origin']);members=next((b for n,b in hc['attrs'] if n=='NestMembers'),None)
    if not members:return own
    r=Reader(members);names=[hc['class_name'](r.u2()).replace('/','.') for _ in range(r.u2())]
    return name if own in names else own
symbols={s['id']:s for s in p['symbols']};factories={}
for f in plan['constructors']:
    assert f['abi']==1 and f['signature']['arguments']==[] and f['preserve_call_site'] and not f.get('module_bootstrap',False)
    s=symbols[f['method_id']];assert next(c['name'] for c in p['classes'] if c['id']==f['class_id'])==s['class_name'] and s['class_name'].replace('/','.')==f['source']['binary_name'] and s['method']=='<init>' and s['descriptor']=='()V'
    c=original(f['source']);ctor=next(m for m in c['methods'] if m[1:3]==('<init>','()V'));assert code(ctor)
    factories[f['helper_id']]=f
decisions=0
for site in plan['sites']:
    b=site['binding'];caller=types[b['caller_type']];assert caller['origin']==b['access_caller']
    c=original(b['caller']);cp=c['constants'];tag,ref=cp[b['constant']];assert tag==10
    owner=c['class_name'](ref[0]);nt=cp[ref[1]][1]
    assert (owner,cp[nt[0]][1],cp[nt[1]][1])==('java/lang/Class','newInstance','()Ljava/lang/Object;')
    assert len(site['rows'])==len(types)
    for i,row in enumerate(site['rows']):
        assert row['type_id']==i;t=types[i];expected=1
        if t['kind']=='class':
            c=original(t['origin']);ctor=next((m for m in c['methods'] if m[1:3]==('<init>','()V')),None)
            if i==class_id:expected=2
            elif ctor:
                co,to=caller['origin'],t['origin'];same=co['loader']==to['loader'] and co['binary_name'].rpartition('.')[0]==to['binary_name'].rpartition('.')[0]
                allowed=i==b['caller_type']
                if not allowed:
                    exported=to['source_id']!='jdk:java.base' or co['source_id']=='jdk:java.base' or any(e['package']==to['binary_name'].rpartition('.')[0].replace('.','/') and not e['targets'] for e in module['descriptor']['exports'])
                    allowed=exported and bool(t['access']&1 or same) and bool(ctor[0]&1 or (ctor[0]&2 and same and nest(caller)==nest(t)) or (not ctor[0]&2 and same))
                expected=2 if not allowed else 3 if t['access']&0x400 else 0 if any(f['source']==to for f in factories.values()) else 4
        assert row['action']==expected,(b['caller']['binary_name'],i,row['action'],expected)
        if expected==0:assert factories[row['constructor_helper']]['source']==t['origin']
        else:assert row.get('constructor_helper') is None
        decisions+=1
print(json.dumps(dict(passed=True,access_rows_checked=decisions,original_constructor_bodies=len(factories),original_Class_Java_body_executed=False,unlinked_bodies_are_explicit=True,dynamic_class_loading_complete=False,game_started=False)))
