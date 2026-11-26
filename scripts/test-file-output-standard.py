"""Original FOS/PrintStream writes to process-owned stdout/stderr, ASM only."""
import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
from threading import Barrier,get_native_id
from time import monotonic,sleep
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('standard_output_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('file-output-standard-candidate');K=module('test-unsafe-park');P=K.P;S=B.S
Ptr,U,Q,Context=K.Ptr,K.U,K.Q,K.Context
addr,proc=K.addr,K.proc
RESULTS={}
FIXTURES=[('java/io/FileOutputStream','<init>','(Ljava/io/FileDescriptor;)V'),
    ('java/io/FileOutputStream','write','(I)V'),('java/io/FileOutputStream','write','([B)V'),
    ('java/io/FileOutputStream','write','([BII)V'),('java/io/FileDescriptor','<init>','()V'),
    ('java/io/FileDescriptor','<init>','(I)V'),('java/io/PrintStream','<init>','(Ljava/io/OutputStream;)V'),
    ('java/io/PrintStream','write','(I)V'),('java/io/PrintStream','write','([BII)V'),
    ('java/io/PrintStream','print','(Ljava/lang/String;)V'),('java/io/PrintStream','println','(Ljava/lang/String;)V'),
    ('java/io/PrintStream','checkError','()Z'),('java/io/PrintStream','flush','()V'),
    ('java/lang/System','getProperties','()Ljava/util/Properties;'),('jdk/internal/misc/VM','saveProperties','(Ljava/util/Map;)V'),
    ('java/lang/System','lineSeparator','()Ljava/lang/String;'),('java/lang/System','initPhase1','()V'),
    ('java/lang/System','getProperty','(Ljava/lang/String;)Ljava/lang/String;'),('jdk/internal/misc/VM','isBooted','()Z')]


def fixtures(candidate,original):
    closure=S.read(S.checked(original['accepted_inputs']['baseline_manifest']))
    _,summary,classes=S.base(Path(closure['batch']),Path(closure['plan']));meta=candidate['metadata']['source']
    # The accepted original Java image precedes the named JCLS overlay. Prove
    # exactly the declarations/Code/layouts used here; do not relabel it as 29.
    I=module('verify-translation-ir');owners={row['name']:row for row in classes
        if row['origin']['loader']=='bootstrap' and row['name'] in set(meta['source_classes'])|{r[0] for r in FIXTURES}|{'jdk/internal/misc/InternalLock'}}
    selected=closure['selected_methods'];members=[]
    for owner,cls in owners.items():
        raw=I.Source(S.original_class(summary,cls))
        for ident,m in zip(cls['method_ids'],raw.methods):
            if (owner,m['name'],m['descriptor']) not in FIXTURES+B.C.JAVA:continue
            code=raw.code(m);S.check(code is not None,'Standard output fixture requires original Java Code')
            row=dict(owner=owner,name=m['name'],descriptor=m['descriptor'],method=ident,class_id=cls['id'],
                class_sha256=cls['origin']['sha256'],code_sha256=hashlib.sha256(code['bytes']).hexdigest())
            chosen=selected.get(str(ident));S.check(chosen and chosen['class_id']==cls['id'] and chosen['source_sha256']==row['class_sha256'] and
                chosen['code_sha256']==row['code_sha256'],'Standard output original Java not selected: '+str(row))
            members.append(row)
    S.check(len(members)==len(FIXTURES+B.C.JAVA),'Output original constructor/error/PrintStream fixtures incomplete')
    for row in meta['original_java']:
        S.check(any(all(x.get(k)==row.get(k) for k in ('owner','name','descriptor','method','class_id','class_sha256','code_sha256')) for x in members),
            'Current output callback differs from accepted original Java Code')
    F=module('file-bootstrap-source');registration=F.index(summary,classes,S)
    S.check(registration['descriptor']==meta['descriptor'] and any(r==meta['stream'] for r in registration['streams']) and
        summary['string_literals']['source_layout']==meta['source_String_shape'],
        'Output source receiver/FD/String layouts differ across the two accepted batches')
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        [ps_layout]=[r for line in stream if (r:=json.loads(line))['class_id']==owners['java/io/PrintStream']['id']]
    [lock]=F.fields(owners['java/io/PrintStream'],ps_layout,[('lock','Ljdk/internal/misc/InternalLock;',0x12,8,True)],S)
    return dict(classes={name:cls['id'] for name,cls in owners.items()},members=members,PrintStream_lock_field=lock,
        original_Java_Code_and_receiver_layouts_equal=True,source_selection=S.artifact(S.checked(original['accepted_inputs']['baseline_manifest'])),
        source_scope='accepted_original_26_source_plus_two_unregistered_current_source_native_stops_only')


def runner():
    tree=ast.parse(inspect.getsource(P.execute));fn=tree.body[0]
    [body]=[node for node in fn.body if isinstance(node,ast.Try) and node.handlers and node.finalbody]
    [index]=[i for i,node in enumerate(body.body) if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and
        ast.unparse(node.value)=="java('java/lang/System', 'setJavaLangAccess', '()V', [])"]
    body.body.insert(index+1,ast.parse('prepare_saved_properties(java,string)').body[0])
    body.body.append(ast.parse('standard_suite(image,rt,heap,meta,java,call,field,new,string,images_file,kind)').body[0])
    for node in ast.walk(fn):
        if isinstance(node,ast.keyword) and node.arg=='extra_Java_Code_or_COFF_or_stop_replacements':node.value=ast.Constant(True)
        if isinstance(node,ast.keyword) and node.arg=='scope' and isinstance(node.value,ast.Constant) and node.value.value=='public_FIS_constructor_registration_explicit_close_probe':
            node.value=ast.Constant('original_FOS_standard_output_candidate_after_real_primordial_and_source_API_setup')
    ast.fix_missing_locations(tree);namespace=dict(vars(P));namespace.update(standard_suite=suite,prepare_saved_properties=K.prepare_saved_properties)
    exec(compile(tree,str(Path(__file__)),'exec'),namespace)
    return namespace['execute'],ast.unparse(tree)+'\n'


def observer_assembly():
    return '''option casemap:none
EXTERN WriteFile:PROC
EXTERN HeapAlloc:PROC
EXTERN GetStdHandle:PROC
EXTERN SetStdHandle:PROC
EXTERN SetLastError:PROC
EXTERN WakeByAddressAll:PROC
EXTERN WaitOnAddress:PROC
.data
ALIGN 8
PUBLIC boom_fos_test_control
; mode0,cap4,error8,entered12,release16,switches20,calls24,bytes32,buffer40,
; hookedCalls48,failedHeapCalls56. Only this test DLL owns these cells.
boom_fos_test_control QWORD 8 DUP(0)
.code
PUBLIC boom_fos_test_HeapAlloc
boom_fos_test_HeapAlloc PROC
 cmp DWORD PTR [boom_fos_test_control],4
 jne fos_test_heap_real
 lock inc QWORD PTR [boom_fos_test_control+56]
 xor eax,eax
 ret
fos_test_heap_real:
 jmp HeapAlloc
boom_fos_test_HeapAlloc ENDP
PUBLIC boom_fos_test_WriteFile
boom_fos_test_WriteFile PROC FRAME
 sub rsp,104
 .allocstack 104
 .endprolog
 mov QWORD PTR [rsp+48],rcx
 mov QWORD PTR [rsp+56],rdx
 mov DWORD PTR [rsp+64],r8d
 mov QWORD PTR [rsp+72],r9
 mov rax,QWORD PTR [rsp+144]
 mov QWORD PTR [rsp+80],rax
 lock inc QWORD PTR [boom_fos_test_control+48]
 cmp DWORD PTR [boom_fos_test_control],2
 je fos_test_zero
 cmp DWORD PTR [boom_fos_test_control],3
 je fos_test_error
 cmp DWORD PTR [boom_fos_test_control],5
 jne fos_test_real
 mov QWORD PTR [boom_fos_test_control+40],rdx
 mov DWORD PTR [boom_fos_test_control+12],1
 lea rcx,boom_fos_test_control+12
 call WakeByAddressAll
fos_test_gate:
 cmp DWORD PTR [boom_fos_test_control+16],0
 jne fos_test_real
 mov DWORD PTR [rsp+88],0
 lea rcx,boom_fos_test_control+16
 lea rdx,[rsp+88]
 mov r8d,4
 mov r9d,-1
 call WaitOnAddress
 jmp fos_test_gate
fos_test_real:
 mov rcx,QWORD PTR [rsp+48]
 mov rdx,QWORD PTR [rsp+56]
 mov r8d,DWORD PTR [rsp+64]
 mov eax,DWORD PTR [boom_fos_test_control+4]
 test eax,eax
 jz fos_test_count
 cmp r8d,eax
 jbe fos_test_count
 mov r8d,eax
fos_test_count:
 mov r9,QWORD PTR [rsp+72]
 mov rax,QWORD PTR [rsp+80]
 mov QWORD PTR [rsp+32],rax
 lock inc QWORD PTR [boom_fos_test_control+24]
 call WriteFile
 mov DWORD PTR [rsp+92],eax
 test eax,eax
 jz fos_test_done
 mov rcx,QWORD PTR [rsp+72]
 mov eax,DWORD PTR [rcx]
 lock add QWORD PTR [boom_fos_test_control+32],rax
 cmp DWORD PTR [boom_fos_test_control],6
 jne fos_test_restore
 cmp DWORD PTR [boom_fos_test_control+20],0
 jne fos_test_restore
 mov ecx,-12
 call GetStdHandle
 mov rdx,rax
 mov ecx,-11
 call SetStdHandle
 mov DWORD PTR [boom_fos_test_control+20],1
fos_test_restore:
 mov eax,DWORD PTR [rsp+92]
 jmp fos_test_done
fos_test_error:
 mov ecx,DWORD PTR [boom_fos_test_control+8]
 call SetLastError
 xor eax,eax
 jmp fos_test_done
fos_test_zero:
 mov DWORD PTR [r9],0
 mov eax,1
fos_test_done:
 add rsp,104
 ret
boom_fos_test_WriteFile ENDP
END
'''


def coff_protocol(path,rename=None):
    """Compare actual data/instructions AND every relocation target by name."""
    rename=rename or {};blob=path.read_bytes();machine,count,_,offset,number,optional,_=struct.unpack_from('<HHIIIHH',blob)
    S.check(machine==0x8664 and optional==0,'Expected actual AMD64 provider COFF')
    strings=offset+number*18;names={};index=0
    while index<number:
        at=offset+index*18;raw,value,section,_,_,aux=struct.unpack_from('<8sIhHBB',blob,at)
        if raw[:4]==b'\0'*4:
            start=strings+struct.unpack_from('<I',raw,4)[0];name=blob[start:blob.index(b'\0',start)].decode('ascii')
        else:name=raw.rstrip(b'\0').decode('ascii')
        names[index]=rename.get(name,name);index+=aux+1
    result=[]
    for i in range(count):
        at=20+i*40;name=blob[at:at+8].rstrip(b'\0').decode('ascii')
        if name.startswith('.debug'):continue # assembler embeds the distinct input filename
        size,raw,reloc=struct.unpack_from('<III',blob,at+16);n=struct.unpack_from('<H',blob,at+32)[0]
        result.append((name,blob[raw:raw+size].hex() if raw else None,
            [(address,names[symbol],kind) for address,symbol,kind in
             [struct.unpack_from('<IIH',blob,reloc+j*10) for j in range(n)]]))
    return result


def build_observer(candidate,assembler,output):
    text=S.checked(candidate['assembly']).read_text();aliases={name:'boom_fos_test_'+name for name in ('WriteFile','HeapAlloc')}
    observed=text
    for name,alias in aliases.items():
        observed=observed.replace('EXTERN '+name+':PROC','EXTERN '+alias+':PROC').replace('call '+name+'\n','call '+alias+'\n')
    normalized=observed
    for name,alias in aliases.items():normalized=normalized.replace(alias,name)
    S.check(normalized==text,'Only explicit test WinAPI target aliases may change')
    paths=[]
    for name,source in [('observed-provider',observed),('observed-calls',observer_assembly())]:
        asm=output/(name+'.asm');obj=asm.with_suffix('.obj');asm.write_text(source)
        with asm.with_suffix('.log').open('wb') as log:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        paths.append((asm,obj))
    protocol=coff_protocol(S.checked(candidate['object']))
    S.check(protocol==coff_protocol(paths[0][1],{v:k for k,v in aliases.items()}),
        'Observed provider changed actual instruction/data bytes or non-aliased relocations')
    return paths,dict(actual_COFF_sections_and_all_relocations_equal=True,normalized_aliases=aliases,
        protocol_sha256=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest())


def build(candidate_file,accepted_park_result,output):
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Current output source proof differs')
    accepted=S.read(accepted_park_result);S.check(accepted['verified'] and accepted['all_park_semantics_completed'],'Actual primordial/Parker original-Java image required')
    original_images=S.checked(accepted['images']);original=S.read(original_images);candidate=S.read(candidate_file);meta=candidate['metadata']['source']
    S.check(original['park_test_generator']==S.artifact(Path(K.__file__)) and original['execution_tool']==S.artifact(Path(P.__file__)),
        'Frozen original public fixture tool changed')
    for row in original['link_inputs']:S.check(S.artifact(row['path'])==row,'Accepted original source input changed')
    model=fixtures(candidate,original);output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh standard-output execution directory required');output.mkdir(parents=True)
    old=original['accepted_inputs'];diagnostic=S.read(Path(old['baseline_manifest']['path']).parent/'diagnostic.json')
    [stop]=[row for row in original['link_inputs'] if Path(row['path']).name=='remaining-stops.obj']
    old_obj=S.checked(stop);old_asm=old_obj.with_suffix('.asm');text=old_asm.read_text();removed=[]
    old_frame=S.read(S.checked(S.read(S.checked(old['candidate']))['metadata']['frame_overlay']['manifest']))
    new_frame=S.read(S.checked(candidate['metadata']['frame_overlay']['manifest']))
    a={r['id']:r for r in old_frame['source']['original_native_declarations']};b={r['id']:r for r in new_frame['source']['original_native_declarations']}
    for method in meta['methods']:
        ident=method['method'];symbol=f'boom_m{ident}';S.check(a[ident]==b[ident],'Output original native frame differs across accepted batches')
        [row]=[r for r in diagnostic['rows'] if r['symbol']==symbol]
        S.check(row['category']==2 and row['source_sha256']==method['class_sha256'],'Output replacement is not an exact original native stop')
        body=f'PUBLIC {symbol}\n{symbol} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{symbol} ENDP\n'
        S.check(text.count(body)==1,'Output exact native diagnostic stop changed');text=text.replace(body,'',1)
        removed.append(dict(symbol=symbol,source_sha256=method['class_sha256'],body_sha256=hashlib.sha256(body.encode()).hexdigest()))
    asm=output/'remaining-stops.asm';obj=asm.with_suffix('.obj');asm.write_text(text)
    assembler=Path(candidate['assembler']['path'])
    with obj.with_suffix('.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    observer_paths,observer_proof=build_observer(candidate,assembler,output)
    lines=S.checked(original['link_response']).read_text().splitlines();exports={line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')}
    exports|=set(candidate['exports'])|{r['symbol'] for r in meta['standard_fields']}|{f"boom_m{r['method']}" for r in model['members']}
    exports|={f'boom_{kind}{ident}' for ident in model['classes'].values() for kind in ('class','layout')}
    response=[];objects=[]
    for line in lines:
        if line.startswith(('/OUT:','/EXPORT:')):continue
        if line.startswith('"'):
            path=Path(line.strip('"')).resolve();path=obj if path==old_obj else path;objects.append(S.artifact(path));line='"'+str(path)+'"'
        response.append(line)
    provider=S.checked(candidate['object']);objects.append(S.artifact(provider));response.append('"'+str(provider)+'"')
    dll=output/'standard-output.dll';rsp=output/'link.rsp'
    rsp.write_text('\n'.join(response+['/OUT:"'+str(dll)+'"',*['/EXPORT:'+n for n in sorted(exports)]])+'\n')
    with (output/'link.log').open('wb') as log:
        subprocess.run([assembler.with_name('link.exe'),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    observed_dll=output/'standard-output-observed.dll';observed_rsp=output/'observed-link.rsp'
    observed_response=[line.replace(str(provider),str(observer_paths[0][1])) for line in response]
    observed_response+=['"'+str(observer_paths[1][1])+'"','/OUT:"'+str(observed_dll)+'"']
    observed_response+=['/EXPORT:'+n for n in sorted(exports|{'boom_fos_test_control'})]
    observed_rsp.write_text('\n'.join(observed_response)+'\n')
    with (output/'observed-link.log').open('wb') as log:
        subprocess.run([assembler.with_name('link.exe'),'@'+str(observed_rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    _,text=runner();script=output/'source-runner.py';script.write_text(text)
    config=json.loads(json.dumps(original));config.update(image=S.artifact(dll),link_response=S.artifact(rsp),link_inputs=objects,
        output_candidate=S.artifact(candidate_file),output_source_proof=S.artifact(candidate_file.with_name('verification.json')),
        output_test_tool=S.artifact(Path(__file__)),output_runner=S.artifact(script),output_model=model,
        output_observer=dict(image=S.artifact(observed_dll),response=S.artifact(observed_rsp),
            inputs=[S.artifact(path) for pair in observer_paths for path in pair],equivalence=observer_proof),
        output_original_images=S.artifact(original_images),output_remaining_stops=dict(original_assembly=S.artifact(old_asm),original_object=stop,
            assembly=S.artifact(asm),object=S.artifact(obj),exact_removed_native_stops=removed),
        original_Java_COFF_or_vtable_or_class_state_changed=False,formal_31_source_consumed=False)
    config['model']['classes'].update(model['classes']);config['model']['members']+=model['members']
    path=output/'images.json';S.write(path,config)
    watched=json.loads(json.dumps(config));watched['image']=config['output_observer']['image'];watched['output_observed_active']=True
    watched['link_inputs']=[S.artifact(observer_paths[0][1]) if row==S.artifact(provider) else row for row in objects]
    watched['link_inputs'].append(S.artifact(observer_paths[1][1]));watched['link_response']=S.artifact(observed_rsp)
    (output/'observed').mkdir();S.write(output/'observed/images.json',watched)
    denied=json.loads(json.dumps(config));denied['output_readonly_stdout']=True
    (output/'access-denied').mkdir();S.write(output/'access-denied/images.json',denied)
    return path


def suite(image,rt,heap,meta,java,call,field,new,string,images_file,kind):
    config=S.read(images_file);model=S.read(S.checked(config['output_candidate']))['metadata']['source']
    counters=(Q*12).from_address(addr(image,'boom_file_output_standard_counters'))
    natives={row['operation']:row['method'] for row in model['methods']};streams={};protocol=[]
    result=dict(original_FOS_standard_constructors=False,source_public_writes=False,default_PrintStream=False,all_tests_completed=False)
    RESULTS[kind]=result
    def array(raw):
        context=Context();value=proc(rt,'boom_array_new',Ptr,Ptr,c.c_int,U,Ptr)(heap,len(raw),8,context)
        S.check(value and not context[0],'Normal source byte array allocation failed');c.memmove(value,raw,len(raw));return value
    def text(value):
        if not value:return None
        chars=java('java/lang/String','toCharArray','()[C',[value]);return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    def native(op,args,error=None):
        value,context=call(natives[op],[v&0xffffffffffffffff for v in args],'original standard FOS native',check=False)
        if error:
            oop=Ptr.from_address(c.addressof(context)+16).value
            S.check(context[0]==16 and oop and Ptr.from_address(oop-8).value==addr(image,'boom_layout'+str(meta['classes'][error])),
                'Original typed standard-output exception differs: '+str((error,list(context))))
            return text(java('java/lang/Throwable','getMessage','()Ljava/lang/String;',[oop]))
        S.check(not context[0],'Original standard native failed: '+str(list(context)));return value
    for standard in model['standard_fields']:
        descriptor=Q.from_address(addr(image,standard['symbol'])).value
        stream=new(B.C.OWNER);java(B.C.OWNER,'<init>','(Ljava/io/FileDescriptor;)V',[stream,descriptor]);streams[standard['name']]=stream
        S.check(descriptor and Q.from_address(stream+model['stream']['fd_offset']).value==descriptor,'Original standard constructor did not retain actual FD static identity')
    result['original_FOS_standard_constructors']=True
    if config.get('output_readonly_stdout'):
        stream=streams['out']
        single=native(0,[stream,65,0],'java/io/IOException')
        many=native(1,[stream,array(bytes(10000)),0,10000,0],'java/io/IOException')
        ps=new('java/io/PrintStream');java('java/io/PrintStream','<init>','(Ljava/io/OutputStream;)V',[ps,stream])
        java('java/io/PrintStream','write','(I)V',[ps,65])
        error=java('java/io/PrintStream','checkError','()Z',[ps])
        S.check(error==1 and not counters[4] and counters[5]==counters[6],'Original PrintStream did not catch the real WriteFile access error')
        result.update(real_readonly_standard_HANDLE_error=dict(code=5,single_message=single,array_message=many,PrintStream_error=True),
            all_tests_completed=True,owned_buffers=0,counters=list(counters),source_FD_untouched=True,read_only_std_HANDLE_not_closed=True)
        return
    for name,stream in streams.items():
        for value in (0,10,255,256,-1,0x12345678):native(0,[stream,value,0])
        payload=bytes((i*17+3)&255 for i in range(10037));value=array(payload);native(1,[stream,value,3,10000,0])
        java(B.C.OWNER,'write','(I)V',[stream,ord('A')])
        raw=(name+' public-source\n').encode();java(B.C.OWNER,'write','([B)V',[stream,array(raw)])
    result['source_public_writes']=True
    value=array(b'abc');stream=streams['out']
    protocol.append(dict(case='null_array',message=native(1,[stream,0,0,1,0],'java/lang/NullPointerException')))
    for off,length in [(-1,1),(0,-1),(2,2),(0x7fffffff,0x7fffffff)]:
        protocol.append(dict(case='bounds',offset=off,length=length,message=native(1,[stream,value,off,length,0],'java/lang/IndexOutOfBoundsException')))
    native(1,[stream,value,3,0,1])
    descriptor=new(B.C.FD);java(B.C.FD,'<init>','()V',[descriptor])
    closed=new(B.C.OWNER);java(B.C.OWNER,'<init>','(Ljava/io/FileDescriptor;)V',[closed,descriptor])
    protocol.append(dict(case='closed_single',message=native(0,[closed,1,0],'java/io/IOException')))
    protocol.append(dict(case='closed_array',message=native(1,[closed,value,0,3,0],'java/io/IOException')))
    native(1,[closed,value,0,0,1])
    for operation,args in [(0,[stream,1,1]),(1,[stream,value,0,1,1])]:
        _,context=call(natives[operation],args,'unsupported append',check=False);S.check(context[0]==20,'Unsupported append did not fail explicitly')
    foreign=new(B.C.FD);java(B.C.FD,'<init>','(I)V',[foreign,1])
    impostor=new(B.C.OWNER);java(B.C.OWNER,'<init>','(Ljava/io/FileDescriptor;)V',[impostor,foreign])
    _,context=call(natives[0],[impostor,1,0],'same HANDLE without original static FD identity',check=False)
    S.check(context[0]==20,'A separately constructed FD with the same standard HANDLE was adopted')
    pending=Context(77,88,99,111,222,333,444,555);argv=(Q*3)(stream,1,0)
    proc(image,'boom_m'+str(natives[0]),Q,Ptr,Ptr)(pending,argv)
    S.check(list(pending)==[77,88,99,111,222,333,444,555],'Pending Context changed')
    result.update(protocol=protocol,append_explicitly_unsupported=True,same_HANDLE_nonstandard_FD_rejected=True,pending_Context_preserved=True)
    separator=java('java/lang/System','lineSeparator','()Ljava/lang/String;',[])
    result['source_lineSeparator_before_Phase1']=text(separator)
    S.check(java('java/lang/System','getProperty','(Ljava/lang/String;)Ljava/lang/String;',[string('jdk.io.useMonitors')])==0,
        'Default PrintStream test unexpectedly forced monitor mode')
    lock_records=[]
    for name,stream in streams.items():
        ps=new('java/io/PrintStream');java('java/io/PrintStream','<init>','(Ljava/io/OutputStream;)V',[ps,stream])
        lock=Q.from_address(ps+config['output_model']['PrintStream_lock_field']['offset']).value
        S.check(lock and Ptr.from_address(lock-8).value==addr(image,'boom_layout'+str(meta['classes']['jdk/internal/misc/InternalLock'])),
            'Default original PrintStream did not construct its normal InternalLock')
        lock_records.append(dict(stream=name,normal_InternalLock_oop=lock))
        java('java/io/PrintStream','print','(Ljava/lang/String;)V',[ps,string(name+' default PrintStream ')])
        java('java/io/PrintStream','print','(Ljava/lang/String;)V',[ps,string('\u4e2d\u6587 \U0001f642')])
        java('java/io/PrintStream','write','(I)V',[ps,10])
        raw=(name+' PrintStream bytes\n').encode();java('java/io/PrintStream','write','([BII)V',[ps,array(raw),0,len(raw)])
        java('java/io/PrintStream','flush','()V',[ps])
        S.check(not java('java/io/PrintStream','checkError','()Z',[ps]),'Default original PrintStream recorded an IO error')
    big=bytes((i*73+19)&255 for i in range((1<<20)+37));native(1,[streams['out'],array(big),0,len(big),0])
    S.check(not java('jdk/internal/misc/VM','isBooted','()Z',[]),'Eight-OS source API fixture unexpectedly booted the full VM')
    begin=b'\n<ASM-CONCURRENT-BEGIN>\n';end=b'<ASM-CONCURRENT-END>\n'
    native(1,[streams['out'],array(begin),0,len(begin),0])
    barrier=Barrier(8);rows=[(f'worker-{i:02d} '+('x'*52)+'\n').encode() for i in range(8)]
    arrays=[array(row) for row in rows]
    def writer(i):
        identity=get_native_id();barrier.wait()
        for _ in range(128):java(B.C.OWNER,'write','([B)V',[streams['out'],arrays[i]])
        return dict(OS_thread_id=identity,writes=128,payload_sha256=hashlib.sha256(rows[i]).hexdigest())
    with ThreadPoolExecutor(max_workers=8) as executor:threads=list(executor.map(writer,range(8)))
    S.check(len({r['OS_thread_id'] for r in threads})==8,'Eight actual OS writers were not used')
    native(1,[streams['out'],array(end),0,len(end),0])
    result.update(default_PrintStream=True,default_PrintStream_entries=['constructor','print(String)','write(int)','write(byte[],int,int)','flush','checkError'],
        default_PrintStream_lock_records=lock_records,println_fixture_boundary='source_System_lineSeparator_null_without_full_Phase1',
        println_passed=False,monitor_property_forced=False,large_array_bytes=len(big),concurrent_OS_writers=threads,
        concurrent_row_bytes=len(rows[0]),concurrent_writes=1024)
    for operation,args in [(0,[1,1,0]),(0,[string('wrong receiver'),1,0]),
                           (1,[stream,1,0,1,0]),(1,[stream,string('wrong array'),0,1,0])]:
        _,context=call(natives[operation],args,'invalid heap or source receiver/array',check=False)
        S.check(context[0] in (7,8),'Invalid heap/type input accepted: '+str(list(context)))
    result['invalid_heap_and_receiver_and_array_rejected']=True
    if config.get('output_observed_active'):
        result['controlled_Win32']=observed_suite(image,streams,natives,array,native,call,counters)
    else:
        # This cold child alone owns its redirected stderr. The provider never
        # closes it: the test invalidates the real OS handle to reach WriteFile's
        # ERROR_INVALID_HANDLE while preserving the original FD source cells.
        kernel=c.WinDLL('kernel32',use_last_error=True)
        handle=proc(kernel,'GetStdHandle',Ptr,c.c_int)(-12)
        S.check(proc(kernel,'CloseHandle',U,Ptr)(handle),'Test failed to close its own redirected stderr')
        result['real_WriteFile_error']=dict(code=6,message=native(1,[streams['err'],array(bytes(10000)),0,10000,0],'java/io/IOException'))
        result['real_WriteFile_error']['single_message']=native(0,[streams['err'],1,0],'java/io/IOException')
        result['test_only_stderr_HANDLE_closed']=True
    result.update(owned_buffers=counters[4],counters=list(counters),all_tests_completed=True)
    S.check(not counters[4] and counters[5]==counters[6],'Standard output scratch buffer leaked')


def observed_suite(image,streams,natives,array,native,call,counters):
    control=addr(image,'boom_fos_test_control');stream=streams['out'];cases=[]
    def mode(value,cap=0,error=0):
        U.from_address(control).value=value;U.from_address(control+4).value=cap
        U.from_address(control+8).value=error
    def write(raw):return native(1,[stream,array(raw),0,len(raw),0])
    payload=bytes((i*11+7)&255 for i in range(10003));before=list(counters)
    mode(1,31);write(payload);mode(0)
    iterations=(len(payload)+30)//31
    S.check(counters[1]-before[1]==iterations and counters[7]-before[7]==iterations and
        counters[3]-before[3]==iterations-1,'Each real partial write did not repeat the original FD/standard HANDLE lookup')
    cases.append(dict(case='real_partial_WriteFile',bytes=len(payload),cap=31,actual_calls=iterations,
        original_FD_and_real_standard_HANDLE_lookups=iterations))
    mode(2);native(0,[stream,65,0]);mode(0)
    cases.append(dict(case='single_success_zero',returned_normally=True,original_writeSingle_protocol=True))
    for length in (3,10000):
        mode(2);message=native(1,[stream,array(bytes(length)),0,length,0],'java/io/IOException');mode(0)
        S.check(message=='Write error' and counters[4]==0,'Zero-progress write did not terminate and clean private storage')
        cases.append(dict(case='zero_progress',bytes=length,message=message,controlled_success_zero=True))
    for error in (5,6):
        mode(3,error=error);message=native(1,[stream,array(bytes(10000)),0,10000,0],'java/io/IOException');mode(0)
        S.check(not counters[4],'Injected Win32 failure leaked the private byte copy')
        cases.append(dict(case='WriteFile_error',code=error,message=message))
    mode(4);message=native(1,[stream,array(bytes(10000)),0,10000,0],'java/lang/OutOfMemoryError');mode(0)
    S.check(message is None and not counters[4] and Q.from_address(control+56).value==1,'Large private-buffer OOM protocol differs')
    cases.append(dict(case='private_HeapAlloc_OOM',message=message,owned_buffers=0))
    kernel=c.WinDLL('kernel32',use_last_error=True);wake=proc(c.WinDLL('KernelBase'),'WakeByAddressAll',None,Ptr)
    for length in (127,10007):
        original=bytes((i*23+length)&255 for i in range(length));value=array(original)
        U.from_address(control+12).value=0;U.from_address(control+16).value=0;mode(5)
        with ThreadPoolExecutor(1) as executor:
            writer=executor.submit(native,1,[stream,value,0,length,0])
            try:
                until=monotonic()+10
                while not U.from_address(control+12).value and monotonic()<until:sleep(.001)
                S.check(U.from_address(control+12).value and not writer.done(),'Actual WriteFile private-copy gate did not block')
                copied=Q.from_address(control+40).value
                S.check(copied!=value and c.string_at(copied,length)==original,'WriteFile was not passed an independent complete private byte copy')
                c.memset(value,0xa5,length)
                S.check(c.string_at(copied,length)==original,'Source array change altered private native bytes')
            finally:
                U.from_address(control+16).value=1;wake(control+16)
            writer.result(timeout=10)
        mode(0);S.check(not counters[4],'Blocked copied write leaked private storage')
        cases.append(dict(case='private_copy_during_actual_WriteFile',bytes=length,original_sha256=hashlib.sha256(original).hexdigest(),
            source_fixture_bytes_modified_after_copy=True,source_reference_fields_untouched=True,actual_buffer_distinct=True))
    # An actual Win32 standard-slot switch after the first real partial write
    # must be observed on the second iteration. No Java FD slot is patched.
    raw=b'changed-standard-handle-must-stop';actual=proc(kernel,'GetStdHandle',Ptr,c.c_int)(-11)
    set_std=proc(kernel,'SetStdHandle',U,c.c_int,Ptr);mode(6,7)
    before=list(counters)
    try:
        _,context=call(natives[1],[stream,array(raw),0,len(raw),0],'real standard HANDLE changed between partial writes',check=False)
        S.check(context[0]==20 and counters[1]-before[1]==1 and counters[7]-before[7]==2 and
            U.from_address(control+20).value==1,'Changed real standard slot was not revalidated before the next partial write')
    finally:
        S.check(set_std(-11,actual),'Test failed to restore its own Win32 stdout slot');mode(0)
    S.check(not counters[4],'Changed standard slot leaked private storage')
    cases.append(dict(case='real_SetStdHandle_between_partial_writes',written_prefix=7,source_FD_untouched=True,context=20,
        lookups=2,actual_WriteFile_calls=1,real_standard_slot_restored=True))
    return dict(cases=cases,actual_code_and_data_and_all_nonaliased_relocations_equal=True,
        production_WinAPI_imports_unchanged=True,all_owned_buffers_released=True)


def worker(images,kind):
    config=S.read(images);S.check(config['output_test_tool']==S.artifact(Path(__file__)),'Output test source changed')
    execute,source=runner();S.check(S.checked(config['output_runner']).read_text()==source,'Output executor AST changed')
    try:result_file=execute(images,kind)
    except BaseException:
        S.write(images.parent/(kind+'-output-progress-at-failure.json'),RESULTS.get(kind,{}));raise
    public=S.read(result_file);result=RESULTS.get(kind,{})
    return dict(verified=bool(public['verified'] and public['failure'] is None and result.get('all_tests_completed')),
        original_public_fixture=S.artifact(result_file),standard_output=result,source_failure=public['failure'],
        worker_cleanup=public['native_worker_lifecycle_cleanup'],production_borrows_standard_HANDLEs_without_closing=True,
        host_FD_JLA_Thread_or_root_fields_written=False,formal_registered=False,game_started=False)


BEGIN=b'\n<ASM-CONCURRENT-BEGIN>\n'
END=b'<ASM-CONCURRENT-END>\n'


def check_captured(output,kind,observed=False):
    streams={name:output/(kind+'-std'+name+'.bin') for name in ('out','err')};records={}
    for name,path in streams.items():
        prefix=bytes([0,10,255,0,255,0x78])+bytes((i*17+3)&255 for i in range(10037))[3:10003]
        prefix+=b'A'+(name+' public-source\n').encode()
        prefix+=(name+' default PrintStream \u4e2d\u6587 \U0001f642\n'+name+' PrintStream bytes\n').encode('utf-8')
        raw=path.read_bytes();S.check(raw.startswith(prefix),'Captured source public/native/PrintStream bytes differ: '+str(path))
        tail=raw[len(prefix):]
        if name=='out':
            big=bytes((i*73+19)&255 for i in range((1<<20)+37))
            S.check(tail.startswith(big+BEGIN),'Captured large array or concurrent boundary differs');tail=tail[len(big+BEGIN):]
            concurrent,tail=tail.split(END,1)
            rows=[(f'worker-{i:02d} '+('x'*52)+'\n').encode() for i in range(8)];width=len(rows[0])
            S.check(Counter(concurrent[i:i+width] for i in range(0,len(concurrent),width))==Counter({row:128 for row in rows}),
                'Eight-OS original Java write records were lost, duplicated, or interleaved')
            if observed:
                wanted=bytes((i*11+7)&255 for i in range(10003))
                wanted+=b''.join(bytes((i*23+length)&255 for i in range(length)) for length in (127,10007))
                wanted+=b'changed'
                S.check(tail==wanted,'Actual partial writes/private copies/standard slot switch captured bytes differ')
            else:S.check(not tail,'Unexpected bytes after concurrent source writes')
        else:S.check(not tail,'Unexpected stderr bytes')
        records[name]=dict(artifact=S.artifact(path),exact_original_native_and_public_Java_bytes=True)
    return dict(streams=records,concurrent_row_multiset_equal=True,rows=1024,ordering_claimed=False)


def oracle(home,output,readonly=False):
    output.mkdir();source=output/'StandardOutputOracle.java';protocol=output/'protocol.txt'
    source.write_text(r'''import java.io.*;import java.lang.reflect.*;import java.nio.file.*;import java.nio.charset.*;import java.util.*;import java.util.concurrent.*;
class StandardOutputOracle {
 static Method one,many; static List<String> log=new ArrayList<>();
 static String text(String x){if(x==null)return "NULL";StringBuilder b=new StringBuilder();for(char c:x.toCharArray())b.append("%04x".formatted((int)c));return b.toString();}
 static void invoke(Method m,Object target,Object... a)throws Exception{try{m.invoke(target,a);}catch(InvocationTargetException e){throw (Exception)e.getCause();}}
 static void error(String key,Method m,Object target,Object... a)throws Exception{try{invoke(m,target,a);throw new AssertionError(key);}catch(NullPointerException|IndexOutOfBoundsException|IOException e){log.add(key+"\t"+e.getClass().getName()+"\t"+text(e.getMessage()));}}
 static byte[] bytes(int n,int scale,int add){byte[] b=new byte[n];for(int i=0;i<n;i++)b[i]=(byte)(i*scale+add);return b;}
 public static void main(String[] args)throws Exception{
  one=FileOutputStream.class.getDeclaredMethod("write",int.class,boolean.class);one.setAccessible(true);
  many=FileOutputStream.class.getDeclaredMethod("writeBytes",byte[].class,int.class,int.class,boolean.class);many.setAccessible(true);
  FileOutputStream out=new FileOutputStream(FileDescriptor.out),err=new FileOutputStream(FileDescriptor.err);
  if(args.length>1){error("readonly_single",one,out,65,false);error("readonly_array",many,out,new byte[10000],0,10000,false);
   PrintStream p=new PrintStream(out);p.write(65);log.add("PrintStream_error\tboolean\t"+p.checkError());
   Files.writeString(Path.of(args[0]),String.join("\n",log),StandardCharsets.US_ASCII);return;}
  for(String name:new String[]{"out","err"}){FileOutputStream f=name.equals("out")?out:err;
   for(int v:new int[]{0,10,255,256,-1,0x12345678})invoke(one,f,v,false);
   invoke(many,f,bytes(10037,17,3),3,10000,false);f.write('A');f.write((name+" public-source\n").getBytes(StandardCharsets.UTF_8));}
  error("null_array",many,out,null,0,1,false);
  for(int[] r:new int[][]{{-1,1},{0,-1},{2,2},{0x7fffffff,0x7fffffff}})error("bounds_"+r[0]+"_"+r[1],many,out,new byte[3],r[0],r[1],false);
  invoke(many,out,new byte[3],3,0,true);
  FileOutputStream closed=new FileOutputStream(new FileDescriptor());
  error("closed_single",one,closed,1,false);error("closed_array",many,closed,new byte[3],0,3,false);invoke(many,closed,new byte[3],0,0,true);
  for(String name:new String[]{"out","err"}){PrintStream p=new PrintStream(name.equals("out")?out:err);
   p.print(name+" default PrintStream ");p.print("\u4e2d\u6587 \ud83d\ude42");p.write(10);
   byte[] b=(name+" PrintStream bytes\n").getBytes(StandardCharsets.UTF_8);p.write(b,0,b.length);p.flush();if(p.checkError())throw new AssertionError("PrintStream");}
  invoke(many,out,bytes((1<<20)+37,73,19),0,(1<<20)+37,false);
  out.write("\n<ASM-CONCURRENT-BEGIN>\n".getBytes(StandardCharsets.UTF_8));
  CountDownLatch gate=new CountDownLatch(8);List<Thread> threads=new ArrayList<>();
  for(int i=0;i<8;i++){final int index=i;Thread t=new Thread(()->{try{gate.countDown();gate.await();byte[] b=("worker-%02d ".formatted(index)+"x".repeat(52)+"\n").getBytes(StandardCharsets.UTF_8);for(int j=0;j<128;j++)out.write(b);}catch(Exception e){throw new RuntimeException(e);}});threads.add(t);t.start();}
  for(Thread t:threads)t.join();out.write("<ASM-CONCURRENT-END>\n".getBytes(StandardCharsets.UTF_8));
  Constructor<FileDescriptor> ctor=FileDescriptor.class.getDeclaredConstructor(int.class);ctor.setAccessible(true);
  Method close=FileDescriptor.class.getDeclaredMethod("close0");close.setAccessible(true);invoke(close,ctor.newInstance(2));
  error("real_error_array",many,err,new byte[10000],0,10000,false);
  Files.writeString(Path.of(args[0]),String.join("\n",log),StandardCharsets.US_ASCII);
 }
}
''',encoding='ascii')
    stdout,stderr=output/'oracle-stdout.bin',output/'oracle-stderr.bin'
    if readonly:stdout.write_bytes(b'read-only stdout fixture')
    with stdout.open('rb' if readonly else 'wb') as out,stderr.open('wb') as err:
        process=subprocess.run([home/'bin/java.exe','--add-opens','java.base/java.io=ALL-UNNAMED','-Dfile.encoding=UTF-8',source,protocol,
                              *(['readonly'] if readonly else [])],
            cwd=output,stdout=out,stderr=err,timeout=120,check=False)
    S.check(process.returncode==0 and protocol.is_file(),'JDK standard output oracle failed: '+str(stderr))
    # Reuse the same exact byte/multiset validator by giving the capture files
    # the same labels; no output is parsed as proof merely because Java exited.
    if readonly:
        S.check(stdout.read_bytes()==b'read-only stdout fixture' and not stderr.read_bytes(),'Read-only JDK oracle unexpectedly wrote process std streams')
        capture=dict(unchanged_readonly_stdout=True,empty_stderr=True)
    else:
        (output/'jdk-stdout.bin').write_bytes(stdout.read_bytes());(output/'jdk-stderr.bin').write_bytes(stderr.read_bytes())
        capture=check_captured(output,'jdk')
    records={}
    for line in protocol.read_text().splitlines():
        key,kind,message=line.split('\t')
        records[key]=dict(type=kind,value=message=='true') if kind=='boolean' else dict(type=kind,
            message=None if message=='NULL' else bytes.fromhex(message).decode('utf-16-be','surrogatepass'))
    S.check(len(records)==(3 if readonly else 8),'JDK typed error protocol incomplete')
    return dict(java=S.artifact(home/'bin/java.exe'),source=S.artifact(source),protocol=S.artifact(protocol),
        stdout=S.artifact(stdout),stderr=S.artifact(stderr),capture=capture,cases=records,verified=True)


def compare_errors(record,wanted):
    got={}
    for row in record['standard_output']['protocol']:
        key=row['case'] if row['case']!='bounds' else f"bounds_{row['offset']}_{row['length']}"
        kind='java.lang.NullPointerException' if key=='null_array' else 'java.lang.IndexOutOfBoundsException' if key.startswith('bounds') else 'java.io.IOException'
        got[key]=dict(type=kind,message=row['message'])
    value=record['standard_output']['real_WriteFile_error']
    got['real_error_array']=dict(type='java.io.IOException',message=value['message'])
    S.check(got==wanted,'Original JDK and actual normal-source typed errors differ: '+repr((got,wanted)))
    S.check(value['single_message']==wanted['real_error_array']['message'],'Single/array ERROR_INVALID_HANDLE source formatting differs')
    return dict(verified=True,typed_error_cases=len(got),messages_exact=True,
        invalid_HANDLE_first_call_JDK_compared=True,subsequent_closed_OS_HANDLE_sequence_assumed_stable=False,
        actual_single_ERROR_INVALID_HANDLE_same_message=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path);parser.add_argument('--park-result',type=Path)
    parser.add_argument('--images',type=Path);parser.add_argument('--worker',choices=('string','file'))
    parser.add_argument('--output',type=Path,default=S.ART/'file-output-standard/execution'/uuid4().hex)
    args=parser.parse_args()
    if args.worker:
        images=args.images.resolve();result=worker(images,args.worker);S.write(images.parent/(args.worker+'-output-execution.json'),result)
        os._exit(0)
    else:
        images=args.images.resolve() if args.images else build(args.candidate.resolve(),args.park_result.resolve(),args.output)
        records=[];captures=[];comparisons=[]
        for input_file,observed in ((images,False),(images.parent/'observed/images.json',True)):
            for kind in ('string','file'):
                with (input_file.parent/(kind+'-stdout.bin')).open('wb') as stdout,(input_file.parent/(kind+'-stderr.bin')).open('wb') as stderr:
                    child=subprocess.run([sys.executable,Path(__file__),'--images',input_file,'--worker',kind],stdout=stdout,stderr=stderr,timeout=240,check=False)
                S.check(child.returncode==0,'Original output worker failed: '+str(input_file.parent/(kind+'-stderr.bin')))
                path=input_file.parent/(kind+'-output-execution.json');records.append(S.artifact(path))
                S.check(S.read(path)['verified'],'Source constructor/write/cleanup suite did not complete: '+str(path))
                captures.append(check_captured(input_file.parent,kind,observed))
        wanted=oracle(Path(S.read(images)['accepted_inputs']['oracle_home']),images.parent/'jdk-oracle')
        for row in records[:2]:comparisons.append(compare_errors(S.read(S.checked(row)),wanted['cases']))
        denied=images.parent/'access-denied';readonly=denied/'stdout-readonly.bin';readonly.write_bytes(b'read-only stdout fixture')
        with readonly.open('rb') as out,(denied/'string-stderr.bin').open('wb') as err:
            child=subprocess.run([sys.executable,Path(__file__),'--images',denied/'images.json','--worker','string'],
                stdout=out,stderr=err,timeout=240,check=False)
        S.check(not child.returncode and readonly.read_bytes()==b'read-only stdout fixture' and not (denied/'string-stderr.bin').read_bytes(),
            'Actual read-only standard HANDLE fixture failed')
        denied_result=S.read(denied/'string-output-execution.json');S.check(denied_result['verified'],'Original read-only FOS/PrintStream errors failed')
        denied_oracle=oracle(Path(S.read(images)['accepted_inputs']['oracle_home']),images.parent/'jdk-readonly-oracle',readonly=True)
        errors=denied_result['standard_output']['real_readonly_standard_HANDLE_error']
        observed_denied=dict(readonly_single=dict(type='java.io.IOException',message=errors['single_message']),
            readonly_array=dict(type='java.io.IOException',message=errors['array_message']),
            PrintStream_error=dict(type='boolean',value=errors['PrintStream_error']))
        S.check(observed_denied==denied_oracle['cases'],'Real access-denied source native and PrintStream errors differ from JDK')
        records.append(S.artifact(denied/'string-output-execution.json'))
        for row in records[2:4]:
            cases=S.read(S.checked(row))['standard_output']['controlled_Win32']['cases']
            for case in cases:
                if case['case']=='WriteFile_error':
                    actual=wanted['cases']['real_error_array']['message'] if case['code']==6 else denied_oracle['cases']['readonly_single']['message']
                    S.check(case['message']==actual,'Injected Win32 code has a different source message from actual JDK failure')
        result=dict(verified=True,scope='two_original_FOS_standard_descriptor_write_natives_and_default_PrintStream_subset',
            images=S.artifact(images),executions=records,captures=captures,JDK_oracle=wanted,JDK_comparisons=comparisons,
            read_only_std_HANDLE=dict(JDK_oracle=denied_oracle,actual_source_errors=observed_denied,all_three_equal=True,
                source_FD_or_reference_fields_written=False,standard_HANDLE_not_closed=True),
            complete_bounded_write_semantics_suite=True,whole_FileOutputStream_implemented=False,default_PrintStream_println_passed=False,
            full_System_Phase1_fixture_executed=False,formal_registered=False,game_started=False)
        path=images.parent/'result.json';S.write(path,result);print(path)
