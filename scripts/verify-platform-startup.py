"""Independent classfile proof for Windows startup native declarations/call sites."""
import hashlib,json,runpy,sys
from pathlib import Path
parser=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def constants(raw):
    p=parser['parse'](raw);r=parser['Reader'](p['cp']);cp={};i=1
    while i<p['count']:
        tag=r.u1()
        if tag==1:cp[i]=(tag,r.take(r.u2()).decode('utf-8',errors='replace'))
        elif tag in (7,8,16,19,20):cp[i]=(tag,r.u2())
        elif tag in (9,10,11,12,17,18):cp[i]=(tag,r.u2(),r.u2())
        elif tag in (3,4):r.take(4)
        elif tag in (5,6):r.take(8);i+=1
        elif tag==15:r.take(3)
        else:raise AssertionError('Unknown constant tag')
        i+=1
    return cp
inspection=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
assert inspection['inspection_only'] and not inspection['signal_class_initialization_executed'] and not inspection['handlers_installed']
assert inspection['control_binding_class_id_is_inspection_placeholder']
raw=Path(inspection['original_class']).read_bytes();c=parser['parse'](raw);cp=constants(raw)
assert digest(inspection['original_class'])==inspection['contract']['origin']['sha256']
assert len(inspection['control_callsite_bindings'])==2
members={'Handle':('handle0','(IJ)J','handle',40),'Raise':('raise0','(I)V','raise',48)}
for b in inspection['control_callsite_bindings']:
    name,desc,caller,pc=members[b['operation']]
    assert b['origin']==b['caller']==inspection['contract']['origin'] and not b['java_dispatch_integrated']
    assert b['requires_bound_transport'] and b['windows_policy']=='normal' and not b['automatic_gc']
    assert b['native_source_sha256']==digest('native/runtime/signal_natives.asm')
    assert b['transport_source_sha256']==digest('native/runtime/signal_control.asm')
    method=next(m for m in c['methods'] if m[1:3]==(name,desc));assert method[0]==0x10a and not any(n=='Code' for n,_ in method[3])
    method=next(m for m in c['methods'] if m[1]==caller);code=next(v for n,v in method[3] if n=='Code');body=code[8:8+int.from_bytes(code[4:8],'big')]
    assert body[pc]==0xb8 and int.from_bytes(body[pc+1:pc+3],'big')==b['constant']
    ref=cp[b['constant']];owner=cp[ref[1]];nt=cp[ref[2]]
    assert ref[0]==10 and cp[owner[1]]==(1,'jdk/internal/misc/Signal') and cp[nt[1]]==(1,name) and cp[nt[2]]==(1,desc)
p=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8-sig'));plan=p['windows_startup']
assert p['schema']==56 and not p['full_game_ready'] and plan['abi']==1
assert plan['native_source_sha256']==digest('native/runtime/windows_startup.asm') and plan['mutates_process_error_mode'] and not plan['original_initialize_executed']
source=next(s for s in p['sources'] if s['class_name']=='sun/io/Win32ErrorMode')
assert digest(source['path'])==source['origin']['sha256']==plan['origin']['sha256']
assert plan['origin']['loader']=='bootstrap' and plan['origin']['source_id']=='jdk:java.base'
c=parser['parse'](Path(source['path']).read_bytes());m=next(m for m in c['methods'] if m[1:3]==('setErrorMode','(J)J'))
assert m[0]==0x10a and not any(n=='Code' for n,_ in m[3])
assert plan['entry']==p['entry_id'] and p['compilation']['signature']=={'arguments':['I64'],'result':'I64'}
assert digest(p['compilation']['dll'])==p['compilation']['dll_digest']['sha256']
print(json.dumps(dict(passed=True,native_declarations_verified=3,original_private_callsites_verified=2,VM_entry_compiled=True,original_System_phase_executed=False)))
