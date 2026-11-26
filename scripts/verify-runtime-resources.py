"""Original declarations, callers and allocator contracts for RUNT64."""
import hashlib,json,runpy,sys
from pathlib import Path
h=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=read(sys.argv[1]);base=Path(sys.argv[2]);jdk=read(base);plan=p['runtime_resources'];original=base.parent/'image/java.base/java/lang/Runtime.class';parsed=h['parse'](original.read_bytes())
assert p['schema']>=67 and plan['abi']==1 and not p['full_game_ready']
assert plan['origin']==jdk['classes']['java.lang.Runtime'] and digest(original)==plan['origin']['sha256']
assert plan['exact_runtime_receiver'] and not plan['override_dispatch_complete']
assert plan['policy']=='windows-default-group-and-job-affinity' and plan['queries_process_affinity'] and plan['queries_job_group_affinity']
assert not plan['guest_heap_allocation'] and not plan['automatic_gc']
assert plan['memory_counters']=='Heap1 committed capacity minus occupied block spans'
for key,file in [('native_source_sha256','runtime_resources.asm'),('heap_source_sha256','heap.asm'),('type_source_sha256','runtime_types.asm')]:assert plan[key]==digest(Path('native/runtime')/file)
methods={m[1:3]:m for m in parsed['methods']};members={'AvailableProcessors':('availableProcessors','()I'),'FreeMemory':('freeMemory','()J'),'TotalMemory':('totalMemory','()J'),'MaxMemory':('maxMemory','()J')}
for name,descriptor in members.values():
    m=methods[name,descriptor];assert m[0]==0x101 and not any(n=='Code' for n,_ in m[3])
assert all(m[0]==2 for m in parsed['methods'] if m[1]=='<init>')
sources={s['class_name']:s for s in p['sources']}
for b in plan['bindings']:
    s=sources[b['caller']['binary_name'].replace('.','/')];assert s['origin']==b['caller'] and digest(s['path'])==b['caller']['sha256']
    r=h['Reader'](Path(s['path']).read_bytes());r.take(8);n=r.u2();cp=[None]*n;i=1
    while i<n:
        tag=r.u1()
        if tag==1:cp[i]=r.take(r.u2()).decode('utf-8',errors='replace')
        elif tag in (7,8,16,19,20):cp[i]=(tag,r.u2())
        elif tag in (9,10,11,12,17,18):cp[i]=(tag,r.u2(),r.u2())
        elif tag in (3,4):r.take(4)
        elif tag in (5,6):r.take(8);i+=1
        elif tag==15:r.take(3)
        else:raise AssertionError(tag)
        i+=1
    ref=cp[b['constant']];assert ref[0]==10 and cp[cp[ref[1]][1]]=='java/lang/Runtime';pair=cp[ref[2]];assert (cp[pair[1]],cp[pair[2]])==members[b['operation']]
# Positive execution image must retain the actual original singleton construction.
if p['compilation']['method'] in ('count','memory'):
    assert sources['java/lang/Runtime']['origin']==plan['origin']
    symbols={(s['class_name'],s['method']) for s in p['symbols']}
    for name in ('getRuntime','<clinit>','<init>'):assert ('java/lang/Runtime',name) in symbols
print(json.dumps(dict(passed=True,bindings=len(plan['bindings']),original_native_declarations_verified=4,exact_Runtime_receiver_required=True,override_dispatch_complete=False,game_started=False)))
