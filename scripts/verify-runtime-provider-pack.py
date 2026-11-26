"""Independently verify source declarations, no-archive policy, ASM and COFF."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

spec=importlib.util.spec_from_file_location('provider_source_verification_io',Path(__file__).with_name('runtime-provider-source.py'))
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)

SPECS=(('initializeFromArchive','(Ljava/lang/Class;)V',0x109,0),
       ('isDumpingClassList0','()Z',0x10a,1),('isDumpingArchive0','()Z',0x10a,2),
       ('isSharingEnabled0','()Z',0x10a,3),('getRandomSeedForDumping','()J',0x109,4))


def contract(classes,owner,raw_methods):
    S.check(owner['origin']['loader']=='bootstrap' and owner['origin']['source_id']=='jdk:java.base' and
            not owner['origin'].get('generated') and owner['name']=='jdk/internal/misc/CDS','Provider must bind original bootstrap CDS')
    S.check(len(owner['method_ids'])==len(raw_methods),'Provider original method inventory differs')
    declarations={(m['name'],m['descriptor']):(i,m) for i,m in zip(owner['method_ids'],raw_methods)}
    result=[]
    for name,desc,access,op in SPECS:
        S.check((name,desc) in declarations,'Provider original native declaration missing')
        i,m=declarations[name,desc]
        S.check(m['code'] is None and m['access']==access,'Provider original native flags/Code changed')
        result.append(dict(method=i,class_id=owner['id'],class_sha256=owner['origin']['sha256'],loader='bootstrap',owner=owner['name'],
            source_id='jdk:java.base',name=name,descriptor=desc,access=access,operation=op))
    return result


def identity_contract(owners,raw):
    result=[]
    for owner,name,desc,access,op in [('java/lang/Object','hashCode','()I',0x101,0),('java/lang/System','identityHashCode','(Ljava/lang/Object;)I',0x109,1)]:
        c=owners[owner]
        S.check(c['origin']['loader']=='bootstrap' and c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Identity service requires original bootstrap source')
        S.check(len(c['method_ids'])==len(raw[owner]),'Identity source inventory differs')
        found=[(i,m) for i,m in zip(c['method_ids'],raw[owner]) if (m['name'],m['descriptor'])==(name,desc)]
        S.check(len(found)==1 and found[0][1]['access']==access and found[0][1]['code'] is None,'Identity source native changed')
        result.append(dict(method=found[0][0],class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',owner=owner,
            source_id='jdk:java.base',name=name,descriptor=desc,access=access,operation=op))
    return result


def wrapper(m,pool='boom_provider_cds_pool',service='boom_provider_cds_service'):
    i=m['method'];c=m['class_id'];op=m['operation']
    return f".code\nPUBLIC boom_m{i}\nboom_m{i} PROC FRAME\n sub rsp,56\n .allocstack 56\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n test rcx,rcx\n jz boom_m{i}_provider_zero\n cmp DWORD PTR [rcx],0\n jne boom_m{i}_provider_zero\n lea rcx,boom_class{c}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz boom_m{i}_provider_zero\n mov rcx,QWORD PTR [rsp+32]\n mov rdx,QWORD PTR [rsp+40]\n call boom_m{i}_native\n add rsp,56\n ret\nboom_m{i}_provider_zero:\n xor eax,eax\n add rsp,56\n ret\nboom_m{i} ENDP\nPUBLIC boom_m{i}_native\nboom_m{i}_native PROC\n lea r8,{pool}\n mov r9d,{op}\n jmp {service}\nboom_m{i}_native ENDP\n"


def verify(path,batch,plan):
    path=Path(path).resolve();S.check(path.is_relative_to(S.ART/'runtime-providers'),'Provider manifest must remain in project runtime-providers')
    services=S.module('verified_framed_services','framed-runtime-service.py')
    m=S.read(path)
    if m['family'] in services.FAMILIES:
        S.check(m['schema']==1 and m['kind']=='assembly_runtime_provider_pack','Invalid source native service manifest')
        return services.verify(path,batch,plan,m,S)
    S.check(not m.get('native_root_spans'),'Legacy family cannot declare native oop roots absent from its verified source model')
    S.check(m['schema']==1 and m['kind']=='assembly_runtime_provider_pack' and m['family'] in ('cds-no-archive-v1','object-identity-v1','normal-constructors-v1','class-flags-v1','normal-constructor-invocation-v1','normal-file-bootstrap-v1','normal-scoped-memory-registration-v1','normal-throwable-v1','normal-signal-lookup-v1','normal-thread-primitives-v1','normal-access-context-v1','normal-thread-start-v1','normal-thread-priority-v1','normal-signal-control-v1','normal-windows-startup-v1','normal-finalization-policy-v1','normal-object-notification-v1','normal-unsafe-class-initialization-v1'),'Unknown runtime provider semantics')
    if m['family']=='normal-unsafe-class-initialization-v1':
        verifier=S.module('verified_normal_unsafe_class_init','verify-unsafe-class-init.py')
        return verifier.verify(path,batch,plan,m,S)
    if m['family']=='normal-object-notification-v1':
        verifier=S.module('original_object_notification_verifier','verify-object-notification.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-finalization-policy-v1':
        verifier=S.module('original_finalization_policy_verifier','verify-finalization-policy.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-thread-priority-v1':
        verifier=S.module('original_normal_thread_priority_verifier','verify-normal-thread-priority.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-windows-startup-v1':
        verifier=S.module('original_normal_windows_startup_verifier','verify-windows-startup-provider.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-signal-control-v1':
        verifier=S.module('original_normal_signal_control_verifier','verify-normal-signal-control.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-thread-start-v1':
        verifier=S.module('original_normal_thread_start_verifier','verify-normal-thread-start.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-access-context-v1':
        verifier=S.module('original_normal_access_context_verifier','verify-normal-access.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-thread-primitives-v1':
        verifier=S.module('original_normal_thread_primitives_verifier','verify-normal-thread.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-signal-lookup-v1':
        verifier=S.module('original_normal_signal_lookup_verifier','verify-signal-lookup.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-scoped-memory-registration-v1':
        verifier=S.module('original_scoped_registration_verifier','verify-scoped-memory.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-throwable-v1':
        verifier=S.module('original_normal_throwable_verifier','verify-normal-throwable.py')
        return verifier.verify(path,batch,plan,m,S)
    if m['family']=='normal-file-bootstrap-v1':
        verifier=S.module('original_file_bootstrap_verifier','verify-file-bootstrap.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-constructor-invocation-v1':
        verifier=S.module('original_constructor_invocation_verifier','verify-constructor-invocation.py')
        return verifier.verify(path,batch,plan,m,S)
    if m['family']=='class-flags-v1':
        verifier=S.module('original_class_flags_provider_verifier','verify-class-flags-provider.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    if m['family']=='normal-constructors-v1':
        verifier=S.module('original_constructor_provider_verifier','verify-constructor-provider.py')
        return verifier.verify(path,batch,plan,m,S,wrapper)
    identity,summary,classes=S.base(batch,plan)
    S.check(m['base']==identity,'Provider base batch/compiler/IR/layout/transform identity differs')
    S.check(m['tool_sources']==S.tools_identity(),'Provider generator/verifier/template/kernel identity changed')
    S.check(m['context_bytes']==32 and m['pool_bytes']==32,'Provider Context/pool ABI differs')
    S.check(m['assembled'] and m['leaf_guest_services'] and not any(m[k] for k in ('java_codegen_rerun','base_Java_ASM_and_COFF_modified','all_family_natives_implemented','linked','executed','game_started','world_created')),
            'Provider metadata overclaims generation/execution scope')
    cds=m['family']=='cds-no-archive-v1';owner_name='jdk/internal/misc/CDS' if cds else 'java/lang/Object'
    owner=next((c for c in classes if c['name']==owner_name and c['origin']['loader']=='bootstrap'),None)
    S.check(owner is not None and owner==m['owner_source'],'Provider source class identity differs')
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    owner_names=[owner_name] if cds else ['java/lang/Object','java/lang/System']
    owners={name:classes[names['bootstrap',name]] for name in owner_names};parser=S.module('provider_raw_class_parser','verify-batch-frames.py');raw={}
    for name,c in owners.items():
        actual,raw[name]=parser.original_methods(S.original_class(summary,c));S.check(actual==name,'Provider original binary name changed')
    expected_owners=sorted(owners.values(),key=lambda c:c['id']);S.check(m['owner_sources']==expected_owners,'Provider declaration owner set differs')
    methods=contract(classes,owner,raw[owner_name]) if cds else identity_contract(owners,raw)
    S.check(m['methods']==methods and m['native_methods']==len(methods),'Provider source members/operations differ')
    expected='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'+''.join(f"EXTERN boom_class{c['id']}:BYTE\n" for c in expected_owners)
    imports={'boom_class_ensure32'}|{f"boom_class{c['id']}" for c in expected_owners}
    if cds:
        pool,service='boom_provider_cds_pool','boom_provider_cds_service';kernel=S.ROOT/'native/providers/cds.asm.inc'
        policy=dict(shared_archive_mapped=False,dumping_archive=False,dumping_class_list=False);pool_abi=2
        required=[owner['id'],names['bootstrap','java/lang/Class'],names['bootstrap','java/lang/Object']];modules=['class_literals']
        runtime_kernels=['classes32.asm','java_classes.asm']
        imports|={'boom_java_class_typeid','boom_java_class_pool'}
        expected+='EXTERN boom_java_class_typeid:PROC\nEXTERN boom_java_class_pool:BYTE\n.const\nALIGN 8\nPUBLIC boom_provider_cds_pool\nboom_provider_cds_pool DWORD 043445350h,2,0,0\n QWORD OFFSET boom_java_class_pool,0\n'
    else:
        pool,service='boom_provider_identity_pool','boom_provider_identity_service';kernel=S.ROOT/'native/providers/identity.asm.inc'
        policy=dict(nonmoving_heap_abi=1,moving_heap=False,identity_algorithm='pointer_mix32_v1');pool_abi=1
        required=[c['id'] for c in expected_owners];modules=[]
        runtime_kernels=['classes32.asm','heap.asm','runtime_types.asm','runtime_type_index.asm','identity_hash.asm']
        imports|={'boom_heap_contains','boom_runtime_type','boom_identity_hash','boom_heap_ptr','boom_runtime_type_map'}
        expected+='EXTERN boom_heap_contains:PROC\nEXTERN boom_runtime_type:PROC\nEXTERN boom_identity_hash:PROC\nEXTERN boom_heap_ptr:BYTE\nEXTERN boom_runtime_type_map:BYTE\n.const\nALIGN 8\nPUBLIC boom_provider_identity_pool\nboom_provider_identity_pool DWORD 04A494448h,1,1,0\n QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map\n'
    S.check(m['policy']==policy and m['pool_abi']==pool_abi,'Provider execution policy/ABI differs')
    S.check(m['required_class_ids']==required and m['required_base_modules']==modules,'Provider initialization/module dependencies differ')
    S.check(m['pool_symbol']==pool and m['service_symbol']==service,'Provider symbols differ')
    S.check(m['kernel_sha256']==S.digest(kernel)['sha256'],'Provider assembly kernel changed')
    expected+=''.join(wrapper(method,pool,service) for method in methods)+kernel.read_text(encoding='utf-8')+'\nEND\n'
    S.check(m['runtime_kernel_sha256']=={'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in runtime_kernels},'Provider imported runtime implementation/heap identity differs')
    assembly=S.checked(m['assembly']);obj=S.checked(m['object'])
    S.check(assembly.parent==path.parent and obj.parent==path.parent,'Provider source/object escaped its package')
    S.check(assembly.read_text(encoding='utf-8')==expected,'Provider ASM differs from original source contracts')
    assembler=Path(m['assembler']['path']);S.check(S.digest(assembler)==m['assembler']['digest'],'Provider assembler changed')
    coff=S.module('provider_actual_coff','verify-batch-assembly.py');defined,undefined=coff.coff_symbols(obj)
    exports={pool,service}|{f"boom_m{r['method']}{suffix}" for r in methods for suffix in ('','_native')}
    S.check(defined==exports==set(m['exports']) and undefined==imports==set(m['imports']),'Provider actual COFF symbols differ')
    # A provider may fill a missing declaration; it must not replace a supplied one.
    import zipfile
    for key in ('system_natives','class_literals','string_intern','properties','class_bootstrap','unsafe_bootstrap','vm_registration','runtime_resources','bitcasts','unsafe_fields','unsafe_memory','class_lookup','frames'):
        module=summary[key]
        with zipfile.ZipFile(module['index']['path']) as z:
            filename='natives.jsonl' if key=='frames' else 'methods.jsonl'
            existing={json.loads(l)['method'] for l in z.read(filename).splitlines()}
        S.check(not existing&{r['method'] for r in methods},'Provider overlaps a base native implementation')
    return dict(schema=1,verified=True,scope='separate_source_bound_assembly_native_family_and_actual_COFF_only',
        provider_manifest=str(path),provider_manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        base_batch_summary_sha256=identity['batch_summary']['digest']['sha256'],native_methods=len(methods),context_bytes=32,pool_abi=pool_abi,
        java_codegen_rerun=False,base_Java_ASM_and_COFF_modified=False,source_initializer_executed=False,
        runtime_linkage_closure_verified=False,linked=False,executed=False,game_started=False,world_created=False)


def load_packs(batch,plan,paths):
    if not paths:return []
    with S.base_scope(batch,plan):return _load_packs_in_scope(batch,plan,paths)


def _load_packs_in_scope(batch,plan,paths):
    result=[];ids=set();symbols=set()
    for path in paths or ():
        path=Path(path).resolve();proof=verify(path,batch,plan);receipt=S.read(path.with_name('verification.json'))
        S.check(receipt==proof,'Provider independent verification receipt differs')
        m=S.read(path);new_ids={r['method'] for r in m['methods']}
        S.check(not ids&new_ids and not symbols&set(m['exports']),'Conflicting or duplicate assembly runtime providers')
        ids|=new_ids;symbols.update(m['exports']);result.append(dict(manifest=m,reference=S.artifact(path),verification=S.artifact(path.with_name('verification.json'))))
    families={p['manifest']['family'] for p in result}
    for p in result:S.check(set(p['manifest'].get('required_provider_families',[]))<=families,'Runtime provider family dependency is missing')
    return result


def references(packs):return [dict(manifest=p['reference'],verification=p['verification']) for p in packs]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('provider',type=Path);p.add_argument('--batch',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();v=verify(a.provider,a.batch,a.plan)
    if a.output:S.write(a.output,v)
    print(json.dumps(v))
