"""Verify the standalone Windows mapLibraryName source binding and AMD64 object."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('library_name_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S=module('runtime-provider-source')
C=module('library-name-source')
R=module('verify-batch-frames')
A=module('verify-batch-assembly')
KERNEL=ROOT/'native/providers/library_name_normal.asm.inc'


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
        'Accepted original library-name native frame changed')
    source=S.read(frame)['source']
    S.check(source['base']['batch_summary']==identity['batch_summary'],'Native frame belongs to another batch')
    rows={r['id']:r for r in source['original_native_declarations']}
    for m in meta['methods']:
        row=rows[m['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[k]==m[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
            'Original mapLibraryName native declaration or frame differs')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(frame.with_name('verification.json'))),
        runtime_kernel_sha256={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS})


def prefix(meta):
    proc,data=C.native_imports(meta)
    owner=meta['owner']
    text=f'option casemap:none\nEXTERN boom_class_ensure32:PROC\nEXTERN boom_class{owner}:BYTE\n'
    text+=''.join(f'EXTERN {name}:{"PROC" if name in proc else "BYTE"}\n' for name in sorted(proc|data))
    return text,proc|data|{'boom_class_ensure32',f'boom_class{owner}'}


def assembly(meta):
    source=meta['source']
    text,imports=prefix(source)
    text+=C.data(source)
    for row in source['methods']:
        ident=row['method']
        text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,row['class_id'],C.POOL,C.SERVICE,0).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports={C.POOL,C.SERVICE}|{f"boom_m{m['method']}{suffix}" for m in source['methods'] for suffix in ('','_native')}
    return text,exports,imports


def text_section(path):
    blob=Path(path).read_bytes()
    machine,count,_,_,_,optional,_=struct.unpack_from('<HHIIIHH',blob)
    S.check(machine==0x8664 and optional==0,'Expected AMD64 COFF library-name comparison')
    result=[]
    for i in range(count):
        position=20+i*40
        if blob[position:position+8].rstrip(b'\0').startswith(b'.text'):
            size,offset=struct.unpack_from('<II',blob,position+16)
            result.append(blob[offset:offset+size])
    S.check(len(result)==1,'Library-name kernel must contain exactly one code section')
    return result[0]


def kernel_assembly(meta,original):
    text,imports=prefix(meta)
    aliases=C.aliases(meta)
    if original:
        aliases={k.replace('MLN_','LIB_NAME_'):v for k,v in aliases.items()}
    text+=''.join(f'{name} TEXTEQU <{value}>\n' for name,value in aliases.items())
    file=ROOT/'native/providers'/('win32_library_name.asm.inc' if original else 'library_name_normal.asm.inc')
    return text+file.read_text()+'\nEND\n',imports


def verify(path):
    candidate=S.read(path)
    meta=contract(S.checked(candidate['metadata']['input_state']))
    S.check(candidate['metadata']==meta and S.artifact(KERNEL)==candidate['kernel'] and
        S.artifact(ROOT/'scripts/library-name-source.py')==candidate['model'] and
        S.artifact(Path(__file__))==candidate['tool'],'Independent library-name source model changed')
    text,exports,imports=assembly(meta)
    S.check(S.checked(candidate['assembly']).read_text()==text and
        A.coff_symbols(S.checked(candidate['object']))==(exports,imports) and
        set(candidate['exports'])==exports and set(candidate['imports'])==imports,
        'Independent library-name ASM or actual COFF differs')
    S.check(S.artifact(Path(candidate['assembler']['path']))==candidate['assembler'],'Library-name assembler changed')
    compared=candidate['standalone_instruction_comparison']
    objects=[]
    for original,row in zip((True,False),compared['units'],strict=True):
        source,needed=kernel_assembly(meta['source'],original)
        obj=S.checked(row['object'])
        name='boom_win32_library_name' if original else C.SERVICE
        S.check(S.checked(row['assembly']).read_text()==source and A.coff_symbols(obj)==({name},needed),
            'Renamed library-name kernel changed a source operand or COFF external target')
        objects.append(obj)
    code=text_section(objects[0])
    S.check(code==text_section(objects[1]) and hashlib.sha256(code).hexdigest()==compared['actual_text_sha256'],
        'Renamed library-name kernel changed actual AMD64 instructions')
    return dict(schema=1,verified=True,scope='original_Windows_System_mapLibraryName_source_frames_String_factory_ASM_COFF_only',
        candidate=S.artifact(path),source_native_methods=1,dynamic_original_method_and_field_IDs=True,
        required_class_ids=meta['source']['required_classes'],actual_kernel_text_identical=True,
        no_NIO_dispatcher_or_buffer_dependency=True,independent_pool_bytes=112,shared_provider_registered=False,
        linked=False,executed=False,game_started=False)


def build(state,assembler,output):
    output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project library-name candidate directory required')
    meta=contract(state)
    output.mkdir(parents=True)
    def assemble(asm,obj,log):
        with (output/log).open('wb') as stream:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=60)
    text,exports,imports=assembly(meta)
    asm,obj=output/'provider.asm',output/'provider.obj'
    asm.write_text(text)
    assemble(asm,obj,'assembler.log')
    S.check(A.coff_symbols(obj)==(exports,imports),'Independent library-name COFF imports/exports differ')
    units=[]
    for name,original in (('tested',True),('standalone',False)):
        source,_=kernel_assembly(meta['source'],original)
        path=output/(name+'-kernel.asm')
        path.write_text(source)
        target=path.with_suffix('.obj')
        assemble(path,target,name+'-assembler.log')
        units.append(dict(assembly=S.artifact(path),object=S.artifact(target)))
    S.check(text_section(Path(units[0]['object']['path']))==text_section(Path(units[1]['object']['path'])),
        'Independent library-name kernel changed actual AMD64 instructions')
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='normal-Windows-System-mapLibraryName-source-candidate',metadata=meta,
        kernel=S.artifact(KERNEL),model=S.artifact(ROOT/'scripts/library-name-source.py'),tool=S.artifact(Path(__file__)),
        assembler=S.artifact(assembler),assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        standalone_instruction_comparison=dict(units=units,actual_text_identical=True,
            actual_text_sha256=hashlib.sha256(text_section(Path(units[0]['object']['path']))).hexdigest()),
        shared_provider_registered=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path))
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'library-name/candidates'/uuid4().hex)
    args=parser.parse_args()
    print(build(args.state.resolve(),args.assembler.resolve(),args.output))
