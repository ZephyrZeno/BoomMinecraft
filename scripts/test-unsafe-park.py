"""Execute original Unsafe/LockSupport and real Java Cleaner workers with ASM Parker."""
import argparse
import ast
import ctypes as c
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic,sleep
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('park_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('unsafe-park-candidate');P=module('test-file-input-public');S=B.S
U,Q,Context=B.module('test-file-input').U,B.module('test-file-input').Q,P.Context
Ptr=c.c_void_p
addr,proc=P.addr,P.proc
LIVE_RESULTS={}
LOCK='java/util/concurrent/locks/LockSupport'
THREAD='java/lang/Thread'
UNSAFE='jdk/internal/misc/Unsafe'
EXTRA=[(LOCK,'unpark','(Ljava/lang/Thread;)V'),(LOCK,'park','()V'),(LOCK,'parkNanos','(J)V'),
    (LOCK,'parkUntil','(J)V'),(THREAD,'interrupt','()V'),(THREAD,'interrupted','()Z'),
    (THREAD,'isInterrupted','()Z'),
    ('java/lang/ref/Cleaner','create','(Ljava/util/concurrent/ThreadFactory;)Ljava/lang/ref/Cleaner;'),
    ('jdk/internal/ref/CleanerFactory$1','<init>','()V'),
    ('jdk/internal/misc/InnocuousThread','newSystemThread','(Ljava/lang/String;Ljava/lang/Runnable;I)Ljava/lang/Thread;'),
    ('java/lang/System','getProperties','()Ljava/util/Properties;'),
    ('jdk/internal/misc/VM','saveProperties','(Ljava/util/Map;)V'),('java/lang/Object','<init>','()V')]


def source_model(candidate,closure):
    base=candidate['metadata']['base'];_,summary,classes=S.base(Path(base['batch']),Path(base['plan']))
    wanted={row[0] for row in EXTRA};owners={row['name']:row for row in classes
        if row['origin']['loader']=='bootstrap' and row['name'] in wanted}
    S.check(set(owners)==wanted,'Park original Java fixture classes missing')
    I=B.module('verify-translation-ir');members=[]
    for name,cls in owners.items():
        raw=I.Source(S.original_class(summary,cls))
        S.check(raw.name==name and len(raw.methods)==len(cls['method_ids']),'Park original method inventory differs')
        for ident,method in zip(cls['method_ids'],raw.methods):
            if (name,method['name'],method['descriptor']) not in EXTRA:continue
            code=raw.code(method);S.check(code is not None,'Park Java fixture requires original Code')
            row=dict(owner=name,name=method['name'],descriptor=method['descriptor'],method=ident,class_id=cls['id'],
                class_sha256=cls['origin']['sha256'],code_sha256=hashlib.sha256(code['bytes']).hexdigest())
            selected=closure['selected_methods'].get(str(ident))
            S.check(selected and selected['class_id']==cls['id'] and selected['source_sha256']==row['class_sha256'] and
                selected['code_sha256']==row['code_sha256'],'Park fixture original Java not selected: '+str(row))
            members.append(row)
    S.check(len(members)==len(EXTRA),'Park fixture original Java declarations missing')
    return dict(classes={name:cls['id'] for name,cls in owners.items()},members=members,
        source_Code_or_COFF_added=False,original_selected_Code_identity_checked=True)


def runner():
    tree=ast.parse(inspect.getsource(P.execute));function=tree.body[0]
    source=ast.dump(tree,include_attributes=False);changed=[]
    for node in ast.walk(function):
        if isinstance(node,ast.keyword) and node.arg=='extra_Java_Code_or_COFF_or_stop_replacements':
            node.value=ast.Constant(True);changed.append(node.arg)
        if isinstance(node,ast.keyword) and node.arg=='scope' and isinstance(node.value,ast.Constant) and node.value.value=='public_FIS_constructor_registration_explicit_close_probe':
            node.value=ast.Constant('public_FIS_with_two_unregistered_Unsafe_park_natives');changed.append(node.arg)
    [body]=[node for node in function.body if isinstance(node,ast.Try) and node.handlers and node.finalbody]
    preparation=[i for i,node in enumerate(body.body) if isinstance(node,ast.Expr) and
        isinstance(node.value,ast.Call) and ast.unparse(node.value)=="java('java/lang/System', 'setJavaLangAccess', '()V', [])"]
    S.check(len(preparation)==1,'Public fixture normal API preparation site changed')
    body.body.insert(preparation[0]+1,ast.parse('prepare_saved_properties(java, string)').body[0])
    body.body.append(ast.parse('unsafe_park_suite(image, rt, heap, meta, java, call, field, new, string, images_file, kind)').body[0])
    ast.fix_missing_locations(tree)
    S.check(sorted(changed)==['extra_Java_Code_or_COFF_or_stop_replacements','scope'],'Unexpected public runner AST delta')
    namespace=dict(vars(P));namespace['unsafe_park_suite']=semantics;namespace['prepare_saved_properties']=prepare_saved_properties
    exec(compile(tree,str(Path(__file__)), 'exec'),namespace)
    return namespace['execute'],dict(original_tool=S.artifact(Path(P.__file__)),
        original_AST_sha256=hashlib.sha256(source.encode()).hexdigest(),
        adapted_AST_sha256=hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),
        changes=['two scope/result labels','one original Java saved-property API preparation before public constructor',
                 'one additional host test-suite invocation after real public close'],
        original_public_constructor_read_register_close_and_cleanup_rules_unchanged=True),ast.unparse(tree)+'\n'


