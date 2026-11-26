"""Compare our read-only ASM path primitives to the locked Windows JDK."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
from threading import Barrier, get_native_id
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'
KERNEL=ROOT/'native/runtime/windows_canonical_path.asm'
BIN=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64')
JDK=Path('D:/Dev/Java/jdk-21')
P,U,W,Q=c.c_void_p,c.c_uint32,c.c_uint16,c.c_uint64


def check(value,message):
    if not value:raise ValueError(message)


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:h=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=h))


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def text_section(path):
    raw=Path(path).read_bytes();machine,count=struct.unpack_from('<HH',raw)
    check(machine==0x8664,'Actual AMD64 COFF required')
    for i in range(count):
        at=20+i*40
        if raw[at:at+8].rstrip(b'\0') in (b'.text',b'.text$mn',b'_TEXT') and struct.unpack_from('<I',raw,at+36)[0]&0x20:
            size,start=struct.unpack_from('<II',raw,at+16);return raw[start:start+size]
    raise ValueError('Missing actual AMD64 instructions')


def build(output):
    output=Path(output).resolve();check(output.is_relative_to(ART) and not output.exists(),'Fresh isolated output required')
    output.mkdir(parents=True);before=artifact(KERNEL)
    linker=BIN/'link.exe';assembler=BIN/'ml64.exe';link=module('canonical_primitive_link','canonical-link-response.py')
    sdk=link.sdk_libraries()[0]
    def tool(args,name):
        with (output/name).open('wb') as log:r=subprocess.run([str(a) for a in args],stdout=log,stderr=log,check=True)
    obj=output/'primitive.obj';dll=output/'primitive.dll'
    tool([assembler,'/nologo','/c','/Fo'+str(obj),KERNEL],'assembler.log')
    exports=['boom_windows_canonical_path','boom_windows_drive_directory']
    rsp=output/'link.rsp';rsp.write_text('\n'.join([*link.PREFIXES['diagnostic'],'/OUT:"'+str(dll)+'"',
        '"'+str(obj)+'"',*['"'+str(p)+'"' for p in sdk],*['/EXPORT:'+n for n in exports]])+'\n')
    link.verify(rsp,profile='diagnostic',output=dll,objects=[obj],library_choices=[sdk],exports=exports)
    tool([linker,'@'+str(rsp)],'link.log')
    # Only imported HeapAlloc/HeapFree names change in this test-only copy.
    instrumented=output/'instrumented.asm'
    instrumented.write_text(KERNEL.read_text().replace('HeapAlloc','boom_test_heap_alloc').replace('HeapFree','boom_test_heap_free'))
    instrumented_obj=instrumented.with_suffix('.obj')
    tool([assembler,'/nologo','/c','/Fo'+str(instrumented_obj),instrumented],'instrumented-assembler.log')
    check(text_section(obj)==text_section(instrumented_obj),'Memory observations changed actual primitive instructions')
    observer=output/'memory-observer.asm'
    observer.write_text('''option casemap:none
EXTERN HeapAlloc:PROC
EXTERN HeapFree:PROC
.data
PUBLIC boom_test_heap_live
PUBLIC boom_test_heap_allocations
PUBLIC boom_test_heap_frees
PUBLIC boom_test_heap_fail
boom_test_heap_live QWORD 0
boom_test_heap_allocations QWORD 0
boom_test_heap_frees QWORD 0
boom_test_heap_fail DWORD 0
.code
PUBLIC boom_test_heap_alloc
boom_test_heap_alloc PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 cmp DWORD PTR [boom_test_heap_fail],0
 jne observed_alloc_fail
 call HeapAlloc
 test rax,rax
 jz observed_alloc_done
 lock inc QWORD PTR [boom_test_heap_live]
 lock inc QWORD PTR [boom_test_heap_allocations]
 jmp observed_alloc_done
observed_alloc_fail:
 xor eax,eax
observed_alloc_done:
 add rsp,40
 ret
boom_test_heap_alloc ENDP
PUBLIC boom_test_heap_free
boom_test_heap_free PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 call HeapFree
 test eax,eax
 jz observed_free_done
 lock dec QWORD PTR [boom_test_heap_live]
 lock inc QWORD PTR [boom_test_heap_frees]
observed_free_done:
 add rsp,40
 ret
boom_test_heap_free ENDP
END
''')
    observer_obj=observer.with_suffix('.obj');tool([assembler,'/nologo','/c','/Fo'+str(observer_obj),observer],'observer-assembler.log')
    observed=output/'observed.dll';observed_rsp=output/'observed-link.rsp'
    observed_exports=exports+['boom_test_heap_live','boom_test_heap_allocations','boom_test_heap_frees','boom_test_heap_fail']
    observed_rsp.write_text('\n'.join([*link.PREFIXES['diagnostic'],'/OUT:"'+str(observed)+'"',
        '"'+str(instrumented_obj)+'"','"'+str(observer_obj)+'"',*['"'+str(p)+'"' for p in sdk],
        *['/EXPORT:'+n for n in sorted(observed_exports)]])+'\n')
    link.verify(observed_rsp,profile='diagnostic',output=observed,objects=[instrumented_obj,observer_obj],
        library_choices=[sdk],exports=observed_exports)
    tool([linker,'@'+str(observed_rsp)],'observed-link.log')
    check(artifact(KERNEL)==before,'Primitive source changed during real assembly/link')
    records=[artifact(p) for p in [KERNEL,Path(__file__),assembler,linker,*sdk,obj,dll,rsp,instrumented,
        instrumented_obj,observer,observer_obj,observed,observed_rsp]]
    return dict(output=str(output),kernel=before,image=artifact(dll),observed=artifact(observed),inputs=records)


def bind(image):
    f=image.boom_windows_canonical_path;f.restype=U;f.argtypes=[P,U,P,U,P]
    d=image.boom_windows_drive_directory;d.restype=U;d.argtypes=[U,P,U,P]
    return f,d


def canonical(function,value,capacity=32768):
    raw=value.encode('utf-16-le','surrogatepass');data=(W*(len(raw)//2+1))()
    if raw:c.memmove(data,raw,len(raw))
    output=(W*max(capacity,1))(*([0x5a5a]*max(capacity,1)));size=U(99)
    before=bytes(output);source=bytes(data)
    error=function(data,len(raw)//2,output,capacity,c.byref(size))
    check(bytes(data)==source,'Primitive modified an input UTF16 buffer')
    if error:
        check(size.value==0 and bytes(output)==before,'Failed primitive published or corrupted its output')
        return dict(error=error,value=None)
    check(size.value<capacity and output[size.value]==0,'Successful output length/NUL escaped its capacity')
    return dict(error=0,value=c.string_at(output,size.value*2).decode('utf-16-le','surrogatepass'))


def oracle(output,work,values):
    source=output/'WindowsCanonicalOracle.java';java=JDK/'bin/java.exe';modules=JDK/'lib/modules'
    source.write_text('''import java.io.*; import java.lang.reflect.*;
class WindowsCanonicalOracle {
 static String decode(String x){StringBuilder b=new StringBuilder();for(int i=0;i<x.length();i+=4)b.append((char)Integer.parseInt(x.substring(i,i+4),16));return b.toString();}
 static String encode(String x){StringBuilder b=new StringBuilder();for(int i=0;i<x.length();i++){String s=Integer.toHexString(x.charAt(i));b.append("0".repeat(4-s.length())).append(s);}return b.toString();}
 public static void main(String[] args)throws Exception{
  Field field=null;for(Field candidate:File.class.getDeclaredFields())if(candidate.getType().getName().equals("java.io.FileSystem")&&Modifier.isStatic(candidate.getModifiers())){if(field!=null)throw new AssertionError("ambiguous filesystem field");field=candidate;}
  if(field==null)throw new AssertionError("missing filesystem field");field.setAccessible(true);Object fs=field.get(null);
  Method m=fs.getClass().getDeclaredMethod("canonicalize0",String.class);m.setAccessible(true);
  Method d=fs.getClass().getDeclaredMethod("getDriveDirectory",int.class);d.setAccessible(true);
  for(String x:args)try{System.out.println("OK:"+encode((String)m.invoke(fs,decode(x))));}
   catch(InvocationTargetException e){Throwable t=e.getCause();System.out.println("ERR:"+t.getClass().getName()+":"+encode(String.valueOf(t.getMessage())));}
  for(int i=-1;i<=27;i++){Object r=d.invoke(fs,i);System.out.println("DRIVE:"+i+":"+(r==null?"NULL":encode((String)r)));}
 }
}
''',encoding='ascii')
    args=[str(java),'--add-opens','java.base/java.io=ALL-UNNAMED',str(source),
        *[s.encode('utf-16-be','surrogatepass').hex() for s in values]]
    r=subprocess.run(args,cwd=work,capture_output=True,timeout=90)
    (output/'oracle.stdout').write_bytes(r.stdout);(output/'oracle.stderr').write_bytes(r.stderr)
    check(r.returncode==0,'Locked JDK oracle failed; inspect '+str(output/'oracle.stderr'))
    lines=r.stdout.decode('ascii').splitlines();check(len(lines)==len(values)+29,'Reference oracle output is incomplete')
    return lines,dict(java=artifact(java),modules=artifact(modules),source=artifact(source),stdout=artifact(output/'oracle.stdout'))


def run(manifest):
    output=Path(manifest['output']);work=output/'work';work.mkdir()
    folder=work/'CaseDir';(folder/'SubDir').mkdir(parents=True);(folder/'RealName.txt').write_bytes(b'canonical source fixture')
    (work/'大小写目录').mkdir();(work/'大小写目录/文件.txt').write_bytes(b'utf16')
    long=work
    for i in range(16):long=long/('LongComponent'+str(i).zfill(2))
    check(long.is_relative_to(work),'Long-path fixture escaped its new test directory')
    long_system=Path('\\\\?\\'+str(long))
    long_system.mkdir(parents=True);(long_system/'LongFile.Case').write_bytes(b'long')
    values=['','.', '..', 'CaseDir/RealName.txt','casedir\\realname.TXT',
        'CaseDir\\SubDir\\..\\REALNAME.TXT','CaseDir\\Missing\\Child.KEEP','NoSuch\\..\\CaseDir\\NoSuch.txt',
        str(folder/'RealName.txt').lower(),str(long/'LongFile.Case').lower(),'大小写目录/文件.txt',
        'CaseDir\\RealName.txt\0ignored','CaseDir\\RealName.txt\\child','CaseDir\\Missing\\More',
        'CaseDir\\*.txt','CaseDir\\a?b','CaseDir\\Ending.','CaseDir\\...','CaseDir\\a:b',
        'NUL','CON','\\\\host','\\\\?\\C:\\tmp','CaseDir\\a\ud800b',str(work.anchor),
        'CaseDir\\SubDir\\','CaseDir\\\\RealName.txt']
    image=c.CDLL(manifest['image']['path']);observed=c.CDLL(manifest['observed']['path']);f,d=bind(image);of,od=bind(observed)
    previous=Path.cwd()
    try:
        os.chdir(work);lines,reference=oracle(output,work,values);results=[]
        for value,line in zip(values,lines):
            actual=canonical(f,value);mirror=canonical(of,value);check(actual==mirror,'Observed copy changed primitive behavior')
            if line.startswith('OK:'):
                expected=bytes.fromhex(line[3:]).decode('utf-16-be','surrogatepass')
                check(not actual['error'] and actual['value']==expected,'Canonical mismatch: '+repr((value,actual,expected)))
            else:check(actual['error'] and line.startswith('ERR:java.io.IOException:'),'Error kind mismatch: '+repr((value,actual,line)))
            results.append(dict(input_UTF16=value.encode('utf-16-be','surrogatepass').hex(),actual=actual,oracle=line))
        for line in lines[len(values):]:
            _,drive,text=line.split(':',2);out=(W*32768)();size=U(99);error=d(int(drive)&0xffffffff,out,32768,c.byref(size))
            if text=='NULL':check(error and size.value==0,'Unavailable drive did not fail without output')
            else:check(not error and c.string_at(out,size.value*2).decode('utf-16-le')==bytes.fromhex(text).decode('utf-16-be'),'Drive-relative directory differs')
        for capacity in (0,1,2,3):check(canonical(f,'.',capacity)['error']==122,'Small caller output buffer was accepted')
        check(canonical(f,'*')['error']==0xffffffff,'Wildcard was not a logical pathname error')
        barrier=Barrier(8,timeout=30)
        def worker(index):
            barrier.wait()
            for _ in range(16):
                for value in values[:14]:canonical(of,value)
            return get_native_id()
        with ThreadPoolExecutor(8) as workers:threads=list(workers.map(worker,range(8)))
        check(len(set(threads))==8,'Concurrent canonicalization did not use eight actual OS threads')
        live=Q.in_dll(observed,'boom_test_heap_live').value;alloc=Q.in_dll(observed,'boom_test_heap_allocations').value;freed=Q.in_dll(observed,'boom_test_heap_frees').value
        check(live==0 and alloc==freed,'Primitive retained native scratch allocations')
        U.in_dll(observed,'boom_test_heap_fail').value=1
        check(canonical(of,'.')['error']==8 and Q.in_dll(observed,'boom_test_heap_live').value==0,'Injected native OOM published output or leaked an allocation')
        U.in_dll(observed,'boom_test_heap_fail').value=0
    finally:os.chdir(previous)
    for record in manifest['inputs']:check(artifact(record['path'])==record,'Primitive test input changed')
    return dict(verified=True,scope='isolated_assembly_read_only_Windows_path_primitives_only',manifest=manifest,
        JDK_oracle=reference,path_cases=results,drive_cases=29,actual_OS_threads=threads,concurrent_calls=8*16*14,
        scratch_allocations=alloc,scratch_frees=freed,scratch_live=live,test_only_import_observation=True,
        primitive_actual_text_unchanged_by_observation=True,native_OOM_verified=True,
        Java_native_binding_verified=False,shared_runtime_modified=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ART/'windows-path-canonicalization/primitive-tests'/uuid4().hex)
    args=parser.parse_args();manifest=build(args.output)
    (Path(manifest['output'])/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    result=run(manifest);p=Path(manifest['output'])/'result.json';p.write_text(json.dumps(result,indent=2,ensure_ascii=True)+'\n');print(p)
