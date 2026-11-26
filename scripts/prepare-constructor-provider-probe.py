"""Select original Constructor getters and an FFI-only reflection test image."""
import argparse
import importlib.util
import json
from pathlib import Path

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def application_annotation_fixture(source,meta,classes,summary):
    """Prepare one real application metadata case; execute no application Code."""
    row=next(r for r in meta['records'] if r['parameter_annotations'] and not r['unavailable'] and
        r['loader']=='vanilla-application' and meta['ranges'][r['owner']]['status']==1)
    owner=classes[row['owner']];types,_,_,_=module('constructor_application_fixture_types','constructor-provider-source.py').inputs(summary,classes)
    names={t['id']:t['name'] for t in types}
    constructors=[dict(r,exception_names=[names[id_] for id_ in r['exceptions']]) for r in meta['records'] if r['owner']==row['owner']]
    source['cases'].append(dict(type_id=owner['id'],name=owner['name'],constructors=constructors,source_class=False,
        original_application_class=True,target_initializer_executed=False))
    loader_type=next(c['id'] for c in classes if (c['origin']['loader'],c['name'])==('bootstrap','jdk/internal/loader/ClassLoaders$AppClassLoader'))
    loader_id=summary['class_literals']['loader_keys'].index('vanilla-application')
    source['fixture_loaders']=[dict(loader_id=loader_id,type_id=loader_type,constructor_executed=False)]
    module_type=next(c['id'] for c in classes if (c['origin']['loader'],c['name'])==('bootstrap','java/lang/Module'))
    with Path(summary['layouts']['path']).open() as stream:
        layout=next(json.loads(line) for line in stream if json.loads(line)['class_id']==module_type)
    fields={f['member']['name']:f['offset'] for f in layout['candidate']['fields'] if f['member']['owner']==module_type}
    unnamed=next(m for m in summary['class_literals']['modules'] if m['name'] is None and m['loader']==loader_id)
    source['fixture_modules'].append(dict(id=unnamed['id'],name=None,module_type=module_type,name_offset=fields['name'],
        loader_id=loader_id,loader_offset=fields['loader']))
    source['oracle_classpath']=[a['path'] for key,a in summary['frames']['original_input_files'].items() if key!='server-bundle']
    source['application_fixture_scope']='original_class_metadata_only_no_constructor_or_initializer_execution'
    return source

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('batch','plan','runtime','output','seed'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--provider',type=Path,action='append',required=True);a=p.parse_args()
    V=module('constructor_fixture_provider_verification','verify-runtime-provider-pack.py');packs=V.load_packs(a.batch,a.plan,a.provider)
    pack=next(p['manifest'] for p in packs if p['manifest']['family']=='normal-constructors-v1')
    meta=V.S.read(V.S.checked(pack['constructor_metadata']));summary=V.S.read(a.batch/'summary.json')
    classes=[json.loads(l) for l in (a.plan/'classes.jsonl').read_text().splitlines()]
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes};byid={c['id']:c for c in classes}
    targets=['java/lang/Object','java/lang/String','java/lang/Thread','java/lang/Thread$State','java/lang/Runnable',
        'java/io/FileInputStream','java/util/ArrayList','java/lang/Class']
    ids=[names['bootstrap',n] for n in targets]
    for attribute in ('signature','annotations','parameter_annotations'):
        row=next((r for r in meta['records'] if r[attribute] and not r['unavailable'] and r['loader']=='bootstrap' and meta['ranges'][r['owner']]['status']==1),None)
        if row is not None and row['owner'] not in ids:ids.append(row['owner'])
    types,_,_,_=module('constructor_fixture_types','constructor-provider-source.py').inputs(summary,classes)
    for n in ('I','V','[I','[Ljava/lang/String;'):
        ids.append(next(t['id'] for t in types if (t['defining_loader'],t['name'])==('bootstrap',n)))
    getters={};wanted={'getDeclaringClass':'()Ljava/lang/Class;','getModifiers':'()I','getParameterCount':'()I',
        'getParameterTypes':'()[Ljava/lang/Class;','getExceptionTypes':'()[Ljava/lang/Class;','isVarArgs':'()Z','isSynthetic':'()Z'}
    entries=[('bootstrap','java/lang/Class','getDeclaredConstructors0','(Z)[Ljava/lang/reflect/Constructor;')]
    ctor=meta['constructor_class']
    for line in (a.plan/'methods.jsonl').open(encoding='utf-8'):
        m=json.loads(line);symbol=m['symbol']
        if m['class_id']==ctor and wanted.get(symbol['name'])==symbol['descriptor']:
            getters[symbol['name']]=f"boom_m{m['id']}";entries.append(('bootstrap','java/lang/reflect/Constructor',symbol['name'],symbol['descriptor']))
    assert set(getters)==set(wanted),'Original reflection getters missing'
    seed=V.S.read(a.seed);assert seed['batch']==str(a.batch.resolve()) and seed['source_batch_summary_sha256']==V.S.digest(a.batch/'summary.json')['sha256']
    selector=module('constructor_fixture_selector','prepare-class-init-probe.py');global_=module('constructor_fixture_globals','diagnostic-closure.py');coff=module('constructor_fixture_coff','verify-batch-assembly.py')
    known,data,identity=global_.globals_index(a.batch,summary,a.runtime,coff,packs)
    roots=[('bootstrap','java/lang/Class'),('bootstrap','java/lang/System')]+[('bootstrap',byid[id_]['name']) for id_ in ids if id_ in byid]
    manifest=selector.prepare(a.batch,a.plan,a.output,roots,entries,
        diagnostic=dict(admit_methods=seed['admitted_methods'],admit_classes=seed['admitted_classes'],known_symbols=known,data_providers=data,global_identity=identity),provider_packs=a.provider,verified_provider_packs=packs)
    manifest['explicit_raw_slot_constructor_provider_fixture']=True
    (a.output/'closure.json').write_text(json.dumps(manifest,indent=2)+'\n')
    cases=[]
    for id_ in ids:
        cases.append(dict(type_id=id_,name=next(t['name'] for t in types if t['id']==id_),
            constructors=[r for r in meta['records'] if r['owner']==id_],source_class=id_ in byid))
    type_names={t['id']:t['name'] for t in types}
    for c in cases:
        for row in c['constructors']:row['exception_names']=[type_names[id_] for id_ in row['exceptions']]
    module_type=names['bootstrap','java/lang/Module']
    with Path(summary['layouts']['path']).open() as stream:
        module_layout=next(json.loads(line) for line in stream if json.loads(line)['class_id']==module_type)
    module_name_offset=next(f['offset'] for f in module_layout['candidate']['fields'] if f['member']['name']=='name' and f['member']['owner']==module_type)
    fixture_names={byid[id_]['origin']['source_id'][4:] for id_ in ids if id_ in byid and byid[id_]['origin']['source_id'].startswith('jdk:')} - {'java.base'}
    fixture_modules=[dict(id=m['id'],name=m['name'],module_type=module_type,name_offset=module_name_offset) for m in summary['class_literals']['modules'] if m['name'] in fixture_names]
    assert len(fixture_modules)==len(fixture_names) and all(m['loader']==0 for m in summary['class_literals']['modules'] if m['name'] in fixture_names)
    source=dict(batch=str(a.batch.resolve()),class_id=names['bootstrap','java/lang/Class'],system_id=names['bootstrap','java/lang/System'],
        constructor_id=ctor,constructor_layout=meta['layouts'][str(ctor)]['candidate'],string_id=meta['string_class'],
        string_value_offset=meta['string_value_offset'],string_coder_offset=meta['string_coder_offset'],
        native_symbol=f"boom_m{pack['methods'][0]['method']}",getters=getters,arrays=meta['arrays'],cases=cases,
        seed_source=str(a.seed.resolve()),fixture_only=True,source_initializer_executed=False,
        fixture_modules=fixture_modules,full_module_bootstrap=False,game_started=False)
    application_annotation_fixture(source,meta,classes,summary)
    (a.output/'source.json').write_text(json.dumps(source,indent=2)+'\n');print(json.dumps(dict(cases=len(cases),getters=len(getters),game_started=False)))
