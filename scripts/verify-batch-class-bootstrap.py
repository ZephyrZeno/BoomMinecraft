"""Prove Class bootstrap source declarations, prelinked subset and actual COFF.

The register operation confirms supplied AOT bindings. Unsupported Class natives
remain missing; the module does not certify complete registration or VM startup.
"""
import json
from pathlib import Path
import zipfile

SPECS=[('registerNatives','()V',0x10a,0),('getPrimitiveClass','(Ljava/lang/String;)Ljava/lang/Class;',0x108,10),
       ('desiredAssertionStatus0','(Ljava/lang/Class;)Z',0x10a,11)]
PRIMITIVES=[('Z','boolean'),('B','byte'),('C','char'),('S','short'),('I','int'),('J','long'),('F','float'),('D','double'),('V','void')]
CORE=[('isInterface','()Z',0x101,1),('isArray','()Z',0x101,2),('isPrimitive','()Z',0x101,3),
      ('isHidden','()Z',0x101,4),('getSuperclass','()Ljava/lang/Class;',0x101,5),
      ('isAssignableFrom','(Ljava/lang/Class;)Z',0x101,6),('isInstance','(Ljava/lang/Object;)Z',0x101,7),
      ('initClassName','()Ljava/lang/String;',0x102,8)]
DATA_EXPORTS={'boom_java_class_bootstrap_pool','boom_java_class_bootstrap_natives','boom_java_primitive_names'}


def check(value,message):
    if not value:raise ValueError(message)


def body(method,cls,op):
    n=f'boom_m{method}'
    return (f'.code\n{n} PROC FRAME\n sub rsp,56\n .allocstack 56\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n'
            f' test rcx,rcx\n jz {n}_zero\n cmp DWORD PTR [rcx],0\n jne {n}_zero\n lea rcx,boom_class{cls}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz {n}_zero\n'
            f' mov rcx,QWORD PTR [rsp+32]\n mov rdx,QWORD PTR [rsp+40]\n call {n}_native\n add rsp,56\n ret\n{n}_zero:\n xor eax,eax\n add rsp,56\n ret\n{n} ENDP\n'
            f'{n}_native PROC\n lea r8,boom_java_class_bootstrap_pool\n mov r9d,{op}\n jmp boom_java_class_bootstrap\n{n}_native ENDP\n')


def data(cls,primitives,registration):
    text='.const\nALIGN 8\nPUBLIC boom_java_class_bootstrap_natives\nboom_java_class_bootstrap_natives LABEL BYTE\n'
    for r in registration:text+=f" DWORD {r['operation']},{r['method']}\n QWORD OFFSET boom_m{r['method']}_native\n DWORD {r['access']},0\n"
    text+='ALIGN 8\nPUBLIC boom_java_primitive_names\nboom_java_primitive_names LABEL BYTE\n'
    for i,r in enumerate(primitives):text+=f" QWORD OFFSET boom_java_primitive_name{i}\n DWORD {len(r['name'])},{r['type_id']}\n"
    for i,r in enumerate(primitives):text+=f"ALIGN 2\nboom_java_primitive_name{i} WORD "+','.join(str(ord(c)) for c in r['name'])+'\n'
    text+=(f'.data\nALIGN 8\nPUBLIC boom_java_class_bootstrap_pool\nboom_java_class_bootstrap_pool DWORD 04A434254h,1,0,{len(registration)}\n'
           f' QWORD OFFSET boom_java_class_pool,OFFSET boom_java_string_literal_pool,OFFSET boom_java_class_bootstrap_natives,OFFSET boom_java_primitive_names\n DWORD 9,0,0,0,{cls},0\n QWORD 0\n')
    return text


