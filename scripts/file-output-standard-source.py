"""Original FOS writes, bounded to the original Java FD.out/err identities."""
import hashlib
import json


OWNER='java/io/FileOutputStream'
FD='java/io/FileDescriptor'
POOL='boom_provider_file_output_standard_pool'
SERVICE='boom_provider_file_output_standard_service'
CONTROL={'boom_file_output_standard_counters'}
FOREIGN={'GetStdHandle','WriteFile','GetLastError','FormatMessageW','GetProcessHeap','HeapAlloc','HeapFree'}
KERNELS=['classes32.asm','frames.asm','heap.asm','objects.asm','file_streams.asm','file_descriptors.asm',
         'runtime_types.asm','runtime_type_index.asm','types.asm','java_properties.asm']
SPECS=[(OWNER,'write','(IZ)V'),(OWNER,'writeBytes','([BIIZ)V')]
JAVA=[(name,'<init>','(Ljava/lang/String;)V') for name in
      ('java/io/IOException','java/lang/NullPointerException','java/lang/IndexOutOfBoundsException','java/lang/OutOfMemoryError')]
JAVA+=[('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]
PINS={'FileOutputStream.c':'d6150579fde20690e9cbb982d28f4fcb52536629a038f843b4c4fb01e1f93691',
      'FileOutputStream.java':'01bbc440c56d2588c53717be9456d0e777850b2e2d019125007c35210faa6adf',
      'FileDescriptor.java':'f2d3fe65312b41bd7c2f42236a6fecabe7d59913af14435ea8d8eaa1f010898c',
      'PrintStream.java':'00877c84d7186458abb0deb7f35ef873d9ed044a7af24658696b05dc4c6c9308'}
SHARED_PINS={'io_util.c':'a191fba799a2f902763b8a59d5cb5df9fa5f55ca788bb4eaf22a098e05e25415',
    'io_util_md.c':'f3630be207d35aafdd60edb8c8db0ed23e84d7092f374138cee27761a6bfdaa7',
    'jni_util_md.c':'7a7adff4a3631fa5476d1f1dc54260ea0fccc535bbb149fb72fee21ac59d38a5'}
POLICY=dict(normal_context_bytes=32,normal_source_fields_and_registration=True,
    original_FD_out_err_static_identity_required=True,actual_GetStdHandle_equality_each_write=True,
    source_FOS_fd_reloaded_after_every_partial_write=True,source_handle_reloaded_after_every_partial_write=True,
    no_arbitrary_HANDLE_adoption=True,standard_handles_never_closed=True,open0_or_close0_implemented=False,
    nonzero_append='explicit_context20',zero_length_before_FD_or_append_check=True,write_byte_low8=True,
    private_buffer_stack_limit=8192,large_private_buffer_Win32_heap_owned=True,typed_source_exceptions=True,
    zero_progress_single='successful_return_like_original_writeSingle',
    zero_progress_array='fail_closed_IOException_Write_error_instead_of_original_nonprogress_loop',
    concurrent_writes='original_unsynchronized_partial_write_order',
    exact_source_FOS_receiver=True,normal_heap_required=True,existing_pending_context_preserved=True,
    nonmoving_heap=True,collection_requires_quiescent_external_calls=True,automatic_GC=False,
    external_JNI_environment=False,source_transform_chain='original_locked_no_transforms')


def index(summary,classes,S):
    I=S.module('output_standard_original_class','verify-translation-ir.py')
    F=S.module('output_standard_registration','file-bootstrap-source.py')
    wanted={OWNER,FD,'java/lang/String'}|{row[0] for row in JAVA}
    owners={row['name']:row for row in classes if row['origin']['loader']=='bootstrap' and row['name'] in wanted}
    S.check(set(owners)==wanted,'Original standard-output classes missing')
    methods=[];java=[];standard=[]
    for name,cls in owners.items():
        S.check(cls['origin']['source_id']=='jdk:java.base' and not cls['origin'].get('generated'),'Original java.base output source required')
        raw=I.Source(S.original_class(summary,cls))
        S.check(raw.name==name and len(raw.methods)==len(cls['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==cls['fields'],'Output original source inventory differs')
        for ident,method in zip(cls['method_ids'],raw.methods):
            key=name,method['name'],method['descriptor']
            if key not in SPECS+JAVA:continue
            code=raw.code(method);row=dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],loader='bootstrap',
                source_id='jdk:java.base',owner=name,name=method['name'],descriptor=method['descriptor'],access=method['access'])
            if key in SPECS:
                S.check(method['access']==0x102 and code is None,'Original output native declaration changed')
                methods.append(dict(**row,operation=SPECS.index(key)))
            else:
                S.check(code is not None,'Original output error constructor/wrapper Code missing')
                java.append(dict(**row,code_sha256=hashlib.sha256(code['bytes']).hexdigest()))
        if name==FD:
            for field in ('out','err'):
                [i]=[i for i,f in enumerate(raw.fields) if (f['name'],f['descriptor'],f['access'])==(field,'Ljava/io/FileDescriptor;',0x19)]
                standard.append(dict(name=field,declaring_class=cls['id'],declaring_field=i,
                    symbol=f"boom_s{cls['id']}_{i}",descriptor='Ljava/io/FileDescriptor;',source_access=0x19,
                    Java_fd=1 if field=='out' else 2,Windows_std_handle=-11 if field=='out' else -12))
    S.check(len(methods)==2 and len(java)==len(JAVA) and len(standard)==2,'Output source declarations incomplete')
    registration=F.index(summary,classes,S);descriptor=registration['descriptor']
    [stream]=[row for row in registration['streams'] if row['class_id']==owners[OWNER]['id']]
    S.check(descriptor['class_id']==owners[FD]['id'],'Output descriptor registration identity differs')
    with S.checked(summary['layouts']).open(encoding='utf-8') as source:
        [layout]=[r for line in source if (r:=json.loads(line))['class_id']==owners['java/lang/String']['id']]
    shape=summary['string_literals']['source_layout']
    fields=F.fields(owners['java/lang/String'],layout,[('value','[B',0x12,8,True),('coder','B',0x12,1,False),
        ('hash','I',2,4,False),('hashIsZero','Z',2,1,False)],S)
    mapping={'value':'value_offset','coder':'coder_offset','hash':'hash_offset','hashIsZero':'hash_is_zero_offset'}
    S.check(shape['class_id']==owners['java/lang/String']['id'] and all(shape[mapping[f['name']]]==f['offset'] for f in fields),
        'Standard-output normal String factory differs')
    source=S.ART/'file-output-standard/pinned-sources/jdk-21.0.13+3'
    shared=S.ART/'file-input-stream/pinned-sources/jdk-21.0.13+3'
    pins={name:S.artifact(source/name) for name in PINS}|{name:S.artifact(shared/name) for name in SHARED_PINS}
    S.check(all(row['digest']['sha256']==(PINS|SHARED_PINS)[name] for name,row in pins.items()),'Locked original output semantics source changed')
    return dict(schema=1,owner=owners[OWNER]['id'],methods=sorted(methods,key=lambda row:row['operation']),original_java=java,
        source_classes={name:cls['id'] for name,cls in owners.items()},stream=stream,descriptor=descriptor,standard_fields=standard,
        source_String_shape=shape,source_String_fields=fields,required_classes=sorted(cls['id'] for cls in owners.values()),
        required_java_methods=[row['method'] for row in java],required_base_modules=['runtime_metadata','properties'],
        required_provider_families=['normal-file-bootstrap-v1','normal-throwable-v1'],native_root_spans=[],
        pool_bytes=112,pool_abi=2,native_sources=pins,
        original_field_extractor='boom_stream_descriptor',field_extractor_context16_prefix_compatible_with_Context32=True)


def aliases(meta):
    cls=meta['source_classes'];a=dict(FOS_STREAM_LAYOUT=f"boom_layout{cls[OWNER]}",FOS_FD_LAYOUT=f"boom_layout{cls[FD]}",
        FOS_THROWABLE_TYPE=f"boom_t{cls['java/lang/Throwable']}")
    for prefix,name in [('IOE','java/io/IOException'),('NPE','java/lang/NullPointerException'),
                        ('BOUNDS','java/lang/IndexOutOfBoundsException'),('OOM','java/lang/OutOfMemoryError')]:
        [method]=[row['method'] for row in meta['original_java'] if row['owner']==name and row['name']=='<init>']
        a['FOS_'+prefix+'_CLASS']=f"boom_class{cls[name]}";a['FOS_'+prefix+'_LAYOUT']=f"boom_layout{cls[name]}";a['FOS_'+prefix+'_CTOR']=f'boom_m{method}'
    for row in meta['standard_fields']:a['FOS_STD_'+row['name'].upper()]=row['symbol']
    return a


def native_imports(meta):
    a=aliases(meta);procs=FOREIGN|{value for name,value in a.items() if name.endswith('_CTOR')}|{
        'boom_class_ensure32','boom_heap_contains','boom_object_check','boom_object_new','boom_stream_descriptor',
        'boom_exception_set32','boom_java_property_copy','boom_java_string_literal','boom_trace_enter','boom_trace_leave'}
    data=set(a.values())-procs|{'boom_heap_ptr','boom_provider_file_bootstrap_pool','boom_runtime_type_map',
        'boom_java_properties_string_pool','boom_trace_pool'}|{f"boom_trace_method{row['method']}" for row in meta['methods']}
    return procs,data


def data(meta):
    text=''.join(f'{name} TEXTEQU <{value}>\n' for name,value in aliases(meta).items())
    text+=f"FOS_STREAM_FD EQU {meta['stream']['fd_offset']}\n"
    for prefix,name in [('INT','fd'),('HANDLE','handle'),('APPEND','append')]:
        text+=f"FOS_FD_{prefix} EQU {next(row['offset'] for row in meta['descriptor']['fields'] if row['name']==name)}\n"
    return text+f'''.const
ALIGN 8
PUBLIC {POOL}
{POOL} DWORD 050524F50h,2,0,0
 QWORD OFFSET boom_heap_ptr,OFFSET boom_java_properties_string_pool,0,0,0
 DWORD 0,0
 QWORD 0,0
 QWORD 0,OFFSET boom_java_property_copy,0,OFFSET boom_java_string_literal
'''
