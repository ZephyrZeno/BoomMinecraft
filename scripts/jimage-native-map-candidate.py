"""Unregistered source/frame/COFF bridge to a separately verified JIMAGE owner."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('jimage_map_'+name,ROOT/'scripts'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


S=module('runtime-provider-source');C=module('jimage-native-map-source')
R=module('verify-batch-frames');A=module('verify-batch-assembly')
KERNEL=ROOT/'native/providers/jimage_native_map.asm.inc'
HELPERS=['scripts/runtime-provider-source.py','scripts/constructor-provider-source.py',
    'scripts/verify-translation-ir.py','scripts/verify-batch-frames.py','scripts/verify-batch-metadata.py',
    'scripts/system-class-inputs.py','scripts/native-frame-overlay.py','scripts/test-file-output-standard.py']


def contract(state_file,owner_file):
    state=S.read(state_file);accepted=state.get('status')=='accepted'
    S.check(state.get('status') in ('accepted','pending_runtime_acceptance') and
        state.get('current_source_provider_verification_complete') is True and
        state.get('runtime_acceptance_complete') is accepted and
        state.get('accepted_provider_set_published') is accepted and state['tool_sources']==S.tools_identity(),
        'Explicit current verified accepted/pending source namespace required')
    base,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(state['batch_summary_sha256']==base['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==base['base_verification']['digest']['sha256'],
        'Original independently verified JIMAGE source batch required')
    source=C.index(summary,classes,S)
    frame=Path(state['frame_manifest']);proof_file=frame.with_name('verification.json')
    actual=module('native-frame-overlay').verify(frame,Path(state['batch']),Path(state['plan']))
    S.check(actual==S.read(proof_file) and actual['verified'] and
        actual['manifest_sha256']==S.digest(frame)['sha256'] and
        state['frame_verification_sha256']==S.digest(proof_file)['sha256'],'Original image native frame changed')
    overlay=S.read(frame)
    S.check(overlay['source']['base']['batch_summary']==base['batch_summary'],'Image frame/base differs')
    declarations={row['id']:row for row in overlay['source']['original_native_declarations']}
    for row in source['methods']:
        native=declarations[row['method']]
        S.check(native['flags']&32 and not native['flags']&128 and all(native[k]==row[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
            'Original NativeImageBuffer declaration/native frame differs')
    D=module('jimage-owner-candidate');owner_proof=D.verify(owner_file)
    owner=S.read(owner_file)
    S.check(owner_proof==S.read(Path(owner_file).with_name('verification.json')) and
        owner['abi']==D.ABI and owner['abi']['owner_bytes']==128 and owner['abi']['job_bytes']==64 and
        owner['abi']['lookup_acquires_lease'] is True and owner['abi']['close_requires_zero_leases'] is True and
        owner['abi']['status_codes']['ok']==0 and owner['abi']['status_codes']['miss']==1,
        'Real lookup-only JIMAGE owner ABI/source/machine proof differs')
    runtime=Path(state['runtime'])/'boom-runtime.dll';runtime_meta=S.read(runtime.with_name('runtime.json'))
    kernels={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS}
    S.check(S.digest(runtime)['sha256']==state['runtime_sha256']==runtime_meta['sha256'] and
        all(runtime_meta['sources'].get(name)==sha for name,sha in kernels.items()),
        'Original normal runtime source/bytes changed')
    return dict(base=base,input_state=S.artifact(state_file),source=source,policy=C.POLICY,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(proof_file)),runtime=S.artifact(runtime),
        mapping_owner=dict(candidate=S.artifact(owner_file),verification=S.artifact(Path(owner_file).with_name('verification.json')),
            object=S.artifact(D.checked(owner['object'])),abi=owner['abi'],producer=S.artifact(ROOT/'scripts/jimage-owner-candidate.py')),
        runtime_kernel_sha256=kernels,source_helpers={name:S.artifact(ROOT/name) for name in HELPERS},
        original_input_namespace=state['tool_sources'],input_state_status=state['status'],
        input_runtime_acceptance_complete=accepted,additional_candidate_in_original_full_selection=False)


def assembly(meta):
    source=meta['source'];procs,data=C.native_imports(source)
    data|={f"boom_class{row['class_id']}" for row in source['methods']}
    text='option casemap:none\n'+''.join(f'EXTERN {name}:{"PROC" if name in procs else "BYTE"}\n'
        for name in sorted(procs|data))
    text+=C.data(source)
    for row in source['methods']:
        ident=row['method'];text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,row['class_id'],C.POOL,C.SERVICE,0).removeprefix('.code\n')
    text+=KERNEL.read_text(encoding='utf-8')+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{row['method']}{suffix}" for row in source['methods'] for suffix in ('','_native')}
    return text,exports,procs|data


def verify(path):
    path=Path(path).resolve();value=S.read(path)
    S.check(value.get('schema')==1 and value.get('family')=='source-jimage-native-map-candidate' and
        all(value.get(k) is False for k in ('registered','linked','executed','game_started')),
        'Unregistered original image native candidate scope differs')
    meta=value['metadata']
    S.check(meta==contract(S.checked(meta['input_state']),S.checked(meta['mapping_owner']['candidate'])),
        'Original image native source/owner/frame contract changed')
    for key,file in [('kernel',KERNEL),('model',ROOT/'scripts/jimage-native-map-source.py'),('tool',Path(__file__))]:
        S.check(value[key]==S.artifact(file),'Image bridge source changed: '+key)
    text,exports,imports=assembly(meta)
    S.check(value['exports']==sorted(exports) and value['imports']==sorted(imports) and
        S.checked(value['assembly']).read_text(encoding='utf-8')==text and
        A.coff_symbols(S.checked(value['object']),C.FOREIGN)==(exports,imports),
        'Image bridge canonical ASM or actual source symbols changed')
    assembler=Path(value['assembler']['path'])
    S.check(S.artifact(assembler)==value['assembler'],'Image bridge assembler changed')
    fresh=S.ART/'jimage-native-map/machine-checks'/uuid4().hex;fresh.mkdir(parents=True)
    asm,obj=fresh/'canonical.asm',fresh/'canonical.obj';asm.write_text(text,encoding='utf-8')
    with (fresh/'assembler.log').open('xb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    T=module('test-file-output-standard');actual=T.coff_protocol(S.checked(value['object']));expected=T.coff_protocol(obj)
    S.check(actual==expected,'Image bridge instructions/data/unwind/all relocations differ from canonical')
    proof=dict(schema=1,verified=True,scope='original_NativeImageBuffer_source_native_frames_lookup_bridge_COFF_only',
        candidate=S.artifact(path),normalized_COFF_sha256=hashlib.sha256(json.dumps(actual,separators=(',',':')).encode()).hexdigest(),
        all_nondebug_sections_and_relocations_equal=True,real_owner_independently_verified=True,
        original_private_DirectByteBuffer_constructor='(JJ)V',owner_initializer_execution_not_implied=True,
        native_op_opens_mapping=False,retained_lease_directory_Java_oops=False,
        registered=False,linked=False,executed=False,game_started=False)
    S.write(fresh/'verification.json',dict(proof,canonical_assembly=S.artifact(asm),canonical_object=S.artifact(obj)))
    return proof


def build(state,owner,assembler,output):
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated image bridge output required')
    meta=contract(state,owner);output.mkdir(parents=True);text,exports,imports=assembly(meta)
    asm,obj=output/'provider.asm',output/'provider.obj';asm.write_text(text,encoding='utf-8')
    with (output/'assembler.log').open('xb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-jimage-native-map-candidate',metadata=meta,kernel=S.artifact(KERNEL),
        model=S.artifact(ROOT/'scripts/jimage-native-map-source.py'),tool=S.artifact(Path(__file__)),assembler=S.artifact(assembler),
        assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        registered=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--owner',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(build(args.state.resolve(),args.owner.resolve(),args.assembler.resolve(),args.output.resolve()))
