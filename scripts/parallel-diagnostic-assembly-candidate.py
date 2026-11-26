"""Offline experiment: split preserved source procedures, then prove real COFF equivalence.

This candidate never changes the diagnostic producer, verifier, link inputs or
runtime. A successful receipt covers machine code, relocation targets, unwind
records and the complete original data/root layout, never guest execution.
"""
import argparse
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'
IDENT=re.compile(rb'\bboom_[A-Za-z0-9_]+\b')
DEFINITION=re.compile(rb'(?m)^[ \t]*(boom_[A-Za-z0-9_]+)(?::|[ \t]+(?:PROC|LABEL|QWORD|DWORD|WORD|BYTE)\b)')
JUMP=re.compile(rb'(?mi)^[ \t]*(?:j[a-z]+|loop[a-z]*)[ \t]+(?:(?:SHORT|NEAR PTR)[ \t]+)?(boom_[A-Za-z0-9_]+)[ \t]*\r?$')
HEADER=re.compile(rb'(?mi)^[ \t]*(?:option[ \t]+casemap[ \t]*:[ \t]*none|EXTERN\b[^\r\n]*|PUBLIC\b[^\r\n]*|END)[ \t]*\r?\n')
WIDTH={1:8,2:4,3:4,4:4,5:4,6:4,7:4,8:4,9:4}
RUNTIME_DATA={'.data','.bss','.rdata'}
KNOWN_SECTIONS=RUNTIME_DATA|{'.text$mn','.text','.pdata','.xdata','.debug$S'}


def check(value,message):
    if not value:raise ValueError(message)


def digest(path):
    p=Path(path)
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(p.resolve()),size=p.stat().st_size,sha256=h)


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')


def load_module(name,file):
    s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def normalized_source(raw):return raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n').encode()


def tokens(raw):
    code=re.sub(rb';[^\r\n]*',b'',raw)
    definitions={sys.intern(n.decode()) for n in DEFINITION.findall(code)}
    references={sys.intern(n.decode()) for n in IDENT.findall(code)}-definitions
    return definitions,references,code


