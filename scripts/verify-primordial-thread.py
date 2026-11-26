"""Check original constructor bytes and emitted guards independently."""
import hashlib,json,runpy,sys
from pathlib import Path
parse=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))['parse']
p=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'));plan=p['thread_bootstrap']
assert p['schema']==54 and not p['full_game_ready'] and plan['primordial_only'] and not plan['general_thread_constructor_complete']
s=next(s for s in p['sources'] if s['class_name']=='java/lang/Thread');raw=Path(s['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==s['origin']['sha256']==plan['origin']['sha256']
m=next(m for m in parse(raw)['methods'] if m[1:3]==('<init>',plan['original_descriptor']))
body=next(b for n,b in m[3] if n=='Code');length=int.from_bytes(body[4:8],'big');code=body[8:8+length]
assert length==311 and hashlib.sha256(code).hexdigest()==plan['original_code_sha256']
asm=Path(p['compilation']['assembly']).read_text()
for pc,opcode,target in [(23,0xa6,30),(35,0x99,73),(39,0xc7,52),(171,0x99,189),(178,0xa2,189),(198,0xc6,205),(213,0xc6,225),(234,0x9a,303)]:
    assert pc in plan['guarded_conditionals'] and code[pc]==opcode and pc+int.from_bytes(code[pc+1:pc+3],'big',signed=True)==target
    assert f'boom_m{plan["method"]}_body_P{pc}_boot_guard_ok' in asm
for owner in ('java/lang/Thread','java/lang/Thread$FieldHolder','java/lang/ThreadGroup','java/security/AccessControlContext'):
    assert any(s['class_name']==owner and s['method']=='<init>' for s in p['symbols'])
    source=next(s for s in p['sources'] if s['class_name']==owner)
    assert source['origin']['loader']=='bootstrap' and source['origin']['source_id']=='jdk:java.base' and not source['origin'].get('generated')
assert not any(s['class_name']=='java/security/AccessController' for s in p['symbols'])
print(json.dumps(dict(passed=True,original_constructor_bytes_verified=True,emitted_conditional_guards=8,source_constructors=4,general_Thread_constructor_complete=False)))
