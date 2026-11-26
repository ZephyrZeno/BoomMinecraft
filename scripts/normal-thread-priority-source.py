"""Original Thread priority native and inherited normal-layout startup fields."""
import json
import re
import zipfile

KERNELS=['thread_registry.asm','thread_natives.asm','heap.asm','objects.asm',
         'runtime_types.asm','runtime_type_index.asm','types.asm','field_address.asm','classes32.asm']
POLICY=dict(normal_source_layouts=True,platform_threads_only=True,Java_priority_min=1,Java_priority_max=10,
    Windows_priority_policy=0,Java_field_update='original_Java_Thread_priority',
    startup_priority='before_original_Java_run_on_attached_worker',
    missing_or_finished_peer='no_OS_operation',native_registration_table_extended=False,
    all_native_frames=False)


def contracts(owner,raw,S):
    S.check(owner['name']=='java/lang/Thread' and owner['origin']['loader']=='bootstrap' and
        owner['origin']['source_id']=='jdk:java.base' and not owner['origin'].get('generated') and
        len(raw)==len(owner['method_ids']),'Thread priority requires original bootstrap Thread')
    found=[(i,m) for i,m in zip(owner['method_ids'],raw) if (m['name'],m['descriptor'])==('setPriority0','(I)V')]
    S.check(len(found)==1 and found[0][1]['access']==0x102 and found[0][1]['code'] is None,
            'Thread priority original private native flags/Code differ')
    return [dict(method=found[0][0],class_id=owner['id'],class_sha256=owner['origin']['sha256'],
        loader='bootstrap',source_id='jdk:java.base',owner=owner['name'],name='setPriority0',descriptor='(I)V',access=0x102,operation=0)]


def index(summary,classes,S):
    T=S.module('priority_normal_thread_fields','normal-thread-start-source.py')
    R=S.module('priority_original_class_reader','verify-batch-frames.py')
    thread=T.index(summary,classes,S);owner=classes[thread['thread_class']];holder=classes[thread['holder_class']]
    name,raw=R.original_methods(S.original_class(summary,owner));S.check(name==owner['name'],'Thread priority original owner differs')
    methods=contracts(owner,raw,S)
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        row=next(value for line in stream if (value:=json.loads(line))['class_id']==holder['id'])
    S.check(row['diagnostic'] is None and row['candidate'] is not None and row['source_sha256']==holder['origin']['sha256'],
            'Thread priority original holder layout differs')
    found=[f for f in row['candidate']['fields'] if f['member']['owner']==holder['id'] and
           (f['member']['name'],f['member']['descriptor'])==('priority','I')]
    S.check(len(found)==1 and found[0]['storage_bytes']==4,'Thread priority normal scalar field differs')
    f=found[0];member=f['member']
    S.check(holder['fields'][member['index']]=={k:member[k] for k in ('name','descriptor','access')},
            'Thread priority original field declaration differs')
    map_id=sum(len(c['fields']) for c in classes[:holder['id']])+member['index']
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as z:
        mapping=next(value for line in z.open('fields.jsonl') if (value:=json.loads(line))['id']==map_id)
    S.check((mapping['declaring_class'],mapping['declaring_field'],mapping['storage_bytes'],mapping['reference'])==
            (holder['id'],member['index'],4,False) and
            {r['receiver_class']:r['offset'] for r in mapping['rows']}.get(holder['id'])==f['offset'],
            'Thread priority normal source field map differs')
    priority=dict(owner=holder['id'],index=member['index'],name='priority',descriptor='I',width=4,
                  base_offset=f['offset'],map_id=map_id,source_field_map=mapping)
    return dict(schema=1,methods=methods,thread_class=owner['id'],holder_class=holder['id'],virtual_class=thread['virtual_class'],
        fields=[next(f for f in thread['fields'] if f['name']=='holder'),priority],
        pool_bytes=80,pool_abi=1,Windows_priorities=[-2,-2,-1,-1,0,0,1,1,2,2],
        source_transform_chain='original_locked_no_transforms',game_started=False)


def data(m):
    pointers=['boom_heap_ptr','boom_runtime_type_map','boom_provider_thread_registry',
        f"boom_t{m['thread_class']}",f"boom_t{m['virtual_class']}"]
    pointers += [f"boom_field_map{f['map_id']}" for f in m['fields']]
    out='.data\nALIGN 8\nPUBLIC boom_provider_thread_priority_pool\nboom_provider_thread_priority_pool DWORD 050525054h,1\n'
    out+=''.join(' QWORD OFFSET '+p+'\n' for p in pointers)+' QWORD 0,0\n'
    return out,set(pointers)


def kernel(S):
    text=(S.ROOT/'native/providers/normal_thread_priority.asm.inc').read_text(encoding='utf-8')
    imports=set(re.findall(r'(?m)^EXTERN (\w+):PROC$',text))
    return re.sub(r'(?m)^EXTERN \w+:PROC\n','',text),imports


def exports(methods):
    return {'boom_provider_thread_priority_pool','boom_provider_thread_priority_service','boom_provider_thread_priority_start'}|{
        f"boom_m{m['method']}{s}" for m in methods for s in ('','_native')}
