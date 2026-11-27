"""Owned normal-array Inflater native component; original constructor stays separate."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from threading import Barrier,get_native_id
import zlib

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('inflater_test_'+name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


B=module('inflater-candidate');S=B.S;C=B.C;H=module('formal-provider-selection');E=module('existing-source-selection')
D=module('diagnostic-objects');L=module('canonical-link-response');PFX=module('probe-native-provider-prefix');T=module('test-zlib-stream')
P,Q,U=c.c_void_p,c.c_uint64,c.c_uint32
Context=U*8


def proc(image,name,result,*arguments):
    value=getattr(image,name);value.restype,value.argtypes=result,arguments;return value


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


def checked(record):return E.checked(record)


def verify_candidate(path):
    proof=B.verify(path);stored=S.read(Path(path).with_name('verification.json'))
    S.check(proof['candidate']==stored['candidate'] and proof['scope']==stored['scope'] and
        proof['machine']['normalized_coff_sha256']==stored['machine']['normalized_coff_sha256'],'Actual candidate source/frame/machine proof differs')
    checked(stored['machine']['canonical_source']);checked(stored['machine']['canonical_object'])
    return S.read(path),proof


def prepare(candidate_file,output):
    candidate=S.read(candidate_file);meta=candidate['metadata']['source'];state_file=S.checked(candidate['metadata']['input_state']);state=S.read(state_file)
    _,_,classes=S.base(Path(state['batch']),Path(state['plan']));names={r['name']:r['id'] for r in classes if r['origin']['loader']=='bootstrap'}
    roots={('bootstrap',m['owner'],m['name'],m['descriptor']) for m in meta['methods']+meta['java_callbacks']+meta['original_java_paths']}
    roots|={('bootstrap','java/lang/String','<init>','([C)V'),('bootstrap','java/lang/String','toCharArray','()[C'),
        ('bootstrap','java/lang/Throwable','getMessage','()Ljava/lang/String;'),('bootstrap','jdk/internal/loader/NativeLibraries','findBuiltinLib','(Ljava/lang/String;)Ljava/lang/String;')}
    allowed=set(meta['source_classes'])|{'java/lang/Object','java/lang/Exception','java/lang/Error','java/lang/VirtualMachineError','java/lang/StringUTF16','java/lang/StringLatin1',
        'java/util/Collections','java/util/Collections$EmptyList','java/util/Collections$EmptySet','java/util/Collections$EmptyMap'}
    procs,data=C.native_imports(meta);optional=(procs|data)-C.FOREIGN-{'boom_deflate_stream_reset','boom_deflate_stream_step','boom_zlib_stream_reset','boom_zlib_stream_step'}
    optional|={f'boom_layout{i}' for i in meta['source_classes'].values()}|{f'boom_class{i}' for i in meta['source_classes'].values()}
    optional|={f"boom_m{m['method']}" for m in meta['original_java_paths']+meta['java_callbacks']+meta['methods']}
    optional|={'boom_heap_ptr','boom_java_string_literals_bind_heap','boom_diagnostic_pool','boom_release_trace_pool','boom_probe_static_roots','boom_probe_static_root_count'}
    optional|={n for pair in ROOT_SPANS for n in pair}
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART/'inflater-normal') and not output.exists(),'Fresh focused output');output.mkdir(parents=True)
    request=dict(method_roots=sorted(roots),class_roots=[('bootstrap',n) for n in meta['source_classes']],admitted_classes=sorted(names[n] for n in allowed),optional_exports=sorted(optional),
        source_native_rows=meta['methods'],source_callback_rows=meta['java_callbacks'],scope='original_source_roots_only_no_native_replacement_or_runtime_acceptance')
    S.write(output/'request.json',request)
    return H.prepare(state_file,output/'selection',method_roots=request['method_roots'],class_roots=request['class_roots'],admitted_classes=request['admitted_classes'],
        optional_exports=request['optional_exports'],harness_sources=[output/'request.json'])


ROOT_SPANS=[('boom_probe_static_roots','boom_probe_static_root_count'),('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),('boom_java_class_roots','boom_java_class_root_count'),('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),('boom_provider_threads_roots','boom_provider_threads_root_count')]


ORACLE=r'''import java.nio.file.*;
import java.lang.reflect.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;
public class InflaterNativeOracle {
 public static void main(String[] args) throws Exception {
  Method nativeCall=Inflater.class.getDeclaredMethod("inflateBytesBytes",long.class,byte[].class,int.class,int.class,byte[].class,int.class,int.class);nativeCall.setAccessible(true);
  Field ref=Inflater.class.getDeclaredField("zsRef"),ic=Inflater.class.getDeclaredField("inputConsumed"),oc=Inflater.class.getDeclaredField("outputConsumed");
  ref.setAccessible(true);ic.setAccessible(true);oc.setAccessible(true);int cases=0,exceptions=0,dictionaries=0;long calls=0;
  for(String line:Files.readAllLines(Path.of(args[0]))) {
   String[] p=line.split("\t");boolean raw=p[2].equals("raw");byte[] input=Files.readAllBytes(Path.of(p[1]));Inflater f=new Inflater(raw);
   try {
    Object r=ref.get(f);Field address=r.getClass().getDeclaredField("address");address.setAccessible(true);long handle=address.getLong(r);
    if(Integer.toUnsignedLong(f.getAdler())!=(raw?0:1)) throw new AssertionError("initial Adler");
    MessageDigest sha=MessageDigest.getInstance("SHA-256");int pos=0;long written=0;boolean finished=false,needDict=false,error=false;
    for(int ncall=0;ncall<1000000;ncall++) {
     byte[] out=new byte[512];int available=Math.min(7,input.length-pos),used=0,n=0;int oldI=ic.getInt(f),oldO=oc.getInt(f);
     try {
      long value=(long)nativeCall.invoke(f,handle,input,pos,available,out,0,out.length);used=(int)(value&0x7fffffffL);n=(int)(value>>>31&0x7fffffffL);
      finished=(value>>>62&1)!=0;needDict=(value>>>63)!=0;
      if(ic.getInt(f)!=oldI || oc.getInt(f)!=oldO) throw new AssertionError("normal native changed error fields");
     } catch(InvocationTargetException e) {
      if(!(e.getCause() instanceof DataFormatException)) throw e;used=ic.getInt(f);n=oc.getInt(f);error=true;exceptions++;
     }
     calls++;if(used<0 || used>available || n<0 || n>out.length) throw new AssertionError("packed/field counts");
     pos+=used;written+=n;sha.update(out,0,n);
     if(error || finished || needDict || used==0 && n==0 && pos==input.length) break;
    }
    if(p[3].equals("good")) {
     if(error || !finished || needDict || pos!=Integer.parseInt(p[4]) || written!=Long.parseLong(p[5]) ||
        !HexFormat.of().formatHex(sha.digest()).equals(p[6]) || Integer.toUnsignedLong(f.getAdler())!=Long.parseLong(p[7])) throw new AssertionError("native oracle "+p[0]);
    } else if(p[3].equals("dict")) {
     if(error || !needDict || finished || pos!=6 || written!=0 || Integer.toUnsignedLong(f.getAdler())!=Long.parseLong(p[7])) throw new AssertionError("dict oracle");dictionaries++;
    } else if(!error) throw new AssertionError("bad input did not throw");
    f.reset();if(Integer.toUnsignedLong(f.getAdler())!=(raw?0:1)) throw new AssertionError("reset Adler");cases++;
   } finally {f.end();}
  }
  System.out.println("Inflater_private_native_cases="+cases+" calls="+calls+" exceptions="+exceptions+" dictionaries="+dictionaries);
 }
}
'''


def jdk_oracle(output,raw_good,wrapped,bad,dictionaries):
    output.mkdir();source=output/'InflaterNativeOracle.java';source.write_text(ORACLE,encoding='utf-8',newline='\n')
    home=T.T.JAVA;tools=[S.artifact(home/n) for n in ('bin/java.exe','bin/javac.exe','bin/server/jvm.dll','bin/zip.dll','lib/modules','lib/src.zip')]
    inputs=[];rows=[]
    cases=[(r,True,'good') for r in raw_good]+[(r,False,'good') for r in wrapped]+[(r,False,'bad') for r in bad[:9]]+[(r,False,'dict') for r in dictionaries]
    for i,(r,raw,mode) in enumerate(cases):
        p=output/(str(i)+'.bin');p.write_bytes(r['raw']+b'UNCONSUMED-TAIL');inputs.append(S.artifact(p));plain=r['output'] or b''
        adler=0 if raw else r['dictionary'] if mode=='dict' else zlib.adler32(plain)
        rows.append('\t'.join([r['name'],str(p),'raw' if raw else 'zlib',mode,str(len(r['raw'])),str(len(plain)),hashlib.sha256(plain).hexdigest(),str(adler)]))
    manifest=output/'cases.tsv';manifest.write_text('\n'.join(rows)+'\n',encoding='utf-8',newline='\n')
    with (output/'javac.log').open('xb') as log:r=subprocess.run([str(home/'bin/javac.exe'),'-d',str(output),str(source)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0,'JNI contract reference compilation failed')
    with (output/'java.log').open('xb') as log:r=subprocess.run([str(home/'bin/java.exe'),'--add-opens=java.base/java.util.zip=ALL-UNNAMED','-cp',str(output),'InflaterNativeOracle',str(manifest)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0 and (output/'java.log').read_text().startswith('Inflater_private_native_cases='+str(len(cases))+' '),'JDK private-native contract mismatch; preserve java.log')
    S.check(tools==[S.artifact(t['path']) for t in tools],'JDK reference inputs changed')
    result=dict(verified=True,scope='JDK_reference_only_original_constructor_then_private_inflateBytesBytes_with_read_only_handle_and_field_observation',
        cases=len(cases),source=S.artifact(source),class_file=S.artifact(output/'InflaterNativeOracle.class'),manifest=S.artifact(manifest),inputs=inputs,tools=tools,stdout=S.artifact(output/'java.log'),
        JNI_packed_counts_and_data_error_field_bounds_checked=True,fields_or_clinit_not_patched=True,reference_only=True,delivery_uses_JVM=False)
    S.write(output/'verification.json',result);return S.artifact(output/'verification.json')


def build(candidate_file,envelope_file,output):
    candidate_file,envelope_file=Path(candidate_file).resolve(),Path(envelope_file).resolve();candidate,proof=verify_candidate(candidate_file)
    source_proof=E.verify(envelope_file);envelope=S.read(envelope_file);source=Path(envelope['source_selection_directory']);closure=S.read(checked(envelope['source_manifest']))
    S.check(candidate['metadata']['base']==envelope['base'] and candidate['metadata']['input_state']==envelope['input_state'],'Candidate and actual source envelope differ')
    meta=candidate['metadata']['source'];selected={r['class_id'] for r in closure['selected_classes']}
    S.check(set(meta['required_classes'])<=selected,'Actual source metadata misses required normal classes')
    for method in meta['java_callbacks']:
        row=closure['selected_methods'].get(str(method['method']))
        S.check(row and row['code_sha256']==method['code_sha256'] and row['source_sha256']==method['class_sha256'],'Original Java callback not actually selected: '+str(method['method']))
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART/'inflater-normal') and not output.exists(),'Fresh component output required');output.mkdir(parents=True)
    sealed=D.verify(source);units=sealed['units'];[stop]=[r for r in units if Path(r['assembly']['path']).name=='diagnostic-stops.asm'];diagnostic=S.read(source/'diagnostic.json')
    targets={f"boom_m{m['method']}" for m in meta['methods']};rows=[r for r in diagnostic['rows'] if r['symbol'] in targets]
    S.check({r['symbol'] for r in rows}==targets and all(r['binding']['kind']=='native_declaration' and r['method']['code_sha256'] is None and
        r['class_id']==meta['owner'] and r['source_sha256']==next(m['class_sha256'] for m in meta['methods'] if m['method']==r['method']['id'])
        for r in rows),'Only source-reconstructed original native fail-only targets may be replaced')
    original=checked(stop['assembly']).read_bytes();remaining,removal=PFX.remove_stops(original,rows,bool(closure.get('diagnostic_context_rows')),targets)
    asm,obj=output/'remaining-stops.asm',output/'remaining-stops.obj';asm.write_bytes(remaining);assembler=Path(candidate['assembler']['path'])
    with (output/'assembler.log').open('xb') as log:run=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(asm)],stdout=log,stderr=subprocess.STDOUT)
    S.check(run.returncode==0,'Remaining native stops assembly failed')
    olddefs,oldrefs=B.A.coff_symbols(checked(stop['object']));S.check(B.A.coff_symbols(obj)==(olddefs-targets,oldrefs),'Retained stop COFF changed more than exact requested PUBLIC/PROCs')
    retained=[r['object']['path'] for r in units]+closure['objects'];objects=[str(obj) if Path(p)==Path(stop['object']['path']) else p for p in retained]
    extras=[S.checked(candidate['object']),Path(candidate['metadata']['core']['object']['path']),Path(candidate['metadata']['core']['raw_object']['path'])]
    wanted=set(candidate['exports']);conflicts={str(p):sorted(PFX.conflicting_public_definitions(p,wanted)) for p in objects}
    S.check(not any(conflicts.values()),'Inflater candidate conflicts with retained definitions')
    objects+=list(map(str,extras));runtime=checked(envelope['runtime']);winsock='normal-native-libraries-v1' in envelope['selected_provider_families'];libraries=L.diagnostic_libraries(runtime,winsock=winsock)[0]
    exports=set(closure['exports'])|wanted;image=output/'inflater-normal.dll';rsp=output/'link.rsp'
    rsp.write_text('\n'.join([*L.PREFIXES['diagnostic'],'/OUT:"'+str(image)+'"']+['"'+str(p)+'"' for p in [*objects,*libraries]]+['/EXPORT:'+n for n in sorted(exports)])+'\n',encoding='utf-8',newline='\n')
    L.verify(rsp,profile='diagnostic',output=image,objects=objects,library_choices=[libraries],exports=exports)
    with (output/'link.log').open('xb') as log:run=subprocess.run([str(assembler.with_name('link.exe')),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    S.check(run.returncode==0,'Inflater owned component link failed')
    V=module('diagnostic-closure');S.check(V.pe_exports(image)==exports,'Actual component PE exports differ')
    public=set(exports);spans=[pair for pair in ROOT_SPANS if set(pair)<=public]
    inputs=[S.artifact(p) for p in [*objects,*libraries,candidate_file,candidate_file.with_name('verification.json'),envelope_file,runtime,runtime.with_name('runtime.json'),assembler,assembler.with_name('link.exe'),Path(__file__),ROOT/'scripts/existing-source-selection.py',rsp]]
    for record in inputs:checked(record)
    record=dict(schema=1,scope='owned_unregistered_Inflater_direct_native_component_over_actual_original_source',candidate=S.artifact(candidate_file),candidate_proof=S.artifact(candidate_file.with_name('verification.json')),
        envelope=S.artifact(envelope_file),runtime=S.artifact(runtime),image=S.artifact(image),response=S.artifact(rsp),objects=objects,libraries=list(map(str,libraries)),exports=sorted(exports),
        source_directory=str(source),metadata=meta,removal=removal,original_diagnostic_rowdata_unchanged=True,non_target_Java_COFF_unchanged=True,
        primitive_objects_reused=candidate['metadata']['core'],native_root_spans=[],source_root_spans=spans,inputs=inputs,
        direct_native_only=True,prototype_native_declarations=11,supported_native_operations=6,unsupported_native_operations=5,full_selection_reverified=False,
        original_Java_constructor_completed=False,registered=False,game_started=False)
    path=output/'images.json';S.write(path,record);return path


def verify_images(path):
    record=S.read(path);E.verify(checked(record['envelope']))
    for item in record['inputs']:checked(item)
    candidate=S.read(checked(record['candidate']));S.check(candidate['metadata']['source']==record['metadata'],'Component model changed')
    L.verify(checked(record['response']),profile='diagnostic',output=checked(record['image']),objects=record['objects'],library_choices=[[Path(p) for p in record['libraries']]],exports=record['exports'])
    S.check(module('diagnostic-closure').pe_exports(checked(record['image']))==set(record['exports']),'Component PE changed')
    return record


def execute(path):
    record=verify_images(path);output=Path(path).parent;meta=record['metadata'];runtime=checked(record['runtime'])
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.CDLL(str(runtime)),c.CDLL(str(checked(record['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(256<<20);S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Normal Java heap/source literals binding failed')
    service=proc(image,C.SERVICE,Q,P,P,P,U);pool=addr(image,C.POOL);close=proc(image,'boom_inflater_close_owned',Q,P);ctx=Context()
    native_calls=0;typed_errors=[];closure=S.read(Path(record['source_directory'])/'closure.json')
    # The direct fixture has no System bootstrap. Run the whole original
    # String initializer before its native factory/Java observers are used.
    # In particular COMPACT_STRINGS must be published by original Java Code.
    string_class=meta['source_classes']['java/lang/String'];string_descriptor=addr(image,'boom_class'+str(string_class))
    initializers=[r for r in closure['selected_methods'].values() if r['class_id']==string_class and r['name']=='<clinit>']
    S.check(len(initializers)==1 and initializers[0]['code_sha256'],'Normal source String initializer missing')
    string_before=U.from_address(string_descriptor+8).value;string_context=Context()
    proc(rt,'boom_class_ensure32',U,P,P)(string_descriptor,string_context)
    string_after=U.from_address(string_descriptor+8).value
    S.check(not string_context[0] and string_before==0 and string_after==2,'Original String cold initialization failed')
    def source_method(owner,name,descriptor,args):
        cls=meta['source_classes'][owner]
        rows=[(ident,row) for ident,row in closure['selected_methods'].items() if row['class_id']==cls and row['name']==name and row['descriptor']==descriptor]
        S.check(len(rows)==1,'Whole original observer method must be selected')
        context=Context();argv=(Q*max(1,len(args)))(*args);value=proc(image,'boom_m'+rows[0][0],Q,P,P)(context,argv)
        if context[0]:first_failure('original observer '+owner+'.'+name,context)
        S.check(not context[0],'Original observer Java method failed');return value
    diagnostic=S.read(Path(record['source_directory'])/'diagnostic.json')
    def first_failure(stage,context):
        pool_diag=addr(image,'boom_diagnostic_pool');row_id=U.from_address(pool_diag+32).value
        rows={r['id']:r for r in diagnostic['rows']};fault=rows.get(row_id) if U.from_address(pool_diag+8).value==2 else None
        target=output/'first-failure.json'
        if not target.exists():S.write(target,dict(verified=False,stage=stage,context=list(context),actual_source_fault=fault,
            original_Java_Code_changed=False,original_Inflater_class_state=U.from_address(addr(image,'boom_class'+str(meta['owner']))+8).value,
            normal_constructor_claimed=False,images=S.artifact(path)))
    def native(op,args,context=None,check=True):
        nonlocal native_calls
        context=Context() if context is None else context;argv=(Q*max(1,len(args)))(*args);value=service(context,argv,pool,op);native_calls+=1
        if check and context[0]:first_failure('direct operation '+str(op),context);raise ValueError('direct native Context '+str((op,list(context))))
        return context,value
    native(0,[]);S.check(Q.from_address(pool+64).value==2,'Original field-map publication failed')
    owner=meta['source_classes'][C.OWNER];owner_descriptor=addr(image,'boom_class'+str(owner));S.check(U.from_address(owner_descriptor+8).value==0,'Direct fixture must begin with cold original Inflater class')
    def new_receiver():
        context=Context();oop=proc(rt,'boom_object_new',P,P,P,P)(heap,addr(image,'boom_layout'+str(owner)),context)
        S.check(oop and not context[0],'Normal direct-component receiver allocation failed');return oop
    def array(n):
        context=Context();oop=proc(rt,'boom_array_new',P,P,c.c_int,U,P)(heap,n,8,context)
        S.check(oop and not context[0] and Q.from_address(oop-8).value==264,'Normal byte[] allocation failed');return oop
    fields={r['name']:next(row['offset'] for row in r['field_map']['rows'] if row['receiver_class']==owner) for r in meta['fields']}
    def stream(raw,expected,nowrap,*,bad=False,dictionary=False,step=7,cap=512):
        receiver=new_receiver();src=array(max(step,1));dst=array(max(cap,1));_,handle=native(1,[int(nowrap)]);pos=0;result=bytearray();iterations=0;error=None;finished=False;need_dict=False
        _,initial=native(2,[handle]);S.check(initial==(0 if nowrap else 1),'Original raw/wrapped initial getAdler differs')
        for _ in range(20*(len(raw)+len(expected or b'')+1)+300):
            chunk=raw[pos:pos+step]
            if chunk:c.memmove(src,chunk,len(chunk))
            before_in=c.string_at(src,len(chunk));before_fields=[U.from_address(receiver+fields[n]).value for n in ('inputConsumed','outputConsumed')]
            context,value=native(5,[receiver,handle,src,0,len(chunk),dst,0,cap],check=False);iterations+=1
            if context[0]:
                if context[0]!=16:first_failure('original typed Java error materialization',context)
                S.check(context[0]==16 and Q.from_address(c.addressof(context)+16).value,'Data error did not materialize a real typed Java exception')
                consumed=U.from_address(receiver+fields['inputConsumed']).value;written=U.from_address(receiver+fields['outputConsumed']).value
                error=dict(context=list(context),exception=Q.from_address(c.addressof(context)+16).value,inputConsumed=consumed,outputConsumed=written);typed_errors.append(error)
            else:
                consumed=value&0x7fffffff;written=(value>>31)&0x7fffffff;finished=bool(value>>62&1);need_dict=bool(value>>63)
                S.check(before_fields==[U.from_address(receiver+fields[n]).value for n in ('inputConsumed','outputConsumed')],'Normal native return changed Java-owned error fields')
            S.check(consumed<=len(chunk) and written<=cap and c.string_at(src,len(chunk))==before_in,'JNI packed/field progress exceeds actual arrays or input changed')
            pos+=consumed;result.extend(c.string_at(dst,written));c.memset(src,0xde,max(step,1));c.memset(dst,0xe9,max(cap,1))
            if error or finished or need_dict:break
            if not consumed and not written and pos==len(raw):break
        _,adler=native(2,[handle])
        if not bad and not dictionary:S.check(not error and finished and not need_dict and result==expected and pos==len(raw),'Direct native decompression/output/consumption differs')
        if dictionary:S.check(not error and need_dict and not finished and pos==6 and not result and adler==int.from_bytes(raw[2:6],'big'),'Original needs-dictionary/getAdler mapping differs')
        if bad:S.check(error is not None,'Malformed compressed stream did not throw DataFormatException')
        if nowrap:S.check(adler==0,'Original nowrap getAdler must remain zero')
        elif not dictionary:S.check(adler==zlib.adler32(result),'Wrapped getAdler differs from actual written output')
        native(3,[handle]);_,reset=native(2,[handle]);S.check(reset==(0 if nowrap else 1),'Original reset/getAdler differs');native(4,[handle])
        return dict(nowrap=nowrap,input_used=pos,output_used=len(result),calls=iterations,finished=finished,need_dictionary=need_dict,typed_error=error is not None,handle=handle),[receiver,src,dst]
    raw_good,raw_bad,_=T.R.fixtures();wrapped,bad,dicts,policies,rfc=T.fixtures();observations=[];keep=[]
    for nowrap,rows in ((True,raw_good),(False,wrapped)):
        for r in rows:
            answer,roots=stream(r['raw'],r['output'],nowrap);observations.append(dict(name=r['name'],**answer));keep=roots
    for r in [bad[0],bad[7],bad[8],policies[0]]:
        answer,roots=stream(r['raw'],r['output'],False,bad=True);observations.append(dict(name=r['name'],**answer));keep=roots
        error=typed_errors[-1]['exception'];context=Context();row=proc(rt,'boom_runtime_row',P,P,P,P)(error,addr(image,'boom_runtime_type_map'),context)
        S.check(row and not context[0] and U.from_address(row+16).value==meta['source_classes']['java/util/zip/DataFormatException'],'Wrong actual typed exception class')
        message=source_method('java/lang/Throwable','getMessage','()Ljava/lang/String;',[error]);chars=source_method('java/lang/String','toCharArray','()[C',[message])
        S.check(chars and Q.from_address(chars-8).value==261 and Q.from_address(chars-16).value==46,'Original message observer must return complete normal char[]')
        observed=c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le')
        if observed!='Invalid compressed data':
            first_failure('original typed exception message mismatch',Context(*typed_errors[-1]['context']))
            S.write(output/'message-observation.json',dict(expected='Invalid compressed data',actual=observed,exception=error,message=message,chars=chars,source_case=r['name'],source_Java_getters_executed=True))
        S.check(observed=='Invalid compressed data','Original typed exception message constructor did not run: '+repr(observed))
    for r in dicts:
        answer,roots=stream(r['raw'],b'',False,dictionary=True);observations.append(dict(name=r['name'],**answer));keep=roots
    # Typed allocation/constructors above are whole source Java. Preserve their
    # actual diagnostic first failure rather than manufacturing typed success.
    invalid=[]
    for op,args in ((2,[0]),(2,[0xdeadbeef]),(4,[observations[0]['handle']])):
        context,value=native(op,args,check=False);S.check(context[0]==7 and value==0,'Invalid/stale token was dereferenced or accepted');invalid.append(dict(op=op,context=list(context)))
    for op in range(6,11):
        context,value=native(op,[0]*8,check=False);S.check(context[0]==20 and value==0,'Unsupported native form falsely succeeded')
    pending=Context(9,3,4,0,5,6,7,8);before=list(pending);native(1,[0],pending,False);S.check(list(pending)==before,'Pending Context overwritten')
    barrier=Barrier(8)
    def worker(index):
        ident=get_native_id();barrier.wait();n=0
        for i in range(16):
            r=raw_good[(i+index)%len(raw_good)];answer,_=stream(r['raw'],r['output'],True);n+=answer['calls']
        return dict(OS_thread=ident,streams=16,inflate_calls=n)
    with ThreadPoolExecutor(max_workers=8) as workers:threads=list(workers.map(worker,range(8)))
    S.check(len({r['OS_thread'] for r in threads})==8,'Eight actual native OS workers required')
    # Observe the shared lifetime lease while a real long native copy is
    # running, then race end against that exact handle. No closed-node pointer
    # is dereferenced after unpublication.
    payload=b'x'*(8<<20);compress=zlib.compressobj(0,zlib.DEFLATED,-15);raw=compress.compress(payload)+compress.flush()
    receiver=new_receiver();src=array(len(raw));dst=array(len(payload));c.memmove(src,raw,len(raw));_,handle=native(1,[1]);race_observed=False
    with ThreadPoolExecutor(max_workers=1) as runner:
        future=runner.submit(native,5,[receiver,handle,src,0,len(raw),dst,0,len(payload)])
        deadline=time.monotonic()+30
        while not future.done() and time.monotonic()<deadline:
            if Q.from_address(pool+16).value:race_observed=True;break
            time.sleep(0)
        native(4,[handle]);context,value=future.result()
    S.check(not context[0] and value>>62&1 and value&0x7fffffff==len(raw) and (value>>31)&0x7fffffff==len(payload) and c.string_at(dst,len(payload))==payload,'Concurrent end damaged in-flight owned state')
    context,_=native(2,[handle],check=False);S.check(context[0]==7,'Ended race handle remained valid')
    spans=[];roots=list(keep)
    for a,b in record['source_root_spans']:
        start=addr(image,a);count=Q.from_address(addr(image,b)).value;S.check(count<=1048576,'Source root count bound')
        roots.extend(Q.from_address(start+i*8).value for i in range(count));spans.append(dict(symbol=a,cells=count))
    roots.extend(r['exception'] for r in typed_errors);roots=[r for r in roots if r];packed=(Q*len(roots))(*roots)
    # Live primitive handles survive managed collection; no managed oop is
    # retained in their native state. Their explicit native lifetime is tested
    # independently of the unexecuted original Cleaner construction.
    live_for_gc=[native(1,[int(i%2)])[1] for i in range(2)]
    freed=proc(rt,'boom_heap_collect',Q,P,P,U)(heap,packed,len(roots));S.check(freed!=0xffffffffffffffff,'Quiescent source heap collection failed')
    for i,handle in enumerate(live_for_gc):
        _,adler=native(2,[handle]);S.check(adler==(0 if i%2 else 1),'Managed GC changed native primitive-owned state');native(4,[handle])
    S.check(Q.from_address(pool+32).value==Q.from_address(pool+104).value==Q.from_address(pool+16).value==0 and Q.from_address(pool+40).value==Q.from_address(pool+48).value,'Owned inflater nodes/bytes/lock leaked')
    abandoned=[native(1,[int(i%2)])[1] for i in range(4)];S.check(close(pool)==4,'Explicit VM-owner cleanup did not free all abandoned native states')
    S.check(Q.from_address(pool+32).value==Q.from_address(pool+104).value==0 and Q.from_address(pool+40).value==Q.from_address(pool+48).value,'Close left native resources')
    S.check(U.from_address(owner_descriptor+8).value==0,'Direct native tests initialized or patched original Inflater class')
    proc(image,'boom_release_trace_pool',None)();proc(rt,'boom_heap_destroy',None,P)(heap)
    oracle=jdk_oracle(output/'jdk-oracle',raw_good,wrapped,bad,dicts)
    for item in record['inputs']:checked(item)
    result=dict(verified=True,scope='unregistered_direct_native_Inflater_component_normal_heap_arrays_fields_and_Java_error_callbacks',images=S.artifact(path),
        observations=observations,typed_errors=typed_errors,invalid_handles=invalid,OS_workers=threads,native_calls=native_calls,JDK_private_native_reference=oracle,quiescent_collection=dict(freed=freed,source_spans=spans,native_handles_survived=len(live_for_gc)),
        end_race=dict(shared_lifetime_lease_observed=race_observed,actual_large_native_copy_completed=True,stale_handle_rejected=True),
        explicit_owner_cleanup_states=len(abandoned),native_owned_states_final=0,native_owned_bytes_final=0,automatic_Cleaner_executed=False,
        original_Inflater_class_remained_cold=True,normal_Inflater_constructor_executed=False,Java_state_or_metadata_patched=False,
        normal_String_initialization=dict(before=string_before,after=string_after,source_Code_sha256=initializers[0]['code_sha256']),
        generic_DataFormat_message=True,RFC_HDIST32_policy_difference=True,strict_CINFO_window_policy_difference=True,registered=False,full_selection_reverified=False,game_started=False)
    S.write(output/'execution.json',result);return output/'execution.json'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','build','execute'));parser.add_argument('--candidate',type=Path);parser.add_argument('--envelope',type=Path);parser.add_argument('--images',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.action=='prepare':print(prepare(args.candidate,args.output))
    elif args.action=='build':print(build(args.candidate,args.envelope,args.output))
    else:print(execute(args.images))
