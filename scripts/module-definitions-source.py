"""Original Module native declarations and a closed normal-JCLS bootstrap graph."""
import hashlib
import json
import struct
import zipfile


OWNER='java/lang/Module'
POOL='boom_provider_module_definitions_pool'
SERVICE='boom_provider_module_definitions_service'
CONTROL={'boom_module_definitions_rows','boom_module_definitions_package_states',
    'boom_module_definitions_owned_buffers','boom_module_definitions_can_read','boom_module_definitions_is_exported'}
FOREIGN={'GetProcessHeap','HeapAlloc','HeapFree','AcquireSRWLockExclusive','ReleaseSRWLockExclusive',
    'AcquireSRWLockShared','ReleaseSRWLockShared'}
KERNELS=['java_classes.asm','classes32.asm','frames.asm','heap.asm','objects.asm','java_properties.asm',
    'field_address.asm','runtime_types.asm','runtime_type_index.asm','types.asm']
SPECS=[(OWNER,'defineModule0','(Ljava/lang/Module;ZLjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V',0),
    (OWNER,'addReads0','(Ljava/lang/Module;Ljava/lang/Module;)V',1),
    (OWNER,'addExports0','(Ljava/lang/Module;Ljava/lang/String;Ljava/lang/Module;)V',2),
    (OWNER,'addExportsToAll0','(Ljava/lang/Module;Ljava/lang/String;)V',3),
    (OWNER,'addExportsToAllUnnamed0','(Ljava/lang/Module;Ljava/lang/String;)V',4)]
ERRORS=['java/lang/NullPointerException','java/lang/IllegalArgumentException','java/lang/IllegalStateException','java/lang/InternalError']
MESSAGES=[(0,'Null module object'),(1,'module is not an instance of type java.lang.Module'),
    (0,'Null module name'),(1,'Invalid module name: '),(1,'Class loader must be the boot class loader'),
    (1,'Bad package name'),(3,'Module java.base is already defined'),(0,'from_module is null'),
    (1,'from_module is not valid'),(1,'from_module cannot be found'),(0,'to_module is null'),
    (1,'to_module is invalid'),(0,'package is null'),(1,'module is invalid'),(0,'module is null')]