def prepare_saved_properties(java,string):
    properties=java('java/lang/System','getProperties','()Ljava/util/Properties;',[])
    java('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;',
        [properties,string('java.class.version'),string('65.0')])
    java('jdk/internal/misc/VM','saveProperties','(Ljava/util/Map;)V',[properties])


def quiesce_assembly():
    # Exact existing test-owner stop/join prefix, without closing either wait
    # domain, the Parker, the main FLS record or the normal Thread registry.
    text=P.owner_asm();begin=text.index('boom_public_owner_close PROC FRAME')
    end=text.index('pub_owner_threads_closed:\n',begin)+len('pub_owner_threads_closed:\n')
    body=text[begin:end].replace('boom_public_owner_close','boom_park_test_quiesce').replace('pub_owner_','pubq_owner_')
    return ('PUBLIC boom_park_test_quiesce\n'+body+
        'pubq_owner_close_success:\n xor eax,eax\npubq_owner_close_done:\n add rsp,48\n'
        ' pop rdi\n pop rsi\n pop rbx\n ret\nboom_park_test_quiesce ENDP\n')


def build(candidate_file,public_images,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated park execution output required')
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Current park source proof differs')
    candidate=S.read(candidate_file);meta=candidate['metadata'];source=meta['source']
    original=S.read(public_images);old=original['accepted_inputs']
    S.check(original['primordial'] and original['execution_tool']==S.artifact(Path(P.__file__)),
        'Actual normal primordial/public FIS fixture required')
    S.checked(original['image']);closure=S.read(S.checked(old['baseline_manifest']))
    S.check(closure['source_batch_summary_sha256']==meta['base']['batch_summary']['digest']['sha256'],
        'Park and original public Java code belong to different source batches')
    for row in original['link_inputs']:S.check(S.artifact(Path(row['path']))==row,'Original public source link input changed')
    older=S.read(S.checked(old['candidate']))['metadata']['frame_overlay']['manifest']
    a=S.read(S.checked(older))['source']['original_native_declarations']
    b=S.read(S.checked(meta['frame_overlay']['manifest']))['source']['original_native_declarations']
    a={row['id']:row for row in a};b={row['id']:row for row in b}
    for row in source['methods']:
        ident=row['method'];S.check(a[ident]==b[ident] and a[ident]['flags']&32 and not a[ident]['flags']&128,
            'Original public source native frame differs from new park frame')
    probes=source_model(candidate,closure)
    diagnostic=S.read(Path(old['baseline_manifest']['path']).parent/'diagnostic.json')
    stop_asm=S.checked(old['remaining_stops'][0]);stop_obj=S.checked(old['remaining_stops'][1]);text=stop_asm.read_text();removed=[]
    for method in source['methods']:
        symbol='boom_m'+str(method['method']);[row]=[row for row in diagnostic['rows'] if row['symbol']==symbol]
        S.check(row['category']==2 and row['source_sha256']==method['class_sha256'],'Park replacement must be an exact original native stop')
        body=(f'PUBLIC {symbol}\n{symbol} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
            f' lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{symbol} ENDP\n')
        S.check(text.count(body)==1,'Original park diagnostic stop differs');text=text.replace(body,'',1)
        removed.append(dict(symbol=symbol,source_sha256=method['class_sha256'],body_sha256=hashlib.sha256(body.encode()).hexdigest()))
    output.mkdir(parents=True);assembler=Path(candidate['assembler']['path']);linker=assembler.with_name('link.exe')
    def assemble(path,obj):
        with obj.with_suffix('.log').open('wb') as log:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),path],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    stops=output/'remaining-stops.asm';stops.write_text(text);new_stop=stops.with_suffix('.obj');assemble(stops,new_stop)
    [owner]=[row for row in original['primordial']['units'] if Path(row['assembly']['path']).name=='public-owner.asm']
    owner_text=S.checked(owner['assembly']).read_text();S.check(owner_text==P.owner_asm(),'Original public owner template changed')
    owner_text=owner_text.replace('.data\nPUBLIC boom_public_owner_status',
        'EXTERN boom_provider_unsafe_park_pool:BYTE\nEXTERN boom_provider_unsafe_park_open:PROC\n'
        'EXTERN boom_provider_unsafe_park_close:PROC\n.data\nPUBLIC boom_public_owner_status',1)
    marker=' mov DWORD PTR [boom_public_owner_status],3\n'
    S.check(owner_text.count(marker)==1,'Public owner open hook location changed')
    owner_text=owner_text.replace(marker,marker+' lea rcx,boom_provider_unsafe_park_pool\n call boom_provider_unsafe_park_open\n'
        ' test eax,eax\n jnz pub_owner_open_bad\n',1)
    marker='pub_owner_threads_closed:\n'
    owner_text=owner_text.replace(marker,marker+' lea rcx,boom_provider_unsafe_park_pool\n call boom_provider_unsafe_park_close\n'
        ' test eax,eax\n jnz pub_owner_close_done\n',1)
    owner_text=owner_text.removesuffix('END\n')+quiesce_assembly()+'END\n'
    owner_asm=output/'park-public-owner.asm';owner_asm.write_text(owner_text);owner_obj=owner_asm.with_suffix('.obj');assemble(owner_asm,owner_obj)
    lines=S.checked(original['link_response']).read_text().splitlines();exports={line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')}
    exports|=set(candidate['exports'])|{f"boom_m{source['Object_constructor']['method']}",'boom_park_test_quiesce',
        'boom_vm_thread_root_cells','boom_vm_thread_root_count'}
    exports|={f"boom_m{row['method']}" for row in probes['members']}
    exports|={f'boom_{kind}{ident}' for ident in probes['classes'].values() for kind in ('class','layout')}
    replacements={stop_obj:new_stop,S.checked(owner['object']):owner_obj}
    objects=[];response=[]
    for line in lines:
        if line.startswith(('/OUT:','/EXPORT:')):continue
        if line.startswith('"'):
            path=Path(line.strip('"')).resolve();path=replacements.get(path,path);objects.append(S.artifact(path));line='"'+str(path)+'"'
        response.append(line)
    provider=S.checked(candidate['object']);objects.append(S.artifact(provider));response.append('"'+str(provider)+'"')
    dll=output/'unsafe-park-public.dll';rsp=output/'link.rsp'
    rsp.write_text('\n'.join(response+['/OUT:"'+str(dll)+'"']+['/EXPORT:'+name for name in sorted(exports)])+'\n')
    with (output/'link.log').open('wb') as log:
        subprocess.run([linker,'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    execute,reuse,adapted=runner();runner_file=output/'public-runner.py';runner_file.write_text(adapted)
    config=json.loads(json.dumps(original));config.update(scope='public_FIS_with_unregistered_Unsafe_park_candidate',
        image=S.artifact(dll),link_response=S.artifact(rsp),link_inputs=objects,COFF_or_Java_or_stops_changed=True,
        original_Java_COFF_changed=False,added_park_native_stops=removed,park_candidate=S.artifact(candidate_file),
        park_verification=S.artifact(candidate_file.with_name('verification.json')),original_public_images=S.artifact(public_images),
        park_test_generator=S.artifact(Path(__file__)),public_runner_reuse=reuse,public_runner=S.artifact(runner_file),
        park_owner_assembly=S.artifact(owner_asm),park_owner_object=S.artifact(owner_obj),park_original_Java_probes=probes)
    config['model']['classes'].update(probes['classes'])
    config['model']['members']+=probes['members']
    path=output/'images.json';S.write(path,config);return path


def semantics(image,rt,heap,meta,java,call,field,new,string,images_file,kind):
    config=S.read(images_file);candidate=S.read(S.checked(config['park_candidate']))
    native={row['name']:row['method'] for row in candidate['metadata']['source']['methods']}
    counters=addr(image,'boom_unsafe_park_counters');pool=addr(image,'boom_provider_threads_pool')
    wait_pool=addr(image,'boom_provider_object_wait_pool');slots=addr(image,'boom_unsafe_park_slots')
    source_waits=Q.from_address(wait_pool+96).value
    def counter(offset):return Q.from_address(counters+offset).value
    def wait_for(predicate,label):
        until=monotonic()+15
        while not predicate() and not U.from_address(pool+120).value and monotonic()<until:sleep(.0005)
        S.check(predicate(),label+'; failure='+str(U.from_address(pool+120).value))
    def records():
        rows=[]
        for i in range(min(16384,counter(56))):
            row=slots+i*64
            if Q.from_address(row).value:
                rows.append(dict(index=i,token=Q.from_address(row).value,JavaId=Q.from_address(row+8).value,
                    Thread_oop=Q.from_address(row+16).value,gate=Q.from_address(row+24).value,
                    permit=U.from_address(row+32).value,borrows=U.from_address(row+36).value,
                    waits=Q.from_address(row+40).value,unparks=Q.from_address(row+48).value))
        return rows
    until=monotonic()+10
    while Q.from_address(counters+72).value==0 and not U.from_address(pool+120).value and monotonic()<until:sleep(.001)
    result=dict(actual_Java_Cleaner_worker_waiting=Q.from_address(counters+72).value>0,
        park_calls=Q.from_address(counters).value,actual_waits=Q.from_address(counters+16).value,
        Object_wait_Java_frame_added=False)
    LIVE_RESULTS[kind]=result
    S.check(result['actual_Java_Cleaner_worker_waiting'],'Original Cleaner worker never entered real park wait')
    unsafe=java(UNSAFE,'getUnsafe','()Ljdk/internal/misc/Unsafe;',[])
    main=call(meta['source_currentThread']['method'],[],'park suite real currentThread')[0]
    def unpark(thread=main):return call(native['unpark'],[unsafe,thread],'original Unsafe.unpark')[0]
    def park(absolute,time):
        started=monotonic();call(native['park'],[unsafe,int(absolute),time&0xffffffffffffffff],'original Unsafe.park')
        return monotonic()-started
    def current_record():return next(row for row in records() if row['Thread_oop']==main)
    protocol=[]
    unpark();unpark();before=counter(24);first=park(False,20000000);second=park(False,20000000)
    S.check(counter(24)==before+1 and current_record()['permit']==0 and second>=.010,'Unparks did not merge into exactly one permit')
    protocol.append(dict(case='double_unpark_single_permit',first_seconds=first,second_seconds=second,fast_permits=1))
    from time import time as wall_time
    for label,absolute,time in [('negative',False,-1),('minimum_long',False,-(1<<63)),
                               ('expired',True,int(wall_time()*1000)-1),('absolute_zero',True,0)]:
        unpark();before=counter(24);elapsed=park(absolute,time)
        S.check(current_record()['permit']==1 and counter(24)==before,'Invalid/expired time consumed permit: '+label)
        park(False,10000000);S.check(counter(24)==before+1 and current_record()['permit']==0,'Preserved permit was not consumed')
        protocol.append(dict(case=label,pending_permit_preserved=True,seconds=elapsed))
    for label,absolute,time,dword in [('relative_zero',False,0,0xffffffff),('relative_one',False,1,1),
        ('relative_floor',False,1999999,1),('relative_DWORD_zero',False,4294967296*1000000,0),
        ('relative_DWORD_infinite',False,4294967295*1000000,0xffffffff),
        ('relative_maximum_long',False,(1<<63)-1,2077252342)]:
        unpark();elapsed=park(absolute,time)
        S.check(counter(104)==dword and current_record()['permit']==0,'Windows timeout conversion differs: '+label)
        protocol.append(dict(case=label,DWORD_timeout=counter(104),seconds=elapsed,early_permit=True))
    before=counter(16);elapsed=park(False,4294967296*1000000)
    S.check(elapsed<1 and counter(16)==before,'A truncated zero DWORD became an infinite wait')
    protocol.append(dict(case='relative_DWORD_zero_without_permit',seconds=elapsed,actual_wait=False))
    before=counter(16);elapsed=park(False,1999999)
    S.check(counter(16)==before+1 and elapsed<1,'Positive nanos did not really wait')
    protocol.append(dict(case='relative_nanos_actual_wait',DWORD_timeout=counter(104),seconds=elapsed))
    elapsed=park(True,int(wall_time()*1000)+20)
    S.check(elapsed<1,'Future absolute park failed to return')
    protocol.append(dict(case='absolute_future_actual_wait',seconds=elapsed))
    unpark();earliest=int(wall_time()*1000);elapsed=park(True,(1<<63)-1);latest=int(wall_time()*1000)
    S.check(counter(104) in {(((1<<63)-1)-now)&0xffffffff for now in range(earliest,latest+1)},
        'Absolute maximum long overflowed or used a different epoch')
    protocol.append(dict(case='absolute_maximum_long',DWORD_timeout=counter(104),seconds=elapsed,early_permit=True))
    java(LOCK,'unpark','(Ljava/lang/Thread;)V',[main]);java(LOCK,'park','()V',[])
    java(LOCK,'parkNanos','(J)V',[1000000]);java(LOCK,'parkUntil','(J)V',[int(wall_time()*1000)-1])
    S.check(not java(THREAD,'isInterrupted','()Z',[main]),'Primordial thread unexpectedly interrupted')
    java(THREAD,'interrupt','()V',[main]);unpark();park(False,10000000)
    S.check(java(THREAD,'isInterrupted','()Z',[main]) and current_record()['permit']==0,
        'Park cleared interrupt status or failed to consume a pending permit')
    before=counter(112);park(False,10000000)
    S.check(counter(112)==before+1 and java(THREAD,'isInterrupted','()Z',[main]),'Interrupted park did not return with flag retained')
    S.check(java(THREAD,'interrupted','()Z',[]) and not java(THREAD,'isInterrupted','()Z',[main]),'Original Java interrupt clearing failed')
    result.update(single_permit_and_time_protocol=protocol,original_LockSupport_entries_executed=True,
        original_Java_interrupt_preserved_and_cleared=True)
    factory=new('jdk/internal/ref/CleanerFactory$1');java('jdk/internal/ref/CleanerFactory$1','<init>','()V',[factory])
    for _ in range(7):java('java/lang/ref/Cleaner','create','(Ljava/util/concurrent/ThreadFactory;)Ljava/lang/ref/Cleaner;',[factory])
    wait_for(lambda:counter(72)>=8,'Eight original Java Cleaner threads never entered independent park waits')
    workers=[row for row in records() if row['Thread_oop']!=main]
    S.check(len(workers)==8 and len({row['token'] for row in workers})==8 and len({row['JavaId'] for row in workers})==8,
        'Parker slots did not retain eight independent real token/JavaId/oop keys')
    for row in workers:
        token=row['token']
        S.check(U.from_address(token).value==0x54485244 and U.from_address(token+4).value==1 and
            Q.from_address(token+40).value==row['Thread_oop'] and Q.from_address(token+48).value==row['JavaId'],
            'Controlled witness does not refer to a real live source Thread registry record')
        row['OS_thread_id']=U.from_address(token+32).value
    S.check(len({row['OS_thread_id'] for row in workers})==8 and all(row['OS_thread_id'] for row in workers),
        'Eight Java workers do not have distinct actual Windows OS thread IDs')
    park_pool=addr(image,'boom_provider_unsafe_park_pool')
    before=list((Q*16384).from_address(addr(image,'boom_unsafe_park_gate_roots')))
    S.check(proc(image,'boom_provider_unsafe_park_close',U,Ptr)(park_pool)==170 and
        list((Q*16384).from_address(addr(image,'boom_unsafe_park_gate_roots')))==before,
        'Premature close released live wait owners or their gate roots')
    S.check(proc(image,'boom_provider_unsafe_park_open',U,Ptr)(park_pool)==170,'A second lifecycle open was accepted')
    witness=[]
    for round in range(128):
        for target in workers:
            before=records();snapshot={row['Thread_oop']:row['waits'] for row in before if row['Thread_oop']!=main}
            java(LOCK,'unpark','(Ljava/lang/Thread;)V',[target['Thread_oop']])
            wait_for(lambda:Q.from_address(slots+target['index']*64+40).value>snapshot[target['Thread_oop']],
                'Real Java Cleaner did not wake and re-enter park')
            after={row['Thread_oop']:row['waits'] for row in records() if row['Thread_oop']!=main}
            S.check(all(after[oop]==value for oop,value in snapshot.items() if oop!=target['Thread_oop']),
                'One unpark woke an unrelated Java thread')
            if not round:witness.append(dict(Thread_oop=target['Thread_oop'],JavaId=target['JavaId'],real_record_token=target['token'],
                OS_thread_id=target['OS_thread_id'],
                old_waits=snapshot[target['Thread_oop']],new_waits=after[target['Thread_oop']],other_seven_waits_unchanged=True))
    target=workers[0];before=counter(40)
    java(THREAD,'interrupt','()V',[target['Thread_oop']])
    wait_for(lambda:counter(40)>before,'Existing source Thread.interrupt did not wake/restore a real Parker wait')
    result.update(eight_real_Java_OS_workers=True,controlled_independent_wake_witnesses=witness,
        completed_wake_repark_cycles=8*128,actual_park_plus_unpark_calls_at_least=2048,
        foreign_original_Thread_interrupt_woke_real_wait=True,source_Object_wait_count_unchanged=Q.from_address(wait_pool+96).value==source_waits,
        slot_records=records(),counters=list((Q*16).from_address(counters)),live_owner_close_rejected_without_root_changes=True,
        duplicate_lifecycle_open_rejected=True)
    S.check(result['source_Object_wait_count_unchanged'],'Parker changed original Object.wait source invocation statistics')
    unpark(0)
    not_started=java('jdk/internal/misc/InnocuousThread','newSystemThread','(Ljava/lang/String;Ljava/lang/Runnable;I)Ljava/lang/Thread;',
        [string('unstarted-park-probe'),0,8])
    count=counter(56);unpark(not_started)
    S.check(counter(56)==count,'Unpark of an unstarted original Thread allocated a Parker')
    invalid=[]
    for value in (0x1234,new('java/lang/Object')):
        _,context=call(native['unpark'],[unsafe,value],'invalid source unpark target',check=False)
        S.check(context[0]==7,'Invalid source Thread target did not fail closed');invalid.append(list(context))
    pending=Context(77,88,99,111,222,333,444,555);argv=(Q*2)(unsafe,main)
    proc(image,'boom_m'+str(native['unpark']),Q,Ptr,Ptr)(pending,argv)
    S.check(list(pending)==[77,88,99,111,222,333,444,555],'Pending context was changed')
    result.update(null_and_unstarted_unpark_no_op=True,invalid_targets_fail_closed=invalid,pending_context_preserved=True)
    from threading import Thread,get_native_id
    outside=[]
    def unattached():
        context=Context();argv=(Q*3)(unsafe,0,1)
        proc(image,'boom_m'+str(native['park']),Q,Ptr,Ptr)(context,argv)
        outside.append(dict(OS_thread_id=get_native_id(),context=list(context)))
    foreign=Thread(target=unattached);foreign.start();foreign.join(15)
    S.check(not foreign.is_alive() and len(outside)==1 and outside[0]['context'][0]==20,
        'A host thread without actual normal Java/FLS ownership was accepted as a Java park caller')
    result['unattached_host_thread_explicitly_rejected']=outside[0]
    context=Context();status=proc(image,'boom_park_test_quiesce',U,Ptr)(context)
    S.check(not status and not context[0] and not U.from_address(pool+120).value and not counter(64) and not counter(72),
        'Actual shared VM stop/join failed before collection')
    S.check(counter(48)>=8 and Q.from_address(pool+216).value==8 and Q.from_address(heap+112).value==0,
        'Actual parked Java workers did not all stop, exit/reap and release private gates')
    for row in workers:unpark(row['Thread_oop'])
    S.check(counter(56)==9,'Unpark of a terminated Java Thread allocated another Parker')
    context=Context(0,0,0,0,0,0,0xabcdef01,0x23456789);argv=(Q*3)(unsafe,0,1000000)
    proc(image,'boom_m'+str(native['park']),Q,Ptr,Ptr)(context,argv)
    S.check(context[0]==0xb002 and list(context)[6:]==[0xabcdef01,0x23456789],
        'A verified post-stop park did not propagate the exact VM stop protocol')
    proc(image,'boom_provider_reference_boundary',U,Ptr,Ptr)(context,addr(image,'boom_provider_reference_pool'))
    S.check(not context[0],'Existing native control boundary did not consume its own exact Parker stop token')
    result.update(terminated_unpark_no_op=True,all_real_workers_joined_before_GC=True,
        exact_VM_stop_from_wait_and_post_stop_entry=True,Context_payload_preserved=True)
    roots=(Q*16384).from_address(addr(image,'boom_unsafe_park_gate_roots'));gates=[oop for oop in roots if oop]
    S.check(len(gates)==9,'Private gate roots do not match eight workers and primordial Thread')
    contains=proc(rt,'boom_heap_contains',U,Ptr,Ptr);collect=proc(rt,'boom_heap_collect',Q,Ptr,Ptr,U)
    T=B.module('test-file-input');collections=[]
    spans_spec=T.ROOTS+[('boom_vm_thread_root_cells','boom_vm_thread_root_count')]
    def collection():
        values=[];spans=[]
        for name,count_symbol in spans_spec:
            count=Q.from_address(addr(image,count_symbol)).value;S.check(count<=1048576,'Invalid normal root span')
            bank=(Q*count).from_address(addr(image,name));nonzero=[oop for oop in bank if oop];values+=nonzero
            spans.append(dict(symbol=name,physical_cells=count,non_null_cells=len(nonzero),snapshot_sha256=hashlib.sha256(bytes(bank)).hexdigest()))
        fd_roots=(Q*4096).from_address(addr(image,'boom_file_input_owner_roots'))
        S.check(not any(fd_roots),'Public FIS explicit close left an active FD owner before quiescent GC')
        spans.append(dict(symbol='boom_file_input_owner_roots',physical_cells=4096,non_null_cells=0,
            snapshot_sha256=hashlib.sha256(bytes(fd_roots)).hexdigest()))
        values += [oop for oop in roots if oop]
        spans.append(dict(symbol='boom_unsafe_park_gate_roots',physical_cells=16384,non_null_cells=sum(bool(oop) for oop in roots),
            snapshot_sha256=hashlib.sha256(bytes(roots)).hexdigest()))
        compact=sorted(set(values));S.check(set(values)<=set(compact),'Normal roots omitted during compaction')
        vector=(Q*len(compact))(*compact);freed=collect(heap,vector,len(compact))
        S.check(freed!=0xffffffffffffffff,'Actual quiescent Parker root collection failed')
        for row in spans:
            S.check(hashlib.sha256(bytes((Q*row['physical_cells']).from_address(addr(image,row['symbol'])))).hexdigest()==row['snapshot_sha256'],
                'Collection changed a source or Parker root bank')
        collections.append(dict(spans=spans,physical_cells=sum(row['physical_cells'] for row in spans),
            non_null_before_deduplication=len(values),unique_oops=len(compact),every_non_null_oop_in_compacted_set=True,
            compact_vector_sha256=hashlib.sha256(bytes(vector)).hexdigest(),extra_host_roots=[],freed_objects=freed,
            source_root_banks_unmodified=True,all_workers_joined=True,nonmoving_quiescent_collection_only=True))
    collection();S.check(all(contains(heap,oop) for oop in gates),'Published gate roots failed to retain private normal Objects')
    S.check(proc(image,'boom_provider_unsafe_park_close',U,Ptr)(park_pool)==0 and not any(roots),
        'Parker close did not clear its declared native root span after workers joined')
    collection();S.check(all(not contains(heap,oop) for oop in gates),'Closed unrooted gate Objects were not reclaimed')
    S.check(proc(image,'boom_provider_unsafe_park_close',U,Ptr)(park_pool)==0,'Repeated Parker close failed')
    result.update(actual_quiescent_GC=collections,all_private_gate_roots_retained_then_reclaimed=True,
        native_root_values_not_host_written=True,gate_root_span_empty_after_close=True,
        final_counters=list((Q*16).from_address(counters)),full_suite_completed=True)


def compare_oracle(images,records):
    config=S.read(images);old=config['accepted_inputs'];home=Path(old['oracle_home'])
    catalog=old['oracle_modules'];digest=S.digest(Path(catalog['path']))
    S.check(all(digest[key]==catalog['digest'][key] for key in ('size','sha256')),'Locked JDK oracle modules changed')
    directory=images.parent/'jdk-oracle';directory.mkdir();source=directory/'UnsafeParkOracle.java'
    source.write_text('''import jdk.internal.misc.Unsafe;
import java.lang.reflect.*;import java.util.*;import java.util.concurrent.locks.LockSupport;
class UnsafeParkOracle {
 static Unsafe u;static Thread self;static LinkedHashMap<String,Boolean> checks=new LinkedHashMap<>();
 static void check(String s,boolean b){checks.put(s,b);}
 static long park(boolean a,long n){long t=System.nanoTime();u.park(a,n);return System.nanoTime()-t;}
 static void preserve(String s,boolean a,long n){u.unpark(self);park(a,n);long t=park(false,1000000000L);check(s,t<250000000L);}
 public static void main(String[] args)throws Exception{
  Field f=Unsafe.class.getDeclaredField("theUnsafe");f.setAccessible(true);u=(Unsafe)f.get(null);self=Thread.currentThread();
  LockSupport.unpark(null);Thread.interrupted();long warm=System.nanoTime();
  u.unpark(self);u.unpark(self);park(false,0);long d=park(false,20000000L);check("double_unpark_single_permit",d>=10000000L);
  preserve("negative",false,-1);preserve("minimum_long",false,Long.MIN_VALUE);
  preserve("expired",true,System.currentTimeMillis()-1);preserve("absolute_zero",true,0);
  String[] labels={"relative_zero","relative_one","relative_floor","relative_DWORD_zero","relative_DWORD_infinite","relative_maximum_long"};
  long[] times={0,1,1999999L,4294967296L*1000000L,4294967295L*1000000L,Long.MAX_VALUE};
  for(int i=0;i<labels.length;i++){u.unpark(self);check(labels[i],park(false,times[i])<250000000L);}
  check("relative_DWORD_zero_without_permit",park(false,4294967296L*1000000L)<250000000L);
  check("relative_nanos_actual_wait",park(false,1999999L)<1000000000L);
  check("absolute_future_actual_wait",park(true,System.currentTimeMillis()+20)<1000000000L);
  u.unpark(self);check("absolute_maximum_long",park(true,Long.MAX_VALUE)<250000000L);
  LockSupport.unpark(self);LockSupport.park();LockSupport.parkNanos(1000000L);LockSupport.parkUntil(System.currentTimeMillis()-1);
  check("original_LockSupport_entries",!self.isInterrupted());
  self.interrupt();u.unpark(self);park(false,10000000L);check("interrupt_preserved",self.isInterrupted());
  park(false,10000000L);check("early_interrupt_preserved",self.isInterrupted());
  check("original_Java_interrupt_clear",Thread.interrupted()&&!self.isInterrupted());
  u.unpark(null);Thread t=new Thread(()->{});u.unpark(t);t.start();t.join();u.unpark(t);
  check("null_unstarted_terminated_unpark",true);
  for(var e:checks.entrySet()){System.out.println(e.getKey()+"\\t"+e.getValue());if(!e.getValue())throw new AssertionError(e.getKey());}
 }
}
''',encoding='ascii')
    command=[home/'bin/java.exe','--add-exports','java.base/jdk.internal.misc=ALL-UNNAMED',
        '--add-opens','java.base/jdk.internal.misc=ALL-UNNAMED',source]
    process=subprocess.run(command,cwd=directory,capture_output=True,timeout=120,check=False)
    stdout=directory/'oracle.stdout';stderr=directory/'oracle.stderr';stdout.write_bytes(process.stdout);stderr.write_bytes(process.stderr)
    S.check(not process.returncode,'Locked JDK park oracle failed: '+str(stderr))
    oracle=dict(line.split('\t') for line in process.stdout.decode('ascii').splitlines());actual=[]
    for artifact in records:
        row=S.read(S.checked(artifact))['real_Java_park']
        observed={entry['case']:'true' for entry in row['single_permit_and_time_protocol']}
        observed.update(original_LockSupport_entries=str(row['original_LockSupport_entries_executed']).lower(),
            interrupt_preserved=str(row['original_Java_interrupt_preserved_and_cleared']).lower(),
            early_interrupt_preserved=str(row['original_Java_interrupt_preserved_and_cleared']).lower(),
            original_Java_interrupt_clear=str(row['original_Java_interrupt_preserved_and_cleared']).lower(),
            null_unstarted_terminated_unpark=str(row['null_and_unstarted_unpark_no_op'] and row['terminated_unpark_no_op']).lower())
        S.check(observed==oracle and all(value=='true' for value in oracle.values()),'Actual ASM park protocol differs from JDK')
        actual.append(dict(execution=artifact,protocol=observed))
    result=dict(verified=True,scope='Windows_JDK_park_unpark_single_permit_time_interrupt_target_lifecycle',
        locked_modules=catalog,source=S.artifact(source),stdout=S.artifact(stdout),stderr=S.artifact(stderr),
        checks=oracle,actual_ASM_executions=actual,Java_used_only_as_isolated_oracle=True)
    path=directory/'result.json';S.write(path,result);return S.artifact(path)


def worker(images_file,kind):
    config=S.read(images_file);S.check(S.artifact(Path(__file__))==config['park_test_generator'],'Park test generator changed')
    execute,reuse,text=runner();S.check(reuse==config['public_runner_reuse'] and S.checked(config['public_runner']).read_text()==text,
        'Public real-Java executor AST reuse changed')
    try:result_file=execute(images_file,kind)
    except BaseException:
        S.write(images_file.parent/(kind+'-suite-progress-at-failure.json'),LIVE_RESULTS.get(kind,{}));raise
    result=S.read(result_file)
    return dict(verified=bool(result['verified'] and result['failure'] is None and LIVE_RESULTS.get(kind,{}).get('full_suite_completed')),
        public_execution=S.artifact(result_file),additional_suite_failure=result['failure'],
        original_public_constructor=result['original_public_constructor_completed'],
        original_cleanup_registration=result['original_FileCleanable_registered'],
        original_explicit_close=result['original_unregisterCleanup_and_Phantom_clear_completed'],
        real_Java_park=LIVE_RESULTS.get(kind),worker_lifecycle=result['native_worker_lifecycle_cleanup'],
        unregistered_park_candidate=True,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path)
    parser.add_argument('--public-images',type=Path);parser.add_argument('--images',type=Path)
    parser.add_argument('--worker',choices=('string','file'))
    parser.add_argument('--output',type=Path,default=S.ART/'unsafe-park/executions'/uuid4().hex)
    args=parser.parse_args()
    if args.worker:
        images=args.images.resolve();path=images.parent/(args.worker+'-park-execution.json');S.write(path,worker(images,args.worker));print(path)
    else:
        images=args.images.resolve() if args.images else build(args.candidate.resolve(),args.public_images.resolve(),args.output)
        records=[]
        for kind in ('string','file'):
            with (images.parent/(kind+'-worker.log')).open('wb') as log:
                child=subprocess.run([sys.executable,Path(__file__),'--images',images,'--worker',kind],stdout=log,stderr=subprocess.STDOUT,check=False,timeout=240)
            S.check(child.returncode==0,'Real park/public Java worker failed: '+str(images.parent/(kind+'-worker.log')))
            path=images.parent/(kind+'-park-execution.json');records.append(S.artifact(path))
        complete=all(S.read(Path(row['path']))['verified'] for row in records)
        oracle=compare_oracle(images,records) if complete else None
        result=dict(verified=bool(complete and oracle),
            scope='unregistered_Unsafe_park_actual_public_FIS_and_Java_Cleaner_workers',images=S.artifact(images),
            cold_process_results=records,JDK_oracle=oracle,all_park_semantics_completed=bool(complete and oracle),game_started=False)
        path=images.parent/'result.json';S.write(path,result);print(path)
