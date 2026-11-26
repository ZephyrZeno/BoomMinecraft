"""Rebuild bootstrap lookup and full initialization map from original inputs."""
import importlib.util
import json
from pathlib import Path
import zipfile

SPECS=[('java/lang/Class','forName0','(Ljava/lang/String;ZLjava/lang/ClassLoader;Ljava/lang/Class;)Ljava/lang/Class;',0),
       ('java/lang/ClassLoader','findBootstrapClass','(Ljava/lang/String;)Ljava/lang/Class;',1)]
def check(v,m):
    if not v:raise ValueError(m)
def rows(z,n):return [json.loads(l) for l in z.read(n).splitlines()]
def contract(classes,inventory,types,states):
    methods=[]
    for owner,name,desc,op in SPECS:
        cs=[c for c in classes if c['origin']['loader']=='bootstrap' and c['name']==owner];check(len(cs)==1,'Lookup source owner not unique');c=cs[0]
        check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Lookup source owner changed')
        ms=[i for i in c['method_ids'] if inventory[i][1:3]==(name,desc)];check(len(ms)==1,'Lookup source method missing');i=ms[0];m=inventory[i]
        check((m[0],m[3],m[4],m[8])==(c['id'],c['origin']['sha256'],None,0x10a),'Lookup native declaration changed')
        methods.append(dict(method=i,class_id=c['id'],class_sha256=c['origin']['sha256'],name=name,descriptor=desc,access=0x10a,operation=op,assembly_unit=0))
    ts={t['id']:t for t in types};names={}
    def units(s):return list(int.from_bytes(s.encode('utf-16-le','surrogatepass')[i:i+2],'little') for i in range(0,len(s.encode('utf-16-le','surrogatepass')),2))
    for c in classes:
        if c['origin']['loader']=='bootstrap' and not c['origin'].get('generated') and c['name']!='module-info':names[tuple(units(c['name'].replace('/','.')))]=(c['id'],int(c['id'] in ts))
    for t in types:
        if t['defining_loader']=='bootstrap' and t['kind']==3:
            key=tuple(units(t['name'].replace('/','.')));check(key not in names,'Duplicate lookup name');names[key]=(t['id'],3)
    def hash_(v):
        h=0
        for u in v:h=(h*31+u)&0xffffffff
        return h
    result=[];offset=0
    for name,(i,f) in sorted(names.items(),key=lambda p:(hash_(p[0]),p[0])):
        result.append(dict(type_id=i,utf16=list(name),java_hash=hash_(name),offset=offset,flags=f));offset+=len(name)
    initializers=[dict(class_id=c['class_id'],source_sha256=c['source_sha256']) for c in states
                  if c['class_id'] in ts and ts[c['class_id']]['kind'] in (1,2) and ts[c['class_id']]['defining_loader']=='bootstrap' and c['diagnostic'] is None]
    return methods,result,initializers,offset

