"""Build and independently verify four normal Reference/Phantom native entries."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('referent_candidate_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S=module('runtime-provider-source')
C=module('reference-referent-source')
R=module('verify-batch-frames')
A=module('verify-batch-assembly')
KERNEL=ROOT/'native/providers/reference_referent_get.asm.inc'


def contract(state_file):
    state=S.read(state_file)
    identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(state['status']=='accepted' and
            state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
            state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'],
            'Current accepted normal source state required')
    meta=C.index(summary,classes,S)
    frame=Path(state['frame_manifest'])
    proof=S.read(frame.with_name('verification.json'))
    S.check(proof['verified'] and proof['manifest_sha256']==S.digest(frame)['sha256'] and
            state['frame_verification_sha256']==S.digest(frame.with_name('verification.json'))['sha256'],
            'Accepted normal native frame differs')
    source=S.read(frame)['source']
    S.check(source['base']['batch_summary']==identity['batch_summary'],'Frame belongs to another source batch')
    rows={r['id']:r for r in source['original_native_declarations']}
    for m in meta['methods']:
        row=rows[m['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[k]==m[k] for k in
                ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
                'Original Reference native frame flags/declaration differ')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(frame.with_name('verification.json'))),
        runtime_kernel_sha256={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS},
        policy=C.POLICY)


def assembly(meta):
    source=meta['source']
    proc,data=C.native_imports(source)
    owners=sorted({m['class_id'] for m in source['methods']})
    prefix='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'
    prefix+=''.join(f'EXTERN boom_class{owner}:BYTE\n' for owner in owners)
    prefix+=''.join(f'EXTERN {name}:{"PROC" if name in proc else "BYTE"}\n' for name in sorted(proc|data))
    text=prefix+C.data(source)
    for row in source['methods']:
        i=row['method']
        text+=f'.code\nPUBLIC boom_m{i}\nPUBLIC boom_m{i}_native\n'
        text+=R.native_adapter(i,row['class_id'],C.POOL,C.SERVICE,row['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports={C.POOL,C.SERVICE}|{f"boom_m{m['method']}{suffix}" for m in source['methods'] for suffix in ('','_native')}
    return text,exports,proc|data|{'boom_class_ensure32'}|{f'boom_class{owner}' for owner in owners}


def text_section(path):
    blob=Path(path).read_bytes()
    machine,count,_,_,_,optional,_=struct.unpack_from('<HHIIIHH',blob)
    S.check(machine==0x8664 and optional==0,'Expected AMD64 COFF code comparison')
    for i in range(count):
        p=20+i*40
        name=blob[p:p+8].rstrip(b'\0')
        if name.startswith(b'.text'):
            size,offset=struct.unpack_from('<II',blob,p+16)
            return blob[offset:offset+size]
    raise ValueError('Original reader has no actual code section')


def build(state,assembler,output):
    output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project source candidate directory required')
    meta=contract(state)
    output.mkdir(parents=True)
    text,exports,imports=assembly(meta)
    asm,obj=output/'provider.asm',output/'provider.obj'
    asm.write_text(text)
    def assemble(source,target,log):
        with (output/log).open('wb') as stream:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(target),source],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=60)
    assemble(asm,obj,'assembler.log')
    S.check(A.coff_symbols(obj)==(exports,imports),'Independent referent source COFF imports/exports differ')
    m=dict(schema=2,family='normal-reference-referent-operations-candidate',metadata=meta,kernel=S.artifact(KERNEL),
        model=S.artifact(ROOT/'scripts/reference-referent-source.py'),tool=S.artifact(Path(__file__)),assembler=S.artifact(assembler),
        assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        ordinary_Java_callers=meta['source']['ordinary_Java'],required_class_ids=meta['source']['required_classes'],
        required_base_modules=meta['source']['required_base_modules'],required_provider_families=[],
        shared_provider_registered=False,linked=False,executed=False,full_weak_reference_GC=False,game_started=False)
    path=output/'candidate.json'
    S.write(path,m)
    S.write(output/'verification.json',verify(path))
    return path


def verify(path):
    m=S.read(path)
    meta=contract(S.checked(m['metadata']['input_state']))
    S.check(meta==m['metadata'] and S.artifact(KERNEL)==m['kernel'] and
            S.artifact(ROOT/'scripts/reference-referent-source.py')==m['model'] and S.artifact(Path(__file__))==m['tool'],
            'Independent normal Reference source model changed')
    body,exports,imports=assembly(meta)
    S.check(S.checked(m['assembly']).read_text()==body and A.coff_symbols(S.checked(m['object']))==(exports,imports) and
            set(m['exports'])==exports and set(m['imports'])==imports,'Reference generated assembly or actual COFF differs')
    S.check(S.artifact(Path(m['assembler']['path']))==m['assembler'],'Reference assembler changed')
    S.check(m['ordinary_Java_callers']==meta['source']['ordinary_Java'] and
        m['required_class_ids']==meta['source']['required_classes'],'Original Reference caller/dependency metadata changed')
    return dict(schema=2,verified=True,scope='original_Reference_get_refers_clear_Phantom_refers_source_field_map_native_frames_ASM_COFF_only',
        candidate=S.artifact(path),source_native_methods=4,required_class_ids=meta['source']['required_classes'],
        inherited_receiver_count=meta['source']['inherited_receiver_count'],aligned_snapshot_atomic_clear=True,
        no_NIO_or_Windows_dispatcher_dependency=True,shared_provider_registered=False,linked=False,executed=False,
        full_weak_reference_GC=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'reference-referent/candidates'/uuid4().hex)
    args=parser.parse_args()
    print(build(args.state.resolve(),args.assembler.resolve(),args.output))
