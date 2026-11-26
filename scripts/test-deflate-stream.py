"""Actual incremental ASM raw DEFLATE: arbitrary fragments, bounds and references."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import struct
import subprocess
import threading
import zlib

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('stream_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


C=module('deflate-stream-candidate');T=module('test-deflate-raw')
STATE_BYTES=34304


class Job(ctypes.Structure):
    _fields_=[('state',ctypes.c_void_p),('src',ctypes.c_void_p),('length',ctypes.c_uint64),('dst',ctypes.c_void_p),('capacity',ctypes.c_uint64),
              ('flags',ctypes.c_uint32),('status',ctypes.c_uint32),('consumed',ctypes.c_uint64),('written',ctypes.c_uint64),('total_in',ctypes.c_uint64),('total_out',ctypes.c_uint64)]


class State:
    def __init__(self,native,snapshot=None):
        self.owner=ctypes.create_string_buffer(b'\xa9'*(STATE_BYTES+64));self.address=ctypes.addressof(self.owner)+32
        if snapshot is None:C.check(native.reset(self.address,STATE_BYTES)==0,'Native state reset failed')
        else:
            C.check(len(snapshot)==STATE_BYTES,'State snapshot size');ctypes.memmove(self.address,snapshot,STATE_BYTES)
        self.guard()
    def bytes(self):return ctypes.string_at(self.address,STATE_BYTES)
    def guard(self):C.check(ctypes.string_at(self.address-32,32)==b'\xa9'*32 and ctypes.string_at(self.address+STATE_BYTES,32)==b'\xa9'*32,'State reset/step overwrote caller canaries')
    def q(self,at):return ctypes.c_uint64.from_address(self.address+at).value
    def d(self,at):return ctypes.c_uint32.from_address(self.address+at).value


class Native:
    def __init__(self,path):
        self.dll=ctypes.CDLL(str(path));self.reset=self.dll.boom_deflate_stream_reset;self.fn=self.dll.boom_deflate_stream_step
        self.reset.argtypes=[ctypes.c_void_p,ctypes.c_uint32];self.reset.restype=ctypes.c_uint32
        self.fn.argtypes=[ctypes.POINTER(Job)];self.fn.restype=ctypes.c_uint32
        self.abi=False
        C.check(ctypes.sizeof(Job)==80 and Job.status.offset==44 and Job.consumed.offset==48,'Job80 layout changed')
    def step(self,state,raw,capacity,final=False):
        source=ctypes.create_string_buffer(b'\x91'*16+raw+b'\x91'*16);target=ctypes.create_string_buffer(b'\xc5'*(capacity+32))
        before=source.raw;old_in,old_out=state.q(40),state.q(48)
        job=Job(state.address,ctypes.addressof(source)+16,len(raw),ctypes.addressof(target)+16,capacity,int(final))
        rc=self.fn(ctypes.byref(job))
        if self.abi:C.check(rc==0,'Win64 nonvolatile/stack ABI probe failed');rc=job.status
        C.check(rc==job.status and 0<=rc<=9,'Status/return mismatch')
        C.check(job.consumed<=len(raw) and job.written<=capacity,'Per-call bounds violated')
        C.check(job.total_in==old_in+job.consumed and job.total_out==old_out+job.written,'Per-call cumulative counters disagree')
        C.check(state.q(40)==job.total_in and state.q(48)==job.total_out,'Published state/job cumulative counters disagree')
        C.check(state.q(40)*8-state.q(56)==state.d(32) and state.d(32)<=23,'Persistent bit-cache accounting disagrees')
        C.check(state.d(64)==job.total_out%32768 and state.d(68)==min(job.total_out,32768),'Persistent history accounting disagrees')
        C.check(source.raw==before,'Decoder changed offered input')
        C.check(target.raw[:16]==b'\xc5'*16 and target.raw[16+capacity:32+capacity]==b'\xc5'*16,'Decoder overwrote output guards')
        state.guard();out=target.raw[16:16+job.written]
        # The next call cannot depend on either previous input or output.
        ctypes.memset(ctypes.addressof(source)+16,0xde,len(raw));ctypes.memset(ctypes.addressof(target)+16,0xe9,capacity)
        return job,out


def fixtures():
    good,bad,rfc=T.fixtures();rng=random.Random(32768);prefix=bytes(rng.randrange(256) for _ in range(32768))
    b=T.Bits();T.stored(b,prefix,False);lit,dist=T.fixed_header(b)
    output=bytearray(prefix)
    for _ in range(260):
        b.code(lit,285);b.code(dist,29);b.put(8191,13)
        for _ in range(258):output.append(output[-32768])
    b.code(lit,256);good.append(T.case('stored-to-fixed-history-multiple-wraps',b.raw(),bytes(output),position=len(b.values)))
    b=T.Bits();lit,dist=T.fixed_header(b,False)
    for value in prefix:b.code(lit,value)
    b.code(lit,256);lengths=[0]*286;lengths[256]=lengths[285]=1;distances=[0]*30;distances[29]=1
    lit,dist=T.dynamic_header(b,lengths,distances);b.code(lit,285);b.code(dist,29);b.put(8191,13);b.code(lit,256)
    good.append(T.case('fixed-to-dynamic-32768-history',b.raw(),prefix+prefix[:258],position=len(b.values)))
    return good,bad,rfc


SCHEDULES=[((1,),(1,)),((2,),(7,)),((7,),(2,)),((512,),(512,)),((0,1,0,2,7,512),(0,1,0,7,2,512)),((7,1,512,2),(1,0,512,7,0,2))]


def drive(native,row,inputs,outputs,tail=b'',cut=None,state=None,prefix=b'',start=0,final=True):
    state=state or State(native);raw=row['raw']+tail;pos=start;result=bytearray(prefix);calls=0;statuses={};phases=set();partial_codes=0
    limit=30*(len(raw)+len(row['output'] or b'')+1)+300
    while calls<limit:
        if cut is None:n=min(inputs[calls%len(inputs)],len(raw)-pos)
        else:n=(cut if calls==0 else cut-pos if pos<cut else len(raw)-pos)
        cap=outputs[calls%len(outputs)]
        job,out=native.step(state,raw[pos:pos+n],cap,final and pos+n==len(raw))
        pos+=job.consumed;result.extend(out);calls+=1
        statuses[job.status]=statuses.get(job.status,0)+1;phases.add(state.d(12));partial_codes+=int(state.d(120)!=0)
        if job.status==0 or job.status>=3:break
        C.check(job.status in (1,2),'Unexpected continuation status')
        if not final and pos==len(raw) and job.status==1:break
    C.check(calls<limit,'Streaming progress stalled: '+row['name'])
    if row['output'] is not None:
        C.check(job.status==0 and bytes(result)==row['output'] and pos==len(row['raw']),'Streaming success/output/consumption mismatch: '+row['name']+' status='+str(job.status)+' pos='+str(pos))
        if row['position'] is not None:C.check(state.q(56)==row['position'],'Streaming exact final bit position mismatch')
    else:
        expected={2:4,4:5,5:6,6:7,7:8}[row['status']]
        C.check(job.status==expected,'Streaming malformed status mismatch: '+row['name']+' '+str(job.status))
    return dict(calls=calls,statuses=statuses,phases=sorted(phases),partial_Huffman_suspensions=partial_codes,input_used=pos,output_used=len(result)),state


def python_stream(row,ins,outs):
    raw=row['raw']+b'PY-TRAIL';decoder=zlib.decompressobj(-15);pos=0;out=bytearray();calls=0
    while calls<30*(len(raw)+len(row['output'])+1)+300:
        n=min(ins[calls%len(ins)],len(raw)-pos);cap=outs[calls%len(outs)];calls+=1
        # Python max_length=0 means unlimited, unlike a native zero-capacity
        # call. Exercise that scheduling gap without mapping it incorrectly.
        if cap==0:continue
        offered=raw[pos:pos+n];part=decoder.decompress(offered,cap);out.extend(part)
        pos+=len(offered)-max(len(decoder.unconsumed_tail),len(decoder.unused_data))
        if decoder.eof:break
    C.check(decoder.eof and out==row['output'] and pos==len(row['raw']),'Python incremental oracle mismatch: '+row['name'])
    return calls


def sticky_and_reset(native,good,bad):
    calls=0
    for row in (good[0],good[-1],bad[0],bad[-1]):
        _,state=drive(native,row,(1,),(7,));before=state.bytes()
        job,out=native.step(state,b'new-unused-input',20,False);calls+=1
        expected=0 if row['output'] is not None else {2:4,4:5,5:6,6:7,7:8}[row['status']]
        C.check(job.status==expected and job.consumed==job.written==0 and not out and state.bytes()==before,'Finished/error state was not sticky')
        C.check(native.reset(state.address,STATE_BYTES)==0,'Reset after terminal state failed');state.guard()
        fresh=State(native);C.check(state.bytes()==fresh.bytes(),'Reset did not completely clear tables/history/counters')
        drive(native,good[1],(1,),(1,),state=state);calls+=1
    state=State(native);before=state.bytes();job,_=native.step(state,b'',0)
    C.check(job.status==1 and state.bytes()==before,'Empty input/output should request input without changing a fresh state');calls+=1
    # EOF remains published across an output-full pause; no new input can be
    # silently appended after the caller marked an entirely consumed chunk.
    row=good[4];state=State(native);job,_=native.step(state,row['raw'],0,True)
    C.check(job.status==2 and job.consumed>0,'Zero output must preserve a pending literal/match');calls+=1
    before=state.bytes();again,_=native.step(state,b'unused-during-output-pause',0)
    C.check(again.status==2 and again.consumed==again.written==0 and state.bytes()==before,'Output pause consumed more input without capacity');calls+=1
    eof_pause_found=False
    for row in good:
        if not row['output']:continue
        state=State(native);job,out=native.step(state,row['raw'],len(row['output'])-1,True);calls+=1
        if job.status==2 and job.consumed==len(row['raw']):
            eof_pause_found=True;C.check(state.d(136)==1,'Entirely consumed END_INPUT was not retained')
            before=state.bytes();source=ctypes.create_string_buffer(b'extra');target=ctypes.create_string_buffer(8)
            invalid=Job(state.address,ctypes.addressof(source),5,ctypes.addressof(target),8)
            C.check(native.fn(ctypes.byref(invalid))==3 and state.bytes()==before,'New input after remembered EOF altered state');calls+=1
            _,state=drive(native,row,(0,),(7,),state=state,prefix=out,start=job.consumed);calls+=1;break
    C.check(eof_pause_found,'Fixture must actually exercise remembered EOF across output-full')
    return calls


def relocated_checkpoint(native,row):
    original=State(native);job,prefix=native.step(original,row['raw'],32769,True)
    C.check(job.status==2 and original.d(12)==14 and original.d(68)==32768,'Checkpoint fixture must suspend a match after filling history')
    snapshot=original.bytes();moved=State(native,snapshot)
    left,_=drive(native,row,(1,),(1,),state=original,prefix=prefix,start=job.consumed)
    right,_=drive(native,row,(7,2,512),(0,1,512),state=moved,prefix=prefix,start=job.consumed)
    C.check(original.bytes()==moved.bytes(),'Relocated opaque state retained an IO/state-relative pointer or changed semantics')
    return dict(checkpoint_phase=14,history_valid=32768,source_consumed=job.consumed,output_written=job.written,
        copied_state_bytes=STATE_BYTES,first_suffix_calls=left['calls'],second_suffix_calls=right['calls'],identical_final_state=True)


def truncations(native,good):
    calls=0
    for row in good:
        cuts={0,len(row['raw'])//2,len(row['raw'])-1}
        if len(row['raw'])<=160:cuts.update(range(len(row['raw'])))
        for n in cuts:
            state=State(native);pos=0;steps=0
            while steps<10*(len(row['output'])+len(row['raw'])+1)+100:
                chunk=row['raw'][pos:min(pos+2,n)];job,_=native.step(state,chunk,7,pos+len(chunk)==n)
                pos+=job.consumed;steps+=1
                if job.status>=3:break
                C.check(job.status in (1,2),'Truncated prefix incorrectly finished')
            C.check(job.status==4 and pos==n,'END_INPUT did not report precise bounded truncation: '+row['name']);calls+=steps
            before=state.bytes();again,_=native.step(state,b'cannot-repair-sticky-error',4)
            C.check(again.status==4 and state.bytes()==before,'Truncation must stay sticky until reset');calls+=1
    return calls


def arguments(native):
    state=State(native);initial=state.bytes();source=ctypes.create_string_buffer(64);p=ctypes.addressof(source);count=0
    C.check(native.fn(None)==3 and native.reset(None,STATE_BYTES)==3,'NULL state/job validation failed');count+=2
    for size in (0,STATE_BYTES-1,STATE_BYTES+1):
        C.check(native.reset(state.address,size)==3 and state.bytes()==initial,'Invalid reset size altered state');count+=1
    for job in [Job(state.address,0,1,p,8),Job(state.address,p,1,0,1),Job(state.address,p,1,p+8,8,2),
                Job(state.address,p,1<<61,p+8,8),Job(state.address,(1<<64)-2,4,p,8),Job(state.address,p,4,(1<<64)-2,4),
                Job(state.address,p,16,p+8,16),Job(state.address,state.address+1500,8,p,8),Job(state.address,p,8,state.address+1500,8)]:
        C.check(native.fn(ctypes.byref(job))==3 and state.bytes()==initial,'Invalid streaming ranges changed valid state');count+=1
    # A Job inside opaque State is rejected without publishing into it.
    alias=Job.from_address(state.address+160);alias.state=state.address;before=state.bytes()
    C.check(native.fn(ctypes.byref(alias))==3 and state.bytes()==before,'State-aliasing Job must be rejected without writing it');count+=1
    for at,value in [(0,0),(8,STATE_BYTES-1),(12,17),(20,2),(24,1),(32,24),(56,1),(64,1),(68,1),(120,16),(136,2)]:
        state=State(native);ctypes.c_uint32.from_address(state.address+at).value=value;before=state.bytes()
        job=Job(state.address,p,0,p+8,0);C.check(native.fn(ctypes.byref(job))==9 and state.bytes()==before,'Invalid opaque-state header not rejected read-only: '+str(at));count+=1
    return count


def random_inputs(native,count):
    rng=random.Random(0x534652);finished=0;bounded=0;invalid=0;calls=0
    for _ in range(count):
        raw=bytes(rng.randrange(256) for _ in range(rng.randrange(97)));state=State(native);pos=0;out=bytearray()
        for i in range(50000):
            cap=min((1,7,32)[i%3],4096-len(out));chunk=raw[pos:pos+(1,2,7)[i%3]]
            job,part=native.step(state,chunk,cap,pos+len(chunk)==len(raw));pos+=job.consumed;out.extend(part);calls+=1
            if job.status==0 or job.status>=3 or (job.status==2 and len(out)==4096):break
        C.check(i<49999,'Random fragment progress stalled')
        ref=zlib.decompressobj(-15)
        try:
            expected=ref.decompress(raw,4097)
            if ref.eof and len(expected)<=4096:
                C.check(job.status==0 and out==expected and pos==len(raw)-len(ref.unused_data),'Complete random incremental differential mismatch');finished+=1
            elif job.status==0:raise ValueError('Streaming ASM accepted unfinished/oversized random input')
            elif job.status==2:bounded+=1
            else:invalid+=1
        except zlib.error:
            C.check(job.status!=0,'Streaming ASM accepted random input rejected by zlib');invalid+=1
    return dict(inputs=count,step_calls=calls,complete=finished,invalid=invalid,output_limited=bounded)


def guard_pages(native,good,bad):
    calls=0
    for row in [good[0],good[4],good[-4],good[-1],bad[0],bad[-1]]:
        for at_end in (False,True):
            state=State(native);pos=0;written=bytearray();limit=10*(len(row['raw'])+len(row['output'] or b'')+1)+300
            for i in range(limit):
                raw=row['raw'][pos:pos+1];cap=7 if i%3 else 0
                with T.guard_buffer(raw,len(raw),True) as src,T.guard_buffer(b'',cap,False,at_end) as dst:
                    job=Job(state.address,src,len(raw),dst,cap,int(pos+len(raw)==len(row['raw'])))
                    rc=native.fn(ctypes.byref(job));C.check(rc==job.status and job.consumed<=len(raw) and job.written<=cap,'Guarded streaming bounds failed')
                    pos+=job.consumed;written.extend(ctypes.string_at(dst,job.written));calls+=1;state.guard()
                if rc==0 or rc>=3:break
            if row['output'] is not None:C.check(rc==0 and written==row['output'],'Guarded streaming output mismatch')
            else:C.check(rc=={2:4,4:5,5:6,6:7,7:8}[row['status']],'Guarded malformed stream mismatch')
    # Put the complete fixed state itself against each guard boundary.
    for end in (False,True):
        with T.guard_buffer(b'',STATE_BYTES,False,end) as state_ptr:
            C.check(native.reset(state_ptr,STATE_BYTES)==0,'Guarded reset failed')
            row=good[-1];src=ctypes.create_string_buffer(row['raw']);out=ctypes.create_string_buffer(len(row['output']))
            job=Job(state_ptr,ctypes.addressof(src),len(row['raw']),ctypes.addressof(out),len(row['output']),1)
            C.check(native.fn(ctypes.byref(job))==0 and out.raw==row['output'],'Guarded full-state decode failed');calls+=1
    return calls


def abi_assembly():
    registers=['rbx','rsi','rdi','rbp','r12','r13','r14','r15'];values=[0x2132435465768700+i for i in range(8)]
    lines=['option casemap:none','EXTERN boom_deflate_stream_step:PROC','EXTERN boom_deflate_stream_reset:PROC',
        '.const','boom_ds_abi_pattern BYTE 16 DUP(0B6h)','.code']
    for kind in ('step','reset'):
        name='boom_ds_'+kind+'_abi';lines.extend(['PUBLIC '+name,name+' PROC FRAME'])
        for reg in registers:lines.extend(['push '+reg,'.pushreg '+reg])
        lines.extend(['sub rsp,248','.allocstack 248'])
        for i in range(10):lines.extend([f'movdqu XMMWORD PTR [rsp+{64+i*16}],xmm{6+i}',f'.savexmm128 xmm{6+i},{64+i*16}'])
        lines.extend(['.endprolog','mov rax,0123456789ABCDEFh','mov QWORD PTR [rsp+32],rax',
            'mov rax,076543210FEDCBA98h','mov QWORD PTR [rsp+40],rax','mov QWORD PTR [rsp+48],rsp'])
        for reg,value in zip(registers,values):lines.append(f'mov {reg},0{value:X}h')
        lines.append('movdqu xmm0,XMMWORD PTR boom_ds_abi_pattern')
        for i in range(6,16):lines.append(f'movdqa xmm{i},xmm0')
        lines.extend(['call boom_deflate_stream_'+kind,'xor eax,eax'])
        for i,(reg,value) in enumerate(zip(registers,values)):
            label=kind+'_ok'+str(i);lines.extend([f'mov r10,0{value:X}h',f'cmp {reg},r10','je '+label,f'or eax,{1<<i}',label+':'])
        lines.extend(['cmp rsp,QWORD PTR [rsp+48]','je '+kind+'_ok8','or eax,256',kind+'_ok8:'])
        for i,value in enumerate((0x0123456789abcdef,0x76543210fedcba98),9):
            label=kind+'_ok'+str(i);lines.extend([f'mov r10,0{value:X}h',f'cmp QWORD PTR [rsp+{32+(i-9)*8}],r10','je '+label,f'or eax,{1<<i}',label+':'])
        lines.append('movdqu xmm0,XMMWORD PTR boom_ds_abi_pattern')
        for i in range(6,16):
            label=kind+'_xmm'+str(i);lines.extend([f'movdqa xmm1,xmm{i}','pcmpeqb xmm1,xmm0','pmovmskb edx,xmm1','cmp edx,65535','je '+label,f'or eax,{1<<(i+5)}',label+':'])
        for i in range(10):lines.append(f'movdqu xmm{6+i},XMMWORD PTR [rsp+{64+i*16}]')
        lines.append('add rsp,248')
        for reg in reversed(registers):lines.append('pop '+reg)
        lines.extend(['ret',name+' ENDP'])
    return '\n'.join(lines+['END'])+'\n'


def abi_fixture(output,candidate,good,bad):
    output.mkdir();source,obj,dll,rsp=(output/n for n in ('abi.asm','abi.obj','abi.dll','link.rsp'))
    source.write_text(abi_assembly(),encoding='utf-8',newline='\n');assembler,linker=(C.checked(candidate[n]) for n in ('assembler','linker'))
    with (output/'assembler.log').open('xb') as log:run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0,'Streaming ABI assembly failed')
    args=['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO',
        '/OUT:"'+str(dll)+'"','/EXPORT:boom_ds_reset_abi','/EXPORT:boom_ds_step_abi','"'+str(C.checked(candidate['object']))+'"','"'+str(obj)+'"']
    rsp.write_text('\n'.join(args)+'\n',encoding='utf-8',newline='\n')
    with (output/'linker.log').open('xb') as log:run=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0,'Streaming ABI LINK failed')
    image=ctypes.CDLL(str(dll));probe=image.boom_ds_step_abi;reset=image.boom_ds_reset_abi
    probe.argtypes=[ctypes.POINTER(Job)];probe.restype=ctypes.c_uint32;reset.argtypes=[ctypes.c_void_p,ctypes.c_uint32];reset.restype=ctypes.c_uint32
    # Native constructor binds the canonical two kernel symbols, which are
    # deliberately not exported by this test-only observer DLL.
    native=Native.__new__(Native);native.dll=image;native.fn=probe;native.reset=reset;native.abi=True
    calls=0;resets=0
    for row in good+bad:
        obs,_=drive(native,row,(1,2,7),(0,1,7,512));calls+=obs['calls'];resets+=1
    state=State(native);resets+=1;before=state.bytes()
    C.check(reset(state.address,STATE_BYTES-1)==0 and state.bytes()==before,'Reset ABI observer or invalid-size preservation failed');resets+=1
    result=dict(verified=True,step_calls=calls,reset_calls=resets,nonvolatile_GPR=['rbx','rsi','rdi','rbp','r12','r13','r14','r15'],nonvolatile_XMM=list(range(6,16)),
        stack_pointer_and_two_canaries=True,source=C.artifact(source),object=C.artifact(obj),image=C.artifact(dll),response=C.artifact(rsp),
        kernel_object=C.artifact(candidate['object']['path']),assembler=C.artifact(assembler),linker=C.artifact(linker),scope='test_only_ABI_observer_exact_original_streaming_COFF')
    C.write(output/'verification.json',result);return C.artifact(output/'verification.json')


ORACLE=r'''import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;
public class DeflateStreamOracle {
 public static void main(String[] args) throws Exception {
  int cases=0;long calls=0;
  int[][][] schedules={{{1},{1}},{{2},{7}},{{7},{2}},{{512},{512}},{{0,1,0,2,7,512},{0,1,0,7,2,512}},{{7,1,512,2},{1,0,512,7,0,2}}};
  for(String line:Files.readAllLines(Path.of(args[0]))) {
   String[] p=line.split("\t");byte[] raw=Files.readAllBytes(Path.of(p[1]));
   for(int[][] schedule:schedules) {
    Inflater f=new Inflater(true);MessageDigest sha=MessageDigest.getInstance("SHA-256");int offered=0,step=0;long written=0;boolean invalid=false;
    try {
     try {
      while(!f.finished()) {
       int cap=schedule[1][step%schedule[1].length];
       if(f.needsInput()) {int n=Math.min(schedule[0][step%schedule[0].length],raw.length-offered);f.setInput(raw,offered,n);offered+=n;}
       long oldIn=f.getBytesRead(),oldOut=f.getBytesWritten();int available=f.getRemaining();byte[] dst=new byte[cap];int n=f.inflate(dst);
       if(f.getBytesRead()-oldIn<0 || f.getBytesRead()-oldIn>available || f.getBytesWritten()-oldOut!=n || n>cap) throw new AssertionError("counters "+p[0]);
       sha.update(dst,0,n);written+=n;step++;calls++;
       if(written>262144 || step>10000000) throw new AssertionError("bound "+p[0]);
       if(f.needsInput() && offered==raw.length && !f.finished()) break;
      }
     } catch(DataFormatException e) {invalid=true;}
     if(p[2].equals("ok")) {
      if(invalid || !f.finished() || written!=Long.parseLong(p[3]) || f.getBytesRead()!=Long.parseLong(p[5]) ||
       f.getRemaining()!=offered-f.getBytesRead() || !HexFormat.of().formatHex(sha.digest()).equals(p[4])) throw new AssertionError("stream mismatch "+p[0]);
     } else if(!invalid && f.finished()) throw new AssertionError("accepted invalid "+p[0]);
     cases++;
    } finally {f.end();}
   }
  }
  System.out.println("raw_stream_JDK_cases="+cases+" calls="+calls);
 }
}
'''


def oracle(output,good,bad,rfc):
    output.mkdir();source=output/'DeflateStreamOracle.java';source.write_text(ORACLE,encoding='utf-8',newline='\n')
    tools=[C.artifact(T.JAVA/n) for n in ('bin/java.exe','bin/javac.exe','bin/server/jvm.dll','lib/modules','lib/src.zip')];lines=[];files=[]
    for row in good+bad+[rfc]:
        path=output/(row['name']+'.bin');path.write_bytes(row['raw']+(b'JDK-TRAIL' if row['output'] is not None else b''));files.append(C.artifact(path))
        valid=row['output'] is not None and row['oracle']
        lines.append('\t'.join([row['name'],str(path),'ok' if valid else 'reject',str(len(row['output'] or b'')),hashlib.sha256(row['output'] or b'').hexdigest(),str(len(row['raw']))]))
    manifest=output/'cases.tsv';manifest.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    with (output/'javac.log').open('xb') as log:run=subprocess.run([str(T.JAVA/'bin/javac.exe'),'-d',str(output),str(source)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0,'JDK incremental oracle compilation failed')
    with (output/'java.log').open('xb') as log:run=subprocess.run([str(T.JAVA/'bin/java.exe'),'-cp',str(output),'DeflateStreamOracle',str(manifest)],stdout=log,stderr=subprocess.STDOUT)
    text=(output/'java.log').read_text();expected=len(lines)*len(SCHEDULES)
    C.check(run.returncode==0 and text.startswith('raw_stream_JDK_cases='+str(expected)+' calls='),'JDK incremental oracle failed; retain java.log')
    C.check(tools==[C.artifact(t['path']) for t in tools],'JDK oracle tools changed')
    result=dict(verified=True,scope='JDK_reference_only_incremental_raw_Inflater_true',cases=expected,source=C.artifact(source),class_file=C.artifact(output/'DeflateStreamOracle.class'),
        manifest=C.artifact(manifest),inputs=files,tools=tools,stdout=C.artifact(output/'java.log'),RFC_HDIST32_count_difference_separate=True,delivery_uses_JVM=False)
    C.write(output/'verification.json',result);return C.artifact(output/'verification.json')


def run(candidate,output,rounds,one_shot_candidate,fuzz_cases):
    output=Path(output).resolve();C.check(output.is_relative_to(C.ART) and not output.exists(),'Fresh isolated stream execution output required');output.mkdir(parents=True)
    candidate=Path(candidate).resolve();record=json.loads(candidate.read_text(encoding='utf-8'));before=C.artifact(candidate);sourcepins=C.sources()
    harnesses=[C.artifact(__file__),C.artifact(ROOT/'scripts/test-deflate-raw.py')]
    C.write(output/'machine-verification.json',C.verify(candidate))
    old=Path(one_shot_candidate).resolve();C.write(output/'one-shot-machine-verification.json',T.C.verify(old));oldrow=json.loads(old.read_text(encoding='utf-8'))
    old_native=T.Native(T.C.checked(oldrow['image']));native=Native(C.checked(record['image']));good,bad,rfc=fixtures()
    observations=[];calls=0;phase_set=set();partial=0;python_calls=0
    for row in good:
        T.success(old_native,row,b'ONE-SHOT-TRAIL')
        for index,(ins,outs) in enumerate(SCHEDULES):
            obs,_=drive(native,row,ins,outs,tail=b'NATIVE-TAIL');calls+=obs['calls'];phase_set.update(obs['phases']);partial+=obs['partial_Huffman_suspensions']
            python_calls+=python_stream(row,ins,outs);observations.append(dict(name=row['name'],schedule=index,**obs))
    drive(native,rfc,(1,),(1,),tail=b'RFC-TRAIL')
    malformed_calls=0
    for row in bad:
        for ins,outs in SCHEDULES:
            obs,_=drive(native,row,ins,outs);malformed_calls+=obs['calls']
    cuts=0;cut_calls=0
    for row in good:
        if len(row['raw'])<=160:
            for at in range(len(row['raw'])+1):
                obs,_=drive(native,row,(512,),(max(1,len(row['output'])),),cut=at,tail=b'CUT-TAIL')
                cuts+=1;cut_calls+=obs['calls']
    sticky=sticky_and_reset(native,good,bad);checkpoint=relocated_checkpoint(native,good[-2]);truncated_calls=truncations(native,good);invalid=arguments(native);guards=guard_pages(native,good,bad)
    fuzz=random_inputs(native,fuzz_cases)
    small=[r for r in good if len(r['output'])<=256];barrier=threading.Barrier(8)
    def worker(index):
        ident=threading.get_native_id();barrier.wait();n=0
        for i in range(rounds):
            row=small[(index+i*3)%len(small)];ins,outs=SCHEDULES[(index+i)%len(SCHEDULES)];obs,_=drive(native,row,ins,outs,tail=b'OS-TAIL');n+=obs['calls']
        obs,_=drive(native,good[-2],(7,2,512),(1,0,512,7),tail=b'OS-HISTORY-TAIL');n+=obs['calls']
        return dict(thread=ident,streams=rounds+1,calls=n)
    with ThreadPoolExecutor(max_workers=8) as pool:threads=list(pool.map(worker,range(8)))
    C.check(len({r['thread'] for r in threads})==8,'Eight actual OS worker identities required')
    abi=abi_fixture(output/'ABI-probe',record,good,bad)
    jdk=oracle(output/'jdk-oracle',good,bad,rfc)
    C.check(before==C.artifact(candidate) and C.sources()==sourcepins and harnesses==[C.artifact(r['path']) for r in harnesses],'Stream execution source/input pins changed')
    for n in ('assembly','object','image','response','assembler','linker'):C.checked(record[n])
    result=dict(verified=True,scope='unregistered_incremental_raw_DEFLATE_actual_ASM_only',candidate=before,harnesses=harnesses,sources=sourcepins,
        machine_verification=C.artifact(output/'machine-verification.json'),one_shot_machine_verification=C.artifact(output/'one-shot-machine-verification.json'),jdk_reference=jdk,native_ABI_probe=abi,
        valid_streams=len(good),fragment_schedules=SCHEDULES,successful_stream_runs=len(good)*len(SCHEDULES),successful_step_calls=calls,observations=observations,
        all_byte_cuts=cuts,byte_cut_step_calls=cut_calls,partial_Huffman_suspensions=partial,continuation_phases=sorted(phase_set),malformed_streams=len(bad),malformed_step_calls=malformed_calls,
        truncation_step_calls=truncated_calls,guard_page_calls=guards,reset_sticky_calls=sticky,relocated_checkpoint=checkpoint,random_fragment_inputs=fuzz,invalid_argument_calls=invalid,OS_workers=threads,python_reference_step_calls=python_calls,
        previous_input_and_output_poisoned_after_each_call=True,fixed_state_bytes=STATE_BYTES,history_bytes=32768,redecode_history=False,
        no_decoder_imports=True,no_mutable_globals=True,registered=False,inflater_compatible=False,zlib_wrapper=False,gzip_wrapper=False,preset_dictionary=False,Adler=False,JNI=False,game_started=False)
    C.write(output/'execution.json',result);return output/'execution.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--one-shot-candidate',type=Path,default=ROOT/'.boom/deflate-raw/source-c/candidate.json');p.add_argument('--thread-rounds',type=int,default=64);p.add_argument('--fuzz-cases',type=int,default=2000);a=p.parse_args()
    C.check(1<=a.thread_rounds<=512 and 0<=a.fuzz_cases<=100000,'Bounded test counts required');print(run(a.candidate,a.output,a.thread_rounds,a.one_shot_candidate,a.fuzz_cases))