class Coff:
    def __init__(self,path):
        self.path=Path(path);self.raw=self.path.read_bytes();d=self.raw
        check(len(d)>=20,'Truncated COFF')
        machine,n,_,symoff,ns,opt,_=struct.unpack_from('<HHIIIHH',d)
        check(machine==0x8664 and opt==0 and 20+n*40<=symoff and symoff+ns*18+4<=len(d),'Expected regular AMD64 COFF')
        strings=symoff+ns*18;ss=struct.unpack_from('<I',d,strings)[0]
        check(4<=ss and strings+ss==len(d),'Invalid COFF string table')
        self.sections={};self.by_section={};self.symbols={};self.index=[None]*ns
        for sid in range(1,n+1):
            at=20+(sid-1)*40;name=d[at:at+8].rstrip(b'\0').decode('ascii')
            _,_,size,data,rel,_,nr,_,flags=struct.unpack_from('<IIIIIIHHI',d,at+8)
            check(name in KNOWN_SECTIONS and name not in self.sections,'Unexpected/duplicate section '+name)
            check((name=='.bss' and data==0) or data+size<=len(d),'Invalid section data bounds')
            if flags&0x01000000:
                check(nr==65535 and rel+10<=len(d),'Invalid relocation overflow')
                count,si,kind=struct.unpack_from('<IIH',d,rel)
                check(count>65535 and si==kind==0,'Invalid overflow sentinel')
                nr=count-1;rel+=10
            check(not nr or rel+nr*10<=len(d),'Invalid relocation bounds')
            reloc=list(struct.iter_unpack('<IIH',d[rel:rel+nr*10])) if nr else []
            check(all(0<=o<size and i<ns and k in WIDTH for o,i,k in reloc),'Unsupported/out-of-range runtime relocation')
            check([r[0] for r in reloc]==sorted({r[0] for r in reloc}),'Unordered/duplicate relocations')
            s=dict(id=sid,name=name,size=size,raw=b'' if name=='.bss' else d[data:data+size],
                   reloc=reloc,offsets=[r[0] for r in reloc],flags=flags&~0x01000000)
            self.sections[name]=s;self.by_section[sid]=s
        i=0
        while i<ns:
            at=symoff+i*18;name=d[at:at+8]
            if name[:4]==b'\0'*4:
                off=struct.unpack_from('<I',name,4)[0];check(4<=off<ss,'Invalid symbol name offset')
                end=d.find(b'\0',strings+off,strings+ss);check(end>=0,'Unterminated symbol')
                name=d[strings+off:end]
            else:name=name.rstrip(b'\0')
            name=sys.intern(name.decode('ascii'));value,section,kind,storage,aux=struct.unpack_from('<IhHBB',d,at+8)
            check(section<=n and i+aux<ns,'Invalid symbol metadata')
            rec=dict(name=name,value=value,section=section,kind=kind,storage=storage)
            self.index[i]=rec
            if name.startswith('boom_'):
                check(name not in self.symbols,'Duplicate COFF source symbol '+name);self.symbols[name]=rec
            i+=aux+1
        text=self.sections.get('.text$mn') or self.sections.get('.text')
        self.text=text;self.functions={};self.starts=[];self.ordered=[]
        if text:
            fs=sorted((s['value'],s['name']) for s in self.symbols.values() if s['section']==text['id'] and s['kind']==32)
            check(len(fs)==len({v for v,n in fs}),'Aliased procedure starts are unsupported')
            for j,(start,name) in enumerate(fs):
                end=fs[j+1][0] if j+1<len(fs) else text['size']
                check(start<end<=text['size'],'Invalid procedure interval')
                self.functions[name]=(start,end);self.starts.append(start);self.ordered.append(name)
            check((fs and fs[0][0]==0) or text['size']==0,'Code exists outside indexed complete procedures')

    def code_address(self,value):
        j=bisect_right(self.starts,value)-1
        check(j>=0 and value<self.text['size'],'Relative target is outside complete source procedures')
        name=self.ordered[j];return ('code',name,value-self.starts[j])

    def address(self,section,value):
        s=self.by_section[section]
        if s is self.text:return self.code_address(value)
        check(s['name'] in RUNTIME_DATA,'Unexpected address into '+s['name'])
        check(0<=value<=s['size'],'Relocation points beyond data section')
        return ('data',s['name'],value)


def definitions(objects):
    result={}
    for obj in objects:
        for name,s in obj.symbols.items():
            if s['section']>0:
                check(name not in result,'Duplicate bundle definition '+name);result[name]=(obj,s)
    return result


def target(obj,index,addend,global_definitions):
    s=obj.index[index];check(s is not None,'Relocation targets auxiliary symbol')
    if s['section']>0:return obj.address(s['section'],s['value']+addend)
    check(s['section']==0 and s['storage']==2,'Unsupported relocation symbol class')
    if s['name'] in global_definitions:
        owner,definition=global_definitions[s['name']]
        return owner.address(definition['section'],definition['value']+addend)
    return ('external',s['name'],addend)


def section_fingerprint(obj,s,global_definitions):
    if s['name']=='.bss':return (s['size'],s['flags'],'zero',())
    body=bytearray(s['raw']);fix=[];last=-1
    for offset,index,kind in s['reloc']:
        width=WIDTH[kind];check(last<=offset and offset+width<=len(body),'Overlapping/out-of-range relocation')
        value=int.from_bytes(body[offset:offset+width],'little',signed=True)
        fix.append((offset,kind,target(obj,index,value,global_definitions)))
        body[offset:offset+width]=b'\0'*width;last=offset+width
    return (s['size'],s['flags'],hashlib.sha256(body).hexdigest(),tuple(fix))


