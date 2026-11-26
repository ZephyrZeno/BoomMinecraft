"""Original platform Thread start, source upcalls and normal field layouts."""
import hashlib
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


R = module('thread_start_original_class_reader', 'verify-batch-frames.py')
CAPACITY = 16384
KERNELS = ['thread_registry.asm', 'thread_natives.asm', 'runtime_types.asm',
           'runtime_type_index.asm', 'types.asm', 'heap.asm', 'objects.asm',
           'classes32.asm', 'frames.asm', 'monitors.asm', 'field_address.asm']
FOREIGN = {'AcquireSRWLockExclusive', 'ReleaseSRWLockExclusive'}
POLICY = dict(normal_source_layouts=True, platform_threads_only=True,
    start_protocol_abi=2, start_protocol_bytes=88, source_Java_upcalls=True,
    subclass_run_dispatch='original_Runnable_run_contract', callback_publication='before_OS_create',
    startup_priority='verified_source_holder_priority_before_original_Java_run',
    failed_create_rolls_back_source_fields=True, completed_records='nonblocking_VM_reap',
    token_capacity=CAPACITY, inherited_fields='verified_runtime_field_maps',
    borrowed_field_addresses='nonmoving_heap_VM_lifetime', native_registration_table_extended=False,
    virtual_threads=False, automatic_gc=False, all_native_frames=False)


def kernel():
    text = (ROOT/'native/providers/normal_thread_start.asm.inc').read_text(encoding='utf-8')
    imports = set(re.findall(r'(?m)^EXTERN (\w+):PROC$', text))
    return re.sub(r'(?m)^EXTERN \w+:PROC\n', '', text), imports


def contracts(owner, raw, check):
    check(owner['name'] == 'java/lang/Thread' and owner['origin']['loader'] == 'bootstrap' and
          owner['origin']['source_id'] == 'jdk:java.base' and not owner['origin'].get('generated'),
          'Thread start requires original bootstrap Thread')
    check(len(raw) == len(owner['method_ids']), 'Thread start original inventory differs')
    by_signature = {(m['name'], m['descriptor']): (i, m) for i, m in zip(owner['method_ids'], raw)}
    i, native = by_signature['start0', '()V']
    check(native['access'] == 0x102 and native['code'] is None, 'Thread start0 native flags/Code differ')
    declaration = dict(method=i, class_id=owner['id'], class_sha256=owner['origin']['sha256'],
        loader='bootstrap', source_id='jdk:java.base', owner=owner['name'], name='start0',
        descriptor='()V', access=0x102, operation=0)
    upcalls = []
    for name, descriptor in [('run', '()V'), ('exit', '()V'),
                             ('dispatchUncaughtException', '(Ljava/lang/Throwable;)V'),
                             ('runWith', '(Ljava/lang/Object;Ljava/lang/Runnable;)V')]:
        mid, method = by_signature[name, descriptor]
        check(method['code'] is not None and not method['access'] & (8 | 0x100 | 0x400),
              'Thread lifecycle upcall must be original instance Java Code')
        check(method['access'] == {'run': 0x1, 'exit': 0x2, 'dispatchUncaughtException': 0,
                                   'runWith': 0x10}[name], 'Thread lifecycle upcall access differs')
        upcalls.append(dict(method=mid, class_id=owner['id'], owner=owner['name'], name=name,
            descriptor=descriptor, access=method['access'], class_sha256=owner['origin']['sha256'],
            code_sha256=hashlib.sha256(method['code'][0]).hexdigest()))
    return [declaration], upcalls


