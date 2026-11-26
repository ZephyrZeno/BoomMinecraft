"""Probe original public FIS(String/File), cleanup registration and explicit close.

Consumes an actually accepted eight-native candidate execution. Only PUBLIC
observation exports are added; Java/native COFF and diagnostic stops stay intact.
String/File attempts run in separate fresh processes and preserve every failure.
"""
import argparse
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic,sleep
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('accepted_readonly_file_test',ROOT/'scripts/test-file-input.py')
T=importlib.util.module_from_spec(spec);spec.loader.exec_module(T)
B,S=T.B,T.S
P,U,Q,Context=T.P,T.U,T.Q,T.Context
proc,addr=T.proc,T.addr
PUBLIC=[('java/io/FileInputStream','<init>','(Ljava/lang/String;)V'),
    ('java/io/FileInputStream','<init>','(Ljava/io/File;)V'),('java/io/File','<init>','(Ljava/lang/String;)V'),
    ('java/io/FileInputStream','getFD','()Ljava/io/FileDescriptor;'),
    ('java/io/FileCleanable','register','(Ljava/io/FileDescriptor;)V'),
    ('java/io/FileDescriptor','unregisterCleanup','()V'),('jdk/internal/ref/PhantomCleanable','clear','()V'),
    ('jdk/internal/ref/CleanerFactory','cleaner','()Ljava/lang/ref/Cleaner;'),
    ('jdk/internal/misc/Unsafe','getUnsafe','()Ljdk/internal/misc/Unsafe;'),
    ('jdk/internal/misc/Unsafe','objectFieldOffset','(Ljava/lang/Class;Ljava/lang/String;)J')]
OBSERVE={'java/io/File','java/io/FileInputStream','java/io/FileDescriptor','java/io/FileCleanable',
    'jdk/internal/ref/CleanerFactory','jdk/internal/ref/CleanerImpl','jdk/internal/ref/PhantomCleanable',
    'java/lang/ref/Cleaner','java/lang/ref/Reference','java/lang/Thread','java/lang/ThreadGroup',
    'jdk/internal/misc/InnocuousThread','jdk/internal/misc/Unsafe'}
OWNER_EXPORTS={'boom_public_owner_open','boom_public_owner_close','boom_public_owner_status'}


