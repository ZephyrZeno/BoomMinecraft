"""Run original framed wait0, native interruption, Java catch and VM cancellation in a source-selected image."""
import argparse
import ctypes as c
import hashlib
import json
import os
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from test_wait import P,Q,U,I,Context,bind,require


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def symbol(d,name):
    return c.addressof(c.c_ubyte.in_dll(d,name))


def ptr(p,n):
    return P.from_address(p+n).value


def word(p,n):
    return U.from_address(p+n).value


def run(runtime,selection,out):
    image=selection/'diagnostic-image.dll'
    closure=json.loads((selection/'closure.json').read_bytes())
    proof=json.loads((selection/'selection-verification.json').read_bytes())
    require(proof['verified'] and proof['verified_assembly_objects'] and proof['closure_manifest_sha256']==sha(selection/'closure.json')
            and proof['diagnostic_manifest_sha256']==sha(selection/'diagnostic.json'),'original source and assembled object proof')
    identity=json.loads((runtime/'runtime.json').read_bytes())
    selected_runtime=json.loads((selection/'diagnostic.json').read_bytes())['global_provider_identity']
    require(Path(selected_runtime['runtime_dll']).resolve()==(runtime/'boom-runtime.dll').resolve() and
            selected_runtime['runtime_sha256']==identity['sha256']==sha(runtime/'boom-runtime.dll'),'selected runtime binary hash')
    packs={p['family']:p for i,r in enumerate(closure['runtime_provider_packs']) if i in closure['selected_runtime_provider_packs']
           and (p:=json.loads(Path(r['manifest']['path']).read_bytes()))}
    wait_pack=packs['normal-object-wait-v1']
    meta=json.loads(Path(wait_pack['object_wait_metadata']['path']).read_bytes())
    source={m['name']:m['method'] for m in wait_pack['methods']}
    notifications=packs['normal-object-notification-v1']
    source.update({m['name']:m['method'] for m in notifications['methods']})
    methods={int(k):v for k,v in closure['selected_methods'].items()}
    entries={(e['owner'],e['name']):e['method'] for e in closure['requested_method_roots']}
    require(all(mid in methods and methods[mid]['code_sha256'] for mid in entries.values()),
            'Every requested Java entry requires its verified original bytecode')
    lifecycle_methods={
        'java/lang/Thread':(('start','()V'),('join','()V'),('join','(J)V'),('run','()V'),('exit','()V'),('clearReferences','()V'),
                            ('isAlive','()Z'),('alive','()Z')),
        'java/util/TimerThread':(('run','()V'),('mainLoop','()V')),
        'java/util/TaskQueue':(('isEmpty','()Z'),),
    }
    class_names={r['class_id']:r['name'] for r in closure['selected_classes']}
    original_callbacks={f"{class_names[row['class_id']]}.{row['name']}{row['descriptor']}":
                        dict(method=mid,code_sha256=row['code_sha256']) for mid,row in methods.items()
                        if (row['name'],row['descriptor']) in lifecycle_methods.get(class_names.get(row['class_id']),())}
    require(len(original_callbacks)==sum(map(len,lifecycle_methods.values())) and
            all(row['code_sha256'] for row in original_callbacks.values()),'thread lifecycle source bytecode')
    with os.add_dll_directory(str(runtime)):
        rt=c.CDLL(str(runtime/'boom-runtime.dll'))
        guest=c.CDLL(str(image))
    def call(mid,ctx,*args):
        f=bind(guest,'m'+str(mid),Q,P,P)
        a=(Q*max(1,len(args)))(*args)
        return f(ctx,a)
    def clean(ctx,where):
        require(word(c.addressof(ctx),0)==0 and word(c.addressof(ctx),12)==0 and ctx[2]==0,f'{where} failed context={list(ctx)}')
    # The test owns the heap and fills only fields required to model a full
    # connected pipe and the original interruptLock of its synthetic peer.
    heap=bind(rt,'heap_create',P,Q)(32<<20)
    reg=bind(rt,'threads_create',P,P,U)(heap,32)
    require(heap and reg and bind(guest,'java_string_literals_bind_heap',U,P)(heap)==1,'heap and source literals binding')
    tp=symbol(guest,'boom_provider_thread_pool')
    require(bind(rt,'thread_native_bind',U,P,P)(reg,tp)==0,'source platform thread registry')
    ref=symbol(guest,'boom_provider_reference_pool')
    pool=symbol(guest,'boom_provider_object_wait_pool')
    require(bind(guest,'provider_reference_open',U,P)(ref)==0 and bind(guest,'provider_object_wait_open',U,P)(pool)==0,'open both stop domains')
    control=(Q*2).from_address(symbol(guest,'boom_provider_threads_control_binding'))
    require(list(control)==[0,0],'fresh platform worker control boundary')
    control[1]=ref
    control[0]=symbol(guest,'boom_provider_reference_boundary')
    cp=symbol(guest,'boom_java_class_pool')
    tmap=ptr(cp,40)
    table=ptr(tmap,16)
    classes={r['name']:r['class_id'] for r in closure['selected_classes']}
    ids=set(classes.values())
    layouts={}
    for n in range(word(tmap,8)):
        addr=table+n*40
        if word(addr,20)==0 and word(addr,16) in ids:
            layouts[word(addr,16)]=ptr(addr,0)
    make=bind(rt,'object_new',P,P,P,P)
    def new(name):
        ctx=Context()
        oop=make(heap,layouts[classes[name]],ctx)
        clean(ctx,name+' allocation')
        require(oop,name+' oop')
        return oop
    jthread=classes['java/lang/Thread']
    normal_cls={}
    field_owners={jthread,classes['java/io/PipedInputStream'],classes['java/lang/Thread$FieldHolder'],classes['java/util/TimerThread']}
    plan=Path(closure['plan'])
    with (plan/'classes.jsonl').open(encoding='utf8') as stream:
        for line in stream:
            cc=json.loads(line)
            if cc['id'] in field_owners:
                normal_cls[cc['id']]=cc
            if len(normal_cls)==len(field_owners):
                break
    # The actual UFM records locate inherited fields in the receiver's real layout.
    uf=symbol(guest,'boom_java_unsafe_field_pool')
    def field(oop,cls,name):
        id_=classes[cls]
        fields=normal_cls[id_]['fields']
        fi=next(i for i,f in enumerate(fields) if f['name']==name)
        ranges=ptr(uf,72)
        k=word(ranges,id_*8)+fi
        r=ptr(ptr(uf,80),k//1024*8)+k%1024*64
        require(word(r,0)==id_ and word(r,4)==fi and c.wstring_at(ptr(uf,64)+word(r,16)*2,word(r,20))==name,
                'compiled source field identity '+name)
        loc=c.CFUNCTYPE(P,P,P)(ptr(r,32))
        ctx=Context()
        address=loc(oop,ctx)
        clean(ctx,'field '+name)
        require(address,'missing address '+name)
        return address
    def new_thread(class_name='java/lang/Thread'):
        t=new(class_name)
        P.from_address(field(t,'java/lang/Thread','interruptLock')).value=new('java/lang/Object')
        return t
    next_id=bind(rt,'threads_next_id',Q,P)
    attach=bind(rt,'threads_attach',P,P,P,Q)
    detach=bind(rt,'threads_detach',U,P)
    enter=bind(rt,'monitor_enter',U,P,P,P)
    leave=bind(rt,'monitor_exit',U,P,P,P)
    root=new_thread()
    require(attach(reg,root,1),'main platform thread')
    observations={}
    progress=out.with_name(out.stem+'-progress.json')
    def record(where,item):
        observations[where]=item
        scratch=progress.with_suffix('.tmp')
        scratch.write_text(json.dumps(observations,indent=2)+'\n',encoding='utf-8')
        scratch.replace(progress)
        if where=='complete':
            progress.replace(out)
        print(where,json.dumps(item),flush=True)
    record('source_native_methods',source)
    record('source_exception_ctor',meta['constructor'])
    record('original_lifecycle_methods',original_callbacks)
    monitor=new('java/lang/Object')
    pipe=new('java/io/PipedInputStream')
    c.c_ubyte.from_address(field(pipe,'java/io/PipedInputStream','connected')).value=1
    # In the game System.initPhase1 installs this original JavaLangAccess before
    # Blocker.<clinit>. The isolated test owns a fresh heap and recreates only
    # that fixture field, using the exact java.base implementation and its type.
    secret=classes['jdk/internal/access/SharedSecrets']
    jla=[]
    field_id=None
    batch=json.loads((Path(closure['batch'])/'summary.json').read_bytes())
    directory=Path(batch['frames']['original_system_catalog']['path']).parent/'image'
    with (plan/'classes.jsonl').open(encoding='utf8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['origin']['loader']!='bootstrap':
                continue
            if row['id']==secret:
                field_id=next(i for i,f in enumerate(row['fields']) if f==dict(name='javaLangAccess',descriptor='Ljdk/internal/access/JavaLangAccess;',access=10))
            if row['name'].startswith('java/lang/System$') and 'jdk/internal/access/JavaLangAccess' in row['interfaces']:
                require(row['origin']['source_id']=='jdk:java.base' and sha(directory/row['origin']['jar_entry'])==row['origin']['sha256'],'original JavaLangAccess implementation')
                jla.append(row)
            if jla and field_id is not None:
                break
    require(len(jla)==1 and field_id is not None,'source SharedSecrets JavaLangAccess fixture')
    jla_layout=next(ptr(table+40*n,0) for n in range(word(tmap,8)) if word(table+40*n,16)==jla[0]['id'] and word(table+40*n,20)==0)
    init_ctx=Context()
    bind(rt,'class_ensure32',U,P,P)(symbol(guest,'boom_class'+str(secret)),init_ctx)
    clean(init_ctx,'SharedSecrets initialization')
    cell=P.from_address(symbol(guest,f'boom_s{secret}_{field_id}'))
    require(not cell.value,'fresh source SharedSecrets state')
    cell.value=make(heap,jla_layout,init_ctx)
    clean(init_ctx,'JavaLangAccess allocation')
    require(cell.value and ptr(cell.value,-8)==jla_layout,'actual source JavaLangAccess heap object')
    record('fixture_JavaLangAccess',jla[0]['name'])
    def acquire(oop,n=1):
        for _ in range(n):
            require(enter(heap,oop,Context())==0,'monitor enter')
    def release(oop,n=1):
        for _ in range(n):
            require(leave(heap,oop,Context())==0,'monitor exit')
    def verify_type(oop,name):
        require(oop and P.from_address(oop-8).value==layouts[classes[name]],'exact original class '+name)
    def wait_count(value,lifecycle_pool=None):
        by=time.monotonic()+7
        while Q.from_address(pool+96).value<value:
            if lifecycle_pool and word(lifecycle_pool,120)==2:
                raise AssertionError(f'Original Java worker failed before waiting: {list(Context.from_address(ptr(lifecycle_pool,224)))}')
            require(time.monotonic()<by,'source native did not enter waiting kernel')
            time.sleep(.001)
    def launch(method,object_,args=()):
        worker=new_thread()
        id_=next_id(reg)
        outcome=Future()
        def entry():
            try:
                require(attach(reg,worker,id_),'worker attach')
                acquire(object_,2)
                ctx=Context()
                call(method,ctx,object_,*args)
                status=word(c.addressof(ctx),0)
                if status==0xb002:
                    require(bind(guest,'provider_reference_boundary',U,P,P)(ctx,ref)==1,'same-thread VM-token consumption')
                    require(leave(heap,object_,Context())==17,'aborted recursive locks released')
                else:
                    release(object_,2)
                    require(leave(heap,object_,Context())==17,'restore exactly depth two')
                require(detach(reg)==0,'worker detach')
                outcome.set_result((status,list(ctx)))
            except BaseException as e:
                outcome.set_exception(e)
        threading.Thread(target=entry,daemon=True).start()
        return worker,outcome
    def enroll(f,count):
        deadline=time.monotonic()+8
        while not f.done() and Q.from_address(pool+96).value<count:
            require(time.monotonic()<deadline,'source waiter timed out before parking')
            time.sleep(.001)
        if f.done():
            raise AssertionError(f'source waiter returned before parking: {f.result()}')
        wait_count(count)
    def source_interrupt(worker):
        ctx=Context()
        call(entries['java/lang/Thread','interrupt'],ctx,worker)
        clean(ctx,'source Thread.interrupt')
    def native_interrupt(worker):
        c.c_ubyte.from_address(field(worker,'java/lang/Thread','interrupted')).value=1
        ctx=Context()
        call(source['interrupt0'],ctx,worker)
        clean(ctx,'framed source interrupt0')
    _,f=launch(source['wait0'],monitor,(0,))
    enroll(f,1)
    acquire(monitor)
    ctx=Context()
    call(source['notify'],ctx,monitor)
    clean(ctx,'source notify')
    require(not f.done(),'notification returns before waiter can reacquire')
    release(monitor)
    require(f.result(3)[0]==0,'source notify completion')
    record('source_notify',True)
    worker,f=launch(source['wait0'],monitor,(0,))
    enroll(f,2)
    acquire(monitor)
    native_interrupt(worker)
    release(monitor)
    kind,ctx=f.result(5)
    require(kind==16,f'constructed interrupt failed: {ctx}')
    verify_type(ctx[2],'java/lang/InterruptedException')
    record('source_wait0_InterruptedException',True)
    worker,f=launch(entries['java/lang/Object','wait'],monitor)
    enroll(f,3)
    acquire(monitor)
    source_interrupt(worker)
    release(monitor)
    kind,ctx=f.result(5)
    require(kind==16,f'original Object.wait did not rethrow: {ctx}')
    verify_type(ctx[2],'java/lang/InterruptedException')
    record('original_Object_wait_catch_rethrow',True)
    worker,f=launch(entries['java/io/PipedInputStream','awaitSpace'],pipe)
    enroll(f,4)
    acquire(pipe);source_interrupt(worker);release(pipe)
    kind,ctx=f.result(5)
    require(kind==16,f'original pipe catch failed: {ctx}')
    verify_type(ctx[2],'java/io/InterruptedIOException')
    record('original_PipedInputStream_typed_catch',{'input':'java/lang/InterruptedException','output':'java/io/InterruptedIOException'})
    def prepare_child(name):
        target=new_thread(name)
        holder=new('java/lang/Thread$FieldHolder')
        P.from_address(field(target,'java/lang/Thread','holder')).value=holder
        Q.from_address(field(target,'java/lang/Thread','tid')).value=next_id(reg)
        U.from_address(field(holder,'java/lang/Thread$FieldHolder','priority')).value=5
        return target,holder
    target,holder=prepare_child('java/lang/Thread')
    lifecycle=symbol(guest,'boom_provider_threads_pool')
    trace_offsets=(176,184,200,208)
    reap=bind(guest,'provider_threads_reap',U,P,P)
    def reap_child(child):
        deadline=time.monotonic()+5
        while (r:=reap(lifecycle,child))==170:
            require(time.monotonic()<deadline,'source worker join/reap timed out')
            time.sleep(.001)
        require(r==0,'child registry cleanup failed')
    before=[Q.from_address(lifecycle+k).value for k in trace_offsets]
    start=entries['java/lang/Thread','start']
    join=entries['java/lang/Thread','join']
    # Own the child monitor across start and join. The real terminal publisher
    # cannot enter it until join's source Object.wait releases every acquisition.
    acquire(target,2)
    cstart=Context()
    call(start,cstart,target)
    clean(cstart,'original Thread.start')
    require(Q.from_address(field(target,'java/lang/Thread','eetop')).value!=0,'VM published live child record')
    waits_before=Q.from_address(pool+96).value
    cjoin=Context()
    call(join,cjoin,target)
    clean(cjoin,'original Thread.join')
    require(Q.from_address(field(target,'java/lang/Thread','eetop')).value==0 and
            U.from_address(field(holder,'java/lang/Thread$FieldHolder','threadStatus')).value==2,'real terminal publisher')
    release(target,2)
    join_waits=Q.from_address(pool+96).value-waits_before
    require(leave(heap,target,Context())==17 and join_waits==1,'join passed through source wait0')
    reap_child(target)
    delta=[Q.from_address(lifecycle+k).value-n for k,n in zip(trace_offsets,before)]
    diagnostic_pool=symbol(guest,'boom_diagnostic_pool')
    diagnostic_id=word(diagnostic_pool,32) if word(diagnostic_pool,8)==2 else None
    diagnostic=json.loads((selection/'diagnostic.json').read_bytes())
    lifecycle_trace=dict(counter_delta=delta,failure_state=word(lifecycle,120),
        failure_context=list(Context.from_address(ptr(lifecycle,224))),
        diagnostic=next((r for r in diagnostic['rows'] if r['id']==diagnostic_id),None))
    record('original_Thread_lifecycle_trace',lifecycle_trace)
    require(delta==[1,1,1,1],'original Java run and exit both completed exactly once')
    record('original_Thread_start_join_exit',{'source_run_returns':delta[1],'source_exit_returns':delta[3],
                                             'wait0_calls':join_waits,'restored_recursion':2})
    _,f=launch(source['wait0'],monitor,(0,))
    enroll(f,6)
    timer,_=prepare_child('java/util/TimerThread')
    queue=new('java/util/TaskQueue')
    P.from_address(field(timer,'java/util/TimerThread','queue')).value=queue
    c.c_ubyte.from_address(field(timer,'java/util/TimerThread','newTasksMayBeScheduled')).value=1
    before=[Q.from_address(lifecycle+k).value for k in trace_offsets]
    timer_start=Context()
    call(start,timer_start,timer)
    clean(timer_start,'original TimerThread.start')
    wait_count(7,lifecycle)
    acquire(queue)
    acquire(monitor)
    require(bind(guest,'provider_reference_stop',U,P)(ref)==0 and bind(guest,'provider_object_wait_stop',U,P)(pool)==0,'owner shutdown')
    forged=Context(0xb002,0,0,0)
    require(bind(guest,'provider_reference_boundary',U,P,P)(forged,ref)==0 and forged[0]==0xb002,'foreign token rejected')
    release(monitor)
    release(queue)
    require(f.result(5)[0]==0xb002,'source wait returned its controlled stop')
    reap_child(timer)
    delta=[Q.from_address(lifecycle+k).value-n for k,n in zip(trace_offsets,before)]
    require(delta==[1,0,1,1],'cancelled TimerThread must skip normal source run completion')
    require(Q.from_address(pool+112).value==2 and Q.from_address(ref+48).value==Q.from_address(ref+56).value==2,'shared stop ledger')
    record('original_TimerThread_cancelled',{'attempted_source_run':delta[0],'normal_source_run_returns':delta[1],
                                             'source_exit_returns':delta[3],'shared_tokens_consumed':Q.from_address(ref+56).value})
    require(bind(guest,'provider_object_wait_close',U,P)(pool)==0 and bind(guest,'provider_reference_close',U,P)(ref)==0,'ordered close')
    counters={key:Q.from_address(pool+offset).value for key,offset in
              (('real_source_waits',96),('source_interrupts',104),('shared_cancellations',112),('normal_wait_returns',120))}
    require(tuple(counters.values())==(7,3,2,2),'each observed source wait must have one measured outcome')
    control[0]=control[1]=0
    require(detach(reg)==0 and bind(rt,'thread_native_bind',U,P,P)(None,tp)==0 and bind(rt,'threads_destroy',U,P)(reg)==0,'registry teardown')
    require(bind(guest,'release_trace_pool',U)()==0 and bind(rt,'heap_destroy',U,P)(heap)==1,'trace and heap teardown')
    record('complete',dict(counters,source_closure_sha256=proof['closure_manifest_sha256'],image_sha256=sha(image),
                           runtime_sha256=identity['sha256'],game_started=False))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('runtime','selection','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    run(a.runtime.resolve(),a.selection.resolve(),a.output.resolve())
