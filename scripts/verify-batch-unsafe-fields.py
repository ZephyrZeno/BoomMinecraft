"""Reconstruct source-declared field cookies and inspect actual MASM/COFF.

Field identity, names, declaration order and available address maps come from
independent source inventories. This is not proof of game or target clinit.
"""
import json
from pathlib import Path
import re
import zipfile

OWNER='jdk/internal/misc/Unsafe'
TAG=0x55464c4400000000
PAGE=1024
BUDGET=8*1024*1024

def check(value,message):
    if not value:raise ValueError(message)

def utf16(text):
    data=text.encode('utf-16le','surrogatepass')
    return tuple(int.from_bytes(data[i:i+2],'little') for i in range(0,len(data),2))

def source_contract(classes,inventory):
    owners=[c for c in classes if c['name']==OWNER and c['origin']['loader']=='bootstrap']
    check(len(owners)==1,'Missing original Unsafe field owner');c=owners[0]
    check(c['access']==0x31 and c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),
          'Unsafe field lookup source identity differs')
    ids=[i for i in c['method_ids'] if inventory[i][1:3]==('objectFieldOffset1','(Ljava/lang/Class;Ljava/lang/String;)J')]
    check(len(ids)==1,'Missing unique original Unsafe field native');i=ids[0];m=inventory[i]
    check((m[0],m[3],m[4],m[8])==(c['id'],c['origin']['sha256'],None,0x102),'Unsafe field declaration differs')
    return c,[dict(method=i,class_id=c['id'],class_sha256=c['origin']['sha256'],name='objectFieldOffset1',
                   descriptor='(Ljava/lang/Class;Ljava/lang/String;)J',access=0x102,operation=0,assembly_unit=0)]

def model(classes,maps,string_maps,capacity):
    available={m['id'] for m in maps}
    check(len(available)==len(maps),'Duplicate normal field address map')
    for m in string_maps:
        match=re.fullmatch(r'boom_field_map(\d+)',m['symbol'])
        check(match is not None,'Invalid String field map identity');i=int(match[1])
        check(i not in available,'String map duplicates normal metadata');available.add(i)
    ordered=sorted({utf16(f['name']) for c in classes for f in c['fields']})
    arena=[];names={}
    for value in ordered:names[value]=len(arena);arena.extend(value)
    rows=[];ranges=[[0,0] for _ in range(capacity)]
    kinds={'Z':(1,1),'B':(2,1),'C':(3,2),'S':(4,2),'I':(5,4),'J':(6,8),'F':(7,4),'D':(8,8)}
    for c in classes:
        check(c['id']<capacity,'Field class outside runtime type capacity')
        ranges[c['id']]=[len(rows),len(c['fields'])]
        for index,f in enumerate(c['fields']):
            descriptor=f['descriptor'];name=utf16(f['name']);id_=len(rows)
            check(0<len(name)<=65535,'Invalid source field name')
            if descriptor.startswith(('L','[')):kind,width=9,8
            else:
                check(descriptor in kinds,'Invalid source field type');kind,width=kinds[descriptor]
            check(not(f['access']&8 and id_ in available),'Static declaration has instance address map')
            rows.append(dict(id=id_,class_id=c['id'],class_sha256=c['origin']['sha256'],field_index=index,
                name=f['name'],descriptor=descriptor,access=f['access'],kind=kind,storage_bytes=width,reference=kind==9,
                name_offset=names[name],name_units=len(name),address_map=id_ if id_ in available else None))
    check(available<={r['id'] for r in rows},'Field map outside declaration inventory')
    return rows,arena,ranges

def adapter(method,cls):
    n=f'boom_m{method}'
    return (f'.code\n{n} PROC FRAME\n sub rsp,56\n .allocstack 56\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n'
        f' test rcx,rcx\n jz {n}_zero\n cmp DWORD PTR [rcx],0\n jne {n}_zero\n lea rcx,boom_class{cls}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz {n}_zero\n'
        f' mov rcx,QWORD PTR [rsp+32]\n mov rdx,QWORD PTR [rsp+40]\n call {n}_native\n add rsp,56\n ret\n{n}_zero:\n xor eax,eax\n add rsp,56\n ret\n{n} ENDP\n'
        f'{n}_native PROC\n lea r8,boom_java_unsafe_field_pool\n mov r9d,0\n jmp boom_java_unsafe_field\n{n}_native ENDP\n')

