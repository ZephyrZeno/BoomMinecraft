"""Original Inflater private-native declarations, field maps and Java callbacks.

Unregistered source model. No builtin zip support or constructor acceptance is
inferred from this inventory. The supplied provider state may be source-pending.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OWNER='java/util/zip/Inflater'
POOL='boom_provider_inflater_pool'
SERVICE='boom_provider_inflater_service'
CONTROL={'boom_inflater_close_owned','boom_inflater_string_pool','boom_inflater_errors'}
FOREIGN={'GetProcessHeap','HeapAlloc','HeapFree','AcquireSRWLockExclusive','ReleaseSRWLockExclusive','AcquireSRWLockShared','ReleaseSRWLockShared'}
KERNELS=['heap.asm','objects.asm','classes32.asm','frames.asm','arrays.asm','field_address.asm','runtime_types.asm','runtime_type_index.asm','types.asm','java_properties.asm']
SPECS=[('initIDs','()V',0x10a,0),('init','(Z)J',0x10a,1),('getAdler','(J)I',0x10a,2),('reset','(J)V',0x10a,3),('end','(J)V',0x10a,4),
       ('inflateBytesBytes','(J[BII[BII)J',0x102,5),('setDictionary','(J[BII)V',0x10a,6),('setDictionaryBuffer','(JJI)V',0x10a,7),
       ('inflateBytesBuffer','(J[BIIJI)J',0x102,8),('inflateBufferBytes','(JJI[BII)J',0x102,9),('inflateBufferBuffer','(JJIJI)J',0x102,10)]
ERRORS=['java/util/zip/DataFormatException','java/lang/OutOfMemoryError','java/lang/InternalError']
CALLBACKS=[(name,'<init>','(Ljava/lang/String;)V') for name in ERRORS]+[('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]
PINS={'Inflater.java':'ff3c671a1a8fab21d4258c2f73a88e77e84825b64df9a7c667f1966fd2a92b7d',
      'ZipUtils.java':'facb12e60a37c0c2033e0e0ffb7e758e437e7641ea2d91360a34bb7482b7f3da',
      'InflaterInputStream.java':'77de7a39749517928c3d89ec4c4b51ffdc6ecd24bf1aebac2904931fb96bb592',
      'DataFormatException.java':'27341cda4f82578cb54cb8565fa566d5eecf2f44df477b1150d5a3c452829fb0'}
POLICY=dict(unregistered=True,direct_native_is_component_only=True,normal_Source_arrays_and_Context32=True,
    handle='nonzero_monotonic_generation_looked_up_before_node_dereference',pool_lifetime_SRW=True,per_handle_exclusive=True,
    locks_across_Java_callbacks=False,native_nodes_contain_oops=False,GC_requires_quiescence=True,
    raw_getAdler=0,wrapped_needs_dictionary_getAdler='parsed_DICTID',wrapped_other_getAdler='actual_output_Adler',
    JNI_packed_input_bits=31,JNI_packed_output_shift=31,JNI_finished_bit=62,JNI_need_dictionary_bit=63,
    normal_return_updates_Java_fields=False,data_error_fields=['inputConsumed','outputConsumed'],
    unsupported=['setDictionary','setDictionaryBuffer','inflateBytesBuffer','inflateBufferBytes','inflateBufferBuffer','overlapping_input_output_ranges'],
    unsupported_Context=20,malformed_private_protocol_Context=7,generic_error_message_not_zlib_exact=True,
    RFC_HDIST32_difference_retained=True,strict_CINFO_window_difference_retained=True,
    builtin_zip_implemented=False,complete_native_library_loading_semantics=False,
    original_Inflater_constructor_executed=False,automatic_Cleaner_acceptance=False)


def module(name):
    spec=importlib.util.spec_from_file_location('inflater_'+name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def index(summary,classes,S):
    I=module('verify-translation-ir');F=module('file-bootstrap-source');R=module('verify-batch-frames')
    paths=[(OWNER,'<clinit>','()V'),(OWNER,'<init>','(Z)V'),(OWNER,'<init>','()V'),
        (OWNER,'inflate','([BII)I'),(OWNER,'reset','()V'),(OWNER,'end','()V'),(OWNER,'getAdler','()I'),
        (OWNER+'$InflaterZStreamRef','<init>','(Ljava/util/zip/Inflater;J)V'),(OWNER+'$InflaterZStreamRef','run','()V'),
        ('java/util/zip/ZipUtils','<clinit>','()V'),('java/util/zip/ZipUtils','loadLibrary','()V'),
        ('jdk/internal/loader/BootLoader','loadLibrary','(Ljava/lang/String;)V'),
        ('jdk/internal/loader/NativeLibraries','loadLibrary','(Ljava/lang/String;)Ljdk/internal/loader/NativeLibrary;')]
    wanted={OWNER,OWNER+'$InflaterZStreamRef','java/util/zip/ZipUtils','java/lang/String','java/lang/Throwable',
        'jdk/internal/loader/BootLoader','jdk/internal/loader/NativeLibraries'}|set(ERRORS)
    owners={c['name']:c for c in classes if c['name'] in wanted and c['origin']['loader']=='bootstrap'}
    S.check(set(owners)==wanted,'Original Inflater/callback classes missing')
    members={};raws={}
    for name,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Original java.base Inflater required')
        original=S.original_class(summary,c);raw=I.Source(original);raws[name]=raw;_,annotated=R.original_methods(original)
        S.check(raw.name==name and len(raw.methods)==len(c['method_ids']) and [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==c['fields'],'Original Inflater source inventory differs')
        for ident,m,a in zip(c['method_ids'],raw.methods,annotated):
            key=name,m['name'],m['descriptor']
            if key not in paths+CALLBACKS and not (name==OWNER and m['access']&256):continue
            code=raw.code(m);row=dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',source_id='jdk:java.base',owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'])
            if code:
                row.update(code_sha256=hashlib.sha256(code['bytes']).hexdigest(),code_bytes=len(code['bytes']),handlers=code['handlers']);calls=[]
                for ins in I.stream(code['bytes']):
                    if 'Constant' not in ins['operand']:continue
                    symbol=raw.symbol(ins['operand']['Constant'])
                    if any(k in symbol for k in ('Method','Field','StringUtf16')):calls.append(dict(pc=ins['pc'],opcode=ins['opcode'],symbol=symbol))
                row['source_references']=calls
            else:row['frame_flags']=R.flags(name,a,True,False,False)
            members[key]=row
    natives=[]
    for name,desc,access,op in SPECS:
        row=members[OWNER,name,desc];S.check(row['access']==access and 'code_sha256' not in row and row['frame_flags']==32,'Original Inflater native declaration/frame differs')
        natives.append(dict(row,operation=op,supported=op<=5))
    S.check(len([m for m in raws[OWNER].methods if m['access']&256])==len(natives),'Unmodelled Inflater native declaration')
    pathrows=[members[key] for key in paths];callbacks=[members[key] for key in CALLBACKS]
    clinit=members[OWNER,'<clinit>','()V']['source_references'];load=members['java/util/zip/ZipUtils','loadLibrary','()V']['source_references']
    order=[r['symbol']['Method']['name'] for r in clinit if 'Method' in r['symbol']]
    S.check(order[-2:]==['loadLibrary','initIDs'] and load[0]['symbol']=={'StringUtf16':[122,105,112]} and
        load[1]['symbol']['Method']['owner']=='jdk/internal/loader/BootLoader','Original zip initialization order changed')
    boot=raws['jdk/internal/loader/BootLoader'];[boot_method]=[m for m in boot.methods if (m['name'],m['descriptor'])==('loadLibrary','(Ljava/lang/String;)V')]
    instructions=list(I.stream(boot.code(boot_method)['bytes']));load_result_pop=[]
    for i,ins in enumerate(instructions[:-1]):
        if ins['opcode']!=0xb6:continue
        target=boot.symbol(ins['operand']['Constant'])['Method']
        if (target['owner'],target['name'],target['descriptor'])==('jdk/internal/loader/NativeLibraries','loadLibrary','(Ljava/lang/String;)Ljdk/internal/loader/NativeLibrary;'):
            S.check(instructions[i+1]['opcode']==0x57,'BootLoader no longer discards the library load result')
            load_result_pop.append(dict(call_pc=ins['pc'],pop_pc=instructions[i+1]['pc']))
    S.check(len(load_result_pop)==1,'Original BootLoader load return handling differs')
    fields=[];owner=owners[OWNER]
    for name in ('inputConsumed','outputConsumed'):
        found=[i for i,f in enumerate(owner['fields']) if f==dict(name=name,descriptor='I',access=2)];S.check(len(found)==1,'Original JNI error field differs')
        fields.append(dict(name=name,index=found[0]))
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as archive:
        maps={r['declaring_field']:r for line in archive.open('fields.jsonl') if (r:=json.loads(line))['declaring_class']==owner['id']}
        byte_types=[r for line in archive.open('types.jsonl') if (r:=json.loads(line))['name'] in ('[B','B')]
    arrays=[r for r in byte_types if r['name']=='[B'];primitives=[r for r in byte_types if r['name']=='B']
    S.check(len(arrays)==len(primitives)==1 and arrays[0]['kind']==3 and primitives[0]['kind']==0 and primitives[0]['marker_flags']==1 and
            arrays[0]['parent_component']==primitives[0]['id'],'Normal source byte[] runtime type differs')
    needed={c['id'] for c in owners.values()};layouts={}
    for line in S.checked(summary['layouts']).open(encoding='utf-8'):
        row=json.loads(line)
        if row['class_id'] in needed:layouts[row['class_id']]=row
    direct=F.fields(owner,layouts[owner['id']],[(n,'I',2,4,False) for n in ('inputConsumed','outputConsumed')],S)
    for field in fields:
        fmap=maps[field['index']];S.check(not fmap['reference'] and fmap['storage_bytes']==4 and any(r['receiver_class']==owner['id'] and r['offset']==next(f['offset'] for f in direct if f['name']==field['name']) for r in fmap['rows']),'Original Inflater FMAP differs')
        field['field_map']=fmap
    pins={name:S.artifact(S.ART/'inflater-normal/pinned-sources'/name) for name in PINS}
    S.check(all(r['digest']['sha256']==PINS[n] for n,r in pins.items()),'Locked Inflater Java source pin changed')
    native=S.artifact(S.ART/'deflate-raw/pinned-sources/Inflater.c')
    S.check(native['digest']['sha256']=='b1e0fddcb21a0f99dcf80fdf500245b7bf76991445cb8b21a52787250e30ddae','Locked Inflater.c differs')
    shape=summary['string_literals']['source_layout'];S.check(shape['class_id']==owners['java/lang/String']['id'] and shape['source_sha256']==owners['java/lang/String']['origin']['sha256'] and summary['properties']['pool_abi']==2,'Normal error-message String factory differs')
    return dict(schema=1,owner=owner['id'],methods=natives,original_java_paths=pathrows,java_callbacks=callbacks,source_classes={n:c['id'] for n,c in owners.items()},fields=fields,
        byte_array_type=arrays[0]['id'],array_heap_kind=264,source_String_shape=shape,native_sources=dict(pins,**{'Inflater.c':native}),
        required_classes=sorted(needed),required_java_methods=[m['method'] for m in callbacks],required_base_modules=['runtime_metadata','properties','unsafe_fields','frames'],required_provider_families=['normal-throwable-v1'],
        source_clinit_calls_original_zip_load=True,BootLoader_discards_library_load_result=load_result_pop,
        actual_first_constructor_obstruction_not_inferred_from_missing_zip=True,
        source_policy=POLICY,pool_bytes=128,pool_abi=1,node_bytes=34608,node_state_offset=48,raw_state_bytes=34304,zlib_state_bytes=34560,
        native_nodes_contain_oops=False,native_root_spans=[],registered=False,executed=False,game_started=False)


def aliases(meta):
    names=meta['source_classes'];values={'IF_THROWABLE_TYPE':f"boom_t{names['java/lang/Throwable']}"}
    for i,name in enumerate(ERRORS):
        ctor=next(m['method'] for m in meta['java_callbacks'] if m['owner']==name and m['name']=='<init>')
        values.update({f'IF_ERROR_CLASS{i}':f'boom_class{names[name]}',f'IF_ERROR_LAYOUT{i}':f'boom_layout{names[name]}',f'IF_ERROR_CTOR{i}':f'boom_m{ctor}'})
    for field in meta['fields']:values['IF_'+('INPUT' if field['name']=='inputConsumed' else 'OUTPUT')+'_MAP']=f"boom_field_map{field['field_map']['id']}"
    return values


def native_imports(meta):
    a=aliases(meta);procs=FOREIGN|{a[f'IF_ERROR_CTOR{i}'] for i in range(3)}|{a['IF_INPUT_MAP'],a['IF_OUTPUT_MAP']}
    procs|={'boom_heap_contains','boom_class_ensure32','boom_object_new','boom_exception_set32','boom_java_property_copy','boom_java_string_literal','boom_trace_enter','boom_trace_leave',
        'boom_deflate_stream_reset','boom_deflate_stream_step','boom_zlib_stream_reset','boom_zlib_stream_step'}
    data=set(a.values())-procs|{'boom_heap_ptr','boom_runtime_type_map','boom_trace_pool','boom_java_properties_string_pool'}
    data|={f"boom_trace_method{m['method']}" for m in meta['methods']}
    return procs,data


def data(meta):
    a=aliases(meta);text=''.join(f'{n} TEXTEQU <{v}>\n' for n,v in a.items())
    text+='''.const
ALIGN 8
PUBLIC boom_inflater_errors
boom_inflater_errors LABEL QWORD
'''
    for i in range(3):text+=f' QWORD OFFSET IF_ERROR_CLASS{i},OFFSET IF_ERROR_LAYOUT{i},OFFSET IF_ERROR_CTOR{i}\n'
    text+=f'''.const
ALIGN 8
PUBLIC boom_inflater_string_pool
boom_inflater_string_pool DWORD 050524F50h,2,0,0
 QWORD OFFSET boom_heap_ptr,OFFSET boom_java_properties_string_pool,0,0,0
 DWORD 0,0
 QWORD 0,0
 QWORD 0,OFFSET boom_java_property_copy,0,OFFSET boom_java_string_literal
.data
ALIGN 8
PUBLIC {POOL}
{POOL} DWORD 04C464E49h,1
 QWORD OFFSET boom_heap_ptr
 QWORD 0,0,0,0,0,0,0
 QWORD OFFSET IF_INPUT_MAP,OFFSET IF_OUTPUT_MAP,OFFSET boom_inflater_string_pool
 QWORD 0,0,0,0
'''
    return text


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    S=module('runtime-provider-source');state=S.read(a.state);identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    S.check(S.digest(Path(state['batch'])/'summary.json')['sha256']==state['batch_summary_sha256'] and S.digest(Path(state['batch'])/'verification.json')['sha256']==state['batch_verification_sha256'],'Current source-pending state proof changed')
    model=index(summary,classes,S);output=a.output.resolve();S.check(output.is_relative_to(S.ART/'inflater-normal') and not output.exists(),'Fresh source model directory required');output.mkdir(parents=True)
    S.write(output/'source-model.json',dict(input_state=S.artifact(a.state),base=identity,source=model,producer=S.artifact(__file__),scope='current_verified_base_original_Inflater_source_model_only_no_native_execution'))
    print(output/'source-model.json')
