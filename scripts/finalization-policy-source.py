"""Original Finalizer policy query; no replacement for Java finalizer execution."""
KERNELS=['classes32.asm']
POLICY=dict(normal_source_layouts=True,finalization='enabled',policy_origin='default_VM_configuration',
    query_only=True,finalizer_registration_implemented=False,automatic_reference_processing=False,
    original_Java_finalizer_threads_retained=True,all_native_frames=False)


def contracts(owner,raw,S):
    S.check(owner['name']=='java/lang/ref/Finalizer' and owner['access']==0x30 and
        owner['origin']['loader']=='bootstrap' and owner['origin']['source_id']=='jdk:java.base' and
        not owner['origin'].get('generated') and len(raw)==len(owner['method_ids']),
        'Finalization policy requires original bootstrap Finalizer')
    enabled=[f for f in owner['fields'] if f['name']=='ENABLED']
    S.check(enabled==[dict(name='ENABLED',descriptor='Z',access=0x18)],'Original Finalizer ENABLED field differs')
    found=[(i,m) for i,m in zip(owner['method_ids'],raw) if (m['name'],m['descriptor'])==('isFinalizationEnabled','()Z')]
    S.check(len(found)==1 and found[0][1]['access']==0x10a and found[0][1]['code'] is None,
        'Finalization policy original private static native flags/Code differ')
    i,m=found[0]
    return [dict(method=i,class_id=owner['id'],class_sha256=owner['origin']['sha256'],loader='bootstrap',
        source_id='jdk:java.base',owner=owner['name'],name=m['name'],descriptor=m['descriptor'],access=0x10a,operation=0)]


def index(summary,classes,S):
    R=S.module('finalization_policy_original_reader','verify-batch-frames.py')
    found=[c for c in classes if (c['origin']['loader'],c['name'])==('bootstrap','java/lang/ref/Finalizer')]
    S.check(len(found)==1,'Original Finalizer owner missing or ambiguous');owner=found[0]
    name,raw=R.original_methods(S.original_class(summary,owner));S.check(name==owner['name'],'Original Finalizer identity differs')
    return dict(schema=1,methods=contracts(owner,raw,S),pool_bytes=32,pool_abi=1,enabled=True,
        other_native_declarations=[dict(method=i,name=m['name'],descriptor=m['descriptor'],access=m['access'],implemented=False)
            for i,m in zip(owner['method_ids'],raw) if m['access']&0x100 and m['name']!='isFinalizationEnabled'],
        source_transform_chain='original_locked_no_transforms',game_started=False)


def data():
    return ('.const\nALIGN 8\nPUBLIC boom_provider_finalization_policy_pool\n'
        'boom_provider_finalization_policy_pool DWORD 0504C4E46h,1,1,0\n QWORD 0,0\n')
