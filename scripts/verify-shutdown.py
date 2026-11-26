"""Independently verify native declarations, package caller and original halt lock."""
import hashlib,json,sys
from pathlib import Path
helper=Path(__file__).with_name('verify-literal-regex.py');prefix=helper.read_text(encoding='utf-8').split('\np=load(sys.argv[1]);',1)[0]
ns={'__file__':str(helper)};exec(compile(prefix,str(helper),'exec'),ns)
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
p=load(sys.argv[1]);base=Path(sys.argv[2]);jdk=load(base);plan=p['shutdown'];assert p['schema']==81 and plan['abi']==1 and not plan['jfr_supported'] and not p['full_game_ready']
origin=jdk['classes']['java.lang.Shutdown'];raw=(base.parent/'image/java.base/java/lang/Shutdown.class').read_bytes();assert sha(raw)==origin['sha256'] and plan['origin']==origin;c=ns['original'](raw)
for name,desc in [('beforeHalt','()V'),('halt0','(I)V')]:
 m=next(m for m in c['methods'] if m[1:3]==(name,desc));assert m[0]==0x108 and not any(n=='Code' for n,_ in m[3])
init=next(m for m in c['methods'] if m[1:3]==('<clinit>','()V'));assert sha(ns['code'](init)[0])==plan['initializer_code_sha256']
halt=next(m for m in c['methods'] if m[1:3]==('halt','(I)V'));code,tail=ns['code'](halt);assert code[5]==0xc2 and code[7]==0xb8 and code[11]==0xc3
bindings=plan['bindings'];assert bindings and all(b['caller']==origin for b in bindings)
for b in bindings:
 cp=c['constants'];tag,ref=cp[b['constant']];nt=cp[ref[1]][1];name,desc=cp[nt[0]][1],cp[nt[1]][1];assert tag==10 and cp[cp[ref[0]][1]][1]=='java/lang/Shutdown' and (name,desc)==('halt0','(I)V') and b['operation']=='Halt'
assert plan['native_source_sha256']==sha(Path('native/runtime/shutdown.asm').read_bytes())
symbols={(s['class_name'],s['method']) for s in p['symbols']};assert {('java/lang/Shutdown','halt'),('java/lang/Shutdown','<clinit>'),('java/lang/Shutdown$Lock','<init>')}.issubset(symbols)
print(json.dumps(dict(passed=True,original_halt_monitor_and_initializer_linked=True,native_declarations=2,JFR_supported=False)))
