"""Source/machine proof for an unregistered assembly JIMAGE mapping owner."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom/jimage-owner'
KERNEL=ROOT/'native/kernels/jimage_owner64.asm.inc'
TOOLS=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64')
SDK=Path('C:/Program Files (x86)/Windows Kits/10/Lib/10.0.26100.0/um/x64/kernel32.lib')
EXPORTS={"boom_jimage_owner_"+n for n in ('init','open','lookup','release','close')}
IMPORTS={'AcquireSRWLockExclusive','ReleaseSRWLockExclusive','CreateFileW','GetFileSizeEx','CreateFileMappingW',
         'MapViewOfFile','UnmapViewOfFile','CloseHandle','GetLastError','VirtualAlloc','VirtualFree'}
STATUS=dict(ok=0,miss=1,busy=2,arguments=3,OS=4,pool=5,token=6,capacity=7,path=8,closed=9,image=10,endian=11,cleanup_pending=12)
ABI=dict(owner_bytes=128,job_bytes=64,calling_convention='Windows_x64',status_codes=STATUS,
    owner_states=dict(ready=1,closed=2,draining_after_cleanup_failure=3),exact_UTF16_keys=True,
    lookup_acquires_lease=True,open_acquires_lease=True,close_requires_zero_leases=True,Java_oop_roots=False,
    little_endian_JIMAGE_1_0_only=True,getNativeMap_or_Java_execution_implemented=False)
PINS={'NativeImageBuffer.cpp':'31eed6d4d7e45595c883a239d6cc228709ac59cb6dfe11010b60de7ddbfd03cb',
 'imageFile.cpp':'1484ea4c11a226cb8b795d4a36ce797bf1e9496c3d7f26b34f3c1cdb489a03f2',
 'imageFile.hpp':'dec917541c8cb7f112a6b230b44633c0a4367ab728f5ebce47f6644327d8b44f'}


def check(value,message):
    if not value:raise ValueError(message)


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(path),size=path.stat().st_size,sha256=sha)


def checked(row):
    check(artifact(row['path'])==row,'Sealed owner input changed: '+row['path']);return Path(row['path'])


def write(path,row):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(row,indent=2,sort_keys=True)+'\n')


def sources():
    pins=[]
    for name,sha in PINS.items():
        row=artifact(ROOT/'.boom/jimage-native-map/pinned-sources/jdk-21.0.13+3'/name)
        check(row['sha256']==sha,'Original fixed JIMAGE source pin differs: '+name)
        pins.append(dict(artifact=row,url='https://raw.githubusercontent.com/openjdk/jdk21u/jdk-21.0.13%2B3/src/java.base/share/native/libjimage/'+name))
    return dict(kernel=artifact(KERNEL),producer=artifact(__file__),primary_sources=pins)


def assembly():return 'option casemap:none\n'+KERNEL.read_text(encoding='utf-8')+'\nEND\n'


def normalized_coff(path):
    """Seal execution bytes, flags, full symbols and normalized relocation targets.

    This reader streams private metadata symbols instead of retaining millions
    of Python dictionaries for the original method table. Only assembler file
    names/debug sections and physical table offsets/timestamp are excluded.
    """
    raw=Path(path).read_bytes();check(len(raw)>=20,'Truncated owner COFF')
    machine,count,_,symbol_at,symbol_count,optional,characteristics=struct.unpack_from('<HHIIIHH',raw)
    check(machine==0x8664 and count>0 and optional==0 and 20+count*40<=symbol_at and
        symbol_at+18*symbol_count+4<=len(raw),'Invalid AMD64 owner COFF header')
    strings=symbol_at+18*symbol_count;string_size=struct.unpack_from('<I',raw,strings)[0]
    check(string_size>=4 and strings+string_size==len(raw),'Invalid owner COFF string table')
    sections={};by_id={};allowed={'.text','.text$mn','.data','.bss','.rdata','.pdata','.xdata','.debug$S'}
    for ident in range(1,count+1):
        at=20+(ident-1)*40;name=raw[at:at+8].rstrip(b'\0').decode('ascii')
        virtual_size,virtual_address,size,data,reloc,line,nrel,nline,flags=struct.unpack_from('<IIIIIIHHI',raw,at+8)
        check(name in allowed and name not in sections and virtual_size==virtual_address==line==nline==0,
            'Unexpected owner COFF section/line metadata')
        check((name=='.bss' and data==0) or (size==0 and data==0) or 20+count*40<=data and data+size<=symbol_at,
            'Owner COFF section bytes escape their range')
        if flags&0x01000000:
            check(nrel==65535 and reloc+10<=symbol_at,'Invalid methods relocation overflow')
            total,si,kind=struct.unpack_from('<IIH',raw,reloc)
            check(total>65535 and si==kind==0,'Invalid methods relocation sentinel');nrel=total-1;reloc+=10
        check(not nrel or 20+count*40<=reloc and reloc+10*nrel<=symbol_at,'Invalid methods relocation range')
        row=dict(name=name,size=size,data=data,reloc=reloc,nrel=nrel,flags=flags&~0x01000000)
        sections[name]=row;by_id[ident]=row
    primaries=bytearray(symbol_count);symbol_hash=hashlib.sha256();defined_symbols=0;exports=set();imports=set()
    def symbol(index):
        check(index<symbol_count,'COFF relocation target is outside the actual symbol table')
        at=symbol_at+18*index;name=raw[at:at+8]
        if name[:4]==b'\0'*4:
            offset=struct.unpack_from('<I',name,4)[0];check(4<=offset<string_size,'Invalid owner COFF name offset')
            end=raw.find(b'\0',strings+offset,strings+string_size);check(end>=0,'Unterminated owner COFF name')
            name=raw[strings+offset:end]
        else:name=name.rstrip(b'\0')
        value,section,kind,storage,aux=struct.unpack_from('<IhHBB',raw,at+8)
        check(section<=count and index+aux<symbol_count,'Invalid owner COFF symbol record')
        return (name.decode('ascii'),value,by_id[section]['name'] if section>0 else section,kind,storage),aux
    index=0
    while index<symbol_count:
        row,aux=symbol(index);primaries[index]=1
        if row[4]==2:
            if isinstance(row[2],str):exports.add(row[0])
            elif row[2]==0:imports.add(row[0])
            else:raise ValueError('External absolute owner symbol is forbidden')
        if row[4]!=103 and row[2]!='.debug$S':
            aux_bytes=raw[symbol_at+(index+1)*18:symbol_at+(index+1+aux)*18]
            symbol_hash.update(json.dumps((row,aux_bytes.hex()),separators=(',',':')).encode()+b'\n');defined_symbols+=1
        index+=aux+1
    result={}
    widths={1:8,2:4,3:4,4:4,5:4,6:4,7:4,8:4,9:4,10:2,11:4}
    for name,section in sections.items():
        if name=='.debug$S':continue
        data=raw[section['data']:section['data']+section['size']] if name!='.bss' else b''
        digest=hashlib.sha256();previous=-1
        for i in range(section['nrel']):
            offset,index,kind=struct.unpack_from('<IIH',raw,section['reloc']+10*i)
            check(index<symbol_count and primaries[index] and kind in widths and previous<=offset and
                offset+widths[kind]<=len(data),'Invalid/overlapping owner COFF relocation')
            row,_=symbol(index);check(row[4]!=103 and row[2]!='.debug$S','Execution relocation targets a filename/debug symbol')
            addend=data[offset:offset+widths[kind]].hex()
            digest.update(json.dumps((offset,kind,addend,row),separators=(',',':')).encode()+b'\n');previous=offset+widths[kind]
        result[name]=dict(size=section['size'],flags=section['flags'],raw_sha256=hashlib.sha256(data).hexdigest(),
                          relocations=section['nrel'],normalized_relocations_sha256=digest.hexdigest())
    check('.pdata' in result and '.xdata' in result and result['.pdata']['size']%12==0 and
        result['.pdata']['relocations']==result['.pdata']['size']//4,'Missing/incomplete owner native x64 unwind table')
    return dict(machine=machine,characteristics=characteristics,sections=result,exports=sorted(exports),imports=sorted(imports),
        nondebug_primary_symbols=defined_symbols,nondebug_symbols_sha256=symbol_hash.hexdigest())


def response(obj,dll,library):
    return '\n'.join(['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO',
        '/OUT:"'+str(dll)+'"',*['/EXPORT:'+n for n in sorted(EXPORTS)],'"'+str(obj)+'"','"'+str(library)+'"'])+'\n'


def compile_image(output,assembler,linker,library):
    output.mkdir(parents=True);source,obj,dll,rsp=(output/n for n in ('owner.asm','owner.obj','owner.dll','link.rsp'))
    source.write_text(assembly(),encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('xb') as log:
        subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    rsp.write_text(response(obj,dll,library),encoding='utf-8',newline='\n')
    with (output/'linker.log').open('xb') as log:
        subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    return source,obj,dll,rsp


def verify(path):
    path=Path(path).resolve();check(path.is_relative_to(ART),'Isolated owner candidate required')
    row=json.loads(path.read_text(encoding='utf-8'));check(row['schema']==1 and row['abi']==ABI and row['sources']==sources(),
        'Owner source or ABI differs')
    check(all(row.get(k) is False for k in ('registered','executed','game_started')),'Owner candidate scope differs')
    source,obj,dll,rsp=(checked(row[k]) for k in ('assembly','object','image','response'))
    assembler,linker,library=(checked(row[k]) for k in ('assembler','linker','kernel32'))
    check(source.read_text(encoding='utf-8')==assembly() and rsp.read_text(encoding='utf-8')==response(obj,dll,library),
        'Owner canonical ASM or exact LINK response differs')
    fresh=ART/'machine-checks'/uuid4().hex;_,canonical_obj,canonical_image,_=compile_image(fresh,assembler,linker,library)
    actual=normalized_coff(obj);expected=normalized_coff(canonical_obj)
    check(actual==expected,'Actual owner instructions/sections/symbol-aux/relocations/unwind differ from canonical')
    check(actual['exports']==sorted(EXPORTS) and actual['imports']==sorted(IMPORTS),'Actual owner Win32 imports or exports differ')
    check(all(not s['size'] for n,s in actual['sections'].items() if n in ('.data','.bss')),'Owner mutable global data forbidden')
    check(dll.read_bytes()==canonical_image.read_bytes(),'Actual complete owner PE differs from canonical')
    check(row['sources']==sources(),'Owner source changed during verification')
    for k in ('assembly','object','image','response','assembler','linker','kernel32'):checked(row[k])
    return dict(verified=True,scope='unregistered_real_readonly_JIMAGE_owner_source_all_nondebug_COFF_and_PE',
        candidate=artifact(path),normalized_COFF_sha256=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest(),
        complete_PE_sha256=artifact(dll)['sha256'],exports=sorted(EXPORTS),Win32_imports=sorted(IMPORTS),mutable_globals=False,
        Java_native_bridge=False,registered=False,executed=False,game_started=False)


def build(output,assembler=TOOLS/'ml64.exe',linker=TOOLS/'link.exe',library=SDK):
    output=Path(output).resolve();check(output.is_relative_to(ART) and not output.exists(),'Fresh isolated owner output required')
    assembler,linker,library=(Path(p).resolve() for p in (assembler,linker,library))
    before=sources();tools={k:artifact(v) for k,v in [('assembler',assembler),('linker',linker),('kernel32',library)]}
    source,obj,dll,rsp=compile_image(output,Path(assembler),Path(linker),Path(library))
    check(sources()==before,'Owner build source changed')
    for row in tools.values():checked(row)
    row=dict(schema=1,abi=ABI,sources=before,assembly=artifact(source),object=artifact(obj),image=artifact(dll),response=artifact(rsp),
        **tools,registered=False,executed=False,game_started=False)
    path=output/'candidate.json';write(path,row);write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('build','verify'))
    p.add_argument('--candidate',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    if a.action=='build':print(build(a.output))
    else:print(json.dumps(verify(a.candidate),indent=2))
