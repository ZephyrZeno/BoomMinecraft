"""Execute the original image owner initializer and long/long buffer constructor."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from threading import Barrier,get_native_id
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location('jimage_execution_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('jimage-native-map-candidate');S=B.S;N=module('native-library-jimage-candidate')
F=module('formal-provider-selection');D=module('diagnostic-objects');M=module('vm-entry-source')
L=module('canonical-link-response');A=module('verify-batch-assembly');P=module('test-native-library-formal')
Q,U,Ptr=c.c_uint64,c.c_uint32,c.c_void_p
Context=U*8


def proc(image,name,result,*arguments):
    value=getattr(image,name);value.restype,value.argtypes=result,arguments;return value


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


def observations(bridge,closure):
    """Source-bound, read-only host observations of the real Java library map."""
    summary=S.read(Path(closure['batch'])/'summary.json')
    classes=[json.loads(line) for line in S.checked(bridge['metadata']['base']['source_classes']).read_text(encoding='utf-8').splitlines()]
    names={row['name']:row for row in classes if row['origin']['loader']=='bootstrap'}
    wanted={'jdk/internal/loader/BootLoader','jdk/internal/loader/NativeLibraries',
        'java/util/concurrent/ConcurrentHashMap','java/util/concurrent/ConcurrentHashMap$Node'}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layouts={row['name']:row for line in stream if (row:=json.loads(line))['name'] in wanted and
            row['class_id']==names[row['name']]['id']}
    fields={}
    for owner,specs in [('jdk/internal/loader/NativeLibraries',[('libraries','Ljava/util/Map;')]),
            ('java/util/concurrent/ConcurrentHashMap',[('table','[Ljava/util/concurrent/ConcurrentHashMap$Node;')]),
            ('java/util/concurrent/ConcurrentHashMap$Node',[('key','Ljava/lang/Object;'),('val','Ljava/lang/Object;'),
                ('next','Ljava/util/concurrent/ConcurrentHashMap$Node;')])]:
        layout=layouts[owner]
        S.check(layout['diagnostic'] is None and layout['source_sha256']==names[owner]['origin']['sha256'],
            'Normal Java library-map observation layout differs')
        for name,descriptor in specs:
            rows=[row for row in layout['candidate']['fields'] if row['member']['owner']==names[owner]['id'] and
                (row['member']['name'],row['member']['descriptor'])==(name,descriptor)]
            S.check(len(rows)==1 and rows[0]['reference'] and rows[0]['storage_bytes']==8,
                'Original library-map oop field identity differs')
            fields[owner+'.'+name]=rows[0]
    boot=names['jdk/internal/loader/BootLoader']
    [index]=[i for i,row in enumerate(boot['fields']) if
        (row['name'],row['descriptor'],row['access'])==('NATIVE_LIBS','Ljdk/internal/loader/NativeLibraries;',0x1a)]
    return dict(classes={name:names[name]['id'] for name in wanted},fields=fields,
        BootLoader_native_libraries_symbol=f"boom_s{boot['id']}_{index}",
        BootLoader_class_sha256=boot['origin']['sha256'],read_only=True)


def build(bridge_file,library_file,focused_file,output,*,unsafe_read_file=None):
    S.check(B.verify(bridge_file)==S.read(bridge_file.with_name('verification.json')),'Actual source bridge proof differs')
    S.check(N.verify(library_file)==S.read(library_file.with_name('verification.json')),'Actual self-jimage module proof differs')
    H=module('jimage-native-machine');machine_inputs=[];machine_proofs=[]
    for file,kind in [(bridge_file,'map'),(library_file,'library')]:
        receipt=H.verify(file,kind,S.ART/'jimage-native-map/combined-machine-checks'/uuid4().hex)
        proof=S.read(receipt);machine_proofs.append(S.artifact(receipt))
        machine_inputs += [receipt,H.checked(proof['canonical_assembly']),H.checked(proof['canonical_object']),
            *[H.checked(row) for row in proof['inputs']]]
    bridge,library,focused=S.read(bridge_file),S.read(library_file),S.read(focused_file)
    S.check(library['metadata']['bridge']['candidate']==S.artifact(bridge_file) and
        focused['input_state']==bridge['metadata']['input_state'],'Overlay source input namespaces differ')
    # prepare() has just run the complete independent source verifier. These
    # native-only overlays keep every original Java/metadata COFF unchanged;
    # consume that current proof through the generic immutable context instead
    # of repeating its full 70k-method verification for each extra native image.
    E=module('existing-source-selection')
    for row in focused['inputs']:F.checked(row)
    S.check(focused['helper']==S.artifact(Path(F.__file__)) and focused['source_selection_independently_reverified'] is True,
        'Fresh focused helper/source proof is required')
    selection=Path(focused['source_selection_directory'])
    source_state,identity,closure,source_proof,_,_,canonical_objects,canonical_libraries,_=E.context(S.checked(focused['input_state']),selection)
    S.check(source_proof['verified'] is True and identity==focused['base'] and source_proof==S.read(S.checked(focused['source_selection'])) and
        S.checked(focused['source_manifest'])==selection/'closure.json',
        'Current immutable source selection/proof differs')
    source_first_hashes={row['path']:S.artifact(F.checked(row)) for row in focused['inputs']}
    source=bridge['metadata']['source'];chosen={row['class_id'] for row in closure['selected_classes']}
    S.check(set(source['required_classes'])<=chosen,'Normal image/buffer classes must be selected normally')
    for row in source['original_java']+source['owner_initializer_source']:
        selected=closure['selected_methods'].get(str(row['method']))
        S.check(selected and selected['class_id']==row['class_id'] and selected['source_sha256']==row['class_sha256'] and
            selected['code_sha256']==row['code_sha256'],'Original buffer/initializer Java Code is not selected')
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh image bridge execution required')
    output.mkdir(parents=True);assembler=Path(bridge['assembler']['path'])
    def assemble(asm,obj):
        with asm.with_suffix('.log').open('xb') as log:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    ident=source['methods'][0]['method'];stops=(selection/'diagnostic-stops.asm').read_text(encoding='utf-8')
    begin=f'PUBLIC boom_m{ident}\nboom_m{ident} PROC\n';end=f'boom_m{ident} ENDP\n'
    S.check(stops.count(begin)==stops.count(end)==1,'Exactly the original image native stop must exist')
    first=stops.index(begin);last=stops.index(end,first)+len(end);removed=stops[first:last]
    diagnostic=S.read(selection/'diagnostic.json')
    rows=[row for row in diagnostic['rows'] if row['symbol']==f'boom_m{ident}']
    S.check(len(rows)==1 and rows[0]['method']['id']==ident and rows[0]['source_sha256']==source['methods'][0]['class_sha256'],
        'Original image native diagnostic identity differs')
    replacement=stops[:first]+stops[last:];stop_asm,stop_obj=output/'remaining-stops.asm',output/'remaining-stops.obj'
    stop_asm.write_text(replacement,encoding='utf-8');assemble(stop_asm,stop_obj)
    binding=M.binding_model(closure,False,signal_control=True);vm_text,vm_imports=M.assembly(binding)
    S.check(binding['system_entry'] is None and not binding.get('system_phase2') and binding['child_constructor'] is None and
        binding.get('object_wait') and binding.get('reference_processing') and binding.get('unsafe_park'),
        'Normal worker/wait/Parker owner boundary required without executing System phase1')
    vm_asm,vm_obj=output/'constructor-vm.asm',output/'constructor-vm.obj';vm_asm.write_text(vm_text,encoding='utf-8');assemble(vm_asm,vm_obj)
    vm_exports=M.entry_exports(binding)
    S.check(A.coff_symbols(vm_obj,M.FOREIGN|{'GetTickCount64','Sleep'})==(vm_exports,vm_imports),
        'Actual constructor-only VM entry symbols differ')
    lifecycle_source=ROOT/'native/probe/jimage_component_owner.asm'
    lifecycle_asm,lifecycle_obj=output/'component-owner.asm',output/'component-owner.obj'
    lifecycle_asm.write_text(lifecycle_source.read_text(encoding='utf-8'),encoding='utf-8');assemble(lifecycle_asm,lifecycle_obj)
    lifecycle_exports={'boom_jimage_component_owner_'+suffix for suffix in ('open','close','status')}|{'boom_jimage_component_quiesce'}
    S.check(A.coff_symbols(lifecycle_obj,{'GetTickCount64','Sleep'})[0]==lifecycle_exports,
        'Actual component native lifecycle export contract differs')
    sealed=D.verify(selection);original=[S.checked(row['object']) for row in sealed['units']]+[Path(p) for p in closure['objects']]
    S.check(original==canonical_objects,'Actual canonical original object collection/order differs')
    original_first_hashes=[S.artifact(path) for path in original]
    [stop_original]=[S.checked(row['object']) for row in sealed['units'] if Path(row['assembly']['path'])==selection/'diagnostic-stops.asm']
    [old_provider]=[S.read(S.checked(row['manifest'])) for row in closure['runtime_provider_packs']
        if S.read(S.checked(row['manifest']))['family']=='normal-native-libraries-v1']
    old_object=S.checked(old_provider['object']);S.check(original.count(old_object)==1,'One old NativeLibraries COFF must be replaced')
    formal_library_prefix=N.old_machine_prefix(S.checked(library['object']),old_object,library['metadata']['source']['methods'])
    objects=[stop_obj if path==stop_original else S.checked(library['object']) if path==old_object else path for path in original]
    owner_file=S.checked(bridge['metadata']['mapping_owner']['candidate']);owner=S.read(owner_file)
    owner_obj=B.module('jimage-owner-candidate').checked(owner['object'])
    objects += [S.checked(bridge['object']),owner_obj,vm_obj,lifecycle_obj]
    read_candidate=None;read_proof=None;read_inputs=[]
    if unsafe_read_file is not None:
        R=module('jimage-unsafe-read-candidate');read_candidate=S.read(unsafe_read_file)
        read_proof=R.verify(unsafe_read_file)
        S.check(read_proof==S.read(unsafe_read_file.with_name('verification.json')) and
            read_candidate['metadata']['input_state']==bridge['metadata']['input_state'] and
            read_candidate['metadata']['bridge_source']==bridge['kernel'] and
            R.O.checked(read_candidate['metadata']['mapping_owner']['candidate'])==owner_file,
            'RO scalar variant must use the same real owner/bridge/current source')
        old_typed=S.checked(read_candidate['metadata']['original_unit']['object'])
        S.check(objects.count(old_typed)==1,'Exactly the selected original 42-native typed unit must be replaced')
        objects=[S.checked(read_candidate['object']) if path==old_typed else path for path in objects]
        objects += [S.checked(read_candidate['wrapper_object']),S.checked(read_candidate['core_object'])]
        read_inputs=[unsafe_read_file,unsafe_read_file.with_name('verification.json'),
            *[S.checked(read_candidate[key]) for key in ('assembly','object','wrapper_assembly','wrapper_object','core_assembly','core_object')],
            *[F.checked(row) for row in read_candidate['metadata']['sources'].values()]]
    runtime=S.checked(bridge['metadata']['runtime']);libraries=L.diagnostic_libraries(runtime,winsock=True)[0]
    S.check(libraries==canonical_libraries,'Actual canonical original import library collection/order differs')
    observe=observations(bridge,closure)
    owner_exports=S.read(owner_file.with_name('verification.json'))['exports']
    exports=set(closure['exports'])|set(bridge['exports'])|set(library['exports'])|set(owner_exports)|vm_exports|lifecycle_exports
    if read_candidate is not None:exports|={R.C.SERVICE,R.EXPORTED_SCALAR}
    exports.add(observe['BootLoader_native_libraries_symbol'])
    image,rsp=output/'jimage-source.dll',output/'link.rsp'
    rsp.write_text('\n'.join([*L.PREFIXES['diagnostic'],'/OUT:"'+str(image)+'"',
        *['"'+str(path)+'"' for path in objects+libraries],*['/EXPORT:'+symbol for symbol in sorted(exports)]])+'\n',encoding='utf-8')
    L.verify(rsp,profile='diagnostic',output=image,objects=objects,library_choices=[libraries],exports=exports)
    with (output/'link.log').open('xb') as log:
        subprocess.run([assembler.with_name('link.exe'),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    pe=M.pe(image)
    S.check(module('diagnostic-closure').pe_exports(image)==exports,'Actual component PE exports differ')
    S.check(set(pe['imports'])<={'boom-runtime.dll','kernel32.dll','api-ms-win-core-synch-l1-2-0.dll','ws2_32.dll'},
        'The image must not load a JDK or other native runtime DLL')
    S.check(sorted(pe['imports']['ws2_32.dll'])==sorted(L.winsock_import_tokens(libraries[-1]).values()),
        'Actual five Winsock imports changed')
    model_files=[S.checked(row) for row in focused['harness_sources'] if Path(row['path']).name=='probe-model.json']
    S.check(len(model_files)==1,'Pinned focused original API model missing')
    model=S.read(model_files[0]);S.check(model['jimage_metadata']==source,'Focused model and native source differ')
    inputs=[]
    for path in dict.fromkeys([*original,*objects,*libraries,bridge_file,bridge_file.with_name('verification.json'),
        library_file,library_file.with_name('verification.json'),owner_file,owner_file.with_name('verification.json'),focused_file,
        *[F.checked(row) for row in focused['inputs']],model_files[0],Path(__file__),vm_asm,stop_asm,lifecycle_source,lifecycle_asm,rsp,image,
        ROOT/'scripts/vm-entry-source.py',ROOT/'native/entry/vm_process.asm.inc',Path(E.__file__),
        ROOT/'.boom/prepare-jimage-map-focused-v177-a.py',*read_inputs,*machine_inputs]):inputs.append(S.artifact(path))
    for row in inputs:F.checked(row)
    source_final_hashes={row['path']:S.artifact(F.checked(row)) for row in focused['inputs']}
    original_final_hashes=[S.artifact(path) for path in original]
    S.check(source_first_hashes==source_final_hashes and original_first_hashes==original_final_hashes,
        'Original current source/Java objects changed across overlay construction')
    R=module('provider-native-roots');spans=[]
    for symbol,count in [*R.STANDARD_SOURCE_SPANS,R.PRIMORDIAL_SPAN]:
        if symbol in exports and count in exports:spans.append(dict(symbol=symbol,count_symbol=count))
    spans += [dict(row) for row in closure.get('selected_provider_native_root_spans',[])]
    S.check(len({row['symbol'] for row in spans})==len(spans) and
        any(row['symbol']==R.PRIMORDIAL_SPAN[0] for row in spans),'Actual source/primordial/native root set is incomplete')
    result=dict(schema=1,scope='original_image_initializer_with_unregistered_real_owner_library_and_lookup_overlays',
        bridge=S.artifact(bridge_file),library=S.artifact(library_file),owner=S.artifact(owner_file),focused=S.artifact(focused_file),
        original_source_selection=S.artifact(selection/'selection-verification.json'),source_model=model,
        source_observations=observe,binding_model=binding,image=S.artifact(image),runtime=S.artifact(runtime),
        native_lifecycle_source=S.artifact(lifecycle_source),native_lifecycle_object=S.artifact(lifecycle_obj),
        actual_formal_NativeLibraries_machine_prefix=formal_library_prefix,
        inputs=inputs,objects=[S.artifact(path) for path in objects],libraries=[S.artifact(path) for path in libraries],
        response=S.artifact(rsp),exports=sorted(exports),imports=pe['imports'],original_objects=[S.artifact(path) for path in original],
        replaced_original_native_stop=rows[0],removed_stop_ASM_sha256=hashlib.sha256(removed.encode()).hexdigest(),
        replaced_original_provider=old_provider['family'],original_Java_Code_or_Java_COFF_changed=False,
        original_current_full_source_verification_consumed=True,full_source_V_repeated_for_native_overlay=False,
        current_full_source_proof_chain=dict(prepare_images=S.artifact(focused_file),prepare_helper=focused['helper'],
            input_state=focused['input_state'],input_state_status=source_state['status'],
            full_V_proof=focused['source_selection'],full_V_verified=True,
            full_V_producer=S.artifact(ROOT/'scripts/verify-diagnostic-closure.py'),
            original_source_verifier=S.artifact(ROOT/'scripts/verify-initialization-closure.py'),
            actual_canonical_original_objects=original_first_hashes,
            source_inputs_first_SHA=source_first_hashes,source_inputs_final_SHA=source_final_hashes,
            original_objects_first_SHA=original_first_hashes,original_objects_final_SHA=original_final_hashes,
            additional_native_objects_in_original_full_V_scope=False),
        quiescent_root_spans=spans,
        original_unsafe_native_unit_replaced=read_candidate is not None,
        complete_native_machine_proofs=machine_proofs,
        unsafe_read_candidate=S.artifact(unsafe_read_file) if unsafe_read_file is not None else None,
        unsafe_read_proof=read_proof,
        new_initializer_Java_substituted=False,metadata_fixture=False,shared_registered=False,executed=False,game_started=False)
    path=output/'images.json';S.write(path,result);return path


def verified_images(path):
    row=S.read(path)
    S.check(row['scope']=='original_image_initializer_with_unregistered_real_owner_library_and_lookup_overlays' and
        not any(row[k] for k in ('original_Java_Code_or_Java_COFF_changed','new_initializer_Java_substituted','metadata_fixture','shared_registered','executed','game_started')),
        'Image bridge overlay scope differs')
    for item in row['inputs']:F.checked(item)
    B.verify(S.checked(row['bridge']));N.verify(S.checked(row['library']))
    O=module('jimage-owner-candidate')
    for receipt in row['complete_native_machine_proofs']:
        proof=S.read(S.checked(receipt))
        for item in proof['inputs']:F.checked(item)
        candidate=S.read(S.checked(proof['candidate']))
        S.check(O.normalized_coff(S.checked(candidate['object']))==proof['normalized']==
            O.normalized_coff(S.checked(proof['canonical_object'])),
            'Complete native actual/canonical symbols/aux/flags/unwind/relocations changed')
    if row['unsafe_read_candidate'] is not None:
        R=module('jimage-unsafe-read-candidate')
        S.check(R.verify(S.checked(row['unsafe_read_candidate']))==row['unsafe_read_proof'],'Current RO scalar variant proof changed')
    return row


def execute(images_file):
    record=verified_images(images_file);out=Path(images_file).parent;meta=record['source_model'];source=meta['jimage_metadata']
    with os.add_dll_directory(str(S.checked(record['runtime']).parent)):
        rt=c.CDLL(str(S.checked(record['runtime'])));image=c.CDLL(str(S.checked(record['image'])))
    members={(row['owner'],row['name'],row['descriptor']):row['method'] for row in meta['members']}
    classes=meta['classes'];heap=proc(rt,'boom_heap_create',Ptr,Q)(256<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,Ptr)(heap)==1,'Normal original heap/literals binding failed')
    selection=Path(S.read(S.checked(record['focused']))['source_selection_directory']);diagnostic=S.read(selection/'diagnostic.json')
    failing_context=None;stage='heap';stages=[];failure=None;registry=None;opened=False;main=None
    owner=c.create_string_buffer(128);owner_ptr=c.addressof(owner);pool=addr(image,B.C.POOL);bootstrap_job=None;library_name=None
    successful=[];threads=[];null_result=None;published=None;read_boundary=None;negatives=[];cleanup={};lease_before_shutdown=None
    misses=[];collections=[]
    def context_fault(context):
        pool_address=addr(image,'boom_diagnostic_pool');index=U.from_address(pool_address+32).value
        return diagnostic['rows'][index-1] if U.from_address(pool_address+8).value==2 and 0<index<=len(diagnostic['rows']) else None
    def check_context(label,context):
        nonlocal failing_context,stage
        stage=label
        if context[0]:
            failing_context=context
            path=out/'first-failure.json'
            if not path.exists():S.write(path,dict(stage=label,context=list(context),row=context_fault(context),
                original_source_changed=False,Java_class_state_or_cache_written=False))
            raise RuntimeError('Original source frontier: '+repr((label,list(context),context_fault(context))))
    def call(ident,arguments,*,check=True,context=None):
        context=Context() if context is None else context;argv=(Q*max(1,len(arguments)))(*arguments)
        value=proc(image,'boom_m'+str(ident),Q,Ptr,Ptr)(context,argv)
        if check:check_context('boom_m'+str(ident),context)
        return value,context
    def java(owner,name,descriptor,arguments):return call(members[owner,name,descriptor],arguments)[0]
    def ensure(owner):
        context=Context();proc(rt,'boom_class_ensure32',U,Ptr,Ptr)(addr(image,'boom_class'+str(classes[owner])),context)
        check_context('ensure '+owner,context)
    def new(owner):
        ensure(owner);context=Context();oop=proc(rt,'boom_object_new',Ptr,Ptr,Ptr,Ptr)(heap,addr(image,'boom_layout'+str(classes[owner])),context)
        check_context('new '+owner,context);S.check(oop,'Normal source allocation returned null');return oop
    def string(text):
        raw=text.encode('utf-16-le','surrogatepass');context=Context()
        chars=proc(rt,'boom_array_new',Ptr,Ptr,c.c_int,U,Ptr)(heap,len(raw)//2,5,context)
        check_context('normal char[]',context);S.check(chars,'Normal char[] allocation failed')
        if raw:c.memmove(chars,raw,len(raw))
        oop=new('java/lang/String');java('java/lang/String','<init>','([C)V',[oop,chars]);return oop
    def text(oop):
        chars=java('java/lang/String','toCharArray','()[C',[oop])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    def field(oop,owner,name,descriptor):
        rows=[row for row in meta['layouts'][owner]['fields'] if row['member']['owner']==classes[owner] and
            (row['member']['name'],row['member']['descriptor'])==(name,descriptor)]
        S.check(len(rows)==1,'Original fixture field is not unique')
        return Q.from_address(oop+rows[0]['offset']).value
    def mapped(oop):
        result={name:(Q if row['storage_bytes']==8 else U).from_address(oop+row['offset']).value
            for name,row in source['normal_direct_fields'].items()}
        for name in ('capacity','position','limit'):S.check(java('java/nio/Buffer',name,'()I',[oop])==result[name],
            'Original Java buffer getter differs from its source FMAP')
        S.check(java('java/nio/DirectByteBuffer','isDirect','()Z',[oop])==1 and
            java('java/nio/ByteBuffer','hasArray','()Z',[oop])==0,'Original direct buffer API flags differ')
        return result
    try:
        context=Context();main=proc(image,'boom_jimage_component_owner_open',Ptr,Ptr)(context);check_context('real primordial constructors and wait/Parker/signal owners',context)
        registry=Ptr.from_address(addr(image,'boom_provider_thread_registry')).value
        S.check(main and registry and java('java/lang/Thread','currentThread','()Ljava/lang/Thread;',[])==main,
            'Original primordial/FLS identity differs')
        stages.append('original_primordial_Thread_and_ThreadGroups')
        fixture=out/'fixtures';fixture.mkdir();path=fixture/'modules';shutil.copyfile('D:/Dev/Java/jdk-21/lib/modules',path)
        expected=dict(size=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        S.check(expected==dict(size=141325186,sha256='541b62fa469595c7eeb2c329dad24151887be50056e08b5e4e1534c6260bb263'),
            'Isolated exact original JIMAGE fixture differs')
        props=new('java/util/Properties');java('java/util/Properties','<init>','()V',[props])
        values={'java.home':str(fixture),'user.dir':str(fixture),'user.home':str(fixture),'user.name':'jimage-map-test',
            'java.io.tmpdir':str(fixture),'file.separator':'\\','path.separator':';','line.separator':'\r\n',
            'os.name':'Windows 10','os.arch':'amd64','os.version':'10.0','file.encoding':'UTF-8','native.encoding':'UTF-8',
            'sun.jnu.encoding':'UTF-8','java.class.version':'65.0','sun.boot.library.path':str(fixture),'java.library.path':str(fixture)}
        for key,value in values.items():java('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;',
            [props,string(key),string(value)])
        java('java/lang/System','setProperties','(Ljava/util/Properties;)V',[props])
        java('jdk/internal/misc/VM','saveProperties','(Ljava/util/Map;)V',[props])
        java('java/lang/System','setJavaLangAccess','()V',[])
        stages.append('original_Properties_System_setProperties_VM_saveProperties_System_setJavaLangAccess')
        S.check(proc(image,'boom_jimage_owner_init',U,Ptr,U,U)(owner_ptr,128,32)==0 and
            proc(image,'boom_jimage_native_map_open',U,Ptr,Ptr)(pool,owner_ptr)==0 and
            proc(image,'boom_jimage_native_map_ready',U,Ptr)(pool)==0,'Actual empty real owner/bridge open failed')
        opened=True
        source_path=string(str(path));library_name=string('jimage')
        owner_class=addr(image,'boom_class'+str(source['owner']))
        S.check(U.from_address(owner_class+8).value==0,'Original NativeImageBuffer owner must start cold')
        native=source['methods'][0]['method'];value,context=call(native,[source_path])
        S.check(not value and Q.from_address(owner_ptr+32).value==0 and Q.from_address(owner_ptr+56).value==0 and
            Q.from_address(owner_ptr+64).value==0 and Q.from_address(owner_ptr+96).value==1 and
            Q.from_address(owner_ptr+104).value==1,'A true empty registry miss must not open a mapping')
        S.check(U.from_address(owner_class+8).value==2 and U.from_address(addr(image,'boom_jimage_library_module')+28).value==1,
            'Original owner initializer/System.loadLibrary did not complete before lookup')
        null_result=dict(value=0,original_owner_cold_to_ready=True,actual_System_loadLibrary_completed=True,
            owner_lookups=1,owner_misses=1,mappings=0,lease_nodes=Q.from_address(pool+40).value)
        obs=record['source_observations'];fields=obs['fields']
        boot_lib=Q.from_address(addr(image,obs['BootLoader_native_libraries_symbol'])).value
        def observed(oop,owner,name):return Q.from_address(oop+fields[owner+'.'+name]['offset']).value
        libraries=observed(boot_lib,'jdk/internal/loader/NativeLibraries','libraries')
        table=observed(libraries,'java/util/concurrent/ConcurrentHashMap','table');S.check(table,'Original Java loaded-library map has no table')
        library_oop=None
        for index in range(Q.from_address(table-16).value//8):
            node=Q.from_address(table+index*8).value
            while node:
                key=observed(node,'java/util/concurrent/ConcurrentHashMap$Node','key')
                if text(key)=='jimage':library_oop=observed(node,'java/util/concurrent/ConcurrentHashMap$Node','val')
                node=observed(node,'java/util/concurrent/ConcurrentHashMap$Node','next')
        S.check(library_oop,'Original Java map did not retain the actual loaded jimage NativeLibraryImpl')
        offsets={row['name']:row['offset'] for row in S.read(S.checked(record['library']))['metadata']['source']['fields']}
        published=dict(handle=Q.from_address(library_oop+offsets['handle']).value,
            jniVersion=U.from_address(library_oop+offsets['jniVersion']).value,original_Java_map_retains_impl=True)
        S.check(published['handle']==image._handle and published['jniVersion']==0x10008 and
            Q.from_address(addr(image,'boom_native_library_pins')).value==1,'Real self pin/version was not published into original Java fields')
        raw=str(path).encode('utf-16-le');key=c.create_string_buffer(raw+b'\0\0');bootstrap_job=(Q*8)()
        bootstrap_job[0]=owner_ptr;bootstrap_job[1]=c.addressof(key);bootstrap_job[2]=len(raw)//2;bootstrap_job[7]=expected['size']
        S.check(proc(image,'boom_jimage_owner_open',U,Ptr)(bootstrap_job)==0,'Explicit real resource bootstrap open failed')
        bootstrap_token=bootstrap_job[3];view=bootstrap_job[4]
        S.check(view and bootstrap_job[5]==expected['size'],'Actual mapped view/length differs')
        value,context=call(native,[source_path]);shape=mapped(value)
        S.check(shape==dict(address=view,capacity=expected['size'],position=0,limit=expected['size'],att=0,cleaner=0),
            'Original JNI long/long constructor did not publish its real normal buffer fields')
        successful.append(dict(buffer=value,shape=shape,first_28_bytes=c.string_at(shape['address'],28).hex()))
        S.check(Q.from_address(owner_ptr+56).value==2 and Q.from_address(pool+48).value==1,
            'Successful source buffer did not retain its distinct real lookup lease')
        S.check(proc(image,'boom_jimage_owner_close',U,Ptr)(owner_ptr)==2,'Live source buffer lease permitted mapping close')
        for label,query in [('empty',''),('embedded_NUL',str(path)+'\0suffix'),('case_changed',str(path).upper()),
                ('dot_component',str(path.parent)+'\\.\\modules'),('forward_slashes',str(path).replace('\\','/')),
                ('missing',str(path)+'.missing'),('over_owner_key_budget','x'*32768),('unpaired_surrogate','\ud800')]:
            before=Q.from_address(owner_ptr+56).value;result,ctx=call(native,[string(query)])
            S.check(not result and Q.from_address(owner_ptr+56).value==before,'Lookup normalized/opened a nonmatching key')
            misses.append(dict(case=label,value=0,leases_unchanged=True))
        read,read_context=call(members['java/nio/DirectByteBuffer','getInt','(I)I'],[value,0],check=False)
        read_boundary=dict(context=list(read_context),value=read,passed=not read_context[0],row=context_fault(read_context))
        if not read_context[0]:S.check(c.c_int32(read).value==int.from_bytes(path.read_bytes()[:4],'big',signed=True),'Original mapped getInt bytes differ')
        for args,wanted in [([0],4),([new('java/lang/Object')],7),([0x10000],7)]:
            result,ctx=call(native,args,check=False);S.check(not result and ctx[0]==wanted,'Original heap/input validation differs')
            negatives.append(dict(context=list(ctx),expected=wanted))
        pending=Context(16,17,18,0,19,20,21,22);before=bytes(pending);result,ctx=call(native,[source_path],check=False,context=pending)
        S.check(not result and bytes(ctx)==before,'Pending original Context32 was changed')
        negatives.append(dict(pending_context_all_32_bytes_unchanged=True))
        pairs=[]
        for index in range(8):
            thread=new('java/lang/Thread');java('java/lang/Thread','<init>','(Ljava/lang/String;)V',[thread,string('jimage-'+str(index))])
            pairs.append((thread,field(thread,'java/lang/Thread','tid','J')))
        registry_before_workers=U.from_address(registry+24).value
        barrier=Barrier(8,timeout=60)
        def worker(pair):
            thread,tid=pair;S.check(proc(rt,'boom_threads_attach',Ptr,Ptr,Ptr,Q)(registry,thread,tid),'Actual source Thread attachment failed')
            try:
                barrier.wait()
                for _ in range(64):
                    oop,ctx=call(native,[source_path]);actual=mapped(oop)
                    S.check(actual==shape,'Concurrent original constructor/view differs')
                    if record['unsafe_read_candidate'] is not None:
                        read,ctx=call(members['java/nio/DirectByteBuffer','getInt','(I)I'],[oop,0])
                        S.check(c.c_int32(read).value==int.from_bytes(bytes.fromhex(successful[0]['first_28_bytes'])[:4],'big',signed=True),
                            'Concurrent original ByteBuffer getInt differs')
                return dict(OS_thread=get_native_id(),Java_tid=tid,calls=64,original_Java_Thread_start_called=False)
            finally:S.check(proc(rt,'boom_threads_detach',U,Ptr)(registry)==0,'Actual source Thread detach failed')
        with ThreadPoolExecutor(8) as executor:threads=list(executor.map(worker,pairs))
        S.check(len({row['OS_thread'] for row in threads})==8 and U.from_address(registry+24).value==registry_before_workers,
            'Eight actual OS/source Thread identities or final registry count differ')
        S.check(Q.from_address(owner_ptr+56).value==514 and Q.from_address(pool+40).value==513 and Q.from_address(pool+48).value==513,
            'Lookup token directory count or owner lease accounting differs')
        quiesce_context=Context();quiesced=proc(image,'boom_jimage_component_quiesce',U,Ptr)(quiesce_context)
        S.check(quiesced==0 and not quiesce_context[0] and U.from_address(registry+24).value==1,
            'Actual native workers did not join before quiescent GC')
        S.check(U.from_address(addr(image,'boom_provider_threads_pool')+120).value==0,
            'A real source background worker stopped at an unresolved frontier')
        def collect(extra):
            # All Java frames are unwound and every external worker is joined.
            # These snapshots cover this selection's banks, not active frames
            # or Context32 pending exceptions and not an automatic collector.
            roots=[];spans=[]
            for span in record['quiescent_root_spans']:
                count=span.get('count')
                if count is None:count=Q.from_address(addr(image,span['count_symbol'])).value
                S.check(count<=1048576,'Original physical source root span exceeds the bound')
                values=list((Q*count).from_address(addr(image,span['symbol'])))
                nonempty=[value for value in values if value];roots.extend(nonempty)
                spans.append(dict(symbol=span['symbol'],physical_cells=count,non_null=len(nonempty),
                    sha256=hashlib.sha256(bytes((Q*count)(*values))).hexdigest()))
            source_non_null=len(roots);roots.extend(extra);unique=sorted(set(roots));members=set(unique)
            S.check(all(value in members for value in roots),'Quiescent snapshot omitted an original source/test oop')
            packed=(Q*max(1,len(unique)))(*unique);before=Q.from_address(owner_ptr+56).value
            freed=proc(rt,'boom_heap_collect',Q,Ptr,Ptr,U)(heap,packed,len(unique))
            S.check(freed!=0xffffffffffffffff and Q.from_address(owner_ptr+56).value==before,
                'Quiescent GC failed or implicitly released native view leases')
            collections.append(dict(spans=spans,source_non_null=source_non_null,additional_test_roots=list(extra),
                before_dedup=len(roots),after_dedup=len(unique),snapshot_sha256=hashlib.sha256(bytes(packed)[:len(unique)*8]).hexdigest(),
                freed_objects=freed,native_leases_unchanged=True,automatic_or_concurrent_GC=False,
                active_Java_frames=False,all_external_workers_joined=True,Context_pending_oops_not_covered=True))
        keep=[source_path,library_name,*[thread for thread,_ in pairs]]
        first_buffer=successful[0]['buffer']
        collect([*keep,first_buffer]);S.check(proc(rt,'boom_heap_contains',U,Ptr,Ptr)(heap,first_buffer),'Correctly rooted buffer was reclaimed')
        S.check(mapped(first_buffer)==shape,'Original source getters failed after quiescent GC')
        collect([*keep,first_buffer]);collect(keep)
        S.check(not proc(rt,'boom_heap_contains',U,Ptr,Ptr)(heap,first_buffer),'Pure native token directory incorrectly rooted a Java buffer')
        fresh,ctx=call(native,[source_path]);S.check(mapped(fresh)==shape,'Original source lookup/constructor failed after reclamation')
        collect([*keep,fresh]);S.check(mapped(fresh)==shape,'New correctly rooted mapped buffer was lost')
        lease_before_shutdown=Q.from_address(owner_ptr+56).value
        S.check(lease_before_shutdown==515 and Q.from_address(pool+48).value==514,'Retained leases after four real GCs differ')
        # This calls the original native lifecycle under its normal source frame.
        unload=next(row['method'] for row in S.read(S.checked(record['library']))['metadata']['source']['methods'] if row['name']=='unload')
        call(unload,[library_name,1,image._handle])
        S.check(Q.from_address(addr(image,'boom_native_library_pins')).value==0 and
            Q.from_address(owner_ptr+56).value==lease_before_shutdown,'Module unload released live VM image mappings')
        stages.append('real_original_owner_clinit_map_miss_hit_JJ_ctor_and_8_OS_threads')
    except BaseException as error:failure=repr(error)
    finally:
        if failing_context is not None and failing_context[0]==0xb001 and failing_context[3]==0 and not Q.from_address(c.addressof(failing_context)+16).value:
            before=bytes(failing_context);released=Q();status=proc(rt,'boom_monitor_abort_owned',U,Ptr,Ptr,Ptr,U)(heap,failing_context,c.byref(released),0)
            cleanup['controlled_diagnostic_monitor_abort']=dict(status=status,released=released.value,Context_unchanged=bytes(failing_context)==before)
        cleanup_context=Context();cleanup['quiesce']=proc(image,'boom_jimage_component_quiesce',U,Ptr)(cleanup_context)
        cleanup['module_unload']=0
        module=addr(image,'boom_jimage_library_module')
        if cleanup['quiesce']==0 and library_name and Q.from_address(module+16).value:
            unload=next(row['method'] for row in S.read(S.checked(record['library']))['metadata']['source']['methods'] if row['name']=='unload')
            _,unload_context=call(unload,[library_name,1,Q.from_address(module+16).value],check=False)
            cleanup['module_unload']=int(unload_context[0]);cleanup['module_unload_context']=list(unload_context)
        cleanup_context=Context();cleanup['component_owner_close']=proc(image,'boom_jimage_component_owner_close',U,Ptr)(cleanup_context)
        cleanup['owner_cleanup_context']=list(cleanup_context)
        cleanup['native_workers_joined']=U.from_address(addr(image,'boom_jimage_component_owner_status')+4).value
        cleanup['normal_owners_closed']=U.from_address(addr(image,'boom_jimage_component_owner_status')+8).value
        cleanup['native_worker_failure']=U.from_address(addr(image,'boom_provider_threads_pool')+120).value
        cleanup['trace_release']=proc(image,'boom_release_trace_pool',U)()
        cleanup['held_monitors']=Q.from_address(heap+112).value
        cleanup['heap_destroy']=proc(rt,'boom_heap_destroy',U,Ptr)(heap) if cleanup['component_owner_close']==0 else 0
        # Only after workers/Java frames/heap users have ended may view leases go.
        if opened and cleanup['heap_destroy']==1:
            cleanup['bridge_close']=proc(image,'boom_jimage_native_map_close',U,Ptr)(pool)
            if bootstrap_job is not None and bootstrap_job[3]:
                token=bootstrap_job[3];release=(Q*8)();release[0]=owner_ptr;release[3]=token
                cleanup['bootstrap_release']=proc(image,'boom_jimage_owner_release',U,Ptr)(release)
            cleanup['owner_close']=proc(image,'boom_jimage_owner_close',U,Ptr)(owner_ptr)
            cleanup['native_nodes']=Q.from_address(pool+40).value;cleanup['native_leases']=Q.from_address(pool+48).value
            cleanup['owner_leases']=Q.from_address(owner_ptr+56).value;cleanup['owner_files']=Q.from_address(owner_ptr+72).value
            cleanup['owner_mappings']=Q.from_address(owner_ptr+80).value
        cleanup['self_module_pins']=Q.from_address(addr(image,'boom_native_library_pins')).value
        for item in record['inputs']:F.checked(item)
    cleanup_expected=dict(quiesce=0,module_unload=0,component_owner_close=0,native_workers_joined=1,normal_owners_closed=1,native_worker_failure=0,
        trace_release=0,held_monitors=0,heap_destroy=1,
        bridge_close=0,bootstrap_release=0,owner_close=0,native_nodes=0,native_leases=0,owner_leases=0,
        owner_files=0,owner_mappings=0,self_module_pins=0)
    complete_cleanup=all(cleanup.get(name)==value for name,value in cleanup_expected.items())
    okay=failure is None and bool(successful) and len(threads)==8 and len(collections)==4 and len(misses)==8 and null_result is not None and published is not None and complete_cleanup
    result=dict(schema=1,verified=okay,scope='original_NativeImageBuffer_cold_initializer_lookup_and_JNI_JJ_constructor_component',
        images=S.artifact(images_file),stages=stages,failure_stage=stage if failure else None,failure=failure,
        true_empty_registry_null=null_result,actual_original_Java_library_publication=published,lookup_hits=successful,
        read_primitive_boundary=read_boundary,negative=negatives,lookup_misses=misses,OS_threads=threads,
        quiescent_collections=collections,lease_count_before_shutdown=lease_before_shutdown,
        cleanup=cleanup,complete_cleanup=complete_cleanup,original_Java_fields_or_class_states_or_caches_host_written=False,
        System_phase1_executed=False,explicit_resource_bootstrap_ASM_open=True,getNativeMap_opens_file=False,
        JDK_oracle_completed=False,quiescent_GC_completed=len(collections)==4,shared_registered=False,full_VM_startup=False,game_started=False)
    path=out/'execution.json';S.write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bridge',type=Path);parser.add_argument('--library',type=Path)
    parser.add_argument('--focused',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--images',type=Path)
    parser.add_argument('--unsafe-read',type=Path)
    parser.add_argument('--worker',type=Path);args=parser.parse_args()
    if args.worker:
        path=execute(args.worker.resolve());print(path);S.check(S.read(path)['verified'],'Original image component failed; receipt preserved')
    else:
        images=args.images.resolve() if args.images else build(args.bridge.resolve(),args.library.resolve(),args.focused.resolve(),args.output.resolve(),
            unsafe_read_file=args.unsafe_read.resolve() if args.unsafe_read else None)
        subprocess.run([os.sys.executable,Path(__file__),'--worker',images],check=True,timeout=2400)
