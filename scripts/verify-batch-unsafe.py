"""Verify original Unsafe declarations, normal array ABI and real COFF bindings.

This confirms a bootstrap subset; it never claims arbitrary Unsafe memory APIs.
"""
import json
from pathlib import Path
import zipfile

OWNER='jdk/internal/misc/Unsafe'
CONSTANTS='jdk/internal/misc/UnsafeConstants'
SPECS=[('registerNatives','()V',0x10a,0),('arrayBaseOffset0','(Ljava/lang/Class;)I',0x102,1),
       ('arrayIndexScale0','(Ljava/lang/Class;)I',0x102,2),('fullFence','()V',0x101,3)]
FIELDS=[('ADDRESS_SIZE0','I'),('PAGE_SIZE','I'),('BIG_ENDIAN','Z'),('UNALIGNED_ACCESS','Z'),('DATA_CACHE_LINE_FLUSH_SIZE','I')]
DATA_EXPORTS={'boom_java_unsafe_pool','boom_java_unsafe_bindings','boom_java_unsafe_scales','boom_java_unsafe_constant_cells'}


def check(value,message):
    if not value:raise ValueError(message)


def source_contract(classes,inventory,types,states,capacity=None):
    def original(name,flags):
        found=[c for c in classes if c['name']==name and c['origin']['loader']=='bootstrap']
        check(len(found)==1,'Missing unique original '+name);c=found[0]
        check(c['access']==flags and c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),
              'Original VM source identity differs: '+name)
        return c
    cls=original(OWNER,0x31);constants=original(CONSTANTS,0x30);methods=[]
    for name,desc,flags,op in SPECS:
        ids=[i for i in cls['method_ids'] if inventory[i][1:3]==(name,desc)]
        check(len(ids)==1,'Missing unique Unsafe native');i=ids[0];m=inventory[i]
        check((m[0],m[3],m[4],m[8])==(cls['id'],cls['origin']['sha256'],None,flags),'Unsafe source declaration differs')
        methods.append(dict(method=i,class_id=cls['id'],class_sha256=cls['origin']['sha256'],name=name,
                            descriptor=desc,access=flags,operation=op,assembly_unit=0))
    check(constants['fields']==[dict(name=n,descriptor=d,access=0x18) for n,d in FIELDS],'UnsafeConstants field declarations differ')
    state=states[constants['id']];init=state['initializer']
    check(state['source_sha256']==constants['origin']['sha256'] and not state['diagnostic']
          and state.get('vm_post_initializer')=='unsafe_constants' and init and init['assembly_emitted'],
          'UnsafeConstants original initialization/hook unavailable')
    m=inventory[init['method']]
    check((m[0],m[1],m[2],m[3],m[4],m[8])==
          (constants['id'],'<clinit>','()V',constants['origin']['sha256'],init['code_sha256'],8),
          'UnsafeConstants original Code identity differs')
    check(len(state['fields'])==5 and all(f['constant'] is None and f['initial_bits']==0 and not f['reference'] for f in state['fields']),
          'UnsafeConstants must begin at source default values')
    ids=[t['id'] for t in types]
    if capacity is None:capacity=len(types)
    check(ids==sorted(set(ids)) and all(isinstance(i,int) and 0<=i<capacity for i in ids),'Unsafe type identity coverage differs')
    scales=[0]*capacity
    for t in types:
        if t['kind']==3:scales[t['id']]={'[Z':1,'[B':1,'[C':2,'[S':2,'[I':4,'[F':4}.get(t['name'],8)
    return cls,constants,methods,scales,init


def body(method,cls,op):
    n=f'boom_m{method}'
    return (f'.code\n{n} PROC FRAME\n sub rsp,56\n .allocstack 56\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n'
            f' test rcx,rcx\n jz {n}_zero\n cmp DWORD PTR [rcx],0\n jne {n}_zero\n lea rcx,boom_class{cls}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz {n}_zero\n'
            f' mov rcx,QWORD PTR [rsp+32]\n mov rdx,QWORD PTR [rsp+40]\n call {n}_native\n add rsp,56\n ret\n{n}_zero:\n xor eax,eax\n add rsp,56\n ret\n{n} ENDP\n'
            f'{n}_native PROC\n lea r8,boom_java_unsafe_pool\n mov r9d,{op}\n jmp boom_java_unsafe\n{n}_native ENDP\n')


