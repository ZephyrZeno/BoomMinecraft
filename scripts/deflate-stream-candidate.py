"""Build/verify an unregistered caller-owned incremental raw-DEFLATE ASM kernel."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom/deflate-stream'
KERNEL=ROOT/'native/kernels/deflate_stream64.asm.inc'
HELPER=ROOT/'scripts/deflate-raw-candidate.py'
spec=importlib.util.spec_from_file_location('stream_artifacts',HELPER)
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
check,artifact,checked,write=C.check,C.artifact,C.checked,C.write
EXPORTS={'boom_deflate_stream_reset','boom_deflate_stream_step'}
ABI=dict(state_bytes=34304,job_bytes=80,history_offset=1536,history_bytes=32768,calling_convention='Windows_x64',
    exports=sorted(EXPORTS),flags={'END_INPUT':1},status_codes={'finished':0,'need_input':1,'need_output':2,'arguments':3,'truncated':4,'block':5,'Huffman':6,'symbol_or_repeat':7,'distance':8,'invalid_state':9})


def sources():
    pins=[]
    for name,(url,sha) in C.PINS.items():
        row=artifact(C.ART/'pinned-sources'/name);check(row['sha256']==sha,'Pinned primary changed: '+name)
        pins.append(dict(url=url,artifact=row))
    java=artifact(ART/'pinned-sources/Inflater.java')
    check(java['sha256']=='ff3c671a1a8fab21d4258c2f73a88e77e84825b64df9a7c667f1966fd2a92b7d','Locked JDK21 Inflater.java differs')
    pins.append(dict(url='https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/classes/java/util/zip/Inflater.java',artifact=java))
    return dict(kernel=artifact(KERNEL),producer=artifact(__file__),artifact_helper=artifact(HELPER),coff_reader=artifact(C.READER),primary_sources=pins)


def assembly():return 'option casemap:none\n'+KERNEL.read_text(encoding='utf-8')+'\nEND\n'


def coff(path):
    spec=importlib.util.spec_from_file_location('stream_coff_reader',C.READER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);obj=module.Coff(path)
    def symbol(r):return (r['name'],r['value'],obj.by_section[r['section']]['name'] if r['section']>0 else r['section'],r['kind'],r['storage'])
    public={r['name'] for r in obj.index if r and r['storage']==2 and r['section']>0}
    imports={r['name'] for r in obj.index if r and r['storage']==2 and r['section']==0}
    check(public==EXPORTS and not imports,'Streaming kernel must have two exact exports and no imports')
    sections={}
    for name,row in obj.sections.items():
        if name=='.debug$S':continue
        check(name not in ('.data','.bss') or row['size']==0,'Mutable global decoder state forbidden')
        reloc=[]
        for offset,index,kind in row['reloc']:
            target=obj.index[index]
            check(target and target['storage']!=103 and (target['section']<=0 or obj.by_section[target['section']]['name']!='.debug$S'),'Execution relocation targets debug data')
            reloc.append((offset,kind,symbol(target)))
        sections[name]=(row['size'],row['flags'],hashlib.sha256(row['raw']).hexdigest(),reloc)
    return dict(sections=sections,symbols=sorted(symbol(r) for r in obj.index if r and r['storage']!=103 and (r['section']<=0 or obj.by_section[r['section']]['name']!='.debug$S')))


def pe(path):
    raw=Path(path).read_bytes();check(raw[:2]==b'MZ' and len(raw)>=64,'Missing PE DOS header')
    p=struct.unpack_from('<I',raw,60)[0]
    check(p+264<=len(raw) and raw[p:p+4]==b'PE\0\0','Missing PE header')
    machine,count,_,_,_,opsize,flags=struct.unpack_from('<HHIIIHH',raw,p+4);o=p+24
    check(machine==0x8664 and flags&0x2000 and opsize>=240 and struct.unpack_from('<H',raw,o)[0]==0x20b,'Expected AMD64 PE32+ DLL')
    check(struct.unpack_from('<I',raw,o+16)[0]==0,'Streaming DLL has an entry point')
    dirs=[struct.unpack_from('<II',raw,o+112+i*8) for i in range(16)]
    check(all(dirs[i]==(0,0) for i in (1,11,13,14)),'Decoder imports/bound/delay/CLR forbidden')
    sections=[]
    for i in range(count):
        at=o+opsize+i*40;check(at+40<=len(raw),'Truncated section table')
        name=raw[at:at+8].rstrip(b'\0').decode();size,rva,physical,offset=struct.unpack_from('<IIII',raw,at+8);f=struct.unpack_from('<I',raw,at+36)[0]
        check(offset+physical<=len(raw) and not f&0x80000000,'Writable/truncated PE section')
        sections.append(dict(name=name,size=size,rva=rva,physical=physical,offset=offset,flags=f))
    def data(rva,size):
        for r in sections:
            if r['rva']<=rva and rva+size<=r['rva']+min(r['size'],r['physical']):
                at=r['offset']+rva-r['rva'];return raw[at:at+size]
        raise ValueError('Directory outside PE section')
    def string(rva):
        result=bytearray()
        while True:
            byte=data(rva+len(result),1)[0]
            if byte==0:return result.decode('ascii')
            check(len(result)<4096,'Unterminated PE name');result.append(byte)
    export,size=dirs[0];check(export and size>=40,'Missing export directory')
    _,_,_,_,name,base,nfun,nnames,funcs,names,ordinals=struct.unpack('<IIHHIIIIIII',data(export,40))
    check(string(name)=='stream.dll' and base==1 and nfun==nnames==2,'Unexpected export shape')
    exported=[]
    for i in range(nnames):
        exported.append(string(struct.unpack('<I',data(names+4*i,4))[0]))
        ordinal=struct.unpack('<H',data(ordinals+2*i,2))[0];check(ordinal<2,'Invalid export ordinal')
        address=struct.unpack('<I',data(funcs+4*ordinal,4))[0]
        check(not export<=address<export+size and any(r['flags']&0x20000000 and r['rva']<=address<r['rva']+r['size'] for r in sections),'Export is forwarded or nonexecutable')
    check(exported==sorted(EXPORTS),'Unexpected public exports')
    return dict(machine=machine,exports=exported,imports=[],complete_image_sha256=hashlib.sha256(raw).hexdigest())


def response(obj,dll):
    return '\n'.join(['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO',
        '/OUT:"'+str(dll)+'"']+['/EXPORT:'+n for n in sorted(EXPORTS)]+['"'+str(obj)+'"'])+'\n'


def compile_image(output,assembler,linker):
    output.mkdir(parents=True);source,obj,dll,rsp=(output/n for n in ('stream.asm','stream.obj','stream.dll','link.rsp'))
    source.write_text(assembly(),encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('xb') as log:run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT)
    check(run.returncode==0,'ML64 failed; retain '+str(output/'assembler.log'))
    rsp.write_text(response(obj,dll),encoding='utf-8',newline='\n')
    with (output/'linker.log').open('xb') as log:run=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    check(run.returncode==0,'LINK failed; retain '+str(output/'linker.log'));return source,obj,dll,rsp


def verify(path):
    path=Path(path).resolve();check(path.is_relative_to(ART),'Isolated streaming candidate required')
    row=json.loads(path.read_text(encoding='utf-8'));check(row['sources']==sources() and row['abi']==ABI,'Streaming source/ABI pins differ')
    source,obj,dll,rsp=(checked(row[n]) for n in ('assembly','object','image','response'))
    assembler,linker=(checked(row[n]) for n in ('assembler','linker'))
    check(source.read_text(encoding='utf-8')==assembly() and rsp.read_text(encoding='utf-8')==response(obj,dll),'ASM or exact link arguments differ')
    canonical=ART/'machine-checks'/uuid4().hex;_,expected_obj,expected_dll,_=compile_image(canonical,assembler,linker)
    actual=coff(obj);check(actual==coff(expected_obj),'Actual streaming COFF bytes/symbols/relocations/unwind differ')
    image=pe(dll);check(image==pe(expected_dll),'Actual streaming complete PE differs')
    check(row['sources']==sources(),'Sources changed during machine verification')
    for name in ('assembly','object','image','response','assembler','linker'):checked(row[name])
    return dict(verified=True,scope='unregistered_incremental_raw_RFC1951_complete_actual_machine_image',candidate=artifact(path),
        canonical_source=artifact(canonical/'stream.asm'),canonical_object=artifact(expected_obj),canonical_image=artifact(expected_dll),
        normalized_coff_sha256=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest(),complete_image_sha256=image['complete_image_sha256'],
        no_imports=True,no_mutable_globals=True,registered=False,inflater_compatible=False,execution_verified=False,game_started=False)


def build(output,assembler,linker):
    output=Path(output).resolve();check(output.is_relative_to(ART) and not output.exists(),'Fresh isolated streaming output required')
    before=sources();assembler,linker=Path(assembler).resolve(),Path(linker).resolve();tools=dict(assembler=artifact(assembler),linker=artifact(linker))
    source,obj,dll,rsp=compile_image(output,assembler,linker)
    check(before==sources() and tools==dict(assembler=artifact(assembler),linker=artifact(linker)),'Streaming build inputs changed')
    row=dict(schema=1,sources=before,abi=ABI,assembly=artifact(source),object=artifact(obj),image=artifact(dll),response=artifact(rsp),**tools,
        registered=False,inflater_compatible=False,executed=False,game_started=False)
    path=output/'candidate.json';write(path,row);write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('build','verify'));p.add_argument('--candidate',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--assembler',type=Path,default=C.TOOLS/'ml64.exe');p.add_argument('--linker',type=Path,default=C.TOOLS/'link.exe');a=p.parse_args()
    if a.action=='build':print(build(a.output,a.assembler,a.linker))
    else:print(json.dumps(verify(a.candidate),indent=2))
