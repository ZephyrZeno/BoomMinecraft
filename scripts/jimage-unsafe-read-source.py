"""Original typed Unsafe reads extended only to leased readonly JIMAGE records."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OWNER_SHA='a11b4253485a1463a4d737174fe49bdc4357a6047111798d5f05833580716635'
OWNER_MAGIC=0x3130474D494A4F42
KINDS={2:('Byte','B',1),3:('Char','C',2),4:('Short','S',2),5:('Int','I',4),6:('Long','J',8)}
SERVICE='boom_java_unsafe_jimage_memory'
BRIDGE_POOL='boom_provider_jimage_native_map_pool'


def module(name):
    spec=importlib.util.spec_from_file_location('jimage_unsafe_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


I=module('verify-translation-ir');G=module('verify-batch-unsafe-memory')


def prefix_source():
    text=(ROOT/'native/runtime/java_unsafe_fields.asm').read_text(encoding='utf-8')
    validator=re.findall(r'(?ms)^uf_pool_valid PROC\n.*?^uf_pool_valid ENDP\n',text)
    memory=re.findall(r'(?ms)^boom_java_unsafe_memory PROC FRAME\n(.*?)^boom_java_unsafe_memory ENDP\n',text)
    assert len(validator)==len(memory)==1,'Locked original typed receiver validation boundary'
    delimiter=' mov rsi,QWORD PTR [r12+8]\n'
    assert memory[0].count(delimiter)==1,'Locked original receiver/base boundary'
    prefix=memory[0].split(delimiter)[0]
    assert prefix.count(' sub rsp,56\n')==prefix.count(' .allocstack 56\n')==1,'Original memory fixed frame'
    # Exactly the same receiver validation, with a larger fixed unwindable
    # frame for Job48. Original method adapters keep their machine bytes.
    relocated=prefix.replace(' sub rsp,56\n',' sub rsp,120\n').replace(' .allocstack 56\n',' .allocstack 120\n')
    relocated=relocated.replace('um_','jur_').replace('uf_pool_valid','jur_pool_valid').replace('uf_widths','jur_widths')
    checker=validator[0].replace('uf_pool','jur_pool').replace('jur_pool_valid PROC\n','jur_pool_valid PROC PRIVATE\n')
    return text,prefix,validator[0],'.const\njur_widths BYTE 1,1,2,2,4,8,4,8,8\n.code\n'+checker,relocated


def index(summary,classes,S):
    wanted={'java/nio/DirectByteBuffer','jdk/internal/misc/ScopedMemoryAccess','jdk/internal/misc/Unsafe'}
    owners={c['name']:c for c in classes if c['origin']['loader']=='bootstrap' and c['name'] in wanted}
    S.check(set(owners)==wanted,'Original direct/scoped/Unsafe classes required')
    raw={name:I.Source(S.original_class(summary,c)) for name,c in owners.items()}
    natives=[];unsafe=owners[G.OWNER];bykey={(m['name'],m['descriptor']):(ident,m) for ident,m in zip(unsafe['method_ids'],raw[G.OWNER].methods)}
    for name,desc,access,operation in G.specs():
        ident,m=bykey[name,desc]
        S.check(m['access']==access and raw[G.OWNER].code(m) is None,'Original typed native differs')
        natives.append(dict(method=ident,class_id=unsafe['id'],class_sha256=unsafe['origin']['sha256'],name=name,descriptor=desc,access=access,operation=operation,assembly_unit=0))
    with zipfile.ZipFile(S.checked(summary['unsafe_memory']['index'])) as archive:
        S.check(archive.namelist()==['methods.jsonl'] and [json.loads(line) for line in archive.read('methods.jsonl').splitlines()]==natives,'Locked original 42-native inventory differs')
    methods=[]
    for name,source in raw.items():
        for ident,m in zip(owners[name]['method_ids'],source.methods):
            code=source.code(m);n=m['name']
            if not code:continue
            if name=='java/nio/DirectByteBuffer':include=n in ('get','getInt','getLong','getShort','getChar','ix','<init>')
            elif name.endswith('/ScopedMemoryAccess'):include=n in {p+s for p in ('getByte','getIntUnaligned','getLongUnaligned','getShortUnaligned','getCharUnaligned') for s in ('','Internal')}
            else:include=n in ('getIntUnaligned','getLongUnaligned','getShortUnaligned','getCharUnaligned','getByte','getInt','getLong','getShort','getChar','makeInt','makeLong','makeShort','makeChar','convEndian')
            if not include:continue
            references=[];instructions=list(I.stream(code['bytes']))
            for instruction in instructions:
                if 'Constant' in instruction['operand']:
                    symbol=source.symbol(instruction['operand']['Constant'])
                    if 'Method' in symbol or 'Field' in symbol:references.append(dict(pc=instruction['pc'],opcode=instruction['opcode'],symbol=symbol))
            methods.append(dict(method=ident,class_id=owners[name]['id'],class_sha256=owners[name]['origin']['sha256'],owner=name,name=n,descriptor=m['descriptor'],access=m['access'],code_sha256=hashlib.sha256(code['bytes']).hexdigest(),references=references,
                aconst_null_pcs=[r['pc'] for r in instructions if r['opcode']==1]))
    reads=[r for r in natives if r['operation'] in KINDS]
    S.check(len(reads)==5 and all((r['name'],r['descriptor'])==('get'+KINDS[r['operation']][0],'(Ljava/lang/Object;J)'+KINDS[r['operation']][1]) for r in reads),'Only five original plain scalar reads')
    text,prefix,checker,_,_=prefix_source();kernel=S.artifact(ROOT/'native/runtime/java_unsafe_fields.asm')
    S.check(kernel['digest']['sha256']==summary['unsafe_memory']['kernel_sha256']['native/runtime/java_unsafe_fields.asm'],'Original runtime typed kernel differs')
    owner=S.artifact(ROOT/'native/kernels/jimage_owner64.asm.inc');S.check(owner['digest']['sha256']==OWNER_SHA,'Pinned real mapping owner differs')
    return dict(schema=1,owner=unsafe['id'],source_classes={n:r['id'] for n,r in owners.items()},methods=natives,read_methods=reads,original_Java=methods,
        read_kinds={str(k):dict(name=v[0],descriptor=v[1],bytes=v[2]) for k,v in KINDS.items()},argv_slots=dict(receiver=0,base=8,address=16),Context_bytes=32,
        original_kernel=kernel,original_receiver_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),original_UFMP_validator_sha256=hashlib.sha256(checker.encode()).hexdigest(),
        Owner128=dict(kernel=owner,magic=OWNER_MAGIC,bytes=128,abi=1,SRW=16,state=24,capacity=28,entries=32,head=48,record_bytes=80,record_view=16,record_length=24,record_refs=48),
        JMAP80=dict(symbol=BRIDGE_POOL,magic=0x50414D4A,abi=1,owner=8,state=24,ready=1,pool_bytes=80),
        required_base_modules=['runtime_metadata','unsafe_fields','unsafe_memory'],required_classes=[unsafe['id']],required_java_methods=[],
        policy=dict(only_original_plain_reads=True,normal_heap_and_thread_counter_delegate_to_original=True,volatile_and_writes_and_CAS_unchanged=True,
            owner_shared_SRW_held_through_actual_read=True,leased_record_required=True,complete_record_bounds_and_overflow_checked=True,
            all_pending_Context_bytes_preserved=True,no_call_and_clear_Context=True,arbitrary_off_heap=False,owner_allocation_outlives_all_VM_users=True),
        registered=False,executed=False,game_started=False)


def assembly(meta):
    _,prefix,checker,declarations,relocated=prefix_source()
    definitions={f"boom_m{r['method']}{suffix}" for r in meta['methods'] for suffix in ('','_native')}
    imports={'boom_java_unsafe_field_pool',f"boom_class{meta['owner']}",'boom_class_ensure32','boom_java_unsafe_memory',SERVICE}
    source='option casemap:none\n'+''.join('EXTERN '+n+(':BYTE\n' if n in {'boom_java_unsafe_field_pool',f"boom_class{meta['owner']}"} else ':PROC\n') for n in sorted(imports))
    for r in meta['methods']:
        body=G.body(r)
        if r['operation'] in KINDS:
            assert body.count(' jmp boom_java_unsafe_memory\n')==1
            body=body.replace(' jmp boom_java_unsafe_memory\n',' jmp '+SERVICE+'\n')
        source+=''.join('PUBLIC boom_m'+str(r['method'])+suffix+'\n' for suffix in ('','_native'))+body
    return source+'\nEND\n',definitions,imports


def wrapper_assembly(meta):
    _,_,_,declarations,relocated=prefix_source()
    imports={'boom_java_unsafe_memory','boom_heap_contains','boom_object_check','boom_runtime_row','boom_jimage_owned_scalar_read',BRIDGE_POOL}
    source='option casemap:none\n'+''.join('EXTERN '+n+(':BYTE\n' if n==BRIDGE_POOL else ':PROC\n') for n in sorted(imports))+declarations
    fragment=(ROOT/'native/providers/jimage_unsafe_read.asm.inc').read_text(encoding='utf-8')
    assert fragment.count(';@ORIGINAL_RECEIVER_PREFIX@')==1
    source+=fragment.replace(';@ORIGINAL_RECEIVER_PREFIX@',relocated.rstrip())+'\nEND\n'
    return source,{SERVICE,'boom_jimage_unsafe_memory_read'},imports
