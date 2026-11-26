"""Source Runtime constructor/natives, real heap metadata and COFF adapters."""
import importlib.util
import json
from pathlib import Path
import zipfile

SPECS=[('availableProcessors','()I',0x101,0),('freeMemory','()J',0x101,1),
       ('totalMemory','()J',0x101,2),('maxMemory','()J',0x101,3)]
KERNELS=['runtime_resources.asm','heap.asm','runtime_types.asm','runtime_type_index.asm']


def check(v,message):
    if not v:raise ValueError(message)


def source_contract(classes,inventory):
    found=[c for c in classes if c['name']=='java/lang/Runtime' and c['origin']['loader']=='bootstrap']
    check(len(found)==1,'Missing unique original Runtime');c=found[0]
    check(c['access']==0x21 and c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Runtime source identity differs')
    constructors=[inventory[i] for i in c['method_ids'] if inventory[i][1]=='<init>']
    check(len(constructors)==1 and constructors[0][0]==c['id'] and constructors[0][2]=='()V'
          and constructors[0][3]==c['origin']['sha256'] and constructors[0][4] and constructors[0][8]==2,
          'Runtime private original Java constructor differs')
    methods=[]
    for n,d,f,o in SPECS:
        ids=[i for i in c['method_ids'] if inventory[i][1:3]==(n,d)]
        check(len(ids)==1,'Missing unique Runtime resource native');i=ids[0];m=inventory[i]
        check((m[0],m[3],m[4],m[8])==(c['id'],c['origin']['sha256'],None,f),'Runtime native declaration differs')
        methods.append(dict(method=i,class_id=c['id'],class_sha256=c['origin']['sha256'],name=n,descriptor=d,access=f,operation=o,assembly_unit=0))
    return c,methods


def data(cls):
    return ('.data\nALIGN 8\nPUBLIC boom_java_runtime_pool\nboom_java_runtime_pool DWORD 0544E5552h,1\n'
            f' QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_t{cls}\n QWORD 0,0,0,0\n')


def body(method,cls,op):
    spec=importlib.util.spec_from_file_location('runtime_adapter_model',Path(__file__).with_name('verify-batch-class-bootstrap.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.body(method,cls,op).replace('boom_java_class_bootstrap_pool','boom_java_runtime_pool').replace('jmp boom_java_class_bootstrap','jmp boom_runtime_resource')


def verify(root,summary,plan,inventory,available,artifact,coff_symbols,file_digest):
    s=summary['runtime_resources'];classes=list(map(json.loads,(Path(plan)/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    cls,methods=source_contract(classes,inventory)
    expected=dict(abi=1,context_bytes=32,pool_bytes=64,native_methods=4,class_id=cls['id'],class_sha256=cls['origin']['sha256'],
        source_native_declarations=sum(bool(inventory[i][8]&0x100) for i in cls['method_ids']),
        memory_counters='Heap1 committed capacity minus occupied block spans',processor_policy='windows-default-group-and-job-affinity')
    check(all(s[k]==v for k,v in expected.items()),'Runtime resource source/ABI policy differs')
    check(s['exact_runtime_receiver'] and not s['override_dispatch_complete'] and s['unsupported_natives_remain_unprovided'],
          'Runtime receiver/unprovided service scope overstated')
    check(not any(s[k] for k in ('original_initialization_executed','automatic_gc','game_started')),'Runtime translation claims unverified execution')
    with zipfile.ZipFile(artifact(root,s['index'],'runtime-resources')) as z:
        check(z.namelist()==['methods.jsonl'] and list(map(json.loads,z.read('methods.jsonl').splitlines()))==methods,'Runtime native source records differ')
    check(len(s['units'])==1,'Runtime resource units differ');unit=s['units'][0]
    text=artifact(root,unit['assembly'],'runtime-resources').read_text(encoding='utf-8')
    expected=data(cls['id'])+''.join(body(m['method'],cls['id'],m['operation']) for m in methods)
    check(text.partition('.code\n')[2][:-5]==expected and text.endswith('\nEND\n'),'Runtime pool/adapters differ')
    check(unit['object'] and not unit['assembler_diagnostic'],'Runtime resource COFF unavailable')
    defined,undefined=coff_symbols(artifact(root,unit['object'],'runtime-resources'))
    check(defined=={'boom_java_runtime_pool'}|{f"boom_m{m['method']}{x}" for m in methods for x in ('','_native')},'Runtime COFF definitions differ')
    source={f"boom_class{cls['id']}",f"boom_t{cls['id']}",'boom_heap_ptr','boom_runtime_type_map'}
    check(source<=available and undefined==source|{'boom_class_ensure32','boom_runtime_resource'},'Runtime COFF source/runtime imports differ')
    check(set(s['kernel_sha256'])=={'native/runtime/'+n for n in KERNELS},'Runtime kernel dependencies differ')
    for p,d in s['kernel_sha256'].items():check(file_digest(Path(__file__).resolve().parents[1]/p)['sha256']==d,'Runtime kernel changed: '+p)
    return dict(verified=True,native_methods=4,exact_Runtime_receiver=True,automatic_gc=False,execution_verified=False,game_started=False),defined,undefined,{m['method'] for m in methods}
