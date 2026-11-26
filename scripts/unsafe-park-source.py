"""Original Unsafe park/unpark, normal Thread ownership and private gate roots."""
import hashlib


OWNER='jdk/internal/misc/Unsafe'
POOL='boom_provider_unsafe_park_pool'
SERVICE='boom_provider_unsafe_park_service'
CONTROL={'boom_provider_unsafe_park_open','boom_provider_unsafe_park_close','boom_unsafe_park_slots',
         'boom_unsafe_park_gate_roots','boom_unsafe_park_counters'}
FOREIGN={'AcquireSRWLockExclusive','ReleaseSRWLockExclusive','AcquireSRWLockShared','ReleaseSRWLockShared','GetSystemTimeAsFileTime'}
KERNELS=['object_wait.asm','monitors.asm','monitor_abort.asm','reference_pending.asm','thread_registry.asm',
    'thread_natives.asm','field_address.asm','heap.asm','objects.asm','classes32.asm','frames.asm',
    'runtime_types.asm','runtime_type_index.asm','types.asm']
SPECS=[(OWNER,'park','(ZJ)V'),(OWNER,'unpark','(Ljava/lang/Object;)V')]
PINS={'unsafe.cpp':'7bf616ae2e10023e9a15eb5ec06577c03527c788bbe8e7d64ccaee7ca3d42c63',
    'os_windows.cpp':'b26b9c90f267a0e127a2539dd4b5923a7b4d9715b03ffd69dac3ce5fba558796',
    'park.hpp':'baecef82088384ba289ee754fc8b5a4ccc2de49b2f4e4c284057fb01a2520690',
    'Unsafe.java':'6132f783945a0e1e83337110d0b523c4b2088a8f5283821883f2efc1475b7fc1',
    'LockSupport.java':'c97f8ca3d6ee2f835e4410502fe2ec1eadebc6e67c91eddcb64ef9536e6c39c8',
    'Thread.java':'c7950ed483c9e4547c73fe2475f7dd802ff5ed433624593b03be7e25ac09639a'}
POLICY=dict(platform_threads_only=True,source_registry_FLS_required=True,normal_source_field_maps=True,
    live_target_identity='real_token_JavaId_and_source_oop',unstarted_or_terminated_target='no_op',
    null_unpark='no_op',unowned_attached_threads='explicit_unsupported',invalid_source_object='fail_closed',
    single_permit=True,early_unpark_remembered=True,wait_lock='private_per_thread_gate',global_lock_held_while_waiting=False,
    caller_Java_monitor_required=False,private_runtime_monitor=True,Object_wait_Java_frames_or_source_counts_added=False,
    Java_interruption='restore_source_interrupted_true_without_throwing',VM_stop='existing_exact_Context_TLS_token',
    negative_or_expired_time_preserves_permit=True,relative_nanoseconds='Windows_floor_to_ms_minimum_1',
    Windows_DWORD_timeout_truncation=True,zero_relative_time='infinite',absolute_milliseconds_since_epoch=True,
    gate_root_span_required=True,Thread_oop_keys_weak_and_never_dereferenced_after_retirement=True,
    retire_only_unborrowed_unowned_tokens=True,lifecycle_open_after_OWAI=True,lifecycle_close_after_workers_joined=True,
    nonmoving_heap=True,collection_requires_quiescence=True,automatic_GC_or_Cleaner=False,
    external_JNI_environment=False,source_transform_chain='original_locked_no_transforms')


