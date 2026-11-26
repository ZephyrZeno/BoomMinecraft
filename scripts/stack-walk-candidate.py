"""Build/verify an unregistered, source-bound Class-only StackWalker candidate."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('stack_walk_candidate_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S,C,R,A=(module(name) for name in ('runtime-provider-source','stack-walk-source','verify-batch-frames','verify-batch-assembly'))
KERNEL=ROOT/'native/providers/stack_walk_class_only.asm.inc'


def contract(state_file):
    state_file=Path(state_file).resolve();S.check(state_file.is_relative_to(S.ART),'Project-owned verified input state required')
    state=S.read(state_file);batch,plan=Path(state['batch']),Path(state['plan']);identity,summary,classes=S.base(batch,plan)
    S.check(state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'] and
        state['current_source_provider_verification_complete'] is True,'Original current verified source provider base required')
    N=module('refresh-named-module-batch');_,lineage=N.verified_resolver(batch,summary,plan)
    meta=C.index(summary,classes,S);frame=Path(state['frame_manifest']);proof=frame.with_name('verification.json')
    F=module('native-frame-overlay')
    actual=F.verify(frame,batch,plan)
    S.check(actual==S.read(proof) and S.digest(proof)['sha256']==state['frame_verification_sha256'],
            'Actual original source frame overlay receipt differs')
    rows={row['id']:row for row in S.read(frame)['source']['original_native_declarations']}
    for row in meta['methods']:
        original=rows[row['method']]
        S.check(original['flags']==row['frame_flags']==32 and all(original[k]==row[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')), 'Original StackWalker native frame differs')
    runtime=Path(state['runtime']);runtime_meta=S.read(runtime/'runtime.json')
    S.check(S.digest(runtime/'boom-runtime.dll')['sha256']==state['runtime_sha256']==runtime_meta['sha256'], 'Source assembly runtime differs')
    kernels={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS}
    S.check(all(runtime_meta['sources'][name]==sha for name,sha in kernels.items()),'Candidate imports different runtime kernels')
    paths=S.read(state['providers']);provided=set()
    for path in paths:
        provider=S.read(path);receipt=S.read(Path(path).with_name('verification.json'))
        S.check(provider['tool_sources']==S.tools_identity() and receipt['verified'] and
                receipt['provider_manifest_sha256']==S.digest(path)['sha256'],'Original provider/current source receipt changed')
        provided.update(row['method'] for row in provider['methods'])
    S.check(not provided&{row['method'] for row in meta['methods']}, 'A source provider already implements the candidate natives')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,source_lineage=lineage,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(proof)),runtime_kernel_sha256=kernels,
        source_tools={name:S.artifact(ROOT/'scripts'/name) for name in ('stack-walk-source.py','stack-walk-candidate.py')},
        shared_tool_sources=S.tools_identity())


def assembly(meta):
    source=meta['source'];procs,data=C.native_imports(source)
    owners={row['class_id'] for row in source['methods']}
    data|={f'boom_class{ident}' for ident in owners}
    text='option casemap:none\n'+''.join(f'EXTERN {name}:{"PROC" if name in procs else "BYTE"}\n' for name in sorted(procs|data))
    text+=C.data(source)
    for row in source['methods']:
        ident=row['method'];text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,row['class_id'],C.POOL,C.SERVICE,row['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text(encoding='utf-8')+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{row['method']}{suffix}" for row in source['methods'] for suffix in ('','_native')}
    return text,exports,procs|data


def normalized_coff(path):
    P=module('parallel-diagnostic-assembly-candidate');obj=P.Coff(path)
    def symbol(row):
        return (row['name'],row['value'],obj.by_section[row['section']]['name'] if row['section']>0 else row['section'],row['kind'],row['storage'])
    sections={}
    for name,row in obj.sections.items():
        if name=='.debug$S':continue
        S.check(name in ('.text','.text$mn','.data','.bss','.rdata','.xdata','.pdata'),'Unexpected StackWalker execution COFF section')
        relocations=[]
        for offset,index,kind in row['reloc']:
            target=obj.index[index]
            S.check(target and target['storage']!=103 and
                    (target['section']<=0 or obj.by_section[target['section']]['name']!='.debug$S'),
                    'StackWalker execution section relocates to a filename/debug symbol')
            relocations.append((offset,kind,symbol(target)))
        sections[name]=(row['size'],row['flags'],hashlib.sha256(row['raw']).hexdigest(),relocations)
    symbols=sorted(symbol(row) for row in obj.index if row and row['storage']!=103 and
                   (row['section']<=0 or obj.by_section[row['section']]['name']!='.debug$S'))
    return dict(sections=sections,symbols=symbols)


def machine_contract(text,obj,assembler):
    """Reassemble the independently reconstructed text; compare all real bytes."""
    output=S.ART/'stack-walk/COFF-checks'/uuid4().hex;output.mkdir(parents=True)
    source,expected=output/'canonical.asm',output/'canonical.obj';source.write_text(text,encoding='utf-8')
    with (output/'assembler.log').open('xb') as log:
        run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(expected),str(source)],stdout=log,stderr=subprocess.STDOUT)
    S.check(run.returncode==0,'Independent canonical StackWalker reassembly failed')
    left,right=normalized_coff(obj),normalized_coff(expected)
    S.check(left==right,'Actual StackWalker instructions/data/relocation targets/symbols/unwind differ from canonical source')
    normal_hash=hashlib.sha256(json.dumps(left,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    S.write(output/'verification.json',dict(verified=True,scope='independently_reassembled_complete_nondebug_StackWalker_COFF',
        input_object=S.artifact(obj),canonical_source=S.artifact(source),canonical_object=S.artifact(expected),
        assembler=S.artifact(assembler),normalized_sha256=normal_hash,
        ignored_nonexecution_fields=['COFF_timestamp_and_physical_offsets','.file_auxiliary_filename','.debug$S'],
        source_Java_executed=False,game_started=False))
    return normal_hash


def verify(path):
    path=Path(path).resolve();S.check(path.is_relative_to(S.ART/'stack-walk'),'Isolated StackWalker candidate required')
    candidate=S.read(path);expected=contract(S.checked(candidate['metadata']['input_state']))
    S.check(candidate['metadata']==expected and S.read(S.checked(candidate['model']))==expected,'Candidate source model/inputs changed')
    text,exports,imports=assembly(expected)
    S.check(S.checked(candidate['assembly']).read_text(encoding='utf-8')==text and
            candidate['kernel']==S.artifact(KERNEL) and candidate['tool']==S.artifact(Path(__file__)), 'Candidate ASM/kernel/producer changed')
    S.check(candidate['exports']==sorted(exports) and candidate['imports']==sorted(imports) and
            A.coff_symbols(S.checked(candidate['object']),C.FOREIGN)==(exports,imports), 'Candidate actual COFF declarations differ')
    S.check(S.artifact(candidate['assembler']['path'])==candidate['assembler'],'Pinned assembler changed')
    machine=machine_contract(text,S.checked(candidate['object']),Path(candidate['assembler']['path']))
    return dict(verified=True,scope='unregistered_original_Class_only_StackWalker_source_ASM_and_actual_COFF',
        candidate=S.artifact(path),native_methods=3,source_model=S.artifact(candidate['model']['path']),
        source_java_callback='intact_original_doStackWalk',callback_execution_verified=False,
        canonical_reassembly_all_nondebug_bytes_and_relocations_verified=True,normalized_COFF_sha256=machine,
        registered=False,full_selection_reverified=False,runtime_acceptance_complete=False,game_started=False,world_created=False)


def build(state,output,assembler):
    output,assembler=Path(output).resolve(),Path(assembler).resolve()
    S.check(output.is_relative_to(S.ART/'stack-walk') and not output.exists(),'Fresh isolated candidate output required')
    metadata=contract(state);text,exports,imports=assembly(metadata);snapshot=S.tools_identity()
    output.mkdir(parents=True);source=output/'candidate.asm';obj=output/'candidate.obj'
    source.write_text(text,encoding='utf-8');S.write(output/'model.json',metadata)
    with (output/'assembler.log').open('xb') as log:
        result=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT)
    S.check(result.returncode==0,'Actual StackWalker candidate assembly failed; retain assembler.log')
    S.check(S.tools_identity()==snapshot and contract(state)==metadata,'Candidate source inputs changed during build')
    candidate=dict(schema=1,metadata=metadata,assembly=S.artifact(source),object=S.artifact(obj),model=S.artifact(output/'model.json'),
        kernel=S.artifact(KERNEL),tool=S.artifact(Path(__file__)),assembler=S.artifact(assembler),exports=sorted(exports),imports=sorted(imports),
        registered=False,full_selection_reverified=False,executed=False,accepted=False,game_started=False,world_created=False)
    S.write(output/'candidate.json',candidate);proof=verify(output/'candidate.json');S.write(output/'verification.json',proof)
    return output/'candidate.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('build','verify'))
    p.add_argument('--state',type=Path);p.add_argument('--output',type=Path);p.add_argument('--candidate',type=Path)
    p.add_argument('--assembler',type=Path,default=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe'))
    a=p.parse_args()
    if a.action=='build':print(build(a.state,a.output,a.assembler))
    else:print(json.dumps(verify(a.candidate)))
