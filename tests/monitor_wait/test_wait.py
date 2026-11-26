"""Use real OS threads, the v138 platform registry, allocator and Monitor32."""
import ctypes as c
import json
import os
import sys
import threading
import time
import traceback
from concurrent.futures import Future
from pathlib import Path

P = c.c_void_p
U = c.c_uint32
Q = c.c_uint64
I = c.c_int64
Context = Q * 4
INTERRUPTED, STOPPED = 0x10001, 995
PLAN = 0x1827364554637281


def bind(dll, name, ret, *params):
    f = getattr(dll, 'boom_' + name)
    f.restype, f.argtypes = ret, list(params)
    return f


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(rt_dir, out):
    with os.add_dll_directory(str(rt_dir)):
        rt = c.CDLL(str(rt_dir / 'boom-runtime.dll'))
        kern = c.CDLL(str(out / 'monitor-wait-test.dll'))
    create = bind(rt, 'heap_create', P, Q)
    destroy = bind(rt, 'heap_destroy', U, P)
    alloc = bind(rt, 'heap_alloc', P, P, Q, U, Q)
    collect = bind(rt, 'heap_collect', I, P, P, U)
    reg_create = bind(rt, 'threads_create', P, P, U)
    reg_destroy = bind(rt, 'threads_destroy', U, P)
    new_id = bind(rt, 'threads_next_id', Q, P)
    attach = bind(rt, 'threads_attach', P, P, P, Q)
    detach = bind(rt, 'threads_detach', U, P)
    enter = bind(rt, 'monitor_enter', U, P, P, P)
    leave = bind(rt, 'monitor_exit', U, P, P, P)
    abort_owned = bind(rt, 'monitor_abort_owned', U, P, P, P, U)
    start = bind(kern, 'monitor_wait_open', P, P, P, P)
    close = bind(kern, 'monitor_wait_close', U, P)
    wait = bind(kern, 'monitor_wait', U, P, P, P, I)
    sample = bind(kern, 'test_monitor_wait_counts', Q, P, P)
    notify = bind(kern, 'monitor_wait_notify', U, P, P, P)
    notify_all = bind(kern, 'monitor_wait_notify_all', U, P, P, P)
    interrupt = bind(kern, 'monitor_wait_interrupt', U, P, P)
    stop = bind(kern, 'monitor_wait_stop', U, P)
    stopping = bind(kern, 'monitor_wait_stopping', U, P)
    mapper = c.cast(kern.boom_test_interrupt_field, P).value
    heap = create(8 << 20)
    reg = reg_create(heap, 128)
    pool = start(heap, reg, mapper)
    require(heap and reg and pool, 'create heap, registry and wait domain')
    require(not start(heap, reg, mapper) and close(pool) == 170 and stopping(pool)==0 and stopping(None)==0, 'unique active domain')
    def obj(tag=0x88):
        result = alloc(heap, 40, 1, tag)
        require(result, 'allocate real heap object')
        return result
    def flag(oop, tag):
        return c.c_ubyte.from_address(oop + (8 if tag == 0x41 else 24))
    def context():
        return Context(0,0,0,PLAN)
    def acquire(oop, depth=1):
        for _ in range(depth):
            require(enter(heap, oop, context()) == 0, 'acquire')
    def release(oop, depth=1):
        for _ in range(depth):
            require(leave(heap, oop, context()) == 0, 'release')
    def expect(oop, active, eligible):
        expected = active | eligible << 32
        until = time.monotonic()+4
        while True:
            value = sample(pool, oop)
            if value == expected:
                return
            if time.monotonic() > until:
                raise AssertionError(f'wait membership expected {active}/{eligible} actual {value&0xffffffff}/{value>>32}')
            time.sleep(0.0005)
    def assert_clear(ctx):
        require(list(ctx) == [0, 0, 0, PLAN], 'raw reason must preserve all Context32')
    def notify_here(oop, all_waiters=False):
        require((notify_all if all_waiters else notify)(heap, oop, context()) == 0, 'notify owned')
    # The kernel and all dynamic synchronization are ASM. Host threads drive the test and record observations.
    def launch(oop, depth, delay=0, tag=0x41, other=None, follow_flag=False):
        root = obj(tag)
        tid = new_id(reg)
        future = Future()
        def worker():
            try:
                require(attach(reg, root, tid), 'worker TLS registry attach')
                try:
                    if other:
                        acquire(other)
                    acquire(oop, depth)
                    ctx = context()
                    t = time.perf_counter()
                    reason = wait(pool, oop, ctx, delay)
                    elapsed = (time.perf_counter()-t)*1000
                    assert_clear(ctx)
                    byte = flag(root, tag).value
                    if follow_flag:
                        require(wait(pool, oop, ctx, 0) == INTERRUPTED, 'consume preserved interrupt on next wait')
                        assert_clear(ctx)
                        require(flag(root, tag).value == 0, 'interrupt actually cleared')
                    release(oop, depth)
                    require(leave(heap, oop, context()) == 17, 'original depth restored exactly')
                    if other:
                        release(other)
                    result = reason, byte, elapsed
                finally:
                    require(detach(reg) == 0, 'detach worker TLS')
                future.set_result(result)
            except BaseException as exc:
                traceback.print_exc()
                future.set_exception(exc)
        threading.Thread(target=worker, daemon=True).start()
        return future, root
    records = {}
    a,b = obj(),obj()
    main = obj(0x41)
    require(attach(reg, main, 1), 'attach main')
    require(interrupt(pool,main)==1168 and interrupt(pool,None)==87,'distinct absent/invalid interrupt domain')
    acquire(a)
    notify_here(a)
    err = context()
    require(wait(pool, a, err, -1) == 18 and err[0] == 18, 'negative wait')
    blocked = Context(7, 9, 15, PLAN)
    require(wait(pool, a, blocked, 0) == 7 and list(blocked) == [7,9,15,PLAN], 'preserve pending exception')
    flag(main,0x41).value=1
    ctx=context()
    require(wait(pool, a, ctx, 0) == INTERRUPTED and flag(main,0x41).value==0, 'pre-interrupted')
    assert_clear(ctx)
    release(a)
    require(wait(pool, a, context(), 0) == 17 and notify(heap,a,context()) == 17 and
            notify_all(heap,None,context()) == 4 and wait(pool,None,context(),0) == 4, 'owner and null checks')
    require(wait(None,a,context(),0)==20, 'missing binding explicitly unsupported')
    require(detach(reg)==0, 'main detach error probe')
    acquire(a)
    require(wait(pool,a,context(),1)==20, 'unregistered caller explicitly unsupported')
    release(a)
    invalid=obj(0x45)
    require(attach(reg, invalid, new_id(reg)), 'unknown source type attach')
    acquire(a)
    ctx=context()
    require(wait(pool,a,ctx,1)==7 and ctx[0]==7, 'unknown current source type rejected')
    release(a)
    require(detach(reg)==0, 'unknown source type detach')
    records['errors'] = {'nonowner':17,'null':4,'negative':18,'unbound':20,'invalid_field_map':7,'preinterrupted':INTERRUPTED}

    f,_=launch(a,3,other=b)
    expect(a,1,1)
    h=Q.from_address(heap+112).value
    require(h==2 and collect(heap,None,0)==-1 and destroy(heap)==0, 'waiter/other monitor strong roots')
    ctx=context()
    require(notify(heap,a,ctx)==17 and ctx[0]==17,'non-owner cannot wake')
    expect(a,1,1)
    acquire(a,2)
    notify_here(a)
    expect(a,1,0)
    time.sleep(0.015)
    require(not f.done(),'notified waiter must reacquire before returning')
    release(a,2)
    require(f.result(3)[0]==0 and Q.from_address(heap+112).value==0, 'recursion and unrelated monitor')
    records['recursive_release_reacquire']={'depth':3,'other_monitors_held':1,'heap_roots_during_wait':h}

    parked,_=launch(a,4)
    expect(a,1,1)
    acquire(a,2);acquire(b)
    owned=Q(0)
    diagnostic_context=Context(0xB001,0,0,PLAN)
    require(abort_owned(heap,diagnostic_context,c.byref(owned),0)==0 and owned.value==3 and
            list(diagnostic_context)==[0xB001,0,0,PLAN],'abort of other owner retains waiter')
    require(Q.from_address(heap+112).value==1,'waiting object remains rooted after other owner abort')
    expect(a,1,1)
    acquire(a)
    ordinary=Future()
    def ordinary_contender():
        try:
            acquire(a)
            release(a)
            ordinary.set_result(True)
        except BaseException as e:
            ordinary.set_exception(e)
    threading.Thread(target=ordinary_contender,daemon=True).start()
    deadline=time.monotonic()+3
    while U.from_address(P.from_address(heap+96).value+24).value!=2:
        require(time.monotonic()<deadline,'ordinary monitor entrant was not parked')
        time.sleep(0.001)
    expect(a,1,1)
    release(a)
    require(ordinary.result(3) and not parked.done(),'ordinary entrants never consume Java notification')
    expect(a,1,1)
    acquire(a);notify_here(a);release(a)
    require(parked.result(3)[0]==0,'waiter survived real monitor abort and ordinary contender')
    records['coexisting_monitor_protocols']={'release_by_other_owner_diagnostic_abort':3,'ordinary_contenders':1,'retained_wait_pins':1}

    futures=[launch(a,d,tag=0x41+(d%2))[0] for d in (1,2,3,4)]
    side,_=launch(b,2,tag=0x42)
    expect(a,4,4); expect(b,1,1)
    acquire(a)
    notify_here(a)
    expect(a,4,3)
    require(all(not f.done() for f in futures),'no return before releasing notifying owner')
    notify_here(a,True)
    expect(a,4,0); expect(b,1,1)
    release(a)
    require(all(f.result(3)[0]==0 for f in futures),'four distinct notified waiters')
    require(not side.done(),'unrelated object isolated')
    acquire(b); notify_here(b,True); release(b)
    require(side.result(3)[0]==0,'separate object notified')
    records['single_broadcast_isolation']={'same_object_waiters':4,'one_selected':1,'remaining_selected':3,'other_object_unaffected':1}

    timed,_=launch(a,3,delay=53)
    timed_result=timed.result(4)
    require(timed_result[0]==0 and timed_result[2]>=53 and timed_result[2]<3500,'real finite timeout')
    long_times=[0x100000001,0x7fffffffffffffff]
    for ms in long_times:
        future,_=launch(b,2,delay=ms,tag=0x42)
        expect(b,1,1)
        time.sleep(0.012)
        require(not future.done(),'64-bit duration must not wrap')
        acquire(b);notify_here(b);release(b)
        require(future.result(3)[0]==0,'64-bit wait awakened')
    records['timers']={'requested_ms':53,'observed_ms':round(timed_result[2],3),'notified_long_durations':long_times}

    x,xt=launch(a,3,tag=0x42)
    y,_=launch(a,2,tag=0x41)
    expect(a,2,2)
    acquire(a)
    require(interrupt(pool,xt)==0,'delayed native interrupt callback')
    expect(a,2,2)
    flag(xt,0x42).value=1
    require(interrupt(pool,xt)==0,'signal target')
    expect(a,2,1)
    notify_here(a);expect(a,2,0)
    require(not x.done() and not y.done(),'interrupt reacquire')
    release(a)
    require(x.result(3)[:2]==(INTERRUPTED,0) and y.result(3)[:2]==(0,0),'interrupt first preserves notification for other')
    z,zt=launch(a,2,tag=0x42,follow_flag=True)
    expect(a,1,1); acquire(a);notify_here(a);expect(a,1,0)
    flag(zt,0x42).value=1
    require(interrupt(pool,zt)==0,'notify precedes interrupt')
    release(a)
    require(z.result(3)[:2]==(0,1),'notify first retains flag')
    records['interrupt_ordering']={'target_only':True,'already_cleared_callback_ignored':True,
                                   'interrupt_first_frees_notification':True,'notify_first_preserves_flag':True}

    for i in range(48):
        target=a if i%2 else b
        future,_=launch(target,1+(i%4),tag=0x41+(i%2))
        expect(target,1,1)
        acquire(target); notify_here(target); release(target)
        require(future.result(3)[0]==0,'enroll/notify race')
    records['repeated_waiters']=48

    ws=[launch((a,b)[i%2],(i%4)+1,tag=0x41+(i%2))[0] for i in range(16)]
    expect(a,8,8); expect(b,8,8)
    acquire(a);acquire(b)
    require(stop(pool)==0 and stop(pool)==0 and stopping(pool)==1,'stop before draining')
    expect(a,8,0);expect(b,8,0)
    require(close(pool)==170 and all(not f.done() for f in ws),'pool retained while reentry blocked')
    shutdown_root=obj(0x42)
    require(attach(reg,shutdown_root,new_id(reg)),'shutdown caller attach')
    ctx=context()
    require(wait(pool,a,ctx,0)==STOPPED,'already stopped cannot start new wait')
    assert_clear(ctx)
    release(a);release(b)
    require(detach(reg)==0,'shutdown caller detach')
    stopped=[f.result(4)[0] for f in ws]
    require(stopped==[STOPPED]*16,'stopped waits return distinct nonzero status')
    expect(a,0,0);expect(b,0,0)
    require(Q.from_address(heap+112).value==0 and close(pool)==0 and stop(pool)==87 and stopping(pool)==0,'drain and teardown')
    require(reg_destroy(reg)==0 and collect(heap,None,0)>0 and destroy(heap)==1,'quiescent collection and teardown')
    records['shutdown']={'concurrent_platform_threads':16,'returned_controlled_stop':len(stopped),'normal_returns':stopped.count(0)}
    records['verified']=True
    (out/'observations.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(records))


if __name__=='__main__':
    run(Path(sys.argv[1]),Path(sys.argv[2]))
