"""Cold original reflection Java over one unregistered normal methods candidate."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from threading import Barrier,get_native_id
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('normal_methods_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('normal-methods-candidate');S=B.S;C=B.C
M=module('vm-entry-source');L=module('canonical-link-response')
D=module('probe-native-provider-prefix')
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8
ROOT_SPANS=[('boom_probe_static_roots','boom_probe_static_root_count'),
    ('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),
    ('boom_java_class_roots','boom_java_class_root_count'),('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),
    ('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),('boom_provider_threads_roots','boom_provider_threads_root_count'),
    ('boom_vm_thread_root_cells','boom_vm_thread_root_count'),('boom_methods_test_roots','boom_methods_test_root_count')]
GETTERS={'getDeclaringClass':'()Ljava/lang/Class;','getName':'()Ljava/lang/String;',
    'getModifiers':'()I','getReturnType':'()Ljava/lang/Class;','getParameterTypes':'()[Ljava/lang/Class;',
    'getExceptionTypes':'()[Ljava/lang/Class;','getParameterCount':'()I','isBridge':'()Z','isSynthetic':'()Z','isVarArgs':'()Z'}
CASES=['java/lang/Object','java/lang/Runnable','java/lang/Enum','java/lang/String','java/lang/Deprecated',
       'java/lang/FunctionalInterface','java/util/function/Function']


def proc(image,name,result,*arguments):
    f=getattr(image,name);f.restype,f.argtypes=result,arguments;return f


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


def compile_asm(text,path,assembler,foreign=frozenset()):
    path.write_text(text,encoding='utf-8',newline='\n');obj=path.with_suffix('.obj')
    with path.with_suffix('.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),path],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    return obj,B.A.coff_symbols(obj,foreign)


TEST_ASM='''option casemap:none
.data
ALIGN 8
PUBLIC boom_methods_test_roots
boom_methods_test_roots QWORD 64 DUP(0)
.const
PUBLIC boom_methods_test_root_count
boom_methods_test_root_count QWORD 64
.code
PUBLIC boom_methods_test_save
boom_methods_test_save PROC
 cmp ecx,64
 jae methods_test_save_bad
 lea rax,boom_methods_test_roots
 mov QWORD PTR [rax+rcx*8],rdx
 mov eax,1
 ret
methods_test_save_bad:
 xor eax,eax
 ret
boom_methods_test_save ENDP
END
'''
TEST_EXPORTS={'boom_methods_test_roots','boom_methods_test_root_count','boom_methods_test_save'}


def test_assembly(model):
    imports={'boom_vm_thread_bootstrap','boom_class_ensure32','boom_vm_thread_bootstrap_pool'}
    imports|={f'boom_class{ident}' for ident in model['prerequisite_classes']}
    procs={'boom_vm_thread_bootstrap','boom_class_ensure32'}
    text='\n'.join(f'EXTERN {name}:{"PROC" if name in procs else "BYTE"}' for name in sorted(imports))+'\n'
    text+=TEST_ASM.removesuffix('END\n')
    text+='PUBLIC boom_methods_test_bootstrap\nboom_methods_test_bootstrap PROC FRAME\n push rbx\n .pushreg rbx\n sub rsp,32\n .allocstack 32\n .endprolog\n mov rbx,rcx\n'
    for ident in model['prerequisite_classes']:
        text+=f' lea rcx,boom_class{ident}\n mov rdx,rbx\n call boom_class_ensure32\n cmp DWORD PTR [rbx],0\n jne methods_test_bootstrap_zero\n'
    text+=' mov rcx,rbx\n lea rdx,boom_vm_thread_bootstrap_pool\n call boom_vm_thread_bootstrap\n jmp methods_test_bootstrap_done\nmethods_test_bootstrap_zero:\n xor eax,eax\nmethods_test_bootstrap_done:\n add rsp,32\n pop rbx\n ret\nboom_methods_test_bootstrap ENDP\nEND\n'
    return text,TEST_EXPORTS|{'boom_methods_test_bootstrap'},imports


def build(candidate_file,native_file,execution_file,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh ignored methods test output required')
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Current methods candidate proof differs')
    candidate=S.read(candidate_file);meta=candidate['metadata']['source'];native=S.read(native_file)
    native_proof_file=native_file.with_name('verification.json');native_proof=S.read(native_proof_file);execution=S.read(execution_file)
    selection=Path(native['baseline_directory']);closure_file=selection/'closure.json';proof_file=selection/'selection-verification.json'
    closure=S.read(closure_file);proof=S.read(proof_file)
    S.check(native_proof['verified'] and native_proof['source_manifest_sha256']==S.digest(native_file)['sha256'] and
        execution['source_verification_sha256']==S.digest(native_proof_file)['sha256'] and
        native['accepted_source_verification_sha256']==S.digest(proof_file)['sha256'] and proof['verified'] and
        proof['closure_manifest_sha256']==S.digest(closure_file)['sha256'] and
        closure['source_batch_summary_sha256']==candidate['metadata']['base']['batch_summary']['digest']['sha256'] and
        execution['cleanup_flags']==7 and execution['worker_failure_state']==0,
        'Accepted full source/native process proof differs')
    _,summary,classes=S.base(Path(closure['batch']),Path(closure['plan']))
    names={row['name']:row for row in classes if row['origin']['loader']=='bootstrap'}
    owners={row['id']:row for row in classes};members={}
    for row in meta['original_java']:members[row['owner'],row['name'],row['descriptor']]=row
    wanted={(C.METHOD,n,d) for n,d in GETTERS.items()}|{
        ('java/lang/String','toCharArray','()[C'),('java/lang/String','<init>','([C)V')}
    for owner in {row[0] for row in wanted}:
        cls=names[owner];raw=C.IR.Source(S.original_class(summary,cls))
        for ident,m in zip(cls['method_ids'],raw.methods):
            key=owner,m['name'],m['descriptor']
            if key not in wanted:continue
            code=raw.code(m);S.check(code is not None,'Original reflection getter has no Java Code')
            members[key]=dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],owner=owner,
                name=m['name'],descriptor=m['descriptor'],code_sha256=hashlib.sha256(code['bytes']).hexdigest())
    S.check(wanted<=members.keys(),'Missing original reflection observation methods')
    for row in members.values():
        selected=closure['selected_methods'].get(str(row['method']))
        S.check(selected and selected['class_id']==row['class_id'] and selected['source_sha256']==row['class_sha256'] and
            selected['code_sha256']==row['code_sha256'],'Original reflection upcall/getter is not selected: '+str(row))
    assembler=Path(candidate['assembler']['path']);output.mkdir(parents=True)
    [stop_unit]=[r for r in proof['verified_assembly_objects']['units'] if Path(r['assembly']['path']).name=='diagnostic-stops.asm']
    original_stops=S.checked(stop_unit['assembly']).read_bytes();old_object=S.checked(stop_unit['object'])
    diagnostic=S.read(selection/'diagnostic.json');target='boom_m'+str(meta['methods'][0]['method'])
    rows=[r for r in diagnostic['rows'] if r['symbol']==target]
    S.check(len(rows)==1 and rows[0]['category']==2,'Expected one original getDeclaredMethods0 native fail-only stop')
    remaining,delta=D.remove_stops(original_stops,rows,closure['diagnostic_context_rows'],{target})
    asm=output/'diagnostic-stops.asm';asm.write_bytes(remaining);obj=asm.with_suffix('.obj')
    with (output/'diagnostic-stops.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    old_defs,old_refs=B.A.coff_symbols(old_object,{'WaitOnAddress','WakeByAddressAll'})
    S.check(B.A.coff_symbols(obj,{'WaitOnAddress','WakeByAddressAll'})==(old_defs-{target},old_refs),
        'Non-target diagnostic actual COFF symbols changed')
    # Preserve the full current owner/root model and all its checks. This image
    # does not call its process entry or owner-opening bootstrap_main. The extra
    # API-only test entry calls the exact source prerequisites + primordial
    # constructor primitive using the compiler-generated 192-byte pool.
    model=M.binding_model(closure,False,signal_control=True);text,imports=M.assembly(model)
    vm_obj,(vm_defs,vm_refs)=compile_asm(text,output/'constructor-vm-entry.asm',assembler,M.FOREIGN|{'Sleep','GetTickCount64'})
    S.check((vm_defs,vm_refs)==(M.entry_exports(model),imports),'Original VM binding actual COFF differs')
    test_text,test_exports,test_imports=test_assembly(model)
    root_obj,(root_defs,root_refs)=compile_asm(test_text,output/'test-root-bank.asm',assembler)
    S.check((root_defs,root_refs)==(test_exports,test_imports),'Test root bank/constructor prefix actual COFF differs')
    units=proof['verified_assembly_objects']['units'];objects=[];inputs=[]
    for unit in units:
        S.checked(unit['assembly']);path=S.checked(unit['object']);objects.append(obj if path==old_object else path)
    objects += [S.checked(r) if isinstance(r,dict) else Path(r) for r in closure['objects']]
    objects += [S.checked(candidate['object']),vm_obj,root_obj]
    runtime=Path(S.read(S.checked(candidate['metadata']['input_state']))['runtime'])/'boom-runtime.dll'
    S.check(S.digest(S.checked(native['runtime']))==S.digest(runtime),'Accepted native/runtime source DLL bytes differ')
    libraries=L.diagnostic_libraries(runtime,winsock=True)[0]
    # Only original source PUBLIC symbols and independently checked extra COFFs.
    exports=set(closure['exports'])|M.entry_exports(model)|test_exports|set(candidate['exports'])
    exports|={f"boom_m{r['method']}" for r in members.values()}
    exports|={f'boom_layout{meta["method_class"]}',f'boom_class{meta["method_class"]}',
        'boom_heap_ptr','boom_java_class_pool','boom_java_platform_properties_pool','boom_java_string_intern_pool',
        'boom_provider_thread_registry','boom_provider_thread_bind','boom_release_trace_pool','boom_trace_pool',
        'boom_java_string_literals_bind_heap','boom_diagnostic_pool'}
    all_defs=set().union(vm_defs,root_defs,set(candidate['exports']))
    for unit in units:
        import re
        all_defs.update(re.findall(rb'(?m)^PUBLIC (boom_\w+)\s*$',S.checked(unit['assembly']).read_bytes()))
    all_defs={s.decode() if isinstance(s,bytes) else s for s in all_defs}
    foreign={'WaitOnAddress','WakeByAddressAll'}
    for p in closure['runtime_provider_packs']:foreign.update(S.read(S.checked(p['manifest'])).get('allowed_foreign_imports',[]))
    for path in closure['objects']:all_defs.update(B.A.coff_symbols(path,foreign)[0])
    spans=[dict(symbol=a,count_symbol=b) for a,b in ROOT_SPANS if {a,b}<=all_defs]
    spans += [dict(symbol=r['symbol'],count=r['count']) for r in closure['selected_provider_native_root_spans']]
    exports|={value for span in spans for key,value in span.items() if key in ('symbol','count_symbol')}
    cold_ids={r['class_id'] for r in closure['selected_classes']}
    for name in CASES:
        ident=names[name]['id']
        if ident in cold_ids:exports.add('boom_class'+str(ident))
    S.check(exports<=all_defs,'Observation export is not in the preserved source or exact extras: '+repr(exports-all_defs))
    dll=output/'normal-methods.dll';response=output/'link.rsp'
    response.write_text('\n'.join([*L.PREFIXES['diagnostic'],'/OUT:"'+str(dll)+'"']+
        ['"'+str(p)+'"' for p in objects+libraries]+['/EXPORT:'+n for n in sorted(exports)])+'\n',encoding='utf-8')
    link=L.verify(response,profile='diagnostic',output=dll,objects=objects,library_choices=[libraries],exports=exports)
    with (output/'link.log').open('wb') as log:
        subprocess.run([assembler.with_name('link.exe'),'@'+str(response)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    S.check(module('diagnostic-closure').pe_exports(dll)==exports,'Actual extra-image PE exports differ')
    types,_,_,_=C.C.inputs(summary,classes)
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    selected_classes={r['class_id']:r for r in closure['selected_classes']}
    for path in [*objects,*libraries,runtime,runtime.with_name('runtime.json'),candidate_file,candidate_file.with_name('verification.json'),
        closure_file,proof_file,selection/'diagnostic.json',native_file,native_proof_file,execution_file,
        ROOT/'scripts/vm-entry-source.py',ROOT/'scripts/canonical-link-response.py',ROOT/'scripts/probe-native-provider-prefix.py',
        Path(__file__),output/'constructor-vm-entry.asm',output/'test-root-bank.asm',response]:inputs.append(S.artifact(path))
    result=dict(schema=1,scope='unregistered_getDeclaredMethods0_over_accepted_31_source_with_constructor_VM_binding',
        candidate=S.artifact(candidate_file),candidate_proof=S.artifact(candidate_file.with_name('verification.json')),
        source_manifest=S.artifact(closure_file),source_proof=S.artifact(proof_file),native_manifest=S.artifact(native_file),
        native_proof=S.artifact(native_proof_file),native_execution=S.artifact(execution_file),image=S.artifact(dll),runtime=S.artifact(runtime),
        link_response=S.artifact(response),link_proof=link,inputs=inputs,execution_tool=S.artifact(Path(__file__)),
        remaining_stops=S.artifact(asm),remaining_stops_object=S.artifact(obj),stop_complement=delta,
        VM_binding=model,VM_binding_assembly=S.artifact(output/'constructor-vm-entry.asm'),VM_binding_object=S.artifact(vm_obj),
        test_root_assembly=S.artifact(output/'test-root-bank.asm'),test_root_object=S.artifact(root_obj),
        fixture_methods=list(members.values()),case_types={name:names[name]['id'] for name in CASES},
        selected_code_classes=sorted({r['class_id'] for r in closure['selected_methods'].values()}),
        selected_case_class_states={str(names[n]['id']):selected_classes[names[n]['id']] for n in CASES if names[n]['id'] in selected_classes},
        type_names={str(r['id']):dict(name=r['name'],loader=r['defining_loader'],kind=r['kind']) for r in types},root_spans=spans,
        oracle_home=str(Path(catalog['image']['path']).parents[1]),oracle_modules=catalog['image'],
        original_Java_or_class_state_modified=False,one_exact_native_stop_removed=True,shared_provider_registered=False,
        system_phase1_requested=False,process_entry_executed=False,executed=False,game_started=False)
    path=output/'images.json';S.write(path,result);return path


ORACLE='''import java.lang.reflect.*;import java.util.*;
class NormalMethodsOracle {
 static String descriptor(Class<?> c){if(c.isArray())return c.getName().replace('.','/');if(!c.isPrimitive())return "L"+c.getName().replace('.','/')+";";
  return c==void.class?"V":c==int.class?"I":c==boolean.class?"Z":c==byte.class?"B":c==char.class?"C":c==short.class?"S":c==long.class?"J":c==float.class?"F":"D";}
 static String signature(Method m){StringBuilder b=new StringBuilder("(");for(Class<?> p:m.getParameterTypes())b.append(descriptor(p));return b.append(')').append(descriptor(m.getReturnType())).toString();}
 public static void main(String[] args)throws Exception{
  Method nativeMethod=Class.class.getDeclaredMethod("getDeclaredMethods0",boolean.class);nativeMethod.setAccessible(true);
  for(String name:args){Class<?> k=Class.forName(name,false,ClassLoader.getSystemClassLoader());
   for(boolean only:new boolean[]{false,true})for(Method m:(Method[])nativeMethod.invoke(k,only)){
    StringJoiner ex=new StringJoiner(",");for(Class<?> e:m.getExceptionTypes())ex.add(e.getName().replace('.','/'));
    System.out.println(name+"\t"+only+"\t"+m.getName()+"\t"+signature(m)+"\t"+m.getModifiers()+"\t"+ex);
   }
  }
 }
}
'''


def oracle(home,names,output):
    source=output/'NormalMethodsOracle.java';source.write_text(ORACLE,encoding='utf-8')
    args=[str(home/'bin/java.exe'),'--add-opens','java.base/java.lang=ALL-UNNAMED',str(source),*names]
    process=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=120)
    stdout=output/'oracle.stdout.txt';stderr=output/'oracle.stderr.txt';stdout.write_bytes(process.stdout);stderr.write_bytes(process.stderr)
    S.check(process.returncode==0,'Locked JDK original method oracle failed')
    rows=[]
    for line in process.stdout.decode('utf-8').splitlines():
        owner,only,name,desc,mods,throws=line.split('\t');rows.append(dict(owner=owner.replace('.','/'),publicOnly=only=='true',
            name=name,descriptor=desc,modifiers=int(mods),exceptions=throws.split(',') if throws else []))
    return rows,dict(java=S.artifact(home/'bin/java.exe'),source=S.artifact(source),stdout=S.artifact(stdout),stderr=S.artifact(stderr))


def recheck(images_file,output):
    """New cold process over the same sealed DLL; preserve the producer tool."""
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh methods recheck directory required')
    old=S.read(images_file);archived=images_file.parent/'producer-test-normal-methods-candidate.py'
    S.check(S.digest(archived)==old['execution_tool']['digest'],'Exact producer test tool archive is missing')
    records=[];changed=0
    for record in old['inputs']:
        if Path(record['path']).resolve()==Path(__file__).resolve():
            S.check(record==old['execution_tool'],'Original execution-tool input seal differs')
            records.extend([S.artifact(archived),S.artifact(Path(__file__))]);changed+=1
        else:D.checked(record);records.append(record)
    S.check(changed==1,'Expected exactly one producer execution-tool input')
    for key in ('image','runtime','candidate','candidate_proof','source_manifest','source_proof','native_manifest',
        'native_proof','native_execution','link_response','remaining_stops','remaining_stops_object','VM_binding_assembly',
        'VM_binding_object','test_root_assembly','test_root_object'):D.checked(old[key])
    output.mkdir(parents=True)
    result=dict(old,producer_images=S.artifact(images_file),producer_execution_tool=S.artifact(archived),
        execution_tool=S.artifact(Path(__file__)),inputs=records,image_relinked=False,
        new_OS_process_and_new_heap_required=True,producer_runtime_failure_not_overwritten=True)
    path=output/'images.json';S.write(path,result);return path


def run(images_file):
    config=S.read(images_file);output=images_file.parent
    S.check(config['execution_tool']==S.artifact(Path(__file__)),'Execution harness changed; build a fresh sealed image')
    for record in config['inputs']:D.checked(record)
    candidate=S.read(S.checked(config['candidate']));meta=candidate['metadata']['source']
    S.check(B.verify(S.checked(config['candidate']))==S.read(S.checked(config['candidate_proof'])),'Current original methods candidate changed')
    runtime=S.checked(config['runtime'])
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Normal methods heap binding failed')
    methods={(r['owner'],r['name'],r['descriptor']):r['method'] for r in config['fixture_methods']}
    source_class_pool=addr(image,'boom_java_class_pool');fields=meta['fields'];types=config['type_names']
    diagnostic=None
    def failure(stage,ctx):
        nonlocal diagnostic
        if not ctx[0]:return
        if diagnostic is None:diagnostic=S.read(Path(config['source_manifest']['path']).parent/'diagnostic.json')
        pool=addr(image,'boom_diagnostic_pool');row_id=U.from_address(pool+32).value
        row=diagnostic['rows'][row_id-1] if U.from_address(pool+8).value==2 and 0<row_id<=len(diagnostic['rows']) else None
        path=output/'first-failure.json'
        if not path.exists():S.write(path,dict(stage=stage,context=list(ctx),row=row,images=S.artifact(images_file)))
        raise ValueError('Original reflection stopped: '+repr((stage,list(ctx),row['symbol'] if row else None)))
    def call(ident,args,ctx=None,check=True):
        ctx=Context() if ctx is None else ctx
        result=proc(image,'boom_m'+str(ident),Q,P,P)(ctx,(Q*max(1,len(args)))(*args))
        if check:failure('boom_m'+str(ident),ctx);S.check(not ctx[3],'Original Java/native source frame depth leaked')
        return ctx,result
    def source(owner,name,desc,args):return call(methods[owner,name,desc],args)[1]
    def mirror(ident):
        ctx=Context();value=proc(rt,'boom_java_class_load',P,P,P,U)(ctx,source_class_pool,ident)
        failure('normal Class mirror '+str(ident),ctx);S.check(value,'Normal source mirror returned null');return value
    def type_id(value):
        ctx=Context();ident=proc(rt,'boom_java_class_typeid',U,P,P,P)(ctx,source_class_pool,value)
        failure('registered Class identity',ctx);return ident
    def array_values(value):
        S.check(value and Q.from_address(value-16).value%8==0,'Normal reference array header differs')
        return list((Q*(Q.from_address(value-16).value//8)).from_address(value))
    def string(value):
        ctx=Context();raw=value.encode('utf-16-le','surrogatepass');buf=c.create_string_buffer(raw)
        result=proc(rt,'boom_java_property_copy',P,P,P,P,U)(ctx,addr(image,'boom_java_platform_properties_pool'),buf,len(raw)//2)
        failure('normal UTF16 String factory',ctx);return result
    def text(value):
        if not value:return None
        chars=source('java/lang/String','toCharArray','()[C',[value])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    def member(value):
        return dict(name=text(Q.from_address(value+fields['name']).value),
            modifiers=U.from_address(value+fields['modifiers']).value,slot=U.from_address(value+fields['slot']).value,
            return_type=type_id(Q.from_address(value+fields['returnType']).value),
            parameters=[type_id(v) for v in array_values(Q.from_address(value+fields['parameterTypes']).value)],
            exceptions=[type_id(v) for v in array_values(Q.from_address(value+fields['exceptionTypes']).value)])
    def raw_bytes(value):return None if not value else c.string_at(value,Q.from_address(value-16).value).hex()
    save=proc(image,'boom_methods_test_save',U,U,P)
    native=meta['methods'][0]['method'];cold=[]
    bank=addr(image,'boom_probe_static_roots');bank_count=Q.from_address(addr(image,'boom_probe_static_root_count')).value
    method_state=addr(image,'boom_class'+str(meta['method_class']))
    S.check(U.from_address(method_state+8).value==0,'Method normal class is not cold')
    for ident,record in config['selected_case_class_states'].items():
        state=addr(image,'boom_class'+ident);root=Q.from_address(state+56).value
        S.check(bank<=root<bank+8*bank_count and not (root-bank)%8 and Q.from_address(root).value==0,
            'Original declaring-class failure cell is outside normal source root span')
        cold.append(dict(class_id=int(ident),initial_state=U.from_address(state+8).value,failure_root_cell=(root-bank)//8))
    ctx=Context();main=proc(image,'boom_methods_test_bootstrap',P,P)(ctx);failure('original primordial constructors',ctx)
    registry=P.from_address(addr(image,'boom_provider_thread_registry')).value
    S.check(main and registry,'Original constructor-only VM bindings failed')
    S.check(U.from_address(addr(image,'boom_vm_system_phase1_called')).value==0,'Cold methods component unexpectedly ran Phase1')
    records_by_owner={}
    for row in meta['records']:records_by_owner.setdefault(row['owner'],[]).append(row)
    answers=[];arrays=[];normal_class_states=[];source_lookup=[];native_calls=0
    for case_index,(name,ident) in enumerate(config['case_types'].items()):
        represented=mirror(ident);state=next((r for r in cold if r['class_id']==ident),None)
        state_before=U.from_address(addr(image,'boom_class'+str(ident))+8).value if state else None
        for only in (False,True):
            expected=[r for r in records_by_owner.get(ident,[]) if not only or r['modifiers']&1]
            S.check(not any(r['unavailable'] for r in expected),'Fixture has unavailable source reflection types')
            _,array=call(native,[represented,int(only)]);native_calls+=1;save(case_index*2+int(only),array);arrays.append(array)
            values=array_values(array);S.check(len(values)==len(expected),'Original native method array count differs')
            for value,row in zip(values,expected):
                actual=member(value)
                S.check(actual=={key:row[key] for key in ('name','modifiers','slot','return_type','parameters','exceptions')},
                    'Original Method metadata does not match the normal object: '+repr((name,row['name'],actual)))
                S.check(Q.from_address(value+fields['clazz']).value==represented and not Q.from_address(value+fields['root']).value,
                    'Native Method declaration/root identity differs')
                S.check(text(Q.from_address(value+fields['signature']).value)==row['signature'] and all(
                    raw_bytes(Q.from_address(value+fields[field]).value)==row[key]
                    for field,key in [('annotations','annotations'),('parameterAnnotations','parameter_annotations'),('annotationDefault','annotation_default')]),
                    'Original generic/annotation bytes were lost or invented')
                S.check(source(C.METHOD,'getName',GETTERS['getName'],[value])==Q.from_address(value+fields['name']).value and
                    source(C.METHOD,'getDeclaringClass',GETTERS['getDeclaringClass'],[value])==represented and
                    source(C.METHOD,'getModifiers',GETTERS['getModifiers'],[value])==row['modifiers'] and
                    type_id(source(C.METHOD,'getReturnType',GETTERS['getReturnType'],[value]))==row['return_type'] and
                    source(C.METHOD,'getParameterCount',GETTERS['getParameterCount'],[value])==len(row['parameters']),
                    'Original Method Java getters do not consume the produced object')
                for method,mask in [('isBridge',0x40),('isSynthetic',0x1000),('isVarArgs',0x80)]:
                    S.check(source(C.METHOD,method,GETTERS[method],[value])==bool(row['modifiers']&mask),'Original source flag getter differs')
                answers.append(dict(owner=name,publicOnly=only,name=row['name'],descriptor=row['descriptor'],modifiers=row['modifiers'],
                    exceptions=[types[str(t)]['name'] for t in row['exceptions']]))
            if not only and values:
                # The real Class API searches its own source cache, then invokes
                # the original ReflectionFactory/Method.copy chain.
                value=values[0];row=expected[0];name_oop=string(row['name']);params=Q.from_address(value+fields['parameterTypes']).value
                for getter,field,key in [('getParameterTypes','parameterTypes','parameters'),('getExceptionTypes','exceptionTypes','exceptions')]:
                    clone=source(C.METHOD,getter,GETTERS[getter],[value])
                    S.check(clone!=Q.from_address(value+fields[field]).value and
                        [type_id(v) for v in array_values(clone)]==row[key],
                        'Original Method array getter did not create an accurate defensive copy')
                copy=source(C.OWNER,'getDeclaredMethod','(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;',
                    [represented,name_oop,params])
                S.check(copy and copy!=value and member(copy)==member(value) and Q.from_address(copy+fields['root']).value,
                    'Original Class.getDeclaredMethod lookup/copy chain was bypassed or incorrect')
                source_lookup.append(dict(owner=name,method=row['name'],descriptor=row['descriptor'],returned_copy=True))
        state_after=U.from_address(addr(image,'boom_class'+str(ident))+8).value if state else None
        S.check(state_before==state_after,'Reflection initialized the represented declaring class')
        normal_class_states.append(dict(class_id=ident,state_before=state_before,state_after=state_after,
            Java_Code_selected=ident in config['selected_code_classes']))
    # Primitive and array mirrors have genuinely empty Method[] results.
    for name in ('I','V','[I','[Ljava/lang/String;'):
        [ident]=[int(i) for i,r in types.items() if r['name']==name and r['loader']=='bootstrap']
        _,value=call(native,[mirror(ident),0]);native_calls+=1;S.check(not array_values(value),'Primitive/array Method[] is not empty')
    expected,oracle_proof=oracle(Path(config['oracle_home']),[n.replace('/','.') for n in config['case_types']],output)
    key=lambda r:(r['owner'],r['publicOnly'],r['name'],r['descriptor'],r['modifiers'],r['exceptions'])
    S.check(sorted(answers,key=key)==sorted(expected,key=key),'Actual original reflected methods differ from locked JDK')
    S.write(output/'jdk-comparisons.json',dict(native=answers,JDK=expected,oracle=oracle_proof,order_required=False))
    # Invalid receivers, malformed publicOnly and an existing pending Context.
    negative=[];valid=mirror(meta['owner'])
    for value,only,kind in [(0,0,4),(1,0,7),(main,0,7),(valid+1,0,7),(valid,2,7)]:
        ctx,result=call(native,[value,only],check=False)
        S.check(not result and ctx[0]==kind and ctx[3]==0,'Native bad receiver/boolean validation differs')
        negative.append(dict(kind=kind,context=list(ctx)))
    ctx=Context(9,4,7,0,11,12,13,14);before=list(ctx)
    _,value=call(native,[valid,0],ctx,False);S.check(not value and list(ctx)==before,'Existing pending Context was replaced')
    barrier=Barrier(8);target=mirror(config['case_types']['java/lang/Runnable']);thread_results=[]
    def work(index):
        barrier.wait();count=0
        for _ in range(16):
            ctx,result=call(native,[target,index&1]);S.check(len(array_values(result))==1,'Concurrent native enumeration differs')
            count+=1
        return dict(OS_thread=get_native_id(),calls=count)
    with ThreadPoolExecutor(max_workers=8) as executor:thread_results=list(executor.map(work,range(8)))
    S.check(len({r['OS_thread'] for r in thread_results})==8,'Eight actual OS workers were not observed')
    collections=[]
    def collect():
        roots=[];spans=[]
        for span in config['root_spans']:
            count=span.get('count')
            if count is None:count=Q.from_address(addr(image,span['count_symbol'])).value
            S.check(count<=1048576,'Normal source root span exceeds the runtime bound')
            base=addr(image,span['symbol']);raw=bytes((Q*count).from_address(base))
            values=[v for v in (Q*count).from_address(base) if v];roots.extend(values)
            spans.append(dict(symbol=span['symbol'],count=count,non_null=len(values),sha256=hashlib.sha256(raw).hexdigest()))
        packed=(Q*max(1,len(roots)))(*roots)
        freed=proc(rt,'boom_heap_collect',Q,P,P,U)(heap,packed,len(roots))
        S.check(freed!=0xffffffffffffffff,'Quiescent collection failed')
        collections.append(dict(spans=spans,non_null_cells=len(roots),freed_objects=freed,automatic_collection=False))
        return freed
    victim=arrays[0];collect()
    S.check(proc(rt,'boom_heap_contains',U,P,P)(heap,victim)==1 and array_values(victim),'Strong native result/root graph was not retained')
    for i in range(64):save(i,0)
    collect();S.check(proc(rt,'boom_heap_contains',U,P,P)(heap,victim)==0,'Unrooted fresh Method[] was retained')
    S.write(output/'pre-oom-progress.json',dict(status='pending_final_allocation_failure_and_cleanup',
        original_Method_constructor_executed=True,original_lookup_copy=source_lookup,
        JDK_method_comparisons=len(answers),workers=thread_results,collections=collections,
        images=S.artifact(images_file),accepted=False,game_started=False))
    # Exercise an allocation failure without writing allocator or class states.
    allocations=[]
    for payload in (1<<18,4096,64,1):
        count=0
        while proc(rt,'boom_heap_alloc',P,P,Q,Q,Q)(heap,payload,0,264):count+=1
        allocations.append(dict(payload_bytes=payload,successful_allocations=count,following_allocation_returned_null=True))
    ctx,result=call(native,[target,0],check=False)
    S.write(output/'allocation-failure-observation.json',dict(allocations=allocations,context=list(ctx),result=result,
        source_or_allocator_fields_written=False))
    S.check(not result and ctx[0]==3 and not ctx[3],'Real heap exhaustion did not preserve native frame/error semantics')
    collect();ctx,result=call(native,[target,0]);S.check(result and len(array_values(result))==1,'Post-GC native service did not recover from OOM')
    collect()
    S.check(proc(rt,'boom_threads_detach',U,P)(registry)==0 and proc(image,'boom_provider_thread_bind',U,P)(None)==0 and
        proc(rt,'boom_threads_destroy',U,P)(registry)==0,'Constructor-only real main Thread registry did not clean up')
    S.check(proc(image,'boom_release_trace_pool',U)()==0,'Normal source frame TLS was not released')
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Normal methods heap destroy failed')
    result=dict(schema=1,verified=True,scope='unregistered_normal_Class_getDeclaredMethods0_native_and_original_Java_lookup_copy_only',
        images=S.artifact(images_file),original_method_records=len(meta['records']),type_capacity=meta['type_capacity'],
        source_native_frame=meta['methods'][0],source_constructor=meta['constructor'],cold_Method_state_before=0,
        normal_declaring_classes=cold,declaring_class_initialization_unchanged=normal_class_states,
        cases=list(config['case_types']),native_enumeration_calls=native_calls+sum(r['calls'] for r in thread_results),
        actual_JDK_method_comparisons=len(answers),JDK_oracle=oracle_proof,raw_original_attributes_verified=True,
        original_Java_lookup_and_copy=source_lookup,worker_OS_threads=thread_results,worker_Thread_start_claimed=False,
        invalid_inputs=negative,existing_pending_Context_preserved=True,quiescent_collections=collections,
        real_allocation_failure_and_recovery=True,normal_source_root_spans_used=True,host_class_or_object_fields_written=False,
        original_Java_Code_modified=False,only_one_native_stop_replaced=True,shared_provider_registered=False,
        represented_class_initializers_invoked_by_native=False,method_invoke0_implemented=False,
        original_annotation_parser_or_generic_repository_execution_claimed=False,system_phase1_executed=False,
        full_VM_bootstrap=False,game_started=False,world_created=False,source_trace_released=True,heap_destroyed=True)
    path=output/'execution.json';S.write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path);parser.add_argument('--native',type=Path);parser.add_argument('--execution',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'normal-methods'/('execution-'+uuid4().hex))
    parser.add_argument('--images',type=Path);parser.add_argument('--worker',type=Path);parser.add_argument('--recheck-images',type=Path)
    args=parser.parse_args()
    if args.worker:print(run(args.worker.resolve()))
    else:
        if args.recheck_images:images=recheck(args.recheck_images.resolve(),args.output.resolve())
        elif args.images:images=args.images.resolve()
        else:images=build(args.candidate.resolve(),args.native.resolve(),args.execution.resolve(),args.output.resolve())
        subprocess.run([os.sys.executable,str(Path(__file__).resolve()),'--worker',str(images)],check=True)
