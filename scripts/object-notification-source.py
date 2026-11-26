"""Original final Object notifications over the owned assembly monitor service."""
KERNELS=['classes32.asm','monitors.asm','heap.asm']
POLICY=dict(normal_source_layouts=True,monitor_abi=1,real_OS_monitor_owner=True,
    receivers='all_owned_Java_objects_including_arrays',Java_wait_set='proven_empty_only',
    nonempty_wait_metadata='explicit_error',Object_wait_implemented=False,Java_interruption=False,
    all_native_frames=False)


def contracts(owner,raw,S):
    S.check(owner['name']=='java/lang/Object' and owner['access']==0x21 and
        owner['origin']['loader']=='bootstrap' and owner['origin']['source_id']=='jdk:java.base' and
        not owner['origin'].get('generated') and len(raw)==len(owner['method_ids']),
        'Object notifications require original bootstrap Object')
    result=[]
    for op,name in enumerate(('notify','notifyAll')):
        found=[(i,m) for i,m in zip(owner['method_ids'],raw) if (m['name'],m['descriptor'])==(name,'()V')]
        S.check(len(found)==1 and found[0][1]['access']==0x111 and found[0][1]['code'] is None,
            'Object notification original public final native flags/Code differ')
        i,m=found[0]
        result.append(dict(method=i,class_id=owner['id'],class_sha256=owner['origin']['sha256'],loader='bootstrap',
            source_id='jdk:java.base',owner=owner['name'],name=name,descriptor='()V',access=0x111,operation=op))
    return result


def index(summary,classes,S):
    R=S.module('object_notification_original_reader','verify-batch-frames.py')
    found=[c for c in classes if (c['origin']['loader'],c['name'])==('bootstrap','java/lang/Object')]
    S.check(len(found)==1,'Original Object owner missing or ambiguous');owner=found[0]
    name,raw=R.original_methods(S.original_class(summary,owner));S.check(name==owner['name'],'Original Object identity differs')
    return dict(schema=1,methods=contracts(owner,raw,S),pool_bytes=32,pool_abi=1,
        source_transform_chain='original_locked_no_transforms',game_started=False)


def data():
    return ('.const\nALIGN 8\nPUBLIC boom_provider_object_notification_pool\n'
        'boom_provider_object_notification_pool DWORD 059464E4Fh,1\n QWORD OFFSET boom_heap_ptr\n QWORD 0,0\n')