def unwind(obj):
    p=obj.sections.get('.pdata');x=obj.sections.get('.xdata')
    if not p or not p['size']:
        check(not x or not x['size'],'Unreferenced unwind data');return {}
    check(p['size']%12==0 and x is not None,'Invalid x64 function table')
    rel={offset:(index,kind) for offset,index,kind in p['reloc']}
    check(len(rel)==p['size']//4,'Missing/unexpected x64 unwind relocation')
    result={};covered=set()
    for at in range(0,p['size'],12):
        resolved=[]
        for off in (at,at+4,at+8):
            index,kind=rel[off];s=obj.index[index]
            check(kind==3 and s is not None and s['section']>0,'Unexpected x64 unwind relocation target')
            value=struct.unpack_from('<I',p['raw'],off)[0]+s['value']
            resolved.append((obj.by_section[s['section']]['name'],value))
        (code,start),(endcode,end),(xname,pos)=resolved
        check(code==endcode==obj.text['name'] and xname=='.xdata' and start in obj.starts,'Unwind entry is not a source procedure')
        name=obj.ordered[bisect_left(obj.starts,start)]
        check(obj.functions[name]==(start,end) and name not in result,'Unwind/code boundaries differ')
        check(pos+4<=x['size'],'Truncated unwind header')
        version=x['raw'][pos]&7;flags=x['raw'][pos]>>3;count=x['raw'][pos+2]
        check(version==1 and flags==0,'Unsupported handler/chained/versioned unwind; retain original group')
        size=(4+count*2+3)&~3
        check(pos+size<=x['size'] and not any(pos+i in covered for i in range(size)),'Overlapping unwind records')
        covered.update(range(pos,pos+size));result[name]=x['raw'][pos:pos+size]
    check(len(covered)==x['size'] and not x['reloc'],'Unaccounted unwind bytes/relocations')
    return result


def code_fingerprint(obj,name,global_definitions,lite,detail,capstone):
    from capstone.x86 import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    start,end=obj.functions[name];raw=obj.text['raw'][start:end];body=bytearray(raw)
    a=bisect_left(obj.text['offsets'],start);b=bisect_left(obj.text['offsets'],end)
    pending={};fix={}
    for pos,index,kind in obj.text['reloc'][a:b]:
        off=pos-start;width=WIDTH[kind];check(off+width<=len(raw),'Relocation crosses a procedure boundary')
        addend=int.from_bytes(raw[off:off+width],'little',signed=True)
        pending[off]=(kind,width,index,addend)
    consumed=0
    for ip,size,mnemonic,operands in lite.disasm_lite(raw,start):
        check(ip==start+consumed,'Undecoded code gap');consumed+=size
        if not (mnemonic.startswith(('j','loop')) or mnemonic in ('call','xbegin') or 'rip' in operands):continue
        ins=next(detail.disasm(raw[ip-start:ip-start+size],ip,count=1))
        relative=ins.group(capstone.CS_GRP_JUMP) or ins.group(capstone.CS_GRP_CALL)
        if relative and ins.operands and ins.operands[0].type==X86_OP_IMM:
            offset=ip-start+ins.imm_offset;width=ins.imm_size
            check(width in (1,4),'Unsupported direct relative transfer width')
            if offset in pending:
                kind,rwidth,index,addend=pending.pop(offset)
                check(kind==4 and rwidth==width==4,'Relative branch relocation width/type changed')
                value=target(obj,index,addend,global_definitions)
            else:
                displacement=int.from_bytes(raw[offset:offset+width],'little',signed=True)
                value=obj.code_address(ip+size+displacement)
            fix[offset]=('relative_branch',width,value)
        for operand in ins.operands:
            if operand.type!=X86_OP_MEM or operand.mem.base!=X86_REG_RIP:continue
            # 66 0F 2E 05 disp32 (the real source's UCOMISD) is reported with
            # disp_size=2 by Capstone 5.0.7. Validate the actual AMD64 ModR/M
            # encoding: mod=00/rm=101 in 64-bit address mode has no SIB and
            # always carries four displacement bytes, independent of operand
            # width or the decoder's mistaken size annotation.
            modrm=ins.modrm_offset
            check(ins.addr_size==8 and 0<modrm<size and ins.bytes[modrm]&0xC7==0x05 and
                  ins.disp_offset==modrm+1 and ins.disp_offset+4<=size and ins.sib==0,
                  f'Unsupported actual RIP encoding: {name}+{ip-start} {ins.bytes.hex()} '
                  f'{ins.mnemonic} {ins.op_str} displacement_offset={ins.disp_offset} displacement_size={ins.disp_size}')
            offset=ip-start+ins.disp_offset;width=4
            if offset in pending:
                kind,rwidth,index,addend=pending.pop(offset)
                check(4<=kind<=9 and rwidth==4,'Unsupported RIP relocation')
                # REL32_n may encode the trailing immediate either in n or as
                # an inline negative addend. Compare the CPU's real RIP end.
                value=target(obj,index,addend+size-ins.disp_offset-4-(kind-4),global_definitions)
            else:
                displacement=int.from_bytes(raw[offset:offset+4],'little',signed=True)
                value=obj.code_address(ip+size+displacement)
            fix[offset]=('rip_relative',4,value)
    check(consumed==len(raw),'Invalid/unsupported AMD64 instruction at end of '+name)
    for offset,(kind,width,index,addend) in pending.items():
        fix[offset]=('coff',kind,width,target(obj,index,addend,global_definitions))
    last=-1
    for offset,value in sorted(fix.items()):
        width=value[2] if value[0]=='coff' else value[1]
        check(last<=offset and offset+width<=len(body),'Overlapping code fixups')
        body[offset:offset+width]=b'\0'*width;last=offset+width
    return len(body),hashlib.sha256(body).hexdigest(),tuple(sorted(fix.items()))


def preserve_transfer_widths(units,spans,index,baseline,jump_sources):
    """Merge whole source groups until ml64 cannot shorten an original jump.

    Unit order is always an original-order subsequence. A merge can only restore
    original intervening code, so an originally short transfer stays in range.
    All final widths and targets are still independently checked in real COFF.
    """
    import capstone
    from capstone.x86 import X86_OP_IMM
    engine=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);engine.detail=True
    old_defs=definitions([baseline]);jumps=[]
    for name in jump_sources:
        start,end=baseline.functions[name]
        rel={o:(i,k) for o,i,k in baseline.text['reloc'][
            bisect_left(baseline.text['offsets'],start):bisect_left(baseline.text['offsets'],end)]}
        for ins in engine.disasm(baseline.text['raw'][start:end],start):
            if not ins.group(capstone.CS_GRP_JUMP) or not ins.operands or ins.operands[0].type!=X86_OP_IMM:continue
            width=ins.imm_size;check(width in (1,4),'Unsupported actual source transfer width')
            field=ins.address+ins.imm_offset
            if field in rel:
                i,k=rel[field];check(k==4 and width==4,'Unsupported original transfer relocation')
                addend=int.from_bytes(baseline.text['raw'][field:field+width],'little',signed=True)
                destination=target(baseline,i,addend,old_defs)
            else:destination=baseline.code_address(ins.operands[0].imm)
            if destination[0]!='code' or destination[1]==name:continue
            _,callee,offset=destination
            original_displacement=baseline.functions[callee][0]+offset-ins.address-ins.size
            # An explicit near transfer that was already in short range does
            # not depend on intervening code to preserve its width.
            if width==4 and -128<=original_displacement<=127:continue
            jumps.append((name,callee,offset,ins.address-start+ins.size,width))
    sizes={n:end-start for n,(start,end) in baseline.functions.items()};merges=[]
    while True:
        owner={};positions={}
        for u,unit in enumerate(units):
            unit.sort(key=index.__getitem__);position=0
            for name in unit:owner[name]=u;positions[name]=position;position+=sizes[name]
        bad=None
        for caller,callee,offset,next_ip,width in jumps:
            check(owner[caller]==owner[callee],'Original cross-procedure jump group was split')
            displacement=positions[callee]+offset-positions[caller]-next_ip
            if width==1:check(-128<=displacement<=127,'Short transfer would grow; retain its complete source group')
            elif -128<=displacement<=127:bad=(caller,callee,displacement);break
        if bad is None:break
        caller,callee,displacement=bad;current=owner[caller]
        lo,hi=sorted((index[caller],index[callee]));required=128-displacement if displacement>=0 else 129+displacement
        choices=[]
        for u,unit in enumerate(units):
            if u==current or not unit:continue
            contribution=sum(sizes[n] for n in unit if lo<index[n]<hi)
            if contribution:
                source_bytes=sum(spans[n][1]-spans[n][0] for n in unit)
                choices.append((contribution<required,source_bytes,-contribution,u))
        check(choices,'Original near transfer cannot be preserved by whole source groups: '+caller)
        _,_,_,other=min(choices);keep,remove=sorted((current,other))
        units[keep].extend(units[remove]);units[remove]=[]
        merges.append(dict(caller=caller,callee=callee,shortened_displacement=displacement,
            merged_source_units=[current+1,other+1],
            protected_source_bytes=sum(spans[n][1]-spans[n][0] for n in units[keep])))
        check(len(merges)<len(units),'Unbounded transfer-preservation merge')
    return [u for u in units if u],merges