def bodies(rows,arena,ranges,cls,string,method):
    blocks=[];pages=(len(rows)+PAGE-1)//PAGE
    s='.const\nALIGN 2\nPUBLIC boom_java_unsafe_field_names\nboom_java_unsafe_field_names LABEL WORD\n'
    for at in range(0,len(arena),16):s+=' WORD '+','.join(map(str,arena[at:at+16]))+'\n'
    blocks.append(s)
    blocks.append('.const\nALIGN 8\nPUBLIC boom_java_unsafe_field_ranges\nboom_java_unsafe_field_ranges LABEL DWORD\n'+''.join(f' DWORD {a},{b}\n' for a,b in ranges))
    blocks.append('.const\nALIGN 8\nPUBLIC boom_java_unsafe_field_pages\nboom_java_unsafe_field_pages LABEL QWORD\n'+''.join(f' QWORD OFFSET boom_java_unsafe_field_page{i}\n' for i in range(pages)))
    for page,at in enumerate(range(0,len(rows),PAGE)):
        s=f'.const\nALIGN 8\nPUBLIC boom_java_unsafe_field_page{page}\nboom_java_unsafe_field_page{page} LABEL BYTE\n'
        for r in rows[at:at+PAGE]:
            address=f"OFFSET boom_field_map{r['address_map']}" if r['address_map'] is not None else '0'
            flags=int(r['reference'])|(2 if r['access']&8 else 0)
            s+=(f" DWORD {r['class_id']},{r['field_index']},{r['access']},{r['kind']}\n"
                f" DWORD {r['name_offset']},{r['name_units']},{r['storage_bytes']},{flags}\n QWORD {address},0\n DWORD {r['id']},0\n QWORD 0\n")
        blocks.append(s)
    pool=(f'.const\nALIGN 8\nPUBLIC boom_java_unsafe_field_pool\nboom_java_unsafe_field_pool DWORD 055464D50h,1,{len(ranges)},{len(rows)}\n'
        f' QWORD OFFSET boom_heap_ptr,OFFSET boom_java_class_pool,OFFSET boom_runtime_type_map,OFFSET boom_layout{cls}\n'
        f" QWORD OFFSET boom_java_unsafe_pool,OFFSET boom_layout{string['class_id']}\n"
        ' QWORD OFFSET boom_java_unsafe_field_names,OFFSET boom_java_unsafe_field_ranges,OFFSET boom_java_unsafe_field_pages\n'
        f" DWORD {len(arena)},{pages},{string['value_offset']},{string['coder_offset']},{cls},64\n QWORD 055464C4400000000h,0\n")
    blocks.append(pool+adapter(method,cls))
    result=[]
    for block in blocks:
        if not result or (result[-1] and len(result[-1])+len(block)+1>BUDGET):result.append('')
        result[-1]+=block+'\n'
    return result,len(result)-1

