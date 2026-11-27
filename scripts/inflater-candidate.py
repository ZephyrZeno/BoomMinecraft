"""Unregistered normal-source Inflater native subset, using frozen ASM cores."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('inflater_candidate_'+name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


S,C,R,A,F,Z,P=(module(n) for n in ('runtime-provider-source','inflater-source','verify-batch-frames','verify-batch-assembly','native-frame-overlay','zlib-stream-candidate','stack-walk-candidate'))
KERNEL=ROOT/'native/providers/inflater_normal.asm.inc'
CORE_SOURCE={'raw':'6be97c2d2305ce6cc9dc0deb3f2781214525dd6ac8560d3a3b19c67689bbb3bd','zlib':'83893490391272283eb7b854f6fb02d6e52aa10456218f5c03fee97e9cad8501'}


def contract(state_file,core_file):
    state_file,core_file=Path(state_file).resolve(),Path(core_file).resolve();state=S.read(state_file)
    S.check(state['current_source_provider_verification_complete'] is True and state['provider_count']==31 and
        state['status'] in ('pending_runtime_acceptance','accepted'),'Current source-verified provider inputs required')
    identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(identity['batch_summary']['digest']['sha256']==state['batch_summary_sha256'] and identity['base_verification']['digest']['sha256']==state['batch_verification_sha256'],'Current source batch proof differs')
    N=module('refresh-named-module-batch');_,lineage=N.verified_resolver(Path(state['batch']),summary,Path(state['plan']))
    meta=C.index(summary,classes,S);frame=Path(state['frame_manifest']);receipt=frame.with_name('verification.json')
    actual=F.verify(frame,Path(state['batch']),Path(state['plan']))
    S.check(actual==S.read(receipt) and S.digest(receipt)['sha256']==state['frame_verification_sha256'],'Actual native source/frame proof differs')
    rows={r['id']:r for r in S.read(frame)['source']['original_native_declarations']}
    for native in meta['methods']:
        original=rows[native['method']]
        S.check(original['flags']==32 and all(original[k]==native[k] for k in ('class_id','class_sha256','loader','source_id','name','descriptor','access')),'Original Inflater source native frame differs')
    core=S.read(core_file);proof=Z.verify(core_file)
    S.check(core['sources']['kernel']['sha256']==CORE_SOURCE['zlib'] and core['raw']['layout']['kernel_sha256']==CORE_SOURCE['raw'],'Frozen decoder private layout differs')
    runtime=Path(state['runtime']);runtime_meta=S.read(runtime/'runtime.json')
    S.check(S.digest(runtime/'boom-runtime.dll')['sha256']==state['runtime_sha256']==runtime_meta['sha256'],'Original ASM runtime changed')
    kernels={'native/runtime/'+n:S.digest(ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS}
    S.check(all(runtime_meta['sources'][n]==h for n,h in kernels.items()),'Inflater imports different runtime kernels')
    paths=S.read(state['providers']);provided=set();families=set()
    S.check(len(paths)==state['provider_count'],'Current provider count/list differs')
    for path in paths:
        provider=S.read(path);v=S.read(Path(path).with_name('verification.json'))
        S.check(provider['tool_sources']==S.tools_identity() and v['verified'] and v['provider_manifest_sha256']==S.digest(path)['sha256'],'Current provider manifest/source receipt differs')
        S.check(provider['family'] not in families,'Duplicate provider family');families.add(provider['family']);provided.update(r['method'] for r in provider['methods'])
    S.check(not provided&{m['method'] for m in meta['methods']} and set(meta['required_provider_families'])<=families,'Inflater candidate collision or missing dependency')
    return dict(base=identity,input_state=S.artifact(state_file),source=meta,policy=C.POLICY,source_lineage=lineage,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(receipt)),runtime_kernel_sha256=kernels,tool_sources=S.tools_identity(),
        core=dict(candidate=Z.artifact(core_file),assembly=core['assembly'],object=core['object'],raw_object=core['raw']['object'],
            raw_candidate=core['raw']['candidate'],source_sha256=CORE_SOURCE,actual_image_sha256=proof['complete_image_sha256'],
            private_read_only_zlib_fields=dict(phase=12,need_dictionary_phase=7,DICTID=32,output_Adler=28)),
        source_tools={n:S.artifact(ROOT/'scripts'/n) for n in ('inflater-source.py','inflater-candidate.py','stack-walk-candidate.py','zlib-stream-candidate.py')},
        input_provider_runtime_acceptance=bool(state.get('runtime_acceptance_complete',False)),candidate_registered=False)


def assembly(meta):
    source=meta['source'];procs,data=C.native_imports(source);owner=source['owner'];data|={f'boom_class{owner}'}
    text='option casemap:none\n'+''.join(f'EXTERN {n}:{"PROC" if n in procs else "BYTE"}\n' for n in sorted(procs|data))
    text+=C.data(source)
    for row in source['methods']:
        mid=row['method'];text+=f'.code\nPUBLIC boom_m{mid}\nPUBLIC boom_m{mid}_native\n'
        text+=R.native_adapter(mid,owner,C.POOL,C.SERVICE,row['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text(encoding='utf-8')+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{r['method']}{suffix}" for r in source['methods'] for suffix in ('','_native')}
    return text,exports,procs|data


def machine(text,obj,assembler):
    directory=S.ART/'inflater-normal/machine-checks'/uuid4().hex;directory.mkdir(parents=True);source,expected=directory/'canonical.asm',directory/'canonical.obj'
    source.write_text(text,encoding='utf-8',newline='\n')
    with (directory/'assembler.log').open('xb') as log:run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(expected),str(source)],stdout=log,stderr=subprocess.STDOUT)
    S.check(run.returncode==0,'Independent Inflater source assembly failed')
    actual=P.normalized_coff(obj);S.check(actual==P.normalized_coff(expected),'Actual Inflater COFF code/data/symbols/relocations/unwind differs')
    return dict(canonical_source=S.artifact(source),canonical_object=S.artifact(expected),normalized_coff_sha256=hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest())


def verify(path):
    path=Path(path).resolve();S.check(path.is_relative_to(S.ART/'inflater-normal'),'Isolated Inflater candidate required');row=S.read(path)
    meta=contract(S.checked(row['metadata']['input_state']),Z.checked(row['metadata']['core']['candidate']))
    S.check(row['metadata']==meta and S.read(S.checked(row['model']))==meta,'Inflater current source/model inputs differ')
    text,exports,imports=assembly(meta)
    S.check(row['kernel']==S.artifact(KERNEL) and row['tool']==S.artifact(__file__) and S.checked(row['assembly']).read_text(encoding='utf-8')==text,'Inflater source/kernel/ASM changed')
    S.check(row['exports']==sorted(exports) and row['imports']==sorted(imports) and A.coff_symbols(S.checked(row['object']),C.FOREIGN)==(exports,imports),'Actual Inflater COFF exports/imports differ')
    assembler=Path(row['assembler']['path']);S.check(row['assembler']==S.artifact(assembler),'Inflater assembler changed');proof=machine(text,S.checked(row['object']),assembler)
    return dict(verified=True,scope='unregistered_original_Inflater_native_subset_source_frames_and_actual_COFF',candidate=S.artifact(path),machine=proof,
        supported_native_operations=['initIDs','init','getAdler','reset','end','inflateBytesBytes'],unsupported_context=20,
        frozen_decoder_objects_reused=True,original_Java_callbacks_executed=False,original_Java_constructor_executed=False,
        builtin_zip_implemented=False,generic_DataFormat_message=True,complete_Inflater_compatibility=False,registered=False,full_selection_reverified=False,game_started=False)


def build(state,core,output,assembler):
    output=Path(output).resolve();assembler=Path(assembler).resolve();S.check(output.is_relative_to(S.ART/'inflater-normal') and not output.exists(),'Fresh isolated Inflater output required')
    metadata=contract(state,core);snapshot=S.tools_identity();text,exports,imports=assembly(metadata);output.mkdir(parents=True)
    source,obj=output/'provider.asm',output/'provider.obj';source.write_text(text,encoding='utf-8',newline='\n');S.write(output/'model.json',metadata)
    with (output/'assembler.log').open('xb') as log:run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT)
    S.check(run.returncode==0,'Actual Inflater assembly failed; retain assembler.log')
    S.check(snapshot==S.tools_identity(),'Shared namespace changed during candidate build')
    row=dict(schema=1,metadata=metadata,model=S.artifact(output/'model.json'),assembly=S.artifact(source),object=S.artifact(obj),kernel=S.artifact(KERNEL),tool=S.artifact(__file__),assembler=S.artifact(assembler),
        exports=sorted(exports),imports=sorted(imports),registered=False,accepted=False,executed=False,game_started=False)
    path=output/'candidate.json';S.write(path,row);S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('build','verify'));p.add_argument('--state',type=Path);p.add_argument('--core',type=Path);p.add_argument('--output',type=Path);p.add_argument('--candidate',type=Path)
    p.add_argument('--assembler',type=Path,default=Z.B.C.TOOLS/'ml64.exe');a=p.parse_args()
    if a.action=='build':print(build(a.state,a.core,a.output,a.assembler))
    else:print(json.dumps(verify(a.candidate),indent=2))
