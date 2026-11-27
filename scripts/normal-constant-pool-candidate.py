"""Isolated normal ConstantPool ASM plus independently reconstructed readonly ROM."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('normal_cp_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source');C=module('normal-constant-pool-source')
R=module('verify-batch-frames');A=module('verify-batch-assembly')
MACHINE=module('normal-methods-candidate')
KERNEL=ROOT/'native/providers/normal_constant_pool.asm.inc'


def factory_contract():
    source=ROOT/'native/providers/normal_methods.asm.inc'
    original=re.search(r'(?ms)^normal_method_string PROC.*?^normal_method_string ENDP$',source.read_text())
    actual=re.search(r'(?ms)^ncp_string PROC.*?^ncp_string ENDP$',KERNEL.read_text())
    S.check(original and actual and original[0].replace('normal_method_string','ncp_string')==actual[0],
            'CP normal String factory changed an instruction/offset beyond its private labels')
    return S.artifact(source)


def contract(state_file):
    state_file=Path(state_file).resolve();S.check(state_file.is_relative_to(S.ART),'Project source input state required')
    state=S.read(state_file);batch,plan=Path(state['batch']),Path(state['plan'])
    identity,summary,classes=S.base(batch,plan)
    S.check(state['status'] in ('accepted','pending_runtime_acceptance') and
        state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'] and
        state['current_source_provider_verification_complete'] is True and state['tool_sources']==S.tools_identity(),
        'Current independently verified source state/namespace required')
    frame=Path(state['frame_manifest']);frame_proof=frame.with_name('verification.json')
    F=module('native-frame-overlay');actual=F.verify(frame,batch,plan)
    S.check(actual==S.read(frame_proof) and state['frame_verification_sha256']==S.digest(frame_proof)['sha256'],
        'Current original full native frame proof differs')
    meta=C.index(summary,classes,S);rows={r['id']:r for r in S.read(frame)['source']['original_native_declarations']}
    for method in meta['all_original_native_declarations']:
        native=rows[method['method']]
        S.check(native['flags']&32 and not native['flags']&128 and all(native[k]==method[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
            'Original CP native declaration/frame identity differs')
    runtime=Path(state['runtime']);runtime_meta=S.read(runtime/'runtime.json')
    kernels={'native/runtime/'+n:S.digest(ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS}
    S.check(S.digest(runtime/'boom-runtime.dll')['sha256']==state['runtime_sha256']==runtime_meta['sha256'] and
        all(runtime_meta['sources'][name]==sha for name,sha in kernels.items()),'Original CP runtime kernel input differs')
    S.check(factory_contract()==meta['String_factory_kernel'],'CP String primitive artifact differs')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(frame_proof)),runtime_kernel_sha256=kernels)


def assembly(meta):
    source=meta['source'];procs,data=C.native_imports(source)
    text='option casemap:none\n'+''.join(f'EXTERN {name}:{"PROC" if name in procs else "BYTE"}\n' for name in sorted(procs|data))
    text+=C.data(source)
    for method in source['methods']:
        ident=method['method'];text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,method['class_id'],C.POOL,C.SERVICE,method['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{r['method']}{suffix}" for r in source['methods'] for suffix in ('','_native')}
    return text,exports,procs|data


def verify_rom_object(path,source_meta,payload):
    expected=C.rom_coff(payload,source_meta)
    S.check(Path(path).read_bytes()==expected,'Actual CP data COFF differs from original classfile ROM reconstruction')
    raw=expected;machine,count,stamp,table,symbols,optional,flags=struct.unpack_from('<HHIIIHH',raw)
    name,virtual_size,virtual_address,size,data,reloc,line,nrel,nline,section_flags=struct.unpack_from('<8sIIIIIIHHI',raw,20)
    S.check((machine,count,stamp,symbols,optional,flags)==(0x8664,1,0,5,0,0) and
        name.rstrip(b'\0')==b'.rdata' and virtual_size==virtual_address==reloc==line==nrel==nline==0 and
        section_flags==0x40500040 and data==64 and size==len(payload) and table>=data+size and
        A.coff_symbols(path)==(C.ROM_EXPORTS,set()),'Readonly CP data COFF contains code, relocation, writable or extra data/symbols')
    return dict(verified=True,readonly_bytes=size,sections=['.rdata'],relocations=0,imports=[],exports=sorted(C.ROM_EXPORTS),
        code_sections=False,original_source_payload_sha256=hashlib.sha256(payload).hexdigest())


def machine_contract(text,obj,assembler):
    output=S.ART/'normal-constant-pool/COFF-checks'/uuid4().hex;output.mkdir(parents=True)
    source=output/'canonical.asm';expected=output/'canonical.obj';source.write_text(text,encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('xb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(expected),source],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    left,right=MACHINE.normalized_coff(obj),MACHINE.normalized_coff(expected)
    S.check(left==right,'Actual CP kernel instructions/data/flags/relocations/auxiliary/unwind differ from canonical ASM')
    digest=hashlib.sha256(json.dumps(left,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    S.write(output/'verification.json',dict(verified=True,scope='independently_reassembled_all_nondebug_CP_kernel_COFF',
        object=S.artifact(obj),canonical_assembly=S.artifact(source),canonical_object=S.artifact(expected),normalized=left,normalized_sha256=digest))
    return digest


def verify(path):
    path=Path(path).resolve();candidate=S.read(path)
    S.check(path.is_relative_to(S.ART/'normal-constant-pool') and candidate['family']=='source-normal-constant-pool-candidate',
        'Expected isolated ConstantPool candidate')
    meta=contract(S.checked(candidate['metadata']['input_state']))
    S.check(candidate['metadata']==meta and S.artifact(KERNEL)==candidate['kernel'] and
        S.artifact(ROOT/'scripts/normal-constant-pool-source.py')==candidate['model'] and
        S.artifact(Path(__file__))==candidate['tool'] and S.artifact(ROOT/'scripts/normal-methods-candidate.py')==candidate['COFF_reader'],
        'CP source model/kernel/verifier identity changed')
    text,exports,imports=assembly(meta)
    S.check(S.checked(candidate['assembly']).read_text()==text and candidate['exports']==sorted(exports) and
        candidate['imports']==sorted(imports) and A.coff_symbols(S.checked(candidate['object']),C.FOREIGN)==(exports,imports),
        'CP canonical ASM or actual kernel COFF declarations differ')
    S.check(S.artifact(candidate['assembler']['path'])==candidate['assembler'],'CP assembler changed')
    _,summary,classes=S.base(Path(meta['base']['batch_summary']['path']).parent,Path(meta['base']['source_plan']['path']).parent)
    rom,payload=C.build_rom(summary,classes,S);S.check(rom==meta['source']['ROM'],'Original CP ROM model changed')
    data_proof=verify_rom_object(S.checked(candidate['ROM_object']),rom,payload)
    kernel=machine_contract(text,S.checked(candidate['object']),Path(candidate['assembler']['path']))
    return dict(schema=1,verified=True,scope='unregistered_original_Class_ConstantPool_wrapper_and_explicit_readonly_getter_subset_source_ASM_COFF',
        candidate=S.artifact(path),provided_native_methods=len(meta['source']['methods']),explicit_unsupported_native_methods=5,
        original_class_pools=rom['original_class_pools'],CP_entries=rom['constant_pool_entries'],ROM=data_proof,
        kernel_nondebug_machine_and_relocations_verified=True,normalized_kernel_sha256=kernel,
        IfLoaded_claimed=False,methodAt_or_fieldAt_claimed=False,registered=False,linked=False,executed=False,game_started=False)


def build(state_file,output,assembler):
    output=Path(output).resolve();assembler=Path(assembler).resolve()
    S.check(output.is_relative_to(S.ART/'normal-constant-pool') and not output.exists(),'Fresh CP candidate output required')
    meta=contract(state_file);text,exports,imports=assembly(meta)
    state=S.read(state_file);_,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    rom,payload=C.build_rom(summary,classes,S);S.check(rom==meta['source']['ROM'],'CP original ROM inputs changed during build')
    output.mkdir(parents=True);asm=output/'provider.asm';obj=output/'provider.obj';data=output/'constant-pool-ROM.obj'
    asm.write_text(text,encoding='utf-8',newline='\n');data.write_bytes(C.rom_coff(payload,rom));verify_rom_object(data,rom,payload)
    with (output/'assembler.log').open('xb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-normal-constant-pool-candidate',metadata=meta,assembly=S.artifact(asm),object=S.artifact(obj),
        ROM_object=S.artifact(data),ROM_has_code=False,model=S.artifact(ROOT/'scripts/normal-constant-pool-source.py'),
        kernel=S.artifact(KERNEL),tool=S.artifact(Path(__file__)),COFF_reader=S.artifact(ROOT/'scripts/normal-methods-candidate.py'),
        assembler=S.artifact(assembler),exports=sorted(exports),imports=sorted(imports),shared_registered=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('build','verify'))
    parser.add_argument('--state',type=Path);parser.add_argument('--candidate',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--assembler',type=Path,default=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe'))
    args=parser.parse_args()
    if args.action=='build':print(build(args.state.resolve(),args.output,args.assembler))
    else:print(json.dumps(verify(args.candidate)))