def verify_source_preservation(manifest):
    if 'source' not in manifest:return False
    source=Path(manifest['source']['path']);check(digest(source)==manifest['source'],'Original source changed')
    raw=source.read_bytes();B=load_module('parallel_candidate_independent_source_ranges','batch-source.py')
    spans=B.procedure_spans(raw);check(spans.keys()==manifest['functions'].keys(),'Original procedure inventory changed')
    last=0;data=[];seen=set()
    for name,(start,end) in spans.items():
        check(hashlib.sha256(raw[start:end]).hexdigest()==manifest['functions'][name],'Original source function hash differs')
        data.append(raw[last:start]);last=end
    data.append(raw[last:]);payload=HEADER.sub(b'',b''.join(data))
    for unit in manifest['units']:
        path=Path(unit['assembly']['path']);check(digest(path)==unit['assembly'],'Candidate ASM changed')
        body=path.read_bytes();actual=B.procedure_spans(body)
        check(set(actual)==set(unit['functions']) and not seen&actual.keys(),'Candidate source function coverage differs')
        seen.update(actual)
        for name,(start,end) in actual.items():
            check(hashlib.sha256(body[start:end]).hexdigest()==manifest['functions'][name],
                  'Candidate changed complete source function bytes: '+name)
        if unit['unit']==0:
            start=unit['payload_offset'];end=start+unit['source_bytes']
            check(body[start:end]==payload,'Original class/dispatch/handler/root source bytes changed')
    check(seen==set(spans),'Candidate omitted a complete original function')
    return True


