"""Independently verify original getter Code and component-loader metadata."""
import hashlib
import json
import runpy
import sys
from pathlib import Path

bridges = runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
p = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
proof_path = Path(sys.argv[2])
bridge_proof = bridges['verify'](proof_path)
records = json.loads(proof_path.read_text(encoding='utf-8-sig'))
plan = p['class_loaders']
assert p['schema'] == 57 and not p['full_game_ready']
assert plan['abi'] == 1 and plan['field_read_only'] and not plan['automatic_gc']
assert plan['application_loaders_require_explicit_binding']
original = next(r for r in records if r['kind'] == 'ClassGetClassLoader0')
assert original['original'] == plan['class_origin']
assert any(r['kind'] == 'ClassGetClassLoader' for r in records)
source = next(s for s in p['sources'] if s['origin'] == plan['loader_origin'])
assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == plan['loader_origin']['sha256']
registration = len(sys.argv) > 3 and sys.argv[3] == 'registration'
assert plan['keys'] == (['bootstrap'] if registration else ['bootstrap', 'explicit-application'])
types = p['mirror_types']
assert len(plan['type_loader_ids']) == len(types)
for i, typ in enumerate(types):
    for _ in range(256):
        if typ['kind'] != 'array':
            key = 'bootstrap' if typ['kind'] == 'primitive' else typ['key']['loader']
            assert plan['keys'][plan['type_loader_ids'][i]] == key
            break
        typ = types[typ['component']]
    else:
        raise AssertionError('Invalid array component chain')
assert any(r['tag'] == 'OFFSET boom_loader_vm_layout' and r['type_id'] == plan['loader_type']
           and r['payload_bytes'] == plan['loader_vm_layout']['payload_bytes']
           and r['references'] == plan['loader_vm_layout']['reference_prefix_fields']
           for r in p['runtime_type_bindings'])
assert hashlib.sha256(Path('native/runtime/class_loaders.asm').read_bytes()).hexdigest() == plan['native_source_sha256']
assert plan['registered_name'] == 'retrieveDirectives'
assert plan['registered_descriptor'] == '()Ljava/lang/AssertionStatusDirectives;'
assert not plan['retrieve_directives_implemented']
loader_class = bridges['parse'](Path(source['path']).read_bytes())
for name, desc in [('registerNatives', '()V'), ('retrieveDirectives', plan['registered_descriptor'])]:
    method = next(m for m in loader_class['methods'] if m[1:3] == (name, desc))
    assert method[0] == 0x10a and not any(n == 'Code' for n, _ in method[3])
if registration:
    assert plan['registration_bindings'] and not plan['bindings']
    assert all(b['caller'] == plan['loader_origin'] for b in plan['registration_bindings'])
    for name in ('<clinit>', 'checkName'):
        assert any(s['class_name'] == 'java/lang/ClassLoader' and s['method'] == name for s in p['symbols'])
else:
    assert not plan['registration_bindings']
    assert all(b['caller']['generated']['site'] == 15 for b in plan['bindings'])
    assert any(s['class_name'] == 'java/lang/Class$$BoomJdk$000f' and s['method'] == 'getClassLoader0'
               for s in p['symbols'])
    assert not any(s['class_name'] == 'java/lang/ClassLoader' and s['method'] == '<clinit>'
                   for s in p['symbols'])
print(json.dumps(dict(passed=True, original_getter_bridges=bridge_proof['bridges'],
                     component_loader_mappings=len(types), public_getter_executed=False,
                     ClassLoader_initializer_planned=registration,
                     ClassLoader_constructor_executed=False, game_started=False)))
