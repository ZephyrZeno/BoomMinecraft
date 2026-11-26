"""Select a source-preserving development image with explicit failure stops."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile


def prepare(batch,plan,output,class_roots,entries,admit=(),runtime=None,receiver=None,admit_classes=(),provider_paths=None):
    output=Path(output).resolve();root=Path(__file__).resolve().parents[1]
    if not output.is_relative_to((root/'.boom').resolve()):raise ValueError('Diagnostic outputs must stay inside project .boom')
    if not class_roots and not entries:raise ValueError('Diagnostic source roots are required')
    for entry in entries:
        if entry[-1]!=('()Z' if receiver else '()V'):raise ValueError('Unsupported diagnostic entry descriptor')
    if receiver and (len(entries)!=1 or class_roots):raise ValueError('Prepared receiver fixture requires one instance predicate and no initialization roots')
    spec=importlib.util.spec_from_file_location('diagnostic_source_selection',Path(__file__).with_name('prepare-class-init-probe.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    def module(name,file):
        spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);return v
    model=module('diagnostic_global_index','diagnostic-closure.py');coff=module('diagnostic_global_coff','verify-batch-assembly.py')
    summary=json.loads((Path(batch)/'summary.json').read_text(encoding='utf-8'))
    provider_module=module('diagnostic_separate_providers','verify-runtime-provider-pack.py') if provider_paths else None
    packs=provider_module.load_packs(batch,plan,provider_paths) if provider_paths else []
    known,providers,identity=model.globals_index(batch,summary,runtime,coff,packs,plan)
    manifest=m.prepare(batch,plan,output,class_roots,entries,diagnostic=dict(admit_methods=list(admit),admit_classes=list(admit_classes),known_symbols=known,data_providers=providers,global_identity=identity),provider_packs=provider_paths,verified_provider_packs=packs)
    manifest['exports'].append('boom_java_string_literal_root_count')
    if receiver:
        loader,name=receiver.split(':',1)
        with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as z:types=[json.loads(l) for l in z.read('types.jsonl').splitlines()]
        matches=[t for t in types if t['kind']==1 and t['name']==name and t['defining_loader']==loader]
        if len(matches)!=1:raise ValueError('Prepared diagnostic receiver type is not unique')
        target=manifest['requested_method_roots'][0];typ=matches[0]
        classes=[json.loads(l) for l in (Path(plan)/'classes.jsonl').open(encoding='utf-8')]
        owner=next(c['id'] for c in classes if c['name']==target['owner'] and c['origin']['loader']==target['loader'])
        if owner!=typ['id'] and owner not in typ['ancestors']:raise ValueError('Prepared receiver is not assignable to entry owner')
        layout=f"boom_layout{typ['id']}";manifest['exports'].append(layout)
        manifest['diagnostic_receiver']=dict(type_id=typ['id'],name=name,loader=loader,source_sha256=typ['source_sha256'],layout_symbol=layout,
            fixture_only=True,constructor_executed=False,class_initialization_executed=False)
    manifest['diagnostic_selection_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output/'closure.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--class-root',action='append',default=[]);p.add_argument('--entry',action='append',default=[]);p.add_argument('--admit-profile',type=Path);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--receiver-class',help='Development-only zero-field-state receiver shape fixture')
    p.add_argument('--provider-pack',type=Path,action='append',default=[])
    a=p.parse_args();admit=[];admit_classes=[]
    if a.admit_profile:
        profile=json.loads(a.admit_profile.read_text(encoding='utf-8'));summary=Path(a.batch)/'summary.json'
        if profile['source_batch_summary_sha256']!=hashlib.sha256(summary.read_bytes()).hexdigest():raise ValueError('Diagnostic profile belongs to a different source batch')
        admit=profile['admitted_methods']
        admit_classes=profile.get('admitted_classes',[])
    r=prepare(a.batch,a.plan,a.output,[tuple(s.split(':',1)) for s in a.class_root],[tuple(s.split(':',3)) for s in a.entry],admit,a.runtime,a.receiver_class,admit_classes,a.provider_pack)
    print(json.dumps(dict(diagnostic_only=True,classes=len(r['selected_classes']),Java_methods=len(r['selected_methods']),stop_symbols=len(r['unprovided_diagnostic_symbols']),game_started=False)))
