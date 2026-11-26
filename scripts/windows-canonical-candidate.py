"""Build the two original Windows canonical natives without shared registration."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('windows_canonical_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S=module('runtime-provider-source')
C=module('windows-canonical-source')
R=module('verify-batch-frames')
A=module('verify-batch-assembly')
KERNEL=ROOT/'native/providers/windows_canonical.asm.inc'


def contract(state_file):
    state=S.read(state_file)
    identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'] and
        state.get('current_source_provider_verification_complete',state['status']=='accepted'),
        'Verified current source provider inputs required')
    meta=C.index(summary,classes,S)
    frame=Path(state['frame_manifest']);proof=frame.with_name('verification.json')
    accepted=S.read(proof)
    S.check(accepted['verified'] and accepted['manifest_sha256']==S.digest(frame)['sha256'] and
        state['frame_verification_sha256']==S.digest(proof)['sha256'],'Current original native frame proof differs')
    source=S.read(frame)['source']
    S.check(source['base']['batch_summary']==identity['batch_summary'],'Canonical source frame belongs to another batch')
    rows={row['id']:row for row in source['original_native_declarations']}
    for method in meta['methods']:
        row=rows[method['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[key]==method[key] for key in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
            'Original canonical native declaration/frame changed')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(proof)),
        runtime_kernel_sha256={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS})


def assembly(meta):
    source=meta['source'];proc,data=C.native_imports(source)
    owner=source['owner']
    text=f'option casemap:none\nEXTERN boom_class_ensure32:PROC\nEXTERN boom_class{owner}:BYTE\n'
    text+=''.join(f'EXTERN {name}:{"PROC" if name in proc else "BYTE"}\n' for name in sorted(proc|data))
    text+=C.data(source)
    for method in source['methods']:
        ident=method['method']
        text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,owner,C.POOL,C.SERVICE,method['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{row['method']}{suffix}" for row in source['methods'] for suffix in ('','_native')}
    return text,exports,proc|data|{'boom_class_ensure32',f'boom_class{owner}'}


def sections(path):
    blob=Path(path).read_bytes()
    machine,count,_,_,_,optional,_=struct.unpack_from('<HHIIIHH',blob)
    S.check(machine==0x8664 and optional==0,'Expected canonical AMD64 COFF sections')
    result={}
    for index in range(count):
        position=20+index*40
        name=blob[position:position+8].rstrip(b'\0').decode('ascii')
        size,offset=struct.unpack_from('<II',blob,position+16)
        if name.startswith(('.text','.rdata','.data')) and offset:
            S.check(name not in result,'Duplicate primitive COFF data section')
            result[name]=blob[offset:offset+size]
    return result


def verify(path):
    candidate=S.read(path);meta=contract(S.checked(candidate['metadata']['input_state']))
    S.check(candidate['metadata']==meta and S.artifact(KERNEL)==candidate['kernel'] and
        S.artifact(ROOT/'scripts/windows-canonical-source.py')==candidate['model'] and
        S.artifact(Path(__file__))==candidate['tool'],'Canonical source model or provider source changed')
    text,exports,imports=assembly(meta)
    S.check(S.checked(candidate['assembly']).read_text()==text and
        A.coff_symbols(S.checked(candidate['object']),C.FOREIGN)==(exports,imports) and
        set(candidate['exports'])==exports and set(candidate['imports'])==imports,'Canonical provider ASM/COFF changed')
    units=candidate['primitive_envelope_comparison']['units']
    original,embedded=[S.checked(row['object']) for row in units]
    S.check(sections(original)==sections(embedded),'Primitive envelope stripping changed actual code or data')
    S.check(A.coff_symbols(original,C.FOREIGN)==A.coff_symbols(embedded,C.FOREIGN),
        'Primitive envelope stripping changed an actual external target or PUBLIC definition')
    S.check(S.artifact(Path(candidate['assembler']['path']))==candidate['assembler'],'Canonical assembler changed')
    return dict(schema=1,verified=True,scope='two_original_WinNT_canonical_natives_source_frames_primitive_ASM_COFF_only',
        candidate=S.artifact(path),source_native_methods=2,dynamic_method_class_and_String_layout_IDs=True,
        obsolete_prefix_native_registered=False,embedded_primitive_text_and_data_identical=True,
        runtime572_modified=False,shared_provider_registered=False,linked=False,executed=False,game_started=False)


def build(state,assembler,output):
    output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project canonical source candidate directory required')
    meta=contract(state);output.mkdir(parents=True)
    def assemble(path,obj,log):
        with (output/log).open('wb') as stream:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),path],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=90)
    text,exports,imports=assembly(meta)
    asm,obj=output/'provider.asm',output/'provider.obj';asm.write_text(text)
    assemble(asm,obj,'assembler.log')
    S.check(A.coff_symbols(obj,C.FOREIGN)==(exports,imports),'Canonical actual COFF imports/exports differ')
    original=Path(meta['source']['primitive_source']['path'])
    units=[]
    for name,source in (('original',original.read_text()),('embedded','option casemap:none\n'+
        ''.join(f'EXTERN {symbol}:{kind}\n' for symbol,kind in meta['source']['primitive_declarations'])+
        C.primitive_body(original.read_text())+'\nEND\n')):
        path=output/(name+'-primitive.asm');path.write_text(source);target=path.with_suffix('.obj')
        assemble(path,target,name+'-primitive.log');units.append(dict(assembly=S.artifact(path),object=S.artifact(target)))
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-Windows-canonical-native-candidate',metadata=meta,
        kernel=S.artifact(KERNEL),model=S.artifact(ROOT/'scripts/windows-canonical-source.py'),tool=S.artifact(Path(__file__)),
        assembler=S.artifact(assembler),assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        primitive_envelope_comparison=dict(units=units,only_option_EXTERN_END_removed=True),
        shared_provider_registered=False,runtime572_modified=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'windows-path-canonicalization/candidates'/uuid4().hex)
    args=parser.parse_args();print(build(args.state.resolve(),args.assembler.resolve(),args.output))
