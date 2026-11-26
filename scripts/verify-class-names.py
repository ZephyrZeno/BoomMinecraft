"""Verify naming rows against original InnerClasses/EnclosingMethod attributes."""
import hashlib,json,sys
from pathlib import Path
helper=Path(__file__).with_name('verify-literal-regex.py');prefix=helper.read_text(encoding='utf-8').split('\np=load(sys.argv[1]);',1)[0]
ns={'__file__':str(helper)};exec(compile(prefix,str(helper),'exec'),ns)
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
p=load(sys.argv[1]);base_path=Path(sys.argv[2]);classes=Path(sys.argv[3]);base=load(base_path)
plan=p['class_queries'];names=plan['names'];rows=names['rows'];types=p['mirror_types'];assert p['schema']==78 and len(rows)==len(types)==plan['type_count'] and not p['full_game_ready']
assert names['abi']==2 and not names['original_java_name_bodies_executed'] and plan['native_source_sha256']==sha(Path('native/runtime/class_queries.asm').read_bytes())
literals={v['id']:bytes().join(int(c).to_bytes(2,'little') for c in v['utf16']).decode('utf-16-le',errors='surrogatepass') for v in p['string_literals']}
sources={(s['origin']['loader'],s['origin']['binary_name']):Path(s['path']) for s in p['sources'] if s.get('origin')}
meta={}
for i,(row,t) in enumerate(zip(rows,types)):
 if t['kind']!='class':continue
 origin=t['origin'];assert row['origin']==origin
 path=sources.get((origin['loader'],origin['binary_name']))
 if path is None:path=(base_path.parent/'image' if origin['source_id']=='jdk:java.base' else classes)/origin['jar_entry']
 raw=path.read_bytes();assert sha(raw)==origin['sha256'];c=ns['original'](raw);cp=c['constants'];entry=False;simple=None;outer=None;local=False
 def cname(index):return cp[cp[index][1]][1]
 for name,body in c['attrs']:
  r=ns['Reader'](body)
  if name=='InnerClasses':
   for _ in range(r.u2()):
    inner,owner,label,flags=[r.u2() for _ in range(4)]
    if cname(inner)==t['key']['name']:entry=True;simple=cp[label][1] if label else '';outer=cname(owner) if owner else None
  if name=='EnclosingMethod':local=True
 parent=next((j for j,v in enumerate(types) if v['kind']=='class' and v['key']['loader']==t['key']['loader'] and v['key']['name']==outer),None) if outer else None
 assert row['declaring_type']==parent and row['local_or_anonymous']==(local or (entry and not simple))
 meta[i]=(entry,simple,local,parent)
memo={}
primitive=['boolean','byte','char','short','int','long','float','double','void']
def expected(i):
 if i in memo:return memo[i]
 t=types[i]
 if t['kind']=='primitive':value=t['value'].lower();result=(value,value)
 elif t['kind']=='array':canonical,simple=expected(t['component']);result=(canonical+'[]' if canonical is not None else None,simple+'[]')
 else:
  entry,simple,local,parent=meta[i];simple=simple if entry else t['key']['name'].rsplit('/',1)[-1]
  canonical=None if local or (entry and not simple) else (t['key']['name'].replace('/','.') if parent is None else (expected(parent)[0]+'.'+simple if expected(parent)[0] is not None else None))
  result=(canonical,simple)
 memo[i]=result;return result
for i,row in enumerate(rows):
 canonical,simple=expected(i);t=types[i];parent=row['declaring_type'];assert row['fresh_canonical']==(canonical is not None and (t['kind']=='array' or parent is not None));assert row['fresh_simple']==(bool(simple) and (t['kind']=='array' or (t['kind']=='class' and (meta[i][0] or '/' in t['key']['name']))));assert (literals[row['canonical']] if row['canonical'] is not None else None)==canonical and literals[row['simple']]==simple
print(json.dumps(dict(passed=True,verified_types=len(rows),raw_nesting_attributes_checked=True,original_Java_name_bodies_executed=False)))