def adapter(m,traced=False):
    if traced:
        spec=importlib.util.spec_from_file_location('lookup_frame_adapter',Path(__file__).with_name('verify-batch-frames.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
        return v.native_adapter(m['method'],m['class_id'],'boom_java_class_lookup_pool','boom_java_class_lookup',m['operation'])
    spec=importlib.util.spec_from_file_location('lookup_adapter_contract',Path(__file__).with_name('verify-batch-unsafe-memory.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    return v.body(m).replace('boom_java_unsafe_field_pool','boom_java_class_lookup_pool').replace('boom_java_unsafe_memory','boom_java_class_lookup')
def data(methods,names,capacity,string,traced=False):
    count=sum(len(n['utf16']) for n in names);cls=methods[0]['class_id'];loader=methods[1]['class_id']
    out=f".const\nALIGN 8\nPUBLIC boom_java_class_lookup_pool\nboom_java_class_lookup_pool DWORD 04A43464Eh,1,{capacity},{len(names)}\n QWORD OFFSET boom_java_class_pool,OFFSET boom_java_string_literal_pool,OFFSET boom_java_class_bootstrap_pool,OFFSET boom_java_class_lookup_rows\n QWORD OFFSET boom_java_class_initialization_map,OFFSET boom_heap_ptr\n DWORD {string['value_offset']},{string['coder_offset']},{string['class_id']},0\n QWORD OFFSET boom_java_class_lookup_names\n DWORD {count},32,16,{cls},{loader},1\n QWORD 0,0\nPUBLIC boom_java_class_lookup_rows\nboom_java_class_lookup_rows LABEL BYTE\n"
    for n in names:out+=f" DWORD {n['offset']},{len(n['utf16'])},0{n['java_hash']:08X}h,{n['type_id']},{n['flags']},0\n QWORD 0\n"
    out+='ALIGN 2\nPUBLIC boom_java_class_lookup_names\nboom_java_class_lookup_names LABEL WORD\n'
    for n in names:
        for i in range(0,len(n['utf16']),16):out+=' WORD '+','.join(f'0{u:04X}h' for u in n['utf16'][i:i+16])+'\n'
    return out+''.join(adapter(m,traced) for m in methods)
def initialization_map(capacity,ids,selected=None):
    out='.const\nALIGN 8\nPUBLIC boom_java_class_initialization_map\nboom_java_class_initialization_map LABEL QWORD\n'
    for i in range(capacity):
        if i not in ids:out+=' QWORD 0,0\n'
        elif selected is None or i in selected:out+=f' QWORD OFFSET boom_class{i},0\n'
        else:out+=f' QWORD 0,OFFSET boom_batch_initialize_{i}\n'
    return out

def verify(root,summary,plan,inventory,available,artifact,coff_symbols,file_digest):
    s=summary['class_lookup'];classes=[json.loads(l) for l in (Path(plan)/'classes.jsonl').read_text().splitlines()]
    with zipfile.ZipFile(artifact(root,summary['runtime_metadata']['index'],'runtime-metadata')) as z:types=rows(z,'types.jsonl')
    with zipfile.ZipFile(artifact(root,summary['class_state']['index'],'class-state')) as z:states=rows(z,'classes.jsonl')
    methods,names,inits,count=contract(classes,inventory,types,states);capacity=summary['runtime_metadata']['type_capacity']
    expected=dict(abi=1,context_bytes=32,pool_bytes=128,record_bytes=32,initialization_record_bytes=16,native_methods=2,type_capacity=capacity,names=len(names),name_units=count,initializers=len(inits))
    check(all(s[k]==v for k,v in expected.items()),'Lookup source counts/ABI differ')
    check(s['bootstrap_loader'] and not any(s[k] for k in ('custom_loaders','dynamic_array_types','throwable_objects_materialized','original_initialization_executed','automatic_gc','game_started')),'Lookup domain/execution claims differ')
    with zipfile.ZipFile(artifact(root,s['index'],'class-lookup')) as z:
        check(z.namelist()==['methods.jsonl','names.jsonl','initializers.jsonl'],'Lookup index entries differ')
        for k,v in [('methods.jsonl',methods),('names.jsonl',names),('initializers.jsonl',inits)]:check(rows(z,k)==v,'Lookup source records differ: '+k)
    check(len(s['units'])==2,'Lookup unit count differs');defined=set();undefined=set();ids={r['class_id'] for r in inits}
    expected_bodies=[data(methods,names,capacity,summary['string_literals']['source_layout'],summary['schema']>=23),initialization_map(capacity,ids)]
    for i,(u,body) in enumerate(zip(s['units'],expected_bodies)):
        text=artifact(root,u['assembly'],'class-lookup').read_text();check(u['id']==i and u['body_bytes']==len(body) and text.partition('.code\n')[2][:-5]==body and text.endswith('\nEND\n'),'Lookup MASM source changed')
        check(u['object'] and not u['assembler_diagnostic'],'Lookup object unavailable');d,x=coff_symbols(artifact(root,u['object'],'class-lookup'))
        if i==0:
            exports={'boom_java_class_lookup_pool','boom_java_class_lookup_rows','boom_java_class_lookup_names'}|{f"boom_m{m['method']}{suffix}" for m in methods for suffix in ('','_native')}
            imports={'boom_java_class_pool','boom_java_string_literal_pool','boom_java_class_bootstrap_pool','boom_java_class_initialization_map','boom_heap_ptr','boom_class_ensure32','boom_java_class_lookup'}|{f"boom_class{m['class_id']}" for m in methods}
        else:exports={'boom_java_class_initialization_map'};imports={f'boom_class{i}' for i in ids}
        if i==0 and summary['schema']>=23:
            imports|={'boom_trace_pool','boom_trace_enter','boom_trace_leave'}|{f"boom_trace_method{m['method']}" for m in methods}
        check(d==exports and x==imports,'Lookup COFF provenance differs');defined|=d;undefined|=x
    kernels={'java_class_lookup.asm','java_classes.asm','java_class_bootstrap.asm','classes32.asm','objects.asm','heap.asm'}
    if summary['schema']>=23:kernels.add('frames.asm')
    check(set(s['kernel_sha256'])=={'native/runtime/'+n for n in kernels},'Lookup kernel set differs')
    for p,h in s['kernel_sha256'].items():check(file_digest(Path(__file__).resolve().parents[1]/p)['sha256']==h,'Lookup ASM kernel changed')
    return dict(verified=True,native_methods=2,bootstrap_names=len(names),initializers=len(inits),custom_loaders=False,execution_verified=False,game_started=False),defined,undefined,{m['method'] for m in methods}
