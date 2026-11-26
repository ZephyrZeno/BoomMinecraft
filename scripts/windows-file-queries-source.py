"""Locked legacy java.io WinNT readonly queries, normal File.path and source frames."""
import hashlib
import json
from pathlib import Path
import re
import zipfile


OWNER='java/io/WinNTFileSystem'
POOL='boom_provider_windows_file_queries_pool'
SERVICE='boom_provider_windows_file_queries_service'
CONTROL={'boom_windows_file_queries_owned_buffers','boom_query_path_attributes','boom_query_raw_file_attributes'}
FOREIGN={'GetFileAttributesExW','GetFileAttributesW','GetLastError','SetLastError','FindFirstFileW','FindClose','CreateFileW',
    'GetFileInformationByHandle','DeviceIoControl','CloseHandle','LocalAlloc','LocalFree','GetFileTime',
    'GetLogicalDrives','GetVolumePathNameW','GetDiskFreeSpaceExW','GetVolumeInformationW',
    'GetFullPathNameW','GetCurrentDirectoryW','GetDriveTypeW','GetProcessHeap','HeapAlloc','HeapFree','FormatMessageW'}
KERNELS=['classes32.asm','frames.asm','heap.asm','objects.asm','field_address.asm','java_properties.asm',
    'runtime_types.asm','runtime_type_index.asm','types.asm']
SPECS=[(OWNER,'getBooleanAttributes0','(Ljava/io/File;)I',0),
    (OWNER,'getLastModifiedTime0','(Ljava/io/File;)J',1),(OWNER,'getLength0','(Ljava/io/File;)J',2),
    (OWNER,'listRoots0','()I',3),(OWNER,'getSpace0','(Ljava/io/File;I)J',4),
    (OWNER,'getNameMax0','(Ljava/lang/String;)I',5),(OWNER,'checkAccess0','(Ljava/io/File;I)Z',6)]
