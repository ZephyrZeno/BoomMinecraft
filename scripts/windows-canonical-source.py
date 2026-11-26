"""Original Windows canonicalize0/getDriveDirectory source, String and error ABI."""
import hashlib
import json
from pathlib import Path
import re


OWNER='java/io/WinNTFileSystem'
POOL='boom_provider_windows_canonical_pool'
SERVICE='boom_provider_windows_canonical_service'
CONTROL={'boom_windows_canonical_owned_buffers','boom_windows_canonical_path','boom_windows_drive_directory'}
FOREIGN={'GetProcessHeap','HeapAlloc','HeapFree','FormatMessageW','GetFullPathNameW','GetCurrentDirectoryW',
         'GetDriveTypeW','FindFirstFileW','FindClose','GetLastError'}
KERNELS=['classes32.asm','frames.asm','heap.asm','objects.asm','java_properties.asm',
         'runtime_types.asm','runtime_type_index.asm','types.asm']
SPECS=[(OWNER,'canonicalize0','(Ljava/lang/String;)Ljava/lang/String;',0),
       (OWNER,'getDriveDirectory','(I)Ljava/lang/String;',1)]
JAVA=[('java/lang/String','length','()I'),('java/lang/String','toCharArray','()[C'),
      ('java/io/IOException','<init>','(Ljava/lang/String;)V'),
      ('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]
PINS={'WinNTFileSystem_md.c':'0a8dbaa9872c434b5405ae698bd7777561fe73ab24adaa1eef19169e72e7682e',
      'canonicalize_md.c':'ea886e568ae007302f31447b9c1910eb87e77191c41df3ccf7a7732fc0bc9996',
      'io_util_md.c':'f3630be207d35aafdd60edb8c8db0ed23e84d7092f374138cee27761a6bfdaa7',
      'io_util_md.h':'94b8e577df754524fe61dc2672bd1ed19f634defbe87afe3a05116a624ac074f',
      'WinNTFileSystem.java':'578a582b3071e6cc3a218438846d0e4398913ccbe40e0e87b563a35dad50ab9d',
      'jni_util.c':'31596047469d6107b1e515eb04f3e9a9d98719ba50d2d9d753309eef51b2ce94',
      'jni_util_md.c':'7a7adff4a3631fa5476d1f1dc54260ea0fccc535bbb149fb72fee21ac59d38a5',
      'io_util.h':'ff1c363e3edecb164d2f7112dbb33996d2a1221f337264308546c57780a3a5c3'}
POLICY=dict(normal_source_layouts=True,source_String_callbacks=True,source_IOException_String_constructor=True,
    source_Throwable_wrapper_required=True,primitive_capacity_includes_NUL=True,primitive_max_effective_units=32767,
    first_embedded_NUL_terminates_native_path=True,drive_result_excludes_ASCII_drive_prefix=True,
    unavailable_drive_returns_null=True,error_message_FormatMessageW_units=256,
    error_message_trim_order=['LF','CR','ASCII_period'],logical_failure_default='Bad pathname',
    logical_failure_reuses_cross_call_GetLastError_history=False,
    complete_JNI_error_message_sequence_compatibility=False,
    primitive_native_allocation_failure_context=3,wrapper_native_allocation_failure_context=3,
    exact_original_all_malloc_site_OOM_behavior_proven=False,nonmoving_heap=True,
    collection_requires_quiescence=True,symlinks_resolved_to_target=False,external_JNI_environment=False,
    source_transform_chain='original_locked_no_transforms')


def index(summary,classes,S):
    I=S.module('windows_canonical_original_class','verify-translation-ir.py')
    F=S.module('windows_canonical_normal_fields','file-bootstrap-source.py')
    wanted={OWNER,'java/lang/String','java/io/IOException','java/lang/Throwable'}
    owners={c['name']:c for c in classes if c['name'] in wanted and c['origin']['loader']=='bootstrap'}
    S.check(set(owners)==wanted,'Original Windows canonical classes are missing')
    members={}
    for name,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),
            'Windows canonicalization requires original java.base classes')
        raw=I.Source(S.original_class(summary,c))
        S.check(raw.name==name and len(raw.methods)==len(c['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==c['fields'],
            'Original canonical class method/field inventory differs')
        if name==OWNER:
            S.check(not any(m['name']=='canonicalizeWithPrefix0' for m in raw.methods),
                'Obsolete C prefix symbol must not be registered without a current classfile declaration')
        for ident,m in zip(c['method_ids'],raw.methods):
            key=name,m['name'],m['descriptor']
            if key not in JAVA and key not in [row[:3] for row in SPECS] and key!=(OWNER,'canonicalize','(Ljava/lang/String;)Ljava/lang/String;'):
                continue
            code=raw.code(m)
            members[key]=dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',
                source_id='jdk:java.base',owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],
                code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None)
    methods=[]
    for name,method,descriptor,operation in SPECS:
        row=dict(members[name,method,descriptor])
        S.check(row['access']==0x102 and row.pop('code_sha256') is None,'Original private canonical native declaration changed')
        methods.append(dict(**row,operation=operation))
    java=[members[key] for key in JAVA]
    S.check(all(row['code_sha256'] for row in java),'Original canonical Java callback Code is unavailable')
    string=owners['java/lang/String']
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layouts={row['class_id']:row for line in stream if (row:=json.loads(line))['class_id'] in {c['id'] for c in owners.values()}}
    fields=F.fields(string,layouts[string['id']],[('value','[B',0x12,8,True),('coder','B',0x12,1,False),
        ('hash','I',2,4,False),('hashIsZero','Z',2,1,False)],S)
    shape=summary['string_literals']['source_layout']
    mapping={'value':'value_offset','coder':'coder_offset','hash':'hash_offset','hashIsZero':'hash_is_zero_offset'}
    S.check(shape['class_id']==string['id'] and shape['source_sha256']==string['origin']['sha256'] and
        all(shape[mapping[row['name']]]==row['offset'] for row in fields) and summary['properties']['pool_abi']==2,
        'Canonical factory must use the original normal String shape')
    pinned=S.ART/'windows-path-canonicalization/pinned-sources/jdk-21.0.13+3'
    sources={name:S.artifact(pinned/name) for name in PINS}
    S.check(all(row['digest']['sha256']==PINS[name] for name,row in sources.items()),'Pinned canonical native source changed')
    primitive=S.ROOT/'native/runtime/windows_canonical_path.asm'
    declarations=re.findall(r'(?im)^\s*EXTERN\s+(\w+)\s*:\s*(PROC|BYTE)\s*$',primitive.read_text())
    S.check(declarations and all(name in FOREIGN for name,_ in declarations),'Canonical primitive WinAPI imports differ')
    return dict(schema=1,owner=owners[OWNER]['id'],methods=methods,original_java=java,
        original_Java_canonicalize=members[OWNER,'canonicalize','(Ljava/lang/String;)Ljava/lang/String;'],
        source_classes={name:c['id'] for name,c in owners.items()},source_String_fields=fields,source_String_shape=shape,
        required_classes=sorted(c['id'] for c in owners.values()),required_java_methods=[row['method'] for row in java],
        required_base_modules=['runtime_metadata','properties'],
        required_provider_families=['normal-winnt-filesystem-v1','normal-throwable-v1'],
        pool_bytes=112,pool_abi=2,native_sources=sources,source_fields_accessed_by_native=[],
        normal_String_factory_kernel=S.artifact(S.ROOT/'native/kernels/java_string_literals.inc'),
        primitive_source=S.artifact(primitive),primitive_declarations=[list(row) for row in declarations],
        primitive_exports=['boom_windows_canonical_path','boom_windows_drive_directory'],
        primitive_runtime572_modified=False,obsolete_prefix_native_registered=False)