def index(summary,classes,S):
    I=S.module('unsafe_park_original_class','verify-translation-ir.py')
    T=S.module('unsafe_park_existing_thread_start_model','normal-thread-start-source.py')
    O=S.module('unsafe_park_existing_interrupt_model','object-wait-source.py')
    thread=T.index(summary,classes,S);wait=O.index(summary,classes,S)
    wanted={OWNER,'java/lang/Object','java/lang/Thread','java/lang/BaseVirtualThread'}
    owners={row['name']:row for row in classes if row['origin']['loader']=='bootstrap' and row['name'] in wanted}
    S.check(set(owners)==wanted and thread['thread_class']==wait['thread_class']==owners['java/lang/Thread']['id'] and
        thread['virtual_class']==wait['virtual_base']==owners['java/lang/BaseVirtualThread']['id'] and
        (thread['pool_bytes'],thread['pool_abi'],thread['start_bytes'],thread['start_abi'])==(256,1,88,2) and
        (wait['pool_bytes'],wait['pool_abi'])==(128,1),'Park requires the accepted normal Thread/MWAI ownership ABI')
    methods=[];ctor=None
    for name,cls in owners.items():
        S.check(cls['origin']['source_id']=='jdk:java.base' and not cls['origin'].get('generated'),'Original java.base park source required')
        raw=I.Source(S.original_class(summary,cls))
        S.check(raw.name==name and len(raw.methods)==len(cls['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==cls['fields'],'Original park class inventory differs')
        for ident,method in zip(cls['method_ids'],raw.methods):
            key=name,method['name'],method['descriptor'];code=raw.code(method)
            if key in SPECS:
                S.check(method['access']==0x101 and code is None,'Original public instance park native changed')
                methods.append(dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],loader='bootstrap',
                    source_id='jdk:java.base',owner=name,name=method['name'],descriptor=method['descriptor'],
                    access=method['access'],operation=SPECS.index(key)))
            if key==('java/lang/Object','<init>','()V'):
                S.check(method['access']==1 and code and code['bytes']==b'\xb1','Original empty Object constructor changed')
                ctor=dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],owner=name,
                    name='<init>',descriptor='()V',code_sha256=hashlib.sha256(code['bytes']).hexdigest())
    S.check(len(methods)==2 and ctor,'Both original park natives and Object constructor required')
    peer=next(row for row in thread['fields'] if row['name']=='eetop')
    tid=next(row for row in thread['fields'] if row['name']=='tid')
    pinned=S.ART/'unsafe-park/pinned-sources/jdk-21.0.13+3'
    sources={name:S.artifact(pinned/name) for name in PINS}
    S.check(all(row['digest']['sha256']==PINS[name] for name,row in sources.items()),'Pinned Windows Parker semantics source changed')
    return dict(schema=1,owner=owners[OWNER]['id'],methods=sorted(methods,key=lambda row:row['operation']),
        source_classes={name:cls['id'] for name,cls in owners.items()},Object_constructor=ctor,
        peer_field=peer,tid_field=tid,interrupt_field_map=wait['interrupt_field_map'],
        original_thread_source_model=S.artifact(S.ROOT/'scripts/normal-thread-start-source.py'),
        original_wait_source_model=S.artifact(S.ROOT/'scripts/object-wait-source.py'),
        thread_start_ABI=dict(pool_bytes=256,pool_abi=1,slot_bytes=64,capacity=thread['capacity']),
        shared_wait_ABI=dict(pool_bytes=128,pool_abi=1,domain='MWAI72/1',controller='RPRC88/2'),
        required_classes=sorted(cls['id'] for cls in owners.values()),required_java_methods=[ctor['method']],
        required_base_modules=['runtime_metadata'],required_provider_families=['normal-thread-primitives-v1',
            'normal-thread-start-v1','normal-object-wait-v1','normal-reference-processing-v1'],
        native_root_spans=[dict(symbol='boom_unsafe_park_gate_roots',count=16384,kind='private_normal_Object_gates')],
        capacity=16384,slot_bytes=64,pool_bytes=128,pool_abi=1,native_sources=sources)


def native_imports(meta):
    procs=FOREIGN|{'boom_class_ensure32','boom_heap_contains','boom_object_check','boom_object_new','boom_runtime_type',
        'boom_type_assignable','boom_threads_current','boom_monitor_enter','boom_monitor_exit','boom_monitor_notify',
        'boom_monitor_wait','boom_provider_reference_issue_stop','boom_trace_enter','boom_trace_leave',
        f"boom_field_map{meta['interrupt_field_map']}",f"boom_field_map{meta['peer_field']['map_id']}",
        f"boom_field_map{meta['tid_field']['map_id']}",f"boom_m{meta['Object_constructor']['method']}"}
    classes=meta['source_classes']
    data={'boom_heap_ptr','boom_provider_thread_registry','boom_provider_threads_pool','boom_provider_object_wait_pool',
        'boom_provider_reference_pool','boom_runtime_type_map','boom_trace_pool',
        f"boom_layout{classes[OWNER]}",f"boom_t{classes['java/lang/Thread']}",f"boom_t{classes['java/lang/BaseVirtualThread']}",
        f"boom_class{classes['java/lang/Object']}",f"boom_layout{classes['java/lang/Object']}"}
    data|={f"boom_trace_method{row['method']}" for row in meta['methods']}
    return procs,data


def data(meta):
    cls=meta['source_classes'];values=['boom_heap_ptr','boom_provider_thread_registry','boom_provider_threads_pool',
        'boom_provider_object_wait_pool','boom_provider_reference_pool','boom_runtime_type_map',
        f"boom_layout{cls[OWNER]}",f"boom_t{cls['java/lang/Thread']}",f"boom_t{cls['java/lang/BaseVirtualThread']}",
        f"boom_field_map{meta['interrupt_field_map']}",f"boom_field_map{meta['peer_field']['map_id']}",
        f"boom_field_map{meta['tid_field']['map_id']}",'boom_unsafe_park_slots','boom_unsafe_park_gate_roots']
    return (f"UP_OBJECT_CLASS TEXTEQU <boom_class{cls['java/lang/Object']}>\n"
        f"UP_OBJECT_LAYOUT TEXTEQU <boom_layout{cls['java/lang/Object']}>\n"
        f"UP_OBJECT_CTOR TEXTEQU <boom_m{meta['Object_constructor']['method']}>\n"
        f'.data\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 04B524150h,1,0,0\n'+
        ''.join(' QWORD OFFSET '+value+'\n' for value in values))
