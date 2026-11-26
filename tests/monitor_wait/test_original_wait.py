"""Call the original retained image's receiver-dependent field-map code on actual JDK object layouts."""
import ctypes as c
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
import zipfile
from concurrent.futures import Future
from pathlib import Path

from test_wait import P, Q, U, I, Context, PLAN, INTERRUPTED, bind, require

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NAMES=('java/lang/Thread', 'java/lang/ref/Finalizer$FinalizerThread', 'java/lang/ref/Reference$ReferenceHandler',
       'java/util/TimerThread', 'java/lang/Object', 'java/lang/InterruptedException')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def ptr(address,off):
    return P.from_address(address+off).value


def word(address,off):
    return U.from_address(address+off).value


def symbol(dll,name):
    return c.addressof(c.c_ubyte.in_dll(dll,name))


def class_fields(binary, frames):
    r=frames.Reader(binary)
    require(r.number(4)==0xcafebabe,'original class magic')
    r.take(4)
    n=r.number(2)
    cp=[None]*n
    i=1
    while i<n:
        tag=r.number(1)
        if tag==1:
            cp[i]=frames.modified_utf8(r.take(r.number(2)))
        elif tag in (5,6):
            r.take(8)
            i+=1
        else:
            r.take({3:4,4:4,7:2,8:2,9:4,10:4,11:4,12:4,15:3,16:2,17:4,18:4,19:2,20:2}[tag])
        i+=1
    r.take(6)
    r.take(r.number(2)*2)
    fields=[]
    for _ in range(r.number(2)):
        flags,name,des=r.number(2),r.number(2),r.number(2)
        fields.append((cp[name],cp[des],flags))
        for _ in range(r.number(2)):
            r.take(2)
            r.take(r.number(4))
    return fields


