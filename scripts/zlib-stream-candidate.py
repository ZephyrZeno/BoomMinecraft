"""Build/verify a source-pinned raw-stream + RFC1950/Adler32 ASM candidate."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom/zlib-stream'
KERNEL=ROOT/'native/kernels/zlib_stream64.asm.inc'
RAW_BUILDER=ROOT/'scripts/deflate-stream-candidate.py'
spec=importlib.util.spec_from_file_location('zlib_raw_builder',RAW_BUILDER)
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
check,artifact,checked,write=B.check,B.artifact,B.checked,B.write
RAW_SHA='6be97c2d2305ce6cc9dc0deb3f2781214525dd6ac8560d3a3b19c67689bbb3bd'
EXPORTS={'boom_adler32_update','boom_zlib_stream_reset','boom_zlib_stream_step'}
LAYOUT=dict(kernel_sha256=RAW_SHA,state_bytes=34304,magic=0x315354464c464544,phase=12,bit_count=32,
    stored_remaining=72,match_remaining=100,match_distance=104,pending_phases={'stored':4,'literal':10,'match':14,'finished':15})
ABI=dict(state_bytes=34560,raw_state_offset=256,job_bytes=96,adler_job_bytes=32,exports=sorted(EXPORTS),calling_convention='Windows_x64',raw_private_layout=LAYOUT,
    flags={'END_INPUT':1},status_codes=dict(B.ABI['status_codes'],zlib_header=10,Adler=11,need_dictionary_unsupported=12,CINFO_distance=13,internal=14))


def sources():
    pin=artifact(ART/'pinned-sources/rfc1950.txt')
    check(pin['sha256']=='8f0475a5c984657bf26277f73df9456c9b97f175084f0c1748f1eb1f0b9b10b9','RFC1950 primary pin differs')
    check(artifact(B.KERNEL)['sha256']==RAW_SHA,'Pinned raw private layout version changed')
    return dict(kernel=artifact(KERNEL),producer=artifact(__file__),raw_builder=artifact(RAW_BUILDER),
        artifact_helper=artifact(B.HELPER),coff_reader=artifact(B.C.READER),raw_kernel=artifact(B.KERNEL),
        primary_sources=[dict(url='https://www.rfc-editor.org/rfc/rfc1950.txt',artifact=pin)]+B.sources()['primary_sources'])


def raw_contract(path):
    path=Path(path).resolve();row=json.loads(path.read_text(encoding='utf-8'));receipt=path.with_name('verification.json')
    original=json.loads(receipt.read_text(encoding='utf-8'));actual=B.verify(path)
    check(original['candidate']==artifact(path) and original['verified'] is True and
        all(original[n]==actual[n] for n in ('normalized_coff_sha256','complete_image_sha256')),'Frozen raw verification differs from actual source/COFF/PE')
    check(row['abi']==B.ABI and row['sources']['kernel']['sha256']==RAW_SHA,'Raw ABI/private layout differs')
    return dict(candidate=artifact(path),verification=artifact(receipt),object=row['object'],image=row['image'],assembly=row['assembly'],
        complete_image_sha256=actual['complete_image_sha256'],normalized_coff_sha256=actual['normalized_coff_sha256'],layout=LAYOUT)


def assembly():return 'option casemap:none\n'+KERNEL.read_text(encoding='utf-8')+'\nEND\n'


def coff(path):
    spec=importlib.util.spec_from_file_location('zlib_coff_reader',B.C.READER)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);obj=m.Coff(path)
    def symbol(r):return (r['name'],r['value'],obj.by_section[r['section']]['name'] if r['section']>0 else r['section'],r['kind'],r['storage'])
    public={r['name'] for r in obj.index if r and r['storage']==2 and r['section']>0}
    imports={r['name'] for r in obj.index if r and r['storage']==2 and r['section']==0}
    check(public==EXPORTS and imports==B.EXPORTS,'Wrapper exports/raw imports differ')
    sections={}
    for name,row in obj.sections.items():
        if name=='.debug$S':continue
        check(name not in ('.data','.bss') or not row['size'],'Mutable global wrapper data forbidden')
        reloc=[]
        for offset,index,kind in row['reloc']:
            target=obj.index[index];check(target and target['storage']!=103 and (target['section']<=0 or obj.by_section[target['section']]['name']!='.debug$S'),'Execution relocation targets debug data')
            reloc.append((offset,kind,symbol(target)))
        sections[name]=(row['size'],row['flags'],hashlib.sha256(row['raw']).hexdigest(),reloc)
    return dict(sections=sections,symbols=sorted(symbol(r) for r in obj.index if r and r['storage']!=103 and (r['section']<=0 or obj.by_section[r['section']]['name']!='.debug$S')))


def pe(path):
    raw=Path(path).read_bytes();check(raw[:2]==b'MZ' and len(raw)>=64,'Invalid DOS header')
    p=struct.unpack_from('<I',raw,60)[0];check(p+264<=len(raw) and raw[p:p+4]==b'PE\0\0','Invalid PE header')
    machine,count,_,_,_,opsize,flags=struct.unpack_from('<HHIIIHH',raw,p+4);o=p+24
    check(machine==0x8664 and flags&0x2000 and opsize>=240 and struct.unpack_from('<H',raw,o)[0]==0x20b,'Expected AMD64 PE32+ DLL')
    check(struct.unpack_from('<I',raw,o+16)[0]==0,'Wrapper DLL entry point forbidden')
    dirs=[struct.unpack_from('<II',raw,o+112+8*i) for i in range(16)];check(all(dirs[i]==(0,0) for i in (1,11,13,14)),'Decoder imports/bound/delay/CLR forbidden')
    sections=[]
    for i in range(count):
        at=o+opsize+40*i;check(at+40<=len(raw),'Truncated section table')
        name=raw[at:at+8].rstrip(b'\0').decode();size,rva,physical,offset=struct.unpack_from('<IIII',raw,at+8);f=struct.unpack_from('<I',raw,at+36)[0]
        check(offset+physical<=len(raw) and not f&0x80000000,'Writable/truncated section');sections.append((name,size,rva,physical,offset,f))
    def data(rva,size):
        for _,n,v,physical,at,_ in sections:
            if v<=rva and rva+size<=v+min(n,physical):return raw[at+rva-v:at+rva-v+size]
        raise ValueError('PE directory outside section data')
    def string(rva):
        out=bytearray()
        while True:
            byte=data(rva+len(out),1)[0]
            if byte==0:return out.decode('ascii')
            check(len(out)<4096,'Unterminated export name');out.append(byte)
    export,size=dirs[0];check(export and size>=40,'Missing exports')
    _,_,_,_,name,base,nfun,nnames,funcs,names,ordinals=struct.unpack('<IIHHIIIIIII',data(export,40))
    check(string(name)=='zlib.dll' and base==1 and nfun==nnames==3,'Unexpected wrapper export shape')
    exported=[]
    for i in range(3):
        exported.append(string(struct.unpack('<I',data(names+4*i,4))[0]));ordinal=struct.unpack('<H',data(ordinals+2*i,2))[0]
        check(ordinal<3,'Bad export ordinal');address=struct.unpack('<I',data(funcs+ordinal*4,4))[0]
        check(not export<=address<export+size and any(f&0x20000000 and v<=address<v+n for _,n,v,_,_,f in sections),'Nonexecutable/forwarded export')
    check(exported==sorted(EXPORTS),'Unexpected wrapper export names')
    return dict(exports=exported,imports=[],complete_image_sha256=hashlib.sha256(raw).hexdigest())


def response(obj,dll,raw_obj):
    return '\n'.join(['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(dll)+'"']+
        ['/EXPORT:'+n for n in sorted(EXPORTS)]+['"'+str(obj)+'"','"'+str(raw_obj)+'"'])+'\n'


def compile_image(output,assembler,linker,raw_obj):
    output.mkdir(parents=True);source,obj,dll,rsp=(output/n for n in ('zlib.asm','zlib.obj','zlib.dll','link.rsp'))
    source.write_text(assembly(),encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('xb') as log:run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT)
    check(run.returncode==0,'ML64 failed; retain '+str(output/'assembler.log'));rsp.write_text(response(obj,dll,raw_obj),encoding='utf-8',newline='\n')
    with (output/'linker.log').open('xb') as log:run=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    check(run.returncode==0,'LINK failed; retain '+str(output/'linker.log'));return source,obj,dll,rsp


def verify(path):
    path=Path(path).resolve();check(path.is_relative_to(ART),'Isolated wrapper candidate required');row=json.loads(path.read_text(encoding='utf-8'))
    check(row['sources']==sources() and row['abi']==ABI,'Wrapper source/ABI/private-layout pins differ')
    raw=raw_contract(checked(row['raw']['candidate']));check(row['raw']==raw,'Actual frozen raw contract differs')
    source,obj,dll,rsp=(checked(row[n]) for n in ('assembly','object','image','response'));assembler,linker=(checked(row[n]) for n in ('assembler','linker'));raw_obj=checked(raw['object'])
    check(source.read_text(encoding='utf-8')==assembly() and rsp.read_text(encoding='utf-8')==response(obj,dll,raw_obj),'ASM/exact link arguments differ')
    canonical=ART/'machine-checks'/uuid4().hex;_,expected_obj,expected_dll,_=compile_image(canonical,assembler,linker,raw_obj)
    actual=coff(obj);check(actual==coff(expected_obj),'Actual wrapper COFF bytes/symbols/relocations/unwind differ')
    image=pe(dll);check(image==pe(expected_dll),'Actual wrapper complete PE differs')
    check(row['sources']==sources(),'Wrapper sources changed during verification')
    for n in ('assembly','object','image','response','assembler','linker'):checked(row[n])
    for n in ('candidate','verification','object','image','assembly'):checked(raw[n])
    return dict(verified=True,scope='unregistered_RFC1950_wrapper_Adler32_and_original_raw_kernel_actual_machine',candidate=artifact(path),raw_contract=raw,
        canonical_source=artifact(canonical/'zlib.asm'),canonical_object=artifact(expected_obj),canonical_image=artifact(expected_dll),
        normalized_coff_sha256=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest(),complete_image_sha256=image['complete_image_sha256'],
        imports=[],mutable_globals=False,raw_bytes_preserved=True,raw_private_layout_read_only=True,registered=False,JNI=False,inflater_compatible=False,execution_verified=False,game_started=False)


def build(raw_candidate,output,assembler,linker):
    output=Path(output).resolve();check(output.is_relative_to(ART) and not output.exists(),'Fresh isolated wrapper output required')
    before=sources();raw=raw_contract(raw_candidate);assembler,linker=Path(assembler).resolve(),Path(linker).resolve();tools=dict(assembler=artifact(assembler),linker=artifact(linker))
    source,obj,dll,rsp=compile_image(output,assembler,linker,checked(raw['object']))
    check(sources()==before and tools==dict(assembler=artifact(assembler),linker=artifact(linker)),'Wrapper inputs changed during build')
    row=dict(schema=1,sources=before,raw=raw,abi=ABI,assembly=artifact(source),object=artifact(obj),image=artifact(dll),response=artifact(rsp),**tools,
        registered=False,JNI=False,inflater_compatible=False,executed=False,game_started=False)
    path=output/'candidate.json';write(path,row);write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('build','verify'));p.add_argument('--candidate',type=Path);p.add_argument('--output',type=Path);p.add_argument('--raw-candidate',type=Path)
    p.add_argument('--assembler',type=Path,default=B.C.TOOLS/'ml64.exe');p.add_argument('--linker',type=Path,default=B.C.TOOLS/'link.exe');a=p.parse_args()
    if a.action=='build':print(build(a.raw_candidate,a.output,a.assembler,a.linker))
    else:print(json.dumps(verify(a.candidate),indent=2))
