"""Actual primitive heap span component tests over an explicit pure-ASM runtime.

The helper and fixture DLLs are separate. Fixtures use the real ASM allocator;
their deliberately malformed payloads never claim an original Java identity.
No VM, Java selection, automatic collection, or provider registration runs here.
"""
import argparse
import concurrent.futures
import ctypes as C
import importlib.util
import json
from pathlib import Path
import sys
import threading

SENTINEL=0x6a5b4c3d2e1f0908
SHIFTS=(0,1,2,3,0,1,2,3)
FIXTURE_EXPORTS={'boom_heap_span_test_layout','boom_heap_span_forge_interior'}
FIXTURE_ASSEMBLY='''; Native component fixtures only; never linked into a provider or Main.
option casemap:none
PUBLIC boom_heap_span_test_layout
PUBLIC boom_heap_span_forge_interior
.const
ALIGN 8
test_object_layout DWORD 04F424A43h,2
 QWORD 0
 DWORD 0,0
.code
boom_heap_span_test_layout PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 lea rax,test_object_layout
 add rsp,40
 ret
boom_heap_span_test_layout ENDP
; Caller supplied the actual payload of a >=128B primitive byte[] allocation.
; Write only its bytes, imitating a self-consistent header for an interior oop.
boom_heap_span_forge_interior PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 mov QWORD PTR [rcx],64
 mov DWORD PTR [rcx+8],0B00B0001h
 mov DWORD PTR [rcx+12],0
 mov QWORD PTR [rcx+16],32
 mov QWORD PTR [rcx+24],264
 lea rax,[rcx+32]
 add rsp,40
 ret
boom_heap_span_forge_interior ENDP
END
'''


def check(value,message):
    if not value:raise ValueError(message)


