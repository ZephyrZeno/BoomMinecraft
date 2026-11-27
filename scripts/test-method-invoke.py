"""Actual invoke0 over normal source Method objects; default API stops preserved."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import zipfile
from threading import Barrier,get_native_id
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location('method_invoke_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('method-invoke-candidate');S=B.S;N=module('test-normal-methods-candidate')
P,Q,U,Context=N.P,N.Q,N.U,N.Context
addr,proc=N.addr,N.proc
FIXTURES=[('java/lang/Class','getDeclaredMethod','(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;'),
    ('java/lang/Class','getEnumConstantsShared','()[Ljava/lang/Object;'),
    ('java/util/EnumSet','noneOf','(Ljava/lang/Class;)Ljava/util/EnumSet;'),
    ('java/lang/reflect/Method','invoke','(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;'),
    ('java/lang/Throwable','getMessage','()Ljava/lang/String;'),('java/lang/Throwable','getCause','()Ljava/lang/Throwable;'),
    ('java/lang/reflect/InvocationTargetException','getTargetException','()Ljava/lang/Throwable;'),
    ('java/lang/reflect/InvocationTargetException','getCause','()Ljava/lang/Throwable;'),
    ('java/lang/System','setJavaLangAccess','()V'),('java/lang/String','toCharArray','()[C'),
    ('java/lang/Enum','name','()Ljava/lang/String;')]
CASES=[('java/util/Optional','empty','()Ljava/util/Optional;'),('java/util/Collections','emptyList','()Ljava/util/List;'),
    ('java/lang/System','getSecurityManager','()Ljava/lang/SecurityManager;'),
    ('java/lang/StackWalker$Option','values','()[Ljava/lang/StackWalker$Option;')]


def prove_methods_state(config):
    candidate_file=S.checked(config['candidate']);candidate=S.read(candidate_file)
    state=S.read(S.checked(candidate['metadata']['input_state']))
    S.check(state['tool_sources']==S.tools_identity(),'Normal Method producer is not in current source namespace')
    S.check(N.B.verify(candidate_file)==S.read(S.checked(config['candidate_proof'])),'Current ordinary Method source/machine proof differs')
    return candidate


def additional_diagnostics(meta,sites,existing,summary,output,assemble):
    """Exactly the lazy source frontiers a full selector would have requested.

    Historical source closure objects are immutable. Additional invocation
    capabilities therefore get their own ordinary diagnostic table, using
    the original source row and unchanged development fail-stop protocol.
    This does not grant any Java Code or class-initialization capability.
    """
    required={r['callback'] for r in sites if r['callback']} - existing
    if not required:return None,[],[]
    source_rows={f"boom_m{r['method']}":r for r in meta['records']}
    S.check(required<=set(source_rows),'Missing source initializer diagnostics must come from a full selector')
    owners={source_rows[symbol]['owner'] for symbol in required};original={};pins=[]
    for shard in summary['shards']:
        path=S.checked(shard['zip'])
        with zipfile.ZipFile(path) as z:
            found=False
            for owner in owners:
                member=f'classes/{owner:06}.json'
                if member not in z.namelist():continue
                row=json.loads(z.read(member));original[owner]=row;found=True
            if found:pins.append(S.artifact(path))
    S.check(set(original)==owners,'Original lazy invocation source shards are incomplete')
    frontiers=[]
    for symbol in sorted(required):
        row=source_rows[symbol];cls=original[row['owner']]
        [method]=[m for m in cls['methods'] if m['id']==row['method']]
        S.check(cls['source_sha256']==row['source_sha256'] and method['code_sha256']==row['code_sha256'] and
            method['assembly_emitted']==row['assembly_emitted'] and (method['name'],method['descriptor'])==(row['name'],row['descriptor']),
            'Additional diagnostic original source/Code differs')
        frontiers.append(dict(kind='unselected_method' if method['assembly_emitted'] else 'method',symbol=symbol,
            reason='Original noarg static reference target has not been selected',binding=None,class_id=row['owner'],
            source_sha256=row['source_sha256'],method={key:method[key] for key in
                ('id','name','descriptor','code_sha256','stage','assembly_emitted','assembly_unit')}))
    diagnostic=module('diagnostic-closure');records=diagnostic.rows(frontiers)
    original_text=diagnostic.body(records,True)
    text=original_text.replace('boom_diagnostic_','boom_minvoke_diagnostic_')
    S.check(text.replace('boom_minvoke_diagnostic_','boom_diagnostic_')==original_text,
        'Additional source diagnostics changed more than their isolated public namespace')
    asm=output/'additional-source-stops.asm';obj=asm.with_suffix('.obj');asm.write_text(text);assemble(asm,obj)
    exports={r['symbol'] for r in records}|{'boom_minvoke_diagnostic_rows','boom_minvoke_diagnostic_pool',
        'boom_minvoke_diagnostic_stop','boom_minvoke_diagnostic_context_map',
        'boom_minvoke_diagnostic_context_map_record','boom_minvoke_diagnostic_context_map_row'}
    S.check(B.A.coff_symbols(obj)==(exports,set()),'Actual additional source diagnostic protocol differs')
    receipt=output/'additional-source-stops.json'
    S.write(receipt,dict(rows=records,ordinary_diagnostic_protocol_unchanged=True,only_public_namespace_changed=True,
        selected_Java_Code_added=False,selected_class_roots_added=False,source_shards=pins,
        helpers=[S.artifact(ROOT/'scripts/diagnostic-closure.py'),S.artifact(diagnostic.HELPER),
            *[S.artifact(file) for file in diagnostic.CONTEXT_HELPERS]],assembly=S.artifact(asm),object=S.artifact(obj)))
    return obj,records,[asm,receipt,ROOT/'scripts/diagnostic-closure.py',diagnostic.HELPER,*diagnostic.CONTEXT_HELPERS]


def build(candidate_file,methods_images,output,*,allow_equivalent_batch=False):
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Current invoke source/machine proof differs')
    candidate=S.read(candidate_file);meta=candidate['metadata']['source'];original=S.read(methods_images)
    abort_source=ROOT/'native/runtime/monitor_abort.asm'
    runtime_metadata=S.checked(candidate['metadata']['runtime']).with_name('runtime.json')
    S.check(S.read(runtime_metadata)['sources']['native/runtime/monitor_abort.asm']==S.digest(abort_source)['sha256'],
        'Controlled source-stop cleanup runtime source differs')
    for row in original['inputs']:N.D.checked(row)
    producer=prove_methods_state(original);normal=producer['metadata']['source']
    S.check(normal['method_class']==meta['method_class'] and all(normal['fields'][r['name']]==r['offset'] for r in meta['method_fields']),
        'Invocation normal Method fields differ from the actual ordinary producer')
    source_manifest=S.checked(original['source_manifest']);closure=S.read(source_manifest)
    # A new named batch may reuse an old Java closure only through the caller's
    # already sealed complete equality proof, never a manifest-label rewrite.
    state=S.read(S.checked(candidate['metadata']['input_state']))
    same_batch=closure['source_batch_summary_sha256']==candidate['metadata']['base']['batch_summary']['digest']['sha256']
    lineage=None
    if not same_batch:
        S.check(allow_equivalent_batch,'Explicit equivalent-source batch guard is required')
        transition=module('extend-runtime-provider-set')
        lineage=transition.equivalent_named_batch(Path(closure['batch']),Path(state['batch']),Path(state['plan']),state['batch_verification_sha256'])
        S.check(lineage==state['batch_source_lineage']==original.get('source_batch_equivalence'),
            'Complete freshly rechecked source equivalence differs from current Method image/state')
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh method invoke execution required')
    output.mkdir(parents=True)
    selected_classes={r['class_id'] for r in closure['selected_classes']}
    site_body,site_imports,sites=B.C.selected_sites(meta,selected_classes,closure['selected_methods'])
    site_text='option casemap:none\n'+''.join('EXTERN '+p+(':BYTE\n' if p.startswith('boom_class') else ':PROC\n') for p in sorted(site_imports))+site_body+'END\n'
    assembler=Path(candidate['assembler']['path']);site_asm=output/'selected-sites.asm';site_obj=site_asm.with_suffix('.obj');site_asm.write_text(site_text)
    def assemble(source,obj):
        with source.with_suffix('.log').open('wb') as log:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),source],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    assemble(site_asm,site_obj)
    S.check(B.A.coff_symbols(site_obj)==({B.C.SELECTED},site_imports),'Actual selected capability sites differ')
    diagnostic=S.read(source_manifest.parent/'diagnostic.json');targets={f"boom_m{r['method']}" for r in meta['methods']}
    rows=[r for r in diagnostic['rows'] if r['symbol'] in targets]
    S.check(len(rows)==2 and all(r['category']==2 for r in rows),'Only the two original invoke0 native stops may be removed')
    old_asm=S.checked(original['remaining_stops']);old_obj=S.checked(original['remaining_stops_object'])
    remaining,delta=N.D.remove_stops(old_asm.read_bytes(),rows,closure['diagnostic_context_rows'],targets)
    stops=output/'remaining-stops.asm';stops_obj=stops.with_suffix('.obj');stops.write_bytes(remaining);assemble(stops,stops_obj)
    old_defs,old_refs=B.A.coff_symbols(old_obj,{'WaitOnAddress','WakeByAddressAll'})
    S.check(B.A.coff_symbols(stops_obj,{'WaitOnAddress','WakeByAddressAll'})==(old_defs-targets,old_refs),'Other diagnostic COFF symbols changed')
    _,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    existing=old_defs|{f'boom_m{ident}' for ident in closure['selected_methods']}
    extra_obj,extra_rows,extra_pins=additional_diagnostics(meta,sites,existing,summary,output,assemble)
    names={(r['origin']['loader'],r['name']):r for r in classes};members=[]
    wanted=set(FIXTURES)|{(r['owner'],r['name'],r['descriptor']) for r in meta['original_java']}
    for owner in {r[0] for r in wanted}:
        cls=names['bootstrap',owner];raw=B.C.IR.Source(S.original_class(summary,cls))
        for ident,m in zip(cls['method_ids'],raw.methods):
            if (owner,m['name'],m['descriptor']) not in wanted:continue
            code=raw.code(m);S.check(code is not None,'Original invocation API fixture Code missing')
            row=dict(owner=owner,name=m['name'],descriptor=m['descriptor'],method=ident,class_id=cls['id'],
                class_sha256=cls['origin']['sha256'],code_sha256=hashlib.sha256(code['bytes']).hexdigest())
            selected=closure['selected_methods'].get(str(ident))
            # Preserve actual stops for unselected Java; do not synthesize it.
            row['selected']=bool(selected and selected['class_id']==cls['id'] and selected['source_sha256']==row['class_sha256'] and selected['code_sha256']==row['code_sha256'])
            members.append(row)
    S.check(len(members)==len(wanted),'Original invoke fixture inventory incomplete')
    exports=set();response=[];objects=[]
    for line in S.checked(original['link_response']).read_text().splitlines():
        if line.startswith('/OUT:'):continue
        if line.startswith('/EXPORT:'):exports.add(line.removeprefix('/EXPORT:'));continue
        if line.startswith('"'):
            file=Path(line.strip('"')).resolve();file=stops_obj if file==old_obj else file
            objects.append(file);line='"'+str(file)+'"'
        response.append(line)
    for file in [site_obj,S.checked(candidate['object']),*([extra_obj] if extra_obj else [])]:objects.append(file);response.append('"'+str(file)+'"')
    exports|={'boom_diagnostic_context_map','boom_diagnostic_context_map_row'}
    if extra_obj:exports|={'boom_minvoke_diagnostic_context_map','boom_minvoke_diagnostic_context_map_row'}
    exports|=set(candidate['exports'])|{B.C.SELECTED}|{f"boom_m{r['method']}" for r in members}
    exports|={r['symbol'] for r in [meta['source_VM_invoke_guard']]}|{f"boom_class{row['owner']}" for row in meta['records'] if row['owner'] in selected_classes}
    exports|={f"boom_{kind}{meta['source_classes'][n]}" for n in ('java/lang/Throwable','java/lang/IllegalArgumentException','java/lang/reflect/InvocationTargetException') for kind in ('class','layout')}
    dll=output/'method-invoke.dll';rsp=output/'link.rsp';rsp.write_text('\n'.join(response+['/OUT:"'+str(dll)+'"',*['/EXPORT:'+p for p in sorted(exports)]])+'\n')
    with (output/'link.log').open('wb') as log:
        subprocess.run([assembler.with_name('link.exe'),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    normal_projection={key:normal[key] for key in ('owner','methods','method_class','fields','arrays')}
    record=dict(schema=1,image=S.artifact(dll),runtime=original['runtime'],methods_images=S.artifact(methods_images),
        normal_Method_projection=normal_projection,current_Method_candidate=original['candidate'],current_Method_proof=original['candidate_proof'],
        candidate=S.artifact(candidate_file),candidate_proof=S.artifact(candidate_file.with_name('verification.json')),
        source_manifest=original['source_manifest'],source_proof=original['source_proof'],source_input_state=S.artifact(S.checked(candidate['metadata']['input_state'])),
        source_batch_equivalence=lineage,historical_full_selection_reused=not same_batch,current_full_selection_reverified=False,
        original_Java_Code_or_class_state_changed=False,stop_delta=delta,selection_sites=sites,
        selection_source=S.artifact(site_asm),selection_object=S.artifact(site_obj),link_response=S.artifact(rsp),
        original_diagnostic=S.artifact(source_manifest.parent/'diagnostic.json'),additional_source_diagnostics=extra_rows,
        inputs=[S.artifact(p) for p in [*objects,site_asm,stops,rsp,Path(__file__),*extra_pins,source_manifest.parent/'diagnostic.json',abort_source,runtime_metadata]],
        original_inputs=original['inputs'],execution_tool=S.artifact(Path(__file__)),fixture_methods=members,
        case_types={owner:names['bootstrap',owner]['id'] for owner,_,_ in CASES},method_types=original['type_names'],
        root_spans=original['root_spans'],
        shared_provider_registered=False,formal_runtime_acceptance_complete=False,executed=False,game_started=False)
    path=output/'images.json';S.write(path,record);return path


def run(images):
    config=S.read(images);S.check(config['execution_tool']==S.artifact(Path(__file__)),'Invoke worker changed')
    for row in config['inputs']+config['original_inputs']:N.D.checked(row)
    meta=S.read(S.checked(config['candidate']))['metadata']['source'];normal=config['normal_Method_projection']
    runtime=S.checked(config['runtime'])
    with os.add_dll_directory(str(runtime.parent)):rt,image=c.CDLL(str(runtime)),c.CDLL(str(S.checked(config['image'])))
    heap=proc(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and proc(image,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Invoke source heap binding failed')
    methods={(r['owner'],r['name'],r['descriptor']):r['method'] for r in config['fixture_methods']}
    native={r['operation']:r['method'] for r in meta['methods']};pool=addr(image,'boom_java_class_pool');failure=None;stages=[];main=registry=0
    diagnostic_rows=S.read(S.checked(config['original_diagnostic']))['rows']
    def context_fault(ctx):
        if ctx[0]!=0xb001:return None
        for prefix,rows in [('boom_diagnostic_',diagnostic_rows),('boom_minvoke_diagnostic_',config['additional_source_diagnostics'])]:
            if not rows:continue
            row=proc(image,prefix+'context_map_row',U,P,P)(ctx,addr(image,prefix+'context_map'))
            if row:
                S.check(0<row<=len(rows) and rows[row-1]['id']==row,'Observed source context diagnostic row is not sealed')
                return dict(namespace=prefix,belongs_to_original_full_selection=prefix=='boom_diagnostic_',row=rows[row-1],
                    controller_auto_admission_permitted=False)
        return None
    def call(ident,args,check=True,ctx=None):
        ctx=Context() if ctx is None else ctx
        value=proc(image,'boom_m'+str(ident),Q,P,P)(ctx,(Q*max(1,len(args)))(*[v&0xffffffffffffffff for v in args]))
        stages.append(dict(method=ident,context=list(ctx),value=value,source_fault=context_fault(ctx)))
        if check:S.check(not ctx[0] and not ctx[3],'Original invoke call failed: '+repr((ident,list(ctx))))
        return value,ctx
    def java(owner,name,descriptor,args):return call(methods[owner,name,descriptor],args)[0]
    def mirror(ident):
        ctx=Context();value=proc(rt,'boom_java_class_load',P,P,P,U)(ctx,pool,ident)
        S.check(value and not ctx[0],'Normal Class mirror failed');return value
    def string(value):
        raw=value.encode('utf-16-le','surrogatepass');buffer=c.create_string_buffer(raw);ctx=Context()
        value=proc(rt,'boom_java_property_copy',P,P,P,P,U)(ctx,addr(image,'boom_java_platform_properties_pool'),buffer,len(raw)//2)
        S.check(value and not ctx[0],'Normal String factory failed');return value
    def text(value):
        if not value:return None
        chars=java('java/lang/String','toCharArray','()[C',[value]);return c.string_at(chars,Q.from_address(chars-16).value).decode('utf-16-le','surrogatepass')
    def refs(length):
        tag=Q.from_address(addr(image,'boom_normal_method_pool')+64).value
        value=proc(rt,'boom_heap_alloc',P,P,Q,Q,Q)(heap,length*8,length,tag)
        S.check(value,'Reference array allocation failed');return value
    def lookup(owner,name):
        ident=config['case_types'].get(owner)
        if ident is None:
            [ident]=[int(i) for i,row in config['method_types'].items() if row['loader']=='bootstrap' and row['name']==owner]
        return java('java/lang/Class','getDeclaredMethod','(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;',
            [mirror(ident),string(name),refs(0)])
    results=[];api=None;api_context=None;cleanup=None;negative=[];threads=[];arity=None;wrapped=[];collections=[];preserved_array=None;enum_names=None
    try:
        ctx=Context();main=proc(image,'boom_methods_test_bootstrap',P,P)(ctx)
        S.check(main and not ctx[0],'Original constructor-only primordial setup failed')
        registry=P.from_address(addr(image,'boom_provider_thread_registry')).value
        prepared=U.from_address(addr(image,meta['source_VM_invoke_guard']['symbol'])).value
        S.check(prepared==0,'Source component did not retain the natural pre-MH flag')
        for owner,name,descriptor in CASES:
            method=lookup(owner,name);before=None
            try:before=U.from_address(addr(image,'boom_class'+str(config['case_types'][owner]))+8).value
            except ValueError:pass
            pair=[]
            for operation in (0,1):
                value,ctx=call(native[operation],[method,0,0],False)
                pair.append(dict(native_operation=operation,value=value,context=list(ctx)))
                if not ctx[0]:
                    if name=='getSecurityManager':S.check(not value,'Original null static result was replaced')
                    else:S.check(value and proc(rt,'boom_heap_contains',U,P,P)(heap,value),'Static reference result was not a live normal oop')
                    if value:
                        type_context=Context();type_row=proc(rt,'boom_runtime_row',P,P,P,P)(value,addr(image,'boom_runtime_type_map'),type_context)
                        S.check(type_row and not type_context[0],'Target result is not in the original normal type map')
                        ident=U.from_address(type_row+16).value;pair[-1]['normal_runtime_type']=config['method_types'][str(ident)]['name']
                    else:pair[-1]['normal_runtime_type']=None
            if all(not item['context'][0] for item in pair):
                if name=='values':
                    arrays=[list((Q*U.from_address(item['value']-20).value).from_address(item['value'])) for item in pair]
                    S.check(pair[0]['value']!=pair[1]['value'] and arrays[0]==arrays[1] and len(arrays[0])==3,
                        'Original enum values did not return independent accurate clones')
                    preserved_array=pair[0]['value']
                    enum_names=[text(java('java/lang/Enum','name','()Ljava/lang/String;',[element])) for element in arrays[0]]
                    S.check(enum_names==['RETAIN_CLASS_REFERENCE','SHOW_REFLECT_FRAMES','SHOW_HIDDEN_FRAMES'],
                        'Original values/Enum.name Java produced different constants')
                    pair[0]['enum_names']=pair[1]['enum_names']=enum_names
                    for item in pair:item['normalized']='ARRAY:'+','.join(enum_names)
                else:
                    S.check(pair[0]['value']==pair[1]['value'],'Two original native entry implementations disagree')
                    expected={'empty':'java/util/Optional','emptyList':'java/util/Collections$EmptyList','getSecurityManager':None}[name]
                    for item in pair:
                        S.check(item['normal_runtime_type']==expected,'Original source return dynamic class differs')
                        item['normalized']='NULL' if expected is None else expected.replace('/','.')
            results.append(dict(owner=owner,name=name,descriptor=descriptor,declaring_state_before=before,natives=pair))
            if any(r['context'][0] for r in pair):break
        if len(results)==len(CASES) and all(not r['context'][0] for case in results for r in case['natives']):
            method=lookup('java/util/Optional','empty')
            value,ctx=call(native[0],[method,1,refs(0)],False)
            S.check(not ctx[0] and value==results[0]['natives'][0]['value'],'Static receiver was not ignored or empty args differs')
            _,ctx=call(native[1],[method,0,refs(1)],False)
            cause=P.from_address(c.addressof(ctx)+16).value
            S.check(ctx[0]==16 and cause,'Wrong arity did not construct the original Java exception')
            S.check(P.from_address(cause-8).value==addr(image,'boom_layout'+str(meta['source_classes']['java/lang/IllegalArgumentException'])),
                'Wrong arity did not use the actual normal IllegalArgumentException layout')
            kind=U.from_address(addr(image,'boom_class'+str(meta['source_classes']['java/lang/IllegalArgumentException']))+8).value
            S.check(kind==2,'Original IllegalArgumentException constructor class was not initialized')
            message=text(java('java/lang/Throwable','getMessage','()Ljava/lang/String;',[cause]))
            S.check(message=='wrong number of arguments','Wrong-arity exception message differs from original C')
            arity=dict(context=list(ctx),message=message)
            for argument,expected in [(0,4),(1,7),(string('wrong receiver class'),7)]:
                value,ctx=call(native[0],[argument,0,0],False)
                S.check(not value and ctx[0]==expected,'Invalid normal Method pointer/class was accepted')
                negative.append(dict(case='Method_heap_or_type',context=list(ctx)))
            for owner,name in [('java/lang/String','toString'),('java/lang/Math','random')]:
                unsupported=lookup(owner,name);_,ctx=call(native[0],[unsupported,0,0],False)
                S.check(ctx[0]==20,'Unsupported invocation shape did not stop explicitly')
                negative.append(dict(case=owner+'.'+name,context=list(ctx)))
            # The actual original VM Java body naturally throws while this
            # constructor-only component has never run System.initPhase1.
            # No savedProps field or VM flag is changed by this test.
            throwing=lookup('jdk/internal/misc/VM','getSavedProperties')
            for operation in (0,1):
                value,ctx=call(native[operation],[throwing,0,0],False)
                exception=P.from_address(c.addressof(ctx)+16).value
                S.check(not value and ctx[0]==16 and not ctx[3] and exception,
                    'A materialized original target Java Throwable was not preserved as a typed exception')
                S.check(P.from_address(exception-8).value==addr(image,'boom_layout'+str(meta['source_classes']['java/lang/reflect/InvocationTargetException'])),
                    'Target-body Java exception was not wrapped by the original InvocationTargetException constructor')
                cause=java('java/lang/reflect/InvocationTargetException','getTargetException','()Ljava/lang/Throwable;',[exception])
                S.check(cause and cause==java('java/lang/reflect/InvocationTargetException','getCause','()Ljava/lang/Throwable;',[exception]),
                    'Original InvocationTargetException cause identity differs')
                message=text(java('java/lang/Throwable','getMessage','()Ljava/lang/String;',[cause]))
                S.check(message=='Not yet initialized','Original cold VM target-body exception message differs')
                type_context=Context();cause_row=proc(rt,'boom_runtime_row',P,P,P,P)(cause,addr(image,'boom_runtime_type_map'),type_context)
                S.check(cause_row and not type_context[0],'Original target cause is not a normal source Throwable')
                cause_runtime_type=config['method_types'][str(U.from_address(cause_row+16).value)]['name']
                S.check(cause_runtime_type=='java/lang/IllegalStateException','Original cold VM body threw a different Throwable type')
                wrapped.append(dict(native_operation=operation,context=list(ctx),wrapper=exception,cause=cause,message=message,cause_runtime_type=cause_runtime_type,
                    target='original_VM_getSavedProperties',System_initPhase1_executed=False,source_fields_written=False))
            pending=Context(77,88,99,0,222,333,444,555);before=list(pending)
            value,ctx=call(native[0],[method,0,0],False,pending)
            S.check(not value and list(ctx)==before,'Pending native Context was changed')
            barrier=Barrier(8)
            def work(index):
                identity=get_native_id();barrier.wait()
                for _ in range(64):
                    value,ctx=call(native[index&1],[method,0,0],False)
                    S.check(not ctx[0] and value==results[0]['natives'][0]['value'] and not ctx[3],
                        'Concurrent original Java target/source native frame failed')
                return dict(OS_thread=identity,native_calls=64)
            with ThreadPoolExecutor(max_workers=8) as executor:threads=list(executor.map(work,range(8)))
            S.check(len({r['OS_thread'] for r in threads})==8,'Eight actual OS threads did not enter')
            def collect(extra=()):
                # No guest Java frames or external workers are active. The
                # directory is this component's source/native/primordial set;
                # explicit host-held test oops are separate, never Java writes.
                roots=[];spans=[]
                for span in config['root_spans']:
                    count=span.get('count')
                    if count is None:count=Q.from_address(addr(image,span['count_symbol'])).value
                    S.check(count<=1048576,'Original physical root span exceeds the bound')
                    values=list((Q*count).from_address(addr(image,span['symbol'])))
                    nonempty=[value for value in values if value];roots.extend(nonempty)
                    spans.append(dict(symbol=span['symbol'],physical_cells=count,non_null=len(nonempty),
                        sha256=hashlib.sha256(bytes((Q*count)(*values))).hexdigest()))
                source_non_null=len(roots);roots.extend(extra);unique=sorted(set(roots));members=set(unique)
                S.check(all(value in members for value in roots),'Quiescent snapshot omitted a non-null source/test oop')
                packed=(Q*max(1,len(unique)))(*unique)
                freed=proc(rt,'boom_heap_collect',Q,P,P,U)(heap,packed,len(unique))
                S.check(freed!=0xffffffffffffffff,'Quiescent original-root collection failed')
                collections.append(dict(spans=spans,source_non_null=source_non_null,additional_test_roots=list(extra),
                    before_dedup=len(roots),after_dedup=len(unique),snapshot_sha256=hashlib.sha256(bytes(packed)[:len(unique)*8]).hexdigest(),
                    freed_objects=freed,automatic_or_concurrent_GC=False,active_Java_frames=False,all_external_workers_joined=True))
            collect((method,preserved_array))
            S.check(proc(rt,'boom_heap_contains',U,P,P)(heap,method) and proc(rt,'boom_heap_contains',U,P,P)(heap,preserved_array),
                'A correctly rooted normal Method or target return graph was lost')
            collect((method,))
            S.check(not proc(rt,'boom_heap_contains',U,P,P)(heap,preserved_array),'Unrooted original values() array was retained')
            value,ctx=call(native[1],[method,0,0],False)
            S.check(not ctx[0] and value==results[0]['natives'][0]['value'],'Original source invocation did not survive quiescent GC')
            collect();S.check(not proc(rt,'boom_heap_contains',U,P,P)(heap,method),'Unrooted Method copy was retained')
            collect()
        # Preserve the real default Java chain even while Class.getConstantPool
        # or another prerequisite remains a source stop. No caches are filled.
        # This constructor-only component has no Phase1. Prepare its JLA by
        # the original source setter, exactly as the public IO fixture does.
        # There is no host property/cache/static-field write or MH override.
        java('java/lang/System','setJavaLangAccess','()V',[])
        option=mirror(config['case_types']['java/lang/StackWalker$Option'])
        ident=methods['java/lang/Class','getEnumConstantsShared','()[Ljava/lang/Object;']
        value,ctx=call(ident,[option],False)
        api_context=ctx
        api=dict(entry='original_Class_getEnumConstantsShared',value=value,context=list(ctx),passed=not ctx[0],source_fault=context_fault(ctx),property_override_or_Java_cache_write=False,original_System_setJavaLangAccess_executed=True)
    except BaseException as error:
        failure=repr(error)
    finally:
        abort=None
        if api_context is not None and api_context[0]==0xb001 and api_context[3]==0 and not P.from_address(c.addressof(api_context)+16).value:
            before=bytes(api_context);released=Q();owned_before=Q.from_address(heap+112).value
            status=proc(rt,'boom_monitor_abort_owned',U,P,P,P,U)(heap,api_context,c.byref(released),0)
            abort=dict(status=status,released_acquisitions=released.value,owned_before=owned_before,
                owned_after=Q.from_address(heap+112).value,Context_unchanged=bytes(api_context)==before,
                reason='fully_unwound_original_source_diagnostic_controlled_VM_abort_not_Java_monitorexit')
            if status or not abort['Context_unchanged'] or abort['owned_after']:
                failure=failure or 'Controlled diagnostic monitor cleanup failed: '+repr(abort)
        if registry:
            detached=proc(rt,'boom_threads_detach',U,P)(registry)
            unbound=proc(image,'boom_provider_thread_bind',U,P)(None)
            destroyed=proc(rt,'boom_threads_destroy',U,P)(registry)
            cleanup=dict(detached=detached,unbound=unbound,registry_destroyed=destroyed)
        trace=proc(image,'boom_release_trace_pool',U)();destroyed=proc(rt,'boom_heap_destroy',U,P)(heap)
        cleanup=dict(cleanup or {},trace_released=trace==0,heap_destroyed=destroyed==1)
        if cleanup!=dict(detached=0,unbound=0,registry_destroyed=0,trace_released=True,heap_destroyed=True):
            failure=failure or 'Constructor-only Thread/FLS/source-frame/heap cleanup failed: '+repr(cleanup)
        cleanup['controlled_source_diagnostic_monitor_cleanup']=abort
    result=dict(schema=1,verified=failure is None and bool(results) and all(not r['context'][0] for case in results for r in case['natives']) and
        len(results)==len(CASES) and len(wrapped)==2 and len(threads)==8 and len(collections)==4,scope='initial_two_original_invoke0_direct_native_component_not_default_API_acceptance',
        images=S.artifact(images),direct_source_Method_cases=results,default_original_Java_API=api,failure=failure,stages=stages,
        wrong_arity=arity,negative=negative,concurrent_OS_calls=threads,target_Throwable_ITE_wrapping_verified=len(wrapped)==2,target_exceptions=wrapped,quiescent_collections=collections,
        Enum_values_names=enum_names,JDK_oracle_verified=False,
        cleanup=cleanup,host_Method_or_Java_cache_or_class_state_written=False,shared_registered=False,game_started=False)
    path=images.parent/'execution.json';S.write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path);parser.add_argument('--methods-images',type=Path)
    parser.add_argument('--output',type=Path,default=S.ART/'method-invoke/executions'/uuid4().hex)
    parser.add_argument('--images',type=Path);parser.add_argument('--worker',type=Path)
    parser.add_argument('--allow-equivalent-batch',action='store_true')
    args=parser.parse_args()
    if args.worker:
        receipt=run(args.worker.resolve());print(receipt)
        S.check(S.read(receipt)['verified'],'Bounded native Method invocation component failed; receipt preserved')
    else:
        images=args.images.resolve() if args.images else build(args.candidate.resolve(),args.methods_images.resolve(),args.output.resolve(),
            allow_equivalent_batch=args.allow_equivalent_batch)
        subprocess.run([os.sys.executable,Path(__file__),'--worker',images],check=True)
