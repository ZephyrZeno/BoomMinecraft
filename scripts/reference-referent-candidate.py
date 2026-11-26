"""Build and independently check the standalone normal Reference.get0 object."""
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
    owner=source['owner']
    prefix=f'option casemap:none\nEXTERN boom_class_ensure32:PROC\nEXTERN boom_class{owner}:BYTE\n'
    prefix+=''.join(f'EXTERN {name}:{"PROC" if name in proc else "BYTE"}\n' for name in sorted(proc|data))
    text=prefix+C.data(source)
    for row in source['methods']:
        i=row['method']
        text+=f'.code\nPUBLIC boom_m{i}\nPUBLIC boom_m{i}_native\n'
        text+=R.native_adapter(i,owner,C.POOL,C.SERVICE,0).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports={C.POOL,C.SERVICE}|{f"boom_m{m['method']}{suffix}" for m in source['methods'] for suffix in ('','_native')}
    return text,exports,proc|data|{'boom_class_ensure32',f'boom_class{owner}'}


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
    # Separately assemble just each reader under the same compiler. Branch/service
    # names can differ; the actual .text instruction bytes must remain identical.
    readers=[]
    for name,file in (('tested','reference_referent_read.asm.inc'),('standalone','reference_referent_get.asm.inc')):
        path=output/(name+'-reader.asm')
        path.write_text('option casemap:none\nEXTERN boom_heap_contains:PROC\n'+(ROOT/'native/providers'/file).read_text()+'\nEND\n')
        target=path.with_suffix('.obj')
        assemble(path,target,name+'-assembler.log')
        readers.append(target)
    S.check(text_section(readers[0])==text_section(readers[1]),'Renamed Reference service changed actual AMD64 instructions')
    S.check(A.coff_symbols(readers[0])==({'boom_source_reference_get'},{'boom_heap_contains'}) and
            A.coff_symbols(readers[1])==({C.SERVICE},{'boom_heap_contains'}),
            'Renamed reader changed an actual external instruction target')
    code_hash=hashlib.sha256(text_section(readers[0])).hexdigest()
    m=dict(schema=1,family='normal-reference-referent-get-candidate',metadata=meta,kernel=S.artifact(KERNEL),
        model=S.artifact(ROOT/'scripts/reference-referent-source.py'),tool=S.artifact(Path(__file__)),assembler=S.artifact(assembler),
        assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        standalone_instruction_comparison=dict(objects=[S.artifact(p) for p in readers],
            actual_text_identical=True,actual_text_sha256=code_hash),
        ordinary_Java_caller=meta['source']['ordinary_Java_get'],required_class_ids=meta['source']['required_classes'],
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
    compared=[S.checked(r) for r in m['standalone_instruction_comparison']['objects']]
    S.check(text_section(compared[0])==text_section(compared[1]),'Actual original and independent reader code differs')
    return dict(schema=1,verified=True,scope='original_Reference_get0_field_map_native_frame_normal_ASM_COFF_only',
        candidate=S.artifact(path),source_native_methods=1,required_class_ids=meta['source']['required_classes'],
        inherited_receiver_count=meta['source']['inherited_receiver_count'],actual_reader_text_identical=True,
        no_NIO_or_Windows_dispatcher_dependency=True,shared_provider_registered=False,linked=False,executed=False,
        full_weak_reference_GC=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'reference-referent/candidates'/uuid4().hex)
    args=parser.parse_args()
    print(build(args.state.resolve(),args.assembler.resolve(),args.output))
