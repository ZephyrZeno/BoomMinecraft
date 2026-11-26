"""Build and independently reassemble an unregistered one-shot RFC1951 ASM kernel."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom/deflate-raw'
KERNEL=ROOT/'native/kernels/deflate_raw64.asm.inc'
READER=ROOT/'scripts/parallel-diagnostic-assembly-candidate.py'
TOOLS=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64')
PINS={
    'rfc1951.txt':('https://www.rfc-editor.org/rfc/rfc1951.txt','5ebf4b5b7fe1c3a0c0ab9aa3ac8c0f3853a7dc484905e76e03b0b0f301350009'),
    'Inflater.c':('https://raw.githubusercontent.com/openjdk/jdk21u/jdk-21.0.13%2B3/src/java.base/share/native/libzip/Inflater.c','b1e0fddcb21a0f99dcf80fdf500245b7bf76991445cb8b21a52787250e30ddae')}
ABI=dict(job_bytes=64,calling_convention='Windows_x64',export='boom_deflate_raw64',status_codes={'ok':0,'arguments':1,'truncated':2,'output_full':3,'block':4,'Huffman':5,'symbol_or_repeat':6,'distance':7})


def check(value,message):
    if not value:raise ValueError(message)


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(path),size=path.stat().st_size,sha256=sha)


def checked(row):
    check(artifact(row['path'])==row,'Sealed input/output changed: '+row['path'])
    return Path(row['path'])


def write(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as out:
        out.write(json.dumps(value,indent=2,sort_keys=True)+'\n')


def sources():
    pins=[]
    for name,(url,sha) in PINS.items():
        row=artifact(ART/'pinned-sources'/name)
        check(row['sha256']==sha,'Pinned primary source differs: '+name)
        pins.append(dict(url=url,artifact=row))
    return dict(kernel=artifact(KERNEL),producer=artifact(__file__),coff_reader=artifact(READER),primary_sources=pins)


def assembly():return 'option casemap:none\n'+KERNEL.read_text(encoding='utf-8')+'\nEND\n'


def coff(path):
    spec=importlib.util.spec_from_file_location('raw_deflate_coff',READER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    obj=module.Coff(path)
    def symbol(row):
        return (row['name'],row['value'],obj.by_section[row['section']]['name'] if row['section']>0 else row['section'],row['kind'],row['storage'])
    public={r['name'] for r in obj.index if r and r['storage']==2 and r['section']>0}
    imports={r['name'] for r in obj.index if r and r['storage']==2 and r['section']==0}
    check(public=={'boom_deflate_raw64'} and not imports,'Kernel must have exactly one public function and no imports')
    sections={}
    for name,row in obj.sections.items():
        if name=='.debug$S':continue
        check(name not in ('.data','.bss') or row['size']==0,'Mutable global decoder data is forbidden')
        reloc=[]
        for offset,index,kind in row['reloc']:
            target=obj.index[index]
            check(target and target['storage']!=103 and (target['section']<=0 or obj.by_section[target['section']]['name']!='.debug$S'),'Runtime relocation targets debug data')
            reloc.append((offset,kind,symbol(target)))
        sections[name]=(row['size'],row['flags'],hashlib.sha256(row['raw']).hexdigest(),reloc)
    symbols=sorted(symbol(r) for r in obj.index if r and r['storage']!=103 and (r['section']<=0 or obj.by_section[r['section']]['name']!='.debug$S'))
    return dict(sections=sections,symbols=symbols)


def pe(path):
    raw=Path(path).read_bytes()
    check(raw[:2]==b'MZ' and len(raw)>=64,'Missing DOS header')
    p=struct.unpack_from('<I',raw,60)[0]
    check(p+264<=len(raw) and raw[p:p+4]==b'PE\0\0','Truncated PE header')
    machine,count,_,_,_,opsize,flags=struct.unpack_from('<HHIIIHH',raw,p+4)
    o=p+24
    check(machine==0x8664 and flags&0x2000 and opsize>=240 and struct.unpack_from('<H',raw,o)[0]==0x20b,'Expected AMD64 PE32+ DLL')
    check(struct.unpack_from('<I',raw,o+16)[0]==0,'Standalone DLL must have no entry point')
    dirs=[struct.unpack_from('<II',raw,o+112+i*8) for i in range(16)]
    check(all(dirs[i]==(0,0) for i in (1,11,13,14)),'DLL imports/bound imports/delay imports/CLR are forbidden')
    sections=[]
    for i in range(count):
        at=o+opsize+i*40
        check(at+40<=len(raw),'Truncated PE section table')
        name=raw[at:at+8].rstrip(b'\0').decode('ascii')
        size,rva,physical,offset=struct.unpack_from('<IIII',raw,at+8)
        f=struct.unpack_from('<I',raw,at+36)[0]
        check(offset+physical<=len(raw) and not f&0x80000000,'Writable/truncated standalone DLL section')
        sections.append(dict(name=name,size=size,rva=rva,physical=physical,offset=offset,flags=f))
    def data(rva,size):
        for row in sections:
            if row['rva']<=rva and rva+size<=row['rva']+min(row['size'],row['physical']):
                at=row['offset']+rva-row['rva'];return raw[at:at+size]
        raise ValueError('PE directory pointer outside actual section data')
    def string(rva):
        result=bytearray()
        while True:
            byte=data(rva+len(result),1)[0]
            if byte==0:return result.decode('ascii')
            check(len(result)<4096,'Unterminated PE string');result.append(byte)
    export,size=dirs[0]
    check(export and size>=40,'Missing export directory')
    _,_,_,_,name,base,nfun,nnames,funcs,names,ordinals=struct.unpack('<IIHHIIIIIII',data(export,40))
    check(string(name)=='kernel.dll' and nfun==nnames==1 and base==1,'Unexpected export shape')
    check(string(struct.unpack('<I',data(names,4))[0])=='boom_deflate_raw64' and struct.unpack('<H',data(ordinals,2))[0]==0,'Unexpected public export')
    address=struct.unpack('<I',data(funcs,4))[0]
    check(not export<=address<export+size,'Forwarded decoder export forbidden')
    check(any(row['flags']&0x20000000 and row['rva']<=address<row['rva']+row['size'] for row in sections),'Decoder export is not executable')
    # /BREPRO makes the complete independently linked PE deterministic. Keep
    # every header, physical padding byte and directory covered as well.
    return dict(machine=machine,directories=dirs,sections=[(r['name'],r['size'],r['rva'],r['flags'],hashlib.sha256(raw[r['offset']:r['offset']+r['size']]).hexdigest()) for r in sections],export_rva=address,complete_image_sha256=hashlib.sha256(raw).hexdigest())


def response(obj,dll):
    return '\n'.join(['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(dll)+'"','/EXPORT:boom_deflate_raw64','"'+str(obj)+'"'])+'\n'


def compile_image(output,assembler,linker):
    output.mkdir(parents=True)
    source,obj,dll,rsp=(output/name for name in ('kernel.asm','kernel.obj','kernel.dll','link.rsp'))
    source.write_text(assembly(),encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('xb') as log:
        run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT)
    check(run.returncode==0,'ML64 failed; retain '+str(output/'assembler.log'))
    rsp.write_text(response(obj,dll),encoding='utf-8',newline='\n')
    with (output/'linker.log').open('xb') as log:
        run=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    check(run.returncode==0,'LINK failed; retain '+str(output/'linker.log'))
    return source,obj,dll,rsp


def verify(path):
    path=Path(path).resolve();check(path.is_relative_to(ART),'Project-owned candidate required')
    candidate=json.loads(path.read_text(encoding='utf-8'))
    check(candidate['sources']==sources() and candidate['abi']==ABI,'Source/primary pins/ABI changed')
    source,obj,dll,rsp=(checked(candidate[name]) for name in ('assembly','object','image','response'))
    assembler,linker=(checked(candidate[name]) for name in ('assembler','linker'))
    check(source.read_text(encoding='utf-8')==assembly() and rsp.read_text(encoding='utf-8')==response(obj,dll),'ASM or exact link arguments differ')
    output=ART/'independent-machine-checks'/uuid4().hex
    _,expected_obj,expected_dll,_=compile_image(output,assembler,linker)
    actual=coff(obj)
    check(actual==coff(expected_obj),'Actual COFF code/data/symbols/relocations/unwind differ from independent source assembly')
    image=pe(dll)
    check(image==pe(expected_dll),'Actual PE code/data/exports/unwind differ from independent canonical link')
    check(candidate['sources']==sources(),'Sources changed during independent machine check')
    for name in ('assembly','object','image','response','assembler','linker'):checked(candidate[name])
    return dict(verified=True,scope='unregistered_one_shot_raw_RFC1951_source_and_complete_actual_machine_image',candidate=artifact(path),
        canonical_object=artifact(expected_obj),canonical_image=artifact(expected_dll),canonical_assembly=artifact(output/'kernel.asm'),
        normalized_coff_sha256=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest(),
        normalized_pe_sha256=hashlib.sha256(json.dumps(image,sort_keys=True).encode()).hexdigest(),
        imports=[],mutable_global_data=False,registered=False,inflater_compatible=False,execution_verified=False,game_started=False)


def build(output,assembler,linker):
    output=Path(output).resolve();check(output.is_relative_to(ART) and not output.exists(),'Fresh project-owned output required')
    before=sources();assembler,linker=Path(assembler).resolve(),Path(linker).resolve()
    toolpins=dict(assembler=artifact(assembler),linker=artifact(linker))
    source,obj,dll,rsp=compile_image(output,assembler,linker)
    check(before==sources() and toolpins==dict(assembler=artifact(assembler),linker=artifact(linker)),'Build inputs changed')
    candidate=dict(schema=1,sources=before,assembly=artifact(source),object=artifact(obj),image=artifact(dll),response=artifact(rsp),**toolpins,
        abi=ABI,
        registered=False,inflater_compatible=False,executed=False,game_started=False)
    path=output/'candidate.json';write(path,candidate);write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('build','verify'))
    p.add_argument('--output',type=Path);p.add_argument('--candidate',type=Path)
    p.add_argument('--assembler',type=Path,default=TOOLS/'ml64.exe');p.add_argument('--linker',type=Path,default=TOOLS/'link.exe')
    a=p.parse_args()
    if a.action=='build':print(build(a.output,a.assembler,a.linker))
    else:print(json.dumps(verify(a.candidate),indent=2))
