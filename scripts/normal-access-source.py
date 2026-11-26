"""Normal AccessController source declarations, layouts and real frame views."""
import importlib.util
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


R = module('normal_access_original', 'verify-batch-frames.py')
SPECS = (('getStackAccessControlContext', '()Ljava/security/AccessControlContext;', 0x10a),
         ('getInheritedAccessControlContext', '()Ljava/security/AccessControlContext;', 0x108),
         ('ensureMaterializedForStackWalk', '(Ljava/lang/Object;)V', 0x10a))
KERNELS = ['frames.asm', 'classes32.asm', 'heap.asm', 'objects.asm', 'runtime_types.asm',
           'runtime_type_index.asm', 'types.asm', 'thread_registry.asm', 'java_classes.asm']
POLICY = dict(normal_source_layouts=True, source_frame_abi=3, pool_abi=2,
    application_domains_require_explicit_binding=True, privileged_frame_locals='original_source_layout',
    current_Context_only=True, unknown_frame_or_domain='explicit_error', arbitrary_off_heap=False,
    automatic_gc=False, all_native_frames=False)


def kernel():
    text = (ROOT/'native/providers/normal_access.asm.inc').read_text(encoding='utf-8')
    imports = set(re.findall(r'(?m)^EXTERN (\w+):PROC$', text))
    return re.sub(r'(?m)^EXTERN \w+:PROC\n', '', text), imports


def index(summary, classes, overlay, S):
    names = {(c['origin']['loader'], c['name']): c for c in classes}
    owner = names['bootstrap', 'java/security/AccessController']
    acc = names['bootstrap', 'java/security/AccessControlContext']
    thread = names['bootstrap', 'java/lang/Thread']
    pd = names['bootstrap', 'java/security/ProtectionDomain']
    for c in (owner, acc, thread, pd):
        S.check(c['origin']['source_id'] == 'jdk:java.base' and not c['origin'].get('generated'), 'Access VM inputs must be original java.base classes')
    raw_name, raw = R.original_methods(S.original_class(summary, owner))
    S.check(raw_name == owner['name'] and len(raw) == len(owner['method_ids']), 'AccessController original inventory differs')
    methods = []
    for operation, (name, desc, flags) in enumerate(SPECS):
        found = [(i, m) for i, m in zip(owner['method_ids'], raw) if (m['name'], m['descriptor']) == (name, desc)]
        S.check(len(found) == 1 and found[0][1]['access'] == flags and found[0][1]['code'] is None, 'AccessController original native declaration differs')
        i, m = found[0]
        methods.append(dict(method=i, class_id=owner['id'], class_sha256=owner['origin']['sha256'],
            loader='bootstrap', source_id='jdk:java.base', owner=owner['name'], name=name, descriptor=desc, access=flags, operation=operation))
    privileged = {}
    for i, m in zip(owner['method_ids'], raw):
        if m['name'] != 'executePrivileged':
            continue
        S.check(m['descriptor'] in ('(Ljava/security/PrivilegedAction;Ljava/security/AccessControlContext;Ljava/lang/Class;)Ljava/lang/Object;',
            '(Ljava/security/PrivilegedExceptionAction;Ljava/security/AccessControlContext;Ljava/lang/Class;)Ljava/lang/Object;') and
            m['access'] == 0x0a and m['code'] is not None and m['code'][2] >= 3, 'Privileged frame source contract differs')
        privileged[i] = [-8*(m['code'][1]+m['code'][2]), m['code'][2]]
    S.check(len(privileged) == 2, 'Both original privileged overloads are required')
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as z:
        types = [json.loads(line) for line in z.open('types.jsonl')]
    capacity = summary['runtime_metadata']['type_capacity']
    S.check(capacity == summary['class_literals']['type_capacity'] and 0 < capacity <= 1048576, 'Normal access type capacity differs')
    available = {t['id']: t for t in types}
    arrays = [t for t in types if t['name'] == '[Ljava/security/ProtectionDomain;' and t['defining_loader'] == 'bootstrap']
    S.check(len(arrays) == 1 and arrays[0]['kind'] == 3 and arrays[0]['parent_component'] == pd['id'], 'Normal ProtectionDomain[] type missing')
    for c in (acc, thread, pd):
        S.check(available[c['id']]['kind'] == 1 and available[c['id']]['source_sha256'] == c['origin']['sha256'], 'Normal access runtime type identity differs')
    layouts = {}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['class_id'] in {acc['id'], thread['id']}:
                S.check(row['candidate'] is not None and row['diagnostic'] is None and
                        row['source_sha256'] == classes[row['class_id']]['origin']['sha256'], 'Normal access layout/source differs')
                layouts[row['class_id']] = row['candidate']
    def offset(c, name, descriptor, width):
        found = [f for f in layouts[c['id']]['fields'] if f['member']['owner'] == c['id'] and
                 (f['member']['name'], f['member']['descriptor']) == (name, descriptor)]
        S.check(len(found) == 1 and found[0]['storage_bytes'] == width, 'Normal access field width differs')
        f = found[0]
        S.check(c['fields'][f['member']['index']] == {k: f['member'][k] for k in ('name', 'descriptor', 'access')}, 'Original access field declaration differs')
        return f['offset']
    offsets = [offset(acc, 'context', '[Ljava/security/ProtectionDomain;', 8),
        offset(acc, 'privilegedContext', 'Ljava/security/AccessControlContext;', 8),
        offset(acc, 'isPrivileged', 'Z', 1), offset(acc, 'isAuthorized', 'Z', 1),
        offset(thread, 'inheritedAccessControlContext', 'Ljava/security/AccessControlContext;', 8)]
    domain_bound = [0]*capacity
    for t in types:
        if t['kind'] not in (1, 2):
            domain_bound[t['id']] = 1
        else:
            c = classes[t['id']]
            domain_bound[t['id']] = int(c['origin']['loader'] == 'bootstrap' and
                c['origin']['source_id'].startswith('jdk:') and not c['origin'].get('generated'))
    row_lookup = {r[0]: r for r in overlay['source']['rows']}
    S.check(len(row_lookup) == len(overlay['source']['rows']), 'Duplicate source frame identities')
    frame_rows = []
    for i, flags, cls, length in overlay['source']['rows']:
        view_flags = (2 if flags & 8 else 0) | (4 if flags & 64 else 0)
        displacement, locals_count = privileged.get(i, (0, 0))
        if i in privileged:
            S.check(cls == owner['id'] and length > 0 and flags & 32 == 0, 'Privileged frame is not an original Java body')
            view_flags |= 1
        frame_rows.append([i, cls, view_flags, displacement, locals_count])
    S.check(set(privileged) <= set(row_lookup) and len(frame_rows) <= 1048576, 'Privileged method or frame capacity differs')
    return dict(schema=1, methods=methods, access_class=owner['id'], context_class=acc['id'], thread_class=thread['id'],
        domain_class=pd['id'], domain_array=arrays[0]['id'], type_capacity=capacity, field_offsets=offsets,
        frame_rows=frame_rows, method_capacity=max(row_lookup)+1, domain_bound=domain_bound,
        source_frame_abi=3, pool_abi=2, pool_bytes=192, application_domains_require_explicit_binding=True,
        original_privileged_method_ids=sorted(privileged), source_Java_codegen_rerun=False, game_started=False)


