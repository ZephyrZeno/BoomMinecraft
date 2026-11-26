"""Normal builtin NativeLibraries source model; no NIO candidate or fixture roots.

All IDs/offsets come from the supplied verified source plan. Only the original
String/Boolean/error Java callbacks are required; System.setProperties is a test
fixture API and is deliberately excluded from this production provider model.
"""
import hashlib
import importlib.util
import json
from pathlib import Path


OWNER='jdk/internal/loader/NativeLibraries'
IMPL=OWNER+'$NativeLibraryImpl'
POOL='boom_native_library_pool'
SERVICE='boom_native_library_service'
CONTROL={'boom_native_library_modules','boom_native_library_pins','boom_native_library_load_callbacks',
    'boom_native_library_property_reads','boom_builtin_module_pool','boom_builtin_net_pool',
    'boom_builtin_module_check','boom_builtin_nio_body','boom_builtin_nio_on_load'}|{
    'boom_builtin_net_platform_'+name for name in ('start','acquire','release','close')}
FOREIGN={'AcquireSRWLockExclusive','ReleaseSRWLockExclusive','GetCurrentThreadId','GetModuleHandleExW','FreeLibrary',
    'GetLastError','WaitOnAddress','WakeByAddressAll','WSAStartup','WSACleanup','WSAGetLastError','socket','closesocket'}
KERNELS=['classes32.asm','frames.asm','heap.asm','objects.asm','runtime_types.asm','runtime_type_index.asm',
         'types.asm','java_properties.asm','thread_registry.asm','thread_natives.asm']
SPECS=[(OWNER,'findBuiltinLib','(Ljava/lang/String;)Ljava/lang/String;',0x10a),
       (OWNER,'load','(L'+IMPL+';Ljava/lang/String;ZZ)Z',0x10a),
       (OWNER,'unload','(Ljava/lang/String;ZJ)V',0x10a),
       ('jdk/internal/loader/NativeLibrary','findEntry0','(JLjava/lang/String;)J',0x108)]
