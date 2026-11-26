"""Original JDK21 Class-only StackWalker source protocol; no shared registration.

The native candidate supports the ordinary platform-thread getCallerClass mode.
It fills source Class mirrors and calls the entire original doStackWalk Java
method. FrameInfo/continuations and unrepresented frames fail explicitly.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile


OWNER='java/lang/StackStreamFactory'
ABSTRACT=OWNER+'$AbstractStackWalker'
CALLER=OWNER+'$CallerClassFinder'
BUFFER=OWNER+'$FrameBuffer'
POOL='boom_provider_stack_walk_pool'
SERVICE='boom_provider_stack_walk_service'
CONTROL={'boom_stack_walk_active_count','boom_stack_walk_counters'}
FOREIGN={'GetCurrentThreadId','AcquireSRWLockExclusive','ReleaseSRWLockExclusive'}
KERNELS=['frames.asm','java_classes.asm','heap.asm','thread_registry.asm',
         'field_address.asm','runtime_types.asm','runtime_type_index.asm','types.asm']
SPECS=[(OWNER,'checkStackWalkModes','()Z',0x10a),
       (ABSTRACT,'callStackWalk','(JILjdk/internal/vm/ContinuationScope;Ljdk/internal/vm/Continuation;II[Ljava/lang/Object;)Ljava/lang/Object;',0x102),
       (ABSTRACT,'fetchStackFrames','(JJII[Ljava/lang/Object;)I',0x102)]
JAVA=[(ABSTRACT,'doStackWalk','(JIIII)Ljava/lang/Object;'),
      (ABSTRACT,'walkHelper','()Ljava/lang/Object;'),(ABSTRACT,'beginStackWalk','()Ljava/lang/Object;'),
      (CALLER,'findCaller','()Ljava/lang/Class;'),(CALLER,'consumeFrames','()Ljava/lang/Integer;'),
      ('java/lang/StackWalker','getCallerClass','()Ljava/lang/Class;')]
PINS={'stackwalk.cpp':'39b4731473ebccfd0b9d9062519e0d8d9df2c17699ed53e8d79215c7d00a52a6',
      'stackwalk.hpp':'431aba51aa5e551724d8c8efef040c077576e1480ed0235ee5f56abf131858f9',
      'jvm.cpp':'84436b103fb7869e445bac95d2e82e9de9160c2da327a4cf54f4e84555150ad9',
      'jvm.h':'fcdbd3c7cdbb927cca40a35dc57c6b04e9c1836886879c644a0fed163b392faa',
      'StackStreamFactory.c':'ab5b73ae22a85d0c1cc2fcfbaf0db038543ac00691c4a88eea70f80a36ab6af8',
      'StackStreamFactory.java':'b307a7184b3cb92c93e0705e53d2e8c9c6230227f263997bc87313b28447311a',
      'StackWalker.java':'cedc54acbc74ee164f9ababa208621ac1cc407cb0cb98c076f8d2d17000b5a47'}
MODES=('FILL_CLASS_REFS_ONLY','GET_CALLER_CLASS','SHOW_HIDDEN_FRAMES','FILL_LIVE_STACK_FRAMES')
FIELDS=[('thread','Ljava/lang/Thread;',0x14,8,True),('mode','J',0x14,8,False),
        ('contScope','Ljdk/internal/vm/ContinuationScope;',0x14,8,True),
        ('continuation','Ljdk/internal/vm/Continuation;',4,8,True)]
POLICY=dict(platform_threads_only=True,mode='FILL_CLASS_REFS_ONLY|GET_CALLER_CLASS',
    native_check_compares_all_pinned_Java_and_VM_constants=True,
    first_batch_skips='StackWalker_AbstractStackWalker_and_direct_subclasses_then_skipFrames',
    frame_source='actual_TracePool3_TLS_Node2_chain_same_Context',Class_mirrors='normal_JCLS_load',
    VM_filters_only_hidden_flag=16,reflection_and_MethodHandle_filter='intact_original_Java_consumer',
    original_private_doStackWalk_required=True,Java_anchor_and_frameBuffer_fields_written_by='original_Java_only',
    reserved_buffer_slots=2,magic_slot=0,magic_value='actual_current_source_Thread_oop',
    token='unique_nonzero_generation_only_while_owning_native_call_is_active',
    token_lookup='owned_list_before_dereference_same_OS_Context_receiver_mode_and_magic',
    resize='new_Class_array_must_copy_reserved_Thread_magic_original_array_cleared_on_exit',
    lock_across_Java_callback=False,nested_walks='distinct_source_receivers_supported',
    cursor='last_decoded_Node_next_fetch_advances_once',fetch_result='end_index_not_frame_count',
    cleanup='unpublish_token_and_clear_original_magic_even_on_pending_Context',
    unsupported_Context=20,malformed_private_protocol_Context=7,
    caller_sensitive_first_frame='explicit_unsupported_until_original_exception_upcall_is_added',
    no_StackFrameInfo_or_Continuation_or_live_frames=True,generated_frame_profiles='explicit_unsupported',
    automatic_GC=False,GC_requires_quiescence=True,transient_oops='owned_native_call_and_original_Java_arguments',
    no_singleton_caller_or_Main_special_case=True,source_transform_chain='original_locked_no_transforms')


def integer_constants(raw,S):
    values={}
    for field in raw.fields:
        if field['descriptor']=='I' and field['constant_value'] is not None:
            value=raw.symbol(field['constant_value'])
            S.check(set(value)=={'Int'} and field['access']&0x18==0x18,'Original StackWalker ConstantValue type differs')
            values[field['name']]=value['Int']
    return values


def protocol(raw,buffer,pinned,S):
    """Compare original classfile constants, locked Java text and native enum."""
    values=integer_constants(raw,S);java=pinned['StackStreamFactory.java'].read_text(encoding='utf-8')
    header=pinned['jvm.h'].read_text(encoding='utf-8')
    for key in MODES:
        left=re.findall(r'\bint\s+'+key+r'\s*=\s*(0x[\da-fA-F]+|\d+)\s*;',java)
        right=re.findall(r'\bJVM_STACKWALK_'+key+r'\s*=\s*(0x[\da-fA-F]+|\d+)\s*[,}]',header)
        S.check(len(left)==len(right)==1 and values.get(key)==int(left[0],0)==int(right[0],0),
                'Pinned Java/classfile/native StackWalker constant mismatch: '+key)
    constants=integer_constants(buffer,S)
    start=re.findall(r'\bint\s+START_POS\s*=\s*(\d+)\s*;',java)
    hpp=pinned['stackwalk.hpp'].read_text(encoding='utf-8')
    magic=re.findall(r'\bmagic_pos\s*=\s*(\d+)\s*',hpp)
    S.check(len(start)==len(magic)==1 and constants['START_POS']==int(start[0])==2 and int(magic[0])==0,
            'Original reserved buffer/magic positions differ')
    native=pinned['StackStreamFactory.c'].read_text(encoding='utf-8')
    checked=re.findall(r'JVM_STACKWALK_(\w+)\s*==\s*java_lang_StackStreamFactory_(\w+)',native)
    S.check(checked==[(name,name) for name in ('FILL_CLASS_REFS_ONLY','SHOW_HIDDEN_FRAMES','FILL_LIVE_STACK_FRAMES')],
            'Original checkStackWalkModes bridge differs')
    return dict(modes={name:values[name] for name in MODES},supported_mode=values['FILL_CLASS_REFS_ONLY']|values['GET_CALLER_CLASS'],
        START_POS=constants['START_POS'],magic_pos=int(magic[0]),native_check_compares=[a for a,b in checked],
        callback_descriptor='(JIIII)Ljava/lang/Object;',fetch_returns='end_index',
        call_arguments=['receiver','mode','skip_frames','cont_scope','continuation','frame_count','start_index','frames'],
        fetch_arguments=['receiver','mode','anchor','frame_count','start_index','frames'],
        callback_arguments=['receiver','anchor','skip_frames','frame_count','start_index','end_index'],
        argument_slot_bytes=8,category2_arguments_use_one_native_vector_slot=True)


def index(summary,classes,S):
    I=S.module('stack_walk_raw_source','verify-translation-ir.py')
    R=S.module('stack_walk_original_frame_flags','verify-batch-frames.py')
    wanted={OWNER,ABSTRACT,CALLER,BUFFER,'java/lang/StackWalker','java/lang/Thread','java/lang/BaseVirtualThread','java/lang/Class'}
    wanted|={c['name'] for c in classes if c.get('superclass')==ABSTRACT and c['origin']['loader']=='bootstrap'}
    owners={c['name']:c for c in classes if c['name'] in wanted and c['origin']['loader']=='bootstrap'}
    S.check(set(owners)==wanted,'Original platform StackWalker classes missing')
    parsed={};members={};native=[]
    for name,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Original java.base StackWalker required')
        original=S.original_class(summary,c);raw=I.Source(original);parsed[name]=raw
        _,annotated=R.original_methods(original)
        S.check(raw.name==name and raw.parent==c['superclass'] and len(raw.methods)==len(c['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==c['fields'], 'Original StackWalker class inventory differs')
        for ident,m,a in zip(c['method_ids'],raw.methods,annotated):
            key=name,m['name'],m['descriptor'];body=raw.code(m)
            if key not in JAVA and key not in [row[:3] for row in SPECS]:continue
            row=dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',source_id='jdk:java.base',
                     owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],
                     frame_flags=R.flags(name,a,True,False,name in ('jdk/internal/reflect/MethodAccessorImpl','jdk/internal/reflect/ConstructorAccessorImpl')))
            if body:
                row.update(code_sha256=hashlib.sha256(body['bytes']).hexdigest(),code_bytes=len(body['bytes']),handlers=body['handlers'])
            members[key]=row
    for operation,(name,method,desc,access) in enumerate(SPECS):
        row=members[name,method,desc]
        S.check(row['access']==access and 'code_sha256' not in row and row['frame_flags']==32,'Original StackWalker native declaration changed')
        native.append(dict(row,operation=operation))
    java=[members[key] for key in JAVA]
    S.check(all(row.get('code_sha256') for row in java),'Whole original StackWalker Java callback/consumer Code required')
    pinned=S.ART/'stack-walk/pinned-sources/jdk-21.0.13+3'
    paths={name:S.checked(dict(path=str(pinned/name),digest=S.digest(pinned/name))) for name in PINS}
    sources={name:S.artifact(path) for name,path in paths.items()}
    S.check(all(row['digest']['sha256']==PINS[name] for name,row in sources.items()),'Pinned StackWalker semantics source changed')
    spec=protocol(parsed[OWNER],parsed[BUFFER],paths,S)
    fields=[];abstract=owners[ABSTRACT]
    for name,desc,access,width,ref in FIELDS:
        found=[i for i,field in enumerate(abstract['fields']) if field==dict(name=name,descriptor=desc,access=access)]
        S.check(len(found)==1,'Original StackWalker field differs: '+name)
        fields.append(dict(name=name,descriptor=desc,access=access,index=found[0],width=width,reference=ref))
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as z:
        all_fields={row['declaring_field']:row for line in z.open('fields.jsonl') if (row:=json.loads(line))['declaring_class']==abstract['id']}
        types={row['id']:row for line in z.open('types.jsonl') if (row:=json.loads(line))['id'] in {c['id'] for c in owners.values()} or row.get('name')=='[Ljava/lang/Class;'}
    receivers=set()
    for field in fields:
        fmap=all_fields[field['index']]
        S.check(fmap['reference']==field['reference'] and fmap['storage_bytes']==field['width'] and
                abstract['id'] in {r['receiver_class'] for r in fmap['rows']},'Normal inherited StackWalker FMAP changed')
        field['field_map']=fmap;receivers.update(r['receiver_class'] for r in fmap['rows'])
    layouts={}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['class_id'] in receivers:layouts[row['class_id']]=row
    for field in fields:
        for row in field['field_map']['rows']:
            layout=layouts[row['receiver_class']]
            S.check(layout['diagnostic'] is None and layout['candidate'] and any(
                f['member']['owner']==abstract['id'] and f['member']['index']==field['index'] and
                f['offset']==row['offset'] and f['storage_bytes']==field['width'] and f['reference']==field['reference']
                for f in layout['candidate']['fields']),'Normal inherited StackWalker field layout differs')
    [array]=[r for r in types.values() if r['name']=='[Ljava/lang/Class;']
    S.check(array['kind']==3 and array['parent_component']==owners['java/lang/Class']['id'] and
            all(types[c['id']]['kind']==1 and types[c['id']]['source_sha256']==c['origin']['sha256'] for c in owners.values()),
            'Normal StackWalker Class array/source runtime types differ')
    skip=sorted(c['id'] for c in owners.values() if c['name'] in ('java/lang/StackWalker',ABSTRACT) or c.get('superclass')==ABSTRACT)
    return dict(schema=1,owner=owners[OWNER]['id'],methods=native,source_classes={k:v['id'] for k,v in owners.items()},
        java_callbacks=java,required_java_methods=[r['method'] for r in java],required_classes=sorted(c['id'] for c in owners.values()),
        required_base_modules=['runtime_metadata','class_literals','frames','unsafe_fields'],required_provider_families=['normal-thread-primitives-v1'],
        fields=fields,class_array_type=array['id'],skip_prefix_class_ids=skip,protocol=spec,native_sources=sources,
        trace_ABI=dict(pool_magic=0x5452504c,pool_abi=3,pool_bytes=48,method_row_bytes=32,node_magic=0x4652414d,node_abi=2,node_bytes=48,
            row=dict(method=0,flags=4,declaring_type=8,code_bytes=16,class_id=20,reserved=24),
            node=dict(previous=8,method_row=16,pc=24,flags=28,Context=32,pool=40),
            hidden_flag=16,caller_sensitive_flag=8,native_flag=32,generated_flag=4,unbound_flag=128,maximum_walk_nodes=128),
        pool_bytes=144,pool_abi=1,policy=dict(POLICY),native_root_spans=[],registered=False,
        ASM_generated=False,source_Java_executed=False,accepted=False,game_started=False,world_created=False)


def native_imports(meta):
    procs=FOREIGN|{'boom_trace_enter','boom_trace_leave','boom_class_ensure32','boom_trace_head',
        'boom_heap_contains','boom_runtime_type','boom_type_assignable','boom_java_class_load','boom_threads_current',
        f"boom_m{meta['java_callbacks'][0]['method']}"}|{f"boom_field_map{r['field_map']['id']}" for r in meta['fields']}
    classes=meta['source_classes']
    data={'boom_heap_ptr','boom_runtime_type_map','boom_trace_pool','boom_java_class_pool','boom_provider_thread_registry',
        f'boom_t{meta["class_array_type"]}',f'boom_t{classes[ABSTRACT]}',f'boom_t{classes[CALLER]}',
        f'boom_t{classes["java/lang/BaseVirtualThread"]}'}
    data|={f"boom_trace_method{row['method']}" for row in meta['methods']}
    return procs,data


def data(meta):
    classes=meta['source_classes'];fields={r['name']:r['field_map']['id'] for r in meta['fields']}
    values=['boom_heap_ptr','boom_trace_pool','boom_java_class_pool','boom_provider_thread_registry','boom_runtime_type_map',
        f'boom_t{classes[ABSTRACT]}',f'boom_t{meta["class_array_type"]}','boom_stack_walk_skip_classes']
    text=(f"SW_SUPPORTED_MODE EQU {meta['protocol']['supported_mode']}\nSW_BUFFER_START EQU {meta['protocol']['START_POS']}\n"
        f"SW_NATIVE_FIRST EQU {meta['methods'][1]['method']}\nSW_NATIVE_FETCH EQU {meta['methods'][2]['method']}\n"
        '.const\nALIGN 4\nboom_stack_walk_skip_classes LABEL DWORD\n DWORD '+','.join(map(str,meta['skip_prefix_class_ids']))+'\n'
        f'.data\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 053574350h,1,1,{meta["trace_ABI"]["maximum_walk_nodes"]}\n')
    text+=''.join(' QWORD OFFSET '+name+'\n' for name in values)
    text+=f' DWORD {len(meta["skip_prefix_class_ids"])},0\n'
    text+=''.join(f' QWORD OFFSET boom_field_map{fields[name]}\n' for name in ('thread','mode','contScope','continuation'))
    text+=f" QWORD OFFSET boom_m{meta['java_callbacks'][0]['method']}\n"
    text+=f' QWORD OFFSET boom_t{classes["java/lang/BaseVirtualThread"]},OFFSET boom_t{classes[CALLER]}\n'
    return text


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('stack_walk_source_io',root/'scripts/runtime-provider-source.py')
    S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    state=S.read(args.state);identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(identity['batch_summary']['digest']['sha256']==state['batch_summary_sha256'] and
            identity['base_verification']['digest']['sha256']==state['batch_verification_sha256'],'Input batch proof pin differs')
    model=index(summary,classes,S);output=args.output.resolve()
    S.check(output.is_relative_to(S.ART/'stack-walk') and not output.exists(),'Fresh isolated StackWalker source model output required')
    output.mkdir(parents=True);S.write(output/'source-model.json',dict(base=identity,input_state=S.artifact(args.state),source=model,
        producer=S.artifact(Path(__file__)),scope='source_protocol_and_field_mapping_only_not_native_or_execution_acceptance'))
    print(output/'source-model.json')
