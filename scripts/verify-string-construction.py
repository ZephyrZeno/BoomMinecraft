"""Independent source/Code/constant-pool proof for the VM String boundary."""
import hashlib, json, runpy, sys
from pathlib import Path
parser = runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def pool(raw):
    r=parser['Reader'](raw);r.take(8);n=r.u2();p=[None]*n;i=1
    while i<n:
        tag=r.u1()
        if tag==1:p[i]=r.take(r.u2()).decode('utf-8',errors='replace')
        elif tag in (7,8,16,19,20):p[i]=(tag,r.u2())
        elif tag in (9,10,11,12,17,18):p[i]=(tag,r.u2(),r.u2())
        elif tag in (3,4):r.take(4)
        elif tag in (5,6):r.take(8);i+=1
        elif tag==15:r.take(3)
        else:raise AssertionError(tag)
        i+=1
    return p
p=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
base=Path(sys.argv[2]);metadata=json.loads(base.read_text(encoding='utf-8-sig'))
original=base.parent/'image/java.base/java/lang/String.class';raw=original.read_bytes()
assert digest(original)==metadata['classes']['java.lang.String']['sha256']
codes={}
for desc,size in [('([CII)V',14),('([C)V',10)]:
    method=next(m for m in parser['parse'](raw)['methods'] if m[1:3]==('<init>',desc))
    code=next(b for n,b in method[3] if n=='Code');assert method[0]==1 and int.from_bytes(code[4:8],'big')==size
    codes[desc]=code[8:8+size]
assert p['schema']>=61 and not p['full_game_ready'] and p['dynamic_string_runtime']
bindings=p['string_construction'];assert bindings and {b['allocation'] for b in bindings}=={True,False}
sources={s['class_name']:s for s in p['sources']}
for b in bindings:
    assert b['abi']==1 and b['storage_abi']==3 and not b['compact_strings'] and not b['automatic_gc'] and not b['original_Java_constructor_executed']
    assert b['origin']==metadata['classes']['java.lang.String']
    desc=b['descriptor'];assert desc in codes
    assert b['constructor_code_sha256']==hashlib.sha256(codes[desc]).hexdigest()
    source=sources[b['caller']['binary_name'].replace('.','/')]
    assert source['origin']==b['caller'] and digest(source['path'])==b['caller']['sha256']
    cp=pool(Path(source['path']).read_bytes());ref=cp[b['constant']]
    if b['allocation']:assert ref[0]==7 and cp[ref[1]]=='java/lang/String'
    else:
        assert ref[0]==10 and cp[cp[ref[1]][1]]=='java/lang/String'
        pair=cp[ref[2]];assert pair[0]==12 and cp[pair[1]]=='<init>' and cp[pair[2]]==desc
    for key,path in [('native_source_sha256','string_construction.asm'),('string_source_sha256','strings.asm'),('heap_source_sha256','heap.asm'),('object_source_sha256','objects.asm')]:
        assert b[key]==digest(Path('native/runtime')/path)
assert not any(s['class_name']=='java/lang/String' for s in p['symbols'])
print(json.dumps(dict(passed=True,source_bindings=len(bindings),original_constructor_Code_bytes={k:len(v) for k,v in codes.items()},
                     runtime_provided_String_semantics=True,original_Java_constructor_executed=False,game_started=False)))
