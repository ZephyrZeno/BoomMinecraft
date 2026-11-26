"""Actual one-shot ASM raw-DEFLATE differential, malformed-input and bounds probes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import threading
import zlib

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('deflate_candidate',ROOT/'scripts/deflate-raw-candidate.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
JAVA=Path('D:/Dev/Java/jdk-21')


class Job(ctypes.Structure):
    _fields_=[('src',ctypes.c_void_p),('length',ctypes.c_uint64),('dst',ctypes.c_void_p),('capacity',ctypes.c_uint64),
              ('consumed',ctypes.c_uint64),('written',ctypes.c_uint64),('last_bits',ctypes.c_uint32),('status',ctypes.c_uint32),('bit_position',ctypes.c_uint64)]


class Bits:
    def __init__(self):self.values=[]
    def put(self,value,width):
        C.check(0<=value<1<<width,'Fixture bit value out of range')
        self.values.extend((value>>i)&1 for i in range(width))
    def align(self):
        while len(self.values)%8:self.put(0,1)
    def raw(self):
        result=bytearray((len(self.values)+7)//8)
        for i,bit in enumerate(self.values):result[i//8]|=bit<<(i%8)
        return bytes(result)
    def code(self,table,symbol):
        value,width=table[symbol]
        for i in range(width-1,-1,-1):self.put((value>>i)&1,1)


def codes(lengths):
    count=[lengths.count(i) for i in range(16)];count[0]=0
    next_code=[0]*16
    for i in range(1,16):next_code[i]=(next_code[i-1]+count[i-1])*2
    result={}
    for symbol,width in enumerate(lengths):
        if width:
            result[symbol]=(next_code[width],width);next_code[width]+=1
    return result


FIXED=[8]*144+[9]*112+[7]*24+[8]*8
LENGTH_BASE=[3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258]
LENGTH_BITS=[0]*8+[1]*4+[2]*4+[3]*4+[4]*4+[5]*4+[0]
DISTANCE_BASE=[1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577]
DISTANCE_BITS=[0]*4+[v for v in range(1,14) for _ in range(2)]
CL_ORDER=[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15]


def fixed_header(bits,final=True):
    bits.put(int(final),1);bits.put(1,2)
    return codes(FIXED),codes([5]*32)


def stored(bits,payload,final=True):
    bits.put(int(final),1);bits.put(0,2);bits.align()
    bits.put(len(payload),16);bits.put(len(payload)^65535,16)
    for b in payload:bits.put(b,8)


def dynamic_header(bits,lit,dist,cl=None,tokens=None):
    C.check(257<=len(lit)<=286 and 1<=len(dist)<=32,'Dynamic fixture shape')
    if cl is None:cl=[4]*16+[0]*3
    hclen=max(4,max(i+1 for i,s in enumerate(CL_ORDER) if cl[s]))
    bits.put(1,1);bits.put(2,2);bits.put(len(lit)-257,5);bits.put(len(dist)-1,5);bits.put(hclen-4,4)
    for symbol in CL_ORDER[:hclen]:bits.put(cl[symbol],3)
    clcodes=codes(cl)
    if tokens is None:
        for v in lit+dist:bits.code(clcodes,v)
    else:
        for symbol,value,width in tokens:
            bits.code(clcodes,symbol)
            if width:bits.put(value,width)
    return codes(lit),codes(dist)


def case(name,raw,output=None,status=0,position=None,oracle=True):
    return dict(name=name,raw=raw,output=output,status=status,position=position,oracle=oracle)


def fixtures():
    rng=random.Random(1951);good=[];bad=[]
    samples=[b'',b'A',bytes(range(256)),b'ABCD'*2000,bytes(rng.randrange(256) for _ in range(9000)),b'Z'*100000]
    for i,payload in enumerate(samples):
        for name,level,strategy in [('stored',0,0),('fixed',6,zlib.Z_FIXED),('auto',6,0)]:
            compressor=zlib.compressobj(level,zlib.DEFLATED,-15,8,strategy)
            raw=compressor.compress(payload)+compressor.flush()
            good.append(case(f'zlib-{name}-{i}',raw,payload))
    for i in range(40):
        size=rng.randrange(0,20000)
        if i%3==0:payload=bytes(rng.randrange(256) for _ in range(size))
        elif i%3==1:payload=bytes(rng.randrange(8) for _ in range(size))
        else:
            pattern=bytes(rng.randrange(256) for _ in range(rng.randrange(1,100)));payload=(pattern*(size//len(pattern)+1))[:size]
        co=zlib.compressobj(rng.randrange(1,10),zlib.DEFLATED,-15)
        good.append(case(f'zlib-varied-{i}',co.compress(payload)+co.flush(),payload))
    b=Bits();stored(b,b'one',False);f,d=fixed_header(b,False)
    for value in b'two':b.code(f,value)
    b.code(f,256);stored(b,b'three');good.append(case('mixed-unaligned-blocks',b.raw(),b'onetwothree',position=len(b.values)))
    co=zlib.compressobj(wbits=-15);raw=co.compress(b'flush'*600)+co.flush(zlib.Z_SYNC_FLUSH)+co.compress(b'end'*400)+co.flush()
    good.append(case('zlib-sync-flush-multiblock',raw,b'flush'*600+b'end'*400))
    # The last-byte unused padding is arbitrary and never consumes later bytes.
    b=Bits();f,d=fixed_header(b);b.code(f,256)
    good.append(case('fixed-empty-padding',b.raw()[:-1]+bytes([b.raw()[-1]|0xfc]),b'',position=10))
    # Exactly 32KiB back distance, all 29 length codes and all 30 distances,
    # both extra-bit extremes and overlapping distance-one matches.
    b=Bits();f,d=fixed_header(b);output=bytearray(bytes(range(256))*128)
    for value in output:b.code(f,value)
    for li,(base,width) in enumerate(zip(LENGTH_BASE,LENGTH_BITS)):
        extra=(1<<width)-1;b.code(f,257+li);b.put(extra,width);b.code(d,29);b.put(8191,13)
        for _ in range(base+extra):output.append(output[-32768])
    for di,(base,width) in enumerate(zip(DISTANCE_BASE,DISTANCE_BITS)):
        for extra in {0,(1<<width)-1}:
            b.code(f,285);b.code(d,di);b.put(extra,width)
            for _ in range(258):output.append(output[-base-extra])
    b.code(f,256);good.append(case('all-length-distance-32KiB',b.raw(),bytes(output),position=len(b.values)))
    for empty_distance in (True,False):
        lit=[0]*257;lit[65]=lit[256]=1;dist=[0 if empty_distance else 1]
        b=Bits();l,d=dynamic_header(b,lit,dist)
        for _ in range(7):b.code(l,65)
        b.code(l,256);good.append(case(f'dynamic-single-distance-{empty_distance}',b.raw(),b'A'*7,position=len(b.values)))
    lit=[0]*258;lit[65]=1;lit[256]=lit[257]=2;b=Bits();l,d=dynamic_header(b,lit,[1]);b.code(l,65);b.code(l,257);b.code(d,0);b.code(l,256)
    good.append(case('dynamic-single-distance-overlap',b.raw(),b'AAAA',position=len(b.values)))
    lit=[0]*257;lit[256]=1;cl=[0]*19
    for s in (0,1,16):cl[s]=2
    cl[17]=cl[18]=3
    tokens=[(0,0,0),(16,3,2),(17,7,3),(18,127,7),(18,90,7),(1,0,0),(0,0,0)]
    b=Bits();l,d=dynamic_header(b,lit,[0],cl,tokens);b.code(l,256)
    good.append(case('dynamic-all-repeats-including-zero16',b.raw(),b'',position=len(b.values)))
    # Complete comb-shaped trees exercise the maximum 15-bit data codes,
    # and a separate maximum 7-bit code-length tree.
    lit=[0]*257
    for i in range(14):lit[i]=i+1
    lit[14]=lit[256]=15;b=Bits();l,d=dynamic_header(b,lit,[0])
    for value in range(15):b.code(l,value)
    b.code(l,256);good.append(case('literal-max15-tree',b.raw(),bytes(range(15)),position=len(b.values)))
    lit=[0]*286;lit[65]=1;lit[256]=lit[285]=2;dist=list(range(1,15))+[15,15]
    b=Bits();l,d=dynamic_header(b,lit,dist)
    for _ in range(256):b.code(l,65)
    b.code(l,285);b.code(d,15);b.put(63,6);b.code(l,256)
    good.append(case('distance-max15-tree',b.raw(),b'A'*514,position=len(b.values)))
    lit=[0]*257
    for i in range(6):lit[i]=i+1
    lit[6]=lit[256]=7;cl=list(range(1,7))+[7,7]+[0]*11
    b=Bits();l,d=dynamic_header(b,lit,[0],cl);b.code(l,6);b.code(l,256)
    good.append(case('code-length-max7-tree',b.raw(),b'\x06',position=len(b.values)))
    # RFC1951 explicitly gives HDIST 1..32; codes30/31 are never decoded.
    # zlib/JDK reject the declared count>30 early. Keep this documented
    # RFC-vs-zlib policy case separate from the common differential contract.
    lit=[0]*257;lit[256]=1;b=Bits();l,d=dynamic_header(b,lit,[0]*32);b.code(l,256)
    rfc_only=case('RFC-HDIST32-unused-reserved',b.raw(),b'',position=len(b.values),oracle=False)
    bad.append(case('reserved-block',b'\x07',status=4))
    bad.append(case('stored-bad-complement',b'\x01\x01\x00\x00\x00A',status=4))
    bad.append(case('stored-short-payload',b'\x01\x05\x00\xfa\xffA',status=2))
    for symbol in (286,287):
        b=Bits();f,d=fixed_header(b);b.code(f,symbol);bad.append(case(f'reserved-literal-{symbol}',b.raw(),status=6))
    for symbol in (30,31):
        b=Bits();f,d=fixed_header(b);b.code(f,65);b.code(f,257);b.code(d,symbol);bad.append(case(f'reserved-distance-{symbol}',b.raw(),status=6))
    b=Bits();f,d=fixed_header(b);b.code(f,257);b.code(d,0);bad.append(case('backref-before-output',b.raw(),status=7))
    b=Bits();f,d=fixed_header(b);b.code(f,65);b.code(f,257);b.code(d,1);bad.append(case('backref-too-far',b.raw(),status=7))
    for name,cl in [('CL-oversubscribed',[1,1,1]+[0]*16),('CL-incomplete',[1]+[0]*18)]:
        b=Bits();dynamic_header(b,[0]*256+[1],[0],cl,[]);bad.append(case(name,b.raw(),status=5))
    for name,lit,dist in [
        ('literal-oversubscribed',[1,1]+[0]*254+[1],[0]),
        ('literal-incomplete',[2]+[0]*255+[2],[0]),
        ('missing-EOB',[1,1]+[0]*255,[0]),
        ('distance-oversubscribed',[1]+[0]*255+[1],[1,1,1]),
        ('distance-incomplete',[1]+[0]*255+[1],[2])]:
        b=Bits();dynamic_header(b,lit,dist);bad.append(case(name,b.raw(),status=5))
    cl=[0]*19;cl[0]=1;cl[16]=cl[18]=2
    b=Bits();dynamic_header(b,[0]*256+[1],[0],cl,[(16,0,2)]);bad.append(case('repeat16-first',b.raw(),status=6))
    b=Bits();dynamic_header(b,[0]*256+[1],[0],cl,[(18,127,7),(18,127,7)]);bad.append(case('repeat-overrun',b.raw(),status=6))
    lit=[0]*258;lit[65]=1;lit[256]=lit[257]=2;b=Bits();l,d=dynamic_header(b,lit,[0]);b.code(l,65);b.code(l,257)
    bad.append(case('empty-distance-used',b.raw(),status=5))
    for symbol in (30,31):
        dist=[0]*(symbol+1);dist[symbol]=1;b=Bits();l,d=dynamic_header(b,lit,dist)
        b.code(l,65);b.code(l,257);b.code(d,symbol);bad.append(case(f'dynamic-reserved-distance-{symbol}',b.raw(),status=6))
    # Single one-bit trees leave one invalid bit pattern; it must not produce
    # a phantom symbol from uninitialized sorted-table entries.
    lit=[0]*257;lit[256]=1;b=Bits();l,d=dynamic_header(b,lit,[0]);b.put(1,1)
    bad.append(case('single-tree-unused-code',b.raw(),status=5))
    return good,bad,rfc_only


class Native:
    def __init__(self,path):
        self.dll=ctypes.CDLL(str(path));self.fn=self.dll.boom_deflate_raw64
        self.fn.argtypes=[ctypes.POINTER(Job)];self.fn.restype=ctypes.c_uint32
        C.check(ctypes.sizeof(Job)==64 and Job.status.offset==52,'Job64 layout changed')
    def call(self,raw,capacity):
        source=ctypes.create_string_buffer(b'\xa7'*32+raw+b'\xa7'*32)
        target=ctypes.create_string_buffer(b'\xc5'*(capacity+64))
        source_before=source.raw;job=Job(ctypes.addressof(source)+32,len(raw),ctypes.addressof(target)+32,capacity)
        rc=self.fn(ctypes.byref(job))
        C.check(rc==job.status and 0<=rc<=7,'Native status/return disagree')
        C.check(job.written<=capacity and job.consumed<=len(raw) and job.bit_position<=len(raw)*8,'Native progress out of bounds')
        C.check(job.consumed==(job.bit_position+7)//8 and job.last_bits==job.bit_position%8,'Native progress is inconsistent')
        C.check(source.raw==source_before,'Native changed input bytes')
        C.check(target.raw[:32]==b'\xc5'*32 and target.raw[32+capacity:32+capacity+32]==b'\xc5'*32,'Native overwrote buffer guard bytes')
        return job,target.raw[32:32+job.written]


def success(native,row,trailing=b''):
    job,out=native.call(row['raw']+trailing,len(row['output']))
    C.check(job.status==0 and out==row['output'] and job.consumed==len(row['raw']),'Native success/output/consumption failed: '+row['name'])
    if row['position'] is not None:C.check(job.bit_position==row['position'],'Exact bit-position mismatch: '+row['name'])
    return dict(name=row['name'],source_sha256=hashlib.sha256(row['raw']+trailing).hexdigest(),input_bytes=len(row['raw'])+len(trailing),written=job.written,
                consumed=job.consumed,bit_position=job.bit_position,status=job.status)


@contextmanager
def guard_buffer(raw,size,readonly=False,at_end=True):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.VirtualAlloc.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.c_uint32];kernel.VirtualAlloc.restype=ctypes.c_void_p
    kernel.VirtualProtect.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    kernel.VirtualFree.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32]
    usable=max(4096,(size+4095)//4096*4096);total=usable+8192
    base=kernel.VirtualAlloc(None,total,0x3000,4);C.check(base,'VirtualAlloc guard fixture failed')
    try:
        old=ctypes.c_uint32()
        for p in (base,base+4096+usable):C.check(kernel.VirtualProtect(p,4096,1,ctypes.byref(old)),'VirtualProtect guard failed')
        start=base+4096+(usable-size if at_end else 0)
        if raw:ctypes.memmove(start,raw,len(raw))
        if readonly:C.check(kernel.VirtualProtect(base+4096,usable,2,ctypes.byref(old)),'VirtualProtect input readonly failed')
        yield start
    finally:C.check(kernel.VirtualFree(base,0,0x8000),'VirtualFree guard fixture failed')


def bounds(native,good,bad):
    count=0
    for row in [good[0],good[4],good[-5],good[-2],bad[0],bad[7]]:
        capacity=len(row['output']) if row['output'] is not None else 4096
        for end in (False,True):
            with guard_buffer(row['raw'],len(row['raw']),True,True) as source,guard_buffer(b'',capacity,False,end) as target:
                job=Job(source,len(row['raw']),target,capacity);rc=native.fn(ctypes.byref(job))
                C.check(rc==row['status'] and job.written<=capacity,'Guard-page actual decode status mismatch')
                if rc==0:C.check(ctypes.string_at(target,job.written)==row['output'],'Guard-page output mismatch')
                count+=1
    # Every prefix of small streams must terminate as truncated (and never
    # probe the inaccessible byte after the input). Prefix output policy is
    # intentionally our own, rather than zlib's buffer-refill policy.
    for row in [good[0],good[1],good[-3],good[-1]]:
        for n in range(len(row['raw'])):
            with guard_buffer(row['raw'][:n],n,True,True) as source,guard_buffer(b'',4096) as target:
                job=Job(source,n,target,4096);rc=native.fn(ctypes.byref(job))
                C.check(rc==2 and job.consumed<=n,'Valid stream prefix was not bounded truncation: '+row['name'])
                count+=1
    return count


def invalid_arguments(native):
    buffer=ctypes.create_string_buffer(128);p=ctypes.addressof(buffer);count=1
    C.check(native.fn(None)==1,'NULL Job must fail')
    rows=[Job(0,1,p,32),Job(p,1,0,1),Job(p,1<<61,p+64,8),Job((1<<64)-2,4,p,8),Job(p,4,(1<<64)-2,4),Job(p,16,p+8,16)]
    for job in rows:
        C.check(native.fn(ctypes.byref(job))==1 and job.status==1 and job.written==job.consumed==0,'Invalid pointer-range job not rejected before IO');count+=1
    for field in ('src','dst'):
        job=Job(p,4,p+64,8)
        setattr(job,field,ctypes.addressof(job))
        C.check(native.fn(ctypes.byref(job))==1 and job.status==1,'Job/input/output alias not rejected');count+=1
    source=ctypes.create_string_buffer(b'\x03\x00');job=Job(ctypes.addressof(source),2,0,0)
    C.check(native.fn(ctypes.byref(job))==0 and job.status==job.written==0 and job.consumed==2,'NULL zero-capacity output must allow an empty stream');count+=1
    job=Job(0,0,0,0);C.check(native.fn(ctypes.byref(job))==2,'Empty NULL input must return truncated without reading it');count+=1
    return count


def abi_fixture(output,candidate,good,bad):
    """Seed all Win64 nonvolatile GPRs/XMMs and the caller's stack canaries."""
    output.mkdir();registers=['rbx','rsi','rdi','rbp','r12','r13','r14','r15']
    values=[0x1122334455667700+i for i in range(8)]
    lines=['option casemap:none','EXTERN boom_deflate_raw64:PROC','.const','boom_deflate_abi_pattern BYTE 16 DUP(0A5h)',
           '.code','PUBLIC boom_deflate_abi_probe','boom_deflate_abi_probe PROC FRAME']
    for reg in registers:lines.extend(['push '+reg,'.pushreg '+reg])
    lines.extend(['sub rsp,248','.allocstack 248'])
    for i in range(10):lines.extend([f'movdqu XMMWORD PTR [rsp+{64+i*16}],xmm{6+i}',f'.savexmm128 xmm{6+i},{64+i*16}'])
    lines.extend(['.endprolog','mov rax,0123456789ABCDEFh','mov QWORD PTR [rsp+32],rax',
                  'mov rax,076543210FEDCBA98h','mov QWORD PTR [rsp+40],rax','mov QWORD PTR [rsp+48],rsp'])
    for reg,value in zip(registers,values):lines.append(f'mov {reg},0{value:X}h')
    lines.append('movdqu xmm0,XMMWORD PTR boom_deflate_abi_pattern')
    for i in range(6,16):lines.append(f'movdqa xmm{i},xmm0')
    lines.extend(['call boom_deflate_raw64','xor eax,eax'])
    for i,(reg,value) in enumerate(zip(registers,values)):
        lines.extend([f'mov r10,0{value:X}h',f'cmp {reg},r10',f'je abi_ok{i}',f'or eax,{1<<i}',f'abi_ok{i}:'])
    lines.extend(['cmp rsp,QWORD PTR [rsp+48]','je abi_ok8','or eax,256','abi_ok8:'])
    for i,value in enumerate((0x0123456789abcdef,0x76543210fedcba98),9):
        lines.extend([f'mov r10,0{value:X}h',f'cmp QWORD PTR [rsp+{32+(i-9)*8}],r10',f'je abi_ok{i}',f'or eax,{1<<i}',f'abi_ok{i}:'])
    lines.append('movdqu xmm0,XMMWORD PTR boom_deflate_abi_pattern')
    for i in range(6,16):
        lines.extend([f'movdqa xmm1,xmm{i}','pcmpeqb xmm1,xmm0','pmovmskb edx,xmm1','cmp edx,65535',f'je abi_xmm{i}',f'or eax,{1<<(i+5)}',f'abi_xmm{i}:'])
    for i in range(10):lines.append(f'movdqu xmm{6+i},XMMWORD PTR [rsp+{64+i*16}]')
    lines.append('add rsp,248')
    for reg in reversed(registers):lines.append('pop '+reg)
    lines.extend(['ret','boom_deflate_abi_probe ENDP','END'])
    source,obj,dll,rsp=(output/n for n in ('abi.asm','abi.obj','abi.dll','link.rsp'))
    source.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    assembler,linker=C.checked(candidate['assembler']),C.checked(candidate['linker'])
    with (output/'assembler.log').open('xb') as log:
        run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0,'ABI probe assembly failed')
    args=['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO',
          '/OUT:"'+str(dll)+'"','/EXPORT:boom_deflate_abi_probe','"'+str(C.checked(candidate['object']))+'"','"'+str(obj)+'"']
    rsp.write_text('\n'.join(args)+'\n',encoding='utf-8',newline='\n')
    with (output/'linker.log').open('xb') as log:run=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0,'ABI probe link failed')
    image=ctypes.CDLL(str(dll));probe=image.boom_deflate_abi_probe
    probe.argtypes=[ctypes.POINTER(Job)];probe.restype=ctypes.c_uint32
    cases=0
    for row in good+bad:
        source_buffer=ctypes.create_string_buffer(row['raw']);capacity=max(1,len(row['output'])) if row['output'] is not None else 65536
        target=ctypes.create_string_buffer(capacity);job=Job(ctypes.addressof(source_buffer),len(row['raw']),ctypes.addressof(target),capacity)
        mask=probe(ctypes.byref(job))
        C.check(mask==0 and job.status==row['status'],'Win64 callee-saved registers/stack canary or fixture status failed: '+row['name'])
        if row['output'] is not None:C.check(target.raw[:job.written]==row['output'],'ABI probe output differs')
        cases+=1
    result=dict(verified=True,calls=cases,nonvolatile_GPR=registers,nonvolatile_XMM=list(range(6,16)),stack_pointer_and_two_canaries=True,
        source=C.artifact(source),object=C.artifact(obj),image=C.artifact(dll),response=C.artifact(rsp),kernel_object=C.artifact(candidate['object']['path']),
        assembler=C.artifact(assembler),linker=C.artifact(linker),scope='test_only_ABI_observer_exact_original_kernel_object_no_runtime_registration')
    C.write(output/'verification.json',result);return C.artifact(output/'verification.json')