def source_contract(classes,inventory,primitive_types,core_natives):
    found=[c for c in classes if c['name']=='java/lang/Class' and c['origin']['loader']=='bootstrap']
    check(len(found)==1,'Class bootstrap identity is ambiguous');cls=found[0]
    check(cls['access']==0x31 and cls['origin']['source_id']=='jdk:java.base' and not cls['origin'].get('generated'),
          'Class bootstrap requires original java.base Class')
    methods=[]
    for name,desc,access,op in SPECS:
        rows=[(i,inventory[i]) for i in cls['method_ids'] if inventory[i][1:3]==(name,desc)]
        check(len(rows)==1,'Missing unique Class bootstrap declaration');i,m=rows[0]
        check(m[0]==cls['id'] and m[3]==cls['origin']['sha256'] and m[4] is None and m[8]==access,'Class bootstrap native source differs')
        methods.append(dict(method=i,class_id=cls['id'],class_sha256=cls['origin']['sha256'],name=name,descriptor=desc,access=access,operation=op,assembly_unit=0))
    primitives=[]
    for descriptor,name in PRIMITIVES:
        rows=[t for t in primitive_types if t['kind']==0 and t['name']==descriptor]
        check(len(rows)==1 and rows[0]['defining_loader']=='bootstrap','Primitive identity differs')
        primitives.append(dict(descriptor=descriptor,name=name,type_id=rows[0]['id']))
    registration=[]
    for name,desc,access,op in CORE:
        ids=[i for i in cls['method_ids'] if inventory[i][1:3]==(name,desc)]
        check(len(ids)==1,'Prelinked native declaration is missing');i=ids[0];m=inventory[i]
        check(m[0]==cls['id'] and m[3]==cls['origin']['sha256'] and m[4] is None and m[8]==access,
              'Prelinked native source declaration differs')
        rows=[r for r in core_natives if r['method']==i]
        check(len(rows)==1 and rows[0]['class_id']==cls['id'] and rows[0]['operation']==op and rows[0]['access']==access,
              'Prelinked native target differs')
        registration.append(dict(operation=op,method=i,access=access))
    registration += [dict(operation=m['operation'],method=m['method'],access=m['access']) for m in methods if m['operation']]
    registration.sort(key=lambda r:r['operation'])
    check([r['operation'] for r in registration]==list(range(1,9))+[10,11],'Prelinked Class subset differs')
    return cls,methods,primitives,registration


def verify(root,summary,plan,inventory,available,artifact,coff_symbols,file_digest):
    s=summary['class_bootstrap'];classes=[json.loads(l) for l in (Path(plan)/'classes.jsonl').read_text(encoding='utf-8').splitlines()]
    with zipfile.ZipFile(artifact(root,summary['runtime_metadata']['index'],'runtime-metadata')) as z:
        types=[json.loads(l) for l in z.read('types.jsonl').splitlines()]
    with zipfile.ZipFile(artifact(root,summary['class_literals']['index'],'class-literals')) as z:
        core=[json.loads(l) for l in z.read('methods.jsonl').splitlines()]
    cls,methods,primitives,registration=source_contract(classes,inventory,types,core)
    check((s['abi'],s['context_bytes'],s['pool_bytes'],s['native_methods'],s['class_id'],s['class_sha256'],s['registered_prelinked_methods'])==
          (1,32,80,3,cls['id'],cls['origin']['sha256'],10),'Class bootstrap ABI/count differs')
    native_total=sum(bool(inventory[i][8]&0x100) for i in cls['method_ids'])
    check(s['source_native_declarations']==native_total and native_total>len(registration),'Class unprovided native count differs')
    check(s['registered_methods_are_subset'] and s['unsupported_natives_remain_unprovided'],'Unprovided Class entries were hidden')
    for k in ['system_assertions_enabled','application_assertions_enabled','class_assertion_overrides_supported',
              'original_class_initialization_executed','full_class_native_registration_complete','game_started']:
        check(s[k] is False,'Class generation overstates execution/configuration: '+k)
    with zipfile.ZipFile(artifact(root,s['index'],'class-bootstrap')) as z:
        for name,expected in [('methods.jsonl',methods),('primitives.jsonl',primitives),('registration.jsonl',registration)]:
            check([json.loads(l) for l in z.read(name).splitlines()]==expected,'Class bootstrap source records differ: '+name)
    check(len(s['units'])==1,'Class bootstrap unit coverage differs');unit=s['units'][0]
    text=artifact(root,unit['assembly'],'class-bootstrap').read_text(encoding='utf-8')
    expected=data(cls['id'],primitives,registration)+''.join(body(m['method'],cls['id'],m['operation']) for m in methods)
    check(text.partition('.code\n')[2][:-5]==expected and text.endswith('\nEND\n'),'Class bootstrap MASM differs')
    check(unit['object'] is not None and unit['assembler_diagnostic'] is None,'Class bootstrap assembly failed')
    defined,undefined=coff_symbols(artifact(root,unit['object'],'class-bootstrap'))
    required=DATA_EXPORTS|{f"boom_m{m['method']}{suffix}" for m in methods for suffix in ('','_native')}
    source={'boom_java_class_pool','boom_java_string_literal_pool',f"boom_class{cls['id']}"}|{f"boom_m{m['method']}_native" for m in core if m['class_id']==cls['id']}
    runtime={'boom_class_ensure32','boom_java_class_bootstrap'}
    check(defined==required and undefined==source|runtime and source<=available,'Class bootstrap COFF differs')
    check(file_digest(Path(__file__).resolve().parents[1]/'native/runtime/java_class_bootstrap.asm')['sha256']==s['kernel_sha256'],'Class bootstrap MASM kernel changed')
    return dict(verified=True,native_methods=3,prelinked_Class_bindings=10,full_Class_native_registration_complete=False,
                scope='original_Class_declarations_default_assertion_config_MASM_COFF_only',execution_verified=False,game_started=False),defined,undefined,{m['method'] for m in methods}
