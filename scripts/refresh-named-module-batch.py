"""Derive JCLS named identities and independently verify the complete source batch.

Build proves the data-only append. A separate verify-full invocation runs the
real batch verifier before publishing verification.json or a certified resolver.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location('named_append_' + name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


R = module('refresh-boot-unnamed-batch')
S, A = R.S, R.A
I = module('verify-translation-ir')
PROOF = 'named-module-derivation.json'
TOOLS = ('refresh-named-module-batch.py', 'refresh-boot-unnamed-batch.py',
         'boot-unnamed-normal-candidate.py', 'closure-batch-artifacts.py',
         'refresh-unsafe-field-batch.py', 'verify-batch-assembly.py',
         'verify-batch-classes.py', 'verify-translation-ir.py', 'runtime-provider-source.py',
         'provider-tool-manifest.py')


def artifact(path):
    return R.artifact(Path(path))


def checked(record):
    path = Path(record['path']).resolve()
    S.check(path.is_relative_to(S.ART) and artifact(path) == record, 'Candidate input digest or root differs')
    return path


def tools():
    return {name: artifact(ROOT / 'scripts' / name) for name in TOOLS}


def descriptor(path):
    """Read the actual Module/ModulePackages tables, including mandatory requires."""
    raw = I.Source(path.read_bytes())
    S.check(raw.name == 'module-info' and not raw.methods and not raw.fields, 'Expected original module-info.class')
    attrs = {name: body for name, body in raw.attrs}
    S.check(len(attrs) == len(raw.attrs) and 'Module' in attrs, 'Ambiguous module descriptor attributes')
    r = I.Reader(attrs['Module'])

    def text(tag):
        actual, index = raw.cp[r.u2()]
        S.check(actual == tag, 'Module descriptor constant kind differs')
        return raw.text(index)

    name, flags, version = text(19), r.u2(), r.u2()
    requires = []
    for _ in range(r.u2()):
        target, access, ver = text(19), r.u2(), r.u2()
        requires.append(dict(module=target, flags=access, version=raw.text(ver) if ver else None))
    exports, opens = [], []
    for rows in (exports, opens):
        for _ in range(r.u2()):
            package, access = text(20), r.u2()
            rows.append(dict(package=package, flags=access, targets=[text(19) for _ in range(r.u2())]))
    uses = [text(7) for _ in range(r.u2())]
    provides = []
    for _ in range(r.u2()):
        service = text(7)
        provides.append(dict(service=service, providers=[text(7) for _ in range(r.u2())]))
    S.check(r.position == len(r.data), 'Trailing Module descriptor bytes')
    packages = []
    if 'ModulePackages' in attrs:
        r = I.Reader(attrs['ModulePackages'])
        packages = [text(20) for _ in range(r.u2())]
        S.check(r.position == len(r.data), 'Trailing ModulePackages bytes')
    return dict(name=name, flags=flags, version=raw.text(version) if version else None,
                requires=requires, exports=exports, opens=opens, uses=uses, provides=provides, packages=packages)


def required_path(snapshot, name):
    queue = [(root, []) for root in snapshot['graph']['roots']]
    seen = set()
    while queue:
        node, path = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        if node == name:
            return path
        for row in snapshot['modules'][node]['descriptor']['requires']:
            if not row['flags'] & 0x40 and row['module'] in snapshot['graph']['resolved']:
                queue.append((row['module'], path + [dict(source=node, **row)]))
    raise ValueError('Missing module is not mandatory from a locked default root')


def source_graph(base, plan, names=None, classes=None):
    catalog_path = S.checked(base['frames']['original_system_catalog'])
    catalog = S.read(catalog_path)
    snapshot_path = S.checked(catalog['module_snapshot'])
    snapshot = S.read(snapshot_path)
    S.check(snapshot['fingerprint'] == catalog['module_snapshot_fingerprint'] and
            snapshot['input_fingerprint'] == base['input_fingerprint'] and
            snapshot['graph']['profile'] == 'jdk21-system-classpath-default', 'Locked default module graph differs')
    jcls = base['class_literals']
    mods, loaders = jcls['modules'], jcls['loader_keys']
    S.check([m['id'] for m in mods] == list(range(len(mods))) and len(mods) < 65536 and
            len({(m['loader'], m['name']) for m in mods}) == len(mods) and
            loaders == ['bootstrap', 'platform', 'vanilla-application'], 'Original stable JCLS key domain differs')
    missing = sorted(set(snapshot['graph']['resolved']) - {m['name'] for m in mods if m['name'] is not None})
    if names is None:
        names = missing
    S.check(names and sorted(names) == missing and len(set(names)) == len(names),
            'Append exactly the missing resolved named modules, without an extra identity')
    source_records = dict(catalog=artifact(catalog_path), snapshot=artifact(snapshot_path), module_info={})
    rows, requirements = [], []
    for name in names:
        S.check(re.fullmatch(r'[A-Za-z0-9_.]+', name) and '..' not in name, 'Invalid locked module name')
        declared = snapshot['modules'][name]
        info = snapshot_path.parent / 'image' / name / 'module-info.class'
        S.check(S.digest(info)['sha256'] == declared['sha256'], 'Original missing module-info.class changed')
        actual = descriptor(info)
        S.check(all(actual[k] == declared['descriptor'][k] for k in actual) and
                not actual['packages'], 'This append supports original modules without packages or represented types')
        loader = snapshot['graph']['resolved'][name]['loader']
        loader = 'vanilla-application' if loader == 'application' else loader
        S.check(loader in loaders, 'Missing named module defining loader is unsupported')
        path = required_path(snapshot, name)
        S.check(path, 'A root with types should already have a JCLS identity')
        for edge in path:
            origin = snapshot_path.parent / 'image' / edge['source'] / 'module-info.class'
            original = descriptor(origin)
            S.check(S.digest(origin)['sha256'] == snapshot['modules'][edge['source']]['sha256'] and
                    {k: edge[k] for k in ('module', 'flags', 'version')} in original['requires'],
                    'Mandatory dependency edge differs from its original classfile')
            source_records['module_info'][edge['source']] = artifact(origin)
        source_records['module_info'][name] = artifact(info)
        rows.append(dict(id=len(mods) + len(rows), name=name, loader=loaders.index(loader)))
        requirements.append(dict(module=name, mandatory_from_default_root=path, descriptor=actual))
    wanted = {'jdk/internal/module/ModuleBootstrap', 'java/lang/ModuleLayer', 'java/lang/Module'}
    owners = {}
    source_plan = S.read(plan/'summary.json')
    S.check(source_plan['input_fingerprint'] == base['input_fingerprint'] and
            S.checked(source_plan['artifacts']['classes']) == plan/'classes.jsonl', 'Original source class plan changed')
    if classes is None:
        with (plan/'classes.jsonl').open(encoding='utf-8') as stream:
            classes = [json.loads(line) for line in stream]
    for c in classes:
        S.check(c['origin']['source_id'] not in {'jdk:' + name for name in names},
                'Named module has original classes; this would change represented type identities')
        if c['name'] in wanted and c['origin']['loader'] == 'bootstrap':
            S.check(c['name'] not in owners, 'Ambiguous normal bootstrap source')
            owners[c['name']] = c
    S.check(set(owners) == wanted, 'Original module definition Java source is missing')
    expected = [
        ('jdk/internal/module/ModuleBootstrap', 'boot2', '()Ljava/lang/ModuleLayer;',
         'java/lang/ModuleLayer', 'defineModules', '(Ljava/lang/module/Configuration;Ljava/util/function/Function;)Ljava/lang/ModuleLayer;'),
        ('java/lang/ModuleLayer', '<init>', '(Ljava/lang/module/Configuration;Ljava/util/List;Ljava/util/function/Function;)V',
         'java/lang/Module', 'defineModules', '(Ljava/lang/module/Configuration;Ljava/util/function/Function;Ljava/lang/ModuleLayer;)Ljava/util/Map;'),
        ('java/lang/Module', 'defineModules', '(Ljava/lang/module/Configuration;Ljava/util/function/Function;Ljava/lang/ModuleLayer;)Ljava/util/Map;',
         'java/lang/Module', '<init>', '(Ljava/lang/ModuleLayer;Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;Ljava/net/URI;)V'),
        ('java/lang/Module', '<init>', '(Ljava/lang/ModuleLayer;Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;Ljava/net/URI;)V',
         'java/lang/Module', 'defineModule0', '(Ljava/lang/Module;ZLjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V')]
    chain = []
    for owner, name, desc, target, member, target_desc in expected:
        c = owners[owner]
        raw = I.Source(S.original_class(base, c))
        [(ident, method)] = [(i, m) for i, m in zip(c['method_ids'], raw.methods)
                             if (m['name'], m['descriptor']) == (name, desc)]
        code = raw.code(method)
        S.check(code is not None, 'Original module definition chain lacks Java Code')
        calls = []
        for op in I.stream(code['bytes']):
            if op['opcode'] in (0xb6, 0xb7, 0xb8):
                call = raw.member(op['operand']['Constant'])
                if (call['owner'], call['name'], call['descriptor']) == (target, member, target_desc):
                    calls.append(dict(pc=op['pc'], **call))
        S.check(calls, 'Original module definition call chain changed')
        chain.append(dict(method=ident, owner=owner, name=name, descriptor=desc,
                          class_sha256=c['origin']['sha256'], code_sha256=hashlib.sha256(code['bytes']).hexdigest(), calls=calls))
    return rows, dict(inputs=source_records, requirements=requirements, source_Java_definition_chain=chain,
                      actual_missing_module_execution_observed=False)


def overlay(original, jcls, appended):
    nmod, nload, roots = len(jcls['modules']), len(jcls['loader_keys']), jcls['root_cells']
    loader_table = b'boom_java_class_module_loaders LABEL DWORD\n' + b''.join(
        f" DWORD {r['loader']}\n".encode() for r in jcls['modules'])
    edits = [
        (f" DWORD {jcls['reverse_slots']-1},{nload},{nmod},1\n".encode(),
         f" DWORD {jcls['reverse_slots']-1},{nload},{nmod+len(appended)},1\n".encode()),
        (f'boom_java_class_root_count QWORD {roots}\n'.encode(),
         f'boom_java_class_root_count QWORD {roots+len(appended)}\n'.encode()),
        (loader_table + b'.data?\n', loader_table + b''.join(f" DWORD {r['loader']}\n".encode() for r in appended) + b'.data?\n'),
        (f'boom_java_class_module_roots QWORD {nmod} DUP(?)\n'.encode(),
         f'boom_java_class_module_roots QWORD {nmod+len(appended)} DUP(?)\n'.encode())]
    changes = []
    for before, after in edits:
        S.check(original.count(before) == 1, 'Original JCLS declaration is not unique')
        changes.append(dict(before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(after).hexdigest(),
                            before_bytes=len(before), after_bytes=len(after)))
        original = original.replace(before, after, 1)
    return original, changes


def sections(path):
    data = path.read_bytes()
    machine, count, _, _, _, optional, _ = struct.unpack_from('<HHIIIHH', data)
    S.check(machine == 0x8664 and optional == 0, 'Expected AMD64 COFF')
    result = {}
    for i in range(count):
        at = 20 + i * 40
        name = data[at:at+8].rstrip(b'\0').decode('ascii')
        size, raw, relocs, lines, nrel, nline, flags = struct.unpack_from('<IIIIHHI', data, at+16)
        S.check(name not in result and lines == nline == 0 and raw+size <= len(data), 'Unexpected COFF section range')
        if nrel == 65535 and flags & 0x01000000:
            nrel = struct.unpack_from('<I', data, relocs)[0]
        S.check(relocs+nrel*10 <= len(data), 'Truncated COFF relocation table')
        result[name] = dict(size=size, raw=raw, flags=flags, data=data[raw:raw+size] if raw else b'',
                            relocations=data[relocs:relocs+nrel*10])
    return result


def debug_without_object_name(data, path):
    S.check(struct.unpack_from('<I', data)[0] == 4, 'Expected CodeView C13 debug data')
    at, result = 4, []
    while at < len(data):
        kind, size = struct.unpack_from('<II', data, at)
        S.check(kind == 0xf1 and at+8+size <= len(data), 'Unexpected CodeView subsection')
        pos, end = at+8, at+8+size
        records = []
        while pos < end:
            length, tag = struct.unpack_from('<HH', data, pos)
            S.check(length >= 2 and pos+2+length <= end, 'Unexpected CodeView record')
            body = data[pos+4:pos+2+length]
            if tag == 0x1101:
                S.check(body[:4] == bytes(4) and body[4:] == str(path).encode() + b'\0',
                        'Unexpected CodeView object name or signature')
                body = b'original-assembler-object-path'
            records.append(dict(tag=tag, body=body.hex()))
            pos += 2+length
        S.check(pos == end, 'Trailing CodeView record bytes')
        result.append(dict(kind=kind, records=records))
        aligned = (end+3)&~3
        S.check(not any(data[end:aligned]), 'Nonzero CodeView padding')
        at = aligned
    S.check(at == len(data), 'Trailing CodeView section bytes')
    return result


def symbol_contract(old, new):
    def read(path):
        data = path.read_bytes()
        machine, count, _, pointer, entries, optional, _ = struct.unpack_from('<HHIIIHH', data)
        S.check(machine == 0x8664 and optional == 0 and pointer >= 20+40*count, 'Invalid symbol-table header')
        strings = pointer+18*entries
        S.check(strings+4 <= len(data), 'Truncated symbol table')
        string_size = struct.unpack_from('<I', data, strings)[0]
        S.check(string_size >= 4 and strings+string_size == len(data), 'Invalid symbol string table range')
        sections = {}
        for number in range(1, count+1):
            at = 20+(number-1)*40
            name = data[at:at+8].rstrip(b'\0').decode('ascii')
            sections[number] = (name, struct.unpack_from('<I', data, at+16)[0])
        rows, index = [], 0
        while index < entries:
            at = pointer+index*18
            value, section, kind, storage, auxiliaries = struct.unpack_from('<IhHBB', data, at+8)
            S.check(index+1+auxiliaries <= entries and section <= count, 'Invalid symbol or auxiliary range')
            raw = data[at:at+8]
            if raw[:4] == bytes(4):
                offset = struct.unpack_from('<I', raw, 4)[0]
                S.check(4 <= offset < string_size, 'Invalid long symbol name')
                start = strings+offset
                end = data.find(b'\0', start, strings+string_size)
                S.check(end >= start, 'Unterminated symbol name')
                name = data[start:end].decode('ascii')
            else:
                name = raw.rstrip(b'\0').decode('ascii')
            auxiliary = data[at+18:at+18*(1+auxiliaries)]
            if section > 0 and (name, value, kind, storage, auxiliaries) == (sections[section][0], 0, 0, 3, 1):
                S.check(struct.unpack_from('<I', auxiliary)[0] == sections[section][1], 'Section-symbol size disagrees with its header')
                auxiliary = bytes(4)+auxiliary[4:]
            rows.append((index, name, value, section, kind, storage, auxiliaries, auxiliary.hex()))
            index += 1+auxiliaries
        return rows, sections, entries, data[strings:strings+string_size]

    before, old_sections, old_entries, old_strings = read(old)
    after, new_sections, new_entries, new_strings = read(new)
    S.check(old_entries == new_entries and len(before) == len(after) and old_strings == new_strings,
          'JCLS symbol index domain or string table changed')

    def anchor(rows, name):
        found = [(r[3], r[2]) for r in rows if r[1] == name]
        S.check(len(found) == 1 and found[0][0] > 0, 'Missing or ambiguous JCLS symbol anchor')
        return found[0]

    old_record_section, old_records = anchor(before, 'boom_java_class_records')
    new_record_section, new_records = anchor(after, 'boom_java_class_records')
    old_BSS_section, old_reverse = anchor(before, 'boom_java_class_reverse')
    new_BSS_section, new_reverse = anchor(after, 'boom_java_class_reverse')
    S.check(old_record_section == new_record_section and old_BSS_section == new_BSS_section and
          old_sections[old_record_section][0] == new_sections[new_record_section][0] == '.rdata' and
          old_sections[old_BSS_section][0] == new_sections[new_BSS_section][0] == '.bss',
          'JCLS symbol anchor sections changed')
    digest = hashlib.sha256()
    for original, current in zip(before, after):
        index, name, value, section, kind, storage, auxiliaries, auxiliary = original
        expected = value
        if section == old_record_section and value >= old_records:
            expected += new_records-old_records
        elif section == old_BSS_section and value >= old_reverse:
            expected += new_reverse-old_reverse
        S.check(current == (index, name, expected, section, kind, storage, auxiliaries, auxiliary),
              'JCLS relocation symbol target or auxiliary contract changed at index '+str(index))
        digest.update(json.dumps(original, separators=(',', ':')).encode()+b'\n')
    return dict(symbol_entries=old_entries, symbol_records=len(before), indexed_symbol_contract_sha256=digest.hexdigest(),
                rdata_symbol_shift=new_records-old_records, BSS_symbol_shift=new_reverse-old_reverse)



def binary_equivalence(old, new, before, after):
    original, current = sections(old), sections(new)
    S.check(list(original) == list(current) and all(original[k]['flags'] == current[k]['flags'] for k in original),
            'JCLS COFF section inventory or flags differ')
    S.check(R.coff_procedures(old) == R.coff_procedures(new) and A.coff_symbols(old) == A.coff_symbols(new),
            'Original instructions, unwind, complete code relocations, or ABI symbols changed')
    S.check(R.physical_pool(old, before) == R.physical_pool(new, after),
            'Original writable pool, Class records/names/relocations or contiguous root layout changed')
    symbols = symbol_contract(old, new)
    root_delta = len(after['modules'])-len(before['modules'])
    S.check(current['.bss']['size'] == original['.bss']['size'] + 8*root_delta and
            not current['.bss']['data'] and not current['.bss']['relocations'], 'BSS changed beyond one module root per append')
    S.check(original['.data']['relocations'] == current['.data']['relocations'], 'Writable pool relocations changed')
    S.check(debug_without_object_name(original['.debug$S']['data'], old) ==
            debug_without_object_name(current['.debug$S']['data'], new) and
            not original['.debug$S']['relocations'] and not current['.debug$S']['relocations'],
            'Assembler debug data changed beyond the actual new object path')
    allowed = {'.data', '.rdata', '.bss', '.debug$S'}
    for name in original.keys()-allowed:
        S.check(original[name] == current[name], 'Non-data COFF section changed')
    return dict(original_procedures=R.coff_procedures(old), physical_pool=R.physical_pool(new, after),
                indexed_symbol_contract=symbols,
                definitions_and_imports_equal=True, writable_relocations_equal=True, section_flags_equal=True,
                BSS_added_bytes=8*root_delta, debug_change='object_path_only')


def derived(base, appended, asm, obj, delta):
    result = deepcopy(base)
    jcls = result['class_literals']
    jcls['modules'].extend(appended)
    jcls['root_cells'] += len(appended)
    [unit] = jcls['units']
    unit.update(assembly=artifact(asm), object=artifact(obj), body_bytes=unit['body_bytes']+delta, assembler_cache=None)
    return result


def validate(state_file, batch, names, parent_summary_sha, parent_verification_sha):
    state_file, batch = Path(state_file).resolve(), Path(batch).resolve()
    S.check(state_file.is_relative_to(S.ART) and batch.is_relative_to(S.ART/'named-module-batches'), 'Project candidate roots required')
    state = S.read(state_file)
    S.check(state['status'] == 'accepted' and state['runtime_acceptance_complete'] and
            state['batch_summary_sha256'] == parent_summary_sha and
            state['batch_verification_sha256'] == parent_verification_sha,
            'Use an accepted original runtime state with the exact parent batch receipts')
    parent, plan = Path(state['batch']).resolve(), Path(state['plan']).resolve()
    S.check(parent != batch and parent.is_relative_to(S.ART) and plan.is_relative_to(S.ART), 'Distinct original parent batch required')
    base = S.read(parent/'summary.json')
    S.check(S.digest(parent/'summary.json')['sha256'] == parent_summary_sha and
            S.digest(parent/'verification.json')['sha256'] == parent_verification_sha, 'Locked parent summary or full proof changed')
    resolve, identity = R.verified_resolver(parent, base, plan)
    rows, graph = source_graph(base, plan, names)
    runtime, frame = Path(state['runtime']).resolve(), Path(state['frame_manifest']).resolve()
    S.check(runtime.is_relative_to(S.ART) and frame.is_relative_to(S.ART), 'Original frame/runtime must remain project owned')
    dll = artifact(runtime/'boom-runtime.dll')
    S.check(dll['digest']['sha256'] == state['runtime_sha256'], 'Original assembly runtime DLL changed')
    frame_meta = S.read(frame)
    frame_proof = S.read(frame.with_name('verification.json'))
    S.check(frame_proof['verified'] and frame_proof['manifest_sha256'] == S.digest(frame)['sha256'] and
            S.digest(frame.with_name('verification.json'))['sha256'] == state['frame_verification_sha256'],
            'Original native frame proof changed')
    for record in (frame_meta['assembly'], frame_meta['object']):S.checked(record)
    parent_records = dict(state=artifact(state_file), summary=artifact(parent/'summary.json'),
        verification=artifact(parent/'verification.json'), plan=artifact(plan/'summary.json'),
        source_classes=artifact(plan/'classes.jsonl'), frame=artifact(frame),
        frame_verification=artifact(frame.with_name('verification.json')), frame_assembly=artifact(frame_meta['assembly']['path']),
        frame_object=artifact(frame_meta['object']['path']), runtime_dll=dll, runtime_metadata=artifact(runtime/'runtime.json'))
    return base, parent, plan, resolve, identity, rows, graph, parent_records


def reconstruct(batch, summary=None, plan=None):
    batch = Path(batch).resolve()
    evidence = S.read(batch/PROOF)
    S.check(evidence['schema'] == 2 and evidence['tools'] == tools() and
            all(evidence[k] is False for k in ('full_batch_reverified', 'full_selection_reverified', 'accepted')) and
            evidence['required_native_pack_regeneration'] == ['normal-boot-unnamed-module-v1'],
            'Named-module producer sources, scope, or required exact-capacity native regeneration changed')
    inputs = evidence['parent_inputs']
    given_plan = plan
    base, parent, plan, resolve, identity, rows, graph, records = validate(inputs['state']['path'], batch,
        evidence['requested_modules'], inputs['summary']['digest']['sha256'], inputs['verification']['digest']['sha256'])
    S.check(given_plan is None or Path(given_plan).resolve() == plan, 'Named module source plan differs')
    S.check(records == inputs and rows == evidence['appended'] and graph == evidence['source_graph'] and
            identity == evidence['parent_derivation'], 'Original graph, parent provenance, or input bytes changed')
    [unit] = base['class_literals']['units']
    old_asm, old_obj = (resolve(parent, unit[k], 'class-literals') for k in ('assembly', 'object'))
    text, changes = overlay(old_asm.read_bytes(), base['class_literals'], rows)
    asm, obj = batch/'class-literals/0000.asm', batch/'class-literals/0000.obj'
    S.check(asm.read_bytes() == text and changes == evidence['declaration_changes'], 'Changes exceed the four exact JCLS data declarations')
    expected = derived(base, rows, asm, obj, len(text)-old_asm.stat().st_size)
    S.check(expected == S.read(batch/'summary.json') and (summary is None or summary == expected),
            'Derived metadata changed outside the one JCLS unit/module roots')
    binary = binary_equivalence(old_obj, obj, base['class_literals'], expected['class_literals'])
    S.check(binary == evidence['binary_equivalence'], 'Physical JCLS equivalence changed')
    S.check(artifact(evidence['assembler']['path']) == evidence['assembler'], 'Original assembler changed')
    S.check(artifact(batch/'summary.json') == evidence['derived_summary'] and
            artifact(batch/'jcls-assembler.log') == evidence['assembler_log'], 'Generated artifact seal changed')
    return dict(summary=expected, base=base, parent=parent, plan=plan, resolve=resolve,
                parent_identity=identity, rows=rows, graph=graph, evidence=evidence)


def source_contract(batch, summary, plan=None):
    """Recompute the entire data append before granting two-root artifact access."""
    batch = Path(batch).resolve()
    current = reconstruct(batch, summary, plan)
    base, parent, previous = current['base'], current['parent'], current['resolve']
    retained = R.retained_records(base)
    [old] = base['class_literals']['units']
    [new] = summary['class_literals']['units']
    added = {R.record_key(new[k]) for k in ('assembly', 'object')}
    removed = {R.record_key(old[k]) for k in ('assembly', 'object')}

    def resolve(root, record, subdirectory=''):
        S.check(Path(root).resolve() == batch, 'Unexpected named-module source root')
        S.check(not subdirectory or (Path(subdirectory).name == subdirectory and subdirectory not in ('.', '..')),
                'Expected a single named-module artifact subdirectory')
        key = R.record_key(record)
        if key in added:
            path = Path(record['path']).resolve()
            S.check(subdirectory == 'class-literals' and path.parent == batch/'class-literals' and
                    artifact(path) == record, 'New JCLS artifact path or full digest changed')
            return path
        S.check(key in retained and key not in removed, 'Artifact is not retained in the certified named-module parent')
        return previous(parent, record, subdirectory)

    home = previous.verified_original_vm_image_home
    resolve.verified_original_vm_image_home = home
    scope = dict(scope='parent_verified_batch_plus_source_reconstructed_named_JCLS_unit',
        parent=current['evidence']['parent_inputs'], parent_derivation=current['parent_identity'],
        derivation=artifact(batch/PROOF), summary=artifact(batch/'summary.json'), appended=current['rows'],
        source_graph=current['graph']['inputs'], vm_image_home=str(home), resolver_sources=tools())
    return resolve, scope


def check_full_receipt(receipt, parent, scope):
    expected = dict(parent, named_module_derivation=scope)
    S.check(receipt == expected, 'Full named-module receipt differs from complete independently verified parent coverage')


def verified_resolver(batch, summary, plan=None):
    resolve, scope = source_contract(batch, summary, plan)
    receipt = S.read(Path(batch)/'verification.json')
    S.check(receipt.get('verified') is True, 'A genuine full named-module verification receipt is required')
    check_full_receipt(receipt, S.read(scope['parent']['verification']['path']), scope)
    return resolve, dict(**scope, full_verification=artifact(Path(batch)/'verification.json'))


def verify(batch):
    batch = Path(batch).resolve()
    current = reconstruct(batch)
    rows, base = current['rows'], current['base']
    return dict(schema=1, verified=True, scope='development_JCLS_named_module_data_append_only',
        derivation=artifact(batch/PROOF), summary=artifact(batch/'summary.json'), appended=rows,
        original_Java_units_retained=sum(len(s['units']) for s in base['shards']), original_Java_units_regenerated=0,
        source_type_index_unchanged=True, original_IDs_unchanged=True, native_frame_bytes_unchanged=True,
        original_runtime_DLL_unchanged=True, instruction_unwind_and_relocations_equal=True,
        full_selection_reverified=False, full_batch_reverified=False, runtime_executed=False,
        accepted=False, required_native_pack_regeneration=['normal-boot-unnamed-module-v1'])


def build(state_file, batch, names, parent_summary_sha, parent_verification_sha, assembler):
    batch, assembler = Path(batch).resolve(), Path(assembler).resolve()
    S.check(not batch.exists(), 'Use a fresh development named-module-batches directory')
    frozen_tools = tools()
    base, parent, plan, resolve, identity, rows, graph, records = validate(state_file, batch, names,
        parent_summary_sha, parent_verification_sha)
    [unit] = base['class_literals']['units']
    old_asm, old_obj = (resolve(parent, unit[k], 'class-literals') for k in ('assembly', 'object'))
    text, changes = overlay(old_asm.read_bytes(), base['class_literals'], rows)
    assembler_record = artifact(assembler)
    old_producer = S.read(parent/'boot-unnamed-derivation.json')['accepted_parent']['summary']
    [original_unit] = S.read(checked(old_producer))['class_literals']['units']
    S.check(assembler_record['digest']['sha256'] == original_unit['assembler_cache']['assembler_sha256'],
            'Use the original batch assembler')
    (batch/'class-literals').mkdir(parents=True)
    asm, obj = batch/'class-literals/0000.asm', batch/'class-literals/0000.obj'
    asm.write_bytes(text)
    with (batch/'jcls-assembler.log').open('xb') as log:
        subprocess.run([str(assembler), '/nologo', '/c', '/Fo'+str(obj), str(asm)],
                       stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, check=True)
    result = derived(base, rows, asm, obj, len(text)-old_asm.stat().st_size)
    binary = binary_equivalence(old_obj, obj, base['class_literals'], result['class_literals'])
    S.write(batch/'summary.json', result)
    evidence = dict(schema=2, scope='source_bound_named_JCLS_append_requires_separate_full_verification',
        tools=frozen_tools, parent_inputs=records, parent_derivation=identity, requested_modules=names,
        source_graph=graph, appended=rows, declaration_changes=changes, binary_equivalence=binary,
        derived_summary=artifact(batch/'summary.json'), assembler=assembler_record, assembler_log=artifact(batch/'jcls-assembler.log'),
        full_batch_reverified=False, full_selection_reverified=False, accepted=False,
        required_native_pack_regeneration=['normal-boot-unnamed-module-v1'])
    S.check(tools() == frozen_tools and all(artifact(r['path']) == r for r in records.values()), 'An original input or candidate tool changed')
    S.write(batch/PROOF, evidence)
    proof = verify(batch)
    S.write(batch/'jcls-candidate-verification.json', proof)
    return batch/'jcls-candidate-verification.json'


def verify_full(batch, ir):
    batch, ir = Path(batch).resolve(), Path(ir).resolve()
    S.check(ir.is_relative_to(S.ART), 'Use the original project source IR')
    summary = S.read(batch/'summary.json')
    resolve, scope = source_contract(batch, summary)
    full = module('verify-batch-assembly')
    helper = module('closure-batch-artifacts')
    full.artifact = helper.source_records(summary, resolve)
    plan = Path(scope['parent']['plan']['path']).parent
    verified = full.verify(batch, plan, ir)
    parent = S.read(scope['parent']['verification']['path'])
    # Keep the original, checked parent lineage annotation; every actual source,
    # method, data and COFF proof above was freshly calculated by the full verifier.
    for key in ('bootstrap_unnamed_derivation', 'sparse_original_vm_image_home'):
        if key in parent:
            verified[key] = parent[key]
    verified['named_module_derivation'] = scope
    check_full_receipt(verified, parent, scope)
    # Rehash/reconstruct after the expensive full pass before its receipt exists.
    _, final_scope = source_contract(batch, summary, plan)
    S.check(final_scope == scope, 'Named-module source inputs changed during full verification')
    target = batch/'verification.json'
    if target.exists():
        S.check(S.read(target) == verified, 'A different full named-module receipt already exists')
    else:
        with tempfile.TemporaryDirectory(dir=batch) as directory:
            temporary = Path(directory)/target.name
            S.write(temporary, verified)
            os.link(temporary, target)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    make = commands.add_parser('build')
    make.add_argument('--state', type=Path, required=True)
    make.add_argument('--module', action='append', required=True)
    make.add_argument('--parent-summary-sha256', required=True)
    make.add_argument('--parent-verification-sha256', required=True)
    make.add_argument('--assembler', type=Path, required=True)
    make.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('verify')
    check.add_argument('--output', type=Path, required=True)
    full = commands.add_parser('verify-full')
    full.add_argument('--output', type=Path, required=True)
    full.add_argument('--ir', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'build':
        print(build(args.state, args.output, args.module, args.parent_summary_sha256,
                    args.parent_verification_sha256, args.assembler))
    elif args.action == 'verify':
        print(json.dumps(verify(args.output), indent=2))
    else:
        print(verify_full(args.output, args.ir))
