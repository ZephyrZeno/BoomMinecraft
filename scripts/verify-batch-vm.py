"""Prove normal-source VM registration adapters and runtime-owned clock binding."""
import importlib.util
import json
from pathlib import Path
import zipfile

SPECS=[('initialize','()V',0x10a,0),('getNanoTimeAdjustment','(J)J',0x109,1)]
DATA='.data\nALIGN 8\nPUBLIC boom_java_vm_pool\nboom_java_vm_pool DWORD 0564D5247h,2,0,1\n QWORD 0,0\n'


def check(value,message):
    if not value:raise ValueError(message)


def source_contract(classes,inventory):
    found=[c for c in classes if c['name']=='jdk/internal/misc/VM' and c['origin']['loader']=='bootstrap']
    check(len(found)==1,'Missing unique source VM');c=found[0]
    check(c['access']==0x21 and c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'VM source identity differs')
    methods=[]
    for name,desc,flags,op in SPECS:
        ids=[i for i in c['method_ids'] if inventory[i][1:3]==(name,desc)]
        check(len(ids)==1,'Missing unique source VM native');i=ids[0];m=inventory[i]
        check((m[0],m[3],m[4],m[8])==(c['id'],c['origin']['sha256'],None,flags),'VM native declaration differs')
        methods.append(dict(method=i,class_id=c['id'],class_sha256=c['origin']['sha256'],name=name,
                            descriptor=desc,access=flags,operation=op,assembly_unit=0))
    return c,methods


def body(method,cls,op):
    spec=importlib.util.spec_from_file_location('vm_source_adapter_model',Path(__file__).with_name('verify-batch-class-bootstrap.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.body(method,cls,op).replace('boom_java_class_bootstrap_pool','boom_java_vm_pool').replace('jmp boom_java_class_bootstrap','jmp boom_vm_native')


def verify(root,summary,plan,inventory,available,artifact,coff_symbols,file_digest):
    s=summary['vm_registration'];classes=[json.loads(l) for l in (Path(plan)/'classes.jsonl').read_text(encoding='utf-8').splitlines()]
    cls,methods=source_contract(classes,inventory)
    expected=dict(abi=1,context_bytes=32,pool_abi=2,pool_bytes=32,native_methods=2,class_id=cls['id'],
                  class_sha256=cls['origin']['sha256'],registered_prelinked_methods=1,
                  source_native_declarations=sum(bool(inventory[i][8]&0x100) for i in cls['method_ids']))
    check(all(s[k]==v for k,v in expected.items()),'VM source counts/ABI differ')
    check(s['unsupported_natives_remain_unprovided'] and not s['original_initialization_executed']
          and not s['java_boot_level_changed_by_native'] and not s['game_started'],'VM generation overstates semantics/execution')
    with zipfile.ZipFile(artifact(root,s['index'],'vm-registration')) as z:
        check(z.namelist()==['methods.jsonl'] and list(map(json.loads,z.read('methods.jsonl').splitlines()))==methods,'VM source native index differs')
    check(len(s['units'])==1,'VM native units differ');unit=s['units'][0]
    text=artifact(root,unit['assembly'],'vm-registration').read_text(encoding='utf-8')
    expected=DATA+''.join(body(m['method'],cls['id'],m['operation']) for m in methods)
    check(text.partition('.code\n')[2][:-5]==expected and text.endswith('\nEND\n'),'VM MASM adapters/pool differ')
    check(unit['object'] and not unit['assembler_diagnostic'],'VM native COFF unavailable')
    defined,undefined=coff_symbols(artifact(root,unit['object'],'vm-registration'))
    check(defined=={'boom_java_vm_pool'}|{f"boom_m{m['method']}{x}" for m in methods for x in ('','_native')},'VM COFF definitions differ')
    check(undefined=={f"boom_class{cls['id']}",'boom_class_ensure32','boom_vm_native'} and f"boom_class{cls['id']}" in available,'VM COFF runtime/source imports differ')
    check(file_digest(Path(__file__).resolve().parents[1]/'native/runtime/vm_registration.asm')['sha256']==s['kernel_sha256'],'VM assembly kernel changed')
    return dict(verified=True,native_methods=2,registered_clock_bindings=1,pool_abi=2,execution_verified=False,game_started=False),defined,undefined,{m['method'] for m in methods}
