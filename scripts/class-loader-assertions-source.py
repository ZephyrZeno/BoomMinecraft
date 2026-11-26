"""Normal ClassLoader source model, ready for a separately scheduled provider family.

The existing provider registry/tool identities stay untouched until the current
22-provider executions finish. This model shares the already executed ASM.
"""
import importlib.util
import json
from pathlib import Path
import zipfile


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


B=module('class_loader_assertions_source_contract','class-loader-assertions-candidate.py')
OWNER=B.OWNER
DIRECTIVES=B.DIRECTIVES
POOL='boom_class_loader_assertions_pool'
SERVICE='boom_class_loader_assertions'
CONTROL=set()
FOREIGN=set()
KERNELS=['classes32.asm','objects.asm','typed_arrays.asm','heap.asm','runtime_types.asm',
         'runtime_type_index.asm','types.asm','frames.asm','java_class_bootstrap.asm']
POLICY=dict(normal_source_layouts=True,registered_entries=1,registered_name='retrieveDirectives',
    class_and_package_overrides=False,assertion_configuration='registered_JCBT80_1_defaults',
    snapshot_default='application_default',four_fresh_typed_arrays=True,Java_class_initialization_state_modified=False,
    Java_constructor_invoked_by_VM=False,automatic_gc=False)


def index(summary,classes,S):
    wanted={OWNER,DIRECTIVES,'java/lang/Class','java/lang/String'}
    owners={c['name']:c for c in classes if c['origin']['loader']=='bootstrap' and c['name'] in wanted}
    S.check(set(owners)==wanted,'Original ClassLoader assertion classes are missing')
    owner,directives=owners[OWNER],owners[DIRECTIVES]
    raw={}
    for name in (OWNER,DIRECTIVES):
        c=owners[name]
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Original java.base class required')
        raw[name]=B.IR.Source(S.original_class(summary,c))
        S.check(raw[name].name==name and len(raw[name].methods)==len(c['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw[name].fields]==c['fields'], 'Original ClassLoader inventory differs')
    S.check(owner['origin']['sha256']=='1a3959527c8a805391bb21d0bccf9a0bb738383b444a24e87ed4ba130b4e788d',
            'Locked ClassLoader source differs')
    methods=[]
    for op,(name,descriptor) in enumerate((('registerNatives','()V'),('retrieveDirectives',B.DESC))):
        record,code=B.source_method(raw[OWNER],owner,name,descriptor)
        S.check(code is None and record.pop('code_sha256') is None and record['access']==0x10a,'Original native declaration changed')
        methods.append(dict(**record,loader='bootstrap',source_id='jdk:java.base',operation=op))
    java=[]
    for name,descriptor in (('<clinit>','()V'),('initializeJavaAssertionMaps','()V'),('desiredAssertionStatus','(Ljava/lang/String;)Z')):
        record,code=B.source_method(raw[OWNER],owner,name,descriptor)
        S.check(code is not None,'Original ClassLoader Java method is missing')
        java.append(record)
        expected=('registerNatives','()V') if name=='<clinit>' else ('retrieveDirectives',B.DESC) if name=='initializeJavaAssertionMaps' else None
        if expected:
            calls=[raw[OWNER].member(i['operand']['Constant']) for i in B.IR.stream(code['bytes']) if i['opcode']==0xb8]
            S.check(any((r['owner'],r['name'],r['descriptor'])==(OWNER,*expected) for r in calls),'Original native callsite differs')
    specs=[('classes','[Ljava/lang/String;',0,8,True),('classEnabled','[Z',0,8,True),
           ('packages','[Ljava/lang/String;',0,8,True),('packageEnabled','[Z',0,8,True),('deflt','Z',0,1,False)]
    S.check(len(directives['fields'])==5,'Assertion directives field inventory changed')
    with S.checked(summary['layouts']).open(encoding='utf-8') as lines:
        layout=next(r for line in lines if (r:=json.loads(line))['class_id']==directives['id'])
    fields=B.F.fields(directives,layout,specs,S)
    wanted_types={'[Ljava/lang/String;','[Z','Z'}
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as z:
        types={r['name']:r for line in z.open('types.jsonl') if
            (r:=json.loads(line))['name'] in wanted_types and r['defining_loader']=='bootstrap'}
    S.check(set(types)==wanted_types and types['[Ljava/lang/String;']['kind']==3 and types['[Z']['kind']==3 and
        types['[Ljava/lang/String;']['parent_component']==owners['java/lang/String']['id'] and
        types['[Z']['parent_component']==types['Z']['id'] and types['Z']['kind']==0,'Normal typed array definitions changed')
    config=summary['class_bootstrap']
    S.check((config['abi'],config['pool_bytes'],config['registered_prelinked_methods'],config['class_id'])==
        (1,80,10,owners['java/lang/Class']['id']) and config['class_sha256']==owners['java/lang/Class']['origin']['sha256'],
        'Original Class assertion VM configuration differs')
    configuration=B.assertion_configuration(config)
    with zipfile.ZipFile(S.checked(summary['class_state']['index'])) as z:
        states={r['class_id']:r for line in z.open('classes.jsonl') if
            (r:=json.loads(line))['class_id'] in (owner['id'],directives['id'])}
    S.check(states[owner['id']]['source_sha256']==owner['origin']['sha256'] and states[owner['id']]['initializer']==
        dict(method=java[0]['method'],code_sha256=java[0]['code_sha256'],assembly_emitted=True) and
        states[directives['id']]['source_sha256']==directives['origin']['sha256'] and
        states[directives['id']]['initializer'] is None and not states[directives['id']]['diagnostic'],
        'Normal original class initialization metadata changed')
    pins=B.pinned_sources(S.ART/'class-loader-assertions/pinned-sources/jdk-21.0.13+3')
    return dict(schema=1,owner=owner['id'],methods=methods,original_java=java,directives=directives['id'],
        directives_source_sha256=directives['origin']['sha256'],fields=fields,layout=layout['candidate'],
        array_types={name:types[name]['id'] for name in ('[Ljava/lang/String;','[Z')},assertion_class=config['class_id'],
        assertion_configuration=configuration,native_sources=pins,required_classes=sorted({owner['id'],directives['id'],config['class_id']}),
        required_base_modules=['class_literals'],pool_bytes=32,pool_abi=1)


def native_imports(meta):
    procs={'boom_object_new','boom_typed_multi_new','boom_trace_enter','boom_trace_leave'}
    data={'boom_heap_ptr','boom_java_class_bootstrap_pool','boom_java_class_pool','boom_java_string_literal_pool','boom_trace_pool',
        f"boom_class{meta['directives']}",f"boom_layout{meta['directives']}"}
    data.update(f'boom_t{n}' for n in meta['array_types'].values())
    data.update(f"boom_trace_method{m['method']}" for m in meta['methods'])
    return procs,data


def data(meta):
    retrieve=meta['methods'][1]['method']
    aliases=dict(DIRECTIVES_CLASS=f"boom_class{meta['directives']}",LAYOUT=f"boom_layout{meta['directives']}",
        STRING_ARRAY=f"boom_t{meta['array_types']['[Ljava/lang/String;']}",BOOLEAN_ARRAY=f"boom_t{meta['array_types']['[Z']}",
        RETRIEVE=f'boom_m{retrieve}_native')
    result=''.join(f'CLA_{key} TEXTEQU <{value}>\n' for key,value in aliases.items())
    result+=f"CLA_CLASS_ID EQU {meta['assertion_class']}\n"
    names={'classes':'CLASSES','classEnabled':'CLASS_ENABLED','packages':'PACKAGES','packageEnabled':'PACKAGE_ENABLED','deflt':'DEFAULT'}
    result+=''.join(f"CLA_{names[f['name']]} EQU {f['offset']}\n" for f in meta['fields'])
    return result+f'.data\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 050524E4Ch,1,0,1\n QWORD OFFSET boom_m{retrieve}_native,0\n'
