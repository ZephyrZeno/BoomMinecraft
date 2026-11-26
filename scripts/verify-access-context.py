"""Read original class bytes independently; check native declarations/frame views."""
import hashlib
import json
import runpy
import sys
from pathlib import Path

parser = runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
parse, Reader = parser['parse'], parser['Reader']
def skip_value(r):
    tag = r.u1()
    if tag in b'BCDFIJSZsc': r.take(2)
    elif tag == ord('e'): r.take(4)
    elif tag == ord('@'): read_annotation(r)
    elif tag == ord('['):
        for _ in range(r.u2()): skip_value(r)
    else: raise AssertionError('Invalid annotation tag')
def read_annotation(r):
    type_index = r.u2()
    for _ in range(r.u2()): r.u2(); skip_value(r)
    return type_index
p = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
plan = p['access_context']
assert p['schema'] >= 55 and not p['full_game_ready']
assert plan['abi'] == 1 and not plan['automatic_gc']
assert plan['application_domains_require_explicit_binding']
owner = 'java/security/AccessController'
source = next(s for s in p['sources'] if s['class_name'] == owner)
raw = Path(source['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest() == plan['origin']['sha256']
assert plan['origin']['loader'] == 'bootstrap' and plan['origin']['source_id'] == 'jdk:java.base'
c = parse(raw)
for name, desc, flags in [
    ('getStackAccessControlContext', '()Ljava/security/AccessControlContext;', 0x10a),
    ('getInheritedAccessControlContext', '()Ljava/security/AccessControlContext;', 0x108),
    ('ensureMaterializedForStackWalk', '(Ljava/lang/Object;)V', 0x10a),
]:
    m = next(m for m in c['methods'] if m[1:3] == (name, desc))
    assert m[0] == flags and not any(n == 'Code' for n, _ in m[3])
frames = {m['id']: m for m in p['java_frames']['methods']}
assert len(frames) == len(plan['methods'])
for view in plan['methods']:
    m = frames[view['method']]
    src = next(s for s in p['sources'] if s['origin'] == m['source'])
    raw = Path(src['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == m['source']['sha256']
    method = next(x for x in parse(raw)['methods'] if x[1:3] == (m['name'], m['descriptor']))
    code = next(b for n, b in method[3] if n == 'Code')
    stack, locals_count = int.from_bytes(code[:2], 'big'), int.from_bytes(code[2:4], 'big')
    assert view['max_locals'] == locals_count and view['locals_displacement'] == -8*(stack+locals_count)
    generated = m['source'].get('generated')
    bridge = generated is not None and generated['generator'] == 'boom-jdk-bridge'
    if bridge:
        assert m['source']['loader'] == generated['host_loader'] == 'bootstrap'
        assert m['source']['source_id'] == 'boom:jdk-bridge-v1'
        assert generated['host_source_id'] == 'jdk:java.base'
        host = p['mirror_types'][view['type_id']]
        assert host['key'] == dict(loader='bootstrap', name=generated['host_class'])
        assert host['origin']['sha256'] == generated['host_sha256']
        assert host['origin']['source_id'] == 'jdk:java.base'
        assert host['origin'].get('generated') is None
        original = next((s for s in p['sources'] if s['origin'] == host['origin']), None)
        if original is not None:
            original_raw = Path(original['path']).read_bytes()
        else:
            # Opaque Class/String hosts need not enter the executable closure.
            # Supply a separately exported original bridge inspection in argv[2].
            records = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8-sig'))
            proof = next(r for r in records if r['original'] == host['origin']
                         and r['generated'] == m['source'])
            original_raw = Path(proof['original_class']).read_bytes()
        assert hashlib.sha256(original_raw).hexdigest() == generated['host_sha256']
        descriptor = m['descriptor']
        if generated['host_class'] == 'java/lang/Class':
            prefix = '(Ljava/lang/Class;'
            assert descriptor.startswith(prefix)
            descriptor = '(' + descriptor[len(prefix):]
        original_method = next(x for x in parse(original_raw)['methods']
                               if x[1:3] == (m['name'], descriptor))
        assert original_method[3] == method[3]
    else:
        assert view['type_id'] == m['type_id']
    assert view['privileged'] == (m['class_name'] == owner and m['name'] == 'executePrivileged')
    visible = next((b for n, b in method[3] if n == 'RuntimeVisibleAnnotations'), b'\0\0')
    # CallerSensitive has no elements. Resolve its UTF8 constant independently.
    cp_data = parse(raw)['cp']
    r, cp, i = Reader(cp_data), {}, 1
    while i < parse(raw)['count']:
        tag = r.u1()
        if tag == 1: cp[i] = r.take(r.u2()).decode('utf-8', errors='replace')
        elif tag in (7, 8, 16, 19, 20): r.take(2)
        elif tag in (9, 10, 11, 12, 17, 18, 3, 4): r.take(4)
        elif tag in (5, 6): r.take(8); i += 1
        elif tag == 15: r.take(3)
        else: raise AssertionError('Unknown constant tag')
        i += 1
    cs_indices = {i for i, text in cp.items() if text == 'Ljdk/internal/reflect/CallerSensitive;'}
    annotations = Reader(visible)
    found_cs = bool(cs_indices & {read_annotation(annotations) for _ in range(annotations.u2())})
    assert view['caller_sensitive'] == (found_cs and m['source']['loader'] == 'bootstrap'
                                       and (m['source']['source_id'] == 'jdk:java.base' or bridge))
types = p['mirror_types']
for name in ('dev/boom/security/AccessDomain$A', 'dev/boom/security/AccessDomain$B'):
    t = next(t for t in types if t.get('key', {}).get('name') == name)
    assert t['key']['loader'] == 'explicit-application'
assert plan['domain_array'] in p['typed_arrays']['reference_array_types']
assert any(r['tag'] == 'OFFSET boom_access_pd_layout' and r['type_id'] == plan['domain_type'] for r in p['runtime_type_bindings'])
assert any(s['class_name'] == owner and s['method'] == '<clinit>' for s in p['symbols'])
assert any(s['class_name'] == 'java/security/AccessControlContext' and s['method'] == '<clinit>' for s in p['symbols'])
print(json.dumps(dict(passed=True,original_native_declarations=3,source_frame_views_verified=len(frames),game_started=False)))
