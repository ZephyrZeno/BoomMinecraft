"""Run original cold BootLoader.<clinit> in a source-selected diagnostic DLL."""
import argparse
import ctypes as C
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import threading


ROOT=Path(__file__).resolve().parents[1]
def script(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B=script('boot-unnamed-normal-candidate')
S=B.S
U=C.c_uint32
Q=C.c_uint64
P=C.c_void_p
Context=U*8


def run(tool,args,log):
    with log.open('wb') as stream:
        subprocess.run([tool,*args],stdout=stream,stderr=subprocess.STDOUT,check=True)


def formal_inputs(provider,candidate):
    provider=Path(provider).resolve()
    V=script('verify-runtime-provider-pack')
    pack=S.read(provider)
    S.check(pack['family']=='normal-boot-unnamed-module-v1','Expected the formal BootLoader provider family')
    batch,plan=Path(pack['base']['batch']),Path(pack['base']['plan'])
    proof=V.verify(provider,batch,plan)
    receipt=provider.with_name('verification.json')
    S.check(proof==S.read(receipt),'Formal native provider verification differs')
    refresh=script('refresh-boot-unnamed-batch')
    summary=S.read(batch/'summary.json')
    resolve,scope=refresh.verified_resolver(batch,summary,plan)
    meta=S.read(S.checked(pack['boot_unnamed_metadata']))
    previous=candidate['contract']
    [native]=pack['methods']
    S.check(all(native[k]==previous['native'][k] for k in ('method','class_id','class_sha256','owner','name','descriptor','access'))
            and (meta['owner'],meta['module_class'],meta['static_field'],meta['slot'],meta['module_fields'])==
                (previous['owner'],previous['module_type'],previous['static_index'],previous['module_slot'],previous['module_fields'])
            and (meta['module_count'],meta['strong_roots'])==(previous['module_slot']+1,previous['root_cells']+1)
            and summary['class_literals']['modules'][:-1]==previous['original_module_keys'],
            'Formal binding, original source identity or retained JCLS IDs differ')
    expected={r['method']:(r['class_sha256'],r['code_sha256']) for r in previous['source_java']}
    S.check({r['method']:(r['class_sha256'],r['code_sha256']) for r in meta['original_java']}==expected,
            'Formal provider requires different original Java methods')
    [unit]=summary['class_literals']['units']
    assembly=resolve(batch,unit['assembly'],'class-literals')
    original=S.checked(candidate['original_jcls_assembly']).read_text(encoding='utf-8')
    parent=S.read(S.checked(candidate['batch']))
    S.check(assembly.read_text(encoding='utf-8')==B.pool_overlay(original,parent['class_literals']),
            'Formal JCLS assembly differs from the verified one-root extension')
    frame=S.read(S.checked(pack['frame_overlay']['manifest']))
    return dict(object=S.checked(pack['object']),jcls=resolve(batch,unit['object'],'class-literals'),
        frame=S.checked(frame['object']),evidence=dict(provider=S.artifact(provider),verification=S.artifact(receipt),
        batch=S.artifact(batch/'summary.json'),batch_verification=S.artifact(batch/'verification.json'),
        native_frame_overlay=pack['frame_overlay'],sparse_JCLS_source=scope))


def link(candidate_file,nio_file,prior_execution,out,formal_provider=None):
    m,nio=S.read(candidate_file),S.read(nio_file)
    S.check(m['family']=='normal-boot-unnamed-module-candidate' and not m['executed'] and
            nio['family']=='windows-nio-owned-file-query-candidate' and nio['per_context_diagnostic_rows'],
            'Expected source-bound native and validated cold source selection')
    base=Path(nio['artifact_directory'])
    selection=Path(nio['selection_directory'])
    old_image=S.checked(nio['image'])
    old=S.read(prior_execution)
    S.check(old['candidate_manifest_sha256']==S.digest(nio_file)['sha256'] and
            old['candidate_image_sha256']==S.digest(old_image)['sha256'] and old['source_Java_tail_succeeded'],
            'Prior NIO execution does not match its image')
    native=m['contract']['native']
    symbol=f"boom_m{native['method']}"
    row=old['fresh_process_boundaries']['dispatcher-properties']['context_row']
    S.check(row['symbol']==symbol and row['category']==2 and row['method']['name']==B.METHOD and
            row['method']['descriptor']==B.PUBLISH,'Expected original BootLoader native stop')
    proof=S.read(S.checked(nio['base_proof']))
    closure=S.read(selection/'closure.json')
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(selection/'closure.json')['sha256'] and
            proof['diagnostic_manifest_sha256']==S.digest(selection/'diagnostic.json')['sha256'],
            'Selected original closure or native stop table changed')
    for raw in m['contract']['source_java']:
        selected=closure['selected_methods'].get(str(raw['method']))
        S.check(selected and selected['code_sha256']==raw['code_sha256'] and selected['source_sha256']==raw['class_sha256'],
                'Original BootLoader module source chain not present in selected assembly: '+raw['name'])
    frame_manifest=S.read(S.checked(nio['native_frame_provider']['manifest']))
    overlay=S.read(S.checked(frame_manifest['frame_overlay']['manifest']))
    frame=next(r for r in overlay['source']['original_native_declarations'] if r['id']==native['method'])
    S.check(all(frame[k]==native[k] for k in ('access','class_sha256','name','descriptor','class_id')) and
            frame['flags']&32 and not frame['flags']&128,'Original native frame source or identity differs')
    tool=S.artifact(Path(m['assembler']['path']))
    S.check(tool==m['assembler'] and S.artifact(B.TEMPLATE)==m['template'] and
            S.artifact(Path(B.__file__))==m['tool'],'MASM or native candidate source changed')
    asm=Path(tool['path']);linker=asm.with_name('link.exe')
    recipe=(base/'link.rsp').read_text(encoding='utf-8').splitlines()
    stops=base/'remaining-stops.obj'
    [stop_record]=[r for r in nio['generated_assembly'] if Path(r['path']).name=='remaining-stops.asm']
    src=S.checked(stop_record).read_text()
    fragment=(f'PUBLIC {symbol}\n{symbol} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
              f' lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{symbol} ENDP\n')
    S.check(src.count(fragment)==1,'Expected exactly the real context-aware native stop')
    original_jcls=S.checked(m['original_jcls_object'])
    for line in (f'/OUT:"{old_image}"',f'"{stops}"',f'"{original_jcls}"'):
        S.check(recipe.count(line)==1,'Missing unique original link input: '+line)
    S.check('/BREPRO' in recipe,'Control link requires reproducible PE')
    with tempfile.TemporaryDirectory(dir=out,prefix='control-') as temp:
        control=Path(temp)/old_image.name
        rsp=Path(temp)/'control.rsp'
        replacement=[f'/OUT:"{control}"' if line==f'/OUT:"{old_image}"' else line for line in recipe]
        rsp.write_text('\n'.join(replacement)+'\n',encoding='utf-8')
        run(linker,['@'+str(rsp)],out/'original-link.log')
        S.check(S.digest(control)==S.digest(old_image),'Original response inputs no longer reproduce the accepted baseline DLL')
    changed=out/'remaining-stops.asm'
    changed.write_text(src.replace(fragment,'',1),encoding='utf-8')
    obj=changed.with_suffix('.obj')
    run(asm,['/nologo','/c',f'/Fo{obj}',changed],out/'remaining-stops.log')
    formal=formal_inputs(formal_provider,m) if formal_provider else None
    jcls=formal['jcls'] if formal else S.checked(m['jcls_object'])
    provider=formal['object'] if formal else S.checked(m['provider_object'])
    dll=out/'boot-unnamed.dll'
    replacements={f'/OUT:"{old_image}"':f'/OUT:"{dll}"',f'"{stops}"':f'"{obj}"',f'"{original_jcls}"':f'"{jcls}"'}
    if formal:
        original_frame=S.checked(overlay['object'])
        S.check(recipe.count(f'"{original_frame}"')==1,'Expected the original native frame COFF in the accepted link')
        replacements[f'"{original_frame}"']=f'"{formal["frame"]}"'
    lines=[replacements.get(line,line) for line in recipe]
    lines.append(f'"{provider}"')
    for name in (symbol,symbol+'_native','boom_boot_unnamed_normal','boom_java_class_roots',
                 'boom_java_class_root_count','boom_java_class_module_roots','boom_java_class_pool'):
        if '/EXPORT:'+name not in lines:
            lines.append('/EXPORT:'+name)
    rsp=out/'link.rsp'
    rsp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    run(linker,['@'+str(rsp)],out/'candidate-link.log')
    return dll,selection,formal['evidence'] if formal else None


