"""Source-bound proof for empty Object.wait-set notification lowering."""
import hashlib,json,runpy,sys
from pathlib import Path
helpers=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=read(sys.argv[1]);base=Path(sys.argv[2]);jdk=read(base);original=base.parent/'image/java.base/java/lang/Object.class'
assert sha(original)==jdk['classes']['java.lang.Object']['sha256']
methods=helpers['parse'](original.read_bytes())['methods'];bindings=p['monitor_notifications']
assert p['schema']==66 and bindings and not p['full_game_ready']
assert {b['method'] for b in bindings}=={'notify','notifyAll'} or {b['method'] for b in bindings}=={'notifyAll'}
sources={s['class_name']:s for s in p['sources']}
for b in bindings:
    assert not b['wait_sets_supported'] and b['source_sha256']==sha('native/runtime/monitors.asm')
    assert b['origin']==jdk['classes']['java.lang.Object']
    m=next(m for m in methods if m[1:3]==(b['method'],'()V'));assert m[0]==0x111 and not any(n=='Code' for n,_ in m[3])
    caller=sources[b['caller']['binary_name'].replace('.','/')];assert caller['origin']==b['caller'] and sha(caller['path'])==b['caller']['sha256']
    # Parse CP separately, independent of the compiler's classfile parser.
    r=helpers['Reader'](Path(caller['path']).read_bytes());r.take(8);n=r.u2();cp=[None]*n;i=1
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
    ref=cp[b['constant']];assert ref[0]==10;pair=cp[ref[2]];assert pair[0]==12 and (cp[pair[1]],cp[pair[2]])==(b['method'],'()V')
print(json.dumps(dict(passed=True,source_native_bindings=len(bindings),original_native_declarations_verified=True,empty_wait_sets_only=True,Object_wait_implemented=False,game_started=False)))
