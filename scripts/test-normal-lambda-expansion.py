"""Execute generated normal lambda objects over unchanged original Java COFF."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import importlib.util
import os
from pathlib import Path
import subprocess
from threading import Barrier,get_native_id


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('normal_lambda_execution_source',ROOT/'scripts/normal-lambda-source.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
S=C.S;A=C.module('verify-batch-assembly');L=C.module('canonical-link-response')
Q,U,P=c.c_uint64,c.c_uint32,c.c_void_p
Context=U*8
ROOT_SPANS=[('boom_probe_static_roots','boom_probe_static_root_count'),
    ('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),
    ('boom_java_class_roots','boom_java_class_root_count'),('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),
    ('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),('boom_provider_threads_roots','boom_provider_threads_root_count'),
    ('boom_lambda_failure_roots','boom_lambda_failure_root_count')]
JAVA=[('java/lang/String','<init>','([C)V'),('java/lang/String','toCharArray','()[C'),
    ('java/lang/Object','<init>','()V'),
    ('java/lang/Throwable','getMessage','()Ljava/lang/String;'),
    ('java/util/HashSet','<init>','()V'),('java/util/HashSet','add','(Ljava/lang/Object;)Z'),
    ('java/lang/module/ModuleDescriptor','newModule','(Ljava/lang/String;)Ljava/lang/module/ModuleDescriptor$Builder;'),
    ('java/lang/module/ModuleDescriptor$Builder','packages','(Ljava/util/Set;)Ljava/lang/module/ModuleDescriptor$Builder;'),
    ('java/lang/module/ModuleDescriptor$Builder','build','()Ljava/lang/module/ModuleDescriptor;'),
    ('java/lang/Object','getClass','()Ljava/lang/Class;'),('java/lang/Class','isHidden','()Z'),
    ('java/lang/Class','getName','()Ljava/lang/String;'),('java/lang/Class','getModule','()Ljava/lang/Module;')]


def proc(image,name,result,*arguments):
    value=getattr(image,name);value.restype,value.argtypes=result,arguments;return value


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


def build(expansion_file,overlay_file,selection,runtime,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh lambda execution output required')
    V=C.module('verify-normal-lambda-expansion');S.check(V.verify(expansion_file)==S.read(expansion_file.with_name('source-verification.json')),
        'Normal lambda source proof changed')
    m=S.read(expansion_file);overlay=S.read(overlay_file);adapter=S.read(expansion_file.with_name('adapter-assembly.json'))
    OV=C.module('verify-normal-lambda-overlay');S.check(OV.verify(overlay_file)==S.read(overlay_file.with_name('verification.json')),
        'Independent sparse source/actual COFF verification differs')
    S.check(overlay['expansion']==adapter['expansion']==S.artifact(expansion_file) and
        overlay['tool']==S.artifact(ROOT/'scripts/normal-lambda-overlay.py') and
        adapter['generator']==S.artifact(ROOT/'scripts/normal-lambda-assembly.py'),'Current sparse producer identity differs')
    for key in ('assembly','object'):S.checked(adapter[key])
    S.check(S.artifact(adapter['assembler']['path'])==adapter['assembler'],'Actual assembler changed')
    S.check(A.coff_symbols(S.checked(adapter['object']))==(set(adapter['exports']),set(adapter['imports'])),
        'Actual generated adapter COFF changed')
    source=overlay['source'];closure=S.read(S.checked(source['base_closure']));S.checked(source['historical_full_source_proof'])
    S.check(Path(source['base_closure']['path']).parent==selection and overlay['metadata_extension_emitted'],
        'Overlay belongs to another source selection')
    rsp=selection/'link.rsp';lines=rsp.read_text().splitlines()
    objects=[Path(l[1:-1]) for l in lines if l.startswith('"') and Path(l[1:-1]).suffix.lower()=='.obj']
    libraries=[Path(l[1:-1]) for l in lines if l.startswith('"') and Path(l[1:-1]).suffix.lower()=='.lib']
    exports={l.removeprefix('/EXPORT:') for l in lines if l.startswith('/EXPORT:')}
    L.verify(rsp,profile='diagnostic',output=selection/'diagnostic-image.dll',objects=objects,
        library_choices=L.diagnostic_libraries(runtime,winsock=True),exports=exports)
    original_inputs=[S.artifact(p) for p in objects+libraries];replacements={}
    for unit in overlay['units']:
        old=S.checked(unit['replaced_object']);new=S.checked(unit['object']);S.checked(unit['assembly'])
        S.check(objects.count(old)==1 and A.coff_symbols(new)==(set(unit['exports']),set(unit['imports'])),
            'Overlay replacement is missing, repeated, or changed')
        replacements[old]=new
    sources=C.Sources(Path(m['base']['batch']),Path(m['base']['plan']));fixtures=[]
    for owner,name,descriptor in JAVA:
        cls=sources.lookup('bootstrap',owner);member=C.source_member(sources,cls,name,descriptor)
        selected=(closure['selected_methods'].get(str(member['method'])) or closure['selected_native_methods'].get(str(member['method'])) or
            closure['selected_Class_core_natives'].get(str(member['method'])))
        S.check(selected and selected.get('class_id')==cls['id'],'Original lambda test method not selected: '+str((owner,name,descriptor)))
        fixtures.append(member);exports|={'boom_m'+str(member['method']),'boom_class'+str(cls['id']),'boom_layout'+str(cls['id'])}
    for g in m['generated']:
        cls=g['contract']['bootstrap_member']['class_id'];exports|={'boom_class'+str(cls)}
        exports.add('boom_m'+str(g['contract']['implementation_member']['method']))
    exports|=set(adapter['exports'])|{n for pair in ROOT_SPANS for n in pair}
    exports|={'boom_heap_ptr','boom_java_string_literals_bind_heap','boom_java_class_pool','boom_java_class_module_roots','boom_runtime_type_map'}
    linked=[replacements.get(p,p) for p in objects]+[S.checked(adapter['object'])]
    output.mkdir(parents=True);dll=output/'normal-lambda.dll';response=output/'link.rsp'
    response.write_text('\n'.join([*L.PREFIXES['diagnostic'],'/OUT:"'+str(dll)+'"']+
        ['"'+str(p)+'"' for p in linked+libraries]+['/EXPORT:'+n for n in sorted(exports)])+'\n')
    proof=L.verify(response,profile='diagnostic',output=dll,objects=linked,library_choices=[libraries],exports=exports)
    linker=Path(adapter['assembler']['path']).with_name('link.exe')
    with (output/'link.log').open('wb') as log:
        subprocess.run([linker,'@'+str(response)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    for record in original_inputs:S.check(record==S.artifact(record['path']),'Original Java/metadata/provider/SDK input changed')
    config=dict(schema=1,scope='isolated_generic_static_reference_lambda_over_historical_normal_source',
        expansion=S.artifact(expansion_file),overlay=S.artifact(overlay_file),adapter=S.artifact(expansion_file.with_name('adapter-assembly.json')),
        source=source,original_link_response=S.artifact(rsp),original_link_inputs=original_inputs,
        linked_inputs=[S.artifact(p) for p in linked+libraries],runtime=S.artifact(runtime),image=S.artifact(dll),link_response=S.artifact(response),
        link_proof=proof,fixture_methods=fixtures,execution_tool=S.artifact(Path(__file__)),
        expected_error_types={name:sources.lookup('bootstrap',name)['id'] for name in ('java/lang/IllegalArgumentException','java/lang/NullPointerException')},
        oracle_home=str(Path(sources.catalog['image']['path']).parents[1]),oracle_modules=sources.catalog['image'],
        original_Java_Code_and_COFF_preserved=True,source_function_stop_replacements=0,
        original_indy_diagnostic_removed=len(m['generated']),shared_batch_modified=False,production_batch_verification=False,
        executed=False,game_started=False)
    path=output/'images.json';S.write(path,config);return path


def run(images_file):
    config=S.read(images_file);S.check(config['execution_tool']==S.artifact(Path(__file__)),'Lambda execution tool changed')
    for key in ('expansion','overlay','adapter','image','runtime','link_response'):S.checked(config[key])
    for record in config['original_link_inputs']+config['linked_inputs']:
        S.check(S.artifact(record['path'])==record,'Sealed source/SDK link input changed')
    manifest=S.read(S.checked(config['expansion']));[g]=manifest['generated'];plan=g['contract']
    S.check(not plan['captures'] and plan['sam_descriptor']=='(Ljava/lang/Object;)V',
        'This fixture exercises one generic noncapturing Consumer plan, not all supported source forms')
    runtime=S.checked(config['runtime'])
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(256<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Lambda heap bind failed')
    methods={(m['owner'],m['name'],m['descriptor']):m for m in config['fixture_methods']}
    classes={m['owner']:m['class_id'] for m in config['fixture_methods']}
    allocate=proc(rt,'boom_object_new',P,P,P,P);arrays=proc(rt,'boom_array_new',P,P,c.c_int,U,P)
    def call(ident,context,args):return proc(image,'boom_m'+str(ident),Q,P,P)(context,(Q*max(len(args),1))(*args))
    def source(owner,name,descriptor,args):
        context=Context();value=call(methods[owner,name,descriptor]['method'],context,args)
        if context[0] or context[3]:
            failure=dict(owner=owner,name=name,descriptor=descriptor,context=list(context),source_method=methods[owner,name,descriptor])
            path=images_file.parent/'first-source-failure.json'
            if not path.exists():S.write(path,failure)
            raise ValueError('Original Java execution stopped: '+repr(failure))
        return value
    def ensure(owner):
        context=Context();proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(classes[owner])),context)
        S.check(not context[0],'Original class initializer stopped: '+repr((owner,list(context))))
    def new(owner):
        context=Context();value=allocate(heap,addr(image,'boom_layout'+str(classes[owner])),context)
        S.check(value and not context[0],'Normal lambda fixture allocation failed');return value
    def string(value):
        raw=value.encode('utf-16-le','surrogatepass');ctx=Context();chars=arrays(heap,len(raw)//2,5,ctx)
        S.check(chars and not ctx[0],'char[] allocation failed');c.memmove(chars,raw,len(raw))
        value=new('java/lang/String');source('java/lang/String','<init>','([C)V',[value,chars]);return value
    def text(value):
        chars=source('java/lang/String','toCharArray','()[C',[value])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    ensure('java/lang/String');strings=[string('java.lang') for _ in range(8)]
    cls=addr(image,'boom_class'+str(g['class_id']));bsm=addr(image,'boom_class'+str(plan['bootstrap_member']['class_id']))
    S.check(U.from_address(cls+8).value==U.from_address(bsm+8).value==0,'Generated/bootstrap class was not cold')
    methods_new={m['name']:m['id'] for m in g['methods']};barrier=Barrier(8)
    def worker(index):
        barrier.wait();values=[]
        for _ in range(16):
            ctx=Context();obj=call(methods_new['$capture'],ctx,[])
            S.check(obj and not ctx[0] and not ctx[3],'Generated factory stopped: '+repr(list(ctx)))
            ctx=Context();result=call(methods_new[plan['sam_name']],ctx,[obj,strings[index]])
            if ctx[0] or ctx[3]:
                return dict(OS_thread=get_native_id(),failed_context=list(ctx),factory_object=obj,instances=values)
            S.check(not result,'Void SAM leaked the original static String return');values.append(obj)
        return dict(OS_thread=get_native_id(),instances=values)
    with ThreadPoolExecutor(max_workers=8) as executor:workers=list(executor.map(worker,range(8)))
    failures=[w for w in workers if 'failed_context' in w]
    if failures:
        closure=S.read(S.checked(config['source']['base_closure']));failed=[]
        for row in closure['selected_classes']:
            pointer=addr(image,'boom_class'+str(row['class_id']))
            if U.from_address(pointer+8).value==3:
                failed.append(dict(class_id=row['class_id'],name=row['name'],retained_context=list((U*4).from_address(pointer+32))))
        S.write(images_file.parent/'first-SAM-failure.json',dict(workers=failures,failed_original_classes=failed,plan=plan))
        raise ValueError('Generated SAM stopped: '+repr(failures))
    instances=[o for w in workers for o in w['instances']]
    S.check(len({w['OS_thread'] for w in workers})==8 and len(set(instances))==128 and U.from_address(cls+8).value==U.from_address(bsm+8).value==2,
        'Cold lambda initialization, fresh allocation, or 8 OS thread execution failed')
    sample=instances[0];context=Context();actual=proc(rt,'boom_runtime_type',P,P,P,P)(sample,addr(image,'boom_runtime_type_map'),context)
    S.check(actual==addr(image,'boom_t'+str(g['type_id'])) and not context[0],'Synthetic instance is missing from the normal runtime map')
    mirror=source('java/lang/Object','getClass','()Ljava/lang/Class;',[sample])
    S.check(mirror and source('java/lang/Class','isHidden','()Z',[mirror])==1 and
        text(source('java/lang/Class','getName','()Ljava/lang/String;',[mirror]))==g['runtime_class_name'],
        'Generated normal Class mirror/hidden/name identity differs')
    pool=addr(image,'boom_java_class_pool');record=P.from_address(pool+24).value+48*g['type_id']
    S.check(U.from_address(record+16).value==g['class_mirror']['loader'] and U.from_address(record+20).value==g['class_mirror']['module'],
        'Generated Class loader/module record did not inherit the original source host')
    context=Context();underlying=call(plan['implementation_member']['method'],context,[strings[0]])
    context_sam=Context();discarded=call(methods_new[plan['sam_name']],context_sam,[sample,strings[0]])
    S.check(underlying==strings[0] and discarded==0 and not context[0] and not context_sam[0],
        'Void adaptation did not discard the actual original reference result')
    wrong=new('java/lang/Object');source('java/lang/Object','<init>','()V',[wrong]);wrong_context=Context()
    S.check(call(methods_new[plan['sam_name']],wrong_context,[sample,wrong])==0 and wrong_context[0]==12 and
        wrong_context[1]==2 and wrong_context[2]==methods_new[plan['sam_name']] and not wrong_context[3],
        'Object-to-String cast did not report the original checkcast Context32 fault at the generated source PC')
    null_context=Context();S.check(call(methods_new[plan['sam_name']],null_context,[sample,0])==0 and
        null_context[0]==16 and not null_context[3],'Null argument did not reach the original implementation typed exception boundary')
    error=P.from_address(c.addressof(null_context)+16).value;error_context=Context()
    error_row=proc(rt,'boom_runtime_row',P,P,P,P)(error,addr(image,'boom_runtime_type_map'),error_context)
    S.check(error_row and not error_context[0] and U.from_address(error_row+16).value==config['expected_error_types']['java/lang/IllegalArgumentException'],
        'The original Checks null argument result is not IllegalArgumentException')
    null_receiver=Context();S.check(call(methods_new[plan['sam_name']],null_receiver,[0,strings[0]])==0 and
        null_receiver[0]==4 and not null_receiver[3],'Null functional receiver did not preserve the normal NPE boundary')
    pending=[]
    for name,method in methods_new.items():
        context=Context(77,91,0x12345678,0,1,2,3,4);before=bytes(context)
        S.check(call(method,context,[1,2,3])==0 and bytes(context)==before,'Generated method changed an existing pending Context32')
        pending.append(name)
    ensure('java/util/HashSet');ensure('java/lang/module/ModuleDescriptor')
    def set_of(values):
        result=new('java/util/HashSet');source('java/util/HashSet','<init>','()V',[result])
        for value in values:source('java/util/HashSet','add','(Ljava/lang/Object;)Z',[result,value])
        return result
    builder=source('java/lang/module/ModuleDescriptor','newModule','(Ljava/lang/String;)Ljava/lang/module/ModuleDescriptor$Builder;',[string('lambda.witness')])
    package_set=set_of([string('lambda.valid'),string('java.lang')])
    result=source('java/lang/module/ModuleDescriptor$Builder','packages','(Ljava/util/Set;)Ljava/lang/module/ModuleDescriptor$Builder;',[builder,package_set])
    S.check(result==builder,'Original strict Builder packages did not return the same receiver')
    built=source('java/lang/module/ModuleDescriptor$Builder','build','()Ljava/lang/module/ModuleDescriptor;',[builder])
    S.check(built,'Original strict Builder could not build the descriptor after indy')
    # Store the lambda through original HashSet.add. Its normal object graph
    # keeps the generated receiver alive without a bespoke lambda root bank.
    holding_set=set_of([sample]);collections=[]
    for turn in range(2):
        roots=[];spans=[]
        for symbol,count_symbol in ROOT_SPANS:
            count=Q.from_address(addr(image,count_symbol)).value;S.check(count<=2097152,'Invalid normal GC span count')
            cells=(Q*count).from_address(addr(image,symbol));roots += [v for v in cells if v]
            spans.append(dict(symbol=symbol,count=count,non_null=sum(bool(v) for v in cells),sha256=C.hashlib.sha256(bytes(cells)).hexdigest()))
        if turn==0:roots.append(holding_set)
        roots=list(dict.fromkeys(roots));freed=proc(rt,'boom_heap_collect',Q,P,P,U)(heap,(Q*len(roots))(*roots),len(roots))
        S.check(freed!=0xffffffffffffffff,'Quiescent lambda GC failed')
        S.check(bool(proc(rt,'boom_heap_contains',U,P,P)(heap,sample))==(turn==0),
            'Normal HashSet GC edge failed to retain/release generated instance')
        S.check(proc(rt,'boom_heap_contains',U,P,P)(heap,mirror),'Generated Class mirror lost its normal JCLS root')
        for span in spans:S.check(C.hashlib.sha256(c.string_at(addr(image,span['symbol']),span['count']*8)).hexdigest()==span['sha256'],
            'GC modified a normal static/Class/failure root bank')
        collections.append(dict(freed_objects=freed,root_spans=spans,additional_test_handles=['original HashSet'] if turn==0 else [],
            generated_receiver_retained=turn==0))
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Lambda heap destruction failed')
    return dict(schema=1,verified=True,scope=config['scope'],images=S.artifact(images_file),
        generated_rule=C.RULE,generated_origin_original_input=False,original_bytecode_and_COFF_unchanged=True,
        strict_source_witness=dict(method=plan['source_instruction']['method'],pc=plan['source_instruction']['pc'],
            factory_binding=plan['binding_label'],original_strict_packages_returned_same_builder=True,descriptor_built=True),
        cold_factory_8_OS_threads=True,workers=[dict(OS_thread=w['OS_thread'],factory_calls=len(w['instances']),SAM_calls=len(w['instances'])) for w in workers],
        distinct_fresh_instances=len(set(instances)),normal_runtime_type_Class_hidden_name=True,
        hidden_runtime_name=g['runtime_class_name'],module_loader_records_inherited_from_original_host=True,
        named_Module_oop_publication_executed=False,
        semantic_negative_cases=dict(wrong_class_context=list(wrong_context),null_receiver_context=list(null_receiver),
            null_argument_context=list(null_context),null_argument_original_exception='java.lang.IllegalArgumentException',
            original_pending_Context_bytes_preserved=pending,void_discarded_original_nonnull_reference=True,
            implicit_exception_representation='normal_raw_Context32_without_EXVM_materialization'),
        Class_root_retained=True,explicit_quiescent_GC=collections,heap_destroyed=True,automatic_GC=False,
        original_Functional_dispatch_extended=True,production_batch_verification=False,all_LambdaMetafactory_forms=False,game_started=False)


def recheck(images_file,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated recheck output required')
    config=S.read(images_file)
    for key in ('expansion','overlay','adapter','image','runtime','link_response'):S.checked(config[key])
    for record in config['original_link_inputs']+config['linked_inputs']:
        S.check(S.artifact(record['path'])==record,'Sealed source/SDK link input changed')
    config['producer_execution_tool']=config['execution_tool'];config['execution_tool']=S.artifact(Path(__file__))
    config['original_images']=S.artifact(images_file);config['relinked']=False
    output.mkdir(parents=True);path=output/'images.json';S.write(path,config);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--expansion',type=Path);parser.add_argument('--overlay',type=Path)
    parser.add_argument('--selection',type=Path);parser.add_argument('--runtime',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--images',type=Path);parser.add_argument('--recheck-from',type=Path);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    images=(recheck(args.recheck_from.resolve(),args.output) if args.recheck_from else args.images.resolve() if args.images else
        build(args.expansion.resolve(),args.overlay.resolve(),args.selection.resolve(),args.runtime.resolve(),args.output))
    if args.execute:S.write(images.parent/'execution.json',run(images))
    print(images)
