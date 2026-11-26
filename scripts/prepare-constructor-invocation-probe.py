"""Prepare FFI cases from a source image whose independent proof was accepted.

The caller supplies the SHA256 observed after independent closure verification.
This is test preparation, not a replacement verifier or a complete VM bootstrap.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('constructor_binding_test_source',ROOT/'scripts/runtime-provider-source.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)


def prepare(image,fixture,accepted_verification_sha256,output):
    image,fixture,output=Path(image).resolve(),Path(fixture).resolve(),Path(output).resolve()
    S.check(image.is_relative_to(S.ART) and fixture.is_relative_to(S.ART) and output.is_relative_to(S.ART) and not output.exists(),
            'Constructor binding probe requires project evidence and a fresh .boom output')
    proof_path=image/'selection-verification.json';proof=S.read(proof_path)
    S.check(S.digest(proof_path)['sha256']==accepted_verification_sha256 and proof['verified'] and proof['diagnostic_only'] and not proof['source_closure_complete'],
            'The explicitly accepted independent source proof differs')
    closure=S.read(image/'closure.json');source=S.read(fixture)
    S.check(source['batch']==closure['batch'] and source['fixture_only'] and not source['full_module_bootstrap'],'Constructor fixture belongs to a different source batch/scope')
    S.check(hashlib.sha256((image/'initialization-closure.asm').read_text(encoding='utf-8').encode()).hexdigest()==proof['closure_assembly_sha256'],
            'Independently verified original assembly changed')
    packs=[S.read(S.checked(p['manifest'])) for p in closure['runtime_provider_packs']]
    S.check(all(p['tool_sources']==S.tools_identity() for p in packs),'Accepted source provider tools changed')
    invoke=next(p for p in packs if p['family']=='normal-constructor-invocation-v1')
    enumeration=next(p for p in packs if p['family']=='normal-constructors-v1')
    meta=S.read(S.checked(invoke['constructor_invocation_metadata']));ctors=S.read(S.checked(enumeration['constructor_metadata']))
    ready=set(closure['constructor_invocation_sites']['ready_indices']);by_id={r['method']:(i,r) for i,r in enumerate(meta['records'])}
    targets=[]
    S.check(len(source['cases'])==13,'Constructor source fixture coverage differs')
    for case in source['cases']:
        i,r=by_id[case['method_id']]
        S.check(i in ready and r['owner']==case['class_id'] and r['descriptor']==case['descriptor'] and r['available'] and r['target_emitted'],
                'Original constructor target is not ready in this source image')
        if case['index'] in range(1,9):
            box=next(b for b in meta['boxes'] if b['class_id']==case['class_id'])
            S.check(case['value']==dict(offset=box['offset'],width=box['width']),'Constructor value field fixture differs from source boxing metadata')
        targets.append(dict(record_index=i,slot=r['slot'],method=r['method'],source_sha256=r['source_sha256'],code_sha256=r['code_sha256']))
    inputs=[image/'closure.json',proof_path,image/'initialization-closure.asm',image/'initialization-closure.obj',image/'diagnostic-stops.asm',image/'diagnostic-stops.obj',image/'diagnostic.json',image/'diagnostic-image.dll',fixture]
    inputs.extend(Path(p) for p in closure['objects'])
    runtime=Path(S.read(image/'diagnostic.json')['global_provider_identity']['runtime_dll'])
    inputs.extend((runtime,runtime.with_name('runtime.json'),ROOT/'tests/host/ConstructorCallsiteProbe.cs'))
    for p in closure['runtime_provider_packs']:inputs.extend((S.checked(p['manifest']),S.checked(p['verification'])))
    output.mkdir(parents=True)
    S.write(output/'source.json',source);S.write(output/'boxes.json',dict(boxes=meta['boxes']))
    S.write(output/'bindings.json',dict(targets=targets,slot_offset=ctors['field_offsets'][6],native_symbols=[f"boom_m{m['method']}" for m in invoke['methods']]))
    result=dict(schema=1,accepted_verification=S.artifact(proof_path),image_directory=str(image),runtime=str(runtime),
        inputs=[S.artifact(p) for p in dict.fromkeys(inputs)],generated_artifacts=[S.artifact(output/p) for p in ('source.json','boxes.json','bindings.json')],
        fixture_only=True,full_module_bootstrap=False,exception_wrapping_complete=False,game_started=False)
    S.write(output/'prepared.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--accepted-verification-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=prepare(a.image,a.fixture,a.accepted_verification_sha256,a.output);print(json.dumps(dict(prepared=str(a.output/'prepared.json'),targets=13,game_started=False)))