def verify(root,summary,plan,inventory,available,artifact,coff_symbols,file_digest):
    module=summary['unsafe_fields']
    classes=[json.loads(l) for l in (Path(plan)/'classes.jsonl').read_text(encoding='utf-8').splitlines()]
    cls,methods=source_contract(classes,inventory)
    with zipfile.ZipFile(artifact(root,summary['runtime_metadata']['index'],'runtime-metadata')) as z:
        maps=[json.loads(l) for l in z.read('fields.jsonl').splitlines()]
    shape=summary['string_literals']['source_layout']
    fields,names,ranges=model(classes,maps,shape['field_maps'],summary['runtime_metadata']['type_capacity'])
    source,unit=bodies(fields,names,ranges,cls['id'],shape,methods[0]['method']);methods[0]['assembly_unit']=unit
    expected=dict(abi=1,context_bytes=32,pool_bytes=128,record_bytes=64,page_fields=PAGE,pages=(len(fields)+PAGE-1)//PAGE,
        type_capacity=len(ranges),declared_fields=len(fields),instance_fields=sum(not(r['access']&8) for r in fields),
        address_maps=sum(r['address_map'] is not None for r in fields),name_units=len(names),native_methods=1,
        source_native_declarations=sum(bool(inventory[i][8]&0x100) for i in cls['method_ids']),class_id=cls['id'],
        class_sha256=cls['origin']['sha256'],cookie_tag=TAG)
    check(all(module.get(k)==v for k,v in expected.items()),'Unsafe field ABI/source counts differ')
    check(all(module[k] is False for k in ('target_class_initialization_required','typed_memory_natives_provided','original_initialization_executed','game_started')),
          'Unsafe field module claims unavailable execution')
    with zipfile.ZipFile(artifact(root,module['index'],'unsafe-fields')) as z:
        check(z.namelist()==['methods.jsonl','fields.jsonl','names.json','ranges.json'],'Unexpected Unsafe field records')
        check([json.loads(l) for l in z.read('methods.jsonl').splitlines()]==methods,'Unsafe field native source changed')
        check([json.loads(l) for l in z.read('fields.jsonl').splitlines()]==fields and json.loads(z.read('names.json'))==names
              and json.loads(z.read('ranges.json'))==ranges,'Unsafe field metadata differs from declarations/address maps')
    check(len(module['units'])==len(source),'Unsafe field assembly partition differs')
    defined=set();undefined=set()
    for id_,(body,unit) in enumerate(zip(source,module['units'])):
        text=artifact(root,unit['assembly'],'unsafe-fields').read_text(encoding='utf-8')
        check(unit['id']==id_ and unit['body_bytes']==len(body) and text.partition('.code\n')[2][:-5]==body and text.endswith('\nEND\n'),
              'Unsafe field generated MASM differs')
        check(unit['object'] and not unit['assembler_diagnostic'],'Unsafe field object unavailable')
        defs,refs=coff_symbols(artifact(root,unit['object'],'unsafe-fields'))
        check(not defined&defs,'Duplicate Unsafe field definitions');defined.update(defs);undefined.update(refs)
    exports={'boom_java_unsafe_field_names','boom_java_unsafe_field_ranges','boom_java_unsafe_field_pages','boom_java_unsafe_field_pool'}
    exports|={f'boom_java_unsafe_field_page{i}' for i in range(expected['pages'])}
    exports|={f"boom_m{methods[0]['method']}{suffix}" for suffix in ('','_native')}
    dependencies={f"boom_field_map{f['address_map']}" for f in fields if f['address_map'] is not None}
    dependencies|={'boom_heap_ptr','boom_java_class_pool','boom_runtime_type_map','boom_java_unsafe_pool',
        f"boom_layout{cls['id']}",f"boom_layout{shape['class_id']}",f"boom_class{cls['id']}"}
    # Class states are selected later; their symbols are generated but not in
    # the runtime metadata set of the whole-batch verifier.
    check(defined==exports and undefined-defined==dependencies|{'boom_java_unsafe_field','boom_class_ensure32'},'Unsafe field COFF dependencies differ')
    check(dependencies-{f"boom_class{cls['id']}"}<=available,'Unsafe field depends on an unprovided source map/pool')
    expected_kernels={'java_unsafe_fields.asm','field_address.asm','java_unsafe.asm','java_classes.asm','objects.asm','heap.asm'}
    check(set(module['kernel_sha256'])=={'native/runtime/'+n for n in expected_kernels},'Unsafe field runtime contract set differs')
    for name,digest in module['kernel_sha256'].items():
        check(file_digest(Path(__file__).resolve().parents[1]/name)['sha256']==digest,'Unsafe field runtime kernel changed')
    return dict(verified=True,native_methods=1,declared_fields=len(fields),address_maps=expected['address_maps'],
        opaque_field_cookies=True,typed_memory_natives_provided=False,execution_verified=False,game_started=False),defined,undefined-defined,{methods[0]['method']}
