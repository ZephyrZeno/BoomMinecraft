"""Bind original 1.21.1 dedicated-server Main; construct argv only in ASM."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile


REPORT_BYTES=576
REPORT_ABI=14
REPORT_FIELDS=dict(class_initialized=544,main_called=548,main_returned=552,argc=556,kind=560,pc=564,method=568,depth=572)
OWNER='net/minecraft/server/Main'
LOADER='vanilla-application'
MAX_ARGUMENTS=64
MAX_ARGUMENT_UNITS=65535
MAX_TOTAL_UNITS=65535
ARGUMENT_ROWS='boom_game_argv_text_rows'
HELPER='boom_vm_call_game_main'
CALLBACKS={'boom_java_property_array','boom_java_property_copy','boom_class_ensure32'}
CREDENTIAL_OPTIONS={'accesstoken','token','password','session','sessionid','clienttoken','authorization','usertoken'}


def arguments_model(arguments,S):
    S.check(isinstance(arguments,(tuple,list)) and len(arguments)<=MAX_ARGUMENTS,'Bounded server argv list required')
    rows=[];total=0
    for index,text in enumerate(arguments):
        S.check(isinstance(text,str),'Every server argument must be an explicit string')
        option=text.split('=',1)[0].lower().lstrip('-').replace('-','').replace('_','')
        S.check(not text.startswith('-') or option not in CREDENTIAL_OPTIONS,'Credentials are not accepted in the server argv model')
        encoded=text.encode('utf-16-le','surrogatepass');units=[int.from_bytes(encoded[i:i+2],'little') for i in range(0,len(encoded),2)]
        total+=len(units)
        S.check(len(units)<=MAX_ARGUMENT_UNITS and total<=MAX_TOTAL_UNITS,'Server argv UTF16 budget exceeded')
        rows.append(dict(index=index,text=text,utf16=units,units=len(units),symbol='boom_game_argv_text_'+str(index)))
    return dict(argc=len(rows),rows=rows,total_utf16_units=total,maximum_arguments=MAX_ARGUMENTS,
        maximum_argument_units=MAX_ARGUMENT_UNITS,maximum_total_units=MAX_TOTAL_UNITS,
        origin='boom:owned-server-entry-argv-v1',original_JDK_or_game_input=False,
        mode='server_help' if list(arguments)==['--help'] else 'bounded_server_arguments',
        credentials=False,requires_isolated_working_directory=True,EULA_written_by_bridge=False,
        root_lifetime='published_after_array_allocation_until_owned_process_teardown',automatic_GC=False)


def contract(summary,owner,S,reader,arguments=('--help',)):
    origin=owner['origin'];source=origin['source_id']
    S.check(owner['name']==OWNER and origin['loader']==LOADER and not origin.get('generated') and
        origin['binary_name']==OWNER.replace('/','.') and origin['jar_entry']==OWNER+'.class' and
        source=='server/versions/1.21.1/server-1.21.1.jar' and origin['java_class_major']==65 and
        owner.get('parse_error') is None,'Game entry requires the original locked vanilla-application server 1.21.1 Main')
    archive=summary['frames']['original_input_files'].get(source)
    S.check(archive is not None,'Main original server archive is missing from pinned source inputs')
    path=S.checked(archive)
    with zipfile.ZipFile(path) as bundle:original=bundle.read(origin['jar_entry'])
    S.check(hashlib.sha256(original).hexdigest()==origin['sha256'] and int.from_bytes(original[6:8],'big')==65,
        'Original server Main class bytes/major differ')
    name,methods=reader.original_methods(original)
    S.check(name==OWNER and len(methods)==len(owner['method_ids']),'Original server Main method inventory differs')
    I=S.module('game_entry_original_code','verify-translation-ir.py');raw=I.Source(original)
    S.check(raw.name==OWNER and raw.access==owner['access'] and
        [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==owner['fields'],
        'Original server Main class/field inventory differs')
    def method(name,descriptor,access):
        matches=[(ident,m,r) for ident,m,r in zip(owner['method_ids'],methods,raw.methods)
            if (m['name'],m['descriptor'],m['access'])==(name,descriptor,access)]
        S.check(len(matches)==1 and matches[0][1]['code'] is not None,'Original server entry method Code is missing: '+name)
        ident,m,parsed=matches[0];body=raw.code(parsed)
        S.check(body['bytes']==m['code'][0] and (parsed['name'],parsed['descriptor'],parsed['access'])==(name,descriptor,access),
            'Independent original server Main Code parsers differ')
        calls=[];stores=[]
        for op in I.stream(body['bytes']):
            if op['opcode'] in (0xb6,0xb7,0xb8,0xb9):
                constant=op['operand']['Interface']['constant'] if op['opcode']==0xb9 else op['operand']['Constant']
                calls.append(dict(pc=op['pc'],opcode=op['opcode'],**raw.member(constant)))
            if op['opcode']==0xb3:stores.append(dict(pc=op['pc'],**raw.member(op['operand']['Constant'])))
        return dict(method=ident,symbol='boom_m'+str(ident),class_id=owner['id'],owner=OWNER,name=name,descriptor=descriptor,access=access,
            loader=origin['loader'],source_id=source,class_sha256=origin['sha256'],code_sha256=hashlib.sha256(body['bytes']).hexdigest(),
            code_bytes=len(body['bytes']),source_calls=calls,source_static_stores=stores,source_exception_handlers=body['handlers'])
    main=method('main','([Ljava/lang/String;)V',0x9);initializer=method('<clinit>','()V',0x8)
    logger_fields=[f for f in owner['fields'] if f['descriptor']=='Lorg/slf4j/Logger;' and f['access']&8]
    logger_stores=[s for s in initializer['source_static_stores'] if s['owner']==OWNER and
        s['descriptor']=='Lorg/slf4j/Logger;' and any(s['name']==f['name'] for f in logger_fields)]
    logger_calls=[c for c in initializer['source_calls'] if c['opcode']==0xb8 and c['descriptor'].endswith(')Lorg/slf4j/Logger;')]
    S.check(len(logger_fields)==len(logger_stores)==len(logger_calls)==1 and logger_calls[0]['pc']<logger_stores[0]['pc'],
        'Original Main logger initialization must remain an intact Java dependency')
    properties=summary.get('properties',{})
    S.check(properties.get('pool_abi')==2 and properties.get('units') and type(properties.get('array_type')) is int,
        'Game argv requires the original normal String/String[] properties ABI2 module')
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as index:
        types={r['id']:r for line in index.open('types.jsonl') if (r:=json.loads(line))}
    array=types.get(properties['array_type']);component=types.get(array['parent_component']) if array else None
    S.check(array and array['kind']==3 and array['name']=='[Ljava/lang/String;' and array['defining_loader']=='bootstrap' and
        component and component['kind']==1 and component['name']=='java/lang/String','Game argv source String[] type differs')
    kernel='native/runtime/java_properties.asm';expected=properties['kernel_sha256'][kernel]
    S.check(S.digest(S.ROOT/kernel)['sha256']==expected,'Game argv source String callback kernel changed')
    model=dict(schema=1,kind='original_dedicated_server_main',method=main['method'],symbol=main['symbol'],class_id=owner['id'],
        helper_symbol=HELPER,argument_rows_symbol=ARGUMENT_ROWS,additional_root_cells=1,
        root_position='after_five_primordial_and_optional_child_roots',
        owner=dict(class_id=owner['id'],name=owner['name'],access=owner['access'],origin=dict(origin)),
        main=main,initializer=initializer,source_archive=archive,argv=arguments_model(arguments,S),
        source_class_roots=[LOADER+':'+OWNER],source_method_roots=[main['method']],
        source_cli_entries=[LOADER+':'+OWNER+':main:([Ljava/lang/String;)V'],
        source_initializer_method_roots=[initializer['method']],source_initializer_dependencies=[dict(logger_calls[0])],
        required_base_modules=['runtime_metadata','properties'],properties_array_type=array['id'],properties_String_class=component['id'],
        properties_units=[dict(assembly=u['assembly'],object=u['object']) for u in properties['units']],
        required_runtime_exports=sorted(CALLBACKS),required_runtime_kernel_sha256={kernel:expected},
        original_logger_initializer_preserved=True,original_Java_Code_changed=False,ASM_writes_Java_fields=False,
        ASM_sets_VM_level=False,host_writes_Java_argv=False,report_bytes=REPORT_BYTES,report_abi=REPORT_ABI,
        report_fields=dict(REPORT_FIELDS),initial_VM_level=4,requires_completed_System_phase3=True,
        selected=False,help_is_full_game_startup=False,game_started=False,world_created=False)
    S.check(S.artifact(path)['digest']['sha256']==archive['digest']['sha256'],'Original server archive changed during entry binding')
    return model


def bind(closure,summary,owner,S,reader,arguments=('--help',)):
    model=contract(summary,owner,S,reader,arguments)
    for method in (model['main'],model['initializer']):
        selected=closure['selected_methods'].get(str(method['method']))
        S.check(selected and (selected['class_id'],selected['name'],selected['descriptor'],selected['code_sha256'],selected['source_sha256'])==
            (owner['id'],method['name'],method['descriptor'],method['code_sha256'],method['class_sha256']),
            'Original server Main and logger <clinit> must both be selected intact: '+method['name'])
    selected=[c for c in closure['selected_classes'] if c['class_id']==owner['id']]
    S.check(len(selected)==1 and selected[0]['source_sha256']==owner['origin']['sha256'],'Normal original Main class initializer descriptor must be selected')
    objects={str(Path(p).resolve()) for p in closure['objects']}
    S.check(all(str(Path(u['object']['path']).resolve()) in objects for u in model['properties_units']),
        'Actual normal properties COFF must be selected for argv callbacks')
    model['selected']=True;return model


def data(model):
    arguments=model['argv'];rows=arguments['rows']
    if arguments['argc']!=len(rows) or not 0<=len(rows)<=MAX_ARGUMENTS:raise ValueError('Game argv count differs from its bounded rows')
    total=0
    for index,row in enumerate(rows):
        encoded=row['text'].encode('utf-16-le','surrogatepass');units=[int.from_bytes(encoded[i:i+2],'little') for i in range(0,len(encoded),2)]
        if row['index']!=index or row['symbol']!='boom_game_argv_text_'+str(index) or row['units']!=len(units) or row['utf16']!=units or len(units)>MAX_ARGUMENT_UNITS:
            raise ValueError('Game argv UTF16 row/symbol differs from its explicit argument')
        total+=len(units)
    if total!=arguments['total_utf16_units'] or total>MAX_TOTAL_UNITS:raise ValueError('Game argv total UTF16 budget differs')
    out=['.const\nALIGN 8\nPUBLIC '+ARGUMENT_ROWS+'\n'+ARGUMENT_ROWS+' LABEL BYTE\n']
    if not rows:out.append(' QWORD 0\n DWORD 0,0\n')
    for row in rows:out.append(f' QWORD OFFSET {row["symbol"]}\n DWORD {row["units"]},0\n')
    for row in rows:
        out.append(f'ALIGN 2\n{row["symbol"]} LABEL WORD\n')
        if not row['utf16']:out.append(' WORD 0\n')
        for at in range(0,len(row['utf16']),16):out.append(' WORD '+','.join(f'0{v:04X}h' for v in row['utf16'][at:at+16])+'\n')
    return ''.join(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--batch',type=Path,required=True);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--argument',action='append');parser.add_argument('--selection',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('game_entry_original_inputs',root/'scripts/runtime-provider-source.py')
    S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S);R=S.module('game_entry_frame_Code_reader','verify-batch-frames.py')
    _,summary,classes=S.base(args.batch.resolve(),args.plan.resolve());owners=[c for c in classes if (c['name'],c['origin']['loader'])==(OWNER,LOADER)]
    S.check(len(owners)==1,'Original dedicated-server Main class missing/ambiguous');argv=args.argument if args.argument is not None else ['--help']
    model=bind(S.read(args.selection/'closure.json'),summary,owners[0],S,R,argv) if args.selection else contract(summary,owners[0],S,R,argv)
    output=args.output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated game-entry model output required');output.mkdir(parents=True)
    S.write(output/'model.json',model);(output/'argv.asm').write_text(data(model));print(output/'model.json')
