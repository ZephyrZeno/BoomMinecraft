"""Verify original public native Class.isInstance and each caller constant."""
import hashlib,json,sys
from pathlib import Path
helper=Path(__file__).with_name('verify-literal-regex.py');prefix=helper.read_text(encoding='utf-8').split('\np=load(sys.argv[1]);',1)[0]
ns={'__file__':str(helper)};exec(compile(prefix,str(helper),'exec'),ns)
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
p=load(sys.argv[1]);base_path=Path(sys.argv[2]);base=load(base_path);bindings=[b for b in p['class_queries']['bindings'] if b['kind']=='IsInstance'];assert bindings and not p['full_game_ready']
origin=base['classes']['java.lang.Class'];raw=(base_path.parent/'image/java.base/java/lang/Class.class').read_bytes();assert hashlib.sha256(raw).hexdigest()==origin['sha256']
c=ns['original'](raw);method=next(m for m in c['methods'] if m[1:3]==('isInstance','(Ljava/lang/Object;)Z'));assert method[0]==0x101 and 'Code' not in dict(method[3])
for binding in bindings:
 assert binding['origin']==origin
 source=next(s for s in p['sources'] if s['origin']==binding['caller']);raw=Path(source['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==binding['caller']['sha256']
 cp=ns['original'](raw)['constants'];tag,member=cp[binding['constant']];assert tag==10;nt=cp[member[1]][1]
 assert (cp[cp[member[0]][1]][1],cp[nt[0]][1],cp[nt[1]][1])==('java/lang/Class','isInstance','(Ljava/lang/Object;)Z')
print(json.dumps(dict(passed=True,original_native_declaration_verified=True,verified_calls=len(bindings),original_native_JVM_body_executed=False)))
