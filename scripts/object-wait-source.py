"""Bind original Object.wait0, Thread interruption, and the original checked exception constructor."""
import json
import zipfile

POOL = 'boom_provider_object_wait_pool'
SERVICE = 'boom_provider_object_wait_service'
CONTROL = {'boom_provider_object_wait_' + n for n in ('open','stop','close')}
FOREIGN = set()
KERNELS = ['object_wait.asm','monitors.asm','monitor_abort.asm','thread_registry.asm','heap.asm','field_address.asm',
           'objects.asm','classes32.asm','frames.asm','runtime_types.asm','runtime_type_index.asm','types.asm']
POLICY = dict(platform_threads=True, receiver_specific_interrupt_field=True, wait_reacquires_all_recursive_holds=True,
              Java_interruption='source_InterruptedException_constructor', other_blocking_domains='explicit_unsupported',
              VM_stop='shared_reference_controller_TLS_Context32', Java_run_success_on_VM_stop=False)
SPECS = [('java/lang/Object','wait0','(J)V',0x112),('java/lang/Thread','interrupt0','()V',0x102),
         ('java/lang/Thread','clearInterruptEvent','()V',0x10a)]


def index(summary,classes,S):
    names=('java/lang/Object','java/lang/Thread','java/lang/InterruptedException','java/lang/BaseVirtualThread')
    owners={c['name']:c for c in classes if c['origin']['loader']=='bootstrap' and c['name'] in names}
    S.check(set(owners)==set(names),'Missing original wait sources')
    frames=S.module('monitor_wait_original_classes','verify-batch-frames.py')
    members={}
    for name,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Original java.base wait source required')
        owner,methods=frames.original_methods(S.original_class(summary,c))
        S.check(name==owner and len(methods)==len(c['method_ids']),'Wait source inventory mismatch')
        members[name]={(m['name'],m['descriptor']):(mid,m) for mid,m in zip(c['method_ids'],methods)}
    declarations=[]
    for op,(name,method,desc,access) in enumerate(SPECS):
        cls=owners[name]
        mid,raw=members[name][method,desc]
        S.check(raw['code'] is None and raw['access']==access,'Original wait native flags or bytecode changed')
        declarations.append(dict(method=mid,class_id=cls['id'],class_sha256=cls['origin']['sha256'],loader='bootstrap',
                                 owner=name,source_id='jdk:java.base',name=method,descriptor=desc,access=access,operation=op))
    thread,exc=owners['java/lang/Thread'],owners['java/lang/InterruptedException']
    ctor,cm=members[exc['name']]['<init>','()V']
    S.check(cm['code'] and cm['access']==1 and exc['superclass']=='java/lang/Exception','InterruptedException constructor changed')
    fields=[i for i,f in enumerate(thread['fields']) if f==dict(name='interrupted',descriptor='Z',access=0x40)]
    S.check(len(fields)==1,'Original interrupted flag absent/ambiguous')
    field=fields[0]
    map_id=sum(len(c['fields']) for c in classes[:thread['id']])+field
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as z:
        fmap=next((r for line in z.open('fields.jsonl') if (r:=json.loads(line))['id']==map_id),None)
        types={r['id']:r for line in z.open('types.jsonl') if (r:=json.loads(line))['id'] in {c['id'] for c in owners.values()}}
    S.check(fmap and (fmap['declaring_class'],fmap['declaring_field'],fmap['storage_bytes'],fmap['reference'])==
            (thread['id'],field,1,False) and any(r['receiver_class']==thread['id'] for r in fmap['rows']),
            'Normal source field map does not bind original Thread.interrupted')
    S.check(all(types[c['id']]['source_sha256']==c['origin']['sha256'] for c in owners.values()),'Original runtime types changed')
    return dict(schema=1,owner=owners['java/lang/Object']['id'],methods=declarations,exception_class=exc['id'],
                thread_class=thread['id'],virtual_base=owners['java/lang/BaseVirtualThread']['id'],constructor=ctor,
                interrupted_field=field,interrupt_field_map=map_id,required_java_methods=[ctor],
                required_provider_families=['normal-reference-processing-v1','normal-thread-primitives-v1'],
                required_classes=sorted(c['id'] for c in owners.values()),pool_bytes=128,pool_abi=1,
                source_transform_chain='original_locked_no_transforms')


def native_imports(meta):
    proc={'boom_trace_enter','boom_trace_leave','boom_monitor_wait_open','boom_monitor_wait_stop','boom_monitor_wait_close',
          'boom_monitor_wait','boom_monitor_wait_interrupt','boom_provider_reference_issue_stop','boom_threads_current',
          'boom_heap_contains','boom_object_new','boom_runtime_type','boom_type_assignable',
          f"boom_field_map{meta['interrupt_field_map']}",f"boom_m{meta['constructor']}"}
    data={'boom_trace_pool','boom_heap_ptr','boom_provider_thread_registry','boom_provider_reference_pool','boom_runtime_type_map',
          f"boom_t{meta['virtual_base']}",f"boom_layout{meta['exception_class']}",f"boom_class{meta['exception_class']}"}
    data.update(f"boom_trace_method{m['method']}" for m in meta['methods'])
    return proc,data


def data(meta):
    values=['boom_heap_ptr','boom_provider_thread_registry',f"boom_field_map{meta['interrupt_field_map']}",None,
            f"boom_class{meta['exception_class']}",f"boom_layout{meta['exception_class']}",f"boom_m{meta['constructor']}",
            'boom_provider_reference_pool','boom_runtime_type_map',f"boom_t{meta['virtual_base']}"]
    return (f'.data\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 04941574Fh,1,0,0\n'+
            ''.join(f' QWORD OFFSET {v}\n' if v else ' QWORD 0\n' for v in values)+' QWORD 0,0,0,0\n')
