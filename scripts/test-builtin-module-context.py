"""Exercise restricted MASM module callbacks against actual source Thread attachment.

Thread receivers use original layouts with no Java constructor invocation. This
tests the real VM registry/FLS and typed native boundary, not normal VM startup.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import importlib.util
import json
import os
from pathlib import Path
from threading import Barrier, get_native_id
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'
spec=importlib.util.spec_from_file_location('builtin_context_source_tools',ROOT/'scripts/nio-file-native-candidate.py')
N=importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)
S=N.S
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8
KERNEL=ROOT/'native/providers/builtin_module_context.asm.inc'
EXPORTS={'boom_builtin_module_check','boom_builtin_nio_body','boom_builtin_nio_on_load','boom_builtin_module_pool'}


def proc(image,name,result,*arguments):
    f=getattr(image,name)
    f.restype,f.argtypes=result,arguments
    return f


def addr(image,name):
    return c.addressof(c.c_byte.in_dll(image,name))


def build(nio_file,output):
    nio_file,output=nio_file.resolve(strict=True),output.resolve()
    S.check(output.is_relative_to(ART),'Keep module-context images inside project .boom')
    source=S.read(nio_file)
    S.checked(source['image'])
    proof=S.read(S.checked(source['base_proof']))
    selection=Path(source['selection_directory'])
    closure=S.read(selection/'closure.json')
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(selection/'closure.json')['sha256'] and
            source['formal_provider_selection']==closure['runtime_provider_packs'],
            'Source-verified formal NIO candidate required')
    packs=[(ref,S.read(S.checked(ref['manifest']))) for ref in source['formal_provider_selection']]
    ref,pack=next((r,m) for r,m in packs if m['family']=='normal-thread-primitives-v1')
    accepted=S.read(S.checked(ref['verification']))
    S.check(accepted['verified'] and accepted['provider_manifest_sha256']==ref['manifest']['digest']['sha256'] and
            str(S.checked(pack['object'])) in closure['objects'],'The actual Thread provider must be linked and accepted')
    meta=S.read(S.checked(pack['normal_thread_metadata']))
    names={row['name']:row for row in closure['selected_classes']}
    thread,virtual=meta['thread_class'],meta['virtual_base_class']
    string=source['source_classes']['java/lang/String']
    S.check(thread==names['java/lang/Thread']['class_id'] and virtual==names['java/lang/BaseVirtualThread']['class_id'],
            'Original Thread and virtual-thread type identities differ')
    output.mkdir(parents=True,exist_ok=False)
    imports={'boom_heap_ptr','boom_provider_thread_registry','boom_runtime_type_map',f'boom_t{thread}',f'boom_t{virtual}',
             'boom_threads_current','boom_heap_contains','boom_runtime_type','boom_type_assignable'}
    text=('option casemap:none\nEXTERN boom_heap_ptr:BYTE\nEXTERN boom_provider_thread_registry:BYTE\n'
          f'EXTERN boom_runtime_type_map:BYTE\nEXTERN boom_t{thread}:BYTE\nEXTERN boom_t{virtual}:BYTE\n'+KERNEL.read_text()+
          '\n.const\nALIGN 8\nPUBLIC boom_builtin_module_pool\nboom_builtin_module_pool DWORD 043424D56h,1\n'
          f' QWORD OFFSET boom_heap_ptr,OFFSET boom_provider_thread_registry,OFFSET boom_runtime_type_map,'
          f'OFFSET boom_t{thread},OFFSET boom_t{virtual}\nEND\n')
    asm,obj=output/'module-context.asm',output/'module-context.obj'
    asm.write_text(text)
    tools=N.msvc()
    N.run([tools/'ml64.exe','/nologo','/c','/Fo'+str(obj),asm],output,'assemble.log')
    S.check(N.A.coff_symbols(obj)==(EXPORTS,imports),'Restricted module COFF imports or exports differ')
    original=S.checked(source['link_response']).read_text().splitlines()
    exports={line.removeprefix('/EXPORT:') for line in original if line.startswith('/EXPORT:')}
    exports|=EXPORTS|{f'boom_layout{thread}',f'boom_layout{string}'}
    dll=output/'module-context.dll'
    lines=[line for line in original if not line.startswith(('/EXPORT:','/OUT:'))]
    lines+=['/OUT:"'+str(dll)+'"','"'+str(obj)+'"',*['/EXPORT:'+name for name in sorted(exports)]]
    response=output/'link.rsp'
    response.write_text('\n'.join(lines)+'\n')
    N.run([tools/'link.exe','@'+str(response)],output,'link.log')
    receipt=dict(image=S.artifact(dll),runtime=source['runtime_dll'],source_NIO=S.artifact(nio_file),
        source_selection=source['base_proof'],source_Thread_provider=ref,source_Thread_metadata=pack['normal_thread_metadata'],
        kernel=S.artifact(KERNEL),test_tool=S.artifact(Path(__file__)),assembly=S.artifact(asm),object=S.artifact(obj),
        thread_class=thread,string_class=string,native_methods=meta['methods'],source_JCLS_replaced=False,
        receiver_fixture='original source Thread layouts; Java constructors not executed',
        actual_Thread_registry_cell=True,standard_JavaVM_or_JNIEnv_pointer_exposed=False,
        NativeLibraries_source_load_completed=False,game_started=False)
    S.write(output/'image.json',receipt)
    return receipt


def execute(receipt):
    runtime=S.checked(receipt['runtime'])
    with os.add_dll_directory(str(runtime.parent)):
        rt=c.CDLL(str(runtime))
        image=c.CDLL(str(S.checked(receipt['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(64<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Source heap bind failed')
    obj=proc(rt,'boom_object_new',P,P,P,P)
    def new(class_id):
        context=Context()
        oop=obj(heap,addr(image,'boom_layout'+str(class_id)),context)
        S.check(oop and not context[0],'Cannot allocate original source layout fixture')
        return oop
    pool=addr(image,'boom_builtin_module_pool')
    check=proc(image,'boom_builtin_module_check',c.c_int,P,P,U)
    body=proc(image,'boom_builtin_nio_body',c.c_int,P,P)
    wrapper=proc(image,'boom_builtin_nio_on_load',U,P,P)
    def detached():
        context=Context()
        S.check(check(context,pool,0x10002)==-2 and not context[0],'Unattached FFI thread passed the internal VM check')
        context=Context()
        S.check(body(context,pool)==-3 and context[0]==20,'Unattached nio body did not block')
        context=Context()
        S.check(wrapper(context,pool)==0 and context[0]==20,'Unattached nio wrapper reported successful load')
    detached()
    for version in (0,0x10001,0x10003,0x10008,0x150000):
        context=Context()
        S.check(check(context,pool,version)==-3 and not context[0],'Unsupported internal interface version passed')
    methods={m['name']:m['method'] for m in receipt['native_methods']}
    register=proc(image,f"boom_m{methods['registerNatives']}_native",Q,P,P)
    current=proc(image,f"boom_m{methods['currentThread']}_native",Q,P,P)
    context=Context()
    register(context,(Q*1)(0))
    S.check(not context[0],'Actual source Thread native registration failed')
    registry=proc(rt,'boom_threads_create',P,P,U)(heap,32)
    bind=proc(image,'boom_provider_thread_bind',U,P)
    S.check(registry and bind(registry)==0 and P.from_address(addr(image,'boom_provider_thread_registry')).value==registry,
            'Module does not share the real source Thread registry binding')
    detached()
    attach=proc(rt,'boom_threads_attach',P,P,P,Q)
    detach=proc(rt,'boom_threads_detach',U,P)
    next_id=proc(rt,'boom_threads_next_id',Q,P)
    main=new(receipt['thread_class'])
    S.check(attach(registry,main,1),'Cannot attach source main-thread fixture')
    def attached(expected):
        context=Context()
        S.check(check(context,pool,0x10002)==0 and not context[0],'Actual attached source thread failed the internal VM check')
        S.check(current(context,(Q*1)(0))==expected and not context[0],'Original Thread.currentThread native sees a different attachment')
        S.check(body(context,pool)==0x10002 and wrapper(context,pool)==0x10008 and not context[0],
                'Static nio wrapper did not execute its valid 1.2 body before returning 1.8')
    attached(main)
    preserved=Context(9,4,7,0,11,12,13,14)
    before=list(preserved)
    S.check(check(preserved,pool,0x10002)==-1 and wrapper(preserved,pool)==0 and list(preserved)==before,
            'Pending source exception was replaced by the module callback')
    fixtures=[new(receipt['thread_class']) for _ in range(8)]
    enter,leave=Barrier(9,timeout=15),Barrier(9,timeout=15)
    def worker(oop):
        detached()
        ident=next_id(registry)
        S.check(ident>1 and attach(registry,oop,ident),'Cannot attach an independent real OS thread')
        try:
            attached(oop)
            enter.wait()
            leave.wait()
            attached(oop)
        finally:
            S.check(detach(registry)==0,'Real OS-thread detach failed')
        detached()
        return get_native_id(),ident,oop
    with ThreadPoolExecutor(8) as workers:
        jobs=[workers.submit(worker,oop) for oop in fixtures]
        try:
            enter.wait()
            S.check(U.from_address(registry+24).value==9 and bind(None)==170,
                    'Source registry did not hold nine real attachments or allowed early unbinding')
            attached(main)
        finally:
            leave.wait()
        results=[job.result(timeout=15) for job in jobs]
    S.check(len({r[0] for r in results})==len({r[1] for r in results})==len({r[2] for r in results})==8 and
            U.from_address(registry+24).value==1,'Real OS threads shared identities or retained detached records')
    S.check(detach(registry)==0,'Main fixture detach failed')
    wrong=new(receipt['string_class'])
    S.check(attach(registry,wrong,next_id(registry)),'Wrong-type attachment fixture could not enter registry')
    context=Context()
    S.check(check(context,pool,0x10002)==-1 and context[0]==7,'A registered non-Thread oop passed source type validation')
    S.check(detach(registry)==0 and bind(None)==0 and proc(rt,'boom_threads_destroy',U,P)(registry)==0,
            'Source registry cleanup failed')
    detached()
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Normal guest heap cleanup failed')
    return dict(actual_source_Thread_registry_and_FLS_verified=True,real_OS_threads=8,
        concurrent_attached_records=9,distinct_source_Thread_objects=9,before_and_after_attach_detach_checked=True,
        original_currentThread_native_agreed=True,unsupported_versions_rejected=True,pending_exception_preserved=True,
        registered_non_Thread_oop_rejected=True,nio_body_version=0x10002,static_wrapper_version=0x10008,
        original_Thread_Java_constructors_called=False,standard_JavaVM_or_JNIEnv_pointer_exposed=False,
        original_NativeLibraries_load_completed=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nio',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ART/'builtin-module-context-tests'/uuid4().hex)
    args=parser.parse_args()
    receipt=build(args.nio,args.output)
    result=execute(receipt)
    result['image_receipt']=S.artifact(args.output/'image.json')
    S.write(args.output/'result.json',result)
    print(args.output/'result.json')