def load_helper():
    path=Path(__file__).resolve().with_name('primitive-heap-span.py')
    spec=importlib.util.spec_from_file_location('primitive_heap_span_component_builder',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def native_suite(runtime_file,component_file,fixtures_file,result_file):
    runtime=C.WinDLL(str(runtime_file));helper=C.WinDLL(str(component_file));fixtures=C.WinDLL(str(fixtures_file))
    def api(dll,name,args,result):
        fn=getattr(dll,name);fn.argtypes=args;fn.restype=result;return fn
    ptr=C.c_void_p;u64=C.c_uint64;u32=C.c_uint32
    create=api(runtime,'boom_heap_create',[u64],ptr)
    destroy=api(runtime,'boom_heap_destroy',[ptr],u32)
    alloc=api(runtime,'boom_heap_alloc',[ptr,u64,u32,u64],ptr)
    contains=api(runtime,'boom_heap_contains',[ptr,ptr],u32)
    array=api(runtime,'boom_array_new',[ptr,C.c_int32,u32,ptr],ptr)
    object_new=api(runtime,'boom_object_new',[ptr,ptr,ptr],ptr)
    collect=api(runtime,'boom_heap_collect',[ptr,ptr,u64],C.c_int64)
    span=api(helper,'boom_primitive_heap_span',[ptr,ptr,u64,u64,ptr],u32)
    layout=api(fixtures,'boom_heap_span_test_layout',[],ptr)
    forge=api(fixtures,'boom_heap_span_forge_interior',[ptr],ptr)
    heap=create(8*1024*1024);check(heap,'ASM heap create failed')
    events=[]
    def record(name,p,offset,length,expected,expected_address=None,which_heap=None):
        used=heap if which_heap is None else which_heap
        out=u64(SENTINEL);status=span(used,p,offset,length,C.byref(out))
        check(status==expected,f'{name}: status {status} != {expected}')
        check(out.value==(expected_address if status==0 else SENTINEL),name+': output publication differs')
        check(u32.from_address(used+8).value==0,name+': heap lock leaked')
        events.append(dict(case=name,status=status,output_unchanged_on_error=status!=0,
            successful_byte_offset=offset if status==0 else None))
    def new_array(kind,n,used=heap):
        ctx=(u64*4)();p=array(used,n,kind,C.byref(ctx))
        check(p and list(ctx)==[0,0,0,0],'ASM array_new failed');return p
    for kind,shift in zip(range(4,12),SHIFTS):
        for length in (0,1,11):
            p=new_array(kind,length);size=length<<shift
            check(contains(heap,p)==1,'Real ASM array not contained')
            record(f'atype{kind}_len{length}_all',p,0,size,0,p)
            record(f'atype{kind}_len{length}_onepast_zero',p,size,0,0,p+size)
            if size:
                record(f'atype{kind}_len{length}_last',p,size-1,1,0,p+size-1)
                record(f'atype{kind}_len{length}_unaligned',p,1,size-1,0,p+1)
            record(f'atype{kind}_len{length}_past_payload',p,size,1,122)
            record(f'atype{kind}_len{length}_past_zero',p,size+1,0,122)
            record(f'atype{kind}_len{length}_inside_unaligned_pointer',p+1,0,0,487)
    ctx=(u64*4)();ordinary=object_new(heap,layout(),C.byref(ctx))
    check(ordinary and list(ctx)==[0,0,0,0],'Actual ASM object_new fixture failed')
    record('ordinary_runtime_object',ordinary,0,0,13)
    for n in (0,3):record('reference_array_'+str(n),new_array(12,n),0,0,13)
    for tag in (259,268,269,0x100000108,0xfffffffffffffff0):
        p=alloc(heap,16,0,tag);check(p,'negative opaque type fixture allocation failed')
        record('invalid_type_'+str(tag),p,0,0,13)
    p=alloc(heap,16,1,264);check(p,'reference prefix fixture allocation failed')
    record('primitive_tag_reference_prefix',p,0,0,13)
    for tag,n in ((261,3),(262,3),(263,9),(265,3),(266,3),(267,9)):
        p=alloc(heap,n,0,tag);check(p,'invalid physical shape allocation failed')
        record('physical_not_element_multiple_'+str(tag),p,0,0,13)
    p=new_array(8,128);fake=forge(p)
    check(contains(heap,fake)==1,'Test did not reproduce contains header-only membership limitation')
    record('forged_aligned_interior_contains_passes',fake,0,0,487)
    for value in (0,1,16,0x7fffffffffffffff,0xffffffffffffffff):
        record('untrusted_oop_'+str(value),value,0,0,87 if value==0 else 487)
    foreign=C.create_string_buffer(64);record('host_buffer_is_not_heap_oop',C.addressof(foreign),0,0,487)
    p=new_array(8,16)
    record('negative_offset',p,(1<<64)-1,0,87)
    record('negative_length',p,0,1<<63,87)
    record('signed_end_overflow',p,(1<<63)-1,1,534)
    record('signed_end_overflow_two',p,1,(1<<63)-1,534)
    record('large_but_no_arithmetic_overflow',p,(1<<63)-1,0,122)
    check(span(heap,p,0,0,None)==87,'Null output pointer not rejected')
    other=create(4096);check(other,'Second ASM heap creation failed')
    record('wrong_live_heap',p,0,0,487,which_heap=other)
    stale=new_array(8,8,other);check(collect(other,None,0)==1,'Explicit quiescent native GC fixture failed')
    check(contains(other,stale)==0,'Collected fixture still live')
    record('collected_block',stale,0,0,487,which_heap=other)
    check(destroy(other)==1,'Second heap destroy failed')
    barrier=threading.Barrier(8)
    def worker(index):
        barrier.wait();rows=[]
        for i in range(64):
            kind=4+(index+i)%8;length=8+(i%9);p=new_array(kind,length);size=length<<SHIFTS[kind-4]
            out=u64(SENTINEL);status=span(heap,p,1,size-1,C.byref(out))
            check(status==0 and out.value==p+1,'Concurrent actual ASM allocation/span mismatch')
            rows.append((kind,length))
        return dict(worker=index,native_OS_thread=threading.get_native_id(),calls=len(rows))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        workers=list(executor.map(worker,range(8)))
    check(len({r['native_OS_thread'] for r in workers})==8,'Not eight actual OS workers')
    check(u32.from_address(heap+8).value==0,'Heap lock leaked after native concurrency')
    check(destroy(heap)==1,'Actual ASM heap destroy failed')
    result=dict(verified=True,scope='direct_frozen_ASM_heap_arrays_and_independent_span_helper_only',
        cases=events,case_count=len(events),contains_accepts_forged_interior_but_helper_rejects=True,
        eight_OS_workers=workers,concurrent_native_allocations_and_span_calls=512,
        heap_cleanup_succeeded=True,Source_ArrayBaseOffset=0,header_minus16_means_physical_bytes=True,
        ordinary_object_fixture='real runtime object_new with valid test-local ABI2 zero-field layout; no original Java constructor or source-class identity claim',
        invalid_shape_fixtures='real heap_alloc negative fixtures, not claimed as normal Java arrays',
        no_host_Java_field_or_class_state_writes=True,guest_Main_or_SourceV_executed=False,automatic_GC_executed=False,
        explicit_quiescent_native_GC_fixture=True,runtime_acceptance_complete=False,game_started=False)
    with Path(result_file).open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(verified=True,cases=len(events),native_concurrent_calls=512,heap_destroy=True)))