def data(meta):
    rows = {r[0]: r for r in meta['frame_rows']}
    out = '.const\nALIGN 8\nprovider_access_methods LABEL BYTE\n'
    for i in range(meta['method_capacity']):
        row = rows.get(i)
        if row is None:
            out += ' QWORD 0,0,0,0\n'
        else:
            _, cls, flags, displacement, locals_count = row
            out += f' QWORD OFFSET boom_trace_method{i}\n DWORD {cls},{flags}\n SDWORD {displacement}\n DWORD {locals_count}\n QWORD 0\n'
    out += '.data\nALIGN 4\nPUBLIC boom_provider_access_domain_bound\nboom_provider_access_domain_bound LABEL DWORD\n'
    values = meta['domain_bound']
    for at in range(0, len(values), 16):
        out += ' DWORD '+','.join(map(str, values[at:at+16]))+'\n'
    out += '.data?\nALIGN 8\nPUBLIC boom_provider_access_domain_roots\nboom_provider_access_domain_roots QWORD '+str(meta['type_capacity'])+' DUP(?)\n'
    out += '.const\nPUBLIC boom_provider_access_domain_root_count\nboom_provider_access_domain_root_count QWORD '+str(meta['type_capacity'])+'\n'
    out += '.data\nALIGN 8\nPUBLIC boom_provider_access_pool\nboom_provider_access_pool DWORD 050434341h,2,4,0\n'
    pointers = ['boom_heap_ptr', 'boom_runtime_type_map', 'boom_java_class_pool', 'boom_trace_pool',
        f"boom_class{meta['context_class']}", f"boom_layout{meta['context_class']}", f"boom_t{meta['domain_array']}",
        'boom_provider_thread_registry', f"boom_t{meta['context_class']}", f"boom_t{meta['domain_class']}"]
    out += ''.join(' QWORD OFFSET '+s+'\n' for s in pointers)
    out += ' DWORD '+','.join(map(str, meta['field_offsets']+[meta['type_capacity']]))+'\n'
    out += ' QWORD OFFSET boom_provider_access_domain_roots,OFFSET boom_provider_access_domain_bound,OFFSET provider_access_methods\n'
    out += f" DWORD {meta['method_capacity']},0\n QWORD OFFSET boom_t{meta['thread_class']},0,0,0,0\n"
    imports = set(pointers) - {'boom_provider_access_domain_roots', 'boom_provider_access_domain_bound'}
    imports |= {f'boom_trace_method{i}' for i in rows}
    imports.add(f"boom_t{meta['thread_class']}")
    return out, imports
