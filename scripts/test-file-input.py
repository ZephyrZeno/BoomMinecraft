"""Execute eight original read-only file natives and Java delegates over formal26 source."""
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
from time import monotonic,sleep
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('file_input_candidate',ROOT/'scripts/file-input-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
S=B.S
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8
ROOTS=[('boom_probe_static_roots','boom_probe_static_root_count'),
    ('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_class_roots','boom_java_class_root_count'),('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),
    ('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),('boom_provider_threads_roots','boom_provider_threads_root_count')]
FIXTURES=[('java/lang/String','<init>','([C)V'),('java/lang/Throwable','getMessage','()Ljava/lang/String;'),
    ('java/io/FileDescriptor','<init>','()V'),('java/io/FileDescriptor','close','()V'),
    ('java/io/FileInputStream','<init>','(Ljava/io/FileDescriptor;)V'),('java/io/FileInputStream','read','()I'),
    ('java/io/FileInputStream','read','([BII)I'),('java/io/FileInputStream','skip','(J)J'),
    ('java/io/FileInputStream','available','()I'),('java/io/FileInputStream','close','()V'),
    ('java/lang/System','setJavaLangAccess','()V'),('java/util/Properties','<init>','()V'),
    ('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;'),
    ('java/lang/System','setProperties','(Ljava/util/Properties;)V')]


def proc(image,name,result,*arguments):
    value=getattr(image,name);value.restype,value.argtypes=result,arguments;return value


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


def fixture_sources(summary,classes):
    I=B.module('verify-translation-ir');rows=[];owners={}
    for owner,name,descriptor in FIXTURES:
        [cls]=[row for row in classes if row['name']==owner and row['origin']['loader']=='bootstrap']
        raw=I.Source(S.original_class(summary,cls))
        [record]=[dict(owner=owner,name=name,descriptor=descriptor,method=ident,class_id=cls['id'],
            class_sha256=cls['origin']['sha256'],code_sha256=hashlib.sha256(raw.code(method)['bytes']).hexdigest())
            for ident,method in zip(cls['method_ids'],raw.methods) if (method['name'],method['descriptor'])==(name,descriptor)]
        rows.append(record);owners[owner]=cls['id']
    return rows,owners


def build(candidate_file,selection,native_manifest,native_execution,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh read-only execution output required')
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Read-only source proof changed')
    candidate=S.read(candidate_file);meta=candidate['metadata'];source=meta['source']
    closure_file=selection/'closure.json';proof_file=selection/'selection-verification.json'
    closure=S.read(closure_file);proof=S.read(proof_file);native=S.read(native_manifest)
    native_proof=native_manifest.with_name('verification.json');receipt=S.read(native_proof);observed=S.read(native_execution)
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(closure_file)['sha256'] and receipt['verified'] and
        receipt['source_manifest_sha256']==S.digest(native_manifest)['sha256'] and
        native['accepted_source_verification_sha256']==S.digest(proof_file)['sha256'] and
        Path(native['baseline_directory'])==selection and observed['source_verification_sha256']==S.digest(native_proof)['sha256'] and
        observed['cleanup_flags']==7 and not observed['worker_failure_state'] and
        closure['source_batch_summary_sha256']==meta['base']['batch_summary']['digest']['sha256'],
        'Exact original accepted source plus actual native process evidence required')
    _,summary,classes=S.base(Path(closure['batch']),Path(closure['plan']));fixtures,owners=fixture_sources(summary,classes)
    for row in source['original_java']+fixtures:
        selected=closure['selected_methods'].get(str(row['method']))
        S.check(selected and selected['class_id']==row['class_id'] and selected['source_sha256']==row['class_sha256'] and
            selected['code_sha256']==row['code_sha256'],'Actual original Java callback/API fixture not selected: '+str(row))
    diagnostic=S.read(selection/'diagnostic.json')
    [unit]=[row for row in proof['verified_assembly_objects']['units'] if Path(row['assembly']['path']).name=='diagnostic-stops.asm']
    stops=S.checked(unit['assembly']).read_text();old_obj=S.checked(unit['object']);removed=[]
    for method in source['methods']:
        name='boom_m'+str(method['method']);[row]=[row for row in diagnostic['rows'] if row['symbol']==name]
        S.check(row['category']==2 and row['source_sha256']==method['class_sha256'],'Read-only replacement must be an original native stop')
        text=(f'PUBLIC {name}\n{name} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
            f' lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{name} ENDP\n')
        S.check(stops.count(text)==1,'Original read-only native stop differs');stops=stops.replace(text,'',1)
        removed.append(dict(symbol=name,original_stop_sha256=hashlib.sha256(text.encode()).hexdigest()))
    lines=(selection/'link.rsp').read_text().splitlines()
    [old_line]=[line for line in lines if line.startswith('"') and Path(line.strip('"')).resolve()==old_obj]
    inputs=[S.artifact(Path(line.strip('"'))) for line in lines if line.startswith('"')]
    exported={line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')}
    exported|=set(candidate['exports'])|{f"boom_m{row['method']}" for row in source['original_java']+fixtures}
    ids=set(owners.values())|set(source['source_classes'].values())
    exported|={f'boom_{kind}{ident}' for ident in ids for kind in ('class','layout')}
    exported|={'boom_heap_ptr','boom_java_string_literals_bind_heap','boom_diagnostic_pool'}
    exported|={f"boom_m{row['method']}" for row in source['native_inventory'] if row['owner']==B.C.FD and row['name']=='getHandle'}
    exported|={name for pair in ROOTS for name in pair}
    output.mkdir(parents=True);asm,obj=output/'remaining-stops.asm',output/'remaining-stops.obj';asm.write_text(stops)
    assembler=Path(candidate['assembler']['path']);linker=assembler.with_name('link.exe')
    def assemble(assembly,target):
        with target.with_suffix('.log').open('wb') as log:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(target),assembly],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    assemble(asm,obj)
    def link(name,provider,extra=(),added_exports=()):
        dll=output/(name+'.dll');rsp=output/(name+'.rsp')
        modified=[('"'+str(obj)+'"' if line==old_line else line) for line in lines if not line.startswith(('/OUT:','/EXPORT:'))]
        modified+=['/OUT:"'+str(dll)+'"','"'+str(provider)+'"']+['"'+str(p)+'"' for p in extra]
        modified+=['/EXPORT:'+name for name in sorted(exported|set(added_exports))];rsp.write_text('\n'.join(modified)+'\n')
        with dll.with_suffix('.log').open('wb') as log:
            subprocess.run([linker,'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
        return dict(image=S.artifact(dll),link_response=S.artifact(rsp))
    normal=link('file-input',S.checked(candidate['object']))
    observed_asm=output/'observed-provider.asm';text=S.checked(candidate['assembly']).read_text()
    observed_text=text
    for name in ('ReadFile','CloseHandle'):
        observed_text=observed_text.replace('EXTERN '+name+':PROC','EXTERN boom_fir_test_'+name+':PROC')
        observed_text=observed_text.replace('call '+name+'\n','call boom_fir_test_'+name+'\n')
    normalized=observed_text.replace('boom_fir_test_ReadFile','ReadFile').replace('boom_fir_test_CloseHandle','CloseHandle')
    S.check(normalized==text,'Observed provider changed a production instruction or datum')
    observed_asm.write_text(observed_text);observed_obj=observed_asm.with_suffix('.obj');assemble(observed_asm,observed_obj)
    A=B.module('windows-canonical-candidate')
    S.check(A.sections(S.checked(candidate['object']))==A.sections(observed_obj),'Observed read/close hook changed production text/data bytes')
    harness=output/'observed-calls.asm';harness.write_text(observer_asm());harness_obj=harness.with_suffix('.obj');assemble(harness,harness_obj)
    watched=link('file-input-observed',observed_obj,[harness_obj],['boom_fir_test_control'])
    for record in inputs:S.check(S.artifact(Path(record['path']))==record,'Original read-only link input changed')
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    config=dict(schema=1,scope='unregistered_eight_readonly_natives_over_original_formal26_source',
        candidate=S.artifact(candidate_file),source_proof=S.artifact(candidate_file.with_name('verification.json')),
        baseline_manifest=S.artifact(closure_file),baseline_source_proof=S.artifact(proof_file),
        baseline_native_manifest=S.artifact(native_manifest),baseline_native_proof=S.artifact(native_proof),
        baseline_native_execution=S.artifact(native_execution),original_link_response=S.artifact(selection/'link.rsp'),
        link_inputs=inputs,removed_native_stops=removed,remaining_stops=[S.artifact(asm),S.artifact(obj)],
        normal=normal,observed=watched,observer_inputs=[S.artifact(p) for p in (observed_asm,observed_obj,harness,harness_obj)],
        observed_code_data_identical=True,observed_only_WinAPI_target_aliases=['ReadFile','CloseHandle'],
        runtime=meta['runtime'],original_fixture_methods=fixtures,fixture_classes=owners,root_spans=ROOTS,
        execution_tool=S.artifact(Path(__file__)),oracle_home=str(Path(catalog['image']['path']).parents[1]),oracle_modules=catalog['image'],
        Java_ASM_COFF_or_vtables_modified=False,host_reference_fields_written=False,formal_provider_registered=False,game_started=False)
    S.write(output/'images.json',config);return output/'images.json'


def observer_asm():
    return '''option casemap:none
EXTERN ReadFile:PROC
EXTERN CloseHandle:PROC
EXTERN SetLastError:PROC
EXTERN WaitOnAddress:PROC
EXTERN WakeByAddressAll:PROC
.data
ALIGN 8
PUBLIC boom_fir_test_control
; gateHandle0,entered8,release12,failClose16,res20,actualRead24,actualClose32.
boom_fir_test_control QWORD 0,0,0,0,0
.code
PUBLIC boom_fir_test_CloseHandle
boom_fir_test_CloseHandle PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 xor eax,eax
 xchg eax,DWORD PTR [boom_fir_test_control+16]
 test eax,eax
 jz fir_observe_close
 mov ecx,5
 call SetLastError
 xor eax,eax
 jmp fir_observe_close_done
fir_observe_close:
 lock inc QWORD PTR [boom_fir_test_control+32]
 call CloseHandle
fir_observe_close_done:
 add rsp,40
 ret
boom_fir_test_CloseHandle ENDP
PUBLIC boom_fir_test_ReadFile
boom_fir_test_ReadFile PROC FRAME
 sub rsp,104
 .allocstack 104
 .endprolog
 mov QWORD PTR [rsp+48],rcx
 mov QWORD PTR [rsp+56],rdx
 mov QWORD PTR [rsp+64],r8
 mov QWORD PTR [rsp+72],r9
 mov rax,QWORD PTR [rsp+144]
 mov QWORD PTR [rsp+80],rax
 cmp QWORD PTR [boom_fir_test_control],rcx
 jne fir_observe_read
 mov DWORD PTR [boom_fir_test_control+8],1
 lea rcx,boom_fir_test_control+8
 call WakeByAddressAll
fir_observe_read_wait:
 cmp DWORD PTR [boom_fir_test_control+12],0
 jne fir_observe_read
 mov DWORD PTR [rsp+88],0
 lea rcx,boom_fir_test_control+12
 lea rdx,[rsp+88]
 mov r8d,4
 mov r9d,-1
 call WaitOnAddress
 jmp fir_observe_read_wait
fir_observe_read:
 lock inc QWORD PTR [boom_fir_test_control+24]
 mov rcx,QWORD PTR [rsp+48]
 mov rdx,QWORD PTR [rsp+56]
 mov r8,QWORD PTR [rsp+64]
 mov r9,QWORD PTR [rsp+72]
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [rsp+32],rax
 call ReadFile
 add rsp,104
 ret
boom_fir_test_ReadFile ENDP
END
'''


def run(images_file,observed=False):
    config=S.read(images_file);S.check(S.artifact(Path(__file__))==config['execution_tool'],'Read-only test tool changed')
    for name in ('source_proof','baseline_manifest','baseline_source_proof','baseline_native_manifest','baseline_native_proof','baseline_native_execution'):
        S.checked(config[name])
    candidate=S.read(S.checked(config['candidate']));meta=candidate['metadata']['source']
    runtime=S.checked(config['runtime']);record=config['observed' if observed else 'normal']
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(record['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Read-only source heap bind failed')
    classes=dict(meta['source_classes'],**config['fixture_classes'])
    methods={(row['owner'],row['name'],row['descriptor']):row['method'] for row in meta['original_java']+config['original_fixture_methods']}
    natives={row['operation']:row['method'] for row in meta['methods']}
    allocate=proc(rt,'boom_object_new',P,P,P,P);arrays=proc(rt,'boom_array_new',P,P,c.c_int,U,P)
    def call(ident,args,context=None):
        context=Context() if context is None else context;packed=(Q*max(1,len(args)))(*[value&0xffffffffffffffff for value in args])
        value=proc(image,'boom_m'+str(ident),Q,P,P)(context,packed);return value,context
    def source(owner,name,descriptor,args):
        value,context=call(methods[owner,name,descriptor],args)
        S.check(not context[0] and not context[3],'Original read-only source method stopped: '+str((owner,name,list(context))));return value
    def ensure(owner):
        context=Context();proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(classes[owner])),context)
        S.check(not context[0],'Read-only original class init stopped: '+str((owner,list(context))))
    def new(owner):
        context=Context();value=allocate(heap,addr(image,'boom_layout'+str(classes[owner])),context)
        S.check(value and not context[0],'Normal read-only source object allocation failed');return value
    def array(size,kind=8):
        context=Context();value=arrays(heap,size,kind,context);S.check(value and not context[0],'Read-only array allocation failed');return value
    ensure('java/lang/String')
    def string(value):
        raw=value.encode('utf-16-le','surrogatepass');chars=array(len(raw)//2,5);c.memmove(chars,raw,len(raw))
        text=new('java/lang/String');source('java/lang/String','<init>','([C)V',[text,chars]);return text
    def text(value):
        if not value:return None
        chars=source('java/lang/String','toCharArray','()[C',[value]);return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    def failure(context,owner):
        error=P.from_address(c.addressof(context)+16).value
        S.check(context[0]==16 and not context[3] and error and P.from_address(error-8).value==addr(image,'boom_layout'+str(classes[owner])),
            'Read-only typed original exception differs: '+str((owner,list(context))))
        return text(source('java/lang/Throwable','getMessage','()Ljava/lang/String;',[error]))
    def native(operation,args,kind=None):
        value,context=call(natives[operation],args)
        if kind is not None:return failure(context,kind)
        S.check(not context[0] and not context[3],'Read-only original native stopped: '+str((operation,list(context))))
        return c.c_int64(value).value
    def source_read(stream):return c.c_int32(source(B.C.OWNER,'read','()I',[stream])).value
    def stream():
        ensure(B.C.FD);fd=new(B.C.FD);source(B.C.FD,'<init>','()V',[fd])
        ensure(B.C.OWNER);value=new(B.C.OWNER);source(B.C.OWNER,'<init>','(Ljava/io/FileDescriptor;)V',[value,fd]);return value,fd
    fixture=images_file.parent/('observed-fixtures' if observed else 'fixtures');fixture.mkdir()
    payload=bytes((i*73+19)&255 for i in range(10037));path=fixture/'MiXeD-\u4e2d\U0001f600.bin';path.write_bytes(payload)
    ensure('java/util/Properties');properties=new('java/util/Properties');source('java/util/Properties','<init>','()V',[properties])
    values={'java.home':config['oracle_home'],'user.dir':str(fixture),'user.home':str(fixture),'user.name':'file-input-test',
        'java.io.tmpdir':str(fixture),'file.separator':'\\','path.separator':';','line.separator':'\r\n','os.name':'Windows 10','os.arch':'amd64',
        'os.version':'10.0','file.encoding':'UTF-8','native.encoding':'UTF-8','sun.jnu.encoding':'UTF-8'}
    for key,value in values.items():source('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;',[properties,string(key),string(value)])
    source('java/lang/System','setProperties','(Ljava/util/Properties;)V',[properties])
    source('java/lang/System','setJavaLangAccess','()V',[])
    fd_handle=next(row['offset'] for row in meta['descriptor']['fields'] if row['name']=='handle')
    root_bank=(Q*4096).from_address(addr(image,'boom_file_input_owner_roots'))
    handles=Q.from_address(addr(image,'boom_file_input_live_handles'));buffers=Q.from_address(addr(image,'boom_file_input_owned_buffers'))
    first,fd=stream();native(0,[first,string(str(path))]);S.check(handles.value==1 and fd in root_bank,'Owned normal FD not published/rooted')
    checks=[]
    def record_check(name,value):checks.append(dict(operation=name,value=value));return value
    record_check('read',source_read(first));record_check('length',native(3,[first]));record_check('position',native(4,[first]))
    small=array(20);c.memset(small,0xa5,20)
    result=c.c_int32(source(B.C.OWNER,'read','([BII)I',[first,small,3,13])).value
    record_check('read_slice',dict(count=result,bytes=c.string_at(small,20).hex()))
    record_check('skip_negative',c.c_int64(source(B.C.OWNER,'skip','(J)J',[first,-5])).value)
    record_check('available',source(B.C.OWNER,'available','()I',[first]))
    large=array(10020);c.memset(large,0xa5,10020)
    count=native(2,[first,large,7,10000]);record_check('read_large',dict(count=count,sha256=hashlib.sha256(c.string_at(large,10020)).hexdigest()))
    count=native(2,[first,large,0,200]);record_check('read_tail',dict(count=count,bytes=c.string_at(large,max(count,0)).hex()))
    record_check('eof',native(1,[first]));record_check('skip_past_EOF',native(5,[first,5000]));record_check('available_past_EOF',native(6,[first]))
    record_check('negative_seek_error',native(5,[first,-15038],'java/io/IOException'))
    source(B.C.OWNER,'close','()V',[first]);source(B.C.OWNER,'close','()V',[first])
    S.check(not handles.value and not buffers.value and fd not in root_bank and Q.from_address(fd+fd_handle).value==0xffffffffffffffff,
        'Original Java close failed to release the exact owned handle/root')
    closed=[]
    for operation,args in [(1,[first]),(2,[first,small,0,1]),(3,[first]),(4,[first]),(5,[first,0]),(6,[first])]:
        message=native(operation,args,'java/io/IOException');S.check(message=='Stream Closed','Closed stream message differs');closed.append(operation)
    S.check(native(2,[first,small,20,0])==0,'Zero read after close must succeed')
    S.check(native(2,[first,0,0,0],'java/lang/NullPointerException') is None,'Null array message differs')
    for offset,length in [(-1,0),(0,-1),(21,0),(19,2),(0x7fffffff,0x7fffffff)]:
        S.check(native(2,[first,small,offset,length],'java/lang/IndexOutOfBoundsException') is None,'Bounds message differs')
    missing=fixture/'missing.bin';bad,_=stream();missing_message=native(0,[bad,string(str(missing))],'java/io/FileNotFoundException')
    directory,_=stream();directory_message=native(0,[directory,string(str(fixture))],'java/io/FileNotFoundException')
    S.check(not handles.value and not buffers.value and not any(root_bank),'Failed open retained an owner/handle/buffer')
    sharing,shared_fd=stream();native(0,[sharing,string(str(path))])
    shared_stream=new(B.C.OWNER);source(B.C.OWNER,'<init>','(Ljava/io/FileDescriptor;)V',[shared_stream,shared_fd])
    S.check(source_read(sharing)==payload[0] and source_read(shared_stream)==payload[1] and native(4,[sharing])==2,
        'Original shared-FD stream constructor/offset differs')
    source(B.C.OWNER,'close','()V',[shared_stream]);source(B.C.OWNER,'close','()V',[sharing])
    S.check(not handles.value and shared_fd not in root_bank and native(1,[sharing],'java/io/IOException')=='Stream Closed',
        'Original FD.otherParents/closeAll did not close the shared owned handle')
    early,early_fd=stream();native(0,[early,string(str(path)+'\0ignored')]);S.check(native(1,[early])==payload[0],'Early-NUL source path differs');native(7,[early_fd])
    long_directory=fixture/('a'*80)/('b'*80)/('c'*80)
    Path('\\\\?\\'+str(long_directory)).mkdir(parents=True)
    long_path=long_directory/'long.bin';Path('\\\\?\\'+str(long_path)).write_bytes(b'\x80long')
    extended,extended_fd=stream();native(0,[extended,string(str(long_path))]);S.check(native(1,[extended])==128,'Extended source path read differs');native(7,[extended_fd])
    # Preserve an existing source error before any object/argv validation.
    pending=Context(9,8,7,0,11,12,13,14);before=list(pending);value,_=call(natives[1],[1],pending)
    S.check(not value and list(pending)==before,'Read-only pending context changed')
    for operation,args,code in [(0,[1,1],7),(1,[1],7),(2,[first,1,0,1],7),(7,[1],7)]:
        _,context=call(natives[operation],args);S.check(context[0]==code and not context[3],'Read-only foreign pointer validation differs')
    unattached,foreign_fd=stream();Q.from_address(foreign_fd+fd_handle).value=0x12345678
    # Deliberately forged unowned scalar handle is a negative storage fixture.
    for operation,args in [(1,[unattached]),(7,[foreign_fd])]:
        _,context=call(natives[operation],args);S.check(context[0]==20,'Unowned handle was adopted')
    Q.from_address(foreign_fd+fd_handle).value=0xffffffffffffffff
    [std_getter]=[row['method'] for row in meta['native_inventory'] if row['owner']==B.C.FD and row['name']=='getHandle']
    protected=[]
    for number in range(3):
        std_handle,context=call(std_getter,[number]);S.check(not context[0],'Original standard-handle getter failed')
        if std_handle==0xffffffffffffffff:continue
        Q.from_address(foreign_fd+fd_handle).value=std_handle
        for operation,args in [(1,[unattached]),(7,[foreign_fd])]:
            _,context=call(natives[operation],args);S.check(context[0]==20,'Unowned standard handle was adopted/closed')
        protected.append(number)
    Q.from_address(foreign_fd+fd_handle).value=0xffffffffffffffff
    path_string=string(str(path))
    concurrency=concurrent_suite(stream,native,root_bank,handles,buffers,path_string,payload,array)
    observer=observed_suite(image,rt,stream,native,root_bank,handles,buffers,fd_handle,path_string,payload) if observed else None
    gc=collect_suite(image,rt,heap,stream,native,root_bank,handles,path_string,config)
    S.check(not handles.value and not buffers.value and not any(root_bank),'Final read-only ownership did not drain')
    S.check(proc(image,'boom_release_trace_pool',U)()==0,'Read-only source trace TLS did not release')
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Read-only source heap retained a monitor/lease')
    protocol=dict(checks=checks,missing_message=missing_message,directory_message=directory_message,
        early_NUL_read=payload[0],long_path_read=128)
    S.write(images_file.parent/('observed-native-suites.json' if observed else 'normal-native-suites.json'),
        dict(scope='actual_native_and_source_Java_suites_JDK_oracle_pending',protocol=protocol,
            concurrency=concurrency,controlled_borrow_close_and_failure=observer,quiescent_GC=gc,
            native_handles=handles.value,native_buffers=buffers.value,owner_roots=0,heap_destroyed=True))
    modules=config['oracle_modules'];module_digest=S.digest(Path(modules['path']))
    S.check(all(module_digest[key]==modules['digest'][key] for key in ('size','sha256')),'Locked oracle modules changed')
    oracle=compare_oracle(Path(config['oracle_home']),fixture,path,long_path,protocol) if not observed else None
    for record in config['link_inputs']:S.check(S.artifact(Path(record['path']))==record,'Original input changed during read-only execution')
    return dict(verified=True,scope='eight_unregistered_original_readonly_file_natives_and_Java_delegates',images=S.artifact(images_file),
        observed=observed,protocol=protocol,JDK_oracle=oracle,closed_stream_ops=closed,typed_null_and_bounds=True,
        original_Java_FD_and_FIS_FD_constructors=True,original_Java_read_skip_available_close=True,
        original_Java_System_setJavaLangAccess_helper=True,System_phase1_executed=False,
        public_FIS_String_constructor_and_FileCleanable_chain=False,host_reference_fields_written=False,
        foreign_scalar_handle_negative_fixture=True,owner_root_spans=meta['native_root_spans'],
        shared_source_FD_parent_tracking_and_closeAll=True,standard_descriptors_protected=protected,
        early_NUL_native_path=True,long_path_UTF16_units=len(str(long_path).encode('utf-16-le'))//2,
        concurrency=concurrency,controlled_borrow_close_and_failure=observer,quiescent_GC=gc,
        owned_handles=0,native_buffers=0,owner_roots=0,trace_released=True,heap_destroyed=True,
        shared_provider_registered=False,runtime_modified=False,full_VM_startup=False,game_started=False)


def concurrent_suite(stream,native,roots,handles,buffers,path,payload,array):
    pairs=[stream() for _ in range(8)];arrays=[array(140) for _ in pairs]
    for value,fd in pairs:native(0,[value,path])
    barrier=Barrier(8,timeout=20)
    def worker(index):
        value,fd=pairs[index];buffer=arrays[index];barrier.wait();position=0
        for turn in range(32):
            S.check(native(2,[value,buffer,3,128])==128 and c.string_at(buffer+3,128)==payload[position:position+128],
                'Concurrent independent readBytes output differs')
            position+=128
            S.check(native(4,[value])==position and native(1,[value])==payload[position],
                'Concurrent independent source position/read0 differs')
            position+=1
            S.check(native(6,[value])==len(payload)-position,'Concurrent available differs')
        native(7,[fd]);return dict(OS_thread_id=get_native_id(),native_calls=129)
    with ThreadPoolExecutor(8) as pool:rows=list(pool.map(worker,range(8)))
    S.check(len({row['OS_thread_id'] for row in rows})==8 and not handles.value and not buffers.value and not any(roots),
        'Concurrent source file ownership failed to drain')
    return dict(OS_threads=8,threads=rows,native_calls=sum(row['native_calls'] for row in rows),
        independent_owned_descriptors=8,shared_offset_within_each_descriptor=True,performance_speedup_claimed=False)


def observed_suite(image,rt,stream,native,roots,handles,buffers,offset,path,payload):
    control=addr(image,'boom_fir_test_control')
    a,fd=stream();b,other=stream();native(0,[a,path]);native(0,[b,path])
    Q.from_address(control).value=Q.from_address(fd+offset).value
    U.from_address(control+8).value=0;U.from_address(control+12).value=0
    wake=proc(c.WinDLL('KernelBase'),'WakeByAddressAll',None,P)
    def wait(predicate,message):
        until=monotonic()+10
        while not predicate() and monotonic()<until:sleep(.005)
        S.check(predicate(),message)
    before=Q.from_address(control+32).value
    with ThreadPoolExecutor(2) as pool:
        reader=pool.submit(native,1,[a]);closer=None
        try:
            wait(lambda:U.from_address(control+8).value==1,'Controlled real ReadFile never entered')
            closer=pool.submit(native,7,[fd])
            wait(lambda:Q.from_address(fd+offset).value==0xffffffffffffffff,
                'Close did not invalidate the source handle before waiting')
            S.check(not closer.done() and Q.from_address(control+32).value==before,
                'CloseHandle ran before the outstanding native borrow finished')
            # A separate real ReadFile must complete while the first is blocked.
            S.check(native(1,[b])==payload[0] and not reader.done() and not closer.done(),
                'Independent file I/O was serialized behind the blocked descriptor')
        finally:
            U.from_address(control+12).value=1;wake(control+12)
        S.check(reader.result(timeout=10)==payload[0] and closer and closer.result(timeout=10)==0,
            'Controlled source read/close did not finish')
    native(7,[other])
    S.check(Q.from_address(addr(image,'boom_file_input_close_waits')).value>0,'Actual borrow wait was not observed')
    cstream,failed=stream();native(0,[cstream,path]);physical_before=Q.from_address(control+32).value
    U.from_address(control+16).value=1
    message=native(7,[failed],'java/io/IOException')
    S.check(handles.value==1 and failed in roots and Q.from_address(failed+offset).value==0xffffffffffffffff and
        Q.from_address(control+32).value==physical_before,'Failed close lost ownership or called real CloseHandle')
    S.check(native(1,[cstream],'java/io/IOException')=='Stream Closed','Failed-owned descriptor accepted a new native borrow')
    native(7,[failed]);native(7,[failed])
    S.check(not handles.value and failed not in roots and Q.from_address(control+32).value==physical_before+1,
        'Close retry failed to release exactly one actually owned handle')
    shared,shared_fd=stream();native(0,[shared,path]);physical_before=Q.from_address(control+32).value
    barrier=Barrier(8,timeout=20)
    def close(index):barrier.wait();native(7,[shared_fd]);return get_native_id()
    with ThreadPoolExecutor(8) as pool:tids=list(pool.map(close,range(8)))
    S.check(len(set(tids))==8 and Q.from_address(control+32).value==physical_before+1 and
        not handles.value and not buffers.value and not any(roots),'Concurrent close released an owned handle more than once')
    return dict(blocked_actual_ReadFile=True,independent_actual_ReadFile_completed_before_release=True,
        source_handle_invalidated_before_wait=True,actual_CloseHandle_after_borrow_finished=True,
        close_waits=Q.from_address(addr(image,'boom_file_input_close_waits')).value,
        injected_close_error=5,injected_error_message=message,failed_owner_retained=True,
        retry_real_CloseHandle_exactly_once=True,concurrent_close_OS_threads=8,concurrent_close_thread_ids=tids,
        concurrent_close_real_CloseHandle_calls=1,production_text_and_data_bytes_identical=True)


def collect_suite(image,rt,heap,stream,native,roots,handles,path,config):
    value,fd=stream();native(0,[value,path]);contains=proc(rt,'boom_heap_contains',U,P,P)
    collect=proc(rt,'boom_heap_collect',Q,P,P,U);records=[]
    def cycle():
        live=[];spans=[]
        for name,count_symbol in config['root_spans']:
            count=Q.from_address(addr(image,count_symbol)).value;S.check(count<=1048576,'Normal source root span exceeds the heap contract')
            bank=(Q*count).from_address(addr(image,name));nonzero=[oop for oop in bank if oop]
            live+=nonzero;spans.append(dict(symbol=name,physical_cells=count,non_null_cells=len(nonzero),
                snapshot_sha256=hashlib.sha256(bytes(bank)).hexdigest()))
        owner_values=[oop for oop in roots if oop];live+=owner_values
        spans.append(dict(symbol='boom_file_input_owner_roots',physical_cells=4096,non_null_cells=len(owner_values),
            snapshot_sha256=hashlib.sha256(bytes(roots)).hexdigest()))
        compact=sorted(set(live));S.check(all(oop in compact for oop in live),'Source root compaction omitted a live oop')
        vector=(Q*len(compact))(*compact);freed=collect(heap,vector,len(compact))
        S.check(freed!=0xffffffffffffffff,'Actual quiescent file owner GC failed')
        for row in spans:
            bank=(Q*row['physical_cells']).from_address(addr(image,row['symbol']))
            S.check(hashlib.sha256(bytes(bank)).hexdigest()==row['snapshot_sha256'],'GC changed a source/native owner root bank')
        records.append(dict(spans=spans,physical_cells=sum(row['physical_cells'] for row in spans),
            non_null_before_deduplication=len(live),unique_oops=len(compact),all_oops_in_compacted_set=True,
            root_vector_sha256=hashlib.sha256(bytes(vector)).hexdigest(),extra_host_roots=[],workers_joined=True,
            source_root_banks_unmodified=True,freed_objects=freed))
    cycle()
    S.check(contains(heap,fd) and contains(heap,value) and fd in roots and native(1,[value])==19,
        'Published normal FD owner root did not retain the original FD.parent/FIS graph')
    native(7,[fd]);S.check(not handles.value and not any(roots),'Explicit close did not remove the native root')
    cycle();S.check(not contains(heap,fd) and not contains(heap,value),'Closed unrooted stream/FD graph was retained')
    return dict(collections=records,actual_quiescent_collections=2,FD_parent_graph_retained_by_native_owner_root=True,
        closed_unrooted_graph_reclaimed=True,root_values_not_host_written=True,automatic_Cleaner_claimed=False)


def compare_oracle(home,fixture,path,long_path,actual):
    source=fixture/'FileInputOracle.java'
    source.write_text('''import java.io.*;import java.lang.reflect.*;import java.util.*;import java.security.*;
class FileInputOracle {
 static String bytes(byte[] b){return HexFormat.of().formatHex(b);}
 static String path(String hex){StringBuilder s=new StringBuilder();for(int i=0;i<hex.length();i+=4)s.append((char)Integer.parseInt(hex.substring(i,i+4),16));return s.toString();}
 static String str(String s){if(s==null)return "NULL";StringBuilder b=new StringBuilder();for(char c:s.toCharArray())b.append("%04x".formatted((int)c));return b.toString();}
 static void out(String n,Object v){System.out.println(n+"\\t"+v);}
 static Method m(String n,Class<?>... t)throws Exception{Method m=FileInputStream.class.getDeclaredMethod(n,t);m.setAccessible(true);return m;}
 public static void main(String[] a)throws Exception{
  for(int i=0;i<a.length;i++)a[i]=path(a[i]);
  Method open=m("open0",String.class),length=m("length0"),position=m("position0"),skip=m("skip0",long.class),read=m("read0");
  FileInputStream f=new FileInputStream(new FileDescriptor());open.invoke(f,a[0]);
  out("read",f.read());out("length",length.invoke(f));out("position",position.invoke(f));
  byte[] b=new byte[20];Arrays.fill(b,(byte)0xa5);int n=f.read(b,3,13);out("read_slice",n+":"+bytes(b));
  out("skip_negative",f.skip(-5));out("available",f.available());
  b=new byte[10020];Arrays.fill(b,(byte)0xa5);n=f.read(b,7,10000);out("read_large",n+":"+bytes(MessageDigest.getInstance("SHA-256").digest(b)));
  n=f.read(b,0,200);out("read_tail",n+":"+bytes(Arrays.copyOf(b,Math.max(n,0))));
  out("eof",read.invoke(f));out("skip_past_EOF",skip.invoke(f,5000L));out("available_past_EOF",f.available());
  try{skip.invoke(f,-15038L);out("negative_seek_error","NO_ERROR");}catch(InvocationTargetException e){out("negative_seek_error",str(e.getCause().getMessage()));}
  f.close();f.close();
  for(int i=1;i<3;i++){f=new FileInputStream(new FileDescriptor());try{open.invoke(f,a[i]);out(i==1?"missing_message":"directory_message","NO_ERROR");}
   catch(InvocationTargetException e){out(i==1?"missing_message":"directory_message",e.getCause().getClass().getName()+":"+str(e.getCause().getMessage()));}finally{f.close();}}
  f=new FileInputStream(new FileDescriptor());open.invoke(f,a[3]);out("early_NUL_read",f.read());f.close();
  f=new FileInputStream(new FileDescriptor());open.invoke(f,a[4]);out("long_path_read",f.read());f.close();
 }
}
''',encoding='ascii')
    process=subprocess.run([home/'bin/java.exe','--add-opens','java.base/java.io=ALL-UNNAMED',source,
        *[str(value).encode('utf-16-be','surrogatepass').hex() for value in (path,fixture/'missing.bin',fixture,str(path)+'\0ignored',long_path)]],
        capture_output=True,timeout=120,check=False,cwd=fixture)
    stdout,stderr=fixture/'oracle.stdout',fixture/'oracle.stderr';stdout.write_bytes(process.stdout);stderr.write_bytes(process.stderr)
    S.check(not process.returncode,'Read-only JDK oracle failed; see '+str(stderr))
    wanted=dict(line.split('\t',1) for line in process.stdout.decode('ascii').splitlines())
    observed={}
    for row in actual['checks']:
        name,value=row['operation'],row['value']
        if isinstance(value,dict):observed[name]=str(value['count'])+':'+value.get('bytes',value.get('sha256'))
        elif isinstance(value,str):observed[name]=value.encode('utf-16-be','surrogatepass').hex()
        else:observed[name]=str(value)
    for name in ('missing_message','directory_message'):
        observed[name]='java.io.FileNotFoundException:'+actual[name].encode('utf-16-be','surrogatepass').hex()
    for name in ('early_NUL_read','long_path_read'):observed[name]=str(actual[name])
    S.check(wanted==observed,'Read-only JDK/source protocol differs: '+repr((wanted,observed)))
    return dict(java=S.artifact(home/'bin/java.exe'),source=S.artifact(source),stdout=S.artifact(stdout),
        original_private_natives_and_public_Java_delegates=True,protocol_cases=len(wanted),verified=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path)
    parser.add_argument('--selection',type=Path);parser.add_argument('--native-manifest',type=Path)
    parser.add_argument('--native-execution',type=Path);parser.add_argument('--images',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'file-input-stream/executions'/uuid4().hex)
    args=parser.parse_args()
    images=args.images.resolve() if args.images else build(args.candidate.resolve(),args.selection.resolve(),
        args.native_manifest.resolve(),args.native_execution.resolve(),args.output)
    result=run(images);result['observed_execution']=run(images,observed=True)
    path=images.parent/('execution-'+uuid4().hex+'.json');S.write(path,result);print(path)
