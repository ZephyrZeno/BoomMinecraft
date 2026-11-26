"""Independent Windows System.mapLibraryName source model and String factory pool."""
import hashlib
import json


OWNER='java/lang/System'
POOL='boom_provider_library_name_pool'
SERVICE='boom_provider_library_name_service'
CONTROL=set()
FOREIGN=set()
KERNELS=['heap.asm','objects.asm','classes32.asm','frames.asm','java_properties.asm',
         'runtime_types.asm','runtime_type_index.asm','types.asm']
JAVA=[('java/lang/String','length','()I'),('java/lang/String','toCharArray','()[C'),
      ('java/lang/IllegalArgumentException','<init>','(Ljava/lang/String;)V'),
      ('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]
POLICY=dict(normal_source_layouts=True,platform='Windows',input_length_unit='UTF16_code_units',
    maximum_input_units=240,suffix_UTF16=[46,100,108,108],embedded_NUL_preserved=True,
    unpaired_surrogates_preserved=True,new_String_result=True,
    long_name_exception='java/lang/IllegalArgumentException',long_name_message='name too long',
    source_String_callbacks=True,shared_source_String_factory_metadata=True,
    heap_nonmoving=True,collection_requires_quiescence=True,existing_exception_preserved=True,
    NIO_dispatcher_dependency=False,owned_native_buffer_dependency=False,
    source_transform_chain='original_locked_no_transforms')


def normalized_kernel(text,original=False):
    text=text.replace('boom_win32_library_name' if original else SERVICE,'LIBRARY_NAME_SERVICE')
    text=text.replace('map_name_' if original else 'mln_','library_name_')
    text=text.replace('LIB_NAME_' if original else 'MLN_','SOURCE_')
    return '\n'.join(line.split(';',1)[0].strip() for line in text.splitlines() if line.split(';',1)[0].strip())


def index(summary,classes,S):
    I=S.module('map_library_original_class','verify-translation-ir.py')
    F=S.module('map_library_source_fields','file-bootstrap-source.py')
    names={OWNER,'java/lang/String','java/lang/IllegalArgumentException','java/lang/Throwable'}
    owners={c['name']:c for c in classes if c['name'] in names and c['origin']['loader']=='bootstrap'}
    S.check(set(owners)==names,'Original mapLibraryName classes are missing')
    members={}
    target=OWNER,'mapLibraryName','(Ljava/lang/String;)Ljava/lang/String;'
    for name,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),
                'mapLibraryName requires original java.base classes')
        raw=I.Source(S.original_class(summary,c))
        S.check(raw.name==name and len(raw.methods)==len(c['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==c['fields'],
            'Original mapLibraryName class method/field inventory differs')
        for ident,m in zip(c['method_ids'],raw.methods):
            key=name,m['name'],m['descriptor']
            if key not in JAVA and key!=target:
                continue
            code=raw.code(m)
            members[key]=dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',
                source_id='jdk:java.base',owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],
                code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None)
    native=dict(members[target])
    S.check(native['access']==0x109 and native.pop('code_sha256') is None,
            'Original public static mapLibraryName native declaration changed')
    java=[members[key] for key in JAVA]
    S.check(all(m['code_sha256'] for m in java),'Original library-name Java callback Code is missing')
    string=owners['java/lang/String']
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        [layout]=[r for line in stream if (r:=json.loads(line))['class_id']==string['id']]
    fields=F.fields(string,layout,[('value','[B',0x12,8,True),('coder','B',0x12,1,False),
        ('hash','I',2,4,False),('hashIsZero','Z',2,1,False)],S)
    shape=summary['string_literals']['source_layout']
    mapping={'value':'value_offset','coder':'coder_offset','hash':'hash_offset','hashIsZero':'hash_is_zero_offset'}
    S.check(shape['class_id']==string['id'] and shape['source_sha256']==string['origin']['sha256'] and
        shape['payload_bytes']==layout['candidate']['payload_bytes'] and
        shape['reference_prefix']==layout['candidate']['reference_prefix'] and
        all(shape[mapping[f['name']]]==f['offset'] for f in fields) and
        (summary['properties']['abi'],summary['properties']['pool_abi'])==(1,2),
        'Library-name factory does not use the original normal String layout')
    tested=S.ROOT/'native/providers/win32_library_name.asm.inc'
    standalone=S.ROOT/'native/providers/library_name_normal.asm.inc'
    S.check(normalized_kernel(tested.read_text(),True)==normalized_kernel(standalone.read_text()),
            'Independent library-name kernel changed a tested instruction or branch')
    return dict(schema=1,owner=owners[OWNER]['id'],methods=[dict(**native,operation=0)],original_java=java,
        source_classes={name:c['id'] for name,c in owners.items()},source_String_fields=fields,
        source_String_shape=shape,required_classes=sorted(c['id'] for c in owners.values()),
        required_java_methods=[m['method'] for m in java],required_provider_families=['normal-throwable-v1'],
        required_base_modules=['runtime_metadata','properties'],pool_bytes=112,pool_abi=2,
        independent_pool=True,shared_String_metadata='boom_java_properties_string_pool',
        String_factory_kernel=S.artifact(S.ROOT/'native/kernels/java_string_literals.inc'),
        native_buffer_allocations=False,tested_kernel=S.artifact(tested),
        normalization='service/private labels/source aliases only; instructions unchanged')


def aliases(meta):
    names=meta['source_classes']
    method=lambda owner,name:next(m['method'] for m in meta['original_java'] if m['owner']==owner and m['name']==name)
    error=names['java/lang/IllegalArgumentException']
    return dict(MLN_STRING_LAYOUT=f"boom_layout{names['java/lang/String']}",
        MLN_LENGTH=f"boom_m{method('java/lang/String','length')}",
        MLN_CHARS=f"boom_m{method('java/lang/String','toCharArray')}",
        MLN_ERROR_CLASS=f'boom_class{error}',MLN_ERROR_LAYOUT=f'boom_layout{error}',
        MLN_ERROR_CTOR=f"boom_m{method('java/lang/IllegalArgumentException','<init>')}",
        MLN_THROWABLE_TYPE=f"boom_t{names['java/lang/Throwable']}")


def native_imports(meta):
    a=aliases(meta)
    proc={a[k] for k in ('MLN_LENGTH','MLN_CHARS','MLN_ERROR_CTOR')}
    proc|={'boom_heap_contains','boom_object_check','boom_object_new','boom_exception_set32',
        'boom_java_property_copy','boom_java_string_literal','boom_trace_enter','boom_trace_leave'}
    data=set(a.values())-proc
    data|={'boom_heap_ptr','boom_runtime_type_map','boom_java_properties_string_pool',
           'boom_trace_pool',f"boom_trace_method{meta['methods'][0]['method']}"}
    return proc,data


def data(meta):
    text=''.join(f'{name} TEXTEQU <{value}>\n' for name,value in aliases(meta).items())
    # The existing copy callback only reads ABI, heap, String metadata and factory.
    # This independent read-only pool contains no property rows or native buffers.
    return text+f'''.const
ALIGN 8
PUBLIC {POOL}
{POOL} DWORD 050524F50h,2,0,0
 QWORD OFFSET boom_heap_ptr,OFFSET boom_java_properties_string_pool,0,0,0
 DWORD 0,0
 QWORD 0,0
 QWORD 0,OFFSET boom_java_property_copy,0,OFFSET boom_java_string_literal
'''
