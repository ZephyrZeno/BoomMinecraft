"""Original invoke0, bounded to no-argument static Java reference returns.

Method objects still come from the original Class/Method Java protocol. The
target directory uses the same original classfile slots as normal-methods.
Selection supplies real Java entries or original diagnostic callbacks.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


N=module('method_invoke_original_method_directory','normal-methods-source.py')
F=module('method_invoke_original_field_layouts','file-bootstrap-source.py')
IR=module('method_invoke_original_classfile','verify-translation-ir.py')
SPECS=[('jdk/internal/reflect/DirectMethodHandleAccessor$NativeAccessor','invoke0'),
       ('jdk/internal/reflect/NativeMethodAccessorImpl','invoke0')]
DESCRIPTOR='(Ljava/lang/reflect/Method;Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;'
POOL='boom_provider_method_invoke_pool'
SERVICE='boom_provider_method_invoke_service'
SELECTED='boom_provider_method_invoke_selected_sites'
CONTROL={'boom_method_invoke_counters'}
FOREIGN=set()
KERNELS=['classes32.asm','frames.asm','heap.asm','objects.asm','exceptions.asm','java_classes.asm',
    'java_properties.asm','runtime_types.asm','runtime_type_index.asm','types.asm']
JAVA=[('java/lang/IllegalArgumentException','<init>','(Ljava/lang/String;)V'),
      ('java/lang/reflect/InvocationTargetException','<init>','(Ljava/lang/Throwable;)V'),
      ('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]
POLICY=dict(normal_Method_layout=True,slot_namespace='original_classfile_method_table',
    target_scope='noarg_static_Java_reference_or_array_return',receiver_ignored_for_static=True,
    null_or_empty_reference_argument_array=True,wrong_arity='original_IllegalArgumentException_String_constructor',
    declaring_class_initialization_before_argument_count=True,target_Throwable='original_InvocationTargetException_cause_constructor',
    initialization_Throwable_wrapped=False,Context20_or_source_diagnostic_wrapped=False,
    original_Method_invoke_callerSensitive_and_access_and_accessor_Java_preserved=True,
    callerSensitive_native_target_supported=False,property_override_or_Java_field_injection=False,
    primitive_boxing=False,argument_unboxing_or_widening=False,virtual_or_interface_dispatch=False,
    nonselected_source_targets='original_method_or_class_diagnostic_callback',missing_target_success=False,
    ordinary_native_frames=True,normal_String_factory=True,source_transform_chain='original_locked_no_transforms',
    nonmoving_heap=True,GC_requires_quiescent_external_calls=True,automatic_GC=False,additional_native_root_spans=False)

PINS={'java/lang/reflect/Method.java': '2261e2d25ff86f17e254e7fe67da691585108eefeba39f0426479e43c62ab941', 'jdk/internal/reflect/ReflectionFactory.java': 'f875350419ab6f0c5343e45f32f5bfad999f42c6ccda5b39cace03c59f62ce13', 'jdk/internal/reflect/MethodHandleAccessorFactory.java': 'd77fd72063c849d96d2a07521c6dfd5ec6862789be2936eeb4b1d73924ba987e', 'jdk/internal/reflect/DirectMethodHandleAccessor.java': 'e593f6c6a875ada9b5808b40b00cee9fad86251a23eb8fc6ba9eaa9446ef60c7', 'jdk/internal/reflect/NativeMethodAccessorImpl.java': '60238ddeb2f90e69f2e6011d9a4a698c143fb3998dd1e8cb67e35a4001fc102a', 'jdk/internal/misc/VM.java': 'c9c81b2ab2bf8b44cd6c178f9d1081827e51a977899f29f291c6712d6324a6b0', 'java/lang/Class.java': '6b4706c75763b0d3b733d8c9c1d9e1001ad54753c7091b3bbf5ec29d29cbc50d', 'java/lang/StackWalker.java': 'cedc54acbc74ee164f9ababa208621ac1cc407cb0cb98c076f8d2d17000b5a47', 'java/util/EnumSet.java': '534ce16243bf168fd20741752de6bdb5e9fd5ed31977de1c8885af2a5163d1ed', 'java/lang/invoke/MethodHandleNatives.java': '69fcd3520cc8e31d6d35085735035483f5defde22495aaf8561df6d03f9215f1'}


def source_pins(S):
    directory=S.ART/'method-invoke/default-source-v151-a/pinned-sources'
    result={name:S.artifact(directory/name) for name in PINS}
    S.check(all(row['digest']['sha256']==PINS[name] for name,row in result.items()),'Locked original Method invoke Java source changed')
    native=S.ART/'normal-methods/pinned-sources/jdk-21.0.13+3/reflection.cpp'
    S.check(S.digest(native)['sha256']=='a5c605164d0c15a7ef01185c1649d782310453392b5ec32725540d377d4d3f7e','Locked original reflection implementation changed')
    result['reflection.cpp']=S.artifact(native)
    return result


def index(summary,classes,S):
    types,runtime,available,resolve=N.C.inputs(summary,classes)
    byname={(c['origin']['loader'],c['name']):c for c in classes}
    wanted={name:byname['bootstrap',name] for name in {'java/lang/reflect/Method','java/lang/String','java/lang/Throwable',
        'java/lang/IllegalArgumentException','java/lang/reflect/InvocationTargetException','jdk/internal/misc/VM'}|{n for n,_ in SPECS}}
    readers=N.C.RawClasses(summary);native=[];java=[];records=[];vm_guard=None
    try:
        for name,c in wanted.items():
            S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Original reflection source required')
            raw=IR.Source(readers.read(c));S.check(raw.name==name and len(raw.methods)==len(c['method_ids']),'Original invoke source inventory differs')
            for ident,m in zip(c['method_ids'],raw.methods):
                key=name,m['name'],m['descriptor']
                if (name,m['name']) not in SPECS and key not in JAVA and key!=('jdk/internal/misc/VM','isJavaLangInvokeInited','()Z'):continue
                code=raw.code(m);row=dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',
                    source_id='jdk:java.base',owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'])
                if (name,m['name']) in SPECS:
                    S.check(m['descriptor']==DESCRIPTOR and m['access']==0x10a and code is None,'Original invoke0 declaration differs')
                    native.append(dict(**row,operation=SPECS.index((name,m['name']))))
                else:
                    S.check(code is not None,'Original method-invoke Java callback Code missing')
                    row['code_sha256']=hashlib.sha256(code['bytes']).hexdigest()
                    if key in JAVA:java.append(row)
                    else:
                        ops=list(IR.stream(code['bytes']))
                        S.check([op['opcode'] for op in ops]==[0xb2,0xac] and raw.member(ops[0]['operand']['Constant'])==
                            dict(owner=name,name='javaLangInvokeInited',descriptor='Z'),'VM invoke guard must read its original independent boolean')
                        [field]=[i for i,f in enumerate(raw.fields) if f['name']=='javaLangInvokeInited' and f['descriptor']=='Z' and f['access']&8]
                        vm_guard=dict(**row,static_field=field,symbol=f"boom_s{c['id']}_{field}",not_derived_from_initLevel=True)
        S.check(len(native)==2 and len(java)==len(JAVA) and vm_guard is not None,'Original invoke callbacks incomplete')
        # Read the exact same slot inventory as getDeclaredMethods0; retain only
        # the supported static shape. No owner/name (including enums) is special.
        for c in classes:
            if c.get('parse_error') or c['access']&0x8000 or c['origin'].get('generated'):continue
            data=readers.read(c);owner,access,methods=N.original_methods(data)
            S.check(owner==c['name'] and access==c['access'] and len(methods)==len(c['method_ids']),
                'Original invocation classfile slot inventory differs')
            eligible=[r for r in methods if r['name'] not in ('<init>','<clinit>') and r['access']&0x408==8 and not r['access']&0x100 and
                (r['descriptor'].startswith('()L') or r['descriptor'].startswith('()['))]
            if not eligible:continue
            raw=IR.Source(data)
            for r in eligible:
                m=raw.methods[r['slot']];code=raw.code(m)
                S.check((m['name'],m['descriptor'],m['access'])==(r['name'],r['descriptor'],r['access']) and code is not None,
                    'Original noarg static invocation Code is missing')
                result=resolve(c['origin']['loader'],r['descriptor'][2:])
                records.append(dict(owner=c['id'],slot=r['slot'],method=c['method_ids'][r['slot']],name=r['name'],descriptor=r['descriptor'],
                    modifiers=r['access']&0x1dff,access=r['access'],source_sha256=c['origin']['sha256'],
                    code_sha256=hashlib.sha256(code['bytes']).hexdigest(),return_type=result,
                    available=c['id'] in available and result is not None,annotations=r['annotations'],
                    raw_parameter_types=[],slot_matches_normal_method_directory=True))
    finally:readers.close()
    ids={r['method'] for r in records};frames={}
    with zipfile.ZipFile(N.C.artifact(summary['frames']['index'])) as z:
        for line in z.open('methods.jsonl'):
            row=json.loads(line)
            if row['id'] in ids:frames[row['id']]=row
    S.check(set(frames)==ids,'Noarg static reference source frame inventory incomplete')
    for r in records:
        frame=frames[r['method']]
        S.check(all(frame[a]==r[b] for a,b in [('class_id','owner'),('class_sha256','source_sha256'),('name','name'),
            ('descriptor','descriptor'),('code_sha256','code_sha256'),('access','access')]),'Target source Code/frame identity differs')
        r['assembly_emitted']=frame['assembly_emitted'];r['frame_flags']=frame['flags']
        r['caller_sensitive']=bool(frame['flags']&8)
        if r['caller_sensitive']:r['available']=False
    java.sort(key=lambda r:(r['owner'],r['name'],r['descriptor']))
    required_ids={c['id'] for c in wanted.values()}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layouts={r['class_id']:r for line in stream if (r:=json.loads(line))['class_id'] in required_ids}
    method=wanted['java/lang/reflect/Method'];string=wanted['java/lang/String']
    specs=[('clazz','Ljava/lang/Class;',0x12,8,True),('slot','I',0x12,4,False),('name','Ljava/lang/String;',0x12,8,True),
        ('returnType','Ljava/lang/Class;',0x12,8,True),('parameterTypes','[Ljava/lang/Class;',0x12,8,True),('modifiers','I',0x12,4,False)]
    method_fields=F.fields(method,layouts[method['id']],specs,S)
    string_fields=F.fields(string,layouts[string['id']],[('value','[B',0x12,8,True),('coder','B',0x12,1,False)],S)
    shape=summary['string_literals']['source_layout']
    S.check(shape['class_id']==string['id'] and shape['source_sha256']==string['origin']['sha256'] and
        all(shape['value_offset' if r['name']=='value' else 'coder_offset']==r['offset'] for r in string_fields),
        'Invocation uses a different normal String layout')
    ranges=[];at=0
    for owner in range(summary['runtime_metadata']['type_capacity']):
        first=at
        while at<len(records) and records[at]['owner']==owner:at+=1
        ranges.append(dict(first=first,count=at-first))
    S.check(at==len(records),'Invocation records must retain original class/slot order')
    type_names={(r['defining_loader'],r['name']):r['id'] for r in types}
    return dict(schema=1,native_sources=source_pins(S),methods=sorted(native,key=lambda r:r['operation']),records=records,ranges=ranges,type_capacity=len(ranges),
        method_class=method['id'],method_fields=method_fields,normal_method_layout=layouts[method['id']]['candidate'],
        string_class=string['id'],string_fields=string_fields,source_String_shape=shape,Class_array_type=type_names['bootstrap','[Ljava/lang/Class;'],
        source_classes={n:c['id'] for n,c in wanted.items()},original_java=java,source_VM_invoke_guard=vm_guard,
        required_classes=sorted(required_ids),required_java_methods=[r['method'] for r in java],
        required_base_modules=['class_literals','runtime_metadata','properties'],required_provider_families=['normal-throwable-v1'],
        native_root_spans=[],pool_bytes=128,pool_abi=1,record_bytes=48,range_bytes=8,selected_site_bytes=32,
        primitive_boxing_or_virtual_dispatch_supported=False,selection_specific_sites_required=True)


def selected_sites(meta,selected_classes,selected_methods):
    classes={int(i) for i in selected_classes};methods={int(i):r for i,r in selected_methods.items()};parts=[];imports={SELECTED};sites=[]
    parts.append('.const\nALIGN 8\nPUBLIC '+SELECTED+'\n'+SELECTED+' LABEL QWORD\n')
    for i,row in enumerate(meta['records']):
        target=None;reason=None
        if not row['available']:reason='caller_sensitive_unsupported' if row['caller_sensitive'] else 'source_type_unavailable'
        elif row['owner'] not in classes:target=f"boom_batch_initialize_{row['owner']}";reason='class_not_selected'
        elif row['method'] not in methods:target=f"boom_m{row['method']}";reason='Java_Code_not_selected'
        else:
            actual=methods[row['method']]
            N.C.check(row['assembly_emitted'] and not row['frame_flags']&128,'Selected method has no available compiled source body')
            if isinstance(actual,dict):
                N.C.check(actual['class_id']==row['owner'] and actual['source_sha256']==row['source_sha256'] and
                    actual['code_sha256']==row['code_sha256'],'Selected original method Code differs')
        init=f"boom_class{row['owner']}" if row['available'] and row['owner'] in classes else None
        actual=f"boom_m{row['method']}" if reason is None else None
        parts.append(' QWORD '+','.join('OFFSET '+x if x else '0' for x in (init,actual,target,None))+'\n')
        imports|={x for x in (init,actual,target) if x}
        sites.append(dict(index=i,method=row['method'],ready=reason is None,reason=reason,callback=target))
    return ''.join(parts),imports-{SELECTED},sites


def aliases(meta):
    classes=meta['source_classes'];result={}
    for prefix,name in [('IAE','java/lang/IllegalArgumentException'),('ITE','java/lang/reflect/InvocationTargetException')]:
        [method]=[r for r in meta['original_java'] if r['owner']==name and r['name']=='<init>']
        result['MINV_'+prefix+'_CLASS']=f"boom_class{classes[name]}";result['MINV_'+prefix+'_LAYOUT']=f"boom_layout{classes[name]}"
        result['MINV_'+prefix+'_CTOR']=f"boom_m{method['method']}"
    return result


def native_imports(meta):
    proc={'boom_heap_contains','boom_object_check','boom_java_class_typeid','boom_class_ensure32','boom_runtime_row',
        'boom_object_new','boom_exception_set32','boom_exception_take32','boom_java_property_copy','boom_java_string_literal',
        'boom_trace_enter','boom_trace_leave'}|{value for key,value in aliases(meta).items() if key.endswith('_CTOR')}
    data=set(aliases(meta).values())-proc|{'boom_heap_ptr','boom_java_class_pool','boom_runtime_type_map','boom_java_properties_string_pool',
        'boom_trace_pool',SELECTED,f"boom_layout{meta['method_class']}",f"boom_layout{meta['string_class']}",
        f"boom_t{meta['source_classes']['java/lang/Throwable']}"}|{f"boom_trace_method{r['method']}" for r in meta['methods']}
    return proc,data


def data(meta):
    parts=[''.join(f'{key} TEXTEQU <{value}>\n' for key,value in aliases(meta).items()),'.const\nALIGN 8\nPUBLIC '+POOL+'\n',
        f"{POOL} DWORD 04B56494Dh,1,{len(meta['records'])},{meta['type_capacity']}\n",
        f" QWORD OFFSET boom_heap_ptr,OFFSET boom_java_class_pool,OFFSET boom_runtime_type_map,OFFSET boom_layout{meta['method_class']},OFFSET boom_layout{meta['string_class']}\n",
        ' QWORD OFFSET minvoke_fields,OFFSET minvoke_records,OFFSET minvoke_ranges,OFFSET '+SELECTED+'\n',
        f" QWORD OFFSET boom_t{meta['source_classes']['java/lang/Throwable']}\n DWORD {meta['Class_array_type']},0\n",
        ' QWORD OFFSET minvoke_string_pool,0,0\n',
        'ALIGN 8\nminvoke_fields DWORD '+','.join(str(next(r['offset'] for r in meta['method_fields'] if r['name']==name)) for name in
            ('clazz','slot','name','returnType','parameterTypes','modifiers'))+'\n',
        ' DWORD '+','.join(str(next(r['offset'] for r in meta['string_fields'] if r['name']==name)) for name in ('value','coder'))+'\n',
        'ALIGN 8\nminvoke_string_pool DWORD 050524F50h,2,0,0\n QWORD OFFSET boom_heap_ptr,OFFSET boom_java_properties_string_pool,0,0,0\n DWORD 0,0\n QWORD 0,0\n QWORD 0,OFFSET boom_java_property_copy,0,OFFSET boom_java_string_literal\n',
        'ALIGN 8\nminvoke_ranges LABEL DWORD\n']
    parts.extend(f" DWORD {r['first']},{r['count']}\n" for r in meta['ranges'])
    parts.append('ALIGN 8\nminvoke_records LABEL BYTE\n');payload=[]
    for i,row in enumerate(meta['records']):
        units=list(int.from_bytes(row['name'].encode('utf-16-le','surrogatepass')[n:n+2],'little') for n in range(0,len(row['name'].encode('utf-16-le','surrogatepass')),2))
        parts.append(f" DWORD {row['owner']},{row['slot']},{row['method']},{row['modifiers']}\n QWORD OFFSET minvoke_name{i}\n DWORD {len(units)},{row['return_type'] if row['return_type'] is not None else 0xffffffff},{i},0\n QWORD 0\n")
        payload.append(f'minvoke_name{i} LABEL WORD\n')
        payload.extend(' WORD '+','.join(str(v) for v in units[n:n+16])+'\n' for n in range(0,len(units),16))
    return ''.join(parts+payload)
