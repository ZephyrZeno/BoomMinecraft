"""Original NativeImageBuffer lookup and JNI long/long buffer construction."""
import hashlib
import importlib.util
from pathlib import Path


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


I=module('jimage_original_classfile','verify-translation-ir.py')
C=module('jimage_original_runtime_types','constructor-provider-source.py')
OWNER='jdk/internal/jimage/NativeImageBuffer'
DIRECT='java/nio/DirectByteBuffer'
POOL='boom_provider_jimage_native_map_pool'
SERVICE='boom_provider_jimage_native_map_service'
CONTROL={'boom_jimage_native_map_open','boom_jimage_native_map_close','boom_jimage_native_map_ready'}
FOREIGN={'AcquireSRWLockExclusive','ReleaseSRWLockExclusive','GetProcessHeap','HeapAlloc','HeapFree'}
KERNELS=['classes32.asm','frames.asm','heap.asm','objects.asm']
JAVA=[('java/lang/String','toCharArray','()[C'),(DIRECT,'<init>','(JJ)V')]
PINS={'NativeImageBuffer.cpp':'31eed6d4d7e45595c883a239d6cc228709ac59cb6dfe11010b60de7ddbfd03cb',
      'imageFile.cpp':'1484ea4c11a226cb8b795d4a36ce797bf1e9496c3d7f26b34f3c1cdb489a03f2',
      'imageFile.hpp':'dec917541c8cb7f112a6b230b44633c0a4367ab728f5ebce47f6644327d8b44f',
      'jni.cpp':'49f0d0c7507c23afa7c3cdf56a4c5ee0d5e5bd18e9e52fd98376d54ea52544b3'}
OWNER_KERNEL_SHA256='a11b4253485a1463a4d737174fe49bdc4357a6047111798d5f05833580716635'
POLICY=dict(original_owner_initializer_before_native_body=True,original_System_loadLibrary_not_bypassed=True,
    native_lookup_only=True,native_call_opens_or_creates_mapping=False,
    lookup_miss='normal_null_then_original_BasicImageReader_FileChannel_fallback',
    lookup_hit='original_private_DirectByteBuffer_JJ_constructor',
    capacity_checked_by='original_DirectByteBuffer_checkCapacity_long',
    path_key='exact_original_UTF16_units_for_owner_names_from_same_Java_source',
    source_C_comparison='JNI_modified_UTF8_then_byte_exact_strcmp',
    no_case_or_path_normalization=True,shared_view_requires_real_validated_JIMAGE_owner=True,
    returned_buffer_lease_lives_until_controlled_VM_shutdown=True,
    failed_Java_constructor_releases_only_new_lookup_lease=True,
    retained_lease_directory_contains_Java_oops=False,
    explicit_owner_binding_required_before_source_library_load=True,
    native_directory_close_requires_all_Java_heap_view_users_finished=True,
    embedded_UTF16_NUL_lookup='miss_because_no_real_Win32_owner_key_can_contain_NUL',
    empty_or_over_32767_UTF16_query='miss_because_real_owner_keys_require_1_to_32767_units',
    map_owner_ABI_binding_pending=False,standard_JNI_environment_exposed=False,
    no_C_decoder_or_external_JDK_library=True,nonmoving_heap=True,automatic_GC=False,
    source_transform_chain='original_locked_no_transforms')


