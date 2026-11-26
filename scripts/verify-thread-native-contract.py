"""Independently verify original class bytes and all declared Thread native rows."""
import hashlib,json,runpy,sys
from pathlib import Path
parser=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
p=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'));plan=p['thread_natives']
assert p['schema']==53 and not p['full_game_ready']
source=next(s for s in p['sources'] if s['class_name']=='java/lang/Thread')
raw=Path(source['path']).read_bytes();c=parser['parse'](raw)
assert hashlib.sha256(raw).hexdigest()==plan['origin']['sha256']==source['origin']['sha256']
assert plan['origin']['loader']=='bootstrap' and plan['origin']['source_id']=='jdk:java.base'
assert c['access']&0x601==1
for declaration in plan['declarations']:
    m=next(m for m in c['methods'] if m[1:3]==(declaration['name'],declaration['descriptor']))
    assert m[0]==declaration['access'] and not any(n=='Code' for n,_ in m[3])
register=next(m for m in c['methods'] if m[1:3]==('registerNatives','()V'))
assert register[0]==0x10a and not any(n=='Code' for n,_ in register[3])
init=next(m for m in c['methods'] if m[1:3]==('<clinit>','()V'))
body=next(b for n,b in init[3] if n=='Code');length=int.from_bytes(body[4:8],'big');code=body[8:8+length]
assert length==16 and code[0]==0xb8 and hashlib.sha256(code).hexdigest()==plan['class_initializer_code_sha256']
assert len(plan['declarations'])==18
assert {d['name'] for d in plan['declarations'] if d['implemented']}=={'yield0','currentThread','currentCarrierThread','getNextThreadIdOffset','ensureMaterializedForStackWalk'}
assert not plan['native_coverage_complete'] and plan['platform_threads_only'] and not plan['automatic_gc']
def constants(raw_class):
    parsed=parser['parse'](raw_class);r=parser['Reader'](parsed['cp']);cp={};i=1
    while i<parsed['count']:
        tag=r.u1()
        if tag==1:cp[i]=(tag,r.take(r.u2()).decode('utf-8',errors='replace'))
        elif tag in (7,8,16,19,20):cp[i]=(tag,r.u2())
        elif tag in (9,10,11,12,17,18):cp[i]=(tag,r.u2(),r.u2())
        elif tag in (3,4):r.take(4)
        elif tag in (5,6):r.take(8);i+=1
        elif tag==15:r.take(3)
        else:raise AssertionError('Unknown constant tag')
        i+=1
    return cp
methods={'Register':('registerNatives','()V'),'Current':('currentThread','()Ljava/lang/Thread;'),'Carrier':('currentCarrierThread','()Ljava/lang/Thread;'),'Yield':('yield0','()V'),'IdAddress':('getNextThreadIdOffset','()J'),'Materialize':('ensureMaterializedForStackWalk','(Ljava/lang/Object;)V')}
for binding in plan['bindings']:
    caller=next(s for s in p['sources'] if s['origin']==binding['caller'])
    data=Path(caller['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==binding['caller']['sha256']
    cp=constants(data);ref=cp[binding['constant']];assert ref[0]==10
    cls=cp[ref[1]];nt=cp[ref[2]]
    assert cls[0]==7 and cp[cls[1]]==(1,'java/lang/Thread') and nt[0]==12
    name,desc=methods[binding['operation']];assert cp[nt[1]]==(1,name) and cp[nt[2]]==(1,desc)
    if binding['operation'] in ('Register','Yield','Materialize'):assert binding['caller']==plan['origin']
print(json.dumps(dict(passed=True,original_native_declarations=19,registered_declarations=18,executable_registered_operations=5,initializer_Code_sha256_verified=True,callsite_constants_verified=len(plan['bindings']),full_native_coverage=False)))
