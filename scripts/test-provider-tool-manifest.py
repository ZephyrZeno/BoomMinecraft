"""Isolated full-byte identity experiment; never certifies a provider or batch."""
import argparse
import ast
import importlib.util
import json
from pathlib import Path
import shutil
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('tool_manifest_identity_experiment',ROOT/'scripts/provider-tool-manifest.py')
H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)


def write(path,data):
    H.check(not path.exists(),'Identity evidence already exists: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')


def artifact(path):return dict(path=str(path.resolve()),sha256=H.sha256(path.read_bytes()),size=path.stat().st_size)


def projection(root,paths):return {p:H.sha256((root/p).read_bytes()) for p in paths}


def reject_old(proof,root):
    try:H.verify_snapshot(proof,root)
    except ValueError as error:return str(error)
    raise ValueError('Changed full identity unexpectedly accepted an old receipt')


def run(output):
    output=output.resolve();H.check(output.is_relative_to(ROOT/'.boom') and not output.exists(),'Fresh project .boom experiment required')
    output.mkdir(parents=True);mirror=output/'isolated-source';mirror.mkdir()
    current=H.snapshot();source_before={p:H.sha256((ROOT/p).read_bytes()) for p in current['contract']['tool_files']}
    named_path=ROOT/'scripts/refresh-named-module-batch.py'
    named=H.literal_assignment(ast.parse(named_path.read_text(encoding='utf-8-sig')),'TOOLS')
    # This is a proposed future executable-input projection, not a new named
    # resolver receipt. The new helper must join that set at first integration.
    proposed_named=tuple('scripts/'+name for name in named)
    if H.HELPER not in proposed_named:proposed_named+=(H.HELPER,)
    paths=set(current['contract']['tool_files'])|set(current['contract']['runtime_contract_sources'])|set(proposed_named)
    for name in paths:
        target=mirror/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    before=H.snapshot(mirror);named_before=projection(mirror,proposed_named)
    write(output/'before.json',before)
    manifest=H.read(mirror/H.MANIFEST);registry=H.read(mirror/H.REGISTRY)
    std=ROOT/'.boom/file-output-standard/source-bound-v149-c/candidate.json'
    candidate=H.read(std);metadata=candidate['metadata']['source']
    for name in ('scripts/file-output-standard-source.py','native/providers/file_output_standard.asm.inc'):
        path=mirror/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,path)
    family='normal-file-output-standard-v1';kernel='native/providers/file_output_standard.asm.inc';model='scripts/file-output-standard-source.py'
    H.check(family not in registry['families'],'Experiment is only for an unregistered source family')
    registry['families'][family]=dict(owner=metadata['methods'][0]['owner'],loader='bootstrap',source_id='jdk:java.base',kernel=kernel,
        pool='boom_provider_file_output_standard_pool',service='boom_provider_file_output_standard_service',
        methods=[{k:row[k] for k in ('name','descriptor','access','operation')} for row in metadata['methods']])
    (mirror/H.REGISTRY).write_text(json.dumps(registry,indent=2)+'\n',encoding='utf-8')
    framed=manifest['loaders']['framed_table'];file=mirror/framed;parsed=ast.parse(file.read_text(encoding='utf-8-sig'))
    mapping=H.literal_assignment(parsed,manifest['loaders']['assignment'])
    mapping[family]=('file-output-standard-source.py','file_output_standard','file_output_standard.asm.inc')
    [assignment]=[n for n in parsed.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FAMILIES' for t in n.targets)]
    lines=file.read_text(encoding='utf-8-sig').splitlines(keepends=True)
    lines[assignment.lineno-1:assignment.end_lineno]=['FAMILIES = '+repr(mapping)+'\n']
    file.write_text(''.join(lines),encoding='utf-8')
    manifest['tool_order'] += [model,kernel]
    manifest['families'][family]=dict(source_scope=dict(loader='bootstrap',source_id='jdk:java.base',owner=metadata['methods'][0]['owner']),
        model=model,verifier=framed,kernel=kernel,owned_files=[model,kernel])
    manifest['dependency_audits'][model]=H.source_audit(mirror,model)
    manifest['dependency_audits'][framed]=H.source_audit(mirror,framed)
    manifest['native_includes'][kernel]=H.native_includes(mirror,kernel)
    (mirror/H.MANIFEST).write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    after=H.snapshot(mirror);write(output/'after-new-family.json',after)
    named_after=projection(mirror,proposed_named)
    H.check(named_before==named_after,'Provider family data unexpectedly changed a named resolver executable source')
    H.check(after['contract']['tool_files'][:len(before['contract']['tool_files'])]==before['contract']['tool_files'],
        'New family reordered the old source namespace')
    stale=reject_old(before,mirror)
    changed={p for p,sha in before['tool_sources'].items() if after['tool_sources'].get(p)!=sha}
    H.check(changed=={H.MANIFEST,H.REGISTRY,framed} and set(after['tool_sources'])-set(before['tool_sources'])=={model,kernel},
        'Append experiment changed an unexpected implementation file')
    source_name='scripts/runtime-provider-source.py';original=(mirror/source_name).read_bytes()
    altered=original.replace(b'def digest(path):',b'def digest(path):\n    raise RuntimeError("isolated changed I/O implementation")',1)
    H.check(altered!=original,'Real provider digest function was not found')
    (mirror/source_name).write_bytes(altered)
    io_change=H.snapshot(mirror);write(output/'after-IO-implementation-change.json',io_change)
    named_io=projection(mirror,proposed_named)
    H.check(named_io[source_name]!=named_after[source_name],'Changed actual I/O implementation was not sealed')
    io_rejection=reject_old(after,mirror);(mirror/source_name).write_bytes(original)
    helper=(mirror/H.HELPER);original_helper=helper.read_bytes();helper.write_bytes(original_helper+b'\n# isolated full-byte identity change\n')
    H.check(projection(mirror,proposed_named)[H.HELPER]!=named_after[H.HELPER],'New executable helper was omitted from proposed named provenance')
    helper_rejection=reject_old(after,mirror)
    write(output/'after-helper-byte-change.json',dict(changed_helper=artifact(helper),rejected=helper_rejection,
        loaded_old_helper_did_not_publish_new_identity=True,proposed_named_helper_digest_changed=True))
    helper.write_bytes(original_helper)
    H.verify_snapshot(after,mirror)
    H.check(projection(ROOT,current['contract']['tool_files'])==source_before,'A production source changed during the independent experiment')
    result=dict(schema=1,verified=True,scope='isolated_provider_tool_namespace_and_executable_source_identity_experiment',
        helper=artifact(ROOT/H.HELPER),manifest=artifact(ROOT/H.MANIFEST),test_tool=artifact(Path(__file__)),
        original_production_identity=current,original_prefix_count=105,candidate_namespace_count=107,extended_namespace_count=109,
        proposed_named_executable_sources=named_before,proposed_named_executable_sources_unchanged_for_family_data=True,
        changed_existing_tool_inputs=sorted(changed),new_tool_inputs=[model,kernel],
        old_provider_identity_rejected=stale,changed_IO_implementation_rejected=io_rejection,changed_helper_bytes_rejected=helper_rejection,
        historical_named_receipt_accepted=False,full_named_batch_or_provider_pack_verified=False,
        source_binding_or_native_execution_claimed=False,isolated_registry_only=True,production_105_or_registry_modified=False,
        evidence=[artifact(output/name) for name in ('before.json','after-new-family.json','after-IO-implementation-change.json','after-helper-byte-change.json')],
        game_started=False)
    path=output/'result.json';write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,
        default=ROOT/'.boom/provider-tool-manifest/identity-experiments'/uuid4().hex)
    args=parser.parse_args();print(run(args.output))
