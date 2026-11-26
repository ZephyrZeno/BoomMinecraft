"""Check reflected Field records and API callsites against original raw classfiles."""
import hashlib,json,runpy,sys
from pathlib import Path
h=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
def raw_fields(b):
 r=h['Reader'](b);r.take(8);n=r.u2();cp={};i=1
 while i<n:
  t=r.u1()
  if t==1:cp[i]=(t,r.take(r.u2()).decode('utf-8',errors='replace'))
  elif t in (7,8,16,19,20):cp[i]=(t,r.u2())
  elif t in (9,10,11,12,17,18):cp[i]=(t,r.u2(),r.u2())
  elif t in (3,4):r.take(4)
  elif t in (5,6):r.take(8);i+=1
  elif t==15:r.take(3)
  else:raise AssertionError(t)
  i+=1
 r.take(6);r.take(r.u2()*2);fs=[]
 for _ in range(r.u2()):
  fs.append((r.u2(),cp[r.u2()][1],cp[r.u2()][1]))
  for _ in range(r.u2()):r.take(2);r.take(r.u4())
 return cp,fs
def code_hash(method):
 code=next(b for n,b in method[3] if n=='Code');n=int.from_bytes(code[4:8],'big');return sha(code[8:8+n])
p=load(sys.argv[1]);base_path=Path(sys.argv[2]);base=load(base_path);plan=p['reflected_fields']
assert p['schema'] in (72,73,76) and plan['abi'] in (4,5) and plan['first_lookup_filter_snapshot'] and plan['vm_owned_field_layout'] and not plan['original_class_and_field_api_bodies_executed'] and not plan['class_initialization_triggered_by_lookup'] and not p['full_game_ready']
assert plan['native_source_sha256']==sha(Path('native/runtime/reflect_fields.asm').read_bytes())
cache={}
def original(o):
 key=(o['loader'],o['binary_name'],o['sha256'])
 if key in cache:return cache[key]
 matching=[s for s in p['sources'] if s['origin']==o]
 if matching:b=Path(matching[0]['path']).read_bytes()
 else:
  assert o['source_id']=='jdk:java.base' and o==base['classes'][o['binary_name']]
  b=(base_path.parent/'image/java.base'/Path(o['binary_name'].replace('.','/')+'.class')).read_bytes()
 assert sha(b)==o['sha256'];cache[key]=b;return b
primitive={'Boolean':'Z','Byte':'B','Char':'C','Short':'S','Int':'I','Long':'J','Float':'F','Double':'D','Void':'V'}
def descriptor(i):
 t=p['mirror_types'][i]
 if t['kind']=='primitive':return primitive[t['value']]
 if t['kind']=='array':return '['+descriptor(t['component'])
 return 'L'+t['key']['name']+';'
all_filtered={'jdk/internal/reflect/Reflection','java/lang/reflect/AccessibleObject','java/lang/ClassLoader','java/lang/reflect/Constructor','java/lang/reflect/Field','java/lang/reflect/Method','java/lang/Module'}
def filtered(o,n):return o in all_filtered or o=='java/lang/Class' and n in ('classLoader','classData') or o=='java/lang/System' and n=='security'
def jhash(text):
 b=text.encode('utf-16-le',errors='surrogatepass');v=0
 for i in range(0,len(b),2):v=(v*31+int.from_bytes(b[i:i+2],'little'))&0xffffffff
 return v
for r in plan['records']:
 b=original(r['source']);_,fs=raw_fields(b);flags,name,desc=fs[r['slot']]
 assert (flags,name,desc)==(r['modifiers'],r['name'],r['descriptor'])
 owner=p['mirror_types'][r['owner']];assert owner['origin']==r['source'] and r['owner']<plan['indexed_types']
 assert descriptor(r['field_type'])==desc
 width=1 if desc in ('B','Z') else 2 if desc in ('C','S') else 4 if desc in ('I','F') else 8
 assert width==r['width'] and filtered(owner['key']['name'],name)==r['filtered']
 assert jhash(owner['key']['name'].replace('/','.'))==r['owner_name_hash']
 literal=p['string_literals'][r['name_literal']]
 # Literal plans serialize their exact UTF16 code units.
 units=list(int.from_bytes(name.encode('utf-16-le')[i:i+2],'little') for i in range(0,len(name.encode('utf-16-le')),2))
 if isinstance(literal,list):assert literal==units
 else:assert literal.get('utf16',literal.get('units'))==units
 if r['class_state'] is not None:
  state=next(c for c in p['classes'] if c['id']==r['class_state']);assert flags&8 and state['name']==owner['key']['name']
  f=next(f for f in state['fields'] if f['index']==r['slot']);assert (f['name'],f['descriptor'])==(name,desc)
for row in plan['records']:
 if row.get('instance_map') is None:continue
 assert plan['abi']==5 and not row['modifiers']&8 and len(row['descriptor'])==1
 mapping=next(m for m in p['field_maps'] if m['id']==row['instance_map'])
 assert mapping['receiver_constraint']==row['owner'] and mapping['field_index']==row['slot']
 assert p['sources'][mapping['declaring_class']]['origin']==row['source']
 for receiver in mapping['rows']:
  layout=next(l for l in p['object_layouts'] if l['class_id']==receiver['receiver_class'])
  ty=p['mirror_types'][receiver['receiver_type']]
  assert ty['key']['name']==layout['class_name'] and p['sources'][receiver['receiver_class']]['origin']==ty['origin']
  field=next(f for f in layout['layout']['fields'] if f['declaring_class']==row['source']['binary_name'].replace('.','/') and f['declaring_field']==row['slot'])
  assert field['offset']==receiver['offset'] and field['descriptor']==row['descriptor'] and field['storage_bytes']==row['width']
  assert field['offset']>=layout['layout']['reference_prefix_fields']*8 and field['offset']+row['width']<=layout['layout']['payload_bytes']
for binding in plan['bindings']:
 b=original(binding['caller']);cp,_=raw_fields(b);ref=cp[binding['constant']];assert ref[0]==10
 owner=cp[cp[ref[1]][1]][1];nt=cp[ref[2]];name,desc=cp[nt[1]][1],cp[nt[2]][1]
 target=original(binding['declaration']);methods=h['parse'](target)['methods'];m=next(m for m in methods if m[1:3]==(name,desc));assert m[0]&0x109==1 and code_hash(m)==binding['code_sha256']
 assert owner==binding['declaration']['binary_name'].replace('.','/')
assert plan['filter_origin']['sha256']=='367e5447826f325e7952543ecb11983c3314217126a6a46238421e241eed2f34'
original(plan['filter_origin'])
print(json.dumps(dict(passed=True,raw_classes=len(cache),declared_field_records=len(plan['records']),original_API_callsites=len(plan['bindings']),field_slots_descriptors_widths_filters_and_static_cells_checked=True,original_API_bodies_executed=False)))