def addr(image,name):
    return C.addressof(C.c_char.in_dll(image,name))


def func(image,name,result,*args):
    f=getattr(image,name)
    f.restype=result
    f.argtypes=args
    return f


def execution(image,runtime,selection,m,control=False,concurrent=False):
    info=m['contract']
    with os.add_dll_directory(str(runtime)):
        rt=C.CDLL(str(runtime/'boom-runtime.dll'));im=C.CDLL(str(image))
    heap=func(rt,'boom_heap_create',P,Q)(128<<20)
    S.check(heap and func(im,'boom_java_string_literals_bind_heap',U,P)(heap)==1,'Normal guest heap bind failed')
    class_id=info['owner']
    owner=addr(im,f'boom_class{class_id}')
    cell=addr(im,f"boom_s{class_id}_{info['static_index']}")
    jcls=addr(im,'boom_java_class_pool')
    roots=addr(im,'boom_java_class_roots')
    nroots=Q.from_address(addr(im,'boom_java_class_root_count')).value
    count=U.from_address(jcls+88).value
    mod_roots=Q.from_address(jcls+64).value
    slot=info['module_slot']
    S.check(mod_roots==addr(im,'boom_java_class_module_roots') and
            mod_roots+count*8==roots+nroots*8 and not Q.from_address(cell).value and not U.from_address(owner+8).value,
            'Expected a cold original class and contiguous JCLS GC range')
    S.check((count,nroots)==(slot,info['root_cells']) if control else
            (count,nroots)==(slot+1,info['root_cells']+1),'Unexpected module/strong-root count')
    closure=S.read(selection/'closure.json')
    source_ids={r['name']:r['class_id'] for r in closure['selected_classes']}
    natives=S.read(selection/'diagnostic.json')['rows']
    native_method=info['native']['method']
    ensure=func(rt,'boom_class_ensure32',U,P,P)
    def context_row(ctx):
        if ctx[0]!=0xb001:return None
        number=func(im,'boom_diagnostic_context_map_row',U,P,P)(ctx,addr(im,'boom_diagnostic_context_map'))
        return next((r['symbol'] for r in natives if r['id']==number),None)
    prep=Context()
    ensure(addr(im,f"boom_class{source_ids['jdk/internal/misc/Unsafe']}"),prep)
    S.check(not prep[0],'Original Unsafe static initialization failed')
    phase=next(i for i,r in closure['selected_methods'].items() if r['class_id']==source_ids['java/lang/System']
               and r['name']=='initPhase1' and r['descriptor']=='()V')
    func(im,'boom_m'+phase,Q,P,P)(prep,(Q*1)())
    ctx=Context()
    workers=[]
    if concurrent:
        barrier=threading.Barrier(8)
        def initialize():
            thread_ctx=Context()
            barrier.wait(timeout=20)
            result=ensure(owner,thread_ctx)
            workers.append((threading.get_native_id(),result,list(thread_ctx[:4]),
                            Q.from_address(cell).value,Q.from_address(mod_roots+slot*8).value))
        threads=[threading.Thread(target=initialize) for _ in range(barrier.parties)]
        for t in threads:t.start()
        for t in threads:t.join(timeout=30)
        S.check(not any(t.is_alive() for t in threads) and len({r[0] for r in workers})==barrier.parties and
                all(ret==0 and context[0]==context[3]==0 and java and java==vm
                    for _,ret,context,java,vm in workers),'Concurrent original class initialization or root publication failed')
        # A final acquire on the invoking thread must see all writes from the initializing owner.
    ensures=ensure(owner,ctx)
    oop=Q.from_address(cell).value
    S.check(oop and func(rt,'boom_heap_contains',U,P,P)(heap,oop),'Original Java initializer failed to construct its Module')
    fields={f['name']:((Q if f['width']==8 else C.c_ubyte).from_address(oop+f['offset']).value) for f in info['module_fields']}
    S.check(fields==dict(layer=0,name=0,loader=0,descriptor=0,enableNativeAccess=1),
            'Original Module constructor or original Java native-access CAS did not run')
    result=dict(System_initPhase1_context=list(prep[:4]),System_initPhase1_gap=context_row(prep),
        ensure_return=ensures, BootLoader_context=list(ctx[:4]),BootLoader_gap=context_row(ctx),
        BootLoader_state=U.from_address(owner+8).value,original_static_nonnull=True,module_fields=fields,
        module_roots=count,strong_roots=nroots,stack_depth=ctx[3])
    if control:
        S.check(result['BootLoader_gap']==f'boom_m{native_method}','Cold control failed before the original native stop')
    else:
        module_cell=mod_roots+slot*8
        S.check(Q.from_address(module_cell).value==oop,'Normal JCLS slot does not hold the source-created Module')
        bound=sum(Q.from_address(mod_roots+i*8).value==oop for i in range(count))
        S.check(bound==1 and U.from_address(owner+8).value in (2,3) and not ctx[3],
                'Module was assigned more than once or initialization/frame accounting is incomplete')
        result.update(same_oop_in_Java_and_vm=True,matching_jcls_slots=bound,added_gc_root_at_end=True,
                      source_initializer_completed=ensures==0 and not ctx[0] and U.from_address(owner+8).value==2)
        if concurrent:
            S.check(all(java==oop for _,_,_,java,_ in workers),'Concurrent readers saw different source module identities')
            result['concurrent_cold_initialization']=dict(OS_threads=len(workers),distinct_Module_oops=1,
                all_returned_after_publication=True,all_guest_frame_depths_zero=True)
        if result['source_initializer_completed']:
            original_roots={f['name']:bool(Q.from_address(addr(im,f"boom_s{class_id}_{f['index']}")).value)
                            for c in closure['selected_classes'] if c['class_id']==class_id for f in c['fields']}
            S.check(all(original_roots.values()),'Original BootLoader static initialization did not publish all source fields')
            result['Java_static_fields']=original_roots
            call=func(im,f'boom_m{native_method}',Q,P,P)
            again=Context();call(again,(Q*1)(oop))
            wrong=Context();call(wrong,(Q*1)(oop+8))
            null=Context();call(null,(Q*1)(0))
            preserved=Context(9,4,7,0);call(preserved,(Q*1)(oop))
            S.check(not again[0] and wrong[0]==7 and null[0]==4 and list(preserved[:4])==[9,4,7,0] and
                    Q.from_address(module_cell).value==oop and all(t[3]==0 for t in (again,wrong,null)),
                    'Idempotence, original exception or identity boundary failed')
            result['repeated_native_checks']=['identical Module','different reference','null','existing exception preserved']
    # Initialization can retain Java monitors when this diagnostic selection lacks later JDK methods.
    # Both control and candidate run in separate child processes, each with its own image and heap lifetime.
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','nio','prior','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--provider',type=Path)
    parser.add_argument('--worker',choices=['control','candidate','concurrent'])
    args=parser.parse_args()
    m,nio=S.read(args.candidate),S.read(args.nio)
    out=args.output.resolve()
    S.check(out.is_relative_to(S.ART),'Isolated output required')
    if args.worker:
        controlled=args.worker=='control'
        images=S.read(out/'images.json')
        image=S.checked(nio['image']) if controlled else S.checked(images['image'])
        if 'formal_provider' in images:
            S.check(args.provider is not None and S.checked(images['formal_provider']['provider'])==args.provider.resolve(),
                    'Formal worker provider differs from the verified linked pack')
            for key in ('verification','batch','batch_verification'):S.checked(images['formal_provider'][key])
        runtime=Path(nio['runtime'])
        S.check(S.checked(nio['runtime_dll'])==runtime/'boom-runtime.dll','Runtime DLL identity changed')
        observation=execution(image,runtime,Path(nio['selection_directory']),m,controlled,args.worker=='concurrent')
        S.write(out/(args.worker+'-execution.json'),observation)
    else:
        import sys
        out.mkdir(parents=True,exist_ok=False)
        dll,selection,formal=link(args.candidate,args.nio,args.prior,out,args.provider)
        images=dict(image=S.artifact(dll),source=S.artifact(args.candidate),baseline=nio['image'],
            selection_proof=nio['base_proof'],control_link_matched_original_image=True,runtime=nio['runtime_dll'])
        if formal:images['formal_provider']=formal
        S.write(out/'images.json',images)
        for worker in ('control','candidate','concurrent'):
            subprocess.run([sys.executable,__file__,*sys.argv[1:],'--worker',worker],check=True)
        result=dict(verified_Java_static_and_JCLS_publication=True,original_cold_control=S.read(out/'control-execution.json'),
            original_cold_candidate=S.read(out/'candidate-execution.json'),
            concurrent=S.read(out/'concurrent-execution.json'),images=S.artifact(out/'images.json'),
            manually_installed_Module_oop=False,shared_provider_registered=bool(formal),game_started=False)
        if formal:
            result.update(formal_provider=formal,formal_pack_and_normal_JCLS_executed=True,
                full_System_initPhase1_completed=not result['original_cold_candidate']['System_initPhase1_context'][0],
                full_original_game_started=False)
        S.write(out/'result.json',result)
        print(out/'result.json')
