"""Revalidate pending native inputs against a freshly verified equivalent JCLS batch.

This explicit same-input rebase never accepts a provider set, edits old evidence,
reassembles a provider, or changes extend-runtime-provider-set's parent rules.
"""
import argparse
import ast
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import time
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('provider_rebase_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S,R,N=(module(name) for name in ('runtime-provider-source','revalidate-runtime-provider-cache','refresh-named-module-batch'))


def same_source_model(old, new):
    """Permit only a literal append to the tool list, with all executable AST equal."""
    def source(raw):
        tree=ast.parse(raw.decode('utf-8-sig'))
        assignments=[node for node in tree.body if isinstance(node,ast.Assign) and
                     any(isinstance(target,ast.Name) and target.id=='TOOL_FILES' for target in node.targets)]
        S.check(len(assignments)==1 and len(assignments[0].targets)==1, 'Ambiguous provider tool-list declaration')
        [assignment]=assignments
        names=ast.literal_eval(assignment.value)
        S.check(isinstance(names,tuple) and len(names)==len(set(names)) and all(isinstance(n,str) for n in names),
                'Expected a unique literal provider tool tuple')
        tree.body.remove(assignment)
        return names,ast.dump(tree,include_attributes=False)
    before,old_ast=source(old);after,new_ast=source(new)
    S.check(old_ast==new_ast and before==after[:len(before)] and len(after)>len(before),
            'Provider I/O/source logic changed beyond an append-only tool namespace')
    return dict(previous_tool_count=len(before),current_tool_count=len(after),
                appended_tools=list(after[len(before):]),executable_source_AST_identical=True)


def same_summary(old, new):
    expected=deepcopy(old)
    [before]=expected['class_literals']['units'];[after]=new['class_literals']['units']
    for key in ('assembly','object'):before[key]=deepcopy(after[key])
    S.check(expected==new, 'Rebase changes source/type/layout/module/profile or Java units beyond JCLS artifact locations')


def same_full_coverage(old, new):
    before={k:v for k,v in old.items() if k!='named_module_derivation'}
    after={k:v for k,v in new.items() if k!='named_module_derivation'}
    S.check(before==after and old.get('verified') is True and new.get('verified') is True,
            'Fresh full batch coverage differs from the accepted original 65 batch')


def rebase(state_file, state_sha, new_batch, full_sha, old_provider_source, output):
    state_file,new_batch,old_provider_source,output=(Path(p).resolve() for p in (state_file,new_batch,old_provider_source,output))
    S.check(state_file.is_relative_to(S.ART) and new_batch.is_relative_to(S.ART/'named-module-batches') and
            old_provider_source.is_relative_to(S.ART), 'Use isolated project rebase inputs and a historical source snapshot')
    S.check(output.is_relative_to(S.ART/'runtime-provider-rebases') and not output.exists(), 'Use a fresh provider rebase output')
    inputs={}
    def remember(path):
        path=Path(path).resolve();key=str(path)
        if key not in inputs:inputs[key]=N.artifact(path)
        return inputs[key]
    def checked(record):
        path=Path(record['path']).resolve();actual=remember(path)
        S.check(set(record['digest'])<={'size','sha1','sha256'} and {'size','sha256'}<=set(record['digest']) and
                all(actual['digest'][k]==v for k,v in record['digest'].items()), 'Rebase sealed input changed: '+str(path))
        return path
    def artifacts(value):
        if isinstance(value,list):
            for child in value:artifacts(child)
        elif isinstance(value,dict):
            if 'path' in value and isinstance(value.get('digest'),dict):checked(value)
            else:
                for child in value.values():artifacts(child)
    S.check(remember(state_file)['digest']['sha256']==state_sha, 'Pending provider state checksum differs')
    state=S.read(state_file)
    S.check(state['status']=='pending_runtime_acceptance' and state['runtime_acceptance_complete'] is False and
            state['accepted_provider_set_published'] is False and state['current_source_provider_verification_complete'] is True,
            'Rebase requires complete but still pending provider inputs')
    snapshot=S.tools_identity();own=remember(Path(__file__))
    S.check(len(snapshot)==105 and state['tool_sources']==snapshot, 'This explicit rebase requires the frozen current105 tool namespace')
    accepted_path=checked(state['source_state']);accepted=S.read(accepted_path)
    old_batch,plan,runtime=(Path(state[k]).resolve() for k in ('batch','plan','runtime'))
    S.check(all(p.is_relative_to(S.ART) for p in (old_batch,plan,runtime)) and old_batch!=new_batch and
            accepted['status']=='accepted' and accepted['runtime_acceptance_complete'] is True and
            Path(accepted['batch']).resolve()==old_batch and Path(accepted['plan']).resolve()==plan and
            accepted['batch_summary_sha256']==state['batch_summary_sha256'] and
            accepted['batch_verification_sha256']==state['batch_verification_sha256'] and
            accepted['runtime_sha256']==state['runtime_sha256'], 'Pending input does not retain its accepted original65 source/runtime')
    for key in ('main_source_verification','main_native_verification','main_execution','main_native_report'):
        checked(accepted[key])
    S.check(remember(old_batch/'summary.json')['digest']['sha256']==state['batch_summary_sha256'] and
            remember(old_batch/'verification.json')['digest']['sha256']==state['batch_verification_sha256'] and
            remember(new_batch/'verification.json')['digest']['sha256']==full_sha, 'Original or freshly executed batch proof checksum differs')
    before,after=S.read(old_batch/'summary.json'),S.read(new_batch/'summary.json')
    old_full,new_full=S.read(old_batch/'verification.json'),S.read(new_batch/'verification.json')
    old_derivation,new_derivation=S.read(old_batch/N.PROOF),S.read(new_batch/N.PROOF)
    # The old full receipt is pinned by the actual accepted29 checkpoint. Its
    # historical helper pin stays historical; the new side uses the real current
    # strict resolver and separately executed full verifier, without exceptions.
    new_resolver,new_lineage=N.verified_resolver(new_batch,after,plan)
    same_summary(before,after);same_full_coverage(old_full,new_full)
    old_scope=old_full['named_module_derivation']
    S.check(old_scope['summary']==remember(old_batch/'summary.json') and
            old_scope['derivation']==remember(old_batch/N.PROOF), 'Accepted original65 full receipt does not bind its source derivation')
    for key in ('parent_inputs','parent_derivation','requested_modules','source_graph','appended','declaration_changes','binary_equivalence'):
        S.check(old_derivation[key]==new_derivation[key], 'Original parent/graph/append or physical data contract changed: '+key)
    S.check(old_scope['parent']==old_derivation['parent_inputs'] and old_scope['appended']==old_derivation['appended'] and
            old_scope['source_graph']==old_derivation['source_graph']['inputs'] and
            old_derivation['derived_summary']==remember(old_batch/'summary.json') and
            old_derivation['tools'].keys()==new_derivation['tools'].keys(), 'Original65 provenance differs from the accepted full receipt')
    changed=[key for key in old_derivation['tools'] if old_derivation['tools'][key]!=new_derivation['tools'][key]]
    S.check(changed==['runtime-provider-source.py'], 'Source tools changed beyond the declared provider tool-list append')
    previous=old_derivation['tools']['runtime-provider-source.py']
    S.check(remember(old_provider_source)['digest']==previous['digest'], 'Historical provider source snapshot differs from the accepted old tool pin')
    namespace=same_source_model(old_provider_source.read_bytes(),(ROOT/'scripts/runtime-provider-source.py').read_bytes())
    S.check(namespace['previous_tool_count']==99 and namespace['current_tool_count']==105 and len(namespace['appended_tools'])==6,
            'This rebase permits exactly the recorded 99-to-105 append')
    artifacts(old_derivation['parent_inputs']);artifacts(old_derivation['source_graph']['inputs'])
    artifacts(new_derivation['parent_inputs']);artifacts(new_derivation['source_graph']['inputs'])
    remember(old_batch/N.PROOF);remember(new_batch/'summary.json');remember(new_batch/N.PROOF)
    [old_unit]=before['class_literals']['units'];[new_unit]=after['class_literals']['units']
    for unit in (old_unit,new_unit):
        checked(unit['assembly']);checked(unit['object'])
    S.check(old_unit['assembly']['digest']==new_unit['assembly']['digest'], 'Same-input JCLS assembly bytes changed')
    binary=N.binary_equivalence(Path(old_unit['object']['path']),Path(new_unit['object']['path']),
                                before['class_literals'],after['class_literals'])
    S.check(binary['BSS_added_bytes']==0 and binary['indexed_symbol_contract']['rdata_symbol_shift']==0 and
            binary['indexed_symbol_contract']['BSS_symbol_shift']==0, 'Equivalent65 COFF data or symbol layout changed')
    old_identity=S.base(old_batch,plan)[0];new_identity=S.base(new_batch,plan)[0]
    R.compatible_base(old_identity,new_identity)
    runtime_meta=S.read(runtime/'runtime.json')
    S.check(remember(runtime/'boom-runtime.dll')['digest']['sha256']==state['runtime_sha256']==runtime_meta['sha256'] and
            runtime_meta['implementation_language']=='x86-64 MASM assembly', 'Original assembly runtime changed')
    remember(runtime/'runtime.json')
    old_frame=Path(state['frame_manifest']).resolve()
    S.check(remember(old_frame.with_name('verification.json'))['digest']['sha256']==state['frame_verification_sha256'],
            'Pending original frame receipt changed')
    old_frame_meta=S.read(old_frame);old_frame_proof=S.read(old_frame.with_name('verification.json'))
    S.check(old_frame_proof['verified'] is True and old_frame_proof['manifest_sha256']==S.digest(old_frame)['sha256'],
            'Original current frame manifest is not bound to its receipt')
    artifacts(old_frame_meta);remember(old_frame)
    paths=[Path(p).resolve() for p in S.read(state['providers'])]
    remember(state['providers'])
    sealed={Path(row['manifest']['path']).resolve():row for row in state['providers_verified']}
    S.check(len(paths)==len(set(paths))==state['provider_count']==31 and set(paths)==set(sealed) and
            all(p.is_relative_to(S.ART) for p in paths), 'The exact pending31 provider list/records differ')
    families=[];native_ids=set();exports=set()
    for path in paths:
        checked(sealed[path]['manifest']);checked(sealed[path]['verification'])
        m,proof=S.read(path),S.read(path.with_name('verification.json'))
        S.check(m['base']==old_identity and m['tool_sources']==snapshot and proof['verified'] is True and
                proof['provider_manifest_sha256']==S.digest(path)['sha256'] and sealed[path]['family']==m['family'],
                'An original pending31 manifest/receipt/current namespace differs')
        ids={row['method'] for row in m['methods']}
        S.check(len(ids)==len(m['methods']) and not ids&native_ids and not set(m['exports'])&exports,
                'Pending31 repeats native declarations or exported symbols')
        S.check(all(runtime_meta['sources'].get(name)==sha==S.digest(ROOT/name)['sha256']
                    for name,sha in m['runtime_kernel_sha256'].items()), 'A pending provider requires different runtime kernels')
        families.append(m['family']);native_ids|=ids;exports|=set(m['exports']);artifacts(m)
    S.check(len(set(families))==31 and all(set(S.read(p).get('required_provider_families',[]))<=set(families) for p in paths),
            'Pending31 family dependency or uniqueness differs')
    frame=S.ART/'native-frame-overlays'/output.name
    packs=S.ART/'runtime-providers'/output.name
    S.check(not frame.exists() and not packs.exists(), 'Fresh frame/provider destinations required')
    output.mkdir(parents=True)
    started=time.monotonic();journal=output/'progress.json'
    progress=dict(schema=1,status='running',pid=os.getpid(),source_state=remember(state_file),old_batch=str(old_batch),
                  new_batch=str(new_batch),run=str(output),frame=str(frame),packs=str(packs),runtime_acceptance_complete=False)
    def unchanged():
        S.check(S.tools_identity()==snapshot and N.artifact(Path(__file__))==own, 'Rebase producer/current namespace changed')
        for record in inputs.values():S.check(N.artifact(record['path'])==record, 'A rebase input changed during execution')
    def publish(stage):
        unchanged();progress.update(stage=stage,elapsed_seconds=round(time.monotonic()-started,3))
        temporary=output/('progress-'+uuid4().hex+'.tmp');S.write(temporary,progress);temporary.replace(journal)
        print(json.dumps(dict(stage=stage,journal=str(journal))),flush=True)
    try:
        S.write(output/'source-equivalence.json',dict(schema=1,verified=True,
            scope='accepted_historical65_vs_genuine_current_full65_same_source_and_COFF',
            previous_accepted_state=remember(accepted_path),old_summary=remember(old_batch/'summary.json'),
            old_full_receipt=remember(old_batch/'verification.json'),new_summary=remember(new_batch/'summary.json'),
            new_full_receipt=remember(new_batch/'verification.json'),new_source_lineage=new_lineage,
            old_provider_source=remember(old_provider_source),provider_namespace=namespace,COFF_equivalence=binary,
            all_other_summary_fields_identical=True,complete_full_coverage_fields_identical=True,
            same_old64_parent_and_locked_resolved_graph=True,original_Java_units_regenerated=0))
        publish('revalidating_identical_frame_bytes')
        overlay=R.refresh_frames(old_frame,new_batch,plan,frame)
        publish('revalidating_all_31_cached_providers')
        current=R.refresh_packs(paths,new_batch,plan,overlay,packs/'revalidated')
        records=[];reused=[]
        for old_path,new_path,family in zip(paths,current,families):
            old,new=S.read(old_path),S.read(new_path)
            S.check(new['family']==family and new['base']==new_identity and new['tool_sources']==snapshot,
                    'Rebased family/order/current source identity differs')
            equal=[]
            for key,value in old.items():
                if key in ('assembly','object') or key.endswith('_metadata'):
                    if isinstance(value,dict) and 'path' in value:
                        S.check(value['digest']==new[key]['digest'], 'Provider bytes changed during rebase: '+key)
                        equal.append(key)
            records.append(dict(family=family,manifest=S.artifact(new_path),verification=S.artifact(new_path.with_name('verification.json'))))
            reused.append(dict(family=family,old_manifest=remember(old_path),new_manifest=S.artifact(new_path),unchanged_artifacts=equal))
        new_frame=S.read(overlay)
        S.check(all(old_frame_meta[k]['digest']==new_frame[k]['digest'] for k in ('assembly','object')),
                'Rebased frame ASM/COFF bytes changed')
        # Re-enter the real current certified resolver after all expensive checks.
        _,final_lineage=N.verified_resolver(new_batch,after,plan)
        S.check(final_lineage==new_lineage,'Current full-source lineage changed during cache verification')
        unchanged()
        directory=packs/'candidate';directory.mkdir()
        S.write(directory/'providers.json',[str(p) for p in current])
        target=output/'pending-state.json'
        result=dict(schema=1,status='pending_runtime_acceptance',scope='same_input_65_full_source_and_31_provider_cache_rebase_not_runtime_acceptance',
            batch=str(new_batch),plan=str(plan),runtime=str(runtime),frame=str(frame),frame_manifest=str(overlay),
            providers=str(directory/'providers.json'),provider_count=31,reused_provider_count=31,generated_provider_count=0,
            previous_batch=str(old_batch),source_state=remember(state_file),previous_accepted_state=remember(accepted_path),
            batch_source_lineage=new_lineage,source_equivalence=S.artifact(output/'source-equivalence.json'),
            tool_sources=snapshot,rebase_tool=S.artifact(Path(__file__)),providers_verified=records,run=str(output),
            batch_summary_sha256=S.digest(new_batch/'summary.json')['sha256'],batch_verification_sha256=full_sha,
            frame_verification_sha256=S.digest(frame/'verification.json')['sha256'],runtime_sha256=state['runtime_sha256'],
            original_Java_ASM_and_COFF_regenerated=False,reused_provider_ASM_and_COFF_bytes_unchanged=True,
            shared_runtime_kernel_modified=False,current_source_provider_verification_complete=True,
            runtime_acceptance_complete=False,accepted_provider_set_published=False,full_selection_reverified=False,
            game_started=False,world_created=False,elapsed_seconds=round(time.monotonic()-started,3))
        S.write(output/'reused-provider-bytes.json',reused)
        S.write(target,result)
        S.write(output/'sealed-inputs.json',list(inputs.values()))
        progress.update(status='pending_runtime_acceptance',candidate_state=str(target))
        publish('pending_state_ready')
        return target
    except BaseException as error:
        progress.update(status='failed',error=repr(error),elapsed_seconds=round(time.monotonic()-started,3))
        S.write(output/'failure.json',progress)
        temporary=output/('progress-failed-'+uuid4().hex+'.tmp');S.write(temporary,progress);temporary.replace(journal)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--state-sha256',required=True)
    parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--batch-verification-sha256',required=True)
    parser.add_argument('--old-provider-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(rebase(args.state,args.state_sha256,args.batch,args.batch_verification_sha256,args.old_provider_source,args.output))
