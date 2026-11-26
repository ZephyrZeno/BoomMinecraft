"""Relink only mapLibraryName over a verified normal source image and execute it."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
from threading import Barrier,get_native_id
from uuid import uuid4
import zipfile


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('standalone_library_name_candidate',ROOT/'scripts/library-name-candidate.py')
B=importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
S=B.S
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
Context=U*8


def proc(image,name,result,*arguments):
    value=getattr(image,name)
    value.restype,value.argtypes=result,arguments
    return value


def addr(image,name):
    return c.addressof(c.c_byte.in_dll(image,name))


def fixture_methods(meta,summary,classes):
    I=B.module('verify-translation-ir')
    wanted=[('java/lang/String','<init>','([C)V')]
    result=[]
    for owner,name,descriptor in wanted:
        [cls]=[row for row in classes if row['name']==owner and row['origin']['loader']=='bootstrap']
        raw=I.Source(S.original_class(summary,cls))
        [row]=[dict(method=ident,owner=owner,class_id=cls['id'],class_sha256=cls['origin']['sha256'],
            name=name,descriptor=descriptor,code_sha256=hashlib.sha256(raw.code(method)['bytes']).hexdigest())
            for ident,method in zip(cls['method_ids'],raw.methods) if (method['name'],method['descriptor'])==(name,descriptor)]
        result.append(row)
    return result


def source_stacktrace_delta(summary,classes,method,output,assembler):
    """Copy the actually missing original Java method without editing branches."""
    source=B.module('batch-source').Sources()
    ident=method['method']
    key=f"classes/{method['class_id']:06}.json"
    found=None
    for shard in summary['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as archive:
            if key not in archive.namelist():
                continue
            S.checked(shard['zip'])
            compiled=json.loads(archive.read(key))
            [record]=[row for row in compiled['methods'] if row['id']==ident]
            S.check(compiled['source_sha256']==method['class_sha256'] and record['assembly_emitted'] and
                record['operand_verified'] and record['code_sha256']==method['code_sha256'],
                'Stacktrace delta does not belong to the exact compiled original Java Code')
            unit=shard['units'][record['assembly_unit']]
            original=S.checked(unit['assembly'])
            S.checked(unit['object'])
            wrapper,body=[source.function(original,f'boom_m{ident}'+suffix) for suffix in ('','_body')]
            tables=''.join(source.handler_table(original,index) for index in sorted(set(
                map(int,re.findall(r'\bboom_handlers(\d+)\b',wrapper+body)))))
            found=shard,unit,wrapper,body,tables
            break
    S.check(found,'Exact original stacktrace Java source is unavailable')
    shard,unit,wrapper,body,tables=found
    I=B.module('verify-translation-ir')
    [owner]=[row for row in classes if row['id']==method['class_id']]
    raw=I.Source(S.original_class(summary,owner))
    [declaration]=[row for row in raw.methods if (row['name'],row['descriptor'])==(method['name'],method['descriptor'])]
    code=raw.code(declaration)
    pcs=[row['pc'] for row in I.stream(code['bytes'])]
    S.check(hashlib.sha256(code['bytes']).hexdigest()==method['code_sha256'] and
        list(map(int,re.findall(rf'(?m)^boom_m{ident}_body_L(\d+):',body)))==pcs and
        (not code['handlers'] or tables),'Original stacktrace Code, PCs or handlers changed')
    selected=tables+'\n.code\n'+wrapper+'\n'+body
    defined=set(re.findall(r'(?m)^\s*(boom_\w+)(?::|\s+(?:PROC|LABEL|QWORD|DWORD|WORD|BYTE)\b)',selected))
    calls=set(re.findall(r'(?m)^\s*(?:call|jmp)\s+(boom_\w+)',selected))
    imports=set(re.findall(r'\bboom_\w+\b',selected))-defined
    exports={f'boom_m{ident}',f'boom_m{ident}_body'}
    text='option casemap:none\n'+''.join(f'EXTERN {name}:{"PROC" if name in calls else "BYTE"}\n' for name in sorted(imports))
    text+=''.join('PUBLIC '+name+'\n' for name in sorted(exports))+selected+'\nEND\n'
    asm,obj=output/'source-stacktrace.asm',output/'source-stacktrace.obj'
    asm.write_text(text)
    with (output/'source-stacktrace-assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
    S.check(B.A.coff_symbols(obj)==(exports,imports),'Source stacktrace delta COFF imports/exports changed')
    proof=dict(original_method=method,original_shard=S.artifact(S.checked(shard['zip'])),
        original_assembly=unit['assembly'],original_COFF=unit['object'],assembly=S.artifact(asm),object=S.artifact(obj),
        original_wrapper_sha256=hashlib.sha256(wrapper.encode()).hexdigest(),
        original_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        original_handlers_sha256=hashlib.sha256(tables.encode()).hexdigest(),source_bytecode_PCs=pcs,
        source_Code_handler_count=len(code['handlers']),all_original_branches_retained=True,
        imported_symbols=sorted(imports),new_class_or_static_roots=False,Java_codegen_rerun=False,
        original_Java_ASM_or_COFF_modified=False)
    S.write(output/'source-stacktrace.json',proof)
    return obj,S.artifact(output/'source-stacktrace.json')


def build(candidate_file,baseline_result,output):
    output=output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project execution directory required')
    proof=B.verify(candidate_file)
    S.check(proof==S.read(candidate_file.with_name('verification.json')),'Independent library-name source proof changed')
    candidate=S.read(candidate_file)
    meta=candidate['metadata']
    accepted=S.read(baseline_result)
    S.check(accepted['verified'],'Verified cold source image execution required')
    images_file=S.checked(accepted['images'])
    images=S.read(images_file)
    manifest_file=S.checked(images['source_manifest'])
    closure=S.read(manifest_file)
    selection=Path(images['source_selection_directory'])
    selection_proof=S.read(S.checked(images['source_selection']))
    S.check(selection_proof['verified'] and selection_proof['closure_manifest_sha256']==S.digest(manifest_file)['sha256'] and
        closure['source_batch_summary_sha256']==meta['base']['batch_summary']['digest']['sha256'] and
        closure['source_input_fingerprint']==meta['base']['input_fingerprint'] and
        Path(closure['batch'])==Path(meta['base']['batch']) and Path(closure['plan'])==Path(meta['base']['plan']),
        'Execution fixture must use the same verified original source batch and plan')
    S.checked(images['image'])
    runtime=S.checked(images['runtime'])
    runtime_meta=S.read(runtime.with_name('runtime.json'))
    S.check(all(runtime_meta['sources'].get(path)==digest for path,digest in meta['runtime_kernel_sha256'].items()),
        'Actual fixture runtime kernel differs from the independent source contract')
    _,summary,classes=S.base(Path(closure['batch']),Path(closure['plan']))
    fixture=fixture_methods(meta,summary,classes)
    F=B.module('file-bootstrap-source')
    [throwable]=[row for row in classes if row['name']=='java/lang/Throwable' and row['origin']['loader']=='bootstrap']
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        [throwable_layout]=[row for line in stream if (row:=json.loads(line))['class_id']==throwable['id']]
    [message_field]=F.fields(throwable,throwable_layout,[('detailMessage','Ljava/lang/String;',2,8,True)],S)
    error_class=meta['source']['source_classes']['java/lang/IllegalArgumentException']
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        [error_layout]=[row for line in stream if (row:=json.loads(line))['class_id']==error_class]
    inherited=[row for row in error_layout['candidate']['fields'] if row['member']['owner']==throwable['id'] and
        row['member']['name']=='detailMessage' and row['member']['descriptor']=='Ljava/lang/String;']
    S.check(len(inherited)==1 and inherited[0]['reference'] and inherited[0]['storage_bytes']==8 and
        inherited[0]['offset']==message_field['offset'],'Source Throwable message field is not inherited at the verified offset')
    [stacktrace]=[row for row in meta['source']['original_java'] if row['owner']=='java/lang/Throwable']
    S.check(str(stacktrace['method']) not in closure['selected_methods'],
        'This delta fixture requires the actually observed missing original stacktrace Java method')
    for row in [row for row in meta['source']['original_java'] if row!=stacktrace]+fixture:
        selected=closure['selected_methods'].get(str(row['method']))
        S.check(selected and selected['code_sha256']==row['code_sha256'] and
            selected['source_sha256']==row['class_sha256'] and selected['class_id']==row['class_id'],
            'Original required Java callback is not selected: '+str(row))
    ident=meta['source']['methods'][0]['method']
    name='boom_m'+str(ident)
    diagnostic=S.read(selection/'diagnostic.json')
    [native_row]=[row for row in diagnostic['rows'] if row['symbol']==name]
    S.check(native_row['category']==2 and native_row['method']['id']==ident and
        native_row['source_sha256']==meta['source']['methods'][0]['class_sha256'],
        'Replacement would override original Java instead of the exact native declaration')
    [java_row]=[row for row in diagnostic['rows'] if row['symbol']=='boom_m'+str(stacktrace['method'])]
    S.check(java_row['category']==1 and java_row['method']['code_sha256']==stacktrace['code_sha256'],
        'Expected observed unselected stacktrace Java stop is missing')
    state=S.read(S.checked(meta['input_state']))
    packs=S.read(Path(state['providers']))
    pack_records=packs if isinstance(packs,list) else packs['providers']
    throwable=[]
    for record in pack_records:
        file=Path(record) if isinstance(record,str) else Path(record.get('manifest',record.get('path','')))
        manifest=S.read(file)
        if manifest['family']=='normal-throwable-v1':
            throwable.append((file,manifest))
    [(throwable_file,throwable_pack)]=throwable
    S.check(throwable_pack['base']==meta['base'] and throwable_pack['assembled'],
        'Throwable service pack must belong to the same verified source batch')
    throwable_receipt=throwable_file.with_name('verification.json')
    receipt=S.read(throwable_receipt)
    S.check(receipt['verified'] and receipt['provider_manifest_sha256']==S.digest(throwable_file)['sha256'],
        'Original Throwable formal pack receipt differs')
    [throwable_native]=throwable_pack['methods']
    throwable_rows=[row for row in diagnostic['rows'] if row['symbol']=='boom_m'+str(throwable_native['method'])]
    S.check(len(throwable_rows)<=1 and all(row['category']==2 and row['source_sha256']==throwable_native['class_sha256']
        for row in throwable_rows),'Original Throwable native stop differs')
    replaced_rows=[native_row,java_row]+throwable_rows
    units=selection_proof['verified_assembly_objects']['units']
    [stops]=[unit for unit in units if Path(unit['assembly']['path']).name=='diagnostic-stops.asm']
    original=S.checked(stops['assembly']).read_text()
    old_obj=S.checked(stops['object'])
    remaining=original
    fragments=[]
    for row in replaced_rows:
        label=row['symbol']
        fragment=(f'PUBLIC {label}\n{label} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
            f' lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop\n{label} ENDP\n')
        S.check(remaining.count(fragment)==1,'Original development stop changed: '+label)
        remaining=remaining.replace(fragment,'',1)
        fragments.append(dict(symbol=label,sha256=hashlib.sha256(fragment.encode()).hexdigest()))
    response=selection/'link.rsp'
    lines=response.read_text().splitlines()
    original_objects=[str(Path(line.strip('"')).resolve()) for line in lines if line.lower().endswith('.obj"')]
    expected=[selection/'initialization-closure.obj',selection/'diagnostic-stops.obj']+[Path(p) for p in closure['objects']]
    S.check(original_objects==[str(p.resolve()) for p in expected] and len(original_objects)==len(set(original_objects)),
        'Original verified source object list differs')
    [old_line]=[line for line in lines if line.startswith('"') and Path(line.strip('"')).resolve()==old_obj]
    input_paths=[Path(line.strip('"')) for line in lines if line.startswith('"')]
    inputs=[S.artifact(p) for p in input_paths]
    assembler=Path(candidate['assembler']['path'])
    linker=assembler.with_name('link.exe')
    output.mkdir(parents=True)
    delta,delta_proof=source_stacktrace_delta(summary,classes,stacktrace,output,assembler)
    throwable_obj=S.checked(throwable_pack['object'])
    S.check(str(throwable_obj) not in original_objects,'Throwable service must not already be linked in this cold fixture')
    asm,obj=output/'remaining-stops.asm',output/'remaining-stops.obj'
    asm.write_text(remaining)
    with (output/'stops-assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    exported={line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')}
    exported|=set(candidate['exports'])|{f"boom_m{m['method']}" for m in meta['source']['original_java']+fixture}
    exported|={f"boom_layout{i}" for i in meta['source']['required_classes']}
    exported|={'boom_heap_ptr','boom_java_string_literals_bind_heap','boom_java_properties_string_pool',
        'boom_java_platform_properties_pool'}
    dll=output/'library-name.dll'
    modified=[('"'+str(obj)+'"' if line==old_line else line) for line in lines
        if not line.startswith(('/OUT:','/EXPORT:'))]
    modified+=['/OUT:"'+str(dll)+'"','"'+str(S.checked(candidate['object']))+'"','"'+str(delta)+'"','"'+str(throwable_obj)+'"']
    modified+=['/EXPORT:'+name for name in sorted(exported)]
    rsp=output/'link.rsp'
    rsp.write_text('\n'.join(modified)+'\n')
    with (output/'link.log').open('wb') as log:
        subprocess.run([linker,'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    for record in inputs:
        S.check(S.artifact(record['path'])==record,'An original link input changed during isolated relinking')
    E=B.module('diagnostic-closure')
    S.check(E.pe_exports(dll)==exported and not {'boom_nio_buffer_pool','boom_nio_buffer_service'}&exported,
        'Isolated library-name image has unexpected exports or NIO native-buffer dependency')
    catalog=S.read(S.checked(summary['frames']['original_system_catalog']))
    oracle_home=Path(catalog['image']['path']).parents[1]
    S.check(S.digest(catalog['image']['path'])['sha256']==catalog['image']['digest']['sha256'],
        'Locked oracle module image changed')
    manifest=dict(schema=1,scope='standalone_mapLibraryName_over_verified_formal_source_image',
        source_candidate=S.artifact(candidate_file),source_proof=S.artifact(candidate_file.with_name('verification.json')),
        baseline_execution=S.artifact(baseline_result),baseline_images=S.artifact(images_file),
        source_manifest=S.artifact(manifest_file),source_selection=S.artifact(selection/'selection-verification.json'),
        original_link_response=S.artifact(response),link_inputs=inputs,
        replaced_declarations=replaced_rows,removed_development_stops=fragments,
        source_Java_delta=delta_proof,accepted_Throwable_provider=S.artifact(throwable_file),
        accepted_Throwable_receipt=S.artifact(throwable_receipt),accepted_Throwable_COFF=S.artifact(throwable_obj),
        remaining_diagnostic_assembly=S.artifact(asm),remaining_diagnostic_object=S.artifact(obj),
        image=S.artifact(dll),runtime=S.artifact(runtime),link_response=S.artifact(rsp),
        assembler=S.artifact(assembler),linker=S.artifact(linker),execution_tool=S.artifact(Path(__file__)),
        source_fixture_methods=fixture,read_only_Throwable_message_observer=message_field,
        oracle_home=str(oracle_home),oracle_modules=catalog['image'],
        existing_Java_ASM_or_COFF_modified=False,Java_codegen_rerun=False,source_selection_reverified_in_this_run=False,
        original_development_stops_replaced=len(replaced_rows),original_virtual_table_modified=False,
        NIO_candidate_used=False,NIO_buffers_linked=False,
        registered_in_shared_runtime=False,executed=False,game_started=False)
    S.write(output/'images.json',manifest)
    return output/'images.json'


def oracle(java_home,work,names):
    java=java_home/'bin/java.exe'
    source=work/'LibraryNameOracle.java'
    source.write_text('''class LibraryNameOracle {
 public static void main(String[] names) {
  for (String hex : names) {
   StringBuilder name = new StringBuilder();
   for (int i=0; i<hex.length(); i+=4) name.append((char)Integer.parseInt(hex.substring(i,i+4),16));
   try {
    String text=System.mapLibraryName(name.toString());
    StringBuilder result=new StringBuilder("OK:");
    for (int i=0;i<text.length();i++) result.append("%04x".formatted((int)text.charAt(i)));
    System.out.println(result);
   } catch (IllegalArgumentException ex) { System.out.println("ERROR:"+ex.getClass().getName()+":"+ex.getMessage()); }
  }
  try { System.mapLibraryName(null); throw new AssertionError(); }
  catch (NullPointerException ex) { System.out.println(ex.getClass().getName()); }
 }
}
''',encoding='ascii')
    process=subprocess.run([java,source,*[name.encode('utf-16-be','surrogatepass').hex() for name in names]],
        capture_output=True,check=True,timeout=45)
    output=process.stdout.decode('ascii').splitlines()
    S.check(len(output)==len(names)+1 and output[-1]=='java.lang.NullPointerException',
        'Locked JDK oracle null semantics differ')
    (work/'oracle.stdout').write_bytes(process.stdout)
    return output[:-1],dict(source=S.artifact(source),java=S.artifact(java),stdout=S.artifact(work/'oracle.stdout'))


def run(images_file):
    manifest=S.read(images_file)
    S.check(S.artifact(Path(__file__))==manifest['execution_tool'],'Execution tool changed')
    candidate=S.read(S.checked(manifest['source_candidate']))
    meta=candidate['metadata']['source']
    for record in (manifest['source_proof'],manifest['baseline_execution'],manifest['source_manifest'],
            manifest['source_selection'],manifest['remaining_diagnostic_assembly'],manifest['remaining_diagnostic_object']):
        S.checked(record)
    runtime=S.checked(manifest['runtime'])
    with os.add_dll_directory(str(runtime.parent)):
        rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(manifest['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Normal source heap bind failed')
    objects=proc(rt,'boom_object_new',P,P,P,P)
    arrays=proc(rt,'boom_array_new',P,P,c.c_int,U,P)
    class_id=meta['source_classes']['java/lang/String']
    initialization=Context()
    proc(rt,'boom_class_ensure32',U,P,P)(addr(image,'boom_class'+str(class_id)),initialization)
    S.check(not initialization[0],'Original String class initialization failed: '+str(list(initialization)))
    methods={(row['owner'],row['name'],row['descriptor']):row['method'] for row in
        meta['original_java']+manifest['source_fixture_methods']}
    def call(ident,context,args,native=False):
        packed=(Q*max(len(args),1))(*args)
        return proc(image,'boom_m'+str(ident)+('_native' if native else ''),Q,P,P)(context,packed)
    def source(key,args):
        context=Context()
        value=call(methods[key],context,args)
        S.check(not context[0] and not context[3],'Original Java method stopped: '+str(key)+' '+str(list(context)))
        return value
    def string(text):
        data=text.encode('utf-16-le','surrogatepass')
        context=Context()
        chars=arrays(heap,len(data)//2,5,context)
        S.check(chars and not context[0],'Source char[] allocation failed')
        c.memmove(chars,data,len(data))
        value=objects(heap,addr(image,'boom_layout'+str(class_id)),context)
        S.check(value and not context[0],'Normal String object allocation failed')
        source(('java/lang/String','<init>','([C)V'),[value,chars])
        return value
    def text(value):
        chars=source(('java/lang/String','toCharArray','()[C'),[value])
        return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    native=meta['methods'][0]['method']
    names=['','net','nio','中文','\U0001f600','raw\0name','\ud800','\udc00','\ud800\0\udc00',
        'x'*240,'\U0001f600'*120,'x'*239+'\0','\udc00'*240,'\0'*240]
    too_long=['x'*241,'\U0001f600'*120+'x','\0'*241,'\ud800'*241]
    oracle_dir=images_file.parent/('oracle-'+uuid4().hex)
    oracle_dir.mkdir()
    expected,oracle_proof=oracle(Path(manifest['oracle_home']),oracle_dir,names+too_long)
    S.check(all(result=='OK:'+((name+'.dll').encode('utf-16-be','surrogatepass').hex())
        for name,result in zip(names,expected[:len(names)],strict=True)) and
        all(result=='ERROR:java.lang.IllegalArgumentException:name too long' for result in expected[len(names):]),
        'Original Windows oracle differs from the locked UTF16/suffix contract')
    pool=addr(image,B.C.POOL)
    shared=addr(image,'boom_java_platform_properties_pool')
    S.check(pool!=shared and U.from_address(pool).value==0x50524f50 and U.from_address(pool+4).value==2 and
        P.from_address(pool+24).value==addr(image,'boom_java_properties_string_pool') and
        all(not Q.from_address(pool+offset).value for offset in (32,40,48,56,64,72,80,96)),
        'Independent pool contains property/dispatcher/native-buffer state')
    def mapping(name):
        original=string(name)
        context=Context()
        result=call(native,context,[original])
        S.check(result and result!=original and not context[0] and not context[3] and text(result)==name+'.dll',
            'Normal source mapLibraryName entry differs for '+repr(name)+' '+str(list(context)))
        return result
    for name in names:
        mapping(name)
    for name in too_long:
        context=Context()
        result=call(native,context,[string(name)])
        error=P.from_address(c.addressof(context)+16).value
        S.check(not result and context[0]==16 and not context[3] and error,
            '241 UTF16 units did not produce a typed source exception: '+str(list(context)))
        # The original typed exception constructor wrote this inherited field. The
        # host only observes it; no source object/static slot is modified here.
        message=P.from_address(error+manifest['read_only_Throwable_message_observer']['offset']).value
        S.check(text(message)=='name too long','Original IllegalArgumentException message changed')
        S.check(P.from_address(error-8).value==addr(image,'boom_layout'+str(meta['source_classes']['java/lang/IllegalArgumentException'])),
            'Long-name exception is not the original IllegalArgumentException class')
    context=Context()
    S.check(not call(native,context,[0]) and context[0]==4 and not context[3],'Null name did not preserve the source NPE boundary')
    for invalid in (1,):
        context=Context()
        S.check(not call(native,context,[invalid]) and context[0]==7 and not context[3],'Foreign heap name was accepted')
    wrong=objects(heap,addr(image,'boom_layout'+str(meta['source_classes']['java/lang/IllegalArgumentException'])),Context())
    context=Context()
    S.check(not call(native,context,[wrong]) and context[0]==7 and not context[3],'Wrong source class was accepted as String')
    preserved=Context(9,4,7,0,11,12,13,14)
    before=list(preserved)
    S.check(not call(native,preserved,[1]) and list(preserved)==before,'Pending source exception was overwritten')
    barrier=Barrier(8,timeout=20)
    def worker(index):
        barrier.wait()
        for turn in range(10):
            for name in names:
                mapping(name)
        return get_native_id()
    with ThreadPoolExecutor(8) as workers:
        tids=list(workers.map(worker,range(8)))
    S.check(len(set(tids))==8,'Concurrent mapping did not run on eight actual OS threads')
    destroyed=proc(rt,'boom_heap_destroy',U,P)(heap)
    S.check(destroyed==1,'Source mapping test leaked a heap ownership/monitor lease')
    return dict(schema=1,verified=True,scope='isolated_source_System_mapLibraryName_original_Java_String_and_typed_errors',
        images=S.artifact(images_file),source_native_method=native,normal_framed_entry_executed=True,
        original_String_initializer_completed=True,original_String_char_constructor_used=True,
        oracle=oracle_proof,JDK_oracle_cases=len(names)+len(too_long),normal_names=len(names),typed_241_unit_errors=len(too_long),
        UTF16_limit=240,embedded_NUL_and_unpaired_surrogates_preserved=True,
        typed_error_message_observation='source_verified_inherited_Throwable_detailMessage_read_only',
        null_source_error=4,foreign_and_wrong_class_source_error=7,pending_exception_preserved=True,
        actual_OS_thread_ids=tids,concurrent_OS_threads=8,concurrent_mapping_calls=8*10*len(names),
        independent_pool=True,NIO_candidate_used=False,NIO_buffers_linked=False,heap_destroyed=True,
        registered_in_shared_runtime=False,full_VM_startup=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--baseline-result',type=Path)
    parser.add_argument('--images',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'library-name/executions'/uuid4().hex)
    args=parser.parse_args()
    if args.images:
        images=args.images.resolve()
    else:
        S.check(args.candidate and args.baseline_result,'Provide --images or both --candidate and --baseline-result')
        images=build(args.candidate.resolve(),args.baseline_result.resolve(),args.output)
    result=images.parent/('execution-'+uuid4().hex+'.json')
    S.write(result,run(images))
    print(result)
