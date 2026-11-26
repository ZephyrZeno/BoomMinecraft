"""Exercise real translated Java and a source-verified diagnostic NIO binding."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Barrier, Event, get_native_id
from time import monotonic, sleep
from uuid import uuid4
import _winapi


ROOT = Path(__file__).resolve().parents[1]
P,U,Q = c.c_void_p,c.c_uint32,c.c_uint64
Context = U*8


def check(value,reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def checked(record):
    path=Path(record['path'])
    check(path.stat().st_size==record['digest']['size'] and sha(path)==record['digest']['sha256'],
          'Candidate artifact changed: '+str(path))
    return path


def proc(image,name,result,*args):
    f=getattr(image,name)
    f.restype,f.argtypes=result,args
    return f


def addr(image,name):
    return c.addressof(c.c_byte.in_dll(image,name))


def samples(module_path,parent):
    yield module_path,True
    yield parent,False
    yield parent/'absent-file',None
    with TemporaryDirectory(dir=parent) as tmp:
        directory=Path(tmp).resolve()
        check(directory.parent==parent,'Fixture directory escaped the candidate directory')
        target,junction=directory/'target',directory/'junction'
        target.mkdir()
        _winapi.CreateJunction(str(target),str(junction))
        yield junction,'junction'


def jdk_library_names(java_home,work,names):
    oracle=r'''class LibraryNameOracle {
        public static void main(String[] names) {
            for (String input : names) {
                StringBuilder original = new StringBuilder();
                for (int i=0; i<input.length(); i+=4) {
                    original.append((char)Integer.parseInt(input.substring(i, i+4), 16));
                }
                String mapped = System.mapLibraryName(original.toString());
                StringBuilder hex = new StringBuilder();
                for (int i=0; i<mapped.length(); i++) hex.append("%04x".formatted((int)mapped.charAt(i)));
                System.out.println(hex);
            }
            try { System.mapLibraryName("x".repeat(241)); throw new AssertionError(); }
            catch (IllegalArgumentException ex) { System.out.println(ex.getMessage()); }
            try { System.mapLibraryName(null); throw new AssertionError(); }
            catch (NullPointerException ex) { System.out.println(ex.getClass().getName()); }
        }
    }'''
    java=java_home/'bin/java.exe'
    with TemporaryDirectory(dir=work) as tmp:
        source=Path(tmp)/'LibraryNameOracle.java'
        source.write_text(oracle,encoding='ascii')
        values=[n.encode('utf-16-be',errors='surrogatepass').hex() for n in names]
        process=subprocess.run([java,source,*values],check=True,capture_output=True,timeout=45)
    results=process.stdout.decode('ascii').splitlines()
    check(len(results)==len(names)+2 and results[-2:]==['name too long','java.lang.NullPointerException'],
          'Locked JDK library-name exceptions differ')
    return [bytes.fromhex(v).decode('utf-16-be',errors='surrogatepass') for v in results[:-2]]


def run(candidate_file,config_file,boundary=None):
    cfg, candidate=read(config_file),read(candidate_file)
    path=checked(candidate['image'])
    checked(candidate['base_proof'])
    for artifact in candidate['source_inputs']+candidate['generated_assembly']:
        checked(artifact)
    if candidate.get('formal_provider_selection'):
        if candidate.get('formal_provider_input_state'):
            checked(candidate['formal_provider_input_state'])
        summary=read(checked(candidate['source_batch']))
        check(read(checked(candidate['source_batch_verification']))['verified'] and
              candidate['unsafe_carrier'] is None and candidate['boot_unnamed_candidate'] is None,
              'Formal NIO must use the verified batch without previous carrier or JCLS overlays')
        source=read(Path(candidate['selection_directory'])/'closure.json')
        check(source['runtime_provider_packs']==candidate['formal_provider_selection'] and
              candidate['boot_unnamed_provider'] in candidate['formal_provider_selection'],
              'Formal NIO provider list differs from the source-verified selection')
        for record in candidate['formal_provider_selection']:
            pack=checked(record['manifest'])
            proof=read(checked(record['verification']))
            check(proof['verified'] and proof['provider_manifest_sha256']==sha(pack),
                  'Formal NIO provider receipt differs')
        boot=read(checked(candidate['boot_unnamed_metadata']))
        check(boot['slot']==summary['class_literals']['bootstrap_unnamed_module_slot'] and
              boot['strong_roots']==summary['class_literals']['root_cells'],
              'Formal NIO changed the original JCLS root layout')
        jcls=checked(candidate['jcls_object'])
        check(not candidate['jcls_object_replaced'] and
              checked(candidate['link_response']).read_text().splitlines().count('"'+str(jcls)+'"')==1,
              'Formal NIO must link the verified JCLS COFF exactly once without replacement')
    runtime=Path(candidate['runtime'])
    check(sha(runtime/'boom-runtime.dll')==read(runtime/'runtime.json')['sha256'],'Assembly runtime changed')
    with os.add_dll_directory(str(runtime)):
        rt,im=c.CDLL(str(runtime/'boom-runtime.dll')),c.CDLL(str(path))
    pool=addr(im,'boom_nio_buffer_pool')
    check(U.from_address(pool).value==0x424f494e and not Q.from_address(pool+40).value,'Expected cold owned pool')
    base=read(Path(cfg['batch'])/'summary.json')
    module_image=read(base['frames']['original_system_catalog']['path'])['image']
    module_path=Path(module_image['path'])
    check(sha(module_path)==module_image['digest']['sha256'],'JDK lib/modules differs from locked source')
    initial=proc(rt,'boom_heap_create',P,Q)(128<<20)
    check(initial and proc(im,'boom_java_string_literals_bind_heap',U,P)(initial)==1,'Guest heap bind failed')
    obj=proc(rt,'boom_object_new',P,P,P,P)
    array=proc(rt,'boom_array_new',P,P,c.c_int,U,P)
    ensure=proc(rt,'boom_class_ensure32',U,P,P)
    owners=candidate['source_classes']
    methods={(v['owner'],v['name'],v['descriptor']):v['method'] for v in candidate['methods']+candidate['original_Java']}
    def call(id_,ctx,arguments,suffix=''):
        args=(Q*len(arguments))(*arguments)
        return proc(im,f'boom_m{id_}'+suffix,Q,P,P)(ctx,args)
    def new(name):
        ctx=Context()
        value=obj(initial,addr(im,'boom_layout'+str(owners[name])),ctx)
        check(value and not ctx[0],f'Cannot allocate source-layout {name}: {list(ctx)}')
        return value
    def must(id_,arguments,suffix=''):
        ctx=Context()
        value=call(id_,ctx,arguments,suffix)
        check(not ctx[0] and not ctx[3],f'boom_m{id_}{suffix} stopped: {list(ctx)}')
        return value
    read_int,read_long,put_char=[m['method'] for m in candidate['methods'][4:7]]
    allocate,release,copy,query=[m['method'] for m in candidate['methods'][:4]]
    attrs='sun/nio/fs/WindowsFileAttributes'
    cls='java/lang/String'
    little_string=methods[cls,'<init>','([C)V']
    get_chars=methods[cls,'toCharArray','()[C']
    ctor=methods[attrs,'<init>','(IJJJJIIII)V']
    test=methods[attrs,'isRegularFile','()Z']
    init_ctx=Context()
    ensure(addr(im,'boom_class'+str(owners['jdk/internal/misc/Unsafe'])),init_ctx)
    source_unsafe_state=list(init_ctx[:4])
    check(not init_ctx[0], 'Original Unsafe.<clinit> failed')
    closure=read(Path(candidate['selection_directory'])/'closure.json')
    unsafe_class=next(k for k in closure['selected_classes'] if k['name']=='jdk/internal/misc/Unsafe')
    singleton=next(f['index'] for f in unsafe_class['fields'] if f['name']=='theUnsafe')
    unsafe=P.from_address(addr(im,f"boom_s{unsafe_class['class_id']}_{singleton}")).value
    check(unsafe, 'Original Unsafe.<clinit> did not publish its singleton')
    java_alloc=methods['jdk/internal/misc/Unsafe','allocateMemory','(J)J']
    java_free=methods['jdk/internal/misc/Unsafe','freeMemory','(J)V']
    staged_ids=set()
    oracle=proc(im,'boom_win32_path_attributes',U,c.c_wchar_p,U,P)
    proofs=[]
    raised=None
    def boundary_result(label,context,returned):
        selection=Path(candidate['selection_directory'])
        diagnostic=read(selection/'diagnostic.json')
        global_stop=addr(im,'boom_diagnostic_pool')
        row=None
        local=None
        if U.from_address(global_stop+8).value==2:
            rowid=U.from_address(global_stop+32).value
            row=next(r for r in diagnostic['rows'] if r['id']==rowid)
            row={k:row.get(k) for k in ('id','symbol','category','method','binding')}
        if candidate.get('per_context_diagnostic_rows') and context[0]==0xb001:
            rowid=proc(im,'boom_diagnostic_context_map_row',U,P,P)(context,addr(im,'boom_diagnostic_context_map'))
            source=next((r for r in diagnostic['rows'] if r['id']==rowid),None)
            check(source is not None,'Source stop lost its Context32 row')
            local={k:source.get(k) for k in ('id','symbol','category','method','binding')}
        return dict(entry=label,context=list(context[:4]),returned=int(returned),diagnostic_first=row,context_row=local)
    def finish_boundary(observed):
        live_count=Q.from_address(pool+40).value
        observed['native_buffer_allocations_remaining']=live_count
        if candidate.get('boot_unnamed_candidate') or candidate.get('boot_unnamed_provider'):
            if candidate.get('boot_unnamed_provider'):
                info=read(checked(candidate['boot_unnamed_metadata']))
                slot,owner,index,expected_roots=info['slot'],info['owner'],info['static_field'],info['strong_roots']
            else:
                boot=read(checked(candidate['boot_unnamed_candidate']))
                info=boot['contract']
                slot,owner,index,expected_roots=info['module_slot'],info['owner'],info['static_index'],boot['gc_roots_after']
            roots=addr(im,'boom_java_class_module_roots')
            installed=P.from_address(roots+slot*8).value
            static_root=P.from_address(addr(im,f"boom_s{owner}_{index}")).value
            count=U.from_address(addr(im,'boom_java_class_root_count')).value
            check(count==expected_roots and (not installed or installed==static_root),
                  'Installed bootstrap module root does not match original Java static')
            observed['boot_unnamed_module']=dict(module_slot=slot,gc_root_count=count,
                source_static_published=bool(static_root),normal_module_root_published=bool(installed))
        observed['guest_monitor_acquisitions']=Q.from_address(initial+112).value
        observed['heap_destroyed']=bool(proc(rt,'boom_heap_destroy',U,P)(initial))
        if preparation:
            observed['source_properties_preparation']=preparation
        if vm_prerequisites:
            observed['vm_prerequisites']=vm_prerequisites
        return observed
    observed=None
    preparation=None
    vm_prerequisites=[]
    if boundary and boundary.endswith('-vm-properties'):
        # The production VM bootstrap initializes Method and its superclasses
        # before running System.initPhase1. In particular AccessibleObject's
        # original initializer installs SharedSecrets.javaLangReflectAccess.
        classes={v['name']:v['class_id'] for v in closure['selected_classes']}
        for name in ('java/lang/String','java/lang/System','java/lang/Class','java/lang/reflect/Method'):
            entry=Context()
            ensure(addr(im,'boom_class'+str(classes[name])),entry)
            record=boundary_result('VM prerequisite '+name,entry,0)
            vm_prerequisites.append(record)
            if entry[0]:
                vm_prerequisites.pop()
                return finish_boundary(record)
        boundary=boundary.replace('-vm-properties','-properties')
    if boundary and boundary.endswith('-properties'):
        check(('java/lang/System','initPhase1','()V') in methods,'Selected original System.initPhase1 required')
        prep=Context()
        call(methods['java/lang/System','initPhase1','()V'],prep,[])
        system=next(k for k in closure['selected_classes'] if k['name']=='java/lang/System')
        props=next(f['index'] for f in system['fields'] if f['name']=='props')
        preparation=dict(entry='System.initPhase1',context=list(prep[:4]),published_System_props=bool(
            P.from_address(addr(im,f"boom_s{system['class_id']}_{props}")).value))
        preparation['prior_global_diagnostic']=boundary_result('System.initPhase1',prep,0)['diagnostic_first']
        if prep[0]:
            return finish_boundary(boundary_result('System.initPhase1',prep,0))
        boundary=boundary.removesuffix('-properties')
    for requested,regular in samples(module_path,path.parent):
        encoded=str(requested).encode('utf-16-le')
        ctx=Context()
        chars=array(initial,len(encoded)//2,5,ctx)
        check(chars and not ctx[0],'Cannot create source bootstrap char[]')
        c.memmove(chars,encoded,len(encoded))
        string=new(cls)
        must(little_string,[string,chars])
        decoded=must(get_chars,[string])
        check(decoded and decoded!=chars and c.string_at(decoded,len(encoded))==encoded,
              'Original String constructor/toCharArray changed the requested path')
        staged_ids.update((little_string,get_chars))
        if boundary=='files':
            fs=new('sun/nio/fs/WindowsFileSystem')
            provider=new('sun/nio/fs/WindowsFileSystemProvider')
            P.from_address(fs+candidate['filesystem_provider_field']['offset']).value=provider
            constructor=methods['sun/nio/fs/WindowsPath','createFromNormalizedPath',
                '(Lsun/nio/fs/WindowsFileSystem;Ljava/lang/String;)Lsun/nio/fs/WindowsPath;']
            path_ctx=Context()
            original_path=call(constructor,path_ctx,[fs,string])
            if path_ctx[0]:
                observed=boundary_result('WindowsPath.createFromNormalizedPath',path_ctx,original_path)
            else:
                typed=proc(rt,'boom_typed_multi_new',P,P,P,P,U,P)
                options=typed(initial,(Q*1)(0),addr(im,'boom_t'+str(candidate['link_option_array'])),1,path_ctx)
                check(options and not path_ctx[0],'Cannot allocate typed empty LinkOption[]')
                files=methods['java/nio/file/Files','isRegularFile',
                    '(Ljava/nio/file/Path;[Ljava/nio/file/LinkOption;)Z']
                result=call(files,path_ctx,[original_path,options])
                observed=boundary_result('Files.isRegularFile',path_ctx,result)
            observed['filesystem_receiver_fixture']=dict(source_layout_provider_reference_assigned=True,
                original_filesystem_constructor_called=False,default_filesystem_startup_completed=False)
            break
        name=must(java_alloc,[unsafe,len(encoded)+2])
        output=must(java_alloc,[unsafe,36])
        check(name and output and Q.from_address(pool+40).value==2,'Owned native range was not retained')
        try:
            must(copy,[unsafe,decoded,0,0,name,len(encoded)])
            must(put_char,[unsafe,0,name+len(encoded),0])
            if boundary=='dispatcher':
                ctx=Context()
                result=call(query,ctx,[name,output])
                observed=boundary_result('WindowsNativeDispatcher.GetFileAttributesEx0',ctx,result)
                break
            if regular is None:
                failure=Context()
                c.memset(output,0xa7,36)
                call(query,failure,[name,output],'_native')
                check(failure[0]==16 and c.string_at(output,36)==b'\xa7'*36,
                      'Original WindowsException was not published for missing file: '+str(list(failure)))
                thrown=P.from_address(c.addressof(failure)+16).value
                last_error=methods['sun/nio/fs/WindowsException','lastError','()I']
                raised=must(last_error,[thrown])
                check(raised==2,'Original WindowsException.lastError does not contain ERROR_FILE_NOT_FOUND')
                continue
            must(query,[name,output],'_native')
            if boundary=='decode':
                ctx=Context()
                decoder=methods[attrs,'fromFileAttributeData','(JI)Lsun/nio/fs/WindowsFileAttributes;']
                bean=call(decoder,ctx,[output,0])
                result=call(test,ctx,[bean]) if bean and not ctx[0] else 0
                observed=boundary_result('WindowsFileAttributes.fromFileAttributeData -> isRegularFile',ctx,result)
                break
            values=[must(id_,[unsafe,0,output+offset],'_native') for id_,offset in (
                (read_int,0),(read_long,4),(read_long,12),(read_long,20),(read_int,28),(read_int,32))]
            state,cr,ac,wr,high,low=values
            size=(high<<32)|low
            if regular=='junction':
                no_follow=(c.c_ubyte*48)()
                followed=(c.c_ubyte*48)()
                check(state&0x400 and oracle(str(requested),0,no_follow)==0 and oracle(str(requested),1,followed)==0 and
                      U.from_buffer(no_follow,4).value==0xa0000003 and not U.from_buffer(followed).value&0x400,
                      'Raw JNI metadata followed the junction or lost its reparse flag')
                continue
            check(not state&0x400,'Source-tail fast path applies only to original non-reparse attributes')
            bean=new(attrs)
            must(ctor,[bean,state,cr,ac,wr,size,0,0,0,0])
            actual=must(test,[bean])
            baseline=(c.c_byte*48)()
            check(oracle(str(requested),1,baseline)==0,'Reference production kernel failed')
            raw=struct.unpack('<IIQQQQII',bytes(baseline))
            check(actual==regular and bool(raw[6]&1)==regular and raw[0]==state and raw[4]==wr and raw[5]==size,
                  'Original Java attributes.classification differs from Win32')
            proofs.append(dict(path=str(requested),regular=bool(actual),bytes=size,file_time=wr))
            staged_ids.update((ctor,test))
            # Both source address and destination must belong to the live arena.
            for invalid in ((name,output+8),(1,output)):
                failed=Context()
                before=c.string_at(output,36)
                call(query,failed,invalid,'_native')
                check(failed[0]==20 and c.string_at(output,36)==before,'Unowned/truncated guest range was used')
        finally:
            must(java_free,[unsafe,output])
            must(java_free,[unsafe,name])
        dead=Context()
        call(query,dead,[name,output],'_native')
        check(dead[0]==20 and not Q.from_address(pool+40).value,'Released native range was retained')
    if boundary:
        live_count=Q.from_address(pool+40).value
        check(observed and (boundary=='files' or not live_count),'Boundary run left a directly owned native allocation')
        return finish_boundary(observed)
    registration=None
    referent_result=None
    parallel_queries=None
    if candidate.get('owned_buffer_abi')==2:
        check(U.from_address(pool+4).value==2 and candidate['allocation_header_bytes']==32,'Wrong NIO allocation ABI')
        os_kernel=c.WinDLL('kernel32.dll',use_last_error=True)
        take=proc(os_kernel,'AcquireSRWLockExclusive',None,P)
        drop=proc(os_kernel,'ReleaseSRWLockExclusive',None,P)
        try_take=proc(os_kernel,'TryAcquireSRWLockExclusive',c.c_ubyte,P)
        raw_attributes=(c.c_byte*36)()
        direct=proc(os_kernel,'GetFileAttributesExW',c.c_int,c.c_wchar_p,c.c_int,P)
        check(not direct('',0,raw_attributes),'Empty-path failure oracle unexpectedly succeeded')
        empty_error=c.get_last_error()
        check(empty_error,'Empty-path failure oracle did not retain its Win32 error')
        allocations=[]
        def query_pair(text):
            raw=str(text).encode('utf-16-le')
            ctx=Context()
            chars=array(initial,len(raw)//2,5,ctx)
            check(chars and not ctx[0],'Cannot allocate concurrent query path')
            c.memmove(chars,raw,len(raw))
            name=must(java_alloc,[unsafe,len(raw)+2])
            out=must(java_alloc,[unsafe,36])
            allocations.extend((name,out))
            must(copy,[unsafe,chars,0,0,name,len(raw)])
            must(put_char,[unsafe,0,name+len(raw),0])
            return name,out
        def await_query_lock():
            deadline=monotonic()+5
            while try_take(pool+24):
                drop(pool+24)
                check(monotonic()<deadline,'Query did not acquire its shared lifetime lock')
                sleep(.001)
        try:
            first=query_pair(module_path)
            second=query_pair(module_path.parent)
            lock_address=first[0]-candidate['allocation_header_bytes']+16
            with ThreadPoolExecutor(2) as workers:
                take(lock_address)
                try:
                    blocked=workers.submit(must,query,first,'_native')
                    await_query_lock()
                    completed=workers.submit(must,query,second,'_native')
                    completed.result(timeout=5)
                    check(not blocked.done() and U.from_address(second[1]).value&16,
                          'Independent directory query failed while first file query was blocked')
                finally:
                    drop(lock_address)
                blocked.result(timeout=5)
            check(not U.from_address(first[1]).value&16,'Resumed file query returned directory attributes')
            parallel_queries=dict(independent_real_Win32_query_finished_while_peer_held=True,
                                  overlap_used_distinct_live_allocations=True)
            # A pending free must retain the allocation until the actual query
            # leaves its lifetime lease, including while it waits on a node.
            started=Event()
            def free_first():
                started.set()
                must(java_free,[unsafe,first[0]])
            with ThreadPoolExecutor(2) as workers:
                take(lock_address)
                try:
                    blocked=workers.submit(must,query,first,'_native')
                    await_query_lock()
                    freeing=workers.submit(free_first)
                    check(started.wait(5),'Free worker did not enter the native-call fixture')
                    sleep(.05)
                    check(not freeing.done() and Q.from_address(pool+40).value==4,
                          'Concurrent free retired a buffer still owned by a query')
                finally:
                    drop(lock_address)
                blocked.result(timeout=5)
                freeing.result(timeout=5)
            allocations.remove(first[0])
            check(Q.from_address(pool+40).value==3 and not U.from_address(first[1]).value&16,
                  'Query/free handoff lost the file result or allocation ownership')
            dead=Context()
            call(query,dead,first,'_native')
            check(dead[0]==20,'A freed native query name was still accepted')
            parallel_queries['query_lease_delayed_concurrent_free']=True
            # Both addresses can be in one allocation. It needs one node lock,
            # and copying the attributes must not overwrite the path itself.
            raw=str(module_path).encode('utf-16-le')
            output_offset=(len(raw)+9)&~7
            combined=must(java_alloc,[unsafe,output_offset+36])
            allocations.append(combined)
            c.memmove(combined,raw+b'\0\0',len(raw)+2)
            must(query,[combined,combined+output_offset],'_native')
            check(c.string_at(combined,len(raw)+2)==raw+b'\0\0' and
                  not U.from_address(combined+output_offset).value&16,'Single-node query corrupted its owned path')
            parallel_queries['same_allocation_path_and_output_completed']=True
            # Opposite source/output order on the same two allocations must not
            # deadlock. Empty paths yield original WindowsException failures and
            # leave both buffers unchanged, so every iteration stays valid.
            left,right=[must(java_alloc,[unsafe,64]) for _ in range(2)]
            allocations.extend((left,right))
            c.memset(left,0,64)
            c.memset(right,0,64)
            crossing=Barrier(8,timeout=15)
            def opposite(i):
                crossing.wait()
                args=(left,right) if i&1 else (right,left)
                errors=[]
                for _ in range(50):
                    ctx=Context()
                    call(query,ctx,args,'_native')
                    check(ctx[0]==16 and not ctx[3],'Opposite-order query lost its source WindowsException')
                    thrown=P.from_address(c.addressof(ctx)+16).value
                    errors.append(must(methods['sun/nio/fs/WindowsException','lastError','()I'],[thrown]))
                return get_native_id(),set(errors)
            with ThreadPoolExecutor(8) as workers:
                results=list(workers.map(opposite,range(8)))
            check(len({t for t,_ in results})==8 and all(errors=={empty_error} for _,errors in results) and
                  c.string_at(left,64)==c.string_at(right,64)==bytes(64),
                  'Opposite-order query failed or wrote through an error result')
            parallel_queries.update(opposite_buffer_order_OS_threads=8,opposite_buffer_order_calls=400,
                                    empty_path_Win32_error=empty_error)
        finally:
            for allocated in reversed(allocations):
                must(java_free,[unsafe,allocated])
    mapped_names=None
    library_key=('java/lang/System','mapLibraryName','(Ljava/lang/String;)Ljava/lang/String;')
    if library_key in methods:
        def string_value(value):
            encoded=value.encode('utf-16-le',errors='surrogatepass')
            ctx=Context()
            chars=array(initial,len(encoded)//2,5,ctx)
            check(chars and not ctx[0],'Cannot allocate library-name char[]')
            c.memmove(chars,encoded,len(encoded))
            text=new(cls)
            must(little_string,[text,chars])
            return text
        def source_text(value):
            chars=must(get_chars,[value])
            size=Q.from_address(chars-16).value
            return c.string_at(chars,size).decode('utf-16-le',errors='surrogatepass')
        mapping=methods[library_key]
        names=['','net','nio','中文','\U0001f600','raw\0name','\ud800','x'*240]
        expected=jdk_library_names(module_path.parents[1],path.parent,names)
        for original,wanted in zip(names,expected,strict=True):
            guest=string_value(original)
            mapped=must(mapping,[guest],'_native')
            check(mapped and mapped!=guest and source_text(mapped)==wanted,'Windows library name differs from the locked JDK')
        failed=Context()
        call(mapping,failed,[0],'_native')
        check(failed[0]==4,'Null library name did not raise the source null error')
        failed=Context()
        call(mapping,failed,[string_value('x'*241)],'_native')
        error=P.from_address(c.addressof(failed)+16).value
        check(failed[0]==16 and error,'Long library name did not raise a source exception: '+str(list(failed)))
        check(source_text(must(methods['java/lang/Throwable','getMessage','()Ljava/lang/String;'],[error]))=='name too long',
              'Original exception message for long library name differs')
        mapped_names=dict(cases=len(names),null_error=4,typed_length_limit_error=True,utf16_limit=240)
    if candidate.get('source_referent_field'):
        field=candidate['source_referent_field']
        soft='java/lang/ref/SoftReference'
        reference='java/lang/ref/Reference'
        receiver=new(soft)
        target=new(cls)
        referent_address=receiver+field['soft_offset']
        native=methods[reference,'get0','()Ljava/lang/Object;']
        check(must(native,[receiver],'_native')==0,'Empty SoftReference had a referent')
        # Use the original constructor when its independent class-initialization
        # dependencies are present. The direct field-domain fixture is separate.
        construction=Context()
        call(methods[soft,'<init>','(Ljava/lang/Object;)V'],construction,[receiver,target])
        real_constructor=not construction[0]
        if real_constructor:
            check(P.from_address(referent_address).value==target,'Original SoftReference constructor lost its referent')
            check(must(methods[reference,'get','()Ljava/lang/Object;'],[receiver])==target,
                  'Translated original Reference.get did not read the constructed referent')
        else:
            P.from_address(referent_address).value=target
        check(must(native,[receiver],'_native')==target,'Inherited SoftReference.referent returned a different object')
        P.from_address(referent_address).value=None
        check(not must(native,[receiver],'_native'),'Cleared SoftReference still had a referent')
        for bad,kind in ((0,4),(target,7),(1,7)):
            failed=Context()
            check(not call(native,failed,[bad],'_native') and failed[0]==kind,'Invalid Reference read succeeded')
        P.from_address(referent_address).value=1
        failed=Context()
        check(not call(native,failed,[receiver],'_native') and failed[0]==7,'Foreign referent escaped the guest heap')
        P.from_address(referent_address).value=None
        referent_result=dict(source_native_method=native,original_constructor_completed=real_constructor,
                             constructor_context=list(construction[:4]),inherited_map_id=field['map_id'],
                             null_cleared_foreign_and_wrong_type_checked=True)
    if candidate.get('dispatcher_fields'):
        ident=methods['sun/nio/fs/WindowsNativeDispatcher','initIDs','()V']
        slot=addr(im,'boom_nio_dispatcher_ids_pool')
        check(not P.from_address(slot+24).value,'Expected cold JNI field publication')
        latch=Barrier(8,timeout=15)
        def register(_):
            latch.wait()
            must(ident,[],'_native')
            return get_native_id(),P.from_address(slot+24).value
        with ThreadPoolExecutor(8) as workers:
            observed_fields=list(workers.map(register,range(8)))
        table=P.from_address(slot+16).value
        check(table and len({tid for tid,_ in observed_fields})==8 and {row for _,row in observed_fields}=={table},
              'Dispatcher field publication differed across native threads')
        for i,f in enumerate(candidate['dispatcher_fields']):
            row=table+48*i
            specs=struct.unpack('<6I',c.string_at(row+24,24))
            check(specs==(f['class_id'],f['index'],f['offset'],f['width'],int(f['reference']),0) and
                  all(P.from_address(row+k).value for k in (0,8,16)),'Published JNI field ID does not match locked source')
        registration=dict(source_native_method=ident,fields=len(candidate['dispatcher_fields']),threads=len(observed_fields))
    gate=Barrier(8,timeout=15)
    def simultaneous(_):
        allocated=must(java_alloc,[unsafe,64])
        check(allocated,'Concurrent source allocation failed')
        try:
            gate.wait()
            must(put_char,[unsafe,0,allocated,0x41])
            must(put_char,[unsafe,0,allocated+2,0x42])
            check(must(read_int,[unsafe,0,allocated])==0x00420041,'Concurrent owned-buffer access returned wrong bytes')
            return get_native_id(),allocated
        finally:
            must(java_free,[unsafe,allocated])
    with ThreadPoolExecutor(8) as workers:
        live=list(workers.map(simultaneous,range(8)))
    check(len({t for t,_ in live})==len({p for _,p in live})==8 and Q.from_address(pool+40).value==0,
          'Live native buffer ranges overlapped across threads or failed to release')
    report=dict(source_Java_tail_succeeded=True,files=proofs,original_Java_methods=sorted(staged_ids),
                candidate_manifest_sha256=sha(candidate_file),candidate_image_sha256=sha(path),
                unsafe_class_init_context=source_unsafe_state,live_native_allocations=0,
                fixture_input='guest char[] supplied to translated original String.<init>(char[])',
                full_Files_isRegularFile_completed=False,
                original_Unsafe_singleton_used=True,original_Java_allocation_methods=[java_alloc,java_free],
                win32_failure_tested=True,WindowsException_lastError=raised,raw_junction_reparse_bit_preserved=True,
                original_Reference_get0=referent_result,windows_library_names=mapped_names,
                concurrent_native_file_queries=parallel_queries,
                formal_provider_count=len(candidate.get('formal_provider_selection') or []),
                verified_batch_JCLS_used_without_replacement=bool(candidate.get('formal_provider_selection')),
                parallel_OS_threads=len(live),dispatcher_JNI_field_registration=registration,game_started=False)
    check(proc(rt,'boom_heap_destroy',U,P)(initial)==1,'Guest heap cleanup failed')
    boundaries={}
    stages=['files','decode','dispatcher']
    if ('java/lang/System','initPhase1','()V') in methods:
        stages += [s+'-properties' for s in stages]+['files-vm-properties','dispatcher-vm-properties']
    for stage in stages:
        child=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(candidate_file),'--config',str(config_file),
                              '--boundary',stage],capture_output=True,timeout=60)
        check(child.returncode==0,'Fresh source boundary probe failed: '+child.stderr.decode(errors='replace'))
        boundaries[stage]=json.loads(child.stdout)
    report['fresh_process_boundaries']=boundaries
    report['source_dispatcher_class_initializing_adapter_called']=True
    report['full_Files_isRegularFile_completed']=any(v['entry']=='Files.isRegularFile' and
        v['context'][0]==0 and v['returned']==1 for v in boundaries.values())
    report['WindowsNativeDispatcher_initializer_completed']=any(
        v['entry']=='WindowsNativeDispatcher.GetFileAttributesEx0' and v['context'][0]==0 for v in boundaries.values())
    report['default_filesystem_startup_completed']=False
    dest=path.parent/('execution-'+uuid4().hex+'.json')
    dest.write_text(json.dumps(report,indent=2)+'\n')
    return dest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate',type=Path)
    parser.add_argument('--config',type=Path,default=ROOT/'.boom/pending-native-module-packages-v141.json')
    parser.add_argument('--boundary',choices=['files','decode','dispatcher','files-properties','decode-properties',
                        'dispatcher-properties','files-vm-properties','dispatcher-vm-properties'],help=argparse.SUPPRESS)
    args=parser.parse_args()
    result=run(args.candidate,args.config,args.boundary)
    print(json.dumps(result) if args.boundary else result)
