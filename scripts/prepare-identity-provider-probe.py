"""Select original identity entrypoints and source String override for FFI tests."""
import argparse
import importlib.util
import json
from pathlib import Path
import zipfile

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('batch','plan','runtime','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--provider',type=Path,action='append',required=True);a=p.parse_args()
    providers=module('identity_fixture_providers','verify-runtime-provider-pack.py');packs=providers.load_packs(a.batch,a.plan,a.provider)
    identity_pack=next(p['manifest'] for p in packs if p['manifest']['family']=='object-identity-v1')
    summary=providers.S.read(a.batch/'summary.json');classes=[json.loads(l) for l in (a.plan/'classes.jsonl').read_text().splitlines()]
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    signatures=[('java/lang/Object','<init>','()V'),('java/lang/String','hashCode','()I')]
    entries=[('bootstrap',o,n,d) for o,n,d in signatures]+[('bootstrap',m['owner'],m['name'],m['descriptor']) for m in identity_pack['methods']]
    symbols={}
    for owner,name,desc in signatures:
        cid=names['bootstrap',owner]
        for shard in summary['shards']:
            with zipfile.ZipFile(shard['zip']['path']) as z:
                path=f'classes/{cid:06}.json'
                if path not in z.namelist():continue
                c=json.loads(z.read(path));m=next(m for m in c['methods'] if (m['name'],m['descriptor'])==(name,desc));assert m['assembly_emitted']
                symbols[owner]=f"boom_m{m['id']}";break
    with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as z:
        types=[json.loads(l) for l in z.read('types.jsonl').splitlines()]
        wanted={r['id']:r for r in types if r['name'] in ('[I','[Ljava/lang/Object;') and r['defining_loader']=='bootstrap'}
        arrays=[json.loads(l) for l in z.read('runtime.jsonl').splitlines() if json.loads(l)['type_id'] in wanted]
    with zipfile.ZipFile(summary['string_literals']['index']['path']) as z:
        literal=next(json.loads(l) for l in z.open('canonical.jsonl') if 3<=len(json.loads(l)['utf16'])<=16 and all(32<=c<127 for c in json.loads(l)['utf16']))
    selector=module('identity_fixture_source_selector','prepare-class-init-probe.py');globals_=module('identity_fixture_globals','diagnostic-closure.py');coff=module('identity_fixture_coff','verify-batch-assembly.py')
    known,data,global_identity=globals_.globals_index(a.batch,summary,a.runtime,coff,packs)
    m=selector.prepare(a.batch,a.plan,a.output,[('bootstrap','java/lang/Class'),('bootstrap','java/lang/Object'),('bootstrap','java/lang/System')],entries,
        diagnostic=dict(admit_methods=[],admit_classes=[],known_symbols=known,data_providers=data,global_identity=global_identity),provider_packs=a.provider)
    m['explicit_raw_slot_identity_provider_fixture']=True;m['exports'].append(f"boom_layout{names['bootstrap','java/lang/Object']}")
    (a.output/'closure.json').write_text(json.dumps(m,indent=2)+'\n')
    source=dict(batch=str(a.batch.resolve()),image=str(a.output.resolve()),object_id=names['bootstrap','java/lang/Object'],class_id=names['bootstrap','java/lang/Class'],
        system_id=names['bootstrap','java/lang/System'],constructor=symbols['java/lang/Object'],string_hash=symbols['java/lang/String'],
        native_symbols={str(m['operation']):f"boom_m{m['method']}" for m in identity_pack['methods']},arrays=arrays,literal=literal,
        fixture_only=True,fixture_VM_arrays=True,game_started=False)
    (a.output/'source.json').write_text(json.dumps(source,indent=2)+'\n');print(json.dumps(source))
