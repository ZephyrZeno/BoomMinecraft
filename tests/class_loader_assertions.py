"""Exercise a source-selected ClassLoader candidate without changing Java class state."""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('class_loader_assertions_candidate',ROOT/'scripts/class-loader-assertions-candidate.py')
B=importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
S=B.S
Q=C.c_uint64
U=C.c_uint32
P=C.c_void_p
Context=U*8


class ClassLoaderAssertionConfigurationTests(unittest.TestCase):
    def test_global_defaults_are_taken_from_the_actual_registered_source_profile(self):
        for system in (False,True):
            for application in (False,True):
                config=dict(class_assertion_overrides_supported=False,system_assertions_enabled=system,application_assertions_enabled=application)
                actual=B.assertion_configuration(config)
                self.assertEqual(actual,dict(system_default=system,application_default=application,class_overrides=[],package_overrides=[]))
                with self.assertRaises(ValueError):B.assertion_configuration(config,{'application_default':not application})

    def test_named_overrides_wrong_scalar_types_and_unknown_options_are_rejected(self):
        config=dict(class_assertion_overrides_supported=False,system_assertions_enabled=False,application_assertions_enabled=False)
        for request in ({'class_overrides':['example.Test']},{'package_overrides':['example...']},
                        {'system_default':0},{'application_default':1},{'unknown':True},[]):
            with self.subTest(request=request),self.assertRaises(ValueError):B.assertion_configuration(config,request)
        with self.assertRaises(ValueError):B.assertion_configuration(dict(config,class_assertion_overrides_supported=True))


def run(command,log):
    with log.open('wb') as stream:subprocess.run([str(p) for p in command],stdout=stream,stderr=subprocess.STDOUT,check=True)


def source_supplement(meta,closure,out,assembler):
    ident=meta['directives']
    state=meta['class_states'][str(ident)]
    S.check(ident not in {r['class_id'] for r in closure['selected_classes']} and not state['fields'] and
        state['initializer'] is None and state['dependencies']==[4591], 'Only the missing original empty directives class can be supplemented')
    summary=S.read(S.checked(meta['base']['batch_summary']))
    module=summary['class_state']
    path=S.checked(module['units'][state['assembly_unit']]['assembly'])
    root_path=S.checked(module['units'][0]['assembly'])
    sources=B.script('batch-source').Sources()
    descriptor=sources.class_descriptor(path,ident)
    function=sources.function(path,f'boom_batch_initialize_{ident}')
    failure=f'boom_batch_class_failure_root{ident}'
    pattern=f'PUBLIC {failure}\n{failure} QWORD ?\n'
    roots=root_path.read_text(encoding='utf-8')
    S.check(roots.count(pattern)==1 and f'DWORD 0434C4153h,2,0,0\n' in descriptor and
        f'OFFSET {failure}' in descriptor and function.count('call boom_class_ensure32\n')==1,
        'Original cold descriptor, dependency initializer or failure-root declaration differs')
    body=('option casemap:none\nEXTERN boom_class4591:BYTE\nEXTERN boom_class_ensure32:PROC\n'
        '.data?\nALIGN 8\nPUBLIC boom_class_loader_assertions_source_roots\nboom_class_loader_assertions_source_roots LABEL QWORD\n'+pattern+
        '.const\nPUBLIC boom_class_loader_assertions_source_root_count\nboom_class_loader_assertions_source_root_count QWORD 1\n'
        f'.data\nALIGN 8\nPUBLIC boom_class{ident}\n'+descriptor+f'.code\nPUBLIC boom_batch_initialize_{ident}\n'+function+'END\n')
    asm=out/'source-directives-class.asm';asm.write_text(body,encoding='utf-8',newline='\n')
    obj=asm.with_suffix('.obj')
    run([assembler,'/nologo','/c',f'/Fo{obj}',asm],out/'source-directives-class.log')
    exports={f'boom_class{ident}',f'boom_batch_initialize_{ident}',failure,
        'boom_class_loader_assertions_source_roots','boom_class_loader_assertions_source_root_count'}
    S.check(B.A.coff_symbols(obj)==(exports,{'boom_class4591','boom_class_ensure32'}),'Supplement COFF exceeds the original dependency initializer and descriptor')
    proof=dict(scope='one_missing_original_source_Class_descriptor_and_Object_dependency_initializer',class_state=state,
        source_index=S.artifact(S.checked(module['index'])),source_descriptor_and_initializer_ASM=S.artifact(path),
        source_failure_root_ASM=S.artifact(root_path),descriptor_sha256=hashlib.sha256(descriptor.encode()).hexdigest(),
        original_initializer_sha256=hashlib.sha256(function.encode()).hexdigest(),failure_declaration_sha256=hashlib.sha256(pattern.encode()).hexdigest(),
        assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),cold_state=0,
        new_failure_root_cells=1,Java_initializer_replaced=False,Java_class_initialization_state_manually_written=False)
    S.write(out/'source-directives-class-proof.json',proof)
    return obj,proof


