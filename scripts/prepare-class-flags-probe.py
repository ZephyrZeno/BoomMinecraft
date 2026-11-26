"""Select actual source flags APIs, with explicit loader/module FFI fixtures."""
import argparse
import importlib.util
import json
from pathlib import Path

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('batch','plan','runtime','output','seed'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--provider',type=Path,action='append',required=True);a=p.parse_args()
    V=module('flags_fixture_provider_verifier','verify-runtime-provider-pack.py');packs=V.load_packs(a.batch,a.plan,a.provider)
    pack=next(p['manifest'] for p in packs if p['manifest']['family']=='class-flags-v1')
    m=V.S.read(V.S.checked(pack['class_flags_metadata']));summary=V.S.read(a.batch/'summary.json')
    classes=[json.loads(l) for l in (a.plan/'classes.jsonl').read_text().splitlines()];names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    C=module('flags_fixture_type_source','constructor-provider-source.py');types,_,_,_=C.inputs(summary,classes)
    bytype={t['id']:t for t in types};originals={r['class_id']:r for r in m['original_classes']}
    ids={names['bootstrap',n] for n in ('java/lang/Object','java/lang/String','java/lang/Class','java/lang/Enum','java/lang/Record','java/util/Map$Entry','java/lang/Cloneable')}
    for mask in (1,2,4,8,0x200,0x1000,0x2000,0x4000):
        found=next((r for id_,r in originals.items() if classes[id_]['origin']['source_id']=='jdk:java.base' and r['modifiers']&mask),None)
        if found:ids.add(found['class_id'])
    app=next(r for r in m['original_classes'] if r['loader']=='vanilla-application' and classes[r['class_id']]['name']=='aaf$a');ids.add(app['class_id'])
    for t in types:
        if t['kind']==0:ids.add(t['id'])
        elif t['kind']==3:
            bottom=t;rank=0
            while bottom['kind']==3:bottom=bytype[bottom['parent_component']];rank+=1
            if rank<=2 and (bottom['id'] in ids or bottom['kind']==0):ids.add(t['id'])
    cases=[dict(m['rows'][i],name=bytype[i]['name'],loader=bytype[i]['defining_loader']) for i in sorted(ids)]
    wanted_layouts={names['bootstrap',n] for n in ('java/lang/Module','java/lang/String')};layouts={}
    with Path(summary['layouts']['path']).open() as stream:
        for l in stream:
            r=json.loads(l)
            if r['class_id'] in wanted_layouts:layouts[r['name']]=r['candidate']
    fields=lambda name:{f['member']['name']:f['offset'] for f in layouts[name]['fields'] if f['member']['owner']==names['bootstrap',name]}
    mf=fields('java/lang/Module');sf=fields('java/lang/String')
    loaders=[dict(id=1,type_id=names['bootstrap','jdk/internal/loader/ClassLoaders$PlatformClassLoader']),dict(id=2,type_id=names['bootstrap','jdk/internal/loader/ClassLoaders$AppClassLoader'])]
    fixture_modules=[dict(r,module_type=names['bootstrap','java/lang/Module'],name_offset=mf['name'],loader_offset=mf['loader']) for r in summary['class_literals']['modules']]
    seed=V.S.read(a.seed);assert seed['batch']==str(a.batch.resolve()) and seed['source_batch_summary_sha256']==V.S.digest(a.batch/'summary.json')['sha256']
    selector=module('flags_fixture_selector','prepare-class-init-probe.py');globals_=module('flags_fixture_globals','diagnostic-closure.py');coff=module('flags_fixture_coff','verify-batch-assembly.py')
    known,data,identity=globals_.globals_index(a.batch,summary,a.runtime,coff,packs)
    roots=[('bootstrap',n) for n in ('java/lang/String','java/lang/System','java/lang/Class','java/lang/reflect/Method')]
    entries=[('bootstrap',r['owner'],r['name'],r['descriptor']) for r in pack['methods']]
    closure=selector.prepare(a.batch,a.plan,a.output,roots,entries,diagnostic=dict(admit_methods=seed['admitted_methods'],admit_classes=seed['admitted_classes'],known_symbols=known,data_providers=data,global_identity=identity),provider_packs=a.provider,verified_provider_packs=packs)
    closure['explicit_raw_slot_class_flags_fixture']=True;(a.output/'closure.json').write_text(json.dumps(closure,indent=2)+'\n')
    source=dict(batch=str(a.batch.resolve()),cases=cases,native_symbols={str(r['operation']):f"boom_m{r['method']}" for r in pack['methods']},
        source_class_roots=[names['bootstrap',n] for n in ('java/lang/String','java/lang/System','java/lang/Class','java/lang/reflect/Method')],
        fixture_loaders=loaders,fixture_modules=fixture_modules,string_type=names['bootstrap','java/lang/String'],string_value_offset=sf['value'],string_coder_offset=sf['coder'],
        oracle_classpath=[r['path'] for k,r in summary['frames']['original_input_files'].items() if k!='server-bundle'],
        full_module_bootstrap=False,fixture_only=True,source_target_constructors_or_initializers_executed=False,game_started=False)
    (a.output/'source.json').write_text(json.dumps(source,indent=2)+'\n');print(json.dumps(dict(cases=len(cases),game_started=False)))
