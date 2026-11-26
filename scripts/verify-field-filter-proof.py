"""Independent constant-pool, bytecode, branch and handler checks for filter sites."""
import hashlib,json,sys
from pathlib import Path
# Reuse only the existing raw class/bytecode readers, before that script's main.
helper=Path(__file__).with_name('verify-literal-regex.py')
prefix=helper.read_text(encoding='utf-8').split('\np=load(sys.argv[1]);',1)
assert len(prefix)==2
ns={'__file__':str(helper)};exec(compile(prefix[0],str(helper),'exec'),ns)
record=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
raw=Path(record['source_path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==record['source_sha256'] and not record['execution_complete']
c=ns['original'](raw);cp=c['constants'];count=0
def member(index):
 tag,ref=cp[index];nt=cp[ref[1]][1]
 return tag,cp[cp[ref[0]][1]][1],cp[nt[0]][1],cp[nt[1]][1]
def constant(b,at):
 assert b[at] in (0x12,0x13)
 return b[at+1] if b[at]==0x12 else int.from_bytes(b[at+1:at+3],'big')
for p in record['proofs']:
 m=next(m for m in c['methods'] if m[1:3]==(p['method'],p['descriptor']));b,tail=ns['code'](m)
 assert hashlib.sha256(b).hexdigest()==p['code_sha256'] and p['alternative_entries_excluded']
 ins=list(ns['instructions'](b));pcs=[i[0] for i in ins];at=pcs.index(p['pc']);previous=pcs[at-4:at]
 assert len(previous)==4 and previous[0]==p['class_pc'] and previous[3]==p['set_pc']
 k=constant(b,previous[0]);assert k==p['class_constant'] and cp[k][0]==7 and cp[cp[k][1]][1]==p['containing_class']
 for i,pc in enumerate(previous[1:3]):
  k=constant(b,pc);assert k==p['name_constants'][i] and cp[k][0]==8
  text=cp[cp[k][1]][1];data=text.encode('utf-16-le',errors='surrogatepass');units=[int.from_bytes(data[j:j+2],'little') for j in range(0,len(data),2)];assert units==p['names'][i]
 assert b[p['set_pc']]==0xb8 and int.from_bytes(b[p['set_pc']+1:p['set_pc']+3],'big')==p['set_constant']
 assert member(p['set_constant'])==(11,'java/util/Set','of','(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Set;')
 assert b[p['pc']]==0xb8 and member(int.from_bytes(b[p['pc']+1:p['pc']+3],'big'))==(10,'jdk/internal/reflect/Reflection','registerFieldsToFilter','(Ljava/lang/Class;Ljava/util/Set;)V')
 for _,_,targets in ins:assert all(not p['class_pc']<t<=p['pc'] for t in targets)
 r=ns['Reader'](tail)
 for _ in range(r.u2()):
  start,end,target,catch=[r.u2() for _ in range(4)];assert not p['class_pc']<target<=p['pc']
 count+=1
assert count
print(json.dumps(dict(passed=True,constant_registration_sites=count,raw_operands_and_control_flow_checked=True,execution_complete=False)))
