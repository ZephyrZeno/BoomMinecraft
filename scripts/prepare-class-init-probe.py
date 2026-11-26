"""Select an original initialization closure from our generated MASM and metadata.

No native disassembly and no replacement method bodies. Unsupported dependencies
remain link errors. The selector follows actual emitted source method/class refs.
"""
import argparse
from collections import deque
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time
import zipfile

ROOTS=['java/nio/file/StandardCopyOption','java/nio/file/StandardOpenOption','java/nio/file/LinkOption',
       'java/nio/file/AccessMode','java/nio/file/FileVisitResult','java/lang/Thread$State']
CONSTANT_ROOTS=['javax/xml/XMLConstants','javax/xml/transform/OutputKeys','java/awt/Transparency','java/sql/Connection']

def source_identity(batch,plan):
    identity=batch.get('input_fingerprint')
    if not identity or identity!=plan.get('input_fingerprint'):raise ValueError('Source closure batch/plan input identity differs')
    return identity


def prepare(batch,plan,output,class_roots=None,method_roots=None,scan=False,contract_roots=None,expand_dispatch=True,diagnostic=None,provider_packs=None,verified_provider_packs=None):
    batch,plan,output=Path(batch),Path(plan),Path(output);output.mkdir(parents=True,exist_ok=True)
    summary=json.loads((batch/'summary.json').read_text(encoding='utf-8'));assert summary['schema']>=5
    provider_module=None;packs=[];pack_natives={};pack_for={};selected_pack_natives={};selected_packs=set();pack_needs_class_pool=False
    if provider_packs:
        spec=importlib.util.spec_from_file_location('selected_separate_native_providers',Path(__file__).with_name('verify-runtime-provider-pack.py'))
        provider_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider_module)
        if verified_provider_packs is None:
            packs=provider_module.load_packs(batch,plan,provider_packs)
        else:
            reuse_spec=importlib.util.spec_from_file_location('selection_verified_provider_handoff',Path(__file__).with_name('provider-verification-reuse.py'))
            reuse=importlib.util.module_from_spec(reuse_spec);reuse_spec.loader.exec_module(reuse)
            packs=reuse.reuse(provider_module,batch,plan,provider_packs,verified_provider_packs)
        for index,pack in enumerate(packs):
            for m in pack['manifest']['methods']:pack_natives[m['method']]=m;pack_for[m['method']]=index
    if diagnostic is not None and (scan or not expand_dispatch):raise ValueError('Diagnostic linking requires complete dispatch tables and its own execution mode')
    admitted=set(diagnostic.get('admit_methods',[])) if diagnostic is not None else set()
    if any(not isinstance(i,int) or i<0 for i in admitted):raise ValueError('Invalid admitted diagnostic method')
    if diagnostic is not None:
        spec=importlib.util.spec_from_file_location('diagnostic_abi_checks',Path(__file__).with_name('diagnostic-closure.py'))
        diagnostic_checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic_checks)
    if packs and diagnostic is None:
        spec=importlib.util.spec_from_file_location('provider_closure_dependencies',Path(__file__).with_name('diagnostic-closure.py'))
        diagnostic_checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic_checks)
    overlay=diagnostic_checks.frame_overlay(packs) if packs else None
    plan_summary=json.loads((plan/'summary.json').read_text(encoding='utf-8'));identity=source_identity(summary,plan_summary)
    with (plan/'classes.jsonl').open('rb') as stream:classes_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    with (batch/'summary.json').open('rb') as stream:batch_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    if classes_sha!=plan_summary['artifacts']['classes']['digest']['sha256']:raise ValueError('Source closure class plan changed')
    clone_sites={}
    concat_sites={};concat_model=None
    if summary['schema']>=14:
        with zipfile.ZipFile(summary['string_concat']['index']['path']) as bundle:
            concat_sites={s['label']:s for s in map(json.loads,bundle.read('sites.jsonl').splitlines())}
        spec=importlib.util.spec_from_file_location('selected_concat_model',Path(__file__).with_name('verify-batch-concat.py'))
        concat_model=importlib.util.module_from_spec(spec);spec.loader.exec_module(concat_model)
    if summary['schema']>=7:
        with zipfile.ZipFile(summary['array_clone']['index']['path']) as bundle:
            clone_sites={s['label']:s for s in map(json.loads,bundle.read('sites.jsonl').splitlines())}
    native_methods={}
    if summary['schema']>=8:
        with zipfile.ZipFile(summary['system_natives']['index']['path']) as bundle:
            native_methods={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    class_sites={};class_natives={}
    if summary['schema']>=10:
        with zipfile.ZipFile(summary['class_literals']['index']['path']) as bundle:
            class_sites={s['label']:s for s in map(json.loads,bundle.read('sites.jsonl').splitlines())}
            class_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    intern_natives={}
    if summary['schema']>=12:
        with zipfile.ZipFile(summary['string_intern']['index']['path']) as bundle:
            intern_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    property_natives={}
    if summary['schema']>=13:
        with zipfile.ZipFile(summary['properties']['index']['path']) as bundle:
            property_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    bootstrap_natives={}
    if summary['schema']>=15:
        with zipfile.ZipFile(summary['class_bootstrap']['index']['path']) as bundle:
            bootstrap_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    unsafe_natives={}
    if summary['schema']>=16:
        with zipfile.ZipFile(summary['unsafe_bootstrap']['index']['path']) as bundle:
            unsafe_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    vm_natives={}
    if summary['schema']>=17:
        with zipfile.ZipFile(summary['vm_registration']['index']['path']) as bundle:
            vm_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    resource_natives={}
    if summary['schema']>=18:
        with zipfile.ZipFile(summary['runtime_resources']['index']['path']) as bundle:
            resource_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    bitcast_natives={}
    if summary['schema']>=19:
        with zipfile.ZipFile(summary['bitcasts']['index']['path']) as bundle:
            bitcast_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    unsafe_field_natives={}
    if summary['schema']>=20:
        with zipfile.ZipFile(summary['unsafe_fields']['index']['path']) as bundle:
            unsafe_field_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    lookup_natives={};lookup_initializers={};lookup_map=None
    if summary['schema']>=22:
        with zipfile.ZipFile(summary['class_lookup']['index']['path']) as bundle:
            lookup_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
            lookup_initializers={r['class_id']:r for r in map(json.loads,bundle.read('initializers.jsonl').splitlines())}
        spec=importlib.util.spec_from_file_location('selected_lookup_map',Path(__file__).with_name('verify-batch-class-lookup.py'))
        lookup_model=importlib.util.module_from_spec(spec);spec.loader.exec_module(lookup_model)
    frame_natives={}
    if summary['schema']>=23:
        with zipfile.ZipFile(summary['frames']['index']['path']) as bundle:
            frame_natives={m['method']:m for m in map(json.loads,bundle.read('natives.jsonl').splitlines())}
    unsafe_memory_natives={}
    if summary['schema']>=21:
        with zipfile.ZipFile(summary['unsafe_memory']['index']['path']) as bundle:
            unsafe_memory_natives={m['method']:m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
    enum_suite=class_roots is None and method_roots is None and contract_roots is None
    with zipfile.ZipFile(summary['class_state']['index']['path']) as bundle:
        states={s['class_id']:s for s in map(json.loads,bundle.read('classes.jsonl').splitlines())}
    classes=list(map(json.loads,(plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    method_owners={id_:c['id'] for c in classes for id_ in c['method_ids']}
    shard_for={}
    for shard in summary['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as bundle:
            for name in bundle.namelist():shard_for[int(Path(name).stem)]=shard
    spec=importlib.util.spec_from_file_location('initialization_source_cache',Path(__file__).with_name('batch-source.py'))
    source_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(source_module)
    sources=source_module.Sources();text=sources.text
    spec=importlib.util.spec_from_file_location('initialization_dispatch_selection',Path(__file__).with_name('select-batch-dispatch.py'))
    dispatch_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(dispatch_module)
    dispatch=dispatch_module.Dispatch(summary['dispatch'],sources) if summary['schema']>=6 and expand_dispatch else None
    class_results={};bindings={};methods_by_id={}
    def result(id_):
        if id_ not in class_results:
            with zipfile.ZipFile(shard_for[id_]['zip']['path']) as bundle:
                class_results[id_]=json.loads(bundle.read(f'classes/{id_:06}.json'))
                if class_results[id_]['class_id']!=id_ or class_results[id_]['source_sha256']!=classes[id_]['origin']['sha256']:
                    raise ValueError('Source closure class identity differs from plan')
                for m in class_results[id_]['methods']:
                    m.pop('references',None)
                    methods_by_id[m['id']]=m
                    for binding in m['bindings']:bindings[binding['label']]=binding
        return class_results[id_]
    def method(id_):
        if id_ not in methods_by_id:result(method_owners[id_])
        return methods_by_id[id_]
    selected_methods={};selected_classes={};descriptors={};functions={};selected_contracts={};selected_natives={};queue=deque();frontiers={}
    selected_sites={};selected_tables={};dispatch_data={};seen=set()
    selected_concat_sites={};concat_data={};handler_data={};lazy_targets=set()
    selected_class_sites={};selected_class_natives={};selected_intern_natives={};selected_property_natives={};selected_bootstrap_natives={}
    selected_unsafe_natives={}
    selected_vm_natives={}
    selected_resource_natives={}
    selected_bitcast_natives={}
    selected_unsafe_field_natives={}
    selected_lookup_natives={}
    selected_frame_natives={}
    selected_unsafe_memory_natives={}
    started=time.monotonic();next_progress=started
    def progress(finished=False):
        value=dict(stage='static_source_dependency_scan',scan_pass_finished=finished,elapsed_seconds=round(time.monotonic()-started,3),
            selected_classes=len(selected_classes),selected_Java_methods=len(selected_methods),selected_virtual_sites=len(selected_sites),selected_dispatch_tables=len(selected_tables),
            frontier_symbols=len(frontiers),queued_items=len(queue),indexed_units=sources.indexes,source_function_range_reads=sources.slices,game_started=False)
        temporary=output/'progress.json.tmp';temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');temporary.replace(output/'progress.json')
    def unavailable(kind,symbol,reason,**details):
        if not scan and diagnostic is None:raise ValueError(reason)
        row=dict(kind=kind,symbol=symbol,reason=reason,binding=bindings.get(symbol))
        if diagnostic is not None:
            match=re.fullmatch(r'boom_m(\d+)(?:_body)?',symbol)
            if match:
                id_=int(match[1]);m=method(id_);owner=method_owners[id_]
                row.update(class_id=owner,source_sha256=result(owner)['source_sha256'],method={k:m[k] for k in ('id','name','descriptor','code_sha256','stage','assembly_emitted','assembly_unit')})
            else:
                match=re.fullmatch(r'boom_batch_call_(\d+)_\d+_\d+|boom_batch_literal_load_(\d+)_\d+',symbol)
                if match is None:raise ValueError('Diagnostic linker cannot replace missing data/class state: '+reason)
                owner=int(match[1] or match[2]);result(owner);row['binding']=bindings.get(symbol)
                if row['binding'] is None:raise ValueError('Diagnostic frontier lacks original call-site binding: '+symbol)
                row.update(class_id=owner,source_sha256=result(owner)['source_sha256'])
        row.update(details);frontiers[kind,symbol]=row
    provided_native_ids=set(native_methods)|set(class_natives)|set(intern_natives)|set(property_natives)|set(bootstrap_natives)|set(unsafe_natives)|set(vm_natives)|set(resource_natives)|set(bitcast_natives)|set(unsafe_field_natives)|set(unsafe_memory_natives)|set(lookup_natives)|set(frame_natives)|set(pack_natives)
    def dependencies(body,lazy=False):
        for symbol in sorted(set(re.findall(r'\bboom_[A-Za-z0-9_]+\b',body))):
            match=re.fullmatch(r'boom_m(\d+)(?:_body)?',symbol)
            if match:
                id_=int(match[1])
                if diagnostic is not None and lazy and id_ not in admitted and id_ not in provided_native_ids:lazy_targets.add(symbol)
                else:queue.append(('method',symbol))
            if diagnostic is not None and symbol in diagnostic.get('data_providers',{}):queue.append(('method',f"boom_m{diagnostic['data_providers'][symbol]}"))
            if re.fullmatch(r'boom_batch_call_\d+_\d+_\d+',symbol):queue.append(('contract',symbol))
            if re.fullmatch(r'boom_batch_literal_load_\d+_\d+',symbol) and symbol in bindings and bindings[symbol]['kind']!='string_literal_resolution':queue.append(('contract',symbol))
            match=re.fullmatch(r'boom_class(\d+)|boom_s(\d+)_\d+',symbol)
            if match:queue.append(('class',int(match[1] or match[2])))
    def add_function(symbol,path):
        if symbol in functions:return
        body=sources.function(path,symbol)
        if diagnostic is not None and re.fullmatch(r'boom_m\d+(?:_body)?',symbol):
            missing=diagnostic_checks.missing_symbols(body,diagnostic.get('known_symbols',set()),diagnostic.get('data_providers',{}))
            if missing:
                unavailable('abi_dependency',symbol,'Diagnostic source method requires unavailable runtime symbols',unprovided_symbols=missing)
                return
        functions[symbol]=None if scan else body;dependencies(body)
        for id_ in set(map(int,re.findall(r'\bboom_handlers(\d+)\b',body))):
            data=sources.handler_table(path,id_)
            if id_ in handler_data and handler_data[id_]!=data:raise ValueError('Conflicting source exception handler data')
            handler_data[id_]=data
    roots=[];requested_classes=[];requested_methods=[]
    for loader,name in class_roots or []:
        id_=names[loader,name];queue.append(('class',id_));requested_classes.append(dict(loader=loader,name=name,class_id=id_))
    for loader,owner,name,descriptor in method_roots or []:
        id_=names[loader,owner];m=next(m for m in result(id_)['methods'] if (m['name'],m['descriptor'])==(name,descriptor))
        queue.append(('method',f"boom_m{m['id']}"))
        requested_methods.append(dict(loader=loader,owner=owner,name=name,descriptor=descriptor,method=m['id'],symbol=f"boom_m{m['id']}"))
    for label in contract_roots or []:queue.append(('contract',label))
    if diagnostic is not None:
        for id_ in sorted(set(diagnostic.get('admit_classes',[]))):
            if not isinstance(id_,int) or id_ not in states or states[id_]['diagnostic']:raise ValueError('Invalid admitted source initialization')
            queue.append(('class',id_))
    for id_ in sorted(admitted):
        if id_ not in method_owners:raise ValueError('Admitted diagnostic method is outside the source plan')
        queue.append(('method',f'boom_m{id_}'))
    for name in ROOTS if enum_suite else []:
        id_=names[('bootstrap',name)];queue.append(('class',id_))
        roots.append(dict(name=name,class_id=id_))
        if summary['schema']>=7:
            m=next(m for m in result(id_)['methods'] if (m['name'],m['descriptor'])==('values',f'()[L{name};'))
            roots[-1]['values_method']=f"boom_m{m['id']}";queue.append(('method',roots[-1]['values_method']))
    constant_roots=[]
    for name in CONSTANT_ROOTS if enum_suite else []:
        matches=[c for c in classes if c['name']==name and c['origin']['source_id'].startswith('jdk:')]
        if len(matches)!=1:raise ValueError('Constant class identity is ambiguous')
        id_=matches[0]['id'];queue.append(('class',id_));state=states[id_]
        fields=[f for f in state['fields'] if f['constant'] is not None and f['access']&1]
        constant_roots.append(dict(name=name,class_id=id_,fields=fields))
    if enum_suite:
        enum_id=names[('bootstrap','java/lang/Enum')]
        enum_signatures=[('name','()Ljava/lang/String;'),('ordinal','()I')]
        if summary['schema']>=10:enum_signatures.append(('getDeclaringClass','()Ljava/lang/Class;'))
        for name,descriptor in enum_signatures:
            m=next(m for m in result(enum_id)['methods'] if (m['name'],m['descriptor'])==(name,descriptor))
            queue.append(('method',f"boom_m{m['id']}"))
    while queue:
        if (scan or diagnostic is not None) and time.monotonic()>=next_progress:progress();next_progress=time.monotonic()+5
        kind,value=queue.popleft()
        if (kind,value) in seen:continue
        seen.add((kind,value))
        if kind=='class':
            if value in selected_classes:continue
            state=states[value]
            if state.get('vm_post_initializer')=='unsafe_constants':queue.append(('method',f"boom_m{min(unsafe_natives)}"))
            if state['diagnostic']:
                unavailable('class_state',str(value),f"Unprovided source class state {state['name']}: {state['diagnostic']}");continue
            selected_classes[value]=state
            descriptors[value]=sources.class_descriptor(summary['class_state']['units'][state['assembly_unit']]['assembly']['path'],value)
            if state['dependencies'] or state['initializer'] or any(f['constant'] is not None for f in state['fields']):
                add_function(f'boom_batch_initialize_{value}',summary['class_state']['units'][state['assembly_unit']]['assembly']['path'])
        elif kind=='contract':
            if value in functions:continue
            if value in concat_sites:
                site=concat_sites[value]
                if site['plan'] is None:unavailable('invokedynamic',value,'Unprovided source concat: '+site['diagnostic']);continue
                module=summary['string_concat'];path=module['units'][site['assembly_unit']]['assembly']['path']
                selected_concat_sites[value]=site
                expected=concat_model.body(value,site['plan'],module['bootstrap']['class_id'],module['source_layout']).partition('.code\n')[0]
                concat_data[value]=None if scan else sources.fragment(path,value,expected)
                add_function(value,path);continue
            if value in class_sites:
                site=class_sites[value]
                if site['diagnostic'] is not None:unavailable('literal_resolution',value,'Unprovided Class literal: '+site['diagnostic']);continue
                selected_class_sites[value]=site;continue
            if dispatch is not None and value not in clone_sites and (bindings.get(value,{}).get('kind')=='virtual_dispatch' or value in (contract_roots or [])):
                try:
                    site=dispatch.site(value)
                    table=selected_tables.get(site['table']) or dispatch.table(site['table'])
                except ValueError as error:
                    unavailable('virtual_dispatch',value,str(error));continue
                selected_sites[value]=site
                constraint=dispatch_module.constraint_source(site)
                dispatch_data['boom_batch_vconstraints_'+value]=dispatch.fragment(site,constraint)
                if table['id'] not in selected_tables:
                    selected_tables[table['id']]=table
                    body=dispatch.fragment(table,dispatch_module.table_source(table))
                    dispatch_data[f"boom_batch_vtable{table['id']}"]=None if scan else body
                    dependencies(body,lazy=diagnostic is not None)
                add_function('boom_batch_virtual_invoke',summary['dispatch']['units'][0]['assembly']['path'])
                add_function(value,dispatch.path(site));continue
            if value not in clone_sites:
                unavailable(bindings.get(value,{}).get('kind','call_or_literal_contract'),value,'Initialization closure contract unavailable: '+value);continue
            row=clone_sites[value];selected_contracts[value]=row
            add_function(value,summary['array_clone']['units'][row['assembly_unit']]['assembly']['path'])
        else:
            symbol=value
            if symbol in functions:continue
            id_=int(re.fullmatch(r'boom_m(\d+)(?:_body)?',symbol)[1]);m=method(id_)
            if id_ in pack_natives and symbol==f'boom_m{id_}':
                if id_ in selected_pack_natives:continue
                selected_pack_natives[id_]=pack_natives[id_];pack_index=pack_for[id_];selected_packs.add(pack_index)
                pack_needs_class_pool|='class_literals' in packs[pack_index]['manifest']['required_base_modules']
                for cls in packs[pack_index]['manifest']['required_class_ids']:queue.append(('class',cls))
                for callback in packs[pack_index]['manifest'].get('required_java_methods',[]):queue.append(('method',f'boom_m{callback}'))
                for contract in packs[pack_index]['manifest'].get('required_source_contracts',[]):queue.append(('contract',contract))
                for family in packs[pack_index]['manifest'].get('required_provider_families',[]):
                    dependency=next(p for p in packs if p['manifest']['family']==family)
                    queue.append(('method',f"boom_m{min(m['method'] for m in dependency['manifest']['methods'])}"))
                continue
            if id_ in lookup_natives and symbol==f'boom_m{id_}':
                selected_lookup_natives[id_]=lookup_natives[id_]
                for m_ in lookup_natives.values():queue.append(('class',m_['class_id']))
                queue.append(('method',f'boom_m{min(bootstrap_natives)}'))
                continue
            if id_ in frame_natives and symbol==f'boom_m{id_}':
                selected_frame_natives[id_]=frame_natives[id_]
                for cls in (frame_natives[id_]['class_id'],names[('bootstrap','java/lang/Class')],names[('bootstrap','java/lang/Object')]):queue.append(('class',cls))
                continue
            if id_ in unsafe_memory_natives and symbol==f'boom_m{id_}':
                selected_unsafe_memory_natives[id_]=unsafe_memory_natives[id_]
                queue.append(('method',f'boom_m{min(unsafe_field_natives)}'))
                continue
            if id_ in unsafe_field_natives and symbol==f'boom_m{id_}':
                selected_unsafe_field_natives[id_]=unsafe_field_natives[id_]
                for cls in (unsafe_field_natives[id_]['class_id'],summary['unsafe_bootstrap']['constants_class_id'],
                            names[('bootstrap','java/lang/Class')],names[('bootstrap','java/lang/Object')]):queue.append(('class',cls))
                continue
            if id_ in bitcast_natives and symbol==f'boom_m{id_}':
                selected_bitcast_natives[id_]=bitcast_natives[id_]
                for class_id in summary['bitcasts']['source_class_ids']:queue.append(('class',class_id))
                continue
            if id_ in resource_natives and symbol==f'boom_m{id_}':
                selected_resource_natives[id_]=resource_natives[id_];queue.append(('class',resource_natives[id_]['class_id']));continue
            if id_ in vm_natives and symbol==f'boom_m{id_}':
                selected_vm_natives[id_]=vm_natives[id_];queue.append(('class',vm_natives[id_]['class_id']));continue
            if id_ in unsafe_natives and symbol==f'boom_m{id_}':
                selected_unsafe_natives[id_]=unsafe_natives[id_]
                queue.append(('class',unsafe_natives[id_]['class_id']))
                queue.append(('class',summary['unsafe_bootstrap']['constants_class_id']))
                continue
            if id_ in intern_natives and symbol==f'boom_m{id_}':
                selected_intern_natives[id_]=intern_natives[id_];continue
            if id_ in property_natives and symbol==f'boom_m{id_}':
                selected_property_natives[id_]=property_natives[id_];queue.append(('class',property_natives[id_]['class_id']));continue
            if id_ in bootstrap_natives and symbol==f'boom_m{id_}':
                selected_bootstrap_natives[id_]=bootstrap_natives[id_];queue.append(('class',bootstrap_natives[id_]['class_id']))
                # Registration confirms the supplied AOT instance-native table.
                for m_ in class_natives.values():
                    if m_['class_id']==bootstrap_natives[id_]['class_id']:queue.append(('method',f"boom_m{m_['method']}"))
                continue
            if id_ in class_natives and symbol==f'boom_m{id_}':
                selected_class_natives[id_]=class_natives[id_];continue
            if id_ in native_methods and symbol==f'boom_m{id_}':
                selected_natives[id_]=native_methods[id_];queue.append(('class',native_methods[id_]['class_id']));continue
            if not m['assembly_emitted']:
                owner=classes[method_owners[id_]]['name'];detail=m['diagnostic'] or 'native/abstract declaration has no Java Code'
                unavailable('method',symbol,f"Initialization closure method unavailable: {owner}.{m['name']}{m['descriptor']} [method {id_}]: {detail}");continue
            shard=shard_for[method_owners[id_]]
            add_function(symbol,shard['units'][m['assembly_unit']]['assembly']['path'])
            if symbol in functions:selected_methods[id_]=dict(class_id=method_owners[id_],name=m['name'],descriptor=m['descriptor'],code_sha256=m['code_sha256'],
                source_sha256=result(method_owners[id_])['source_sha256'])
    all_source_initializer_map=any('class_initialization_map' in packs[i]['manifest']['required_base_modules'] for i in selected_packs)
    if selected_lookup_natives or all_source_initializer_map:
        initializer_ids=set(lookup_initializers)
        if all_source_initializer_map:
            with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as bundle:
                initializer_ids={t['id'] for line in bundle.open('types.jsonl') if (t:=json.loads(line))['kind'] in (1,2)
                                 and t['id'] in states and states[t['id']]['diagnostic'] is None}
            if not set(lookup_initializers)<=initializer_ids:raise ValueError('Mirror map omitted an indexed bootstrap initializer')
        if diagnostic is None and initializer_ids-set(selected_classes):raise ValueError('Dynamic class initialization needs all source descriptors or explicit diagnostic stops')
        lookup_map=lookup_model.initialization_map(summary['class_lookup']['type_capacity'],initializer_ids,set(selected_classes))
        if diagnostic is not None:
            for id_ in sorted(initializer_ids-set(selected_classes)):
                state=states[id_];symbol=f'boom_batch_initialize_{id_}'
                reason='Reached Class mirror may require an unselected original class descriptor' if all_source_initializer_map else 'Reached name lookup may require an unselected original class initializer'
                frontiers['unselected_initialization',symbol]=dict(kind='unselected_initialization',symbol=symbol,reason=reason,
                    binding=None,class_id=id_,source_sha256=state['source_sha256'],initialization=state)
    invocation_data='';invocation_proof=None
    if packs:
        invocation_data,pending_methods,pending_classes,invocation_proof=diagnostic_checks.constructor_selection(packs,selected_packs,selected_classes,selected_methods)
        if diagnostic is None and (pending_methods or pending_classes):raise ValueError('Constructor registry needs an explicit diagnostic closure for unselected source targets')
        lazy_targets.update(f'boom_m{i}' for i in pending_methods)
        for id_ in sorted(pending_classes):
            state=states[id_];symbol=f'boom_batch_initialize_{id_}'
            frontiers['unselected_initialization',symbol]=dict(kind='unselected_initialization',symbol=symbol,
                reason='Reached constructor requires an unselected original class initializer',binding=None,class_id=id_,
                source_sha256=state['source_sha256'],initialization=state)
    if diagnostic is not None:
        for symbol in sorted(lazy_targets-set(functions)):
            id_=int(re.fullmatch(r'boom_m(\d+)(?:_body)?',symbol)[1]);m=method(id_)
            unavailable('unselected_method' if m['assembly_emitted'] else 'method',symbol,
                'Lazy diagnostic table target is not selected' if m['assembly_emitted'] else 'Diagnostic target has no generated Java body')
        spec=importlib.util.spec_from_file_location('source_diagnostic_stops',Path(__file__).with_name('diagnostic-closure.py'))
        diagnostic_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic_module)
        diagnostic_manifest=diagnostic_module.publish(output,list(frontiers.values()),admitted,diagnostic.get('global_identity'),diagnostic.get('context_rows',False))
    if scan:
        report=dict(closure_ready=not frontiers,scope=('all_static_dispatch_rows_and_direct_source_symbols_unknown_dynamic_targets_unexpanded' if dispatch is not None else 'direct_source_symbols_and_supported_contracts_only_unexpanded_virtual_dynamic_targets'),
            source_input_fingerprint=identity,source_classes_sha256=classes_sha,batch_ir_identity=summary['ir_identity'],source_batch_summary_sha256=batch_sha,
            requested_class_roots=requested_classes,requested_method_roots=method_roots or [],selected_classes=len(selected_classes),selected_Java_methods=len(selected_methods),
            selected_native_methods=len(selected_natives),selected_virtual_sites=len(selected_sites),selected_dispatch_tables=len(selected_tables),
            selected_Class_literals=len(selected_class_sites),selected_Class_core_natives=len(selected_class_natives),
            selected_String_intern_natives=len(selected_intern_natives),
            selected_property_natives=len(selected_property_natives),
            selected_String_concat_sites=len(selected_concat_sites),
            selected_Class_bootstrap_natives=len(selected_bootstrap_natives),
            selected_Unsafe_natives=len(selected_unsafe_natives),
            selected_VM_natives=len(selected_vm_natives),
            selected_Runtime_resource_natives=len(selected_resource_natives),
            selected_bitcast_natives=len(selected_bitcast_natives),
            selected_Unsafe_field_natives=len(selected_unsafe_field_natives),
            selected_Unsafe_memory_natives=len(selected_unsafe_memory_natives),
            requested_contract_roots=contract_roots or [],dispatch_rows_pruned=False,source_cache_reads=sources.reads,source_cache_indexes=sources.indexes,source_function_range_reads=sources.slices,source_metadata_indexes=sources.metadata_indexes,
            frontiers=list(frontiers.values()),game_started=False,System_boot_phases_completed=False)
        (output/'frontiers.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        progress(True)
        return report
    # Preserve the selected source descriptors/functions. Only their physical
    # zero cells and root regions are regrouped, using the verified source plan.
    parts=['.data?','ALIGN 8','PUBLIC boom_probe_static_roots','boom_probe_static_roots LABEL QWORD']
    root_count=0
    for id_,state in sorted(selected_classes.items()):
        for field in state['fields']:
            if field['reference']:
                parts.extend((f"PUBLIC boom_s{id_}_{field['index']}",f"boom_s{id_}_{field['index']} QWORD ?"));root_count+=1
        parts.extend((f'boom_batch_class_failure_root{id_} QWORD ?',));root_count+=1
    parts.extend(('.const','PUBLIC boom_probe_static_root_count',f'boom_probe_static_root_count QWORD {root_count}'))
    for id_,state in sorted(selected_classes.items()):
        parts.extend(('.data','ALIGN 8',f'PUBLIC boom_class{id_}',descriptors[id_]))
        parts.extend(('.data?','ALIGN 8'))
        for field in state['fields']:
            if not field['reference']:parts.extend((f"PUBLIC boom_s{id_}_{field['index']}",f"boom_s{id_}_{field['index']} QWORD ?"))
    clone_pool=None
    if selected_contracts:
        pool_source=text(summary['array_clone']['units'][summary['array_clone']['contract']['pool_unit']]['assembly']['path'])
        pattern=r'(?m)^boom_batch_array_clone_pool DWORD 041434C50h,1\n QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,0\n'
        match=re.search(pattern,pool_source)
        if not match:raise ValueError('Source array clone pool is missing')
        clone_pool=match[0];parts.extend(('.const','ALIGN 8','PUBLIC boom_batch_array_clone_pool',clone_pool))
    if lookup_map:parts.append(lookup_map)
    if invocation_data:parts.append(invocation_data)
    parts.extend(dispatch_data.values());parts.extend(concat_data.values());parts.extend(handler_data.values());parts.append('.code');parts.extend(functions.values());body='\n'.join(parts)+'\n'
    definitions=set(re.findall(r'(?m)^\s*(boom_\w+)(?::|\s+(?:PROC|LABEL|QWORD|DWORD|WORD|BYTE)\b)',body))
    calls=set(re.findall(r'(?m)^\s*(?:call|jmp)\s+(boom_\w+)',body));references=set(re.findall(r'\bboom_\w+\b',body))-definitions
    prefix=['option casemap:none']+[f"EXTERN {symbol}:{'PROC' if symbol in calls else 'BYTE'}" for symbol in sorted(references)]
    prefix.extend(f'PUBLIC {symbol}' for symbol in functions)
    (output/'initialization-closure.asm').write_text('\n'.join(prefix)+'\n.code\n'+body+'\nEND\n',encoding='utf-8')
    enum_methods={name:f"boom_m{next(m['id'] for m in result(enum_id)['methods'] if m['name']==name)}" for name in (('name','ordinal','getDeclaringClass') if summary['schema']>=10 else ('name','ordinal'))} if enum_suite else {}
    for root in roots:
        state=states[root['class_id']]
        root['values_field']=next(f['index'] for f in state['fields'] if f['name']=='$VALUES')
        root['constant_fields']=[f['index'] for f in state['fields'] if f['access']&0x4000]
    (output/'roots.tsv').write_text(''.join(f"{r['name']}\t{r['class_id']}\t{r['values_field']}\t{','.join(map(str,r['constant_fields']))}"+
        (f"\t{r['values_method']}" if 'values_method' in r else '')+'\n' for r in roots),encoding='ascii')
    (output/'constants.tsv').write_text(''.join(f"{r['name']}\t{r['class_id']}\t{f['name']}\t{f['index']}\t{f['descriptor']}\n" for r in constant_roots for f in r['fields']),encoding='ascii')
    objects=[u['object']['path'] for key in ('string_literals','runtime_metadata') for u in summary[key]['units']]
    objects.extend(packs[i]['manifest']['object']['path'] for i in sorted(selected_packs))
    if summary['schema']>=23:objects.append((overlay['object'] if overlay else summary['frames']['units'][0]['object'])['path'])
    if selected_frame_natives:objects.append(summary['frames']['units'][1]['object']['path'])
    objects.append(summary['numeric_kernel_object']['path'])
    if selected_natives:objects.extend(u['object']['path'] for u in summary['system_natives']['units'])
    if selected_class_sites or selected_class_natives or selected_intern_natives or selected_unsafe_field_natives or selected_lookup_natives or selected_frame_natives or pack_needs_class_pool:objects.extend(u['object']['path'] for u in summary['class_literals']['units'])
    if selected_intern_natives:objects.extend(u['object']['path'] for u in summary['string_intern']['units'])
    if selected_property_natives:objects.extend(u['object']['path'] for u in summary['properties']['units'])
    if selected_bootstrap_natives:objects.extend(u['object']['path'] for u in summary['class_bootstrap']['units'])
    if selected_unsafe_natives or selected_unsafe_field_natives:objects.extend(u['object']['path'] for u in summary['unsafe_bootstrap']['units'])
    if selected_vm_natives:objects.extend(u['object']['path'] for u in summary['vm_registration']['units'])
    if selected_resource_natives:objects.extend(u['object']['path'] for u in summary['runtime_resources']['units'])
    if selected_bitcast_natives:objects.extend(u['object']['path'] for u in summary['bitcasts']['units'])
    if selected_unsafe_field_natives:objects.extend(u['object']['path'] for u in summary['unsafe_fields']['units'])
    if selected_lookup_natives:objects.append(summary['class_lookup']['units'][0]['object']['path'])
    if selected_unsafe_memory_natives:objects.extend(u['object']['path'] for u in summary['unsafe_memory']['units'])
    exports=['boom_probe_static_roots','boom_probe_static_root_count','boom_java_string_literals_bind_heap','boom_java_string_literal_pool',*enum_methods.values()]
    for i in sorted(selected_packs):exports.extend(packs[i]['manifest']['exports'])
    if summary['schema']>=23:exports.extend(('boom_trace_pool','boom_release_trace_pool'))
    if selected_frame_natives:
        exports.append('boom_java_caller_pool')
        exports.extend(f"boom_m{m['method']}{suffix}" for m in frame_natives.values() for suffix in ('','_native'))
    if selected_lookup_natives:
        exports.extend(('boom_java_class_lookup_pool','boom_java_class_lookup_rows','boom_java_class_lookup_names','boom_java_class_initialization_map'))
        exports.extend(f"boom_m{m['method']}{suffix}" for m in lookup_natives.values() for suffix in ('','_native'))
    elif all_source_initializer_map:
        exports.append('boom_java_class_initialization_map')
    if selected_unsafe_field_natives:
        exports.extend(('boom_java_unsafe_field_pool','boom_java_unsafe_field_names','boom_java_unsafe_field_ranges','boom_java_unsafe_field_pages'))
        exports.extend(f"boom_m{m['method']}{suffix}" for m in unsafe_field_natives.values() for suffix in ('','_native'))
    if selected_unsafe_memory_natives:
        exports.extend(f"boom_m{m['method']}{suffix}" for m in unsafe_memory_natives.values() for suffix in ('','_native'))
    if selected_bitcast_natives:
        exports.append('boom_java_bitcast_pool')
        exports.extend(f"boom_m{m['method']}{suffix}" for m in bitcast_natives.values() for suffix in ('','_native'))
    if selected_resource_natives:
        exports.append('boom_java_runtime_pool')
        exports.extend(f"boom_m{m['method']}{suffix}" for m in resource_natives.values() for suffix in ('','_native'))
    if selected_vm_natives:
        exports.append('boom_java_vm_pool')
        exports.extend(f"boom_m{m['method']}{suffix}" for m in vm_natives.values() for suffix in ('','_native'))
    if selected_unsafe_natives or selected_unsafe_field_natives:
        exports.extend(('boom_java_unsafe_pool','boom_java_unsafe_bindings','boom_java_unsafe_scales','boom_java_unsafe_constant_cells'))
        exports.extend(f"boom_m{m['method']}{suffix}" for m in unsafe_natives.values() for suffix in ('','_native'))
    for root in roots:exports.extend([f"boom_class{root['class_id']}",f"boom_s{root['class_id']}_{root['values_field']}",*[f"boom_s{root['class_id']}_{f}" for f in root['constant_fields']]])
    exports.extend(r['values_method'] for r in roots if 'values_method' in r)
    for root in constant_roots:exports.extend([f"boom_class{root['class_id']}",*[f"boom_s{root['class_id']}_{f['index']}" for f in root['fields']]])
    if not enum_suite:
        for id_,state in selected_classes.items():exports.extend([f'boom_class{id_}',*[f"boom_s{id_}_{f['index']}" for f in state['fields']]])
        exports.extend(('boom_runtime_type_map','boom_batch_type_descriptors','boom_batch_runtime_rows','boom_java_string_literal'))
        exports.extend(m['symbol'] for m in requested_methods)
        exports.extend(contract_roots or [])
    if selected_natives:
        exports.extend(('boom_batch_system_native_pool','boom_batch_system_native_table'))
        if summary['system_natives']['abi']>=2:exports.extend(('boom_batch_system_stream_pool','boom_batch_system_stream_rows'))
        exports.extend(f"boom_m{m['method']}{suffix}" for m in native_methods.values() for suffix in ('','_native'))
    if selected_class_sites or selected_class_natives or selected_intern_natives or selected_unsafe_field_natives or selected_frame_natives or pack_needs_class_pool:
        exports.extend(('boom_java_class_pool','boom_java_class_root_count','boom_java_class_roots','boom_java_class_loader_roots','boom_java_class_module_roots','boom_java_class_records'))
        if summary['schema']>=11:exports.extend(('boom_java_class_name_pool','boom_java_class_name_root_count','boom_java_class_name_roots'))
        exports.extend(f"boom_m{m['method']}{suffix}" for m in class_natives.values() for suffix in ('','_native'))
        exports.extend(selected_class_sites)
    if selected_intern_natives:
        exports.extend(('boom_java_string_intern_pool','boom_java_string_intern_root_count','boom_java_string_intern_root'))
        exports.extend(f"boom_m{m['method']}{suffix}" for m in intern_natives.values() for suffix in ('','_native'))
    if selected_property_natives:
        exports.extend(('boom_java_properties_roots','boom_java_properties_root_count','boom_java_platform_properties_pool',
                        'boom_java_vm_properties_pool','boom_java_properties_string_pool'))
        exports.extend(f"boom_m{m['method']}{suffix}" for m in property_natives.values() for suffix in ('','_native'))
    if selected_bootstrap_natives:
        exports.extend(('boom_java_class_bootstrap_pool','boom_java_class_bootstrap_natives','boom_java_primitive_names'))
        exports.extend(f"boom_m{m['method']}{suffix}" for m in bootstrap_natives.values() for suffix in ('','_native'))
    if diagnostic is not None:exports.extend(('boom_diagnostic_pool','boom_diagnostic_rows','boom_diagnostic_stop'))
    if diagnostic is not None and diagnostic.get('context_rows'):
        exports.extend(sorted(diagnostic_module.CONTEXT_EXPORTS))
    manifest=dict(batch=str(batch.resolve()),plan=str(plan.resolve()),roots=roots,constant_roots=constant_roots,enum_methods=enum_methods,objects=objects,exports=exports,
        source_input_fingerprint=identity,source_classes_sha256=classes_sha,batch_ir_identity=summary['ir_identity'],source_batch_summary_sha256=batch_sha,
        selected_classes=list(selected_classes.values()),selected_methods=selected_methods,
        enum_suite=enum_suite,requested_class_roots=requested_classes,requested_method_roots=requested_methods,selected_native_methods=selected_natives,
        requested_contract_roots=contract_roots or [],selected_dispatch_sites=selected_sites,selected_dispatch_tables=selected_tables,dispatch_rows_pruned=False,
        selected_dispatch_data_sha256={name:hashlib.sha256(body.encode()).hexdigest() for name,body in dispatch_data.items()},
        selected_array_clone_contracts=selected_contracts,selected_array_clone_pool_sha256=hashlib.sha256(clone_pool.encode()).hexdigest() if clone_pool else None,
        selected_Class_literals=selected_class_sites,selected_Class_core_natives=selected_class_natives,
        selected_String_intern_natives=selected_intern_natives,
        selected_property_natives=selected_property_natives,
        selected_Class_bootstrap_natives=selected_bootstrap_natives,
        selected_Unsafe_natives=selected_unsafe_natives,
        selected_VM_natives=selected_vm_natives,
        selected_Runtime_resource_natives=selected_resource_natives,
        selected_bitcast_natives=selected_bitcast_natives,
        selected_Unsafe_field_natives=selected_unsafe_field_natives,
        selected_Unsafe_memory_natives=selected_unsafe_memory_natives,selected_Class_lookup_natives=selected_lookup_natives,
        selected_caller_natives=selected_frame_natives,source_frame_abi=3 if summary['schema']>=23 else None,
        selected_String_concat_sites=selected_concat_sites,
        selected_concat_data_sha256={name:hashlib.sha256(body.encode()).hexdigest() for name,body in concat_data.items()},
        selected_handler_data_sha256={str(id_):hashlib.sha256(body.encode()).hexdigest() for id_,body in handler_data.items()},
        selected_function_sha256={name:hashlib.sha256(body.encode()).hexdigest() for name,body in functions.items()},
        runtime_language='assembly',class_initialization_executed=False,game_started=False)
    if diagnostic is not None:manifest.update(diagnostic_only=True,source_closure_complete=False,diagnostic_manifest='diagnostic.json',
        admitted_classes=sorted(diagnostic.get('admit_classes',[])),
        unprovided_diagnostic_symbols=[r['symbol'] for r in diagnostic_manifest['rows']],lazy_dispatch=True)
    if packs:manifest.update(runtime_provider_packs=provider_module.references(packs),selected_runtime_provider_packs=sorted(selected_packs),
        selected_runtime_provider_natives=selected_pack_natives,base_Java_codegen_rerun=False,selected_diagnostic_Java_reassembled=True)
    if overlay:manifest['runtime_frame_overlay']=overlay
    if diagnostic is not None and diagnostic.get('context_rows'):manifest['diagnostic_context_rows']=True
    if all_source_initializer_map:manifest['all_source_initializer_map']=True
    if invocation_proof:manifest['constructor_invocation_sites']=invocation_proof
    (output/'closure.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('batch',type=Path);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--class-root',action='append',help='loader:internal/class/name')
    parser.add_argument('--entry',action='append',help='loader:internal/class/name:method:descriptor')
    parser.add_argument('--scan',action='store_true',help='Collect all discovered gaps without publishing a linkable closure')
    parser.add_argument('--contract',action='append',help='Verified generated source call-site symbol')
    parser.add_argument('--direct-only',action='store_true',help='Leave virtual dispatch as an explicit unexpanded frontier')
    args=parser.parse_args()
    result=prepare(args.batch,args.plan,args.output,[tuple(v.split(':',1)) for v in args.class_root] if args.class_root is not None else None,
                   [tuple(v.split(':',3)) for v in args.entry] if args.entry is not None else None,args.scan,args.contract,not args.direct_only)
    print(json.dumps(dict(output=str(args.output),**({'closure_ready':result['closure_ready'],'frontiers':len(result['frontiers'])} if args.scan else
         {'classes':len(result['selected_classes']),'methods':len(result['selected_methods'])})),indent=2))
