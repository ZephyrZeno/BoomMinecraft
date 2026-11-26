"""Fresh source-preserving split MASM units for initialization-closure only.

The receipt certifies source ranges and actual COFF structure. It deliberately
does not certify equivalence to an absent monolithic object. The separate
candidate provides that historical experiment and native prefix replay.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


P=module('fresh_parallel_coff_and_source_primitives','parallel-diagnostic-assembly-candidate.py')
B=module('fresh_parallel_original_procedure_ranges','batch-source.py')
check=P.check


def artifact(path):
    record=P.digest(path)
    return dict(path=record['path'],digest={k:record[k] for k in ('size','sha256')})


def checked(record):
    check(artifact(record['path'])==record,'Parallel assembly artifact changed: '+record['path'])
    return Path(record['path'])


def read(path):return json.loads(Path(path).read_bytes())


def write(path,value):
    path=Path(path);check(not path.exists(),'Immutable parallel assembly record already exists')
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def tools():
    return {name:artifact(Path(__file__).with_name(name)) for name in
            ('parallel-diagnostic-assembly.py','parallel-diagnostic-assembly-candidate.py','batch-source.py')}


def normalized_hash(raw):return hashlib.sha256(P.normalized_source(raw)).hexdigest()


def static_roots(payload):
    code=re.sub(rb';[^\r\n]*',b'',payload)
    count=re.findall(rb'(?m)^boom_probe_static_root_count[ \t]+QWORD[ \t]+(\d+)[ \t]*\r?$',code)
    start=re.search(rb'(?m)^boom_probe_static_roots[ \t]+LABEL[ \t]+QWORD[ \t]*\r?\n',code)
    check(len(count)==1 and start is not None,'Expected the original contiguous static root declaration')
    before=code[:start.start()];sections=list(re.finditer(rb'(?m)^\.(data\??|const|code)[ \t]*\r?$',before))
    check(sections and sections[-1][1]==b'data?','Static roots are outside uninitialized data')
    # The selector places the complete reference-root prefix at the beginning
    # of BSS. No earlier BSS allocations may be hidden by section switches.
    for i,section in enumerate(sections):
        if section[1]!=b'data?':continue
        end=sections[i+1].start() if i+1<len(sections) else len(before)
        prefix=before[section.end():end]
        check(re.sub(rb'(?mi)^[ \t]*ALIGN[ \t]+8[ \t]*\r?$',b'',prefix).strip()==b'',
              'Unexpected allocation before the static root prefix')
    rest=code[start.end():];boundary=re.search(rb'(?m)^\.(?:data\??|const|code)[ \t]*\r?$',rest)
    check(boundary is not None,'Unterminated static root source region')
    rows=[];cells=0
    pattern=re.compile(rb'^(boom_\w+)[ \t]+QWORD[ \t]+(?:\?|([0-9]+)[ \t]+DUP\(\?\))[ \t]*$',re.I)
    for line in rest[:boundary.start()].splitlines():
        line=line.strip()
        if not line:continue
        if line.upper()==b'ALIGN 8':continue
        match=pattern.fullmatch(line);check(match is not None,'Unsupported source static root allocation')
        size=int(match[2]) if match[2] else 1;check(size>0,'Empty root allocation')
        rows.append(dict(name=match[1].decode(),offset=cells*8,cells=size));cells+=size
    check(cells==int(count[0]),'Static root declarations differ from their original count')
    return dict(symbol='boom_probe_static_roots',count_symbol='boom_probe_static_root_count',
                section='.bss',offset=0,cells=cells,bytes=cells*8,rows=rows)


def model(source,expected,budget):
    raw=Path(source).read_bytes();spans=B.procedure_spans(raw);names=list(spans);index={n:i for i,n in enumerate(names)}
    check(spans.keys()==expected.keys() and all(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for h in expected.values()),
          'Source procedures differ from the current normalized function inventory')
    public=set()
    for declaration in re.findall(rb'(?mi)^[ \t]*PUBLIC[ \t]+([^\r\n;]+)',raw):
        public.update(n.decode() for n in re.split(rb'[, \t]+',declaration.strip()) if n)
    check(set(names)<=public,'Private procedures cannot be promoted by the initial-closure splitter')
    parent=list(range(len(names)))
    def root(i):
        while i!=parent[i]:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def join(a,b):
        a,b=root(a),root(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    refs={};hashes={};frames=[];outside=[];last=0
    for name,(begin,end) in spans.items():
        body=raw[begin:end];outside.append(raw[last:begin]);last=end
        check(normalized_hash(body)==expected[name],'Original normalized procedure hash differs: '+name)
        hashes[name]=dict(begin=begin,end=end,raw_sha256=hashlib.sha256(body).hexdigest(),normalized_sha256=expected[name])
        _,refs[name],code=P.tokens(body)
        if re.search(rb'^'+name.encode()+rb' PROC[^\r\n]*\bFRAME\b',body):frames.append(name)
        if name+'_body' in index:join(index[name],index[name+'_body'])
        for target in P.JUMP.findall(code):
            target=target.decode()
            if target in index:join(index[name],index[target])
    outside.append(raw[last:]);payload=P.HEADER.sub(b'',b''.join(outside))
    data_defs,data_refs,_=P.tokens(payload)
    check(not data_defs&set(names) and public<=data_defs|set(names),'Unknown PUBLIC or code outside complete source procedures')
    imports={n.decode():kind.decode().upper() for n,kind in
             re.findall(rb'(?mi)^[ \t]*EXTERN[ \t]+(boom_\w+):(PROC|BYTE|WORD|DWORD|QWORD)[ \t]*\r?$',raw)}
    data_types={}
    for name,label,plain in re.findall(rb'(?mi)^[ \t]*(boom_\w+)[ \t]+(?:LABEL[ \t]+(BYTE|WORD|DWORD|QWORD)|(BYTE|WORD|DWORD|QWORD))\b',payload):
        name=name.decode();kind=(label or plain).decode().upper()
        check(name not in data_types,'Duplicate external data type declaration');data_types[name]=kind
    check(data_types.keys()==data_defs,'Untyped or unsupported external data declaration')
    all_defs=data_defs|set(names);all_refs=set(data_refs).union(*refs.values())
    check(all_refs<=all_defs|imports.keys(),'Undeclared or cross-procedure local source symbol')
    groups={}
    for name in names:groups.setdefault(root(index[name]),[]).append(name)
    units=[];current=[];size=0
    for group in groups.values():
        amount=sum(spans[n][1]-spans[n][0] for n in group)
        if current and size+amount>budget:units.append(current);current=[];size=0
        current.extend(group);size+=amount
    if current:units.append(current)
    plans=[dict(unit=0,role='data',functions=[],exports=sorted(data_defs),imports=sorted(data_refs-data_defs))]
    for i,unit in enumerate(units,1):
        unit.sort(key=index.__getitem__);unit_refs=set().union(*(refs[n] for n in unit))
        plans.append(dict(unit=i,role='code',functions=unit,exports=sorted(unit),imports=sorted(unit_refs-set(unit))))
        for name in unit:hashes[name]['unit']=i
    for plan in plans:
        plan['extern_types']={n:('PROC' if n in spans else data_types.get(n,imports.get(n,'BYTE'))) for n in plan['imports']}
    recipe=dict(functions=hashes,source_public=sorted(public),data_definitions=sorted(data_defs),
        promoted_data=sorted(data_defs-public),framed_functions=sorted(frames),code_budget_bytes=budget,
        data_payload=dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest()),
        static_roots=static_roots(payload),plans=plans)
    return raw,spans,payload,recipe


def render(raw,spans,payload,plan):
    prefix=[b'option casemap:none\r\n']
    prefix.extend(f'EXTERN {n}:{plan["extern_types"][n]}\r\n'.encode() for n in plan['imports'])
    prefix.extend(f'PUBLIC {n}\r\n'.encode() for n in plan['exports'])
    body=payload if plan['role']=='data' else b'\r\n'.join(raw[spans[n][0]:spans[n][1]] for n in plan['functions'])
    return b''.join(prefix)+b'.code\r\n'+body+b'\r\nEND\r\n'


def prepare(source,output,expected_normalized_function_hashes,budget_bytes=8*1024*1024):
    source=Path(source).resolve();output=Path(output).resolve()
    check(source.is_relative_to(ART) and output.is_relative_to(ART) and not output.exists() and budget_bytes>0,
          'Fresh project-owned source splitter directory required')
    before=artifact(source);source_tools=tools();raw,spans,payload,recipe=model(source,expected_normalized_function_hashes,budget_bytes)
    output.mkdir(parents=True);units=[]
    for plan in recipe['plans']:
        path=output/f'{plan["unit"]:04}.asm';path.write_bytes(render(raw,spans,payload,plan))
        units.append(dict(plan,assembly=artifact(path)))
    check(artifact(source)==before and tools()==source_tools,'Source or splitter changed during preparation')
    manifest=dict(schema=1,scope='source_preserving_parallel_initialization_closure',manifest_path=str(output/'prepared.json'),
        source=before,source_tools=source_tools,units=units,recipe=recipe,promoted_data=recipe['promoted_data'],
        monolithic_reference_used=False,monolithic_binary_equivalence=False,game_started=False)
    write(output/'prepared.json',manifest);return manifest


def assemble(manifest,assembler,workers=8):
    if not isinstance(manifest,dict):manifest=read(manifest)
    path=Path(manifest['manifest_path']);check(read(path)==manifest,'Prepared manifest differs')
    checked(manifest['source']);check(manifest['source_tools']==tools(),'Fresh splitter tool identity changed')
    assembler=Path(assembler).resolve();check(assembler.name.lower()=='ml64.exe' and 1<=workers<=8,'Expected ml64 with at most eight workers')
    tool=artifact(assembler);started=time.monotonic()
    def one(unit):
        source=checked(unit['assembly']);obj=source.with_suffix('.obj');start=time.monotonic()
        with source.with_suffix('.log').open('xb') as log:
            result=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        check(result.returncode==0,'Fresh split ml64 failed: '+str(source.with_suffix('.log')))
        checked(unit['assembly']);return dict(unit,object=artifact(obj),assembly_seconds=round(time.monotonic()-start,6))
    units=[None]*len(manifest['units'])
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures=[executor.submit(one,u) for u in manifest['units']]
        for future in as_completed(futures):
            unit=future.result();units[unit['unit']]=unit
    check(artifact(assembler)==tool and manifest['source_tools']==tools(),'Assembler or splitter changed during assembly')
    checked(manifest['source'])
    receipt=dict(schema=1,scope=manifest['scope'],manifest=artifact(path),source=manifest['source'],assembler=tool,
        source_tools=manifest['source_tools'],units=units,promoted_data=manifest['promoted_data'],
        workers=workers,assembly_seconds=round(time.monotonic()-started,6),
        monolithic_reference_used=False,monolithic_binary_equivalence=False,game_started=False)
    write(path.with_name('receipt.json'),receipt);return receipt


def verify(receipt,source,expected_normalized_function_hashes):
    if not isinstance(receipt,dict):receipt=read(receipt)
    manifest=read(checked(receipt['manifest']));source=Path(source).resolve()
    check(manifest['schema']==receipt['schema']==1 and manifest['source_tools']==receipt['source_tools']==tools(),
          'Fresh splitter schema/tool identity differs')
    check(receipt['source']==manifest['source']==artifact(source),'Fresh split source differs')
    check(receipt['monolithic_reference_used'] is False and receipt['monolithic_binary_equivalence'] is False and
          manifest['monolithic_reference_used'] is False and manifest['monolithic_binary_equivalence'] is False,
          'A fresh split receipt cannot claim absent monolithic binary equivalence')
    assembler=checked(receipt['assembler']);check(assembler.name.lower()=='ml64.exe','Unexpected fresh assembler')
    raw,spans,payload,recipe=model(source,expected_normalized_function_hashes,manifest['recipe']['code_budget_bytes'])
    check(recipe==manifest['recipe'] and receipt['promoted_data']==manifest['promoted_data']==recipe['promoted_data'],
          'Fresh source recipe or private data promotions differ')
    check(len(receipt['units'])==len(manifest['units'])==len(recipe['plans']),'Fresh unit coverage differs')
    defined=set();undefined=set();objects=[];unwind={};source_rows=[]
    for plan,unit,prepared in zip(recipe['plans'],receipt['units'],manifest['units']):
        check(all(unit[k]==prepared[k]==v for k,v in plan.items()) and unit['assembly']==prepared['assembly'],
              'Fresh unit assignment or symbol contract differs')
        asm=checked(unit['assembly']);obj=checked(unit['object'])
        check(asm.parent==obj.parent==Path(manifest['manifest_path']).parent and asm.read_bytes()==render(raw,spans,payload,plan),
              'Fresh unit changed complete source functions or data payload')
        coff=P.Coff(obj);objects.append(coff)
        exports={n for n,s in coff.symbols.items() if s['section']>0 and s['storage']==2}
        imports={n for n,s in coff.symbols.items() if s['section']==0 and s['storage']==2}
        check(exports==set(plan['exports']) and imports==set(plan['imports']) and not defined&exports,
              'Actual fresh COFF defs/imports differ from preserved source')
        check(set(coff.functions)==set(plan['functions']),'Actual fresh COFF procedure coverage differs')
        defined|=exports;undefined|=imports
        if plan['role']=='data':
            check(not coff.functions and not coff.sections.get('.pdata',{}).get('size') and
                  not coff.sections.get('.xdata',{}).get('size'),'Functions/unwind moved into the sole data unit')
        else:check(all(not coff.sections.get(n,{}).get('size') for n in P.RUNTIME_DATA),'Runtime data split among code units')
        frames=P.unwind(coff);check(not unwind.keys()&frames.keys(),'Duplicate source unwind entry');unwind.update(frames)
        source_rows.append(dict(unit=unit['unit'],assembly=unit['assembly'],object=unit['object'],
                                functions=len(coff.functions),exports=len(exports),imports=len(imports)))
    check(defined-set(recipe['promoted_data'])==set(recipe['source_public']),
          'Fresh COFF promoted private code or lost original PUBLIC definitions')
    check(set(unwind)==set(recipe['framed_functions']),'Actual FRAME unwind inventory differs')
    data=objects[0];roots=recipe['static_roots'];root=data.symbols[roots['symbol']]
    bss=data.by_section[root['section']]
    check(bss['name']=='.bss' and root['value']==roots['offset']==0 and not bss['reloc'] and
          root['value']+roots['bytes']<=bss['size'],'Actual contiguous root span differs')
    counter=data.symbols[roots['count_symbol']];section=data.by_section[counter['section']]
    check(struct_u64(section['raw'],counter['value'])==roots['cells'],'Actual source root count differs')
    for row in roots['rows']:
        symbol=data.symbols[row['name']]
        check(symbol['section']==root['section'] and symbol['value']==row['offset'],
              'A source reference root moved outside its contiguous cell: '+row['name'])
    for unit in receipt['units']:checked(unit['assembly']);checked(unit['object'])
    checked(receipt['assembler']);check(artifact(source)==receipt['source'] and tools()==receipt['source_tools'],
          'A fresh source/assembler/tool changed during verification')
    unwind_hash=hashlib.sha256()
    for name,value in sorted(unwind.items()):unwind_hash.update(name.encode()+b'\0'+value)
    return dict(schema=1,verified=True,scope='source_ranges_and_actual_split_COFF_structure_only',
        source=receipt['source'],assembler=receipt['assembler'],manifest=receipt['manifest'],source_tools=receipt['source_tools'],
        source_byte_preservation_verified=True,actual_COFF_verified=True,source_functions=len(spans),
        framed_functions=len(unwind),unwind_sha256=unwind_hash.hexdigest(),units=source_rows,
        exports=sorted(defined),imports=sorted(undefined-defined),promoted_data=recipe['promoted_data'],
        static_roots=dict(section='.bss',offset=0,cells=roots['cells'],bytes=roots['bytes'],named_entries=len(roots['rows'])),
        monolithic_reference_used=False,monolithic_binary_equivalence=False,instruction_width_equivalence=False,
        linked=False,executed=False,game_started=False)


def struct_u64(raw,offset):
    check(0<=offset and offset+8<=len(raw),'Truncated scalar root count')
    return int.from_bytes(raw[offset:offset+8],'little')
