"""Raw source/Code verification independent of the compiler's classfile reader."""
import hashlib,json,runpy,struct,sys
from pathlib import Path
parse=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))['parse']
p=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'));base=Path(sys.argv[2]);jdk=json.loads(base.read_text(encoding='utf-8-sig'));plan=p['string_split']
assert p['schema']==63 and not p['full_game_ready'] and plan['abi']==1
assert plan['original_public_wrapper_code_retained'] and plan['literal_delimiter_fast_path']
assert not plan['original_private_java_methods_executed'] and not plan['regex_engine_complete'] and not plan['automatic_gc']
raw=(base.parent/'image/java.base/java/lang/String.class').read_bytes();original=parse(raw)
assert hashlib.sha256(raw).hexdigest()==plan['string_origin']['sha256'] and plan['string_origin']==jdk['classes']['java.lang.String']
for descriptor,key,length in [('(Ljava/lang/String;IZ)[Ljava/lang/String;','dispatch_code_sha256',148),('(CIZ)[Ljava/lang/String;','char_helper_code_sha256',242)]:
    m=next(m for m in original['methods'] if m[1:3]==('split',descriptor));data=next(b for k,b in m[3] if k=='Code');code=data[8:8+struct.unpack('>I',data[4:8])[0]]
    assert m[0]==2 and len(code)==length and hashlib.sha256(code).hexdigest()==plan[key]
assert hashlib.sha256(Path('native/runtime/string_split.asm').read_bytes()).hexdigest()==plan['native_source_sha256']
assert p['string_literals'][plan['empty_literal']]['utf16']==[]
assert len(plan['bindings'])==3
for b in plan['bindings']:
    g=b['caller']['generated'];assert g['generator']=='boom-jdk-bridge' and g['site'] in [17,18,19] and g['host_sha256']==plan['string_origin']['sha256']
for b in p['sources']:
    if not b.get('origin',{}).get('generated',{}):continue
    g=b['origin']['generated']
    if g['generator']!='boom-jdk-bridge' or g['site'] not in [17,18,19]:continue
    generated=parse(Path(b['path']).read_bytes());method=generated['methods'][0];descriptor='('+method[2][len('(Ljava/lang/String;'):]
    source=next(m for m in original['methods'] if m[1:3]==(method[1],descriptor))
    assert generated['cp'].startswith(original['cp']) and method[3]==source[3]
print(json.dumps(dict(passed=True,original_public_wrappers_Code_attributes_identical=True,private_dispatch_and_char_helper_source_bound=True,regex_engine_complete=False,game_started=False)))
