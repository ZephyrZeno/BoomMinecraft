"""Source/frame/canonical-COFF candidate for the two original Method invoke0."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location('method_invoke_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source');C=module('method-invoke-source')
R=module('verify-batch-frames');A=module('verify-batch-assembly')
KERNEL=ROOT/'native/providers/method_invoke_static.asm.inc'
HELPERS=['scripts/runtime-provider-source.py','scripts/normal-methods-source.py','scripts/constructor-provider-source.py',
    'scripts/file-bootstrap-source.py','scripts/verify-translation-ir.py','scripts/verify-batch-frames.py',
    'scripts/verify-batch-metadata.py','scripts/system-class-inputs.py']


def contract(state_file):
    state=S.read(state_file)
    S.check(state['status'] in ('accepted','pending_runtime_acceptance') and state['current_source_provider_verification_complete'] and state['tool_sources']==S.tools_identity(),
        'Current independently verified provider input namespace required')
    base,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(
        state['batch_summary_sha256']==base['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==base['base_verification']['digest']['sha256'],
        'Original independently verified source batch required')
    meta=C.index(summary,classes,S)
    frame=Path(state['frame_manifest']);frame_proof=frame.with_name('verification.json');proof=S.read(frame_proof)
    actual_frame=module('native-frame-overlay').verify(frame,Path(state['batch']),Path(state['plan']))
    S.check(proof==actual_frame and proof['verified'] and proof['manifest_sha256']==S.digest(frame)['sha256'] and
        state['frame_verification_sha256']==S.digest(frame_proof)['sha256'],'Original frame receipt changed')
    overlay=S.read(frame);S.check(overlay['source']['base']['batch_summary']==base['batch_summary'],'Frame/base differs')
    original={r['id']:r for r in overlay['source']['original_native_declarations']}
    for method in meta['methods']:
        row=original[method['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[k]==method[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),'Original invoke0 native frame differs')
    runtime=Path(state['runtime'])/'boom-runtime.dll';runtime_meta=S.read(runtime.with_name('runtime.json'))
    kernels={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS}
    S.check(S.digest(runtime)['sha256']==state['runtime_sha256']==runtime_meta['sha256'] and
        all(runtime_meta['sources'].get(name)==sha for name,sha in kernels.items()),'Original normal runtime bytes/source changed')
    return dict(base=base,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,runtime=S.artifact(runtime),
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(frame_proof)),
        source_helpers={name:S.artifact(ROOT/name) for name in HELPERS},runtime_kernel_sha256=kernels,
        original_input_namespace=state['tool_sources'],input_state_status=state['status'],
        runtime_acceptance_complete=state['runtime_acceptance_complete'],formal_current_namespace_acceptance=False)


def assembly(meta):
    source=meta['source'];procs,data=C.native_imports(source)
    data|={f"boom_class{m['class_id']}" for m in source['methods']}
    text='option casemap:none\n'+''.join(f'EXTERN {name}:{"PROC" if name in procs else "BYTE"}\n' for name in sorted(procs|data))
    text+=C.data(source)
    for method in source['methods']:
        ident=method['method'];text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,method['class_id'],C.POOL,C.SERVICE,method['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{m['method']}{suffix}" for m in source['methods'] for suffix in ('','_native')}
    return text,exports,procs|data


def verify(path):
    value=S.read(path);meta=value['metadata']
    S.check(value.get('schema')==1 and value.get('family')=='source-method-invoke-static-reference-candidate' and
        all(value.get(key) is False for key in ('registered','linked','executed','game_started')),
        'Unregistered original Method invoke source candidate scope differs')
    S.check(contract(S.checked(meta['input_state']))==meta,'Method invoke source model differs')
    for name,file in [('kernel',KERNEL),('model',ROOT/'scripts/method-invoke-source.py'),('tool',Path(__file__))]:
        S.check(value[name]==S.artifact(file),'Method invoke candidate source changed: '+name)
    text,exports,imports=assembly(meta)
    S.check(value.get('exports')==sorted(exports) and value.get('imports')==sorted(imports),
        'Declared original Method invoke source symbols differ')
    S.check(S.checked(value['assembly']).read_text()==text and A.coff_symbols(S.checked(value['object']),C.FOREIGN)==(exports,imports),
        'Method invoke canonical ASM/actual COFF symbols differ')
    # The small directory is reassembled independently; retain instruction,
    # data, unwind and every relocation target, excluding assembler filenames.
    T=module('test-file-output-standard');assembler=Path(value['assembler']['path'])
    S.check(S.artifact(assembler)==value['assembler'],'Method invoke assembler changed')
    check_dir=S.ART/'method-invoke/COFF-checks'/uuid4().hex;check_dir.mkdir(parents=True)
    asm=check_dir/'canonical.asm';obj=asm.with_suffix('.obj');asm.write_text(text)
    with (check_dir/'assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    actual=T.coff_protocol(S.checked(value['object']));expected=T.coff_protocol(obj)
    S.check(actual==expected,'Method invoke actual code/data/unwind/all relocations differ from canonical')
    proof=dict(schema=1,verified=True,scope='two_original_Method_invoke0_static_noarg_reference_source_frames_COFF_only',
        candidate=S.artifact(path),native_methods=2,targets=len(meta['source']['records']),selected_sites_required=True,
        target_Java_Code_selection_not_implied=True,
        normalized_COFF_sha256=hashlib.sha256(json.dumps(actual,separators=(',',':')).encode()).hexdigest(),
        all_nondebug_sections_and_relocations_equal=True,current_shared_namespace_accepted=False,
        linked=False,executed=False,original_Method_invoke_or_EnumSet_API_passed=False,game_started=False)
    S.write(check_dir/'verification.json',dict(proof,canonical_assembly=S.artifact(asm),canonical_object=S.artifact(obj)));return proof


def build(state,assembler,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh method invoke candidate required')
    meta=contract(state);output.mkdir(parents=True);text,exports,imports=assembly(meta)
    asm=output/'provider.asm';obj=asm.with_suffix('.obj');asm.write_text(text)
    with (output/'assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-method-invoke-static-reference-candidate',metadata=meta,
        kernel=S.artifact(KERNEL),model=S.artifact(ROOT/'scripts/method-invoke-source.py'),tool=S.artifact(Path(__file__)),
        assembler=S.artifact(assembler),assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        registered=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(build(args.state.resolve(),args.assembler.resolve(),args.output.resolve()))
