"""Independent self-jimage variant of the original net/nio library provider.

The old helpers, pool, two modules and lifecycle kernel remain verbatim. Only
the four source adapter tail jumps change; a separate dispatcher and one-module
lifecycle handle jimage. No standard JNI pointer or external DLL is provided.
"""
import hashlib
import importlib.util
import json
from pathlib import Path


def module(name):
    spec=importlib.util.spec_from_file_location('jimage_library_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


N=module('native-library-source')
POOL=N.POOL
SERVICE='boom_native_library_with_jimage_service'
CONTROL=N.CONTROL|{N.SERVICE,'boom_jimage_native_library_service','boom_jimage_library_pool','boom_jimage_library_module'}
FOREIGN=N.FOREIGN
KERNELS=N.KERNELS
ORIGINAL_KERNEL=Path(__file__).resolve().parents[1]/'native/providers/native_library_lifecycle.asm.inc'
POLICY=dict(N.POLICY,builtin_self_modules=['net','nio','jimage'],
    original_net_nio_kernel_and_helpers_unchanged=True,only_original_adapter_tail_targets_changed=True,
    real_jimage_owner_initialized_before_library_publication=True,
    jimage_onload='internal_attached_thread_and_real_map_bridge_readiness_check_then_1_8',
    original_C_jimage_JNI_OnLoad_function_not_claimed=True,
    jimage_module_unload_does_not_close_VM_image_mapping_owner=True,
    jimage_mapping_opened_by_getNativeMap=False,
    System_loadLibrary_error_rules_not_BootLoader_POP_rules=True,
    standard_findEntry0_jimage_addresses=False,
    mapped_name_last_four_ASCII_units_stripped_without_suffix_content_check=True,
    source_transform_chain='original_locked_no_transforms')


def index(summary,classes,S):
    base=N.index(summary,classes,S)
    F=S.module('jimage_library_original_String_fields','file-bootstrap-source.py')
    string=next(c for c in classes if c['id']==base['source_classes']['java/lang/String'])
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layout=next(row for line in stream if (row:=json.loads(line))['class_id']==string['id'])
    fields=F.fields(string,layout,[('value','[B',0x12,8,True),('coder','B',0x12,1,False),
        ('hash','I',2,4,False),('hashIsZero','Z',2,1,False)],S)
    shape=summary['string_literals']['source_layout']
    S.check(shape['class_id']==string['id'] and shape['source_sha256']==string['origin']['sha256'] and
        shape['value_offset']==fields[0]['offset'] and shape['coder_offset']==fields[1]['offset'],
        'Jimage classifier must read the exact source String shape')
    old_data=N.data(base)
    return dict(schema=1,owner=base['owner'],methods=base['methods'],original_java=base['original_java'],
        fields=base['fields'],source_classes=base['source_classes'],base_source=base,
        source_String_fields=fields,source_String_shape=shape,runtime_byte_array_tag=256+8,
        required_classes=base['required_classes'],required_java_methods=base['required_java_methods'],
        required_base_modules=base['required_base_modules'],
        required_provider_families=base['required_provider_families'],native_root_spans=[],
        replaces_existing_provider='normal-native-libraries-v1',
        separately_registered_provider=False,requires_real_jimage_bridge=True,
        original_kernel=S.artifact(ORIGINAL_KERNEL),original_source_model=S.artifact(Path(N.__file__)),
        original_data_ASM_sha256=hashlib.sha256(old_data.encode()).hexdigest(),
        jimage_module_kind=3,jimage_module_stride=64,jimage_pool_bytes=32)


def native_imports(meta):
    proc,data=N.native_imports(meta['base_source'])
    return proc|{'boom_jimage_native_map_ready'},data|{'boom_provider_jimage_native_map_pool'}


def data(meta):
    # No actual instruction or byte of the old data precedes a new definition.
    fields={row['name']:row['offset'] for row in meta['source_String_fields']}
    return N.data(meta['base_source'])+f"JLIB_STRING_VALUE EQU {fields['value']}\nJLIB_STRING_CODER EQU {fields['coder']}\n"


def lifecycle_variant(text):
    start='boom_native_library_service PROC FRAME\n';end='boom_native_library_service ENDP'
    if text.count(start)!=1 or text.count(end)!=1:raise ValueError('Original library service envelope changed')
    body=text[text.index(start):text.index(end)+len(end)]
    changes=[('boom_native_library_service','boom_jimage_native_library_service'),
        ('nll_','jll_'),('cmp DWORD PTR [rdi+8],2','cmp DWORD PTR [rdi+8],1'),
        ('mov ecx,2','mov ecx,1'),('mov r8d,3','mov r8d,6'),('mov r8d,7','mov r8d,10'),
        ('call lib_source_name','call jlib_source_name'),('call lib_new_module_name','call jlib_new_module_name'),
        ('call lib_raise_bad_version','call jlib_raise_bad_version')]
    expected=[2,None,1,1,2,1,3,1,1]
    for (old,new),count in zip(changes,expected):
        if count is not None and body.count(old)!=count:raise ValueError('Original lifecycle instruction inventory changed: '+old)
        body=body.replace(old,new)
    return body+'\n'


def extension(meta):
    return '''.const
jlib_name WORD 106,105,109,97,103,101,46,100,108,108
.data
ALIGN 8
PUBLIC boom_jimage_library_module
boom_jimage_library_module DWORD 0444F4D42h,1,3,0
 QWORD 0
 DWORD 0,0
 QWORD OFFSET jlib_on_load,OFFSET jlib_on_close,0,0
PUBLIC boom_jimage_library_pool
boom_jimage_library_pool DWORD 042494C4Eh,1,1,64
 QWORD OFFSET boom_jimage_library_module,0
.code
PUBLIC boom_jimage_native_library_service
'''+lifecycle_variant(ORIGINAL_KERNEL.read_text(encoding='utf-8'))
