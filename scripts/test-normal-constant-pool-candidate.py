"""Fresh normal Java ConstantPool facades over a separately verified CP candidate."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from threading import Barrier,Lock,get_native_id
from uuid import uuid4
import zipfile


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('normal_cp_execution_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('normal-constant-pool-candidate');S=B.S;C=B.C
F=module('formal-provider-selection');D=module('probe-native-provider-prefix');L=module('canonical-link-response')
E=module('existing-source-selection')
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8
CASES=['java/lang/Object','java/lang/String','java/lang/Float','java/lang/Double','java/lang/Deprecated','java/util/regex/Pattern']
SPANS=[('boom_probe_static_roots','boom_probe_static_root_count'),
    ('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),
    ('boom_java_class_roots','boom_java_class_root_count'),('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),
    ('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),
    ('boom_provider_threads_roots','boom_provider_threads_root_count'),
    ('boom_vm_thread_root_cells','boom_vm_thread_root_count')]
TAGS={0:'INVALID',1:'UTF8',3:'INTEGER',4:'FLOAT',5:'LONG',6:'DOUBLE',7:'CLASS',8:'STRING',9:'FIELDREF',10:'METHODREF',
    11:'INTERFACEMETHODREF',12:'NAMEANDTYPE',15:'METHODHANDLE',16:'METHODTYPE',18:'INVOKEDYNAMIC'}


def proc(image,name,result,*args):
    f=getattr(image,name);f.restype,f.argtypes=result,args;return f


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


def build_cases(meta,summary,classes):
    names={row['name']:row for row in classes if row['origin']['loader']=='bootstrap'}
    _,_,_,resolve=C.C.inputs(summary,classes);raw=C.C.RawClasses(summary);cases=[]
    try:
        for name in CASES:
            cls=names[name];parsed=C.parse_class_pool(raw.read(cls));entries=parsed['entries'];selected={0};kinds=set()
            for i,row in enumerate(entries):
                if row[0] in {1,3,4,5,6,7,8,9,10,11,12,15,16,18} and row[0] not in kinds:
                    selected.add(i);kinds.add(row[0])
            for predicate in (lambda s:s=='',lambda s:'\0' in s,lambda s:any(ord(ch)>255 for ch in s)):
                found=next((i for i,r in enumerate(entries) if r[0]==1 and predicate(r[2])),None)
                if found is not None:selected.add(found)
            rows=[]
            for i in sorted(selected):
                tag,_,one,two=entries[i];row=dict(index=i,tag=tag)
                if tag==1:row['utf16']=one.encode('utf-16-le','surrogatepass').hex()
                elif tag in (3,4,5,6):row['bits']=one
                elif tag==7:
                    target=entries[one][2];ident=resolve('bootstrap',target if target.startswith('[') else 'L'+target+';')
                    row.update(class_name=target,target_type=ident)
                elif tag==8:row['utf16']=entries[one][2].encode('utf-16-le','surrogatepass').hex()
                elif tag in (9,10,11):
                    class_name=entries[entries[one][2]][2];nat=entries[two]
                    row.update(class_ref=one,name_type_ref=two,info=[class_name,entries[nat[2]][2],entries[nat[3]][2]])
                elif tag==12:row['info']=[entries[one][2],entries[two][2]]
                elif tag==18:row['name_type_ref']=two
                rows.append(row)
            cases.append(dict(name=name,type_id=cls['id'],source_sha256=cls['origin']['sha256'],size=len(entries),entries=rows))
    finally:raw.close()
    return cases,names


def blocked_class_case(candidate,summary,classes):
    """Choose a genuine original Class reference excluded by the positive proof."""
    with zipfile.ZipFile(C.C.artifact(summary['class_literals']['index'])) as z:
        jcls={row['type_id']:row for line in z.read('types.jsonl').splitlines() if (row:=json.loads(line))}
    types,_,available,resolve=C.C.inputs(summary,classes);types={row['id']:row for row in types}
    base_module=jcls[candidate['metadata']['source']['pool_class']]['module']
    raw=C.C.RawClasses(summary)
    try:
        for cls in classes:
            if cls['id'] not in available or cls.get('parse_error') or cls['access']&0x8000 or \
                jcls.get(cls['id'],{}).get('module')!=base_module:continue
            parsed=C.parse_class_pool(raw.read(cls))
            for index,(tag,_,one,_) in enumerate(parsed['entries']):
                if tag!=7:continue
                name=parsed['entries'][one][2]
                target=resolve(cls['origin']['loader'],name if name.startswith('[') else 'L'+name+';')
                if target is not None and not C.class_reference_access(cls['id'],target,jcls,types,classes):
                    return dict(owner=cls['name'],owner_type=cls['id'],index=index,target=name,target_type=target,
                        reason='unproven_static_class_access_remains_context20_not_a_JDK_rejection_claim')
    finally:raw.close()
    raise ValueError('Expected an explicitly unproven original Class reference in this closed catalogue')


def request_model(candidate_file,state_file):
    candidate=S.read(candidate_file);meta=candidate['metadata']['source']
    state,values,_=F.state_inputs(state_file);identity,summary,classes=S.base(values['batch'],values['plan'])
    S.check(identity==candidate['metadata']['base'],'CP focused source and candidate must use exactly the same current base')
    supported={r['name'].removesuffix('0') for r in meta['methods'] if r['owner']==C.CP}
    members=[r for r in meta['original_java'] if r['owner']==C.CP and r['name'] in supported]
    I=C.I
    wanted=[('java/lang/String','toCharArray','()[C'),('java/lang/Throwable','getMessage','()Ljava/lang/String;'),
            ('java/lang/Enum','name','()Ljava/lang/String;')]
    cases,names=build_cases(meta,summary,classes)
    for owner in {v[0] for v in wanted}:
        cls=names[owner];raw=I.Source(S.original_class(summary,cls))
        for ident,m in zip(cls['method_ids'],raw.methods):
            if (owner,m['name'],m['descriptor']) not in wanted:continue
            body=raw.code(m);members.append(dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],owner=owner,
                name=m['name'],descriptor=m['descriptor'],code_sha256=hashlib.sha256(body['bytes']).hexdigest()))
    S.check(len(members)==len(supported)+3,'Missing original public CP facade or observation getter')
    members += [row for row in meta['original_java'] if row['method'] in meta['required_java_methods']]
    # Collection implementations are ordinary source-only admission groups for
    # the real Reflection.registerFieldsToFilter class initializer.
    groups=[row for row in classes if row['origin']['loader']=='bootstrap' and
        (row['name'] in ('java/util/HashMap','java/util/HashSet','java/util/AbstractMap','java/util/AbstractSet','java/util/AbstractCollection') or
         row['name'].startswith(('java/util/HashMap$','java/util/HashSet$','java/util/ImmutableCollections')))]
    admitted=[]
    for cls in groups:
        raw=I.Source(S.original_class(summary,cls))
        admitted.extend(ident for ident,m in zip(cls['method_ids'],raw.methods) if raw.code(m) is not None)
    return dict(candidate=S.artifact(candidate_file),state=S.artifact(state_file),source=meta,members=members,cases=cases,
        blocked_class_reference=blocked_class_case(candidate,summary,classes),
        collection_source_admission_classes=[r['id'] for r in groups],source_only_admitted_methods=sorted(admitted),
        class_roots=[('bootstrap',n) for n in (C.CP,'java/lang/String','java/lang/Class','java/lang/IllegalArgumentException','java/lang/Throwable')],
        method_roots=[('bootstrap',m['owner'],m['name'],m['descriptor']) for m in members]+[
            ('bootstrap',C.OWNER,'getConstantPool','()Ljdk/internal/reflect/ConstantPool;'),
            ('bootstrap','java/lang/String','intern','()Ljava/lang/String;')])


def prepare(candidate_file,state_file,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART/'normal-constant-pool') and not output.exists(),'Fresh CP component output required')
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'CP current source/canonical COFF proof changed')
    model=request_model(candidate_file,state_file);output.mkdir(parents=True);S.write(output/'request.json',model)
    meta=model['source'];exports={'boom_java_class_pool','boom_heap_ptr','boom_java_string_literals_bind_heap','boom_release_trace_pool',
        'boom_diagnostic_pool',f"boom_class{meta['pool_class']}",f"boom_layout{meta['pool_class']}"}
    exports|={f"boom_m{r['method']}" for r in model['members']+meta['methods']}
    optional={symbol for pair in SPANS for symbol in pair}
    return F.prepare(state_file,output/'source-selection',method_roots=model['method_roots'],class_roots=model['class_roots'],
        admitted_methods=model['source_only_admitted_methods'],exports=sorted(exports),optional_exports=sorted(optional),
        harness_sources=[output/'request.json',ROOT/'scripts/normal-constant-pool-source.py',ROOT/'native/providers/normal_constant_pool.asm.inc'])


ROOT_ASM='''option casemap:none
.data
ALIGN 8
PUBLIC boom_CP_test_roots
boom_CP_test_roots QWORD 64 DUP(0)
.const
PUBLIC boom_CP_test_root_count
boom_CP_test_root_count QWORD 64
.code
PUBLIC boom_CP_test_save
boom_CP_test_save PROC
 cmp ecx,64
 jae CP_test_save_zero
 lea rax,boom_CP_test_roots
 mov QWORD PTR [rax+rcx*8],rdx
 mov eax,1
 ret
CP_test_save_zero:
 xor eax,eax
 ret
boom_CP_test_save ENDP
END
'''


def link(images_file,request_file,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART/'normal-constant-pool') and not output.exists(),'Fresh CP execution image directory required')
    focused=S.read(images_file)
    if focused.get('scope')==E.SCOPE:E.verify(images_file)
    else:F.verify(images_file)
    model=S.read(request_file);candidate_file=S.checked(model['candidate'])
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'CP candidate changed before overlay link')
    candidate=S.read(candidate_file);selection=Path(focused['source_selection_directory']);closure=S.read(selection/'closure.json')
    source_proof=S.read(S.checked(focused['source_selection']));diagnostic=S.read(selection/'diagnostic.json')
    S.check(focused['base']==candidate['metadata']['base'],'Fresh CP selection/candidate source base mismatch')
    for method in model['members']:
        actual=closure['selected_methods'].get(str(method['method']))
        S.check(actual and actual['class_id']==method['class_id'] and actual['source_sha256']==method['class_sha256'] and
            actual['code_sha256']==method['code_sha256'],'Original CP public Java facade is not selected')
    [cp_class]=[r for r in closure['selected_classes'] if r['class_id']==model['source']['pool_class']]
    S.check(cp_class['initializer'] is not None,'Normal CP descriptor has no original class initializer')
    targets={f"boom_m{r['method']}" for r in model['source']['methods']}
    rows=[r for r in diagnostic['rows'] if r['symbol'] in targets]
    S.check({r['symbol'] for r in rows}==targets and all(r['category']==2 for r in rows),'CP overlay must remove exactly the supported original native stops')
    [unit]=[r for r in source_proof['verified_assembly_objects']['units'] if Path(r['assembly']['path']).name=='diagnostic-stops.asm']
    original=S.checked(unit['assembly']).read_bytes();remaining,delta=D.remove_stops(original,rows,bool(closure.get('diagnostic_context_rows')),targets)
    output.mkdir(parents=True);assembler=Path(candidate['assembler']['path']);asm=output/'remaining-stops.asm';obj=asm.with_suffix('.obj')
    asm.write_bytes(remaining)
    with (output/'stops.log').open('xb') as log:subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True)
    root_asm=output/'test-roots.asm';root_obj=root_asm.with_suffix('.obj');root_asm.write_text(ROOT_ASM)
    with (output/'roots.log').open('xb') as log:subprocess.run([assembler,'/nologo','/c','/Fo'+str(root_obj),root_asm],stdout=log,stderr=subprocess.STDOUT,check=True)
    root_exports={'boom_CP_test_roots','boom_CP_test_root_count','boom_CP_test_save'}
    S.check(B.A.coff_symbols(root_obj)==(root_exports,set()),'Test root-bank actual COFF has extra behavior')
    objects=[Path(r['path']) for r in focused['link_inputs'] if Path(r['path']).suffix.lower()=='.obj']
    old=S.checked(unit['object']);S.check(objects.count(old)==1,'Original focused stop object is not present exactly once')
    objects=[obj if r==old else r for r in objects]+[S.checked(candidate['object']),S.checked(candidate['ROM_object']),root_obj]
    runtime=S.checked(focused['runtime']);families=focused['selected_provider_families']
    libraries=L.diagnostic_libraries(runtime,winsock='normal-native-libraries-v1' in families)[0]
    exports=set(closure['exports'])|set(candidate['exports'])|C.ROM_EXPORTS|root_exports
    exports|={f"boom_m{row['method']}" for row in model['members']}
    # Observation symbols already have actual normal selected definitions. They
    # do not create layouts, owner cells or additional Java state.
    exports.add('boom_layout'+str(model['source']['error_class']))
    exports|={r['symbol'] for r in closure.get('selected_provider_native_root_spans',[])}
    selected_classes={r['class_id'] for r in closure['selected_classes']}
    observed_classes=[dict(name=r['name'],type_id=r['type_id'],state_symbol='boom_class'+str(r['type_id']))
        for r in model['cases'] if r['type_id'] in selected_classes]
    exports|={r['state_symbol'] for r in observed_classes}
    public=set();foreign={'WaitOnAddress','WakeByAddressAll'}
    for provider in focused['providers']:
        if provider['selected']:foreign.update(S.read(S.checked(provider['manifest'])).get('allowed_foreign_imports',[]))
    for path in objects:public.update(B.A.coff_symbols(path,foreign)[0])
    public.update(F.module('cp_runtime_exports','diagnostic-closure.py').pe_exports(runtime))
    for pair in SPANS:
        S.check(not (set(pair)&public) or set(pair)<=public,'Selected source root-bank pair has only one actual definition')
        if set(pair)<=public:exports.update(pair)
    S.check(exports<=public,
        'CP observation export has no actual selected COFF/runtime definition')
    image=output/'constant-pool.dll';rsp=output/'link.rsp'
    rsp.write_text('\n'.join([*L.PREFIXES['diagnostic'],'/OUT:"'+str(image)+'"']+['"'+str(p)+'"' for p in objects+libraries]+
        ['/EXPORT:'+n for n in sorted(exports)])+'\n')
    link_proof=L.verify(rsp,profile='diagnostic',output=image,objects=objects,library_choices=[libraries],exports=exports)
    with (output/'link.log').open('xb') as log:subprocess.run([assembler.with_name('link.exe'),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    state=S.read(S.checked(model['state']));_,summary,_=S.base(Path(state['batch']),Path(state['plan']))
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    inputs=[S.artifact(p) for p in [*objects,*libraries,runtime,images_file,request_file,candidate_file,candidate_file.with_name('verification.json'),
        selection/'closure.json',selection/'diagnostic.json',focused['source_selection']['path'],rsp,asm,root_asm,Path(__file__)]]
    spans=[dict(symbol=a,count_symbol=b) for a,b in SPANS if {a,b}<=exports]
    spans+=[dict(symbol='boom_CP_test_roots',count_symbol='boom_CP_test_root_count')]
    spans+=[dict(symbol=r['symbol'],count=r['count']) for r in closure.get('selected_provider_native_root_spans',[])]
    result=dict(schema=1,scope='fresh_current_source_14_unregistered_CP_natives_with_intact_public_Java_facades',
        source_images=S.artifact(images_file),request=S.artifact(request_file),candidate=S.artifact(candidate_file),
        candidate_proof=S.artifact(candidate_file.with_name('verification.json')),image=S.artifact(image),runtime=S.artifact(runtime),
        inputs=inputs,link_response=S.artifact(rsp),link_proof=link_proof,stop_complement=delta,
        execution_tool=S.artifact(Path(__file__)),root_spans=spans,represented_class_observations=observed_classes,
        oracle_home=str(Path(catalog['image']['path']).parents[1]),
        oracle_modules=catalog['image'],class_state_modified=False,original_Java_Code_modified=False,
        original_CP_class=cp_class,current_full_selection_independently_verified=True,shared_provider_registered=False,
        source_only_pending_provider_state=state['status'],source_scope=focused['scope'],
        additional_CP_code_and_ROM_in_original_full_source_verification=False,
        runtime_acceptance_claimed=False,executed=False,game_started=False)
    path=output/'images.json';S.write(path,result);return path


ORACLE='''import java.lang.reflect.*;import java.nio.file.*;import java.util.*;
class NormalConstantPoolOracle {
 static String hex(String s){StringBuilder b=new StringBuilder();for(char c:s.toCharArray())b.append(String.format("%02x%02x",((int)c)&255,((int)c)>>8));return b.toString();}
 public static void main(String[] args)throws Exception{
  Method factory=Class.class.getDeclaredMethod("getConstantPool");factory.setAccessible(true);
  Map<String,Object> pools=new HashMap<>();Map<String,Method> methods=new HashMap<>();
  for(String line:Files.readAllLines(Path.of(args[0]))){String[] p=line.split("\\t");String name=p[0],kind=p[1];int index=Integer.parseInt(p[2]);
   Object cp=pools.get(name);if(cp==null){cp=factory.invoke(Class.forName(name.replace('/','.'),false,ClassLoader.getSystemClassLoader()));pools.put(name,cp);}
   String getter=switch(kind){case "SIZE"->"getSize";case "TAG"->"getTagAt";case "UTF"->"getUTF8At";case "STR"->"getStringAt";case "INT"->"getIntAt";case "FLOAT"->"getFloatAt";case "LONG"->"getLongAt";case "DOUBLE"->"getDoubleAt";case "CLASS"->"getClassAt";case "MEMBER"->"getMemberRefInfoAt";case "NAT"->"getNameAndTypeRefInfoAt";case "CLASSREF"->"getClassRefIndexAt";case "NATREF"->"getNameAndTypeRefIndexAt";default->kind;};
   Method m=methods.get(getter);if(m==null){m=cp.getClass().getDeclaredMethod(getter,getter.equals("getSize")?new Class<?>[0]:new Class<?>[]{int.class});m.setAccessible(true);methods.put(getter,m);}
   try{Object value=m.invoke(cp,getter.equals("getSize")?new Object[0]:new Object[]{index});String out;
    if(value instanceof String s)out=hex(s);else if(value instanceof String[] a){StringJoiner j=new StringJoiner(",");for(String s:a)j.add(hex(s));out=j.toString();}
    else if(value instanceof Float f)out=Integer.toUnsignedString(Float.floatToRawIntBits(f),16);else if(value instanceof Double d)out=Long.toUnsignedString(Double.doubleToRawLongBits(d),16);
    else if(value instanceof Long l)out=Long.toUnsignedString(l,16);else if(kind.equals("INT"))out=Integer.toUnsignedString((Integer)value,16);
    else if(value instanceof Class<?> c)out=c.getName().replace('.','/');else if(value instanceof Enum<?> e)out=e.name();else out=value.toString();
    System.out.println(name+"\\t"+kind+"\\t"+index+"\\tOK\\t"+out);
   }catch(InvocationTargetException e){Throwable t=e.getCause();System.out.println(name+"\\t"+kind+"\\t"+index+"\\tERR\\t"+t.getClass().getName()+"\\t"+hex(t.getMessage()));}
  }
 }
}
'''


def oracle(model,output,home):
    requests=[];expected=[]
    def add(case,kind,index,value):
        requests.append(case['name']+'\t'+kind+'\t'+str(index))
        expected.append((case['name'],kind,index,value))
    for case in model['cases']:
        add(case,'SIZE',-1,str(case['size']))
        for entry in case['entries']:
            index,tag=entry['index'],entry['tag'];add(case,'TAG',index,TAGS[tag])
            if tag in (1,8):add(case,'UTF' if tag==1 else 'STR',index,entry['utf16'])
            elif tag in (3,4,5,6):add(case,{3:'INT',4:'FLOAT',5:'LONG',6:'DOUBLE'}[tag],index,format(entry['bits'],'x'))
            elif tag==7 and entry['target_type'] is not None:add(case,'CLASS',index,entry['class_name'])
            elif tag in (9,10,11,12):
                add(case,'NAT' if tag==12 else 'MEMBER',index,','.join(s.encode('utf-16-le','surrogatepass').hex() for s in entry['info']))
                if tag!=12:add(case,'CLASSREF',index,str(entry['class_ref']))
            if tag in (9,10,11,18):add(case,'NATREF',index,str(entry['name_type_ref']))
    first=model['cases'][0]
    for getter,index in [('getUTF8At',-1),('getIntAt',first['size']),('getUTF8At',0),('getDoubleAt',0)]:
        requests.append(first['name']+'\t'+getter+'\t'+str(index))
    request=output/'oracle-requests.tsv';request.write_text('\n'.join(requests)+'\n',encoding='utf-8')
    source=output/'NormalConstantPoolOracle.java';source.write_text(ORACLE,encoding='utf-8')
    result=subprocess.run([home/'bin/java.exe','--add-opens','java.base/java.lang=ALL-UNNAMED','--add-opens',
        'java.base/jdk.internal.reflect=ALL-UNNAMED',source,request],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    stdout=output/'oracle.stdout.txt';stderr=output/'oracle.stderr.txt';stdout.write_bytes(result.stdout);stderr.write_bytes(result.stderr)
    S.check(result.returncode==0,'Locked JDK CP oracle failed')
    lines=result.stdout.decode('utf-8').splitlines();S.check(len(lines)==len(requests),'CP JDK oracle row count differs')
    for actual,(owner,kind,index,value) in zip(lines,expected):
        S.check(actual.split('\t')==[owner,kind,str(index),'OK',value],'Original CP model/native comparison differs from JDK: '+actual)
    errors=[]
    for actual in lines[len(expected):]:
        owner,kind,index,status,error,message=actual.split('\t');S.check(status=='ERR','Expected original JDK typed CP failure')
        errors.append(dict(getter=kind,index=int(index),error=error.replace('.','/'),message=bytes.fromhex(message).decode('utf-16-le')))
    return errors,dict(java=S.artifact(home/'bin/java.exe'),source=S.artifact(source),requests=S.artifact(request),
        stdout=S.artifact(stdout),stderr=S.artifact(stderr),compared_successful_rows=len(expected),compared_failures=len(errors))


def run(images_file):
    config=S.read(images_file);output=images_file.parent
    S.check(config['execution_tool']==S.artifact(Path(__file__)),'CP execution tool changed')
    for record in config['inputs']:D.checked(record)
    candidate=S.read(S.checked(config['candidate']));meta=candidate['metadata']['source'];model=S.read(S.checked(config['request']))
    S.check(B.verify(S.checked(config['candidate']))==S.read(S.checked(config['candidate_proof'])),'Current CP source/ROM/kernel verification differs')
    runtime=S.checked(config['runtime'])
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'CP normal heap binding failed')
    # Normal VM String initialization precedes metadata APIs. Its original Java
    # initializer sets COMPACT_STRINGS; the host never writes that field/state.
    string_state=addr(image,'boom_class'+str(meta['string_class']));string_before=U.from_address(string_state+8).value
    string_context=Context();string_result=proc(rt,'boom_class_ensure32',U,P,P)(string_state,string_context)
    string_after=U.from_address(string_state+8).value
    S.check(string_before==0 and string_result==0 and string_context[0]==string_context[3]==0 and
        not P.from_address(c.addressof(string_context)+16).value and string_after==2,
        'Original VM String prerequisite did not initialize normally from cold state')
    string_bootstrap=dict(before=string_before,after=string_after,context=list(string_context),result=string_result,
        original_Java_initializer_executed=True,host_Java_fields_written=False)
    members={(r['owner'],r['name']):r['method'] for r in model['members']}
    native={r['name']:r['method'] for r in meta['methods']};pool=addr(image,'boom_java_class_pool')
    diagnostic=S.read(Path(S.read(S.checked(config['source_images']))['source_selection_directory'])/'diagnostic.json')
    failure_lock=Lock()
    def call(ident,args,check=True,ctx=None):
        ctx=Context() if ctx is None else ctx;value=proc(image,'boom_m'+str(ident),Q,P,P)(ctx,(Q*max(1,len(args)))(*args))
        if check and ctx[0]:
            counter=addr(image,'boom_diagnostic_pool');row_id=U.from_address(counter+32).value
            status=U.from_address(counter+8).value
            row=diagnostic['rows'][row_id-1] if status==2 and 0<row_id<=len(diagnostic['rows']) else None
            first=dict(status=status,row_id=row_id,kind=U.from_address(counter+56).value,
                pc=U.from_address(counter+44).value,method=U.from_address(counter+48).value,
                depth=U.from_address(counter+52).value,Context_address=Q.from_address(counter+80).value)
            p=output/'first-failure.json'
            with failure_lock:
                if not p.exists():S.write(p,dict(context=list(ctx),method=ident,row=row,diagnostic_global_first_stop=first,
                    row_is_global_first_stop=row is not None,
                    current_Context_is_global_first_stop=bool(row is not None and first['Context_address']==c.addressof(ctx)),
                    images=S.artifact(images_file)))
            raise ValueError('Original CP source failed: '+repr((ident,list(ctx),row['symbol'] if row else None)))
        S.check(not ctx[3],'CP native/Java frame depth leaked');return ctx,value
    def java(name,args):return call(members[C.CP,name],args)[1]
    def mirror(ident):
        ctx=Context();value=proc(rt,'boom_java_class_load',P,P,P,U)(ctx,pool,ident)
        S.check(value and not ctx[0],'Normal source Class mirror unavailable');return value
    def utf16(value):
        chars=call(members['java/lang/String','toCharArray'],[value])[1]
        return c.string_at(chars,Q.from_address(chars-16).value).hex()
    def array(value):return list((Q*(Q.from_address(value-16).value//8)).from_address(value))
    def class_id(value):
        ctx=Context();ident=proc(rt,'boom_java_class_typeid',U,P,P,P)(ctx,pool,value)
        S.check(not ctx[0],'Result is not a registered normal Class mirror');return ident
    cp_state=addr(image,'boom_class'+str(meta['pool_class']));S.check(U.from_address(cp_state+8).value==0,'CP class is not cold')
    save=proc(image,'boom_CP_test_save',U,U,P);answers=[];wrappers=[]
    summary=S.read(S.checked(candidate['metadata']['base']['batch_summary']))
    with zipfile.ZipFile(C.C.artifact(summary['runtime_metadata']['index'])) as z:
        empty_types=[row for line in z.read('types.jsonl').splitlines() if
            (row:=json.loads(line)) and (row['defining_loader'],row['name']) in {('bootstrap','I'),('bootstrap','[I')}]
    S.check({r['name'] for r in empty_types}=={'I','[I'},'Normal primitive and array type identities are missing')
    primitive_array=[]
    for row in empty_types:
        ctx,value=call(native['getConstantPool'],[mirror(row['id'])])
        S.check(not value and U.from_address(cp_state+8).value==0,'Primitive/array CP factory spuriously initialized the wrapper')
        primitive_array.append(dict(type_id=row['id'],name=row['name'],context=list(ctx),result=value))
    # First CP construction races on the actual original Reflection/ConstantPool
    # class initializer. Only the fixture root-save ASM writes its own root bank.
    represented=mirror(model['cases'][0]['type_id']);cold_barrier=Barrier(8)
    def cold_factory(ordinal):
        cold_barrier.wait()
        _,wrapper=call(native['getConstantPool'],[represented]);save(8+ordinal,wrapper)
        S.check(wrapper and Q.from_address(wrapper+meta['fields']['constantPoolOop']).value==represented,
            'Concurrent cold CP factory lost the actual owner Class')
        return dict(OS_thread=get_native_id(),wrapper=wrapper)
    with ThreadPoolExecutor(8) as executor:cold_workers=list(executor.map(cold_factory,range(8)))
    S.check(len({r['OS_thread'] for r in cold_workers})==len({r['wrapper'] for r in cold_workers})==8,
        'Cold CP creation must observe eight real workers and independent normal wrappers')
    represented_states=[];observed={r['type_id']:r for r in config['represented_class_observations']}
    for ordinal,case in enumerate(model['cases']):
        represented=mirror(case['type_id']);state=observed.get(case['type_id'])
        before=U.from_address(addr(image,state['state_symbol'])+8).value if state else None
        _,wrapper=call(native['getConstantPool'],[represented]);save(ordinal,wrapper);wrappers.append(wrapper)
        after=U.from_address(addr(image,state['state_symbol'])+8).value if state else None
        S.check(before==after,'CP factory changed the represented class initialization state')
        represented_states.append(dict(name=case['name'],normal_descriptor_selected=bool(state),before=before,after=after))
        S.check(wrapper and Q.from_address(wrapper+meta['fields']['constantPoolOop']).value==represented,
            'VM-created normal CP wrapper lost its real owner Class reference')
        S.check(java('getSize',[wrapper])==case['size'],'Original CP.getSize facade/count differs')
        for entry in case['entries']:
            index,tag=entry['index'],entry['tag'];item=dict(owner=case['name'],index=index,tag=tag)
            enum=java('getTagAt',[wrapper,index]);name=call(members['java/lang/Enum','name'],[enum])[1]
            S.check(bytes.fromhex(utf16(name)).decode('utf-16-le')==TAGS[tag],'Original CP.Tag Java lookup differs')
            if tag in (1,8):
                getter='getUTF8At' if tag==1 else 'getStringAt';value=java(getter,[wrapper,index]);item['utf16']=utf16(value)
                S.check(item['utf16']==entry['utf16'],'Decoded original MUTF8/String constant differs')
                if tag==8:S.check(java(getter,[wrapper,index])==value,'Original String constant did not use canonical intern identity')
            elif tag in (3,4,5,6):
                getter={3:'getIntAt',4:'getFloatAt',5:'getLongAt',6:'getDoubleAt'}[tag]
                value=java(getter,[wrapper,index]);bits=value&((1<<(32 if tag in (3,4) else 64))-1)
                S.check(bits==entry['bits'],'Original numeric CP payload bits changed');item['bits']=bits
            elif tag==7 and entry['target_type'] is not None:
                item['target_type']=class_id(java('getClassAt',[wrapper,index]));S.check(item['target_type']==entry['target_type'],'Forced known Class reference differs')
            elif tag in (9,10,11,12):
                getter='getNameAndTypeRefInfoAt' if tag==12 else 'getMemberRefInfoAt'
                item['info']=[bytes.fromhex(utf16(v)).decode('utf-16-le','surrogatepass') for v in array(java(getter,[wrapper,index]))]
                S.check(item['info']==entry['info'],'Original member/name-and-type info differs')
                if tag!=12:S.check(java('getClassRefIndexAt',[wrapper,index])==entry['class_ref'],'Original class-ref CP index changed')
            if tag in (9,10,11,18):S.check(java('getNameAndTypeRefIndexAt',[wrapper,index])==entry['name_type_ref'],'Original name-and-type CP index changed')
            answers.append(item)
    blocked=model['blocked_class_reference']
    _,blocked_wrapper=call(native['getConstantPool'],[mirror(blocked['owner_type'])]);save(16,blocked_wrapper)
    ctx,value=call(members[C.CP,'getClassAt'],[blocked_wrapper,blocked['index']],False)
    S.check(not value and ctx[0]==20,'An unproven Class resolution was returned as successful')
    blocked_observation=dict(**blocked,actual_context=list(ctx),result=value)
    bad_inputs=[]
    for label,ident,args,kind in [('null_Class',native['getConstantPool'],[0],4),
        ('foreign_Class',native['getConstantPool'],[1],7),('null_CP',native['getSize0'],[0,0],4),
        ('wrong_CP_type',native['getSize0'],[represented,0],7),('foreign_CP',native['getSize0'],[1,0],7)]:
        ctx,value=call(ident,args,False)
        S.check(not value and ctx[0]==kind,'CP bad receiver escaped its normal object/Class validation')
        bad_inputs.append(dict(case=label,context=list(ctx),result=value))
    # Source wrappers and invalid semantic indices, not an invented empty CP.
    errors=[];wrapper=wrappers[0]
    for getter,index,message in [('getUTF8At',-1,'Constant pool index out of bounds'),
        ('getIntAt',model['cases'][0]['size'],'Constant pool index out of bounds'),
        ('getUTF8At',0,'Wrong type at constant pool index'),('getDoubleAt',0,'Wrong type at constant pool index')]:
        ctx,value=call(members[C.CP,getter],[wrapper,index&0xffffffff],False)
        S.check(not value and ctx[0]==16,'Original CP index/type failure is not a Java typed exception')
        error=P.from_address(c.addressof(ctx)+16).value
        text=call(members['java/lang/Throwable','getMessage'],[error])[1]
        actual=bytes.fromhex(utf16(text)).decode('utf-16-le')
        S.check(Q.from_address(error-8).value==addr(image,'boom_layout'+str(meta['error_class'])),
            'CP native did not allocate the original IllegalArgumentException type')
        S.check(actual==message,'Original CP index/type message differs');errors.append(dict(getter=getter,index=index,error='java/lang/IllegalArgumentException',message=actual))
    oracle_errors,oracle_proof=oracle(model,output,Path(config['oracle_home']))
    S.check(errors==oracle_errors,'Actual CP typed errors differ from locked JDK')
    ctx=Context(9,4,7,0,11,12,13,14);before=list(ctx)
    _,value=call(native['getSize0'],[wrapper,0],False,ctx);S.check(not value and list(ctx)==before,'Existing CP pending Context changed')
    # The second native token argument really is unused by the pinned VM API.
    _,value=call(native['getSize0'],[wrapper,1]);S.check(value==model['cases'][0]['size'],'Ignored native token was wrongly required to equal owner')
    barrier=Barrier(8);target=next(e['index'] for e in model['cases'][0]['entries'] if e['tag']==1)
    def work(_):
        barrier.wait()
        for _ in range(16):
            S.check(java('getSize',[wrapper])==model['cases'][0]['size'],'Concurrent CP size changed')
            S.check(java('getUTF8At',[wrapper,target]),'Concurrent CP UTF8 returned null')
        return dict(OS_thread=get_native_id(),iterations=16,Java_facade_calls=32)
    with ThreadPoolExecutor(8) as executor:workers=list(executor.map(work,range(8)))
    S.check(len({r['OS_thread'] for r in workers})==8,'Eight actual CP OS workers were not observed')
    collections=[]
    for retain in (True,False):
        if not retain:
            for i in range(64):save(i,0)
        roots=[];spans=[]
        for span in config['root_spans']:
            count=span.get('count')
            if count is None:count=Q.from_address(addr(image,span['count_symbol'])).value
            S.check(count<=1048576,'CP normal root bank exceeds its bound')
            values=[v for v in (Q*count).from_address(addr(image,span['symbol'])) if v];roots.extend(values)
            spans.append(dict(symbol=span['symbol'],count=count,non_null=len(values)))
        packed=(Q*max(1,len(roots)))(*roots);freed=proc(rt,'boom_heap_collect',Q,P,P,U)(heap,packed,len(roots))
        S.check(freed!=0xffffffffffffffff,'CP explicit quiescent GC failed')
        S.check(proc(rt,'boom_heap_contains',U,P,P)(heap,wrappers[0])==int(retain),'CP wrapper/owner graph retention differs')
        collections.append(dict(retained_test_wrappers=retain,source_spans=spans,freed_objects=freed))
    S.check(U.from_address(cp_state+8).value==2,'Original CP class initializer did not complete normally')
    S.check(proc(image,'boom_release_trace_pool',U)()==0 and proc(rt,'boom_heap_destroy',U,P)(heap)==1,'CP source frame/heap cleanup failed')
    result=dict(schema=1,verified=True,scope='current_source_CP_normal_wrapper_and_original_public_facade_subset_only',
        images=S.artifact(images_file),actual_constant_tests=answers,typed_index_errors=errors,bad_receivers=bad_inputs,
        primitive_array_factory_null=primitive_array,represented_class_states=represented_states,
        unproven_ClassAt_is_explicit_gap=blocked_observation,
        cold_factory_OS_threads=cold_workers,worker_OS_threads=workers,
        JDK_oracle=oracle_proof,normal_String_bootstrap_prerequisite=string_bootstrap,
        CP_source_class_cold0_to_initialized2=True,wrapper_field_is_actual_owner_Class=True,normal_string_coder_used=True,
        original_Java_facades_and_CP_initializer_executed=True,original_Java_Code_modified=False,
        source_class_initialization_fields_host_written=False,pending_Context_preserved=True,ignored_native_token_verified=True,
        explicit_quiescent_GC=collections,ROM_native_owned_buffers=0,ROM_has_code=False,
        IfLoaded_not_implemented=True,methodAt_fieldAt_not_implemented=True,shared_provider_registered=False,
        full_VM_bootstrap=False,game_started=False,world_created=False,heap_destroyed=True)
    path=output/'execution.json';S.write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ('state','candidate','output','source-images','request','images','worker'):parser.add_argument('--'+n,type=Path)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    if args.worker:print(run(args.worker.resolve()))
    elif args.prepare_only:print(prepare(args.candidate.resolve(),args.state.resolve(),args.output.resolve()))
    else:
        output=(args.output or S.ART/'normal-constant-pool'/('execution-'+uuid4().hex)).resolve()
        if args.images:images=args.images.resolve()
        else:
            if args.source_images:
                source=args.source_images.resolve()
                if args.request:request=args.request.resolve()
                else:
                    S.check(not output.exists(),'Fresh CP overlay request output required');output.mkdir(parents=True)
                    request=output/'request.json';S.write(request,request_model(args.candidate.resolve(),args.state.resolve()))
            else:
                source=prepare(args.candidate.resolve(),args.state.resolve(),output);request=output/'request.json'
            images=link(source,request,output/'execution-image')
        subprocess.run([os.sys.executable,str(Path(__file__).resolve()),'--worker',str(images)],check=True)
