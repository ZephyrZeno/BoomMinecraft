"""Prove native oop arrays in actual COFF and project only selected providers.

Build/verification helper only. The caller must already have independently
verified each provider source model; this does not replace that verification.
No Python function here reads a live game heap or performs game collection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'
MAX_CELLS=1048576
SYMBOL=re.compile(r'boom_[A-Za-z0-9_]+\Z')
STANDARD_SOURCE_SPANS=[('boom_probe_static_roots','boom_probe_static_root_count'),
    ('boom_java_string_literal_roots','boom_java_string_literal_root_count'),
    ('boom_java_class_roots','boom_java_class_root_count'),('boom_java_class_name_roots','boom_java_class_name_root_count'),
    ('boom_java_properties_roots','boom_java_properties_root_count'),
    ('boom_java_string_intern_root','boom_java_string_intern_root_count'),
    ('boom_provider_access_domain_roots','boom_provider_access_domain_root_count'),
    ('boom_provider_signal_roots','boom_provider_signal_root_count'),('boom_provider_threads_roots','boom_provider_threads_root_count')]
PRIMORDIAL_SPAN=('boom_vm_thread_root_cells','boom_vm_thread_root_count')


def check(value,message):
    if not value:raise ValueError(message)


def artifact(path):
    path=Path(path).resolve();raw=path.read_bytes()
    return dict(path=str(path),digest=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))


def checked(record):
    path=Path(record['path']).resolve();check(path.is_relative_to(ART),'Native root artifact escaped project .boom')
    actual=artifact(path);check(all(record['digest'].get(k)==v for k,v in actual['digest'].items()),'Native root artifact changed: '+str(path))
    return path


def declarations(value):
    check(isinstance(value,list) and len(value)<=4096,'Invalid native root declarations')
    result=[];symbols=set()
    for row in value:
        check(isinstance(row,dict) and set(row)=={'symbol','count','kind'} and
            isinstance(row['symbol'],str) and SYMBOL.fullmatch(row['symbol']) and row['symbol'] not in symbols and
            type(row['count']) is int and 0<row['count']<=MAX_CELLS and
            isinstance(row['kind'],str) and row['kind'] and len(row['kind'])<=256,'Invalid or duplicate native oop root span')
        symbols.add(row['symbol']);result.append(dict(row))
    return result


def coff(path):
    """Read ordinary AMD64 COFF, including private labels and relocations."""
    raw=Path(path).read_bytes();check(len(raw)>=20,'Truncated native root COFF header')
    machine,count,_,symbols_at,symbol_count,optional,_=struct.unpack_from('<HHIIIHH',raw)
    check(machine==0x8664 and 0<count<=4096 and optional==0 and
        20+40*count<=symbols_at and symbols_at+18*symbol_count+4<=len(raw),'Invalid AMD64 native root COFF')
    strings=symbols_at+18*symbol_count;size=struct.unpack_from('<I',raw,strings)[0]
    check(size>=4 and strings+size<=len(raw),'Invalid native root COFF string table')
    def long_name(offset):
        check(4<=offset<size,'Invalid native root long symbol name')
        end=raw.find(b'\0',strings+offset,strings+size);check(end>=strings+offset,'Unterminated native root COFF name')
        return raw[strings+offset:end].decode('ascii')
    sections={}
    for index in range(1,count+1):
        row=struct.unpack_from('<8sIIIIIIHHI',raw,20+40*(index-1))
        name=row[0].rstrip(b'\0').decode('ascii');name=long_name(int(name[1:])) if name.startswith('/') else name
        _,_,_,length,position,relocation,_,relocation_count,_,flags=row
        check(not flags&0x01000000,'Extended COFF relocation counts are unsupported for native roots')
        check((not position or 20+40*count<=position and position+length<=symbols_at) and
            (not relocation_count or 20+40*count<=relocation and relocation+10*relocation_count<=symbols_at),
            'Native root section or relocations leave COFF bounds')
        relocations=[]
        widths={0:0,1:8,2:4,3:4,4:4,5:4,6:4,7:4,8:4,9:4,10:2,11:4,12:1,13:4,14:4,15:4,16:4}
        for i in range(relocation_count):
            offset,entry,kind=struct.unpack_from('<IIH',raw,relocation+10*i)
            check(entry<symbol_count and kind in widths and offset+widths[kind]<=length,'Invalid native root COFF relocation')
            relocations.append((offset,widths[kind],kind))
        sections[index]=dict(name=name,size=length,position=position,flags=flags,relocations=relocations)
    symbols=[];index=0
    while index<symbol_count:
        name,value,section,kind,storage,aux=struct.unpack_from('<8sIhHBB',raw,symbols_at+18*index)
        name=long_name(struct.unpack_from('<I',name,4)[0]) if name[:4]==b'\0'*4 else name.rstrip(b'\0').decode('ascii')
        check(section<=count and index+aux<symbol_count,'Invalid native root COFF symbol')
        symbols.append(dict(name=name,value=value,section=section,type=kind,storage=storage,auxiliary=aux))
        index+=1+aux
    return raw,sections,symbols


def verify_object(path,spans,*,assembly):
    """Prove exact zero-initialized QWORD arrays, never a read-only metadata bank."""
    spans=declarations(spans);raw,sections,symbols=coff(path);text=Path(assembly).read_text(encoding='utf-8-sig')
    result=[];ranges=[]
    for row in spans:
        name=row['symbol'];found=[r for r in symbols if r['name']==name]
        check(len(found)==1,'Missing or duplicate actual native root COFF symbol: '+name)
        symbol=found[0];section=sections.get(symbol['section'])
        check(section is not None and symbol['storage']==2 and symbol['type']==0 and symbol['auxiliary']==0,
            'Native root must be an actual PUBLIC data symbol: '+name)
        start=symbol['value'];length=row['count']*8;end=start+length;flags=section['flags']
        check(flags&0x80000000 and flags&0x40000000 and not flags&(0x20000000|0x20|0x800|0x1000) and
            bool(flags&0x40)^bool(flags&0x80),'Native root is read-only, executable, COMDAT or non-data metadata: '+name)
        check(((flags>>20)&15)>=4 and start%8==0 and end<=section['size'],'Native root alignment or complete physical span differs: '+name)
        initializer=r'(0)' if flags&0x40 else r'(\?)'
        declaration=re.compile(r'(?m)^\s*'+re.escape(name)+r'\s+QWORD\s+'+str(row['count'])+r'\s+DUP\s*\(\s*'+initializer+r'\s*\)\s*(?:;[^\r\n]*)?$',re.I)
        check(len(declaration.findall(text))==1 and len(re.findall(r'(?m)^\s*PUBLIC\s+'+re.escape(name)+r'\s*(?:;[^\r\n]*)?$',text,re.I))==1,
            'Native root source is not the exact PUBLIC zero QWORD array: '+name)
        for other in symbols:
            if other is symbol or other['section']!=symbol['section']:continue
            if other['name']==section['name'] and other['auxiliary']:continue
            check(not start<=other['value']<end,'Another COFF label or metadata symbol intrudes into native root span: '+name)
        check(all(not (offset<end and start<offset+width) for offset,width,_ in section['relocations'] if width),
            'Native oop root contains a relocation or native metadata address: '+name)
        if flags&0x40:
            check(section['position']>0 and not any(raw[section['position']+start:section['position']+end]),
                'Native root actual initialized cells are not all zero: '+name)
        else:check(section['position']==0,'Uninitialized native roots have unexpected physical bytes')
        for number,left,right in ranges:
            check(number!=symbol['section'] or end<=left or right<=start,'Overlapping actual native root spans')
        ranges.append((symbol['section'],start,end))
        result.append(dict(**row,object=artifact(path),assembly=artifact(assembly),section=section['name'],section_index=symbol['section'],
            offset=start,bytes=length,section_bytes=section['size'],initial_zero=True,writable_data=True,
            relocations_in_span=0,foreign_labels_in_span=0,physical_QWORD_span_verified=True))
    return result


def provider_projection(manifest,verified_source_metadata):
    """Called by the source verifier after independently rebuilding its model."""
    expected=declarations(verified_source_metadata.get('native_root_spans',[]))
    actual=declarations(manifest.get('native_root_spans',[]))
    check(actual==expected,'Provider manifest omitted or changed source native root spans')
    check({r['symbol'] for r in actual}<=set(manifest['exports']),'Provider native root span is not a real exported symbol')
    return verify_object(checked(manifest['object']),actual,assembly=checked(manifest['assembly'])) if actual else []


def selection(packs,indices,objects):
    """Project freshly source-verified load_packs records to the exact closure."""
    check(isinstance(indices,(list,set,tuple)) and all(type(i) is int and 0<=i<len(packs) for i in indices) and
        len(indices)==len(set(indices)),'Invalid selected provider root index set')
    paths=[str(Path(p).resolve()).casefold() for p in objects];result=[];names=set()
    for index in sorted(indices):
        pack=packs[index];manifest=pack['manifest'];reference=pack['reference'];verification=pack['verification']
        check(json.loads(checked(reference).read_text(encoding='utf-8-sig'))==manifest,'Selected provider root manifest changed')
        receipt=json.loads(checked(verification).read_text(encoding='utf-8-sig'))
        check(receipt.get('verified') is True and receipt.get('provider_manifest_sha256')==reference['digest']['sha256'],
            'Selected provider root source verification is absent or bound to another manifest')
        spans=declarations(manifest.get('native_root_spans',[]))
        if not spans:continue
        obj=checked(manifest['object']);check(paths.count(str(obj).casefold())==1,'Selected native root provider object must be linked exactly once')
        for span in provider_projection(manifest,dict(native_root_spans=spans)):
            check(span['symbol'] not in names,'Two selected native root providers export the same root span')
            names.add(span['symbol']);result.append(dict(provider_index=index,family=manifest['family'],provider_manifest=reference,
                provider_verification=verification,**span))
    return result


def directory_assembly(selected):
    """Emit address/count metadata. The directory itself must never be an oop root."""
    check(isinstance(selected,list),'Invalid selected native root physical projection')
    spans=declarations([{k:row[k] for k in ('symbol','count','kind')} for row in selected])
    check(all(row.get('physical_QWORD_span_verified') is True for row in selected),'Native root directory requires actual COFF physical verification')
    for declaration,row in zip(spans,selected):
        [fresh]=verify_object(checked(row['object']),[declaration],assembly=checked(row['assembly']))
        check(all(row.get(key)==value for key,value in fresh.items()),'Native root directory physical proof differs')
    symbols={row['symbol'] for row in spans}
    text=''.join('EXTERN '+name+':BYTE\n' for name in sorted(symbols))
    text+='''.const
ALIGN 8
PUBLIC boom_selected_provider_root_spans
boom_selected_provider_root_spans LABEL QWORD
'''
    text+=''.join(f" QWORD OFFSET {row['symbol']},{row['count']}\n" for row in spans)
    text+=f'''PUBLIC boom_selected_provider_root_span_count
boom_selected_provider_root_span_count QWORD {len(spans)}
PUBLIC boom_selected_provider_root_cell_count
boom_selected_provider_root_cell_count QWORD {sum(row['count'] for row in spans)}
'''
    return text,symbols


def complete_consumer_assembly(selected,*,source_exports):
    """Consume all nine ordinary banks, actual main/primordial cells and natives.

    Source exports must be the independently verified closure exports plus the
    normal VM binding exports. Missing base modules fail; nothing is silently
    omitted or selected on this function's behalf. Count symbols are read as
    integers into the caller's stack directory, never treated as oop cells.
    """
    base=STANDARD_SOURCE_SPANS+[PRIMORDIAL_SPAN];imports={name for pair in base for name in pair}
    check(imports<=set(source_exports),'Full native root consumer omitted an ordinary or primordial source root bank')
    directory,native_imports=directory_assembly(selected);imports|=native_imports
    count=len(base)+len(selected);frame=(48+16*count+15)//16*16+8
    text=''.join('EXTERN '+name+':QWORD\n' for name in sorted(imports-native_imports))+directory
    text+='''.code
PUBLIC boom_provider_native_roots_full_snapshot
boom_provider_native_roots_full_snapshot PROC FRAME
'''+f' sub rsp,{frame}\n .allocstack {frame}\n .endprolog\n'
    text+=' mov r10,rcx\n mov r11d,edx\n mov QWORD PTR [rsp+32],r8\n'
    for index,(name,counter) in enumerate(base):
        at=48+16*index
        text+=f' lea rax,{name}\n mov QWORD PTR [rsp+{at}],rax\n mov rax,QWORD PTR [{counter}]\n mov QWORD PTR [rsp+{at+8}],rax\n'
    for index,row in enumerate(selected,len(base)):
        at=48+16*index
        text+=f" lea rax,{row['symbol']}\n mov QWORD PTR [rsp+{at}],rax\n mov QWORD PTR [rsp+{at+8}],{row['count']}\n"
    text+=f' lea rcx,[rsp+48]\n mov edx,{count}\n mov r8,r10\n mov r9d,r11d\n call boom_provider_native_roots_snapshot\n add rsp,{frame}\n ret\n'
    text+='boom_provider_native_roots_full_snapshot ENDP\n'
    return text,imports


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--object',type=Path,required=True);parser.add_argument('--assembly',type=Path,required=True)
    parser.add_argument('--declarations',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=json.loads(args.declarations.read_text(encoding='utf-8-sig'))
    proof=verify_object(args.object,rows,assembly=args.assembly)
    out=args.output.resolve();check(out.is_relative_to(ART) and not out.exists(),'Fresh isolated native root proof output required')
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(dict(verified=True,scope='physical_COFF_native_oop_root_arrays_only',
        spans=proof,helper=artifact(Path(__file__)),automatic_GC=False),indent=2)+'\n',encoding='utf-8');print(out)
