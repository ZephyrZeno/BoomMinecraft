"""Assemble original normal Module natives without shared provider registration."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('module_definitions_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source');C=module('module-definitions-source')
R=module('verify-batch-frames');A=module('verify-batch-assembly')
KERNEL=ROOT/'native/providers/module_definitions_normal.asm.inc'


def contract(state_file):
    state=S.read(state_file);identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'] and
        state.get('current_source_provider_verification_complete',state['status']=='accepted'),
        'Verified source provider base inputs required')
    meta=C.index(summary,classes,S);frame=Path(state['frame_manifest']);proof=frame.with_name('verification.json')
    accepted=S.read(proof);source=S.read(frame)['source']
    S.check(accepted['verified'] and accepted['manifest_sha256']==S.digest(frame)['sha256'] and
        state['frame_verification_sha256']==S.digest(proof)['sha256'] and source['base']['batch_summary']==identity['batch_summary'],
        'Original normal Module frame/base proof differs')
    rows={r['id']:r for r in source['original_native_declarations']}
    for method in meta['methods']:
        row=rows[method['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[k]==method[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),'Original normal Module native changed')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(proof)),
        runtime_kernel_sha256={'native/runtime/'+n:S.digest(ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS})


def assembly(meta):
    source=meta['source'];procs,data=C.native_imports(source);owner=source['owner']
    text=f'option casemap:none\nEXTERN boom_class_ensure32:PROC\nEXTERN boom_class{owner}:BYTE\n'
    text+=''.join(f'EXTERN {n}:{"PROC" if n in procs else "BYTE"}\n' for n in sorted(procs|data))
    text+=C.data(source)
    for method in source['methods']:
        ident=method['method'];text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,owner,C.POOL,C.SERVICE,method['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    return text,C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{m['method']}{suffix}" for m in source['methods'] for suffix in ('','_native')},\
        procs|data|{'boom_class_ensure32',f'boom_class{owner}'}


def verify(path):
    candidate=S.read(path);meta=contract(S.checked(candidate['metadata']['input_state']))
    S.check(candidate['metadata']==meta and S.artifact(KERNEL)==candidate['kernel'] and
        S.artifact(ROOT/'scripts/module-definitions-source.py')==candidate['model'] and
        S.artifact(Path(__file__))==candidate['tool'],'Normal Module source model or kernel changed')
    text,exports,imports=assembly(meta)
    S.check(S.checked(candidate['assembly']).read_text()==text and A.coff_symbols(S.checked(candidate['object']),C.FOREIGN)==(exports,imports) and
        set(candidate['exports'])==exports and set(candidate['imports'])==imports,'Normal Module ASM/actual COFF differs')
    S.check(S.artifact(Path(candidate['assembler']['path']))==candidate['assembler'],'Module assembler changed')
    return dict(schema=1,verified=True,scope='five_original_normal_Module_natives_source_frames_ASM_COFF_only',
        candidate=S.artifact(path),original_natives=5,module_keys=meta['source']['module_count'],
        named_modules=meta['source']['named_module_count'],package_keys=len(meta['source']['package_keys']),
        same_original_Java_Module_oop_required=True,old_MODU3_pool_used=False,additional_Java_oop_roots=False,
        runtime572_modified=False,shared_provider_registered=False,linked=False,executed=False,game_started=False)


def build(state,assembler,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project Module candidate output required')
    meta=contract(state);output.mkdir(parents=True)
    text,exports,imports=assembly(meta);asm,obj=output/'provider.asm',output/'provider.obj';asm.write_text(text)
    with (output/'assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
    S.check(A.coff_symbols(obj,C.FOREIGN)==(exports,imports),'Actual Module COFF imports/exports differ')
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-normal-module-definitions-candidate',metadata=meta,
        kernel=S.artifact(KERNEL),model=S.artifact(ROOT/'scripts/module-definitions-source.py'),tool=S.artifact(Path(__file__)),
        assembler=S.artifact(assembler),assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        shared_provider_registered=False,runtime572_modified=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'module-definitions/candidates'/uuid4().hex)
    args=parser.parse_args();print(build(args.state.resolve(),args.assembler.resolve(),args.output))