def remove_stops(raw,rows):
    edits=[]
    ending=b'\r\n' if b'\r\n' in raw else b'\n'
    for row in rows:
        symbol=row['symbol']
        fragment=(f'PUBLIC {symbol}\n{symbol} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
            f' lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{symbol} ENDP\n').encode().replace(b'\n',ending)
        S.check(raw.count(fragment)==1,'Expected one context-aware source diagnostic stop: '+symbol)
        at=raw.index(fragment)
        edits.append((at,at+len(fragment),row))
    chunks=[];unchanged=[];removed=[];before=after=0
    for begin,end,row in sorted(edits):
        chunk=raw[before:begin]
        chunks.append(chunk)
        unchanged.append(dict(original_begin=before,output_begin=after,bytes=len(chunk),sha256=hashlib.sha256(chunk).hexdigest()))
        after+=len(chunk)
        removed.append(dict(symbol=row['symbol'],row=row['id'],original_begin=begin,bytes=end-begin,
            sha256=hashlib.sha256(raw[begin:end]).hexdigest()))
        before=end
    chunk=raw[before:];chunks.append(chunk)
    unchanged.append(dict(original_begin=before,output_begin=after,bytes=len(chunk),sha256=hashlib.sha256(chunk).hexdigest()))
    updated=b''.join(chunks)
    S.check(len(updated)+sum(r['bytes'] for r in removed)==len(raw),'Diagnostic removal ranges overlap')
    return updated,dict(removed=removed,unchanged_ranges=unchanged,original_sha256=hashlib.sha256(raw).hexdigest(),
        output_sha256=hashlib.sha256(updated).hexdigest(),other_source_bytes_changed=0)


