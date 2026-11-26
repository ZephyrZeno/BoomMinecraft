"""Prepare compiler-owned normal lambda classes and sparse identity manifests."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import zipfile
import subprocess
import re


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('normal_lambda_contract',ROOT/'scripts/normal-lambda-source.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
S=C.S


def rows(archive,name):return [C.json.loads(line) for line in archive.open(name)]


def prepare(batch,plan,requests,output,lock=None):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project lambda expansion output required')
    sources=C.Sources(batch,plan,lock);contracts=[];rejected=[]
    for request in requests:
        loader,name,constant=request.split(':',2);cls=sources.lookup(loader,name)
        S.check(cls is not None,'Original requested lambda host missing')
        try:contracts.append(C.site(sources,cls,int(constant,0)))
        except C.Deferred as error:rejected.append(dict(request=request,reason=str(error),expanded=False))
    S.check(len({c['binding_label'] for c in contracts})==len(contracts),'Duplicate expansion call site')
    contracts.sort(key=lambda c:(c['host']['origin']['loader'],c['host']['class_id'],c['constant']))
    summary=sources.summary
    type_base=summary['runtime_metadata']['type_capacity'];field_base=summary['runtime_metadata']['field_capacity']
    method_base=sum(len(c['method_ids']) for c in sources.classes)
    with zipfile.ZipFile(S.checked(summary['class_literals']['index'])) as archive:
        mirrors={r['type_id']:r for r in rows(archive,'types.jsonl')}
    output.mkdir(parents=True);generated=[];next_field=field_base
    for n,contract in enumerate(contracts):
        typ=type_base+n;method=method_base+3*n
        blob=C.generated_class(contract);raw=C.I.Source(blob)
        relative=Path('generated')/(contract['generated_name']+'.class');path=output/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
        parent=sources.lookup('bootstrap','java/lang/Object');iface=sources.types[contract['interface']['class_id']]
        inherited=sorted({parent['id'],iface['id']}|set(iface['ancestors']))
        captures=[dict(id=next_field+i,index=i,name='c'+str(i),descriptor=ty,offset=i*8,reference=True,storage_bytes=8)
            for i,ty in enumerate(contract['captures'])]
        next_field+=len(captures)
        host=contract['host'];origin=dict(loader=host['origin']['loader'],binary_name=contract['generated_name'].replace('/','.'),
            source_id='boom:'+C.RULE,jar_entry='<generated>/'+contract['generated_name']+'.class',java_class_major=65,
            sha256=hashlib.sha256(blob).hexdigest(),generated=dict(generator=C.RULE,abi=1,host_loader=host['origin']['loader'],
                host_class=host['name'],host_source_id=host['origin']['source_id'],host_sha256=host['origin']['sha256'],
                host_method=contract['source_instruction']['method'],host_Code_sha256=contract['source_instruction']['code_sha256'],
                site=contract['constant'],pc=contract['source_instruction']['pc']))
        methods=[]
        for i,m in enumerate(raw.methods):
            body=raw.code(m)
            methods.append(dict(id=method+i,class_id=typ,name=m['name'],descriptor=m['descriptor'],access=m['access'],
                code_length=len(body['bytes']),code_sha256=hashlib.sha256(body['bytes']).hexdigest(),
                frame_flags=4|16|int(m['name']=='<init>'),original=False))
        mirror=dict(mirrors[host['class_id']],type_id=typ,superclass=parent['id'],component=None,
            flags=(mirrors[host['class_id']]['flags']&1)|2,raw_access=raw.access,major=65)
        generated.append(dict(contract=contract,class_file=S.artifact(path),origin=origin,type_id=typ,class_id=typ,
            runtime_class_name=C.runtime_class_name(contract,typ),
            layout=dict(abi=2,payload_bytes=len(captures)*8,reference_prefix=len(captures),fields=captures),
            type=dict(id=typ,kind=1,marker_flags=0,parent_component=parent['id'],ancestors=inherited,
                defining_loader=host['origin']['loader'],name=contract['generated_name'],source_sha256=origin['sha256']),
            class_mirror=mirror,methods=methods,new_arrays=[],array_of_generated_class_supported=False,
            class_initialization_state_initial=0,class_failure_root_initial=0,additional_instance_roots=False,
            object_constructor=C.source_member(sources,parent,'<init>','()V')))
    manifest=dict(schema=1,scope='normal_lambda_sparse_expansion_source_and_generated_classfiles_only',rule=C.RULE,
        base=sources.base,policy=C.POLICY,source_rule=S.artifact(ROOT/'scripts/normal-lambda-source.py'),
        tool=S.artifact(Path(__file__)),generated=generated,rejected=rejected,
        original_ranges=dict(classes=len(sources.classes),types=type_base,methods=method_base,fields=field_base),
        appended_ranges=dict(types=[type_base,type_base+len(generated)],methods=[method_base,method_base+3*len(generated)],
            fields=[field_base,next_field]),
        original_ids_unchanged=True,original_Java_Code_and_COFF_unchanged=True,
        original_module_identity_from_host=True,sparse_catalog_required=True,shared_batch_modified=False,
        actual_runtime_metadata_dispatch_Class_names_frames_extension_complete=False,
        assembled=False,linked=False,executed=False,game_started=False)
    file=output/'expansion.json';S.write(file,manifest);return file


def assemble(manifest_file,assembler):
    manifest=S.read(manifest_file);S.check(manifest['source_rule']==S.artifact(ROOT/'scripts/normal-lambda-source.py'),
        'Lambda rule source changed')
    sources=C.Sources(Path(manifest['base']['batch']),Path(manifest['base']['plan']))
    spec=importlib.util.spec_from_file_location('normal_lambda_MASM',ROOT/'scripts/normal-lambda-assembly.py')
    generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
    text=generator.module(manifest,sources)
    symbols=S.module('normal_lambda_symbols','batch-source.py')
    definitions={m[1] for m in re.finditer(r'(?m)^(boom_\w+)(?::|\s+(?:PROC|LABEL|QWORD|DWORD|BYTE|WORD)\b)',text)}
    procedures={m[1] for m in re.finditer(r'(?m)^(boom_\w+)\s+PROC\b',text)}
    references=set(re.findall(r'\bboom_\w+\b',text))-definitions
    calls=set(re.findall(r'(?m)^\s*(?:call|jmp)\s+(boom_\w+)\b',text))
    # Trace row definitions are part of the required contiguous derived frame
    # table. They must remain externals until that table is actually extended.
    text='option casemap:none\n'+''.join(f'EXTERN {n}:{"PROC" if n in calls else "BYTE"}\n' for n in sorted(references))+text+'\nEND\n'
    path=manifest_file.parent/'adapters.asm';obj=path.with_suffix('.obj');S.check(not path.exists(),'Lambda adapters already exist')
    path.write_text(text)
    with (manifest_file.parent/'assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),path],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
    A=S.module('normal_lambda_COFF','verify-batch-assembly.py');exports,imports=A.coff_symbols(obj)
    expected=set(re.findall(r'(?m)^PUBLIC (boom_\w+)$',text))
    S.check(exports==expected and imports==references,'Actual lambda adapter COFF symbols differ from derived ASM')
    record=dict(schema=1,scope='normal_lambda_adapter_ASM_COFF_only_not_linked_runtime_acceptance',
        expansion=S.artifact(manifest_file),assembly=S.artifact(path),object=S.artifact(obj),
        assembler=S.artifact(assembler),generator=S.artifact(ROOT/'scripts/normal-lambda-assembly.py'),
        exports=sorted(exports),imports=sorted(imports),assembled=True,
        runtime_metadata_dispatch_Class_names_frames_extension_complete=False,linked=False,executed=False,game_started=False)
    receipt=manifest_file.parent/'adapter-assembly.json';S.write(receipt,record);return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--batch',type=Path,required=True);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--site',action='append',required=True,help='loader:class:constant_pool_index')
    parser.add_argument('--lock',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--assembler',type=Path)
    args=parser.parse_args();file=prepare(args.batch.resolve(),args.plan.resolve(),args.site,args.output,args.lock)
    print(assemble(file,args.assembler.resolve()) if args.assembler else file)
