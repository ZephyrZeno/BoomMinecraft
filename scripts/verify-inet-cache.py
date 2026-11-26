"""Verify cached JNI field names/types and independent compact layouts from raw classes."""
import json,hashlib,runpy,sys
from pathlib import Path
h=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')));parse=h['parse']
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
def raw_fields(raw):
 r=h['Reader'](raw);r.take(8);count=r.u2();names={};classes={};i=1
 while i<count:
  tag=r.u1()
  if tag==1:names[i]=r.take(r.u2()).decode('utf-8',errors='replace')
  elif tag in (3,4,9,10,11,12,17,18):r.take(4)
  elif tag in (5,6):r.take(8);i+=1
  elif tag==7:classes[i]=r.u2()
  elif tag in (8,16,19,20):r.take(2)
  elif tag==15:r.take(3)
  else:raise AssertionError(tag)
  i+=1
 r.take(4);parent=r.u2();r.take(r.u2()*2);fields=[]
 for _ in range(r.u2()):
  flags,name,desc=r.u2(),names[r.u2()],names[r.u2()]
  fields.append((flags,name,desc))
  for _ in range(r.u2()):r.take(2);r.take(r.u4())
 return fields, names[classes[parent]] if parent else None
p=load(sys.argv[1]);base=Path(sys.argv[2]);jdk=load(base);family=p['cache_family']
expected={0:[(0,'holder','Ljava/net/InetAddress$InetAddressHolder;'),(1,'address','I'),(1,'family','I'),(1,'hostName','Ljava/lang/String;'),(1,'originalHostName','Ljava/lang/String;')],4:[],6:[(0,'holder6','Ljava/net/Inet6Address$Inet6AddressHolder;'),(1,'ipaddress','[B'),(1,'scope_id','I'),(1,'scope_id_set','Z'),(1,'scope_ifname','Ljava/net/NetworkInterface;')]}[family]
names={0:('java.net.InetAddress','java.net.InetAddress$InetAddressHolder'),4:('java.net.Inet4Address','java.net.Inet4Address'),6:('java.net.Inet6Address','java.net.Inet6Address$Inet6AddressHolder')}[family]
assert p['abi']==(1 if family==0 else 2) and p['bootstrap_class_metadata_pinned'] and not p['runtime_jni_lookup_used'] and not p['network_backend_complete']
assert p['native_source_sha256']==sha(Path('native/runtime/inet_address.asm').read_bytes())
def locked_raw(name):
 raw=(base.parent/'image/java.base'/Path(name.replace('.','/')+'.class')).read_bytes()
 assert sha(raw)==jdk['classes'][name.replace('/','.')]['sha256'];return raw
def inherited_fields(name):
 fs,parent=raw_fields(locked_raw(name));result=inherited_fields(parent) if parent else []
 for index,f in enumerate(fs):
  if f[0]&8:continue
  d=f[2];ref=d.startswith(('L','['));width=8 if ref or d in ('J','D') else 4 if d in ('I','F') else 2 if d in ('C','S') else 1
  result.append(dict(index=index,name=f[1],descriptor=d,reference=ref,width=width,declaring=name))
 return result
layouts=[]
for i,name in enumerate(names):
 o=p['origins'][i];assert o==jdk['classes'][name];raw=locked_raw(name);c=parse(raw)
 if i==0:
  for member,desc in [('init','()V')]+([('isIPv4Available','()Z'),('isIPv6Supported','()Z')] if family==0 else []):
   m=next(m for m in c['methods'] if m[1:3]==(member,desc));assert m[0]==0x10a and not any(n=='Code' for n,_ in m[3])
  if family==0:
   f=raw_fields(raw)[0][p['prefer_ipv4_stack_field']];assert f==(0x1a,'PREFER_IPV4_STACK_VALUE','Ljava/lang/String;') and p['constructor'] is None
  else:
   ctor=p['constructor'];m=c['methods'][ctor['index']];assert m[0]==ctor['access']==0 and m[1:3]==('<init>','()V')
   code=next(b for n,b in m[3] if n=='Code');length=int.from_bytes(code[4:8],'big');assert sha(code[8:8+length])==ctor['code_sha256'] and not ctor['invoked_by_cache_initialization'] and p['prefer_ipv4_stack_field'] is None
 elif name!=names[0]:assert not any(m[1]=='<clinit>' for m in c['methods'])
 fields=inherited_fields(name.replace('.','/'))
 fields.sort(key=lambda f:(not f['reference'],-f['width']));cursor=0
 for f in fields:cursor=(cursor+f['width']-1)&-f['width'];f['offset']=cursor;cursor+=f['width']
 assert p['layouts'][i]==dict(payload_bytes=cursor,reference_prefix=sum(f['reference'] for f in fields),fields=len(fields));layouts.append(fields)
assert len(p['fields'])==len(expected)
for got,(owner,name,descriptor) in zip(p['fields'],expected):
 f=next(f for f in layouts[owner] if (f['declaring'],f['name'],f['descriptor'])==(names[owner].replace('.','/'),name,descriptor));f={k:v for k,v in f.items() if k!='declaring'};assert got==dict(owner=owner,**f)
print(json.dumps(dict(passed=True,cache_family=family,locked_classes=len(set(names)),cached_fields=len(expected),raw_native_declaration_checked=True,constructor_method_identity_checked=family!=0,compact_field_offsets_independently_checked=True,Java_class_initialization_executed=False,network_backend_complete=False)))
