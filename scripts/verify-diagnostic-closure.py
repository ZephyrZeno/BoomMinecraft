"""Independent source identities and COFF coverage for fail-stop development images."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile


def check(value,message):
    if not value:raise ValueError(message)


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def verify_stops(directory,manifest,summary,coff,verified_provider_packs=None):
    directory=Path(directory);report=json.loads((directory/'diagnostic.json').read_text(encoding='utf-8'))
    check(manifest.get('diagnostic_only') is True and manifest.get('source_closure_complete') is False and manifest.get('lazy_dispatch') is True,
          'Diagnostic source image was promoted to a complete closure')
    check(report['diagnostic_only'] is True and report['source_closure_complete'] is False and not report['native_implementations_added']
          and not report['provided_methods_added'] and report['stop_kind']==0xB001 and (report['pool_bytes'],report['row_bytes'],report['context_bytes'])==(96,48,32),
          'Diagnostic ABI or semantic-provider scope differs')
    rows=report['rows'];symbols=[r['symbol'] for r in rows]
    check(symbols==sorted(set(symbols))==manifest['unprovided_diagnostic_symbols'],'Diagnostic symbol set differs')
    check([r['id'] for r in rows]==list(range(1,len(rows)+1)),'Diagnostic row identity differs')
    batch=Path(manifest['batch']);needed={r['class_id'] for r in rows if r.get('initialization') is None};sources={};shard_for={}
    model=load('diagnostic_stop_render','diagnostic-closure.py')
    global_identity=report.get('global_provider_identity')
    check(global_identity is not None,'Diagnostic ABI provider identity is missing')
    packs=[]
    if manifest.get('runtime_provider_packs'):
        provider_module=load('diagnostic_provider_verification','verify-runtime-provider-pack.py')
        paths=[str(provider_module.S.checked(p['manifest'])) for p in manifest['runtime_provider_packs']]
        if verified_provider_packs is None:
            packs=provider_module.load_packs(batch,manifest['plan'],paths)
        else:
            reuse=load('diagnostic_verified_provider_handoff','provider-verification-reuse.py')
            packs=reuse.reuse(provider_module,batch,manifest['plan'],paths,verified_provider_packs)
        check(provider_module.references(packs)==manifest['runtime_provider_packs'],'Diagnostic provider identities changed')
    known,providers,actual_identity=model.globals_index(batch,summary,global_identity['runtime_dll'],coff,packs,manifest['plan'])
    check(actual_identity==global_identity,'Diagnostic runtime/global provider artifacts changed')
    receiver=manifest.get('diagnostic_receiver')
    if receiver:
        check(receiver['fixture_only'] is True and receiver['constructor_executed'] is False and receiver['class_initialization_executed'] is False
              and not manifest['requested_class_roots'] and len(manifest['requested_method_roots'])==1,'Prepared receiver fixture scope differs')
        entry=manifest['requested_method_roots'][0];check(entry['descriptor']=='()Z','Prepared receiver entry signature differs')
        with zipfile.ZipFile(coff.artifact(batch,summary['runtime_metadata']['index'],'runtime-metadata')) as z:
            types=[json.loads(l) for l in z.read('types.jsonl').splitlines()]
        typ=next((t for t in types if t['id']==receiver['type_id']),None)
        check(typ is not None and typ['kind']==1 and typ['name']==receiver['name'] and typ['defining_loader']==receiver['loader']
              and typ['source_sha256']==receiver['source_sha256'] and receiver['layout_symbol']==f"boom_layout{typ['id']}",'Prepared receiver original type differs')
        classes=[json.loads(l) for l in (Path(manifest['plan'])/'classes.jsonl').open(encoding='utf-8')]
        owner=next(c['id'] for c in classes if c['name']==entry['owner'] and c['origin']['loader']==entry['loader'])
        check(owner==typ['id'] or owner in typ['ancestors'],'Prepared receiver ancestry differs')
        for line in (Path(manifest['plan'])/'methods.jsonl').open(encoding='utf-8'):
            m=json.loads(line)
            if m['id']==entry['method']:
                check(m['access']&8==0,'Prepared receiver cannot call a static entry');break
        else:raise ValueError('Prepared receiver method is missing from source plan')
    for shard in summary['shards']:
        if not needed:break
        with zipfile.ZipFile(coff.artifact(batch,shard['zip'],'shards')) as z:
            for name in z.namelist():
                id_=int(Path(name).stem)
                if id_ not in needed:continue
                cls=json.loads(z.read(name));methods={m['id']:{k:v for k,v in m.items() if k not in ('references','bindings')} for m in cls['methods']}
                bindings={}
                for m in cls['methods']:
                    for b in m['bindings']:bindings.setdefault(b['label'],[]).append(b)
                sources[id_]=dict(source_sha256=cls['source_sha256'],methods=methods,bindings=bindings);shard_for[id_]=shard;needed.remove(id_)
    check(not needed,'Diagnostic source class results missing')
    row_class_ids={r['class_id'] for r in rows};selected_class_ids={c['class_id'] for c in manifest['selected_classes']}
    plan=Path(manifest['plan']);class_hashes={c['id']:c['origin']['sha256'] for l in (plan/'classes.jsonl').open(encoding='utf-8') if (c:=json.loads(l))['id'] in row_class_ids}
    with zipfile.ZipFile(coff.artifact(batch,summary['class_state']['index'],'class-state')) as z:initializations={r['class_id']:r for r in map(json.loads,z.read('classes.jsonl').splitlines())}
    lazy_targets={f"boom_m{target}" for t in manifest['selected_dispatch_tables'].values()
                  for target in [t['array_target'],*[r['target'] for r in t['rows']]] if target is not None}
    site_data,pending_methods,_,site_proof=model.constructor_selection(packs,set(manifest.get('selected_runtime_provider_packs',[])),
        selected_class_ids,manifest['selected_methods'])
    check(manifest.get('constructor_invocation_sites')==site_proof,'Diagnostic constructor selection differs')
    if site_proof:
        check(site_data in (directory/'initialization-closure.asm').read_text(encoding='utf-8'),'Diagnostic constructor callsite data changed')
        lazy_targets.update(f'boom_m{i}' for i in pending_methods)
    for r in rows:
        cls=sources.get(r['class_id']);source_sha=(r['initialization']['source_sha256'] if r.get('initialization') is not None else cls['source_sha256'])
        check(source_sha==r['source_sha256']==class_hashes[r['class_id']],'Diagnostic source class hash differs')
        method=r.get('method');binding=r.get('binding')
        if r.get('initialization') is not None:
            check(r['category']==5 and r['kind']=='unselected_initialization' and method is None and binding is None and
                  initializations.get(r['class_id'])==r['initialization'] and r['class_id'] not in selected_class_ids and
                  r['symbol']=='boom_batch_initialize_'+str(r['class_id']) and r['initialization']['diagnostic'] is None,
                  'Diagnostic original initialization request differs')
        elif method is not None:
            original=cls['methods'].get(method['id'])
            check(original is not None and all(original[k]==v for k,v in method.items()),'Diagnostic method source differs')
            check(re.fullmatch(r'boom_m'+str(method['id'])+r'(?:_body)?',r['symbol']) is not None,'Diagnostic method symbol differs')
            if r['category']==1:
                check(method['assembly_emitted'] and r['kind']=='unselected_method' and r['symbol'] in lazy_targets
                      and method['id'] not in report['admitted_methods'],'Diagnostic lazy target is not an original unselected table target')
            elif r['category']==4:
                check(method['assembly_emitted'] and r['kind']=='abi_dependency','Unavailable runtime-ABI method source differs')
                path=shard_for[r['class_id']]['units'][method['assembly_unit']]['assembly']['path']
                cache=load('diagnostic_original_abi_source','batch-source.py').Sources();body_=cache.function(path,r['symbol'])
                check(r['unprovided_symbols']==model.missing_symbols(body_,known,providers) and r['unprovided_symbols'],
                      'Diagnostic runtime-ABI stop does not match missing original dependencies')
            else:check(r['category']==2 and not method['assembly_emitted'] and r['kind']=='method','Unavailable diagnostic method was marked available')
        else:
            originals=cls['bindings'].get(r['symbol'],[])
            normalize=lambda b:{k:v for k,v in b.items() if k!='caller_method'}
            check(r['category']==3 and binding is not None and originals and binding in originals and all(normalize(b)==normalize(binding) for b in originals),
                  'Diagnostic protocol source binding differs')
    check(report['helper_sha256']==hashlib.sha256(model.HELPER.read_bytes()).hexdigest(),'Diagnostic ASM helper changed')
    context_rows=manifest.get('diagnostic_context_rows',False)
    check(context_rows is ('context_map_sources' in report),'Diagnostic per-context source record differs')
    if context_rows:
        check(report['context_map_sources']=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in model.CONTEXT_HELPERS}
              and model.CONTEXT_EXPORTS<=set(manifest['exports']),'Diagnostic per-context sources or exports changed')
    asm=(directory/'diagnostic-stops.asm').read_text(encoding='utf-8')
    check(asm==model.body(rows,context_rows) and report['assembly_sha256']==hashlib.sha256((directory/'diagnostic-stops.asm').read_bytes()).hexdigest(),
          'Diagnostic ASM differs from its failure-only model')
    defined,undefined=coff.coff_symbols(directory/'diagnostic-stops.obj')
    expected=set(symbols)|{'boom_diagnostic_stop','boom_diagnostic_pool','boom_diagnostic_rows'}
    if context_rows:expected|=model.CONTEXT_EXPORTS
    check(defined==expected and not undefined,'Diagnostic COFF contains missing/extra definitions or imports')
    result=dict(verified=True,diagnostic_only=True,stop_rows=len(rows),unselected_Java_targets=sum(r['category']==1 for r in rows),
                unavailable_methods=sum(r['category']==2 for r in rows),unavailable_protocols=sum(r['category']==3 for r in rows),
                unavailable_runtime_ABI_methods=sum(r['category']==4 for r in rows),
                source_closure_complete=False,native_implementations_added=0,game_started=False,full_game_ready=False)
    return result,defined


def verify(directory):
    m=load('diagnostic_original_source_verifier','verify-initialization-closure.py')
    objects=load('diagnostic_source_object_provenance','diagnostic-objects.py')
    sealed=objects.verify(directory) if (Path(directory)/objects.RECEIPT).is_file() else None
    result=m.verify(directory,allow_diagnostics=True)
    if sealed is not None:
        check(objects.verify(directory)==sealed,'Diagnostic assembly changed during independent source/COFF verification')
        result['verified_assembly_objects']=sealed
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();v=verify(a.directory)
    if a.output:a.output.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(v))
