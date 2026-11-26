"""Verify a formal ClassLoader pack in a fresh source selection with normal roots."""
import argparse
import ctypes as C
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


T=module('formal_class_loader_native_execution',ROOT/'tests/class_loader_assertions.py')
S=T.S
MODES=('cold00','cold01','cold10','cold11','concurrent','exceptions','oom','gc')


def forbid_old_contract(*args,**kwargs):
    raise AssertionError('Formal execution must not validate against the historical 22-provider candidate contract')


T.B.contract=forbid_old_contract
T.B.verify=forbid_old_contract


def run(args,log):
    with log.open('wb') as stream:
        subprocess.run([str(a) for a in args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)


def observation_image(selection,output,pack,meta):
    original=selection/'diagnostic-image.dll'
    recipe=selection/'link.rsp'
    lines=recipe.read_text(encoding='utf-8').splitlines()
    targets=[line for line in lines if line.upper().startswith('/OUT:')]
    S.check(len(targets)==1 and Path(targets[0][5:].strip('"')).resolve()==original and '/BREPRO' in lines and
        not any(line.upper().startswith('/FORCE') for line in lines),'Expected the independently verified reproducible link recipe')
    linker=Path(pack['assembler']['path']).with_name('link.exe')
    with tempfile.TemporaryDirectory(dir=output,prefix='control-link-') as tmp:
        control=Path(tmp)/original.name;rsp=Path(tmp)/'link.rsp'
        rsp.write_text('\n'.join(f'/OUT:"{control}"' if line==targets[0] else line for line in lines)+'\n',encoding='utf-8')
        run([linker,'@'+str(rsp)],output/'original-link-reproduction.log')
        S.check(S.digest(control)==S.digest(original),'The accepted original source link no longer reproduces its DLL')
    directory=output/'observation-image';directory.mkdir()
    image=directory/original.name
    required={f"boom_layout{meta['directives']}"}|{f'boom_t{v}' for v in meta['array_types'].values()}
    added=sorted('/EXPORT:'+name for name in required if '/EXPORT:'+name not in lines)
    replacement=[f'/OUT:"{image}"' if line==targets[0] else line for line in lines]+added
    rsp=directory/'link.rsp';rsp.write_text('\n'.join(replacement)+'\n',encoding='utf-8')
    run([linker,'@'+str(rsp)],output/'observation-export-link.log')
    objects=[Path(line.strip('"')) for line in lines if not line.startswith('/') and Path(line.strip('"')).suffix.lower() in ('.obj','.lib')]
    proof=dict(scope='source_image_relinked_with_read_only_observation_exports_only',original_image=S.artifact(original),
        original_link_recipe=S.artifact(recipe),observation_image=S.artifact(image),observation_link_recipe=S.artifact(rsp),
        added_exports=added,original_source_link_reproduced=True,all_object_and_library_inputs=[S.artifact(path) for path in objects],
        source_or_COFF_inputs_changed=False,Java_class_state_modified=False)
    S.write(output/'observation-exports.json',proof)
    return image,proof


def worker(output,mode):
    images=S.read(output/'images.json')
    S.check(S.artifact(Path(__file__))==images['execution_tool'],'Formal test tool changed')
    info=S.read(output/'formal-execution-input.json')
    pack=S.read(S.checked(info['formal_provider']))
    meta=info['metadata']
    S.check(pack['tool_sources']==S.tools_identity() and S.checked(images['formal_provider_verification'])==
        Path(info['formal_provider']['path']).with_name('verification.json'),'Formal worker source inputs changed')
    runtime=S.checked(images['runtime']);image=S.checked(images['image'])
    with os.add_dll_directory(str(runtime.parent)):
        runtime_image=C.CDLL(str(runtime));im=C.CDLL(str(image))
    descriptor=T.addr(im,f"boom_class{meta['directives']}")
    start=T.addr(im,'boom_probe_static_roots')
    count=T.Q.from_address(T.addr(im,'boom_probe_static_root_count')).value
    failure=T.Q.from_address(descriptor+56).value
    S.check(T.U.from_address(descriptor+8).value==0 and start<=failure<start+count*8 and (failure-start)%8==0 and
        T.Q.from_address(failure).value==0,'Original cold directives failure root must belong to the normal selected root bank')
    result=T.execute(output/'formal-execution-input.json',Path(images['source_selection_directory']),output,mode)
    S.check(T.U.from_address(descriptor+8).value==2 and T.Q.from_address(descriptor+56).value==failure,
        'Normal source initialization or its root cell changed')
    result.update(formal_provider_executed=True,old_22_candidate_contract_called=False,scratch_source_supplement_used=False,
        normal_source_failure_root=dict(offset_cells=(failure-start)//8,normal_root_cells=count,registered_in_normal_span=True),
        original_source_class_selected_by_provider_dependency=True)
    if mode=='gc':
        result['scratch_failure_root_span_registered']=result.pop('source_failure_root_span_registered')
        S.check(any(r['name']=='boom_probe_static_roots' for r in result['GC_root_regions']), 'Normal source roots were omitted from actual GC')
        result['source_failure_root_span_registered']=True
    S.write(output/(mode+'.json'),result)


def execute(state_path,output,reuse_source_images=None):
    state_path,output=Path(state_path).resolve(),Path(output).resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated formal execution output required')
    state=S.read(state_path)
    S.check(state['status']=='accepted' and state['provider_count']==23 and state['tool_sources']==S.tools_identity(),
        'Accepted current 23-provider source state required')
    paths=[Path(p) for p in S.read(state['providers'])]
    [formal]=[p for p in paths if S.read(p)['family']=='normal-class-loader-assertions-v1']
    V=module('formal_class_loader_current_provider_verification',ROOT/'scripts/verify-runtime-provider-pack.py')
    proof=V.verify(formal,Path(state['batch']),Path(state['plan']))
    S.check(proof==S.read(formal.with_name('verification.json')),'Fresh formal source/ASM/COFF verification differs')
    pack=S.read(formal);meta=S.read(S.checked(pack['class_loader_assertions_metadata']))
    S.check(4458 in pack['required_class_ids'],'Formal source selection must require the original directives state')
    output.mkdir(parents=True)
    if reuse_source_images:
        previous=S.read(reuse_source_images)
        selection=S.checked(previous['source_manifest']).parent
        source_proof=S.read(S.checked(previous['source_selection']))
        closure=S.read(selection/'closure.json')
        S.check(previous['formal_provider']==S.artifact(formal) and previous['formal_provider_verification']==S.artifact(formal.with_name('verification.json')) and
            previous['runtime']==S.artifact(Path(state['runtime'])/'boom-runtime.dll') and source_proof['verified'] and
            source_proof['closure_manifest_sha256']==S.digest(selection/'closure.json')['sha256'] and
            source_proof['diagnostic_manifest_sha256']==S.digest(selection/'diagnostic.json')['sha256'] and
            closure['source_batch_summary_sha256']==state['batch_summary_sha256'], 'Previously verified exact source selection differs')
        status=S.read(selection/'selection-verification-status.json')
        S.check(status['state']=='verified' and status['exit_code']==0,'A naturally completed source verification is required')
        for unit in source_proof['verified_assembly_objects']['units']:
            S.checked(unit['assembly']);S.checked(unit['object'])
        S.write(output/'reused-source-verification.json',dict(source_images=S.artifact(reuse_source_images),
            source_manifest=S.artifact(selection/'closure.json'),source_verification=S.artifact(selection/'selection-verification.json'),
            current_formal_provider_independently_reverified=True,source_tool_identity_unchanged=True,source_or_COFF_changed=False))
    else:
        old=ROOT/'.boom/nio-file-selections/6b30fc242db94a35b0a4b5c564390f39/admit.json'
        profile=S.read(old)
        S.check(4458 not in profile['admitted_classes'],'The test must not supply the missing class as a manual admission root')
        profile['source_batch_summary_sha256']=state['batch_summary_sha256']
        profile['origin']=S.artifact(old)
        admission=output/'source-profile.json';S.write(admission,profile)
        selection=output/'source-selection'
        args=[sys.executable,ROOT/'scripts/prepare-diagnostic-closure.py',state['batch'],'--plan',state['plan'],
            '--output',selection,'--runtime',Path(state['runtime'])/'boom-runtime.dll','--class-root','bootstrap:java/lang/ClassLoader',
            '--admit-profile',admission]
        for path in paths:args.extend(('--provider-pack',path))
        run(args,output/'prepare-source-selection.log')
    closure=S.read(selection/'closure.json')
    selected={c['class_id']:c for c in closure['selected_classes']}
    S.check(4458 in selected and all(r['class_id']!=4458 for r in closure['requested_class_roots']) and
        4458 not in closure['admitted_classes'],'Directives state must be selected through the actual formal provider dependency')
    references=closure['runtime_provider_packs']
    selected_packs=closure['selected_runtime_provider_packs']
    S.check(any(S.read(S.checked(references[i]['manifest']))['family']=='normal-class-loader-assertions-v1' for i in selected_packs) and
        '41548' in closure['selected_runtime_provider_natives'],
        'Formal source selection did not use the new provider')
    if not reuse_source_images:
        run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',ROOT/'scripts/Build-DiagnosticClosure.ps1',
            '-Batch',state['batch'],'-Plan',state['plan'],'-Output',selection,'-Runtime',state['runtime'],'-PreparedSelection'],
            output/'build-and-verify-source-selection.log')
    source_proof=S.read(selection/'selection-verification.json')
    S.check(source_proof['verified'],'Independent formal source selection verification failed')
    observed,export_proof=observation_image(selection,output,pack,meta)
    info=dict(kind='formal_ClassLoader_native_execution_inputs',formal_provider=S.artifact(formal),
        formal_input_state=S.artifact(state_path),metadata=dict(meta,base=pack['base'],input_state=S.artifact(state_path)),
        old_22_candidate_contract_called=False)
    S.write(output/'formal-execution-input.json',info)
    images=dict(image=S.artifact(observed),original_image=S.artifact(selection/'diagnostic-image.dll'),source_selection_directory=str(selection),
        runtime=S.artifact(Path(state['runtime'])/'boom-runtime.dll'),formal_provider=S.artifact(formal),
        formal_provider_verification=S.artifact(formal.with_name('verification.json')),source_selection=S.artifact(selection/'selection-verification.json'),
        source_manifest=S.artifact(selection/'closure.json'),execution_tool=S.artifact(Path(__file__)),
        scratch_source_supplement_used=False,original_Java_or_class_state_COFF_changed=False,observation_export_proof=S.artifact(output/'observation-exports.json'))
    S.write(output/'images.json',images)
    for mode in MODES:
        run([sys.executable,__file__,'--output',output,'--worker',mode],output/(mode+'.log'))
    result=dict(scope='formal_ClassLoader_pack_cold_native_execution_with_current_source_selection_and_normal_GC_roots',
        verified=True,formal_provider=images['formal_provider'],images=S.artifact(output/'images.json'),
        cases={mode:S.read(output/(mode+'.json')) for mode in MODES},input_provider_count=len(paths),selected_provider_count=len(selected_packs),
        original_source_class4458_selected=True,scratch_source_supplement_used=False,old_22_candidate_contract_called=False,
        Java_class_initialization_state_manually_written=False,original_Java_batch_recompiled=False,
        ClassLoader_assertion_map_Java_API_executed=False,entire_23_provider_runtime_execution_claimed=False,
        full_System_bootstrap=False,game_started=False,world_created=False)
    S.write(output/'result.json',result)
    print(output/'result.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reuse-source-images',type=Path)
    p.add_argument('--worker',choices=MODES);a=p.parse_args()
    if a.worker:worker(a.output.resolve(),a.worker)
    else:
        S.check(a.state is not None,'Formal source input state required')
        execute(a.state,a.output,a.reuse_source_images)
