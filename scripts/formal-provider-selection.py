"""Prepare and independently verify focused source images from the pending 26 packs."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'
DEFAULT_ASSEMBLER=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')
COMMON_SOURCES=('formal-provider-selection.py','prepare-class-init-probe.py','diagnostic-closure.py',
    'diagnostic-objects.py','parallel-diagnostic-assembly.py','canonical-link-response.py',
    'verify-diagnostic-closure.py','verify-initialization-closure.py','closure-batch-artifacts.py',
    'refresh-boot-unnamed-batch.py','batch-source.py','select-batch-dispatch.py','provider-verification-reuse.py')


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('formal_focused_provider_source','runtime-provider-source.py')


def checked(record):
    path=Path(record['path']).resolve()
    sdk=module('formal_focused_checked_sdk','canonical-link-response.py')
    allowed_sdk={p.resolve() for pair in sdk.sdk_libraries(winsock=True) for p in pair}
    S.check(path.is_relative_to(ROOT) or path.is_relative_to(Path('D:/Dev')) or path in allowed_sdk,
            'Focused selection input escaped project/tool/SDK roots')
    S.check(S.artifact(path)==record,'Focused selection input changed: '+str(path))
    return path


def provider_paths(value):
    rows=value if isinstance(value,list) else value['providers']
    paths=[]
    for row in rows:
        item=row if isinstance(row,str) else row.get('manifest',row)
        path=Path(item) if isinstance(item,str) else S.checked(item)
        path=path.resolve();S.check(path.is_relative_to(ART),'Focused provider escaped project artifacts')
        paths.append(path)
    S.check(len(paths)==26 and len(set(paths))==26,'Focused formal selection requires the exact 26-provider input set')
    return paths


def state_inputs(state_file):
    state_file=Path(state_file).resolve()
    S.check(state_file.is_relative_to(ART),'Focused input state must stay in project artifacts')
    state=S.read(state_file)
    values={key:Path(state[key]).resolve() for key in ('batch','plan','runtime','providers')}
    S.check(all(p.is_relative_to(ART) for p in values.values()),'Focused state escaped project artifacts')
    values['runtime']=values['runtime']/'boom-runtime.dll' if values['runtime'].is_dir() else values['runtime']
    paths=provider_paths(S.read(values['providers']))
    return state,values,paths


def prepare(state_file,output,*,method_roots,class_roots=(),admitted_methods=(),admitted_classes=(),
            source_profile=None,exports=(),optional_exports=(),harness_sources=(),assembler=DEFAULT_ASSEMBLER,workers=8,code_mib=8):
    output=Path(output).resolve();assembler=Path(assembler).resolve()
    S.check(output.is_relative_to(ART) and not output.exists(),'Use a fresh isolated focused source directory')
    S.check(bool(method_roots or class_roots),'Focused original source roots are required')
    state,values,paths=state_inputs(state_file)
    batch,plan,runtime=values['batch'],values['plan'],values['runtime']
    records={}
    def seal(path):
        record=S.artifact(path);old=records.setdefault(record['path'],record)
        S.check(old==record,'Focused input changed while sealing');return record
    state_record=seal(state_file);provider_list=seal(values['providers'])
    for path in [*(ROOT/p for p in S.TOOL_FILES),*(ROOT/'scripts'/p for p in COMMON_SOURCES),
                 *(Path(p) for p in harness_sources),assembler,assembler.with_name('link.exe'),runtime,runtime.with_name('runtime.json')]:
        seal(path)
    V=module('formal_focused_provider_verifier','verify-runtime-provider-pack.py')
    packs=V.load_packs(batch,plan,paths)
    S.check(len({p['manifest']['family'] for p in packs})==26,'Focused provider families are duplicated')
    identity,summary,_=S.base(batch,plan)
    for key in ('batch_summary','base_verification','source_plan','source_classes','source_methods'):
        seal(identity[key]['path'])
    for pack in packs:
        for record in (pack['reference'],pack['verification'],pack['manifest']['assembly'],pack['manifest']['object']):seal(record['path'])
        for key,record in pack['manifest'].items():
            if key.endswith('_metadata') and isinstance(record,dict) and 'digest' in record:seal(record['path'])
    methods=set(admitted_methods);classes=set(admitted_classes);profile_record=None
    if source_profile is not None:
        profile_record=seal(source_profile);profile=S.read(source_profile)
        S.check(profile['source_batch_summary_sha256']==identity['batch_summary']['digest']['sha256'],
                'Focused source-only profile belongs to another original batch')
        methods.update(profile['admitted_methods']);classes.update(profile.get('admitted_classes',[]))
    model=module('formal_focused_global_index','diagnostic-closure.py')
    coff=module('formal_focused_original_coff','verify-batch-assembly.py')
    known,providers,global_identity=model.globals_index(batch,summary,runtime,coff,packs,plan)
    selector=module('formal_focused_source_selector','prepare-class-init-probe.py')
    manifest=selector.prepare(batch,plan,output,list(class_roots),list(method_roots),
        diagnostic=dict(admit_methods=sorted(methods),admit_classes=sorted(classes),known_symbols=known,
                        data_providers=providers,global_identity=global_identity),
        provider_packs=paths,verified_provider_packs=packs)
    selected_indices=manifest.get('selected_runtime_provider_packs',[])
    foreign={'WaitOnAddress','WakeByAddressAll'}|{name for i in selected_indices for name in packs[i]['manifest'].get('allowed_foreign_imports',[])}
    public=set(model.pe_exports(runtime))
    for name in ('initialization-closure.asm','diagnostic-stops.asm'):
        public.update(re.findall(r'(?m)^PUBLIC (boom_\w+)\s*$',(output/name).read_text(encoding='utf-8')))
    for path in manifest['objects']:public.update(coff.coff_symbols(Path(path),foreign)[0])
    optional_added=sorted(set(optional_exports)&public)
    S.check(set(exports)<=public,'Focused observation export is not public in the actual selected source/runtime')
    manifest['exports']=list(manifest['exports'])+list(exports)+optional_added
    (output/'closure.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    D=module('formal_focused_object_assembler','diagnostic-objects.py')
    D.assemble(output,assembler,parallel_assembly=True,workers=workers,code_mib=code_mib)
    sealed=D.verify(output)
    R=module('formal_focused_canonical_link','canonical-link-response.py')
    families=sorted(packs[i]['manifest']['family'] for i in manifest.get('selected_runtime_provider_packs',[]))
    libraries=R.diagnostic_libraries(runtime,winsock='normal-native-libraries-v1' in families)[0]
    objects=[unit['object']['path'] for unit in sealed['units']]+manifest['objects']
    for path in [*objects,*libraries]:seal(path)
    image=output/'diagnostic-image.dll'
    lines=[*R.PREFIXES['diagnostic'],'/OUT:"'+str(image)+'"']
    lines+=['"'+str(path)+'"' for path in [*objects,*libraries]]
    lines+=['/EXPORT:'+symbol for symbol in sorted(set(manifest['exports']))]
    response=output/'link.rsp';response.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    R.verify(response,profile='diagnostic',output=image,objects=objects,library_choices=[libraries],exports=manifest['exports'])
    with (output/'link.log').open('wb') as log:
        result=subprocess.run([str(assembler.with_name('link.exe')),'@'+str(response)],stdout=log,stderr=subprocess.STDOUT,timeout=240)
    S.check(result.returncode==0,'Focused source link failed; inspect '+str(output/'link.log'))
    verify_module=module('formal_focused_independent_source_verifier','verify-diagnostic-closure.py')
    proof=verify_module.verify(output)
    proof_file=output/'selection-verification.json';S.write(proof_file,proof)
    for path in [output/'closure.json',output/'diagnostic.json',output/'initialization-closure.asm',
                 output/'diagnostic-stops.asm',output/D.RECEIPT,response,proof_file,image]:seal(path)
    for unit in sealed['units']:seal(unit['assembly']['path'])
    receipt=S.read(output/D.RECEIPT)
    for unit in receipt['units']:
        if 'parallel_receipt' in unit:seal(unit['parallel_receipt']['path'])
    for record in records.values():checked(record)
    images=dict(schema=1,scope='focused_original_source_with_26_individually_verified_provider_inputs',
        input_state=state_record,provider_list=provider_list,base=identity,
        source_selection_directory=str(output),source_manifest=S.artifact(output/'closure.json'),
        source_selection=S.artifact(proof_file),image=S.artifact(image),runtime=S.artifact(runtime),
        selection_request=dict(method_roots=list(method_roots),class_roots=list(class_roots),
            admitted_methods=sorted(methods),admitted_classes=sorted(classes),source_profile=profile_record,
            additional_observation_exports=list(exports),optional_observation_exports=list(optional_exports)),
        optional_added_exports=optional_added,
        providers=[dict(family=p['manifest']['family'],manifest=p['reference'],verification=p['verification'],
            metadata={k:v for k,v in p['manifest'].items() if k.endswith('_metadata') and isinstance(v,dict) and 'digest' in v},
            selected=i in manifest.get('selected_runtime_provider_packs',[])) for i,p in enumerate(packs)],
        selected_provider_families=families,link_inputs=[S.artifact(p) for p in [*objects,*libraries]],
        inputs=list(records.values()),helper=S.artifact(__file__),harness_sources=[S.artifact(p) for p in harness_sources],
        source_selection_independently_reverified=True,provider_inputs=26,runtime_acceptance_proven=False,
        metadata_fixture=False,Java_codegen_rerun=False,original_Java_or_metadata_modified=False,
        diagnostic_stops_replaced=False,executed=False,full_VM_startup=False,game_started=False)
    path=output/'images.json';S.write(path,images);return path


def verify(images_file):
    images_file=Path(images_file).resolve();S.check(images_file.is_relative_to(ART),'Focused evidence escaped artifacts')
    images=S.read(images_file)
    S.check(images['scope']=='focused_original_source_with_26_individually_verified_provider_inputs' and
            images['provider_inputs']==26 and images['source_selection_independently_reverified'] and
            not any(images[k] for k in ('runtime_acceptance_proven','metadata_fixture','Java_codegen_rerun',
                'original_Java_or_metadata_modified','diagnostic_stops_replaced','full_VM_startup','game_started')),
            'Focused source proof scope differs')
    S.check(images['helper']==S.artifact(__file__) and images['helper'] in images['inputs'] and
            all(record in images['inputs'] for record in images['harness_sources']), 'Focused helper/harness identity is not sealed')
    for record in images['inputs']:checked(record)
    directory=Path(images['source_selection_directory'])
    S.check(directory.is_relative_to(ART) and images_file==directory/'images.json','Focused evidence directory differs')
    S.check(checked(images['source_manifest'])==directory/'closure.json' and
            checked(images['source_selection'])==directory/'selection-verification.json' and
            checked(images['image'])==directory/'diagnostic-image.dll','Focused source artifacts belong to another directory')
    V=module('formal_focused_execution_source_verifier','verify-diagnostic-closure.py')
    proof=V.verify(directory)
    S.check(proof==S.read(images['source_selection']['path']),'Focused independent source verification differs')
    closure=S.read(directory/'closure.json');diagnostic=S.read(directory/'diagnostic.json')
    refs=[dict(manifest=p['manifest'],verification=p['verification']) for p in images['providers']]
    S.check(len(refs)==26 and refs==closure['runtime_provider_packs'],'Focused provider references differ from the verified source')
    selected=closure.get('selected_runtime_provider_packs',[])
    for i,row in enumerate(images['providers']):
        pack=S.read(checked(row['manifest']));checked(row['verification'])
        metadata={k:v for k,v in pack.items() if k.endswith('_metadata') and isinstance(v,dict) and 'digest' in v}
        S.check(row['family']==pack['family'] and row['metadata']==metadata and row['selected']==(i in selected) and
                pack['base']==images['base'],'Focused pack metadata/base or selection differs')
    S.check(images['selected_provider_families']==sorted(images['providers'][i]['family'] for i in selected),
            'Focused selected provider family set differs')
    runtime=checked(images['runtime']);global_identity=diagnostic['global_provider_identity']
    S.check(runtime==Path(global_identity['runtime_dll']).resolve() and
            images['runtime']['digest']['sha256']==global_identity['runtime_sha256'],'Focused runtime differs from the verified source')
    request=images['selection_request']
    S.check(request['method_roots']==[[r[k] for k in ('loader','owner','name','descriptor')] for r in closure['requested_method_roots']] and
            request['class_roots']==[[r[k] for k in ('loader','name')] for r in closure['requested_class_roots']] and
            request['admitted_methods']==diagnostic['admitted_methods'] and request['admitted_classes']==closure['admitted_classes'],
            'Focused root/admission request differs from actual source selection')
    S.check(set(images['optional_added_exports'])<=set(request['optional_observation_exports'])&set(closure['exports']),
            'Focused optional observation export was not linked')
    for record in images['inputs']:checked(record)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path)
    parser.add_argument('--output',type=Path,default=ART/'formal-provider-selections'/uuid4().hex)
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--entry',action='append',default=[])
    parser.add_argument('--class-root',action='append',default=[])
    parser.add_argument('--source-profile',type=Path)
    parser.add_argument('--export',action='append',default=[])
    parser.add_argument('--optional-export',action='append',default=[])
    parser.add_argument('--harness-source',type=Path,action='append',default=[])
    args=parser.parse_args()
    if args.verify:print(json.dumps(verify(args.verify)))
    else:
        S.check(args.state is not None,'Provide the pending 26-provider input state')
        print(prepare(args.state,args.output,method_roots=[tuple(s.split(':',3)) for s in args.entry],
            class_roots=[tuple(s.split(':',1)) for s in args.class_root],source_profile=args.source_profile,
            exports=args.export,optional_exports=args.optional_export,harness_sources=args.harness_source))
