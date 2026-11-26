"""Check original Module Code and physical metadata independently of the compiler."""
import hashlib, json, runpy, sys
from pathlib import Path

parse = runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))['parse']
p = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
m = p['module_plan']; o = m['objects']; ctor = p['constructor_entry']
assert p['schema'] == 60 and not p['full_game_ready'] and m['abi'] == 3
assert o['bootstrap_entry'] and ctor['module_bootstrap'] and not o['named_module_bootstrap_complete'] and not o['automatic_gc']
assert o['origin']['loader'] == 'bootstrap' and o['origin']['source_id'] == 'jdk:java.base'
source = next(s for s in p['sources'] if s['origin'] == o['origin'])
raw = Path(source['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest() == o['origin']['sha256']
method = next(m for m in parse(raw)['methods'] if m[1:3] == ('<init>', '(Ljava/lang/ClassLoader;)V'))
assert method[0] == 0
attr = next(b for n,b in method[3] if n == 'Code')
assert int.from_bytes(attr[4:8], 'big') == 25
assert hashlib.sha256(attr[8:33]).hexdigest() == o['original_unnamed_constructor_code_sha256']
assert any(s['class_name'] == 'java/lang/Module' and s['method'] == '<init>' and s['descriptor'] == method[2] for s in p['symbols'])
assert not any(s['class_name'] == 'java/lang/Module' and s['method'] == '<clinit>' for s in p['symbols'])
fields = {f['name']: f for f in o['layout']['fields']}
for name in ('name', 'loader', 'layer', 'descriptor'):
    assert fields[name]['offset'] == o[name+'_offset'] and fields[name]['storage_bytes'] == 8
    assert fields[name]['declaring_class'] == 'java/lang/Module'
assert o['layout']['abi'] == 2 and o['layout']['reference_prefix_fields'] == 8 and o['layout']['payload_bytes'] == 65
assert any(r['class_name'] == 'java/lang/Module' and r['layout'] == o['layout'] for r in p['object_layouts'])
assert not any(r['tag'] == 'OFFSET boom_module_layout' for r in p['runtime_type_bindings'])
assert hashlib.sha256(Path('native/runtime/module_objects.asm').read_bytes()).hexdigest() == o['native_source_sha256']
assert len(m['object_loader_keys']) == len(m['identities'])
for i, identity in enumerate(m['identities']):
    assert p['class_loaders']['keys'][m['object_loader_keys'][i]] == identity['defining_loader']
print(json.dumps(dict(passed=True, original_constructor_Code_bytes=25, physical_Module_fields=9,
                      Module_Java_initializer_executed=False, named_Module_bootstrap_complete=False, game_started=False)))
