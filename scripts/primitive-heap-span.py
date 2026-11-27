"""Build and independently verify the frozen-ABI primitive heap span helper.

All tool/runtime paths are explicit. Outputs stay in fresh project .boom paths;
this tool never rebuilds a runtime, Java, a provider set, or a VM selection.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

KERNEL=Path(__file__).resolve().parents[1]/'native/kernels/primitive_heap_span64.asm.inc'
SYMBOL='boom_primitive_heap_span'
ABI_SOURCES={
    'native/runtime/heap.asm':'ba4acbc5168484e757b03dec0f724e3ef0a847e5ea60092592c72a8adc353818',
    'native/runtime/arrays.asm':'395c83c9717d78a4b0a29b6c72d1d913680ebaa90e4f7cf567666e347f92c614',
    'native/runtime/objects.asm':'e45dfac599567e8da3741c6c20d467b74404f9c6530c11ca07e1b40913139ad4'}


def check(value,message):
    if not value:raise ValueError(message)


def project_root():
    for root in Path(__file__).resolve().parents:
        if (root/'AGENTS.md').is_file() and (root/'native/runtime/heap.asm').is_file():return root
    raise ValueError('An explicit project source workspace is required')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=sha))


def checked(row):
    expected=row.get('digest',row);actual=artifact(row['path'])
    check(all(actual['digest'][k]==expected[k] for k in ('size','sha256')),'Input changed: '+row['path'])
    if 'sha1' in expected:
        with Path(row['path']).open('rb') as stream:check(hashlib.file_digest(stream,'sha1').hexdigest()==expected['sha1'],'Source SHA1 differs')
    return Path(actual['path'])


def write(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:stream.write(json.dumps(value,indent=2)+'\n')


def fresh(path):
    path=Path(path).resolve()
    check(path.is_relative_to(project_root()/'.boom') and not path.exists(),'A fresh isolated project .boom directory is required')
    path.mkdir(parents=True);return path


def run(output,label,command):
    with (output/(label+'.log')).open('xb') as log:
        result=subprocess.run(list(map(str,command)),cwd=output,stdout=log,stderr=subprocess.STDOUT,timeout=45)
    write(output/(label+'-status.json'),dict(natural_exit_code=result.returncode,command=list(map(str,command))))
    check(result.returncode==0,'Natural stage failure preserved: '+label)


def coff_reader(source_root):
    path=Path(source_root)/'scripts/jimage-owner-candidate.py'
    spec=importlib.util.spec_from_file_location('primitive_span_complete_COFF',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def pe(path):
    data=Path(path).read_bytes();check(data[:2]==b'MZ','Expected PE')
    h=struct.unpack_from('<I',data,60)[0];check(data[h:h+4]==b'PE\0\0','Bad PE signature')
    machine,count=struct.unpack_from('<HH',data,h+4);size,flags=struct.unpack_from('<HH',data,h+20);opt=h+24
    check(machine==0x8664 and 1<=count<=96 and struct.unpack_from('<H',data,opt)[0]==0x20b,'Expected AMD64 PE32+')
    sections=[struct.unpack_from('<IIII',data,opt+size+i*40+8) for i in range(count)]
    def pos(rva):
        for _,va,raw_size,raw in sections:
            if va<=rva<va+raw_size:return raw+rva-va
        raise ValueError('PE RVA outside raw sections')
    def name(rva):
        at=pos(rva);end=data.find(b'\0',at,at+4096);check(end>=at,'Unterminated PE name');return data[at:end].decode('ascii')
    imports={};rva=struct.unpack_from('<I',data,opt+120)[0]
    if rva:
        at=pos(rva)
        for index in range(256):
            original,_,_,dll,first=struct.unpack_from('<IIIII',data,at+index*20)
            if not(original or dll or first):break
            check(dll and (original or first),'Invalid PE imports');thunk=pos(original or first);symbols=[]
            for i in range(65536):
                value=struct.unpack_from('<Q',data,thunk+i*8)[0]
                if not value:break
                symbols.append('#'+str(value&0xffff) if value>>63 else name(value+2))
            else:raise ValueError('PE import thunk limit')
            module=name(dll).lower();check(module not in imports,'Duplicate PE import module');imports[module]=symbols
        else:raise ValueError('PE import directory limit')
    exports=[];rva=struct.unpack_from('<I',data,opt+112)[0]
    if rva:
        at=pos(rva);names=struct.unpack_from('<I',data,at+24)[0];table=pos(struct.unpack_from('<I',data,at+32)[0])
        check(names<=65536,'PE export name count limit')
        exports=[name(struct.unpack_from('<I',data,table+i*4)[0]) for i in range(names)]
    return dict(dll=bool(flags&0x2000),entry_rva=struct.unpack_from('<I',data,opt+16)[0],imports=imports,exports=exports)


def runtime_contract(runtime,source_root):
    runtime=Path(runtime).resolve();runtime=runtime/'boom-runtime.dll' if runtime.is_dir() else runtime
    source_root=Path(source_root).resolve();meta_file=runtime.with_name('runtime.json');meta=read(meta_file)
    check(meta['implementation_language']=='x86-64 MASM assembly' and
          all(meta[k] is False for k in ('java_runtime','rust_runtime','c_runtime')) and
          artifact(runtime)['digest']['sha256']==meta['sha256'],'The explicit runtime is not its sealed pure-ASM binary')
    records=[artifact(p) for p in (runtime,runtime.with_suffix('.lib'),meta_file)]
    for group in ('sources','data_sources'):
        for relative,digest in meta[group].items():
            path=(source_root/relative).resolve()
            check(not Path(relative).is_absolute() and path.is_relative_to(source_root),'Runtime source escaped source root')
            row=artifact(path);check(row['digest']['sha256']==digest,'Actual runtime source differs: '+relative);records.append(row)
    check(all(meta['sources'].get(path)==sha for path,sha in ABI_SOURCES.items()),'Unsupported frozen heap/arrays/object ABI')
    image=pe(runtime);allowed={'kernel32.dll','kernelbase.dll','ntdll.dll','user32.dll','ws2_32.dll','bcrypt.dll',
                            'advapi32.dll','shell32.dll','ole32.dll'}
    check(image['dll'] and all(n in allowed or n.startswith('api-ms-win-') for n in image['imports']),
          'Runtime imports a foreign execution engine or CRT')
    return dict(runtime=artifact(runtime),import_library=artifact(runtime.with_suffix('.lib')),metadata=artifact(meta_file),
        source_root=str(source_root),sources=records,pure_ASM=True,known_heap_array_object_ABI=True)


def assembly(kernel):
    text=Path(kernel).read_text(encoding='utf-8')
    check(not re.search(r'(?m)^\s*(?:option\b|END\s*$)',text),'Kernel include must omit option/END wrappers')
    return 'option casemap:none\n'+text+'\nEND\n'


def assemble(output,label,assembler,source,obj):
    run(output,label,[assembler,'/nologo','/c','/Fo'+str(obj),source])


def link(output,label,linker,obj,dll,library,exports):
    rsp=output/(label+'.rsp')
    args=['/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/NODEFAULTLIB','/DYNAMICBASE','/NXCOMPAT','/HIGHENTROPYVA','/BREPRO',
          '/OUT:"'+str(dll)+'"','"'+str(obj)+'"']
    if library is not None:args.append('"'+str(library)+'"')
    args+=['/EXPORT:'+name for name in sorted(exports)]
    with rsp.open('x',encoding='utf-8') as stream:stream.write('\n'.join(args)+'\n')
    run(output,label,[linker,'@'+str(rsp)]);return rsp


def build(runtime,output,assembler,linker,source_root=None):
    source_root=project_root() if source_root is None else Path(source_root).resolve()
    contract=runtime_contract(runtime,source_root);reader=coff_reader(source_root)
    before=contract['sources']+[artifact(p) for p in (Path(__file__),KERNEL,assembler,linker,Path(reader.__file__))]
    output=fresh(output);source=output/'span.asm';source.write_text(assembly(KERNEL),encoding='utf-8',newline='\n')
    obj,dll=output/'span.obj',output/'span.dll';assemble(output,'assemble',assembler,source,obj)
    rsp=link(output,'link',linker,obj,dll,checked(contract['import_library']),{SYMBOL})
    shutil.copyfile(checked(contract['runtime']),output/'boom-runtime.dll')
    for row in before:checked(row)
    result=dict(schema=1,scope='standalone_primitive_heap_span_build_only',producer=artifact(__file__),kernel=artifact(KERNEL),
        tools=dict(assembler=artifact(assembler),linker=artifact(linker)),COFF_reader=artifact(reader.__file__),
        runtime_contract=contract,assembly=artifact(source),object=artifact(obj),DLL=artifact(dll),
        runtime_copy=artifact(output/'boom-runtime.dll'),link_response=artifact(rsp),inputs=before,
        exports=[SYMBOL],imports=['boom_heap_contains'],registered=False,executed=False,
        original_Runtime_or_Java_rebuilt=False,SourceV_or_VM_executed=False,runtime_acceptance_complete=False)
    write(output/'helper.json',result);return output/'helper.json'


def verify(inputs,output,runtime,reference_assembly=None,reference_object=None):
    inputs=Path(inputs).resolve();input_pin=artifact(inputs);m=read(inputs);check(m['schema']==1 and m['scope']=='standalone_primitive_heap_span_build_only',
        'Explicit helper build inputs required')
    check(m['exports']==[SYMBOL] and m['imports']==['boom_heap_contains'] and
          all(m[k] is False for k in ('registered','executed','original_Runtime_or_Java_rebuilt',
              'SourceV_or_VM_executed','runtime_acceptance_complete')),'Helper build scope or symbol declaration differs')
    check(m['producer']['digest']==artifact(__file__)['digest'] and m['kernel']['digest']==artifact(KERNEL)['digest'],
          'Current helper producer/kernel differ')
    for row in m['inputs']:checked(row)
    current=runtime_contract(runtime,m['runtime_contract']['source_root']);check(current==m['runtime_contract'],'Explicit runtime differs')
    for key in ('assembly','object','DLL','runtime_copy','link_response','COFF_reader'):checked(m[key])
    check(checked(m['assembly']).read_text(encoding='utf-8')==assembly(KERNEL),'Actual source wrapper differs')
    expected_args=['/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/NODEFAULTLIB','/DYNAMICBASE','/NXCOMPAT','/HIGHENTROPYVA','/BREPRO',
        '/OUT:"'+str(checked(m['DLL']))+'"','"'+str(checked(m['object']))+'"',
        '"'+str(checked(current['import_library']))+'"','/EXPORT:'+SYMBOL]
    check(checked(m['link_response']).read_text().splitlines()==expected_args,'Helper canonical LINK arguments differ')
    output=fresh(output);canonical=output/'canonical.asm';canonical.write_text(assembly(KERNEL),encoding='utf-8',newline='\n')
    obj=output/'canonical.obj';assemble(output,'canonical-assemble',checked(m['tools']['assembler']),canonical,obj)
    reader=coff_reader(current['source_root']);check(artifact(reader.__file__)==m['COFF_reader'],'Complete COFF reader changed')
    actual_norm,expected_norm=reader.normalized_coff(checked(m['object'])),reader.normalized_coff(obj)
    check(actual_norm==expected_norm and set(actual_norm['exports'])=={SYMBOL} and
          set(actual_norm['imports'])=={'boom_heap_contains'},'Actual full COFF code/data/flags/symbol aux/relocs/unwind differ')
    image=pe(checked(m['DLL']));check(image==dict(dll=True,entry_rva=0,imports={'boom-runtime.dll':['boom_heap_contains']},exports=[SYMBOL]),
          'Helper PE imports/exports/entry differ')
    dll=output/'span.dll';rsp=link(output,'canonical-link',checked(m['tools']['linker']),obj,dll,
        checked(current['import_library']),{SYMBOL})
    check(artifact(dll)['digest']==m['DLL']['digest'],'Fresh canonical full PE bytes differ')
    reference=None
    check(bool(reference_assembly)==bool(reference_object),'Reference source and actual object must be supplied together')
    if reference_object:
        reference_pins=[artifact(reference_assembly),artifact(reference_object)]
        ref_text=Path(reference_assembly).read_text(encoding='utf-8')
        check(ref_text.count('option casemap:none\n')==1 and ref_text.endswith('END\n'),'Unknown original source wrappers')
        body=ref_text.replace('option casemap:none\n','',1)[:-4]
        check(body==KERNEL.read_text(encoding='utf-8') and reader.normalized_coff(reference_object)==actual_norm,
              'Original source/body or actual full COFF is not equivalent')
        reference_output=output/'original-reference';reference_output.mkdir()
        reference_dll=reference_output/'span.dll'
        reference_rsp=link(reference_output,'link',checked(m['tools']['linker']),checked(reference_pins[1]),
            reference_dll,checked(current['import_library']),{SYMBOL})
        check(artifact(reference_dll)['digest']==m['DLL']['digest'],'Original helper object full PE bytes differ')
        for row in reference_pins:checked(row)
        reference=dict(assembly=reference_pins[0],object=reference_pins[1],
            linked_DLL=artifact(reference_dll),link_response=artifact(reference_rsp),
            only_option_and_END_wrapping_changed=True,complete_machine_equivalence=True,full_PE_bytes_equal=True)
    for row in m['inputs']:checked(row)
    for key in ('assembly','object','DLL','runtime_copy','link_response','COFF_reader'):checked(m[key])
    checked(input_pin)
    check(runtime_contract(runtime,current['source_root'])==current,'Runtime changed during fresh verification')
    proof=dict(schema=1,verified=True,scope='fresh_canonical_complete_COFF_and_full_PE_primitive_heap_span_only',
        inputs=input_pin,current_verifier=artifact(__file__),kernel=artifact(KERNEL),COFF_reader=artifact(reader.__file__),
        canonical_assembly=artifact(canonical),canonical_object=artifact(obj),actual_object=m['object'],normalized=actual_norm,
        canonical_DLL=artifact(dll),actual_DLL=m['DLL'],canonical_link=artifact(rsp),complete_COFF_equal=True,
        section_flags_symbol_values_types_storage_aux_relocations_pdata_xdata_verified=True,full_PE_bytes_equal=True,
        actual_PE=image,original_reference=reference,runtime_contract=current,
        native_or_Java_execution=False,registered=False,runtime_acceptance_complete=False,game_started=False)
    write(output/'verification.json',proof);return output/'verification.json'


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('--runtime',type=Path,required=True);b.add_argument('--output',type=Path,required=True)
    b.add_argument('--assembler',type=Path,required=True);b.add_argument('--linker',type=Path,required=True);b.add_argument('--runtime-source-root',type=Path)
    v=sub.add_parser('verify');v.add_argument('--runtime',type=Path,required=True);v.add_argument('--inputs',type=Path,required=True)
    v.add_argument('--output',type=Path,required=True);v.add_argument('--reference-assembly',type=Path);v.add_argument('--reference-object',type=Path)
    a=p.parse_args()
    if a.command=='build':result=build(a.runtime,a.output,a.assembler,a.linker,a.runtime_source_root)
    else:result=verify(a.inputs,a.output,a.runtime,a.reference_assembly,a.reference_object)
    print(json.dumps(dict(output=artifact(result)),indent=2))


if __name__=='__main__':main()
