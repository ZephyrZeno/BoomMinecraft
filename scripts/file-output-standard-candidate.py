"""Build/verify two original FOS natives bounded to source FD.out/err."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('file_output_standard_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source');C=module('file-output-standard-source')
R=module('verify-batch-frames');A=module('verify-batch-assembly')
KERNEL=ROOT/'native/providers/file_output_standard.asm.inc'


def contract(state_file):
    state=S.read(state_file);identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'] and
        state.get('current_source_provider_verification_complete',state['status']=='accepted'),
        'Standard-output candidate needs independently verified current source inputs')
    source=C.index(summary,classes,S);frame=Path(state['frame_manifest']);proof=frame.with_name('verification.json')
    receipt=S.read(proof);overlay=S.read(frame)
    S.check(receipt['verified'] and receipt['manifest_sha256']==S.digest(frame)['sha256'] and
        state['frame_verification_sha256']==S.digest(proof)['sha256'] and
        overlay['source']['base']['batch_summary']==identity['batch_summary'],'Standard-output source frame proof differs')
    rows={row['id']:row for row in overlay['source']['original_native_declarations']}
    for method in source['methods']:
        row=rows[method['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[key]==method[key] for key in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
            'Standard-output original native declaration/frame differs')
    runtime=Path(state['runtime'])/'boom-runtime.dll';runtime_json=S.read(runtime.with_name('runtime.json'))
    kernels={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS}
    S.check(S.digest(runtime)['sha256']==runtime_json['sha256'] and
        all(runtime_json['sources'].get(name)==sha for name,sha in kernels.items()),
        'Original registration/heap kernel bytes are not the accepted runtime sources')
    return dict(base=identity,input_state=S.artifact(state_file),source=source,policy=C.POLICY,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(proof)),
        runtime=S.artifact(runtime),runtime_kernel_sha256=kernels)


def assembly(meta):
    source=meta['source'];procs,data=C.native_imports(source)
    procs|={'boom_class_ensure32'};data|={f"boom_class{row['class_id']}" for row in source['methods']}
    text='option casemap:none\n'+''.join(f'EXTERN {name}:{"PROC" if name in procs else "BYTE"}\n' for name in sorted(procs|data))
    text+=C.data(source)
    for row in source['methods']:
        ident=row['method'];text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,row['class_id'],C.POOL,C.SERVICE,row['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{row['method']}{suffix}" for row in source['methods'] for suffix in ('','_native')}
    return text,exports,procs|data


def verify(path):
    candidate=S.read(path);meta=candidate['metadata']
    S.check(contract(S.checked(meta['input_state']))==meta,'Standard-output source contract changed')
    for name,file in [('kernel',KERNEL),('model',ROOT/'scripts/file-output-standard-source.py'),('tool',Path(__file__))]:
        S.check(S.artifact(file)==candidate[name],'Standard-output candidate source changed: '+name)
    text,exports,imports=assembly(meta)
    S.check(S.checked(candidate['assembly']).read_text()==text and A.coff_symbols(S.checked(candidate['object']),C.FOREIGN)==(exports,imports),
        'Standard-output ASM/COFF exports or actual external targets changed')
    S.check(S.artifact(Path(candidate['assembler']['path']))==candidate['assembler'],'Standard-output assembler changed')
    return dict(schema=1,verified=True,scope='two_original_standard_FOS_write_source_natives_ASM_COFF_only',
        candidate=S.artifact(path),native_methods=2,dynamic_declarations_fields_and_frames=True,
        original_registration_kernels_unchanged=True,development_fd_IO_service_reused=False,only_source_standard_descriptors=True,
        uses_original_FD_static_root_cells=True,additional_native_root_span=False,
        shared_provider_registered=False,runtime_modified=False,executed=False,game_started=False)


def build(state,assembler,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh standard-output candidate output required')
    meta=contract(state);output.mkdir(parents=True);text,exports,imports=assembly(meta)
    asm,obj=output/'provider.asm',output/'provider.obj';asm.write_text(text)
    with (output/'assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    S.check(A.coff_symbols(obj,C.FOREIGN)==(exports,imports),'Standard-output actual COFF contract differs')
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-file-output-standard-candidate',metadata=meta,
        kernel=S.artifact(KERNEL),model=S.artifact(ROOT/'scripts/file-output-standard-source.py'),tool=S.artifact(Path(__file__)),
        assembler=S.artifact(assembler),assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        registered=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'file-output-standard/candidates'/uuid4().hex)
    args=parser.parse_args();print(build(args.state.resolve(),args.assembler.resolve(),args.output))
