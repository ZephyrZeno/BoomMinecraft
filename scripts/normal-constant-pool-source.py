"""Original compact classfile constant pools for normal reflection wrappers.

ROM is immutable metadata, not executable guest bytecode. Runtime operations
are implemented by the separate normal_constant_pool ASM kernel.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zipfile


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


C=module('normal_cp_original_classes','constructor-provider-source.py')
I=module('normal_cp_original_java','verify-translation-ir.py')
OWNER='java/lang/Class'
CP='jdk/internal/reflect/ConstantPool'
POOL='boom_normal_constant_pool_pool'
SERVICE='boom_normal_constant_pool_service'
ROM_EXPORTS={'boom_constant_pool_directory','boom_constant_pool_entries','boom_constant_pool_bytes'}
CONTROL=set()
FOREIGN=set()
KERNELS=['heap.asm','objects.asm','classes32.asm','frames.asm','java_classes.asm','java_string_intern.asm',
         'runtime_types.asm','runtime_type_index.asm','types.asm','exceptions.asm']
NATIVE_SPECS=[('getSize0','(Ljava/lang/Object;)I'),
    ('getClassAt0','(Ljava/lang/Object;I)Ljava/lang/Class;'),
    ('getClassAtIfLoaded0','(Ljava/lang/Object;I)Ljava/lang/Class;'),
    ('getClassRefIndexAt0','(Ljava/lang/Object;I)I'),
    ('getMethodAt0','(Ljava/lang/Object;I)Ljava/lang/reflect/Member;'),
    ('getMethodAtIfLoaded0','(Ljava/lang/Object;I)Ljava/lang/reflect/Member;'),
    ('getFieldAt0','(Ljava/lang/Object;I)Ljava/lang/reflect/Field;'),
    ('getFieldAtIfLoaded0','(Ljava/lang/Object;I)Ljava/lang/reflect/Field;'),
    ('getMemberRefInfoAt0','(Ljava/lang/Object;I)[Ljava/lang/String;'),
    ('getNameAndTypeRefIndexAt0','(Ljava/lang/Object;I)I'),
    ('getNameAndTypeRefInfoAt0','(Ljava/lang/Object;I)[Ljava/lang/String;'),
    ('getIntAt0','(Ljava/lang/Object;I)I'),('getLongAt0','(Ljava/lang/Object;I)J'),
    ('getFloatAt0','(Ljava/lang/Object;I)F'),('getDoubleAt0','(Ljava/lang/Object;I)D'),
    ('getStringAt0','(Ljava/lang/Object;I)Ljava/lang/String;'),
    ('getUTF8At0','(Ljava/lang/Object;I)Ljava/lang/String;'),('getTagAt0','(Ljava/lang/Object;I)B')]
UNSUPPORTED_OPERATIONS={3,5,6,7,8}
POLICY=dict(normal_source_layouts=True,constantPoolOop_is_actual_owner_Class_mirror=True,
    wrapper_class_initialization_required=True,wrapper_Java_constructor_invoked_by_VM=False,
    represented_class_initialized=False,original_Java_annotation_parser_preserved=True,
    forced_class_resolution_scope='statically_proven_original_same_module_public_or_same_runtime_package_only',
    unproven_cross_module_or_loader_resolution='context20',
    original_constant_pool_indices_and_wide_holes=True,original_numeric_bits_preserved=True,
    readonly_original_raw_CP_ROM=True,ROM_contains_executable_sections=False,
    IfLoaded_not_inferred_from_metadata_or_clinit=True,IfLoaded_supported=False,
    methodAt_or_fieldAt_supported=False,Java_unused_native_token_argument_ignored=True,
    source_transform_chain='original_locked_no_transforms',dynamic_redefinition=False,
    heap_nonmoving=True,collection_requires_quiescence=True,automatic_GC=False)
PINS={
    'ConstantPool.java':('b904eacc1803827dbeedc256de81aaba386640f42c5b2e38c493e05a31cb8688','src/java.base/share/classes/jdk/internal/reflect/ConstantPool.java'),
    'ConstantPool.c':('2ddc5e5d66a738a6f4a7bb736aef6c4f52b7f77229da4f2d974f29f81b1fa500','src/java.base/share/native/libjava/ConstantPool.c'),
    'jvm.cpp':('84436b103fb7869e445bac95d2e82e9de9160c2da327a4cf54f4e84555150ad9','src/hotspot/share/prims/jvm.cpp'),
    'javaClasses.cpp':('15d8e8a8ecd9e2ff9d74eb4d3651de0ee134f2bb4efbfed68ac3b3c8fce64313','src/hotspot/share/classfile/javaClasses.cpp')}


def source_pins(S):
    result={}
    for name,(sha,relative) in PINS.items():
        path=S.ART/'normal-constant-pool/pinned-sources/jdk-21.0.13+3'/name
        S.check(S.digest(path)['sha256']==sha,'Pinned original ConstantPool source changed: '+name)
        result[name]=dict(**S.artifact(path),url='https://raw.githubusercontent.com/openjdk/jdk21u/jdk-21.0.13%2B3/'+relative)
    return result


def parse_class_pool(data):
    """Retain raw bytes/indices/holes; floats never pass through host floats."""
    R=C.RAW.Reader(data)
    C.check(R.number(4)==0xcafebabe,'Original CP class magic differs');minor=R.number(2);major=R.number(2)
    count=R.number(2);C.check(count>=1,'Empty constant pool count')
    rows=[(0,-1,None,None)]*count;at=10;index=1
    while index<count:
        C.check(at<len(data),'Truncated original CP tag')
        start=at;tag=data[at];at+=1;one=two=None
        def take(size):
            nonlocal at
            C.check(at+size<=len(data),'Truncated original CP entry');value=data[at:at+size];at+=size;return value
        if tag==1:
            amount=int.from_bytes(take(2),'big');encoded=take(amount)
            C.check(not any(byte>=0xf0 for byte in encoded),'Classfile MUTF8 cannot contain a four-byte UTF8 lead')
            one=C.RAW.modified_utf8(encoded)
        elif tag in (3,4):one=int.from_bytes(take(4),'big')
        elif tag in (5,6):one=int.from_bytes(take(8),'big')
        elif tag in (7,8,16,19,20):one=int.from_bytes(take(2),'big')
        elif tag in (9,10,11,12,17,18):one=int.from_bytes(take(2),'big');two=int.from_bytes(take(2),'big')
        elif tag==15:one=take(1)[0];two=int.from_bytes(take(2),'big')
        else:raise ValueError('Unsupported original CP tag '+str(tag))
        rows[index]=(tag,start-10,one,two)
        if tag in (5,6):
            C.check(index+1<count,'Wide CP entry has no following reserved slot');index+=1
        index+=1
    C.check(at+6<=len(data),'Missing original class header after CP')
    def ref(index,tags):
        C.check(type(index) is int and 0<index<count and rows[index][0] in tags,'Invalid original CP reference');return rows[index]
    for tag,_,one,two in rows[1:]:
        if tag in (7,8,16,19,20):ref(one,{1})
        elif tag in (9,10,11):ref(one,{7});ref(two,{12})
        elif tag==12:ref(one,{1});ref(two,{1})
        elif tag in (17,18):ref(two,{12})
        elif tag==15:
            C.check(1<=one<=9,'Invalid method handle kind')
            ref(two,{9} if one<=4 else {10} if one in (5,8) else {11} if one==9 else {10,11})
    flags,owner=struct.unpack_from('>HH',data,at)
    owner_name=ref(ref(owner,{7})[2],{1})[2]
    return dict(major=major,minor=minor,access=flags,name=owner_name,entries=rows,raw=data[10:at])


def class_reference_access(owner,target,jcls,types,classes):
    """Positive proof only. A catalogue entry never proves dynamic loading/access.

    Original same-module public classes and the original runtime package need no
    mutable read/export graph assumptions. Other valid links remain a real gap.
    Array accessibility follows its ultimate component, as JVM resolution does.
    """
    if owner not in jcls or target is None or target not in jcls or target not in types:return False
    seen=set()
    while types[target]['kind']==3:
        if target in seen:return False
        seen.add(target);target=types[target]['parent_component']
        if target not in jcls or target not in types:return False
    if types[target]['kind']==0:return True
    if types[target]['kind'] not in (1,2):return False
    if not (0<=owner<len(classes) and 0<=target<len(classes)):return False
    one,two=jcls.get(owner),jcls[target]
    if one is None or one['module']!=two['module'] or one['loader']!=two['loader']:return False
    if classes[target]['access']&1:return True
    return one['loader']==two['loader'] and \
        classes[owner]['name'].rpartition('/')[0]==classes[target]['name'].rpartition('/')[0]


def build_rom(summary,classes,S,source_inputs=None):
    types,_,available,resolve=C.inputs(summary,classes) if source_inputs is None else source_inputs
    capacity=summary['runtime_metadata']['type_capacity'];by_type={r['id']:r for r in types};kinds={i:r['kind'] for i,r in by_type.items()}
    with zipfile.ZipFile(C.artifact(summary['class_literals']['index'])) as index:
        jcls={r['type_id']:r for line in index.read('types.jsonl').splitlines() if (r:=json.loads(line))}
    S.check([r['id'] for r in classes]==list(range(len(classes))),'Original CP class identifiers are not dense')
    directory=bytearray(capacity*24);entries=bytearray();raw=bytearray();inventory=hashlib.sha256();counts={};sources=C.RawClasses(summary)
    original_count=0;unresolved=0;unproven_access=0
    try:
        for cls in classes:
            ident=cls['id'];S.check(0<=ident<capacity,'CP class ID outside the normal type capacity')
            status=1 if ident in available else 3
            if cls.get('parse_error') or cls['access']&0x8000 or cls['origin'].get('generated'):
                struct.pack_into('<6I',directory,ident*24,len(entries)//8,0,3,len(raw),0,0);continue
            parsed=parse_class_pool(sources.read(cls));S.check(parsed['name']==cls['name'] and parsed['access']==cls['access'],
                'Original CP owner identity differs')
            first=len(entries)//8;begin=len(raw);payload=parsed['raw'];items=parsed['entries']
            S.check(begin+len(payload)<0x80000000 and first+len(items)<=0xffffffff,'CP ROM exceeds the supported bounded image size')
            for tag,offset,one,two in items:
                target=0xffffffff
                if tag==7:
                    name=items[one][2];target=resolve(cls['origin']['loader'],name if name.startswith('[') else 'L'+name+';')
                    if target is None:target=0xffffffff;unresolved+=1
                    elif not class_reference_access(ident,target,jcls,by_type,classes):target=0xffffffff;unproven_access+=1
                entries.extend(struct.pack('<II',0xffffffff if offset<0 else begin+offset,target))
                counts[str(tag)]=counts.get(str(tag),0)+1
            raw.extend(payload)
            struct.pack_into('<6I',directory,ident*24,first,len(items),status,begin,len(payload),0)
            inventory.update(json.dumps((ident,cls['origin']['sha256'],len(items),hashlib.sha256(payload).hexdigest()),separators=(',',':')).encode()+b'\n')
            original_count+=1
        for ident in range(len(classes),capacity):
            status=2 if ident in available and kinds[ident] in (0,3) else 3
            struct.pack_into('<6I',directory,ident*24,len(entries)//8,0,status,len(raw),0,0)
    finally:sources.close()
    entry_offset=(len(directory)+7)&~7;raw_offset=(entry_offset+len(entries)+15)&~15
    payload=bytes(directory)+b'\0'*(entry_offset-len(directory))+bytes(entries)+b'\0'*(raw_offset-entry_offset-len(entries))+bytes(raw)
    meta=dict(schema=1,original_class_pools=original_count,type_capacity=capacity,constant_pool_entries=len(entries)//8,
        raw_CP_bytes=len(raw),directory_bytes=len(directory),entry_bytes=8,directory_row_bytes=24,
        entry_section_offset=entry_offset,raw_section_offset=raw_offset,readonly_section_bytes=len(payload),
        readonly_section_sha256=hashlib.sha256(payload).hexdigest(),original_class_CP_inventory_sha256=inventory.hexdigest(),
        original_tag_counts=counts,unresolved_class_references=unresolved,unproven_class_reference_access=unproven_access)
    return meta,payload


def rom_coff(payload,meta):
    """One deterministic readonly data section, three symbols, no code/relocs."""
    C.check(len(payload)==meta['readonly_section_bytes'] and hashlib.sha256(payload).hexdigest()==meta['readonly_section_sha256'],
        'CP ROM payload differs')
    symbol_at=(64+len(payload)+3)&~3;strings=bytearray(struct.pack('<I',4));symbols=[]
    symbols.append(struct.pack('<8sIhHBB',b'.rdata',0,1,0,3,1))
    symbols.append(struct.pack('<IHHIhBBH',len(payload),0,0,0,0,0,0,0))
    for name,value in [('boom_constant_pool_directory',0),('boom_constant_pool_entries',meta['entry_section_offset']),
                       ('boom_constant_pool_bytes',meta['raw_section_offset'])]:
        offset=len(strings);strings.extend(name.encode()+b'\0')
        symbols.append(struct.pack('<IIIhHBB',0,offset,value,1,0,2,0))
    struct.pack_into('<I',strings,0,len(strings))
    header=struct.pack('<HHIIIHH',0x8664,1,0,symbol_at,5,0,0)
    section=struct.pack('<8sIIIIIIHHI',b'.rdata',0,0,len(payload),64,0,0,0,0,0x40500040)
    return header+section+b'\0'*4+payload+b'\0'*(symbol_at-64-len(payload))+b''.join(symbols)+strings


def index(summary,classes,S):
    names={row['name']:row for row in classes if row['origin']['loader']=='bootstrap'}
    wanted={name:names[name] for name in (OWNER,CP,'java/lang/String','java/lang/IllegalArgumentException','java/lang/Throwable')}
    declarations=[];java=[]
    targets={(CP,n,d):op for op,(n,d) in enumerate(NATIVE_SPECS,1)}
    targets[OWNER,'getConstantPool','()Ljdk/internal/reflect/ConstantPool;']=0
    for name,cls in wanted.items():
        S.check(cls['origin']['source_id']=='jdk:java.base' and not cls['origin'].get('generated'),'Original java.base CP classes required')
        raw=I.Source(S.original_class(summary,cls))
        S.check(raw.name==name and len(raw.methods)==len(cls['method_ids']),'Original CP method inventory differs')
        for ident,m in zip(cls['method_ids'],raw.methods):
            code=raw.code(m);key=name,m['name'],m['descriptor']
            row=dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],loader='bootstrap',source_id='jdk:java.base',
                owner=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],
                code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None)
            if key in targets:
                S.check(code is None and m['access']==(0x100 if name==OWNER else 0x102),'Original CP native declaration differs')
                declarations.append(dict(row,operation=targets[key]))
            elif name==CP or key in [('java/lang/IllegalArgumentException','<init>','(Ljava/lang/String;)V'),
                                     ('java/lang/Throwable','fillInStackTrace','()Ljava/lang/Throwable;')]:
                S.check(code is not None,'Original CP Java wrapper/callback is missing');java.append(row)
    S.check(len(declarations)==19 and len([r for r in declarations if r['operation']==0])==1,'Original CP native inventory differs')
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layouts={r['name']:r for line in stream if (r:=json.loads(line))['name'] in wanted and r['class_id']==wanted[r['name']]['id']}
    S.check(set(layouts)==set(wanted) and all(r['diagnostic'] is None and r['candidate'] is not None and
        r['source_sha256']==wanted[n]['origin']['sha256'] for n,r in layouts.items()),'Normal CP source layouts differ')
    def offset(cls,name,desc):
        rows=[r for r in layouts[cls]['candidate']['fields'] if (r['member']['owner'],r['member']['name'],r['member']['descriptor'])==
            (wanted[cls]['id'],name,desc)]
        S.check(len(rows)==1,'Normal CP source field missing: '+name);return rows[0]['offset']
    S.check(wanted[CP]['fields']==[dict(name='constantPoolOop',descriptor='Ljava/lang/Object;',access=2)],'Original wrapper field changed')
    inputs=C.inputs(summary,classes);types,runtime,_,_=inputs
    [array_type]=[r for r in types if (r['defining_loader'],r['name'])==('bootstrap','[Ljava/lang/String;')]
    [array]=[r for r in runtime if r['type_id']==array_type['id']]
    rom,_=build_rom(summary,classes,S,inputs)
    error=[r for r in java if r['owner']=='java/lang/IllegalArgumentException' and r['name']=='<init>']
    stack=[r for r in java if r['owner']=='java/lang/Throwable' and r['name']=='fillInStackTrace']
    S.check(len(error)==len(stack)==1,'Original CP typed-error callback changed')
    return dict(schema=1,owner=wanted[OWNER]['id'],pool_class=wanted[CP]['id'],string_class=wanted['java/lang/String']['id'],
        error_class=wanted['java/lang/IllegalArgumentException']['id'],throwable_class=wanted['java/lang/Throwable']['id'],
        fields=dict(constantPoolOop=offset(CP,'constantPoolOop','Ljava/lang/Object;')),
        String_fields=dict(value=offset('java/lang/String','value','[B'),coder=offset('java/lang/String','coder','B')),
        compact_strings=summary['string_literals']['compact_strings'],string_array=array,
        methods=sorted([r for r in declarations if r['operation'] not in UNSUPPORTED_OPERATIONS],key=lambda r:r['operation']),
        unsupported_original_natives=sorted([r for r in declarations if r['operation'] in UNSUPPORTED_OPERATIONS],key=lambda r:r['operation']),
        all_original_native_declarations=sorted(declarations,key=lambda r:r['operation']),original_java=java,
        error_constructor=error[0],required_java_methods=[r['method'] for r in error+stack],
        required_classes=sorted(r['id'] for r in wanted.values()),required_provider_families=['normal-throwable-v1'],
        required_base_modules=['class_literals','string_intern','runtime_metadata'],native_sources=source_pins(S),
        ROM=rom,pool_bytes=192,pool_abi=1,extra_static_Java_oop_roots=False,
        String_factory_kernel=S.artifact(S.ROOT/'native/providers/normal_methods.asm.inc'),
        String_factory_normalization='private helper and branch labels only; all factory instructions and pool offsets preserved',
        source_Java_Code_selection_required_for_CP_read=False)


def native_imports(meta):
    procs={'boom_heap_alloc','boom_heap_contains','boom_object_check','boom_object_new','boom_class_ensure32',
        'boom_java_class_typeid','boom_java_class_load','boom_java_string_intern','boom_exception_set32',
        'boom_trace_enter','boom_trace_leave',f"boom_m{meta['error_constructor']['method']}"}
    data=ROM_EXPORTS|{'boom_heap_ptr','boom_java_class_pool','boom_java_string_intern_pool','boom_runtime_type_map','boom_trace_pool',
        meta['string_array']['tag_symbol'],f"boom_layout{meta['pool_class']}",f"boom_class{meta['pool_class']}",
        f"boom_layout{meta['string_class']}",f"boom_class{meta['error_class']}",f"boom_layout{meta['error_class']}",
        f"boom_t{meta['throwable_class']}"}
    data|={f"boom_class{r['class_id']}" for r in meta['methods']}
    data|={f"boom_trace_method{r['method']}" for r in meta['methods']}
    return procs,data


def data(meta):
    error=meta['error_class'];cp=meta['pool_class'];string=meta['string_class'];rom=meta['ROM']
    text=f'''.const
ALIGN 8
PUBLIC {POOL}
{POOL} DWORD 04E435050h,1,{rom['type_capacity']},{rom['constant_pool_entries']}
 QWORD OFFSET boom_java_class_pool,OFFSET boom_heap_ptr,OFFSET boom_constant_pool_directory,OFFSET boom_constant_pool_entries
 QWORD OFFSET boom_layout{cp},OFFSET {meta['string_array']['tag_symbol']},0,OFFSET boom_layout{string}
 QWORD OFFSET boom_class{cp},0,OFFSET boom_java_string_intern_pool
 DWORD {meta['String_fields']['value']},{meta['String_fields']['coder']}
 QWORD 264
 DWORD 24,8,{meta['fields']['constantPoolOop']},{int(meta['compact_strings'])}
 QWORD OFFSET boom_constant_pool_bytes,{rom['raw_CP_bytes']}
 QWORD OFFSET boom_class{error},OFFSET boom_layout{error},OFFSET boom_m{meta['error_constructor']['method']}
 QWORD OFFSET boom_t{meta['throwable_class']},OFFSET boom_runtime_type_map
'''
    for label,value in [('bounds','Constant pool index out of bounds'),('type','Wrong type at constant pool index')]:
        raw=value.encode('utf-16-le');text+='ncp_'+label+'_message LABEL BYTE\n'
        text+=''.join(' BYTE '+','.join(map(str,raw[at:at+32]))+'\n' for at in range(0,len(raw),32))
        text+=f'NCP_{label.upper()}_UNITS EQU {len(raw)//2}\n'
    return text
