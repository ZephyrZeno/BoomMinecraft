"""Verify standard concat expansion from source constants through actual COFF."""
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import zipfile


OWNER='java/lang/invoke/StringConcatFactory'
STRING='Ljava/lang/String;'
BOOTSTRAPS={
 'makeConcat':'(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;',
 'makeConcatWithConstants':'(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/invoke/CallSite;'}


def check(value,message):
    if not value:raise ValueError(message)


def parser():
    spec=importlib.util.spec_from_file_location('concat_source_descriptor',Path(__file__).with_name('plan-protocol-expansion.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.signature


def source_contract(classes,inventory,lookup):
    bsm,string=lookup('bootstrap',OWNER),lookup('bootstrap','java/lang/String')
    for id_ in (bsm,string):
        c=classes[id_]
        check(c['origin']['source_id']=='jdk:java.base' and c['origin'].get('generated') is None and c['access']&0x611==0x11,
              'Concat requires original final bootstrap source')
    def method(cls,name,desc):
        ids=[i for i in classes[cls]['method_ids'] if inventory[i][1:3]==(name,desc)]
        check(len(ids)==1 and inventory[ids[0]][8]&0x109==9 and not inventory[ids[0]][8]&0x400 and inventory[ids[0]][4] is not None,
              'Concat source bootstrap/conversion method declaration differs')
        return ids[0]
    return dict(class_id=bsm,class_sha256=classes[bsm]['origin']['sha256'],
                methods={name:method(bsm,name,desc) for name,desc in sorted(BOOTSTRAPS.items())},
                string_class=string,string_sha256=classes[string]['origin']['sha256'],
                conversion_methods={ty:method(string,'valueOf',f'({ty}){STRING}') for ty in ('D','F','Ljava/lang/Object;')})


def expand(source,constants,converters,signature):
    b=source['bootstrap']
    check(b['owner']==OWNER and b['reference_kind']==6 and not b['interface'] and
          b['descriptor']==BOOTSTRAPS.get(b['name']),'Concat bootstrap identity/signature unsupported')
    args,result=signature(source['descriptor'])
    check(result==STRING and sum(2 if a in ('J','D') else 1 for a in args)<=200,'Concat descriptor contract unsupported')
    operations=[];conversions=[]
    for index,ty in enumerate(args):
        operation={'B':1,'S':1,'I':1,'J':2,'Z':3,'C':4,STRING:5}.get(ty)
        if operation is None:
            operation=5;conversion=ty if ty in ('F','D') else 'Ljava/lang/Object;'
            conversions.append(dict(argument=index,method=converters[conversion],descriptor=f'({conversion}){STRING}'))
        operations.append(operation)
    ids=source['arguments']
    if b['name']=='makeConcat':
        check(not ids,'makeConcat static constants unsupported');recipe=[1]*len(args);values=[]
    else:
        check(ids and 'StringUtf16' in constants[str(ids[0])],'Concat recipe is not static String')
        recipe=constants[str(ids[0])]['StringUtf16'];values=[]
        for id_ in ids[1:]:
            check('StringUtf16' in constants[str(id_)],'Concat static constant requires runtime conversion')
            values.append(constants[str(id_)]['StringUtf16'])
    parts=[];literal=[];dynamic=fixed=0
    for unit in recipe:
        if unit==1:
            if literal:parts.append(dict(kind='literal',utf16=literal));literal=[]
            check(dynamic<len(args),'Too many concat argument markers')
            parts.append(dict(kind='argument',index=dynamic,operation=operations[dynamic]));dynamic+=1
        elif unit==2:
            check(fixed<len(values),'Too many concat constant markers');literal.extend(values[fixed]);fixed+=1
        else:literal.append(unit)
    if literal:parts.append(dict(kind='literal',utf16=literal))
    check(dynamic==len(args) and fixed==len(values) and len(parts)<=65535,'Concat marker/part contract differs')
    return dict(arguments=args,parts=parts,conversions=conversions)


def body(label,plan,bsm,shape):
    out=f'.const\nALIGN 8\n{label}_rows LABEL BYTE\n'
    if not plan['parts']:out+=' DWORD 0,0\n QWORD 0,0\n'
    for i,p in enumerate(plan['parts']):
        out+=(f" DWORD 0,0\n QWORD OFFSET {label}_text{i},{len(p['utf16'])}\n" if p['kind']=='literal' else
              f" DWORD {p['operation']},{p['index']}\n QWORD 0,0\n")
    for i,p in enumerate(plan['parts']):
        if p['kind']=='literal':
            out+=f'ALIGN 2\n{label}_text{i} LABEL WORD\n'
            for j in range(0,len(p['utf16']),16):out+=' WORD '+','.join(f'0{u:04X}h' for u in p['utf16'][j:j+16])+'\n'
    out+=f"ALIGN 8\n{label}_pool DWORD 04A434E43h,1,{len(plan['parts'])},{len(plan['arguments'])}\n QWORD OFFSET {label}_rows,OFFSET boom_heap_ptr,OFFSET boom_layout{shape['class_id']}\n DWORD {shape['value_offset']},{shape['coder_offset']},{shape['hash_offset']},{shape['hash_is_zero_offset']},1,0,32,0\n QWORD 0\n"
    frame=((80+len(plan['arguments'])*8+15)//16)*16+8
    out+=f'.code\n{label} PROC FRAME\n sub rsp,{frame}\n .allocstack {frame}\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n test rcx,rcx\n jz {label}_zero\n cmp DWORD PTR [rcx],0\n jne {label}_zero\n'
    if plan['arguments']:out+=f' test rdx,rdx\n jnz {label}_args\n mov DWORD PTR [rcx],7\n jmp {label}_zero\n{label}_args:\n'
    out+=f' lea rcx,boom_class{bsm}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz {label}_zero\n mov r10,QWORD PTR [rsp+40]\n'
    for i in range(len(plan['arguments'])):out+=f' mov rax,QWORD PTR [r10+{i*8}]\n mov QWORD PTR [rsp+{80+i*8}],rax\n'
    for c in plan['conversions']:
        offset=80+c['argument']*8
        out+=f" mov rcx,QWORD PTR [rsp+32]\n lea rdx,[rsp+{offset}]\n call boom_m{c['method']}\n mov r10,QWORD PTR [rsp+32]\n cmp DWORD PTR [r10],0\n jne {label}_zero\n mov QWORD PTR [rsp+{offset}],rax\n"
    out+=f' mov rcx,QWORD PTR [rsp+32]\n lea rdx,[rsp+80]\n lea r8,{label}_pool\n call boom_java_concat\n add rsp,{frame}\n ret\n{label}_zero:\n xor eax,eax\n add rsp,{frame}\n ret\n{label} ENDP\n'
    return out


def verify(root,batch,plan_path,inventory,requests,available,artifact,coff_symbols,file_digest):
    root=Path(root);s=batch['string_concat'];shape=batch['string_literals']['source_layout']
    check((s['abi'],s['context_bytes'],s['pool_bytes'])==(1,32,80) and s['source_layout']==shape,'Concat ABI/normal String layout differs')
    check(s['bootstrap_class_initialization_required'] and all(s[k] is False for k in
          ('bootstrap_class_initialization_executed','active_roots_registered','linked','game_started')),'Concat claims unsupported initialization/GC/link execution')
    classes=list(map(json.loads,(Path(plan_path)/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    spec=importlib.util.spec_from_file_location('concat_source_lookup',Path(__file__).with_name('verify-batch-metadata.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);lookup,_,_,_=m.source_model(classes)
    bootstrap=source_contract(classes,inventory,lookup);check(s['bootstrap']==bootstrap,'Concat bootstrap/conversion source identity differs')
    signature=parser();expected=[];rejected=[];per_unit=defaultdict(list);imports=defaultdict(set)
    with zipfile.ZipFile(artifact(root,s['index'],'string-concat')) as z:
        check(z.namelist()==['sites.jsonl'],'Concat source index coverage differs')
        actual=list(map(json.loads,z.read('sites.jsonl').splitlines()))
    check([r['label'] for r in actual]==sorted(requests.concat_sites),'Concat call-site coverage/order differs')
    converted=0
    for row in actual:
        request=requests.concat_sites[row['label']];identity=request['site']
        check(all(row[k]==v for k,v in identity.items()) and row['caller_methods']==sorted(request['methods']),'Concat caller/Code provenance differs')
        constants=requests.constants[row['caller_class']];source=constants[str(row['constant'])]['InvokeDynamic']
        check(row['source']==source and row['descriptor']==source['descriptor'] and row['opcode']==186,'Concat original bootstrap differs')
        binding=request['binding'];b=source['bootstrap']
        check(binding['protocol']==b['owner']+'.'+b['name']+b['descriptor'],'Concat binding differs from source bootstrap')
        try:
            check(lookup(classes[row['caller_class']]['origin']['loader'],OWNER)==bootstrap['class_id'],'Concat bootstrap defining loader differs')
            plan=expand(source,constants,bootstrap['conversion_methods'],signature)
        except ValueError:
            check(row['plan'] is None and row['assembly_unit'] is None and isinstance(row['diagnostic'],str) and row['diagnostic'],
                  'Unsupported concat was silently provided')
            rejected.append(row['label']);continue
        check(row['plan']==plan and row['diagnostic'] is None and isinstance(row['assembly_unit'],int),'Concat lowering plan differs')
        unit=row['assembly_unit'];check(0<=unit<len(s['units']),'Concat unit index invalid')
        per_unit[unit].append((row['label'],body(row['label'],plan,bootstrap['class_id'],shape)))
        imports[unit].update({'boom_heap_ptr',f"boom_layout{shape['class_id']}",f"boom_class{bootstrap['class_id']}",'boom_class_ensure32','boom_java_concat'})
        imports[unit].update(f"boom_m{c['method']}" for c in plan['conversions'])
        converted+=bool(plan['conversions']);expected.append(row['label'])
    requests.reject_concat(rejected)
    check((s['sites'],s['generated_sites'],s['rejected_sites'],s['source_conversion_sites'])==(len(actual),len(expected),len(rejected),converted),'Concat generation/rejection accounting differs')
    check(set(per_unit)==set(range(len(s['units']))),'Concat unit coverage differs')
    all_defined=set();all_undefined=set()
    for i,u in enumerate(s['units']):
        check(u['id']==i and u['object'] is not None and u['assembler_diagnostic'] is None,'Concat actual assembly failed')
        text=artifact(root,u['assembly'],'string-concat').read_text(encoding='utf-8')
        check(text.partition('.code\n')[2][:-5]==''.join(b+'\n' for _,b in per_unit[i]) and text.endswith('\nEND\n'),
              'Concat MASM differs from source recipe/conversion/bootstrap model')
        defined,undefined=coff_symbols(artifact(root,u['object'],'string-concat'))
        check(defined=={label for label,_ in per_unit[i]} and undefined==imports[i],'Concat COFF definitions/imports differ')
        source_imports=imports[i]-{'boom_java_concat','boom_class_ensure32'}
        check(source_imports<=available,'Concat required source method/type/class not generated')
        check(not all_defined&defined,'Duplicate concat call-site definition');all_defined.update(defined);all_undefined.update(undefined)
    check(file_digest(Path(__file__).resolve().parents[1]/'native/runtime/java_concat.asm')['sha256']==s['kernel_sha256'],'Concat assembly kernel changed')
    return dict(verified=True,scope='source_concat_protocol_lowering_MASM_COFF_only',generated_sites=len(expected),rejected_sites=len(rejected),
                original_conversion_sites=converted,bootstrap_initialization_required=True,execution_verified=False,game_started=False),all_defined,all_undefined