JAVA=[('java/lang/String','length','()I'),('java/lang/String','toCharArray','()[C'),
    ('java/io/IOException','<init>','(Ljava/lang/String;)V'),
    ('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]
WRAPPERS=[(OWNER,'getBooleanAttributes','(Ljava/io/File;)I'),
    (OWNER,'getLastModifiedTime','(Ljava/io/File;)J'),(OWNER,'getLength','(Ljava/io/File;)J'),
    (OWNER,'listRoots','()[Ljava/io/File;'),(OWNER,'getSpace','(Ljava/io/File;I)J'),
    (OWNER,'getNameMax','(Ljava/lang/String;)I'),(OWNER,'checkAccess','(Ljava/io/File;I)Z')]
PINS={'WinNTFileSystem_md.c':'0a8dbaa9872c434b5405ae698bd7777561fe73ab24adaa1eef19169e72e7682e',
    'io_util_md.c':'f3630be207d35aafdd60edb8c8db0ed23e84d7092f374138cee27761a6bfdaa7',
    'io_util_md.h':'94b8e577df754524fe61dc2672bd1ed19f634defbe87afe3a05116a624ac074f',
    'canonicalize_md.c':'ea886e568ae007302f31447b9c1910eb87e77191c41df3ccf7a7732fc0bc9996',
    'WinNTFileSystem.java':'578a582b3071e6cc3a218438846d0e4398913ccbe40e0e87b563a35dad50ab9d',
    'jni_util.c':'31596047469d6107b1e515eb04f3e9a9d98719ba50d2d9d753309eef51b2ce94',
    'jni_util_md.c':'7a7adff4a3631fa5476d1f1dc54260ea0fccc535bbb149fb72fee21ac59d38a5'}
RENAMES={'boom_win32_path_attributes':'boom_query_path_attributes',
    'boom_win32_raw_file_attributes':'boom_query_raw_file_attributes'}
POLICY=dict(legacy_java_io=True,normal_source_layouts=True,inherited_File_path_FMAP=True,
    published_WNFS_FieldID_required=True,source_String_callbacks=True,source_IOException_constructor=True,
    attr_fallback_errors=[32,5],length_fallback_errors=[32],length_fallback_exact_case=True,
    length_fallback_reparse_rejected=True,length_fallback_unsigned_overflow_rejected=True,
    reserved_device_filter_on_boolean_attributes_only=True,follow_reparse_by_handle=True,
    AF_UNIX_fallback_on_error_1920=True,mtime_access_mask=0,mtime_unsigned_ticks_divisor=10000,
    mtime_epoch_milliseconds=11644473600000,space_selectors=[0,1,2],name_max_null_root_allowed=True,
    first_embedded_NUL_terminates_native_path=True,long_path_prefix_threshold=248,
    process_cwd_stable_during_execution=True,CRT_allocation_and_cached_cwd_history_compatibility_proven=False,
    exact_original_all_malloc_site_OOM_behavior_proven=False,nonmoving_heap=True,
    collection_requires_quiescence=True,external_JNI_environment=False,
    source_transform_chain='original_locked_no_transforms',read_only=True)


def index(summary,classes,S):
    I=S.module('windows_query_original_class','verify-translation-ir.py')
    F=S.module('windows_query_fields','file-bootstrap-source.py')
    wanted={OWNER,'java/io/File','java/lang/String','java/io/IOException','java/lang/Throwable'}
    owners={c['name']:c for c in classes if c['name'] in wanted and c['origin']['loader']=='bootstrap'}
    S.check(set(owners)==wanted,'Original WinNT query classes are missing')
    members={}
    for name,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),
            'Original locked bootstrap query classes required')
        raw=I.Source(S.original_class(summary,c))
        S.check(raw.name==name and len(raw.methods)==len(c['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==c['fields'],
            'Original query class method/field inventory differs')
        for ident,m in zip(c['method_ids'],raw.methods):
            key=name,m['name'],m['descriptor']
            if key not in JAVA+WRAPPERS+[row[:3] for row in SPECS]:continue
            body=raw.code(m)
            members[key]=dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',
                source_id='jdk:java.base',owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],
                code_sha256=hashlib.sha256(body['bytes']).hexdigest() if body else None)
    methods=[]
    for owner,name,descriptor,operation in SPECS:
        row=dict(members[owner,name,descriptor]);access=0x10a if operation==3 else 0x102
        S.check(row['access']==access and row.pop('code_sha256') is None,'Original query native declaration differs')
        methods.append(dict(**row,operation=operation))
    java=[members[key] for key in JAVA];wrappers=[members[key] for key in WRAPPERS]
    S.check(all(row['code_sha256'] for row in java+wrappers),'Original query Java Code missing')
    file=owners['java/io/File'];field_index=next(i for i,f in enumerate(file['fields']) if
        f==dict(name='path',descriptor='Ljava/lang/String;',access=0x12))
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as archive:
        [field]=[r for line in archive.open('fields.jsonl') if (r:=json.loads(line))['declaring_class']==file['id'] and
            r['declaring_field']==field_index]
        needed={r['receiver_class'] for r in field['rows']}
        types={r['id']:r for line in archive.open('types.jsonl') if (r:=json.loads(line))['id'] in needed}
    allclasses={c['id']:c for c in classes};layouts={}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['class_id'] in needed|{c['id'] for c in owners.values()}:layouts[row['class_id']]=row
    S.check(field['reference'] is True and field['storage_bytes']==8 and file['id'] in needed and
        len(needed)==len(field['rows']) and set(types)==needed,'File.path inherited source FMAP differs')
    for row in field['rows']:
        ident,offset=row['receiver_class'],row['offset'];layout=layouts[ident]
        S.check(types[ident]['kind']==1 and types[ident]['source_sha256']==allclasses[ident]['origin']['sha256'] and
            (ident==file['id'] or file['id'] in types[ident]['ancestors']) and layout['diagnostic'] is None and
            layout['source_sha256']==allclasses[ident]['origin']['sha256'] and offset%8==0 and
            offset+8<=layout['candidate']['payload_bytes'] and offset<layout['candidate']['reference_prefix']*8 and
            any(f['member']['owner']==file['id'] and f['member']['index']==field_index and f['offset']==offset and
                f['reference'] and f['storage_bytes']==8 for f in layout['candidate']['fields']),
            'Inherited File.path source receiver layout differs')
    normal_field=F.fields(file,layouts[file['id']],[('path','Ljava/lang/String;',0x12,8,True)],S)[0]
    normal_field['index']=field_index
    string=owners['java/lang/String'];shape=summary['string_literals']['source_layout']
    stringfields=F.fields(string,layouts[string['id']],[('value','[B',0x12,8,True),('coder','B',0x12,1,False),
        ('hash','I',2,4,False),('hashIsZero','Z',2,1,False)],S)
    offsets={'value':'value_offset','coder':'coder_offset','hash':'hash_offset','hashIsZero':'hash_is_zero_offset'}
    S.check(shape['class_id']==string['id'] and shape['source_sha256']==string['origin']['sha256'] and
        all(shape[offsets[f['name']]]==f['offset'] for f in stringfields) and summary['properties']['pool_abi']==2,
        'Query String factory must use the original normal source shape')
    pinned=S.ART/'windows-path-canonicalization/pinned-sources/jdk-21.0.13+3'
    sources={name:S.artifact(pinned/name) for name in PINS}
    S.check(all(r['digest']['sha256']==PINS[n] for n,r in sources.items()),'Pinned query native semantics changed')
    primitive=S.ROOT/'native/runtime/win32_path_attributes.asm'
    declarations=re.findall(r'(?im)^\s*EXTERN\s+(\w+)\s*:\s*(PROC|BYTE)\s*$',primitive.read_text())
    S.check(declarations and all(name in FOREIGN for name,_ in declarations) and
        set(re.findall(r'(?m)^PUBLIC (\w+)$',primitive.read_text()))==set(RENAMES),
        'Readonly path attribute primitive declarations changed')
    return dict(schema=1,owner=owners[OWNER]['id'],methods=methods,original_java=java,original_wrappers=wrappers,
        source_classes={n:c['id'] for n,c in owners.items()},path_field=field,normal_path_field=normal_field,
        source_String_shape=shape,source_String_fields=stringfields,required_classes=sorted(c['id'] for c in owners.values()),
        required_java_methods=[r['method'] for r in java],required_base_modules=['runtime_metadata','properties'],
        required_provider_families=['normal-winnt-filesystem-v1','normal-throwable-v1'],pool_bytes=40,pool_abi=1,
        primitive_source=S.artifact(primitive),primitive_declarations=[list(r) for r in declarations],
        primitive_renames=RENAMES,native_sources=sources,source_fields_accessed_by_native=[field],
        normal_String_factory_kernel=S.artifact(S.ROOT/'native/kernels/java_string_literals.inc'))