def prepare(directory,output,budget):
    source=directory/'initialization-closure.asm';raw=source.read_bytes()
    closure=json.loads((directory/'closure.json').read_bytes());expected=closure['selected_function_sha256']
    spans=load_module('parallel_candidate_source_ranges','batch-source.py').procedure_spans(raw)
    check(spans.keys()==expected.keys(),'Complete source procedures differ from the selected closure')
    names=list(spans);index={n:i for i,n in enumerate(names)};parents=list(range(len(names)))
    def root(i):
        while i!=parents[i]:parents[i]=parents[parents[i]];i=parents[i]
        return i
    def join(i,j):
        i,j=root(i),root(j)
        if i!=j:parents[max(i,j)]=min(i,j)
    last=0;outside=[];references={};hashes={};frames=set();jump_sources=[]
    for n,(begin,end) in spans.items():
        outside.append(raw[last:begin]);last=end;body=raw[begin:end]
        check(hashlib.sha256(normalized_source(body)).hexdigest()==expected[n],'Selected source procedure bytes differ: '+n)
        hashes[n]=hashlib.sha256(body).hexdigest()
        _,refs,code=tokens(body);references[n]=refs
        if re.search(rb'^'+n.encode()+rb' PROC[^\r\n]*\bFRAME\b',body):frames.add(n)
        if n+'_body' in index:join(index[n],index[n+'_body'])
        has_jump=False
        for target_name in JUMP.findall(code):
            target_name=target_name.decode()
            if target_name in index:join(index[n],index[target_name]);has_jump=True
        if has_jump:jump_sources.append(n)
    outside.append(raw[last:]);data_raw=b''.join(outside);data_payload=HEADER.sub(b'',data_raw)
    data_defs,data_refs,_=tokens(data_payload)
    check(not (data_defs&set(names)),'A complete procedure was left in the data unit')
    groups={}
    for n in names:groups.setdefault(root(index[n]),[]).append(n)
    units=[];current=[];size=0
    for group in groups.values():
        total=sum(spans[n][1]-spans[n][0] for n in group)
        if current and size+total>budget:units.append(current);current=[];size=0
        current.extend(group);size+=total
    if current:units.append(current)
    baseline=Coff(directory/'initialization-closure.obj')
    check(baseline.ordered==names,'Actual monolithic procedure order differs from preserved source')
    units,merges=preserve_transfer_widths(units,spans,index,baseline,jump_sources)
    all_defs=set(names)|data_defs
    imports={x.decode():y.decode().upper() for x,y in re.findall(rb'(?mi)^EXTERN (boom_\w+):(PROC|BYTE|QWORD|DWORD)[ \t]*\r?$',raw)}
    known=all_defs|set(imports)
    all_refs=set(data_refs).union(*(references.values()))
    check(all_refs<=known,'Unsupported cross-procedure local label or undeclared symbol: '+str(sorted(all_refs-known)[:8]))
    records=[]
    def emit(number,unit,content,defs,refs):
        extern=sorted(refs-defs);prefix=[b'option casemap:none\r\n']
        for name in extern:
            kind='PROC' if name in spans or imports.get(name)=='PROC' else 'BYTE'
            prefix.append(f'EXTERN {name}:{kind}\r\n'.encode())
        prefix.extend(f'PUBLIC {name}\r\n'.encode() for name in sorted(defs))
        prefix=b''.join(prefix)+b'.code\r\n'
        path=output/f'{number:04}.asm';path.write_bytes(prefix+content+b'\r\nEND\r\n')
        records.append(dict(unit=number,assembly=digest(path),functions=unit,source_bytes=len(content),
                            payload_offset=len(prefix),externs=extern))
    emit(0,[],data_payload,data_defs,data_refs)
    for number,unit in enumerate(units,1):
        unit.sort(key=index.__getitem__)
        defs=set(unit);refs=set().union(*(references[n] for n in unit))
        content=b'\r\n'.join(raw[spans[n][0]:spans[n][1]] for n in unit)
        emit(number,unit,content,defs,refs)
    return dict(schema=1,offline_candidate=True,source=digest(source),closure=digest(directory/'closure.json'),
        monolithic_object=digest(directory/'initialization-closure.obj'),units=records,functions=hashes,
        framed_functions=sorted(frames),data_definitions=sorted(data_defs),code_budget=budget,
        branch_width_preserving_merges=merges,
        complete_source_function_bytes_preserved=True,all_data_in_one_unit=True,
        source_procedures=len(names),synchronized_and_jump_groups=len(groups),linked=False,executed=False,game_started=False)