JAVA=[('java/lang/String','toCharArray','()[C'),('java/lang/Boolean','getBoolean','(Ljava/lang/String;)Z'),
      ('java/lang/InternalError','<init>','(Ljava/lang/String;)V'),
      ('java/lang/UnsatisfiedLinkError','<init>','(Ljava/lang/String;)V'),
      ('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]
PINS={'NativeLibraries.c':'75549e652ada82c64b4199d92f5423287fb59aa20cff382dbd95e432830fe6bf',
      'jni_util.h':'05f7396789edad4d6987a5a223dd0e78ebc5f29d2e3ef03d4694b3d4849fbc5c',
      'nio_util.c':'ea2ef0421238f79036007d3cdb77229c0a77f855590ac5e0ac26ffab0198f7b8',
      'net_util.c':'44a9b56b83f0de78e40f2ac69608b0d991c518c227df7163ca97544c3230926e',
      'net_util_md.c':'8aead522655304fac388b2b5dfef80ffc0472f5a8eee1939f291e166ffe1c1eb'}
HELPER_ASM_SHA256='0a11aebe115ffb65503453fe9c8c1a2f3a3f8bb80bdeba9f02375c85bcb3b284'
POLICY=dict(normal_source_layouts=True,builtin_self_modules=['net','nio'],real_OS_image_pins=True,
    Java_callbacks_outside_SRW=True,source_Boolean_property='java.net.preferIPv4Stack',
    require_actual_source_Thread_attachment=True,static_wrapper_JNI_version=0x10008,
    source_fields_published_after_callback_and_version_check=True,
    external_JNI_libraries=False,standard_JNI_function_addresses=False,
    ASCII_platform_names_and_NUL_prefix=True,non_ASCII_names_explicitly_blocked=True,
    nonmoving_heap=True,collection_requires_quiescence=True,original_locked_no_transforms=True)


def helpers_module(S):
    return S.module('independent_native_library_helper_templates','native-library-helpers-source.py')


def index(summary,classes,S):
    I=S.module('native_library_model_classfile','verify-translation-ir.py')
    F=S.module('native_library_model_field_layout','file-bootstrap-source.py')
    wanted={s[0] for s in SPECS+JAVA}|{IMPL,'java/lang/System','java/lang/Throwable','java/lang/Thread','java/lang/BaseVirtualThread'}
    owners={c['name']:c for c in classes if c['origin']['loader']=='bootstrap' and c['name'] in wanted}
    S.check(set(owners)==wanted,'Original builtin library classes are missing')
    members={}
    for name,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Original java.base class required')
        raw=I.Source(S.original_class(summary,c))
        S.check(raw.name==name and len(raw.methods)==len(c['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==c['fields'],'Original library class inventory differs')
        for ident,m in zip(c['method_ids'],raw.methods):
            key=name,m['name'],m['descriptor']
            if key not in JAVA and key not in [s[:3] for s in SPECS]:
                continue
            code=raw.code(m)
            members[key]=dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',
                source_id='jdk:java.base',owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],
                code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None)
    methods=[]
    for op,(*key,flags) in enumerate(SPECS):
        row=dict(members[tuple(key)])
        S.check(row['access']==flags and row.pop('code_sha256') is None,'Original library native declaration changed')
        methods.append(dict(**row,operation=op))
    java=[members[key] for key in JAVA]
    S.check(all(m['code_sha256'] for m in java),'Original library Java callback Code is missing')
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layout=next(r for line in stream if (r:=json.loads(line))['class_id']==owners[IMPL]['id'])
    fields=F.fields(owners[IMPL],layout,[('handle','J',0,8,False),('jniVersion','I',0,4,False)],S)
    [props]=[i for i,f in enumerate(owners['java/lang/System']['fields']) if
             (f['name'],f['descriptor'],f['access'])==('props','Ljava/util/Properties;',0xa)]
    pinned=S.ART/'native-library-lifecycle/pinned-sources/jdk-21.0.13+3'
    sources={name:S.artifact(pinned/name) for name in PINS}
    S.check(all(r['digest']['sha256']==PINS[n] for n,r in sources.items()),'Pinned native load protocol source differs')
    helper=S.ROOT/'scripts/native-library-helpers-source.py'
    helper_hash=hashlib.sha256(helpers_module(S).helpers().encode()).hexdigest()
    S.check(helper_hash==HELPER_ASM_SHA256,'Independent ASM helper template differs from the executed lifecycle kernel')
    embedded=['builtin_net_platform.asm.inc','builtin_module_context.asm.inc']
    return dict(schema=1,owner=owners[OWNER]['id'],methods=methods,original_java=java,fields=fields,
        source_classes={name:c['id'] for name,c in owners.items()},system_props_index=props,
        thread_class=owners['java/lang/Thread']['id'],virtual_base_class=owners['java/lang/BaseVirtualThread']['id'],
        required_classes=sorted(c['id'] for c in owners.values()),required_java_methods=[m['method'] for m in java],
        required_base_modules=['runtime_metadata','properties'],
        required_provider_families=['normal-thread-primitives-v1','normal-throwable-v1'],
        pool_bytes=32,pool_abi=1,native_sources=sources,
        embedded_kernels={name:S.artifact(S.ROOT/'native/providers'/name) for name in embedded},
        helper_generator=S.artifact(helper),helper_ASM_sha256=helper_hash,
        property_API_fixture_included=False,standard_JNI_environment_exposed=False)


def aliases(meta):
    names=meta['source_classes']
    method=lambda owner,name:next(m['method'] for m in meta['original_java'] if m['owner']==owner and m['name']==name)
    return {'NLL_IMPL_CLASS':f"boom_class{names[IMPL]}",'NLL_IMPL_LAYOUT':f"boom_layout{names[IMPL]}",
        'NLL_STRING_LAYOUT':f"boom_layout{names['java/lang/String']}",
        'NLL_STRING_CHARS':f"boom_m{method('java/lang/String','toCharArray')}",
        'NLL_INTERNAL_CLASS':f"boom_class{names['java/lang/InternalError']}",
        'NLL_INTERNAL_LAYOUT':f"boom_layout{names['java/lang/InternalError']}",
        'NLL_INTERNAL_CTOR':f"boom_m{method('java/lang/InternalError','<init>')}",
        'NLL_UNSAT_CLASS':f"boom_class{names['java/lang/UnsatisfiedLinkError']}",
        'NLL_UNSAT_LAYOUT':f"boom_layout{names['java/lang/UnsatisfiedLinkError']}",
        'NLL_UNSAT_CTOR':f"boom_m{method('java/lang/UnsatisfiedLinkError','<init>')}",
        'NLL_THROWABLE_TYPE':f"boom_t{names['java/lang/Throwable']}",
        'NLL_BOOLEAN_GET':f"boom_m{method('java/lang/Boolean','getBoolean')}",
        'NLL_SYSTEM_PROPS':f"boom_s{names['java/lang/System']}_{meta['system_props_index']}"}


def native_imports(meta):
    a=aliases(meta)
    procs={a[k] for k in ('NLL_STRING_CHARS','NLL_INTERNAL_CTOR','NLL_UNSAT_CTOR','NLL_BOOLEAN_GET')}
    procs|=FOREIGN|{'boom_heap_contains','boom_object_check','boom_object_new','boom_class_ensure32','boom_exception_set32',
        'boom_java_property_copy','boom_trace_enter','boom_trace_leave','boom_threads_current','boom_runtime_type','boom_type_assignable'}
    data=set(a.values())-procs
    data|={'boom_heap_ptr','boom_runtime_type_map','boom_java_platform_properties_pool','boom_provider_thread_registry',
           'boom_trace_pool',f"boom_t{meta['thread_class']}",f"boom_t{meta['virtual_base_class']}"}
    data|={f"boom_trace_method{m['method']}" for m in meta['methods']}
    # Declaring classes/ensure are supplied by the common source adapter prefix.
    procs.discard('boom_class_ensure32')
    return procs,data


def data(meta):
    a=aliases(meta)
    text=''.join(f'{name} TEXTEQU <{value}>\n' for name,value in a.items())
    fields={f['name']:f['offset'] for f in meta['fields']}
    text+=f"NLL_HANDLE_OFFSET EQU {fields['handle']}\nNLL_VERSION_OFFSET EQU {fields['jniVersion']}\n"
    # These are already executed MASM helpers, embedded without source edits.
    for name in ('builtin_net_platform.asm.inc','builtin_module_context.asm.inc'):
        record=meta['embedded_kernels'][name]
        text+=Path(record['path']).read_text()+'\n'
    path=Path(meta['helper_generator']['path'])
    definition=importlib.util.spec_from_file_location('formal_native_library_helpers',path)
    helper=importlib.util.module_from_spec(definition)
    definition.loader.exec_module(helper)
    text+=helper.helpers()+f'''
.const
ALIGN 8
PUBLIC boom_builtin_module_pool
boom_builtin_module_pool DWORD 043424D56h,1
 QWORD OFFSET boom_heap_ptr,OFFSET boom_provider_thread_registry,OFFSET boom_runtime_type_map
 QWORD OFFSET boom_t{meta['thread_class']},OFFSET boom_t{meta['virtual_base_class']}
.data
ALIGN 8
PUBLIC boom_builtin_net_pool
boom_builtin_net_pool DWORD 04D54454Eh,2
 QWORD 0
 DWORD 0,0,0,0,0,0,0,0
 QWORD 0,0,0
 DWORD 0,0
PUBLIC boom_native_library_pins
boom_native_library_pins QWORD 0
PUBLIC boom_native_library_load_callbacks
boom_native_library_load_callbacks QWORD 0
PUBLIC boom_native_library_property_reads
boom_native_library_property_reads QWORD 0
PUBLIC boom_native_library_modules
boom_native_library_modules DWORD 0444F4D42h,1,1,0
 QWORD 0
 DWORD 0,0
 QWORD OFFSET lib_net_on_load,OFFSET lib_net_close,OFFSET boom_builtin_net_pool,0
 DWORD 0444F4D42h,1,2,0
 QWORD 0
 DWORD 0,0
 QWORD OFFSET lib_nio_on_load,OFFSET lib_nio_close,OFFSET boom_builtin_module_pool,0
PUBLIC {POOL}
{POOL} DWORD 042494C4Eh,1,2,64
 QWORD OFFSET boom_native_library_modules,0
'''
    return text