def link(candidate_file,selection,out,baseline_images_file=None):
    candidate_file,selection=Path(candidate_file).resolve(),Path(selection).resolve()
    m=S.read(candidate_file)
    S.check(B.verify(candidate_file)==S.read(candidate_file.with_name('verification.json')),'Current candidate receipt differs')
    meta=m['metadata']
    closure=S.read(selection/'closure.json')
    proof=S.read(selection/'selection-verification.json')
    diagnostic=S.read(selection/'diagnostic.json')
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(selection/'closure.json')['sha256'] and
        proof['diagnostic_manifest_sha256']==S.digest(selection/'diagnostic.json')['sha256'] and
        Path(closure['plan']).resolve()==Path(meta['base']['plan']), 'Accepted original source selection required')
    baseline=None
    state=S.read(S.checked(meta['input_state']))
    if baseline_images_file:
        baseline_images_file=Path(baseline_images_file).resolve()
        execution=S.read(S.checked(state['boot_unnamed_execution']))
        S.check(S.checked(execution['images'])==baseline_images_file and execution['formal_pack_and_normal_JCLS_executed'] and
            not execution['game_started'],'Expected the accepted actual formal Boot execution baseline')
        baseline=S.read(baseline_images_file)
        S.check(S.checked(baseline['selection_proof'])==selection/'selection-verification.json' and
            baseline['formal_provider']['batch']==meta['base']['batch_summary'] and
            baseline['formal_provider']['batch_verification']==meta['base']['base_verification'] and
            baseline['formal_provider']['native_frame_overlay']==meta['frame'] and
            S.checked(baseline['runtime'])==Path(state['runtime'])/'boom-runtime.dll',
            'Baseline must contain the current verified JCLS, native frame and runtime')
        old=S.read(Path(closure['batch'])/'summary.json')
        current=S.read(S.checked(meta['base']['batch_summary']))
        S.check(old['input_fingerprint']==current['input_fingerprint'] and old['ir_identity']==current['ir_identity'] and
            old['layouts']==current['layouts'] and all(old[k]==current[k] for k in ('class_state','runtime_metadata','class_bootstrap')),
            'Only the exact retained ClassLoader layouts, source state, types and assertion configuration may be reused')
    else:
        S.check(closure['source_batch_summary_sha256']==meta['base']['batch_summary']['digest']['sha256'] and
            Path(closure['batch']).resolve()==Path(meta['base']['batch']), 'Accepted current source selection required')
    selected={r['class_id']:r for r in closure['selected_classes']}
    S.check(selected.get(meta['owner'])==meta['class_states'][str(meta['owner'])] and
        (meta['directives'] not in selected or selected[meta['directives']]==meta['class_states'][str(meta['directives'])]),
        'Original source ClassLoader/directives class state changed')
    missing_callers=[]
    for java in meta['original_java']:
        row=closure['selected_methods'].get(str(java['method']))
        if baseline and row is None and java['name']!='<clinit>':missing_callers.append(java['method']);continue
        S.check(row and row['source_sha256']==java['class_sha256'] and row['code_sha256']==java['code_sha256'],
                'Original ClassLoader Java body missing from selection: '+java['name'])
    for unit in proof['verified_assembly_objects']['units']:
        S.checked(unit['assembly']);S.checked(unit['object'])
    image=S.checked(baseline['image']) if baseline else selection/'diagnostic-image.dll'
    recipe_path=baseline_images_file.parent/'link.rsp' if baseline else selection/'link.rsp'
    recipe=recipe_path.read_text(encoding='utf-8').splitlines()
    out_lines=[n for n in recipe if n.upper().startswith('/OUT:')]
    S.check(len(out_lines)==1 and Path(out_lines[0][5:].strip('"')).resolve()==image and '/BREPRO' in recipe,
            'Expected reproducible original diagnostic image recipe')
    asm=Path(m['assembler']['path']);linker=asm.with_name('link.exe')
    with tempfile.TemporaryDirectory(dir=out,prefix='control-') as temp:
        control=Path(temp)/image.name
        rsp=Path(temp)/'control.rsp'
        rsp.write_text('\n'.join(f'/OUT:"{control}"' if line==out_lines[0] else line for line in recipe)+'\n',encoding='utf-8')
        run([linker,'@'+str(rsp)],out/'original-link.log')
        S.check(S.digest(control)==S.digest(image),'Accepted source image is not reproduced by its original link inputs')
    stops=baseline_images_file.parent/'remaining-stops.obj' if baseline else selection/'diagnostic-stops.obj'
    stop_lines=[line for line in recipe if not line.startswith('/') and Path(line.strip('"')).resolve()==stops]
    S.check(len(stop_lines)==1,'Original diagnostic stop COFF must appear once')
    supplement,extra=(None,None) if meta['directives'] in selected else source_supplement(meta,closure,out,asm)
    rows=[]
    for native in meta['methods']:
        symbol=f"boom_m{native['method']}"
        matches=[r for r in diagnostic['rows'] if r['symbol']==symbol]
        if baseline and not matches and native['name']=='retrieveDirectives':continue
        [row]=matches
        S.check(row['category']==2 and row['method']['id']==native['method'],'Expected original unavailable native boundary')
        rows.append(row)
    if extra:
        [row]=[r for r in diagnostic['rows'] if r['symbol']==f"boom_batch_initialize_{meta['directives']}"]
        S.check(row['category']==5 and row['initialization']==meta['class_states'][str(meta['directives'])],
            'Only the verified original directives initializer placeholder may be removed')
        rows.append(row)
    raw=stops.with_suffix('.asm').read_bytes()
    changed_raw,range_proof=remove_stops(raw,rows)
    changed=out/'remaining-stops.asm'
    changed.write_bytes(changed_raw)
    obj=changed.with_suffix('.obj')
    run([asm,'/nologo','/c',f'/Fo{obj}',changed],out/'remaining-stops.log')
    dll=out/image.name
    lines=[f'/OUT:"{dll}"' if line==out_lines[0] else f'"{obj}"' if line==stop_lines[0] else line for line in recipe]
    lines.append(f'"{S.checked(m["object"])}"')
    if supplement:lines.append(f'"{supplement}"')
    exports=set(m['exports'])|{'boom_java_class_bootstrap_pool','boom_heap_ptr','boom_runtime_type_map',
        f"boom_class{meta['owner']}",f"boom_class{meta['directives']}",f"boom_layout{meta['directives']}",
        f"boom_s{meta['owner']}_6",f"boom_s{meta['owner']}_17",'boom_java_string_literal_root_count'}|{f'boom_t{v}' for v in meta['array_types'].values()}
    if extra:exports.update(extra['exports'])
    for name in sorted(exports):
        if '/EXPORT:'+name not in lines:lines.append('/EXPORT:'+name)
    rsp=out/'link.rsp'
    rsp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    run([linker,'@'+str(rsp)],out/'candidate-link.log')
    images=dict(image=S.artifact(dll),original_image=S.artifact(image),candidate=S.artifact(candidate_file),
        candidate_receipt=S.artifact(candidate_file.with_name('verification.json')),source_selection=S.artifact(selection/'selection-verification.json'),
        original_source_link_reproduced=True,removed_diagnostic_rows=rows,diagnostic_source_byte_ranges=range_proof,remaining_stops=S.artifact(obj),
        original_Java_or_class_state_COFF_changed=False,runtime=S.artifact(Path(state['runtime'])/'boom-runtime.dll'),
        unselected_original_Java_callers=missing_callers,ClassLoader_assertion_map_Java_API_executed=False,
        joint_formal_22_provider_execution_claimed=False)
    if baseline:images['accepted_formal_Boot_baseline']=S.artifact(baseline_images_file)
    if extra:images['additional_original_source_class']=extra
    S.write(out/'images.json',images)
    return images


