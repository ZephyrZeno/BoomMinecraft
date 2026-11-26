"""Execute unregistered legacy readonly WinNT natives over current formal26 source."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from threading import Barrier,get_native_id
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('windows_queries_candidate',ROOT/'scripts/windows-file-queries-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
S=B.S
L=B.module('canonical-link-response')
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8
JAVA=[('java/lang/String','<init>','([C)V'),('java/lang/Throwable','getMessage','()Ljava/lang/String;'),
    ('java/util/Properties','<init>','()V'),
    ('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;'),
    ('java/lang/System','setProperties','(Ljava/util/Properties;)V'),
    ('java/io/File','<init>','(Ljava/lang/String;)V'),('java/io/File','getPath','()Ljava/lang/String;'),
    ('java/io/File','exists','()Z'),('jdk/internal/misc/Blocker','<clinit>','()V')]


def proc(image,name,result,*arguments):
    value=getattr(image,name);value.restype,value.argtypes=result,arguments;return value


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


def fixtures(summary,classes):
    I=B.module('verify-translation-ir');members=[];owners={};fs=None
    for owner in sorted({key[0] for key in JAVA}):
        [cls]=[row for row in classes if row['name']==owner and row['origin']['loader']=='bootstrap']
        raw=I.Source(S.original_class(summary,cls));owners[owner]=cls['id']
        for ident,method in zip(cls['method_ids'],raw.methods):
            if (owner,method['name'],method['descriptor']) not in JAVA:continue
            body=raw.code(method)
            members.append(dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],owner=owner,
                name=method['name'],descriptor=method['descriptor'],code_sha256=B.hashlib.sha256(body['bytes']).hexdigest()))
        if owner=='java/io/File':
            [index]=[i for i,f in enumerate(raw.fields) if
                (f['name'],f['descriptor'],f['access'])==('FS','Ljava/io/FileSystem;',0x1a)]
            fs=f"boom_s{cls['id']}_{index}"
    S.check(len(members)==len(JAVA) and fs,'Original query constructor/API fixture inventory differs')
    return members,owners,fs


def build(candidate_file,selection,native_manifest,native_execution,output):
    output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated query execution directory required')
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Readonly query source proof changed')
    candidate=S.read(candidate_file);meta=candidate['metadata'];source=meta['source']
    manifest=selection/'closure.json';proof_file=selection/'selection-verification.json'
    closure=S.read(manifest);proof=S.read(proof_file)
    native=S.read(native_manifest);native_proof=native_manifest.with_name('verification.json');accepted=S.read(native_proof)
    observed=S.read(native_execution)
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(manifest)['sha256'] and
        accepted['verified'] and accepted['source_manifest_sha256']==S.digest(native_manifest)['sha256'] and
        observed['source_verification_sha256']==S.digest(native_proof)['sha256'] and
        Path(native['baseline_directory'])==selection and native['accepted_source_verification_sha256']==S.digest(proof_file)['sha256'] and
        observed['cleanup_flags']==7 and observed['worker_failure_state']==0 and
        closure['source_batch_summary_sha256']==meta['base']['batch_summary']['digest']['sha256'],
        'Exact original formal26 source and actual native process evidence required')
    _,summary,classes=S.base(Path(closure['batch']),Path(closure['plan']))
    members,owners,fs=fixtures(summary,classes);methods=source['original_java']+members
    for method in methods:
        selected=closure['selected_methods'].get(str(method['method']))
        S.check(selected and selected['class_id']==method['class_id'] and selected['source_sha256']==method['class_sha256'] and
            selected['code_sha256']==method['code_sha256'],'Original readonly query API fixture not selected: '+str(method))
    diagnostic=S.read(selection/'diagnostic.json')
    [unit]=[u for u in proof['verified_assembly_objects']['units'] if Path(u['assembly']['path']).name=='diagnostic-stops.asm']
    original=S.checked(unit['assembly']).read_text();stops=original;old_object=S.checked(unit['object']);removed=[]
    for method in source['methods']:
        name='boom_m'+str(method['method']);[row]=[r for r in diagnostic['rows'] if r['symbol']==name]
        S.check(row['category']==2 and row['source_sha256']==method['class_sha256'],'Replacement must be the exact original query native stop')
        text=(f'PUBLIC {name}\n{name} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
            f' lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{name} ENDP\n')
        S.check(stops.count(text)==1,'Original query native stop body differs')
        stops=stops.replace(text,'',1);removed.append(dict(symbol=name,source_category=2,
            exact_removed_text=text,sha256=B.hashlib.sha256(text.encode()).hexdigest()))
    lines=(selection/'link.rsp').read_text().splitlines()
    objects=[Path(line[1:-1]) for line in lines if line.startswith('"') and Path(line[1:-1]).suffix.lower()=='.obj']
    libraries=[Path(line[1:-1]) for line in lines if line.startswith('"') and Path(line[1:-1]).suffix.lower()=='.lib']
    S.check(objects.count(old_object)==1,'Original query stop object must occur once')
    inputs=[S.artifact(path) for path in objects+libraries]
    state=S.read(S.checked(meta['input_state']));runtime=Path(state['runtime'])/'boom-runtime.dll';runtime_meta=S.read(runtime.with_name('runtime.json'))
    S.check(S.digest(runtime)['sha256']==runtime_meta['sha256'] and
        all(runtime_meta['sources'].get(name)==sha for name,sha in meta['runtime_kernel_sha256'].items()),
        'Readonly query fixture runtime differs')
    exported={line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')}
    L.verify(selection/'link.rsp',profile='diagnostic',output=selection/'diagnostic-image.dll',objects=objects,
        library_choices=L.diagnostic_libraries(runtime,winsock=True),exports=exported)
    output.mkdir(parents=True)
    asm,obj=output/'remaining-stops.asm',output/'remaining-stops.obj';asm.write_text(stops)
    assembler=Path(candidate['assembler']['path']);linker=assembler.with_name('link.exe')
    with (output/'stops-assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    original_exports,original_imports=B.A.coff_symbols(old_object)
    S.check(B.A.coff_symbols(obj)==(original_exports-{r['symbol'] for r in removed},original_imports),
        'Remaining stop COFF changed beyond seven exact native definitions')
    exported|=set(candidate['exports'])|{f"boom_m{r['method']}" for r in methods}|{fs}
    exported|={f'boom_{kind}{ident}' for kind in ('layout','class') for ident in set(owners.values())|set(source['source_classes'].values())}
    exported|={'boom_heap_ptr','boom_java_string_literals_bind_heap','boom_diagnostic_pool','boom_provider_winnt_file_pool'}
    linked=[obj if p==old_object else p for p in objects]+[S.checked(candidate['object'])]
    dll=output/'windows-file-queries.dll';response=output/'link.rsp'
    response.write_text('\n'.join([*L.PREFIXES['diagnostic'],'/OUT:"'+str(dll)+'"']+
        ['"'+str(p)+'"' for p in linked+libraries]+['/EXPORT:'+n for n in sorted(exported)])+'\n')
    link_proof=L.verify(response,profile='diagnostic',output=dll,objects=linked,
        library_choices=[libraries],exports=exported)
    with (output/'link.log').open('wb') as log:
        subprocess.run([linker,'@'+str(response)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    for record in inputs:S.check(S.artifact(record['path'])==record,'Original source link input changed')
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    config=dict(schema=1,scope='unregistered_seven_readonly_query_candidates_over_formal26_original_source',
        candidate=S.artifact(candidate_file),source_proof=S.artifact(candidate_file.with_name('verification.json')),
        baseline_manifest=S.artifact(manifest),baseline_source_proof=S.artifact(proof_file),
        baseline_native_manifest=S.artifact(native_manifest),baseline_native_proof=S.artifact(native_proof),
        baseline_native_execution=S.artifact(native_execution),original_link_response=S.artifact(selection/'link.rsp'),
        link_inputs=inputs,removed_native_stops=removed,remaining_diagnostic_assembly=S.artifact(asm),remaining_diagnostic_object=S.artifact(obj),
        image=S.artifact(dll),runtime=S.artifact(runtime),link_response=S.artifact(response),link_proof=link_proof,
        execution_tool=S.artifact(Path(__file__)),fixture_methods=members,fixture_classes=owners,source_File_fs_symbol=fs,
        oracle_home=str(Path(catalog['image']['path']).parents[1]),oracle_modules=catalog['image'],
        original_Java_ASM_or_COFF_modified=False,only_seven_exact_native_stops_removed=True,
        runtime572_modified=False,registered_in_shared_runtime=False,executed=False,game_started=False)
    S.write(output/'images.json',config);return output/'images.json'


ORACLE='''import java.io.*;import java.lang.reflect.*;import java.nio.file.*;import java.util.*;
public class WindowsFileQueriesOracle {
 static String decode(String s) {char[] c=new char[s.length()/4];for(int i=0;i<c.length;i++)c[i]=(char)Integer.parseInt(s.substring(4*i,4*i+4),16);return new String(c);}
 static String encode(String s) {StringBuilder b=new StringBuilder();for(char c:s.toCharArray())b.append(String.format("%04x",(int)c));return b.toString();}
 public static void main(String[] args)throws Exception {
  Field ff=File.class.getDeclaredField("FS");ff.setAccessible(true);Object fs=ff.get(null);Class<?> cl=fs.getClass();
  String[] names={"getBooleanAttributes0","getLastModifiedTime0","getLength0","listRoots0","getSpace0","getNameMax0","checkAccess0"};
  Class<?>[][] types={{File.class},{File.class},{File.class},{},{File.class,int.class},{String.class},{File.class,int.class}};
  Method[] methods=new Method[7];for(int i=0;i<7;i++){methods[i]=cl.getDeclaredMethod(names[i],types[i]);methods[i].setAccessible(true);}
  for(String line:Files.readAllLines(Path.of(args[0]))) {String[] p=line.split(" ",-1);int op=Integer.parseInt(p[0]),sel=Integer.parseInt(p[1]);String path=p[2].equals("NULL")?null:decode(p[2]);
   Object[] a=op==3?new Object[]{}:op==5?new Object[]{path}:op==4||op==6?new Object[]{new File(path),sel}:new Object[]{new File(path)};
   try{Object v=methods[op].invoke(fs,a);System.out.println("OK:"+(v instanceof Boolean?((Boolean)v?1:0):v));}catch(InvocationTargetException e){Throwable t=e.getCause();System.out.println("ERROR:"+t.getClass().getName()+":"+encode(t.getMessage()==null?"":t.getMessage()));}
  }
 }
}
'''


def oracle(home,work,cases):
    work.mkdir();source=work/'WindowsFileQueriesOracle.java';source.write_text(ORACLE)
    requests=work/'requests.txt';requests.write_text('\n'.join(f'{op} {selector} '+('NULL' if path is None else
        path.encode('utf-16-be','surrogatepass').hex()) for op,path,selector in cases)+'\n')
    result=subprocess.run([home/'bin/java.exe','--add-opens','java.base/java.io=ALL-UNNAMED',source,requests],
        cwd=work.parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=120)
    (work/'stdout.txt').write_bytes(result.stdout);(work/'stderr.txt').write_bytes(result.stderr)
    S.check(result.returncode==0,'Locked JDK query oracle failed; see '+str(work/'stderr.txt'))
    answers=result.stdout.decode('utf-8').splitlines()
    S.check(len(answers)==len(cases),'Locked JDK query answer count differs')
    return answers,dict(java=S.artifact(home/'bin/java.exe'),source=S.artifact(source),requests=S.artifact(requests),
        stdout=S.artifact(work/'stdout.txt'),stderr=S.artifact(work/'stderr.txt'))


def recheck(images_file,output):
    """Pin a fresh execution harness over the identical sealed native image."""
    S.check(output.resolve().is_relative_to(S.ART) and not output.exists(),'Fresh recheck output required')
    config=S.read(images_file)
    for key in ('candidate','source_proof','baseline_manifest','baseline_source_proof','baseline_native_manifest',
        'baseline_native_proof','baseline_native_execution','remaining_diagnostic_assembly','remaining_diagnostic_object',
        'link_response','image','runtime'):
        S.checked(config[key])
    config['original_images']=S.artifact(images_file)
    config['producer_execution_tool']=config['execution_tool']
    config['execution_tool']=S.artifact(Path(__file__))
    config['relinked']=False
    output.mkdir(parents=True);path=output/'images.json';S.write(path,config);return path


def run(images_file):
    config=S.read(images_file);S.check(S.artifact(Path(__file__))==config['execution_tool'],'Query execution tool changed')
    candidate=S.read(S.checked(config['candidate']));meta=candidate['metadata']['source']
    S.check(B.verify(S.checked(config['candidate']))==S.read(S.checked(config['source_proof'])),'Current query source proof differs')
    for name in ('baseline_manifest','baseline_source_proof','baseline_native_manifest','baseline_native_proof',
        'baseline_native_execution','remaining_diagnostic_assembly','remaining_diagnostic_object','link_response','image'):
        S.checked(config[name])
    for record in config['link_inputs']:
        S.check(S.artifact(Path(record['path']))==record,'Sealed original source/SDK link input changed')
    modules=config['oracle_modules'];digest=S.digest(Path(modules['path']))
    S.check(all(digest[k]==modules['digest'][k] for k in ('size','sha256')),'Locked oracle module catalog changed')
    runtime=S.checked(config['runtime'])
    with os.add_dll_directory(str(runtime.parent)):
        rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(256<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Query heap bind failed')
    allocate=proc(rt,'boom_object_new',P,P,P,P);arrays=proc(rt,'boom_array_new',P,P,c.c_int,U,P)
    classes=dict(meta['source_classes'],**config['fixture_classes']);members=meta['original_java']+config['fixture_methods']
    methods={(m['owner'],m['name'],m['descriptor']):m['method'] for m in members}
    natives={m['operation']:m['method'] for m in meta['methods']};owned=addr(image,'boom_windows_file_queries_owned_buffers')
    def call(ident,context,args):return proc(image,'boom_m'+str(ident),Q,P,P)(context,(Q*max(len(args),1))(*args))
    def source(owner,name,descriptor,args):
        context=Context();value=call(methods[owner,name,descriptor],context,args)
        S.check(not context[0] and not context[3],'Original query fixture Java stopped: '+repr((owner,name,list(context))))
        return value
    def ensure(name):
        context=Context();proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(classes[name])),context)
        S.check(not context[0],'Original query fixture initializer stopped: '+repr((name,list(context))))
    def new(name):
        context=Context();value=allocate(heap,addr(image,'boom_layout'+str(classes[name])),context)
        S.check(value and not context[0],'Normal query fixture allocation failed');return value
    def string(value):
        raw=value.encode('utf-16-le','surrogatepass');context=Context();chars=arrays(heap,len(raw)//2,5,context)
        S.check(chars and not context[0],'Query source char[] allocation failed');c.memmove(chars,raw,len(raw))
        obj=new('java/lang/String');source('java/lang/String','<init>','([C)V',[obj,chars]);return obj
    def text(value):
        chars=source('java/lang/String','toCharArray','()[C',[value])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    ensure('java/lang/String');ensure('java/util/Properties')
    props=new('java/util/Properties');source('java/util/Properties','<init>','()V',[props])
    fixture=images_file.parent/'fixtures';fixture.mkdir()
    values={'java.home':config['oracle_home'],'user.home':str(fixture),'user.dir':str(fixture),
        'user.name':'query-test','java.io.tmpdir':str(fixture),'file.separator':'\\','path.separator':';',
        'os.name':'Windows 10','os.arch':'amd64','os.version':'10.0','file.encoding':'UTF-8',
        'native.encoding':'UTF-8','sun.jnu.encoding':'UTF-8'}
    for key,value in values.items():source('java/util/Properties','setProperty','(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;',[props,string(key),string(value)])
    source('java/lang/System','setProperties','(Ljava/util/Properties;)V',[props])
    ensure('java/io/File');receiver=P.from_address(addr(image,config['source_File_fs_symbol'])).value
    S.check(receiver and P.from_address(receiver-8).value==addr(image,'boom_layout'+str(classes[B.C.OWNER])),
        'Original File.<clinit>/DefaultFileSystem did not construct the real WinNTFileSystem receiver')
    def file(value):
        obj=new('java/io/File');source('java/io/File','<init>','(Ljava/lang/String;)V',[obj,string(value)])
        return obj
    def invoke(op,path=None,selector=0,*,file_object=None,check_idle=True):
        args=[] if op==3 else [receiver,string(path) if path is not None else 0] if op==5 else [
            receiver,file(path) if file_object is None else file_object]
        if op in (4,6):args.append(selector)
        context=Context();value=call(natives[op],context,args)
        S.check(not context[3] and (not check_idle or Q.from_address(owned).value==0),'Query leaked a frame or native path')
        if not context[0]:
            result=c.c_int64(value).value if op in (1,2,4) else value
            return 'OK:'+str(result),result
        error=P.from_address(c.addressof(context)+16).value
        S.check(op==5 and context[0]==16 and error and P.from_address(error-8).value==addr(image,'boom_layout'+str(classes['java/io/IOException'])),
            'Query failure is not original typed IOException: '+repr((op,path,list(context))))
        message=source('java/lang/Throwable','getMessage','()Ljava/lang/String;',[error])
        return 'ERROR:java.io.IOException:'+text(message).encode('utf-16-be','surrogatepass').hex(),0
    (fixture/'directory').mkdir();(fixture/'MiXeD.TxT').write_bytes(b'legacy-query\0' * 17)
    (fixture/'hidden.dat').write_bytes(b'hidden');(fixture/'readonly.dat').write_bytes(b'readonly')
    kernel=c.WinDLL('kernel32',use_last_error=True)
    setattrs=proc(kernel,'SetFileAttributesW',U,c.c_wchar_p,U)
    S.check(setattrs(str(fixture/'hidden.dat'),2) and setattrs(str(fixture/'readonly.dat'),1),'Query fixture flags failed')
    longdir=fixture/('a'*100)/('b'*100)/('c'*60)
    extended_longdir=Path('\\\\?\\'+str(longdir));extended_longdir.mkdir(parents=True)
    (extended_longdir/'long.txt').write_bytes(b'long')
    create=proc(kernel,'CreateFileW',P,c.c_wchar_p,U,U,P,U,U,P);close=proc(kernel,'CloseHandle',U,P)
    (fixture/'pre-epoch.dat').write_bytes(b'pre-epoch')
    epoch_handle=create(str(fixture/'pre-epoch.dat'),0x100,7,None,3,0,None)
    S.check(epoch_handle and epoch_handle!=P(-1).value,'Pre-epoch query fixture handle failed')
    try:
        epoch=Q((11644473600000-1001)*10000+9999)
        S.check(proc(kernel,'SetFileTime',U,P,P,P,P)(epoch_handle,None,None,c.byref(epoch)),
            'Pre-epoch FILETIME fixture failed')
    finally:S.check(close(epoch_handle),'Pre-epoch fixture close failed')
    junction=fixture/'junction'
    link=subprocess.run(['cmd.exe','/c','mklink','/J',str(junction),str(fixture/'directory')],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    (images_file.parent/'junction-create.log').write_bytes(link.stdout+link.stderr)
    paths=['MiXeD.TxT','mixed.txt','directory','hidden.dat','readonly.dat','missing','', '.', '..',
        'NUL','CON','PRN','AUX','COM1','LPT9','CLOCK$',r'\\.\NUL',r'\\.\COM1',
        'MiXeD.TxT\0ignored','MiXeD.TxT\\','*','MiXeD?TxT','bad:name','bad<name','\ud800.txt',
        str(longdir/'long.txt'),os.path.relpath(longdir/'long.txt',fixture),'junction','pre-epoch.dat']
    # Native zero methods see File's normal normalized source path. File.exists
    # has an additional Java invalid-path check and is a separate observation.
    cases=[(op,path,0) for path in paths for op in (0,1,2)]
    cases += [(6,path,access) for path in ('MiXeD.TxT','directory','readonly.dat','missing','NUL') for access in (1,2,4,0,3)]
    root=fixture.anchor;cases += [(3,None,0),(5,None,0),(5,root,0),(5,'',0),(5,'Q:\\',0),(5,'bad<name',0)]
    prior=Path.cwd();os.chdir(fixture)
    unix_socket=None;winsock=None
    try:
        # A real filesystem AF_UNIX reparse point exercises the special
        # ERROR_CANT_ACCESS_FILE branch rather than treating all reparse alike.
        winsock=c.WinDLL('ws2_32')
        wsadata=c.create_string_buffer(512)
        S.check(proc(winsock,'WSAStartup',c.c_int,c.c_uint16,P)(0x202,wsadata)==0,'AF_UNIX fixture Winsock startup failed')
        unix_socket=proc(winsock,'socket',c.c_size_t,c.c_int,c.c_int,c.c_int)(1,1,0)
        S.check(unix_socket!=c.c_size_t(-1).value,'AF_UNIX fixture socket failed')
        sockaddr=c.create_string_buffer(110);c.c_uint16.from_buffer(sockaddr).value=1
        c.memmove(c.addressof(sockaddr)+2,b'unix.sock\0',10)
        S.check(proc(winsock,'bind',c.c_int,c.c_size_t,P,c.c_int)(unix_socket,sockaddr,110)==0,
            'AF_UNIX fixture bind failed: '+str(proc(winsock,'WSAGetLastError',c.c_int)()))
        cases += [(op,'unix.sock',0) for op in (0,1,2)]
        process=proc(kernel,'GetCurrentProcess',P)()
        handle_count_api=proc(kernel,'GetProcessHandleCount',U,P,P)
        def handles():
            count=U();S.check(handle_count_api(process,c.byref(count)),'Process handle count query failed');return count.value
        expected,oracle_proof=oracle(Path(config['oracle_home']),fixture/'oracle',cases)
        handles_before=handles()
        actual=[invoke(*row)[0] for row in cases]
        handles_after=handles()
        S.check(handles_after==handles_before,'Readonly native batch retained a Windows handle')
        comparisons=[dict(operation=op,path_UTF16=None if path is None else path.encode('utf-16-be','surrogatepass').hex(),
            selector=selector,actual=value,JDK=wanted) for (op,path,selector),value,wanted in zip(cases,actual,expected)]
        S.write(images_file.parent/'jdk-comparisons.json',dict(oracle=oracle_proof,rows=comparisons))
        S.check(actual==expected,'Legacy query/JDK mismatch: '+repr([row for row in comparisons if row['actual']!=row['JDK']]))
        # Sharing violations exercise the *different* attribute and length
        # fallback rules. Exact case matching is required by the length C code.
        handle=create(str(fixture/'MiXeD.TxT'),0x80000000,0,None,3,0,None)
        S.check(handle and handle!=P(-1).value,'Exclusive readonly query fixture handle failed')
        try:
            sharing_cases=[(op,path,0) for path in ('MiXeD.TxT','mixed.txt','MiXeD.*','missing') for op in (0,1,2)]
            sharing_expected,sharing_oracle=oracle(Path(config['oracle_home']),fixture/'oracle-sharing',sharing_cases)
            sharing_actual=[invoke(*row)[0] for row in sharing_cases]
            S.write(images_file.parent/'sharing-comparisons.json',dict(oracle=sharing_oracle,
                cases=sharing_cases,actual=sharing_actual,JDK=sharing_expected))
            S.check(sharing_actual==sharing_expected,'Sharing fallback differs from legacy JDK')
        finally:S.check(close(handle),'Exclusive query fixture handle cleanup failed')
        # Capacity is stable; free/usable are live counters. Compare both with
        # JDK and immediate SDK observations, preserving the measured tolerance.
        space_cases=[(4,str(fixture),selector) for selector in range(3)]
        space_jdk,space_oracle=oracle(Path(config['oracle_home']),fixture/'oracle-space',space_cases)
        space_actual=[invoke(*row)[1] for row in space_cases]
        getdisk=proc(kernel,'GetDiskFreeSpaceExW',U,c.c_wchar_p,P,P,P);usable,total,free=Q(),Q(),Q()
        S.check(getdisk(root,c.byref(usable),c.byref(total),c.byref(free)),'SDK free space observation failed')
        sdk=[total.value,free.value,usable.value]
        S.check(space_actual[0]==int(space_jdk[0][3:])==sdk[0] and all(abs(a-b)<=16*1024*1024 for a,b in
            zip(space_actual[1:],[int(v[3:]) for v in space_jdk[1:]])) and
            all(abs(a-b)<=65536 for a,b in zip(space_actual[1:],sdk[1:])),
            'Live query capacity/free space differs from SDK/JDK observations')
        barrier=Barrier(8);shared_file=file('MiXeD.TxT');shared_dir=file('directory');root_string=string(root)
        rounds=32
        def worker(index):
            barrier.wait();answers=[]
            for iteration in range(rounds):
                for op,obj,wanted in ((0,shared_file,3),(2,shared_file,221),(0,shared_dir,5)):
                    context=Context();value=call(natives[op],context,[receiver,obj])
                    S.check(value==wanted and not any(context),'Concurrent readonly native query differed')
                context=Context();value=call(natives[6],context,[receiver,shared_file,4])
                S.check(value==1 and not any(context),'Concurrent access query differed')
                context=Context();value=call(natives[5],context,[receiver,root_string])
                S.check(value>0 and not any(context),'Concurrent volume query differed');answers.append(value)
            return dict(OS_thread=get_native_id(),calls=rounds*5,max_component_lengths=sorted(set(answers)))
        with ThreadPoolExecutor(max_workers=8) as pool:concurrent=list(pool.map(worker,range(8)))
        S.check(len({r['OS_thread'] for r in concurrent})==8 and not Q.from_address(owned).value,'Concurrent query native paths leaked')
        invalid=[]
        for op,args in ((0,[receiver,0]),(0,[receiver,string('wrong File')]),(0,[0,shared_file]),(0,[shared_file,shared_file]),
            (4,[receiver,shared_file,3])):
            context=Context();value=call(natives[op],context,args)
            S.check(value==0 and context[0] in (4,7) and not context[3] and not Q.from_address(owned).value,'Invalid query input was not rejected')
            invalid.append(dict(operation=op,context=list(context)))
        pending=[]
        for op in range(7):
            context=Context(77,91,0x12345678,0,7,8,9,10);before=list(context)
            value=call(natives[op],context,[0,0,0]);S.check(value==0 and list(context)==before,'Query changed an existing exception')
            pending.append(op)
        context=Context();exists=call(methods['java/io/File','exists','()Z'],context,[shared_file])
        java_boundary=dict(method=methods['java/io/File','exists','()Z'],result=exists,context=list(context),
            expected_unexecuted_Phase1_Blocker_boundary=True,source_Java_exists_chain_passed=False)
        S.check(not exists and context[0]==20 and context[1]==37,'File.exists source boundary differs from original Blocker initialization')
        S.write(images_file.parent/'source-Java-entry-boundary.json',java_boundary)
    finally:
        if unix_socket is not None:
            S.check(proc(winsock,'closesocket',c.c_int,c.c_size_t)(unix_socket)==0,'AF_UNIX fixture close failed')
        if winsock is not None:S.check(proc(winsock,'WSACleanup',c.c_int)()==0,'AF_UNIX fixture Winsock cleanup failed')
        os.chdir(prior);setattrs(str(fixture/'readonly.dat'),0x80)
    S.check(not Q.from_address(owned).value,'Readonly query owned native allocations remain')
    S.check(proc(rt,'boom_heap_destroy',U,P)(heap)==1,'Readonly query heap cleanup failed')
    return dict(schema=1,verified=True,scope='seven_unregistered_original_legacy_readonly_natives_over_formal26_source',
        images=S.artifact(images_file),source_proof=config['source_proof'],original_File_String_and_Properties_constructors=True,
        real_File_fs_from_original_class_initialization=True,original_File_path_FieldID_FMAP=True,
        JDK_comparisons=S.artifact(images_file.parent/'jdk-comparisons.json'),
        sharing_comparisons=S.artifact(images_file.parent/'sharing-comparisons.json'),
        AF_UNIX_reparse_socket=True,Windows_handle_counts=dict(before=handles_before,after=handles_after),
        space=dict(JDK_oracle=space_oracle,actual=space_actual,SDK=sdk,JDK_free_tolerance_bytes=16*1024*1024,SDK_free_tolerance_bytes=65536),
        concurrent=dict(workers=concurrent,total_calls=8*rounds*5),invalid_inputs=invalid,pending_exception_operations=pending,
        source_Java_exists_boundary=S.artifact(images_file.parent/'source-Java-entry-boundary.json'),
        System_phase1_executed=False,source_Java_exists_chain_passed=False,owned_native_buffers=0,heap_destroyed=True,
        runtime572_modified=False,shared_provider_registered=False,complete_legacy_filesystem=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path);parser.add_argument('--selection',type=Path)
    parser.add_argument('--native-manifest',type=Path);parser.add_argument('--native-execution',type=Path)
    parser.add_argument('--images',type=Path);parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--recheck-images',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'windows-file-queries/execution'/uuid4().hex)
    args=parser.parse_args()
    if args.recheck_images:images=recheck(args.recheck_images.resolve(),args.output.resolve())
    elif args.images:images=args.images.resolve()
    else:
        S.check(all((args.candidate,args.selection,args.native_manifest,args.native_execution)),'Exact candidate and original source/native proof inputs required')
        images=build(args.candidate.resolve(),args.selection.resolve(),args.native_manifest.resolve(),args.native_execution.resolve(),args.output)
    if args.build_only:print(images)
    else:
        result=run(images);S.write(images.parent/'execution.json',result);print(images.parent/'execution.json')
