"""Independent raw record attributes, bootstrap getters and generated source checks."""
import hashlib,json,sys
from pathlib import Path
helper=Path(__file__).with_name('verify-literal-regex.py')
prefix=helper.read_text(encoding='utf-8').split('\np=load(sys.argv[1]);',1)[0]
ns={'__file__':str(helper)};exec(compile(prefix,str(helper),'exec'),ns)
Reader=ns['Reader'];original=ns['original']
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(data):return hashlib.sha256(data).hexdigest()
p=load(sys.argv[1]);base_path=Path(sys.argv[2]);base=load(base_path)
assert p['schema']==74 and p['record_sites'] and not p['full_game_ready']
sources={s['origin']['binary_name']:s for s in p['sources'] if s.get('origin')}
def raw(origin):
 source=sources.get(origin['binary_name'])
 if source:assert source['origin']==origin;data=Path(source['path']).read_bytes()
 else:
  assert origin==base['classes'][origin['binary_name']]
  data=(base_path.parent/'image/java.base'/Path(origin['binary_name'].replace('.','/')+'.class')).read_bytes()
 assert sha(data)==origin['sha256'];return original(data)
def member(cp,index):
 tag,value=cp[index];nt=cp[value[1]][1]
 return tag,cp[cp[value[0]][1]][1],cp[nt[0]][1],cp[nt[1]][1]
def bootstraps(c):
 reader=Reader(dict(c['attrs'])['BootstrapMethods']);result=[]
 for _ in range(reader.u2()):
  handle=reader.u2();result.append((handle,[reader.u2() for _ in range(reader.u2())]))
 assert reader.pos==len(reader.data);return result
for binding in p['record_sites']:
 plan=binding['plan'];assert plan['abi']==1 and not binding['original_object_methods_java_body_executed']
 c=raw(binding['caller']);cp=c['constants'];components=[]
 reader=Reader(dict(c['attrs'])['Record'])
 for _ in range(reader.u2()):
  name=cp[reader.u2()][1];desc=cp[reader.u2()][1]
  for _ in range(reader.u2()):reader.u2();reader.take(reader.u4())
  components.append((name,desc))
 assert reader.pos==len(reader.data) and c['access']&0x610==0x10
 assert cp[plan['site']][0]==18;bootstrap,nt=cp[plan['site']][1]
 assert (cp[cp[nt][1][0]][1],cp[cp[nt][1][1]][1])==('toString',plan['descriptor'])
 handle,args=bootstraps(c)[bootstrap];kind,reference=cp[handle][1]
 assert kind==6 and member(cp,reference)[1:3]==('java/lang/runtime/ObjectMethods','bootstrap');bootstrap_descriptor=member(cp,reference)[3]
 assert cp[cp[args[0]][1]][1]==plan['host']
 assert cp[cp[args[1]][1]][1]==';'.join(name for name,_ in components)
 assert len(args)==len(components)+2==len(plan['fields'])+2
 for (name,desc),index,field in zip(components,args[2:],plan['fields']):
  kind,reference=cp[index][1];assert kind==1 and member(cp,reference)==(9,plan['host'],name,desc)
  assert (field['reference_kind'],field['owner'],field['name'],field['descriptor'],field['interface'])==(1,plan['host'],name,desc,False)
 simple=plan['host'].rsplit('/',1)[-1]
 if 'InnerClasses' in dict(c['attrs']):
  reader=Reader(dict(c['attrs'])['InnerClasses'])
  for _ in range(reader.u2()):
   inner,outer,name,flags=[reader.u2() for _ in range(4)]
   if cp[cp[inner][1]][1]==plan['host']:assert name;simple=cp[name][1]
 assert simple==plan['simple_name']
 generated=raw(binding['generated']);gcp=generated['constants'];proof=binding['generated']['generated']
 assert proof['generator']=='boom-record' and proof['host_sha256']==binding['caller']['sha256'] and proof['site']==plan['site']
 assert generated['access']==0x1031 and generated['fields']==0 and len(generated['methods'])==1
 method=generated['methods'][0];assert method[:3]==(0x1009,'$apply',plan['descriptor']);body,_=ns['code'](method)
 reads=[member(gcp,int.from_bytes(body[pc+1:pc+3],'big')) for pc,_,_ in ns['instructions'](body) if body[pc]==0xb4]
 assert reads==[(9,plan['host'],name,desc) for name,desc in components]
 if components:
  _,arguments=bootstraps(generated)[0];recipe=gcp[gcp[arguments[0]][1]][1]
  assert recipe==simple+'['+', '.join(name+'=\x01' for name,_ in components)+']'
 else:assert body[0]==0x13 and gcp[gcp[int.from_bytes(body[1:3],'big')][1]][1]==simple+'[]'
 bootstrap=raw(binding['bootstrap'])
 methods=[m for m in bootstrap['methods'] if m[1]=='bootstrap' and m[2]==bootstrap_descriptor]
 assert len(methods)==1 and sha(ns['code'](methods[0])[0])==binding['bootstrap_code_sha256']
print(json.dumps(dict(passed=True,record_sites=len(p['record_sites']),Record_attributes_names_getters_and_generated_code_checked=True,original_ObjectMethods_Java_body_executed=False,full_game_ready=False)))
