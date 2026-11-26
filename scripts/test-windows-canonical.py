"""Relink two unregistered canonical natives over an accepted formal26 source image."""
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
spec=importlib.util.spec_from_file_location('windows_canonical_source_candidate',ROOT/'scripts/windows-canonical-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
S=B.S
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8


def proc(image,name,result,*arguments):
    value=getattr(image,name);value.restype,value.argtypes=result,arguments;return value


def addr(image,name):
    return c.addressof(c.c_byte.in_dll(image,name))


def fixture_sources(summary,classes):
    I=B.module('verify-translation-ir')
    wanted=[('java/lang/String','<init>','([C)V'),('java/lang/Throwable','getMessage','()Ljava/lang/String;'),
        ('java/util/Properties','<init>','()V'),
        ('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;'),
        ('java/lang/System','setProperties','(Ljava/util/Properties;)V'),
        ('jdk/internal/misc/Blocker','<clinit>','()V'),
        ('jdk/internal/access/SharedSecrets','getJavaLangAccess','()Ljdk/internal/access/JavaLangAccess;')]
    methods=[];owners={}
    for name,method,descriptor in wanted:
        [cls]=[row for row in classes if row['name']==name and row['origin']['loader']=='bootstrap']
        raw=I.Source(S.original_class(summary,cls))
        [record]=[dict(method=ident,owner=name,class_id=cls['id'],class_sha256=cls['origin']['sha256'],
            name=method,descriptor=descriptor,code_sha256=B.hashlib.sha256(raw.code(m)['bytes']).hexdigest())
            for ident,m in zip(cls['method_ids'],raw.methods) if (m['name'],m['descriptor'])==(method,descriptor)]
        if name=='jdk/internal/misc/Blocker':
            [original]=[m for m in raw.methods if (m['name'],m['descriptor'])==(method,descriptor)]
            record['source_athrow_pcs']=[row['pc'] for row in I.stream(raw.code(original)['bytes']) if row['opcode']==0xbf]
        methods.append(record);owners[name]=cls['id']
    return methods,owners


def build(candidate_file,selection,native_manifest,native_execution,output):
    output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated canonical execution directory required')
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Canonical source proof changed')
    candidate=S.read(candidate_file);meta=candidate['metadata'];source=meta['source']
    manifest=selection/'closure.json';proof_file=selection/'selection-verification.json'
    closure=S.read(manifest);proof=S.read(proof_file)
    native=S.read(native_manifest);native_proof=native_manifest.with_name('verification.json');accepted=S.read(native_proof)
    observed=S.read(native_execution)
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(manifest)['sha256'] and
        accepted['verified'] and accepted['source_manifest_sha256']==S.digest(native_manifest)['sha256'] and
        observed['source_verification_sha256']==S.digest(native_proof)['sha256'] and
        Path(native['baseline_directory'])==selection and native['accepted_source_verification_sha256']==S.digest(proof_file)['sha256'] and
        observed['cleanup_flags']==7 and observed['worker_failure_state']==0 and
        closure['source_batch_summary_sha256']==meta['base']['batch_summary']['digest']['sha256'],
        'Exact original formal source and native process evidence required')
    _,summary,classes=S.base(Path(closure['batch']),Path(closure['plan']))
    fixtures,owners=fixture_sources(summary,classes)
    methods=source['original_java']+fixtures+[source['original_Java_canonicalize']]
    for method in methods:
        selected=closure['selected_methods'].get(str(method['method']))
        S.check(selected and selected['class_id']==method['class_id'] and selected['source_sha256']==method['class_sha256'] and
            selected['code_sha256']==method['code_sha256'],'Original canonical Java callback/API fixture not selected: '+str(method))
    diagnostic=S.read(selection/'diagnostic.json')
    [unit]=[unit for unit in proof['verified_assembly_objects']['units'] if Path(unit['assembly']['path']).name=='diagnostic-stops.asm']
    stops=S.checked(unit['assembly']).read_text();old_obj=S.checked(unit['object'])
    removed=[]
    for method in source['methods']:
        name='boom_m'+str(method['method'])
        [row]=[row for row in diagnostic['rows'] if row['symbol']==name]
        S.check(row['category']==2 and row['source_sha256']==method['class_sha256'],'Replacement must be the exact original native stop')
        text=(f'PUBLIC {name}\n{name} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
            f' lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{name} ENDP\n')
        S.check(stops.count(text)==1,'Original canonical native stop body differs')
        stops=stops.replace(text,'',1);removed.append(dict(symbol=name,original_stop_sha256=B.hashlib.sha256(text.encode()).hexdigest()))
    lines=(selection/'link.rsp').read_text().splitlines()
    [old_line]=[line for line in lines if line.startswith('"') and Path(line.strip('"')).resolve()==old_obj]
    inputs=[S.artifact(Path(line.strip('"'))) for line in lines if line.startswith('"')]
    state=S.read(S.checked(meta['input_state']));runtime=Path(state['runtime'])/'boom-runtime.dll'
    runtime_meta=S.read(runtime.with_name('runtime.json'))
    S.check(S.digest(runtime)['sha256']==runtime_meta['sha256'] and
        all(runtime_meta['sources'].get(name)==sha for name,sha in meta['runtime_kernel_sha256'].items()),
        'Original canonical fixture runtime differs')
    output.mkdir(parents=True)
    asm,obj=output/'remaining-stops.asm',output/'remaining-stops.obj';asm.write_text(stops)
    assembler=Path(candidate['assembler']['path']);linker=assembler.with_name('link.exe')
    with (output/'stops-assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    exported={line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')}
    exported|=set(candidate['exports'])|{f"boom_m{row['method']}" for row in methods}
    exported|={f'boom_layout{ident}' for ident in set(owners.values())|set(source['source_classes'].values())}
    exported|={f'boom_class{ident}' for ident in set(owners.values())|set(source['source_classes'].values())}
    exported|={'boom_heap_ptr','boom_java_string_literals_bind_heap','boom_diagnostic_pool'}
    dll=output/'windows-canonical.dll'
    modified=[('"'+str(obj)+'"' if line==old_line else line) for line in lines if not line.startswith(('/OUT:','/EXPORT:'))]
    modified+=['/OUT:"'+str(dll)+'"','"'+str(S.checked(candidate['object']))+'"']
    modified+=['/EXPORT:'+name for name in sorted(exported)]
    response=output/'link.rsp';response.write_text('\n'.join(modified)+'\n')
    with (output/'link.log').open('wb') as log:
        subprocess.run([linker,'@'+str(response)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    for record in inputs:S.check(S.artifact(record['path'])==record,'An original source link input changed')
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    config=dict(schema=1,scope='unregistered_canonical_candidate_over_formal26_original_source',
        candidate=S.artifact(candidate_file),source_proof=S.artifact(candidate_file.with_name('verification.json')),
        baseline_manifest=S.artifact(manifest),baseline_source_proof=S.artifact(proof_file),
        baseline_native_manifest=S.artifact(native_manifest),baseline_native_proof=S.artifact(native_proof),
        baseline_native_execution=S.artifact(native_execution),original_link_response=S.artifact(selection/'link.rsp'),
        link_inputs=inputs,removed_native_stops=removed,remaining_diagnostic_assembly=S.artifact(asm),remaining_diagnostic_object=S.artifact(obj),
        image=S.artifact(dll),runtime=S.artifact(runtime),link_response=S.artifact(response),execution_tool=S.artifact(Path(__file__)),
        original_API_fixture_methods=fixtures,fixture_classes=owners,
        oracle_home=str(Path(catalog['image']['path']).parents[1]),oracle_modules=catalog['image'],
        normal_String_char_constructor=True,original_Java_ASM_or_COFF_modified=False,
        primitive_runtime572_modified=False,registered_in_shared_runtime=False,executed=False,game_started=False)
    S.write(output/'images.json',config);return output/'images.json'


def oracle(home,work,paths,*,cwd=None,isolate=False):
    work.mkdir(exist_ok=True)
    source=work/'WindowsCanonicalOracle.java'
    source.write_text('''import java.io.*;import java.lang.reflect.*;
class WindowsCanonicalOracle {
 static String hex(String value){StringBuilder b=new StringBuilder();for(int i=0;i<value.length();i++)b.append("%04x".formatted((int)value.charAt(i)));return b.toString();}
 public static void main(String[] paths)throws Exception{
  Class<?> type=Class.forName("java.io.WinNTFileSystem");Constructor<?> ctor=type.getDeclaredConstructor();ctor.setAccessible(true);Object fs=ctor.newInstance();
  Method canonical=fs.getClass().getDeclaredMethod("canonicalize0",String.class);canonical.setAccessible(true);
  Method drive=fs.getClass().getDeclaredMethod("getDriveDirectory",int.class);drive.setAccessible(true);
  for(String encoded:paths){StringBuilder input=new StringBuilder();for(int i=0;i<encoded.length();i+=4)input.append((char)Integer.parseInt(encoded.substring(i,i+4),16));
   try{System.out.println("OK:"+hex((String)canonical.invoke(fs,input.toString())));}
   catch(InvocationTargetException ex){Throwable t=ex.getCause();System.out.println("ERROR:"+t.getClass().getName()+":"+hex(t.getMessage()==null?"":t.getMessage()));}}
  for(int i=-1;i<=27;i++){String value=(String)drive.invoke(fs,i);System.out.println("DRIVE:"+i+":"+(value==null?"NULL":hex(value)));}
 }
}
''',encoding='ascii')
    outputs=[];results=[];drives=None
    for index,values in enumerate(([path] for path in paths) if isolate else [paths]):
        process=subprocess.run([home/'bin/java.exe','--add-opens','java.base/java.io=ALL-UNNAMED',source,
            *[path.encode('utf-16-be','surrogatepass').hex() for path in values]],check=False,capture_output=True,timeout=90,cwd=cwd or work)
        stdout=work/('oracle-'+str(index)+'.stdout');stderr=work/('oracle-'+str(index)+'.stderr')
        stdout.write_bytes(process.stdout);stderr.write_bytes(process.stderr)
        S.check(process.returncode==0,'Canonical oracle failed; see '+str(stderr))
        output=process.stdout.decode('ascii').splitlines()
        S.check(len(output)==len(values)+29,'Locked canonical JNI oracle output differs')
        results+=output[:len(values)]
        observed_drives=output[len(values):]
        S.check(drives is None or drives==observed_drives,'Per-case JDK drive environment changed')
        drives=observed_drives;outputs.append(S.artifact(stdout))
    return results,drives,dict(java=S.artifact(home/'bin/java.exe'),source=S.artifact(source),stdout=outputs,
        separate_JVM_per_canonical_case=isolate,cwd=str(cwd or work))


def run(images_file):
    config=S.read(images_file)
    S.check(S.artifact(Path(__file__))==config['execution_tool'],'Canonical execution tool changed')
    candidate=S.read(S.checked(config['candidate']));meta=candidate['metadata']['source']
    for name in ('source_proof','baseline_manifest','baseline_source_proof','baseline_native_manifest','baseline_native_proof',
                 'baseline_native_execution','remaining_diagnostic_assembly','remaining_diagnostic_object'):
        S.checked(config[name])
    for record in config['link_inputs']:
        S.check(S.artifact(Path(record['path']))==record,'Original canonical link input changed')
    modules=config['oracle_modules'];locked_modules=S.digest(Path(modules['path']))
    S.check(all(locked_modules[key]==modules['digest'][key] for key in ('size','sha256')),
        'Locked JDK module catalog image changed')
    runtime=S.checked(config['runtime'])
    with os.add_dll_directory(str(runtime.parent)):
        rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Source canonical heap bind failed')
    allocate=proc(rt,'boom_object_new',P,P,P,P);arrays=proc(rt,'boom_array_new',P,P,c.c_int,U,P)
    classes=dict(meta['source_classes'],**config['fixture_classes'])
    methods={(row['owner'],row['name'],row['descriptor']):row['method'] for row in
        meta['original_java']+config['original_API_fixture_methods']+[meta['original_Java_canonicalize']]}
    natives={row['operation']:row['method'] for row in meta['methods']}
    def call(ident,context,args,native=False):
        packed=(Q*max(len(args),1))(*args)
        return proc(image,'boom_m'+str(ident)+('_native' if native else ''),Q,P,P)(context,packed)
    def source(owner,name,descriptor,args):
        context=Context();result=call(methods[owner,name,descriptor],context,args)
        S.check(not context[0] and not context[3],'Original canonical Java method stopped: '+str((owner,name,list(context))))
        return result
    def ensure(name):
        context=Context();proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(classes[name])),context)
        S.check(not context[0],'Original canonical fixture initializer stopped: '+str((name,list(context))))
    def new(name):
        context=Context();value=allocate(heap,addr(image,'boom_layout'+str(classes[name])),context)
        S.check(value and not context[0],'Source canonical fixture allocation failed');return value
    string_class='java/lang/String';system='java/lang/System';props_class='java/util/Properties';fs_class='java/io/WinNTFileSystem'
    ensure(string_class)
    def string(value):
        raw=value.encode('utf-16-le','surrogatepass');context=Context();chars=arrays(heap,len(raw)//2,5,context)
        S.check(chars and not context[0],'Source UTF16 char array allocation failed');c.memmove(chars,raw,len(raw))
        text=new(string_class);source(string_class,'<init>','([C)V',[text,chars]);return text
    def text(value):
        chars=source(string_class,'toCharArray','()[C',[value])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    # WinNTFileSystem's original initializer reads System properties. Publish a
    # small API fixture with original Java constructors/setters, never a raw slot.
    ensure(props_class);properties=new(props_class);source(props_class,'<init>','()V',[properties])
    fixture=images_file.parent/'fixtures';fixture.mkdir()
    values={'java.home':config['oracle_home'],'user.home':str(fixture),'user.dir':str(fixture),
        'user.name':'canonical-test','java.io.tmpdir':str(fixture),'file.separator':'\\','path.separator':';',
        'os.name':'Windows 10','os.arch':'amd64','os.version':'10.0',
        'file.encoding':'UTF-8','native.encoding':'UTF-8','sun.jnu.encoding':'UTF-8'}
    for key,value in values.items():source(props_class,'setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;',[properties,string(key),string(value)])
    source(system,'setProperties','(Ljava/util/Properties;)V',[properties])
    ensure(fs_class);receiver=new(fs_class)
    # Receiver is an explicit source-layout storage fixture. These two native
    # methods do not access filesystem instance fields; its ctor is not claimed.
    (fixture/'MiXeD').mkdir();(fixture/'MiXeD'/'FiLe.TxT').write_text('fixture',encoding='ascii')
    (fixture/'中文').mkdir();(fixture/'中文'/'\U0001f600.txt').write_text('fixture',encoding='ascii')
    paths=['.','..',r'MiXeD\FiLe.TxT',r'mixed\file.txt',r'MiXeD\..\Absent.TXT',
        r'MiXeD\Missing\Suffix.TXT','中文/\U0001f600.txt',str(fixture/'mixed'/'file.txt'),
        r'MiXeD\.',r'MiXeD\..',r'MiXeD\trailing.',r'MiXeD\bad*',r'MiXeD\bad?',
        'MiXeD\\FiLe.TxT\0ignored','MiXeD\\\ud800.txt',r'MiXeD\bad:name',r'MiXeD\bad<file']
    prior=Path.cwd();os.chdir(fixture)
    try:
        ordered,drive_ordered,ordered_oracle=oracle(Path(config['oracle_home']),fixture/'oracle-ordered',paths,cwd=fixture)
        expected,drive_expected,oracle_proof=oracle(Path(config['oracle_home']),fixture/'oracle-isolated',paths,cwd=fixture,isolate=True)
        S.check(drive_ordered==drive_expected,'Ordered/isolated drive environment changed')
        owned=addr(image,'boom_windows_canonical_owned_buffers')
        def canonical(value,check_idle=True,java=False):
            ident=methods[fs_class,'canonicalize','(Ljava/lang/String;)Ljava/lang/String;'] if java else natives[0]
            context=Context();result=call(ident,context,[receiver,string(value)])
            S.check(not context[3] and (not check_idle or not Q.from_address(owned).value),
                'Canonical native retained a frame or output buffer')
            if not context[0]:return 'OK:'+text(result).encode('utf-16-be','surrogatepass').hex()
            error=P.from_address(c.addressof(context)+16).value
            S.check(context[0]==16 and error and P.from_address(error-8).value==addr(image,'boom_layout'+str(classes['java/io/IOException'])),
                'Canonical native failure is not the original typed IOException: '+str(list(context)))
            message=source('java/lang/Throwable','getMessage','()Ljava/lang/String;',[error])
            return 'ERROR:java.io.IOException:'+text(message).encode('utf-16-be','surrogatepass').hex()
        actual=[canonical(path) for path in paths]
        differences=[dict(path_UTF16=path.encode('utf-16-be','surrogatepass').hex(),actual=value,JDK_ordered=wanted)
            for path,value,wanted in zip(paths,actual,ordered) if value!=wanted]
        ordered_file=images_file.parent/'ordered-JNI-message-differences.json'
        S.write(ordered_file,dict(ordered_oracle=ordered_oracle,differences=differences,
            complete_JNI_error_message_sequence_compatibility=False,
            logical_failure_reuses_cross_call_GetLastError_history=False))
        S.check(all(row['actual']=='ERROR:java.io.IOException:'+('Bad pathname'.encode('utf-16-be').hex()) and
            row['JDK_ordered'].startswith('ERROR:java.io.IOException:') for row in differences),
            'Ordered canonical mismatch exceeds the declared logical-error TLS-history boundary')
        S.check(actual==expected,'Native canonical source differs from the locked JDK: '+repr(list(zip(paths,actual,expected))))
        primitive=proc(image,'boom_windows_canonical_path',U,P,U,P,U,P)
        format_message=proc(c.WinDLL('kernel32',use_last_error=True),'FormatMessageW',U,U,P,U,U,P,U,P)
        primitive_results=[]
        for path,wanted in zip(paths,expected):
            raw=path.encode('utf-16-le','surrogatepass');input_buffer=c.create_string_buffer(raw+b'\0\0')
            output_buffer=(c.c_uint16*32768)(*([0x5a5a]*32768));count=U(0xffffffff)
            status=primitive(input_buffer,len(raw)//2,output_buffer,32768,c.byref(count))
            if not status:
                S.check(count.value<32768 and not output_buffer[count.value] and
                    'OK:'+c.string_at(output_buffer,count.value*2).decode('utf-16-le','surrogatepass').encode('utf-16-be','surrogatepass').hex()==wanted,
                    'Successful primitive output differs from its source binding')
            else:
                S.check(count.value==0 and all(unit==0x5a5a for unit in output_buffer),
                    'Failed primitive changed the caller output')
                if status==0xffffffff:message='Bad pathname'
                else:
                    S.check(status!=8,'Unplanned primitive native allocation failure')
                    system_message=(c.c_uint16*256)();units=format_message(0x1200,None,status,0,system_message,256,None)
                    message=c.string_at(system_message,units*2).decode('utf-16-le','surrogatepass')
                    if units>3:
                        for suffix in ('\n','\r','.'):
                            if message.endswith(suffix):message=message[:-1]
                S.check(wanted=='ERROR:java.io.IOException:'+message.encode('utf-16-be','surrogatepass').hex(),
                    'Real returned Win32 code/FormatMessage differs from source/JDK error')
            primitive_results.append(dict(path_UTF16=raw.hex(),status=status,output_units=count.value,source_and_JDK=wanted))
        S.check(any(row['status'] not in (0,0xffffffff) for row in primitive_results),
            'At least one actual reportable Win32 error must exercise FormatMessage')
        primitive_file=images_file.parent/'primitive-codes-and-source-results.json'
        S.write(primitive_file,dict(cases=primitive_results,failed_output_unchanged=True,
            exact_real_Win32_code_FormatMessage=True,logical_failure_default='Bad pathname'))
        java_cases=['C:','D:','C:\\','D:\\']
        java_entry=methods[fs_class,'canonicalize','(Ljava/lang/String;)Ljava/lang/String;']
        for path in java_cases:
            argument=string(path);context=Context();result=call(java_entry,context,[receiver,argument])
            S.check(not context[0] and not context[3] and result==argument and text(result)==path,
                'Original Java drive-only canonicalize branch differs')
        drives=[]
        for drive in range(-1,28):
            context=Context();result=call(natives[1],context,[receiver,drive&0xffffffffffffffff])
            S.check(not context[0] and not context[3] and not Q.from_address(owned).value,'Drive native failed or leaked')
            drives.append('DRIVE:'+str(drive)+':'+(text(result).encode('utf-16-be','surrogatepass').hex() if result else 'NULL'))
        S.check(drives==drive_expected,'Drive directory source native differs from JDK')
        for operation,args,wanted in ((0,[0,string('.')],4),(0,[receiver,0],4),(0,[1,string('.')],7),
            (0,[receiver,1],7),(0,[receiver,receiver],7),(1,[0,1],4),(1,[1,1],7)):
            context=Context();S.check(not call(natives[operation],context,args) and context[0]==wanted and not context[3],
                'Canonical argument validation boundary differs')
        preserved=Context(9,4,7,0,11,12,13,14);before=list(preserved)
        S.check(not call(natives[0],preserved,[1,1]) and list(preserved)==before,'Pending canonical context changed')
        barrier=Barrier(8,timeout=20)
        def worker(index):
            barrier.wait()
            for turn in range(20):
                for path,wanted in zip(paths[:10],expected[:10]):S.check(canonical(path,False)==wanted,'Concurrent canonical output differs')
            return get_native_id()
        with ThreadPoolExecutor(8) as workers:tids=list(workers.map(worker,range(8)))
        S.check(len(set(tids))==8 and not Q.from_address(owned).value,'Canonical concurrency/ownership differs')
        # This API property fixture intentionally has not run System phase1.
        # Preserve the actual original Blocker initializer failure; do not
        # install JavaLangAccess or alter a class state to reach the native.
        S.check(source('jdk/internal/access/SharedSecrets','getJavaLangAccess',
            '()Ljdk/internal/access/JavaLangAccess;',[])==0,'API fixture unexpectedly has JavaLangAccess')
        context=Context();result=call(java_entry,context,[receiver,string('.')])
        [blocker]=[row for row in config['original_API_fixture_methods'] if row['owner']=='jdk/internal/misc/Blocker']
        S.check(not result and context[0]==20 and context[1] in blocker['source_athrow_pcs'] and
            context[2]==blocker['method'] and not context[3] and not Q.from_address(owned).value,
            'Original Java entry exceeded the recorded uninitialized JavaLangAccess boundary')
        java_boundary=images_file.parent/'source-Java-entry-boundary.json'
        S.write(java_boundary,dict(original_method=blocker,context=list(context),
            actual_original_Blocker_InternalError_athrow=True,JavaLangAccess_null=True,
            System_phase1_executed=False,source_Java_canonicalize_to_native_path_passed=False,
            class_or_static_state_modified_by_host=False))
    finally:os.chdir(prior)
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Canonical binding retained a monitor/heap lease')
    for record in config['link_inputs']:
        S.check(S.artifact(Path(record['path']))==record,'Original canonical link input changed during execution')
    S.check(S.digest(Path(modules['path']))==locked_modules,'Locked JDK modules changed during oracle execution')
    return dict(schema=1,verified=True,scope='unregistered_two_original_WinNT_native_bindings_and_real_primitive',
        images=S.artifact(images_file),native_methods=[row['method'] for row in meta['methods']],original_String_constructor_and_callbacks=True,
        properties_prepared_by_original_Java_APIs=True,test_receiver_WinNTFileSystem_constructor_executed=False,
        WinNTFileSystem_class_initializer_executed=True,typed_IOException_String_and_Throwable_wrapper=True,
        canonical_JDK_cases=len(paths),drive_JDK_cases=29,JDK_oracle=oracle_proof,ordered_JDK_oracle=ordered_oracle,
        ordered_message_differences=S.artifact(ordered_file),complete_JNI_error_message_sequence_compatibility=False,
        primitive_code_and_message_audit=S.artifact(primitive_file),original_Java_canonicalize_drive_only_cases=len(java_cases),
        source_Java_canonicalize_to_native_path_passed=False,source_Java_entry_boundary=S.artifact(java_boundary),
        logical_failure_default='Bad pathname',real_Win32_message_uses_exact_returned_error=True,
        argument_validation_and_pending_error=True,
        concurrent_OS_threads=8,OS_thread_ids=tids,concurrent_canonical_calls=1600,native_output_buffers=0,heap_destroyed=True,
        runtime572_modified=False,registered_in_shared_runtime=False,full_System_phase1=False,full_VM_startup=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path);parser.add_argument('--selection',type=Path)
    parser.add_argument('--native-manifest',type=Path);parser.add_argument('--native-execution',type=Path)
    parser.add_argument('--images',type=Path);parser.add_argument('--output',type=Path,default=S.ART/'windows-path-canonicalization/executions'/uuid4().hex)
    args=parser.parse_args()
    if args.images:images=args.images.resolve()
    else:
        S.check(all((args.candidate,args.selection,args.native_manifest,args.native_execution)),'Provide exact candidate and original formal source/native evidence')
        images=build(args.candidate.resolve(),args.selection.resolve(),args.native_manifest.resolve(),args.native_execution.resolve(),args.output)
    path=images.parent/('execution-'+uuid4().hex+'.json');S.write(path,run(images));print(path)
