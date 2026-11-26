"""Raw classfile proof for frozen Constructor metadata, access and source factories."""
import hashlib,json,runpy,struct,sys
from pathlib import Path
h=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
parse,Reader=h['parse'],h['Reader']
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
p=load(sys.argv[1]);base=Path(sys.argv[2]);jdk=load(base);modules=Path(sys.argv[3]);snapshot=load(modules);plan=p['reflected_constructors'];catalog=plan['catalog'];types=p['mirror_types']
assert p['schema'] in (68,73) and not p['full_game_ready'] and plan['abi']==2
for flag in ('original_java_class_methods_executed','original_java_constructor_methods_executed','security_manager_supported','set_accessible_supported','generic_reflection_complete','reflective_stack_frames_complete','automatic_gc'):assert not plan[flag],flag
assert plan['vm_owned_constructor_layout']
assert sha(Path('native/runtime/reflect_constructors.asm').read_bytes())==plan['native_source_sha256']
module=snapshot['modules']['java.base'];assert plan['module_descriptor_sha256']==module['sha256'] and plan['module_snapshot_fingerprint']==snapshot['fingerprint']
assert sha((modules.parent/'image/java.base/module-info.class').read_bytes())==module['sha256']
sources={(s['origin']['loader'],s['origin']['binary_name']):s for s in p['sources'] if s.get('origin')};cache={}
def original(o):
 key=(o['loader'],o['binary_name'])
 if key in cache:return cache[key]
 raw=Path(sources[key]['path']).read_bytes() if key in sources else (base.parent/'image/java.base'/Path(o['binary_name'].replace('.','/')+'.class')).read_bytes()
 assert sha(raw)==o['sha256'];c=parse(raw);r=Reader(c['cp']);cp={};i=1
 while i<c['count']:
  tag=r.u1()
  if tag==1:value=r.take(r.u2()).decode('utf-8',errors='replace')
  elif tag in (7,8,16,19,20):value=r.u2()
  elif tag in (9,10,11,12,17,18):value=(r.u2(),r.u2())
  elif tag in (3,4):value=r.take(4)
  elif tag in (5,6):value=r.take(8)
  elif tag==15:value=(r.u1(),r.u2())
  else:raise AssertionError(tag)
  cp[i]=(tag,value);i+=2 if tag in (5,6) else 1
 c['constants']=cp;c['text']=lambda index:cp[index][1];c['class_name']=lambda index:cp[cp[index][1]][1];cache[key]=c;return c
def code(m):
 raw=next((v for n,v in m[3] if n=='Code'),None)
 return None if raw is None else raw[8:8+struct.unpack('>I',raw[4:8])[0]]
def names(desc):
 result=[];i=1
 while desc[i]!=')':
  start=i
  while desc[i]=='[':i+=1
  if desc[i]=='L':i=desc.index(';',i)+1
  else:i+=1
  part=desc[start:i];result.append(part[1:-1].replace('/','.') if part.startswith('L') else part.replace('/','.') if part.startswith('[') else {'Z':'boolean','B':'byte','C':'char','S':'short','I':'int','J':'long','F':'float','D':'double'}[part])
 return result
def typename(i):return ''.join(chr(u) for u in plan['type_names'][i])
records={(r['type_id'],r['slot']):r for r in catalog['records']};assert len(records)==len(catalog['records'])
for i,t in enumerate(types[:catalog['indexed_types']]):
 if t['kind']!='class':continue
 c=original(t['origin'])
 ctors=[(slot,m) for slot,m in enumerate(c['methods']) if m[1]=='<init>']
 assert sum(r['type_id']==i for r in records.values())==len(ctors)
 for slot,m in ctors:
  row=records[i,slot];attrs=dict(m[3]);body=code(m)
  assert row['source']==t['origin'] and row['modifiers']==m[0] and row['descriptor']==m[2]
  assert row['code_sha256']==(sha(body) if body is not None else None)
  assert [typename(t) for t in row['parameters']]==names(m[2])
  exceptions=[]
  if 'Exceptions' in attrs:
   r=Reader(attrs['Exceptions']);exceptions=[c['class_name'](r.u2()).replace('/','.') for _ in range(r.u2())]
  assert [typename(t) for t in row['exceptions']]==exceptions==[n.replace('/','.') for n in row['attributes']['exceptions']]
  sig=c['text'](struct.unpack('>H',attrs['Signature'])[0]) if 'Signature' in attrs else None
  assert row['signature']==sig==row['attributes']['signature']
  for key,attr in [('annotations','RuntimeVisibleAnnotations'),('parameter_annotations','RuntimeVisibleParameterAnnotations'),('type_annotations','RuntimeVisibleTypeAnnotations'),('parameters','MethodParameters')]:assert bytes(row['attributes'][key])==attrs.get(attr,b'')
  assert row['flags']==((1 if t['access']&0x400 else 0)|(2 if t['access']&0x4000 else 0))
for f in plan['constructors']:
 assert f['preserve_call_site'] and f['report_constructor_phase'] and not f.get('module_bootstrap',False)
 symbol=next(s for s in p['symbols'] if s['id']==f['method_id']);assert symbol['method']=='<init>' and symbol['class_name'].replace('/','.')==f['source']['binary_name']
 c=original(f['source']);slot=next(i for i,m in enumerate(c['methods']) if m[1:3]==('<init>',symbol['descriptor']))
 row=next(r for r in records.values() if r['source']==f['source'] and r['slot']==slot)
 assert row['helper']==f['helper_id'] and row['class_state']==f['class_id'] and len(f['signature']['arguments'])==len(row['parameters'])
# Verify direct call sites against original declarations (including inherited getters).
operation_names=['getDeclaredConstructor','getConstructor','newInstance','getDeclaringClass','getParameterTypes','getExceptionTypes','getModifiers','getParameterCount','isVarArgs','isSynthetic','getName','equals','hashCode']
for site in plan['sites']:
 b=site['binding'];c=original(b['caller']);tag,ref=c['constants'][b['constant']];assert tag==10
 nt=c['constants'][ref[1]][1];name=c['text'](nt[0]);desc=c['text'](nt[1]);decl=original(b['declaration']);m=next(m for m in decl['methods'] if m[1:3]==(name,desc))
 assert name=={'Declared':'getDeclaredConstructor','Public':'getConstructor','Invoke':'newInstance','DeclaringClass':'getDeclaringClass','Parameters':'getParameterTypes','Exceptions':'getExceptionTypes','Modifiers':'getModifiers','ParameterCount':'getParameterCount','VarArgs':'isVarArgs','Synthetic':'isSynthetic','Name':'getName','Equals':'equals','Hash':'hashCode','ToString':'toString'}[b['operation']]
 assert sha(code(m))==b['code_sha256'] and m[0]&0x109==1
 assert types[b['caller_type']]['origin']==b['access_caller'] and len(site['access'])==len(records)
print(json.dumps(dict(passed=True,raw_constructor_declarations=len(records),compiled_constructor_factories=len(plan['constructors']),verified_calls=len(plan['sites']),original_Class_and_Constructor_API_Java_bodies_executed=False,full_game_ready=False)))
