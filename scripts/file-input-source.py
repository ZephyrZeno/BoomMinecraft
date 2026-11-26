"""Eight original read-only FileInputStream/FileDescriptor source contracts."""
import hashlib
import json


OWNER='java/io/FileInputStream'
FD='java/io/FileDescriptor'
POOL='boom_provider_file_input_pool'
SERVICE='boom_provider_file_input_service'
CONTROL={'boom_file_input_owner_roots','boom_file_input_owners','boom_file_input_live_handles',
         'boom_file_input_owned_buffers','boom_file_input_close_waits'}
FOREIGN={'AcquireSRWLockExclusive','ReleaseSRWLockExclusive','WaitOnAddress','WakeByAddressAll',
         'GetProcessHeap','HeapAlloc','HeapFree','GetFullPathNameW','CreateFileW','GetFileType',
         'ReadFile','GetFileSizeEx','SetFilePointerEx','CloseHandle','GetLastError','FormatMessageW'}
KERNELS=['classes32.asm','frames.asm','heap.asm','objects.asm','file_streams.asm','file_descriptors.asm',
         'runtime_types.asm','runtime_type_index.asm','types.asm','java_properties.asm']
SPECS=[(OWNER,'open0','(Ljava/lang/String;)V'),(OWNER,'read0','()I'),(OWNER,'readBytes','([BII)I'),
       (OWNER,'length0','()J'),(OWNER,'position0','()J'),(OWNER,'skip0','(J)J'),
       (OWNER,'available0','()I'),(FD,'close0','()V')]
