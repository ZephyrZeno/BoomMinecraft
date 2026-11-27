"""Original Windows NIO attribute native/Java/Frame/error projection.

The normal Frame/error callback, query arena and borrowed-span helper remain
four independent COFF units. This tool does not alter Java fields or Code.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
OWNER='sun/nio/fs/WindowsNativeDispatcher'
POOL='boom_provider_windows_nio_file_attributes_pool'
SERVICE='boom_provider_windows_nio_file_attributes_service'
ERROR_HELPER='boom_windows_nio_throw_error'
SPECS=[('GetFileAttributesEx0','(JJ)V',0)]
QUERY=ROOT/'native/providers/windows_nio_file_attributes.asm.inc'
ERROR=ROOT/'native/providers/windows_nio_throw_error.asm.inc'
SPAN=ROOT/'native/providers/native_memory_borrowed_span.asm.inc'
ABI=ROOT/'native-config/windows-nio-file-attributes-abi.json'
CORE=ROOT/'native/kernels/native_memory_owner64.asm.inc'
FIELD_MODEL=ROOT/'scripts/windows-nio-dispatcher-source.py'
KERNELS=(QUERY,ERROR,SPAN)


def check(value,message):
    if not value:raise ValueError(message)


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=sha))


def checked(row):
    row_digest=row.get('digest',row);got=artifact(row['path'])
    check(all(got['digest'][key]==row_digest[key] for key in ('size','sha256')),'Actual model input changed: '+row['path'])
    return Path(got['path'])


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def validate_abi(abi):
    check(abi['schema']=='boom-windows-nio-file-attributes-abi-v1' and abi['operations']=={'GetFileAttributesEx0':0} and
        (abi['capacity'],abi['slot_bytes'],abi['pool_bytes'],abi['pool_magic'],abi['pool_ABI'])==(256,192,64,'0x54414657',1),
        'Exact query capacity/operation/pool ABI differs')
    check(abi['pool_offsets']==dict(magic=0,abi=4,bytes=8,state=12,slots=16,roots=24,count=32,stride=36,
        publication_lock=40,active=44,sequence=48,pending=56,drainer=60) and
        abi['pool_states']==dict(admitting=0,draining=1,closed=2),'Query publication/lifecycle fields differ')
    check(abi['slot_offsets']==dict(path_Span64=0,output_Span64=64,state_DWORD=128,Win32_last_error_DWORD=132,
        Win32_result_DWORD=136,native_cleanup_error_DWORD=140,opaque_Context_key_QWORD=144,call_sequence_QWORD=152,
        operation_DWORD=160,flags_DWORD=164,reserved_QWORD_0=168,reserved_QWORD_1=176,reserved_QWORD_2=184) and
        abi['slot_states']==dict(free=0,active=1,pending_cleanup=2),'Persistent native slot offsets differ')
    check(abi['normal_native_service']['symbol']==SERVICE and
        abi['normal_native_service']['argv_byte_offsets']==dict(path_address_QWORD=0,output_address_QWORD=8) and
        abi['exception_helper']['symbol']==ERROR_HELPER,'Normal Frame/error callback ABI differs')
    check(abi['Span64_ABI']['fields']==dict(owner_QWORD=0,address_QWORD=8,minimum_bytes_QWORD=16,remaining_QWORD=24,
        token_QWORD=32,generation_QWORD=40,flags_DWORD=48,status_DWORD=52,os_error_DWORD=56,reserved_DWORD=60) and
        abi['Span64_ABI']['flags']==dict(read=1,write=2,read_write=3),'Consumer Span64 layout differs')
    span=abi['Span64_contract']
    check(span['schema']=='boom-native-memory-borrowed-span-abi-v1' and span['span_bytes']==64 and
        span['offsets']==dict(owner_q=0,address_q=8,minimum_bytes_q=16,remaining_logical_bytes_q=24,lease_token_q=32,
            allocation_generation_q=40,permissions_d=48,status_d=52,os_error_d=56,reserved_d=60) and
        set(span['exports'])=={'boom_native_memory_span_acquire','boom_native_memory_span_release'} and
        set(span['status_codes'])=={'0','1','2','3','4','5','7','9','12'},'Core Span64 helper ABI differs')
    check(abi['native_root_spans']==[dict(symbol='boom_windows_nio_attributes_throwable_roots',count=256,
            kind='pending native WindowsException across original source constructor')] and
        abi['control_exports']==['boom_windows_nio_attributes_drain'] and
        abi['external_native_dependencies']==['boom_native_memory_service','boom_provider_owned_unsafe_pool'],
        'Exact physical root/control/dependency contract differs')


def module(name,path):
    spec=importlib.util.spec_from_file_location('Windows_attrs_'+name,path);result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result);return result


def references(I,source,code):
    result=[]
    for row in I.stream(code):
        value=row['operand'];constant=value.get('Constant') if isinstance(value,dict) else None
        if row['opcode']==0xb9:constant=value['Interface']['constant']
        if constant is not None:result.append(dict(pc=row['pc'],opcode=row['opcode'],constant=constant,symbol=source.symbol(constant)))
    return result


def bind(state_file,source_file,parent_file,pinned_C,slot_abi):
    W=module('normal_field_records',FIELD_MODEL)
    I=module('original_Code',ROOT/'scripts/verify-translation-ir.py')
    R=module('original_Frame',ROOT/'scripts/verify-batch-frames.py')
    state,closure,parent=map(read,(state_file,source_file,parent_file));seal=read(checked(parent['source_seal']))
    check(artifact(state_file)==parent['input_state']==seal['input_state'] and artifact(source_file)==seal['source_manifest'],
        'Exact original Main source/state required')
    check(read(checked(seal['source_full_verification']))['verified'] is True,'Original complete source verification required')
    for name,sha in state['tool_sources'].items():check(artifact(ROOT/name)['digest']['sha256']==sha,'Current source tools changed: '+name)
    abi=read(slot_abi)
    validate_abi(abi)
    check(abi==read(ABI) and abi['capacity']==256 and abi['slot_bytes']==192 and abi['pool_bytes']==64 and
        abi['Span64_contract']['span_bytes']==64 and abi['Span64_contract']['CoreKernel_sha256']==artifact(CORE)['digest']['sha256'],
        'Exact current query/Span64/Owner ABI required')
    dependencies=read(checked(parent['composite']))
    check(dependencies['metadata']['input_state']==artifact(state_file) and
        artifact(checked(dependencies['metadata']['owner']['source']))==artifact(CORE),'Parent native owner uses another source/state')
    for name in ('owned-services','owned-core'):
        unit=dependencies['units'][name]
        check(sum(row==unit['object'] for row in parent['objects'])==1,'Parent must link the exact native owner dependency once: '+name)
        checked(unit['object']);checked(unit['assembly'])
    c_pin=artifact(pinned_C);check(c_pin['digest']['sha256']=='d9c4e8b26dfeaee66474473d6f7f262d3cb111a3130ee27c4fcddacc43bb74fb',
        'Exact upstream native implementation changed')
    summary_file=Path(closure['batch'])/'summary.json';summary=read(summary_file);plan=Path(closure['plan'])
    needed={OWNER,'sun/nio/fs/WindowsException','sun/nio/fs/WindowsFileAttributes','sun/nio/fs/NativeBuffer',
        'sun/nio/fs/NativeBuffers','java/lang/Throwable','java/lang/Exception'}
    classes={}
    for line in (plan/'classes.jsonl').open(encoding='utf-8'):
        row=json.loads(line)
        if row['name'] in needed and row['origin']['loader']=='bootstrap':classes[row['name']]=row
    check(set(classes)==needed,'Original NIO/Throwable source classes unavailable')
    selected={r['class_id']:r for r in closure['selected_classes']};layouts={}
    for line in checked(summary['layouts']).open(encoding='utf-8'):
        row=json.loads(line)
        if row['class_id'] in {c['id'] for c in classes.values()}:layouts[row['class_id']]=row
    inputs=[artifact(p) for p in (state_file,source_file,parent_file,pinned_C,FIELD_MODEL,slot_abi,ABI,CORE,__file__,
        QUERY,ERROR,SPAN,summary_file,plan/'classes.jsonl',I.__file__,R.__file__)]
    inputs.append(parent['composite'])
    for name in ('owned-services','owned-core'):
        inputs += [dependencies['units'][name]['assembly'],dependencies['units'][name]['object']]
    inputs += [parent['source_seal'],seal['source_full_verification'],summary['layouts'],summary['frames']['original_system_catalog']]
    image=checked(summary['frames']['original_system_catalog']).parent/'image';catalog={};constants={}
    for name,cls in classes.items():
        path=(image/cls['origin']['jar_entry']).resolve();check(path.is_relative_to(image.resolve()),'Original class escaped image')
        item=artifact(path);raw=path.read_bytes();source=I.Source(raw);_,annotated=R.original_methods(raw)
        check(item['digest']['sha256']==cls['origin']['sha256'] and int.from_bytes(raw[6:8],'big')==65 and
            cls['origin']['source_id']=='jdk:java.base' and cls['id'] in selected and
            selected[cls['id']]['source_sha256']==cls['origin']['sha256'],'Locked normal source class differs')
        methods=[]
        for ident,method,annotation in zip(cls['method_ids'],source.methods,annotated):
            code=source.code(method);sha=hashlib.sha256(code['bytes']).hexdigest() if code else None
            chosen=closure['selected_methods'].get(str(ident));present=bool(chosen and chosen['code_sha256']==sha and
                chosen['source_sha256']==cls['origin']['sha256']) if code else False
            methods.append(dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],owner=name,
                loader='bootstrap',source_id='jdk:java.base',name=method['name'],descriptor=method['descriptor'],access=method['access'],
                code_sha256=sha,frame_flags=R.flags(name,annotation,code is None,False,False),selected_Java=present,
                original_Code_hex=code['bytes'].hex() if code else None,
                references=references(I,source,code['bytes']) if code else []))
        catalog[name]=dict(source_class=cls,normal_layout=layouts[cls['id']],selected_source_class=selected[cls['id']],
            original_class=item,methods=methods)
        if name=='sun/nio/fs/WindowsFileAttributes':
            for field in source.fields:
                if 'FILE_ATTRIBUTE_DATA' in field['name']:
                    constant=source.cp[field['constant_value']];check(constant[0]==3,'Expected actual original Integer ConstantValue')
                    constants[field['name']]=int.from_bytes(constant[1],'big',signed=True)
        inputs.append(item)
    def method(owner,name,descriptor):
        [result]=[r for r in catalog[owner]['methods'] if (r['name'],r['descriptor'])==(name,descriptor)];return result
    natives=[dict(method(OWNER,name,descriptor),operation=op) for name,descriptor,op in SPECS]
    check(all(r['access']==0x10a and r['code_sha256'] is None and r['frame_flags']==32 for r in natives),
        'Original private static native Frame declarations differ')
    callback=method('sun/nio/fs/WindowsException','<init>','(I)V');fill=method('sun/nio/fs/WindowsException','fillInStackTrace','()Ljava/lang/Throwable;')
    wrappers=[method(OWNER,'GetFileAttributesEx','(Ljava/lang/String;J)V'),method(OWNER,'asNativeBuffer','(Ljava/lang/String;)Lsun/nio/fs/NativeBuffer;'),
        method('sun/nio/fs/NativeBuffers','getNativeBufferFromCache','(I)Lsun/nio/fs/NativeBuffer;'),
        method('sun/nio/fs/NativeBuffers','allocNativeBuffer','(I)Lsun/nio/fs/NativeBuffer;'),
        method('sun/nio/fs/NativeBuffers','getNativeBuffer','(I)Lsun/nio/fs/NativeBuffer;'),
        method('sun/nio/fs/NativeBuffers','releaseNativeBuffer','(Lsun/nio/fs/NativeBuffer;)V'),
        method('sun/nio/fs/NativeBuffer','<init>','(I)V'),method('sun/nio/fs/NativeBuffer','close','()V'),
        method('sun/nio/fs/WindowsFileAttributes','get','(Lsun/nio/fs/WindowsPath;Z)Lsun/nio/fs/WindowsFileAttributes;'),
        method('sun/nio/fs/WindowsFileAttributes','fromFileAttributeData','(JI)Lsun/nio/fs/WindowsFileAttributes;')]
    check(all(r['selected_Java'] for r in [callback,fill,*wrappers]),'Required original Java Code is not in this closure')
    check(fill['original_Code_hex']=='2ab0','Actual WindowsException stack trace override changed')
    expected_constants=dict(SIZEOF_FILE_ATTRIBUTE_DATA=36,OFFSETOF_FILE_ATTRIBUTE_DATA_ATTRIBUTES=0,
        OFFSETOF_FILE_ATTRIBUTE_DATA_CREATETIME=4,OFFSETOF_FILE_ATTRIBUTE_DATA_LASTACCESSTIME=12,
        OFFSETOF_FILE_ATTRIBUTE_DATA_LASTWRITETIME=20,OFFSETOF_FILE_ATTRIBUTE_DATA_SIZEHIGH=28,OFFSETOF_FILE_ATTRIBUTE_DATA_SIZELOW=32)
    check(constants==expected_constants,'Original parsed classfile struct size/offset constants changed')
    frame=read(checked(closure['runtime_frame_overlay']['reference']['manifest']))
    inputs += [closure['runtime_frame_overlay']['reference']['manifest'],closure['runtime_frame_overlay']['reference']['verification'],frame['object']]
    target={'boom_trace_method'+str(r['method']):32 for r in natives}
    target['boom_layout'+str(callback['class_id'])]=24;target['boom_class'+str(callback['class_id'])]=16
    actual={};objects=[parent['objects'][0],frame['object']]+[u['object'] for u in summary['runtime_metadata']['units']]
    for obj in objects:
        check(any(r['path']==obj['path'] for r in parent['objects']),'Required source descriptor data is not linked in the parent')
        checked(obj);inputs.append(obj)
        for name,value in W.coff_records(obj['path'],target).items():
            check(name not in actual,'Duplicate descriptor in linked parent');actual[name]=dict(value,object=obj)
    check(set(actual)==set(target),'Actual native Frame/error class/layout data missing')
    for native in natives:
        row=actual['boom_trace_method'+str(native['method'])];raw=bytes.fromhex(row['bytes'])
        check(struct.unpack_from('<II',raw)==(native['method'],32) and struct.unpack_from('<I',raw,20)[0]==native['class_id'] and
            [(r['offset'],r['type'],r['target']) for r in row['relocations']]==[(8,1,'boom_t'+str(native['class_id']))],
            'Actual original native Frame record differs')
    error_layout=catalog['sun/nio/fs/WindowsException']['normal_layout'];candidate=error_layout['candidate']
    layout=bytes.fromhex(actual['boom_layout'+str(callback['class_id'])]['bytes'])
    check(error_layout['diagnostic'] is None and struct.unpack('<IIQII',layout)==(0x4f424a43,2,candidate['payload_bytes'],
        candidate['reference_prefix'],len(candidate['fields'])),'Actual original exception layout differs')
    for row in inputs:checked(row)
    return dict(schema=1,scope='GetFileAttributesEx0_original_native_Java_Frame_error_and_native_query_source_projection',
        input_state=artifact(state_file),source_selection=artifact(source_file),source_full_verification=seal['source_full_verification'],
        parent_overlay=artifact(parent_file),runtime=parent['runtime'],native_methods=natives,implemented_service_operations=[0],
        priority_native=natives[0],original_Java_wrappers=wrappers,error_constructor=callback,error_fillInStackTrace=fill,
        error_class=catalog['sun/nio/fs/WindowsException'],throwable_type=classes['java/lang/Throwable']['id'],
        source_classes=catalog,actual_original_records=actual,original_struct_constants=constants,
        slot_ABI=artifact(slot_abi),ABI=abi,kernel_sources={p.name:artifact(p) for p in KERNELS},
        native_root_spans=abi['native_root_spans'],control_exports=abi['control_exports'],
        external_native_dependencies=abi['external_native_dependencies'],native_owner_parent=parent['composite'],
        required_base_modules=['runtime_metadata','frames'],required_classes=sorted(c['id'] for c in classes.values()),
        required_Java_methods=[callback['method']],no_new_Java_Code_or_class_selection_required=True,
        helper_temporary_root='Caller supplies an exact trusted temporary Throwable root cell; producer does not invent/auto-register a GC root bank.',
        inputs=inputs,SourceV_repeated=False,query_service_source_provided=True,Win32_or_Java_executed=False,registered=False)


def normal_frames(meta,operations=(0,)):
    R=module('Frame_adapter',ROOT/'scripts/verify-batch-frames.py');methods=[r for r in meta['native_methods'] if r['operation'] in operations]
    data={POOL,'boom_trace_pool'}|{'boom_class'+str(r['class_id']) for r in methods}|{'boom_trace_method'+str(r['method']) for r in methods}
    procs={'boom_class_ensure32','boom_trace_enter','boom_trace_leave',SERVICE}
    text='option casemap:none\n'+''.join('EXTERN '+n+(':PROC\n' if n in procs else ':BYTE\n') for n in sorted(data|procs));exports=set()
    for row in methods:
        names={'boom_m'+str(row['method']),'boom_m'+str(row['method'])+'_native'};exports|=names
        text+=''.join('PUBLIC '+n+'\n' for n in sorted(names))+R.native_adapter(row['method'],row['class_id'],POOL,SERVICE,row['operation'])
    return text+'\nEND\n',exports,procs|data


def exception_helper(meta):
    ctor=meta['error_constructor'];err=ctor['class_id'];throwable=meta['throwable_type']
    procs={'boom_class_ensure32','boom_object_new','boom_exception_set32','boom_m'+str(ctor['method'])}
    data={'boom_heap_ptr','boom_runtime_type_map','boom_class'+str(err),'boom_layout'+str(err),'boom_t'+str(throwable)}
    text='option casemap:none\n'+''.join('EXTERN '+n+(':PROC\n' if n in procs else ':BYTE\n') for n in sorted(procs|data))
    text+=f'WNFA_ERROR_CLASS TEXTEQU <boom_class{err}>\nWNFA_ERROR_LAYOUT TEXTEQU <boom_layout{err}>\nWNFA_ERROR_CTOR TEXTEQU <boom_m{ctor["method"]}>\nWNFA_THROWABLE_TYPE TEXTEQU <boom_t{throwable}>\n'
    text+=ERROR.read_text()+'\nEND\n'
    return text,{ERROR_HELPER},procs|data


def fragment(path):
    """Wrap a frozen standalone fragment without rewriting instructions/data."""
    import re
    text=path.read_text(encoding='utf-8')
    exports=set(re.findall(r'^PUBLIC (\w+)',text,re.M))
    imports=set(re.findall(r'^EXTERN (\w+):',text,re.M))
    check(exports and imports and not re.search(r'^\s*(?:option\s|END\s*$)',text,re.M|re.I),
        'Canonical fragment contains a translation-unit wrapper')
    return 'option casemap:none\n'+text+'\nEND\n',exports,imports


def unit_sources(meta):
    return dict(native=normal_frames(meta),error=exception_helper(meta),query=fragment(QUERY),span=fragment(SPAN))