def python_oracle(row):
    ref=zlib.decompressobj(-15);out=ref.decompress(row['raw']+b'PYTHON-TRAIL')+ref.flush()
    C.check(ref.eof and out==row['output'] and ref.unused_data==b'PYTHON-TRAIL','Python reference output or consumed count mismatch: '+row['name'])


ORACLE=r'''import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.zip.*;
public class DeflateRawOracle {
  public static void main(String[] args) throws Exception {
    int passed=0;
    for (String line:Files.readAllLines(Path.of(args[0]))) {
      String[] p=line.split("\t");byte[] raw=Files.readAllBytes(Path.of(p[1]));
      Inflater f=new Inflater(true);boolean invalid=false;
      MessageDigest sha=MessageDigest.getInstance("SHA-256");long written=0;
      try {
        f.setInput(raw);byte[] buf=new byte[8192];
        try {
          while (!f.finished()) {
            int n=f.inflate(buf);sha.update(buf,0,n);written+=n;
            if (n==0 && !f.finished()) {if(f.needsInput() || f.needsDictionary()) break;throw new AssertionError("stalled "+p[0]);}
            if (written>1048576) throw new AssertionError("oracle bound "+p[0]);
          }
        } catch (DataFormatException e) {invalid=true;}
        if (p[2].equals("ok")) {
          if(invalid || !f.finished() || written!=Long.parseLong(p[3]) || f.getBytesWritten()!=written ||
             f.getBytesRead()!=Long.parseLong(p[5]) || f.getRemaining()!=raw.length-Long.parseLong(p[5]) ||
             !HexFormat.of().formatHex(sha.digest()).equals(p[4])) throw new AssertionError("JDK mismatch "+p[0]);
        } else if (!invalid && f.finished()) throw new AssertionError("JDK accepted invalid fixture "+p[0]);
        passed++;
      } finally {f.end();}
    }
    System.out.println("raw_deflate_JDK_reference_cases="+passed);
  }
}
'''