def owner_asm():
    # Same owner order as native/entry/vm_process.asm.inc. Calls are existing
    # source-verified runtime APIs, not Java field/initializer substitutions.
    return '''option casemap:none
EXTERN boom_provider_reference_pool:BYTE
EXTERN boom_provider_reference_open:PROC
EXTERN boom_provider_reference_boundary:PROC
EXTERN boom_provider_reference_stop:PROC
EXTERN boom_provider_reference_close:PROC
EXTERN boom_provider_threads_control_binding:BYTE
EXTERN boom_provider_object_wait_pool:BYTE
EXTERN boom_provider_object_wait_open:PROC
EXTERN boom_provider_object_wait_stop:PROC
EXTERN boom_provider_object_wait_close:PROC
EXTERN boom_provider_threads_pool:BYTE
EXTERN boom_provider_threads_close:PROC
EXTERN boom_provider_thread_registry:BYTE
EXTERN boom_provider_thread_bind:PROC
EXTERN boom_threads_detach:PROC
EXTERN boom_threads_destroy:PROC
EXTERN boom_vm_bootstrap_main:PROC
EXTERN GetTickCount64:PROC
EXTERN Sleep:PROC
.data
PUBLIC boom_public_owner_status
boom_public_owner_status DWORD 0,0
.code
PUBLIC boom_public_owner_open
boom_public_owner_open PROC FRAME
 push rbx
 .pushreg rbx
 sub rsp,64
 .allocstack 64
 .endprolog
 mov rbx,rcx
 lea rcx,boom_provider_reference_pool
 call boom_provider_reference_open
 test eax,eax
 jnz pub_owner_open_bad
 mov DWORD PTR [boom_public_owner_status],1
 lea rax,boom_provider_reference_pool
 mov QWORD PTR [boom_provider_threads_control_binding+8],rax
 lea rax,boom_provider_reference_boundary
 mov QWORD PTR [boom_provider_threads_control_binding],rax
 mov rcx,rbx
 call boom_vm_bootstrap_main
 cmp DWORD PTR [rbx],0
 jne pub_owner_open_zero
 test rax,rax
 jz pub_owner_open_bad
 mov QWORD PTR [rsp+32],rax
 mov DWORD PTR [boom_public_owner_status],2
 lea rcx,boom_provider_object_wait_pool
 call boom_provider_object_wait_open
 test eax,eax
 jnz pub_owner_open_bad
 mov DWORD PTR [boom_public_owner_status],3
 mov rax,QWORD PTR [rsp+32]
 jmp pub_owner_open_done
pub_owner_open_bad:
 mov DWORD PTR [boom_public_owner_status+4],eax
 mov DWORD PTR [rbx],7
pub_owner_open_zero:
 xor eax,eax
pub_owner_open_done:
 add rsp,64
 pop rbx
 ret
boom_public_owner_open ENDP
PUBLIC boom_public_owner_close
boom_public_owner_close PROC FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov esi,DWORD PTR [boom_public_owner_status]
 test esi,esi
 jz pub_owner_close_success
 cmp esi,4
 je pub_owner_close_success
 mov rcx,rbx
 lea rdx,boom_provider_reference_pool
 call boom_provider_reference_boundary
 lea rcx,boom_provider_reference_pool
 call boom_provider_reference_stop
 test eax,eax
 jnz pub_owner_close_done
 cmp esi,3
 jb pub_owner_close_threads
 lea rcx,boom_provider_object_wait_pool
 call boom_provider_object_wait_stop
 test eax,eax
 jnz pub_owner_close_done
pub_owner_close_threads:
 call GetTickCount64
 add rax,20000
 mov QWORD PTR [rsp+32],rax
pub_owner_close_loop:
 lea rcx,boom_provider_threads_pool
 call boom_provider_threads_close
 test eax,eax
 jz pub_owner_threads_closed
 cmp eax,170
 jne pub_owner_close_done
 call GetTickCount64
 cmp rax,QWORD PTR [rsp+32]
 jae pub_owner_close_timeout
 mov ecx,1
 call Sleep
 jmp pub_owner_close_loop
pub_owner_close_timeout:
 mov eax,170
 jmp pub_owner_close_done
pub_owner_threads_closed:
 mov QWORD PTR [boom_provider_threads_control_binding],0
 mov QWORD PTR [boom_provider_threads_control_binding+8],0
 cmp esi,3
 jb pub_owner_close_reference
 lea rcx,boom_provider_object_wait_pool
 call boom_provider_object_wait_close
 test eax,eax
 jnz pub_owner_close_done
pub_owner_close_reference:
 lea rcx,boom_provider_reference_pool
 call boom_provider_reference_close
 test eax,eax
 jnz pub_owner_close_done
 mov rdi,QWORD PTR [boom_provider_thread_registry]
 test rdi,rdi
 jz pub_owner_close_publish
 mov rcx,rdi
 call boom_threads_detach
 test eax,eax
 jnz pub_owner_close_done
 xor ecx,ecx
 call boom_provider_thread_bind
 test eax,eax
 jnz pub_owner_close_done
 mov rcx,rdi
 call boom_threads_destroy
 test eax,eax
 jnz pub_owner_close_done
pub_owner_close_publish:
 mov DWORD PTR [boom_public_owner_status],4
pub_owner_close_success:
 xor eax,eax
pub_owner_close_done:
 add rsp,48
 pop rdi
 pop rsi
 pop rbx
 ret
boom_public_owner_close ENDP
END
'''


class SourceFailure(Exception):pass


