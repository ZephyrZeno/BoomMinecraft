"""Independently validate AOT literal operands, control-flow exclusion and JDK origins."""
import json,hashlib,runpy,struct,sys
from pathlib import Path
h=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')));Reader,parse=h['Reader'],h['parse']
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
def original(raw):
 c=parse(raw);r=Reader(c['cp']);cp={};i=1
 while i<c['count']:
  t=r.u1()
  if t==1:v=r.take(r.u2()).replace(b'\xc0\x80',b'\0').decode('utf-8',errors='surrogatepass')
  elif t in (7,8,16,19,20):v=r.u2()
  elif t in (9,10,11,12,17,18):v=(r.u2(),r.u2())
  elif t in (3,4):v=r.take(4)
  elif t in (5,6):v=r.take(8)
  elif t==15:v=(r.u1(),r.u2())
  else:raise AssertionError(t)
  cp[i]=(t,v);i+=2 if t in (5,6) else 1
 c['constants']=cp;return c

def instructions(b):
 pc=0
 while pc<len(b):
  at=pc;op=b[pc];targets=[]
  if op in (0xaa,0xab):
   base=(pc+4)&~3;v=lambda i:struct.unpack_from('>i',b,i)[0];targets=[pc+v(base)]
   if op==0xaa:
    count=v(base+8)-v(base+4)+1;targets +=[pc+v(base+12+4*i) for i in range(count)];pc=base+12+4*count
   else:
    count=v(base+4);targets +=[pc+v(base+12+8*i) for i in range(count)];pc=base+8+8*count
  elif op==0xc4:pc+=6 if b[pc+1]==0x84 else 4
  elif op in (0xb9,0xba,0xc8,0xc9):
   if op in (0xc8,0xc9):targets=[pc+struct.unpack_from('>i',b,pc+1)[0]]
   pc+=5
  elif op==0xc5:pc+=4
  elif op in (0x10,0x12,0xa9,0xbc) or 0x15<=op<=0x19 or 0x36<=op<=0x3a:pc+=2
  elif op in (0x11,0x13,0x14,0x84,0xc6,0xc7) or 0x99<=op<=0xa8 or 0xb2<=op<=0xb8 or op in (0xbb,0xbd,0xc0,0xc1):
   if 0x99<=op<=0xa8 or op in (0xc6,0xc7):targets=[pc+struct.unpack_from('>h',b,pc+1)[0]]
   pc+=3
  else:assert op<=0xc3;pc+=1
  assert pc<=len(b);yield at,pc,targets

def code(m):
 raw=next(v for n,v in m[3] if n=='Code');n=struct.unpack_from('>I',raw,4)[0];return raw[8:8+n],raw[8+n:]
p=load(sys.argv[1]);base=Path(sys.argv[2]);jdk=load(base);bindings=p['literal_regex_replacements'];assert p['schema']==69 and not p['full_game_ready'] and bindings
source={(s['origin']['loader'],s['origin']['binary_name']):s for s in p['sources'] if s.get('origin')}
string_origin=jdk['classes']['java.lang.String'];string_raw=(base.parent/'image/java.base/java/lang/String.class').read_bytes();assert sha(string_raw)==string_origin['sha256'];string=original(string_raw)
wide=0;decisions=0
for bind in bindings:
 assert bind['abi']==1 and bind['string_origin']==string_origin and not bind['original_replace_all_java_body_executed'] and not bind['regex_engine_complete']
 assert bind['native_source_sha256']==sha(Path('native/runtime/string_replace.asm').read_bytes())
 for name,desc,key in [('replaceAll','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;','replace_all_code_sha256'),('replace','(CC)Ljava/lang/String;','char_replace_code_sha256')]:
  m=next(m for m in string['methods'] if m[1:3]==(name,desc));assert m[0]==1 and sha(code(m)[0])==bind[key]
 o=bind['caller'];raw=Path(source[o['loader'],o['binary_name']]['path']).read_bytes();assert sha(raw)==o['sha256'];c=original(raw);cp=c['constants'];proof=bind['proof'];m=next(m for m in c['methods'] if m[1:3]==(proof['method'],proof['descriptor']));b,tail=code(m);assert sha(b)==proof['code_sha256'] and proof['branch_and_handler_entries_excluded']
 ins=list(instructions(b));pcs=[i[0] for i in ins];i=pcs.index(proof['pc']);assert pcs[i-2:i]==[proof['pattern_pc'],proof['replacement_pc']]
 values=[]
 for field,at in [('pattern_constant',proof['pattern_pc']),('replacement_constant',proof['replacement_pc'])]:
  assert b[at] in (0x12,0x13);index=b[at+1] if b[at]==0x12 else struct.unpack_from('>H',b,at+1)[0];assert index==proof[field];wide+=b[at]==0x13
  assert cp[index][0]==8;text=cp[cp[index][1]][1];data=text.encode('utf-16-le',errors='surrogatepass');assert len(data)==2;values.append(int.from_bytes(data,'little'))
 old,new=values;assert old==proof['old'] and new==proof['new'] and old!=new and not 0xd800<=old<=0xdfff and chr(old) not in '.^$*+?{}[]\\|()' and new not in (36,92)
 assert b[proof['pc']]==0xb6 and struct.unpack_from('>H',b,proof['pc']+1)[0]==bind['constant']
 tag,ref=cp[bind['constant']];assert tag==10;assert cp[cp[ref[0]][1]][1]=='java/lang/String';nt=cp[ref[1]][1];assert (cp[nt[0]][1],cp[nt[1]][1])==('replaceAll','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;')
 for _,_,targets in ins:assert all(not proof['pattern_pc']<t<=proof['pc'] for t in targets)
 r=Reader(tail)
 for _ in range(r.u2()):
  start,end,target,catch=[r.u2() for _ in range(4)];assert not proof['pattern_pc']<target<=proof['pc']
 decisions+=1
assert wide>0,'ldc_w fixture did not exercise wide constants'
print(json.dumps(dict(passed=True,verified_call_sites=decisions,wide_literal_operands=wide,control_flow_and_handlers_independently_checked=True,regex_engine_complete=False,game_started=False)))