def test(runtime,inputs,output,reference_assembly=None,reference_object=None):
    G=load_helper();manifest=G.read(inputs)
    before=[G.artifact(__file__),G.artifact(G.__file__),G.artifact(inputs)]+manifest['inputs']
    before+=[manifest[k] for k in ('assembly','object','DLL','runtime_copy','link_response','COFF_reader')]
    output=G.fresh(output)
    proof=G.verify(inputs,output/'machine-verification',runtime,reference_assembly,reference_object)
    assembler=G.checked(manifest['tools']['assembler']);linker=G.checked(manifest['tools']['linker'])
    fixtures=output/'fixtures.asm';fixtures.write_text(FIXTURE_ASSEMBLY,encoding='utf-8',newline='\n')
    obj=output/'fixtures.obj';G.assemble(output,'fixture-assemble',assembler,fixtures,obj)
    canonical=output/'canonical-fixtures.asm';canonical.write_text(FIXTURE_ASSEMBLY,encoding='utf-8',newline='\n')
    canonical_obj=output/'canonical-fixtures.obj';G.assemble(output,'fixture-canonical-assemble',assembler,canonical,canonical_obj)
    reader=G.coff_reader(manifest['runtime_contract']['source_root']);normalized=reader.normalized_coff(obj)
    G.check(normalized==reader.normalized_coff(canonical_obj) and set(normalized['exports'])==FIXTURE_EXPORTS and
        not normalized['imports'],'Fixture complete COFF or symbol surface differs')
    dll=output/'fixtures.dll';rsp=G.link(output,'fixture-link',linker,obj,dll,None,FIXTURE_EXPORTS)
    G.check(G.pe(dll)==dict(dll=True,entry_rva=0,imports={},exports=sorted(FIXTURE_EXPORTS)),
        'Test fixtures import runtime or foreign code')
    pins=[G.artifact(p) for p in (proof,fixtures,obj,canonical,canonical_obj,dll,rsp)]
    result=output/'native-result.json'
    G.run(output,'native-worker',[sys.executable,Path(__file__).resolve(),'--native-worker',
        '--runtime',G.checked(manifest['runtime_copy']),'--component',G.checked(manifest['DLL']),
        '--fixtures',dll,'--result',result])
    native=G.read(result)
    G.check(native['verified'] is True and native['case_count']==181 and
        native['concurrent_native_allocations_and_span_calls']==512 and native['heap_cleanup_succeeded'] is True,
        'Actual native component scope did not complete')
    for row in before+pins:G.checked(row)
    G.check(G.runtime_contract(runtime,manifest['runtime_contract']['source_root'])==manifest['runtime_contract'],
        'Runtime/source changed during native tests')
    record=dict(schema=1,verified=True,scope='primitive_heap_span_component_native_execution_only',
        producer=G.artifact(__file__),helper_inputs=G.artifact(inputs),machine_verification=G.artifact(proof),
        fixtures=dict(source=G.artifact(fixtures),object=G.artifact(obj),canonical_object=G.artifact(canonical_obj),
            DLL=G.artifact(dll),link_response=G.artifact(rsp),complete_COFF_equal=True,actual_PE=G.pe(dll)),
        native_result=G.artifact(result),native_case_count=native['case_count'],
        eight_OS_workers=native['eight_OS_workers'],concurrent_native_allocations_and_span_calls=512,
        heap_cleanup_succeeded=True,all_consumed_inputs=before+pins,
        no_host_Java_field_or_class_state_writes=True,SourceV_or_VM_executed=False,
        runtime_acceptance_complete=False,game_started=False)
    G.write(output/'verification.json',record);return output/'verification.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--inputs',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--reference-assembly',type=Path);parser.add_argument('--reference-object',type=Path)
    parser.add_argument('--native-worker',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--component',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--fixtures',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--result',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.native_worker:
        check(args.component and args.fixtures and args.result,'Native component worker arguments are incomplete')
        native_suite(args.runtime,args.component,args.fixtures,args.result)
    else:
        check(args.inputs and args.output,'Explicit --inputs and fresh --output are required')
        result=test(args.runtime,args.inputs,args.output,args.reference_assembly,args.reference_object)
        print(json.dumps(dict(output=load_helper().artifact(result)),indent=2))


if __name__=='__main__':main()
