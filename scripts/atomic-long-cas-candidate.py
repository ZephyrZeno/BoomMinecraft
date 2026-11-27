"""Build/verify one unregistered original AtomicLong native and actual CPUID."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]

def module(name):
    spec=importlib.util.spec_from_file_location('atomic_cas_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

S,C,F,R,A,O,N=(module(n) for n in ('runtime-provider-source','atomic-long-cas-source','native-frame-overlay',
    'verify-batch-frames','verify-batch-assembly','jimage-owner-candidate','refresh-named-module-batch'))
KERNEL=ROOT/'native/providers/atomic_long_cas.asm.inc'
ASSEMBLER=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')

def contract(state_file):
    state=S.read(state_file)
    S.check(state['status'] in ('accepted','pending_runtime_acceptance') and state['current_source_provider_verification_complete'] is True and
        state['tool_sources']==S.tools_identity(),'Current independently source-verified provider namespace required')
    identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    N.verified_resolver(Path(state['batch']),summary,Path(state['plan']))
    S.check(identity['batch_summary']['digest']['sha256']==state['batch_summary_sha256'] and
        identity['base_verification']['digest']['sha256']==state['batch_verification_sha256'],'Original batch/full proof differs')
    meta=C.index(summary,classes,S);frame=Path(state['frame_manifest']);receipt=frame.with_name('verification.json')
    proof=F.verify(frame,Path(state['batch']),Path(state['plan']))
    S.check(proof==S.read(receipt) and S.digest(receipt)['sha256']==state['frame_verification_sha256'],'Original Frame8 proof differs')
    declarations={r['id']:r for r in S.read(frame)['source']['original_native_declarations']}
    for m in meta['methods']:
        row=declarations[m['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[k]==m[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),'Original native frame/declaration changed')
    runtime=Path(state['runtime'])/'boom-runtime.dll';runtime_meta=S.read(runtime.with_name('runtime.json'))
    kernels={'native/runtime/'+n:S.digest(ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS}
    S.check(S.digest(runtime)['sha256']==state['runtime_sha256']==runtime_meta['sha256'] and
        all(runtime_meta['sources'][n]==h for n,h in kernels.items()),'Actual runtime class/frame kernels differ')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,tools=S.tools_identity(),
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(receipt)),
        runtime=S.artifact(runtime),runtime_kernel_sha256=kernels,
        helpers={n:S.artifact(ROOT/'scripts'/n) for n in ('runtime-provider-source.py','native-frame-overlay.py',
            'verify-batch-frames.py','verify-batch-assembly.py','verify-translation-ir.py','jimage-owner-candidate.py',
            'refresh-named-module-batch.py')})

def assembly(metadata):
    meta=metadata['source'];procs,data=C.native_imports(meta)
    text='option casemap:none\n'+''.join(f'EXTERN {n}:{"PROC" if n in procs else "BYTE"}\n' for n in sorted(procs|data))
    text+=C.data(meta)
    for row in meta['methods']:
        i=row['method'];text+=f'.code\nPUBLIC boom_m{i}\nPUBLIC boom_m{i}_native\n'
        text+=R.native_adapter(i,row['class_id'],C.POOL,C.SERVICE,row['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports={C.POOL,C.SERVICE}|{f"boom_m{r['method']}{suffix}" for r in meta['methods'] for suffix in ('','_native')}
    return text,exports,procs|data

def machine(text,obj,assembler):
    directory=S.ART/'atomic-long-cas/machine-checks'/uuid4().hex;directory.mkdir(parents=True)
    asm,canonical=directory/'canonical.asm',directory/'canonical.obj';asm.write_text(text,encoding='utf-8',newline='\n')
    with (directory/'assembler.log').open('xb') as output:
        subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(canonical),str(asm)],check=True,stdout=output,stderr=subprocess.STDOUT,timeout=120)
    actual,expected=O.normalized_coff(obj),O.normalized_coff(canonical)
    S.check(actual==expected,'Canonical code/data/flags/symbol aux/normalized relocations/unwind differ')
    proof=dict(verified=True,canonical_assembly=S.artifact(asm),canonical_object=S.artifact(canonical),actual_object=S.artifact(obj),
        normalized=actual,all_nondebug_sections_symbols_auxiliary_relocations_unwind_verified=True)
    S.write(directory/'verification.json',proof)
    return hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def verify(path):
    row=S.read(path);meta=row['metadata']
    S.check(contract(S.checked(meta['input_state']))==meta,'AtomicLong original source/frame contract changed')
    for name,source in (('tool',Path(__file__)),('model',Path(C.__file__)),('kernel',KERNEL),('COFF_reader',Path(O.__file__))):
        S.check(S.artifact(source)==row[name],'AtomicLong candidate source changed: '+name)
    assembler=Path(row['assembler']['path']);S.check(S.artifact(assembler)==row['assembler'],'Actual assembler changed')
    text,exports,imports=assembly(meta);obj=S.checked(row['object'])
    S.check(S.checked(row['assembly']).read_text()==text and A.coff_symbols(obj)==(exports,imports) and
        row['exports']==sorted(exports) and row['imports']==sorted(imports),'AtomicLong actual ASM/COFF symbols differ')
    normalized=machine(text,obj,assembler)
    S.check(not any(row[k] for k in ('registered','linked','executed','game_started')),'AtomicLong source scope overclaimed')
    return dict(schema=1,verified=True,scope='one_original_AtomicLong_capability_native_source_Frame8_complete_COFF_only',
        candidate=S.artifact(path),original_native_methods=1,normal_original_native_frame=True,
        original_clinit_Code_preserved=True,Java_static_field_host_written=False,actual_CPUID_leaf0_then_leaf1_EDX8=True,
        target_profile_requires_CX8=True,missing_physical_capability_is_unsupported_Context20=True,
        canonical_all_nondebug_machine_and_relocations_verified=True,normalized_COFF_sha256=normalized,
        shared_provider_registered=False,runtime_DLL_modified=False,linked=False,executed=False,game_started=False)

def build(state,assembler,output):
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART/'atomic-long-cas') and not output.exists(),'Fresh AtomicLong candidate required')
    metadata=contract(state);text,exports,imports=assembly(metadata);output.mkdir(parents=True)
    asm,obj=output/'provider.asm',output/'provider.obj';asm.write_text(text,encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('xb') as log:
        subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(asm)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-atomic-long-cas-capability-candidate',metadata=metadata,
        assembly=S.artifact(asm),object=S.artifact(obj),assembler=S.artifact(assembler),tool=S.artifact(__file__),
        model=S.artifact(C.__file__),kernel=S.artifact(KERNEL),COFF_reader=S.artifact(O.__file__),
        exports=sorted(exports),imports=sorted(imports),registered=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    make=sub.add_parser('build');make.add_argument('--state',type=Path,required=True);make.add_argument('--assembler',type=Path,default=ASSEMBLER)
    make.add_argument('--output',type=Path,required=True);check_=sub.add_parser('verify');check_.add_argument('candidate',type=Path)
    args=parser.parse_args()
    print(build(args.state,args.assembler,args.output) if args.command=='build' else json.dumps(verify(args.candidate),indent=2))
