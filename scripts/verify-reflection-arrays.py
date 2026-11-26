"""Raw classfile and metadata checks, independent of compiler/native execution."""
import hashlib
import json
import runpy
import sys
from pathlib import Path

bridge = runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
p = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
plan = p['reflection_arrays']
assert p['schema'] == 58 and not p['full_game_ready']
assert plan['abi'] == 1 and not plan['automatic_gc'] and not plan['dynamic_type_creation']
assert plan['missing_array_metadata_is_an_error']
assert plan['origin']['loader'] == 'bootstrap' and plan['origin']['source_id'] == 'jdk:java.base'
source = next(s for s in p['sources'] if s['origin'] == plan['origin'])
raw = Path(source['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest() == plan['origin']['sha256']
parsed = bridge['parse'](raw)
r, cp, i = bridge['Reader'](parsed['cp']), {}, 1
while i < parsed['count']:
    tag = r.u1()
    if tag == 1: cp[i] = r.take(r.u2()).decode('utf-8', errors='replace')
    elif tag in (7, 8, 16, 19, 20): cp[i] = (tag, r.u2())
    elif tag in (9, 10, 11, 12, 17, 18): cp[i] = (tag, r.u2(), r.u2())
    elif tag in (3, 4): r.take(4)
    elif tag in (5, 6): r.take(8); i += 1
    elif tag == 15: r.take(3)
    else: raise AssertionError('Unknown constant tag')
    i += 1
expected = set()
for op, name, desc, flags, load in [
    ('New', 'newArray', '(Ljava/lang/Class;I)Ljava/lang/Object;', 9, b'\x2a\x1b'),
    ('Multi', 'multiNewArray', '(Ljava/lang/Class;[I)Ljava/lang/Object;', 0x89, b'\x2a\x2b'),
]:
    native = next(m for m in parsed['methods'] if m[1:3] == (name, desc))
    assert native[0] == 0x10a and not any(n == 'Code' for n, _ in native[3])
    public = next(m for m in parsed['methods'] if m[1:3] == ('newInstance', desc))
    assert public[0] == flags
    code = next(b for n, b in public[3] if n == 'Code')
    count = int.from_bytes(code[4:8], 'big')
    instructions = code[8:8+count]
    assert count == 6 and instructions[:2] == load and instructions[2] == 0xb8 and instructions[5] == 0xb0
    constant = int.from_bytes(instructions[3:5], 'big')
    method = cp[constant]; owner, nt = cp[method[1]], cp[method[2]]
    assert method[0] == 10 and cp[owner[1]] == 'java/lang/reflect/Array'
    assert cp[nt[1]] == name and cp[nt[2]] == desc
    expected.add((op, constant))
    assert any(s['class_name'] == 'java/lang/reflect/Array' and s['method'] == 'newInstance'
               and s['descriptor'] == desc for s in p['symbols'])
assert {(b['operation'], b['constant']) for b in plan['bindings']} == expected
assert all(b['caller'] == plan['origin'] for b in plan['bindings'])
types = p['mirror_types']
def descriptor(id):
    typ = types[id]
    if typ['kind'] == 'array': return '[' + descriptor(typ['component'])
    if typ['kind'] == 'class': return 'L' + typ['key']['name'] + ';'
    return dict(Boolean='Z', Byte='B', Char='C', Short='S', Int='I', Long='J', Float='F', Double='D', Void='V')[typ['value']]
names = [descriptor(i) for i in range(len(types))]
assert len(plan['rows']) == len(types)
for i, row in enumerate(plan['rows']):
    assert row['component_rank'] == len(names[i]) - len(names[i].lstrip('['))
    assert row['void_component'] == (names[i] == 'V')
    target = row['array_type']
    if i < plan['prepared_component_types'] and not row['void_component'] and row['component_rank'] < 255:
        assert target is not None
    if target is not None:
        assert types[target] == dict(kind='array', component=i)
        assert names[target] == '[' + names[i]
        if types[i]['kind'] != 'primitive':
            assert target in p['typed_arrays']['reference_array_types']
            assert any(b['tag'] == f'OFFSET boom_t{target}' and b['type_id'] == target and b['kind'] == 2
                       for b in p['runtime_type_bindings'])
assert max(r['component_rank'] for r in plan['rows']) == 255
assert any(r['array_type'] is None and not r['void_component'] and r['component_rank'] < 255 for r in plan['rows'])
for field, path in [('native_source_sha256', 'native/runtime/reflection_arrays.asm'), ('allocator_source_sha256', 'native/runtime/typed_arrays.asm')]:
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == plan[field]
proof = Path(sys.argv[2])
checks = bridge['verify'](proof)
assert checks['bridges'] == 2
records = json.loads(proof.read_text(encoding='utf-8-sig'))
assert {r['kind'] for r in records} == {'ClassToString', 'ClassAsSubclass'}
for record in records:
    assert any(s['origin'] == record['generated'] for s in p['sources'])
Path(sys.argv[3]).write_text(json.dumps(names), encoding='utf-8')
print(json.dumps(dict(passed=True, original_Array_native_declarations=2, original_Java_wrapper_Code_verified=2,
                     exact_component_array_rows=len(types), original_Class_method_bridges=2,
                     dynamic_type_creation=False, game_started=False)))
