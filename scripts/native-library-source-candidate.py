"""Verify the production NativeLibraries source model independently of NIO fixtures."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('formal_native_libraries_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S=module('runtime-provider-source')
C=module('native-library-source')
R=module('verify-batch-frames')
A=module('verify-batch-assembly')
KERNEL=ROOT/'native/providers/native_library_lifecycle.asm.inc'


def contract(state_file):
    state=S.read(state_file)
    identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(state['status']=='accepted' and state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
            state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'],
            'Accepted original source batch required')
    meta=C.index(summary,classes,S)
    frame=Path(state['frame_manifest'])
    proof=S.read(frame.with_name('verification.json'))
    S.check(proof['verified'] and proof['manifest_sha256']==S.digest(frame)['sha256'] and
            state['frame_verification_sha256']==S.digest(frame.with_name('verification.json'))['sha256'],
            'Accepted original native frame changed')
    source=S.read(frame)['source']
    S.check(source['base']['batch_summary']==identity['batch_summary'],'Native frame belongs to another batch')
    rows={r['id']:r for r in source['original_native_declarations']}
    for m in meta['methods']:
        row=rows[m['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[k]==m[k] for k in
                ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
                'Original native declaration or frame differs')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(frame.with_name('verification.json'))),
        runtime_kernel_sha256={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS})


def assembly(meta):
    source=meta['source']
    owners=sorted({m['class_id'] for m in source['methods']})
    proc,data=C.native_imports(source)
    declared={'boom_class_ensure32'}|{f'boom_class{i}' for i in owners}
    text='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'
    text+=''.join(f'EXTERN boom_class{i}:BYTE\n' for i in owners)
    text+=''.join(f'EXTERN {name}:{"PROC" if name in proc else "BYTE"}\n' for name in sorted((proc|data)-declared))
    text+=C.data(source)
    for m in source['methods']:
        ident=m['method']
        text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,m['class_id'],C.POOL,C.SERVICE,m['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{m['method']}{suffix}" for m in source['methods'] for suffix in ('','_native')}
    return text,exports,proc|data|declared


def verify(path):
    candidate=S.read(path)
    meta=contract(S.checked(candidate['metadata']['input_state']))
    S.check(candidate['metadata']==meta and S.artifact(KERNEL)==candidate['kernel'] and
            S.artifact(ROOT/'scripts/native-library-source.py')==candidate['model'] and
            S.artifact(Path(__file__))==candidate['tool'],'Production library source model changed')
    text,exports,imports=assembly(meta)
    S.check(S.checked(candidate['assembly']).read_text()==text and
            A.coff_symbols(S.checked(candidate['object']),C.FOREIGN)==(exports,imports) and
            set(candidate['exports'])==exports and set(candidate['imports'])==imports,'Production native library ASM/COFF changed')
    S.check(S.artifact(Path(candidate['assembler']['path']))==candidate['assembler'],'Library assembler changed')
    return dict(schema=1,verified=True,scope='original_builtin_NativeLibraries_source_Java_callbacks_fields_frames_ASM_COFF_only',
        candidate=S.artifact(path),native_methods=len(meta['source']['methods']),
        dynamic_original_method_and_field_IDs=True,API_fixture_setProperties_included=False,NIO_candidate_required=False,
        normal_root_Java_callbacks=meta['source']['required_java_methods'],Java_callbacks_outside_SRW=True,
        standard_JNI_environment_exposed=False,shared_provider_registered=False,linked=False,executed=False,game_started=False)


def build(state,assembler,output):
    output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project candidate directory required')
    meta=contract(state)
    output.mkdir(parents=True)
    text,exports,imports=assembly(meta)
    asm,obj=output/'provider.asm',output/'provider.obj'
    asm.write_text(text)
    with (output/'assembler.log').open('wb') as stream:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=60)
    S.check(A.coff_symbols(obj,C.FOREIGN)==(exports,imports),'Production library COFF has unexpected dependencies')
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='normal-builtin-native-libraries-source-candidate',metadata=meta,
        kernel=S.artifact(KERNEL),model=S.artifact(ROOT/'scripts/native-library-source.py'),tool=S.artifact(Path(__file__)),
        assembler=S.artifact(assembler),assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        shared_provider_registered=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path))
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'native-library-source/candidates'/uuid4().hex)
    args=parser.parse_args()
    print(build(args.state.resolve(),args.assembler.resolve(),args.output))
