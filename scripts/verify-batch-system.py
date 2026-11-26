"""Independently validate original System natives, real registration and COFF."""
import json
from pathlib import Path
import zipfile

SPECS=[('registerNatives','()V',0x10a,None),('currentTimeMillis','()J',0x109,0),('nanoTime','()J',0x109,1),
       ('arraycopy','(Ljava/lang/Object;ILjava/lang/Object;II)V',0x109,2),('setIn0','(Ljava/io/InputStream;)V',0x10a,3),
       ('setOut0','(Ljava/io/PrintStream;)V',0x10a,4),('setErr0','(Ljava/io/PrintStream;)V',0x10a,5)]
POOL='.const\nALIGN 8\nPUBLIC boom_batch_system_native_table\nboom_batch_system_native_table DWORD 05359534Dh,1,3,0\n QWORD OFFSET boom_vm_current_time_millis,OFFSET boom_vm_nano_time,OFFSET boom_system_arraycopy\n.data\nALIGN 8\nPUBLIC boom_batch_system_native_pool\nboom_batch_system_native_pool DWORD 053595350h,1\n QWORD 0,OFFSET boom_batch_system_native_table,OFFSET boom_runtime_type_map\n'

def check(value,message):
    if not value:raise ValueError(message)

def source_methods(classes,inventory,streams=True):
    matches=[c for c in classes if c['name']=='java/lang/System' and c['origin']['loader']=='bootstrap']
    check(len(matches)==1,'Missing/ambiguous original System source');source=matches[0];origin=source['origin']
    check(origin['source_id']=='jdk:java.base' and origin.get('generated') is None and source['access']==0x31
          and source['superclass']=='java/lang/Object','System source-native class contract differs')
    expected=[]
    for name,desc,access,operation in SPECS if streams else SPECS[:4]:
        found=[id_ for id_ in source['method_ids'] if inventory[id_][1:3]==(name,desc)]
        check(len(found)==1 and inventory[found[0]][8]==access and inventory[found[0]][4] is None,
              'System native declaration identity/access/Code differs')
        expected.append(dict(method=found[0],class_id=source['id'],class_sha256=origin['sha256'],name=name,
                             descriptor=desc,access=access,operation=operation,assembly_unit=0))
    return source,expected

def stream_pool(class_id,slots):
    text='.const\nALIGN 8\nPUBLIC boom_batch_system_stream_rows\nboom_batch_system_stream_rows LABEL QWORD\n'
    for slot in slots:text+=f" QWORD OFFSET boom_s{class_id}_{slot['field_index']},OFFSET boom_t{slot['type_id']}\n"
    return text+f'PUBLIC boom_batch_system_stream_pool\nboom_batch_system_stream_pool DWORD 053595349h,1\n QWORD OFFSET boom_class{class_id},OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_batch_system_stream_rows\n DWORD 3,0\n QWORD 0,0\n'

def source_stream_slots(classes,source):
    slots=[]
    for op,(name,desc,target) in enumerate([('in','Ljava/io/InputStream;','java/io/InputStream'),('out','Ljava/io/PrintStream;','java/io/PrintStream'),('err','Ljava/io/PrintStream;','java/io/PrintStream')]):
        fields=[(index,f) for index,f in enumerate(source['fields']) if (f['name'],f['descriptor'])==(name,desc)]
        types=[c['id'] for c in classes if c['name']==target and c['origin']['loader']=='bootstrap']
        check(len(fields)==1 and fields[0][1]['access']==0x19 and len(types)==1,'Original System stream field/type differs')
        slots.append(dict(operation=op,field=name,descriptor=desc,field_index=fields[0][0],type_id=types[0]))
    return slots

def method_body(method,class_id,operation):
    setup=('    lea r8,boom_batch_system_native_pool\n    jmp boom_system_register\n' if operation is None else
           f'    lea r8,boom_batch_system_stream_pool\n    mov r9d,{operation-3}\n    jmp boom_system_stream_set\n' if operation>=3 else
           f'    lea r8,boom_batch_system_native_pool\n    mov r9d,{operation}\n    jmp boom_system_dispatch\n')
    args=(f'    test rdx,rdx\n    jnz boom_m{method}_native_ready\n    mov DWORD PTR [rcx],7\n    jmp boom_m{method}_native_zero\nboom_m{method}_native_ready:\n' if operation is not None and operation>=2 else '')
    return (f'.code\nboom_m{method} PROC FRAME\n    sub rsp,72\n    .allocstack 72\n    .endprolog\n    mov QWORD PTR [rsp+48],rcx\n    mov QWORD PTR [rsp+56],rdx\n'
            f'    test rcx,rcx\n    jz boom_m{method}_native_entry_zero\n    cmp DWORD PTR [rcx],0\n    jne boom_m{method}_native_entry_zero\n    lea rcx,boom_class{class_id}\n'
            f'    mov rdx,QWORD PTR [rsp+48]\n    call boom_class_ensure32\n    test eax,eax\n    jnz boom_m{method}_native_entry_zero\n    mov rcx,QWORD PTR [rsp+48]\n'
            f'    mov rdx,QWORD PTR [rsp+56]\n    call boom_m{method}_native\n    add rsp,72\n    ret\nboom_m{method}_native_entry_zero:\n    xor eax,eax\n    add rsp,72\n    ret\nboom_m{method} ENDP\n'
            f'boom_m{method}_native PROC\n    test rcx,rcx\n    jz boom_m{method}_native_zero\n    cmp DWORD PTR [rcx],0\n    jne boom_m{method}_native_zero\n{args}{setup}'
            f'boom_m{method}_native_zero:\n    xor eax,eax\n    ret\nboom_m{method}_native ENDP\n')

