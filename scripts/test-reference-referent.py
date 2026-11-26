"""Execute four source Reference natives, original Java delegation and quiescent GC."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from threading import Barrier,Event,get_native_id
from time import perf_counter_ns
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reference_operations_candidate',ROOT/'scripts/reference-referent-candidate.py')
B=importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
S=B.S
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8
ROOTS=[('boom_probe_static_roots','boom_probe_static_root_count'),
    ('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_class_roots','boom_java_class_root_count'),
    ('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),
    ('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),
    ('boom_provider_threads_roots','boom_provider_threads_root_count')]


def proc(image,name,result,*arguments):
    value=getattr(image,name)
    value.restype,value.argtypes=result,arguments
    return value


def addr(image,name):
    return c.addressof(c.c_byte.in_dll(image,name))


def java_fixtures(summary,classes):
    I=B.module('verify-translation-ir')
    wanted=[('java/lang/Object','<init>','()V'),('java/lang/ref/WeakReference','<init>','(Ljava/lang/Object;)V'),
        ('java/lang/ref/SoftReference','<init>','(Ljava/lang/Object;)V'),
        ('java/lang/ref/SoftReference','get','()Ljava/lang/Object;'),
        ('java/lang/ref/PhantomReference','<init>','(Ljava/lang/Object;Ljava/lang/ref/ReferenceQueue;)V')]
    methods=[];owners={}
    for name,method,descriptor in wanted:
        [owner]=[row for row in classes if row['name']==name and row['origin']['loader']=='bootstrap']
        raw=I.Source(S.original_class(summary,owner))
        [row]=[dict(method=ident,class_id=owner['id'],class_sha256=owner['origin']['sha256'],owner=name,
            name=method,descriptor=descriptor,code_sha256=hashlib.sha256(raw.code(m)['bytes']).hexdigest())
            for ident,m in zip(owner['method_ids'],raw.methods) if (m['name'],m['descriptor'])==(method,descriptor)]
        methods.append(row);owners[name]=owner['id']
    return methods,owners


def build(candidate_file,baseline,execution,native_manifest,output):
    output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project reference execution directory required')
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Independent Reference source proof differs')
    candidate=S.read(candidate_file);meta=candidate['metadata']
    closure=S.read(baseline/'closure.json');proof=S.read(baseline/'selection-verification.json')
    observed=S.read(execution)
    native=S.read(native_manifest)
    native_proof=native_manifest.with_name('verification.json')
    binding=S.read(native_proof)
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(baseline/'closure.json')['sha256'] and
        binding['verified'] and binding['source_manifest_sha256']==S.digest(native_manifest)['sha256'] and
        observed['source_verification_sha256']==S.digest(native_proof)['sha256'] and
        Path(native['baseline_directory'])==baseline and
        native['accepted_source_verification_sha256']==S.digest(baseline/'selection-verification.json')['sha256'] and
        observed['cleanup_flags']==7 and observed['worker_failure_state']==0 and
        Path(closure['batch'])==Path(meta['base']['batch']) and Path(closure['plan'])==Path(meta['base']['plan']) and
        closure['source_batch_summary_sha256']==meta['base']['batch_summary']['digest']['sha256'],
        'Same-batch verified original source and actual cleaned-up native process required')
    _,summary,classes=S.base(Path(closure['batch']),Path(closure['plan']))
    fixtures,owners=java_fixtures(summary,classes)
    for method in meta['source']['ordinary_Java']+fixtures:
        row=closure['selected_methods'].get(str(method['method']))
        S.check(row and row['class_id']==method['class_id'] and row['source_sha256']==method['class_sha256'] and
            row['code_sha256']==method['code_sha256'],'Original reference Java entry is not selected: '+str(method))
    diagnostic=S.read(baseline/'diagnostic.json')
    native_rows=[]
    for method in meta['source']['methods']:
        rows=[row for row in diagnostic['rows'] if row['symbol']=='boom_m'+str(method['method'])]
        S.check(len(rows)==1 and rows[0]['category']==2 and rows[0]['source_sha256']==method['class_sha256'],
            'Exact original Reference native stop is missing')
        native_rows+=rows
    [unit]=[unit for unit in proof['verified_assembly_objects']['units'] if Path(unit['assembly']['path']).name=='diagnostic-stops.asm']
    original=S.checked(unit['assembly']).read_text();old_obj=S.checked(unit['object'])
    remaining=original;removed=[]
    for row in native_rows:
        name=row['symbol']
        text=(f'PUBLIC {name}\n{name} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
            f' lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{name} ENDP\n')
        S.check(remaining.count(text)==1,'Source Reference native diagnostic body changed')
        remaining=remaining.replace(text,'',1)
        removed.append(dict(symbol=name,sha256=hashlib.sha256(text.encode()).hexdigest()))
    state=S.read(S.checked(meta['input_state']))
    runtime=Path(state['runtime'])/'boom-runtime.dll'
    runtime_meta=S.read(runtime.with_name('runtime.json'))
    S.check(S.digest(runtime)['sha256']==runtime_meta['sha256'] and
        all(runtime_meta['sources'].get(name)==digest for name,digest in meta['runtime_kernel_sha256'].items()),
        'Original reference fixture runtime source differs')
    lines=(baseline/'link.rsp').read_text().splitlines()
    [old_line]=[line for line in lines if line.startswith('"') and Path(line.strip('"')).resolve()==old_obj]
    inputs=[S.artifact(Path(line.strip('"'))) for line in lines if line.startswith('"')]
    assembler=Path(candidate['assembler']['path']);linker=assembler.with_name('link.exe')
    output.mkdir(parents=True)
    asm,obj=output/'remaining-stops.asm',output/'remaining-stops.obj'
    asm.write_text(remaining)
    with (output/'stops-assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    exported={line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')}
    exported|=set(candidate['exports'])|{f"boom_m{row['method']}" for row in meta['source']['ordinary_Java']+fixtures}
    exported|={f'boom_layout{ident}' for ident in owners.values()}
    exported|={f'boom_class{ident}' for ident in owners.values()}
    exported|={f"boom_layout{meta['source']['final_reference_type']}"}
    exported|={'boom_heap_ptr','boom_java_string_literals_bind_heap','boom_runtime_type_map','boom_diagnostic_pool'}
    exported|={name for pair in ROOTS for name in pair}
    dll=output/'reference-operations.dll'
    modified=[('"'+str(obj)+'"' if line==old_line else line) for line in lines if not line.startswith(('/OUT:','/EXPORT:'))]
    modified+=['/OUT:"'+str(dll)+'"','"'+str(S.checked(candidate['object']))+'"']
    modified+=['/EXPORT:'+name for name in sorted(exported)]
    rsp=output/'link.rsp';rsp.write_text('\n'.join(modified)+'\n')
    with (output/'link.log').open('wb') as log:
        subprocess.run([linker,'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    for record in inputs:
        S.check(S.artifact(record['path'])==record,'Original image input changed during isolated reference relink')
    E=B.module('diagnostic-closure')
    S.check(E.pe_exports(dll)==exported,'Reference observation image export set differs')
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    image=dict(schema=2,scope='four_original_reference_natives_over_verified_formal23_source',
        candidate=S.artifact(candidate_file),source_proof=S.artifact(candidate_file.with_name('verification.json')),
        baseline_manifest=S.artifact(baseline/'closure.json'),baseline_verification=S.artifact(baseline/'selection-verification.json'),
        baseline_execution=S.artifact(execution),original_link_response=S.artifact(baseline/'link.rsp'),
        native_process_manifest=S.artifact(native_manifest),native_process_verification=S.artifact(native_proof),
        link_inputs=inputs,removed_native_stops=removed,remaining_diagnostic_assembly=S.artifact(asm),
        remaining_diagnostic_object=S.artifact(obj),image=S.artifact(dll),runtime=S.artifact(runtime),
        link_response=S.artifact(rsp),linker=S.artifact(linker),execution_tool=S.artifact(Path(__file__)),
        original_Java_fixture_methods=fixtures,fixture_classes=owners,root_spans=ROOTS,
        oracle_home=str(Path(catalog['image']['path']).parents[1]),oracle_modules=catalog['image'],
        Java_ASM_or_COFF_modified=False,original_virtual_tables_modified=False,Java_codegen_rerun=False,
        source_selection_reverified_in_this_run=False,registered_in_shared_runtime=False,game_started=False)
    S.write(output/'images.json',image)
    return output/'images.json'


def linearization(history,target):
    clears=[row for row in history if row['kind']=='clear']
    before=[];after=[]
    for row in history:
        kind,value=row['kind'],row['value']
        if kind=='clear':
            S.check(value==0,'Void original clear returned an object')
        elif kind=='get':
            S.check(value in (0,target),'Concurrent get returned a non-referent')
            (before if value==target else after).append(row)
        elif kind=='target':
            S.check(value in (0,1),'Concurrent identity returned a non-boolean')
            (before if value else after).append(row)
        elif kind=='null':
            S.check(value in (0,1),'Concurrent null identity returned a non-boolean')
            (after if value else before).append(row)
    low=max([row['start'] for row in before]+[min(row['start'] for row in clears)])
    high=min([row['end'] for row in after]+[min(row['end'] for row in clears)])
    possible=[max(low,row['start']) for row in clears if max(low,row['start'])<=min(high,row['end'])]
    S.check(possible,'Concurrent read/identity/clear history has no valid atomic clear linearization')
    return dict(first_clear_ns=min(possible),lower_bound_ns=low,upper_bound_ns=high,
        operations=len(history),before_observations=len(before),after_observations=len(after),clear_calls=len(clears))


def oracle(home,output):
    source=output/'ReferenceOperationsOracle.java'
    source.write_text('''import java.lang.ref.*;
class ReferenceOperationsOracle {
 public static void main(String[] args) {
  Object value=new Object(),other=new Object();
  java.util.List<Reference<Object>> refs=java.util.List.of(new WeakReference<>(value),new SoftReference<>(value),new PhantomReference<>(value,null));
  for (int i=0;i<refs.size();i++) {
   Reference<Object> ref=refs.get(i);
   if(ref.get()!=(i==2?null:value)||!ref.refersTo(value)||ref.refersTo(other)||ref.refersTo(null)) throw new AssertionError();
   ref.clear();ref.clear();
   if(ref.get()!=null||ref.refersTo(value)||!ref.refersTo(null)) throw new AssertionError();
   System.out.println("identity/null/clear:"+i);
  }
  Reference<Object> empty=new PhantomReference<>(null,null);
  if(!empty.refersTo(null)||empty.refersTo(value)) throw new AssertionError();
  Reference.reachabilityFence(value);
 }
}
''',encoding='ascii')
    process=subprocess.run([home/'bin/java.exe',source],check=True,capture_output=True,timeout=45)
    S.check(process.stdout.decode('ascii').splitlines()==['identity/null/clear:0','identity/null/clear:1','identity/null/clear:2'],
        'Locked JDK original reference semantics differ')
    (output/'oracle.stdout').write_bytes(process.stdout)
    return dict(java=S.artifact(home/'bin/java.exe'),source=S.artifact(source),stdout=S.artifact(output/'oracle.stdout'))


def run(images_file):
    config=S.read(images_file)
    S.check(S.artifact(Path(__file__))==config['execution_tool'],'Reference execution tool changed')
    candidate=S.read(S.checked(config['candidate']));meta=candidate['metadata']['source']
    for record in (config['source_proof'],config['baseline_manifest'],config['baseline_verification'],
            config['baseline_execution'],config['remaining_diagnostic_assembly'],config['remaining_diagnostic_object']):
        S.checked(record)
    runtime=S.checked(config['runtime'])
    with os.add_dll_directory(str(runtime.parent)):
        rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
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
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Reference operations retained a monitor/heap ownership lease')
    oracle_dir=images_file.parent/('oracle-'+uuid4().hex);oracle_dir.mkdir()
    S.check(S.digest(config['oracle_modules']['path'])['sha256']==config['oracle_modules']['digest']['sha256'],
        'Locked oracle JDK input changed')
    comparison=oracle(Path(config['oracle_home']),oracle_dir)
    return dict(schema=2,verified=True,scope='four_original_reference_natives_Java_constructors_delegation_atomic_clear_quiescent_GC',
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
        registered_in_shared_runtime=False,full_VM_startup=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--baseline-execution',type=Path)
    parser.add_argument('--baseline-native-manifest',type=Path)
    parser.add_argument('--images',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'reference-referent/executions'/uuid4().hex)
    args=parser.parse_args()
    if args.images:
        images=args.images.resolve()
    else:
        S.check(args.candidate and args.baseline and args.baseline_execution and args.baseline_native_manifest,
            'Provide source candidate, verified baseline, actual process execution and bound native manifest')
        images=build(args.candidate.resolve(),args.baseline.resolve(),args.baseline_execution.resolve(),
            args.baseline_native_manifest.resolve(),args.output)
    result=images.parent/('execution-'+uuid4().hex+'.json')
    S.write(result,run(images));print(result)
