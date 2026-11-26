"""Execute original Module construction and native graph over sealed normal source."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from threading import Barrier,get_native_id
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('normal_Module_candidate',ROOT/'scripts/module-definitions-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
S=B.S;L=B.module('canonical-link-response')
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8
ROOT_SPANS=[('boom_probe_static_roots','boom_probe_static_root_count'),
    ('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),
    ('boom_java_class_roots','boom_java_class_root_count'),('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),
    ('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),('boom_provider_threads_roots','boom_provider_threads_root_count')]
JAVA=[('java/lang/String','<init>','([C)V'),('java/lang/String','toCharArray','()[C'),
    ('java/lang/Throwable','getMessage','()Ljava/lang/String;'),('java/lang/Class','getModule','()Ljava/lang/Module;'),
    ('java/util/HashSet','<init>','()V'),('java/util/HashSet','add','(Ljava/lang/Object;)Z'),
    ('java/util/AbstractCollection','toArray','()[Ljava/lang/Object;'),
    ('java/lang/module/ModuleDescriptor','newModule','(Ljava/lang/String;)Ljava/lang/module/ModuleDescriptor$Builder;'),
    ('java/lang/module/ModuleDescriptor$Builder','<init>','(Ljava/lang/String;ZLjava/util/Set;)V'),
    ('java/lang/module/ModuleDescriptor$Builder','packages','(Ljava/util/Set;)Ljava/lang/module/ModuleDescriptor$Builder;'),
    ('java/lang/module/ModuleDescriptor$Builder','build','()Ljava/lang/module/ModuleDescriptor;'),
    ('java/lang/Module','<init>','(Ljava/lang/ModuleLayer;Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;Ljava/net/URI;)V'),
    ('java/lang/Module','<init>','(Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;)V'),
    ('java/lang/Module','<init>','(Ljava/lang/ClassLoader;)V'),
    ('java/lang/Module','implAddReads','(Ljava/lang/Module;)V'),('java/lang/Module','canRead','(Ljava/lang/Module;)Z'),
    ('java/lang/Module','implAddExports','(Ljava/lang/String;Ljava/lang/Module;)V'),
    ('java/lang/Module','isExported','(Ljava/lang/String;Ljava/lang/Module;)Z')]


def proc(image,name,result,*arguments):
    value=getattr(image,name);value.restype,value.argtypes=result,arguments;return value


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


def fixtures(summary,classes):
    I=B.module('verify-translation-ir');members=[];owners={}
    for owner in sorted({key[0] for key in JAVA}):
        [cls]=[r for r in classes if r['name']==owner and r['origin']['loader']=='bootstrap']
        raw=I.Source(S.original_class(summary,cls));owners[owner]=cls['id']
        for ident,method in zip(cls['method_ids'],raw.methods):
            if (owner,method['name'],method['descriptor']) not in JAVA:continue
            body=raw.code(method);members.append(dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],
                owner=owner,name=method['name'],descriptor=method['descriptor'],code_sha256=B.C.hashlib.sha256(body['bytes']).hexdigest()))
    S.check(len(members)==len(JAVA),'Original Module fixture inventory differs');return members,owners


def build(candidate_file,selection,native_manifest,native_execution,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated Module output required')
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Normal Module source proof changed')
    candidate=S.read(candidate_file);meta=candidate['metadata'];source=meta['source']
    manifest=selection/'closure.json';proof_file=selection/'selection-verification.json';closure=S.read(manifest);proof=S.read(proof_file)
    native=S.read(native_manifest);native_proof=native_manifest.with_name('verification.json');accepted=S.read(native_proof);observed=S.read(native_execution)
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(manifest)['sha256'] and accepted['verified'] and
        accepted['source_manifest_sha256']==S.digest(native_manifest)['sha256'] and
        observed['source_verification_sha256']==S.digest(native_proof)['sha256'] and Path(native['baseline_directory'])==selection and
        native['accepted_source_verification_sha256']==S.digest(proof_file)['sha256'] and observed['cleanup_flags']==7 and
        observed['worker_failure_state']==0 and closure['source_batch_summary_sha256']==meta['base']['batch_summary']['digest']['sha256'],
        'Original normal source and actual native process evidence required')
    _,summary,classes=S.base(Path(closure['batch']),Path(closure['plan']));members,owners=fixtures(summary,classes)
    for method in source['original_java']+members:
        selected=closure['selected_methods'].get(str(method['method']))
        S.check(selected and selected['class_id']==method['class_id'] and selected['source_sha256']==method['class_sha256'] and
            selected['code_sha256']==method['code_sha256'],'Original Module Java fixture not selected: '+str(method))
    diagnostic=S.read(selection/'diagnostic.json')
    [unit]=[u for u in proof['verified_assembly_objects']['units'] if Path(u['assembly']['path']).name=='diagnostic-stops.asm']
    original=S.checked(unit['assembly']).read_bytes();old_object=S.checked(unit['object'])
    delta=B.module('probe-native-provider-prefix')
    names={'boom_m'+str(m['method']) for m in source['methods']}
    rows=[r for r in diagnostic['rows'] if r['symbol'] in names]
    S.check(len(rows)==len(names) and all(r['category']==2 and r['source_sha256']==next(
        m['class_sha256'] for m in source['methods'] if 'boom_m'+str(m['method'])==r['symbol']) for r in rows),
        'Only exact original Module native stops may be removed')
    remaining,complement=delta.remove_stops(original,rows,True,names)
    lines=(selection/'link.rsp').read_text().splitlines()
    objects=[Path(l[1:-1]) for l in lines if l.startswith('"') and Path(l[1:-1]).suffix.lower()=='.obj']
    libraries=[Path(l[1:-1]) for l in lines if l.startswith('"') and Path(l[1:-1]).suffix.lower()=='.lib']
    S.check(objects.count(old_object)==1,'Original Module stop object must occur once')
    inputs=[S.artifact(p) for p in objects+libraries]
    state=S.read(S.checked(meta['input_state']));runtime=Path(state['runtime'])/'boom-runtime.dll';runtime_meta=S.read(runtime.with_name('runtime.json'))
    S.check(S.digest(runtime)['sha256']==runtime_meta['sha256'] and all(runtime_meta['sources'].get(n)==h for n,h in
        meta['runtime_kernel_sha256'].items()),'Normal Module runtime kernel identity differs')
    exported={l.removeprefix('/EXPORT:') for l in lines if l.startswith('/EXPORT:')}
    L.verify(selection/'link.rsp',profile='diagnostic',output=selection/'diagnostic-image.dll',objects=objects,
        library_choices=L.diagnostic_libraries(runtime,winsock=True),exports=exported)
    output.mkdir(parents=True);asm,obj=output/'remaining-stops.asm',output/'remaining-stops.obj';asm.write_bytes(remaining)
    assembler=Path(candidate['assembler']['path']);linker=assembler.with_name('link.exe')
    with (output/'stops-assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    ex,im=B.A.coff_symbols(old_object);S.check(B.A.coff_symbols(obj)==(ex-names,im),'Non-target stop COFF symbols changed')
    exported|=set(candidate['exports'])|{f"boom_m{m['method']}" for m in source['original_java']+members}
    exported|={f'boom_{kind}{ident}' for kind in ('class','layout') for ident in set(owners.values())|set(source['source_classes'].values())}
    exported|={'boom_heap_ptr','boom_java_string_literals_bind_heap','boom_java_class_pool','boom_java_class_root_count',
        'boom_java_class_roots','boom_java_class_loader_roots','boom_java_class_module_roots','boom_probe_static_roots','boom_probe_static_root_count'}
    exported|={n for pair in ROOT_SPANS for n in pair}
    linked=[obj if p==old_object else p for p in objects]+[S.checked(candidate['object'])]
    dll=output/'module-definitions.dll';response=output/'link.rsp'
    response.write_text('\n'.join([*L.PREFIXES['diagnostic'],'/OUT:"'+str(dll)+'"']+
        ['"'+str(p)+'"' for p in linked+libraries]+['/EXPORT:'+n for n in sorted(exported)])+'\n')
    link_proof=L.verify(response,profile='diagnostic',output=dll,objects=linked,library_choices=[libraries],exports=exported)
    with (output/'link.log').open('wb') as log:
        subprocess.run([linker,'@'+str(response)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    for record in inputs:S.check(S.artifact(record['path'])==record,'Original source/SDK input changed')
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    config=dict(schema=1,scope='unregistered_five_Module_natives_over_historical_verified_normal_source',
        candidate=S.artifact(candidate_file),source_proof=S.artifact(candidate_file.with_name('verification.json')),
        baseline_manifest=S.artifact(manifest),baseline_source_proof=S.artifact(proof_file),baseline_native_manifest=S.artifact(native_manifest),
        baseline_native_proof=S.artifact(native_proof),baseline_native_execution=S.artifact(native_execution),
        original_link_response=S.artifact(selection/'link.rsp'),link_inputs=inputs,complement_source_proof=complement,
        remaining_diagnostic_assembly=S.artifact(asm),remaining_diagnostic_object=S.artifact(obj),
        image=S.artifact(dll),runtime=S.artifact(runtime),link_response=S.artifact(response),link_proof=link_proof,
        execution_tool=S.artifact(Path(__file__)),stop_delta_tool=S.artifact(ROOT/'scripts/probe-native-provider-prefix.py'),
        fixture_methods=members,fixture_classes=owners,oracle_home=str(Path(catalog['image']['path']).parents[1]),oracle_modules=catalog['image'],
        runtime572_modified=False,original_Java_modified=False,only_five_native_stops_removed=True,
        registered_in_shared_runtime=False,executed=False,game_started=False)
    S.write(output/'images.json',config);return output/'images.json'


def recheck(images_file,output):
    S.check(output.resolve().is_relative_to(S.ART) and not output.exists(),'Fresh Module recheck output required')
    config=S.read(images_file)
    for key in ('candidate','source_proof','baseline_manifest','baseline_source_proof','baseline_native_manifest','baseline_native_proof',
        'baseline_native_execution','remaining_diagnostic_assembly','remaining_diagnostic_object','link_response','image','runtime'):S.checked(config[key])
    config['original_images']=S.artifact(images_file);config['producer_execution_tool']=config['execution_tool']
    config['execution_tool']=S.artifact(Path(__file__));config['relinked']=False
    output.mkdir(parents=True);path=output/'images.json';S.write(path,config);return path


def relink(images_file,candidate_file,output):
    """Reuse sealed original Java/stops; replace only the independent candidate COFF."""
    S.check(output.resolve().is_relative_to(S.ART) and not output.exists(),'Fresh Module relink output required')
    old=S.read(images_file);previous=S.read(S.checked(old['candidate']));candidate=S.read(candidate_file)
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')) and
        candidate['metadata']['base']==previous['metadata']['base'] and candidate['metadata']['source']['methods']==previous['metadata']['source']['methods'],
        'Module replacement belongs to another source/frame domain')
    for key in ('baseline_manifest','baseline_source_proof','baseline_native_manifest','baseline_native_proof','baseline_native_execution',
        'remaining_diagnostic_assembly','remaining_diagnostic_object','link_response','image','runtime'):S.checked(old[key])
    for a in old['link_inputs']:S.check(S.artifact(a['path'])==a,'Original Module/SDK link input changed')
    old_object=S.checked(previous['object']);new_object=S.checked(candidate['object'])
    objects=[Path(p) for p in old['link_proof']['objects']];S.check(objects.count(old_object)==1,'Old candidate object must occur once')
    objects=[new_object if p==old_object else p for p in objects]
    libraries=[Path(p) for p in old['link_proof']['libraries']];exports=set(old['link_proof']['exports'])
    exports|={n for pair in ROOT_SPANS for n in pair}
    S.check(set(previous['exports'])==set(candidate['exports']),'Candidate exports changed during source-only relink')
    output.mkdir(parents=True);dll=output/'module-definitions.dll';response=output/'link.rsp'
    response.write_text('\n'.join([*L.PREFIXES['diagnostic'],'/OUT:"'+str(dll)+'"']+['"'+str(p)+'"' for p in objects+libraries]+
        ['/EXPORT:'+n for n in sorted(exports)])+'\n')
    proof=L.verify(response,profile='diagnostic',output=dll,objects=objects,library_choices=[libraries],exports=exports)
    linker=Path(candidate['assembler']['path']).with_name('link.exe')
    with (output/'link.log').open('wb') as log:
        subprocess.run([linker,'@'+str(response)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    config=dict(old,original_images=S.artifact(images_file),producer_execution_tool=old['execution_tool'],
        candidate=S.artifact(candidate_file),source_proof=S.artifact(candidate_file.with_name('verification.json')),
        image=S.artifact(dll),link_response=S.artifact(response),link_proof=proof,execution_tool=S.artifact(Path(__file__)),
        replaced_candidate_object=dict(before=S.artifact(old_object),after=S.artifact(new_object)),original_Java_reassembled=False)
    path=output/'images.json';S.write(path,config);return path


ORACLE='''import java.lang.reflect.*;import java.lang.module.*;import java.util.*;
public class ModuleDefinitionsOracle {
 static Method[] m=new Method[5];static Constructor<Module> unnamedCtor;
 static String hex(String s){StringBuilder b=new StringBuilder();for(char c:s.toCharArray())b.append(String.format("%04x",(int)c));return b.toString();}
 static void call(int op,Object...args)throws Exception {try{m[op].invoke(null,args);System.out.println("OK");}
  catch(InvocationTargetException e){Throwable t=e.getCause();System.out.println(t.getClass().getName()+"\\t"+hex(t.getMessage()==null?"":t.getMessage()));}}
 public static void main(String[] args)throws Exception {
  String[] names={"defineModule0","addReads0","addExports0","addExportsToAll0","addExportsToAllUnnamed0"};
  Class<?>[][] sig={{Module.class,boolean.class,String.class,String.class,Object[].class},{Module.class,Module.class},
   {Module.class,String.class,Module.class},{Module.class,String.class},{Module.class,String.class}};
  for(int i=0;i<5;i++){m[i]=Module.class.getDeclaredMethod(names[i],sig[i]);m[i].setAccessible(true);}
  unnamedCtor=Module.class.getDeclaredConstructor(ClassLoader.class);unnamedCtor.setAccessible(true);Module u=unnamedCtor.newInstance((Object)null);
  Module b=Object.class.getModule(),l=java.util.logging.Logger.class.getModule();
  call(0,null,false,null,null,null);call(0,u,false,null,null,null);call(1,null,null);call(2,null,null,null);call(3,null,null);call(4,null,null);
  call(4,b,null);call(2,b,"missing.package",l);call(4,b,"missing.package");
  call(0,b,false,null,null,b.getDescriptor().packages().toArray());call(0,b,false,null,null,null);
  call(0,b,false,null,null,new Object[]{null});call(0,b,false,null,null,new Object[]{""});
  call(0,b,false,null,null,new Object[]{"bad;"});call(0,b,false,null,null,new Object[]{"a..b"});
  call(0,l,false,null,null,l.getDescriptor().packages().toArray());
 }
}
'''


def oracle(home,output):
    source=output/'ModuleDefinitionsOracle.java';source.write_text(ORACLE)
    process=subprocess.run([home/'bin/java.exe','--add-opens','java.base/java.lang=ALL-UNNAMED',source],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=120)
    (output/'oracle.stdout.txt').write_bytes(process.stdout);(output/'oracle.stderr.txt').write_bytes(process.stderr)
    S.check(process.returncode==0,'Module JDK oracle failed; see oracle.stderr.txt')
    answers=[]
    for line in process.stdout.decode().splitlines():
        if line=='OK':answers.append(dict(ok=True))
        else:
            kind,message=line.split('\t');answers.append(dict(ok=False,error=kind,message=bytes.fromhex(message).decode('utf-16-be','surrogatepass')))
    return answers,dict(java=S.artifact(home/'bin/java.exe'),source=S.artifact(source),stdout=S.artifact(output/'oracle.stdout.txt'),
        stderr=S.artifact(output/'oracle.stderr.txt'))


def run(images_file):
    config=S.read(images_file);S.check(config['execution_tool']==S.artifact(Path(__file__)),'Module execution harness changed')
    candidate=S.read(S.checked(config['candidate']));meta=candidate['metadata']['source']
    S.check(B.verify(S.checked(config['candidate']))==S.read(S.checked(config['source_proof'])),'Module source proof differs')
    for key in ('baseline_manifest','baseline_source_proof','baseline_native_manifest','baseline_native_proof','baseline_native_execution',
        'remaining_diagnostic_assembly','remaining_diagnostic_object','link_response','image'):S.checked(config[key])
    for a in config['link_inputs']:S.check(S.artifact(a['path'])==a,'Sealed normal source/SDK input changed')
    runtime=S.checked(config['runtime'])
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(256<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Module heap bind failed')
    allocate=proc(rt,'boom_object_new',P,P,P,P);arrays=proc(rt,'boom_array_new',P,P,c.c_int,U,P)
    classes=dict(meta['source_classes'],**config['fixture_classes']);members=meta['original_java']+config['fixture_methods']
    methods={(m['owner'],m['name'],m['descriptor']):m['method'] for m in members};natives={m['operation']:m['method'] for m in meta['methods']}
    def call(ident,context,args):return proc(image,'boom_m'+str(ident),Q,P,P)(context,(Q*max(len(args),1))(*args))
    def source(owner,name,descriptor,args):
        context=Context();value=call(methods[owner,name,descriptor],context,args)
        S.check(not context[0] and not context[3],'Original Module Java stopped: '+repr((owner,name,list(context))));return value
    def ensure(name):
        context=Context();proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(classes[name])),context)
        S.check(not context[0],'Original Module class initialization stopped: '+repr((name,list(context))))
    def new(name):
        context=Context();value=allocate(heap,addr(image,'boom_layout'+str(classes[name])),context)
        S.check(value and not context[0],'Normal Module fixture allocation failed');return value
    def string(value):
        raw=value.encode('utf-16-le','surrogatepass');context=Context();chars=arrays(heap,len(raw)//2,5,context)
        S.check(chars and not context[0],'Module char[] allocation failed');c.memmove(chars,raw,len(raw))
        obj=new('java/lang/String');source('java/lang/String','<init>','([C)V',[obj,chars]);return obj
    def text(value):
        chars=source('java/lang/String','toCharArray','()[C',[value])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    ensure('java/lang/String');ensure('java/util/HashSet');ensure('java/lang/module/ModuleDescriptor')
    def set_of(values):
        obj=new('java/util/HashSet');source('java/util/HashSet','<init>','()V',[obj])
        for value in values:source('java/util/HashSet','add','(Ljava/lang/Object;)Z',[obj,value])
        return obj
    def package_array(values):return source('java/util/AbstractCollection','toArray','()[Ljava/lang/Object;',[set_of(values)])
    def descriptor(key):
        builder=new('java/lang/module/ModuleDescriptor$Builder')
        source('java/lang/module/ModuleDescriptor$Builder','<init>','(Ljava/lang/String;ZLjava/util/Set;)V',
            [builder,string(key['name']),0,set_of([])])
        pkgs=set_of([string(p['name'].replace('/','.')) for p in meta['package_keys'] if p['module']==key['id']])
        source('java/lang/module/ModuleDescriptor$Builder','packages','(Ljava/util/Set;)Ljava/lang/module/ModuleDescriptor$Builder;',[builder,pkgs])
        return source('java/lang/module/ModuleDescriptor$Builder','build','()Ljava/lang/module/ModuleDescriptor;',[builder])
    fields={r['name']:r['offset'] for r in meta['module_fields']};pool=addr(image,'boom_java_class_pool')
    row_base=addr(image,'boom_module_definitions_rows');owned=addr(image,'boom_module_definitions_owned_buffers')
    module_roots=addr(image,'boom_java_class_module_roots')
    early=[]
    for name in ('java/lang/String','java/lang/Module'):
        context=Context();mirror=proc(rt,'boom_java_class_load',P,P,P,U)(context,pool,classes[name])
        S.check(mirror and not context[0] and not P.from_address(mirror+U.from_address(pool+100).value).value,
            'Early original Class mirror is not in the permitted java.base-unbound phase');early.append(mirror)
    loader_owner=addr(image,'boom_class'+str(classes['jdk/internal/loader/ClassLoaders']))
    loader_state_before=U.from_address(loader_owner+8).value
    base_key=meta['module_keys'][0];base_descriptor=descriptor(base_key);ensure('java/lang/Module')
    base=new('java/lang/Module')
    source('java/lang/Module','<init>','(Ljava/lang/ModuleLayer;Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;Ljava/net/URI;)V',
        [base,0,0,base_descriptor,0])
    S.check(P.from_address(module_roots).value==base and U.from_address(row_base).value==1 and
        U.from_address(pool+92).value==0 and all(P.from_address(m+U.from_address(pool+100).value).value==base for m in early),
        'Original java.base constructor did not publish the same oop and repair early mirrors')
    S.check(U.from_address(loader_owner+8).value==loader_state_before and not Q.from_address(owned).value,
        'java.base/null path initialized ClassLoaders or retained a native buffer')
    S.write(images_file.parent/'java-base-publication.json',dict(verified=True,original_named_constructor=methods[('java/lang/Module','<init>',
        '(Ljava/lang/ModuleLayer;Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;Ljava/net/URI;)V')],
        same_original_Module_oop=True,early_mirrors_repaired=len(early),ClassLoaders_state_before=loader_state_before,
        ClassLoaders_state_after=U.from_address(loader_owner+8).value,native_owned=0))
    def native(op,args):
        context=Context();result=call(natives[op],context,args)
        S.check(not context[3] and not Q.from_address(owned).value,'Module native frame/buffer leak')
        if not context[0]:return dict(ok=True,result=result)
        if context[0]!=16:return dict(ok=False,context=list(context))
        error=P.from_address(c.addressof(context)+16).value
        owner=next((name for name in B.C.ERRORS if P.from_address(error-8).value==addr(image,'boom_layout'+str(classes[name]))),None)
        S.check(owner,'Native Module failure is not an original typed exception')
        message=source('java/lang/Throwable','getMessage','()Ljava/lang/String;',[error])
        return dict(ok=False,error=owner.replace('/','.'),message=text(message))
    second_key=next(m for m in meta['module_keys'] if m['name']=='java.logging');second_descriptor=descriptor(second_key)
    second=new('java/lang/Module');source('java/lang/Module','<init>',
        '(Ljava/lang/ModuleLayer;Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;Ljava/net/URI;)V',[second,0,0,second_descriptor,0])
    unnamed=new('java/lang/Module');source('java/lang/Module','<init>','(Ljava/lang/ClassLoader;)V',[unnamed,0])
    can_read=proc(image,'boom_module_definitions_can_read',U,P,P,P)
    exported=proc(image,'boom_module_definitions_is_exported',U,P,P,P,P)
    def read(a,b):
        ctx=Context();value=can_read(ctx,a,b);S.check(not ctx[0],'Graph can_read rejected normal modules');return value
    def exp(a,p,b):
        ctx=Context();value=exported(ctx,a,p,b);S.check(not ctx[0],'Graph is_exported rejected normal modules');return value
    package=string('java.lang');other_package=string('java.io')
    whitebox=new('java/lang/Module');source('java/lang/Module','<init>',
        '(Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;)V',[whitebox,0,base_descriptor])
    S.check(read(whitebox,second) and native(2,[whitebox,string('missing.package'),second])['ok'] and
        P.from_address(module_roots).value==base,'Unregistered named whitebox Module did not retain loader unnamed VM-entry semantics')
    S.check(not read(base,second) and read(second,base) and read(base,base) and read(unnamed,second) and
        not exp(base,package,second),'Native Module graph began with fabricated reads/exports')
    S.check(native(1,[base,second])['ok'] and read(base,second),'addReads0 did not add a real read edge')
    S.check(native(1,[base,unnamed])['ok'] and read(base,unnamed) and not read(base,0),
        'Specific unnamed read was conflated with all unnamed')
    S.check(native(1,[base,0])['ok'] and read(base,0),'Null read target did not permit all unnamed modules')
    S.check(native(2,[base,package,second])['ok'] and exp(base,package,second) and not exp(base,package,0),
        'Qualified export was not distinct from unqualified export')
    S.check(native(2,[base,other_package,unnamed])['ok'] and exp(base,other_package,unnamed) and not exp(base,other_package,0),
        'Specific unnamed export was conflated with unqualified export')
    S.check(native(4,[base,package])['ok'] and exp(base,package,unnamed),'All-unnamed export missing')
    S.check(native(3,[base,package])['ok'] and exp(base,package,0),'Unqualified export missing')
    failures=[native(0,[0,0,0,0,0]),native(0,[unnamed,0,0,0,0]),native(1,[0,0]),native(2,[0,0,0]),
        native(3,[0,0]),native(4,[0,0]),native(4,[base,0]),native(2,[base,string('missing.package'),second]),
        native(4,[base,string('missing.package')])]
    full_base_packages=package_array([string(p['name'].replace('/','.')) for p in meta['package_keys'] if p['module']==0])
    failures.append(native(0,[base,0,0,0,full_base_packages]))
    failures.append(native(0,[base,0,0,0,0]))
    for values in ([0],[string('')],[string('bad;')],[string('a..b')]):failures.append(native(0,[base,0,0,0,package_array(values)]))
    full_second_packages=package_array([string(p['name'].replace('/','.')) for p in meta['package_keys'] if p['module']==second_key['id']])
    failures.append(native(0,[second,0,0,0,full_second_packages]))
    S.check(all(not r['ok'] and r.get('error') for r in failures),'A Module invalid argument or duplicate silently succeeded')
    S.check(failures[9]==dict(ok=False,error='java.lang.InternalError',message='Module java.base is already defined'),
        'Duplicate java.base result differs from original VM')
    expected,oracle_proof=oracle(Path(config['oracle_home']),images_file.parent)
    S.write(images_file.parent/'jdk-comparisons.json',dict(actual=failures,JDK=expected,oracle=oracle_proof))
    S.check(failures==expected,'Original Module typed error differs from locked JDK: '+repr(list(zip(failures,expected))))
    # Eight normal Java objects race one definition. The one published object
    # is selected by ASM under the graph lock; the host never chooses a winner.
    race_key=next(m for m in meta['module_keys'] if m['name']=='java.naming');race_descriptor=descriptor(race_key)
    race_packages=package_array([string(p['name'].replace('/','.')) for p in meta['package_keys'] if p['module']==race_key['id']])
    contenders=[]
    for _ in range(8):
        obj=new('java/lang/Module');source('java/lang/Module','<init>',
            '(Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;)V',[obj,0,race_descriptor]);contenders.append(obj)
    define_barrier=Barrier(8)
    version_texts=['candidate-version-\u4e2d-'+str(i) for i in range(8)]
    location_texts=['jrt:/java.naming?test='+str(i) for i in range(8)]
    versions=[string(v) for v in version_texts];locations=[string(v) for v in location_texts]
    def define_worker(index):
        define_barrier.wait();ctx=Context();value=call(natives[0],ctx,[contenders[index],0,versions[index],locations[index],race_packages])
        S.check(not value and not ctx[3],'Concurrent Module definition retained a frame')
        if not ctx[0]:return dict(index=index,OS_thread=get_native_id(),defined=True)
        error=P.from_address(c.addressof(ctx)+16).value
        S.check(ctx[0]==16 and error and P.from_address(error-8).value==addr(image,'boom_layout'+str(classes['java/lang/IllegalStateException'])),
            'Concurrent duplicate is not the original IllegalStateException')
        message=source('java/lang/Throwable','getMessage','()Ljava/lang/String;',[error])
        S.check(text(message)=='Module java.naming is already defined','Concurrent duplicate message differs')
        return dict(index=index,OS_thread=get_native_id(),defined=False)
    with ThreadPoolExecutor(max_workers=8) as executor:definition_race=list(executor.map(define_worker,range(8)))
    winners=[r['index'] for r in definition_race if r['defined']]
    S.check(len(winners)==1 and P.from_address(module_roots+race_key['id']*8).value==contenders[winners[0]] and
        Q.from_address(row_base+race_key['id']*64+32).value==1 and not Q.from_address(owned).value,
        'Concurrent define did not publish precisely one original Module object')
    race_row=row_base+race_key['id']*64;symbols=P.from_address(race_row+48).value
    version_text=version_texts[winners[0]];location_text=location_texts[winners[0]]
    S.check(symbols and U.from_address(race_row+16).value==len(version_text) and U.from_address(race_row+20).value==len(location_text) and
        c.string_at(symbols,len(version_text)*2).decode('utf-16-le')==version_text and
        c.string_at(symbols+8192,len(location_text)*2).decode('utf-16-le')==location_text,
        'Definition did not retain actual Latin1/UTF16 version/location symbols')
    unknown_descriptor=descriptor(dict(name='candidate.dynamic',id=-1))
    unknown=new('java/lang/Module');source('java/lang/Module','<init>',
        '(Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;)V',[unknown,0,unknown_descriptor])
    before_rows=c.string_at(row_base,meta['module_count']*64);before_modules=c.string_at(module_roots,meta['module_count']*8)
    outside=native(0,[unknown,0,0,0,0])
    S.check(not outside['ok'] and outside.get('context',[0])[0]==20 and c.string_at(row_base,len(before_rows))==before_rows and
        c.string_at(module_roots,len(before_modules))==before_modules,'Unsupported dynamic module fabricated a definition or modified the graph')
    barrier=Barrier(8);rounds=32
    def worker(index):
        barrier.wait()
        for _ in range(rounds):
            for op,args in ((1,[base,second]),(2,[base,package,second]),(3,[base,package]),(4,[base,other_package])):
                context=Context();value=call(natives[op],context,args)
                S.check(value==0 and not context[0] and not context[3],'Concurrent native module graph mutation failed')
            S.check(read(base,second) and exp(base,package,second),'Concurrent module graph observation failed')
        return dict(OS_thread=get_native_id(),native_calls=rounds*4)
    with ThreadPoolExecutor(max_workers=8) as executor:workers=list(executor.map(worker,range(8)))
    S.check(len({w['OS_thread'] for w in workers})==8 and not Q.from_address(owned).value,'Module graph concurrency/buffer cleanup failed')
    pending=[]
    for op in range(5):
        context=Context(77,91,0x12345678,0,1,2,3,4);before=list(context)
        S.check(call(natives[op],context,[0,0,0,0,0])==0 and list(context)==before,'Module native changed pending exception');pending.append(op)
    collections=[]
    for iteration in range(2):
        roots=[];spans=[]
        for symbol,count_name in ROOT_SPANS:
            count=Q.from_address(addr(image,count_name)).value;S.check(count<=1048576,'Invalid source root count')
            cells=(Q*count).from_address(addr(image,symbol));values=[v for v in cells if v];roots+=values
            spans.append(dict(symbol=symbol,count=count,non_null=len(values),sha256=B.C.hashlib.sha256(bytes(cells)).hexdigest()))
        roots=list(dict.fromkeys(roots));packed=(Q*len(roots))(*roots)
        freed=proc(rt,'boom_heap_collect',Q,P,P,U)(heap,packed,len(roots))
        S.check(freed!=0xffffffffffffffff,'Quiescent module GC failed')
        for span in spans:
            cells=(Q*span['count']).from_address(addr(image,span['symbol']))
            S.check(B.C.hashlib.sha256(bytes(cells)).hexdigest()==span['sha256'],'GC modified a source root bank')
        for key,obj in ((base_key,base),(second_key,second),(race_key,contenders[winners[0]])):
            S.check(P.from_address(module_roots+key['id']*8).value==obj and proc(rt,'boom_heap_contains',U,P,P)(heap,obj),
                'The original JCLS module root failed to retain its object')
        S.check(read(base,second),'Native module graph changed after source-root GC')
        collections.append(dict(freed_objects=freed,normal_root_spans=spans,additional_test_handles=[],
            source_root_banks_unmodified=True,original_Module_roots_retained=True))
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Module heap destruction failed')
    return dict(schema=1,verified=True,scope='unregistered_normal_Module_definition_read_export_graph_component',images=S.artifact(images_file),
        source_proof=config['source_proof'],java_base_publication=S.artifact(images_file.parent/'java-base-publication.json'),
        named_Module_constructors_executed=['java.base','java.logging'],original_Module_String_HashSet_Builder_Java=True,
        Java_Module_fields_written_by_host=False,old_MODU3_used=False,source_JCLS_root_identity_and_early_mirrors=True,
        private_native_operations_executed=list(range(5)),typed_failures=failures,concurrent=dict(workers=workers,total_native_calls=8*rounds*4),
        definition_race=definition_race,definition_winners=1,explicit_quiescent_GC=collections,
        JDK_comparisons=S.artifact(images_file.parent/'jdk-comparisons.json'),
        pending_exception_operations=pending,native_owned_buffers=0,heap_destroyed=True,additional_Java_oop_roots=False,
        version_location_symbols_preserved=True,nonboot_loader_app_unnamed_binding_executed=False,
        outside_closed_profile=outside,unsupported_definition_left_JCLS_and_rows_unchanged=True,
        automatic_GC=False,dynamic_modules_or_layers_complete=False,runtime572_modified=False,shared_provider_registered=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path);parser.add_argument('--selection',type=Path)
    parser.add_argument('--native-manifest',type=Path);parser.add_argument('--native-execution',type=Path);parser.add_argument('--images',type=Path)
    parser.add_argument('--recheck-images',type=Path);parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--relink-images',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'module-definitions/execution'/uuid4().hex)
    args=parser.parse_args()
    if args.relink_images:
        S.check(args.candidate,'A verified replacement candidate is required')
        images=relink(args.relink_images.resolve(),args.candidate.resolve(),args.output.resolve())
    elif args.recheck_images:images=recheck(args.recheck_images.resolve(),args.output.resolve())
    elif args.images:images=args.images.resolve()
    else:
        S.check(all((args.candidate,args.selection,args.native_manifest,args.native_execution)),'Exact source/native proof inputs required')
        images=build(args.candidate.resolve(),args.selection.resolve(),args.native_manifest.resolve(),args.native_execution.resolve(),args.output)
    if args.build_only:print(images)
    else:
        result=run(images);S.write(images.parent/'execution.json',result);print(images.parent/'execution.json')
