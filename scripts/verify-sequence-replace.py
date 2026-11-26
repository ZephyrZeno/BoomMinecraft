"""Raw classfile binding and frozen CharSequence callback checks for VM replacement."""
import hashlib,json,runpy,struct,sys
from pathlib import Path
h=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')));parse,Reader=h['parse'],h['Reader']
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
def original(raw):
 c=parse(raw);r=Reader(c['cp']);cp={};i=1
 while i<c['count']:
  t=r.u1()
  if t==1:v=r.take(r.u2()).decode('utf-8',errors='replace')
  elif t in (7,8,16,19,20):v=r.u2()
  elif t in (9,10,11,12,17,18):v=(r.u2(),r.u2())
  elif t in (3,4):v=r.take(4)
  elif t in (5,6):v=r.take(8)
  elif t==15:v=(r.u1(),r.u2())
  else:raise AssertionError(t)
  cp[i]=(t,v);i+=2 if t in (5,6) else 1
 c['constants']=cp;return c

def code(m):
 b=next(v for n,v in m[3] if n=='Code');return b[8:8+struct.unpack('>I',b[4:8])[0]]
p=load(sys.argv[1]);base=Path(sys.argv[2]);jdk=load(base);path=base.parent/'image/java.base/java/lang/String.class';raw=path.read_bytes();assert sha(raw)==jdk['classes']['java.lang.String']['sha256'];string=original(raw);cp=string['constants']
member=next(m for m in string['methods'] if m[1:3]==('replace','(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;'));assert member[0]==1
assert p['schema']==70 and not p['full_game_ready']
plans=[v for v in p['string_join_plans'] if v['kind']=='Replace'];assert plans
sources={(s['origin']['loader'],s['origin']['binary_name']):s for s in p['sources'] if s.get('origin')}
# These plans share the established AOT interface dispatcher, not a host callback.
sites={s['id']:s for s in p['interface_dispatch']}
for v in plans:
 assert v['origin']==jdk['classes']['java.lang.String'] and v['source_method']=='replace' and v['code_sha256']==sha(code(member))
 assert not v['original_java_api_body_executed'] and v['literal_role']=='empty'
 assert v['native_source_sha256']==sha(Path('native/runtime/string_join.asm').read_bytes()+Path('native/runtime/string_sequence_replace.asm').read_bytes())
 assert len(v['dispatch_sites'])==1
 d=sites[v['dispatch_sites'][0]];assert d['owner']=='java/lang/CharSequence' and d['name']=='toString' and d['descriptor']=='()Ljava/lang/String;' and d['interface']
 assert p['mirror_types'][v['char_sequence_type']]['key']==dict(loader='bootstrap',name='java/lang/CharSequence')
 o=v['caller'];raw=Path(sources[o['loader'],o['binary_name']]['path']).read_bytes();assert sha(raw)==o['sha256'];c=original(raw);cpc=c['constants'];tag,ref=cpc[v['constant']];assert tag==10
 assert cpc[cpc[ref[0]][1]][1]=='java/lang/String';nt=cpc[ref[1]][1];assert (cpc[nt[0]][1],cpc[nt[1]][1])==('replace','(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;')
# Independently bind the package-only coder operation to its locked field getter.
coder=next(m for m in string['methods'] if m[1:3]==('coder','()B'));b=code(coder);assert coder[0]==0 and len(b)==15 and b[0]==0xb2 and b[3:8]==bytes([0x99,0,10,0x2a,0xb4]) and b[10:]==bytes([0xa7,0,4,4,0xac])
index=struct.unpack_from('>H',b,8)[0];tag,ref=cp[index];assert tag==9 and cp[cp[ref[0]][1]][1]=='java/lang/String';nt=cp[ref[1]][1];assert (cp[nt[0]][1],cp[nt[1]][1])==('coder','B')
print(json.dumps(dict(passed=True,verified_API_bindings=len(plans),original_CharSequence_Java_API_body_executed=False,original_toString_callbacks_AOT_bound=True,private_coder_source_contract_verified=True,game_started=False)))
