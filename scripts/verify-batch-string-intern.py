"""Verify normal String.intern source, pool, MASM and actual COFF identities."""
import json
from pathlib import Path
import zipfile


def check(value,message):
    if not value:raise ValueError(message)


def pool(shape):
    return f".data?\nALIGN 8\nPUBLIC boom_java_string_intern_root\nboom_java_string_intern_root QWORD ?\n.const\nPUBLIC boom_java_string_intern_root_count\nboom_java_string_intern_root_count QWORD 1\n.data\nALIGN 8\nPUBLIC boom_java_string_intern_pool\nboom_java_string_intern_pool DWORD 04A494E50h,1,0,0,0,0\n QWORD OFFSET boom_heap_ptr,OFFSET boom_layout{shape['class_id']}\n DWORD {shape['value_offset']},{shape['coder_offset']},{shape['hash_offset']},{shape['hash_is_zero_offset']}\n QWORD OFFSET boom_java_string_literal_pool,OFFSET boom_java_class_name_pool,OFFSET boom_java_string_intern_root\n DWORD 32,1\n QWORD 0\n"


def body(id_):
    return f'.code\nboom_m{id_} PROC\n jmp boom_m{id_}_native\nboom_m{id_} ENDP\nboom_m{id_}_native PROC\n lea r8,boom_java_string_intern_pool\n jmp boom_java_string_intern\nboom_m{id_}_native ENDP\n'


def source_method(classes,inventory,shape):
    owners=[c for c in classes if (c['origin']['loader'],c['name'])==('bootstrap','java/lang/String')]
    check(len(owners)==1,'Missing/ambiguous source String');c=owners[0]
    check(c['id']==shape['class_id'] and c['origin']['sha256']==shape['source_sha256'] and c['origin']['source_id']=='jdk:java.base' and c['origin'].get('generated') is None and c['access']&0x10,'String intern owner differs')
    ids=[i for i in c['method_ids'] if inventory[i][1:3]==('intern','()Ljava/lang/String;')]
    check(len(ids)==1 and inventory[ids[0]][8]==0x101 and inventory[ids[0]][4] is None,'String intern native signature/access/Code differs')
    return dict(method=ids[0],class_id=c['id'],class_sha256=c['origin']['sha256'],name='intern',descriptor='()Ljava/lang/String;',access=0x101,assembly_unit=0)


def verify(root,batch,plan,inventory,available,artifact,coff_symbols,file_digest):
    root,plan=Path(root),Path(plan);s=batch['string_intern'];shape=batch['string_literals']['source_layout']
    check((s['abi'],s['context_bytes'],s['root_cells'],s['native_methods'])==(1,32,1,1),'Invalid normal intern ABI')
    check(s['general_string_intern'] and s['strong_retention'] and not s['weak_intern'],'Intern retention policy differs')
    check(all(s[f] is False for f in ('original_string_initialization_executed','automatic_gc','linked')),'Intern falsely claims bootstrap/GC/link completion')
    classes=list(map(json.loads,(plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()));method=source_method(classes,inventory,shape)
    with zipfile.ZipFile(artifact(root,s['index'],'string-intern')) as z:
        check(z.namelist()==['methods.jsonl'] and list(map(json.loads,z.read('methods.jsonl').splitlines()))==[method],'Intern source native declaration differs')
    check(len(s['units'])==1,'Unexpected intern unit count');unit=s['units'][0]
    text=artifact(root,unit['assembly'],'string-intern').read_text(encoding='utf-8')
    check(text.partition('.code\n')[2][:-5]==pool(shape)+body(method['method']) and text.endswith('\nEND\n'),'Intern MASM differs from source model')
    check(unit['object'] is not None and unit['assembler_diagnostic'] is None,'Intern actual assembly failed')
    defined,undefined=coff_symbols(artifact(root,unit['object'],'string-intern'))
    required={f"boom_m{method['method']}{suffix}" for suffix in ('','_native')}|{'boom_java_string_intern_pool','boom_java_string_intern_root','boom_java_string_intern_root_count'}
    needed={'boom_heap_ptr',f"boom_layout{shape['class_id']}",'boom_java_string_literal_pool','boom_java_class_name_pool'}
    check(defined==required and needed<=available and undefined==needed|{'boom_java_string_intern'},'Intern COFF definitions/imports differ')
    check(set(s['kernel_sha256'])=={'native/runtime/java_string_intern.asm'},'Intern kernel coverage differs')
    for path,digest in s['kernel_sha256'].items():check(file_digest(Path(__file__).resolve().parents[1]/path)['sha256']==digest,'Intern MASM kernel changed')
    return dict(verified=True,scope='source_native_pool_MASM_and_COFF_only',native_methods=1,strong_retention=True,weak_intern=False,execution_verified=False,game_started=False),defined,undefined,{method['method']}
