"""Test restricted source-native library callbacks, real pins and field publication."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import importlib.util
import os
from pathlib import Path
from threading import Barrier, get_native_id


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_library_test_build',ROOT/'scripts/native-library-lifecycle-candidate.py')
B=importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
S=B.S
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8


def proc(image,name,result,*arguments):
    function=getattr(image,name)
    function.restype,function.argtypes=result,arguments
    return function


def addr(image,name):
    return c.addressof(c.c_byte.in_dll(image,name))


def run(candidate_file):
    candidate=S.read(candidate_file)
    image_file=S.checked(candidate['image'])
    for record in candidate['kernel_sources']:
        path=Path(record['path'])
        S.check(S.digest(path)==record['digest'],'Library ASM source changed')
    S.check(S.digest(Path(candidate['tool']['path']))==candidate['tool']['digest'],'Library candidate generator changed')
    runtime=S.checked(candidate['runtime'])
    with os.add_dll_directory(str(runtime.parent)):
        rt,image=c.CDLL(str(runtime)),c.CDLL(str(image_file))
    nio=S.read(S.checked(candidate['source_NIO']))
    meta=candidate['metadata']
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Normal guest heap bind failed')
    obj=proc(rt,'boom_object_new',P,P,P,P)
    array=proc(rt,'boom_array_new',P,P,c.c_int,U,P)
    classes={name:row['id'] for name,row in meta['classes'].items()}
    def new(class_id):
        context=Context()
        value=obj(heap,addr(image,'boom_layout'+str(class_id)),context)
        S.check(value and not context[0],'Cannot create source-layout native library fixture')
        return value
    all_methods=nio['original_Java']+nio['methods']+meta['original_java']+meta.get('api_fixture_methods',[])
    methods={(row['owner'],row['name'],row['descriptor']):row['method'] for row in all_methods}
    natives={row['name']:row['method'] for row in meta['natives']}
    def call(ident,context,arguments,native=False):
        packed=(Q*max(1,len(arguments)))(*arguments)
        return proc(image,'boom_m'+str(ident)+('_native' if native else ''),Q,P,P)(context,packed)
    def source(ident,arguments):
        context=Context()
        result=call(ident,context,arguments)
        S.check(not context[0] and not context[3],'Original Java fixture method stopped: '+str(list(context)))
        return result
    def string(text):
        raw=text.encode('utf-16-le')
        context=Context()
        chars=array(heap,len(raw)//2,5,context)
        S.check(chars and not context[0],'Cannot allocate source char[]')
        c.memmove(chars,raw,len(raw))
        value=new(classes['java/lang/String'])
        source(methods['java/lang/String','<init>','([C)V'],[value,chars])
        return value
    def text(value):
        chars=source(methods['java/lang/String','toCharArray','()[C'],[value])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le')
    def native(name,arguments):
        context=Context()
        value=call(natives[name],context,arguments,True)
        return context,value
    net,nio_name=string('net'),string('nio')
    discoveries=[]
    for filename,wanted in (('net.dll','net'),('nio.dll','nio'),('net.abc','net'),('net.dll\0extra','net'),('missing.dll',None)):
        context,value=native('findBuiltinLib',[string(filename)])
        S.check(not context[0] and (text(value) if value else None)==wanted,'Builtin discovery differs for '+repr(filename))
        discoveries.append(filename)
    context,value=native('findBuiltinLib',[0])
    error=P.from_address(c.addressof(context)+16).value
    S.check(context[0]==16 and error and not value,'Null builtin name did not throw the original InternalError')
    message=source(methods['java/lang/Throwable','getMessage','()Ljava/lang/String;'],[error])
    S.check(text(message)=='NULL filename for native library','Original InternalError message differs')
    thread=meta['thread']
    register=next(m['method'] for m in thread['methods'] if m['name']=='registerNatives')
    current=next(m['method'] for m in thread['methods'] if m['name']=='currentThread')
    context=Context()
    call(register,context,[],True)
    S.check(not context[0],'Source Thread registration failed')
    registry=proc(rt,'boom_threads_create',P,P,U)(heap,32)
    bind=proc(image,'boom_provider_thread_bind',U,P)
    S.check(registry and bind(registry)==0,'Source Thread registry binding failed')
    attach=proc(rt,'boom_threads_attach',P,P,P,Q)
    detach=proc(rt,'boom_threads_detach',U,P)
    next_id=proc(rt,'boom_threads_next_id',Q,P)
    main=new(thread['thread_class'])
    S.check(attach(registry,main,1),'Source thread attachment fixture failed')
    fields={f['name']:f for f in meta['fields']}
    def library():
        return new(classes[B.IMPL])
    def published(oop):
        return Q.from_address(oop+fields['handle']['offset']).value,U.from_address(oop+fields['jniVersion']['offset']).value
    pins=addr(image,'boom_native_library_pins')
    modules=addr(image,'boom_native_library_modules')
    receiver=library()
    context,value=native('load',[receiver,nio_name,1,1])
    if candidate['test_only_callback_version'] is not None:
        S.check(context[0]==16 and not value and published(receiver)==(0,0) and not Q.from_address(pins).value,
                'Bad version published a library or retained an owner pin')
        thrown=P.from_address(c.addressof(context)+16).value
        actual=text(source(methods['java/lang/Throwable','getMessage','()Ljava/lang/String;'],[thrown]))
        expected=f"unsupported JNI version 0x{candidate['test_only_callback_version']:08X} required by nio"
        S.check(actual==expected,'Original unsupported JNI version message differs: '+actual)
        result=dict(typed_bad_version_rejected=True,source_error_message=actual,source_fields_unchanged=True,owner_pins=0)
    else:
        S.check(not context[0] and value==1 and published(receiver)==(image._handle,0x10008) and Q.from_address(pins).value==1,
                'Real callback did not publish the actual owner and JNI version: '+str(list(context)))
        detached_receiver=library()
        with ThreadPoolExecutor(1) as workers:
            failed,_=workers.submit(native,'load',[detached_receiver,nio_name,1,1]).result(timeout=15)
        S.check(failed[0]==20 and published(detached_receiver)==(0,0) and Q.from_address(pins).value==1,
                'A ready module bypassed per-caller actual VM attachment')
        context,_=native('findEntry0',[image._handle,string('Java_missing_native')])
        S.check(context[0]==20,'Unsupported standard JNI entry was exposed as a Context ABI address')
        context,_=native('unload',[nio_name,1,image._handle+1])
        S.check(context[0]==7 and Q.from_address(pins).value==1,'Wrong handle changed ownership')
        preserved=Context(9,4,7,0,11,12,13,14)
        before=list(preserved)
        call(natives['unload'],preserved,[nio_name,1,image._handle],True)
        S.check(list(preserved)==before and Q.from_address(pins).value==1,'Pending exception consumed a library owner')
        context,_=native('unload',[nio_name,1,image._handle])
        S.check(not context[0] and not Q.from_address(pins).value,'Actual owner pin was not released')
        fixtures=[(new(thread['thread_class']),library()) for _ in range(8)]
        enter,leave=Barrier(9,timeout=15),Barrier(9,timeout=15)
        def worker(pair):
            oop,lib=pair
            S.check(attach(registry,oop,next_id(registry)),'Concurrent source Thread attach failed')
            try:
                context,value=native('load',[lib,nio_name,1,1])
                S.check(not context[0] and value==1 and published(lib)==(image._handle,0x10008),'Concurrent source load failed')
                check=Context()
                S.check(call(current,check,[],True)==oop and not check[0],'Loaded module used an unrelated thread registry')
                enter.wait()
                leave.wait()
                context,_=native('unload',[nio_name,1,image._handle])
                S.check(not context[0],'Concurrent source unload failed')
                return get_native_id()
            finally:
                S.check(detach(registry)==0,'Concurrent thread detach failed')
        with ThreadPoolExecutor(8) as workers:
            jobs=[workers.submit(worker,pair) for pair in fixtures]
            try:
                enter.wait()
                S.check(U.from_address(modules+64+12).value==8 and Q.from_address(pins).value==1,
                        'Concurrent loads did not share one real owner pin')
            finally:
                leave.wait()
            ids=[job.result(timeout=15) for job in jobs]
        S.check(len(set(ids))==8 and not Q.from_address(pins).value,'Concurrent library refs or owner pin leaked')
        # Without actual System.props publication the net body must block;
        # an uninitialized VM cannot be silently treated as preferIPv4Stack=false.
        net_receiver=library()
        context,value=native('load',[net_receiver,net,1,1])
        S.check(context[0]==20 and not value and published(net_receiver)==(0,0) and not Q.from_address(pins).value and
                not Q.from_address(addr(image,'boom_native_library_property_reads')).value,
                'Uninitialized properties were replaced with a fabricated net preference')
        context,value=native('load',[library(),string('unknown'),1,0])
        S.check(context[0]==20 and not value and not Q.from_address(pins).value,'Unknown module pretended to load')
        property_success=False
        if candidate.get('source_properties_API_fixture'):
            api=S.read(S.checked(candidate['source_properties_API_fixture']))
            for record in (api['original_assembly'],api['original_COFF'],api['original_shard']):
                S.checked(record)
            S.check(S.digest(Path(api['extractor_tool']['path']))==api['extractor_tool']['digest'],
                    'Original API extractor tool changed')
            S.check(api['all_original_branches_retained'] and not api['new_static_or_class_roots'],
                    'Property API delta changed original branches or class/static roots')
            props_symbol=f"boom_s{classes['java/lang/System']}_{meta['props_index']}"
            root_base,cell=addr(image,'boom_probe_static_roots'),addr(image,props_symbol)
            root_count=Q.from_address(addr(image,'boom_probe_static_root_count')).value
            S.check(root_base<=cell<root_base+root_count*8 and not (cell-root_base)&7,
                    'Original System.props cell left the existing source GC root bank')
            properties_init=Context()
            proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(classes['java/util/Properties'])),properties_init)
            S.check(not properties_init[0],'Original Properties class initialization failed: '+str(list(properties_init)))
            properties=new(classes['java/util/Properties'])
            source(methods['java/util/Properties','<init>','()V'],[properties])
            setter=methods['java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;']
            key=string('java.net.preferIPv4Stack')
            source(setter,[properties,key,string('false')])
            source(methods['java/lang/System','setProperties','(Ljava/util/Properties;)V'],[properties])
            S.check(P.from_address(cell).value==properties,'The actual Java setter did not publish the source Properties object')
            ws=c.WinDLL('ws2_32.dll')
            socket=proc(ws,'socket',c.c_size_t,c.c_int,c.c_int,c.c_int)
            close_socket=proc(ws,'closesocket',c.c_int,c.c_size_t)
            last_error=proc(ws,'WSAGetLastError',c.c_int)
            for wanted in (False,True):
                source(setter,[properties,key,string(str(wanted).lower())])
                S.check(source(methods['java/lang/Boolean','getBoolean','(Ljava/lang/String;)Z'],[key])==wanted,
                        'Original Boolean.getBoolean did not read the actual source Properties value')
                lib=library()
                context,value=native('load',[lib,net,1,1])
                net_pool=addr(image,'boom_builtin_net_pool')
                S.check(not context[0] and value==1 and published(lib)==(image._handle,0x10008) and
                        U.from_address(net_pool+28).value==wanted and
                        (not wanted or U.from_address(net_pool+36).value==0),'net ignored its real original Java preference')
                real=socket(2,1,0)
                S.check(real!=c.c_size_t(-1).value and close_socket(real)==0,'Loaded net callback lost its real Winsock owner')
                context,_=native('unload',[net,1,image._handle])
                S.check(not context[0] and not Q.from_address(pins).value and
                        Q.from_address(net_pool+48).value==Q.from_address(net_pool+56).value,
                        'net unload failed to balance its actual module pin or Winsock reference')
                S.check(socket(2,1,0)==c.c_size_t(-1).value and last_error()==10093,
                        'net unload leaked the process-local Winsock reference')
            S.check(Q.from_address(addr(image,'boom_native_library_property_reads')).value==2,
                    'The net body did not execute both real original Java property callbacks')
            property_success=True
        result=dict(source_builtin_find_load_unload_verified=True,actual_owner_HMODULE=image._handle,
            static_wrapper_JNI_version=0x10008,real_OS_threads=8,one_pin_for_eight_simultaneous_loads=True,
            final_owner_pins=0,source_fields_written_only_after_callback=True,existing_exception_preserved=True,
            unknown_module_and_standard_JNI_blocked=True,net_without_source_properties_blocked=True,
            net_real_Java_property_success_path_executed=property_success,
            source_property_setup='original Properties constructor/setProperty and unchanged System.setProperties' if property_success else None,
            original_Properties_class_init_and_constructor_completed=property_success,
            full_Phase1_cold_start_completed=False)
    S.check(detach(registry)==0 and bind(None)==0 and proc(rt,'boom_threads_destroy',U,P)(registry)==0,
            'Library test registry cleanup failed')
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Library test heap cleanup failed')
    result.update(candidate=S.artifact(candidate_file),test_tool=S.artifact(Path(__file__)),discovery_cases=discoveries,
        source_Thread_and_library_Java_constructors_called=False,original_NativeLibraries_cold_Java_init_completed=False,
        standard_JavaVM_or_JNIEnv_pointer_exposed=False,game_started=False)
    path=candidate_file.parent/'execution.json'
    S.write(path,result)
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate',type=Path)
    print(run(parser.parse_args().candidate.resolve(strict=True)))
