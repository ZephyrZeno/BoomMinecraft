"""Execute leased JIMAGE scalar reads; typed valid-heap integration is separate."""
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
import struct
import subprocess
from threading import Barrier,get_native_id
import time

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('jimage_read_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('jimage-unsafe-read-candidate');S=B.S;O=B.O
P,Q,U=c.c_void_p,c.c_uint64,c.c_uint32


class ReadJob(c.Structure):
    _fields_=[('owner',P),('address',Q),('kind',U),('reserved',U),('value',Q),('status',U),('reserved2',U),('reserved3',Q)]


class OwnerJob(c.Structure):
    _fields_=[('owner',P),('path',P),('units',Q),('token',Q),('view',P),('length',Q),('status',U),('winerr',U),('expected',Q)]


def proc(image,name,result,*args):
    fn=getattr(image,name);fn.restype=result;fn.argtypes=list(args);return fn


def abi_image(output,row):
    output.mkdir();R=module('test-deflate-stream');text=R.abi_assembly()
    [block]=re.findall(r'(?ms)^PUBLIC boom_ds_step_abi\n.*?^boom_ds_step_abi ENDP\n',text)
    source='option casemap:none\nEXTERN boom_jimage_owned_scalar_read:PROC\n.const\nboom_ds_abi_pattern BYTE 16 DUP(0B6h)\n.code\n'+block.replace('boom_ds_step_abi','boom_jur_read_abi').replace('boom_deflate_stream_step','boom_jimage_owned_scalar_read')+'END\n'
    asm,obj,dll,rsp=(output/n for n in ('abi.asm','abi.obj','abi.dll','link.rsp'));asm.write_text(source,encoding='utf-8',newline='\n')
    assembler,linker,library=(B.checked(row[n]) for n in ('assembler','linker','kernel32'))
    B.assemble(asm,obj,assembler,output/'assembler.log')
    args=['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(dll)+'"','/EXPORT:boom_jur_read_abi']
    args+=['"'+str(p)+'"' for p in (B.checked(row['core_object']),obj,library)]
    rsp.write_text('\n'.join(args)+'\n',encoding='utf-8',newline='\n')
    with (output/'link.log').open('xb') as log:r=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0,'Actual production scalar ABI observer link failed');image=c.WinDLL(str(dll));fn=proc(image,'boom_jur_read_abi',U,P)
    return image,fn,dict(source=S.artifact(asm),object=S.artifact(obj),image=S.artifact(dll),response=S.artifact(rsp),original_scalar_object=row['core_object'],template=S.artifact(ROOT/'scripts/test-deflate-stream.py'))


def protocol_image(output,row):
    output.mkdir();bridge=module('jimage-native-map-source');candidate=S.read(S.ART/'jimage-native-map/source-bound-v176-c/candidate.json')
    meta=candidate['metadata']['source'];text='option casemap:none\n'+bridge.data(meta)+'\nEND\n'
    # This is the actual cold bridge data only, never a published fake owner.
    # Tests below use pending Contexts/invalid typed metadata, not success.
    asm,obj,dll,rsp=(output/n for n in ('bridge-data.asm','bridge-data.obj','protocol.dll','link.rsp'));asm.write_text(text,encoding='utf-8',newline='\n')
    assembler,linker,library=(B.checked(row[n]) for n in ('assembler','linker','kernel32'));B.assemble(asm,obj,assembler,output/'assembler.log')
    runtime=B.checked(row['metadata']['runtime']);objects=[B.checked(row['wrapper_object']),B.checked(row['core_object']),obj];libraries=[runtime.with_suffix('.lib'),library]
    exports={B.C.SERVICE,'boom_jimage_unsafe_memory_read'}
    args=['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(dll)+'"',*['/EXPORT:'+n for n in sorted(exports)],*['"'+str(p)+'"' for p in objects+libraries]]
    rsp.write_text('\n'.join(args)+'\n',encoding='utf-8',newline='\n')
    with (output/'link.log').open('xb') as log:r=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0,'Typed invalid/pending protocol image link failed')
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.WinDLL(str(runtime)),c.WinDLL(str(dll))
    old=proc(rt,'boom_java_unsafe_memory',Q,P,P,P,U);new=proc(image,'boom_jimage_unsafe_memory_read',Q,P,P,P,U,P);tramp=proc(image,B.C.SERVICE,Q,P,P,P,U);calls=0
    for op in [r['operation'] for r in row['metadata']['source']['methods']]+[0,0xffffffff]:
        for base in (0,1):
            for pending in (0,16,20,0xdeadbeef):
                initial=[pending,0x12345678,0x89abcdef,0,0x11223344,0x55667788,0x99aabbcc,0xddeeff00];argv=(Q*5)(0,base,0xffffffffffffffff,7,9)
                before=(U*8)(*initial);a=old(before,argv,None,op)
                for fn,extra in ((new,(None,)),(tramp,())):
                    ctx=(U*8)(*initial);b=fn(ctx,argv,None,op,*extra);S.check(a==b and list(ctx)==list(before),'Original pending/invalid typed protocol changed');calls+=1
                    if pending:S.check(list(ctx)==initial,'Any pending Context byte changed')
    result=dict(verified=True,calls=calls,actual_original_runtime=row['metadata']['runtime'],all_eight_Context_DWORDs_checked=True,
        no_successful_typed_heap_receiver_claimed=True,bridge_state_remained_cold=True,host_owner_cell_written=False,
        wrapper_object=row['wrapper_object'],scalar_object=row['core_object'],source=S.artifact(asm),image=S.artifact(dll),response=S.artifact(rsp),
        inputs=[S.artifact(p) for p in objects+libraries],bridge_source=S.artifact(ROOT/'scripts/jimage-native-map-source.py'),bridge_candidate=S.artifact(S.ART/'jimage-native-map/source-bound-v176-c/candidate.json'))
    S.write(output/'verification.json',result);return S.artifact(output/'verification.json')


def jdk_oracle(output,image_file,rows):
    output.mkdir();home=Path('D:/Dev/Java/jdk-21');pins=[S.artifact(home/p) for p in ('bin/java.exe','bin/javac.exe','bin/server/jvm.dll','lib/modules')]
    text='''import java.nio.*;import java.nio.channels.*;import java.nio.file.*;public class JimageReadOracle {public static void main(String[] a)throws Exception{try(FileChannel f=FileChannel.open(Path.of(a[0]),StandardOpenOption.READ)){ByteBuffer b=f.map(FileChannel.MapMode.READ_ONLY,0,f.size()).order(ByteOrder.LITTLE_ENDIAN);int count=0;for(String line:Files.readAllLines(Path.of(a[1]))){String[] p=line.split("\\t");int k=Integer.parseInt(p[0]),at=Integer.parseInt(p[1]);long v=switch(k){case 2->b.get(at);case 3->b.getChar(at);case 4->b.getShort(at);case 5->b.getInt(at);case 6->b.getLong(at);default->throw new AssertionError();};if(!Long.toUnsignedString(v).equals(p[2]))throw new AssertionError(line);count++;}System.out.println("JIMAGE_scalar_references="+count);}}}'''
    source=output/'JimageReadOracle.java';manifest=output/'cases.tsv';source.write_text(text,encoding='utf-8',newline='\n');manifest.write_text(''.join(f'{kind}\t{at}\t{value}\n' for kind,at,value in rows),encoding='utf-8',newline='\n')
    with (output/'javac.log').open('xb') as log:r=subprocess.run([str(home/'bin/javac.exe'),'-d',str(output),str(source)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0,'JDK scalar oracle compilation failed')
    with (output/'java.log').open('xb') as log:r=subprocess.run([str(home/'bin/java.exe'),'-cp',str(output),'JimageReadOracle',str(image_file),str(manifest)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0 and (output/'java.log').read_text().strip()=='JIMAGE_scalar_references='+str(len(rows)),'JDK mapped ByteBuffer references differ')
    for item in pins:B.checked(item)
    result=dict(verified=True,scope='tool_only_JDK_actual_readonly_mapped_ByteBuffer_reference',cases=len(rows),source=S.artifact(source),class_file=S.artifact(output/'JimageReadOracle.class'),manifest=S.artifact(manifest),tools=pins,delivery_uses_JVM=False)
    S.write(output/'verification.json',result);return S.artifact(output/'verification.json')


def run(candidate_file,output):
    output=Path(output).resolve();S.check(output.is_relative_to(B.ART) and not output.exists(),'Fresh scalar execution output required')
    proof=B.verify(candidate_file);row=S.read(candidate_file);output.mkdir(parents=True);S.write(output/'machine-verification.json',proof)
    before=[S.artifact(Path(__file__)),S.artifact(candidate_file),*row['metadata']['sources'].values(),row['metadata']['bridge_source']]
    image=c.WinDLL(str(B.checked(row['image'])));scalar=proc(image,B.EXPORTED_SCALAR,U,P);init=proc(image,'boom_jimage_owner_init',U,P,U,U);close=proc(image,'boom_jimage_owner_close',U,P)
    funcs={n:proc(image,'boom_jimage_owner_'+n,U,P) for n in ('open','lookup','release')}
    S.check(c.sizeof(ReadJob)==48 and ReadJob.status.offset==32 and c.sizeof(OwnerJob)==64,'Actual job sizes/offsets')
    image_file=Path('D:/Dev/Java/jdk-21/lib/modules');original=S.artifact(image_file);S.check(original['digest']['size']==141325186 and original['digest']['sha256']=='541b62fa469595c7eeb2c329dad24151887be50056e08b5e4e1534c6260bb263','Locked original modules image differs')
    plain=image_file.read_bytes();pool=c.create_string_buffer(128);S.check(init(pool,128,4)==0,'Actual owner initialization failed')
    def owner(n,key=None,token=0):
        raw=c.create_string_buffer(key.encode('utf-16-le')) if key else None
        job=OwnerJob(c.addressof(pool),c.addressof(raw) if raw else None,len(key) if key else 0,token)
        result=funcs[n](c.byref(job));S.check(result==job.status,'Actual owner result/status mismatch');return job
    opened=owner('open',str(image_file.resolve()));S.check(opened.status==0 and opened.length==len(plain),'Real image owner open failed')
    baseline=pool.raw
    calls=0
    def read(address,kind,*,fn=scalar,expected=None):
        nonlocal calls
        storage=c.create_string_buffer(b'\xa5'*16+b'\0'*48+b'\x5a'*16);job=ReadJob.from_buffer(storage,16);job.owner=c.addressof(pool);job.address=address;job.kind=kind
        inputs=bytes(storage.raw[16:40]);status=fn(c.byref(job));calls+=1
        if fn is scalar:S.check(status==job.status,'Actual scalar result/status mismatch')
        else:S.check(status==0,'Win64 nonvolatile/stack ABI violation')
        S.check(storage.raw[:16]==b'\xa5'*16 and storage.raw[64:80]==b'\x5a'*16 and storage.raw[16:40]==inputs,'Scalar changed guard or input fields')
        S.check(job.reserved==job.reserved2==job.reserved3==0,'Reserved job input changed')
        if expected is not None:S.check(job.status==0 and job.value==expected,'Actual signed/unsigned JIMAGE read differs')
        return job.status,job.value
    def expected(offset,kind):
        width=B.C.KINDS[kind][2];return int.from_bytes(plain[offset:offset+width],'little',signed=kind in (2,4,5))&0xffffffffffffffff
    abi_dll,abi,abi_record=abi_image(output/'ABI-probe',row);rng=random.Random(0x4a494d47);checked=0;references=[]
    for kind,(_,_,width) in B.C.KINDS.items():
        offsets=sorted({0,1,2,3,4,7,8,27,28,len(plain)-width,*[rng.randrange(len(plain)-width+1) for _ in range(1024)]})
        for at in offsets:
            value=expected(at,kind);read(opened.view+at,kind,expected=value);read(opened.view+at,kind,fn=abi,expected=value);references.append((kind,at,value));checked+=1
        for address in (0,1,opened.view-1,opened.view+len(plain),opened.view+len(plain)-width+1,0xffffffffffffffff,0xffffffffffffffff-width+2):
            status,_=read(address,kind);S.check(status in (1,2),'Unknown/partial/wrapped address was read')
    for kind in (0,1,7,8,9,18,34,69,86,0xffffffff):S.check(read(opened.view,kind)[0]==2,'An unprovided operation performed a read')
    S.check(pool.raw==baseline,'Read-only scalar changed owner counters/records')
    abi_record.update(verified=True,calls=checked,nonvolatile_GPR=8,nonvolatile_XMM=10,stack_and_two_canaries=True);S.write(output/'ABI-probe/verification.json',abi_record)
    # A real empty leased record is skipped; another real node remains readable.
    fixture=output/'fixture.jimage';fixture.write_bytes(struct.pack('<7I',0xcafedada,0x10000,0,0,0,0,1)+bytes(range(256)))
    second=owner('open',str(fixture));S.check(second.status==0,'Second real mapping');S.check(owner('release',token=second.token).status==0,'Second mapping lease release')
    S.check(read(second.view,5)[0]==1,'Unleased record was readable');read(opened.view,5,expected=expected(0,5));S.check(close(pool)==2,'A Java/VM lease must prevent close')
    barrier=Barrier(9)
    def worker(seed):
        local=random.Random(seed);ident=get_native_id();succeeded=misses=0
        read(opened.view+seed,2,expected=expected(seed,2));barrier.wait()
        for _ in range(2048):
            kind=local.choice(list(B.C.KINDS));width=B.C.KINDS[kind][2];at=local.randrange(len(plain)-width+1);status,value=read(opened.view+at,kind)
            if status==0:S.check(value==expected(at,kind),'Concurrent physical data differs');succeeded+=1
            else:S.check(status in (1,4),'Concurrent close/read status');misses+=1
        return dict(OS_thread=ident,successful_reads=succeeded,rejected_after_lease_or_close=misses)
    with ThreadPoolExecutor(max_workers=8) as workers:
        futures=[workers.submit(worker,i) for i in range(8)];barrier.wait();time.sleep(.002)
        S.check(owner('release',token=opened.token).status==0 and close(pool)==0,'Concurrent exclusive release/close failed')
        observations=[f.result() for f in futures]
    S.check(len({r['OS_thread'] for r in observations})==8,'Eight actual native OS workers required')
    S.check(read(opened.view,6)[0]==4,'Closed owner retained readable stale view')
    S.check(U.from_address(c.addressof(pool)+24).value==2 and all(Q.from_address(c.addressof(pool)+at).value==0 for at in (32,48,56,64,72,80)),'Mapping resources were not actually closed')
    protocol=protocol_image(output/'source-protocol',row)
    jdk=jdk_oracle(output/'jdk-oracle',image_file,references)
    for item in before:B.checked(item)
    for key in ('assembly','object','wrapper_assembly','wrapper_object','core_assembly','core_object','image','response'):B.checked(row[key])
    S.check(S.artifact(image_file)==original,'Original file changed')
    result=dict(verified=True,scope='standalone_actual_RO_JIMAGE_scalar_and_pending_invalid_typed_protocol_not_Java_buffer_execution',
        candidate=S.artifact(candidate_file),machine_verification=S.artifact(output/'machine-verification.json'),original_image=original,scalar_calls=calls,scalar_reference_values=checked,
        ABI=S.artifact(output/'ABI-probe/verification.json'),JDK_reference=jdk,OS_workers=observations,source_protocol=protocol,owner_final=dict(state=2,entries=0,leases=0,mapped_bytes=0,file_handles=0,map_handles=0),
        actual_production_owner_object_reused=True,only_five_plain_read_kinds=True,source_job_guards_and_inputs_unchanged=True,arbitrary_off_heap=False,
        pending_Context_not_cleared=True,valid_Java_Unsafe_receiver_executed=False,original_Java_DirectByteBuffer_execution=False,bridge_runtime_binding_verified=False,
        registered=False,full_selection_reverified=False,game_started=False,harness=S.artifact(__file__))
    S.write(output/'execution.json',result);return output/'execution.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();existed=a.output.exists()
    try:print(run(a.candidate,a.output))
    except BaseException as error:
        if not existed and a.output.resolve().is_relative_to(B.ART):
            a.output.mkdir(parents=True,exist_ok=True);failure=a.output/'failure.json'
            if not failure.exists():S.write(failure,dict(verified=False,error=repr(error),harness=S.artifact(__file__),candidate=S.artifact(a.candidate)))
        raise
