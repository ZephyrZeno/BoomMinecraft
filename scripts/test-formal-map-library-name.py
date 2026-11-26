"""Cold normal mapLibraryName using the formal 26 input set and original Java."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier,get_native_id
from uuid import uuid4
import zipfile


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('formal_map_selection',ROOT/'scripts/formal-provider-selection.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)
S=F.S
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8
NORMAL=['','net','nio','中文','\U0001f600','raw\0name','\ud800','\udc00','\ud800\0\udc00',
        'x'*240,'\U0001f600'*120,'x'*239+'\0','\udc00'*240,'\0'*240]
LONG=['x'*241,'\U0001f600'*120+'x','\0'*241,'\ud800'*241]
ROOT_SPANS=[('boom_probe_static_roots','boom_probe_static_root_count'),
    ('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),
    ('boom_java_class_roots','boom_java_class_root_count'),
    ('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),
    ('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),
    ('boom_provider_threads_roots','boom_provider_threads_root_count')]


def proc(image,name,result,*arguments):
    function=getattr(image,name);function.restype,function.argtypes=result,arguments;return function


def addr(image,name):return c.addressof(c.c_byte.in_dll(image,name))


class SourceGap(Exception):
    def __init__(self,stage,context,row):
        self.record=dict(stage=stage,context=list(context),row=row)
        super().__init__('Original source gap: '+str((stage,list(context),row['symbol'])))


def source_members(summary,classes):
    wanted=[('java/lang/String','<init>','([C)V'),('java/lang/String','toCharArray','()[C'),
            ('java/lang/Object','<init>','()V')]
    I=S.module('formal_map_original_members','verify-translation-ir.py');result=[]
    for owner,name,descriptor in wanted:
        [cls]=[row for row in classes if row['name']==owner and row['origin']['loader']=='bootstrap']
        raw=I.Source(S.original_class(summary,cls))
        [member]=[dict(method=ident,class_id=cls['id'],class_sha256=cls['origin']['sha256'],owner=owner,
            name=name,descriptor=descriptor,code_sha256=hashlib.sha256(raw.code(m)['bytes']).hexdigest())
            for ident,m in zip(cls['method_ids'],raw.methods) if (m['name'],m['descriptor'])==(name,descriptor)]
        result.append(member)
    return result


def oracle(summary,output):
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']));record=catalog['image']
    S.check(S.digest(record['path'])==record['digest'],'Locked JDK module image changed')
    home=Path(record['path']).parents[1];java=home/'bin/java.exe';source=output/'MapLibraryNameOracle.java'
    source.write_text('''class MapLibraryNameOracle {
 public static void main(String[] args) {
  for (String hex:args) {
   StringBuilder name=new StringBuilder();
   for(int i=0;i<hex.length();i+=4) name.append((char)Integer.parseInt(hex.substring(i,i+4),16));
   try { String value=System.mapLibraryName(name.toString()); StringBuilder out=new StringBuilder("OK:");
    for(int i=0;i<value.length();i++) out.append("%04x".formatted((int)value.charAt(i)));
    System.out.println(out);
   } catch(IllegalArgumentException e) {System.out.println("ERROR:"+e.getClass().getName()+":"+e.getMessage());}
  }
  try {System.mapLibraryName(null);throw new AssertionError();}
  catch(NullPointerException e){System.out.println(e.getClass().getName());}
 }
}
''',encoding='ascii')
    result=subprocess.run([str(java),str(source),*[name.encode('utf-16-be','surrogatepass').hex() for name in NORMAL+LONG]],
        check=True,capture_output=True,timeout=60)
    (output/'oracle.stdout').write_bytes(result.stdout);(output/'oracle.stderr').write_bytes(result.stderr)
    expected=['OK:'+(name+'.dll').encode('utf-16-be','surrogatepass').hex() for name in NORMAL]
    expected+=['ERROR:java.lang.IllegalArgumentException:name too long']*len(LONG)+['java.lang.NullPointerException']
    S.check(result.stdout.decode('ascii').splitlines()==expected,'Locked JDK mapLibraryName UTF16/error behavior differs')
    return dict(java=S.artifact(java),modules=record,source=S.artifact(source),stdout=S.artifact(output/'oracle.stdout'),cases=19)


def contract(images_file):
    images=S.read(images_file);closure=S.read(F.checked(images['source_manifest']))
    [pack]=[row for row in images['providers'] if row['family']=='normal-library-name-v1']
    [throwable_pack]=[row for row in images['providers'] if row['family']=='normal-throwable-v1']
    S.check(pack['selected'] and throwable_pack['selected'],'Formal map and Throwable packs were not selected')
    meta=S.read(F.checked(pack['metadata']['library_name_metadata']))
    throwable_manifest=S.read(F.checked(throwable_pack['manifest']))
    throwable=S.read(F.checked(throwable_manifest['normal_throwable_metadata']))
    _,summary,classes=S.base(Path(closure['batch']),Path(closure['plan']))
    fixtures=source_members(summary,classes)
    S.check(not closure['selected_property_natives'],'Focused map test selected a property native')
    properties=summary['properties'];S.check(properties['root_cells']==109,'Expected the original 109-cell properties bank')
    S.check(all(closure['objects'].count(u['object']['path'])==1 for u in properties['units']),
            'Formal map omitted or duplicated the original properties COFF')
    raw=properties['class_id'];[raw_state]=[row for row in closure['selected_classes'] if row['class_id']==raw]
    S.check(raw_state['name']=='jdk/internal/util/SystemProps$Raw' and not raw_state['diagnostic'],
            'Formal map omitted the normal original Raw class state')
    assembly=(images_file.parent/'initialization-closure.asm').read_text(encoding='utf-8')
    S.check('boom_batch_class_failure_root'+str(raw)+' QWORD ?' in assembly,'Original Raw failure root is missing')
    for row in [*meta['original_java'],*fixtures]:
        selected=closure['selected_methods'].get(str(row['method']))
        S.check(selected and selected['class_id']==row['class_id'] and selected['source_sha256']==row['class_sha256'] and
                selected['code_sha256']==row['code_sha256'],'Original map callback/constructor was not selected: '+str(row))
    layout_id=meta['source_classes']['java/lang/IllegalArgumentException']
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        [layout]=[row for line in stream if (row:=json.loads(line))['class_id']==layout_id]
    throwable_id=meta['source_classes']['java/lang/Throwable']
    [message]=[f for f in layout['candidate']['fields'] if f['member']['owner']==throwable_id and
        f['member']['name']=='detailMessage' and f['member']['descriptor']=='Ljava/lang/String;']
    S.check(message['reference'] and message['storage_bytes']==8,'Original Throwable message layout changed')
    [trace]=[row for row in throwable['rows'] if row['class_id']==layout_id]
    return images,closure,summary,meta,fixtures,properties,raw_state,message,trace


def execute(images_file):
    F.verify(images_file)
    images,closure,summary,meta,fixtures,properties,raw_state,message,trace=contract(images_file)
    for record in images['harness_sources']:F.checked(record)
    runtime=F.checked(images['runtime'])
    with os.add_dll_directory(str(runtime.parent)):
        rt,image=c.CDLL(str(runtime)),c.CDLL(str(F.checked(images['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Normal source heap bind failed')
    diagnostic=S.read(images_file.parent/'diagnostic.json');pool=addr(image,'boom_diagnostic_pool')
    classes=meta['source_classes'];string_id=classes['java/lang/String'];raw=raw_state['class_id']
    def state(ident):return U.from_address(addr(image,'boom_class'+str(ident))+8).value
    raw_descriptor=addr(image,'boom_class'+str(raw));failure=P.from_address(raw_descriptor+56).value
    root=addr(image,'boom_probe_static_roots');count=Q.from_address(addr(image,'boom_probe_static_root_count')).value
    S.check(root<=failure<root+count*8 and (failure-root)%8==0 and not Q.from_address(failure).value,
            'Raw failure root is not its original source static bank cell')
    props_root=addr(image,'boom_java_properties_roots');props_count=Q.from_address(addr(image,'boom_java_properties_root_count')).value
    S.check(props_count==109 and not any((Q*props_count).from_address(props_root)),
            'Original properties root bank was not cold and complete')
    cold=dict(System=state(meta['owner']),String=state(string_id),Raw=state(raw),Raw_failure_root_offset=failure-root,
        properties_cells=props_count,properties_non_null=0,Raw_failure_root_zero=True)
    S.check((cold['System'],cold['String'],cold['Raw'])==(0,0,0),'Source class metadata was not cold')
    methods={(r['owner'],r['name'],r['descriptor']):r['method'] for r in [*meta['original_java'],*fixtures]}
    def check_context(stage,context):
        row=U.from_address(pool+32).value
        if row:
            [record]=[r for r in diagnostic['rows'] if r['id']==row]
            raise SourceGap(stage,context,record)
        S.check(not context[0] and not context[3],'Original Java stopped: '+str((stage,list(context))))
    def call(ident,context,args):
        return proc(image,'boom_m'+str(ident),Q,P,P)(context,(Q*max(1,len(args)))(*args))
    def source(key,args):
        context=Context();value=call(methods[key],context,args);check_context(str(key),context);return value
    allocate=proc(rt,'boom_object_new',P,P,P,P);array=proc(rt,'boom_array_new',P,P,c.c_int,U,P)
    context=Context();proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(string_id)),context)
    check_context('original String initialization',context)
    def string(text):
        raw_text=text.encode('utf-16-le','surrogatepass');context=Context()
        chars=array(heap,len(raw_text)//2,5,context);check_context('normal char array allocation',context)
        S.check(chars,'Normal char array allocation returned null');c.memmove(chars,raw_text,len(raw_text))
        value=allocate(heap,addr(image,'boom_layout'+str(string_id)),context);check_context('normal String allocation',context)
        S.check(value,'Normal String allocation returned null')
        source(('java/lang/String','<init>','([C)V'),[value,chars]);return value
    def text(value):
        chars=source(('java/lang/String','toCharArray','()[C'),[value])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    map_id=meta['methods'][0]['method']
    def mapping(guest,name):
        context=Context();value=call(map_id,context,[guest]);check_context('normal mapLibraryName wrapper',context)
        S.check(value and value!=guest and text(value)==name+'.dll','Formal map returned different String contents or identity')
        return value
    guests=[string(name) for name in NORMAL[:8]]
    S.check(state(meta['owner'])==0 and state(raw)==0,'String construction preinitialized System/Raw')
    barrier=Barrier(8,timeout=30)
    def cold_worker(index):
        barrier.wait();value=mapping(guests[index],NORMAL[index]);return get_native_id(),value
    with ThreadPoolExecutor(8) as workers:rows=list(workers.map(cold_worker,range(8)))
    S.check(len({r[0] for r in rows})==8 and state(meta['owner'])==2,'Eight cold normal wrappers did not publish original System initialization')
    held=[r[1] for r in rows]
    for name in NORMAL:held.append(mapping(string(name),name))
    errors=[]
    for name in LONG:
        context=Context();value=call(map_id,context,[string(name)])
        if U.from_address(pool+32).value:check_context('original typed long-name exception',context)
        error=P.from_address(c.addressof(context)+16).value
        S.check(not value and context[0]==16 and not context[3] and error,'Long name did not produce an original typed error')
        S.check(P.from_address(error-8).value==addr(image,'boom_layout'+str(classes['java/lang/IllegalArgumentException'])),
                'Long-name error has another source class')
        S.check(text(P.from_address(error+message['offset']).value)=='name too long','Original Java exception message differs')
        depth=U.from_address(error+trace['depth']).value;backtrace=P.from_address(error+trace['backtrace']).value
        S.check(0<depth<=128 and backtrace and Q.from_address(backtrace).value==0x142545243 and
                Q.from_address(backtrace+8).value==addr(image,'boom_trace_pool'),'Original Throwable backtrace was not captured')
        frames=[Q.from_address(backtrace+16+i*8).value for i in range(depth)]
        S.check(map_id in [frame>>32 for frame in frames],'Original Throwable trace omitted the normal map frame')
        errors.append(dict(input_units=len(name.encode('utf-16-le','surrogatepass'))//2,
            depth=depth,frames=[dict(method=v>>32,bci=v&0xffffffff) for v in frames]));held.append(error)
    context=Context();S.check(not call(map_id,context,[0]) and context[0]==4 and not context[3],'Null map boundary differs')
    context=Context();S.check(not call(map_id,context,[1]) and context[0]==7 and not context[3],'Foreign map boundary differs')
    object_id=next(r['class_id'] for r in fixtures if r['owner']=='java/lang/Object');context=Context()
    wrong=allocate(heap,addr(image,'boom_layout'+str(object_id)),context);check_context('wrong-class Object allocation',context)
    source(('java/lang/Object','<init>','()V'),[wrong])
    context=Context();S.check(not call(map_id,context,[wrong]) and context[0]==7 and not context[3],'Wrong source class was accepted')
    preserved=Context(9,4,7,0,11,12,13,14);before=list(preserved)
    S.check(not call(map_id,preserved,[1]) and list(preserved)==before,'Pending context was overwritten')
    barrier=Barrier(8,timeout=30)
    def worker(index):
        barrier.wait()
        for turn in range(10):
            for name in NORMAL:mapping(string(name),name)
        return get_native_id()
    with ThreadPoolExecutor(8) as workers:tids=list(workers.map(worker,range(8)))
    S.check(len(set(tids))==8,'Normal mapping did not run on eight OS threads')
    exported=set(closure['exports']);root_values=[];spans=[]
    for name,count_name in ROOT_SPANS:
        if name not in exported and count_name not in exported:continue
        S.check(name in exported and count_name in exported,'Partial source GC span was exported')
        cells=Q.from_address(addr(image,count_name)).value;S.check(cells<=1048576,'Source GC span exceeds the heap ABI')
        raw_values=(Q*cells).from_address(addr(image,name));snapshot=bytes(raw_values)
        values=[v for v in raw_values if v];root_values+=values
        spans.append(dict(symbol=name,cells=cells,non_null_cells=len(values),sha256=hashlib.sha256(snapshot).hexdigest()))
    S.check(any(r['symbol']=='boom_java_properties_roots' and r['cells']==109 for r in spans),'Actual GC omitted the original properties bank')
    roots=list(dict.fromkeys(root_values+held));packed=(Q*len(roots))(*roots)
    freed=proc(rt,'boom_heap_collect',Q,P,P,U)(heap,packed,len(roots))
    S.check(freed!=0xffffffffffffffff,'Quiescent original ASM collection failed')
    contains=proc(rt,'boom_heap_contains',U,P,P)
    S.check(all(contains(heap,value) for value in roots),'Collection lost a complete source root or explicit test handle')
    for row in spans:
        S.check(hashlib.sha256(bytes((Q*row['cells']).from_address(addr(image,row['symbol'])))).hexdigest()==row['sha256'],
                'Collection changed an original root bank')
    S.check(state(raw)==0 and not Q.from_address(failure).value,'Map calls changed the unused original Raw class state/failure root')
    S.check(not U.from_address(pool+32).value and not Q.from_address(addr(image,'boom_trace_pool')+32).value,
            'Successful map execution retained a diagnostic stop or shadow frame lease')
    S.check(proc(image,'boom_release_trace_pool',U)()==0 and proc(rt,'boom_heap_destroy',U,P)(heap)==1,
            'Map trace/heap cleanup failed')
    oracle_dir=images_file.parent/'oracle';oracle_dir.mkdir();comparison=oracle(summary,oracle_dir)
    for record in images['inputs']:F.checked(record)
    return dict(schema=1,verified=True,scope='formal26_focused_cold_normal_mapLibraryName_original_Java_and_properties_dependency',
        images=S.artifact(images_file),formal_map_pack=next(p['manifest'] for p in images['providers'] if p['family']=='normal-library-name-v1'),
        selected_property_natives={},original_properties_module_linked=True,original_property_root_cells=109,
        original_Raw_class_and_failure_root_selected=True,cold=cold,original_System_class_initializer_completed=True,
        metadata_or_clinit_state_written_by_host=False,original_String_constructor_executed=True,
        normal_names=14,typed_long_name_errors=errors,null_error=4,foreign_and_wrong_class_error=7,
        pending_context_preserved=True,ordinary_framed_map_wrapper_only=True,native_entry_bypassed=False,
        cold_OS_thread_ids=[r[0] for r in rows],concurrent_OS_thread_ids=tids,concurrent_OS_threads=8,
        repeated_concurrent_mapping_calls=1120,original_Throwable_backtrace_verified=True,JDK_oracle=comparison,
        normal_root_spans=spans,quiescent_collection_freed=freed,property_bank_live_oop_retention_claim=False,
        source_root_banks_unmodified=True,heap_destroyed=True,trace_pool_released=True,
        full_VM_startup=False,game_started=False,world_created=False)


def run(state_file,output,max_rounds):
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Use a fresh formal map output directory')
    _,values,paths=F.state_inputs(state_file);identity,summary,classes=S.base(values['batch'],values['plan'])
    manifests=[S.read(p) for p in paths];[pack]=[p for p in manifests if p['family']=='normal-library-name-v1']
    meta=S.read(S.checked(pack['library_name_metadata']));fixtures=source_members(summary,classes)
    roots=[('bootstrap','java/lang/System','mapLibraryName','(Ljava/lang/String;)Ljava/lang/String;')]
    roots += [('bootstrap',r['owner'],r['name'],r['descriptor']) for r in fixtures]
    admitted=set(meta['required_java_methods'])|{r['method'] for r in fixtures};admitted_classes=set();history=[]
    output.mkdir(parents=True)
    for attempt in range(max_rounds):
        directory=output/('round-'+format(attempt,'03d'))
        images=F.prepare(state_file,directory,method_roots=roots,admitted_methods=sorted(admitted),admitted_classes=sorted(admitted_classes),
            exports=[f"boom_layout{i}" for i in {r['class_id'] for r in fixtures}|set(meta['source_classes'].values())],
            optional_exports=[name for pair in ROOT_SPANS for name in pair],harness_sources=[__file__])
        with (directory/'execution.stdout').open('wb') as stdout,(directory/'execution.stderr').open('wb') as stderr:
            process=subprocess.run([sys.executable,'-B',__file__,'--execute','--images',str(images)],stdout=stdout,stderr=stderr)
        result_file=directory/'execution-result.json'
        S.check(result_file.exists(),'Formal map execution failed without a structured result; inspect '+str(directory))
        result=S.read(result_file);history.append(dict(round=attempt,exit_code=process.returncode,result=S.artifact(result_file)))
        if result.get('verified'):
            result.update(rounds=history,source_admitted_methods=sorted(admitted),source_admitted_classes=sorted(admitted_classes))
            S.write(output/'result.json',result);print(output/'result.json',flush=True);return
        S.check(result.get('source_gap') is not None,'Formal map failed outside an admitted original source gap: '+str(result))
        row=result['source_gap']['row'];method=row.get('method');initialization=row.get('initialization')
        if method is not None:
            S.check(row['category']==1 and method['assembly_emitted'] and method['id'] not in admitted,
                    'Formal map reached an unavailable/duplicate Java source gap')
            admitted.add(method['id'])
        else:
            S.check(row['category']==5 and initialization is not None and initialization['class_id'] not in admitted_classes,
                    'Formal map reached an unsupported original initialization gap')
            admitted_classes.add(initialization['class_id'])
        S.write(directory/'next-source-admission.json',dict(methods=sorted(admitted),classes=sorted(admitted_classes),
            original_failure=S.artifact(result_file),whole_original_methods_and_classes_only=True,instructions_changed=False))
        print(json.dumps(dict(round=attempt,observed_original_gap=row['symbol'],next_methods=len(admitted),next_classes=len(admitted_classes))),flush=True)
    raise ValueError('Formal map source admission round limit reached; all original failures retained in '+str(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'formal-map-library-name'/uuid4().hex)
    parser.add_argument('--images',type=Path);parser.add_argument('--execute',action='store_true');parser.add_argument('--max-rounds',type=int,default=32)
    args=parser.parse_args()
    if args.execute:
        S.check(args.images is not None,'Execution requires its newly prepared formal image')
        try:S.write(args.images.parent/'execution-result.json',execute(args.images.resolve()))
        except SourceGap as error:
            S.write(args.images.parent/'execution-result.json',dict(verified=False,source_gap=error.record,original_failure_preserved=True,game_started=False))
            print(str(error),file=sys.stderr);sys.exit(86)
        except Exception as error:
            S.write(args.images.parent/'execution-result.json',dict(verified=False,error=repr(error),game_started=False));raise
    else:
        S.check(args.state is not None,'Provide the pending verified formal26 state')
        run(args.state.resolve(),args.output,args.max_rounds)
