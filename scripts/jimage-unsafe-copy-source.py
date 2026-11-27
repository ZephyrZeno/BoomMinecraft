"""Original copyMemory0 contract: leased RO JIMAGE -> normal heap byte[] only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OWNER='jdk/internal/misc/Unsafe'
DESCRIPTOR='(Ljava/lang/Object;JLjava/lang/Object;JJ)V'
SERVICE='boom_provider_jimage_copy_service'


def module(name):
    spec=importlib.util.spec_from_file_location('jimage_copy_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


I=module('verify-translation-ir');SC=module('jimage-unsafe-read-source');R=module('verify-batch-frames')


def index(summary,classes,S):
    [cls]=[c for c in classes if c['name']==OWNER and c['origin']['loader']=='bootstrap'];raw_bytes=S.original_class(summary,cls);raw=I.Source(raw_bytes);_,annotated=R.original_methods(raw_bytes)
    S.check(cls['origin']['source_id']=='jdk:java.base' and not cls['origin'].get('generated') and len(raw.methods)==len(cls['method_ids']),'Original Unsafe class required')
    natives=[];java=[]
    names={'copyMemory','copyMemoryChecks','checkSize','checkPrimitivePointer','checkPrimitiveArray','checkPointer','checkOffset','checkNativeAddress','invalidInput'}
    for ident,m,annotation in zip(cls['method_ids'],raw.methods,annotated):
        code=raw.code(m);name=m['name'];desc=m['descriptor']
        if name!='copyMemory0' and name not in names:continue
        row=dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],loader='bootstrap',source_id='jdk:java.base',owner=OWNER,name=name,descriptor=desc,access=m['access'])
        if name=='copyMemory0':
            S.check(desc==DESCRIPTOR and m['access']==0x102 and code is None,'Original private copyMemory0 declaration differs')
            S.check(R.flags(OWNER,annotation,True,False,False)==32,'Original copyMemory0 native Frame8 flags differ');natives.append(dict(row,operation=0,frame_flags=32))
        else:
            S.check(code is not None,'Original Java checks must remain whole methods');instructions=list(I.stream(code['bytes']));references=[]
            for ins in instructions:
                if 'Constant' in ins['operand']:
                    symbol=raw.symbol(ins['operand']['Constant'])
                    if 'Method' in symbol or 'Field' in symbol:references.append(dict(pc=ins['pc'],opcode=ins['opcode'],symbol=symbol))
            java.append(dict(row,code_sha256=hashlib.sha256(code['bytes']).hexdigest(),source_references=references,bytecode=[dict(pc=r['pc'],opcode=r['opcode'],operand=r['operand']) for r in instructions]))
    S.check(len(natives)==1,'Unique original copy native required')
    [public]=[m for m in java if m['name']=='copyMemory' and m['descriptor']==DESCRIPTOR]
    calls=[r for r in public['source_references'] if 'Method' in r['symbol']];S.check([(r['pc'],r['symbol']['Method']['name']) for r in calls]==[(9,'copyMemoryChecks'),(29,'copyMemory0')],'Original copy checks/native order changed')
    S.check(any(r['pc']==19 and r['opcode']==0xb1 for r in public['bytecode']),'Original zero-byte Java return must remain')
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as archive:
        types=[r for line in archive.open('types.jsonl') if (r:=json.loads(line))['name'] in ('[B','B')]
    arrays=[r for r in types if r['name']=='[B'];primitive=[r for r in types if r['name']=='B'];S.check(len(arrays)==len(primitive)==1 and arrays[0]['kind']==3 and primitive[0]['kind']==0 and primitive[0]['marker_flags']==1 and arrays[0]['parent_component']==primitive[0]['id'],'Normal byte-array source types differ')
    # Independently retain the exact already-verified normal array ABI. It is
    # payload-at-oop, not HotSpot's object-header offset.
    bootstrap=(ROOT/'native/runtime/java_unsafe.asm').read_text(encoding='utf-8');arrays_text=(ROOT/'native/runtime/arrays.asm').read_text(encoding='utf-8')
    S.check('cmp DWORD PTR [rsp+32],2\n je ju_done\n ; Normal array payload starts at oop+0, independently validated above.\n xor eax,eax\n jmp ju_done' in bootstrap,'Original array-base bootstrap contract changed')
    S.check('array_shifts BYTE 0,0,0,0,0,1,2,3,0,1,2,3,3' in arrays_text and 'lea r9, [r12+256]' in arrays_text,'Original byte-array allocation kind/width changed')
    S.check(summary['unsafe_memory']['primitive_array_byte_views'] is True,'Original typed byte views required')
    kernels={n:S.artifact(ROOT/'native/runtime'/n) for n in ('java_unsafe.asm','arrays.asm','heap.asm','java_unsafe_fields.asm')}
    S.check(kernels['java_unsafe.asm']['digest']['sha256']==summary['unsafe_bootstrap']['kernel_sha256'],'Original Unsafe bootstrap source differs')
    _,prefix,checker,_,_=SC.prefix_source()
    return dict(schema=1,owner=cls['id'],methods=natives,original_Java=java,required_classes=[cls['id']],required_java_methods=[],
        required_base_modules=['runtime_metadata','class_literals','unsafe_fields','unsafe_bootstrap','frames'],
        argv_slots=dict(receiver=0,source_base=8,source_address=16,destination_base=24,destination_offset=32,bytes=40),
        copy_job_bytes=64,byte_array=dict(type_id=arrays[0]['id'],component_id=primitive[0]['id'],allocation_kind=8,heap_tag=264,reference_prefix_slots=0,array_base_offset=0,array_scale=1),
        array_offset_conversion='original_Unsafe_offset_minus_verified_array_base_offset',
        source_kernels=kernels,original_receiver_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),
        owner_kernel_sha256=SC.OWNER_SHA,bridge_ABI=dict(symbol=SC.BRIDGE_POOL,magic=0x50414D4A,abi=1,owner=8,state=24,ready=1),
        policy=dict(source_null_base_only=True,destination_normal_heap_byte_array_only=True,leased_complete_RO_source_range=True,
            signed_size_and_offset_checked=True,all_address_and_length_overflows_checked=True,Owner_shared_SRW_through_complete_copy=True,
            original_Java_checks_and_zero_byte_return_unchanged=True,pending_Context_all_32_bytes_unchanged=True,
            heap_to_heap=False,arbitrary_off_heap=False,mapping_writes=False,GC_requires_quiescence=True,registered=False),
        registered=False,executed=False,game_started=False)


def assembly(meta):
    _,_,_,declarations,relocated=SC.prefix_source();declarations=declarations.replace('jur_','jup_');relocated=relocated.replace('jur_','jup_').replace(' sub rsp,120\n',' sub rsp,152\n').replace(' .allocstack 120\n',' .allocstack 152\n')
    mid=meta['methods'][0]['method'];procs={'boom_class_ensure32','boom_trace_enter','boom_trace_leave','boom_heap_contains','boom_object_check','boom_runtime_row','boom_jimage_owned_copy_to_bytes'}
    data={'boom_class'+str(meta['owner']),'boom_java_unsafe_field_pool','boom_trace_pool','boom_trace_method'+str(mid),SC.BRIDGE_POOL}
    text='option casemap:none\n'+''.join('EXTERN '+n+(':PROC\n' if n in procs else ':BYTE\n') for n in sorted(procs|data))
    text+='JUC_ARRAY_BASE_OFFSET EQU '+str(meta['byte_array']['array_base_offset'])+'\n.code\n'+f'PUBLIC boom_m{mid}\nPUBLIC boom_m{mid}_native\n'
    text+=R.native_adapter(mid,meta['owner'],'boom_java_unsafe_field_pool',SERVICE,0).removeprefix('.code\n')+declarations
    fragment=(ROOT/'native/providers/jimage_unsafe_copy.asm.inc').read_text(encoding='utf-8');SENTINEL=';@ORIGINAL_RECEIVER_PREFIX@';assert fragment.count(SENTINEL)==1
    text+=fragment.replace(SENTINEL,relocated.rstrip())+'\nEND\n'
    return text,{f'boom_m{mid}',f'boom_m{mid}_native',SERVICE},procs|data
