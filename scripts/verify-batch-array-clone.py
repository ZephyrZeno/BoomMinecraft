"""Check every clone site against original array CP references and native source."""
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import zipfile


def check(value,message):
    if not value:raise ValueError(message)


def source_array(member,caller,classes,lookup,arrays):
    text=member['owner']
    check(text.startswith('[') and (member['name'],member['descriptor'],member['interface'])==('clone','()Ljava/lang/Object;',False),
          'Invalid original array clone reference')
    element=text.lstrip('[');component=lookup(classes[caller]['origin']['loader'],element[1:-1]) if element.startswith('L') else None
    check(component is not None or len(element)==1 and element in 'ZBCSIJFD','Clone component identity is unavailable')
    loader=classes[component]['origin']['loader'] if component is not None else 'bootstrap'
    id_=arrays.get((loader,text));check(id_ is not None,'Clone array loader/type is unavailable')
    return id_


def original_object(source):
    origin=source['origin']
    return (source['name']=='java/lang/Object' and origin['loader']=='bootstrap' and origin['source_id']=='jdk:java.base'
            and origin.get('generated') is None and source['access']&0x611==1)


def verify(root,batch,plan,inventory,requests,available,artifact,coff_symbols,file_digest):
    summary=batch['array_clone'];root,plan=Path(root),Path(plan)
    check((summary['abi'],summary['context_bytes'])==(1,32),'Invalid generated clone ABI')
    for flag in ('linked','execution_verified','automatic_gc'):check(summary[flag] is False,'Clone generator claims unverified execution')
    classes=list(map(json.loads,(plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    spec=importlib.util.spec_from_file_location('clone_source_types',Path(__file__).with_name('verify-batch-metadata.py'))
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    lookup,ancestry,parents,omitted=model.source_model(classes)
    arrays={ (a['defining_loader'],a['descriptor']):a['id'] for a in map(json.loads,artifact(root,batch['array_types']).read_text(encoding='utf-8').splitlines()) }
    with zipfile.ZipFile(artifact(root,summary['index'],'array-clone')) as bundle:
        check(bundle.namelist()==['sites.jsonl'],'Unexpected clone index')
        sites=list(map(json.loads,bundle.read('sites.jsonl').splitlines()))
    check([s['label'] for s in sites]==sorted(requests.array_clones),'Array clone source coverage differs')
    bodies,defs=defaultdict(list),defaultdict(set);types=set()
    if sites:
        object_id=lookup('bootstrap','java/lang/Object');source=classes[object_id]
        methods=[id_ for id_ in source['method_ids'] if inventory[id_][1:3]==('clone','()Ljava/lang/Object;')]
        check(len(methods)==1 and inventory[methods[0]][8]==0x104 and inventory[methods[0]][4] is None,
              'Clone native declaration differs from original Object')
        check(original_object(source),
              'Clone source is not original bootstrap Object')
        native=Path(__file__).resolve().parents[1]/'native/runtime/array_clone.asm'
        contract=summary['contract']
        check(contract==dict(object_class=object_id,class_sha256=source['origin']['sha256'],clone_method=methods[0],
              source_access=0x104,heap_abi=1,runtime_map_abi=2,pool_abi=1,pool_unit=0,kernel_sha256=file_digest(native)['sha256']),
              'Clone source-native contract differs')
        bodies[0].append('.const\nALIGN 8\nPUBLIC boom_batch_array_clone_pool\nboom_batch_array_clone_pool DWORD 041434C50h,1\n QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,0\n')
        defs[0].add('boom_batch_array_clone_pool')
        check({'boom_heap_ptr','boom_runtime_type_map'}<=available,'Clone pool is missing source heap/type metadata')
    else:check(summary['contract'] is None,'Unused clone contract was generated')
    for site in sites:
        original=requests.array_clones[site['label']]
        check({k:site[k] for k in original['site']}==original['site'] and site['caller_methods']==sorted(original['methods']),
              'Generated clone site differs from source requests')
        cid,cp=site['caller_class'],str(site['constant']);constant=requests.constants[cid][cp]
        check(constant is not None and set(constant)=={'Method'},'Clone source constant is not a method')
        member=constant['Method'];id_=source_array(member,cid,classes,lookup,arrays)
        check(site['descriptor']==member['descriptor'] and site['opcode']==182 and id_==site['array_type'] and f'boom_t{id_}' in available,
              'Clone array loader/type differs')
        types.add(id_);label=site['label'];check(label==f"boom_batch_call_{cid}_{cp}_182",'Clone call symbol differs')
        check(isinstance(site['assembly_unit'],int),'Clone site has no generated unit')
        bodies[site['assembly_unit']].append(f'.code\n{label} PROC\n lea r8,boom_batch_array_clone_pool\n lea r9,boom_t{id_}\n jmp boom_array_clone\n{label} ENDP\n')
        defs[site['assembly_unit']].add(label)
    check(set(bodies)==set(range(len(summary['units']))),'Clone unit coverage differs')
    defined,undefined=set(),set()
    for unit in summary['units']:
        id_=unit['id'];text=artifact(root,unit['assembly'],'array-clone').read_text(encoding='utf-8')
        check(text.endswith('\nEND\n') and text.partition('.code\n')[2][:-5]==''.join(b+'\n' for b in bodies[id_]),'Clone MASM differs from original source contracts')
        check(unit['object'] and not unit['assembler_diagnostic'],'Missing successful clone COFF object')
        actual,imports=coff_symbols(artifact(root,unit['object'],'array-clone'))
        check(actual==defs[id_] and not actual&defined,'Clone COFF definitions differ')
        defined.update(actual);undefined.update(imports)
    check(summary['generated_sites']==len(sites) and summary['source_array_types']==len(types),'Clone summary counts differ')
    check(not undefined-({'boom_array_clone'}|available),'Clone has an unprovided data/runtime dependency')
    return dict(verified=True,scope='source_array_clone_contracts_MASM_and_COFF_only',sites=len(sites),array_types=len(types),
                execution_verified=False),defined,undefined