def data(cls,constants,scales,methods):
    text='.const\nALIGN 8\nPUBLIC boom_java_unsafe_bindings\nboom_java_unsafe_bindings LABEL BYTE\n'
    for m in methods:
        if m['operation']:text+=f" DWORD {m['operation']},{m['method']}\n QWORD OFFSET boom_m{m['method']}_native\n DWORD {m['access']},0\n"
    text+='PUBLIC boom_java_unsafe_scales\nboom_java_unsafe_scales LABEL DWORD\n'
    for i in range(0,len(scales),16):text+=' DWORD '+','.join(map(str,scales[i:i+16]))+'\n'
    text+='ALIGN 8\nPUBLIC boom_java_unsafe_constant_cells\nboom_java_unsafe_constant_cells LABEL QWORD\n'
    for i in range(5):text+=f' QWORD OFFSET boom_s{constants}_{i}\n'
    return text+(f'.data\nALIGN 8\nPUBLIC boom_java_unsafe_pool\nboom_java_unsafe_pool DWORD 04A554E53h,1,0,3\n'
                 f' QWORD OFFSET boom_java_class_pool,OFFSET boom_runtime_type_map,OFFSET boom_heap_ptr,OFFSET boom_layout{cls}\n'
                 ' QWORD OFFSET boom_java_unsafe_bindings,OFFSET boom_java_unsafe_scales\n'
                 f' DWORD {len(scales)},{cls}\n QWORD OFFSET boom_java_unsafe_constant_cells\n')


def verify(root,summary,plan,inventory,available,artifact,coff_symbols,file_digest):
    s=summary['unsafe_bootstrap'];classes=[json.loads(l) for l in (Path(plan)/'classes.jsonl').read_text(encoding='utf-8').splitlines()]
    with zipfile.ZipFile(artifact(root,summary['runtime_metadata']['index'],'runtime-metadata')) as z:
        types=[json.loads(l) for l in z.read('types.jsonl').splitlines()]
    with zipfile.ZipFile(artifact(root,summary['class_state']['index'],'class-state')) as z:
        states={r['class_id']:r for r in map(json.loads,z.read('classes.jsonl').splitlines())}
    cls,constants,methods,scales,init=source_contract(classes,inventory,types,states,summary['runtime_metadata']['type_capacity'])
    expected=dict(abi=1,context_bytes=32,pool_bytes=80,native_methods=4,class_id=cls['id'],class_sha256=cls['origin']['sha256'],
                  constants_class_id=constants['id'],constants_class_sha256=constants['origin']['sha256'],
                  constants_initializer=init['method'],constants_initializer_sha256=init['code_sha256'],
                  registered_prelinked_methods=3,type_capacity=len(scales),
                  source_native_declarations=sum(bool(inventory[i][8]&0x100) for i in cls['method_ids']))
    check(all(s[k]==v for k,v in expected.items()),'Unsafe native ABI/source counts differ')
    check(s['unsupported_natives_remain_unprovided'] and not s['original_initialization_executed'] and not s['game_started'],
          'Unsafe translation claims unverified execution')
    with zipfile.ZipFile(artifact(root,s['index'],'unsafe-bootstrap')) as z:
        check(z.namelist()==['methods.jsonl','scales.json'],'Unexpected Unsafe index records')
        check([json.loads(l) for l in z.read('methods.jsonl').splitlines()]==methods and json.loads(z.read('scales.json'))==scales,
              'Unsafe native/array metadata differs from source')
    check(len(s['units'])==1,'Unsafe native unit coverage differs');unit=s['units'][0]
    source=artifact(root,unit['assembly'],'unsafe-bootstrap').read_text(encoding='utf-8')
    expected=data(cls['id'],constants['id'],scales,methods)+''.join(body(m['method'],cls['id'],m['operation']) for m in methods)
    check(source.partition('.code\n')[2][:-5]==expected and source.endswith('\nEND\n'),'Unsafe generated MASM differs')
    check(unit['object'] and not unit['assembler_diagnostic'],'Unsafe COFF assembly unavailable')
    defined,undefined=coff_symbols(artifact(root,unit['object'],'unsafe-bootstrap'))
    required=DATA_EXPORTS|{f"boom_m{m['method']}{suffix}" for m in methods for suffix in ('','_native')}
    inputs={'boom_java_class_pool','boom_runtime_type_map','boom_heap_ptr',f"boom_layout{cls['id']}",f"boom_class{cls['id']}"}
    inputs|={f"boom_s{constants['id']}_{i}" for i in range(5)}
    check(defined==required and undefined==inputs|{'boom_class_ensure32','boom_java_unsafe'} and inputs<=available,
          'Unsafe real COFF source dependencies differ')
    check(file_digest(Path(__file__).resolve().parents[1]/'native/runtime/java_unsafe.asm')['sha256']==s['kernel_sha256'],
          'Unsafe ASM kernel changed')
    return dict(verified=True,native_methods=4,prelinked_Unsafe_bindings=3,execution_verified=False,game_started=False),defined,undefined,{m['method'] for m in methods}
