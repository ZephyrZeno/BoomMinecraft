"""Source projection for appending normal reference-capture Lambda metadata.

project_units consumes an explicit current unit graph and original dispatch
selection/catalogue. It changes only reconstructed metadata regions and whole
source-identified diagnostic tails. project verifies explicit file identities;
render returns MASM text. No assembly, linking, Java or runtime is executed.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tomllib
import zipfile

MODULES = {}
ROLES = ('runtime-globals', 'runtime-rows', 'Class-identities-and-names',
         'Unsafe-array-scales', 'Unsafe-field-class-ranges', 'Unsafe-field-pool',
         'Class-forName-capacity', 'contiguous-frames', 'selected-dispatch',
         'remaining-original-diagnostics')


def require(value, message):
    if not value:
        raise ValueError(message)


def installed_root():
    for path in Path(__file__).resolve().parents:
        cargo = path / 'Cargo.toml'
        if (cargo.is_file() and (path / 'scripts/constructor-provider-source.py').is_file()
                and (path / 'native/runtime/java_classes.asm').is_file()):
            with cargo.open('rb') as stream:
                if tomllib.load(stream).get('package', {}).get('name') == 'boom-minecraft':
                    return path
    raise ValueError('Installed project source/tool root not found')


def module(name):
    if name not in MODULES:
        key = 'lambda_runtime_append_' + name.replace('-', '_')
        spec = importlib.util.spec_from_file_location(key, installed_root() / 'scripts' / (name + '.py'))
        value = importlib.util.module_from_spec(spec)
        sys.modules[key] = value
        spec.loader.exec_module(value)
        MODULES[name] = value
    return MODULES[name]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=digest))


def checked(row):
    actual = artifact(row['path'])
    require(all(actual['digest'][key] == row['digest'][key] for key in ('size', 'sha256')),
            'Explicit source artifact changed: ' + row['path'])
    if 'sha1' in row['digest']:
        with Path(actual['path']).open('rb') as stream:
            require(hashlib.file_digest(stream, 'sha1').hexdigest() == row['digest']['sha1'],
                    'Explicit source artifact SHA1 changed: ' + row['path'])
    return Path(actual['path'])


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class Edit:
    def __init__(self, unit):
        self.unit = unit
        self.original = checked(unit['assembly']).read_bytes().decode('utf-8')
        self.text = self.original
        self.edits = []
        self.extern_prefix = ''

    def replace(self, before, after, label):
        require(before and self.text.count(before) == 1, 'Expected one exact source range: ' + label)
        at = self.text.index(before)
        self.text = self.text[:at] + after + self.text[at + len(before):]
        self.edits.append((before, after, label))

    def externs(self, symbols):
        existing = set(re.findall(r'(?m)^EXTERN (boom_\w+):', self.text))
        prefix = ''.join('EXTERN ' + name + ':' + ('PROC' if re.fullmatch(r'boom_m\d+', name) else 'BYTE') + '\n'
                         for name in sorted(set(symbols) - existing))
        self.text = prefix + self.text
        self.extern_prefix = prefix + self.extern_prefix

    def plan(self, **detail):
        require(self.text.startswith(self.extern_prefix), 'Added extern prefix changed')
        restored = self.text[len(self.extern_prefix):]
        for before, after, label in reversed(self.edits):
            require(restored.count(after) == 1, 'Exact inverse ambiguous: ' + label)
            restored = restored.replace(after, before, 1)
        require(restored == self.original, 'Complete source inverse differs: ' + self.unit['role'])
        return dict(role=self.unit['role'], original_assembly=self.unit['assembly'], replaced_object=self.unit['object'],
                    text=self.text, detail=detail, exact_complete_source_inverse=True,
                    edits=[dict(label=label, before_bytes=len(a.encode()), after_bytes=len(b.encode()),
                                before_sha256=sha(a), after_sha256=sha(b)) for a, b, label in self.edits],
                    added_externs=self.extern_prefix.splitlines())


def field_inputs(summary, manifest, raw_reader):
    """Retain original names/order; append derived names without reindexing."""
    with zipfile.ZipFile(checked(summary['unsafe_fields']['index'])) as archive:
        originals = [json.loads(row) for row in archive.read('fields.jsonl').splitlines()]
        arena = json.loads(archive.read('names.json'))
        ranges = json.loads(archive.read('ranges.json'))
    require(len(originals) == manifest['original_ranges']['fields'] and
            len(ranges) == manifest['original_ranges']['types'], 'Original UFMP dimensions differ')
    rows = copy.deepcopy(originals)
    for generated in manifest['generated']:
        fields = generated['layout']['fields']
        parsed = raw_reader.Source(checked(generated['class_file']).read_bytes())
        require(len(parsed.fields) == len(fields), 'Derived field declaration count differs')
        first = len(rows)
        for field, declaration in zip(fields, parsed.fields):
            require(field['id'] == len(rows) and field['index'] == len(rows) - first and
                    field['name'] == declaration['name'] and field['descriptor'] == declaration['descriptor'] and
                    declaration['access'] == 0x1012 and field['storage_bytes'] == 8 and field['reference'] is True and
                    field['offset'] == field['index'] * 8, 'Normal capture declaration/layout differs')
            encoded = field['name'].encode('utf-16-le', 'surrogatepass')
            units = [int.from_bytes(encoded[i:i+2], 'little') for i in range(0, len(encoded), 2)]
            require(0 < len(units) <= 65535 and field['descriptor'].startswith(('L', '[')), 'Reference field/name required')
            rows.append(dict(id=field['id'], class_id=generated['class_id'], class_sha256=generated['origin']['sha256'],
                             field_index=field['index'], name=field['name'], descriptor=field['descriptor'], access=declaration['access'],
                             kind=9, storage_bytes=8, reference=True, name_offset=len(arena), name_units=len(units),
                             address_map=field['id']))
            arena.extend(units)
        require(generated['type_id'] == len(ranges), 'Derived UFMP class ranges are not an exact append')
        ranges.append([first, len(fields)] if fields else [0, 0])
    require(len(rows) == manifest['appended_ranges']['fields'][1] and
            len(ranges) == manifest['appended_ranges']['types'][1], 'Aggregate field/type ranges differ')
    return rows, arena, ranges


def names_body(arena):
    return 'boom_java_unsafe_field_names LABEL WORD\n' + ''.join(
        ' WORD ' + ','.join(map(str, arena[at:at+16])) + '\n' for at in range(0, len(arena), 16))


def ranges_body(ranges):
    return 'boom_java_unsafe_field_ranges LABEL DWORD\n' + ''.join(f' DWORD {a},{b}\n' for a, b in ranges)


def pages_body(count):
    return 'boom_java_unsafe_field_pages LABEL QWORD\n' + ''.join(
        f' QWORD OFFSET boom_java_unsafe_field_page{i}\n' for i in range(count))


def field_page(rows, page):
    text = f'.const\nALIGN 8\nPUBLIC boom_java_unsafe_field_page{page}\nboom_java_unsafe_field_page{page} LABEL BYTE\n'
    for row in rows[page*1024:(page+1)*1024]:
        target = '0' if row['address_map'] is None else 'OFFSET boom_field_map' + str(row['address_map'])
        flags = int(row['reference']) | (2 if row['access'] & 8 else 0)
        text += (f" DWORD {row['class_id']},{row['field_index']},{row['access']},{row['kind']}\n"
                 f" DWORD {row['name_offset']},{row['name_units']},{row['storage_bytes']},{flags}\n"
                 f" QWORD {target},0\n DWORD {row['id']},0\n QWORD 0\n")
    return text


def jcls_body(summary, manifest, verifier):
    cls = summary['class_literals']
    with zipfile.ZipFile(checked(cls['index'])) as archive:
        rows = lambda name: [json.loads(line) for line in archive.read(name).splitlines()]
        mirrors = {row['type_id']: row for row in rows('types.jsonl')}
        names = rows('names.jsonl')
        canonical = rows('canonical_names.jsonl')
    for generated in manifest['generated']:
        mirrors[generated['type_id']] = generated['class_mirror']
        raw = generated['runtime_class_name'].encode('utf-16-le')
        units = [int.from_bytes(raw[i:i+2], 'little') for i in range(0, len(raw), 2)]
        existing = next((row['id'] for row in canonical if row['utf16'] == units), None)
        if existing is None:
            existing = len(canonical)
            hash_ = 0
            for unit in units:
                hash_ = (31 * hash_ + unit) & 0xffffffff
            canonical.append(dict(id=existing, utf16=units, java_hash=hash_, literal=None))
        names.append(dict(type_id=generated['type_id'], canonical=existing))
    capacity = manifest['appended_ranges']['types'][1]
    text = verifier.pool_body(cls['source_shape'], capacity, cls['loader_keys'], cls['modules'], mirrors, cls['reverse_slots'])
    text += verifier.names_body(cls['source_shape'], capacity, summary['string_literals']['source_layout'], names, canonical)
    return text, len(canonical)


def project_units(sources, prefix, aggregate, current_units, dispatch_selection, diagnostic_catalogue):
    """Read explicit original source/units and return (plans, model), without writes.

    sources is the maintained normal-lambda-source.Sources object. The original
    dispatch selection is explicit: it need not equal a newer selected-source
    epoch if unrelated ordinary Class additions retained its table prefixes.
    Every reconstruction must still match the actual current source verbatim.
    """
    old_count = len(prefix['generated'])
    require(aggregate['generated'][:old_count] == prefix['generated'] and len(aggregate['generated']) > old_count and
            aggregate['base'] == prefix['base'] and aggregate['original_ranges'] == prefix['original_ranges'],
            'Exact old generated prefix and original input namespace required')
    require(all(aggregate['appended_ranges'][k][0] == prefix['appended_ranges'][k][0] for k in ('types', 'methods', 'fields')),
            'Original namespace start changed')
    O = module('normal-lambda-overlay')
    require(sources.base == aggregate['base'], 'Explicit original source batch differs')
    summary = sources.summary
    appended = aggregate['generated'][old_count:]
    oldcap, newcap = (m['appended_ranges']['types'][1] for m in (prefix, aggregate))
    require(newcap == oldcap + len(appended) and oldcap == aggregate['original_ranges']['types'] + old_count,
            'Type namespace is not an exact append')
    old_fields, old_arena, old_ranges = field_inputs(summary, prefix, O.C.I)
    new_fields, new_arena, new_ranges = field_inputs(summary, aggregate, O.C.I)
    require(new_fields[:len(old_fields)] == old_fields and new_arena[:len(old_arena)] == old_arena and
            new_ranges[:len(old_ranges)] == old_ranges, 'Old field identities/names/ranges changed')
    oldfc, newfc = len(old_fields), len(new_fields)
    units = {unit['role']: unit for unit in current_units}
    require(len(units) == len(current_units) and set(ROLES) <= set(units), 'Explicit current unit roles must be unique and complete')
    plans = []

    edit = Edit(units['runtime-globals'])
    old_rows = summary['runtime_metadata']['runtime_rows'] + old_count
    edit.replace(f'boom_runtime_type_map DWORD 052545950h,2,{old_rows},{oldcap}',
                 f'boom_runtime_type_map DWORD 052545950h,2,{old_rows+len(appended)},{newcap}', 'runtime:row-type-counts')
    anchor = 'PUBLIC boom_batch_field_records\nboom_batch_field_records LABEL QWORD\n'
    descriptors = edit.text.split('boom_batch_type_descriptors LABEL QWORD\n', 1)[1].split(anchor, 1)[0]
    require(len(descriptors.splitlines()) == oldcap and all(re.fullmatch(r' QWORD (0|OFFSET boom_t\d+)', line)
            for line in descriptors.splitlines()), 'Actual old type-pointer directory shape differs')
    edit.replace(anchor, ''.join(f' QWORD OFFSET boom_t{g["type_id"]}\n' for g in appended) + anchor, 'runtime:type-pointer-tail')
    anchor = '.data?\nALIGN 8\nboom_batch_runtime_slots'
    pointers = edit.text.split('boom_batch_field_records LABEL QWORD\n', 1)[1].split(anchor, 1)[0]
    require(len(pointers.splitlines()) == oldfc and all(re.fullmatch(r' QWORD (0|OFFSET boom_batch_field_record\d+)', line)
            for line in pointers.splitlines()), 'Actual old field-pointer directory shape differs')
    added_fields = [field for g in appended for field in g['layout']['fields']]
    edit.replace(anchor, ''.join(f' QWORD OFFSET boom_batch_field_record{f["id"]}\n' for f in added_fields) + anchor,
                 'runtime:field-pointer-tail')
    edit.externs({f'boom_t{g["type_id"]}' for g in appended} | {f'boom_batch_field_record{f["id"]}' for f in added_fields})
    plans.append(edit.plan(type_capacity=newcap, field_pointer_count=newfc, old_pointer_prefix_preserved=True))

    edit = Edit(units['runtime-rows'])
    require(len(re.findall(r'(?m)^ QWORD (?:OFFSET boom_\w+|\d+),OFFSET boom_t\d+$', edit.text)) == old_rows,
            'Actual runtime row count differs')
    extra = ''.join(f' QWORD OFFSET boom_layout{g["type_id"]},OFFSET boom_t{g["type_id"]}\n DWORD {g["type_id"]},0\n'
                    f' QWORD {g["layout"]["payload_bytes"]}\n DWORD {g["layout"]["reference_prefix"]},0\n' for g in appended)
    edit.replace('\n\nEND', extra + '\n\nEND', 'runtime:normal-reference-row-tail')
    edit.externs({f'boom_{part}{g["type_id"]}' for g in appended for part in ('layout', 't')})
    plans.append(edit.plan(original_rows=old_rows, appended_rows=len(appended), actual_reference_layouts=[g['layout'] for g in appended]))

    edit = Edit(units['Class-identities-and-names'])
    before, old_names = jcls_body(summary, prefix, O.J)
    after, new_names = jcls_body(summary, aggregate, O.J)
    edit.replace(before, after, 'Class:identity-names-root-bank-append')
    edit.externs({f'boom_t{g["type_id"]}' for g in appended})
    plans.append(edit.plan(type_capacity=newcap, canonical_names=[old_names, new_names], old_modules_unchanged=True,
                           root_cells=newcap+len(summary['class_literals']['loader_keys'])+len(summary['class_literals']['modules']),
                           names_root_cells=new_names*2))

    edit = Edit(units['Unsafe-array-scales'])
    U = O.C.module('verify-batch-unsafe')
    with zipfile.ZipFile(checked(summary['unsafe_bootstrap']['index'])) as archive:
        scales = json.loads(archive.read('scales.json'))
        methods = [json.loads(line) for line in archive.read('methods.jsonl').splitlines()]
    unsafe = summary['unsafe_bootstrap']
    edit.replace(U.data(unsafe['class_id'], unsafe['constants_class_id'], scales+[0]*old_count, methods),
                 U.data(unsafe['class_id'], unsafe['constants_class_id'], scales+[0]*len(aggregate['generated']), methods),
                 'Unsafe:nonarray-scale-tail')
    plans.append(edit.plan(type_capacity=newcap, additional_nonarray_scales=len(appended)))

    edit = Edit(units['Unsafe-field-class-ranges'])
    # Encoded UTF16 data retains its exact old prefix. Re-render the final WORD
    # line deterministically so future appends use the same source projection.
    old_name_source = names_body(old_arena)
    new_name_source = names_body(new_arena)
    edit.replace(old_name_source, new_name_source, 'UFMP:UTF16-name-tail')
    edit.replace(ranges_body(old_ranges), ranges_body(new_ranges), 'UFMP:declaring-class-field-ranges')
    old_pages, new_pages = ((len(rows)+1023)//1024 for rows in (old_fields, new_fields))
    if old_pages != new_pages:
        edit.replace(pages_body(old_pages), pages_body(new_pages), 'UFMP:page-pointer-tail')
        edit.externs(f'boom_java_unsafe_field_page{page}' for page in
                     range(old_pages, new_pages))
    plans.append(edit.plan(type_capacity=newcap, name_units=len(new_arena), field_capacity=newfc,
                           appended_class_ranges=new_ranges[oldcap:], old_rows_unchanged=True))

    edit = Edit(units['Unsafe-field-pool'])
    old_last_page = field_page(old_fields, old_pages-1)
    new_page_tail = '\n'.join(field_page(new_fields, page) for page in range(old_pages-1, new_pages))
    edit.replace(old_last_page, new_page_tail, 'UFMP:real-Field64-record-tail')
    edit.replace(f'boom_java_unsafe_field_pool DWORD 055464D50h,2,{oldcap},{oldfc}',
                 f'boom_java_unsafe_field_pool DWORD 055464D50h,2,{newcap},{newfc}', 'UFMP:both-capacities')
    uf = summary['unsafe_fields']
    string = summary['string_literals']['source_layout']
    edit.replace(f" DWORD {len(old_arena)},{old_pages},{string['value_offset']},{string['coder_offset']},{uf['class_id']},64\n",
                 f" DWORD {len(new_arena)},{new_pages},{string['value_offset']},{string['coder_offset']},{uf['class_id']},64\n",
                 'UFMP:name-and-page-counts')
    edit.externs({f'boom_field_map{field["id"]}' for field in added_fields})
    plans.append(edit.plan(type_capacity=newcap, field_capacity=newfc, appended_Field64_rows=new_fields[oldfc:],
                           original_cookie_ABI=2, page_count=new_pages, original_Field64_rows_preserved=True))

    edit = Edit(units['Class-forName-capacity'])
    edit.replace(f'boom_java_class_lookup_pool DWORD 04A43464Eh,1,{oldcap},',
                 f'boom_java_class_lookup_pool DWORD 04A43464Eh,1,{newcap},', 'ClassLookup:capacity')
    plans.append(edit.plan(type_capacity=newcap, hidden_generated_names_not_discoverable_by_forName=True))

    edit = Edit(units['contiguous-frames'])
    old_frame_count = len(re.findall(r'(?m)^boom_trace_method\d+ DWORD', edit.text))
    new_methods = [method for g in appended for method in g['methods']]
    anchor = '.data\nALIGN 8\nPUBLIC boom_trace_pool\n'
    rows = ''.join(f'PUBLIC boom_trace_method{m["id"]}\nboom_trace_method{m["id"]} DWORD {m["id"]},{m["frame_flags"]}\n'
                   f' QWORD OFFSET boom_t{m["class_id"]}\n DWORD {m["code_length"]},{m["class_id"]}\n QWORD 0\n' for m in new_methods)
    edit.replace(anchor, rows+anchor, 'Frames:generated-Code-row-tail')
    edit.replace(f' DWORD {old_frame_count},0\n QWORD OFFSET boom_trace_methods,0,0',
                 f' DWORD {old_frame_count+len(new_methods)},0\n QWORD OFFSET boom_trace_methods,0,0', 'Frames:count')
    edit.externs({f'boom_t{g["type_id"]}' for g in appended})
    plans.append(edit.plan(original_rows=old_frame_count, appended_rows=new_methods, original_rows_byte_preserved=True))

    # Reconstruct the original dispatch recipes in memory, then alter only the
    # new receiver rows within the actual current source (which also contains
    # unrelated ordinary Class additions).
    catalogue = diagnostic_catalogue
    closure = dispatch_selection
    owners = {owner for g in appended for owner in g['type']['ancestors']}
    method_owner = {mid: cls['id'] for cls in sources.classes for mid in cls['method_ids']}
    tables = {key: table for key, table in closure['selected_dispatch_tables'].items()
              if method_owner[table['resolved_method']] in owners}
    limited = dict(closure, selected_dispatch_tables=tables)
    original_tables = ''.join(O.table_body(table).replace(f'PUBLIC boom_batch_vtable{key}\n', '')
                              for key, table in sorted(tables.items(), key=lambda item:int(item[0])))
    _, old_dispatch = O.dispatch_overlay(limited, prefix, sources, original_tables, [])
    _, new_dispatch = O.dispatch_overlay(limited, aggregate, sources, original_tables, [])
    old_map = {str(row['id']): row['appended_rows'] for row in old_dispatch}
    new_map = {str(row['id']): row['appended_rows'] for row in new_dispatch}
    edit = Edit(units['selected-dispatch'])
    new_targets = set()
    changed_tables = []
    for key, table in tables.items():
        old_tail, new_tail = old_map.get(key, []), new_map.get(key, [])
        require(new_tail[:len(old_tail)] == old_tail, 'Old dispatch receiver prefix changed')
        if old_tail == new_tail:
            continue
        before = O.table_body(dict(table, rows=table['rows']+old_tail)).replace(f'PUBLIC boom_batch_vtable{key}\n', '')
        after = O.table_body(dict(table, rows=table['rows']+new_tail)).replace(f'PUBLIC boom_batch_vtable{key}\n', '')
        edit.replace(before, after, 'Dispatch:receiver-tail:'+key)
        tail = new_tail[len(old_tail):]
        new_targets.update('boom_m'+str(row['target']) for row in tail if row['target'] is not None)
        changed_tables.append(dict(id=int(key), appended_rows=tail))
    require(changed_tables, 'No selected dispatch accepts an appended receiver')
    start = edit.text.index('boom_java_class_initialization_map LABEL QWORD\n')
    end = edit.text.index('\n.const', start)
    before = edit.text[start:end]
    require(before.count(' QWORD ') == oldcap, 'Actual initializer map capacity differs')
    after = before.rstrip('\n')+'\n'+''.join(f' QWORD OFFSET boom_class{g["class_id"]},0\n' for g in appended)+'\n'
    edit.replace(before, after, 'ClassLookup:actual-initializer-map-tail')
    edit.externs(new_targets | {'boom_class'+str(g['class_id']) for g in appended})
    plans.append(edit.plan(tables=changed_tables, type_capacity=newcap, unrelated_original_Class_and_roots_byte_preserved=True,
                           original_Java_functions_changed=False))

    edit = Edit(units['remaining-original-diagnostics'])
    labels = {g['contract']['binding_label'] for g in appended}
    diagnostics = [row for row in catalogue['rows'] if row['symbol'] in labels]
    require(len(diagnostics) == len(labels) and all(row['category'] == 3 for row in diagnostics),
            'Exact actual linked invokedynamic diagnostic rows required')
    D = O.C.module('probe-native-provider-prefix')
    transformed, complement = D.remove_stops(edit.original.encode('utf-8'), diagnostics, True, labels)
    # remove_stops already proves all complemented bytes. Preserve each full
    # exact removed procedure as an explicit replacement for our inverse too.
    removed = []
    total_removed = 0
    for span in complement['only_removed_PUBLIC_and_complete_PROCs']:
        fragment = edit.original[span['begin']:span['end']]
        position = span['begin'] - total_removed
        require(edit.text[position:position+len(fragment)] == fragment, 'Actual complete diagnostic span differs')
        edit.replace(fragment, '', 'Diagnostic:complete-indy-tail:'+span['symbol'])
        removed.append((position,fragment))
        total_removed += len(fragment)
    require(edit.text.encode('utf-8') == transformed, 'Independent diagnostic complement differs')
    restored = edit.text
    for position, fragment in reversed(removed):
        restored = restored[:position]+fragment+restored[position:]
    require(restored == edit.original, 'Exact whole diagnostic source inverse failed')
    # Empty replacements have no unique reverse marker; the dedicated helper
    # proves the exact complement. Record this unit without Edit.plan().
    plans.append(dict(role=edit.unit['role'], original_assembly=edit.unit['assembly'], replaced_object=edit.unit['object'],
                      text=edit.text, detail=dict(removed=diagnostics, complement=complement),
                      exact_complete_source_inverse=True, edits=[dict(label=label, before_sha256=sha(a), after_sha256=sha(b))
                                                                 for a,b,label in edit.edits], added_externs=[]))
    require([row['role'] for row in plans] == list(ROLES), 'Runtime role projection coverage differs')
    return plans, dict(schema=1, scope='normal_reference_lambda_runtime_append_source_only',
        producer=artifact(__file__), old_generated_count=old_count, appended_generated_count=len(appended),
        type_capacity=[oldcap,newcap], field_capacity=[oldfc,newfc],
        normal_capture_layouts=[g['layout'] for g in appended],
        original_Java_Code_changed=False, old_generated_prefix_preserved=True, original_source_ids_preserved=True,
        other_native_capacity_consumers_and_entry_roots_require_separate_integration=True,
        source_only=True, machine_or_behavior_verified=False,
        dependencies={name:artifact(installed_root()/'scripts'/(name+'.py')) for name in
            ('normal-lambda-overlay','normal-lambda-source','verify-normal-lambda-expansion','verify-batch-unsafe-fields',
             'verify-batch-classes','verify-batch-unsafe','probe-native-provider-prefix')})


def project(prefix_file, aggregate_file, aggregate_verification_file, unit_graph_file,
            dispatch_source_file, dispatch_verification_file, diagnostic_catalogue_file, *,
            batch, plan, selection_file, source_verification_file, unit_graph_verification_file=None):
    """Bind explicit files, including independent source and optional unit-graph proofs.

    Full Source verification and the original Lambda Class semantics verifier
    remain distinct inputs. An optional graph proof must bind this exact graph;
    its presence does not turn a newly projected source into machine acceptance.
    """
    prefix, aggregate, graph, dispatch, catalogue, selection, full_v = map(read,
        (prefix_file, aggregate_file, unit_graph_file, dispatch_source_file, diagnostic_catalogue_file,
         selection_file, source_verification_file))
    dispatch_v = read(dispatch_verification_file)
    require(dispatch_v['verified'] is True and
            dispatch_v['closure_manifest_sha256'] == artifact(dispatch_source_file)['digest']['sha256'],
            'Explicit original dispatch source and complete verification differ')
    require(full_v['verified'] is True and full_v['closure_manifest_sha256'] == artifact(selection_file)['digest']['sha256'] and
            aggregate['original_source_manifest'] == artifact(selection_file) and
            aggregate['original_source_full_verification'] == artifact(source_verification_file),
            'Aggregate must bind the explicit current original source and its complete verification')
    C = module('normal-lambda-source')
    sources = C.Sources(Path(batch), Path(plan))
    for selected in (selection, dispatch):
        require(selected['source_batch_summary_sha256'] == sources.base['batch_summary']['digest']['sha256'] and
                selected['source_classes_sha256'] == sources.base['source_classes']['digest']['sha256'],
                'Explicit selected source belongs to another original Class plan')
    original_verify = C.module('verify-normal-lambda-expansion')
    require(original_verify.verify(Path(aggregate_file)) == read(aggregate_verification_file),
            'Independent maintained original Lambda Class semantics verification differs')
    units = graph['units'] if isinstance(graph, dict) else graph
    require(isinstance(units, list), 'Explicit current unit graph must provide a unit list')
    selected_units = [row for row in units if row['role'] in ROLES]
    require(len(selected_units) == len(ROLES) and len({u['role'] for u in selected_units}) == len(ROLES),
            'Explicit current unit roles are incomplete or duplicated')
    for unit in selected_units:
        checked(unit['assembly'])
        checked(unit['object'])
        if isinstance(graph, dict) and 'objects' in graph:
            require(sum(item == unit['object'] for item in graph['objects']) == 1,
                    'Current role object is not present exactly once in the explicit object graph')
    graph_verified = unit_graph_verification_file is not None
    if graph_verified:
        graph_v = read(unit_graph_verification_file)
        require(graph_v['verified'] is True and graph_v['full_PE_byte_equal'] is True and
                graph_v['overlay'] == artifact(unit_graph_file),
                'Optional current object-graph proof must bind this exact full PE input graph')
    plans, model = project_units(sources, prefix, aggregate, units, dispatch, catalogue)
    model.update(prefix=artifact(prefix_file), aggregate=artifact(aggregate_file),
        aggregate_source_verification=artifact(aggregate_verification_file), unit_graph=artifact(unit_graph_file),
        source_manifest=artifact(selection_file), source_full_verification=artifact(source_verification_file),
        actual_dispatch_source=artifact(dispatch_source_file),
        actual_dispatch_source_full_verification=artifact(dispatch_verification_file),
        actual_linked_diagnostic_catalogue=artifact(diagnostic_catalogue_file),
        unit_graph_full_PE_proof=artifact(unit_graph_verification_file) if graph_verified else None,
        input_unit_graph_provenance_verified=graph_verified)
    return plans, model


def render(plans):
    require(len(plans) == len(ROLES) and {p['role'] for p in plans} == set(ROLES),
            'Runtime source rendering requires the complete unique role set')
    return {plan['role']: plan['text'] for plan in plans}


def output_target(value):
    target, root = Path(value).resolve(), installed_root()
    require(any(target.is_relative_to(root / name) for name in ('.boom', 'target', 'dist')),
            'Generated source output must stay in the installed project .boom, target or dist')
    require(not target.exists(), 'Generated source output must be create-new')
    return target


def main(args):
    output = output_target(args.output)  # Refuse output before any input read.
    plans, model = project(args.prefix, args.aggregate, args.aggregate_verification, args.unit_graph,
        args.dispatch_source, args.dispatch_verification, args.diagnostic_catalogue,
        batch=args.batch, plan=args.plan, selection_file=args.selection,
        source_verification_file=args.source_verification, unit_graph_verification_file=args.unit_graph_verification)
    texts = render(plans)
    output.mkdir(parents=True)
    records = []
    for plan in plans:
        path = output / (plan['role'] + '.asm')
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(texts[plan['role']])
        records.append(dict({key:value for key,value in plan.items() if key != 'text'}, assembly=artifact(path)))
    model['units'] = records
    with (output / 'source.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(model, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(source_model=artifact(output / 'source.json'), source_only=True,
                          machine_or_behavior_verified=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prefix', 'aggregate', 'aggregate-verification', 'unit-graph', 'dispatch-source',
                 'dispatch-verification', 'diagnostic-catalogue', 'batch', 'plan', 'selection',
                 'source-verification', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--unit-graph-verification', type=Path)
    main(parser.parse_args())