def verify(root,batch,plan,inventory,available,artifact,coff_symbols,file_digest):
    root,plan=Path(root),Path(plan);summary=batch['system_natives']
    streams=batch['schema']>=9
    check((summary['abi'],summary['context_bytes'],summary['pool_abi'],summary['runtime_map_abi'])==(2 if streams else 1,32,1,2),'Invalid System native ABI')
    check(summary['initial_registration_null'] is True,'System native table was pre-registered')
    for flag in ('linked','system_class_initialization_executed','system_boot_phases_completed'):
        check(summary[flag] is False,'System generator claims unverified execution')
    classes=list(map(json.loads,(plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    source,expected=source_methods(classes,inventory,streams)
    check((summary['class_id'],summary['class_sha256'],summary['native_methods'],summary['registered_methods'])==
          (source['id'],source['origin']['sha256'],7 if streams else 4,3),'System native summary provenance differs')
    with zipfile.ZipFile(artifact(root,summary['index'],'system-natives')) as bundle:
        check(bundle.namelist()==['methods.jsonl'],'Unexpected System native index')
        methods=list(map(json.loads,bundle.read('methods.jsonl').splitlines()))
    check(methods==expected,'Native implementations differ from original declarations')
    project=Path(__file__).resolve().parents[1]
    kernels={'native/runtime/system.asm','native/runtime/vm_clock.asm'}
    if streams:kernels.add('native/runtime/system_streams.asm')
    check(set(summary['kernel_sha256'])==kernels,'Unexpected System kernels')
    for name,digest in summary['kernel_sha256'].items():check(file_digest(project/name)['sha256']==digest,'System kernel source changed')
    check(len(summary['units'])==1,'Invalid System native unit count');unit=summary['units'][0]
    slots=[]
    if streams:
        slots=source_stream_slots(classes,source)
        check(summary['stream_slots']==slots and summary['stream_pool_unit']==0,'Generated stream slot map differs')
    body=POOL+(stream_pool(source['id'],slots) if streams else '')+''.join(method_body(m['method'],source['id'],m['operation']) for m in expected)
    text=artifact(root,unit['assembly'],'system-natives').read_text(encoding='utf-8')
    check(text.endswith('\nEND\n') and text.partition('.code\n')[2][:-5]==body,'System MASM differs from source-native contracts')
    check(unit['object'] and not unit['assembler_diagnostic'],'System native assembly failed')
    defined,undefined=coff_symbols(artifact(root,unit['object'],'system-natives'))
    expected_defs={f"boom_m{m['method']}{suffix}" for m in expected for suffix in ('','_native')}|{'boom_batch_system_native_pool','boom_batch_system_native_table'}
    if streams:expected_defs.update(('boom_batch_system_stream_pool','boom_batch_system_stream_rows'))
    check(defined==expected_defs,'System native COFF definitions differ')
    check({'boom_runtime_type_map',f"boom_class{source['id']}"}<=available,'System native pool has no source type/class metadata')
    imports={'boom_runtime_type_map',f"boom_class{source['id']}",'boom_class_ensure32','boom_system_register','boom_system_dispatch',
                       'boom_vm_current_time_millis','boom_vm_nano_time','boom_system_arraycopy'}
    if streams:
        imports.update(('boom_heap_ptr','boom_system_stream_set'))
        for slot in slots:imports.update((f"boom_s{source['id']}_{slot['field_index']}",f"boom_t{slot['type_id']}"))
        check((imports-{'boom_system_stream_set','boom_class_ensure32','boom_system_register','boom_system_dispatch','boom_vm_current_time_millis','boom_vm_nano_time','boom_system_arraycopy'})<=available,
              'System streams are missing real source static cells or type metadata')
    check(undefined==imports,'Unexpected System native imports')
    return dict(verified=True,scope='source_System_registration_envelopes_MASM_and_COFF_only',native_methods=len(expected),
                registered_methods=3,stream_setters=3 if streams else 0,execution_verified=False),defined,undefined,{m['method'] for m in methods}