def aliases(meta):
    names=meta['source_classes'];path=meta['normal_path_field'];file=names['java/io/File']
    method=lambda owner,name:next(r['method'] for r in meta['original_java'] if r['owner']==owner and r['name']==name)
    error=names['java/io/IOException']
    return dict(WFQ_FS_LAYOUT=f"boom_layout{names[OWNER]}",WFQ_STRING_LAYOUT=f"boom_layout{names['java/lang/String']}",
        WFQ_FILE_LAYOUT=f'boom_layout{file}',WFQ_FILE_CLASS=file,WFQ_PATH_OFFSET=path['offset'],WFQ_PATH_INDEX=path['index'],
        WFQ_LENGTH=f"boom_m{method('java/lang/String','length')}",WFQ_CHARS=f"boom_m{method('java/lang/String','toCharArray')}",
        WFQ_ERROR_CLASS=f'boom_class{error}',WFQ_ERROR_LAYOUT=f'boom_layout{error}',
        WFQ_ERROR_CTOR=f"boom_m{method('java/io/IOException','<init>')}",WFQ_THROWABLE_TYPE=f"boom_t{names['java/lang/Throwable']}")


def native_imports(meta):
    a=aliases(meta);procs={a[n] for n in ('WFQ_LENGTH','WFQ_CHARS','WFQ_ERROR_CTOR')}
    procs|=FOREIGN|{'boom_heap_contains','boom_object_check','boom_object_new','boom_exception_set32',
        'boom_java_property_copy','boom_java_string_literal','boom_trace_enter','boom_trace_leave',
        f"boom_field_map{meta['path_field']['id']}"}
    data={v for v in a.values() if isinstance(v,str)}-procs
    data|={'boom_heap_ptr','boom_runtime_type_map','boom_java_properties_string_pool','boom_trace_pool',
        'boom_provider_winnt_file_pool'}|{f"boom_trace_method{r['method']}" for r in meta['methods']}
    return procs,data


def primitive_body(text):
    text='\n'.join(line for line in text.splitlines() if not(
        line.strip().lower().startswith(('option ','extern ')) or line.strip().upper()=='END'))+'\n'
    for before,after in RENAMES.items():text=re.sub(r'\b'+before+r'\b',after,text)
    return text


def data(meta):
    text=''.join(f'{name} TEXTEQU <{value}>\n' for name,value in aliases(meta).items())
    return text+primitive_body(Path(meta['primitive_source']['path']).read_text())+f'''.const
ALIGN 8
wfq_string_pool DWORD 050524F50h,2,0,0
 QWORD OFFSET boom_heap_ptr,OFFSET boom_java_properties_string_pool,0,0,0
 DWORD 0,0
 QWORD 0,0
 QWORD 0,OFFSET boom_java_property_copy,0,OFFSET boom_java_string_literal
ALIGN 8
PUBLIC {POOL}
{POOL} DWORD 059514657h,1
 QWORD OFFSET boom_heap_ptr,OFFSET boom_provider_winnt_file_pool
 QWORD OFFSET boom_field_map{meta['path_field']['id']},OFFSET wfq_string_pool
'''
