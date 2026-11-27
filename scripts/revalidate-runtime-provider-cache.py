"""Copy our immutable ASM/COFF cache and accept it only after current verification.

Producer provenance is retained separately. Current source models reconstruct
all declarations, metadata, canonical ASM and COFF contracts before publication.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import importlib.util
import time

spec=importlib.util.spec_from_file_location('provider_cache_revalidation_io',Path(__file__).with_name('runtime-provider-source.py'))
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)


def copy_record(record,directory):
    source=S.checked(record);target=Path(directory)/source.name
    S.check(not target.exists(),'Cache destination already exists')
    shutil.copy2(source,target);actual=S.artifact(target)
    S.check(actual['digest']=={k:record['digest'][k] for k in ('size','sha256')},'Cache copy changed the original bytes')
    return actual


def compatible_base(previous,current):
    """Permit a new compiler/build only with the same source and public ABI.

    This is a reuse precondition, never an acceptance receipt. The complete
    current source/ASM/COFF verifier still runs before anything is published.
    """
    for key in ('input_fingerprint','ir_identity','runtime_layout_abi','context_bytes',
                'source_frame_abi','class_pool_abi','source_transform_chain'):
        S.check(previous[key]==current[key],'Provider cache source/ABI changed: '+key)
    for key in ('source_classes','source_methods','source_plan'):
        S.check(previous[key]['digest']==current[key]['digest'],'Provider cache original source changed: '+key)
    return current


def refresh_frames(old_path,batch,plan,output):
    old_path=Path(old_path).resolve();output=Path(output).resolve()
    S.check(output.is_relative_to(S.ART/'native-frame-overlays') and not output.exists(),'Frame cache requires a fresh project overlay directory')
    old=S.read(old_path);receipt=old_path.with_name('verification.json');proof=S.read(receipt)
    S.check(proof['verified'] and proof['manifest_sha256']==S.digest(old_path)['sha256'],'Original frame cache receipt differs')
    F=S.module('cache_current_frame_model','native-frame-overlay.py');m=copy.deepcopy(old);output.mkdir(parents=True)
    current=F.index(batch,plan)
    compatible_base(old['source']['base'],current['base'])
    for key in ('rows','original_native_declarations','added_native_ids','base_rows','runtime_kernel_sha256'):
        S.check(old['source'][key]==current[key],'Native frame cache semantic source changed: '+key)
    m['source']=current;m['reused_producer_base']=old['source']['base']
    m['assembly']=copy_record(old['assembly'],output);m['object']=copy_record(old['object'],output)
    m['tool_sources']=F.tools();m['reused_producer_manifest']=S.artifact(old_path);m['reused_producer_verification']=S.artifact(receipt)
    m['reused_producer_tool_sources']=old['tool_sources'];m['COFF_reassembled_this_build']=False
    manifest=output/'overlay.json';S.write(manifest,m)
    accepted=F.verify(manifest,batch,plan)
    S.write(output/'verification.json',accepted)
    return manifest


def refresh_packs(paths,batch,plan,frame_path,output):
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART/'runtime-providers') and not output.exists(),'Provider cache requires a fresh project output directory')
    frame_path=Path(frame_path).resolve();frame_reference=dict(manifest=S.artifact(frame_path),verification=S.artifact(frame_path.with_name('verification.json')))
    records=[];output.mkdir(parents=True);current_base=None
    for original in paths:
        started=time.monotonic()
        original=Path(original).resolve();old=S.read(original);receipt=original.with_name('verification.json');prior=S.read(receipt)
        S.check(prior['verified'] and prior['provider_manifest_sha256']==S.digest(original)['sha256'],'Original provider cache receipt differs')
        directory=output/old['family'];directory.mkdir();m=copy.deepcopy(old)
        if 'base' in old:
            if current_base is None:current_base=S.base(batch,plan)[0]
            m['base']=compatible_base(old['base'],current_base);m['reused_producer_base']=old['base']
            m['runtime_kernel_sha256']={p:S.digest(S.ROOT/p)['sha256'] for p in old['runtime_kernel_sha256']}
        artifact_keys=['assembly','object']+[k for k,v in old.items() if k.endswith('_metadata') and isinstance(v,dict) and 'digest' in v]
        for name in artifact_keys:m[name]=copy_record(old[name],directory)
        extra=[]
        for row in old.get('additional_objects',[]):
            changed=copy.deepcopy(row);changed['object']=copy_record(row['object'],directory);extra.append(changed)
        if extra:
            m['additional_objects']=extra
            S.check(len(extra)==1 and old.get('ROM_object')==old['additional_objects'][0]['object'],'Readonly cache ROM alias differs')
            m['ROM_object']=extra[0]['object']
        m['tool_sources']=S.tools_identity();m['reused_producer_manifest']=S.artifact(original);m['reused_producer_verification']=S.artifact(receipt)
        m['reused_producer_tool_sources']=old['tool_sources'];m['native_ASM_codegen_rerun']=False;m['COFF_reassembled_this_build']=False
        m['reused_producer_elapsed_ms']=old.get('elapsed_ms');m['elapsed_ms']=round((time.monotonic()-started)*1000)
        if 'frame_overlay' in m:m['frame_overlay']=frame_reference
        manifest=directory/'provider.json';S.write(manifest,m);records.append(manifest)
    V=S.module('cache_current_provider_models','verify-runtime-provider-pack.py');proofs=[]
    with V.S.base_scope(batch,plan):
        for manifest in records:proofs.append(V.verify(manifest,batch,plan))
    for manifest,proof in zip(records,proofs):S.write(manifest.with_name('verification.json'),proof)
    S.write(output/'accepted-caches.json',dict(schema=1,providers=[str(p) for p in records],
        current_source_models_independently_verified=True,producer_provenance_retained=True,ASM_and_COFF_bytes_unchanged=True,game_started=False))
    return records


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frame-cache',type=Path);p.add_argument('--provider-list',type=Path);p.add_argument('--frame-overlay',type=Path)
    a=p.parse_args()
    if a.frame_cache:
        result=refresh_frames(a.frame_cache,a.batch,a.plan,a.output);print(json.dumps(dict(frame_overlay=str(result),game_started=False)))
    else:
        S.check(a.provider_list is not None and a.frame_overlay is not None,'Provider refresh requires a cache list and verified frame overlay')
        result=refresh_packs(S.read(a.provider_list),a.batch,a.plan,a.frame_overlay,a.output);print(json.dumps(dict(providers=[str(p) for p in result],game_started=False)))