def index(summary, classes, S):
    names = {(c['origin']['loader'], c['name']): c for c in classes}
    owner, holder, virtual, throwable, runnable = [names['bootstrap', name] for name in
        ('java/lang/Thread', 'java/lang/Thread$FieldHolder', 'java/lang/BaseVirtualThread',
         'java/lang/Throwable', 'java/lang/Runnable')]
    for c in (owner, holder, virtual, throwable, runnable):
        S.check(c['origin']['source_id'] == 'jdk:java.base' and not c['origin'].get('generated'),
                'Thread lifecycle metadata requires original java.base classes')
    raw_name, raw = R.original_methods(S.original_class(summary, owner))
    S.check(raw_name == owner['name'], 'Thread start raw class identity differs')
    methods, upcalls = contracts(owner, raw, S.check)
    layouts = {}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['class_id'] in (owner['id'], holder['id']):
                S.check(row['candidate'] is not None and row['diagnostic'] is None and
                        row['source_sha256'] == classes[row['class_id']]['origin']['sha256'],
                        'Thread lifecycle normal layout/source differs')
                layouts[row['class_id']] = row['candidate']

    def field(c, name, descriptor, width):
        found = [f for f in layouts[c['id']]['fields'] if f['member']['owner'] == c['id'] and
                 (f['member']['name'], f['member']['descriptor']) == (name, descriptor)]
        S.check(len(found) == 1 and found[0]['storage_bytes'] == width, 'Thread lifecycle field width differs')
        f = found[0]
        S.check(c['fields'][f['member']['index']] == {k: f['member'][k] for k in ('name', 'descriptor', 'access')},
                'Thread lifecycle original field declaration differs')
        return dict(owner=c['id'], index=f['member']['index'], name=name, descriptor=descriptor,
                    width=width, base_offset=f['offset'],
                    map_id=sum(len(cls['fields']) for cls in classes[:c['id']])+f['member']['index'])

    fields = [field(owner, 'tid', 'J', 8), field(owner, 'eetop', 'J', 8),
               field(owner, 'holder', 'Ljava/lang/Thread$FieldHolder;', 8),
               field(holder, 'threadStatus', 'I', 4), field(holder, 'stackSize', 'J', 8)]
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as archive:
        available = {t['id']: t for line in archive.open('types.jsonl') if (t := json.loads(line))}
        wanted = {f['map_id']: f for f in fields}
        maps = {m['id']: m for line in archive.open('fields.jsonl')
                if (m := json.loads(line))['id'] in wanted}
    S.check(set(maps) == set(wanted), 'Thread lifecycle source field map is missing')
    for field_id, f in wanted.items():
        m = maps[field_id]
        S.check((m['declaring_class'], m['declaring_field'], m['storage_bytes'], m['reference']) ==
                (f['owner'], f['index'], f['width'], f['descriptor'].startswith('L')) and
                {row['receiver_class']: row['offset'] for row in m['rows']}.get(f['owner']) == f['base_offset'],
                'Thread lifecycle inherited field map contract differs')
        f['source_field_map'] = m
    for c in (owner, holder, virtual, throwable, runnable):
        t = available[c['id']]
        S.check(t['kind'] == (2 if c['access'] & 0x200 else 1) and
                t['source_sha256'] == c['origin']['sha256'], 'Thread lifecycle normal type identity differs')
    run_with = next(m for m in upcalls if m['name'] == 'runWith')
    compiled = None
    class_name = f"classes/{owner['id']:06}.json"
    for shard in summary['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as archive:
            if class_name in archive.namelist():
                S.checked(shard['zip'])
                compiled = json.loads(archive.read(class_name))
                break
    S.check(compiled is not None and compiled['source_sha256'] == owner['origin']['sha256'],
            'Thread lifecycle original compiled class missing')
    body = next(m for m in compiled['methods'] if m['id'] == run_with['method'])
    S.check(body['assembly_emitted'] and body['code_sha256'] == run_with['code_sha256'],
            'Thread runWith original generated body differs')
    runnable_name, runnable_raw = R.original_methods(S.original_class(summary, runnable))
    S.check(runnable_name == runnable['name'], 'Original Runnable class differs')
    run_ids = [i for i, m in zip(runnable['method_ids'], runnable_raw)
               if m['name'] == 'run' and m['descriptor'] == '()V' and m['access'] == 0x401 and m['code'] is None]
    S.check(len(run_ids) == 1, 'Original Runnable.run declaration differs')
    bindings = [b for b in body['bindings'] if b['kind'] == 'virtual_dispatch' and b['opcode'] == 185 and
                b['descriptor'] == '()V' and b['resolved_method'] == run_ids[0] and
                b['dispatch']['symbolic_owner'] == runnable['id'] and b['dispatch']['receiver_constraint'] == runnable['id']]
    S.check(len(bindings) == 1 and bindings[0]['dispatch']['interface'] and
            bindings[0]['label'] == f"boom_batch_call_{owner['id']}_{bindings[0]['constant']}_185",
            'Thread VM run upcall requires the original complete Runnable dispatch contract')
    return dict(schema=1, methods=methods, upcalls=upcalls, run_contract=bindings[0],
        thread_class=owner['id'], holder_class=holder['id'], virtual_class=virtual['id'],
        throwable_class=throwable['id'], runnable_class=runnable['id'], fields=fields,
        field_offsets=[f['base_offset'] for f in fields],
        capacity=CAPACITY, pool_bytes=256, pool_abi=1, start_bytes=88, start_abi=2,
        context_bytes=32, source_transform_chain='original_locked_no_transforms', game_started=False)


def data(m):
    calls = {c['name']: c for c in m['upcalls']}
    pointers = ['boom_heap_ptr', 'boom_runtime_type_map', 'boom_provider_thread_registry',
        f"boom_t{m['thread_class']}", f"boom_t{m['virtual_class']}", f"boom_t{m['holder_class']}",
        m['run_contract']['label'], f"boom_m{calls['exit']['method']}",
        f"boom_m{calls['dispatchUncaughtException']['method']}", f"boom_t{m['throwable_class']}"]
    out = '.data?\nALIGN 8\nprovider_thread_slots BYTE '+str(m['capacity']*64)+' DUP(?)\n'
    out += 'PUBLIC boom_provider_threads_roots\nboom_provider_threads_roots QWORD '+str(m['capacity'])+' DUP(?)\n'
    out += 'PUBLIC boom_provider_threads_failure\nboom_provider_threads_failure QWORD 4 DUP(?)\n'
    out += '.const\nPUBLIC boom_provider_threads_root_count\nboom_provider_threads_root_count QWORD '+str(m['capacity'])+'\n'
    out += '.data\nALIGN 8\nPUBLIC boom_provider_threads_pool\nboom_provider_threads_pool DWORD 050434C54h,1,0,'+str(m['capacity'])+'\n'
    out += ''.join(' QWORD OFFSET '+p+'\n' for p in pointers)
    out += ' QWORD OFFSET provider_thread_slots,OFFSET boom_provider_threads_roots,0\n DWORD 0,0\n'
    field_functions = [f"boom_field_map{f['map_id']}" for f in m['fields']]
    out += ''.join(' QWORD OFFSET '+p+'\n' for p in field_functions)
    out += ' QWORD 0,0,0,0,0,0,0,OFFSET boom_provider_threads_failure,0,0,0\n'
    return out, set(pointers+field_functions)


def exports(methods):
    return {'boom_provider_threads_pool', 'boom_provider_threads_service', 'boom_provider_threads_reap',
            'boom_provider_threads_close', 'boom_provider_threads_roots', 'boom_provider_threads_root_count',
            'boom_provider_threads_failure','boom_provider_threads_control_binding'} | {f"boom_m{m['method']}{suffix}" for m in methods for suffix in ('', '_native')}
