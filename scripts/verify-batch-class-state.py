"""Verify source static cells and initialization code, without running classes."""
import importlib.util
import json
from pathlib import Path
import re
import zipfile

def check(value,message):
    if not value:raise ValueError(message)

def constant_bits(descriptor,value,cp):
    if descriptor=='Ljava/lang/String;' and 'StringUtf16' in value:return 0,cp
    variant={'Z':'Int','B':'Int','C':'Int','S':'Int','I':'Int','J':'Long','F':'FloatBits','D':'DoubleBits'}.get(descriptor)
    check(variant in value if variant else False,'ConstantValue type differs')
    bits=value[variant]
    if descriptor=='Z':bits&=1
    elif descriptor=='B':bits=((bits&255)^128)-128;bits&=0xffffffff
    elif descriptor=='S':bits=((bits&65535)^32768)-32768;bits&=0xffffffff
    elif descriptor=='C':bits&=65535
    elif descriptor in ('I','F'):bits&=0xffffffff
    else:bits&=0xffffffffffffffff
    return bits,None

def dependencies(classes,inputs,lookup,parents,id_):
    if classes[id_]['access']&0x200:return []
    result=[] if parents[id_] is None else [parents[id_]];seen=set()
    def visit(id_):
        if id_ in seen:return
        seen.add(id_);check(len(seen)<=4096,'Initialization interface budget exceeded')
        c=classes[id_]
        for name in c['interfaces']:
            target=lookup(c['origin']['loader'],name);check(target is not None,'Missing initializer interface');visit(target)
        # JVMS 21 5.5 step 7 says non-abstract, non-static, including private.
        if inputs[id_]['concrete_instance_method']:result.append(id_)
    c=classes[id_]
    for name in c['interfaces']:
        target=lookup(c['origin']['loader'],name);check(target is not None,'Missing initializer interface');visit(target)
    return result

def initialization_body(state):
    id_=state['class_id'];lines=[f'boom_batch_initialize_{id_} PROC FRAME','sub rsp,72','.allocstack 72','.endprolog',
        'mov QWORD PTR [rsp+48],rcx','mov QWORD PTR [rsp+56],rdx']
    for field in state['fields']:
        if field['constant'] is None:continue
        if field['string_constant'] is not None:
            lines+=['mov rcx,QWORD PTR [rsp+48]','lea rdx,[rsp+64]',f"call boom_batch_literal_load_{id_}_{field['string_constant']}",
                    'mov r10,QWORD PTR [rsp+48]','cmp DWORD PTR [r10],0',f'jne boom_batch_initialize_{id_}_done']
        else:lines.append(f"mov rax,0{field['initial_bits']:016X}h")
        lines.append(f"mov QWORD PTR [boom_s{id_}_{field['index']}],rax")
    for dependency in state['dependencies']:
        lines += [f'lea rcx,boom_class{dependency}','mov rdx,QWORD PTR [rsp+48]','call boom_class_ensure32','test eax,eax',f'jnz boom_batch_initialize_{id_}_done']
    if state['initializer']:
        lines+=['mov rcx,QWORD PTR [rsp+48]','mov rdx,QWORD PTR [rsp+56]',f"call boom_m{state['initializer']['method']}_body"]
    if state.get('vm_post_initializer')=='unsafe_constants':
        lines+=['mov rcx,QWORD PTR [rsp+48]','cmp DWORD PTR [rcx],0',f'jne boom_batch_initialize_{id_}_done',
                'lea rdx,boom_java_unsafe_pool','call boom_java_unsafe_constants']
    lines += [f'boom_batch_initialize_{id_}_done:','mov r10,QWORD PTR [rsp+48]','mov eax,DWORD PTR [r10]',
              'add rsp,72','ret',f'boom_batch_initialize_{id_} ENDP']
    return '\n'.join(lines)

