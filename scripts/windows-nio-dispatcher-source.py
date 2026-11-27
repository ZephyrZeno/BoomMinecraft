"""Locked WindowsNativeDispatcher.initIDs normal-source projection; no guest/V."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

sys.dont_write_bytecode=True
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
KERNEL=Path(__file__).resolve().parents[1]/'native/providers/windows_nio_dispatcher_ids.asm.inc'
OWNER='sun/nio/fs/WindowsNativeDispatcher'
POOL='boom_windows_nio_dispatcher_pool'
SERVICE='boom_windows_nio_dispatcher_init_ids'
PINNED={'WindowsNativeDispatcher.c':'d9c4e8b26dfeaee66474473d6f7f262d3cb111a3130ee27c4fcddacc43bb74fb',
    'WindowsNativeDispatcher.java':'a2a7b2618b01504eb5b8e5c6bc4a1c124fe610111300cc1296fe4dde77301897',
    'jni.cpp':'49f0d0c7507c23afa7c3cdf56a4c5ee0d5e5bd18e9e52fd98376d54ea52544b3'}


def check(value,message):
    if not value:raise ValueError(message)


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=sha))


def checked(row):
    actual=artifact(row['path']);expected=row.get('digest',row)
    check(actual['digest']=={k:expected[k] for k in ('size','sha256')},'Sealed source changed: '+row['path']);return Path(row['path'])


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def module(name):
    spec=importlib.util.spec_from_file_location('windows_nio_original_'+name,ROOT/'scripts'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def coff_records(path,wanted):
    """Actual public data symbols, their bytes and pointer relocation targets."""
    raw=Path(path).read_bytes();machine,count,_,symbols,number,optional,_=struct.unpack_from('<HHIIIHH',raw)
    check(machine==0x8664 and optional==0 and symbols+18*number+4<=len(raw),'Expected real AMD64 COFF')
    strings=symbols+18*number;size=struct.unpack_from('<I',raw,strings)[0]
    check(strings+size==len(raw),'Invalid actual COFF symbol strings')
    sections={}
    for i in range(1,count+1):
        at=20+(i-1)*40;name=raw[at:at+8].rstrip(b'\0').decode()
        _,_,n,data,reloc,_,nr,_,flags=struct.unpack_from('<IIIIIIHHI',raw,at+8)
        if flags&0x1000000:nr=struct.unpack_from('<I',raw,reloc)[0]-1;reloc+=10
        sections[i]=dict(name=name,size=n,data=data,reloc=reloc,nrel=nr)
    def sym(index):
        at=symbols+18*index;name=raw[at:at+8]
        if name[:4]==b'\0'*4:
            off=struct.unpack_from('<I',name,4)[0];end=raw.index(b'\0',strings+off);name=raw[strings+off:end]
        else:name=name.rstrip(b'\0')
        value,section,kind,storage,aux=struct.unpack_from('<IhHBB',raw,at+8)
        return name.decode(),dict(value=value,section_id=section,type=kind,storage=storage,aux=aux)
    found={};index=0
    while index<number:
        at=symbols+18*index;storage,aux=raw[at+16:at+18]
        if storage==2:
            name,row=sym(index)
            if name in wanted and row['section_id']>0:
                sec=sections[row['section_id']];begin=row['value'];length=wanted[name]
                check(begin+length<=sec['size'],'Source record escaped actual COFF data')
                found[name]=dict(symbol=row,section=sec['name'],bytes=raw[sec['data']+begin:sec['data']+begin+length].hex(),relocations=[])
        index+=aux+1
    by_section={}
    for name,row in found.items():by_section.setdefault(row['symbol']['section_id'],[]).append((name,row))
    for section,records in by_section.items():
        sec=sections[section]
        for i in range(sec['nrel']):
            at,target,kind=struct.unpack_from('<IIH',raw,sec['reloc']+i*10)
            for name,row in records:
                begin=row['symbol']['value'];length=wanted[name]
                if begin<=at<begin+length:
                    target_name,target_row=sym(target);target_section=sections.get(target_row['section_id'])
                    target_bytes=b'' if target_section is None else raw[target_section['data']+target_row['value']:
                        target_section['data']+min(target_row['value']+256,target_section['size'])]
                    row['relocations'].append(dict(offset=at-begin,type=kind,target=target_name,
                        target_symbol=target_row,target_data_first256=target_bytes.hex()))
    return found


def c_contract(pinned):
    sources={name:artifact(Path(pinned)/name) for name in PINNED}
    check(all(row['digest']['sha256']==PINNED[name] for name,row in sources.items()),'Official exact-tag source pin differs')
    text=Path(sources['WindowsNativeDispatcher.c']['path']).read_text()
    marker='Java_sun_nio_fs_WindowsNativeDispatcher_initIDs';begin=text.index(marker);start=text.index('{',begin);end=text.index('\n}',start)+2
    body=text[start+1:end-1];sequence=[];current=None
    tokens=re.finditer(r'clazz\s*=\s*\(\*env\)->FindClass\(env,\s*"([^"]+)"\);|'
        r'(\w+)\s*=\s*\(\*env\)->GetFieldID\(env,\s*clazz,\s*"([^"]+)",\s*"([^"]+)"\);',body)
    for match in tokens:
        if match.group(1):current=match.group(1);sequence.append(dict(kind='class',name=current))
        else:
            check(current is not None,'Field lookup precedes its class')
            sequence.append(dict(kind='field',owner=current,C_variable=match.group(2),name=match.group(3),descriptor=match.group(4)))
    residue=re.sub(r'\bCHECK_NULL\s*\(\w+\)\s*;|jclass\s+clazz\s*;','',body)
    residue=re.sub(r'clazz\s*=\s*\(\*env\)->FindClass\(env,\s*"[^"]+"\);|'
        r'\w+\s*=\s*\(\*env\)->GetFieldID\(env,\s*clazz,\s*"[^"]+",\s*"[^"]+"\);','',residue)
    check(not residue.strip() and sum(r['kind']=='class' for r in sequence)==7 and sum(r['kind']=='field' for r in sequence)==20,
        'Exact initIDs body changed or contains additional native/Win32 behavior')
    declared=re.findall(r'^static jfieldID (\w+);',text,re.M)
    check(set(declared)=={r['C_variable'] for r in sequence if r['kind']=='field'} and len(declared)==20,
        'C static FieldID inventory differs')
    jni=Path(sources['jni.cpp']['path']).read_text();check('k->initialize(CHECK_NULL);' in jni[jni.index('JNI_ENTRY(jfieldID, jni_GetFieldID'):],
        'JNI field lookup initialization obligation missing')
    return dict(sources=sources,sequence=sequence,initIDs_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        initIDs_source_lines=[text[:begin].count('\n')+1,text[:end].count('\n')+1],
        native_API_calls=['FindClass','GetFieldID'],Win32_API_calls=[],
        JNI_GetFieldID_initializes_class=True,JNI_FindClass_initialization_requested=True)


def bind(state_file,source_file,parent_file,pinned):
    I=module('verify-translation-ir');R=module('verify-batch-frames')
    state,closure,parent=map(read,(state_file,source_file,parent_file));source_seal=read(checked(parent['source_seal']))
    check(artifact(state_file)==parent['input_state'] and artifact(source_file)==source_seal['source_manifest'] and
        source_seal['input_state']==parent['input_state'],
        'Exact current Main source/state required')
    for name,sha in state['tool_sources'].items():check(artifact(ROOT/name)['digest']['sha256']==sha,'Current source epoch changed: '+name)
    summary_file=Path(closure['batch'])/'summary.json';summary=read(summary_file);plan=Path(closure['plan'])
    inputs=[artifact(p) for p in (state_file,source_file,parent_file,summary_file,plan/'classes.jsonl',__file__,I.__file__,R.__file__)]
    inputs += [parent['source_seal'],source_seal['source_full_verification'],summary['unsafe_fields']['index'],
        summary['runtime_metadata']['index'],summary['layouts'],summary['frames']['original_system_catalog']]
    contract=c_contract(pinned);inputs+=list(contract['sources'].values())
    names={OWNER}|{row['name'] for row in contract['sequence'] if row['kind']=='class'}
    classes={}
    for line in (plan/'classes.jsonl').open(encoding='utf-8'):
        row=json.loads(line)
        if row['name'] in names and row['origin']['loader']=='bootstrap':classes[row['name']]=row
    check(set(classes)==names,'Exact bootstrap classes unavailable')
    ids={c['id'] for c in classes.values()};layouts={}
    for line in checked(summary['layouts']).open(encoding='utf-8'):
        row=json.loads(line)
        if row['class_id'] in ids:layouts[row['class_id']]=row
    selected={row['class_id']:row for row in closure['selected_classes']}
    catalog=checked(summary['frames']['original_system_catalog']);image=catalog.parent/'image';original={};native=None;clinit=None
    for name,cls in classes.items():
        path=(image/cls['origin']['jar_entry']).resolve();check(path.is_relative_to(image.resolve()),'Original class escaped image')
        item=artifact(path);check(item['digest']['sha256']==cls['origin']['sha256'] and cls['id'] in selected and
            selected[cls['id']]['source_sha256']==cls['origin']['sha256'],'Original normal selected class differs')
        raw=path.read_bytes();src=I.Source(raw);_,annotations=R.original_methods(raw)
        check(int.from_bytes(raw[6:8],'big')==65 and cls['origin']['source_id']=='jdk:java.base' and
            not cls['origin'].get('generated'),'Original locked bootstrap JDK21 source required')
        check(src.name==name and len(src.methods)==len(cls['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in src.fields]==cls['fields'], 'Classfile source inventory differs')
        methods=[]
        for ident,method,annotation in zip(cls['method_ids'],src.methods,annotations):
            code=src.code(method);record=dict(method=ident,class_id=cls['id'],owner=name,name=method['name'],descriptor=method['descriptor'],
                access=method['access'],class_sha256=item['digest']['sha256'],loader='bootstrap',source_id='jdk:java.base',
                code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None,
                frame_flags=R.flags(name,annotation,code is None,False,False))
            if code:record['selected']=closure['selected_methods'].get(str(ident),{}).get('code_sha256')==record['code_sha256']
            if name==OWNER and method['name']=='initIDs':native=record
            if name==OWNER and method['name']=='<clinit>':clinit=dict(record,original_Code_hex=code['bytes'].hex())
            methods.append(record)
        check(name==OWNER or selected[cls['id']]['initializer'] is None,'Nested initialization requires additional original Code')
        original[name]=dict(class_record=cls,normal_layout=layouts[cls['id']],source= item,methods=methods,
            selected_normal_class=selected[cls['id']],class_symbol='boom_class'+str(cls['id']),layout_symbol='boom_layout'+str(cls['id']))
        inputs.append(item)
    check(native and native['access']==0x10a and native['descriptor']=='()V' and native['code_sha256'] is None and
        native['frame_flags']==32 and clinit['selected'],'Exact private static native/init source required')
    fields={};maps={}
    with zipfile.ZipFile(checked(summary['unsafe_fields']['index'])) as z:
        for line in z.open('fields.jsonl'):
            row=json.loads(line)
            if row['class_id'] in ids:fields[row['class_id'],row['name'],row['descriptor']]=row
    with zipfile.ZipFile(checked(summary['runtime_metadata']['index'])) as z:
        for line in z.open('fields.jsonl'):
            row=json.loads(line)
            if row['declaring_class'] in ids:maps[row['id']]=row
    groups=[];records=[]
    for row in contract['sequence']:
        if row['kind']=='class':
            cls=original[row['name']];groups.append(dict(name=row['name'],class_id=cls['class_record']['id'],
                first_field=len(records),field_count=0,class_symbol=cls['class_symbol'],layout_symbol=cls['layout_symbol'],
                payload_bytes=cls['normal_layout']['candidate']['payload_bytes'],reference_prefix=cls['normal_layout']['candidate']['reference_prefix'],
                declared_field_count=len(cls['class_record']['fields'])))
        else:
            group=groups[-1];field=fields[group['class_id'],row['name'],row['descriptor']];fmap=maps[field['id']]
            layout=original[row['owner']]['normal_layout']['candidate'];[physical]=[f for f in layout['fields'] if
                f['member']['owner']==field['class_id'] and f['member']['index']==field['field_index']]
            check(field['access']==2 and field['address_map']==field['id'] and fmap['storage_bytes']==field['storage_bytes']==physical['storage_bytes'] and
                fmap['reference']==field['reference']==physical['reference'] and
                dict(receiver_class=field['class_id'],offset=physical['offset']) in fmap['rows'], 'Normal FieldID/FMAPPROC/layout differs')
            records.append(dict(row,**{'class_id':field['class_id'],'field':field,'FMAP':fmap,'offset':physical['offset'],
                'symbol':'boom_field_map'+str(field['id']),'record_symbol':'boom_batch_field_record'+str(field['id']),
                'layout_symbol':group['layout_symbol']}));group['field_count']+=1
    frame=read(checked(closure['runtime_frame_overlay']['reference']['manifest']));frame_obj=checked(frame['object']);inputs += [
        closure['runtime_frame_overlay']['reference']['manifest'],closure['runtime_frame_overlay']['reference']['verification'],frame['object']]
    targets={'boom_trace_method'+str(native['method']):32}|{v['class_symbol']:16 for v in original.values()}|{
        v['layout_symbol']:24 for v in original.values()}|{r['symbol']:19 for r in records}|{r['record_symbol']:32 for r in records}
    objects=[parent['objects'][0],frame['object']]+[r['object'] for r in summary['runtime_metadata']['units']]
    physical={}
    for obj in objects:
        check(any(r['path']==obj['path'] and artifact(r['path'])['digest']==artifact(obj['path'])['digest']
            for r in parent['objects']),'Required source data object not linked into exact parent')
        checked(obj);inputs.append(obj)
        for name,value in coff_records(obj['path'],targets).items():
            check(name not in physical,'Duplicate actual normal record: '+name);physical[name]=dict(value,object=obj)
    check(set(physical)==set(targets),'Actual Class/layout/FMAPPROC/Frame data missing from parent')
    trace=bytes.fromhex(physical['boom_trace_method'+str(native['method'])]['bytes'])
    check(struct.unpack_from('<II',trace)==(native['method'],32) and struct.unpack_from('<I',trace,20)[0]==native['class_id'],
        'Actual normal native Frame descriptor differs')
    trace_reloc=physical['boom_trace_method'+str(native['method'])]['relocations']
    check([(r['offset'],r['type'],r['target']) for r in trace_reloc]==[(8,1,'boom_t'+str(native['class_id']))],
        'Actual native Frame type identity relocation differs')
    for name,item in original.items():
        desc=bytes.fromhex(physical[item['class_symbol']]['bytes']);layout=bytes.fromhex(physical[item['layout_symbol']]['bytes']);shape=item['normal_layout']['candidate']
        check(struct.unpack_from('<II',desc)==(0x434c4153,2) and struct.unpack_from('<IIQII',layout)==
            (0x4f424a43,2,shape['payload_bytes'],shape['reference_prefix'],len(shape['fields'])),'Actual normal Class/layout bytes differ')
    for record in records:
        f=record['field'];value=physical[record['record_symbol']];raw=bytes.fromhex(value['bytes'])
        check(struct.unpack_from('<IIIIII',raw)==(0x464d4150,1,len(record['FMAP']['rows']),f['storage_bytes'],int(f['reference']),0),
            'Actual source FMAP header differs')
        [reloc]=value['relocations'];check(reloc['offset']==24 and reloc['type']==1,'Actual FMAP pointer relocation differs')
        check(reloc['target_symbol']['section_id']==value['symbol']['section_id'] and
            reloc['target_symbol']['value']==value['symbol']['value']+32,'Normal FMAP inline row range differs')
        rows_raw=bytes.fromhex(reloc['target_data_first256']);check([dict(receiver_class=a,offset=b) for a,b in
            struct.iter_unpack('<II',rows_raw[:8*len(record['FMAP']['rows'])])]==record['FMAP']['rows'],'Actual FMAP receiver offsets differ')
        function=physical[record['symbol']]
        check(function['section'] in ('.text','.text$mn') and function['bytes']=='4c8d05000000004c8d0d00000000e900000000' and
            [(r['offset'],r['type'],r['target']) for r in function['relocations']]==[
            (3,4,record['record_symbol']),(10,4,'boom_runtime_type_map'),(15,4,'boom_field_address')],
            'Actual normal source field address PROC differs')
    for row in inputs:checked(row)
    return dict(schema=1,scope='normal_original_server_Main_WindowsNativeDispatcher_initIDs_source_layout_Frame_projection_only',
        input_state=artifact(state_file),source_selection=artifact(source_file),source_full_verification=source_seal['source_full_verification'],
        parent_overlay=artifact(parent_file),runtime=parent['runtime'],official_C=contract,owner=classes[OWNER]['id'],
        methods=[native],original_clinit=clinit,source_classes=original,groups=groups,fields=records,actual_source_records=physical,
        UFMP_summary={k:summary['unsafe_fields'][k] for k in ('abi','type_capacity','declared_fields','pages','name_units')},
        source_helpers={n:artifact(ROOT/'scripts'/(n+'.py')) for n in ('verify-translation-ir','verify-batch-frames')},
        tool_sources=state['tool_sources'],
        required_classes=sorted(ids),required_java_methods=[],required_base_modules=['runtime_metadata','unsafe_fields','frames'],
        no_new_Java_Code_or_classes_required=True,class_initialization_by_normal_ensure32_required=True,
        proposed_pool=dict(magic='WNID',abi=1,bytes=224,classes=7,fields=20,registration_cells=20,
            private_FieldID_representation='exact normal source field-address PROC pointer; source FieldID and FMAP data record retained in immutable records',
            cache_contains_Java_oops=False,ready_only_after_all20=True),
        inputs=inputs,SourceV_repeated=False,guest_or_Main_executed=False,registered=False,runtime_acceptance_complete=False)


def normal_frames(meta):
    R=module('verify-batch-frames');row=meta['methods'][0]
    imports={'boom_class_ensure32','boom_trace_enter','boom_trace_leave',SERVICE}
    data={POOL,'boom_trace_pool','boom_class'+str(meta['owner']),'boom_trace_method'+str(row['method'])}
    text='option casemap:none\n'+''.join('EXTERN '+n+(':PROC\n' if n in imports else ':BYTE\n') for n in sorted(imports|data))
    exports={'boom_m'+str(row['method']),'boom_m'+str(row['method'])+'_native'}
    text+=''.join('PUBLIC '+n+'\n' for n in sorted(exports))+R.native_adapter(row['method'],meta['owner'],POOL,SERVICE,0)+'\nEND\n'
    return text,exports,imports|data


def registry(meta):
    groups,fields=meta['groups'],meta['fields'];ufmp=meta['UFMP_summary']
    check(len(groups)==7 and len(fields)==20 and ufmp['abi']==2,'Exact locked initIDs registration domain required')
    template=KERNEL
    procs={'boom_class_ensure32'}|{r['symbol'] for r in fields}
    data={'boom_java_unsafe_field_pool','boom_java_unsafe_field_names','boom_java_unsafe_field_pages'}|{
        'boom_java_unsafe_field_page'+str(r['field']['id']>>10) for r in fields}|{r['record_symbol'] for r in fields}|{
        r[k] for r in groups for k in ('class_symbol','layout_symbol')}
    text='option casemap:none\n'+''.join('EXTERN '+n+(':PROC\n' if n in procs else ':BYTE\n') for n in sorted(procs|data))
    constants=dict(WNID_CLASS_COUNT=len(groups),WNID_FIELD_COUNT=len(fields),WNID_POOL_BYTES=64+len(fields)*8,
        WNID_UFMP_ABI=ufmp['abi'],WNID_UFMP_TYPES=ufmp['type_capacity'],WNID_UFMP_FIELDS=ufmp['declared_fields'],
        WNID_UFMP_PAGES=ufmp['pages'],WNID_UFMP_NAME_UNITS=ufmp['name_units'])
    text+=''.join(name+' EQU '+str(value)+'\n' for name,value in constants.items())+'.const\nALIGN 8\nwnid_groups LABEL BYTE\n'
    for group in groups:
        text+=f" QWORD OFFSET {group['class_symbol']},OFFSET {group['layout_symbol']}\n DWORD {group['first_field']},{group['field_count']}\n QWORD {group['payload_bytes']}\n DWORD {group['reference_prefix']},{group['declared_field_count']}\n"
    text+='ALIGN 8\nwnid_fields LABEL BYTE\n'
    for i,row in enumerate(fields):
        f=row['field'];units=len(row['name'].encode('utf-16le'))//2
        text+=f" DWORD {f['class_id']},{f['field_index']},{f['id']},{f['kind']},{f['storage_bytes']},{int(f['reference'])},{row['offset']},{units}\n"
        text+=f" QWORD OFFSET {row['symbol']},OFFSET {row['record_symbol']},OFFSET wnid_name{i},OFFSET wnid_rows{i}\n"
        text+=f" DWORD {len(row['FMAP']['rows'])},0\n QWORD OFFSET boom_java_unsafe_field_page{f['id']>>10}\n"
    for i,row in enumerate(fields):
        raw=row['name'].encode('utf-16le');units=[int.from_bytes(raw[k:k+2],'little') for k in range(0,len(raw),2)]
        text+=f"ALIGN 2\nwnid_name{i} WORD "+','.join(map(str,units+[0]))+'\nALIGN 8\n'+f'wnid_rows{i} LABEL DWORD\n'
        text+=''.join(f" DWORD {r['receiver_class']},{r['offset']}\n" for r in row['FMAP']['rows'])
    text+='.data\nALIGN 8\nPUBLIC '+POOL+'\n'+POOL+' DWORD 044494E57h,1,WNID_POOL_BYTES,0\n'
    text+=' DWORD WNID_CLASS_COUNT,WNID_FIELD_COUNT,0,0\n QWORD OFFSET wnid_fields,OFFSET wnid_groups,OFFSET boom_java_unsafe_field_pool,0\n'
    text+=' QWORD WNID_FIELD_COUNT DUP(0)\n'+template.read_text()+'\nEND\n'
    return text,{POOL,SERVICE},procs|data
