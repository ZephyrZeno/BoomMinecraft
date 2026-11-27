"""Verify a separate RO JIMAGE scalar kernel and five typed Unsafe read tails."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('jimage_unsafe_candidate_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S,C,O,F,A,N=(module(n) for n in ('runtime-provider-source','jimage-unsafe-read-source','jimage-owner-candidate','native-frame-overlay','verify-batch-assembly','refresh-named-module-batch'))
ART=S.ART/'jimage-unsafe-read'
CORE=ROOT/'native/kernels/jimage_unsafe_read64.asm.inc'
WRAPPER=ROOT/'native/providers/jimage_unsafe_read.asm.inc'
EXPORTED_SCALAR='boom_jimage_owned_scalar_read'


def checked(record):
    path=Path(record['path']).resolve();expected=record.get('digest',record);actual=S.digest(path)
    S.check(all(actual[k]==expected[k] for k in ('size','sha256')),'JIMAGE read artifact changed: '+str(path))
    if 'sha1' in expected:
        with path.open('rb') as stream:S.check(hashlib.file_digest(stream,'sha1').hexdigest()==expected['sha1'],'Legacy source SHA1 changed')
    return path


def coff(path):
    raw=Path(path).read_bytes();machine,count,_,symbols,n,optional,_=struct.unpack_from('<HHIIIHH',raw)
    S.check(machine==0x8664 and optional==0 and symbols>=20+40*count and symbols+18*n+4<=len(raw),'Actual AMD64 COFF required')
    strings=symbols+18*n;size=struct.unpack_from('<I',raw,strings)[0];S.check(size>=4 and strings+size==len(raw),'COFF string range')
    sections={};names={};rows={};index=0
    for i in range(count):
        at=20+i*40;name=raw[at:at+8].rstrip(b'\0').decode();vs,va,length,offset,reloc,line,nr,nl,flags=struct.unpack_from('<IIIIIIHHI',raw,at+8)
        S.check(vs==va==line==nl==0 and not flags&0x01000000 and offset+length<=symbols and reloc+10*nr<=symbols,'Small COFF section ranges')
        names[i+1]=name;sections[name]=dict(data=raw[offset:offset+length],flags=flags,relocations=[struct.unpack_from('<IIH',raw,reloc+10*j) for j in range(nr)])
    while index<n:
        at=symbols+18*index;label=raw[at:at+8]
        if label[:4]==b'\0'*4:
            off=struct.unpack_from('<I',label,4)[0];S.check(4<=off<size,'COFF symbol name');end=raw.index(b'\0',strings+off,strings+size);label=raw[strings+off:end]
        else:label=label.rstrip(b'\0')
        value,section,kind,storage,aux=struct.unpack_from('<IhHBB',raw,at+8);S.check(section<=count and index+aux<n,'COFF symbol row')
        rows[index]=dict(name=label.decode(),value=value,section=names[section] if section>0 else section,kind=kind,storage=storage);index+=aux+1
    for section in sections.values():
        section['relocations']=[dict(offset=at,kind=kind,target=rows[index]) for at,index,kind in section['relocations']]
    return sections,{r['name']:r for r in rows.values() if r['storage']==2}


def prefix_proof(original,new,methods):
    before,old=coff(original);after,actual=coff(new)
    reads={f"boom_m{r['method']}_native" for r in methods if r['operation'] in C.KINDS}
    for name,row in old.items():
        if isinstance(row['section'],str):S.check(actual.get(name)==row,'Original native symbol offset/type changed: '+name)
    S.check(len([r for r in old.values() if isinstance(r['section'],str)])==84,'Original 42 native aliases required')
    changed=[];sections={}
    for name,section in before.items():
        if name.startswith('.debug'):continue
        expected=after[name];length=len(section['data'])
        S.check(section['data']==expected['data'][:length] and section['flags']==expected['flags'],'Original typed adapter instructions/data/unwind prefix changed: '+name)
        relocs=[r for r in expected['relocations'] if r['offset']<length];S.check(len(relocs)==len(section['relocations']),'Original typed relocation prefix count')
        for a,b in zip(section['relocations'],relocs):
            if a==b:continue
            candidates=[n for n in reads if old[n]['value']<=a['offset']<old[n]['value']+32]
            S.check(name in ('.text','.text$mn') and len(candidates)==1 and a['offset']==b['offset'] and a['kind']==b['kind']==4 and
                a['target']['name']=='boom_java_unsafe_memory' and b['target']['name']==C.SERVICE,'Only five terminal plain-read route relocations may differ')
            # Each native body is exactly LEA pool, MOV operation, JMP service.
            # Its one service relocation is the last instruction's disp32.
            entry=old[candidates[0]]['value'];S.check(section['data'][a['offset']-1]==0xe9 and a['offset']>entry,'Terminal native JMP relocation required')
            changed.append(candidates[0])
        sections[name]=dict(prefix_bytes=length,sha256=hashlib.sha256(section['data']).hexdigest(),relocations=len(relocs))
    S.check(sorted(changed)==sorted(reads),'Exactly five distinct plain native tails required')
    return dict(verified=True,unchanged_native_entry_aliases=84,unchanged_method_adapters=42,unchanged_other_native_routes=37,
        routed_plain_native_tails=sorted(reads),instruction_data_and_unwind_prefixes=sections,original=S.artifact(original),variant=S.artifact(new),original_runtime_DLL_changed=False)


def contract(state_file,owner_file):
    state_file,owner_file=Path(state_file).resolve(),Path(owner_file).resolve();state=S.read(state_file)
    S.check(state['current_source_provider_verification_complete'] is True and state['provider_count'] in (31,35) and
        state['status'] in ('accepted','pending_runtime_acceptance') and state['tool_sources']==S.tools_identity(),
        'Current 31/35 source-only provider state and tool namespace required')
    identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']));N.verified_resolver(Path(state['batch']),summary,Path(state['plan']))
    S.check(identity['batch_summary']['digest']['sha256']==state['batch_summary_sha256'] and identity['base_verification']['digest']['sha256']==state['batch_verification_sha256'],'Actual source batch/full proof changed')
    frame=Path(state['frame_manifest']);actual=F.verify(frame,Path(state['batch']),Path(state['plan']));S.check(actual==S.read(frame.with_name('verification.json')) and S.digest(frame.with_name('verification.json'))['sha256']==state['frame_verification_sha256'],'Actual frame proof differs')
    meta=C.index(summary,classes,S);runtime=Path(state['runtime']);runtime=runtime/'boom-runtime.dll' if runtime.is_dir() else runtime;rm=S.read(runtime.with_name('runtime.json'))
    S.check(S.digest(runtime)['sha256']==state['runtime_sha256']==rm['sha256'] and rm['sources']['native/runtime/java_unsafe_fields.asm']==meta['original_kernel']['digest']['sha256'],'Original typed runtime DLL/source differs')
    owner=S.read(owner_file);owner_proof=O.verify(owner_file);S.check(owner['sources']['kernel']['sha256']==C.OWNER_SHA,'Actual frozen owner object source differs')
    [unit]=summary['unsafe_memory']['units'];original=S.checked(unit['assembly']);body=''.join(C.G.body(r) for r in meta['methods'])
    S.check(original.read_text(encoding='utf-8').partition('.code\n')[2][:-5]==body,'Original typed unit source changed')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,runtime=S.artifact(runtime),original_unit=unit,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(frame.with_name('verification.json'))),
        mapping_owner=dict(candidate=O.artifact(owner_file),verification=owner_proof,object=owner['object']),
        bridge_source=S.artifact(ROOT/'native/providers/jimage_native_map.asm.inc'),bridge_ABI=meta['JMAP80'],
        bridge_runtime_linked_or_verified=False,tools=S.tools_identity(),
        sources={n:S.artifact(ROOT/n) for n in ('scripts/jimage-unsafe-read-source.py','scripts/jimage-unsafe-read-candidate.py','native/kernels/jimage_unsafe_read64.asm.inc','native/providers/jimage_unsafe_read.asm.inc')})


def assemble(source,obj,assembler,log):
    with Path(log).open('xb') as output:run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=output,stderr=subprocess.STDOUT)
    S.check(run.returncode==0,'Actual JIMAGE read assembly failed; retain '+str(log))


def compile_candidate(directory,metadata,assembler,linker,library):
    directory=Path(directory).resolve();assembler=Path(assembler).resolve();linker=Path(linker).resolve();library=Path(library).resolve()
    directory.mkdir(parents=True);source,obj,wrapper,wrapper_obj,core,core_obj,dll,rsp=(directory/n for n in ('typed.asm','typed.obj','wrapper.asm','wrapper.obj','scalar.asm','scalar.obj','scalar.dll','link.rsp'))
    text,exports,imports=C.assembly(metadata['source']);source.write_text(text,encoding='utf-8',newline='\n')
    wrapper_text,wrapper_exports,wrapper_imports=C.wrapper_assembly(metadata['source']);wrapper.write_text(wrapper_text,encoding='utf-8',newline='\n')
    core.write_text('option casemap:none\n'+CORE.read_text(encoding='utf-8')+'\nEND\n',encoding='utf-8',newline='\n')
    assemble(source,obj,assembler,directory/'typed-assembler.log');assemble(wrapper,wrapper_obj,assembler,directory/'wrapper-assembler.log');assemble(core,core_obj,assembler,directory/'scalar-assembler.log')
    S.check(A.coff_symbols(obj)==(exports,imports),'Actual typed variant symbol contract differs')
    S.check(A.coff_symbols(wrapper_obj)==(wrapper_exports,wrapper_imports),'Actual wrapper symbol contract differs')
    S.check(A.coff_symbols(core_obj,{'AcquireSRWLockShared','ReleaseSRWLockShared'})==({EXPORTED_SCALAR},{'AcquireSRWLockShared','ReleaseSRWLockShared'}),'Scalar imports/exports differ')
    owner=metadata['mapping_owner']['object'];owner_obj=O.checked(owner);public=O.EXPORTS|{EXPORTED_SCALAR}
    args=['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(dll)+'"',*['/EXPORT:'+n for n in sorted(public)],*['"'+str(p)+'"' for p in (core_obj,owner_obj,library)]]
    rsp.write_text('\n'.join(args)+'\n',encoding='utf-8',newline='\n')
    with (directory/'link.log').open('xb') as output:run=subprocess.run([str(linker),'@'+str(rsp)],stdout=output,stderr=subprocess.STDOUT)
    S.check(run.returncode==0,'Actual owner/scalar link failed')
    return dict(assembly=S.artifact(source),object=S.artifact(obj),wrapper_assembly=S.artifact(wrapper),wrapper_object=S.artifact(wrapper_obj),core_assembly=S.artifact(core),core_object=S.artifact(core_obj),image=S.artifact(dll),response=S.artifact(rsp))


def verify(path):
    path=Path(path).resolve();S.check(path.is_relative_to(ART),'Isolated JIMAGE Unsafe candidate required');row=S.read(path)
    meta=contract(S.checked(row['metadata']['input_state']),O.checked(row['metadata']['mapping_owner']['candidate']));S.check(row['metadata']==meta,'Current JIMAGE read source/model changed')
    generated=('assembly','object','wrapper_assembly','wrapper_object','core_assembly','core_object','image','response')
    for key in generated:S.check(checked(row[key]).is_relative_to(ART),'Generated candidate file outside isolated output')
    for key,value in [('assembler',O.TOOLS/'ml64.exe'),('linker',O.TOOLS/'link.exe'),('kernel32',O.SDK)]:
        S.check(row[key]==S.artifact(value),'Candidate replaced the actual fixed tool/library: '+key);checked(row[key])
    text,exports,imports=C.assembly(meta['source']);S.check(S.checked(row['assembly']).read_text(encoding='utf-8')==text,'Typed ASM differs')
    S.check(S.checked(row['core_assembly']).read_text(encoding='utf-8')=='option casemap:none\n'+CORE.read_text(encoding='utf-8')+'\nEND\n','Scalar ASM differs')
    S.check(S.checked(row['wrapper_assembly']).read_text(encoding='utf-8')==C.wrapper_assembly(meta['source'])[0],'Typed validation/route wrapper differs')
    prefix=prefix_proof(S.checked(meta['original_unit']['object']),S.checked(row['object']),meta['source']['methods'])
    fresh=compile_candidate(ART/'machine-checks'/uuid4().hex,meta,checked(row['assembler']),checked(row['linker']),checked(row['kernel32']))
    for name in ('object','wrapper_object','core_object'):S.check(O.normalized_coff(S.checked(row[name]))==O.normalized_coff(S.checked(fresh[name])),'Actual read code/data/symbols/relocations/unwind differs: '+name)
    S.check(S.checked(row['image']).read_bytes()==S.checked(fresh['image']).read_bytes(),'Actual complete scalar/owner PE differs from canonical')
    # The linker response is sealed and must enumerate only the two real
    # objects and kernel32 library, with a fixed complete export set.
    expected=S.checked(fresh['response']).read_text(encoding='utf-8').replace(str(S.checked(fresh['image'])),str(S.checked(row['image']))).replace(str(S.checked(fresh['core_object'])),str(S.checked(row['core_object'])))
    S.check(S.checked(row['response']).read_text(encoding='utf-8')==expected,'Scalar response changed')
    return dict(verified=True,scope='unregistered_RO_JIMAGE_scalar_COFF_PE_and_five_typed_native_route_variant',candidate=S.artifact(path),old_native_machine_prefix=prefix,
        scalar_machine=O.normalized_coff(S.checked(row['core_object'])),complete_scalar_PE_sha256=S.digest(S.checked(row['image']))['sha256'],
        real_owner_object_reused=True,bridge_runtime_linked_or_verified=False,original_Java_execution=False,arbitrary_off_heap=False,registered=False,full_selection_reverified=False,game_started=False)


def build(state,owner,output,assembler=O.TOOLS/'ml64.exe',linker=O.TOOLS/'link.exe',library=O.SDK):
    output=Path(output).resolve();S.check(output.is_relative_to(ART) and not output.exists(),'Fresh JIMAGE Unsafe output required');metadata=contract(state,owner)
    before=S.tools_identity();files=compile_candidate(output,metadata,Path(assembler),Path(linker),Path(library));row=dict(schema=1,metadata=metadata,**files,assembler=S.artifact(assembler),linker=S.artifact(linker),kernel32=S.artifact(library),registered=False,executed=False,game_started=False)
    S.check(before==S.tools_identity(),'Namespace changed during candidate construction');path=output/'candidate.json';S.write(path,row);S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('build','verify'));p.add_argument('--state',type=Path);p.add_argument('--owner',type=Path);p.add_argument('--output',type=Path);p.add_argument('--candidate',type=Path);a=p.parse_args()
    print(build(a.state,a.owner,a.output) if a.action=='build' else json.dumps(verify(a.candidate),indent=2))