JAVA=[('java/lang/String','length','()I'),('java/lang/String','toCharArray','()[C'),
      ('java/io/IOException','<init>','(Ljava/lang/String;)V'),
      ('java/io/FileNotFoundException','<init>','(Ljava/lang/String;Ljava/lang/String;)V'),
      ('java/lang/NullPointerException','<init>','()V'),
      ('java/lang/IndexOutOfBoundsException','<init>','()V'),
      ('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]
PINS={'FileInputStream.c':'f8d81cbead0daa771be62bc0e712a36621fd9ca121f830a8073a27ce28f33233',
      'canonicalize_md.c':'ea886e568ae007302f31447b9c1910eb87e77191c41df3ccf7a7732fc0bc9996',
      'FileDescriptor_md.c':'9a3342c9c65c83ece5afa193e1d24e8abec1f1ce8d742933ff5c4db994aec272',
      'io_util.c':'a191fba799a2f902763b8a59d5cb5df9fa5f55ca788bb4eaf22a098e05e25415',
      'io_util_md.c':'f3630be207d35aafdd60edb8c8db0ed23e84d7092f374138cee27761a6bfdaa7',
      'io_util_md.h':'94b8e577df754524fe61dc2672bd1ed19f634defbe87afe3a05116a624ac074f',
      'io_util.h':'ff1c363e3edecb164d2f7112dbb33996d2a1221f337264308546c57780a3a5c3',
      'jni_util_md.c':'7a7adff4a3631fa5476d1f1dc54260ea0fccc535bbb149fb72fee21ac59d38a5'}
POLICY=dict(normal_source_layouts=True,normal_context_bytes=32,original_registered_field_tables=True,
    source_String_callbacks=True,source_typed_IOException_FileNotFoundException=True,
    source_typed_null_and_bounds_errors=True,read_bytes_private_buffer_then_copy=True,
    read_bytes_zero_before_closed_check=True,EOF_minus_one=True,signed_skip=True,
    open_access=0x80000000,open_sharing=3,open_disposition=3,open_attributes=0x80,
    maximum_effective_path_units=32767,early_NUL_terminates_native_path=True,
    owned_regular_disk_files_only=True,external_FileDescriptor_adoption=False,standard_streams_owned=False,
    exact_FileInputStream_receiver_layout=True,per_descriptor_IO_serialization=True,
    close_invalidates_source_handle_before_waiting=True,close_waits_for_all_native_borrows=True,
    failed_close_retains_owned_handle_for_retry=True,Java_callbacks_outside_OS_locks=True,
    owner_root_retained_until_explicit_close=True,automatic_Cleaner_or_weak_GC=False,
    native_owner_root_span_must_be_registered_by_future_formal_consumer=True,
    nonmoving_heap=True,collection_requires_quiescence=True,
    cross_call_GetLastError_history_compatibility=False,exact_all_original_OOM_sites_proven=False,
    source_transform_chain='original_locked_no_transforms')


def index(summary,classes,S):
    I=S.module('file_input_original_class','verify-translation-ir.py')
    F=S.module('file_input_source_fields','file-bootstrap-source.py')
    wanted={row[0] for row in SPECS+JAVA}
    owners={c['name']:c for c in classes if c['origin']['loader']=='bootstrap' and c['name'] in wanted}
    S.check(set(owners)==wanted,'Read-only stream original classes missing')
    members={};inventory=[]
    for name,cls in owners.items():
        S.check(cls['origin']['source_id']=='jdk:java.base' and not cls['origin'].get('generated'),
            'Read-only stream requires locked original java.base source')
        raw=I.Source(S.original_class(summary,cls))
        S.check(raw.name==name and len(raw.methods)==len(cls['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==cls['fields'],
            'Read-only source class inventory differs')
        for ident,method in zip(cls['method_ids'],raw.methods):
            key=name,method['name'],method['descriptor']
            if name in (OWNER,FD) and method['access']&0x100:
                inventory.append(dict(owner=name,method=ident,name=method['name'],descriptor=method['descriptor'],access=method['access']))
            if key not in SPECS+JAVA:continue
            code=raw.code(method)
            members[key]=dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],
                loader='bootstrap',source_id='jdk:java.base',owner=name,name=method['name'],descriptor=method['descriptor'],
                access=method['access'],code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None)
    methods=[]
    for operation,key in enumerate(SPECS):
        row=dict(members[key])
        S.check(row['access']==0x102 and row.pop('code_sha256') is None,'Original read-only native declaration changed')
        methods.append(dict(**row,operation=operation))
    java=[members[key] for key in JAVA]
    S.check(all(row['code_sha256'] for row in java),'Read-only original Java callback Code missing')
    registration=F.index(summary,classes,S)
    [stream]=[row for row in registration['streams'] if row['class_id']==owners[OWNER]['id']]
    descriptor=registration['descriptor']
    S.check(descriptor['class_id']==owners[FD]['id'],'Descriptor registration class differs')
    with S.checked(summary['layouts']).open(encoding='utf-8') as source:
        [layout]=[row for line in source if (row:=json.loads(line))['class_id']==owners['java/lang/String']['id']]
    string_fields=F.fields(owners['java/lang/String'],layout,[('value','[B',0x12,8,True),('coder','B',0x12,1,False),
        ('hash','I',2,4,False),('hashIsZero','Z',2,1,False)],S)
    shape=summary['string_literals']['source_layout']
    mapping={'value':'value_offset','coder':'coder_offset','hash':'hash_offset','hashIsZero':'hash_is_zero_offset'}
    S.check(shape['class_id']==owners['java/lang/String']['id'] and all(shape[mapping[f['name']]]==f['offset'] for f in string_fields),
        'Read-only String factory shape differs')
    pinned=S.ART/'file-input-stream/pinned-sources/jdk-21.0.13+3'
    sources={name:S.artifact(pinned/name) for name in PINS}
    S.check(all(row['digest']['sha256']==PINS[name] for name,row in sources.items()),'Read-only pinned C native source changed')
    return dict(schema=1,owner=owners[OWNER]['id'],methods=methods,original_java=java,native_inventory=inventory,
        source_classes={name:cls['id'] for name,cls in owners.items()},stream=stream,descriptor=descriptor,
        source_String_fields=string_fields,source_String_shape=shape,
        required_classes=sorted(cls['id'] for cls in owners.values()),required_java_methods=[row['method'] for row in java],
        required_base_modules=['runtime_metadata','properties'],
        required_provider_families=['normal-file-bootstrap-v1','normal-throwable-v1'],
        native_root_spans=[dict(symbol='boom_file_input_owner_roots',count=4096,kind='strong_owned_FileDescriptor_until_close')],
        original_field_registration_pool='boom_provider_file_bootstrap_pool',original_field_extractor='boom_stream_descriptor',
        field_extractor_context16_prefix_compatible_with_Context32=True,
        source_fields_read_or_written=descriptor['fields']+[dict(name='fd',descriptor='Ljava/io/FileDescriptor;',
            offset=stream['fd_offset'],width=8)],pool_bytes=112,pool_abi=2,native_sources=sources)


def aliases(meta):
    classes=meta['source_classes']
    find=lambda owner,name:next(row['method'] for row in meta['original_java'] if row['owner']==owner and row['name']==name)
    a=dict(FIR_STREAM_LAYOUT=f"boom_layout{classes[OWNER]}",FIR_FD_LAYOUT=f"boom_layout{classes[FD]}",
        FIR_STRING_LAYOUT=f"boom_layout{classes['java/lang/String']}",
        FIR_STRING_CHARS=f"boom_m{find('java/lang/String','toCharArray')}",FIR_STRING_LENGTH=f"boom_m{find('java/lang/String','length')}",
        FIR_THROWABLE_TYPE=f"boom_t{classes['java/lang/Throwable']}")
    for prefix,name in [('IOE','java/io/IOException'),('FNFE','java/io/FileNotFoundException'),
                        ('NPE','java/lang/NullPointerException'),('BOUNDS','java/lang/IndexOutOfBoundsException')]:
        a['FIR_'+prefix+'_CLASS']=f'boom_class{classes[name]}'
        a['FIR_'+prefix+'_LAYOUT']=f'boom_layout{classes[name]}'
        a['FIR_'+prefix+'_CTOR']=f"boom_m{find(name,'<init>')}"
    return a


def native_imports(meta):
    a=aliases(meta);procs={value for name,value in a.items() if name.endswith('_CTOR') or name in ('FIR_STRING_LENGTH','FIR_STRING_CHARS')}
    procs|=FOREIGN|{'boom_heap_contains','boom_object_check','boom_object_new','boom_stream_descriptor',
        'boom_exception_set32','boom_java_property_copy','boom_java_string_literal','boom_trace_enter','boom_trace_leave'}
    data=set(a.values())-procs
    data|={'boom_heap_ptr','boom_provider_file_bootstrap_pool','boom_runtime_type_map','boom_java_properties_string_pool','boom_trace_pool'}
    data|={f"boom_trace_method{row['method']}" for row in meta['methods']}
    return procs,data


def data(meta):
    text=''.join(f'{name} TEXTEQU <{value}>\n' for name,value in aliases(meta).items())
    for name,field in [('INT','fd'),('HANDLE','handle'),('APPEND','append')]:
        offset=next(row['offset'] for row in meta['descriptor']['fields'] if row['name']==field)
        text+=f'FIR_FD_{name} EQU {offset}\n'
    return text+f'''.const
ALIGN 8
PUBLIC {POOL}
{POOL} DWORD 050524F50h,2,0,0
 QWORD OFFSET boom_heap_ptr,OFFSET boom_java_properties_string_pool,0,0,0
 DWORD 0,0
 QWORD 0,0
 QWORD 0,OFFSET boom_java_property_copy,0,OFFSET boom_java_string_literal
'''
