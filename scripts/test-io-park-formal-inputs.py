"""Verify formal IO8/Parker inputs and reject mutated source/root contracts.

No Java execution or main startup. Current source verification is mandatory;
only our immutable ASM/COFF caches may be copied into new isolated directories.
"""
import argparse
import copy
import importlib.util
from pathlib import Path
import shutil
import struct
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('formal_io_park_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source');V=module('verify-runtime-provider-pack');R=module('revalidate-runtime-provider-cache')
N=module('provider-native-roots')
FAMILIES={'normal-file-input-readonly-v1':'file_input_metadata','normal-unsafe-park-v1':'unsafe_park_metadata'}


def clone(path,directory):
    directory.mkdir(parents=True);manifest=copy.deepcopy(S.read(path))
    for key in ('assembly','object',FAMILIES[manifest['family']]):
        before=S.checked(manifest[key]);after=directory/before.name;shutil.copy2(before,after);manifest[key]=S.artifact(after)
    return manifest


def verify(state_file,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh formal IO/Parker test output required')
    output.mkdir(parents=True);state=S.read(state_file)
    S.check(state['provider_count']==31 and state['current_source_provider_verification_complete'] and
        not state['runtime_acceptance_complete'],'Expected fresh source-verified pending 31 inputs')
    paths=[Path(p) for p in S.read(state['providers'])];batch,plan=Path(state['batch']),Path(state['plan'])
    snapshot=S.tools_identity();S.check(state['tool_sources']==snapshot,'Formal provider tools changed')
    packs=V.load_packs(batch,plan,paths);members={p['manifest']['family']:p for p in packs}
    S.check(len(packs)==len(members)==31 and set(FAMILIES)<=set(members),'Incomplete formal family set')
    records=[];negative=[]
    with V.S.base_scope(batch,plan):
        for family,key in FAMILIES.items():
            pack=members[family];path=Path(pack['reference']['path']);manifest=pack['manifest'];meta=S.read(S.checked(manifest[key]))
            physical=N.provider_projection(manifest,meta);proof=V.verify(path,batch,plan)
            S.check(proof==S.read(path.with_name('verification.json')) and proof['source_native_root_spans']==physical,
                'Formal native root/source receipt differs')
            S.check(manifest['required_java_methods']==meta['required_java_methods'] and
                manifest['required_provider_families']==meta['required_provider_families'] and manifest['native_java_upcalls'],
                'Formal original callbacks or dependencies are absent')
            records.append(dict(family=family,manifest=pack['reference'],verification=pack['verification'],physical_roots=physical))
            for case in ('omit_roots','wrong_count','wrong_symbol','omit_export','omit_Java_callbacks','wrong_frame_claim','nonzero_COFF_root'):
                directory=S.ART/'runtime-providers'/(output.name+'-negative')/family/case
                bad=clone(path,directory)
                if case=='omit_roots':bad.pop('native_root_spans')
                elif case=='wrong_count':bad['native_root_spans'][0]['count']-=1
                elif case=='wrong_symbol':bad['native_root_spans'][0]['symbol']=bad['pool_symbol']
                elif case=='omit_export':bad['exports'].remove(bad['native_root_spans'][0]['symbol'])
                elif case=='omit_Java_callbacks':bad['required_java_methods']=[]
                elif case=='wrong_frame_claim':bad['native_java_upcalls']=False
                else:
                    obj=Path(bad['object']['path']);raw=bytearray(obj.read_bytes());row=physical[0]
                    position=struct.unpack_from('<I',raw,20+40*(row['section_index']-1)+20)[0]
                    raw[position+row['offset']]=1;obj.write_bytes(raw);bad['object']=S.artifact(obj)
                target=directory/'provider.json';S.write(target,bad)
                try:V.verify(target,batch,plan)
                except ValueError as error:
                    negative.append(dict(family=family,case=case,manifest=S.artifact(target),rejected=True,error=str(error)))
                else:raise ValueError('Mutated formal source/root contract accepted: '+case)
    # A second cache pass must move both metadata files and preserve actual bytes.
    cache=S.ART/'runtime-providers'/(output.name+'-cache-replay')
    refreshed=R.refresh_packs([members[family]['reference']['path'] for family in FAMILIES],batch,plan,Path(state['frame_manifest']),cache)
    replay=[]
    for path in refreshed:
        current=S.read(path);old=members[current['family']]['manifest'];key=FAMILIES[current['family']]
        S.check(all(current[k]['digest']==old[k]['digest'] for k in ('assembly','object',key)) and
            Path(current[key]['path']).parent==path.parent,'Native root cache altered or failed to relocate immutable source metadata')
        replay.append(dict(manifest=S.artifact(path),verification=S.artifact(path.with_name('verification.json'))))
    S.check(S.tools_identity()==snapshot,'Formal source tools changed during validation')
    result=dict(verified=True,scope='31_source_provider_inputs_and_IO_Parker_source_root_negative_checks_only',input_state=S.artifact(state_file),
        families=records,negative_cases=negative,cache_replay=replay,provider_count=31,root_counts=[4096,16384],
        registered_Java_natives=10,formal_closure_execution_verified=False,main_executed=False,runtime_acceptance=False,game_started=False,
        test_tool=S.artifact(Path(__file__)))
    target=output/'result.json';S.write(target,result);return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'formal-io-park-input-tests'/uuid4().hex)
    args=parser.parse_args();print(verify(args.state.resolve(),args.output))