JAVA=[(name,'<init>','(Ljava/lang/String;)V') for name in ERRORS]+[
    ('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]
CHAIN=[(OWNER,'<init>','(Ljava/lang/ModuleLayer;Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;Ljava/net/URI;)V'),
    (OWNER,'<init>','(Ljava/lang/ClassLoader;)V'),
    (OWNER,'<init>','(Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;)V'),
    ('jdk/internal/module/Modules','defineModule','(Ljava/lang/ClassLoader;Ljava/lang/module/ModuleDescriptor;Ljava/net/URI;)Ljava/lang/Module;'),
    ('jdk/internal/module/ModuleBootstrap','boot2','()Ljava/lang/ModuleLayer;')]
PINS={'Module.c':'5531eb775a35590e19e421897ab2c27d3c6b402c996ef7a08992b3c4c2b39ad4',
    'modules.cpp':'a1e63505ef55a68efd0e940a34d655704c1967d83ca287c815e06726ddf2adde',
    'moduleEntry.cpp':'18d9d25c8cc4ae4ca544d879f35c75ac80e257fda80fc27bfffe8df2114c7a00',
    'packageEntry.cpp':'0224cd8f7aab646d69b1164c0d54d2a81d18d4150366283bad4e1dad9dff3684',
    'moduleEntry.hpp':'28a90c2912beab51b50ec783e456974f245f8b74a561ebef030405db8f0773b4',
    'packageEntry.hpp':'6c62caca14b101ee1169a81fde4f580af97280d0428b5e6720edf7a57d18ee75',
    'Module.java':'c420e6421c44756f2355d6614c31bfda404533a0c1f4f170f439cd43df424f1e',
    'ModuleBootstrap.java':'f98fd1781102c71c9cdbedb9caf5df593323368abcab7a48d6fff80385535dbb',
    'ModuleLayer.java':'eff4ab3b69985ec9cccfca39a9c7c6ba3d4944141fd419e632d59cbdf06a6e9a'}
PINS.update({'jvm.cpp':'84436b103fb7869e445bac95d2e82e9de9160c2da327a4cf54f4e84555150ad9',
    'javaClasses.cpp':'15d8e8a8ecd9e2ff9d74eb4d3651de0ee134f2bb4efbfed68ac3b3c8fce64313',
    'javaClasses.inline.hpp':'954c5f971f3b7ee52b4572c3bf9b072d9ac2908478caa777291048efa3326ce5',
    'classFileParser.cpp':'ddfc2850e1408cb9ea919986b7948043b2c76727051252b84db632548978eedc'})
POLICY=dict(normal_source_Module_objects=True,Java_Module_fields_modified=False,old_MODU3_pool_used=False,
    same_original_Module_oop_bound_to_JCLS=True,early_Class_mirror_module_patch=True,
    classloader_initialized_by_native=False,nonboot_loader_requires_original_published_ClassLoaders_identity=True,
    package_inventory='exact_locked_ModulePackages_set',package_duplicates='idempotent_membership',
    metadata_strings_UTF16_capacity=4096,unknown_module_loader_package_profiles_context=20,
    class_redefinition_or_dynamic_layer_support=False,original_BOOT_unnamed_identity_unchanged=True,
    graph_mutation_serialized=True,read_target_null_means_all_unnamed=True,
    unnamed_reads_everyone=True,all_modules_read_java_base=True,open_or_unnamed_exports_all=True,
    no_additional_Java_oop_roots=True,automatic_GC=False,GC_requires_quiescence=True,
    unregistered_Module_entry_falls_back_to_loader_unnamed=True,external_JNI_environment=False,
    app_unnamed_identity_from_original_ClassLoader_FMAP=True,platform_unnamed_extra_Module_created=False,
    source_transform_chain='original_locked_no_transforms')


def units(value):
    raw=value.encode('utf-16-le','surrogatepass');return list(struct.unpack('<'+'H'*(len(raw)//2),raw))


def index(summary,classes,S):
    I=S.module('module_definitions_original_class','verify-translation-ir.py')
    F=S.module('module_definitions_normal_fields','file-bootstrap-source.py')
    wanted={OWNER,'java/lang/String','java/lang/ClassLoader','jdk/internal/loader/ClassLoaders','java/lang/Throwable'}
    wanted|={row[0] for row in JAVA+CHAIN}
    owners={c['name']:c for c in classes if c['name'] in wanted and c['origin']['loader']=='bootstrap'}
    S.check(set(owners)==wanted,'Original normal Module source classes missing')
    members={};parsed={}
    for name,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Original java.base Module classes required')
        raw=I.Source(S.original_class(summary,c));parsed[name]=raw
        S.check(raw.name==name and len(raw.methods)==len(c['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==c['fields'],'Original Module inventory differs')
        for ident,method in zip(c['method_ids'],raw.methods):
            key=name,method['name'],method['descriptor']
            if key not in JAVA+CHAIN+[r[:3] for r in SPECS]:continue
            code=raw.code(method)
            calls=[] if not code else [dict(pc=op['pc'],**raw.member(op['operand']['Constant']))
                for op in I.stream(code['bytes']) if op['opcode'] in (0xb6,0xb7,0xb8)]
            members[key]=dict(method=ident,owner=name,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',
                source_id='jdk:java.base',name=method['name'],descriptor=method['descriptor'],access=method['access'],
                code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None,calls=calls)
    methods=[]
    for owner,name,descriptor,operation in SPECS:
        row=dict(members[owner,name,descriptor]);row.pop('calls')
        S.check(row['access']==0x10a and row.pop('code_sha256') is None,'Original private static Module native changed')
        methods.append(dict(**row,operation=operation))
    java=[members[key] for key in JAVA];chain=[members[key] for key in CHAIN]
    S.check(all(r['code_sha256'] for r in java+chain) and any(
        (r['owner'],r['name'],r['descriptor'])==SPECS[0][:3] for r in chain[0]['calls']),
        'Original Module constructor no longer calls the original native')
    classloader=owners['java/lang/ClassLoader']
    [unnamed_index]=[i for i,f in enumerate(classloader['fields']) if f==dict(
        name='unnamedModule',descriptor='Ljava/lang/Module;',access=0x12)]
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as archive:
        [unnamed_field]=[r for line in archive.open('fields.jsonl') if (r:=json.loads(line))['declaring_class']==classloader['id'] and
            r['declaring_field']==unnamed_index]
        inherited={r['receiver_class'] for r in unnamed_field['rows']}
        types={r['id']:r for line in archive.open('types.jsonl') if (r:=json.loads(line))['id'] in inherited}
    S.check(unnamed_field['reference'] and unnamed_field['storage_bytes']==8 and
        len(inherited)==len(unnamed_field['rows']) and classloader['id'] in inherited and set(types)==inherited,
        'Original ClassLoader.unnamedModule inherited field map differs')
    layouts={};allclasses={c['id']:c for c in classes}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['class_id'] in inherited|{c['id'] for c in owners.values()}:layouts[row['class_id']]=row
    for row in unnamed_field['rows']:
        ident,offset=row['receiver_class'],row['offset'];layout=layouts[ident]
        S.check(types[ident]['kind']==1 and types[ident]['source_sha256']==allclasses[ident]['origin']['sha256'] and
            (ident==classloader['id'] or classloader['id'] in types[ident]['ancestors']) and layout['diagnostic'] is None and
            layout['source_sha256']==allclasses[ident]['origin']['sha256'] and offset%8==0 and
            offset+8<=layout['candidate']['payload_bytes'] and offset<layout['candidate']['reference_prefix']*8 and any(
                f['member']['owner']==classloader['id'] and f['member']['index']==unnamed_index and f['offset']==offset and
                f['reference'] and f['storage_bytes']==8 for f in layout['candidate']['fields']),
            'ClassLoader.unnamedModule normal inherited receiver layout differs')
    module=owners[OWNER];fields=F.fields(module,layouts[module['id']],[
        ('layer','Ljava/lang/ModuleLayer;',0x12,8,True),('name','Ljava/lang/String;',0x12,8,True),
        ('loader','Ljava/lang/ClassLoader;',0x12,8,True),('descriptor','Ljava/lang/module/ModuleDescriptor;',0x12,8,True)],S)
    string=owners['java/lang/String'];sf=F.fields(string,layouts[string['id']],[
        ('value','[B',0x12,8,True),('coder','B',0x12,1,False),('hash','I',2,4,False),('hashIsZero','Z',2,1,False)],S)
    shape=summary['string_literals']['source_layout'];mapping={'value':'value_offset','coder':'coder_offset','hash':'hash_offset','hashIsZero':'hash_is_zero_offset'}
    S.check(shape['class_id']==string['id'] and shape['source_sha256']==string['origin']['sha256'] and
        all(shape[mapping[r['name']]]==r['offset'] for r in sf) and summary['properties']['pool_abi']==2,
        'Normal Module error String shape differs')
    jcls=summary['class_literals'];loader_keys=jcls['loader_keys'];mods=jcls['modules']
    S.check(0<len(mods)<=128 and [m['id'] for m in mods]==list(range(len(mods))) and
        mods[0]==dict(id=0,name='java.base',loader=0) and jcls['source_shape']['module_type']==module['id'] and
        loader_keys==['bootstrap','platform','vanilla-application'] and
        jcls['bootstrap_unnamed_module_slot']==next(m['id'] for m in mods if m['loader']==0 and m['name'] is None),
        'Normal JCLS module/loader identity domain differs')
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    snapshot_file=S.checked(catalog['module_snapshot']);snapshot=S.read(snapshot_file)
    S.check(snapshot['fingerprint']==catalog['module_snapshot_fingerprint'] and
        snapshot['input_fingerprint']==summary['input_fingerprint'],'Locked Module snapshot identity differs')
    keys=[];packages=[]
    for row in mods:
        record=dict(row,start=len(packages),count=0,module_info=None)
        if row['name'] is not None:
            name=row['name'];entry=snapshot['modules'][name];descriptor=entry['descriptor']
            original=snapshot_file.parent/'image'/name/'module-info.class'
            S.check(S.digest(original)['sha256']==entry['sha256'],'Locked module-info.class changed')
            raw=I.Source(original.read_bytes());bodies=[b for n,b in raw.attrs if n=='ModulePackages']
            S.check(len(bodies)<=1 and (bodies or not descriptor['packages']),'ModulePackages attribute availability differs')
            body=bodies[0] if bodies else b'\0\0';r=I.Reader(body)
            actual=[]
            for _ in range(r.u2()):
                tag,text=raw.cp[r.u2()];S.check(tag==20,'Expected source Package constant');actual.append(raw.text(text))
            S.check(r.position==len(body) and sorted(actual)==sorted(descriptor['packages']) and
                len(actual)==len(set(actual)) and descriptor['name']==name,'Locked ModulePackages differs from native package inventory')
            resolved=snapshot['graph']['resolved'][name]['loader'];resolved='vanilla-application' if resolved=='application' else resolved
            S.check(loader_keys[row['loader']]==resolved,'Named Module expected defining loader differs')
            for package in sorted(actual):
                S.check(catalog['packages'][package]==dict(module=name,loader=resolved),'Source Module package ownership differs')
                packages.append(dict(id=len(packages),module=row['id'],name=package,utf16=units(package)))
            record.update(count=len(actual),module_info=S.artifact(original),descriptor=descriptor)
        keys.append(record)
    S.check(len(packages)<=8192,'Closed Module package bitset capacity exceeded')
    loaders=owners['jdk/internal/loader/ClassLoaders'];static=[]
    with zipfile.ZipFile(S.checked(summary['class_state']['index'])) as archive:
        [state]=[r for line in archive.open('classes.jsonl') if (r:=json.loads(line))['class_id']==loaders['id']]
    for name,key,descriptor in [('PLATFORM_LOADER',1,'Ljdk/internal/loader/ClassLoaders$PlatformClassLoader;'),
        ('APP_LOADER',2,'Ljdk/internal/loader/ClassLoaders$AppClassLoader;')]:
        [index]=[i for i,f in enumerate(loaders['fields']) if (f['name'],f['descriptor'],f['access'])==(name,descriptor,0x1a)]
        [field]=[r for r in state['fields'] if r['index']==index]
        S.check(field['reference'] and field['initial_bits']==0 and state['source_sha256']==loaders['origin']['sha256'],
            'Original ClassLoaders static publication differs')
        static.append(dict(loader=key,class_id=loaders['id'],source_sha256=loaders['origin']['sha256'],index=index,name=name,descriptor=descriptor))
    pinned=S.ART/'module-definitions/pinned-sources/jdk-21.0.13+3';sources={n:S.artifact(pinned/n) for n in PINS}
    S.check(all(a['digest']['sha256']==PINS[n] for n,a in sources.items()),'Pinned Module native semantics changed')
    return dict(schema=1,owner=module['id'],methods=methods,original_java=java,original_chain=chain,module_fields=fields,
        source_String_fields=sf,source_String_shape=shape,source_classes={n:c['id'] for n,c in owners.items()},
        loader_statics=static,classloader_unnamed_field=unnamed_field,source_fields_accessed_by_native=[unnamed_field],
        app_unnamed_slot=next(m['id'] for m in mods if m['loader']==2 and m['name'] is None),
        module_keys=keys,package_keys=packages,module_count=len(mods),edge_words=(len(mods)+63)//64,
        maximum_module_slots=128,unnamed_graph_id_base=128,named_module_count=sum(m['name'] is not None for m in mods),
        graph_row=dict(bytes=64,defined=0,open=4,reads_low=8,version_length=16,location_length=20,
            read_all_unnamed=24,specific_unnamed_reads=28,definitions=32,reads_high=40,native_symbols=48),
        missing_JCLS_named_modules=sorted(set(snapshot['graph']['resolved'])-{m['name'] for m in mods if m['name'] is not None}),
        original_module_snapshot=S.artifact(snapshot_file),JCLS_modules=mods,bootstrap_unnamed_slot=jcls['bootstrap_unnamed_module_slot'],
        required_classes=sorted(c['id'] for c in owners.values()),required_java_methods=[r['method'] for r in java],
        required_base_modules=['class_literals','runtime_metadata','properties'],required_provider_families=['normal-throwable-v1'],
        pool_bytes=112,pool_abi=1,native_sources=sources,old_development_Module_kernel=S.artifact(S.ROOT/'native/runtime/module_objects.asm'))


def aliases(meta):
    names=meta['source_classes'];fields={r['name']:r['offset'] for r in meta['module_fields']};sf={r['name']:r['offset'] for r in meta['source_String_fields']}
    result=dict(JMD_MODULE_LAYOUT=f'boom_layout{meta["owner"]}',JMD_MODULE_NAME=fields['name'],JMD_MODULE_LOADER=fields['loader'],
        JMD_STRING_LAYOUT=f'boom_layout{names["java/lang/String"]}',JMD_STRING_VALUE=sf['value'],JMD_STRING_CODER=sf['coder'],
        JMD_LOADER_OWNER=f'boom_class{names["jdk/internal/loader/ClassLoaders"]}',JMD_COUNT=meta['module_count'],
        JMD_PACKAGE_COUNT=len(meta['package_keys']),JMD_BOOT_UNNAMED=meta['bootstrap_unnamed_slot'])
    result['JMD_APP_UNNAMED']=meta['app_unnamed_slot']
    result['JMD_UNNAMED_FIELD']=f"boom_field_map{meta['classloader_unnamed_field']['id']}"
    for i,name in enumerate(ERRORS):
        ident=names[name];method=next(r['method'] for r in meta['original_java'] if r['owner']==name)
        result.update({f'JMD_ERROR_CLASS{i}':f'boom_class{ident}',f'JMD_ERROR_LAYOUT{i}':f'boom_layout{ident}',f'JMD_ERROR_CTOR{i}':f'boom_m{method}'})
    result['JMD_THROWABLE_TYPE']=f'boom_t{names["java/lang/Throwable"]}'
    return result


def native_imports(meta):
    a=aliases(meta);procs={a[f'JMD_ERROR_CTOR{i}'] for i in range(len(ERRORS))}|FOREIGN|{a['JMD_UNNAMED_FIELD']}
    procs|={'boom_heap_contains','boom_object_check','boom_object_new','boom_runtime_row','boom_java_class_bind_module','boom_java_class_bind_loader',
        'boom_java_class_seal','boom_exception_set32','boom_java_property_copy','boom_java_string_literal','boom_trace_enter','boom_trace_leave'}
    data={v for v in a.values() if isinstance(v,str)}-procs
    data|={'boom_java_class_pool','boom_heap_ptr','boom_runtime_type_map','boom_java_properties_string_pool','boom_trace_pool'}
    data|={f"boom_trace_method{m['method']}" for m in meta['methods']}
    data|={f"boom_s{r['class_id']}_{r['index']}" for r in meta['loader_statics']}
    return procs,data


def data(meta):
    def words(label,values):
        return label+' LABEL WORD\n'+''.join(' WORD '+','.join(map(str,values[i:i+16]))+'\n' for i in range(0,len(values),16))
    text=''.join(f'{n} TEXTEQU <{v}>\n' for n,v in aliases(meta).items())+'.const\nALIGN 8\njmod_module_keys LABEL BYTE\n'
    for m in meta['module_keys']:
        label='OFFSET jmod_name'+str(m['id']) if m['name'] else '0'
        text+=f" QWORD {label}\n DWORD {len(units(m['name'])) if m['name'] else 0},{m['loader']},{m['start']},{m['count']},{int(m['name'] is not None)},0\n"
    text+='ALIGN 8\njmod_package_keys LABEL BYTE\n'
    for p in meta['package_keys']:text+=f" QWORD OFFSET jmod_package{p['id']}\n DWORD {len(p['utf16'])},{p['module']}\n"
    for m in meta['module_keys']:
        if m['name']:text+=words(f"jmod_name{m['id']}",units(m['name']))
    for p in meta['package_keys']:text+=words(f"jmod_package{p['id']}",p['utf16'])
    text+='ALIGN 8\njmod_error_types LABEL QWORD\n'
    for i in range(4):text+=f' QWORD OFFSET JMD_ERROR_CLASS{i},OFFSET JMD_ERROR_LAYOUT{i},OFFSET JMD_ERROR_CTOR{i}\n'
    messages=MESSAGES+[(2,f"Module {m['name']} is already defined") for m in meta['module_keys']]
    text+='ALIGN 8\njmod_error_messages LABEL BYTE\n'
    for i,(kind,value) in enumerate(messages):text+=f' QWORD OFFSET jmod_error_text{i}\n DWORD {len(units(value))},{kind}\n'
    for i,(kind,value) in enumerate(messages):text+=words(f'jmod_error_text{i}',units(value))
    text+='''ALIGN 8
jmod_string_pool DWORD 050524F50h,2,0,0
 QWORD OFFSET boom_heap_ptr,OFFSET boom_java_properties_string_pool,0,0,0
 DWORD 0,0
 QWORD 0,0
 QWORD 0,OFFSET boom_java_property_copy,0,OFFSET boom_java_string_literal
.data?
ALIGN 8
PUBLIC boom_module_definitions_rows
boom_module_definitions_rows BYTE JMD_COUNT*64 DUP(?)
PUBLIC boom_module_definitions_package_states
boom_module_definitions_package_states BYTE JMD_PACKAGE_COUNT*32 DUP(?)
jmod_symbol_copies BYTE JMD_COUNT*16384 DUP(?)
.data
ALIGN 8
PUBLIC boom_module_definitions_owned_buffers
boom_module_definitions_owned_buffers QWORD 0
ALIGN 8
'''
    static={r['loader']:f"boom_s{r['class_id']}_{r['index']}" for r in meta['loader_statics']}
    text+=f'''PUBLIC {POOL}
{POOL} DWORD 0444F4D4Ah,1
 QWORD 0
 QWORD OFFSET boom_java_class_pool,OFFSET boom_module_definitions_rows,OFFSET jmod_module_keys
 QWORD OFFSET jmod_package_keys
 DWORD JMD_PACKAGE_COUNT,JMD_COUNT
 QWORD OFFSET boom_heap_ptr,OFFSET jmod_string_pool,OFFSET boom_runtime_type_map,OFFSET JMD_THROWABLE_TYPE
 QWORD OFFSET {static[1]},OFFSET {static[2]},OFFSET JMD_LOADER_OWNER
'''
    return text
