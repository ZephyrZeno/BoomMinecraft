"""Independent source contracts and COFF for the 42 typed heap memory entries."""
import json
from pathlib import Path
import zipfile

OWNER='jdk/internal/misc/Unsafe'
TYPES=[('Boolean','Z',1),('Byte','B',2),('Char','C',3),('Short','S',4),('Int','I',5),('Long','J',6),('Float','F',7),('Double','D',8),('Reference','Ljava/lang/Object;',9)]

def check(value,message):
    if not value:raise ValueError(message)

def specs():
    result=[]
    for name,ty,kind in TYPES:
        for action in range(4):
            verb='get' if action%2==0 else 'put';suffix='Volatile' if action>=2 else ''
            desc=f'(Ljava/lang/Object;J){ty}' if action%2==0 else f'(Ljava/lang/Object;J{ty})V'
            result.append((verb+name+suffix,desc,0x101,16*action+kind))
        if kind in (5,6,9):
            result.extend([(f'compareAndSet{name}',f'(Ljava/lang/Object;J{ty}{ty})Z',0x111,64+kind),
                (f'compareAndExchange{name}',f'(Ljava/lang/Object;J{ty}{ty}){ty}',0x111,80+kind)])
    return result

def source_contract(classes,inventory):
    found=[c for c in classes if c['name']==OWNER and c['origin']['loader']=='bootstrap']
    check(len(found)==1,'Missing original typed Unsafe owner');c=found[0]
    check(c['access']==0x31 and c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Typed Unsafe source identity differs')
    methods=[]
    for name,desc,flags,op in specs():
        ids=[i for i in c['method_ids'] if inventory[i][1:3]==(name,desc)]
        check(len(ids)==1,'Missing unique typed Unsafe native: '+name);i=ids[0];m=inventory[i]
        check((m[0],m[3],m[4],m[8])==(c['id'],c['origin']['sha256'],None,flags),'Typed Unsafe source declaration differs')
        methods.append(dict(method=i,class_id=c['id'],class_sha256=c['origin']['sha256'],name=name,descriptor=desc,access=flags,operation=op,assembly_unit=0))
    check(len(methods)==42 and len({m['method'] for m in methods})==42,'Typed Unsafe operation coverage differs')
    return c,methods

def body(m):
    n=f"boom_m{m['method']}";c=m['class_id'];op=m['operation']
    return (f'.code\n{n} PROC FRAME\n sub rsp,56\n .allocstack 56\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n'
        f' test rcx,rcx\n jz {n}_zero\n cmp DWORD PTR [rcx],0\n jne {n}_zero\n lea rcx,boom_class{c}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz {n}_zero\n'
        f' mov rcx,QWORD PTR [rsp+32]\n mov rdx,QWORD PTR [rsp+40]\n call {n}_native\n add rsp,56\n ret\n{n}_zero:\n xor eax,eax\n add rsp,56\n ret\n{n} ENDP\n'
        f'{n}_native PROC\n lea r8,boom_java_unsafe_field_pool\n mov r9d,{op}\n jmp boom_java_unsafe_memory\n{n}_native ENDP\n')

def verify(root,summary,plan,inventory,available,artifact,coff_symbols,file_digest):
    s=summary['unsafe_memory'];classes=[json.loads(l) for l in (Path(plan)/'classes.jsonl').read_text().splitlines()]
    c,methods=source_contract(classes,inventory)
    expected=dict(abi=1,context_bytes=32,shared_field_pool_bytes=128,native_methods=42,class_id=c['id'],class_sha256=c['origin']['sha256'],
        vm_thread_id_counter=True,vm_thread_id_operations=[6,38,70,86],
        source_native_declarations=sum(bool(inventory[i][8]&0x100) for i in c['method_ids']))
    check(all(s.get(k)==v for k,v in expected.items()),'Typed Unsafe ABI/source counts differ')
    for flag in ('field_cookies','primitive_array_byte_views','reference_arrays','unaligned_plain_scalar_access'):check(s[flag] is True,'Missing declared typed heap domain')
    for flag in ('unaligned_atomic_access','off_heap','static_field_base','automatic_gc','original_initialization_executed','game_started'):check(s[flag] is False,'Typed memory module claims unavailable domain/execution')
    with zipfile.ZipFile(artifact(root,s['index'],'unsafe-memory')) as z:
        check(z.namelist()==['methods.jsonl'] and [json.loads(l) for l in z.read('methods.jsonl').splitlines()]==methods,'Typed Unsafe native inventory differs')
    check(len(s['units'])==1,'Typed Unsafe unit coverage differs');u=s['units'][0]
    text=artifact(root,u['assembly'],'unsafe-memory').read_text(encoding='utf-8');expected_body=''.join(body(m) for m in methods)
    check(u['id']==0 and u['body_bytes']==len(expected_body) and text.partition('.code\n')[2][:-5]==expected_body and text.endswith('\nEND\n'),'Typed Unsafe generated MASM differs')
    check(u['object'] and not u['assembler_diagnostic'],'Typed Unsafe object unavailable')
    defined,undefined=coff_symbols(artifact(root,u['object'],'unsafe-memory'))
    exports={f"boom_m{m['method']}{suffix}" for m in methods for suffix in ('','_native')}
    inputs={'boom_java_unsafe_field_pool',f"boom_class{c['id']}",'boom_class_ensure32','boom_java_unsafe_memory'}
    check(defined==exports and undefined==inputs and 'boom_java_unsafe_field_pool' in available,'Typed Unsafe COFF source dependencies differ')
    kernels={'java_unsafe_fields.asm','field_address.asm','java_unsafe.asm','objects.asm','heap.asm','runtime_types.asm','runtime_type_index.asm','thread_registry.asm'}
    check(set(s['kernel_sha256'])=={'native/runtime/'+n for n in kernels},'Typed Unsafe kernel contract set differs')
    for name,digest in s['kernel_sha256'].items():check(file_digest(Path(__file__).resolve().parents[1]/name)['sha256']==digest,'Typed Unsafe ASM kernel changed')
    return dict(verified=True,native_methods=42,typed_heap_memory=True,vm_thread_id_counter=True,vm_thread_id_operations=[6,38,70,86],off_heap=False,static_field_base=False,execution_verified=False,game_started=False),defined,undefined,{m['method'] for m in methods}