def verify(root,batch,plan,inputs,emitted_initializers,artifact,coff_symbols,file_digest):
    root,plan=Path(root),Path(plan);summary=batch['class_state']
    check((summary['abi'],summary['descriptor_abi'],summary['context_bytes'],summary['initial_state'])==(1,2,32,0),'Invalid class state ABI')
    check(summary['initial_static_storage_zero'] is True,'Static cells do not start at default values')
    for key in ('complete_original_class_initialization_verified','linked','automatic_gc'):
        check(summary[key] is False,'Class state claims unverified full initialization')
    spec=importlib.util.spec_from_file_location('class_state_source_model',Path(__file__).with_name('verify-batch-metadata.py'))
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    source=json.loads((plan/'summary.json').read_text(encoding='utf-8'))
    check(file_digest(plan/'classes.jsonl')==source['artifacts']['classes']['digest'],'Static source class plan changed')
    classes=list(map(json.loads,(plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    check(set(inputs)==set(range(len(classes))),'Incomplete source static inputs')
    lookup,ancestry,parents,omitted=model.source_model(classes)
    with zipfile.ZipFile(artifact(root,summary['index'],'class-state')) as bundle:
        check(bundle.namelist()==['classes.jsonl'],'Unexpected class state index')
        states=list(map(json.loads,bundle.read('classes.jsonl').splitlines()))
    check([s['class_id'] for s in states]==list(range(len(classes))),'Class state identity coverage differs')
    provided=set();expected={}
    for c,state in zip(classes,states):
        id_=c['id'];original=inputs[id_]
        check((original['name'],original['source_sha256'],original['access'])==(c['name'],c['origin']['sha256'],c['access']),
              'Static IR source identity differs')
        check([{k:f[k] for k in ('name','descriptor','access')} for f in original['fields']]==c['fields'],'Static field declarations differ from plan')
        if id_ in omitted:continue
        fields=[]
        try:
            for index,field in enumerate(original['fields']):
                if not field['access']&8:continue
                cp=field['constant_value'];desc=field['descriptor'];reference=desc.startswith(('L','['))
                bits,string=constant_bits(desc,original['constants'][str(cp)],cp) if cp is not None else (0,None)
                size=8 if reference else {'Z':1,'B':1,'C':2,'S':2,'I':4,'F':4,'J':8,'D':8}.get(desc)
                check(size is not None,'Invalid static field descriptor')
                fields.append(dict(index=index,name=field['name'],descriptor=desc,access=field['access'],reference=reference,
                    declared_storage_bytes=size,constant=cp,initial_bits=bits,string_constant=string))
            initializers=original['initializers'];check(len(initializers)<=1,'Duplicate class initializer')
            initializer=None
            if initializers:
                m=initializers[0];check(m['descriptor']=='()V' and m['access']&0x500==0 and
                    (original['major']<51 or m['access']&8) and m['code_sha256'],'Invalid class initializer')
                initializer=dict(method=m['id'],code_sha256=m['code_sha256'],assembly_emitted=m['id'] in emitted_initializers)
            expected[id_]=dict(class_id=id_,source_sha256=c['origin']['sha256'],name=c['name'],access=c['access'],fields=fields,
                initializer=initializer,dependencies=dependencies(classes,inputs,lookup,parents,id_))
            if batch['schema']>=16 and c['name']=='jdk/internal/misc/UnsafeConstants' and c['origin']['loader']=='bootstrap':
                check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated') and initializer is not None,
                      'UnsafeConstants post-initializer requires original java.base Java initializer')
                expected[id_]['vm_post_initializer']='unsafe_constants'
            provided.add(id_)
        except ValueError:continue
    while True:
        invalid={id_ for id_ in provided if any(d not in provided for d in expected[id_]['dependencies'])}
        if not invalid:break
        provided-=invalid
    check(sorted(set(range(len(classes)))-provided)==summary['omitted_classes'],'Omitted class state coverage differs')
    for state in states:
        id_=state['class_id']
        if id_ not in provided:
            check(state['diagnostic'] and state['assembly_unit'] is None,'Unprovided class falsely has state/code');continue
        check(not state['diagnostic'] and {k:v for k,v in state.items() if k not in ('diagnostic','assembly_unit')}==expected[id_],
              'Class state differs from source constants/initialization order')
        check(isinstance(state['assembly_unit'],int) and 0<=state['assembly_unit']<len(summary['units']),'Invalid class state unit')
    fields=[f for id_ in sorted(provided) for f in states[id_]['fields']]
    refs=sum(f['reference'] for f in fields);root_cells=refs+len(provided)
    initializers=[states[id_]['initializer'] for id_ in provided if states[id_]['initializer']]
    counts=dict(class_capacity=len(classes),provided_classes=len(provided),static_fields=len(fields),static_reference_fields=refs,
        constant_values=sum(f['constant'] is not None for f in fields),string_constants=sum(f['string_constant'] is not None for f in fields),
        java_initializers=len(initializers),emitted_java_initializers=sum(i['assembly_emitted'] for i in initializers),
        initialization_dependencies=sum(len(states[id_]['dependencies']) for id_ in provided),root_cells=root_cells)
    check(all(summary[key]==value for key,value in counts.items()),'Class state counts differ')
    definitions,imports=set(),set();seen_classes=set();seen_functions=set();seen_fields=set();seen_causes=set();roots_seen=False
    for unit_id,unit in enumerate(summary['units']):
        check(unit['id']==unit_id and unit['object'] and not unit['assembler_diagnostic'],'Missing class-state COFF object')
        text=artifact(root,unit['assembly'],'class-state').read_text(encoding='utf-8');normalized='\n'.join(line.strip() for line in text.splitlines())
        defined,undefined=coff_symbols(artifact(root,unit['object'],'class-state'))
        check(not definitions&defined,'Duplicate class-state definition');definitions.update(defined);imports.update(undefined)
        for match in re.finditer(r'boom_class(\d+) DWORD 0434C4153h,2,0,0\n QWORD ([^\n]+)\n DWORD (\d+),0\n QWORD 0,0,0,OFFSET boom_batch_class_failure_root\1\n',text):
            id_=int(match[1]);check(id_ in provided and id_ not in seen_classes and int(match[3])==id_,'Unexpected/duplicate class descriptor');seen_classes.add(id_)
            state=states[id_];has_work=bool(state['dependencies'] or state['initializer'] or any(f['constant'] is not None for f in state['fields']))
            check(state['assembly_unit']==unit_id and match[2]==(f'OFFSET boom_batch_initialize_{id_}' if has_work else '0'),'Descriptor initializer differs')
        for match in re.finditer(r'boom_batch_initialize_(\d+) PROC FRAME[\s\S]*?boom_batch_initialize_\1 ENDP',text):
            id_=int(match[1]);check(id_ in provided and id_ not in seen_functions,'Unexpected/duplicate initializer');seen_functions.add(id_)
            check('\n'.join(line.strip() for line in match[0].splitlines())==initialization_body(states[id_]),'Generated initialization code differs from source order')
        for match in re.finditer(r'(?m)^boom_s(\d+)_(\d+) QWORD \?$',text):
            key=int(match[1]),int(match[2]);check(key not in seen_fields,'Duplicate static cell');seen_fields.add(key)
        for match in re.finditer(r'(?m)^boom_batch_class_failure_root(\d+) QWORD \?$',text):
            id_=int(match[1]);check(id_ not in seen_causes,'Duplicate cause root');seen_causes.add(id_)
        if 'boom_batch_class_roots LABEL QWORD' in text:
            check(not roots_seen,'Duplicate static root region');roots_seen=True
            expected_roots='boom_batch_class_roots LABEL QWORD\n'
            for id_ in sorted(provided):
                for f in states[id_]['fields']:
                    if f['reference']:expected_roots+=f"PUBLIC boom_s{id_}_{f['index']}\nboom_s{id_}_{f['index']} QWORD ?\n"
                expected_roots+=f'PUBLIC boom_batch_class_failure_root{id_}\nboom_batch_class_failure_root{id_} QWORD ?\n'
            check(expected_roots in text and f'boom_batch_class_root_count QWORD {root_cells}' in text,'Static root region differs')
            registry='boom_batch_class_descriptors LABEL QWORD\n'+''.join(f' QWORD OFFSET boom_class{i}\n' if i in provided else ' QWORD 0\n' for i in range(len(classes)))
            check(registry in text,'Class descriptor registry differs')
    functions={id_ for id_ in provided if states[id_]['dependencies'] or states[id_]['initializer'] or any(f['constant'] is not None for f in states[id_]['fields'])}
    field_ids={(id_,f['index']) for id_ in provided for f in states[id_]['fields']}
    check(seen_classes==seen_causes==provided and seen_fields==field_ids and seen_functions==functions and roots_seen,'Class-state assembly coverage differs')
    required={f'boom_class{i}' for i in provided}|{f'boom_batch_class_failure_root{i}' for i in provided}
    required|={f'boom_s{i}_{j}' for i,j in field_ids}|{f'boom_batch_initialize_{i}' for i in functions}
    required.update(('boom_batch_class_roots','boom_batch_class_root_count','boom_batch_class_descriptors'))
    check(definitions==required,'Class-state COFF exports differ from source-backed data/functions')
    allowed={f"boom_m{i['method']}_body" for i in initializers}|{f"boom_batch_literal_load_{id_}_{f['string_constant']}" for id_ in provided for f in states[id_]['fields'] if f['string_constant'] is not None}|{'boom_class_ensure32'}
    if batch['schema']>=16:allowed.update(('boom_java_unsafe_pool','boom_java_unsafe_constants'))
    check(imports-definitions<=allowed,'Unexpected class initialization external contract')
    return dict(verified=True,scope='source_static_storage_initialization_order_and_COFF_only',**counts,
        complete_original_class_initialization_verified=False,linked=False,game_started=False),definitions,imports
