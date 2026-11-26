"""Execute formal builtin NativeLibraries with original constructors and VM bindings.

The development Python host supplies primitive arguments and observes results.
All Java, native, thread attachment, image pin and Winsock work runs in our ASM.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier,get_native_id
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


F=module('formal_library_source_selection','formal-provider-selection.py');S=F.S
M=module('formal_library_original_VM_bindings','vm-entry-source.py')
L=module('formal_library_canonical_link','canonical-link-response.py')
C=module('formal_library_model','native-library-source.py')
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8
JAVA=[(name,'<init>',descriptor) for name,descriptor in M.CTOR_SPECS]+[
    ('java/util/Properties','<init>','()V'),
    ('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;'),
    ('java/lang/System','setProperties','(Ljava/util/Properties;)V'),
    ('java/lang/String','<init>','([C)V'),('java/lang/String','toCharArray','()[C'),
    ('java/lang/Object','<init>','()V'),('java/lang/Object','getClass','()Ljava/lang/Class;'),
    ('java/lang/Thread','<init>','(Ljava/lang/String;)V'),
    (C.IMPL,'<init>','(Ljava/lang/Class;Ljava/lang/String;Z)V'),
    ('java/lang/Throwable','getMessage','()Ljava/lang/String;')]
ROOT_SPANS=[('boom_probe_static_roots','boom_probe_static_root_count'),
    ('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),
    ('boom_java_class_roots','boom_java_class_root_count'),
    ('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),
    ('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),
    ('boom_provider_threads_roots','boom_provider_threads_root_count')]


def proc(image,name,result,*arguments):
    value=getattr(image,name);value.restype,value.argtypes=result,arguments;return value


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


def source_model(state_file):
    state,values,paths=F.state_inputs(state_file)
    _,summary,classes=S.base(values['batch'],values['plan'])
    [pack_file]=[path for path in paths if S.read(path)['family']=='normal-native-libraries-v1']
    pack=S.read(pack_file);meta=S.read(S.checked(pack['native_library_metadata']))
    S.check(pack['tool_sources']==S.tools_identity() and C.index(summary,classes,S)==meta,
        'Formal library pack source metadata differs from current original classes')
    I=S.module('formal_library_probe_classfiles','verify-translation-ir.py')
    wanted=set(JAVA)|{(m['owner'],m['name'],m['descriptor']) for m in meta['original_java']+meta['methods']}
    # Current-thread observations must use the actual selected original native.
    wanted.add(('java/lang/Thread','currentThread','()Ljava/lang/Thread;'))
    names={row['name']:row for row in classes if row['origin']['loader']=='bootstrap'}
    members=[]
    for owner in sorted({row[0] for row in wanted}):
        cls=names[owner];raw=I.Source(S.original_class(summary,cls))
        S.check(raw.name==owner and len(raw.methods)==len(cls['method_ids']),'Original probe inventory differs')
        for ident,method in zip(cls['method_ids'],raw.methods):
            if (owner,method['name'],method['descriptor']) not in wanted:continue
            code=raw.code(method)
            members.append(dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],owner=owner,
                name=method['name'],descriptor=method['descriptor'],access=method['access'],
                code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None))
    S.check({(m['owner'],m['name'],m['descriptor']) for m in members}==wanted,'Missing original Java/native probe member')
    class_names={m['owner'] for m in members}|{'java/lang/Class','java/lang/reflect/Method','jdk/internal/misc/VM'}
    layouts={}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['name'] in class_names and row['class_id']==names[row['name']]['id']:
                S.check(row['diagnostic'] is None and row['source_sha256']==names[row['name']]['origin']['sha256'],
                    'Original probe object layout differs')
                layouts[row['name']]=row['candidate']
    S.check(set(layouts)==class_names,'Missing normal source object layouts')
    return dict(schema=1,input_state=S.artifact(state_file),formal_provider=S.artifact(pack_file),
        formal_verification=S.artifact(pack_file.with_name('verification.json')),metadata=meta,
        members=members,classes={name:names[name]['id'] for name in class_names},layouts=layouts,
        primary_provider_classes=[names[name]['id'] for name in (C.OWNER,C.IMPL,'jdk/internal/loader/NativeLibrary')],
        class_roots=[('bootstrap',name) for name in ('java/lang/String','java/lang/System','java/lang/Class',
            'java/lang/reflect/Method','java/lang/Thread','java/lang/ThreadGroup','java/security/AccessControlContext','jdk/internal/misc/VM')])


def observation_exports(model):
    exports={f"boom_m{m['method']}" for m in model['members']}
    exports|={f'boom_layout{ident}' for ident in model['classes'].values()}
    exports|={f'boom_class{ident}' for ident in model['classes'].values()}
    exports|={'boom_heap_ptr','boom_provider_thread_registry','boom_probe_static_roots','boom_probe_static_root_count',
        'boom_java_string_literals_bind_heap','boom_release_trace_pool','boom_diagnostic_pool'}
    optional={name for pair in ROOT_SPANS for name in pair}
    return exports,optional-exports


def prepare(state_file,output,source_profile=None):
    model=source_model(state_file);S.write(output/'probe-model.json',model)
    exports,optional=observation_exports(model)
    roots=[('bootstrap',m['owner'],m['name'],m['descriptor']) for m in model['members']]
    images=F.prepare(state_file,output/'source-selection',method_roots=roots,class_roots=model['class_roots'],
        source_profile=source_profile,exports=sorted(exports),optional_exports=sorted(optional),
        # The source request/model is immutable; each later execution harness is
        # separately pinned by its fresh extra-object/image manifest.
        harness_sources=[output/'probe-model.json',ROOT/'scripts/vm-entry-source.py',ROOT/'native/entry/vm_process.asm.inc'])
    return dict(kind='focused_images',images=S.artifact(images),selection=str(images.parent),model=model)


def source_bundle(state_file,selection):
    return dict(kind='existing_verified_source_selection',selection=str(Path(selection).resolve()),model=source_model(state_file))


def verify_source(bundle):
    selection=Path(bundle['selection']).resolve();model=bundle['model']
    state,values,paths=F.state_inputs(F.checked(model['input_state']))
    S.check(selection.is_relative_to(S.ART),'Formal source selection escaped project outputs')
    if bundle['kind']=='focused_images':
        images=F.checked(bundle['images']);proof=F.verify(images)
        S.check(Path(S.read(images)['source_selection_directory'])==selection,'Focused source directory differs')
    else:
        S.check(bundle['kind']=='existing_verified_source_selection','Unknown original source selection kind')
        V=module('formal_library_existing_source_verifier','verify-diagnostic-closure.py');proof=V.verify(selection)
        S.check(proof==S.read(selection/'selection-verification.json'),'Existing source proof differs from current full verification')
    closure=S.read(selection/'closure.json')
    references=closure['runtime_provider_packs']
    S.check([S.checked(row['manifest']) for row in references]==paths and len(references)==26,
        'Source selection does not have the exact current 26-provider inputs')
    selected=closure['selected_runtime_provider_packs']
    [index]=[i for i in selected if S.checked(references[i]['manifest'])==F.checked(model['formal_provider'])]
    pack=S.read(model['formal_provider']['path']);meta=model['metadata']
    S.check(S.read(S.checked(pack['native_library_metadata']))==meta and pack['tool_sources']==S.tools_identity(),
        'Current formal NativeLibraries metadata changed')
    S.check(set(pack['required_class_ids'])<={r['class_id'] for r in closure['selected_classes']} and
        S.checked(pack['object']) in [Path(p) for p in closure['objects']] and
        all(str(m['method']) in closure['selected_runtime_provider_natives'] for m in pack['methods']),
        'Actual formal pack or its original required classes/natives were not selected')
    explicit={r['class_id'] for r in closure['requested_class_roots']}|set(closure['admitted_classes'])
    S.check(not explicit&set(model['primary_provider_classes']),
        'Primary NativeLibraries classes must come from ordinary source/provider selection')
    for method in model['members']:
        if method['code_sha256'] is None:continue
        row=closure['selected_methods'].get(str(method['method']))
        S.check(row and row['class_id']==method['class_id'] and row['code_sha256']==method['code_sha256'] and
            row['source_sha256']==method['class_sha256'],'Original Java constructor/API probe was not selected')
    S.check(proof.get('source_property_root_span',{}).get('cells')==109,
        'The original properties module/root span is absent')
    return closure,proof,values['runtime']


def build_extra(bundle,output,assembler=F.DEFAULT_ASSEMBLER):
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh extra-image directory required')
    closure,proof,runtime=verify_source(bundle);selection=Path(bundle['selection']);model=M.binding_model(closure,False)
    S.check(model['system_entry'] is None and not model.get('system_phase2') and model['child_constructor'] is None and
        not model.get('object_wait') and not model.get('reference_processing'),'Constructor-only VM binding model required')
    text,imports=M.assembly(model);output.mkdir(parents=True)
    asm=output/'constructor-vm-entry.asm';obj=asm.with_suffix('.obj');asm.write_text(text,encoding='utf-8')
    with (output/'assembler.log').open('wb') as log:
        result=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(asm)],stdout=log,stderr=log,timeout=120)
    S.check(result.returncode==0,'Constructor-only VM entry assembly failed')
    A=module('formal_library_extra_actual_coff','verify-batch-assembly.py')
    S.check(A.coff_symbols(obj,M.FOREIGN)==(M.EXPORTS,imports),'Generated constructor VM entry actual COFF differs')
    D=module('formal_library_original_source_objects','diagnostic-objects.py');sealed=D.verify(selection)
    original=[r['object']['path'] for r in sealed['units']]+closure['objects'];objects=[*original,str(obj)]
    libraries=L.diagnostic_libraries(runtime,winsock=True)[0]
    exports=set(closure['exports'])|M.EXPORTS|observation_exports(bundle['model'])[0]
    # A full-source selection may not have exposed optional observation symbols.
    present=set()
    for name in ('initialization-closure.asm','diagnostic-stops.asm'):
        import re
        present.update(re.findall(r'(?m)^PUBLIC (boom_\w+)\s*$',(selection/name).read_text(encoding='utf-8')))
    foreign=set().union(*(set(S.read(S.checked(r['manifest'])).get('allowed_foreign_imports',[])) for r in closure['runtime_provider_packs']))
    for path in closure['objects']:present.update(A.coff_symbols(path,foreign|{'WaitOnAddress','WakeByAddressAll'})[0])
    optional={name for pair in ROOT_SPANS for name in pair}&present;exports|=optional
    S.check(exports<=present|M.EXPORTS,'Extra image observation export is not an existing source PUBLIC')
    image=output/'native-library-formal.dll';rsp=output/'link.rsp'
    lines=[*L.PREFIXES['diagnostic'],'/OUT:"'+str(image)+'"']+['"'+str(p)+'"' for p in [*objects,*libraries]]
    lines+=['/EXPORT:'+name for name in sorted(exports)];rsp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    L.verify(rsp,profile='diagnostic',output=image,objects=objects,library_choices=[libraries],exports=exports)
    with (output/'link.log').open('wb') as log:
        result=subprocess.run([str(assembler.with_name('link.exe')),'@'+str(rsp)],stdout=log,stderr=log,timeout=240)
    S.check(result.returncode==0,'Formal extra-object image link failed')
    tokens=L.winsock_import_tokens(libraries[-1]);parsed=M.pe(image)
    S.check(sorted(parsed['imports'].get('ws2_32.dll',[]))==sorted(tokens.values()),'Actual image lost the five exact Winsock imports')
    S.check(module('formal_library_extra_exports','diagnostic-closure.py').pe_exports(image)==exports,'Extra image PE exports differ')
    inputs=[S.artifact(p) for p in [*objects,*libraries,runtime,runtime.with_name('runtime.json'),assembler,assembler.with_name('link.exe'),
        selection/'closure.json',selection/'diagnostic.json',selection/'selection-verification.json',selection/D.RECEIPT,
        ROOT/'scripts/vm-entry-source.py',ROOT/'native/entry/vm_process.asm.inc',ROOT/'scripts/canonical-link-response.py',Path(__file__),asm,rsp]]
    for record in inputs:F.checked(record)
    result=dict(schema=1,scope='formal_NativeLibraries_original_source_plus_generated_constructor_VM_entry_only',
        source_bundle=bundle,source_proof=S.artifact(selection/'selection-verification.json'),
        binding_model=model,assembly=S.artifact(asm),object=S.artifact(obj),image=S.artifact(image),runtime=S.artifact(runtime),
        source_objects=original,extra_objects=[S.artifact(obj)],link_response=S.artifact(rsp),exports=sorted(exports),
        imports=sorted(imports),inputs=inputs,optional_root_exports=sorted(optional),Winsock_API_imports=tokens,
        execution_tool=S.artifact(Path(__file__)),source_Java_or_COFF_modified=False,diagnostic_stops_replaced=False,
        host_Thread_or_class_init_fields_written=False,system_phase1_requested=False,process_entry_executed=False,
        original_source_independently_verified=True,extra_object_source_and_COFF_verified=True,
        full_NativeLibraries_Java_loadLibrary_chain=False,full_VM_startup=False,game_started=False)
    S.write(output/'extra-image.json',result);return output/'extra-image.json'


def verify_extra(path):
    record=S.read(path)
    S.check(record['execution_tool']==S.artifact(Path(__file__)) and all(F.checked(r) for r in record['inputs']),
        'Formal execution harness or immutable extra-image input changed')
    closure,proof,runtime=verify_source(record['source_bundle'])
    model=M.binding_model(closure,False);text,imports=M.assembly(model)
    S.check(model==record['binding_model'] and F.checked(record['assembly']).read_text(encoding='utf-8')==text,
        'Source-derived constructor binding model/source changed')
    A=module('formal_library_verify_extra_coff','verify-batch-assembly.py')
    S.check(A.coff_symbols(F.checked(record['object']),M.FOREIGN)==(M.EXPORTS,imports),
        'Constructor VM entry actual COFF definitions/imports changed')
    D=module('formal_library_verify_original_parts','diagnostic-objects.py');sealed=D.verify(Path(record['source_bundle']['selection']))
    original=[r['object']['path'] for r in sealed['units']]+closure['objects']
    S.check(record['source_objects']==original and record['extra_objects']==[record['object']],
        'Formal source objects were replaced or extra code was added')
    libraries=L.diagnostic_libraries(runtime,winsock=True)
    L.verify(F.checked(record['link_response']),profile='diagnostic',output=F.checked(record['image']),
        objects=[*original,record['object']['path']],library_choices=libraries,exports=record['exports'])
    selected=[r for r in record['inputs'] if Path(r['path']).name.lower()=='ws2_32.lib']
    S.check(len(selected)==1 and L.winsock_import_tokens(F.checked(selected[0]))==record['Winsock_API_imports'],
        'Selected SDK Winsock library or its exact import tokens changed')
    parsed=M.pe(F.checked(record['image']))
    S.check(sorted(parsed['imports'].get('ws2_32.dll',[]))==sorted(record['Winsock_API_imports'].values()),
        'Formal image changed the exact five native Winsock imports')
    return record


class SourceFailure(Exception):
    pass


def execute(extra_file):
    record=verify_extra(extra_file);output=Path(extra_file).parent;model=record['source_bundle']['model'];binding=record['binding_model']
    runtime=F.checked(record['runtime'])
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.CDLL(str(runtime)),c.CDLL(str(F.checked(record['image'])))
    classes=model['classes'];members={(m['owner'],m['name'],m['descriptor']):m['method'] for m in model['members']}
    def mid(owner,name,descriptor):return members[owner,name,descriptor]
    class_by_id={ident:name for name,ident in classes.items()}
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20);S.check(heap,'Normal source heap creation failed')
    S.check(proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Normal source literal/heap binding failed')
    diagnostic=S.read(Path(record['source_bundle']['selection'])/'diagnostic.json')
    def check_context(stage,context):
        if not context[0]:return
        pool=addr(image,'boom_diagnostic_pool');row_id=U.from_address(pool+32).value
        row=diagnostic['rows'][row_id-1] if U.from_address(pool+8).value==2 and 0<row_id<=len(diagnostic['rows']) else None
        failure=dict(stage=stage,context=list(context),row=row,extra_image=S.artifact(extra_file),
            original_source_changed=False,diagnostic_stops_replaced=False)
        path=output/'first-failure.json'
        if not path.exists():S.write(path,failure)
        raise SourceFailure('Original source call failed: '+str((stage,list(context),row['symbol'] if row else None)))
    def call(ident,arguments,context=None,check=True):
        context=Context() if context is None else context;args=(Q*max(1,len(arguments)))(*arguments)
        value=proc(image,'boom_m'+str(ident),Q,P,P)(context,args)
        if check:check_context('boom_m'+str(ident),context)
        return context,value
    def source(owner,name,descriptor,args):return call(mid(owner,name,descriptor),args)[1]
    def ensure(owner):
        context=Context();proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(classes[owner])),context)
        check_context('initialize '+owner,context)
    def new(owner):
        ensure(owner);context=Context();value=proc(rt,'boom_object_new',P,P,P,P)(heap,addr(image,'boom_layout'+str(classes[owner])),context)
        check_context('allocate '+owner,context);S.check(value,'Source object allocation returned null');return value
    def string(value):
        raw=value.encode('utf-16-le','surrogatepass');context=Context()
        chars=proc(rt,'boom_array_new',P,P,c.c_int,U,P)(heap,len(raw)//2,5,context);check_context('char[]',context)
        S.check(chars,'Normal char[] allocation failed')
        if raw:c.memmove(chars,raw,len(raw))
        value=new('java/lang/String');source('java/lang/String','<init>','([C)V',[value,chars]);return value
    def text(value):
        chars=source('java/lang/String','toCharArray','()[C',[value])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    def field(owner,name,descriptor):
        rows=[f for f in model['layouts'][owner]['fields'] if f['member']['owner']==classes[owner] and
            (f['member']['name'],f['member']['descriptor'])==(name,descriptor)]
        S.check(len(rows)==1,'Original normal source field not unique');return rows[0]['offset']
    def value(oop,owner,name,descriptor):
        offset=field(owner,name,descriptor);kind=Q if descriptor[0] in ('L','[','J') else U if descriptor=='I' else c.c_ubyte
        return kind.from_address(oop+offset).value
    root_start=addr(image,'boom_probe_static_roots');root_count=Q.from_address(addr(image,'boom_probe_static_root_count')).value
    required=[]
    for ident in model['primary_provider_classes']:
        descriptor=addr(image,'boom_class'+str(ident));failure=Q.from_address(descriptor+56).value
        S.check(U.from_address(descriptor+8).value==0 and root_start<=failure<root_start+root_count*8 and
            not (failure-root_start)%8 and Q.from_address(failure).value==0,'Required source class is not cold/normal-rooted')
        required.append(dict(class_id=ident,cold_state=0,failure_root_cell=(failure-root_start)//8))
    context=Context();main=proc(image,'boom_vm_bootstrap_main',P,P)(context);check_context('original primordial constructors',context)
    registry=P.from_address(addr(image,'boom_provider_thread_registry')).value
    S.check(main and registry and U.from_address(addr(image,'boom_vm_thread_bootstrap_pool')+8).value==2,
        'Source VM bootstrap did not publish its real primordial Thread/registry')
    S.check(value(main,'java/lang/Thread','tid','J')==1 and value(main,'java/lang/Thread','eetop','J')!=0 and
        source('java/lang/Thread','currentThread','()Ljava/lang/Thread;',[])==main,
        'Original constructor/FLS main Thread identity differs')
    S.check(U.from_address(addr(image,'boom_vm_system_phase1_called')).value==0 and
        U.from_address(addr(image,binding['vm_level_symbol'])).value==0,'Constructor-only test unexpectedly advanced System phase1')
    object_oop=new('java/lang/Object');source('java/lang/Object','<init>','()V',[object_oop])
    mirror=source('java/lang/Object','getClass','()Ljava/lang/Class;',[object_oop]);S.check(mirror,'Original Object.getClass did not return its normal Class mirror')
    natives={m['name']:m['method'] for m in model['metadata']['methods']}
    def native(name,args,context=None,check=True):return call(natives[name],args,context,check)
    def library(name):
        oop=new(C.IMPL);source(C.IMPL,'<init>','(Ljava/lang/Class;Ljava/lang/String;Z)V',[oop,mirror,name,1])
        S.check(value(oop,C.IMPL,'fromClass','Ljava/lang/Class;')==mirror and value(oop,C.IMPL,'name','Ljava/lang/String;')==name and
            value(oop,C.IMPL,'isBuiltin','Z')==1 and published(oop)==(0,0),'Original NativeLibraryImpl constructor fields differ')
        return oop
    def published(oop):return value(oop,C.IMPL,'handle','J'),value(oop,C.IMPL,'jniVersion','I')
    pins=addr(image,'boom_native_library_pins');modules=addr(image,'boom_native_library_modules')
    callbacks=addr(image,'boom_native_library_load_callbacks');property_reads=addr(image,'boom_native_library_property_reads')
    net,nio=string('net'),string('nio');discovery=[]
    for filename,wanted in (('net.dll','net'),('nio.dll','nio'),('net.abc','net'),('net.dll\0extra','net'),('missing.dll',None)):
        _,found=native('findBuiltinLib',[string(filename)]);actual=text(found) if found else None
        S.check(actual==wanted,'Source builtin discovery differs');discovery.append(dict(input=filename,actual=actual))
    context,found=native('findBuiltinLib',[0],check=False);error=Q.from_address(c.addressof(context)+16).value
    S.check(context[0]==16 and error and not found,'Null builtin filename did not materialize original InternalError')
    message=source('java/lang/Throwable','getMessage','()Ljava/lang/String;',[error])
    S.check(text(message)=='NULL filename for native library','Original typed InternalError message differs')
    receiver=library(nio);_,loaded=native('load',[receiver,nio,1,1])
    S.check(loaded==1 and published(receiver)==(image._handle,0x10008) and Q.from_address(pins).value==1,
        'Actual nio callback did not publish the real owner/version')
    context,duplicate=native('load',[receiver,nio,1,1],check=False)
    S.check(context[0]==20 and not duplicate and Q.from_address(pins).value==1 and U.from_address(modules+64+12).value==1,
        'Duplicate receiver changed native module ownership')
    detached=library(nio)
    with ThreadPoolExecutor(1) as workers:
        failed,loaded=workers.submit(native,'load',[detached,nio,1,1],None,False).result(timeout=20)
    S.check(failed[0]==20 and not loaded and published(detached)==(0,0) and Q.from_address(pins).value==1,
        'Ready module bypassed actual per-OS-thread attachment')
    context,_=native('findEntry0',[image._handle,string('Java_missing_native')],check=False)
    S.check(context[0]==20,'Unsupported standard JNI entry was exposed')
    context,_=native('unload',[nio,1,image._handle+1],check=False)
    S.check(context[0]==7 and Q.from_address(pins).value==1,'Wrong real HMODULE changed native ownership')
    preserved=Context(9,4,7,0,11,12,13,14);before=list(preserved)
    native('unload',[nio,1,image._handle],preserved,False)
    S.check(list(preserved)==before and Q.from_address(pins).value==1,'Existing exception consumed native ownership')
    native('unload',[nio,1,image._handle]);S.check(Q.from_address(pins).value==0,'Actual nio owner pin leaked')
    pairs=[]
    for i in range(8):
        thread=new('java/lang/Thread');source('java/lang/Thread','<init>','(Ljava/lang/String;)V',[thread,string('native-library-worker-'+str(i))])
        tid=value(thread,'java/lang/Thread','tid','J')
        S.check(tid>1 and value(thread,'java/lang/Thread','eetop','J')==0,'Original ordinary Thread constructor did not assign a fresh source tid')
        pairs.append((thread,tid,library(nio)))
    S.check(len({tid for _,tid,_ in pairs})==8,'Source Thread constructors repeated a Java tid')
    enter,leave=Barrier(9,timeout=30),Barrier(9,timeout=30)
    def work(pair):
        thread,tid,lib=pair;entry=proc(rt,'boom_threads_attach',P,P,P,Q)(registry,thread,tid)
        S.check(entry,'Real OS thread/source Thread attachment failed')
        try:
            _,loaded=native('load',[lib,nio,1,1])
            S.check(loaded==1 and published(lib)==(image._handle,0x10008) and
                source('java/lang/Thread','currentThread','()Ljava/lang/Thread;',[])==thread,'Concurrent real source attachment/load differs')
            enter.wait();leave.wait();native('unload',[nio,1,image._handle])
            return dict(OS_thread=get_native_id(),Java_tid=tid,source_Thread=thread)
        finally:S.check(proc(rt,'boom_threads_detach',U,P)(registry)==0,'Concurrent real OS thread detach failed')
    with ThreadPoolExecutor(8) as workers:
        jobs=[workers.submit(work,pair) for pair in pairs]
        try:
            enter.wait();S.check(U.from_address(modules+64+12).value==8 and Q.from_address(pins).value==1 and
                U.from_address(registry+24).value==9,'Eight source receivers did not share one actual image pin')
        finally:leave.wait()
        thread_results=[job.result(timeout=30) for job in jobs]
    S.check(len({r['OS_thread'] for r in thread_results})==8 and Q.from_address(pins).value==0 and U.from_address(registry+24).value==1,
        'Concurrent module/Thread registry references leaked')
    blocked=library(net);context,loaded=native('load',[blocked,net,1,1],check=False)
    S.check(context[0]==20 and not loaded and published(blocked)==(0,0) and not Q.from_address(pins).value and
        not Q.from_address(property_reads).value,'Missing source System.props was silently fabricated')
    context,loaded=native('load',[library(string('unknown')),string('unknown'),1,0],check=False)
    S.check(context[0]==20 and not loaded and not Q.from_address(pins).value,'Unknown external module pretended to load')
    props=new('java/util/Properties');source('java/util/Properties','<init>','()V',[props]);key=string('java.net.preferIPv4Stack')
    source('java/lang/System','setProperties','(Ljava/util/Properties;)V',[props])
    cell=addr(image,f"boom_s{model['metadata']['source_classes']['java/lang/System']}_{model['metadata']['system_props_index']}")
    S.check(root_start<=cell<root_start+root_count*8 and Q.from_address(cell).value==props,
        'Original System.setProperties did not publish into its normal source root cell')
    ws=c.WinDLL('ws2_32.dll');socket=proc(ws,'socket',c.c_size_t,c.c_int,c.c_int,c.c_int)
    close=proc(ws,'closesocket',c.c_int,c.c_size_t);last=proc(ws,'WSAGetLastError',c.c_int)
    net_results=[];pool=addr(image,'boom_builtin_net_pool')
    for wanted in (False,True):
        source('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;',[props,key,string(str(wanted).lower())])
        S.check(source('java/lang/Boolean','getBoolean','(Ljava/lang/String;)Z',[key])==wanted,'Original Boolean callback does not read source Properties')
        lib=library(net);before_reads=Q.from_address(property_reads).value;_,loaded=native('load',[lib,net,1,1])
        S.check(loaded==1 and published(lib)==(image._handle,0x10008) and Q.from_address(pins).value==1 and
            U.from_address(pool+28).value==wanted and Q.from_address(property_reads).value==before_reads+1,
            'Actual net callback ignored its source Boolean/property preference')
        handle=socket(2,1,0);S.check(handle!=c.c_size_t(-1).value and close(handle)==0,'Net callback did not own usable Winsock state')
        native('unload',[net,1,image._handle]);S.check(Q.from_address(pins).value==0 and
            Q.from_address(pool+48).value==Q.from_address(pool+56).value,'Net image/socket ownership did not balance')
        S.check(socket(2,1,0)==c.c_size_t(-1).value and last()==10093,'Final net unload left Winsock initialized')
        net_results.append(dict(preferIPv4Stack=wanted,source_Boolean_callback=True,WSANOTINITIALISED_after_unload=True))
    S.check(Q.from_address(property_reads).value==2,'The two real net property callbacks did not execute exactly once each')
    spans=[]
    exported=set(record['exports'])
    for base,count in [*ROOT_SPANS,('boom_vm_thread_root_cells','boom_vm_thread_root_count')]:
        if base not in exported or count not in exported:continue
        size=Q.from_address(addr(image,count)).value;S.check(size<=1048576,'Original root bank exceeds runtime capacity')
        spans.append(dict(symbol=base,count=size,non_null=sum(bool(Q.from_address(addr(image,base)+8*i).value) for i in range(size))))
    S.check(any(row['symbol']=='boom_java_properties_roots' and row['count']==109 for row in spans) and
        any(row['symbol']=='boom_vm_thread_root_cells' and row['count']==5 for row in spans),'Normal/constructor VM root banks missing')
    S.check(proc(rt,'boom_threads_detach',U,P)(registry)==0 and proc(image,'boom_provider_thread_bind',U,P)(None)==0 and
        proc(rt,'boom_threads_destroy',U,P)(registry)==0,'Actual primordial source registry cleanup failed')
    S.check(proc(image,'boom_release_trace_pool',U)()==0,'Actual source frame TLS/lease cleanup failed')
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Actual normal heap cleanup failed')
    result=dict(schema=1,verified=True,scope='formal_builtin_NativeLibraries_wrappers_original_Java_constructors_upcalls_and_OS_lifecycle_only',
        extra_image=S.artifact(extra_file),formal_provider=model['formal_provider'],actual_owner_HMODULE=image._handle,
        original_primordial_Thread_ThreadGroups_ACC_constructors_executed=True,compiler_generated_VM_pool_bytes=192,VM_pool_ABI=1,
        original_NativeLibraryImpl_constructor_fields_verified=True,original_Object_getClass_used=True,
        all_probe_and_provider_method_IDs_dynamic=True,source_Thread_instances_created_by_original_constructor=True,
        worker_OS_threads=thread_results,worker_Java_Thread_start_called=False,one_actual_pin_for_eight_receivers=True,
        original_Properties_API_publication=True,actual_net_Java_Boolean_callbacks=net_results,
        discovery_cases=discovery,source_error_message='NULL filename for native library',
        duplicate_unknown_detached_wrong_handle_and_existing_exception_checked=True,
        native_fields_published_only_after_actual_callback_and_version_success=True,
        final_owner_pins=0,registry_destroyed=True,source_trace_TLS_released=True,heap_destroyed=True,
        ordinary_class_cold_roots=required,normal_source_root_spans=spans,automatic_GC_or_stack_roots_claimed=False,
        host_Thread_or_class_init_fields_written=False,diagnostic_stops_replaced=False,old_native_candidate_used=False,
        bad_JNI_version_injected=False,full_NativeLibraries_Java_loadLibrary_chain=False,
        system_phase1_executed=False,process_entry_executed=False,development_Python_ctypes_host=True,
        full_VM_startup=False,game_started=False,world_created=False)
    S.write(output/'execution.json',result);return output/'execution.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'native-library-source'/('formal-'+uuid4().hex))
    parser.add_argument('--source-profile',type=Path);parser.add_argument('--selection',type=Path)
    parser.add_argument('--images',type=Path);parser.add_argument('--extra-image',type=Path);parser.add_argument('--worker',type=Path)
    args=parser.parse_args()
    if args.worker:print(execute(args.worker));return
    output=args.output.resolve();S.check(output.is_relative_to(S.ART/'native-library-source') and not output.exists(),'Fresh formal component directory required')
    output.mkdir(parents=True)
    if args.extra_image:extra=args.extra_image.resolve()
    else:
        S.check(args.state is not None,'Provide the current formal26 input state')
        if args.selection:bundle=source_bundle(args.state,args.selection)
        elif args.images:
            bundle=dict(kind='focused_images',images=S.artifact(args.images),selection=str(args.images.resolve().parent),model=source_model(args.state))
        else:bundle=prepare(args.state,output,args.source_profile)
        S.write(output/'source-bundle.json',bundle);extra=build_extra(bundle,output/'extra-image')
    with (output/'worker.log').open('wb') as log:
        result=subprocess.run([sys.executable,str(Path(__file__)), '--worker',str(extra)],stdout=log,stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    S.check(result.returncode==0,'Formal NativeLibraries worker failed; inspect '+str(output/'worker.log'))
    result=S.read(extra.parent/'execution.json');S.write(output/'result.json',result);print(output/'result.json')


if __name__=='__main__':main()
