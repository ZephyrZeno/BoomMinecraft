"""Execute only the isolated ASM mapping owner, including concurrent leases."""
import argparse
import ctypes as c
import gc
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('test_jimage_owner_builder',ROOT/'scripts/jimage-owner-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
P=c.c_void_p;U=c.c_uint32;Q=c.c_uint64


class Job(c.Structure):
    _fields_=[('pool',P),('path',P),('units',Q),('token',Q),('view',P),('length',Q),('status',U),('error',U),('expected',Q)]


def run(candidate_file,output):
    output=Path(output).resolve();B.check(output.is_relative_to(B.ART) and not output.exists(),'Fresh owner execution directory required')
    proof=B.verify(candidate_file);candidate=json.loads(Path(candidate_file).read_text(encoding='utf-8'))
    B.check(proof==json.loads(Path(candidate_file).with_name('verification.json').read_text()),'Owner canonical source proof differs')
    output.mkdir(parents=True);B.write(output/'machine-verification.json',proof)
    before={str(Path(__file__).resolve()):B.artifact(__file__)}
    for row in [candidate['image'],candidate['object'],candidate['assembly'],candidate['sources']['kernel'],candidate['sources']['producer']]:
        before[row['path']]=row;B.checked(row)
    image=c.WinDLL(str(B.checked(candidate['image'])))
    def bind(name,restype,*args):
        fn=getattr(image,'boom_jimage_owner_'+name);fn.argtypes=list(args);fn.restype=restype;return fn
    init=bind('init',U,P,U,U);close=bind('close',U,P)
    funcs={name:bind(name,U,P) for name in ('open','lookup','release')}
    B.check(c.sizeof(Job)==64 and Job.status.offset==48 and Job.expected.offset==56,'Actual host Job ABI differs')
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=P
    kernel.GetProcessHandleCount.argtypes=[P,P];kernel.GetProcessHandleCount.restype=U
    kernel.CreateFileW.argtypes=[c.c_wchar_p,U,U,P,U,U,P];kernel.CreateFileW.restype=P
    kernel.CloseHandle.argtypes=[P];kernel.CloseHandle.restype=U
    kernel.VirtualAlloc.argtypes=[P,Q,U,U];kernel.VirtualAlloc.restype=P
    kernel.VirtualProtect.argtypes=[P,Q,U,P];kernel.VirtualProtect.restype=U
    kernel.VirtualFree.argtypes=[P,Q,U];kernel.VirtualFree.restype=U
    kernel.AcquireSRWLockExclusive.argtypes=[P];kernel.AcquireSRWLockExclusive.restype=None
    kernel.ReleaseSRWLockExclusive.argtypes=[P];kernel.ReleaseSRWLockExclusive.restype=None
    def handles():
        n=U();B.check(kernel.GetProcessHandleCount(kernel.GetCurrentProcess(),c.byref(n)),'GetProcessHandleCount failed');return n.value
    def value(pool,offset):return Q.from_address(c.addressof(pool)+offset).value
    def call(name,pool,path=None,token=0,expected=0):
        key=c.create_string_buffer(path.encode('utf-16-le','surrogatepass')) if path is not None else None
        job=Job(c.addressof(pool),c.addressof(key) if key is not None else None,len(path.encode('utf-16-le','surrogatepass'))//2 if path is not None else 0,
                token,None,0,0,0,expected)
        status=funcs[name](c.byref(job));B.check(status==job.status,'Native return and Job.status differ')
        return job
    primary=Path('D:/Dev/Java/jdk-21/lib/modules').resolve();primary_row=B.artifact(primary)
    B.check(primary_row['size']==141325186 and primary_row['sha256']=='541b62fa469595c7eeb2c329dad24151887be50056e08b5e4e1534c6260bb263','Original JDK image differs')
    with primary.open('rb') as source:actual_header=source.read(28)
    fixtures=output/'fixtures';fixtures.mkdir()
    # Header-only fixtures exercise the native header/range contract, not resource decoding.
    valid=fixtures/'valid-image.jimage';payload=struct.pack('<7I',0xcafedada,0x10000,0xabc,11,0,0,1)+b'\0'+bytes(range(255))
    valid.write_bytes(payload)
    invalid={
      'empty':b'', 'short':payload[:27], 'magic':b'bad!'+payload[4:],
      'version':payload[:4]+struct.pack('<I',0x20000)+payload[8:],
      'index_overflow':struct.pack('<7I',0xcafedada,0x10000,0,0,0xffffffff,0xffffffff,0xffffffff),
      'endian':struct.pack('>7I',0xcafedada,0x10000,0,0,0,0,1)+b'\0'}
    def warm_host_threads():
        ready=threading.Barrier(8)
        def wait(_):ready.wait();return threading.get_native_id()
        with ThreadPoolExecutor(max_workers=8) as executor:
            B.check(len(set(executor.map(wait,range(8))))==8,'Host thread baseline did not warm eight workers')
    def warm_contended_Win32_lock():
        lock=Q();entered=threading.Event()
        kernel.AcquireSRWLockExclusive(c.byref(lock))
        def wait():
            entered.set();kernel.AcquireSRWLockExclusive(c.byref(lock));kernel.ReleaseSRWLockExclusive(c.byref(lock))
        thread=threading.Thread(target=wait);thread.start();entered.wait();time.sleep(.025)
        kernel.ReleaseSRWLockExclusive(c.byref(lock));thread.join()
    warm_host_threads();gc.collect();lock_warmup_before=handles()
    warm_contended_Win32_lock();gc.collect();lock_warmup_after=handles()
    pools=[];observations=[];failure=None;baseline=handles();guard_allocations=[];handle_observations=[('baseline',baseline)]
    def pool(capacity=4):
        p=c.create_string_buffer(128);B.check(init(p,128,capacity)==0,'Real owner init failed');pools.append(p);return p
    try:
        p=pool();key=str(primary);opened=call('open',p,key,expected=primary_row['size'])
        handle_observations.append(('primary_open',handles()))
        B.check(opened.status==0 and opened.view and opened.length==primary_row['size'],'Real JDK mapping open failed')
        mapped=(c.c_ubyte*opened.length).from_address(opened.view)
        B.check(hashlib.sha256(memoryview(mapped).cast('B')).hexdigest()==primary_row['sha256'],'Actual mapped JDK data differs')
        handle_observations.append(('mapped_data_hashed',handles()))
        B.check(value(p,56)==1 and value(p,64)==opened.length and value(p,72)==value(p,80)==1,'Actual initial ownership counters differ')
        B.check(close(p)==2 and c.string_at(opened.view,28)==actual_header,'Active lease did not protect real mapping')
        duplicate=call('open',p,key);B.check((duplicate.token,duplicate.view,duplicate.length)==(opened.token,opened.view,opened.length),'Duplicate key did not reuse real map')
        B.check(call('release',p,token=duplicate.token).status==0,'Duplicate lease release failed')
        handle_observations.append(('duplicate_open_release',handles()))
        B.check(call('lookup',p,key.swapcase()).status==1,'Lookup canonicalized the exact key')
        B.check(call('lookup',p,key+'-missing').status==1,'Lookup miss is not explicit')
        B.check(call('open',p,key,expected=opened.length+1).status==10 and value(p,56)==1,'Cached expected-size mismatch changed leases')
        handle_observations.append(('before_workers_primary_still_open',handles()))
        barrier=threading.Barrier(8)
        def worker(worker_id):
            barrier.wait();calls=0
            for i in range(128):
                job=call('open' if i%16==0 else 'lookup',p,key)
                B.check(job.status==0 and job.token==opened.token and job.view==opened.view,'Concurrent exact lookup/open failed')
                B.check(c.string_at(job.view,28)==payload_header,'Concurrent mapped header changed')
                B.check(close(p)==2,'Close unmapped an active shared lease')
                B.check(call('release',p,token=job.token).status==0,'Concurrent lease release failed');calls+=1
            return dict(worker=worker_id,OS_thread=threading.get_native_id(),leased_reads=calls)
        payload_header=c.string_at(opened.view,28)
        with ThreadPoolExecutor(max_workers=8) as executor:workers=list(executor.map(worker,range(8)))
        handle_observations.append(('workers_joined_python_refs_live',handles()))
        B.check(len({w['OS_thread'] for w in workers})==8 and value(p,56)==1,'OS workers or final lease count differ')
        B.check(call('release',p,token=opened.token).status==0 and call('release',p,token=opened.token).status==6,'Stale/unleased token accepted')
        B.check(close(p)==0 and all(value(p,o)==0 for o in (32,48,56,64,72,80)),'Native owner did not release real resources')
        handle_observations.append(('primary_closed_python_refs_live',handles()))
        B.check(call('lookup',p,key).status==9 and close(p)==9,'Closed owner reused without initialization')
        B.check(init(p,128,1)==0,'Closed owner did not reinitialize')
        new=call('open',p,str(valid));B.check(new.status==0 and new.token!=opened.token,'Generation reused an old token')
        B.check(call('release',p,token=opened.token).status==6,'Previous initialization token accepted')
        B.check(call('open',p,str(primary)).status==7,'Capacity did not bound OS mappings')
        # The real read-only file handle excludes competing writers, even after releasing the last lease.
        writer=kernel.CreateFileW(str(valid),0x40000000,7,None,3,0,None)
        B.check(writer==P(-1).value and c.get_last_error()==32,'Owner did not pin a stable read-only input')
        B.check(call('release',p,token=new.token).status==0 and close(p)==0,'Fixture owner cleanup failed')
        handle_observations.append(('fixture_closed',handles()))
        for name,data in invalid.items():
            path=fixtures/(name+'.jimage');path.write_bytes(data);p2=pool(1);job=call('open',p2,str(path))
            B.check(job.status==(11 if name=='endian' else 10),'Malformed image/header classification differs: '+name)
            B.check(all(value(p2,o)==0 for o in (32,48,56,64,72,80)),'Failed open leaked real handles or mappings: '+name)
            B.check(close(p2)==0,'Failed-open owner could not close')
            observations.append(dict(case=name,status=job.status,error=job.error))
        p3=pool();job=call('open',p3,str(fixtures/'missing.jimage'));B.check(job.status==4 and job.error in (2,3),'Real missing-file error not retained')
        job=call('open',p3,str(valid),expected=len(payload)+1);B.check(job.status==10,'Expected-size mismatch not checked against actual file')
        for path,status in [('',3),(str(valid)+'\0suffix',8)]:
            B.check(call('lookup',p3,path).status==status,'Bad key was not rejected')
        B.check(init(p3,128,4)==2,'Live owner was reinitialized')
        B.check(close(p3)==0,'Invalid-input owner cleanup failed')
        handle_observations.append(('all_files_closed_before_guard',handles()))
        # Read the last requested UTF16 code unit at a real inaccessible page boundary.
        base=kernel.VirtualAlloc(None,8192,0x3000,4);B.check(base,'Guard allocation failed');guard_allocations.append(base)
        old=U();B.check(kernel.VirtualProtect(base+4096,4096,1,c.byref(old)),'Guard protection failed')
        data=str(valid).encode('utf-16-le');ptr=base+4096-len(data);c.memmove(ptr,data,len(data))
        p4=pool();job=Job(c.addressof(p4),ptr,len(data)//2,0,None,0,0,0,0)
        B.check(funcs['open'](c.byref(job))==0,'Exact-length guard key was overread or rejected')
        B.check(call('release',p4,token=job.token).status==0 and close(p4)==0,'Guard-key mapping cleanup failed')
        # CPython's executor retains native thread handles until its Thread
        # objects are released; those belong to this development driver.
        del executor,barrier
        gc.collect()
        handle_observations.append(('host_executor_objects_released',handles()))
        B.check(handles()==baseline,'Functional cases leaked real Windows handles')
        repeated_baseline=handles()
        for _ in range(128):
            cycle=pool(1);lease=call('open',cycle,str(valid))
            B.check(lease.status==0 and call('release',cycle,token=lease.token).status==0 and close(cycle)==0,
                    'Repeated native owner lifecycle failed')
        B.check(handles()==repeated_baseline,'Repeated mappings leaked Windows handles')
        for row in before.values():B.checked(row)
        B.check(B.artifact(primary)==primary_row,'Original module image was changed')
    except BaseException as error:
        failure=repr(error);workers=locals().get('workers',[])
    finally:
        for base in guard_allocations:kernel.VirtualFree(base,0,0x8000)
    result=dict(verified=failure is None,scope='standalone_real_readonly_JIMAGE_owner_not_Java_getNativeMap_or_game',
        candidate=B.artifact(candidate_file),primary=primary_row,OS_workers=workers,header_errors=observations,
        handle_count_before=baseline,handle_count_after=handles(),failure=failure,
        handle_observations=handle_observations,
        host_thread_runtime_warmed_before_handle_baseline=True,repeated_lifecycles=128 if failure is None else 0,
        oracle_file_IO_prepared_before_handle_baseline=True,
        contended_Win32_lock_control=dict(before=lock_warmup_before,after=lock_warmup_after),
        pools=[dict(state=U.from_address(c.addressof(p)+24).value,entries=value(p,32),leases=value(p,56),
            mapped_bytes=value(p,64),file_handles=value(p,72),map_handles=value(p,80)) for p in pools],
        tool=B.artifact(__file__),Java_native_bridge_executed=False,game_started=False)
    B.write(output/'execution.json',result);B.check(result['verified'],'Owner component failed; retain execution.json: '+str(failure))
    return output/'execution.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(run(a.candidate.resolve(),a.output.resolve()))