def assemble(manifest,assembler,output,workers):
    def one(unit):
        source=Path(unit['assembly']['path']);obj=source.with_suffix('.obj');start=time.monotonic()
        with source.with_suffix('.log').open('xb') as log:
            p=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        check(p.returncode==0,'ml64 failed: '+str(source.with_suffix('.log')))
        check(digest(source)==unit['assembly'],'Candidate source changed during assembly')
        return unit['unit'],digest(obj),round(time.monotonic()-start,6)
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending=[executor.submit(one,u) for u in manifest['units']]
        for future in as_completed(pending):
            number,obj,seconds=future.result();manifest['units'][number].update(object=obj,assembly_seconds=seconds)
            print(json.dumps(dict(stage='assembled',unit=number,seconds=seconds)),flush=True)
    manifest['parallel_assembly_seconds']=round(time.monotonic()-start,6)


def equivalence(manifest):
    import capstone
    decoder_root=Path(capstone.__file__).resolve().parent
    decoder={str(p.relative_to(decoder_root)):digest(p) for p in sorted(decoder_root.rglob('*.py'))}
    decoder['native_library']=digest(capstone._cs._name)
    lite=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    detail=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);detail.detail=True
    source_checked=verify_source_preservation(manifest)
    check(digest(manifest['monolithic_object']['path'])==manifest['monolithic_object'],'Monolithic COFF changed')
    for unit in manifest['units']:check(digest(unit['object']['path'])==unit['object'],'Candidate COFF changed')
    baseline=Coff(manifest['monolithic_object']['path']);objects=[Coff(u['object']['path']) for u in manifest['units']]
    old_defs=definitions([baseline]);new_defs=definitions(objects)
    expected=set(manifest['functions'])
    check(set(baseline.functions)==expected and set().union(*(o.functions for o in objects))==expected,'Actual COFF procedure coverage differs')
    check(sum(len(o.functions) for o in objects)==len(expected),'Duplicate actual COFF procedures')
    data=objects[0]
    check(not data.functions and all(not o.sections.get(n,{}).get('size') for o in objects[1:] for n in RUNTIME_DATA),
          'Runtime data moved into a code unit')
    layout={}
    for name in RUNTIME_DATA:
        old=baseline.sections.get(name);new=data.sections.get(name)
        check(old is not None and new is not None,'Missing original data section')
        check(section_fingerprint(baseline,old,old_defs)==section_fingerprint(data,new,new_defs),'Data bytes, relocations or roots differ: '+name)
        layout[name]=dict(bytes=old['size'],relocations=len(old['reloc']),alignment_and_flags=old['flags'])
    for name,s in baseline.symbols.items():
        if s['section']>0 and baseline.by_section[s['section']]['name'] in RUNTIME_DATA:
            check(name in data.symbols,'Original data symbol disappeared: '+name)
            now=data.symbols[name]
            check(data.by_section[now['section']]['name']==baseline.by_section[s['section']]['name'] and
                  now['value']==s['value'],'Original data/root symbol layout changed: '+name)
    old_unwind=unwind(baseline);new_unwind={}
    for obj in objects:
        current=unwind(obj);check(not new_unwind.keys()&current.keys(),'Duplicate unwind entry');new_unwind.update(current)
    check(old_unwind==new_unwind and set(old_unwind)==set(manifest['framed_functions']),'Per-function unwind bytes/coverage changed')
    start=time.monotonic();verified={};count=0
    for obj in objects[1:]:
        for name in obj.ordered:
            before=code_fingerprint(baseline,name,old_defs,lite,detail,capstone)
            after=code_fingerprint(obj,name,new_defs,lite,detail,capstone)
            check(before==after,'Machine code/branch width/relocation target differs: '+name)
            verified[name]=dict(bytes=before[0],normalized_machine_sha256=before[1],fixups=len(before[2]));count+=1
            if count%5000==0:print(json.dumps(dict(stage='equivalent_functions',functions=count,seconds=round(time.monotonic()-start,3))),flush=True)
    roots={}
    if 'boom_probe_static_roots' in baseline.symbols:
        root=baseline.symbols['boom_probe_static_roots'];num=baseline.symbols['boom_probe_static_root_count']
        s=baseline.by_section[num['section']];cells=struct.unpack_from('<Q',s['raw'],num['value'])[0]
        check(baseline.by_section[root['section']]['name']=='.bss' and root['value']+cells*8<=baseline.sections['.bss']['size'],'Invalid original contiguous root span')
        roots=dict(section='.bss',offset=root['value'],cells=cells,bytes=cells*8)
    check(all(digest(record['path'])==record for record in decoder.values()),'Instruction decoder changed during verification')
    check(digest(manifest['monolithic_object']['path'])==manifest['monolithic_object'],'Monolithic COFF changed during proof')
    for unit in manifest['units']:
        check(digest(unit['object']['path'])==unit['object'],'Candidate COFF changed during proof')
        if 'assembly' in unit:check(digest(unit['assembly']['path'])==unit['assembly'],'Candidate ASM changed during proof')
    return dict(schema=1,verified=True,scope='complete_source_procedures_actual_code_fixups_unwind_and_data_root_layout',
        source_procedures=count,framed_procedures=len(old_unwind),machine_code_bytes=sum(v['bytes'] for v in verified.values()),
        per_function=verified,data_sections=layout,contiguous_static_roots=roots,decoder_version=capstone.__version__,decoder=decoder,
        exact_instruction_widths=True,relative_targets_compared=True,original_data_symbol_offsets_preserved=True,
        rip_disp32_validated_from_actual_modrm=True,
        source_byte_preservation_independently_checked=source_checked,
        debug_sections_compared=False,linked=False,executed=False,game_started=False,
        verification_seconds=round(time.monotonic()-start,6))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--assembler',type=Path,required=True);p.add_argument('--workers',type=int,default=8)
    p.add_argument('--code-mib',type=int,default=8);p.add_argument('--prepare-only',action='store_true')
    a=p.parse_args();directory=a.directory.resolve();output=a.output.resolve();assembler=a.assembler.resolve()
    check(directory.is_relative_to(ART) and output.is_relative_to(ART) and not output.exists(),'Fresh project-owned candidate output required')
    check(assembler.name.lower()=='ml64.exe' and 1<=a.workers<=8 and a.code_mib>0,'Expected ml64, at most eight workers and a positive code budget')
    output.mkdir(parents=True);start=time.monotonic()
    inputs={n:digest(directory/n) for n in ('initialization-closure.asm','initialization-closure.obj','closure.json',
            'assembly-provenance.json','selection-verification.json')}
    sealed=json.loads((directory/'selection-verification.json').read_bytes())
    check(sealed.get('verified') is True and sealed.get('verified_assembly_objects') and
          sealed['closure_manifest_sha256']==inputs['closure.json']['sha256'],
          'The immutable source selection must already have its independent complete verification')
    provenance=json.loads((directory/'assembly-provenance.json').read_bytes())
    check(provenance['assembler']['path']==str(assembler) and provenance['assembler']['digest']==
          {k:v for k,v in digest(assembler).items() if k!='path'},'Baseline ml64 identity differs')
    check(any(u['assembly']['digest']['sha256']==inputs['initialization-closure.asm']['sha256'] and
              u['object']['digest']['sha256']==inputs['initialization-closure.obj']['sha256'] for u in provenance['units']),
          'Monolithic COFF is not bound to its original source receipt')
    tool=digest(assembler);own=digest(Path(__file__));indexer=digest(Path(__file__).with_name('batch-source.py'))
    try:
        manifest=prepare(directory,output,a.code_mib*1024*1024)
        manifest.update(assembler=tool,candidate_script=own,source_indexer=indexer,inputs=inputs,workers=a.workers,
                        preparation_seconds=round(time.monotonic()-start,6))
        print(json.dumps(dict(stage='prepared',functions=manifest['source_procedures'],units=len(manifest['units']),
                             seconds=manifest['preparation_seconds'])),flush=True)
        write(output/'prepared.json',manifest)
        if a.prepare_only:return
        assemble(manifest,assembler,output,a.workers);write(output/'assembled.json',manifest)
        proof=equivalence(manifest)
        check(digest(assembler)==tool and digest(Path(__file__))==own and digest(indexer['path'])==indexer,
              'Candidate tool changed during experiment')
        check(all(digest(directory/n)==v for n,v in inputs.items()),'Original monolithic input changed during experiment')
        proof.update(manifest=digest(output/'assembled.json'),inputs=inputs,parallel_assembly_seconds=manifest['parallel_assembly_seconds'],
                     total_seconds=round(time.monotonic()-start,6))
        write(output/'equivalence.json',proof)
        print(json.dumps({k:v for k,v in proof.items() if k not in ('per_function','inputs')}),flush=True)
    except Exception as error:
        write(output/'failure.json',dict(failed=True,error_type=type(error).__name__,error=str(error),
            elapsed_seconds=round(time.monotonic()-start,6),linked=False,executed=False,game_started=False))
        raise


if __name__=='__main__':main()
