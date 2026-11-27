"""Unregistered source-bound copyMemory0: RO JIMAGE to normal heap byte[]."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('jimage_copy_candidate_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


RB=module('jimage-unsafe-read-candidate');S=RB.S;O=RB.O;C=module('jimage-unsafe-copy-source')
ART=S.ART/'jimage-unsafe-copy';CORE=ROOT/'native/kernels/jimage_unsafe_copy64.asm.inc'
WRAPPER=ROOT/'native/providers/jimage_unsafe_copy.asm.inc'
CORE_EXPORT='boom_jimage_owned_copy_to_bytes'
checked=RB.checked


def contract(state_file,owner_file,bridge_file):
    inherited=RB.contract(state_file,owner_file);state=S.read(state_file);identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(identity==inherited['base'],'Exact current source base required');source=C.index(summary,classes,S)
    declarations={r['id']:r for r in S.read(Path(state['frame_manifest']))['source']['original_native_declarations']}
    [method]=source['methods'];frame=declarations[method['method']]
    S.check(frame['flags']==32 and all(frame[k]==method[k] for k in ('class_id','class_sha256','loader','source_id','name','descriptor','access')),'Original copyMemory0 source/frame declaration differs')
    for record in source['source_kernels'].values():
        key='native/runtime/'+Path(record['path']).name;runtime=S.read(checked(inherited['runtime']).with_name('runtime.json'))
        S.check(runtime['sources'][key]==record['digest']['sha256'],'Copy uses different normal runtime kernels')
    for path in S.read(state['providers']):
        provider=S.read(path);S.check(method['method'] not in {r['method'] for r in provider['methods']},'copyMemory0 already has a provider')
    bridge_file=Path(bridge_file).resolve();bridge=S.read(bridge_file);receipt=bridge_file.with_name('verification.json');v=S.read(receipt)
    S.check(bridge['kernel']==S.artifact(ROOT/'native/providers/jimage_native_map.asm.inc') and bridge['metadata']['base']==identity,'Exact current JMAP source/ABI base required')
    # Pin the actual source/COFF receipt, without claiming Java bridge execution.
    S.check(v['verified'] is True and v['candidate']==S.artifact(bridge_file),'Actual source-bound bridge receipt differs')
    for key in ('assembly','object','kernel','tool'):checked(bridge[key])
    return dict(base=identity,input_state=S.artifact(state_file),source=source,runtime=inherited['runtime'],frame_overlay=inherited['frame_overlay'],
        mapping_owner=inherited['mapping_owner'],bridge_candidate=S.artifact(bridge_file),bridge_verification=S.artifact(receipt),bridge_source=bridge['kernel'],
        bridge_runtime_binding_verified=False,source_scalar_receiver_validator=S.artifact(ROOT/'scripts/jimage-unsafe-read-source.py'),tools=S.tools_identity(),
        sources={n:S.artifact(ROOT/n) for n in ('scripts/jimage-unsafe-copy-source.py','scripts/jimage-unsafe-copy-candidate.py','native/kernels/jimage_unsafe_copy64.asm.inc','native/providers/jimage_unsafe_copy.asm.inc')})


def response(image,objects,libraries,exports):
    return '\n'.join(['/NOLOGO','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/INCREMENTAL:NO','/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(image)+'"',*['/EXPORT:'+n for n in sorted(exports)],*['"'+str(p)+'"' for p in objects+libraries]])+'\n'


def compile_candidate(directory,metadata):
    directory=Path(directory).resolve();directory.mkdir(parents=True);assembler,linker=(O.TOOLS/n for n in ('ml64.exe','link.exe'));library=O.SDK.resolve()
    assembly,obj,core,core_obj,image,rsp=(directory/n for n in ('native.asm','native.obj','copy.asm','copy.obj','copy.dll','link.rsp'))
    text,exports,imports=C.assembly(metadata['source']);assembly.write_text(text,encoding='utf-8',newline='\n');core.write_text('option casemap:none\n'+CORE.read_text(encoding='utf-8')+'\nEND\n',encoding='utf-8',newline='\n')
    RB.assemble(assembly,obj,assembler,directory/'native-assembler.log');RB.assemble(core,core_obj,assembler,directory/'copy-assembler.log')
    S.check(RB.A.coff_symbols(obj)==(exports,imports),'Actual normal copy adapter/service symbol contract differs')
    S.check(RB.A.coff_symbols(core_obj,{'AcquireSRWLockShared','ReleaseSRWLockShared'})==({CORE_EXPORT},{'AcquireSRWLockShared','ReleaseSRWLockShared','boom_heap_contains'}),'Actual RO copy core imports/exports differ')
    runtime=checked(metadata['runtime']);objects=[core_obj,O.checked(metadata['mapping_owner']['object'])];libraries=[runtime.with_suffix('.lib'),library]
    rsp.write_text(response(image,objects,libraries,O.EXPORTS|{CORE_EXPORT}),encoding='utf-8',newline='\n')
    with (directory/'link.log').open('xb') as log:run=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    S.check(run.returncode==0,'Actual RO copy/owner image link failed')
    return dict(assembly=S.artifact(assembly),object=S.artifact(obj),core_assembly=S.artifact(core),core_object=S.artifact(core_obj),image=S.artifact(image),response=S.artifact(rsp),
        assembler=S.artifact(assembler),linker=S.artifact(linker),kernel32=S.artifact(library),runtime_library=S.artifact(runtime.with_suffix('.lib')))


def machine(row,meta):
    for key in ('assembly','object','core_assembly','core_object','image','response'):S.check(checked(row[key]).is_relative_to(ART),'Fresh isolated generated copy artifacts required')
    for key,path in [('assembler',O.TOOLS/'ml64.exe'),('linker',O.TOOLS/'link.exe'),('kernel32',O.SDK),('runtime_library',checked(meta['runtime']).with_suffix('.lib'))]:
        S.check(row[key]==S.artifact(path),'Fixed copy tool/library changed: '+key);checked(row[key])
    S.check(checked(row['assembly']).read_text(encoding='utf-8')==C.assembly(meta['source'])[0],'Normal copy adapter/receiver source differs')
    S.check(checked(row['core_assembly']).read_text(encoding='utf-8')=='option casemap:none\n'+CORE.read_text(encoding='utf-8')+'\nEND\n','Actual copy core source differs')
    fresh=compile_candidate(ART/'machine-checks'/uuid4().hex,meta)
    for key in ('object','core_object'):S.check(O.normalized_coff(checked(row[key]))==O.normalized_coff(checked(fresh[key])),'Actual copy code/data/symbols/relocations/unwind differs: '+key)
    S.check(checked(row['image']).read_bytes()==checked(fresh['image']).read_bytes(),'Actual complete copy PE differs')
    expected=response(checked(row['image']),[checked(row['core_object']),O.checked(meta['mapping_owner']['object'])],[checked(row['runtime_library']),checked(row['kernel32'])],O.EXPORTS|{CORE_EXPORT})
    S.check(checked(row['response']).read_text(encoding='utf-8')==expected,'Copy exact canonical response differs')
    return dict(native_normalized_COFF_sha256=hashlib.sha256(json.dumps(O.normalized_coff(checked(row['object'])),sort_keys=True).encode()).hexdigest(),
        core_normalized_COFF_sha256=hashlib.sha256(json.dumps(O.normalized_coff(checked(row['core_object'])),sort_keys=True).encode()).hexdigest(),complete_PE_sha256=S.digest(checked(row['image']))['sha256'])


def verify(path):
    path=Path(path).resolve();S.check(path.is_relative_to(ART),'Isolated copy candidate required');row=S.read(path)
    meta=contract(checked(row['metadata']['input_state']),O.checked(row['metadata']['mapping_owner']['candidate']),checked(row['metadata']['bridge_candidate']))
    S.check(row['metadata']==meta,'Current normal copy source/model/ABI inputs changed');proof=machine(row,meta)
    return dict(verified=True,scope='unregistered_original_copyMemory0_RO_JIMAGE_to_normal_heap_byte_array_source_frame_COFF_PE',candidate=S.artifact(path),machine=proof,
        provided_original_native_declarations=1,original_Java_checks_unchanged=True,bridge_runtime_binding_verified=False,original_Java_execution=False,
        arbitrary_off_heap=False,heap_to_heap=False,mapping_writes=False,registered=False,full_selection_reverified=False,game_started=False)


def build(state,owner,bridge,output):
    output=Path(output).resolve();S.check(output.is_relative_to(ART) and not output.exists(),'Fresh isolated RO copy output required');metadata=contract(state,owner,bridge);snapshot=S.tools_identity();files=compile_candidate(output,metadata)
    S.check(snapshot==S.tools_identity(),'Namespace changed during copy construction');row=dict(schema=1,metadata=metadata,**files,registered=False,executed=False,game_started=False);path=output/'candidate.json';S.write(path,row);S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('build','verify'));p.add_argument('--state',type=Path);p.add_argument('--owner',type=Path);p.add_argument('--bridge',type=Path);p.add_argument('--output',type=Path);p.add_argument('--candidate',type=Path);a=p.parse_args()
    print(build(a.state,a.owner,a.bridge,a.output) if a.action=='build' else json.dumps(verify(a.candidate),indent=2))
