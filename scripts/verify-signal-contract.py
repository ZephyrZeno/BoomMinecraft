"""Independent declaration and initializer checks for a native VM contract."""
import hashlib,json,runpy,sys
from pathlib import Path
parser=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
parse=parser['parse']
record=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
c=record['contract'];data=Path(record['original_class']).read_bytes();classfile=parse(data)
assert c['origin']['loader']=='bootstrap' and c['origin']['source_id']=='jdk:java.base'
assert hashlib.sha256(data).hexdigest()==c['origin']['sha256']
assert classfile['access'] & 0x611 == 0x11
for name,desc in [('findSignal0','(Ljava/lang/String;)I'),('handle0','(IJ)J'),('raise0','(I)V')]:
    methods=[m for m in classfile['methods'] if m[1:3]==(name,desc)]
    assert len(methods)==1 and methods[0][0]==0x10a and not any(n=='Code' for n,_ in methods[0][3])
method=next(m for m in classfile['methods'] if m[1:3]==('<clinit>','()V'))
code=next(b for n,b in method[3] if n=='Code');n=int.from_bytes(code[4:8],'big')
assert hashlib.sha256(code[8:8+n]).hexdigest()==c['class_initializer_code_sha256']
method=next(m for m in classfile['methods'] if m[1:3]==('<init>','(Ljava/lang/String;)V'))
code=next(b for n,b in method[3] if n=='Code');n=int.from_bytes(code[4:8],'big');code=code[8:8+n]
assert method[0]==1 and n==95 and record['constructor_lookup_pc']==54 and code[54]==0xb8
constant=int.from_bytes(code[55:57],'big')
assert record['original_private_callsite_verified'] and record['constructor_lookup_constant']==constant
r=parser['Reader'](classfile['cp']);cp={};i=1
while i<classfile['count']:
    tag=r.u1()
    if tag==1: cp[i]=(tag,r.take(r.u2()).decode('utf-8',errors='replace'))
    elif tag in (7,8,16,19,20): cp[i]=(tag,r.u2())
    elif tag in (9,10,11,12,17,18): cp[i]=(tag,r.u2(),r.u2())
    elif tag in (3,4): r.take(4)
    elif tag in (5,6): r.take(8);i+=1
    elif tag==15: r.take(3)
    else: raise AssertionError('Unknown constant tag')
    i+=1
ref=cp[constant];assert ref[0]==10
owner=cp[ref[1]];name_type=cp[ref[2]]
assert owner[0]==7 and cp[owner[1]]==(1,'jdk/internal/misc/Signal')
assert name_type[0]==12 and cp[name_type[1]]==(1,'findSignal0') and cp[name_type[2]]==(1,'(Ljava/lang/String;)I')
assert c['labels']==[['ABRT',22],['FPE',8],['SEGV',11],['INT',2],['TERM',15],['BREAK',21],['ILL',4]]
assert c['native_access']==0x10a and c['native_descriptor']=='(Ljava/lang/String;)I'
assert c['platform']=='windows-x64' and c['unknown_result']==-1 and c['storage_abi']==3
assert record['inspection_only'] and not record['signal_class_initialization_executed']
assert not c['handler_registration_implemented'] and not record['handlers_installed']
print(json.dumps(dict(passed=True,private_native_declarations=3,initializer_Code_sha256_verified=True,original_private_constructor_callsite_verified=True,lookup_labels=7,inspection_only=True)))
