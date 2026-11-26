"""Actual RFC1950/Adler ASM streaming probes and Python/JDK references."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import subprocess
import threading
import zlib

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    s=importlib.util.spec_from_file_location('zlib_test_'+name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


C=module('zlib-stream-candidate');R=module('test-deflate-stream');T=R.T
STATE_BYTES=34560


class Job(R.Job):
    _fields_=[('adler',ctypes.c_uint32),('dictionary',ctypes.c_uint32),('expected',ctypes.c_uint32),('reserved',ctypes.c_uint32)]


class AdlerJob(ctypes.Structure):
    _fields_=[('seed',ctypes.c_uint32),('reserved',ctypes.c_uint32),('src',ctypes.c_void_p),('length',ctypes.c_uint64),('result',ctypes.c_uint32),('status',ctypes.c_uint32)]


class State(R.State):
    def __init__(self,native,snapshot=None):
        self.owner=ctypes.create_string_buffer(b'\xa9'*(STATE_BYTES+64));self.address=ctypes.addressof(self.owner)+32
        if snapshot is None:C.check(native.reset(self.address,STATE_BYTES)==0,'zlib reset failed')
        else:C.check(len(snapshot)==STATE_BYTES,'Wrapper snapshot size');ctypes.memmove(self.address,snapshot,STATE_BYTES)
        self.guard()
    def bytes(self):return ctypes.string_at(self.address,STATE_BYTES)
    def guard(self):C.check(ctypes.string_at(self.address-32,32)==b'\xa9'*32 and ctypes.string_at(self.address+STATE_BYTES,32)==b'\xa9'*32,'Wrapper state canary overwritten')


class Native:
    def __init__(self,path):
        self.dll=ctypes.CDLL(str(path));self.reset=self.dll.boom_zlib_stream_reset;self.fn=self.dll.boom_zlib_stream_step;self.adler_fn=self.dll.boom_adler32_update
        self.reset.argtypes=[ctypes.c_void_p,ctypes.c_uint32];self.reset.restype=ctypes.c_uint32
        self.fn.argtypes=[ctypes.POINTER(Job)];self.fn.restype=ctypes.c_uint32
        self.adler_fn.argtypes=[ctypes.POINTER(AdlerJob)];self.adler_fn.restype=ctypes.c_uint32;self.abi=False
        C.check(ctypes.sizeof(Job)==96 and Job.adler.offset==80 and ctypes.sizeof(AdlerJob)==32,'Wrapper/Adler ABI layout changed')
    def step(self,state,raw,capacity,final=False):
        source=ctypes.create_string_buffer(b'\x91'*16+raw+b'\x91'*16);target=ctypes.create_string_buffer(b'\xc5'*(capacity+32));before=source.raw
        old_in,old_out,old_adler=state.q(56),state.q(64),state.d(28)
        job=Job(state.address,ctypes.addressof(source)+16,len(raw),ctypes.addressof(target)+16,capacity,int(final));rc=self.fn(ctypes.byref(job))
        if self.abi:C.check(rc==0,'zlib Win64 ABI violation');rc=job.status
        C.check(rc==job.status and job.consumed<=len(raw) and job.written<=capacity,'zlib return/progress bounds violated')
        C.check(job.total_in==old_in+job.consumed==state.q(56) and job.total_out==old_out+job.written==state.q(64),'Wrapper cumulative counters disagree')
        out=target.raw[16:16+job.written]
        C.check(job.adler==zlib.adler32(out,old_adler)==state.d(28),'Adler did not accumulate exactly actual output')
        C.check(job.dictionary==state.d(32) and job.expected==state.d(48) and job.reserved==0,'Wrapper observations differ from actual state')
        C.check(state.q(256+48)==job.total_out,'Nested raw and wrapper output counts differ')
        C.check(source.raw==before and target.raw[:16]==b'\xc5'*16 and target.raw[16+capacity:32+capacity]==b'\xc5'*16,'Wrapper changed input/guard bytes')
        state.guard();ctypes.memset(ctypes.addressof(source)+16,0xde,len(raw));ctypes.memset(ctypes.addressof(target)+16,0xe9,capacity)
        return job,out
    def adler(self,raw,seed=1):
        src=ctypes.create_string_buffer(b'\x91'*16+raw+b'\x91'*16);before=src.raw;job=AdlerJob(seed,0,ctypes.addressof(src)+16,len(raw))
        rc=self.adler_fn(ctypes.byref(job))
        if self.abi:C.check(rc==0,'Adler Win64 ABI violation');rc=job.status
        C.check(rc==job.status==0 and job.result==zlib.adler32(raw,seed) and src.raw==before,'Standalone Adler mismatch/input changed')
        return job.result


def header(cinfo=7,level=2,dictionary=False,method=8):
    cmf=(cinfo<<4)|method;flg=(level<<6)|(32 if dictionary else 0);flg+=(31-((cmf<<8)|flg)%31)%31
    return bytes([cmf,flg])


def row(name,raw,output,status=0,used=None,reference='ok',reference_output=None,dictionary=0):
    return dict(name=name,raw=raw,output=output,status=status,used=len(raw) if used is None and status==0 else used,
        reference=reference,reference_output=output if reference_output is None else reference_output,dictionary=dictionary)


def wrap(original,cinfo=7,level=2):
    return header(cinfo,level)+original['raw']+zlib.adler32(original['output']).to_bytes(4,'big')


def fixtures():
    raw_good,raw_bad,rfc=R.fixtures();good=[row('wrapped-'+r['name'],wrap(r),r['output']) for r in raw_good]
    variants={((r['raw'][0]>>1)&3):r for r in raw_good if r['name'].startswith('zlib-') and r['name'].endswith('-3')}
    for cinfo in range(8):
        for level in range(4):
            original=variants[(cinfo+level)%3];good.append(row(f'CINFO{cinfo}-FLEVEL{level}',wrap(original,cinfo,level),original['output']))
    bad=[];policies=[];rng=random.Random(1950)
    for cinfo in range(8):
        size=1<<(cinfo+8)
        for excess in (0,1):
            if size+excess>32768:continue
            distance=size+excess;prefix=bytes(rng.randrange(256) for _ in range(distance));b=T.Bits();T.stored(b,prefix,False);lit,dist=T.fixed_header(b)
            index=max(i for i,v in enumerate(T.DISTANCE_BASE) if v<=distance)
            b.code(lit,285);b.code(dist,index);b.put(distance-T.DISTANCE_BASE[index],T.DISTANCE_BITS[index]);b.code(lit,256)
            output=bytearray(prefix)
            for _ in range(258):output.append(output[-distance])
            original=T.case('window',b.raw(),bytes(output));compressed=wrap(original,cinfo)
            if excess:policies.append(row(f'CINFO{cinfo}-distance-plus1',compressed,prefix,13,reference='policy',reference_output=bytes(output)))
            else:good.append(row(f'CINFO{cinfo}-distance-exact',compressed,bytes(output)))
    for method in (0,7,15):bad.append(row(f'bad-CM{method}',header(method=method)+b'\x03\x00'+b'\x00\x00\x00\x01',b'',10,1,'reject'))
    for cinfo in (8,9,15):bad.append(row(f'bad-CINFO{cinfo}',header(cinfo=cinfo)+b'\x03\x00'+b'\x00\x00\x00\x01',b'',10,1,'reject'))
    h=header();bad.append(row('bad-mod31',h[:1]+bytes([h[1]^1])+b'junk',b'',10,2,'reject'))
    for i in (0,1,4,5,11):
        original=good[i]
        for n in range(4):
            broken=bytearray(original['raw']);broken[len(broken)-4+n]^=1
            bad.append(row(f'bad-Adler-{i}-{n}',bytes(broken),original['output'],11,len(broken),'reject'))
    for original in raw_bad:
        bad.append(row('raw-'+original['name'],header()+original['raw']+b'\x00'*4,None,{2:4,4:5,5:6,6:7,7:8}[original['status']],reference='reject'))
    dictionaries=[]
    for value in (0,1,0x12345678,0xffffffff):
        dictionaries.append(row('FDICT-'+hex(value),header(dictionary=True)+value.to_bytes(4,'big')+b'unread-body',b'',12,6,'dict',dictionary=value))
    dictionary=b'original-dictionary-pattern'*200;co=zlib.compressobj(wbits=15,zdict=dictionary);raw=co.compress(dictionary[:300])+co.flush()
    dictionaries.append(row('FDICT-actual-zlib',raw,b'',12,6,'dict',dictionary=zlib.adler32(dictionary)))
    rfc_row=row('RFC-HDIST32-unused-reserved',wrap(rfc),b'',reference='reject')
    return good,bad,dictionaries,policies,rfc_row


def drive(native,r,ins,outs,tail=b'',cut=None,state=None,prefix=b'',start=0):
    state=state or State(native);raw=r['raw']+tail;pos=start;out=bytearray(prefix);calls=0;phases=set();statuses={}
    limit=30*(len(raw)+len(r['output'] or b'')+1)+300
    while calls<limit:
        n=min(ins[calls%len(ins)],len(raw)-pos) if cut is None else cut if calls==0 else cut-pos if pos<cut else len(raw)-pos
        job,part=native.step(state,raw[pos:pos+n],outs[calls%len(outs)],pos+n==len(raw));calls+=1;pos+=job.consumed;out.extend(part)
        phases.add(state.d(12));statuses[job.status]=statuses.get(job.status,0)+1
        if job.status==0 or job.status>=3:break
        C.check(job.status in (1,2),'Invalid continuation status')
    C.check(calls<limit and job.status==r['status'],'Wrapper stream/status stalled or differs: '+r['name']+' '+str(job.status))
    if r['output'] is not None:C.check(out==r['output'],'Wrapper output differs: '+r['name'])
    if r['used'] is not None:C.check(pos==r['used'],'Wrapper consumption differs: '+r['name'])
    if job.status==0:C.check(job.adler==job.expected==zlib.adler32(out),'Final Adler/trailer mismatch')
    if job.status==12:C.check(job.dictionary==r['dictionary'] and job.adler==1 and job.total_out==0,'DICTID and output Adler were conflated')
    return dict(calls=calls,phases=sorted(phases),statuses=statuses,input_used=pos,output_used=len(out),Adler=job.adler,DICTID=job.dictionary),state


def python_stream(r,ins,outs):
    decoder=zlib.decompressobj();raw=r['raw']+b'PY-TAIL';pos=0;out=bytearray();calls=0
    while calls<30*(len(raw)+len(r['output'])+1)+300:
        n=min(ins[calls%len(ins)],len(raw)-pos);cap=outs[calls%len(outs)];calls+=1
        if cap==0:continue
        offered=raw[pos:pos+n];out.extend(decoder.decompress(offered,cap));pos+=len(offered)-max(len(decoder.unconsumed_tail),len(decoder.unused_data))
        if decoder.eof:break
    C.check(decoder.eof and out==r['output'] and pos==len(r['raw']),'Python wrapped incremental oracle mismatch: '+r['name']);return calls


def protocol(native,good,bad,dictionaries):
    calls=0
    for r in (good[0],good[-1],bad[0],bad[7],dictionaries[-1]):
        _,state=drive(native,r,(1,),(7,));before=state.bytes();job,out=native.step(state,b'new-unread-input',10)
        C.check(job.status==r['status'] and job.consumed==job.written==0 and not out and state.bytes()==before,'Terminal/dictionary state was not sticky');calls+=1
        C.check(native.reset(state.address,STATE_BYTES)==0 and state.bytes()==State(native).bytes(),'Wrapper reset failed to clear all raw/history/checksum state');calls+=1
        drive(native,good[1],(1,),(1,),state=state);calls+=1
    # A pending trailer must still be consumed with no output capacity.
    r=good[4];state=State(native);body=r['raw'][:-4];job,out=native.step(state,body,len(r['output']),False)
    C.check(job.status==1 and state.d(12)==4 and job.adler==zlib.adler32(out),'Real raw completion did not wait for trailer');calls+=1
    for byte in r['raw'][-4:]:
        job,_=native.step(state,bytes([byte]),0,False);calls+=1
    C.check(job.status==0 and job.written==0 and job.expected==job.adler,'Trailer incorrectly depended on output capacity')
    return calls


def truncations(native,good,dictionaries):
    streams=0;calls=0
    for r in good:
        points={0,1,2,len(r['raw'])//2,*range(max(0,len(r['raw'])-5),len(r['raw']))}
        if len(r['raw'])<=160:points.update(range(len(r['raw'])))
        for n in points:
            bad=dict(r,raw=r['raw'][:n],output=None,status=4,used=n,reference='reject')
            obs,state=drive(native,bad,(1,2,7),(7,512));calls+=obs['calls'];streams+=1;before=state.bytes()
            job,_=native.step(state,b'cannot-repair-end-input',2);C.check(job.status==4 and state.bytes()==before,'Truncated wrapper was not sticky')
    for r in dictionaries:
        for n in range(6):
            obs,_=drive(native,dict(r,raw=r['raw'][:n],output=None,status=4,used=n),(1,),(0,7));calls+=obs['calls'];streams+=1
    return dict(streams=streams,calls=calls)


def arguments(native):
    state=State(native);before=state.bytes();buf=ctypes.create_string_buffer(64);p=ctypes.addressof(buf);calls=0
    C.check(native.fn(None)==3 and native.reset(None,STATE_BYTES)==3,'NULL wrapper validation failed');calls+=2
    for n in (0,STATE_BYTES-1,STATE_BYTES+1):C.check(native.reset(state.address,n)==3 and state.bytes()==before,'Bad wrapper reset size altered state');calls+=1
    for job in [Job(state.address,0,1,p,8),Job(state.address,p,1,0,1),Job(state.address,p,1,p+8,8,2),Job(state.address,p,16,p+8,16),
                Job(state.address,(1<<64)-2,4,p,8),Job(state.address,p,4,(1<<64)-2,4),Job(state.address,state.address+256,8,p,8),Job(state.address,p,8,state.address+256,8)]:
        C.check(native.fn(ctypes.byref(job))==3 and state.bytes()==before,'Invalid wrapper ranges changed valid state');calls+=1
    alias=Job.from_address(state.address+144);alias.state=state.address;before=state.bytes()
    C.check(native.fn(ctypes.byref(alias))==3 and state.bytes()==before,'Wrapper job-state alias was written');calls+=1
    for at,value in ((0,0),(8,STATE_BYTES-1),(12,8),(52,2)):
        state=State(native);ctypes.c_uint32.from_address(state.address+at).value=value;before=state.bytes();job=Job(state.address,p,0,p+8,0)
        C.check(native.fn(ctypes.byref(job))==9 and state.bytes()==before,'Invalid wrapper header not rejected read-only');calls+=1
    C.check(native.adler_fn(None)==3,'NULL Adler job');calls+=1
    for job in [AdlerJob(1,1,p,1),AdlerJob(1,0,0,1),AdlerJob(1,0,(1<<64)-2,4)]:
        C.check(native.adler_fn(ctypes.byref(job))==job.status==3,'Invalid Adler arguments not rejected');calls+=1
    return calls


def guards(native,good,bad,dictionaries):
    calls=0
    for r in [good[0],good[4],good[-1],bad[0],bad[7],dictionaries[-1]]:
        for end in (False,True):
            state=State(native);pos=0;out=bytearray()
            for i in range(30*(len(r['raw'])+len(r['output'] or b'')+1)+300):
                raw=r['raw'][pos:pos+1];cap=0 if i%3==0 else 7
                with T.guard_buffer(raw,len(raw),True) as src,T.guard_buffer(b'',cap,False,end) as dst:
                    job=Job(state.address,src,len(raw),dst,cap,int(pos+len(raw)==len(r['raw'])));rc=native.fn(ctypes.byref(job));calls+=1
                    C.check(rc==job.status and job.consumed<=len(raw) and job.written<=cap,'Guarded wrapper bounds/status violated')
                    pos+=job.consumed;out.extend(ctypes.string_at(dst,job.written));state.guard()
                if rc==0 or rc>=3:break
            C.check(rc==r['status'] and (r['output'] is None or out==r['output']),'Guarded wrapper result differs')
    for end in (False,True):
        with T.guard_buffer(b'',STATE_BYTES,False,end) as state:
            C.check(native.reset(state,STATE_BYTES)==0,'Guarded wrapper reset');r=good[-1];src=ctypes.create_string_buffer(r['raw']);dst=ctypes.create_string_buffer(len(r['output']))
            job=Job(state,ctypes.addressof(src),len(r['raw']),ctypes.addressof(dst),len(r['output']),1)
            C.check(native.fn(ctypes.byref(job))==0 and dst.raw==r['output'],'Guarded wrapper state decode');calls+=1
    return calls


def adler_vectors(native):
    rng=random.Random(65521);vectors=[];calls=0
    for size in (0,1,2,7,512,5551,5552,5553,11104,65535,100000):
        vectors.append(bytes([255])*size);vectors.append(bytes(rng.randrange(256) for _ in range(size)))
    for raw in vectors:
        for seed in (0,1,0xffff,0xffff0000,0xffffffff,rng.randrange(1<<32)):
            native.adler(raw,seed);calls+=1
        seed=1
        for at in range(0,len(raw),7):seed=native.adler(raw[at:at+7],seed);calls+=1
        C.check(seed==zlib.adler32(raw),'Adler chunk accumulation differs')
    guards=0
    for raw in vectors[:16]:
        with T.guard_buffer(raw,len(raw),True) as src:
            job=AdlerJob(1,0,src,len(raw));C.check(native.adler_fn(ctypes.byref(job))==0 and job.result==zlib.adler32(raw),'Guarded Adler input overread');guards+=1
    return vectors,dict(whole_and_chunk_calls=calls,guard_page_calls=guards)


def abi_fixture(output,candidate,rows,vectors):
    output.mkdir();text=R.abi_assembly().replace('boom_deflate_stream_','boom_zlib_stream_').replace('boom_ds_','boom_zw_')
    match=re.search(r'PUBLIC boom_zw_step_abi\n.*?boom_zw_step_abi ENDP\n',text,re.S);C.check(match,'Pinned ABI template step block missing')
    extra=match.group().replace('boom_zw_step_abi','boom_zw_adler_abi').replace('step_ok','adler_ok').replace('step_xmm','adler_xmm').replace('call boom_zlib_stream_step','call boom_adler32_update')
    text=text.replace('option casemap:none\n','option casemap:none\nEXTERN boom_adler32_update:PROC\n').removesuffix('END\n')+extra+'END\n'
    source,obj,dll,rsp=(output/n for n in ('abi.asm','abi.obj','abi.dll','link.rsp'));source.write_text(text,encoding='utf-8',newline='\n')
    assembler,linker=(C.checked(candidate[n]) for n in ('assembler','linker'))
    with (output/'assembler.log').open('xb') as log:run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0,'Wrapper ABI assembly failed')
    args=['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(dll)+'"']
    args+=['/EXPORT:boom_zw_'+n+'_abi' for n in ('step','reset','adler')]+['"'+str(C.checked(candidate['object']))+'"','"'+str(C.checked(candidate['raw']['object']))+'"','"'+str(obj)+'"']
    rsp.write_text('\n'.join(args)+'\n',encoding='utf-8',newline='\n')
    with (output/'linker.log').open('xb') as log:run=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0,'Wrapper ABI link failed')
    image=ctypes.CDLL(str(dll));native=Native.__new__(Native);native.dll=image;native.abi=True
    native.reset=image.boom_zw_reset_abi;native.fn=image.boom_zw_step_abi;native.adler_fn=image.boom_zw_adler_abi
    native.reset.argtypes=[ctypes.c_void_p,ctypes.c_uint32];native.reset.restype=ctypes.c_uint32;native.fn.argtypes=[ctypes.POINTER(Job)];native.fn.restype=ctypes.c_uint32
    native.adler_fn.argtypes=[ctypes.POINTER(AdlerJob)];native.adler_fn.restype=ctypes.c_uint32;calls=0
    for r in rows:obs,_=drive(native,r,(1,2,7),(0,1,7,512));calls+=obs['calls']
    for raw in vectors:native.adler(raw);native.adler(raw,0xffffffff)
    result=dict(verified=True,step_calls=calls,reset_calls=len(rows),Adler_calls=2*len(vectors),nonvolatile_GPR=8,nonvolatile_XMM=10,stack_pointer_and_two_canaries=True,
        template_source=C.artifact(ROOT/'scripts/test-deflate-stream.py'),template_changes='exact target/public/label renames plus third same-ABI block',source=C.artifact(source),object=C.artifact(obj),image=C.artifact(dll),response=C.artifact(rsp),
        original_objects=[candidate['object'],candidate['raw']['object']],assembler=C.artifact(assembler),linker=C.artifact(linker),scope='test_only_ABI_observer_exact_wrapper_and_raw_objects')
    C.write(output/'verification.json',result);return C.artifact(output/'verification.json')


ORACLE=r'''import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;
public class ZlibStreamOracle {
 public static void main(String[] args) throws Exception {
  int cases=0,adlers=0,policyAccept=0,policyReject=0;long calls=0;
  int[][][] schedules={{{1},{1}},{{2},{7}},{{7},{2}},{{512},{512}},{{0,1,0,2,7,512},{0,1,0,7,2,512}},{{7,1,512,2},{1,0,512,7,0,2}}};
  for(String line:Files.readAllLines(Path.of(args[0]))) {
   String[] p=line.split("\t");byte[] raw=Files.readAllBytes(Path.of(p[1]));
   for(int[][] schedule:schedules) {
    Inflater f=new Inflater();MessageDigest sha=MessageDigest.getInstance("SHA-256");int offered=0,step=0;long written=0;boolean invalid=false;
    try {
     try {
      while(!f.finished() && !f.needsDictionary()) {
       int cap=schedule[1][step%schedule[1].length];
       if(f.needsInput()) {int n=Math.min(schedule[0][step%schedule[0].length],raw.length-offered);f.setInput(raw,offered,n);offered+=n;}
       long oldIn=f.getBytesRead(),oldOut=f.getBytesWritten();int available=f.getRemaining();byte[] dst=new byte[cap];int n=f.inflate(dst);
       if(f.getBytesRead()-oldIn<0 || f.getBytesRead()-oldIn>available || f.getBytesWritten()-oldOut!=n || n>cap) throw new AssertionError("counters "+p[0]);
       sha.update(dst,0,n);written+=n;step++;calls++;
       if(written>262144 || step>10000000) throw new AssertionError("bound "+p[0]);
       if(f.needsInput() && offered==raw.length && !f.finished()) break;
      }
     } catch(DataFormatException e) {invalid=true;}
     if(p[2].equals("ok") || p[2].equals("policy") && f.finished()) {
      if(invalid || !f.finished() || written!=Long.parseLong(p[3]) || f.getBytesRead()!=Long.parseLong(p[5]) ||
       f.getRemaining()!=offered-f.getBytesRead() || Integer.toUnsignedLong(f.getAdler())!=Long.parseLong(p[7]) ||
       !HexFormat.of().formatHex(sha.digest()).equals(p[4])) throw new AssertionError("wrapped mismatch "+p[0]);
      if(p[2].equals("policy")) policyAccept++;
     } else if(p[2].equals("dict")) {
      if(invalid || !f.needsDictionary() || f.finished() || f.getBytesRead()!=6 || f.getBytesWritten()!=0 ||
       Integer.toUnsignedLong(f.getAdler())!=Long.parseLong(p[6]) || f.getRemaining()!=offered-6) throw new AssertionError("DICTID "+p[0]);
     } else {
      if(f.finished() || p[2].equals("policy") && !invalid) throw new AssertionError("accepted invalid "+p[0]);
      if(p[2].equals("policy")) policyReject++;
     }
     cases++;
    } finally {f.end();}
   }
  }
  for(String line:Files.readAllLines(Path.of(args[1]))) {
   String[] p=line.split("\t");byte[] raw=Files.readAllBytes(Path.of(p[0]));
   for(int[][] schedule:schedules) {
    Adler32 a=new Adler32();int pos=0,step=0;
    while(pos<raw.length) {int n=Math.min(schedule[0][step%schedule[0].length],raw.length-pos);a.update(raw,pos,n);pos+=n;step++;}
    if(a.getValue()!=Long.parseLong(p[1])) throw new AssertionError("Adler32 oracle "+p[0]);adlers++;
   }
  }
  System.out.println("zlib_JDK_cases="+cases+" calls="+calls+" Adler_cases="+adlers+" policy_accept="+policyAccept+" policy_reject="+policyReject);
 }
}
'''


def oracle(output,rows,vectors):
    output.mkdir();source=output/'ZlibStreamOracle.java';source.write_text(ORACLE,encoding='utf-8',newline='\n')
    tools=[C.artifact(T.JAVA/n) for n in ('bin/java.exe','bin/javac.exe','bin/server/jvm.dll','lib/modules','lib/src.zip')];lines=[];files=[]
    for r in rows:
        path=output/(r['name']+'.bin');path.write_bytes(r['raw']+b'JDK-TAIL');files.append(C.artifact(path));expected=r['reference_output'] or b''
        lines.append('\t'.join([r['name'],str(path),r['reference'],str(len(expected)),hashlib.sha256(expected).hexdigest(),str(6 if r['reference']=='dict' else len(r['raw'])),str(r['dictionary']),str(zlib.adler32(expected))]))
    manifest=output/'streams.tsv';manifest.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n');adlers=[]
    for i,raw in enumerate(vectors):
        path=output/('Adler-'+str(i)+'.bin');path.write_bytes(raw);files.append(C.artifact(path));adlers.append(str(path)+'\t'+str(zlib.adler32(raw)))
    checks=output/'Adler.tsv';checks.write_text('\n'.join(adlers)+'\n',encoding='utf-8',newline='\n')
    with (output/'javac.log').open('xb') as log:run=subprocess.run([str(T.JAVA/'bin/javac.exe'),'-d',str(output),str(source)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0,'JDK zlib oracle compilation failed')
    with (output/'java.log').open('xb') as log:run=subprocess.run([str(T.JAVA/'bin/java.exe'),'-cp',str(output),'ZlibStreamOracle',str(manifest),str(checks)],stdout=log,stderr=subprocess.STDOUT)
    text=(output/'java.log').read_text();match=re.fullmatch(r'zlib_JDK_cases=(\d+) calls=(\d+) Adler_cases=(\d+) policy_accept=(\d+) policy_reject=(\d+)\s*',text)
    C.check(run.returncode==0 and match and int(match[1])==len(rows)*6 and int(match[3])==len(vectors)*6,'JDK zlib oracle mismatch; retain java.log')
    C.check(tools==[C.artifact(t['path']) for t in tools],'JDK zlib tools changed')
    result=dict(verified=True,scope='JDK_reference_only_incremental_Inflater_nowrap_false_and_Adler32',cases=int(match[1]),calls=int(match[2]),Adler_cases=int(match[3]),
        small_window_policy_accepted=int(match[4]),small_window_policy_rejected=int(match[5]),source=C.artifact(source),class_file=C.artifact(output/'ZlibStreamOracle.class'),
        manifest=C.artifact(manifest),Adler_manifest=C.artifact(checks),inputs=files,tools=tools,stdout=C.artifact(output/'java.log'),JNI_getAdler_when_needsDictionary='returns_DICTID_not_output_checksum',delivery_uses_JVM=False)
    C.write(output/'verification.json',result);return C.artifact(output/'verification.json')


def run(candidate,output,rounds):
    output=Path(output).resolve();C.check(output.is_relative_to(C.ART) and not output.exists(),'Fresh isolated zlib execution required');output.mkdir(parents=True)
    candidate=Path(candidate).resolve();record=json.loads(candidate.read_text(encoding='utf-8'));before=C.artifact(candidate);sourcepins=C.sources()
    harnesses=[C.artifact(__file__),C.artifact(ROOT/'scripts/test-deflate-stream.py'),C.artifact(ROOT/'scripts/test-deflate-raw.py')]
    C.write(output/'machine-verification.json',C.verify(candidate));native=Native(C.checked(record['image']));good,bad,dictionaries,policies,rfc=fixtures()
    observations=[];calls=0;python_calls=0
    for r in good:
        for index,(ins,outs) in enumerate(R.SCHEDULES):
            obs,_=drive(native,r,ins,outs,tail=b'NATIVE-TAIL');calls+=obs['calls'];observations.append(dict(name=r['name'],schedule=index,**obs));python_calls+=python_stream(r,ins,outs)
    for r in bad+dictionaries+policies+[rfc]:
        for index,(ins,outs) in enumerate(R.SCHEDULES):
            obs,_=drive(native,r,ins,outs);observations.append(dict(name=r['name'],schedule=index,**obs))
    cuts=0;cut_calls=0
    for r in good:
        points=set(range(len(r['raw'])+1)) if len(r['raw'])<=160 else {0,1,2,*range(len(r['raw'])-5,len(r['raw'])+1)}
        for at in points:
            obs,_=drive(native,r,(512,),(max(1,len(r['output'])),),cut=at,tail=b'CUT-TAIL');cuts+=1;cut_calls+=obs['calls']
    protocol_calls=protocol(native,good,bad,dictionaries);truncated=truncations(native,good,dictionaries);invalid=arguments(native);guard_calls=guards(native,good,bad,dictionaries)
    vectors,adler=adler_vectors(native);barrier=threading.Barrier(8);small=[r for r in good if len(r['output'])<=256]
    def worker(index):
        ident=threading.get_native_id();barrier.wait();n=0
        for i in range(rounds):
            r=small[(i*3+index)%len(small)];ins,outs=R.SCHEDULES[(i+index)%6];obs,_=drive(native,r,ins,outs,tail=b'OS-TAIL');n+=obs['calls'];native.adler(r['output'])
        drive(native,good[-1],(1,7,512),(0,1,7,512),tail=b'OS-WINDOW-TAIL');drive(native,dictionaries[-1],(1,),(0,1))
        return dict(thread=ident,small_streams=rounds,history_streams=1,dictionary_streams=1,calls=n,Adler_calls=rounds)
    with ThreadPoolExecutor(max_workers=8) as pool:threads=list(pool.map(worker,range(8)))
    C.check(len({r['thread'] for r in threads})==8,'Eight zlib OS workers required')
    abi=abi_fixture(output/'ABI-probe',record,good+bad+dictionaries+policies+[rfc],vectors)
    jdk=oracle(output/'jdk-oracle',good+bad+dictionaries+policies+[rfc],vectors)
    C.check(before==C.artifact(candidate) and sourcepins==C.sources() and harnesses==[C.artifact(r['path']) for r in harnesses],'zlib execution source pins changed')
    for n in ('assembly','object','image','response','assembler','linker'):C.checked(record[n])
    for n in ('candidate','verification','object','image','assembly'):C.checked(record['raw'][n])
    result=dict(verified=True,scope='unregistered_incremental_RFC1950_Adler32_actual_ASM_only',candidate=before,sources=sourcepins,harnesses=harnesses,
        machine_verification=C.artifact(output/'machine-verification.json'),native_ABI_probe=abi,JDK_reference=jdk,valid_streams=len(good),successful_stream_runs=len(good)*6,successful_step_calls=calls,
        python_reference_calls=python_calls,observations=observations,malformed_streams=len(bad),dictionary_cases=len(dictionaries),CINFO_distance_policy_cases=len(policies),
        all_byte_or_trailer_cuts=cuts,cut_step_calls=cut_calls,truncations=truncated,protocol_calls=protocol_calls,invalid_argument_calls=invalid,guard_page_calls=guard_calls,standalone_Adler=adler,OS_workers=threads,
        old_input_and_output_poisoned_after_each_call=True,raw_private_layout_read_only=record['abi']['raw_private_layout'],CINFO7_whole_chunk_fast_path=True,CINFO_smaller_window_distance_checked_before_copy=True,
        FDICT='actual_DICTID_then_need_dictionary_unsupported_12',output_Adler_excludes_dictionary=True,RFC_HDIST32_policy_separate=True,no_decoder_imports=True,no_mutable_globals=True,
        registered=False,JNI=False,setDictionary=False,gzip=False,CRC=False,inflater_compatible=False,game_started=False)
    C.write(output/'execution.json',result);return output/'execution.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--thread-rounds',type=int,default=64);a=p.parse_args()
    C.check(1<=a.thread_rounds<=512,'Bounded OS test rounds');print(run(a.candidate,a.output,a.thread_rounds))