def jdk_oracle(output,good,bad,rfc_only):
    output.mkdir();source=output/'DeflateRawOracle.java';source.write_text(ORACLE,encoding='utf-8',newline='\n')
    tools=[C.artifact(JAVA/name) for name in ('bin/java.exe','bin/javac.exe','bin/server/jvm.dll','lib/modules','lib/src.zip')]
    lines=[];inputs=[]
    for row in good+bad+[rfc_only]:
        path=output/(row['name']+'.bin');raw=row['raw']+(b'JDK-TRAIL' if row['output'] is not None else b'')
        path.write_bytes(raw);inputs.append(C.artifact(path));valid=row['output'] is not None and row['oracle']
        lines.append('\t'.join([row['name'],str(path),'ok' if valid else 'reject',str(len(row['output'] or b'')),hashlib.sha256(row['output'] or b'').hexdigest(),str(len(row['raw']))]))
    manifest=output/'cases.tsv';manifest.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    with (output/'javac.log').open('xb') as log:run=subprocess.run([str(JAVA/'bin/javac.exe'),'-d',str(output),str(source)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0,'JDK oracle compilation failed')
    with (output/'java.log').open('xb') as log:run=subprocess.run([str(JAVA/'bin/java.exe'),'-cp',str(output),'DeflateRawOracle',str(manifest)],stdout=log,stderr=subprocess.STDOUT)
    C.check(run.returncode==0 and (output/'java.log').read_text().strip()=='raw_deflate_JDK_reference_cases='+str(len(lines)),'JDK oracle mismatch; retain java.log')
    C.check(tools==[C.artifact(t['path']) for t in tools],'JDK reference tools changed')
    result=dict(verified=True,scope='JDK_reference_only_raw_Inflater_true_output_and_exact_consumption',cases=len(lines),source=C.artifact(source),
        class_file=C.artifact(output/'DeflateRawOracle.class'),manifest=C.artifact(manifest),inputs=inputs,tools=tools,stdout=C.artifact(output/'java.log'),
        RFC_HDIST32_unused_reserved='JDK_and_zlib_reject_count_above30_while_RFC_allows_up_to32',delivery_uses_JVM=False)
    C.write(output/'verification.json',result);return C.artifact(output/'verification.json')


def run(candidate,output,thread_rounds,fuzz_cases):
    output=Path(output).resolve();C.check(output.is_relative_to(C.ART) and not output.exists(),'Fresh isolated execution output required')
    output.mkdir(parents=True);candidate=Path(candidate).resolve()
    before=C.artifact(candidate);data=json.loads(candidate.read_text(encoding='utf-8'))
    sourcepins=C.sources();harness=C.artifact(__file__);machine=C.verify(candidate)
    C.write(output/'machine-verification.json',machine)
    native=Native(C.checked(data['image']));good,bad,rfc_only=fixtures();observations=[]
    C.check({(r['raw'][0]>>1)&3 for r in good}=={0,1,2},'All three actual block types must be present')
    for row in good:
        python_oracle(row);observations.append(success(native,row,b'TRAILING\x00\xff'))
        # An independently complete second raw member must remain unread.
        success(native,row,good[1]['raw'])
    success(native,rfc_only,b'TRAIL')
    for row in bad:
        job,_=native.call(row['raw'],65536)
        C.check(job.status==row['status'],'Malformed fixture status mismatch: '+row['name']+' '+str(job.status))
        observations.append(dict(name=row['name'],status=job.status,consumed=job.consumed,written=job.written,bit_position=job.bit_position))
    output_full=0
    for row in good:
        if row['output']:
            for capacity in {0,max(0,len(row['output'])-1),len(row['output'])//2}:
                job,_=native.call(row['raw'],capacity)
                C.check(job.status==3,'Short output buffer must return bounded output-full: '+row['name']);output_full+=1
    truncations=0
    for row in good:
        cuts={0,len(row['raw'])-1,len(row['raw'])//2}
        if len(row['raw'])<=160:cuts.update(range(len(row['raw'])))
        for n in cuts:
            job,_=native.call(row['raw'][:n],max(1,len(row['output'])))
            C.check(job.status==2,'Valid truncated stream returned wrong status: '+row['name']);truncations+=1
    guards=bounds(native,good,bad);arguments=invalid_arguments(native)
    rng=random.Random(0x1951);valid_fuzz=0;rejected_fuzz=0
    for _ in range(fuzz_cases):
        raw=bytes(rng.randrange(256) for _ in range(rng.randrange(97)));job,out=native.call(raw,4096)
        ref=zlib.decompressobj(-15)
        try:
            expected=ref.decompress(raw,4097)
            if ref.eof and len(expected)<=4096:
                C.check(job.status==0 and out==expected and job.consumed==len(raw)-len(ref.unused_data),'Valid random-stream differential mismatch');valid_fuzz+=1
            elif job.status==0:raise ValueError('Native accepted unfinished/oversized random stream')
            else:rejected_fuzz+=1
        except zlib.error:
            C.check(job.status!=0,'Native accepted random input rejected by zlib');rejected_fuzz+=1
    mutated_valid=0;mutated_invalid=0;mutated_RFC_header=0
    for row in good:
        for _ in range(8):
            raw=bytearray(row['raw']);at=rng.randrange(len(raw));raw[at]^=1<<rng.randrange(8);raw=bytes(raw)
            job,out=native.call(raw,262144)
            # The explicit RFC-vs-zlib HDIST policy is outside the common
            # oracle subset, including when a header mutation introduces it.
            if len(raw)>1 and ((raw[0]>>1)&3)==2 and (raw[1]&31)>=30:
                mutated_RFC_header+=1;continue
            ref=zlib.decompressobj(-15)
            try:
                expected=ref.decompress(raw,262145)
                if ref.eof and len(expected)<=262144:
                    C.check(job.status==0 and out==expected and job.consumed==len(raw)-len(ref.unused_data),'Mutated complete-stream differential mismatch');mutated_valid+=1
                elif job.status==0:raise ValueError('Native accepted unfinished/oversized mutated stream')
                else:mutated_invalid+=1
            except zlib.error:
                C.check(job.status!=0,'Native accepted mutated input rejected by zlib');mutated_invalid+=1
    small=[row for row in good if len(row['output'])<=9000];barrier=threading.Barrier(8)
    def worker(index):
        ident=threading.get_native_id();barrier.wait()
        for i in range(thread_rounds):success(native,small[(i*7+index)%len(small)],b'THREAD-TAIL')
        return dict(thread=ident,calls=thread_rounds)
    with ThreadPoolExecutor(max_workers=8) as pool:threads=list(pool.map(worker,range(8)))
    C.check(len({r['thread'] for r in threads})==8,'Eight distinct OS workers required')
    abi=abi_fixture(output/'ABI-probe',data,good,bad)
    oracle=jdk_oracle(output/'jdk-oracle',good,bad,rfc_only)
    C.check(C.artifact(candidate)==before and C.sources()==sourcepins and C.artifact(__file__)==harness,'Execution inputs/source changed')
    for name in ('assembly','object','image','response','assembler','linker'):C.checked(data[name])
    result=dict(verified=True,scope='unregistered_one_shot_raw_DEFLATE_actual_ASM_kernel_only',candidate=before,harness=harness,sources=sourcepins,
        machine_verification=C.artifact(output/'machine-verification.json'),native_ABI_probe=abi,jdk_reference=oracle,python_reference=dict(version=zlib.ZLIB_VERSION,runtime_version=zlib.ZLIB_RUNTIME_VERSION,executable=C.artifact(__import__('sys').executable)),
        valid_streams=len(good),observations=observations,malformed_fixtures=len(bad),truncated_prefixes=truncations,guard_page_calls=guards,short_output_calls=output_full,
        invalid_argument_calls=arguments,random_input_calls=fuzz_cases,random_zlib_complete=valid_fuzz,random_rejected=rejected_fuzz,
        mutated_stream_calls=len(good)*8,mutated_zlib_complete=mutated_valid,mutated_rejected=mutated_invalid,mutated_separate_RFC_HDIST_headers=mutated_RFC_header,OS_workers=threads,
        RFC_HDIST32_separate_case=dict(ASM='accepted_without_using_reserved_codes',zlib_and_JDK='reject_count_above30',RFC='HDIST_1_through32_distance30_31_never_occur'),
        input_immutable=True,no_decoder_imports=True,no_mutable_globals=True,registered=False,inflater_compatible=False,incremental=False,zlib_wrapper=False,preset_dictionary=False,game_started=False)
    C.write(output/'execution.json',result);return output/'execution.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--thread-rounds',type=int,default=128);p.add_argument('--fuzz-cases',type=int,default=2000);a=p.parse_args()
    C.check(1<=a.thread_rounds<=1024 and 0<=a.fuzz_cases<=100000,'Bounded test counts required')
    print(run(a.candidate,a.output,a.thread_rounds,a.fuzz_cases))
