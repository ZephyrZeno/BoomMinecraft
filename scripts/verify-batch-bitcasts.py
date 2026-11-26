"""Original Float/Double raw-bit declarations, managed-slot adapters and COFF."""
import importlib.util
import json
from pathlib import Path
import zipfile

SPECS=[('java/lang/Float','floatToRawIntBits','(F)I',0),('java/lang/Float','intBitsToFloat','(I)F',1),
       ('java/lang/Double','doubleToRawLongBits','(D)J',2),('java/lang/Double','longBitsToDouble','(J)D',3)]
DATA='.const\nALIGN 8\nPUBLIC boom_java_bitcast_pool\nboom_java_bitcast_pool DWORD 054534342h,1,4,0\n'


def check(v,message):
    if not v:raise ValueError(message)


def source_contract(classes,inventory):
    methods=[];owners=[]
    for owner,name,desc,op in SPECS:
        found=[c for c in classes if c['name']==owner and c['origin']['loader']=='bootstrap']
        check(len(found)==1,'Missing unique bitcast source class');c=found[0]
        check(c['access']==0x31 and c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Bitcast numeric class identity differs')
        ids=[i for i in c['method_ids'] if inventory[i][1:3]==(name,desc)]
        check(len(ids)==1,'Missing unique original bitcast declaration');i=ids[0];m=inventory[i]
        check((m[0],m[3],m[4],m[8])==(c['id'],c['origin']['sha256'],None,0x109),'Bitcast source declaration differs')
        methods.append(dict(method=i,class_id=c['id'],class_sha256=c['origin']['sha256'],name=name,descriptor=desc,access=0x109,operation=op,assembly_unit=0));owners.append(c['id'])
    return methods,sorted(set(owners))


def body(method,cls,op):
    spec=importlib.util.spec_from_file_location('bitcast_adapter_model',Path(__file__).with_name('verify-batch-class-bootstrap.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.body(method,cls,op).replace('boom_java_class_bootstrap_pool','boom_java_bitcast_pool').replace('jmp boom_java_class_bootstrap','jmp boom_java_bitcast')


def verify(root,summary,plan,inventory,available,artifact,coff_symbols,file_digest):
    s=summary['bitcasts'];classes=list(map(json.loads,(Path(plan)/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    methods,owners=source_contract(classes,inventory)
    declarations=sum(bool(inventory[i][8]&0x100) for c in classes if c['id'] in owners for i in c['method_ids'])
    expected=dict(abi=1,context_bytes=32,pool_bytes=16,native_methods=4,source_class_ids=owners,source_native_declarations=declarations)
    check(all(s[k]==v for k,v in expected.items()) and declarations==4,'Bitcast source/ABI counts differ')
    check(s['raw_nan_payloads_preserved'] and not any(s[k] for k in ('numeric_conversion','original_initialization_executed','game_started')),
          'Bitcast translation claims conversion or unverified execution')
    with zipfile.ZipFile(artifact(root,s['index'],'bitcasts')) as z:
        check(z.namelist()==['methods.jsonl'] and list(map(json.loads,z.read('methods.jsonl').splitlines()))==methods,'Bitcast source records differ')
    check(len(s['units'])==1,'Bitcast units differ');unit=s['units'][0]
    text=artifact(root,unit['assembly'],'bitcasts').read_text(encoding='utf-8');expected=DATA+''.join(body(m['method'],m['class_id'],m['operation']) for m in methods)
    check(text.partition('.code\n')[2][:-5]==expected and text.endswith('\nEND\n'),'Bitcast MASM pool/adapters differ')
    check(unit['object'] and not unit['assembler_diagnostic'],'Bitcast COFF unavailable')
    defined,undefined=coff_symbols(artifact(root,unit['object'],'bitcasts'));source={f'boom_class{i}' for i in owners}
    check(defined=={'boom_java_bitcast_pool'}|{f"boom_m{m['method']}{x}" for m in methods for x in ('','_native')},'Bitcast COFF definitions differ')
    check(source<=available and undefined==source|{'boom_class_ensure32','boom_java_bitcast'},'Bitcast COFF source/runtime imports differ')
    check(file_digest(Path(__file__).resolve().parents[1]/'native/runtime/java_bitcasts.asm')['sha256']==s['kernel_sha256'],'Bitcast assembly kernel changed')
    return dict(verified=True,native_methods=4,raw_bits_only=True,execution_verified=False,game_started=False),defined,undefined,{m['method'] for m in methods}
