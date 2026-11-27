"""Execute actual leased mapping copies into real ASM-heap byte arrays."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import subprocess
from threading import Barrier,get_native_id
import time

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('jimage_copy_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('jimage-unsafe-copy-candidate');S=B.S;RTEST=module('test-jimage-unsafe-read')
P,Q,U=c.c_void_p,c.c_uint64,c.c_uint32
Context=U*8


class Job(c.Structure):
    _fields_=[('owner',P),('heap',P),('source',Q),('array',P),('offset',Q),('length',Q),('status',U),('reserved',U),('copied',Q)]


def proc(image,name,result,*args):
    value=getattr(image,name);value.restype=result;value.argtypes=list(args);return value


def abi_image(output,row):
    output.mkdir();template=module('test-deflate-stream').abi_assembly();[block]=re.findall(r'(?ms)^PUBLIC boom_ds_step_abi\n.*?^boom_ds_step_abi ENDP\n',template)
    text='option casemap:none\nEXTERN boom_jimage_owned_copy_to_bytes:PROC\n.const\nboom_ds_abi_pattern BYTE 16 DUP(0B6h)\n.code\n'+block.replace('boom_ds_step_abi','boom_juc_copy_abi').replace('boom_deflate_stream_step',B.CORE_EXPORT)+'END\n'
    asm,obj,dll,rsp=(output/n for n in ('abi.asm','abi.obj','abi.dll','link.rsp'));asm.write_text(text,encoding='utf-8',newline='\n');assembler,linker=(B.checked(row[k]) for k in ('assembler','linker'));B.RB.assemble(asm,obj,assembler,output/'assembler.log')
    objects=[B.checked(row['core_object']),obj];libraries=[B.checked(row['runtime_library']),B.checked(row['kernel32'])];rsp.write_text(B.response(dll,objects,libraries,{'boom_juc_copy_abi'}),encoding='utf-8',newline='\n')
    with (output/'link.log').open('xb') as log:run=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    S.check(run.returncode==0,'Production copy ABI image link failed');runtime=B.checked(row['metadata']['runtime'])
    with os.add_dll_directory(str(runtime.parent)):image=c.WinDLL(str(dll))
    return image,proc(image,'boom_juc_copy_abi',U,P),dict(source=S.artifact(asm),object=S.artifact(obj),image=S.artifact(dll),response=S.artifact(rsp),original_core=row['core_object'],template=S.artifact(ROOT/'scripts/test-deflate-stream.py'))


def pending_protocol(output,row):
    output.mkdir();meta=row['metadata'];text,_,_=B.C.assembly(meta['source']);mid=meta['source']['methods'][0]['method'];adapter=B.C.R.native_adapter(mid,meta['source']['owner'],'boom_java_unsafe_field_pool',B.C.SERVICE,0).removeprefix('.code\n')
    header=f'PUBLIC boom_m{mid}\nPUBLIC boom_m{mid}_native\n';S.check(text.count(adapter)==text.count(header)==1,'Exact unexecuted adapter extraction')
    text=text.replace(header,'').replace(adapter,'')
    removed={'boom_class_ensure32':'PROC','boom_trace_enter':'PROC','boom_trace_leave':'PROC','boom_class'+str(meta['source']['owner']):'BYTE','boom_java_unsafe_field_pool':'BYTE','boom_trace_pool':'BYTE','boom_trace_method'+str(mid):'BYTE'}
    for name,kind in removed.items():
        line='EXTERN '+name+':'+kind+'\n';S.check(text.count(line)==1,'Exact adapter-only import removal');text=text.replace(line,'')
    local_pool='EXTERN '+B.C.SC.BRIDGE_POOL+':BYTE\n';S.check(text.count(local_pool)==1,'Exact now-locally-defined bridge pool import');text=text.replace(local_pool,'')
    bridge=B.S.read(B.checked(meta['bridge_candidate']));data=module('jimage-native-map-source').data(bridge['metadata']['source']);text=text.removesuffix('END\n')+data+'\nEND\n'
    asm,obj,dll,rsp=(output/n for n in ('protocol.asm','protocol.obj','protocol.dll','link.rsp'));asm.write_text(text,encoding='utf-8',newline='\n');assembler,linker=(B.checked(row[k]) for k in ('assembler','linker'));B.RB.assemble(asm,obj,assembler,output/'assembler.log')
    objects=[obj,B.checked(row['core_object'])];libraries=[B.checked(row['runtime_library']),B.checked(row['kernel32'])];rsp.write_text(B.response(dll,objects,libraries,{B.C.SERVICE}),encoding='utf-8',newline='\n')
    with (output/'link.log').open('xb') as log:r=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0,'Service-only pending protocol image link failed');runtime=B.checked(meta['runtime'])
    with os.add_dll_directory(str(runtime.parent)):image=c.WinDLL(str(dll))
    fn=proc(image,B.C.SERVICE,Q,P,P,P,U);calls=0
    for pending in (16,20,0xdeadbeef):
        for operation in (0,1,0xffffffff):
            for argv in (None,(Q*6)(1,1,0xffffffffffffffff,0,0xffffffffffffffff,0xffffffffffffffff)):
                initial=[pending,0x12345678,0x89abcdef,0x11223344,0x55667788,0x99aabbcc,0xddeeff00,0x01020304];ctx=Context(*initial);value=fn(ctx,argv,None,operation);calls+=1
                S.check(value==0 and list(ctx)==initial,'Any pending Context DWORD changed')
    for arguments,operation,expected in [(None,0,7),((1,1,0,1,0,1),0,20),((1,0,0,0,0,1),0,20),((1,0,0,1,0,1),0,7),((1,0,0,1,0,1),1,7)]:
        ctx=Context();args=(Q*6)(*arguments) if arguments else None;value=fn(ctx,args,None,operation);calls+=1
        S.check(value==0 and ctx[0]==expected and list(ctx)[1:]==[0]*7,'Unsupported/invalid native domain reported success')
    result=dict(verified=True,calls=calls,scope='test_only_exact_service_fragment_pending_and_invalid_protocol',source=S.artifact(asm),object=S.artifact(obj),image=S.artifact(dll),response=S.artifact(rsp),
        exact_whole_adapter_removed_only_for_unexecuted_protocol_fixture=True,remaining_service_and_receiver_source_unchanged=True,normal_Frame8_adapter_runtime_executed=False,
        no_successful_Java_Unsafe_receiver_claimed=True,bridge_data_from=meta['bridge_candidate'],host_owner_or_Java_state_written=False)
    S.write(output/'verification.json',result);return S.artifact(output/'verification.json')


def jdk_oracle(output,path,rows):
    output.mkdir();home=Path('D:/Dev/Java/jdk-21');tools=[S.artifact(home/n) for n in ('bin/java.exe','bin/javac.exe','bin/server/jvm.dll','lib/modules')]
    text='''import java.nio.*;import java.nio.channels.*;import java.nio.file.*;import java.util.*;import java.security.*;public class JimageCopyOracle{public static void main(String[] a)throws Exception{try(FileChannel f=FileChannel.open(Path.of(a[0]),StandardOpenOption.READ)){ByteBuffer b=f.map(FileChannel.MapMode.READ_ONLY,0,f.size());int count=0;for(String line:Files.readAllLines(Path.of(a[1]))){String[] p=line.split("\\t");int at=Integer.parseInt(p[0]),n=Integer.parseInt(p[1]),off=Integer.parseInt(p[2]),size=Integer.parseInt(p[3]);byte[] out=new byte[size];Arrays.fill(out,(byte)0xa5);b.position(at);b.get(out,off,n);String sha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(out));if(!sha.equals(p[4]))throw new AssertionError(line);count++;}System.out.println("JIMAGE_copy_references="+count);}}}'''
    source=output/'JimageCopyOracle.java';manifest=output/'cases.tsv';source.write_text(text,encoding='utf-8',newline='\n');manifest.write_text(''.join('\t'.join(map(str,r))+'\n' for r in rows),encoding='utf-8',newline='\n')
    with (output/'javac.log').open('xb') as log:r=subprocess.run([str(home/'bin/javac.exe'),'-d',str(output),str(source)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0,'JDK copy reference compilation failed')
    with (output/'java.log').open('xb') as log:r=subprocess.run([str(home/'bin/java.exe'),'-cp',str(output),'JimageCopyOracle',str(path),str(manifest)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0 and (output/'java.log').read_text().strip()=='JIMAGE_copy_references='+str(len(rows)),'JDK original mapped ByteBuffer.get reference differs')
    for p in tools:B.checked(p)
    result=dict(verified=True,cases=len(rows),scope='tool_only_original_JDK_mapped_ByteBuffer_get_array_reference',source=S.artifact(source),class_file=S.artifact(output/'JimageCopyOracle.class'),manifest=S.artifact(manifest),tools=tools,delivery_uses_JVM=False)
    S.write(output/'verification.json',result);return S.artifact(output/'verification.json')


def run(candidate_file,output):
    output=Path(output).resolve();S.check(output.is_relative_to(B.ART) and not output.exists(),'Fresh copy execution directory required');proof=B.verify(candidate_file);row=S.read(candidate_file);output.mkdir(parents=True);S.write(output/'machine-verification.json',proof)
    before=[S.artifact(__file__),S.artifact(candidate_file),*row['metadata']['sources'].values(),row['metadata']['bridge_source'],row['metadata']['source_scalar_receiver_validator']]
    runtime=B.checked(row['metadata']['runtime'])
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.WinDLL(str(runtime)),c.WinDLL(str(B.checked(row['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(256<<20);S.check(heap,'Actual normal ASM heap creation failed');pools=[];calls=0
    copy=proc(image,B.CORE_EXPORT,U,P);init=proc(image,'boom_jimage_owner_init',U,P,U,U);close=proc(image,'boom_jimage_owner_close',U,P);funcs={n:proc(image,'boom_jimage_owner_'+n,U,P) for n in ('open','release')}
    S.check(c.sizeof(Job)==64 and Job.status.offset==48 and Job.copied.offset==56,'Actual copy job offsets differ')
    original=Path('D:/Dev/Java/jdk-21/lib/modules');original_pin=S.artifact(original);S.check(original_pin['digest']['size']==141325186 and original_pin['digest']['sha256']=='541b62fa469595c7eeb2c329dad24151887be50056e08b5e4e1534c6260bb263','Original image differs');plain=original.read_bytes()
    def pool():
        p=c.create_string_buffer(128);S.check(init(p,128,2)==0,'Actual owner init failed');pools.append(p);return p
    def owner(name,p,path=None,token=0):
        key=c.create_string_buffer(str(path).encode('utf-16-le')) if path else None;job=RTEST.OwnerJob(c.addressof(p),c.addressof(key) if key else None,len(str(path)) if path else 0,token)
        status=funcs[name](c.byref(job));S.check(status==job.status,'Owner status mismatch');return job
    def array(n,kind=8):
        ctx=Context();p=proc(rt,'boom_array_new',P,P,c.c_int,U,P)(heap,n,kind,ctx);S.check(p and not ctx[0],'Actual normal primitive array allocation failed');return p
    def call(p,source,destination,offset,length,*,fn=copy,expected_status=0,heap_pointer=heap):
        nonlocal calls
        raw=c.create_string_buffer(b'\x91'*16+b'\0'*64+b'\xc7'*16);job=Job.from_buffer(raw,16);job.owner=c.addressof(p);job.heap=heap_pointer;job.source=source;job.array=destination;job.offset=offset;job.length=length;inputs=raw.raw[16:64]
        status=fn(c.byref(job));calls+=1
        S.check(raw.raw[:16]==b'\x91'*16 and raw.raw[80:96]==b'\xc7'*16 and raw.raw[16:64]==inputs and job.reserved==0,'Native copy modified job input or guard')
        S.check(status==(0 if fn is not copy else job.status),'Actual copy ABI/status mismatch')
        if expected_status is not None:S.check(job.status==expected_status,'Wrong native copy status: '+str((job.status,expected_status)))
        S.check(job.copied==(length if job.status==0 else 0),'Rejected copy wrote partial bytes')
        return job.status
    p=pool();opened=owner('open',p,original.resolve());S.check(opened.status==0 and opened.length==len(plain),'Real source mapping open failed');destination=array(65536+64);size=Q.from_address(destination-16).value;observations=[];reference=[];rng=random.Random(0x434f5059)
    abi_dll,abi,abi_record=abi_image(output/'ABI-probe',row)
    cases=[(0,n,32) for n in (0,1,2,7,8,15,16,17,31,32,512,4096,65536)]
    cases += [(len(plain)-n,n,0) for n in (0,1,2,7,512,4096,65536)]
    cases += [(rng.randrange(len(plain)-n+1),n,rng.randrange(33)) for n in [rng.randrange(65537) for _ in range(512)]]
    for at,n,off in cases:
        expected=b'\xa5'*off+plain[at:at+n]+b'\xa5'*(size-off-n)
        for fn in (copy,abi):
            c.memset(destination,0xa5,size);call(p,opened.view+at,destination,off,n,fn=fn);S.check(c.string_at(destination,size)==expected,'Copy data or surrounding destination bytes differ')
        sha=hashlib.sha256(expected).hexdigest();reference.append((at,n,off,size,sha));observations.append(dict(offset=at,bytes=n,destination_offset=off,output_sha256=sha))
    abi_record.update(verified=True,calls=len(cases),nonvolatile_GPR=8,nonvolatile_XMM=10,stack_and_two_canaries=True);S.write(output/'ABI-probe/verification.json',abi_record)
    rejects=[];boolean=array(64,4);references=array(8,12);outside=c.create_string_buffer(64)
    invalid=[('source-miss',0,destination,0,1,1),('partial-source',opened.view+len(plain)-7,destination,0,8,1),('source-add-wrap',0xffffffffffffffff,destination,0,8,2),('negative-length',opened.view,destination,0,0xffffffffffffffff,2),('negative-offset',opened.view,destination,0xffffffffffffffff,1,2),('destination-tail',opened.view,destination,size,1,2),('destination-large-length',opened.view,destination,0,size+1,2),('boolean-array',opened.view,boolean,0,1,5),('reference-array',opened.view,references,0,1,5),('off-heap-destination',opened.view,c.addressof(outside),0,1,6),('readonly-mapping-destination',opened.view,opened.view,0,1,6)]
    for name,source,dst,off,n,status in invalid:
        saved=c.string_at(destination,size);call(p,source,dst,off,n,expected_status=status);S.check(c.string_at(destination,size)==saved,'Rejected copy changed normal destination');rejects.append(name)
    barrier=Barrier(8)
    def worker(seed):
        dst=array(1024);local=random.Random(seed);ident=get_native_id();barrier.wait()
        for _ in range(256):
            n=local.randrange(1025);at=local.randrange(len(plain)-n+1);c.memset(dst,0x72,1024);call(p,opened.view+at,dst,0,n);S.check(c.string_at(dst,n)==plain[at:at+n] and c.string_at(dst+n,1024-n)==b'\x72'*(1024-n),'Concurrent actual copy differs')
        return dict(OS_thread=ident,copies=256)
    with ThreadPoolExecutor(max_workers=8) as workers:threads=list(workers.map(worker,range(8)))
    S.check(len({r['OS_thread'] for r in threads})==8,'Eight actual native OS workers required')
    # Primitive owner state retains no destination oop. Root only the actual
    # surviving Java array and exercise it again after quiescent collection.
    roots=(Q*1)(destination);freed=proc(rt,'boom_heap_collect',Q,P,P,U)(heap,roots,1);S.check(freed!=0xffffffffffffffff,'Normal quiescent collection failed');call(p,opened.view,destination,0,28);S.check(c.string_at(destination,28)==plain[:28],'GC changed live source/native destination behavior')
    S.check(owner('release',p,token=opened.token).status==0,'VM source lease release failed');call(p,opened.view,destination,0,1,expected_status=1);S.check(close(p)==0,'Owner close after released source failed');call(p,opened.view,destination,0,1,expected_status=4)
    long_pool=pool();long_source=owner('open',long_pool,original.resolve());S.check(long_source.status==0,'Long copy mapping');n=32<<20;long_dst=array(n);observed=False
    with ThreadPoolExecutor(max_workers=1) as runner:
        future=runner.submit(call,long_pool,long_source.view,long_dst,0,n);deadline=time.monotonic()+30
        while not future.done() and time.monotonic()<deadline:
            if Q.from_address(c.addressof(long_pool)+16).value:observed=True;break
            time.sleep(0)
        S.check(owner('release',long_pool,token=long_source.token).status==0 and close(long_pool)==0,'Exclusive release/close during real copy failed');future.result()
    S.check(c.string_at(long_dst,n)==plain[:n],'Closing overlapped and damaged long physical copy')
    protocol=pending_protocol(output/'source-protocol',row);oracle=jdk_oracle(output/'jdk-oracle',original,reference)
    pool_rows=[]
    for obj in pools:
        address=c.addressof(obj);state=U.from_address(address+24).value;values={str(at):Q.from_address(address+at).value for at in (32,48,56,64,72,80)};S.check(state==2 and not any(values.values()),'Native mapping resources leaked');pool_rows.append(dict(state=state,resources=values))
    proc(rt,'boom_heap_destroy',None,P)(heap)
    for record in before:B.checked(record)
    for key in ('assembly','object','core_assembly','core_object','image','response'):B.checked(row[key])
    S.check(S.artifact(original)==original_pin,'Original image was changed')
    result=dict(verified=True,scope='unregistered_real_leased_RO_JIMAGE_to_normal_ASM_heap_byte_array_core_not_Java_consumer_execution',candidate=S.artifact(candidate_file),machine_verification=S.artifact(output/'machine-verification.json'),original_image=original_pin,
        actual_copy_calls=calls,reference_cases=len(cases),observations=observations,rejected_cases=rejects,OS_workers=threads,ABI=S.artifact(output/'ABI-probe/verification.json'),JDK_reference=oracle,source_protocol=protocol,
        long_copy=dict(bytes=n,shared_lifetime_lease_observed=observed,exclusive_release_close_completed=True,data_equal=True),quiescent_collection=dict(freed=freed,surviving_real_destination_arrays=1),owner_final=pool_rows,
        normal_primitive_arrays_allocated_by_original_ASM=True,object_headers_or_Java_state_manually_written=False,pending_Context_32_bytes_preserved=True,
        valid_Java_Unsafe_receiver_executed=False,normal_Frame8_adapter_runtime_executed=False,original_Java_ByteBuffer_get_array_executed=False,bridge_runtime_binding_verified=False,
        registered=False,full_selection_reverified=False,game_started=False,harness=S.artifact(__file__))
    S.write(output/'execution.json',result);return output/'execution.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();existed=a.output.exists()
    try:print(run(a.candidate,a.output))
    except BaseException as error:
        if not existed and a.output.resolve().is_relative_to(B.ART):
            a.output.mkdir(parents=True,exist_ok=True);target=a.output/'failure.json'
            if not target.exists():S.write(target,dict(verified=False,error=repr(error),harness=S.artifact(__file__),candidate=S.artifact(a.candidate)))
        raise
