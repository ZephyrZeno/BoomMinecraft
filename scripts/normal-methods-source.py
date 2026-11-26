"""Immutable original method metadata for normal java.lang.reflect.Method objects.

This is an unregistered source model. It neither initializes represented classes
nor turns missing executable Java bodies into invocable methods.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile


def module(name, file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


C=module('normal_method_original_classes','constructor-provider-source.py')
IR=module('normal_method_original_code','verify-translation-ir.py')
OWNER='java/lang/Class'
METHOD='java/lang/reflect/Method'
DESCRIPTOR='(Z)[Ljava/lang/reflect/Method;'
CONSTRUCTOR='(Ljava/lang/Class;Ljava/lang/String;[Ljava/lang/Class;Ljava/lang/Class;[Ljava/lang/Class;IILjava/lang/String;[B[B[B)V'
POOL='boom_normal_method_pool'
SERVICE='boom_normal_method_service'
CONTROL=set()
FOREIGN=set()
KERNELS=['heap.asm','objects.asm','classes32.asm','frames.asm','java_classes.asm','java_string_intern.asm',
         'runtime_types.asm','runtime_type_index.asm','types.asm']
POLICY=dict(original_classfile_method_inventory=True,exclude_initializers=True,include_bridge_synthetic=True,
    native_and_abstract_declarations_enumerated=True,publicOnly_source_ACC_PUBLIC=True,
    original_method_constructor_upcall=True,represented_class_initializer_invoked=False,
    original_Class_lookup_filter_copy_preserved=True,method_names_interned=True,
    normal_source_layouts=True,raw_annotations_preserved=True,generic_signatures_preserved=True,
    reflection_order='original_classfile_slot_order_not_HotSpot_order',slot_namespace='original_classfile_method_table',
    dynamic_redefinition=False,automatic_gc=False,collection_requires_quiescence=True,
    invoke0_implemented=False,annotation_parser_or_constant_pool_native_implemented=False,
    source_transform_chain='original_locked_no_transforms')
PINS={
    'Class.c':('6dbf6965c1cf6c9f9f62e0f268d23deeacdb7184979319efafa5c42887d1ae57','src/java.base/share/native/libjava/Class.c'),
    'jvm.cpp':('84436b103fb7869e445bac95d2e82e9de9160c2da327a4cf54f4e84555150ad9','src/hotspot/share/prims/jvm.cpp'),
    'reflection.cpp':('a5c605164d0c15a7ef01185c1649d782310453392b5ec32725540d377d4d3f7e','src/hotspot/share/runtime/reflection.cpp'),
}


def source_pins(S):
    result={}
    for name,(sha,relative) in PINS.items():
        path=S.ART/'normal-methods/pinned-sources/jdk-21.0.13+3'/name
        S.check(S.digest(path)['sha256']==sha,'Pinned original reflection native source changed: '+name)
        result[name]=dict(**S.artifact(path),url='https://raw.githubusercontent.com/openjdk/jdk21u/jdk-21.0.13%2B3/'+relative)
    return result


def descriptor_types(descriptor):
    """Validate the entire descriptor, preserving each original type spelling."""
    C.check(isinstance(descriptor,str) and descriptor.startswith('('),'Invalid method descriptor')
    def one(at,void=False):
        begin=at
        while at<len(descriptor) and descriptor[at]=='[':at+=1
        C.check(at<len(descriptor),'Truncated method type')
        tag=descriptor[at]
        if tag=='L':
            end=descriptor.find(';',at+1)
            C.check(end>at+1 and not any(ch in descriptor[at+1:end] for ch in '[.;('),
                    'Invalid method reference descriptor')
            return descriptor[begin:end+1],end+1
        C.check(tag in 'ZBCSIJFD' or tag=='V' and void and begin==at,'Invalid method primitive type')
        return descriptor[begin:at+1],at+1
    params=[];at=1
    while at<len(descriptor) and descriptor[at]!=')':
        value,at=one(at);params.append(value)
    C.check(at<len(descriptor) and descriptor[at]==')','Method descriptor parameter end missing')
    result,at=one(at+1,True)
    C.check(at==len(descriptor) and len(params)<=255,'Method descriptor trailing data or excess parameters')
    return params,result


def original_methods(data):
    """Read reflection attributes without losing absent versus present-empty."""
    raw=C.RAW;r=raw.Reader(data)
    C.check(r.number(4)==0xcafebabe,'Original reflection class magic differs');r.take(4)
    count=r.number(2);cp=[None]*count;i=1
    while i<count:
        tag=r.number(1)
        if tag==1:cp[i]=raw.modified_utf8(r.take(r.number(2)))
        elif tag in (3,4):r.take(4)
        elif tag in (5,6):r.take(8);i+=1
        elif tag in (7,8,16,19,20):cp[i]=r.number(2)
        elif tag in (9,10,11,12,17,18):r.take(4)
        elif tag==15:r.take(3)
        else:raise ValueError('Unknown original reflection constant tag')
        i+=1
    def utf(i):
        C.check(0<i<count and isinstance(cp[i],str),'Reflection UTF8 constant missing');return cp[i]
    def clazz(i):
        C.check(0<i<count and type(cp[i]) is int,'Reflection class constant missing');return utf(cp[i])
    def attrs():
        result={}
        for _ in range(r.number(2)):
            name=utf(r.number(2));payload=r.take(r.number(4))
            C.check(name not in result,'Duplicate original reflection attribute');result[name]=payload
        return result
    access=r.number(2);owner=clazz(r.number(2));r.number(2);r.take(2*r.number(2))
    for _ in range(r.number(2)):r.take(6);attrs()
    result=[]
    for slot in range(r.number(2)):
        flags=r.number(2);name=utf(r.number(2));descriptor=utf(r.number(2));a=attrs()
        descriptor_types(descriptor)
        ex=raw.Reader(a.get('Exceptions',b'\0\0'));exceptions=[clazz(ex.number(2)) for _ in range(ex.number(2))];ex.end()
        signature=None
        if 'Signature' in a:
            x=raw.Reader(a['Signature']);signature=utf(x.number(2));x.end()
        result.append(dict(slot=slot,name=name,descriptor=descriptor,access=flags,exceptions=exceptions,signature=signature,
            annotations=a['RuntimeVisibleAnnotations'].hex() if 'RuntimeVisibleAnnotations' in a else None,
            parameter_annotations=a['RuntimeVisibleParameterAnnotations'].hex() if 'RuntimeVisibleParameterAnnotations' in a else None,
            annotation_default=a['AnnotationDefault'].hex() if 'AnnotationDefault' in a else None,
            type_annotations=a['RuntimeVisibleTypeAnnotations'].hex() if 'RuntimeVisibleTypeAnnotations' in a else None,
            method_parameters=a['MethodParameters'].hex() if 'MethodParameters' in a else None))
    attrs();r.end();return owner,access,result


def index(summary,classes,S):
    types,runtime,available,resolve=C.inputs(summary,classes)
    S.check([row['id'] for row in classes]==list(range(len(classes))), 'Original class identifiers are not dense')
    byname={(c['origin']['loader'],c['name']):c for c in classes}
    wanted={name:byname['bootstrap',name] for name in (OWNER,METHOD,'java/lang/String','java/lang/reflect/Executable',
        'java/lang/reflect/AccessibleObject','java/lang/Object')}
    source=C.RawClasses(summary);records=[];ranges=[];original_java=[];native=None
    try:
        for cls in classes:
            first=len(records);status=1 if cls['id'] in available else 3
            if cls.get('parse_error') or cls['access']&0x8000 or cls['origin'].get('generated'):
                status=3
            else:
                data=source.read(cls);name,access,methods=original_methods(data)
                S.check(name==cls['name'] and access==cls['access'] and len(methods)==len(cls['method_ids']),
                        'Original reflection inventory differs: '+cls['name'])
                for row in methods:
                    ident=cls['method_ids'][row['slot']]
                    if name==OWNER and cls['origin']['loader']=='bootstrap' and row['name']=='getDeclaredMethods0':
                        S.check(row['descriptor']==DESCRIPTOR and row['access']==0x102,'Original Class native declaration differs')
                        native=dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],loader='bootstrap',
                            source_id='jdk:java.base',owner=OWNER,name=row['name'],descriptor=row['descriptor'],access=row['access'],operation=0)
                    if row['name'] in ('<init>','<clinit>'):continue
                    params,returns=descriptor_types(row['descriptor'])
                    params=[resolve(cls['origin']['loader'],p) for p in params]
                    result=resolve(cls['origin']['loader'],returns)
                    exceptions=[resolve(cls['origin']['loader'],'L'+n+';') for n in row['exceptions']]
                    records.append(dict(row,owner=cls['id'],method=ident,source_sha256=cls['origin']['sha256'],
                        loader=cls['origin']['loader'],source_id=cls['origin']['source_id'],modifiers=row['access']&0x1dff,
                        parameter_descriptors=descriptor_types(row['descriptor'])[0],return_descriptor=returns,
                        parameters=params,return_type=result,exception_names=row['exceptions'],exceptions=exceptions,
                        unavailable=any(v is None for v in params+exceptions+[result])))
            ranges.append(dict(type_id=cls['id'],first=first,count=len(records)-first,status=status))
        for name,c in wanted.items():
            raw=IR.Source(source.read(c))
            S.check(raw.name==name and len(raw.methods)==len(c['method_ids']),'Original Method upcall inventory differs')
            for ident,m in zip(c['method_ids'],raw.methods):
                include=(name==METHOD and m['name']=='<init>' and m['descriptor']==CONSTRUCTOR)
                include|=(name==OWNER and m['name'] in ('getDeclaredMethod','getDeclaredMethods','privateGetDeclaredMethods'))
                include|=(name==METHOD and m['name'] in ('copy','getName','getReturnType','getParameterTypes','getExceptionTypes','getModifiers'))
                if not include:continue
                code=raw.code(m);S.check(code is not None,'Original Method Java body missing')
                original_java.append(dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',
                    source_id='jdk:java.base',owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],
                    code_sha256=hashlib.sha256(code['bytes']).hexdigest()))
    finally:source.close()
    S.check(native is not None,'Original Class getDeclaredMethods0 is missing')
    [constructor]=[r for r in original_java if r['owner']==METHOD and r['name']=='<init>']
    capacity=summary['runtime_metadata']['type_capacity']
    for ident in range(len(classes),capacity):
        ranges.append(dict(type_id=ident,first=len(records),count=0,status=1 if ident in available else 3))
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layouts={r['name']:r for line in stream if (r:=json.loads(line))['name'] in wanted and
                 r['class_id']==wanted[r['name']]['id']}
    S.check(set(layouts)==set(wanted) and all(r['diagnostic'] is None and r['candidate'] is not None and
        r['source_sha256']==wanted[n]['origin']['sha256'] for n,r in layouts.items()),'Normal reflection layouts differ')
    method_id=wanted[METHOD]['id'];string=wanted['java/lang/String']['id']
    def field(cls,owner,name,descriptor):
        rows=[f for f in layouts[cls]['candidate']['fields'] if (f['member']['owner'],f['member']['name'],f['member']['descriptor'])==(wanted[owner]['id'],name,descriptor)]
        S.check(len(rows)==1,'Normal Method source field missing: '+name);return rows[0]['offset']
    fields={n:field(METHOD,METHOD,n,d) for n,d in (
        ('clazz','Ljava/lang/Class;'),('slot','I'),('name','Ljava/lang/String;'),('returnType','Ljava/lang/Class;'),
        ('parameterTypes','[Ljava/lang/Class;'),('exceptionTypes','[Ljava/lang/Class;'),('modifiers','I'),
        ('signature','Ljava/lang/String;'),('annotations','[B'),('parameterAnnotations','[B'),('annotationDefault','[B'),
        ('root','Ljava/lang/reflect/Method;'))}
    kinds={(t['defining_loader'],t['name']):t for t in types};runtime_by_id={r['type_id']:r for r in runtime}
    arrays={name:runtime_by_id[kinds['bootstrap',name]['id']] for name in ('[Ljava/lang/reflect/Method;','[Ljava/lang/Class;','[B')}
    return dict(schema=1,owner=wanted[OWNER]['id'],methods=[native],method_class=method_id,string_class=string,
        type_capacity=capacity,records=records,ranges=ranges,normal_method_layout=layouts[METHOD]['candidate'],fields=fields,
        string_value_offset=field('java/lang/String','java/lang/String','value','[B'),
        string_coder_offset=field('java/lang/String','java/lang/String','coder','B'),arrays=arrays,
        compact_strings=summary['string_literals']['compact_strings'],
        original_java=original_java,constructor=constructor,native_sources=source_pins(S),
        required_classes=sorted(c['id'] for c in wanted.values()),required_java_methods=[constructor['method']],
        required_base_modules=['class_literals','string_intern','runtime_metadata'],required_provider_families=[],
        pool_bytes=192,pool_abi=1,row_bytes=144,range_bytes=16,
        all_original_declarations=True,Java_Code_selection_required_for_enumeration=False,
        method_invocation_supported=False,extra_static_Java_oop_roots=False)


def native_imports(meta):
    proc={'boom_heap_alloc','boom_object_new','boom_java_class_load','boom_java_class_typeid','boom_class_ensure32',
          'boom_java_string_intern','boom_trace_enter','boom_trace_leave',f"boom_m{meta['constructor']['method']}"}
    data={'boom_heap_ptr','boom_java_class_pool','boom_java_string_intern_pool','boom_trace_pool',
          f"boom_layout{meta['method_class']}",f"boom_layout{meta['string_class']}",f"boom_class{meta['method_class']}"}
    data|={meta['arrays'][name]['tag_symbol'] for name in ('[Ljava/lang/reflect/Method;','[Ljava/lang/Class;')}
    data|={f"boom_trace_method{r['method']}" for r in meta['methods']}
    return proc,data


def data(meta):
    ptr=lambda symbol,present:'OFFSET '+symbol if present else '0'
    arrays=meta['arrays'];method=meta['method_class'];string=meta['string_class']
    text=['.const\nALIGN 8\nPUBLIC '+POOL+'\n',
        f"{POOL} DWORD 04E4D5448h,1,{meta['type_capacity']},{len(meta['records'])}\n",
        ' QWORD OFFSET boom_java_class_pool,OFFSET boom_heap_ptr,OFFSET normal_method_ranges,OFFSET normal_method_rows\n',
        f" QWORD OFFSET boom_layout{method},OFFSET {arrays['[Ljava/lang/reflect/Method;']['tag_symbol']},OFFSET {arrays['[Ljava/lang/Class;']['tag_symbol']},OFFSET boom_layout{string}\n",
        f" QWORD OFFSET boom_class{method},OFFSET boom_m{meta['constructor']['method']},OFFSET boom_java_string_intern_pool\n",
        f" DWORD {meta['string_value_offset']},{meta['string_coder_offset']}\n QWORD {arrays['[B']['primitive_tag']}\n",
        f" DWORD 144,16,12,{int(meta['compact_strings'])}\n QWORD 0,0,0,0,0,0,0\nALIGN 8\nnormal_method_ranges LABEL BYTE\n"]
    text.extend(f" DWORD {r['first']},{r['count']},{r['status']},0\n" for r in meta['ranges'])
    text.append('ALIGN 8\nnormal_method_rows LABEL BYTE\n')
    payloads=[]
    for i,row in enumerate(meta['records']):
        prefix='normal_method_'+str(i)+'_'
        name=row['name'].encode('utf-16-le','surrogatepass')
        sig=row['signature'].encode('utf-16-le','surrogatepass') if row['signature'] is not None else None
        text.append(f" DWORD {row['owner']},{row['slot']},{row['modifiers']},{len(row['parameters'])}\n")
        text.append(' QWORD '+ptr(prefix+'params',row['parameters'])+','+ptr(prefix+'exceptions',row['exceptions'])+'\n')
        text.append(f" DWORD {len(row['exceptions'])},{int(row['unavailable'])}\n QWORD OFFSET {prefix}name\n")
        text.append(f" DWORD {len(name)//2},{row['return_type'] if row['return_type'] is not None else 0xffffffff}\n")
        text.append(' QWORD '+ptr(prefix+'signature',sig is not None)+'\n')
        text.append(f" DWORD {len(sig or b'')//2},{int(sig is not None)}\n")
        payload={'name':name,'signature':sig}
        for key in ('annotations','parameter_annotations','annotation_default','type_annotations'):
            value=bytes.fromhex(row[key]) if row[key] is not None else None;payload[key]=value
            text.append(' QWORD '+ptr(prefix+key,value is not None)+'\n')
            text.append(f" DWORD {len(value or b'')},{int(value is not None)}\n")
        text.append(' QWORD 0\n')
        for key,label in (('parameters','params'),('exceptions','exceptions')):
            if row[key]:payloads.append(prefix+label+' DWORD '+','.join(str(v if v is not None else 0xffffffff) for v in row[key])+'\n')
        for key,value in payload.items():
            if value is None:continue
            payloads.append(prefix+key+' LABEL BYTE\n')
            payloads.extend(' BYTE '+','.join(map(str,value[at:at+32]))+'\n' for at in range(0,len(value),32))
            if not value:payloads.append(' BYTE 0\n')
    return ''.join(text+payloads)
