"""Compose restricted all-MASM builtin NativeLibraries bindings over original Java."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'


def module(name):
    spec=importlib.util.spec_from_file_location('native_libraries_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


N=module('nio-file-native-candidate')
S,R,A=N.S,N.R,N.A
IR=module('verify-translation-ir')
F=module('file-bootstrap-source')
OWNER='jdk/internal/loader/NativeLibraries'
IMPL=OWNER+'$NativeLibraryImpl'
SPEC=[(OWNER,'findBuiltinLib','(Ljava/lang/String;)Ljava/lang/String;',0x10a),
      (OWNER,'load','(L'+IMPL+';Ljava/lang/String;ZZ)Z',0x10a),
      (OWNER,'unload','(Ljava/lang/String;ZJ)V',0x10a),
      ('jdk/internal/loader/NativeLibrary','findEntry0','(JLjava/lang/String;)J',0x108)]
JAVA=[('java/lang/String','toCharArray','()[C'),('java/lang/Boolean','getBoolean','(Ljava/lang/String;)Z'),
      ('java/lang/InternalError','<init>','(Ljava/lang/String;)V'),
      ('java/lang/UnsatisfiedLinkError','<init>','(Ljava/lang/String;)V')]
FIXTURE_JAVA=[('java/lang/System','setProperties','(Ljava/util/Properties;)V'),
              ('java/util/Properties','<init>','()V'),
              ('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;')]
PINS={'NativeLibraries.c':'75549e652ada82c64b4199d92f5423287fb59aa20cff382dbd95e432830fe6bf',
      'jni_util.h':'05f7396789edad4d6987a5a223dd0e78ebc5f29d2e3ef03d4694b3d4849fbc5c',
      'nio_util.c':'ea2ef0421238f79036007d3cdb77229c0a77f855590ac5e0ac26ffab0198f7b8',
      'net_util.c':'44a9b56b83f0de78e40f2ac69608b0d991c518c227df7163ca97544c3230926e',
      'net_util_md.c':'8aead522655304fac388b2b5dfef80ffc0472f5a8eee1939f291e166ffe1c1eb'}
KERNELS=['native_library_lifecycle.asm.inc','builtin_net_platform.asm.inc','builtin_module_context.asm.inc']


def contracts(nio):
    closure=S.read(Path(nio['selection_directory'])/'closure.json')
    summary=S.read(S.checked(nio['source_batch']))
    plan=S.read(Path(closure['plan'])/'summary.json')
    wanted={v[0] for v in SPEC+JAVA+FIXTURE_JAVA}|{IMPL,'java/lang/Throwable','java/lang/System'}
    classes={c['name']:c for line in S.checked(plan['artifacts']['classes']).open(encoding='utf-8')
             if (c:=json.loads(line))['name'] in wanted and c['origin']['loader']=='bootstrap'}
    S.check(set(classes)==wanted,'Original library source declarations are missing')
    records={}
    for name,c in classes.items():
        raw=S.original_class(summary,c)
        parsed=IR.Source(raw)
        S.check(parsed.name==name and [{k:f[k] for k in ('name','descriptor','access')} for f in parsed.fields]==c['fields'],
                'Original library source class/field inventory differs')
        _,methods=R.original_methods(raw)
        for ident,m in zip(c['method_ids'],methods):
            key=name,m['name'],m['descriptor']
            if key not in JAVA+FIXTURE_JAVA and key not in [x[:3] for x in SPEC]:
                continue
            records[key]=dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],owner=name,
                name=m['name'],descriptor=m['descriptor'],access=m['access'],
                code_sha256=hashlib.sha256(m['code'][0]).hexdigest() if m['code'] is not None else None)
    natives=[]
    for op,(*key,flags) in enumerate(SPEC):
        row=records[tuple(key)]
        S.check(row['access']==flags and row['code_sha256'] is None,'Original library native descriptor/flags differ')
        natives.append(dict(**row,operation=op))
    java=[records[key] for key in JAVA]
    for row in java:
        chosen=closure['selected_methods'].get(str(row['method']))
        S.check(chosen and chosen['code_sha256']==row['code_sha256'],'Required original Java callback was not selected')
    layout=None
    for line in S.checked(summary['layouts']).open(encoding='utf-8'):
        row=json.loads(line)
        if row['class_id']==classes[IMPL]['id']:
            layout=row
            break
    fields=F.fields(classes[IMPL],layout,[('handle','J',0,8,False),('jniVersion','I',0,4,False)],S)
    props=[i for i,f in enumerate(classes['java/lang/System']['fields']) if
           (f['name'],f['descriptor'],f['access'])==('props','Ljava/util/Properties;',0xa)]
    S.check(len(props)==1,'Source System.props cell differs')
    frame=S.read(S.checked(S.read(S.checked(nio['native_frame_provider']['manifest']))['frame_overlay']['manifest']))
    frame_rows={r['id']:r for r in frame['source']['original_native_declarations']}
    for row in natives:
        expected=frame_rows[row['method']]
        S.check(all(expected[k]==row[k] for k in ('class_id','class_sha256','name','descriptor','access')) and
                expected['flags']&32 and not expected['flags']&128,'Original library native frame differs')
    thread_pack=next(S.read(S.checked(r['manifest'])) for r in nio['formal_provider_selection'] if
                     S.read(S.checked(r['manifest']))['family']=='normal-thread-primitives-v1')
    thread=S.read(S.checked(thread_pack['normal_thread_metadata']))
    return dict(natives=natives,original_java=java,api_fixture_methods=[records[k] for k in FIXTURE_JAVA],
                classes=classes,fields=fields,props_index=props[0],thread=thread)


def words(label,text):
    return label+' WORD '+','.join(str(ord(c)) for c in text)+'\n'


def helpers():
    null='NULL filename for native library'
    prefix,postfix='unsupported JNI version 0x',' required by '
    text='.const\n'+words('lib_name_net','net')+words('lib_name_nio','nio')
    text+=words('lib_null_filename',null)+words('lib_version_prefix',prefix)+words('lib_version_postfix',postfix)
    text+=words('lib_hex_digits','0123456789ABCDEF')+words('lib_prefer_v4','java.net.preferIPv4Stack')
    text+='''ALIGN 8
lib_error_rows QWORD OFFSET NLL_INTERNAL_CLASS,OFFSET NLL_INTERNAL_LAYOUT,OFFSET NLL_INTERNAL_CTOR
 QWORD OFFSET NLL_UNSAT_CLASS,OFFSET NLL_UNSAT_LAYOUT,OFFSET NLL_UNSAT_CTOR
.code
lib_new_module_name PROC PRIVATE
 mov r9d,3
 cmp r8d,1
 lea r8,lib_name_net
 je lib_module_name_ready
 lea r8,lib_name_nio
lib_module_name_ready:
 lea rdx,boom_java_platform_properties_pool
 jmp boom_java_property_copy
lib_new_module_name ENDP
lib_throw PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 sub rsp,48
 .allocstack 48
 .endprolog
 mov rbx,rcx
 mov r12,rdx
 mov r13d,r8d
 imul r9d,r9d,24
 lea rsi,lib_error_rows
 add rsi,r9
 mov rcx,QWORD PTR [rsi]
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne lib_throw_done
 mov rcx,rbx
 lea rdx,boom_java_platform_properties_pool
 mov r8,r12
 mov r9d,r13d
 call boom_java_property_copy
 test rax,rax
 jz lib_throw_done
 mov QWORD PTR [rsp+40],rax
 mov rcx,QWORD PTR [boom_heap_ptr]
 mov rdx,QWORD PTR [rsi+8]
 mov r8,rbx
 call boom_object_new
 test rax,rax
 jz lib_throw_done
 mov rdi,rax
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 call QWORD PTR [rsi+16]
 cmp DWORD PTR [rbx],0
 jne lib_throw_done
 mov rcx,rbx
 mov rdx,rdi
 lea r8,boom_runtime_type_map
 lea r9,NLL_THROWABLE_TYPE
 call boom_exception_set32
lib_throw_done:
 add rsp,48
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
lib_throw ENDP
lib_raise_null_filename PROC PRIVATE
 lea rdx,lib_null_filename
 mov r8d,NLL_NULL_LENGTH
 xor r9d,r9d
 jmp lib_throw
lib_raise_null_filename ENDP
lib_raise_bad_version PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 sub rsp,192
 .allocstack 192
 .endprolog
 mov rbx,rcx
 mov r12d,edx
 mov r13d,r8d
 lea rdi,[rsp+32]
 lea rsi,lib_version_prefix
 mov ecx,NLL_PREFIX_LENGTH
 rep movsw
 mov ecx,8
 lea rsi,lib_hex_digits
lib_version_digit:
 rol r12d,4
 mov eax,r12d
 and eax,15
 mov ax,WORD PTR [rsi+rax*2]
 mov WORD PTR [rdi],ax
 add rdi,2
 dec ecx
 jnz lib_version_digit
 lea rsi,lib_version_postfix
 mov ecx,NLL_POSTFIX_LENGTH
 rep movsw
 lea rsi,lib_name_net
 cmp r13d,1
 je lib_version_name
 lea rsi,lib_name_nio
lib_version_name:
 mov ecx,3
 rep movsw
 mov rcx,rbx
 lea rdx,[rsp+32]
 mov r8d,NLL_VERSION_MESSAGE_LENGTH
 mov r9d,1
 call lib_throw
 add rsp,192
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbx
 ret
lib_raise_bad_version ENDP
lib_net_body PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 push rsi
 .pushreg rsi
 sub rsp,56
 .allocstack 56
 .endprolog
 mov rbx,rcx
 mov rsi,rdx
 lea rdx,boom_builtin_module_pool
 mov r8d,00010002h
 call boom_builtin_module_check
 test eax,eax
 jnz lib_net_unavailable
 cmp QWORD PTR [NLL_SYSTEM_PROPS],0
 je lib_net_unavailable
 mov rcx,rbx
 lea rdx,boom_java_platform_properties_pool
 lea r8,lib_prefer_v4
 mov r9d,NLL_PREFER_LENGTH
 call boom_java_property_copy
 test rax,rax
 jz lib_net_failed
 mov QWORD PTR [rsp+32],rax
 mov rcx,rbx
 lea rdx,[rsp+32]
 lock inc QWORD PTR [boom_native_library_property_reads]
 call NLL_BOOLEAN_GET
 cmp DWORD PTR [rbx],0
 jne lib_net_failed
 cmp eax,1
 ja lib_net_unavailable
 mov edx,eax
 mov rcx,QWORD PTR [rsi+48]
 call boom_builtin_net_platform_start
 test eax,eax
 jnz lib_net_unavailable
 mov eax,00010002h
 jmp lib_net_done
lib_net_unavailable:
 cmp DWORD PTR [rbx],0
 jne lib_net_failed
 mov DWORD PTR [rbx],20
lib_net_failed:
 mov eax,-3
lib_net_done:
 add rsp,56
 pop rsi
 pop rbx
 ret
lib_net_body ENDP
lib_net_on_load PROC PRIVATE FRAME
 push rbx
 .pushreg rbx
 sub rsp,32
 .allocstack 32
 .endprolog
 mov rbx,rcx
 call lib_net_body
 cmp DWORD PTR [rbx],0
 jne lib_net_zero
 cmp eax,00010002h
 jne lib_net_zero
 mov eax,00010008h
 jmp lib_net_load_done
lib_net_zero:
 xor eax,eax
lib_net_load_done:
 add rsp,32
 pop rbx
 ret
lib_net_on_load ENDP
lib_net_close PROC PRIVATE
 mov rcx,QWORD PTR [rdx+48]
 jmp boom_builtin_net_platform_close
lib_net_close ENDP
lib_nio_on_load PROC PRIVATE
 lea rdx,boom_builtin_module_pool
 jmp boom_builtin_nio_on_load
lib_nio_on_load ENDP
lib_nio_close PROC PRIVATE
 xor eax,eax
 ret
lib_nio_close ENDP
'''
    values={'NLL_NULL_LENGTH':len(null),'NLL_PREFIX_LENGTH':len(prefix),'NLL_POSTFIX_LENGTH':len(postfix),
            'NLL_VERSION_MESSAGE_LENGTH':len(prefix)+8+len(postfix)+3,'NLL_PREFER_LENGTH':len('java.net.preferIPv4Stack')}
    for key,value in values.items():
        text=text.replace(key,str(value))
    return text


def build(nio_file,sources,output,fault_version=None,api_fixture=False):
    nio_file,output=nio_file.resolve(strict=True),output.resolve()
    S.check(output.is_relative_to(ART),'Keep native library candidates inside project .boom')
    nio=S.read(nio_file)
    S.checked(nio['image'])
    proof=S.read(S.checked(nio['base_proof']))
    selection=Path(nio['selection_directory'])
    closure=S.read(selection/'closure.json')
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(selection/'closure.json')['sha256'] and
            nio['formal_provider_selection']==closure['runtime_provider_packs'] and not nio['jcls_object_replaced'],
            'Verified formal NIO image required')
    pins={name:S.artifact(Path(sources)/name) for name in PINS}
    S.check(all(r['digest']['sha256']==PINS[n] for n,r in pins.items()),'Pinned OpenJDK library source changed')
    meta=contracts(nio)
    classes=meta['classes']
    method=lambda owner,name:next(m['method'] for m in meta['original_java'] if m['owner']==owner and m['name']==name)
    fields={f['name']:f for f in meta['fields']}
    symbols={
        'NLL_IMPL_CLASS':f"boom_class{classes[IMPL]['id']}",
        'NLL_IMPL_LAYOUT':f"boom_layout{classes[IMPL]['id']}",
        'NLL_STRING_LAYOUT':f"boom_layout{classes['java/lang/String']['id']}",
        'NLL_STRING_CHARS':f"boom_m{method('java/lang/String','toCharArray')}",
        'NLL_INTERNAL_CLASS':f"boom_class{classes['java/lang/InternalError']['id']}",
        'NLL_INTERNAL_LAYOUT':f"boom_layout{classes['java/lang/InternalError']['id']}",
        'NLL_INTERNAL_CTOR':f"boom_m{method('java/lang/InternalError','<init>')}",
        'NLL_UNSAT_CLASS':f"boom_class{classes['java/lang/UnsatisfiedLinkError']['id']}",
        'NLL_UNSAT_LAYOUT':f"boom_layout{classes['java/lang/UnsatisfiedLinkError']['id']}",
        'NLL_UNSAT_CTOR':f"boom_m{method('java/lang/UnsatisfiedLinkError','<init>')}",
        'NLL_THROWABLE_TYPE':f"boom_t{classes['java/lang/Throwable']['id']}",
        'NLL_BOOLEAN_GET':f"boom_m{method('java/lang/Boolean','getBoolean')}",
        'NLL_SYSTEM_PROPS':f"boom_s{classes['java/lang/System']['id']}_{meta['props_index']}"}
    procedures={symbols[k] for k in ('NLL_STRING_CHARS','NLL_INTERNAL_CTOR','NLL_UNSAT_CTOR','NLL_BOOLEAN_GET')}
    procedures|={'boom_heap_contains','boom_object_check','boom_object_new','boom_class_ensure32','boom_exception_set32',
                 'boom_java_property_copy','boom_trace_enter','boom_trace_leave'}
    data=set(symbols.values())-procedures
    thread=meta['thread']
    data|={'boom_heap_ptr','boom_runtime_type_map','boom_java_platform_properties_pool','boom_provider_thread_registry',
           'boom_trace_pool',f"boom_t{thread['thread_class']}",f"boom_t{thread['virtual_base_class']}"}
    adapters=[]
    for m in meta['natives']:
        ident=m['method']
        data|={f"boom_class{m['class_id']}",f'boom_trace_method{ident}'}
        adapters.append(f'PUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'+
            R.native_adapter(ident,m['class_id'],'boom_native_library_pool','boom_native_library_service',m['operation']))
    text='option casemap:none\n'+''.join(f'EXTERN {name}:BYTE\n' for name in sorted(data))
    text+=''.join(f'EXTERN {name}:PROC\n' for name in sorted(procedures))
    text+='\n'.join((ROOT/'native/providers'/name).read_text() for name in KERNELS)
    text+='\n'+helpers()+'\n'+''.join(adapters)
    if fault_version is not None:
        text+=f'.code\nlib_test_on_load PROC PRIVATE\n mov eax,{fault_version}\n ret\nlib_test_on_load ENDP\n'
    nio_callback='lib_nio_on_load' if fault_version is None else 'lib_test_on_load'
    text+=f'''.const
ALIGN 8
PUBLIC boom_builtin_module_pool
boom_builtin_module_pool DWORD 043424D56h,1
 QWORD OFFSET boom_heap_ptr,OFFSET boom_provider_thread_registry,OFFSET boom_runtime_type_map
 QWORD OFFSET boom_t{thread['thread_class']},OFFSET boom_t{thread['virtual_base_class']}
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
 QWORD OFFSET {nio_callback},OFFSET lib_nio_close,OFFSET boom_builtin_module_pool,0
PUBLIC boom_native_library_pool
boom_native_library_pool DWORD 042494C4Eh,1,2,64
 QWORD OFFSET boom_native_library_modules,0
END
'''
    symbols.update(NLL_HANDLE_OFFSET=str(fields['handle']['offset']),NLL_VERSION_OFFSET=str(fields['jniVersion']['offset']))
    for name,value in symbols.items():
        text=text.replace(name,value)
    output.mkdir(parents=True,exist_ok=False)
    tools=N.msvc()
    asm,obj=output/'native-libraries.asm',output/'native-libraries.obj'
    asm.write_text(text)
    N.run([tools/'ml64.exe','/nologo','/c','/Fo'+str(obj),asm],output,'assemble.log')
    foreign={'AcquireSRWLockExclusive','ReleaseSRWLockExclusive','GetCurrentThreadId','GetModuleHandleExW','FreeLibrary',
             'GetLastError','WaitOnAddress','WakeByAddressAll','WSAStartup','WSACleanup','WSAGetLastError','socket','closesocket'}
    defined,imports=A.coff_symbols(obj,foreign)
    expected={'boom_native_library_service','boom_native_library_pool','boom_native_library_modules','boom_native_library_pins',
              'boom_native_library_load_callbacks','boom_native_library_property_reads','boom_builtin_module_pool','boom_builtin_net_pool',
              'boom_builtin_module_check','boom_builtin_nio_body','boom_builtin_nio_on_load'}
    expected|={'boom_builtin_net_platform_'+n for n in ('start','acquire','release','close')}
    expected|={f"boom_m{m['method']}{suffix}" for m in meta['natives'] for suffix in ('','_native')}
    S.check(defined==expected and imports==procedures|data|foreign|
            {'boom_threads_current','boom_runtime_type','boom_type_assignable'},'Native library actual COFF differs')
    [old_stops]=[r for r in nio['generated_assembly'] if Path(r['path']).name=='remaining-stops.asm']
    stops=S.checked(old_stops).read_text()
    diagnostics=S.read(selection/'diagnostic.json')
    replaced=[]
    for m in meta['natives']:
        name=f"boom_m{m['method']}"
        rows=[r for r in diagnostics['rows'] if r['symbol']==name]
        if not rows:
            continue
        [row]=rows
        S.check(row['category']==2,'Library binding would replace original Java')
        body=(f'PUBLIC {name}\n{name} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
              f' lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{name} ENDP\n')
        S.check(stops.count(body)==1,'Source native diagnostic body differs')
        stops=stops.replace(body,'',1)
        replaced.append(name)
    stop_asm,stop_obj=output/'remaining-stops.asm',output/'remaining-stops.obj'
    stop_asm.write_text(stops)
    N.run([tools/'ml64.exe','/nologo','/c','/Fo'+str(stop_obj),stop_asm],output,'stops.log')
    api_object,api_proof=None,None
    if api_fixture:
        api_object,api_proof=module('native-library-api-source').extract(nio,meta,output,tools,N)
    original=S.checked(nio['link_response']).read_text().splitlines()
    old_stop_obj=str(Path(old_stops['path']).with_suffix('.obj'))
    S.check(original.count('"'+old_stop_obj+'"')==1,'Original NIO native-stop object must occur exactly once')
    dll=output/'native-libraries.dll'
    exports={line.removeprefix('/EXPORT:') for line in original if line.startswith('/EXPORT:')}
    exports|=expected|{f"boom_layout{classes[IMPL]['id']}",f"boom_layout{thread['thread_class']}"}
    exports|={f"boom_m{row['method']}" for row in meta['original_java']}
    exports.add(symbols['NLL_SYSTEM_PROPS'])
    if api_fixture:
        exports|={f"boom_m{m['method']}" for m in meta['api_fixture_methods']}
        exports.add(f"boom_layout{classes['java/util/Properties']['id']}")
    lines=[('"'+str(stop_obj)+'"' if line=='"'+old_stop_obj+'"' else line) for line in original
           if not line.startswith(('/OUT:','/EXPORT:'))]
    [kernel32]=[Path(line.strip('"')) for line in original if line.lower().endswith('kernel32.lib"')]
    lines.append('"'+str(kernel32.with_name('ws2_32.lib'))+'"')
    lines+=['/OUT:"'+str(dll)+'"','"'+str(obj)+'"',*['/EXPORT:'+name for name in sorted(exports)]]
    if api_object:
        lines.append('"'+str(api_object)+'"')
    rsp=output/'link.rsp'
    rsp.write_text('\n'.join(lines)+'\n')
    N.run([tools/'link.exe','@'+str(rsp)],output,'link.log')
    report=dict(schema=1,family='source-builtin-native-libraries-candidate',source_NIO=S.artifact(nio_file),
        source_proof=nio['base_proof'],runtime=nio['runtime_dll'],metadata=meta,pinned_native_sources=pins,
        kernel_sources=[S.artifact(ROOT/'native/providers'/name) for name in KERNELS],tool=S.artifact(Path(__file__)),
        assembly=S.artifact(asm),object=S.artifact(obj),image=S.artifact(dll),link_response=S.artifact(rsp),
        replaced_native_stops=replaced,diagnostic_assembly=S.artifact(stop_asm),diagnostic_object=S.artifact(stop_obj),
        test_only_callback_version=fault_version,actual_OS_image_pins=True,Java_callbacks_outside_SRW=True,
        source_properties_API_fixture=api_proof,
        normal_source_String_and_library_fields=True,source_Java_codegen_rerun=False,source_JCLS_replaced=False,
        supported_modules=['net','nio'],platform_name_conversion='ASCII and embedded NUL prefix; non-ASCII explicitly blocked',
        external_JNI_libraries_implemented=False,standard_JNI_function_addresses_exposed=False,
        registered_in_shared_runtime=False,executed=False,game_started=False)
    S.write(output/'candidate.json',report)
    return output/'candidate.json'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nio',type=Path,required=True)
    parser.add_argument('--sources',type=Path,default=ART/'native-library-lifecycle/pinned-sources/jdk-21.0.13+3')
    parser.add_argument('--output',type=Path,default=ART/'native-library-lifecycle/candidates'/uuid4().hex)
    parser.add_argument('--test-return-version',type=lambda s:int(s,0),help=argparse.SUPPRESS)
    parser.add_argument('--with-api-fixture',action='store_true',help='Link unchanged original System.setProperties for an API fixture')
    args=parser.parse_args()
    print(build(args.nio,args.sources,args.output,args.test_return_version,args.with_api_fixture))