def source_model(config):
    closure=S.read(S.checked(config['baseline_manifest']));state=S.read(S.checked(S.read(S.checked(config['candidate']))['metadata']['input_state']))
    _,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    wanted=OBSERVE|{row[0] for row in PUBLIC+T.FIXTURES+B.C.JAVA}
    owners={row['name']:row for row in classes if row['origin']['loader']=='bootstrap' and row['name'] in wanted}
    S.check(set(owners)==wanted,'Public FIS source class inventory missing')
    I=B.module('verify-translation-ir');members=[]
    for name,cls in owners.items():
        raw=I.Source(S.original_class(summary,cls))
        S.check(raw.name==name and len(raw.methods)==len(cls['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==cls['fields'],'Public FIS original class identity differs')
        for ident,method in zip(cls['method_ids'],raw.methods):
            if (name,method['name'],method['descriptor']) not in PUBLIC+T.FIXTURES+B.C.JAVA:continue
            code=raw.code(method)
            S.check(code is not None,'Public FIS requested method is not original Java Code')
            row=dict(owner=name,name=method['name'],descriptor=method['descriptor'],method=ident,class_id=cls['id'],
                class_sha256=cls['origin']['sha256'],code_sha256=hashlib.sha256(code['bytes']).hexdigest())
            selected=closure['selected_methods'].get(str(ident))
            S.check(selected and selected['class_id']==cls['id'] and selected['source_sha256']==row['class_sha256'] and
                selected['code_sha256']==row['code_sha256'],'Public FIS additional original Java method not selected: '+str(row))
            members.append(row)
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layouts={row['class_id']:row for line in stream if (row:=json.loads(line))['class_id'] in {cls['id'] for cls in owners.values()}}
    def field(owner,name,descriptor,receiver=None):
        cls=owners[owner];receiver=owner if receiver is None else receiver
        [index]=[i for i,row in enumerate(cls['fields']) if (row['name'],row['descriptor'])==(name,descriptor)]
        layout=layouts[owners[receiver]['id']]
        S.check(layout['diagnostic'] is None and layout['source_sha256']==owners[receiver]['origin']['sha256'],
            'Public FIS normal observation receiver layout unavailable')
        [row]=[row for row in layout['candidate']['fields'] if row['member']['owner']==cls['id'] and row['member']['index']==index]
        ref=descriptor[0] in ('L','[');width=8 if ref or descriptor=='J' else 4 if descriptor=='I' else 1
        S.check(row['storage_bytes']==width and row['reference']==ref and row['offset']%width==0 and
            row['offset']+width<=layout['candidate']['payload_bytes'] and
            (row['offset']<layout['candidate']['reference_prefix']*8)==ref,'Public FIS observation field map differs')
        return dict(owner=owner,receiver=receiver,name=name,descriptor=descriptor,offset=row['offset'],width=width,reference=ref)
    fields=[field(B.C.OWNER,'fd','Ljava/io/FileDescriptor;'),field(B.C.FD,'handle','J'),
        field(B.C.FD,'cleanup','Ljdk/internal/ref/PhantomCleanable;'),field(B.C.FD,'parent','Ljava/io/Closeable;'),
        field('java/io/FileCleanable','fd','I'),field('java/io/FileCleanable','handle','J'),
        field('java/lang/ref/Reference','referent','Ljava/lang/Object;','java/io/FileCleanable'),
        field('jdk/internal/ref/PhantomCleanable','prev','Ljdk/internal/ref/PhantomCleanable;','java/io/FileCleanable'),
        field('jdk/internal/ref/PhantomCleanable','next','Ljdk/internal/ref/PhantomCleanable;','java/io/FileCleanable')]
    innocuous=owners['jdk/internal/misc/InnocuousThread'];raw=I.Source(S.original_class(summary,innocuous))
    [clinit]=[row for row in raw.methods if row['name']=='<clinit>']
    literal_probes=[]
    for instruction in I.stream(raw.code(clinit)['bytes']):
        if instruction['opcode'] not in (0x12,0x13):continue
        constant=instruction['operand']['Constant'];symbol=raw.symbol(constant)
        if symbol.get('Class') not in ('java/lang/Thread','java/lang/ThreadGroup') and 'StringUtf16' not in symbol:continue
        if 'StringUtf16' in symbol and symbol['StringUtf16']!=list(map(ord,'parent')):continue
        literal_probes.append(dict(pc=instruction['pc'],constant=constant,source_symbol=symbol,
            symbol=f"boom_batch_literal_load_{innocuous['id']}_{constant}"))
    [current]=[row for row in closure['selected_runtime_provider_natives'].values() if
        (row['owner'],row['name'],row['descriptor'])==('java/lang/Thread','currentThread','()Ljava/lang/Thread;')]
    return dict(classes={name:cls['id'] for name,cls in owners.items()},members=members,fields=fields,
        literal_probes=literal_probes,source_currentThread=current,
        original_source_selected=True,source_Code_or_COFF_added=False,host_reference_fields_written=False)


def build(accepted_result,output,primordial=False):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh public FIS output required')
    accepted=S.read(accepted_result)
    S.check(accepted['verified'] and accepted['observed_execution']['verified'] and
        accepted['original_Java_read_skip_available_close'] and not accepted['owned_handles'] and accepted['heap_destroyed'],
        'Public FIS requires an actually completed normal/observed eight-native suite')
    images=S.checked(accepted['images']);config=S.read(images)
    for name in ('candidate','source_proof','baseline_manifest','baseline_source_proof','baseline_native_manifest',
                 'baseline_native_proof','baseline_native_execution'):S.checked(config[name])
    candidate=S.read(S.checked(config['candidate']));S.check(B.verify(S.checked(config['candidate']))==S.read(S.checked(config['source_proof'])),
        'Frozen read-only candidate no longer verifies')
    S.check(S.artifact(Path(T.__file__))==config['execution_tool'],'Accepted eight-native execution tool changed')
    model=source_model(config);output.mkdir(parents=True)
    original_rsp=S.checked(config['normal']['link_response']);lines=original_rsp.read_text().splitlines()
    objects=[S.artifact(Path(line.strip('"'))) for line in lines if line.startswith('"')]
    exports={line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')}
    exports|={f"boom_m{row['method']}" for row in model['members']}
    exports|={row['symbol'] for row in model['literal_probes']}
    exports|={f'boom_{kind}{ident}' for ident in model['classes'].values() for kind in ('class','layout')}
    extra=[];binding=None
    if primordial:
        M=B.module('vm-entry-source');closure=S.read(S.checked(config['baseline_manifest']))
        vm_model=M.binding_model(closure,False);text,imports=M.assembly(vm_model)
        assembler=Path(candidate['assembler']['path']);units=[]
        for name,body,expected in [('primordial',text,M.EXPORTS),('public-owner',owner_asm(),OWNER_EXPORTS)]:
            assembly=output/(name+'.asm');obj=assembly.with_suffix('.obj');assembly.write_text(body)
            with obj.with_suffix('.log').open('wb') as log:
                subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),assembly],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
            actual,undefined=B.A.coff_symbols(obj,M.FOREIGN|{'GetTickCount64','Sleep'})
            S.check(actual==expected and (name!='primordial' or undefined==imports),'Public VM helper actual COFF contract differs')
            units.append(dict(assembly=S.artifact(assembly),object=S.artifact(obj),exports=sorted(actual),imports=sorted(undefined)))
            extra.append('"'+str(obj)+'"');objects.append(S.artifact(obj));exports|=actual
        exports|={'boom_provider_thread_registry','boom_provider_thread_bind','boom_provider_threads_pool',
            'boom_provider_threads_close','boom_provider_object_wait_pool','boom_provider_reference_pool'}
        binding=dict(model=vm_model,generator=S.artifact(Path(M.__file__)),
            vm_template=S.artifact(ROOT/'native/entry/vm_process.asm.inc'),units=units,
            source_Java_constructors_unmodified=True,helper_scope='primordial_and_native_worker_wait_shutdown_only')
    dll=output/'public-file-input.dll';rsp=output/'link.rsp'
    rsp.write_text('\n'.join([line for line in lines if not line.startswith(('/OUT:','/EXPORT:'))]+extra+
        ['/OUT:"'+str(dll)+'"']+['/EXPORT:'+name for name in sorted(exports)])+'\n')
    linker=Path(candidate['assembler']['path']).with_name('link.exe')
    with (output/'link.log').open('wb') as log:
        subprocess.run([linker,'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    for row in objects:S.check(S.artifact(Path(row['path']))==row,'An accepted public FIS input changed')
    data=dict(schema=1,scope='public_FIS_String_File_and_explicit_cleanup_probe_over_accepted_eight_native_candidate',
        accepted_execution=S.artifact(accepted_result),accepted_images=S.artifact(images),accepted_inputs=config,
        model=model,image=S.artifact(dll),link_response=S.artifact(rsp),original_link_response=S.artifact(original_rsp),
        link_inputs=objects,public_observation_exports=sorted(exports),execution_tool=S.artifact(Path(__file__)),
        frozen_eight_native_tool=S.artifact(Path(T.__file__)),COFF_or_Java_or_stops_changed=False,shared28_changed=False,
        FIS_FileDescriptor_constructor_used=False,primordial=binding,automatic_Cleaner_or_weak_GC=False,game_started=False)
    path=output/'public-images.json';S.write(path,data);return path


def execute(images_file,kind):
    config=S.read(images_file);S.check(S.artifact(Path(__file__))==config['execution_tool'],'Public FIS test tool changed')
    S.check(S.artifact(Path(T.__file__))==config['frozen_eight_native_tool'],'Frozen eight-native test tool changed')
    for row in config['link_inputs']:S.check(S.artifact(Path(row['path']))==row,'Original public FIS link input changed')
    old=config['accepted_inputs'];meta=config['model'];source=S.read(S.checked(old['candidate']))['metadata']['source']
    runtime=S.checked(old['runtime'])
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Public source heap bind failed')
    members={(row['owner'],row['name'],row['descriptor']):row['method'] for row in meta['members']}
    native={row['operation']:row['method'] for row in source['methods']};classes=meta['classes']
    diagnostic=S.read(Path(old['baseline_manifest']['path']).parent/'diagnostic.json')
    stages=[];failure=None;stream=0;fd=0;cleanup=0;diagnostic_queries=None;vm_cleanup=None;main=0
    root_bank=(Q*4096).from_address(addr(image,'boom_file_input_owner_roots'))
    def states():return {name:U.from_address(addr(image,'boom_class'+str(ident))+8).value for name,ident in classes.items() if name in OBSERVE}
    initial_states=states()
    def call(ident,args,label,check=True):
        context=Context();argv=(Q*max(1,len(args)))(*args);value=proc(image,'boom_m'+str(ident),Q,P,P)(context,argv)
        stages.append(dict(stage=label,method=ident,context=list(context),returned=value))
        if context[0] and check:
            pool=addr(image,'boom_diagnostic_pool');row_id=U.from_address(pool+32).value
            row=diagnostic['rows'][row_id-1] if U.from_address(pool+8).value==2 and 0<row_id<=len(diagnostic['rows']) else None
            data=dict(stage=label,method=ident,context=list(context),diagnostic=row,class_states=states(),
                owner_roots=[value for value in root_bank if value],image=S.artifact(images_file),
                source_Code_COFF_or_stop_changed=False,host_reference_fields_written=False)
            path=images_file.parent/(kind+'-first-failure.json')
            if not path.exists():S.write(path,data)
            raise SourceFailure(str((label,list(context),row['symbol'] if row else None)))
        return value,context
    def java(owner,name,descriptor,args,label=None):
        return call(members[owner,name,descriptor],args,label or owner+'.'+name+descriptor)[0]
    def ensure(owner):
        context=Context();proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(classes[owner])),context)
        S.check(not context[0],'Public fixture source initializer failed: '+str((owner,list(context))))
    def new(owner):
        ensure(owner);context=Context();value=proc(rt,'boom_object_new',P,P,P,P)(heap,addr(image,'boom_layout'+str(classes[owner])),context)
        S.check(value and not context[0],'Public normal object allocation failed');return value
    def string(value):
        raw=value.encode('utf-16-le','surrogatepass');context=Context()
        chars=proc(rt,'boom_array_new',P,P,c.c_int,U,P)(heap,len(raw)//2,5,context)
        S.check(chars and not context[0],'Public source char array allocation failed');c.memmove(chars,raw,len(raw))
        text=new('java/lang/String');java('java/lang/String','<init>','([C)V',[text,chars]);return text
    def field(oop,receiver,name):
        [row]=[row for row in meta['fields'] if row['receiver']==receiver and row['name']==name]
        kind=Q if row['width']==8 else U if row['width']==4 else c.c_ubyte
        return kind.from_address(oop+row['offset']).value
    fixture=images_file.parent/(kind+'-fixtures');fixture.mkdir();path=fixture/'public.bin';payload=b'public-file-input\x00\xff';path.write_bytes(payload)
    constructor_complete=False;registered=False;explicit_close=False;cleanup_cleared=False;bytes_read=[]
    try:
        ensure('java/lang/String')
        if config['primordial']:
            # M emits the same original-constructor binding used by the formal
            # native-library suite. The ASM owner opens/stops the native domains.
            context=Context();main=proc(image,'boom_public_owner_open',P,P)(context)
            S.check(main and not context[0],'Actual primordial/public worker owner setup failed: '+str(list(context)))
            current,context=call(meta['source_currentThread']['method'],[],'original currentThread after normal primordial setup')
            S.check(current==main,'Primordial FLS currentThread identity differs')
        properties=new('java/util/Properties');java('java/util/Properties','<init>','()V',[properties])
        values={'java.home':old['oracle_home'],'user.dir':str(fixture),'user.home':str(fixture),'user.name':'public-file-input-test',
            'java.io.tmpdir':str(fixture),'file.separator':'\\','path.separator':';','line.separator':'\r\n','os.name':'Windows 10','os.arch':'amd64',
            'os.version':'10.0','file.encoding':'UTF-8','native.encoding':'UTF-8','sun.jnu.encoding':'UTF-8'}
        for key,value in values.items():java('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;',
            [properties,string(key),string(value)])
        java('java/lang/System','setProperties','(Ljava/util/Properties;)V',[properties])
        java('java/lang/System','setJavaLangAccess','()V',[])
        argument=string(str(path));descriptor='(Ljava/lang/String;)V'
        if kind=='file':
            file=new('java/io/File');java('java/io/File','<init>','(Ljava/lang/String;)V',[file,argument]);argument=file;descriptor='(Ljava/io/File;)V'
        stream=new(B.C.OWNER)
        java(B.C.OWNER,'<init>',descriptor,[stream,argument],kind+' public FIS constructor')
        constructor_complete=True;fd=field(stream,B.C.OWNER,'fd');cleanup=field(fd,B.C.FD,'cleanup')
        registered=bool(cleanup and P.from_address(cleanup-8).value==addr(image,'boom_layout'+str(classes['java/io/FileCleanable'])))
        S.check(registered and field(cleanup,'java/io/FileCleanable','referent')==fd and
            field(cleanup,'java/io/FileCleanable','handle')==field(fd,B.C.FD,'handle'),
            'Public constructor returned without the original FileCleanable FD/handle registration')
        for byte in payload:bytes_read.append(java(B.C.OWNER,'read','()I',[stream]))
        S.check(bytes(bytes_read)==payload and c.c_int32(java(B.C.OWNER,'read','()I',[stream])).value==-1,
            'Public FIS read output/EOF differs')
        java(B.C.OWNER,'close','()V',[stream]);explicit_close=True
        cleanup_cleared=field(fd,B.C.FD,'cleanup')==0 and field(cleanup,'java/io/FileCleanable','referent')==0
        S.check(cleanup_cleared and field(fd,B.C.FD,'handle')==0xffffffffffffffff and fd not in root_bank,
            'Original unregisterCleanup/Phantom clear/explicit close did not complete')
        java(B.C.OWNER,'close','()V',[stream])
    except SourceFailure as error:
        failure=dict(error=str(error),artifact=S.artifact(images_file.parent/(kind+'-first-failure.json')))
        # Read-only follow-up queries distinguish an unbound primordial context
        # from a field/name/mirror defect. They do not retry a failed clinit.
        literals=[]
        for row in meta['literal_probes']:
            context=Context();argv=(Q*1)()
            value=proc(image,row['symbol'],Q,P,P)(context,argv)
            literals.append(dict(**row,value=value,context=list(context)))
        unsafe=java('jdk/internal/misc/Unsafe','getUnsafe','()Ljdk/internal/misc/Unsafe;',[])
        queries=[]
        for owner,names in [('java/lang/Thread',['threadLocals','inheritableThreadLocals','inheritedAccessControlContext','contextClassLoader']),
                            ('java/lang/ThreadGroup',['parent'])]:
            [mirror]=[row['value'] for row in literals if row['source_symbol'].get('Class')==owner]
            for name in names:
                cookie,context=call(members['jdk/internal/misc/Unsafe','objectFieldOffset','(Ljava/lang/Class;Ljava/lang/String;)J'],
                    [unsafe,mirror,string(name)],'readonly Unsafe field query '+owner+'.'+name,check=False)
                queries.append(dict(owner=owner,name=name,cookie=cookie,context=list(context)))
        current,context=call(meta['source_currentThread']['method'],[],'readonly original Thread.currentThread without primordial binding',check=False)
        diagnostic_queries=dict(original_literal_thunks=literals,original_Unsafe_field_queries=queries,
            original_currentThread=dict(value=current,context=list(context)),normal_primordial_Thread_prepared=False,
            VM_or_Java_fields_host_written=False)
    finally:
        # Failed public constructors can have opened the actual owned FD already.
        # Invoke original close on that same partially constructed object; never
        # substitute the FileDescriptor constructor for public-constructor proof.
        if stream and any(root_bank):
            value,context=call(members[B.C.OWNER,'close','()V'],[stream],kind+' cleanup after public constructor failure',check=False)
            if context[0]:
                for owner in list(root_bank):
                    if owner:call(native[7],[owner],kind+' owned FD fallback cleanup',check=False)
        if config['primordial']:
            context=Context();status=proc(image,'boom_public_owner_close',U,P)(context)
            owner=addr(image,'boom_public_owner_status');pool=addr(image,'boom_provider_threads_pool')
            pending=Q.from_address(pool+224).value
            diag_pool=addr(image,'boom_diagnostic_pool');row_id=U.from_address(diag_pool+32).value
            worker_row=diagnostic['rows'][row_id-1] if U.from_address(diag_pool+8).value==2 and 0<row_id<=len(diagnostic['rows']) else None
            vm_cleanup=dict(status=status,context=list(context),owner_stage=U.from_address(owner).value,
                worker_failure_state=U.from_address(pool+120).value,worker_failure_context=list(Context.from_address(pending)),
                worker_failure_diagnostic=worker_row,
                worker_started=Q.from_address(pool+168).value,worker_tasks_entered=Q.from_address(pool+176).value,
                worker_tasks_returned=Q.from_address(pool+184).value,worker_uncaught_callbacks=Q.from_address(pool+192).value,
                worker_exit_callbacks=Q.from_address(pool+200).value,worker_exit_callbacks_succeeded=Q.from_address(pool+208).value,
                worker_reaped=Q.from_address(pool+216).value,held_monitor=Q.from_address(heap+112).value)
        handles=Q.from_address(addr(image,'boom_file_input_live_handles')).value
        buffers=Q.from_address(addr(image,'boom_file_input_owned_buffers')).value
        roots=[value for value in root_bank if value]
        if not vm_cleanup or not vm_cleanup['status']:
            trace=proc(image,'boom_release_trace_pool',U)();destroyed=proc(rt,'boom_heap_destroy',U,P)(heap)
        else:
            # A live native worker must never observe a released trace pool/heap.
            trace=None;destroyed=0
    result=dict(schema=1,kind=kind,verified=bool(constructor_complete and registered and explicit_close and cleanup_cleared and
        not handles and not buffers and not roots and not trace and destroyed==1 and
        (not vm_cleanup or (not vm_cleanup['status'] and not vm_cleanup['worker_failure_state'] and not vm_cleanup['held_monitor']))),
        scope='public_FIS_constructor_registration_explicit_close_probe',images=S.artifact(images_file),
        original_public_constructor_completed=constructor_complete,original_FileCleanable_registered=registered,
        original_public_read_bytes=bytes_read,original_explicit_close_completed=explicit_close,
        original_unregisterCleanup_and_Phantom_clear_completed=cleanup_cleared,failure=failure,stages=stages,
        readonly_failure_diagnostics=diagnostic_queries,
        normal_primordial_Thread_prepared=bool(main),native_worker_lifecycle_cleanup=vm_cleanup,
        cold_states=initial_states,final_states=states(),owned_handles=handles,owned_buffers=buffers,owner_roots=roots,
        trace_released=trace==0,heap_destroyed=destroyed==1,API_properties_and_original_System_JLA_helper=True,
        FIS_FileDescriptor_constructor_used=False,host_JLA_or_reference_root_fields_written=False,
        extra_Java_Code_or_COFF_or_stop_replacements=False,automatic_Cleaner_or_weak_GC=False,
        FILE_TYPE_DISK_filter_only=True,device_path_blacklist_or_strict_regular_file_test=False,
        System_phase1_executed=False,formal28_consumed=False,game_started=False)
    path=images_file.parent/(kind+'-execution.json');S.write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--accepted-result',type=Path)
    parser.add_argument('--images',type=Path);parser.add_argument('--worker',choices=('string','file'))
    parser.add_argument('--primordial',action='store_true')
    parser.add_argument('--output',type=Path,default=S.ART/'file-input-stream/public'/uuid4().hex)
    args=parser.parse_args()
    if args.worker:print(execute(args.images.resolve(),args.worker))
    else:
        images=args.images.resolve() if args.images else build(args.accepted_result.resolve(),args.output,args.primordial)
        results=[]
        for kind in ('string','file'):
            with (images.parent/(kind+'-worker.log')).open('wb') as log:
                process=subprocess.run([sys.executable,Path(__file__),'--images',images,'--worker',kind],
                    stdout=log,stderr=subprocess.STDOUT,check=False,timeout=240)
            S.check(process.returncode==0,'Public constructor worker failed; see '+str(images.parent/(kind+'-worker.log')))
            result=images.parent/(kind+'-execution.json');S.checked(S.artifact(result));results.append(S.artifact(result))
        result=dict(schema=1,verified=all(S.read(Path(row['path']))['verified'] for row in results),
            scope='two_public_FIS_constructors_original_registration_and_explicit_close_probe',
            images=S.artifact(images),cold_process_results=results,shared28_changed=False,game_started=False)
        path=images.parent/'result.json';S.write(path,result);print(path)