def addr(image,name):return C.addressof(C.c_char.in_dll(image,name))


def func(image,name,result,*args):
    f=getattr(image,name);f.restype=result;f.argtypes=args
    return f


def execute(candidate_file,selection,out,mode):
    m=S.read(candidate_file);meta=m['metadata'];images=S.read(out/'images.json')
    runtime=S.checked(images['runtime'])
    image=S.checked(images['original_image'] if mode=='control' else images['image'])
    with os.add_dll_directory(str(runtime.parent)):
        rt=C.CDLL(str(runtime));im=C.CDLL(str(image))
    heap=func(rt,'boom_heap_create',P,Q)(64<<20)
    S.check(heap and func(im,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Normal guest heap bind failed')
    owner=addr(im,f"boom_class{meta['owner']}")
    directives=None if mode=='control' and images.get('additional_original_source_class') else addr(im,f"boom_class{meta['directives']}")
    jcb=addr(im,'boom_java_class_bootstrap_pool')
    S.check(not U.from_address(owner+8).value and (directives is None or not U.from_address(directives+8).value) and
        not U.from_address(jcb+8).value,'Expected cold original source class state and unregistered assertion configuration')
    system,application=(int(mode[-2]),int(mode[-1])) if mode.startswith('cold') else (0,0)
    # Development VM startup knobs, before source Class.registerNatives runs.
    # These two configuration fields are not Java class initialization state.
    U.from_address(jcb+56).value=system
    U.from_address(jcb+60).value=application
    ensure=func(rt,'boom_class_ensure32',U,P,P)
    state=lambda:dict(ClassLoader=U.from_address(owner+8).value,AssertionStatusDirectives=U.from_address(directives+8).value if directives else None,
        Class_native_registration=U.from_address(jcb+8).value)
    def fault(ctx):
        if ctx[0]!=0xb001:return None
        ident=func(im,'boom_diagnostic_context_map_row',U,P,P)(ctx,addr(im,'boom_diagnostic_context_map'))
        return next((r['symbol'] for r in S.read(selection/'diagnostic.json')['rows'] if r['id']==ident),None)
    if mode=='control':
        ctx=Context();result=ensure(owner,ctx)
        observed=dict(context=list(ctx[:4]),source_gap=fault(ctx),ensure_return=result,class_state=state())
        S.check(result and observed['source_gap']=='boom_m41548','Original cold control failed before the declared register native')
        return observed
    pool=addr(im,'boom_class_loader_assertions_pool')
    S.check(not U.from_address(pool+8).value and Q.from_address(pool+16).value==C.cast(getattr(im,'boom_m41631_native'),P).value,
        'Expected cold real native registration table with the actual retrieve entry')
    if images.get('additional_original_source_class'):
        S.check(Q.from_address(directives+56).value==addr(im,f"boom_batch_class_failure_root{meta['directives']}") and
            Q.from_address(addr(im,'boom_class_loader_assertions_source_root_count')).value==1 and
            addr(im,'boom_class_loader_assertions_source_roots')==Q.from_address(directives+56).value,
            'Original source failure cell is not the recorded one-cell GC root span')
    call=func(im,'boom_m41631',Q,P,P)
    native=func(im,'boom_m41631_native',Q,P,P)
    register=func(im,'boom_m41548',Q,P,P)
    service=func(im,'boom_class_loader_assertions',Q,P,P,P,U)
    slots=(Q*1)()
    if mode=='exceptions':
        ctx=Context();S.check(native(ctx,slots)==0 and ctx[0]==20 and not ctx[3] and state()['ClassLoader']==0,
            'Unregistered entry fabricated a directives object or altered Java initialization')
        invalid=Context();service(invalid,slots,pool+8,0)
        S.check(invalid[0]==7 and not U.from_address(pool+8).value,'Invalid pool was accepted')
    contains=func(rt,'boom_heap_contains',U,P,P)
    runtime_type=func(rt,'boom_runtime_type',P,P,P,P)
    length=func(rt,'boom_typed_array_length',Q,P,P,P)
    type_map=addr(im,'boom_runtime_type_map')
    fields={f['name']:f for f in meta['fields']}
    def snapshot(oop,ctx):
        S.check(oop and not ctx[0] and not ctx[3] and contains(heap,oop) and
            Q.from_address(oop-8).value==addr(im,f"boom_layout{meta['directives']}") and
            Q.from_address(oop-16).value==meta['layout']['payload_bytes'] and U.from_address(oop-20).value==4,
            'Return is not a normal source-layout AssertionStatusDirectives instance')
        values={name:Q.from_address(oop+fields[name]['offset']).value for name in ('classes','classEnabled','packages','packageEnabled')}
        for name,array in values.items():
            typ='[Z' if name.endswith('Enabled') else '[Ljava/lang/String;'
            check=Context()
            S.check(array and contains(heap,array) and Q.from_address(array-16).value==0 and
                runtime_type(array,type_map,check)==addr(im,f"boom_t{meta['array_types'][typ]}") and not check[0] and
                length(array,type_map,check)==0 and not check[0], 'Empty array has the wrong normal source type or length')
        default=C.c_ubyte.from_address(oop+fields['deflt']['offset']).value
        S.check(default==application and len({oop,*values.values()})==5,'Wrong registered application default or aliased VM snapshot arrays')
        return dict(oop=oop,arrays=values,deflt=default,guest_depth=ctx[3])
    snapshots=[]
    if mode=='concurrent':
        barrier=threading.Barrier(8);errors=[]
        def worker():
            try:
                ctx=Context();barrier.wait(timeout=30);oop=call(ctx,slots)
                snapshots.append((threading.get_native_id(),snapshot(oop,ctx)))
            except BaseException as error:errors.append(str(error))
        threads=[threading.Thread(target=worker) for _ in range(8)]
        for t in threads:t.start()
        for t in threads:t.join(timeout=45)
        S.check(not errors and not any(t.is_alive() for t in threads) and len({r[0] for r in snapshots})==8,
            'Concurrent cold source initialization or native retrieval failed: '+repr(errors))
        ptrs=[p for _,r in snapshots for p in [r['oop'],*r['arrays'].values()]]
        S.check(len(set(ptrs))==40,'Concurrent snapshots share object or array identity')
    else:
        ctx=Context();result=ensure(owner,ctx)
        S.check(result==0 and not ctx[0] and not ctx[3], 'Original cold ClassLoader initializer failed at '+str(fault(ctx)))
        for _ in range(2):
            ctx=Context();snapshots.append(snapshot(call(ctx,slots),ctx))
        ptrs=[p for r in snapshots for p in [r['oop'],*r['arrays'].values()]]
        S.check(len(set(ptrs))==10,'Independent retrieves reuse a directives object or array')
    S.check(state()==dict(ClassLoader=2,AssertionStatusDirectives=2,Class_native_registration=2) and
        U.from_address(pool+8).value==2 and C.c_ubyte.from_address(addr(im,f"boom_s{meta['owner']}_17")).value==1-system,
        'Original source initialization, registered defaults or native registration did not publish')
    nocerts=Q.from_address(addr(im,f"boom_s{meta['owner']}_6")).value
    S.check(nocerts and contains(heap,nocerts) and not Q.from_address(nocerts-16).value,'Original nocerts initialization did not run')
    result=dict(mode=mode,development_VM_startup_defaults=dict(system=system,application=application),
        actual_registered_JCBT_defaults=[U.from_address(jcb+56).value,U.from_address(jcb+60).value],
        original_cold_ClassLoader_initializer_completed=True,class_state=state(),native_registration_state=2,
        source_nocerts_published=True,source_assertionsDisabled=1-system,Java_class_initialization_state_manually_written=False,
        guest_depths_zero=True,snapshots=len(snapshots),snapshot_objects=len(ptrs),distinct_snapshot_objects=len(set(ptrs)),game_started=False)
    if mode=='concurrent':result['OS_threads']=8
    if mode=='exceptions':
        existing=Context(9,4,7,0);S.check(call(existing,slots)==0 and list(existing[:4])==[9,4,7,0],'Existing exception was replaced')
        for _ in range(32):
            again=Context();S.check(register(again,slots)==0 and not again[0] and not again[3] and U.from_address(pool+8).value==2,
                'Repeated registration failed')
        saved=U.from_address(jcb+60).value;U.from_address(jcb+60).value=2
        bad=Context();S.check(call(bad,slots)==0 and bad[0]==7 and not bad[3],'Invalid VM assertion boolean was accepted')
        U.from_address(jcb+60).value=saved
        result['native_boundary_checks']=['unregistered target -> kind20','invalid pool -> kind7','existing exception preserved',
            '32 repeated registrations','invalid assertion configuration -> kind7']
    if mode=='oom':
        alloc=func(rt,'boom_heap_alloc',P,P,Q,U,P)
        fillers=0
        for amount in (1<<20,4096,0):
            while alloc(heap,amount,0,260):fillers+=1
        oom=Context();S.check(call(oom,slots)==0 and oom[0]==3 and not oom[3] and U.from_address(pool+8).value==2 and
            state()==dict(ClassLoader=2,AssertionStatusDirectives=2,Class_native_registration=2),'OOM did not preserve native/class state and its source exception ABI')
        result['OOM_Context32_kind']=3;result['partial_directives_result_escaped']=False;result['filler_objects']=fillers
    if mode=='gc':
        alloc=func(rt,'boom_heap_alloc',P,P,Q,U,P)
        garbage=alloc(heap,0,0,260)
        S.check(garbage,'Unrooted empty-array allocation failed')
        root_cells=(Q*len(snapshots))(*(r['oop'] for r in snapshots))
        regions=[(C.addressof(root_cells),len(snapshots),'native_result_objects')]
        pairs=[('boom_java_class_roots','boom_java_class_root_count'),('boom_probe_static_roots','boom_probe_static_root_count'),
            ('boom_java_class_name_roots','boom_java_class_name_root_count'),('boom_java_string_intern_root','boom_java_string_intern_root_count'),
            ('boom_java_properties_roots','boom_java_properties_root_count'),('boom_provider_access_domain_roots','boom_provider_access_domain_root_count')]
        exports=set(S.read(selection/'closure.json')['exports'])
        for cells,count in pairs:
            if cells in exports and count in exports:regions.append((addr(im,cells),Q.from_address(addr(im,count)).value,cells))
        strings=addr(im,'boom_java_string_literal_pool')
        regions.append((Q.from_address(strings+24).value,Q.from_address(addr(im,'boom_java_string_literal_root_count')).value,'boom_java_string_literal_roots'))
        if images.get('additional_original_source_class'):
            regions.append((addr(im,'boom_class_loader_assertions_source_roots'),1,'original_AssertionStatusDirectives_failure_root'))
        spans=(Q*(len(regions)*2))(*(n for cells,count,_ in regions for n in (cells,count)))
        freed=func(rt,'boom_heap_collect_spans',C.c_int64,P,P,Q)(heap,spans,len(regions))
        S.check(freed>=1 and not contains(heap,garbage) and all(contains(heap,p) for p in ptrs),
            'Explicit GC did not trace normal directives fields or register every source root region')
        result.update(explicit_quiescent_GC_freed_objects=freed,all_snapshot_objects_retained=True,
            GC_root_regions=[dict(name=name,cells=count) for _,count,name in regions],
            source_failure_root_span_registered=bool(images.get('additional_original_source_class')))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','selection','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--baseline-images',type=Path)
    modes=['control','cold00','cold01','cold10','cold11','concurrent','exceptions','oom','gc']
    p.add_argument('--worker',choices=modes)
    a=p.parse_args();out=a.output.resolve()
    S.check(out.is_relative_to(S.ART),'Project-isolated native test required')
    if a.worker:
        result=execute(a.candidate.resolve(),a.selection.resolve(),out,a.worker)
        S.write(out/(a.worker+'.json'),result)
    else:
        out.mkdir(parents=True,exist_ok=False)
        images=link(a.candidate,a.selection,out,a.baseline_images)
        for mode in modes:subprocess.run([sys.executable,__file__,*sys.argv[1:],'--worker',mode],check=True)
        result=dict(verified_original_ClassLoader_cold_initializer_and_assertion_natives=True,images=S.artifact(out/'images.json'),
            cases={mode:S.read(out/(mode+'.json')) for mode in modes},normal_source_objects_and_typed_arrays=True,
            class_and_package_overrides_supported=False,Java_class_initialization_state_manually_written=False,
            shared_provider_registered=False,full_System_bootstrap=False,game_started=False)
        S.write(out/'result.json',result);print(out/'result.json')


if __name__=='__main__':
    if '--candidate' in sys.argv:main()
    else:unittest.main()
