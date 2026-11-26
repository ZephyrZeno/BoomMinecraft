"""Build only a source-bound ClassLoader native candidate; no registry/kernel edits."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import zipfile


def script(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


S=script('runtime-provider-source')
IR=script('verify-translation-ir')
FR=script('verify-batch-frames')
F=script('file-bootstrap-source')
A=script('verify-batch-assembly')
OWNER='java/lang/ClassLoader'
DIRECTIVES='java/lang/AssertionStatusDirectives'
DESC='()L'+DIRECTIVES+';'
KERNEL=S.ROOT/'native/providers/class_loader_assertions.asm.inc'
PINS={
    'ClassLoader.c':('e68e8b04e5216eaf999e500dca2b8226e9c5946641f69abb353dc5e8963047bf',
        'src/java.base/share/native/libjava/ClassLoader.c'),
    'javaAssertions.cpp':('af7c77f65a759fb1673937ff133e6c389811092dc435465d8fd19f10733b3a96',
        'src/hotspot/share/classfile/javaAssertions.cpp'),
}


def pinned_sources(directory):
    result={}
    for name,(sha,relative) in PINS.items():
        path=(Path(directory)/name).resolve()
        S.check(path.is_relative_to(S.ART) and S.digest(path)['sha256']==sha,'Pinned OpenJDK source differs: '+name)
        result[name]=dict(**S.artifact(path),url='https://raw.githubusercontent.com/openjdk/jdk21u/jdk-21.0.13%2B3/'+relative)
    text=Path(result['ClassLoader.c']['path']).read_text()
    table=re.search(r'static JNINativeMethod methods\[\] = \{(.*?)\};',text,re.S)
    S.check(table and re.findall(r'\{\s*"([^"]+)",\s*"([^"]+)",\s*\(void \*\)&(\w+)\s*\}',table[1])==
            [('retrieveDirectives',DESC,'JVM_AssertionStatusDirectives')], 'Pinned ClassLoader registration table differs')
    return result


def source_method(raw,c,name,descriptor):
    [found]=[(i,m) for i,m in zip(c['method_ids'],raw.methods) if (m['name'],m['descriptor'])==(name,descriptor)]
    ident,m=found
    code=raw.code(m)
    return dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],owner=c['name'],name=name,
                descriptor=descriptor,access=m['access'],code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None),code


def assertion_configuration(config,requested=None):
    S.check(config['class_assertion_overrides_supported'] is False,'Named assertion overrides are outside this VM profile')
    requested={} if requested is None else requested
    S.check(isinstance(requested,dict) and set(requested)<={'system_default','application_default','class_overrides','package_overrides'},
            'Unknown assertion VM configuration')
    result={}
    for name,source in (('system_default','system_assertions_enabled'),('application_default','application_assertions_enabled')):
        value=requested.get(name,config[source])
        S.check(type(value) is bool and value==config[source],'Assertion defaults must match the actual source JCBT configuration')
        result[name]=value
    for name in ('class_overrides','package_overrides'):
        value=requested.get(name,[])
        S.check(isinstance(value,list) and not value,'Class/package assertion overrides are not supported by this VM profile')
        result[name]=value
    return result


def contract(state_file,sources):
    state=S.read(state_file)
    batch,plan=(Path(state[k]).resolve() for k in ('batch','plan'))
    identity,summary,classes=S.base(batch,plan)
    S.check(state['status']=='accepted' and state['provider_count']==22 and
        state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'] and
        state['tool_sources']==S.tools_identity(),'Frozen current normal provider input required')
    native_sources=pinned_sources(sources)
    names={c['name']:c for c in classes if c['origin']['loader']=='bootstrap'}
    owners={name:names[name] for name in (OWNER,DIRECTIVES)}
    raw={}
    for name,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Original java.base class required')
        raw[name]=IR.Source(S.original_class(summary,c))
        S.check(raw[name].name==name and len(raw[name].methods)==len(c['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw[name].fields]==c['fields'],'Original field/method inventory differs')
    owner=owners[OWNER]
    S.check(owner['origin']['sha256']=='1a3959527c8a805391bb21d0bccf9a0bb738383b444a24e87ed4ba130b4e788d',
            'ClassLoader source pin differs')
    methods=[]
    for op,(name,descriptor) in enumerate((('registerNatives','()V'),('retrieveDirectives',DESC))):
        record,code=source_method(raw[OWNER],owner,name,descriptor)
        S.check(code is None and record['access']==0x10a,'Original private static native contract differs')
        methods.append(dict(**record,operation=op))
    java=[]
    for name,descriptor in (('<clinit>','()V'),('initializeJavaAssertionMaps','()V'),('desiredAssertionStatus','(Ljava/lang/String;)Z')):
        record,code=source_method(raw[OWNER],owner,name,descriptor)
        S.check(code is not None,'Original ClassLoader Java body is missing')
        java.append(record)
        calls=[]
        for ins in IR.stream(code['bytes']):
            if ins['opcode']==0xb8:
                ref=raw[OWNER].member(ins['operand']['Constant'])
                calls.append((ins['pc'],ref['owner'],ref['name'],ref['descriptor']))
        expected=('registerNatives','()V') if name=='<clinit>' else ('retrieveDirectives',DESC) if name=='initializeJavaAssertionMaps' else None
        if expected:S.check(any((o,n,d)==(OWNER,*expected) for _,o,n,d in calls),'Original native callsite differs')
    c=owners[DIRECTIVES]
    fields=[('classes','[Ljava/lang/String;',0,8,True),('classEnabled','[Z',0,8,True),
            ('packages','[Ljava/lang/String;',0,8,True),('packageEnabled','[Z',0,8,True),('deflt','Z',0,1,False)]
    S.check(len(c['fields'])==5,'Assertion directives field inventory differs')
    with S.checked(summary['layouts']).open() as lines:
        layout=next(r for line in lines if (r:=json.loads(line))['class_id']==c['id'])
    offsets=F.fields(c,layout,fields,S)
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as bundle:
        types={r['name']:r for line in bundle.open('types.jsonl') if
            (r:=json.loads(line))['defining_loader']=='bootstrap' and r['name'] in ('[Ljava/lang/String;','[Z','Z')}
    S.check(set(types)=={'[Ljava/lang/String;','[Z','Z'} and types['[Ljava/lang/String;']['kind']==3 and
        types['[Ljava/lang/String;']['parent_component']==names['java/lang/String']['id'] and types['[Z']['kind']==3 and
        types['[Z']['parent_component']==types['Z']['id'] and types['Z']['kind']==0,'Original array types differ')
    config=summary['class_bootstrap']
    S.check((config['abi'],config['pool_bytes'],config['registered_prelinked_methods'])==(1,80,10) and
        all(config[k] is False for k in ('class_assertion_overrides_supported','system_assertions_enabled','application_assertions_enabled')),
        'The current declared VM assertion configuration differs')
    S.check(not state.get('assertion_options'),'Unbound assertion command-line options cannot override the source JCBT profile')
    configuration=assertion_configuration(config,state.get('assertion_configuration'))
    frame=Path(state['frame_manifest'])
    S.check(S.digest(frame.with_name('verification.json'))['sha256']==state['frame_verification_sha256'],'Native frame receipt differs')
    overlay=S.read(frame)
    rows={r['id']:r for r in overlay['source']['original_native_declarations']}
    for m in methods:
        row=rows[m['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[k]==m[k] for k in
            ('class_id','class_sha256','name','descriptor','access')),'Original native source frame differs')
    with zipfile.ZipFile(S.checked(summary['class_state']['index'])) as bundle:
        states={r['class_id']:r for line in bundle.open('classes.jsonl') if (r:=json.loads(line))['class_id'] in {owner['id'],c['id']}}
    S.check(states[owner['id']]['initializer']==dict(method=java[0]['method'],code_sha256=java[0]['code_sha256'],assembly_emitted=True) and
        states[c['id']]['initializer'] is None and not states[c['id']]['diagnostic'],'Normal source class initialization differs')
    return dict(base=identity,input_state=S.artifact(state_file),native_sources=native_sources,methods=methods,original_java=java,
        owner=owner['id'],directives=c['id'],directives_source_sha256=c['origin']['sha256'],fields=offsets,
        layout=layout['candidate'],array_types={name:types[name]['id'] for name in ('[Ljava/lang/String;','[Z')},
        assertion_class=config['class_id'],class_states={str(k):v for k,v in states.items()},frame=dict(manifest=S.artifact(frame),
        verification=S.artifact(frame.with_name('verification.json'))),no_class_or_package_overrides=True,
        assertion_configuration=configuration,
        registered_JCBT_defaults_read_at_runtime=True,returned_default='application_default_at_JCBT_offset_60',
        Java_constructor_called_by_VM=False,automatic_gc=False)


def assembly(meta):
    imports={'boom_class_ensure32','boom_object_new','boom_typed_multi_new','boom_trace_enter','boom_trace_leave'}
    data={'boom_heap_ptr','boom_java_class_bootstrap_pool','boom_java_class_pool','boom_java_string_literal_pool','boom_trace_pool',
          f"boom_class{meta['owner']}",f"boom_class{meta['directives']}",f"boom_layout{meta['directives']}"}
    data.update(f'boom_t{n}' for n in meta['array_types'].values())
    data.update(f"boom_trace_method{m['method']}" for m in meta['methods'])
    parts=['option casemap:none\n']
    parts.extend(f'EXTERN {name}:PROC\n' for name in sorted(imports))
    parts.extend(f'EXTERN {name}:BYTE\n' for name in sorted(data))
    retrieve=meta['methods'][1]['method']
    aliases=dict(DIRECTIVES_CLASS=f"boom_class{meta['directives']}",LAYOUT=f"boom_layout{meta['directives']}",
        STRING_ARRAY=f"boom_t{meta['array_types']['[Ljava/lang/String;']}",BOOLEAN_ARRAY=f"boom_t{meta['array_types']['[Z']}",
        RETRIEVE=f'boom_m{retrieve}_native')
    parts.extend(f'CLA_{key} TEXTEQU <{value}>\n' for key,value in aliases.items())
    parts.append(f"CLA_CLASS_ID EQU {meta['assertion_class']}\n")
    names={'classes':'CLASSES','classEnabled':'CLASS_ENABLED','packages':'PACKAGES','packageEnabled':'PACKAGE_ENABLED','deflt':'DEFAULT'}
    parts.extend(f"CLA_{names[f['name']]} EQU {f['offset']}\n" for f in meta['fields'])
    parts.append('.data\nALIGN 8\nPUBLIC boom_class_loader_assertions_pool\nboom_class_loader_assertions_pool DWORD 050524E4Ch,1,0,1\n')
    parts.append(f' QWORD OFFSET boom_m{retrieve}_native,0\n')
    exports={'boom_class_loader_assertions_pool','boom_class_loader_assertions'}
    for m in meta['methods']:
        parts.append(f".code\nPUBLIC boom_m{m['method']}\nPUBLIC boom_m{m['method']}_native\n")
        parts.append(FR.native_adapter(m['method'],m['class_id'],'boom_class_loader_assertions_pool','boom_class_loader_assertions',m['operation']))
        exports.update(f"boom_m{m['method']}{suffix}" for suffix in ('','_native'))
    parts.extend((KERNEL.read_text(encoding='utf-8'),'\nEND\n'))
    return ''.join(parts),exports,imports|data


def verify(path):
    path=Path(path).resolve()
    m=S.read(path)
    S.check(path.is_relative_to(S.ART) and m['family']=='normal-class-loader-assertions-candidate','Expected isolated ClassLoader candidate')
    meta=contract(S.checked(m['metadata']['input_state']),Path(m['native_source_directory']))
    S.check(meta==m['metadata'] and S.artifact(KERNEL)==m['kernel'] and S.artifact(Path(__file__))==m['tool'], 'Candidate source identity changed')
    body,exports,imports=assembly(meta)
    asm,obj=S.checked(m['assembly']),S.checked(m['object'])
    S.check(asm.parent==obj.parent==path.parent and asm.read_text(encoding='utf-8')==body and
        S.artifact(Path(m['assembler']['path']))==m['assembler'] and A.coff_symbols(obj)==(exports,imports), 'Candidate canonical ASM or COFF differs')
    return dict(schema=1,verified=True,scope='original_ClassLoader_native_declarations_no_override_assertion_VM_ASM_COFF_only',
        candidate=S.artifact(path),source_methods=[r['method'] for r in meta['methods']],
        Java_class_state_modified=False,shared_provider_registered=False,linked=False,executed=False,game_started=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('state','sources','assembler','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    output=a.output.resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh project-isolated output required')
    meta=contract(a.state.resolve(),a.sources.resolve())
    output.mkdir(parents=True)
    body,exports,imports=assembly(meta)
    asm=output/'provider.asm'
    asm.write_text(body,encoding='utf-8',newline='\n')
    obj=asm.with_suffix('.obj')
    with (output/'assembler.log').open('wb') as log:
        subprocess.run([str(a.assembler.resolve()),'/nologo','/c',f'/Fo{obj}',str(asm)],stdout=log,stderr=subprocess.STDOUT,check=True)
    candidate=output/'candidate.json'
    S.write(candidate,dict(schema=1,family='normal-class-loader-assertions-candidate',metadata=meta,
        native_source_directory=str(a.sources.resolve()),kernel=S.artifact(KERNEL),tool=S.artifact(Path(__file__)),
        assembler=S.artifact(a.assembler),assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        shared_provider_registered=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(candidate))
    print(candidate)
