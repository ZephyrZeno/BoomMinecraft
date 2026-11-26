"""Execute the formal Reference provider with normal cold class and failure roots."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier,Event,get_native_id
from time import perf_counter_ns
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


T=module('reference_existing_verified_execution_rules','test-reference-referent.py')
S=T.S
P,U,Q,Context=T.P,T.U,T.Q,T.Context
proc,addr,linearization,oracle=T.proc,T.addr,T.linearization,T.oracle
ROOTS=[]
ACTIVE_IMAGE=None


def forbid_candidate(*args,**kwargs):
    raise AssertionError('Formal Reference execution cannot validate, build or consume a scratch native candidate')


T.B.contract=T.B.verify=T.B.build=forbid_candidate


def probe_model(pack,meta,summary,classes):
    fixtures,owners=T.java_fixtures(summary,classes)
    required=pack['required_class_ids']
    named={row['id']:row for row in classes}
    S.check(meta['methods']==pack['methods'] and required==meta['required_classes'] and len(required)==3 and
        len(pack['methods'])==4 and pack['pool_bytes']==48 and pack['pool_abi']==2,
        'Expected the complete source-bound formal four-native Reference pack')
    entries=meta['ordinary_Java']+fixtures
    class_roots=[('bootstrap',name) for name in owners if name!='java/lang/ref/PhantomReference']
    S.check(not set(required)&{row['id'] for row in classes if (row['origin']['loader'],row['name']) in class_roots},
        'Probe roots must not manually provide a required reference class descriptor')
    return dict(original_Java_fixture_methods=fixtures,fixture_classes=owners,
        required_classes=[dict(id=ident,name=named[ident]['name'],reference_static_fields=[dict(index=index,**field)
            for index,field in enumerate(named[ident]['fields']) if field['access']&8 and field['descriptor'][0] in ('L','[')])
            for ident in required],
        requested_class_roots=class_roots,requested_method_ids=sorted({row['method'] for row in entries}),
        expected_original_Java=entries)


def verify_suite_reuse():
    original=ast.parse(inspect.getsource(T.run)).body[0]
    formal=ast.parse(inspect.getsource(run_suite)).body[0]
    start=next(index for index,node in enumerate(original.body) if isinstance(node,ast.Assign) and
        any(isinstance(target,ast.Name) and target.id=='runtime' for target in node.targets))
    reference=original.body[start:-1]
    actual=[node for node in formal.body[:-1] if not (isinstance(node,ast.Assign) and
        any(isinstance(target,ast.Name) and target.id in ('cold_before','cold_after') for target in node.targets))]
    normalized=lambda nodes:ast.dump(ast.Module(body=nodes,type_ignores=[]),include_attributes=False)
    S.check(normalized(reference)==normalized(actual),
        'Formal suite changed the verified original Java/native/linearization/GC/oracle rules')
    old={row.arg:ast.dump(row.value,include_attributes=False) for row in original.body[-1].value.keywords}
    new={row.arg:ast.dump(row.value,include_attributes=False) for row in formal.body[-1].value.keywords}
    S.check(all(new.get(name)==value for name,value in old.items() if name not in ('scope','registered_in_shared_runtime')),
        'Formal suite changed a previously verified result assertion')
    return dict(original_tool=S.artifact(Path(T.__file__)),formal_tool=S.artifact(Path(__file__)),
        common_execution_AST_sha256=hashlib.sha256(normalized(reference).encode()).hexdigest(),
        unchanged_original_Java_native_linearization_GC_oracle_rules=True,
        additional_checks='formal provider source/receipt; cold ordinary classes; standard static and failure root bank')


def class_roots(image,config,require_cold):
    global ACTIVE_IMAGE
    ACTIVE_IMAGE=image
    start=addr(image,'boom_probe_static_roots')
    count=Q.from_address(addr(image,'boom_probe_static_root_count')).value
    S.check(count and count<=1048576,'Invalid normal static/failure root span')
    result=[]
    for cls in config['required_source_classes']:
        ident=cls['id'];descriptor=addr(image,'boom_class'+str(ident))
        S.check(U.from_address(descriptor+4).value==2,'Source class descriptor ABI differs')
        state=U.from_address(descriptor+8).value
        failure=P.from_address(descriptor+56).value
        S.check(failure and start<=failure<start+count*8 and (failure-start)%8==0 and
            Q.from_address(failure).value==0 and (not require_cold or state==0),
            'Required ordinary class is warm or its failure root is outside the normal source bank')
        fields=[]
        for field in cls['reference_static_fields']:
            address=addr(image,f"boom_s{ident}_{field['index']}")
            S.check(start<=address<start+count*8 and (address-start)%8==0,
                'Original reference static field is outside the normal root bank')
            fields.append(dict(name=field['name'],index=field['index'],root_cell=(address-start)//8,
                value=Q.from_address(address).value))
        result.append(dict(class_id=ident,name=cls['name'],state=state,failure_root_cell=(failure-start)//8,
            normal_root_cells=count,failure_root_in_normal_span=True,reference_static_fields=fields))
    if not require_cold:
        states={row['class_id']:row['state'] for row in result}
        S.check(states[config['reference_class']]==2 and states[config['phantom_class']]==2,
            'Original Reference/Phantom class initializers did not complete')
        reference=next(row for row in result if row['class_id']==config['reference_class'])
        [lock]=[field for field in reference['reference_static_fields'] if field['name']=='processPendingLock']
        S.check(lock['value']!=0,'Original Reference initializer did not publish its lock in the normal static root')
    return result


def execution_exports(probe,meta):
    exports={f"boom_m{row['method']}" for row in probe['expected_original_Java']}
    exports|={f'boom_class{ident}' for ident in probe['fixture_classes'].values()}
    exports|={f'boom_layout{ident}' for ident in probe['fixture_classes'].values()}
    exports|={f"boom_layout{meta['final_reference_type']}"}
    exports|={f"boom_class{row['id']}" for row in probe['required_classes']}
    exports|={f"boom_s{row['id']}_{field['index']}" for row in probe['required_classes'] for field in row['reference_static_fields']}
    exports|={'boom_heap_ptr','boom_java_string_literals_bind_heap','boom_diagnostic_pool',
        'boom_probe_static_roots','boom_probe_static_root_count'}
    optional={name for pair in T.ROOTS for name in pair}
    return exports,optional-exports


def selected_source_model(images,formal_provider,pack,meta,probe):
    closure=S.read(S.checked(images['source_manifest']))
    selected={row['class_id']:row for row in closure['selected_classes']}
    required=set(pack['required_class_ids'])
    explicit={row['class_id'] for row in closure['requested_class_roots']}|set(closure['admitted_classes'])
    S.check(required<=set(selected) and not required&explicit,
        'Required Reference classes must use ordinary provider dependencies, not manual class roots')
    all_packs=closure['runtime_provider_packs']
    selected_packs=closure['selected_runtime_provider_packs']
    matches=[index for index in selected_packs if S.checked(all_packs[index]['manifest'])==formal_provider]
    S.check(len(matches)==1 and S.checked(pack['object']) in [Path(path) for path in closure['objects']] and
        all(str(row['method']) in closure['selected_runtime_provider_natives'] for row in meta['methods']),
        'Source image must select the actual formal Reference COFF and all four original natives')
    for method in probe['expected_original_Java']:
        row=closure['selected_methods'].get(str(method['method']))
        S.check(row and row['class_id']==method['class_id'] and row['source_sha256']==method['class_sha256'] and
            row['code_sha256']==method['code_sha256'],'Formal source selection omitted an original Java probe entry')
    descriptors=[]
    for row in probe['required_classes']:
        state=selected[row['id']]
        S.check({(field['index'],field['name']) for field in state['fields'] if field['reference']}==
            {(field['index'],field['name']) for field in row['reference_static_fields']},
            'Ordinary selected source state omitted an original reference static field')
        descriptors.append(dict(row,reference_static_fields=[field for field in state['fields'] if field['reference']]))
    return descriptors


def worker(output):
    global ROOTS
    config_file=output/'formal-reference-input.json'
    config=S.read(config_file)
    S.check(S.artifact(Path(__file__))==config['execution_tool'] and verify_suite_reuse()==config['execution_rule_reuse'],
        'Formal Reference test or shared execution rules changed')
    images_file=S.checked(config['images'])
    images=S.read(images_file)
    helper=module('formal_reference_worker_source_helper','formal-provider-selection.py')
    helper.verify(images_file)
    provider=S.checked(config['formal_provider']);pack=S.read(provider)
    meta=S.read(S.checked(pack['reference_referent_metadata']))
    S.check(meta==config['metadata'] and pack['tool_sources']==S.tools_identity() and
        S.artifact(provider.with_name('verification.json'))==config['formal_provider_verification'],
        'Actual formal Reference source metadata or receipt changed')
    ROOTS=[tuple(pair) for pair in config['root_spans']]
    try:
        result=run_suite(images_file,config,meta)
        result.update(execution_rule_reuse=config['execution_rule_reuse'],
            original_Java_or_COFF_changed=False,original_virtual_tables_modified=False,
            manual_Java_class_state_write=False,all_26_provider_runtime_execution_claimed=False)
        S.write(output/'execution.json',result)
    except BaseException as error:
        fault=None
        context=None
        if ACTIVE_IMAGE is not None:
            pool=addr(ACTIVE_IMAGE,'boom_diagnostic_pool')
            index=U.from_address(pool+32).value
            diagnostic=S.read(Path(images['source_selection_directory'])/'diagnostic.json')
            fault=next((row for row in diagnostic['rows'] if row['id']==index),None)
            context=[U.from_address(pool+offset).value for offset in (56,44,48,52)]
        S.write(output/'failure.json',dict(verified=False,diagnostic_only=True,scope='formal_Reference_cold_source_execution_failure',
            error=repr(error),fault=fault,context=context,images=S.artifact(images_file),
            formal_provider=config['formal_provider'],game_started=False))
        raise


def run_suite(images_file,config,meta):
    runtime=S.checked(config['runtime'])
    with os.add_dll_directory(str(runtime.parent)):
        rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
    cold_before=class_roots(image,config,require_cold=True)
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Reference source heap bind failed')
    allocate=proc(rt,'boom_object_new',P,P,P,P)
    contains=proc(rt,'boom_heap_contains',U,P,P)
    methods={(row['owner'],row['name'],row['descriptor']):row['method'] for row in
        meta['ordinary_Java']+config['original_Java_fixture_methods']}
    def call(ident,context,args,native=False):
        packed=(Q*max(len(args),1))(*args)
        value=proc(image,'boom_m'+str(ident)+('_native' if native else ''),Q,P,P)(context,packed)
        return value
    def source(owner,name,descriptor,args):
        context=Context()
        value=call(methods[owner,name,descriptor],context,args)
        if context[0] or context[3]:
            diagnostic=addr(image,'boom_diagnostic_pool')
            raise ValueError('Original Reference Java stopped: '+str((owner,name,descriptor,list(context),U.from_address(diagnostic+32).value)))
        return value
    def new(name):
        cls=config['fixture_classes'][name];context=Context()
        proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(cls)),context)
        S.check(not context[0],'Original reference fixture class initializer stopped: '+str((name,list(context))))
        value=allocate(heap,addr(image,'boom_layout'+str(cls)),context)
        S.check(value and not context[0],'Source reference object allocation failed')
        return value
    obj='java/lang/Object';ref='java/lang/ref/Reference'
    weak='java/lang/ref/WeakReference';soft='java/lang/ref/SoftReference';phantom='java/lang/ref/PhantomReference'
    def target():
        value=new(obj);source(obj,'<init>','()V',[value]);return value
    def reference(name,value):
        value_oop=new(name)
        descriptor='(Ljava/lang/Object;Ljava/lang/ref/ReferenceQueue;)V' if name==phantom else '(Ljava/lang/Object;)V'
        source(name,'<init>',descriptor,[value_oop,value,0] if name==phantom else [value_oop,value])
        return value_oop
    def get(value,name=ref):
        return source(name,'get','()Ljava/lang/Object;',[value])
    def identity(value,other):
        return source(ref,'refersTo','(Ljava/lang/Object;)Z',[value,other])
    def clear(value):
        return source(ref,'clear','()V',[value])
    left,right=target(),target()
    natives={row['operation']:row for row in meta['methods']}
    cases=[]
    for name in (weak,soft,phantom):
        value=reference(name,left)
        getter=phantom if name==phantom else soft if name==soft else ref
        S.check(get(value,getter)==(0 if name==phantom else left) and identity(value,left)==1 and
            identity(value,right)==0 and identity(value,0)==0,'Original live reference Java semantics differ')
        operation=3 if name==phantom else 1
        context=Context()
        S.check(call(natives[operation]['method'],context,[value,left])==1 and not context[0],
            'Original framed refersTo0 native did not execute')
        clear(value);clear(value)
        S.check(get(value,getter)==0 and identity(value,left)==0 and identity(value,0)==1,
            'Original Java clear did not clear the inherited referent')
        empty=reference(name,0)
        S.check(identity(empty,0)==1 and identity(empty,left)==0,'Originally null referent identity differs')
        cases.append(name)
    live=reference(weak,left);p_live=reference(phantom,left)
    negative=0
    for operation,row in natives.items():
        valid=p_live if operation==3 else live
        for bad,expected in ((0,4),(1,7),(left,7),(live+1,7)):
            context=Context();args=[bad,0] if operation in (1,3) else [bad]
            S.check(not call(row['method'],context,args) and context[0]==expected and not context[3],
                'Invalid source receiver escaped field/heap/type checking')
            negative+=1
        context=Context(9,4,7,0,11,12,13,14);before=list(context)
        args=[valid,left] if operation in (1,3) else [valid]
        S.check(not call(row['method'],context,args) and list(context)==before,'Pending error was replaced')
        if operation in (1,3):
            context=Context()
            S.check(not call(row['method'],context,[valid,1]) and context[0]==7,'Foreign comparison oop was accepted')
    S.check(get(live)==left and identity(p_live,left)==1,'Negative tests modified valid referent fields')
    for operation,receiver in ((0,p_live),(1,p_live),(3,live)):
        context=Context();args=[receiver,left] if operation in (1,3) else [receiver]
        S.check(not call(natives[operation]['method'],context,args) and context[0]==7,'Private native type precondition was bypassed')
    context=Context();final_oop=allocate(heap,addr(image,'boom_layout'+str(meta['final_reference_type'])),context)
    S.check(final_oop and not context[0],'Cannot allocate negative FinalReference type fixture')
    context=Context()
    S.check(not call(natives[2]['method'],context,[final_oop]) and context[0]==7,'FinalReference private clear precondition was bypassed')
    histories=[];certificates=[];tids=set()
    with ThreadPoolExecutor(8) as workers:
        for iteration in range(16):
            value=reference(weak,left);barrier=Barrier(9,timeout=20);reader_done=Event();cleared=Event()
            def timed(kind):
                start=perf_counter_ns()
                result=get(value) if kind=='get' else clear(value) if kind=='clear' else identity(value,left if kind=='target' else 0)
                return dict(kind=kind,start=start,end=perf_counter_ns(),value=result,OS_thread=get_native_id())
            initial=timed('get')
            def worker(index):
                kind=('clear','get','target','null')[index%4];barrier.wait();rows=[]
                if kind=='clear':
                    S.check(reader_done.wait(15),'No real reader entered the concurrent clear trial')
                for step in range(16):
                    if kind!='clear' and step==8:
                        S.check(cleared.wait(15),'Concurrent clear did not complete')
                    rows.append(timed(kind))
                    if kind=='clear':cleared.set()
                    else:reader_done.set()
                return rows
            jobs=[workers.submit(worker,index) for index in range(8)]
            barrier.wait()
            history=[initial]+[row for job in jobs for row in job.result(timeout=20)]+[timed('get')]
            tids|={row['OS_thread'] for row in history[1:-1]}
            certificates.append(linearization(history,left));histories.append(history)
    S.check(len(tids)==8,'Concurrent clear history did not use eight actual OS threads')
    history_file=images_file.parent/('linearization-'+uuid4().hex+'.json')
    S.write(history_file,dict(histories=histories,certificates=certificates))
    # Explicit collection occurs only after every worker joined. Keep every real
    # source static/cache root, then add the test's live Java local handles.
    collections=[]
    def collect(extra):
        roots=[];spans=[]
        for name,count_name in ROOTS:
            count=Q.from_address(addr(image,count_name)).value
            S.check(count<=1048576,'Invalid normal source GC root span')
            base=addr(image,name)
            values=[value for value in (Q*count).from_address(base) if value]
            roots+=values;spans.append(dict(symbol=name,count=count,non_null_cells=len(values),
                snapshot_sha256=hashlib.sha256(bytes((Q*count).from_address(base))).hexdigest()))
        # Null/duplicate cells do not change reachability. Compact the exact
        # supplied root values; do not add allocated objects or mutate a bank.
        original=roots+extra
        roots=list(dict.fromkeys(original))
        compact=set(roots)
        S.check(all(value in compact for value in original),'Compaction omitted a real source root or explicit test handle')
        S.check(len(roots)<=1048576,'Explicit source roots exceed the runtime GC contract')
        packed=(Q*len(roots))(*roots)
        snapshot=dict(source_spans=spans,physical_source_cells=sum(row['count'] for row in spans),
            non_null_source_cells=sum(row['non_null_cells'] for row in spans),
            additional_test_handles=list(extra),before_deduplication=len(original),after_deduplication=len(roots),
            every_non_null_oop_in_compacted_set=True,snapshot_sha256=hashlib.sha256(bytes(packed)).hexdigest(),
            source_root_banks_unmodified=True,all_workers_joined=True)
        freed=proc(rt,'boom_heap_collect',Q,P,P,U)(heap,packed,len(roots))
        S.check(freed!=0xffffffffffffffff,'Quiescent source collection failed')
        for row in spans:
            S.check(hashlib.sha256(bytes((Q*row['count']).from_address(addr(image,row['symbol'])))).hexdigest()==row['snapshot_sha256'],
                'Collection changed an original source root bank')
        snapshot['freed_objects']=freed;collections.append(snapshot)
        return freed,spans
    retained_target=target();retained_ref=reference(weak,retained_target)
    first,spans=collect([retained_ref])
    S.check(contains(heap,retained_ref) and contains(heap,retained_target) and get(retained_ref)==retained_target,
        'Inherited referent reference-prefix root was lost in explicit collection')
    clear(retained_ref)
    second,_=collect([retained_ref,retained_target])
    S.check(contains(heap,retained_target) and get(retained_ref)==0 and identity(retained_ref,0)==1,
        'Independent strong root did not survive clear and explicit collection')
    third,_=collect([retained_ref])
    S.check(not contains(heap,retained_target) and get(retained_ref)==0 and identity(retained_ref,0)==1,
        'Cleared referent did not become reclaimable after removing its last explicit strong root')
    fourth,_=collect([])
    gc_file=images_file.parent/('quiescent-GC-'+uuid4().hex+'.json')
    S.write(gc_file,dict(collections=collections,root_vectors_compacted_without_omission=True,
        source_root_banks_unmodified=True,referent_fields_host_written=False))
    context=Context()
    S.check(not call(natives[0]['method'],context,[retained_ref]) and context[0]==7,
        'An actually collected receiver bypassed heap validation')
    cold_after=class_roots(image,config,require_cold=False)
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Reference operations retained a monitor/heap ownership lease')
    oracle_dir=images_file.parent/('oracle-'+uuid4().hex);oracle_dir.mkdir()
    S.check(S.digest(config['oracle_modules']['path'])['sha256']==config['oracle_modules']['digest']['sha256'],
        'Locked oracle JDK input changed')
    comparison=oracle(Path(config['oracle_home']),oracle_dir)
    return dict(schema=2,verified=True,scope='formal_Reference_pack_original_Java_four_natives_atomic_clear_quiescent_GC',
        images=S.artifact(images_file),native_methods=[row['method'] for row in meta['methods']],
        original_Java_constructors=cases,identity_null_clear_and_Phantom_get_verified=True,
        referent_fields_host_written=False,negative_receiver_cases=negative,private_native_type_preconditions_checked=True,
        foreign_comparison_and_collected_receiver_rejected=True,pending_contexts_preserved=True,
        concurrent_OS_threads=8,OS_thread_ids=sorted(tids),concurrent_trials=16,concurrent_native_calls=2048,
        linearization_proof=S.artifact(history_file),normal_root_spans=spans,
        quiescent_GC_proof=S.artifact(gc_file),
        quiescent_collections=4,collection_freed_counts=[first,second,third,fourth],
        live_inherited_referent_preserved=True,independent_strong_target_preserved_after_clear=True,
        cleared_unrooted_target_reclaimed=True,heap_destroyed=True,JDK_oracle=comparison,
        automatic_weak_reference_discovery=False,weak_reference_GC_complete=False,
        registered_in_shared_runtime=True,formal_provider_executed=True,
        formal_provider=config['formal_provider'],cold_source_classes_before=cold_before,cold_source_classes_after=cold_after,
        scratch_source_supplement_used=False,native_development_stops_replaced=0,
        full_VM_startup=False,game_started=False)


def execute(args):
    helper=module('formal_reference_source_helper','formal-provider-selection.py')
    state_file=args.state.resolve();output=args.output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Use a fresh formal Reference execution directory')
    state,values,paths=helper.state_inputs(state_file)
    [formal]=[path for path in paths if S.read(path)['family']=='normal-reference-referent-v1']
    pack=S.read(formal);meta=S.read(S.checked(pack['reference_referent_metadata']))
    _,summary,classes=S.base(values['batch'],values['plan'])
    probe=probe_model(pack,meta,summary,classes)
    exports,optional=execution_exports(probe,meta)
    method_roots=[('bootstrap',row['owner'],row['name'],row['descriptor']) for row in probe['expected_original_Java']]
    methods=set();class_ids=set();admission=None
    if args.source_profile:
        supplied=S.read(args.source_profile)
        S.check(not set(pack['required_class_ids'])&set(supplied.get('admitted_classes',[])),
            'A source profile cannot manually supply the required Reference class descriptors')
    if args.follow_failure:
        prior=args.follow_failure.resolve();failure=S.read(prior)
        S.check(failure.get('diagnostic_only') and failure.get('fault') and failure['fault']['category'] in (1,5),
            'Follow-up admission requires an actually observed unselected original Java/class source boundary')
        previous=S.read(S.checked(failure['images']))
        S.check(previous['base']['batch_summary']==pack['base']['batch_summary'] and
            previous['provider_list']==S.artifact(values['providers']), 'Admission belongs to different formal source inputs')
        profile=previous['selection_request']
        A=module('formal_reference_observed_whole_class_admission','update-diagnostic-profile.py')
        admission=A.admit_target(summary,failure['fault'],profile['admitted_methods'],profile['admitted_classes'],S.digest(prior)['sha256'])
        methods.update(admission['admitted_methods']);class_ids.update(admission['admitted_classes'])
        S.check(not set(pack['required_class_ids'])&class_ids,'A missing required class must be fixed in the provider dependency path')
    output.mkdir(parents=True)
    if admission:S.write(output/'observed-source-admission.json',admission)
    S.write(output/'probe-request.json',dict(formal_provider=S.artifact(formal),metadata=S.artifact(S.checked(pack['reference_referent_metadata'])),
        source_Input=pack['base'],probe=probe,follow_failure=S.artifact(args.follow_failure) if args.follow_failure else None))
    images_file=helper.prepare(state_file,output/'source-selection',method_roots=method_roots,
        class_roots=probe['requested_class_roots'],admitted_methods=sorted(methods),admitted_classes=sorted(class_ids),
        source_profile=args.source_profile,exports=sorted(exports),optional_exports=sorted(optional),
        harness_sources=[Path(__file__),Path(T.__file__),Path(T.B.__file__)],workers=args.workers,code_mib=args.code_mib)
    images=S.read(images_file)
    required=selected_source_model(images,formal,pack,meta,probe)
    linked=set(S.read(S.checked(images['source_manifest']))['exports'])
    roots=[]
    for name,count in T.ROOTS:
        S.check((name in linked)==(count in linked),'Partially provided normal source root span')
        if name in linked:roots.append((name,count))
    S.check(T.ROOTS[0] in roots and T.ROOTS[1] in roots,'Normal static/failure and String literal roots must be real selected source spans')
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    config=dict(schema=1,scope='formal_Reference_original_Java_and_native_execution_inputs',
        images=S.artifact(images_file),image=images['image'],runtime=images['runtime'],
        formal_provider=S.artifact(formal),formal_provider_verification=S.artifact(formal.with_name('verification.json')),
        metadata=meta,execution_tool=S.artifact(Path(__file__)),execution_rule_reuse=verify_suite_reuse(),
        original_Java_fixture_methods=probe['original_Java_fixture_methods'],fixture_classes=probe['fixture_classes'],
        required_source_classes=required,reference_class=meta['owner'],phantom_class=meta['phantom_type'],
        root_spans=roots,oracle_home=str(Path(catalog['image']['path']).parents[1]),oracle_modules=catalog['image'],
        scratch_source_supplement_used=False,native_development_stops_replaced=0,
        original_Java_or_COFF_changed=False,manual_Java_class_state_write=False)
    S.write(output/'formal-reference-input.json',config)
    with (output/'execution.log').open('wb') as log:
        process=subprocess.run([sys.executable,Path(__file__),'--worker','--output',output],
            stdout=log,stderr=subprocess.STDOUT,check=False)
    if process.returncode:
        S.check(False,'Formal Reference execution failed; preserved execution.log/failure.json in '+str(output))
    result=S.read(output/'execution.json')
    S.check(result['verified'] and result['formal_provider_executed'] and not result['scratch_source_supplement_used'] and
        result['native_development_stops_replaced']==0 and result['heap_destroyed'], 'Formal Reference execution scope differs')
    return output/'execution.json'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'reference-referent/formal-executions'/uuid4().hex)
    parser.add_argument('--source-profile',type=Path)
    parser.add_argument('--follow-failure',type=Path)
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--code-mib',type=int,default=8)
    parser.add_argument('--worker',action='store_true')
    args=parser.parse_args()
    if args.worker:worker(args.output.resolve())
    else:
        S.check(args.state is not None,'Provide the current formal 26-provider source state')
        print(execute(args))