def aliases(meta):
    names=meta['source_classes']
    method=lambda owner,name:next(row['method'] for row in meta['original_java'] if row['owner']==owner and row['name']==name)
    error=names['java/io/IOException']
    return dict(WCAN_FS_LAYOUT=f"boom_layout{names[OWNER]}",WCAN_STRING_LAYOUT=f"boom_layout{names['java/lang/String']}",
        WCAN_LENGTH=f"boom_m{method('java/lang/String','length')}",WCAN_CHARS=f"boom_m{method('java/lang/String','toCharArray')}",
        WCAN_ERROR_CLASS=f'boom_class{error}',WCAN_ERROR_LAYOUT=f'boom_layout{error}',
        WCAN_ERROR_CTOR=f"boom_m{method('java/io/IOException','<init>')}",
        WCAN_THROWABLE_TYPE=f"boom_t{names['java/lang/Throwable']}")


def native_imports(meta):
    a=aliases(meta)
    procs={a[name] for name in ('WCAN_LENGTH','WCAN_CHARS','WCAN_ERROR_CTOR')}
    procs|=FOREIGN|{'boom_heap_contains','boom_object_check','boom_object_new',
        'boom_exception_set32','boom_java_property_copy','boom_java_string_literal','boom_trace_enter','boom_trace_leave'}
    data=set(a.values())-procs
    data|={'boom_heap_ptr','boom_runtime_type_map','boom_java_properties_string_pool','boom_trace_pool'}
    data|={f"boom_trace_method{row['method']}" for row in meta['methods']}
    return procs,data


def data(meta):
    text=''.join(f'{name} TEXTEQU <{value}>\n' for name,value in aliases(meta).items())
    return text+primitive_body(Path(meta['primitive_source']['path']).read_text())+f'''.const
ALIGN 8
PUBLIC {POOL}
{POOL} DWORD 050524F50h,2,0,0
 QWORD OFFSET boom_heap_ptr,OFFSET boom_java_properties_string_pool,0,0,0
 DWORD 0,0
 QWORD 0,0
 QWORD 0,OFFSET boom_java_property_copy,0,OFFSET boom_java_string_literal
'''


def primitive_body(text):
    # Remove only standalone assembler declarations/envelope. Every actual
    # instruction, constant, data definition and private label stays verbatim.
    return '\n'.join(line for line in text.splitlines() if not (
        line.strip().lower().startswith(('option ','extern ')) or line.strip().upper()=='END'))+'\n'
