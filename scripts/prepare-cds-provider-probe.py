"""Select raw-slot CDS verification entries; this is not a game startup entry."""
import argparse
import importlib.util
import json
from pathlib import Path
import zipfile


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',required=True,type=Path);p.add_argument('--plan',required=True,type=Path)
    p.add_argument('--provider',required=True,type=Path);p.add_argument('--runtime',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    providers=module('CDS_fixture_provider_verification','verify-runtime-provider-pack.py');packs=providers.load_packs(a.batch,a.plan,[a.provider]);pack=packs[0]['manifest']
    summary=providers.S.read(a.batch/'summary.json');classes=[json.loads(l) for l in (a.plan/'classes.jsonl').read_text().splitlines()]
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes};class_id=pack['owner_source']['id']
    result=None
    for shard in summary['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as z:
            name=f'classes/{class_id:06}.json'
            if name in z.namelist():result=json.loads(z.read(name));break
    assert result is not None
    signatures=[('isDumpingClassList','()Z'),('isDumpingArchive','()Z'),('isSharingEnabled','()Z')]
    entries=[('bootstrap','jdk/internal/misc/CDS',n,d) for n,d in signatures]
    entries.extend(('bootstrap',m['owner'],m['name'],m['descriptor']) for m in pack['methods'])
    selector=module('CDS_fixture_selector','prepare-class-init-probe.py');globals_=module('CDS_fixture_globals','diagnostic-closure.py');coff=module('CDS_fixture_coff','verify-batch-assembly.py')
    known,data,identity=globals_.globals_index(a.batch,summary,a.runtime,coff,packs)
    manifest=selector.prepare(a.batch,a.plan,a.output,[('bootstrap','java/lang/Class'),('bootstrap','jdk/internal/misc/CDS'),('bootstrap','java/util/Optional')],entries,
        diagnostic=dict(admit_methods=[],admit_classes=[],known_symbols=known,data_providers=data,global_identity=identity),provider_packs=[a.provider])
    native={str(m['operation']):f"boom_m{m['method']}" for m in pack['methods']}
    getters=[f"boom_m{next(m['id'] for m in result['methods'] if (m['name'],m['descriptor'])==(n,d))}" for n,d in signatures]
    source=dict(batch=str(a.batch.resolve()),plan=str(a.plan.resolve()),image=str(a.output.resolve()),provider=str(a.provider.resolve()),
        class_class_id=names['bootstrap','java/lang/Class'],CDS_class_id=class_id,cold_target_class_id=names['bootstrap','java/util/Optional'],
        native_symbols=native,getter_symbols=getters,fixture_only=True,original_CDS_initializer_selected=True,game_started=False)
    target=next(c for c in manifest['selected_classes'] if c['class_id']==source['cold_target_class_id'])
    empty=next(f for f in target['fields'] if f['name']=='EMPTY')
    source['cold_target_empty_field']=f"boom_s{target['class_id']}_{empty['index']}"
    manifest['explicit_raw_slot_CDS_provider_fixture']=True
    (a.output/'closure.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (a.output/'source.json').write_text(json.dumps(source,indent=2)+'\n');print(json.dumps(source))