def run(state_file,out):
    state=json.loads(state_file.read_bytes())
    batch_dir,plan_dir=Path(state['batch']),Path(state['plan'])
    source_dir=Path(state['diagnostic'])/'round-000'
    proof=json.loads((source_dir/'selection-verification.json').read_bytes())
    require(proof['verified'] and proof['closure_manifest_sha256']==sha(source_dir/'closure.json') and
            proof['diagnostic_manifest_sha256']==sha(source_dir/'diagnostic.json'),'retained source proof')
    cl=json.loads((source_dir/'closure.json').read_bytes())
    require(cl['source_batch_summary_sha256']==sha(batch_dir/'summary.json') and
            cl['source_classes_sha256']==sha(plan_dir/'classes.jsonl'),'selected plan/batch identities')
    batch=json.loads((batch_dir/'summary.json').read_bytes())
    fspec=importlib.util.spec_from_file_location('original_wait_raw',ROOT/'scripts/verify-batch-frames.py')
    frames=importlib.util.module_from_spec(fspec)
    fspec.loader.exec_module(frames)
    classes={}
    expected={}
    index=None
    nfields=0
    with (plan_dir/'classes.jsonl').open(encoding='utf8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['name'] in NAMES and row['origin']['loader']=='bootstrap':
                n=row['name']
                classes[n]=row
                binary=(Path(batch['frames']['original_system_catalog']['path']).parent/'image'/row['origin']['jar_entry']).read_bytes()
                require(row['origin']['source_id']=='jdk:java.base' and hashlib.sha256(binary).hexdigest()==row['origin']['sha256'],
                        'real java.base source '+n)
                binary_name,raw_methods=frames.original_methods(binary)
                require(binary_name==n,'original class name')
                if n=='java/lang/Thread':
                    fields=class_fields(binary,frames)
                    expected_field=('interrupted','Z',0x40)
                    require(fields.count(expected_field)==1,'original volatile boolean')
                    index=fields.index(expected_field)
                    require(row['fields'][index]==dict(name='interrupted',descriptor='Z',access=0x40),'plan volatile boolean')
                    map_id=nfields+index
                    require(any(m['name']=='interrupt0' and m['descriptor']=='()V' and m['access']==0x102 for m in raw_methods),
                            'original interrupt0')
                if n=='java/lang/Object':
                    for member,descriptor,access in (('wait0','(J)V',0x112),('notify','()V',0x111),('notifyAll','()V',0x111)):
                        require(any(m['name']==member and m['descriptor']==descriptor and m['access']==access for m in raw_methods),
                                'original Object.'+member)
                if n=='java/lang/InterruptedException':
                    require(any(m['name']=='<init>' and m['descriptor']=='()V' and m['code'] for m in raw_methods),
                            'original InterruptedException constructor')
            nfields+=len(row['fields'])
            if len(classes)==len(NAMES):
                break
    require(set(classes)==set(NAMES) and index is not None,'all original classes')
    zrec=batch['runtime_metadata']['index']
    require(sha(Path(zrec['path']))==zrec['digest']['sha256'],'source field maps index digest')
    with zipfile.ZipFile(zrec['path']) as archive:
        fmap=next(r for l in archive.open('fields.jsonl') if (r:=json.loads(l))['id']==map_id)
    require((fmap['declaring_class'],fmap['declaring_field'],fmap['storage_bytes'],fmap['reference'])==
            (classes['java/lang/Thread']['id'],index,1,False),'source field map identity')
    offsets={r['receiver_class']:r['offset'] for r in fmap['rows']}
    runtime=Path(state['runtime'])
    require(sha(runtime/'boom-runtime.dll')==json.loads((runtime/'runtime.json').read_bytes())['sha256'],'assembly runtime identity')
    image_file=source_dir/'diagnostic-image.dll'
    with os.add_dll_directory(str(runtime)):
        rt=c.CDLL(str(runtime/'boom-runtime.dll'))
        image=c.CDLL(str(image_file))
        kern=c.CDLL(str(out/'monitor-wait-production.dll'))
    # Resolve the original private mapper via the image's own source-bound UFM record.
    field_pool=symbol(image,'boom_java_unsafe_field_pool')
    class_pool=symbol(image,'boom_java_class_pool')
    type_map=symbol(image,'boom_runtime_type_map')
    require((word(field_pool,0),word(field_pool,4),ptr(field_pool,24),ptr(field_pool,32),word(field_pool,108))==
            (0x55464d50,1,class_pool,type_map,64),'image unsafe source field-pool ABI')
    require(map_id<word(field_pool,12) and map_id//1024<word(field_pool,92),'image record bounds')
    row=ptr(ptr(field_pool,80),(map_id//1024)*8)+(map_id%1024)*64
    require((word(row,0),word(row,4),word(row,8),word(row,24),word(row,28),word(row,48))==
            (classes['java/lang/Thread']['id'],index,0x40,1,0,map_id),'compiled field identity')
    name=c.wstring_at(ptr(field_pool,64)+word(row,16)*2,word(row,20))
    require(name=='interrupted','original compiled field name')
    mapper=ptr(row,32)
    require(mapper and ptr(class_pool,40)==type_map,'compiled mapper and type map')
    address_of=c.CFUNCTYPE(P,P,P)(mapper)
    table=ptr(type_map,16)
    wanted={r['id'] for r in classes.values()}
    layouts={}
    for i in range(word(type_map,8)):
        p=table+40*i
        key=word(p,16)
        if key in wanted and word(p,20)==0:
            require(key not in layouts,'unique runtime object type')
            layouts[key]=ptr(p,0)
    require(set(layouts)==wanted,'source layouts available')
    make=bind(rt,'object_new',P,P,P,P)
    heap=bind(rt,'heap_create',P,Q)(4<<20)
    reg=bind(rt,'threads_create',P,P,U)(heap,16)
    pool=bind(kern,'monitor_wait_open',P,P,P,P)(heap,reg,mapper)
    require(heap and reg and pool,'actual-image wait domain')
    next_id=bind(rt,'threads_next_id',Q,P)
    attach=bind(rt,'threads_attach',P,P,P,Q)
    detach=bind(rt,'threads_detach',U,P)
    enter=bind(rt,'monitor_enter',U,P,P,P)
    leave=bind(rt,'monitor_exit',U,P,P,P)
    wait=bind(kern,'monitor_wait',U,P,P,P,I)
    signal=bind(kern,'monitor_wait_notify',U,P,P,P)
    interrupt=bind(kern,'monitor_wait_interrupt',U,P,P)
    stop=bind(kern,'monitor_wait_stop',U,P)
    close=bind(kern,'monitor_wait_close',U,P)
    def ctx():
        return Context(0,0,0,PLAN)
    def oop(name):
        state=ctx()
        obj=make(heap,layouts[classes[name]['id']],state)
        require(obj and state[0]==0,'source heap allocation')
        return obj
    mon=oop('java/lang/Object')
    unknown=ctx()
    require(not address_of(mon,unknown) and unknown[0]==7,'actual mapper rejects non-Thread')
    for name in NAMES[:4]:
        root=oop(name)
        expected_offset=offsets[classes[name]['id']]
        field=address_of(root,ctx())
        require(field==root+expected_offset,'actual compiled per-object field address '+name)
        id_=next_id(reg)
        published=threading.Event()
        future=Future()
        outcome=INTERRUPTED if 'Finalizer' in name or 'TimerThread' in name else 0
        def worker():
            try:
                require(attach(reg,root,id_),'attach original Thread oop')
                require(enter(heap,mon,ctx())==0 and enter(heap,mon,ctx())==0,'original object lock')
                published.set()
                state=ctx()
                r=wait(pool,mon,state,0)
                require(r==outcome and list(state)==[0,0,0,PLAN],'actual-image monitor outcome')
                require(leave(heap,mon,ctx())==0 and leave(heap,mon,ctx())==0 and leave(heap,mon,ctx())==17,'exact original recursion')
                require(detach(reg)==0,'worker detach')
                future.set_result(r)
            except BaseException as e:
                future.set_exception(e)
        threading.Thread(target=worker,daemon=True).start()
        require(published.wait(3),'registered worker')
        # Ownership transfer is the barrier: the worker held this monitor recursively before publishing.
        require(enter(heap,mon,ctx())==0 and not future.done(),'waiter released all recursion')
        if outcome==INTERRUPTED:
            c.c_ubyte.from_address(field).value=1
            require(interrupt(pool,root)==0,'wake actual source object')
        else:
            require(signal(heap,mon,ctx())==0,'notify actual original thread')
        require(not future.done() and leave(heap,mon,ctx())==0,'reacquire ordering')
        require(future.result(3)==outcome and c.c_ubyte.from_address(field).value==0,'actual Java flag semantics')
        expected[name]={'offset':expected_offset,'native_reason':outcome}
    require(len({v['offset'] for v in expected.values()})>=2,'real source subtype layout variation')
    require(stop(pool)==0 and close(pool)==0 and bind(rt,'threads_destroy',U,P)(reg)==0 and
            bind(rt,'heap_destroy',U,P)(heap)==1,'real source probe shutdown')
    result={'original_image':str(image_file),'image_sha256':sha(image_file),'retained_source_closure':proof['closure_manifest_sha256'],
            'field_map_id':map_id,'original_native_wait0_declaration_verified':True,'execution':'isolated_wait_kernel_with_original_field_map_and_layouts',
            'source_threads':expected,'source_Object_wait0_wrapper_executed':False,'source_InterruptedException_constructed':False}
    (out/'original-image-observations.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    run(Path(sys.argv[1]),Path(sys.argv[2]))
