"""Test controlled Win32 failures and ABI preservation in the owned mapping slice."""
import argparse
import ctypes as c
import gc
import importlib.util
import json
from pathlib import Path
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location('jimage_protocol_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
B=module('jimage-owner-candidate');T=module('test-jimage-owner')
P,U,Q=T.P,T.U,T.Q
FAULTS=['CreateFileW','GetFileSizeEx','CreateFileMappingW','MapViewOfFile','VirtualAlloc','UnmapViewOfFile','CloseHandle','VirtualFree']


def compile_object(assembler,source,text):
    source.write_text(text,encoding='utf-8',newline='\n');obj=source.with_suffix('.obj')
    with source.with_suffix('.log').open('xb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),source],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    return obj


def link(candidate,output,objects,exports):
    dll=output/'owner.dll';rsp=output/'link.rsp'
    lines=['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO',
           '/OUT:"'+str(dll)+'"',*['/EXPORT:'+name for name in sorted(exports)],
           *['"'+str(p)+'"' for p in objects+[B.checked(candidate['kernel32'])]]]
    rsp.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    with (output/'link.log').open('xb') as log:
        subprocess.run([B.checked(candidate['linker']),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    return dll,rsp


def aliased_protocol(original,observed,aliases,output):
    """Only known imported names may differ; compare all execution bytes and aux."""
    def rows(path,rename=False):
        data=bytearray(Path(path).read_bytes());_,_,_,at,count,_,_=struct.unpack_from('<HHIIIHH',data)
        strings=at+18*count;index=0;symbols=[];seen=set()
        while index<count:
            pos=at+18*index;name=bytes(data[pos:pos+8]);long=name[:4]==b'\0'*4
            if long:
                start=strings+struct.unpack_from('<I',name,4)[0];end=data.index(0,start);name=bytes(data[start:end]).decode()
            else:name=name.rstrip(b'\0').decode()
            value,section,kind,storage,aux=struct.unpack_from('<IhHBB',data,pos+8)
            if rename and name in aliases:
                B.check(storage==2 and section==0 and long,'Observer alias was not an ordinary external import')
                old=aliases[name];encoded=old.encode();B.check(len(encoded)<=end-start,'Observer alias cannot normalize')
                data[start:end]=encoded+b'\0'*(end-start-len(encoded));name=old;seen.add(old)
            section_name=bytes(data[20+(section-1)*40:28+(section-1)*40]).rstrip(b'\0').decode() if section>0 else section
            if storage!=103 and section_name!='.debug$S':
                symbols.append((name,value,section_name,kind,storage,bytes(data[pos+18:pos+18*(1+aux)]).hex()))
            index+=1+aux
        if rename:B.check(seen==set(aliases.values()),'Observer alias set differs')
        target=output/'alias-normalized-not-linked.obj' if rename else Path(path)
        if rename:target.write_bytes(data)
        normalized=B.normalized_coff(target);normalized.pop('nondebug_symbols_sha256')
        return normalized,sorted(symbols)
    B.check(rows(original)==rows(observed,True),'Observer changed instructions, symbol aux, sections or non-aliased relocations')


def fault_image(candidate,output):
    output.mkdir();original=B.checked(candidate['assembly']).read_text();text=original;aliases={}
    for name in FAULTS:
        alias='boom_jio_test_'+name;aliases[alias]=name
        text=text.replace('EXTERN '+name+':PROC','EXTERN '+alias+':PROC').replace('call '+name+'\n','call '+alias+'\n')
    restored=text
    for alias,name in aliases.items():restored=restored.replace(alias,name)
    B.check(restored==original,'Test observer changed more than explicit Win32 aliases')
    assembler=B.checked(candidate['assembler']);obj=compile_object(assembler,output/'observed.asm',text)
    aliased_protocol(B.checked(candidate['object']),obj,aliases,output)
    lines=['option casemap:none','EXTERN SetLastError:PROC','.data','PUBLIC boom_jio_test_controls',
           'boom_jio_test_controls DWORD '+str(len(FAULTS))+' DUP(0)','.code']
    for i,name in enumerate(FAULTS):
        alias='boom_jio_test_'+name
        lines.extend(['EXTERN '+name+':PROC',alias+' PROC FRAME','sub rsp,40','.allocstack 40','.endprolog',
            f'cmp DWORD PTR [boom_jio_test_controls+{4*i}],0','je '+alias+'_pass',
            f'dec DWORD PTR [boom_jio_test_controls+{4*i}]','jnz '+alias+'_pass',
            'mov ecx,5','call SetLastError','mov rax,-1' if name=='CreateFileW' else 'xor eax,eax',
            'add rsp,40','ret',alias+'_pass:','add rsp,40','jmp '+name,alias+' ENDP'])
    thunks=compile_object(assembler,output/'controls.asm','\n'.join(lines+['END'])+'\n')
    dll,rsp=link(candidate,output,[obj,thunks],B.EXPORTS|{'boom_jio_test_controls'})
    return c.WinDLL(str(dll)),[B.artifact(p) for p in (obj,thunks,dll,rsp,output/'observed.asm',output/'controls.asm')]


def abi_image(candidate,output):
    output.mkdir();registers=['rbx','rbp','rsi','rdi','r12','r13','r14','r15'];values=[0x4131000000000001+i for i in range(8)]
    lines=['option casemap:none','.const','ALIGN 16','abi_pattern QWORD 0123456789ABCDEFh,076543210FEDCBA98h',
        '.code','PUBLIC boom_jio_abi_probe','boom_jio_abi_probe PROC FRAME']
    for reg in registers:lines+=['push '+reg,'.pushreg '+reg]
    lines+=['sub rsp,248','.allocstack 248']
    for i in range(10):lines += [f'movdqu XMMWORD PTR [rsp+{64+16*i}],xmm{6+i}',f'.savexmm128 xmm{6+i},{64+16*i}']
    lines+=['.endprolog','mov QWORD PTR [rsp+56],rcx','mov rcx,rdx','mov rdx,r8','mov r8,r9',
        'mov rax,QWORD PTR [rsp+352]','mov QWORD PTR [rsp+240],rax',
        'mov rax,0123456789ABCDEFh','mov QWORD PTR [rsp+32],rax',
        'mov rax,076543210FEDCBA98h','mov QWORD PTR [rsp+40],rax','mov QWORD PTR [rsp+48],rsp']
    for reg,value in zip(registers,values):lines+= [f'mov {reg},0{value:X}h']
    lines+=['movdqu xmm0,XMMWORD PTR abi_pattern']
    for i in range(6,16):lines+= [f'movdqa xmm{i},xmm0']
    lines+=['call QWORD PTR [rsp+56]','mov QWORD PTR [rsp+224],rax','xor eax,eax']
    for i,(reg,value) in enumerate(zip(registers,values)):
        lines += [f'mov r10,0{value:X}h',f'cmp {reg},r10',f'je abi_gpr{i}',f'or eax,{1<<i}',f'abi_gpr{i}:']
    lines+=['cmp rsp,QWORD PTR [rsp+48]','je abi_stack','or eax,256','abi_stack:']
    for i,value in enumerate((0x0123456789abcdef,0x76543210fedcba98)):
        lines += [f'mov r10,0{value:X}h',f'cmp QWORD PTR [rsp+{32+8*i}],r10',f'je abi_guard{i}',f'or eax,{1<<(9+i)}',f'abi_guard{i}:']
    lines+=['movdqu xmm0,XMMWORD PTR abi_pattern']
    for i in range(6,16):
        lines += [f'movdqa xmm1,xmm{i}','pcmpeqb xmm1,xmm0','pmovmskb edx,xmm1','cmp edx,65535',f'je abi_xmm{i}',f'or eax,{1<<(5+i)}',f'abi_xmm{i}:']
    lines+=['mov rdx,QWORD PTR [rsp+240]','mov r10,QWORD PTR [rsp+224]','mov QWORD PTR [rdx],r10']
    for i in range(10):lines += [f'movdqu xmm{6+i},XMMWORD PTR [rsp+{64+16*i}]']
    lines+=['add rsp,248',*['pop '+reg for reg in reversed(registers)],'ret','boom_jio_abi_probe ENDP','END']
    obj=compile_object(B.checked(candidate['assembler']),output/'abi.asm','\n'.join(lines)+'\n')
    dll,rsp=link(candidate,output,[B.checked(candidate['object']),obj],B.EXPORTS|{'boom_jio_abi_probe'})
    return c.WinDLL(str(dll)),[B.artifact(p) for p in (obj,dll,rsp,output/'abi.asm')]


def run(path,output):
    output=Path(output).resolve();B.check(output.is_relative_to(B.ART) and not output.exists(),'Fresh owner protocol output required')
    candidate=json.loads(Path(path).read_text());B.check(B.verify(path)==json.loads(Path(path).with_name('verification.json').read_text()),'Original owner machine positive control differs')
    output.mkdir(parents=True);driver=B.artifact(__file__);host=B.artifact(T.__file__)
    valid=output/'valid.jimage';valid.write_bytes(struct.pack('<7I',0xcafedada,0x10000,0,0,0,0,1)+b'\0')
    invalid=output/'invalid.jimage';invalid.write_bytes(b'bad!'+valid.read_bytes()[4:])
    fault,pins=fault_image(candidate,output/'faults');abi,abi_pins=abi_image(candidate,output/'ABI')
    controls=(U*len(FAULTS)).in_dll(fault,'boom_jio_test_controls')
    for image in (fault,abi):
        image.boom_jimage_owner_init.argtypes=[P,U,U];image.boom_jimage_owner_init.restype=U
        image.boom_jimage_owner_close.argtypes=[P];image.boom_jimage_owner_close.restype=U
        for name in ('open','lookup','release'):
            f=getattr(image,'boom_jimage_owner_'+name);f.argtypes=[P];f.restype=U
    def owner(image):
        pool=c.create_string_buffer(128);B.check(image.boom_jimage_owner_init(pool,128,4)==0,'Protocol owner init failed');return pool
    def call(image,name,pool,path=None,token=0):
        key=c.create_string_buffer(str(path).encode('utf-16-le')) if path is not None else None
        job=T.Job(c.addressof(pool),c.addressof(key) if key is not None else None,len(str(path)) if path is not None else 0,token,None,0,0,0,0)
        status=getattr(image,'boom_jimage_owner_'+name)(c.byref(job));B.check(status==job.status,'Job/result protocol differs');return job
    def stat(pool,at):return Q.from_address(c.addressof(pool)+at).value
    cases=[]
    for name in FAULTS[:5]:
        pool=owner(fault);controls[FAULTS.index(name)]=1;job=call(fault,'open',pool,valid)
        B.check(job.status==4 and job.error==5 and all(stat(pool,o)==0 for o in (32,48,56,64,72,80)),'Failed open lost real resources: '+name)
        B.check(fault.boom_jimage_owner_close(pool)==0,'Failed-open owner could not close');cases.append(name)
    for name,skip in [('UnmapViewOfFile',1),('CloseHandle',1),('CloseHandle',2),('VirtualFree',1)]:
        pool=owner(fault);lease=call(fault,'open',pool,valid);B.check(lease.status==0,'Cleanup fixture open failed')
        B.check(call(fault,'release',pool,token=lease.token).status==0,'Cleanup fixture release failed')
        controls[FAULTS.index(name)]=skip
        B.check(fault.boom_jimage_owner_close(pool)==12 and U.from_address(c.addressof(pool)+24).value==3 and stat(pool,48),
            'Cleanup failure was hidden or tracking was dropped: '+name)
        B.check(call(fault,'lookup',pool,valid).status==12,'Draining owner returned a view')
        retained=[stat(pool,o) for o in (32,56,64,72,80)]
        B.check(fault.boom_jimage_owner_close(pool)==0 and all(stat(pool,o)==0 for o in (32,48,56,64,72,80)),'Retained cleanup could not retry: '+name)
        cases.append(dict(cleanup=name,skip=skip,retained=retained))
    pool=owner(fault);lease=call(fault,'open',pool,valid);controls[FAULTS.index('UnmapViewOfFile')]=1
    failed=call(fault,'open',pool,invalid)
    B.check(failed.status==12 and failed.error==5 and stat(pool,56)==1,'Failed-open rollback lost its cleanup node or existing lease')
    B.check(fault.boom_jimage_owner_close(pool)==2 and call(fault,'release',pool,token=lease.token).status==0,'Draining owner blocked safe lease release')
    B.check(fault.boom_jimage_owner_close(pool)==0 and all(stat(pool,o)==0 for o in (32,48,56,64,72,80)),'Rollback orphan was not retained and freed')
    cases.append('rollback_orphan_with_existing_live_lease')
    probe=abi.boom_jio_abi_probe;probe.argtypes=[P,P,Q,Q,P];probe.restype=U;abi_calls=[]
    def invoke(name,arg1=None,arg2=0,arg3=0,expected=0):
        fn=getattr(abi,'boom_jimage_owner_'+name);value=Q()
        mask=probe(c.cast(fn,P),arg1,arg2,arg3,c.byref(value))
        B.check(mask==0 and value.value==expected,'Win64 register/stack/canary or return mismatch: '+name)
        abi_calls.append(dict(operation=name,result=value.value,mask=mask))
    pool=c.create_string_buffer(128);invoke('init',c.addressof(pool),128,4)
    key=c.create_string_buffer(str(valid).encode('utf-16-le'));job=T.Job(c.addressof(pool),c.addressof(key),len(str(valid)),0,None,0,0,0,0)
    invoke('open',c.addressof(job));token=job.token
    invoke('close',c.addressof(pool),expected=2)
    for _ in range(64):
        job=T.Job(c.addressof(pool),c.addressof(key),len(str(valid)),0,None,0,0,0,0);invoke('lookup',c.addressof(job))
        job=T.Job(c.addressof(pool),None,0,token,None,0,0,0,0);invoke('release',c.addressof(job))
    job=T.Job(c.addressof(pool),None,0,token,None,0,0,0,0);invoke('release',c.addressof(job))
    invoke('close',c.addressof(pool));invoke('lookup',c.addressof(job),expected=9)
    for name in ('init','open','lookup','release'):invoke(name,expected=3)
    invoke('close',expected=5)
    for record in [driver,host,*pins,*abi_pins,candidate['object'],candidate['image']]:B.checked(record)
    result=dict(verified=True,scope='test_only_fault_aliases_and_exact_original_object_Win64_ABI',candidate=B.artifact(path),
        failure_cases=cases,ABI_calls=abi_calls,ABI_original_owner_object_reused=True,
        observer_only_explicit_import_aliases=True,observer_all_nondebug_bytes_aux_and_relocations_verified=True,
        inputs=[driver,host,*pins,*abi_pins],Java_executed=False,game_started=False)
    B.write(output/'execution.json',result);return output/'execution.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(run(a.candidate.resolve(),a.output.resolve()))