def index(summary,classes,S):
    names={(row['origin']['loader'],row['name']):row for row in classes}
    wanted={name:names['bootstrap',name] for name in (OWNER,OWNER+'$1',DIRECT,'java/nio/MappedByteBuffer',
        'java/nio/ByteBuffer','java/nio/Buffer','sun/nio/ch/DirectBuffer','java/lang/String')}
    native=None;java=[];initializers=[];source=C.RawClasses(summary)
    try:
        for name,cls in wanted.items():
            S.check(cls['origin']['source_id']=='jdk:java.base' and not cls['origin'].get('generated'),
                'Original java.base image/buffer class required')
            raw=I.Source(source.read(cls))
            S.check(raw.name==name and len(raw.methods)==len(cls['method_ids']),'Original image/buffer source inventory differs')
            for ident,method in zip(cls['method_ids'],raw.methods):
                key=name,method['name'],method['descriptor'];code=raw.code(method)
                row=dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],loader='bootstrap',
                    source_id='jdk:java.base',owner=name,name=method['name'],descriptor=method['descriptor'],access=method['access'])
                if name==OWNER and method['name']=='getNativeMap':
                    S.check(method['descriptor']=='(Ljava/lang/String;)Ljava/nio/ByteBuffer;' and
                        method['access']==0x108 and code is None and native is None,'Original getNativeMap native declaration differs')
                    native=dict(row,operation=0)
                elif key in JAVA or (name==DIRECT and method['name']=='checkCapacity' and method['descriptor']=='(J)I'):
                    S.check(code is not None,'Original JNI buffer constructor/helper Code missing')
                    if key==(DIRECT,'<init>','(JJ)V'):S.check(method['access']==2,'Original JNI direct buffer constructor is private')
                    java.append(dict(row,code_sha256=hashlib.sha256(code['bytes']).hexdigest()))
                elif name in (OWNER,OWNER+'$1') and method['name'] in ('<clinit>','run'):
                    S.check(code is not None,'Original image library initializer/action Code missing')
                    initializers.append(dict(row,code_sha256=hashlib.sha256(code['bytes']).hexdigest()))
    finally:source.close()
    S.check(native is not None and {key for key in JAVA}<={(r['owner'],r['name'],r['descriptor']) for r in java},
        'Original image native/Java callback inventory incomplete')
    fields={};wanted_ids={row['id'] for row in wanted.values()}
    import json
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layouts={row['class_id']:row for line in stream if (row:=json.loads(line))['class_id'] in wanted_ids}
    direct=layouts[wanted[DIRECT]['id']]
    S.check(direct['diagnostic'] is None and direct['candidate'] is not None and
        direct['source_sha256']==wanted[DIRECT]['origin']['sha256'],'Original direct-buffer normal layout missing')
    string=layouts[wanted['java/lang/String']['id']]
    S.check(string['diagnostic'] is None and string['candidate'] is not None and
        string['source_sha256']==wanted['java/lang/String']['origin']['sha256'],
        'Original source String normal layout missing')
    specs=[('java/nio/Buffer','address','J',8,False),('java/nio/Buffer','capacity','I',4,False),
        ('java/nio/Buffer','position','I',4,False),('java/nio/Buffer','limit','I',4,False),
        (DIRECT,'att','Ljava/lang/Object;',8,True),(DIRECT,'cleaner','Ljdk/internal/ref/Cleaner;',8,True)]
    for owner,name,descriptor,width,reference in specs:
        owner_id=wanted[owner]['id']
        rows=[row for row in direct['candidate']['fields'] if row['member']['owner']==owner_id and
            row['member']['name']==name and row['member']['descriptor']==descriptor]
        S.check(len(rows)==1 and rows[0]['storage_bytes']==width and rows[0]['reference'] is reference,
            'Original direct-buffer inherited FMAP field differs: '+name)
        fields[name]=rows[0]
    directory=S.ART/'jimage-native-map/pinned-sources/jdk-21.0.13+3'
    pins={name:S.artifact(directory/name) for name in PINS}
    S.check(all(pins[name]['digest']['sha256']==sha for name,sha in PINS.items()),'Pinned JNI/JIMAGE source changed')
    jni=(directory/'jni.cpp').read_text(encoding='utf-8')
    S.check(jni.count('env->GetMethodID(directByteBufferClass, "<init>", "(JJ)V")')==1,
        'Locked JNI NewDirectByteBuffer must use the original long/long constructor')
    owner_kernel=S.artifact(S.ROOT/'native/kernels/jimage_owner64.asm.inc')
    S.check(owner_kernel['digest']['sha256']==OWNER_KERNEL_SHA256,'Frozen actual JIMAGE owner kernel changed')
    return dict(schema=1,owner=wanted[OWNER]['id'],methods=[native],original_java=sorted(java,key=lambda row:row['method']),
        owner_initializer_source=initializers,normal_direct_layout=direct['candidate'],normal_direct_fields=fields,
        normal_String_layout=string['candidate'],
        source_classes={name:row['id'] for name,row in wanted.items()},native_sources=pins,
        required_classes=sorted(wanted_ids),required_java_methods=sorted(row['method'] for row in java if
            (row['owner'],row['name'],row['descriptor']) in JAVA),required_provider_families=[],
        required_base_modules=['class_literals','runtime_metadata'],native_root_spans=[],
        owned_native_buffer_lease_directory_required=True,map_owner_ABI_defined=True,
        map_owner_kernel=owner_kernel,map_owner_magic=0x3130474D494A4F42,map_owner_state_offset=24,
        bridge_pool_bytes=80,bridge_node_bytes=96,
        source_only=True,assembled=False,linked=False,executed=False,game_started=False)


def aliases(meta):
    names=meta['source_classes']
    method=lambda owner,name,desc:next(row['method'] for row in meta['original_java'] if
        (row['owner'],row['name'],row['descriptor'])==(owner,name,desc))
    return dict(JMAP_STRING_LAYOUT=f"boom_layout{names['java/lang/String']}",
        JMAP_STRING_CHARS=f"boom_m{method('java/lang/String','toCharArray','()[C')}",
        JMAP_DIRECT_CLASS=f"boom_class{names[DIRECT]}",JMAP_DIRECT_LAYOUT=f"boom_layout{names[DIRECT]}",
        JMAP_DIRECT_CTOR=f"boom_m{method(DIRECT,'<init>','(JJ)V')}")


def native_imports(meta):
    a=aliases(meta)
    procs=FOREIGN|{'boom_jimage_owner_lookup','boom_jimage_owner_release','boom_heap_contains',
        'boom_object_check','boom_object_new','boom_class_ensure32','boom_trace_enter','boom_trace_leave',
        a['JMAP_STRING_CHARS'],a['JMAP_DIRECT_CTOR']}
    data=(set(a.values())-procs)|{'boom_heap_ptr','boom_trace_pool'}
    data|={f"boom_trace_method{row['method']}" for row in meta['methods']}
    return procs,data


def data(meta):
    return ''.join(f'{name} TEXTEQU <{value}>\n' for name,value in aliases(meta).items())+f'''.data
ALIGN 8
PUBLIC {POOL}
{POOL} DWORD 050414D4Ah,1
 QWORD 0,0
 DWORD 0,0
 QWORD 0,0,0,0,0,0
'''
