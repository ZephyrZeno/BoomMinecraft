"""Assemble seven original readonly WinNT natives without shared registration."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('windows_file_queries_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source')
C=module('windows-file-queries-source')
R=module('verify-batch-frames')
A=module('verify-batch-assembly')
P=module('parallel-diagnostic-assembly-candidate')
KERNEL=ROOT/'native/providers/windows_file_queries.asm.inc'


def contract(state_file):
    state=S.read(state_file)
    identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'] and
        state.get('current_source_provider_verification_complete',state['status']=='accepted'),
        'Verified current source provider inputs required')
    meta=C.index(summary,classes,S)
    frame=Path(state['frame_manifest']);proof=frame.with_name('verification.json');accepted=S.read(proof)
    S.check(accepted['verified'] and accepted['manifest_sha256']==S.digest(frame)['sha256'] and
        state['frame_verification_sha256']==S.digest(proof)['sha256'],'Current original native frame proof differs')
    source=S.read(frame)['source']
    S.check(source['base']['batch_summary']==identity['batch_summary'],'Query source frames belong to another batch')
    rows={r['id']:r for r in source['original_native_declarations']}
    for method in meta['methods']:
        row=rows[method['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[k]==method[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
            'Original readonly query declaration/frame changed')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(proof)),
        runtime_kernel_sha256={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS})


def assembly(meta):
    source=meta['source'];procs,data=C.native_imports(source);owner=source['owner']
    text=f'option casemap:none\nEXTERN boom_class_ensure32:PROC\nEXTERN boom_class{owner}:BYTE\n'
    text+=''.join(f'EXTERN {n}:{"PROC" if n in procs else "BYTE"}\n' for n in sorted(procs|data))
    text+=C.data(source)
    for method in source['methods']:
        ident=method['method']
        text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,owner,C.POOL,C.SERVICE,method['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text()+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{r['method']}{suffix}" for r in source['methods'] for suffix in ('','_native')}
    return text,exports,procs|data|{'boom_class_ensure32',f'boom_class{owner}'}


def normalized_primitive(path):
    obj=P.Coff(path)
    def normalize(value):
        if isinstance(value,str):return C.RENAMES.get(value,value)
        if isinstance(value,(list,tuple)):return tuple(normalize(v) for v in value)
        return value
    sections={}
    for name,row in obj.sections.items():
        if name not in {'.text','.text$mn','.rdata','.data','.bss','.xdata','.pdata'}:continue
        relocations=[]
        for offset,index,kind in row['reloc']:
            symbol=obj.index[index]
            S.check(symbol is not None,'Primitive relocation targets an auxiliary symbol')
            target=(obj.by_section[symbol['section']]['name'],symbol['value'],normalize(symbol['name'])) if symbol['section']>0 else (
                'external',symbol['value'],normalize(symbol['name']))
            relocations.append((offset,kind,target))
        sections[name]=(row['size'],row['flags'],hashlib.sha256(row['raw']).hexdigest(),tuple(relocations))
    exports,imports=A.coff_symbols(path,C.FOREIGN)
    return dict(sections=sections,exports=sorted(C.RENAMES.get(n,n) for n in exports),imports=sorted(imports),
        unwind=normalize(tuple(sorted(P.unwind(obj).items()))))


def verify(path):
    candidate=S.read(path);meta=contract(S.checked(candidate['metadata']['input_state']))
    S.check(candidate['metadata']==meta and S.artifact(KERNEL)==candidate['kernel'] and
        S.artifact(ROOT/'scripts/windows-file-queries-source.py')==candidate['model'] and
        S.artifact(Path(__file__))==candidate['tool'],'Query source model or provider source changed')
    text,exports,imports=assembly(meta)
    S.check(S.checked(candidate['assembly']).read_text()==text and
        A.coff_symbols(S.checked(candidate['object']),C.FOREIGN)==(exports,imports) and
        set(candidate['exports'])==exports and set(candidate['imports'])==imports,'Query provider ASM/COFF changed')
    units=candidate['primitive_comparison']['units']
    original,embedded=[S.checked(row['object']) for row in units]
    before,after=normalized_primitive(original),normalized_primitive(embedded)
    S.check(before==after,'Primitive code/data/relocations/unwind changed beyond the two PUBLIC renames')
    original_text=Path(meta['source']['primitive_source']['path']).read_text()
    S.check(S.checked(units[0]['assembly']).read_text()==original_text and
        S.checked(units[1]['assembly']).read_text()==primitive_envelope(meta),
        'Primitive comparison assembly differs from immutable source')
    S.check(S.artifact(Path(candidate['assembler']['path']))==candidate['assembler'],'Query assembler changed')
    return dict(schema=1,verified=True,scope='seven_original_WinNT_readonly_natives_source_frames_ASM_COFF_only',
        candidate=S.artifact(path),source_native_methods=len(meta['source']['methods']),
        dynamic_method_class_File_FieldID_FMAP_and_String_layout_IDs=True,
        primitive_code_data_relocations_unwind_identical_after_exact_two_PUBLIC_renames=True,
        normal_Source_field_publication_required=True,runtime572_modified=False,
        shared_provider_registered=False,linked=False,executed=False,game_started=False)


def primitive_envelope(meta):
    return ('option casemap:none\n'+''.join(f'EXTERN {n}:{kind}\n' for n,kind in meta['source']['primitive_declarations'])+
        C.primitive_body(Path(meta['source']['primitive_source']['path']).read_text())+'\nEND\n')


def build(state,assembler,output):
    output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project readonly source candidate directory required')
    meta=contract(state);output.mkdir(parents=True)
    def assemble(path,obj,log):
        with (output/log).open('wb') as stream:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),path],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=90)
    text,exports,imports=assembly(meta)
    asm,obj=output/'provider.asm',output/'provider.obj';asm.write_text(text);assemble(asm,obj,'assembler.log')
    S.check(A.coff_symbols(obj,C.FOREIGN)==(exports,imports),'Query actual COFF imports/exports differ')
    units=[]
    for name,text in (('original',Path(meta['source']['primitive_source']['path']).read_text()),('embedded',primitive_envelope(meta))):
        path=output/(name+'-primitive.asm');path.write_text(text);target=path.with_suffix('.obj')
        assemble(path,target,name+'-primitive.log');units.append(dict(assembly=S.artifact(path),object=S.artifact(target)))
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-Windows-readonly-native-candidate',metadata=meta,
        kernel=S.artifact(KERNEL),model=S.artifact(ROOT/'scripts/windows-file-queries-source.py'),tool=S.artifact(Path(__file__)),
        assembler=S.artifact(assembler),assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        primitive_comparison=dict(units=units,only_envelope_removed_and_two_PUBLIC_symbols_renamed=C.RENAMES),
        shared_provider_registered=False,runtime572_modified=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'windows-file-queries/candidates'/uuid4().hex)
    args=parser.parse_args();print(build(args.state.resolve(),args.assembler.resolve(),args.output))
