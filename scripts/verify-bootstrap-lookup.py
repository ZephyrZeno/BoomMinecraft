"""Check the original private ClassLoader native and its Java caller provenance."""
import hashlib,json,runpy,sys
from pathlib import Path
helpers=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
p=load(sys.argv[1]);base=Path(sys.argv[2]);jdk=load(base);plan=p['class_for_name'];origin=jdk['classes']['java.lang.ClassLoader']
raw=(base.parent/'image/java.base/java/lang/ClassLoader.class').read_bytes();assert sha(raw)==origin['sha256'];c=helpers['parse'](raw)
native=next(m for m in c['methods'] if m[1:3]==('findBootstrapClass','(Ljava/lang/String;)Ljava/lang/Class;'));assert native[0]==0x10a and not any(n=='Code' for n,_ in native[3])
bindings=[b for b in plan['bindings'] if b['bootstrap_lookup']];assert p['schema']==79 and bindings and not p['full_game_ready']
assert plan['native_source_sha256']==sha(Path('native/runtime/class_for_name.asm').read_bytes())
source=next(s for s in p['sources'] if s['origin']==origin);assert Path(source['path']).read_bytes()==raw
for b in bindings:assert b['caller']==origin
assert any(s['class_name']=='java/lang/ClassLoader' and s['method']=='findBootstrapClassOrNull' for s in p['symbols'])
assert any(s['class_name']=='java/lang/ClassLoader' and s['method']=='checkName' for s in p['symbols'])
assert any(s['class_name']=='java/lang/ClassLoader' and s['method']=='<clinit>' for s in p['symbols'])
assert not any(s['class_name']=='java/lang/Class' and s['method']=='forName0' for s in p['symbols'])
print(json.dumps(dict(passed=True,private_native_call_sites=len(bindings),original_ClassLoader_wrapper_and_checkName_linked=True,bootstrap_lookup_does_not_request_target_initializers=True)))
