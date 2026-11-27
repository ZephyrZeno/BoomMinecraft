"""Execute the exact standalone capability kernel; original Java runs separately."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as ct
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import threading
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]

def module(name):
    spec=importlib.util.spec_from_file_location('atomic_cas_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

B=module('atomic-long-cas-candidate');S=B.S;C=B.C
U=ct.c_uint32;Q=ct.c_uint64;P=ct.c_void_p

class Context(ct.Structure):
    _fields_=[('kind',U),('pc',U),('method',U),('depth',U),('pending',Q),('reserved',Q)]

def execute(arguments,path):
    with Path(path).open('xb') as log:subprocess.run(list(map(str,arguments)),stdout=log,stderr=subprocess.STDOUT,check=True)

def text_suffix(path,name):
    raw=Path(path).read_bytes();count=struct.unpack_from('<H',raw,2)[0];at,number=struct.unpack_from('<II',raw,8)
    strings=at+number*18;found=[];i=0
    while i<number:
        label,value,section,kind,storage,aux=struct.unpack_from('<8sIhHBB',raw,at+i*18)
        if label[:4]==b'\0'*4:
            offset=struct.unpack_from('<I',label,4)[0];label=raw[strings+offset:raw.index(b'\0',strings+offset)]
        else:label=label.rstrip(b'\0')
        if label.decode()==name:found.append((value,section))
        i+=1+aux
    S.check(len(found)==1 and found[0][1]>0,'Actual kernel symbol differs');value,section=found[0]
    header=20+(section-1)*40;size,data=struct.unpack_from('<II',raw,header+16)
    return raw[data+value:data+size]

def probe_assembly(kernel):
    return 'option casemap:none\n'+C.data(None)+kernel+'\nEND\n'

def link_kernel(directory,text,assembler,linker,extra=()):
    directory.mkdir(parents=True);asm,obj,dll=directory/'probe.asm',directory/'probe.obj',directory/'probe.dll'
    asm.write_text(text,encoding='utf-8',newline='\n')
    execute([assembler,'/nologo','/c','/Fo'+str(obj),asm],directory/'assembler.log')
    exports={C.POOL,C.SERVICE}|set(extra)
    S.check(B.A.coff_symbols(obj)==(exports,set()),'Standalone native fixture imports or exports differ')
    rsp=directory/'link.rsp';rsp.write_text('\n'.join(['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64',
        '/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(dll)+'"','"'+str(obj)+'"',
        *['/EXPORT:'+n for n in sorted(exports)]])+'\n')
    execute([linker,'@'+str(rsp)],directory/'link.log')
    return asm,obj,dll

def test(candidate,output,jdk):
    output=output.resolve();S.check(output.is_relative_to(S.ART/'atomic-long-cas') and not output.exists(),'Fresh isolated execution required')
    row=S.read(candidate);kernel=B.KERNEL.read_text();pins=[S.artifact(candidate),row['model'],row['kernel'],row['tool'],
        row['assembly'],row['object'],row['assembler'],S.artifact(__file__),S.artifact(ROOT/'java/reference/AtomicLongCasReference.java')]
    for pin in pins:S.check(S.artifact(pin['path'])==pin,'Frozen source changed')
    S.check(kernel.count('\n cpuid\n')==2,'Production kernel must execute both actual CPUID leaves')
    assembler=Path(row['assembler']['path']);linker=assembler.with_name('link.exe');output.mkdir(parents=True)
    asm,obj,dll=link_kernel(output/'actual',probe_assembly(kernel),assembler,linker)
    actual=text_suffix(S.checked(row['object']),C.SERVICE);standalone=text_suffix(obj,C.SERVICE)
    S.check(actual==standalone and actual.count(b'\x0f\xa2')==2,'Standalone executed instructions differ from real native candidate')
    library=ct.WinDLL(str(dll));service=getattr(library,C.SERVICE);service.argtypes=[P,P,P,U];service.restype=Q
    pool=(U*4).in_dll(library,C.POOL);context=Context();cap=service(ct.byref(context),None,ct.addressof(pool),0)
    S.check(cap==1 and context.kind==0,'This x64 target profile requires real physical CX8; unsupported Context20 is not Java false')
    S.check(service(None,None,ct.addressof(pool),0)==0,'Null context must not report success')
    pending=Context(20,123,456,7,0x11223344,0x55667788);before=bytes(pending)
    S.check(service(ct.byref(pending),None,None,99)==0 and bytes(pending)==before,'Existing Context32 was changed')
    invalid=[]
    for field,value,op,null in [(0,0,0,False),(1,2,0,False),(2,1,0,False),(3,1,0,False),(None,None,1,False),(None,None,0,True)]:
        copy=(U*4)(*pool)
        if field is not None:copy[field]=value
        ctx=Context(0,77,88,0,0,0)
        S.check(service(ct.byref(ctx),None,None if null else ct.addressof(copy),op)==0 and
            bytes(ctx)==bytes(Context(7,77,88,0,0,0)),'Bad metadata/op must set only normal Context.kind=7')
        invalid.append(dict(field=field,operation=op,null_pool=null,kind=ctx.kind))
    barrier=threading.Barrier(8)
    def worker(index):
        barrier.wait()
        for n in range(256):
            ctx=Context();S.check(service(ct.byref(ctx),None,ct.addressof(pool),0)==cap and bytes(ctx)==bytes(Context()),'Concurrent hardware query changed')
        return dict(thread=threading.get_native_id(),calls=256)
    with ThreadPoolExecutor(max_workers=8) as executor:counts=list(executor.map(worker,range(8)))
    S.check(len({r['thread'] for r in counts})==8,'Eight distinct real OS threads required')
    # Native-only test fixtures replace exactly the two CPUID instructions with
    # scalar leaf results. They are never used as candidate/provider objects.
    variants=[]
    for maximum,edx,ecx in [(0,0,0),(0,0x100,0),(1,0,0),(1,0,1<<13),(1,0x80,1<<13),(1,0x100,0),(1,0x100,1<<13),(0xffffffff,0x100,0)]:
        first=f' mov eax,{maximum}\n xor ebx,ebx\n xor ecx,ecx\n xor edx,edx\n'
        second=f' xor eax,eax\n xor ebx,ebx\n mov ecx,{ecx}\n mov edx,{edx}\n'
        fixture=kernel.replace(' cpuid\n',first,1).replace(' cpuid\n',second,1)
        _,_,path=link_kernel(output/('synthetic-leaves-'+str(len(variants))),probe_assembly(fixture),assembler,linker)
        image=ct.WinDLL(str(path));call=getattr(image,C.SERVICE);call.argtypes=[P,P,P,U];call.restype=Q
        bank=(U*4).in_dll(image,C.POOL);ctx=Context();value=call(ct.byref(ctx),None,ct.addressof(bank),0)
        supported=maximum>=1 and bool(edx&0x100)
        S.check((value,ctx.kind)==((1,0) if supported else (0,20)),'Missing CX8/leaf1 cannot be accepted as Java false or confused with CX16')
        variants.append(dict(max_leaf=maximum,leaf1_EDX=edx,leaf1_ECX=ecx,result=value,kind=ctx.kind,
            test_only_two_CPUID_instruction_replacements=True,production_object=False))
    rbx='''
.code
PUBLIC boom_atomic_cas_check_rbx
boom_atomic_cas_check_rbx PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,1122334455667788h
 call boom_provider_atomic_long_cas_service
 mov rax,1122334455667788h
 xor rax,rbx
 add rsp,32
 pop rbx
 ret
boom_atomic_cas_check_rbx ENDP
'''
    text=probe_assembly(kernel).removesuffix('END\n')+rbx+'END\n'
    _,_,path=link_kernel(output/'RBX',text,assembler,linker,('boom_atomic_cas_check_rbx',));image=ct.WinDLL(str(path))
    call=image.boom_atomic_cas_check_rbx;call.argtypes=[P,P,P,U];call.restype=Q;bank=(U*4).in_dll(image,C.POOL)
    for _ in range(64):
        ctx=Context();S.check(call(ct.byref(ctx),None,ct.addressof(bank),0)==0 and ctx.kind==0,'Windows x64 RBX was not preserved')
    javac,java=jdk/'bin/javac.exe',jdk/'bin/java.exe';source=ROOT/'java/reference/AtomicLongCasReference.java'
    classes=output/'oracle';classes.mkdir();execute([javac,'-d',classes,source],output/'javac.log')
    result=subprocess.run([str(java),'--add-opens','java.base/java.util.concurrent.atomic=ALL-UNNAMED','-cp',str(classes),'AtomicLongCasReference'],
        check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    (output/'JDK-oracle.stdout').write_text(result.stdout);(output/'JDK-oracle.stderr').write_text(result.stderr)
    values=dict(line.split('=',1) for line in result.stdout.splitlines())
    S.check(values==dict(supports='true',cached='true',native_modifiers='266',field_modifiers='24',primitive_boolean='true',parameter_count='0'),
        'Locked JVM capability/source reflection differs from actual ASM')
    for pin in pins:S.check(S.artifact(pin['path'])==pin,'Input changed during actual tests')
    proof=dict(schema=1,verified=True,scope='exact_CPUID_kernel_actual_CPU_native_ABI_and_development_JDK_oracle_only',
        inputs=pins,actual_object=S.artifact(obj),actual_DLL=S.artifact(dll),
        provider_service_instruction_bytes_equal_executed_kernel=True,service_instruction_sha256=hashlib.sha256(actual).hexdigest(),
        actual_hardware_capability=cap,existing_pending_Context32_preserved=True,bad_metadata=invalid,
        real_OS_workers=8,OS_thread_calls=counts,hardware_calls=sum(r['calls'] for r in counts),RBX_preservation_calls=64,synthetic_leaf_cases=variants,
        JDK_oracle=values,JDK_tools=[S.artifact(java),S.artifact(javac)],
        whole_candidate_original_Java_wrapper_executed=False,original_AtomicLong_clinit_executed_in_ASM=False,
        Java_fields_or_clinit_state_host_written=False,native_allocations=0,native_Java_roots=0,
        runtime_DLL_modified=False,shared_registered=False,game_started=False)
    S.write(output/'execution.json',proof);return output/'execution.json'

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--jdk',type=Path,default=Path('D:/Dev/Java/jdk-21'))
    args=parser.parse_args();print(test(args.candidate.resolve(),args.output,args.jdk))
