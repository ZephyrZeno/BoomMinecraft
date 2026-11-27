"""Strict native source contracts, complete COFF and readonly source data."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from uuid import uuid4


NATIVE_KEYS=('method','class_id','class_sha256','loader','owner','source_id','name','descriptor','access','operation')


def check(value,message):
    if not value:raise ValueError(message)


def methods(meta):
    result=[]
    for row in meta['methods']:
        check(set(row) in (set(NATIVE_KEYS),set(NATIVE_KEYS)|{'code_sha256'}) and
              ('code_sha256' not in row or row['code_sha256'] is None) and
              type(row['method']) is int and row['method']>=0 and row['access']&0x100 and not row['access']&0x400,
              'Native projection contains Java Code or unknown contract fields')
        result.append({key:row[key] for key in NATIVE_KEYS})
    check(result and len({r['method'] for r in result})==len(result),'Empty or duplicate native declarations')
    return result


def owners(meta,classes,rule):
    rows=methods(meta);source=[]
    expected=[(r.get('owner',rule['owner']),rule['loader'],rule['source_id'],r['name'],r['descriptor'],r['access'],r['operation'])
              for r in rule['methods']]
    actual=[tuple(r[k] for k in ('owner','loader','source_id','name','descriptor','access','operation')) for r in rows]
    check(actual==expected,'Registry declarations/operations or secondary owner boundary differ')
    for ident in sorted({r['class_id'] for r in rows}):
        check(0<=ident<len(classes) and classes[ident]['id']==ident,'Native owner outside source catalogue')
        cls=classes[ident];check(not cls['origin'].get('generated'),'Fabricated native owner')
        for row in rows:
            if row['class_id']!=ident:continue
            check((cls['name'],cls['origin']['sha256'],cls['origin']['loader'],cls['origin']['source_id'])==
                  (row['owner'],row['class_sha256'],row['loader'],row['source_id']),'Native class identity differs')
        source.append(cls)
    primary=[c for c in source if c['name']==rule['owner'] and c['origin']['loader']==rule['loader'] and
             c['origin']['source_id']==rule['source_id']]
    check(len(primary)==1 and ('owner' not in meta or meta['owner']==primary[0]['id']),
          'Registry primary owner or optional model owner differs')
    return primary[0],source


def dependencies(meta,rule):
    java=meta.get('required_java_methods',[]);contracts=meta.get('required_source_contracts',[])
    check(isinstance(java,list) and all(type(i) is int and i>=0 for i in java) and len(java)==len(set(java)),
          'Required Java callbacks must be unique original method IDs')
    check(isinstance(contracts,list) and all(isinstance(s,str) and s.startswith('boom_') for s in contracts) and
          len(contracts)==len(set(contracts)),'Required source contracts differ')
    families=list(meta.get('required_provider_families',[]))
    check(len(families)==len(set(families)),'Duplicate model provider dependency')
    for name in rule.get('required_provider_families',[]):
        if name not in families:families.append(name)
    check(all(isinstance(name,str) and name for name in families),'Invalid required provider family')
    check(type(rule.get('native_java_upcalls')) is bool,'Framed registry must explicitly declare Java upcalls')
    return dict(required_java_methods=java,required_provider_families=families,required_source_contracts=contracts,
                native_java_upcalls=rule['native_java_upcalls'])


def service_assembly(C,meta,R,kernel):
    procs,data=C.native_imports(meta);procs=set(procs);data=set(data)|{f"boom_class{m['class_id']}" for m in methods(meta)}
    check(not procs&data,'Incompatible PROC/data import types')
    text='option casemap:none\n'+''.join(f"EXTERN {name}:{'PROC' if name in procs else 'BYTE'}\n" for name in sorted(procs|data))
    text+=C.data(meta);exports=set(C.CONTROL)|{C.POOL,C.SERVICE}
    for row in methods(meta):
        ident=row['method'];text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,row['class_id'],C.POOL,C.SERVICE,row['operation']).removeprefix('.code\n')
        exports.update((f'boom_m{ident}',f'boom_m{ident}_native'))
    return text+Path(kernel).read_text(encoding='utf-8')+'\nEND\n',exports,procs|data


def object_records(manifest):
    records=[manifest['object']];extra=manifest.get('additional_objects',[])
    check(isinstance(extra,list),'Invalid additional provider objects')
    check(not extra or manifest.get('family')=='normal-constant-pool-v1',
          'Only the independently source-verified CP family may contribute readonly extra COFF')
    for row in extra:
        check(set(row)=={'role','object','exports','source_payload_sha256','read_only_source_metadata'} and
              row['role']=='source_constant_pool_ROM' and row['read_only_source_metadata'] is True,
              'Unknown or executable additional provider object')
        records.append(row['object'])
    check(len({str(Path(r['path']).resolve()).casefold() for r in records})==len(records),'Duplicate provider COFF')
    if 'ROM_object' in manifest:
        check(len(extra)==1 and manifest['ROM_object']==extra[0]['object'],'CP ROM alias differs')
    check(not extra or 'ROM_object' in manifest,'CP extra object omitted ROM_object')
    return records


def verify_readonly(path,expected,exports):
    raw=Path(path).read_bytes();check(raw==expected,'Readonly COFF differs from rebuilt original source bytes')
    check(len(raw)>=64,'Truncated readonly COFF')
    machine,count,stamp,table,symbols,optional,flags=struct.unpack_from('<HHIIIHH',raw)
    check((machine,count,stamp,optional,flags)==(0x8664,1,0,0,0) and table+symbols*18+4<=len(raw),'Invalid readonly COFF')
    name,vs,va,size,data,reloc,line,nrel,nline,section=struct.unpack_from('<8sIIIIIIHHI',raw,20)
    check(name.rstrip(b'\0')==b'.rdata' and vs==va==reloc==line==nrel==nline==0 and section==0x40500040 and
          data==64 and data+size<=table,'Additional object contains code, writable data or relocations')
    strings=table+symbols*18;length=struct.unpack_from('<I',raw,strings)[0]
    check(strings+length==len(raw),'Readonly string table differs');defined=set();at=0
    while at<symbols:
        label,value,number,kind,storage,aux=struct.unpack_from('<8sIhHBB',raw,table+at*18)
        if label[:4]==b'\0'*4:
            offset=struct.unpack_from('<I',label,4)[0];check(4<=offset<length,'Invalid readonly symbol name')
            end=raw.find(b'\0',strings+offset,strings+length);check(end>=0,'Unterminated readonly symbol');label=raw[strings+offset:end]
        else:label=label.rstrip(b'\0')
        check(number==1 and value<=size and kind==0 and at+aux<symbols,'Additional object contains imports or unknown symbols')
        if storage==2:check(not aux,'Readonly exported symbol has auxiliary data');defined.add(label.decode('ascii'))
        else:check(storage==3 and label==b'.rdata' and aux==1,'Unexpected private readonly symbol')
        at+=aux+1
    check(defined==set(exports),'Readonly actual exports differ')
    return dict(readonly=True,code_sections=False,relocations=0,imports=[],exports=sorted(defined),
                payload_bytes=size,payload_sha256=hashlib.sha256(raw[data:data+size]).hexdigest())


def prepare_additional(C,meta,summary,classes,output,S):
    if 'ROM' not in meta:return [],None
    rebuilt,payload=C.build_rom(summary,classes,S);check(rebuilt==meta['ROM'],'ROM metadata changed during prepare')
    path=Path(output)/'constant-pool-ROM.obj';raw=C.rom_coff(payload,rebuilt);path.write_bytes(raw)
    proof=verify_readonly(path,raw,C.ROM_EXPORTS)
    record=dict(role='source_constant_pool_ROM',object=S.artifact(path),exports=sorted(C.ROM_EXPORTS),
                source_payload_sha256=rebuilt['readonly_section_sha256'],read_only_source_metadata=True)
    return [record],proof


def verify_additional(manifest,C,meta,summary,classes,S):
    extra=manifest.get('additional_objects',[])
    if 'ROM' not in meta:
        check(not extra and 'ROM_object' not in manifest,'Family without ROM declared extra COFF');return []
    check(len(extra)==1 and manifest.get('ROM_object')==extra[0]['object'],'Readonly ROM omitted, duplicated or substituted')
    object_records(manifest);row=extra[0];path=S.checked(row['object'])
    check(path.parent==Path(manifest['object']['path']).parent,'Readonly metadata escaped provider directory')
    rebuilt,payload=C.build_rom(summary,classes,S);check(rebuilt==meta['ROM'],'Readonly original source model changed')
    check(row['exports']==sorted(C.ROM_EXPORTS) and row['source_payload_sha256']==rebuilt['readonly_section_sha256'],
          'Readonly declaration differs from source')
    proof=verify_readonly(path,C.rom_coff(payload,rebuilt),C.ROM_EXPORTS)
    return [dict(object=row['object'],**proof)]


def normalized_coff(path):
    """Seal execution bytes, flags, full symbols and normalized relocation targets.

    This reader streams private metadata symbols instead of retaining millions
    of Python dictionaries for the original method table. Only assembler file
    names/debug sections and physical table offsets/timestamp are excluded.
    """
    raw=Path(path).read_bytes();check(len(raw)>=20,'Truncated methods COFF')
    machine,count,_,symbol_at,symbol_count,optional,characteristics=struct.unpack_from('<HHIIIHH',raw)
    check(machine==0x8664 and count>0 and optional==0 and 20+count*40<=symbol_at and
        symbol_at+18*symbol_count+4<=len(raw),'Invalid AMD64 methods COFF header')
    strings=symbol_at+18*symbol_count;string_size=struct.unpack_from('<I',raw,strings)[0]
    check(string_size>=4 and strings+string_size==len(raw),'Invalid methods COFF string table')
    sections={};by_id={};allowed={'.text','.text$mn','.data','.bss','.rdata','.pdata','.xdata','.debug$S'}
    for ident in range(1,count+1):
        at=20+(ident-1)*40;name=raw[at:at+8].rstrip(b'\0').decode('ascii')
        virtual_size,virtual_address,size,data,reloc,line,nrel,nline,flags=struct.unpack_from('<IIIIIIHHI',raw,at+8)
        check(name in allowed and name not in sections and virtual_size==virtual_address==line==nline==0,
            'Unexpected methods COFF section/line metadata')
        check((name=='.bss' and data==0) or (size==0 and data==0) or 20+count*40<=data and data+size<=symbol_at,
            'Methods COFF section bytes escape their range')
        if flags&0x01000000:
            check(nrel==65535 and reloc+10<=symbol_at,'Invalid methods relocation overflow')
            total,si,kind=struct.unpack_from('<IIH',raw,reloc)
            check(total>65535 and si==kind==0,'Invalid methods relocation sentinel');nrel=total-1;reloc+=10
        check(not nrel or 20+count*40<=reloc and reloc+10*nrel<=symbol_at,'Invalid methods relocation range')
        row=dict(name=name,size=size,data=data,reloc=reloc,nrel=nrel,flags=flags&~0x01000000)
        sections[name]=row;by_id[ident]=row
    primaries=bytearray(symbol_count);symbol_hash=hashlib.sha256();defined_symbols=0
    def symbol(index):
        check(index<symbol_count,'COFF relocation target is outside the actual symbol table')
        at=symbol_at+18*index;name=raw[at:at+8]
        if name[:4]==b'\0'*4:
            offset=struct.unpack_from('<I',name,4)[0];check(4<=offset<string_size,'Invalid methods COFF name offset')
            end=raw.find(b'\0',strings+offset,strings+string_size);check(end>=0,'Unterminated methods COFF name')
            name=raw[strings+offset:end]
        else:name=name.rstrip(b'\0')
        value,section,kind,storage,aux=struct.unpack_from('<IhHBB',raw,at+8)
        check(section<=count and index+aux<symbol_count,'Invalid methods COFF symbol record')
        return (name.decode('ascii'),value,by_id[section]['name'] if section>0 else section,kind,storage),aux
    index=0
    while index<symbol_count:
        row,aux=symbol(index);primaries[index]=1
        if row[4]!=103 and row[2]!='.debug$S':
            aux_bytes=raw[symbol_at+(index+1)*18:symbol_at+(index+1+aux)*18]
            symbol_hash.update(json.dumps((row,aux_bytes.hex()),separators=(',',':')).encode()+b'\n');defined_symbols+=1
        index+=aux+1
    result={}
    widths={1:8,2:4,3:4,4:4,5:4,6:4,7:4,8:4,9:4,10:2,11:4}
    for name,section in sections.items():
        if name=='.debug$S':continue
        data=raw[section['data']:section['data']+section['size']] if name!='.bss' else b''
        digest=hashlib.sha256();previous=-1
        for i in range(section['nrel']):
            offset,index,kind=struct.unpack_from('<IIH',raw,section['reloc']+10*i)
            check(index<symbol_count and primaries[index] and kind in widths and previous<=offset and
                offset+widths[kind]<=len(data),'Invalid/overlapping methods COFF relocation')
            row,_=symbol(index);check(row[4]!=103 and row[2]!='.debug$S','Execution relocation targets a filename/debug symbol')
            addend=data[offset:offset+widths[kind]].hex()
            digest.update(json.dumps((offset,kind,addend,row),separators=(',',':')).encode()+b'\n');previous=offset+widths[kind]
        result[name]=dict(size=section['size'],flags=section['flags'],raw_sha256=hashlib.sha256(data).hexdigest(),
                          relocations=section['nrel'],normalized_relocations_sha256=digest.hexdigest())
    check('.pdata' in result and '.xdata' in result and result['.pdata']['size']%12==0 and
        result['.pdata']['relocations']==result['.pdata']['size']//4,'Missing/incomplete methods native x64 unwind table')
    return dict(machine=machine,characteristics=characteristics,sections=result,
        nondebug_primary_symbols=defined_symbols,nondebug_symbols_sha256=symbol_hash.hexdigest())



def machine_contract(text,obj,assembler,S):
    output=S.ART/'runtime-provider-machine-checks'/uuid4().hex;output.mkdir(parents=True)
    asm,canonical=output/'canonical.asm',output/'canonical.obj';asm.write_text(text,encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('xb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(canonical),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    actual,expected=normalized_coff(obj),normalized_coff(canonical)
    check(actual==expected,'Native code/data/flags/symbol auxiliary/relocations/unwind differ from canonical assembly')
    digest=hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    S.write(output/'verification.json',dict(verified=True,scope='independent_complete_nondebug_native_provider_COFF',
        object=S.artifact(obj),canonical_assembly=S.artifact(asm),canonical_object=S.artifact(canonical),assembler=S.artifact(assembler),
        normalized=actual,normalized_sha256=digest))
    return dict(all_nondebug_sections_symbols_auxiliary_relocations_unwind_verified=True,normalized_sha256=digest)
