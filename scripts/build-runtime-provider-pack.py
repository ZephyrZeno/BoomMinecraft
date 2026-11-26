"""Generate a source-bound native family separately from existing Java ASM/COFF."""
import argparse
import json
from pathlib import Path
import time
import importlib.util

spec=importlib.util.spec_from_file_location('provider_source_generator',Path(__file__).with_name('runtime-provider-source.py'))
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)


def prepare(batch,plan,output,family,frame_overlay=None):
    started=time.monotonic();output=Path(output).resolve()
    S.check(output.is_relative_to(S.ART/'runtime-providers') and not output.exists(),'Use a fresh project runtime-providers directory')
    identity,summary,classes=S.base(batch,plan);registry=S.read(S.ROOT/'native-config/runtime-providers.json')
    S.check(registry['schema']==1 and family in registry['families'],'Unknown provider family');rule=registry['families'][family]
    wanted_owners={rule['owner']}|{m.get('owner',rule['owner']) for m in rule['methods']}
    owners={c['name']:c for c in classes if (c['origin']['loader'],c['origin']['source_id'])==(rule['loader'],rule['source_id']) and c['name'] in wanted_owners and not c['origin'].get('generated')}
    S.check(set(owners)==wanted_owners,'Provider owners missing or ambiguous');owner=owners[rule['owner']]
    declarations={}
    with Path(identity['source_methods']['path']).open(encoding='utf-8') as stream:
        for line in stream:
            m=json.loads(line)
            if m['class_id'] in {c['id'] for c in owners.values()}:declarations[m['symbol']['owner'],m['symbol']['name'],m['symbol']['descriptor']]=m
    members=[]
    for contract in rule['methods']:
        declared=owners[contract.get('owner',rule['owner'])];m=declarations[declared['name'],contract['name'],contract['descriptor']]
        S.check(m['access']==contract['access'] and m['code_sha256'] is None and m['class_sha256']==declared['origin']['sha256'],'Provider source declaration changed')
        members.append(dict(method=m['id'],class_id=declared['id'],class_sha256=m['class_sha256'],loader=rule['loader'],owner=declared['name'],
            source_id=rule['source_id'],name=contract['name'],descriptor=contract['descriptor'],access=m['access'],operation=contract['operation']))
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    imports=['boom_class_ensure32']+[f"boom_class{c['id']}" for c in owners.values()]
    source='option casemap:none\nEXTERN boom_class_ensure32:PROC\n'
    source+=''.join(f"EXTERN boom_class{c['id']}:BYTE\n" for c in sorted(owners.values(),key=lambda c:c['id']))
    metadata=None;pool_bytes=32;metadata_kind=None;additional_exports=[];kernel_override=None;framed=False;frame_reference=None
    framed_services=S.module('native_framed_service_contracts','framed-runtime-service.py')
    if family in framed_services.FAMILIES:
        module,metadata_kind,_=framed_services.FAMILIES[family]
        C=S.module('source_'+metadata_kind,module)
        metadata=C.index(summary,classes,S);S.check(members==metadata['methods'],'Native registry differs from original declarations')
        frame_reference=framed_services.source_frame(batch,plan,frame_overlay,metadata,S)
        procs,data=C.native_imports(metadata);extra=sorted(procs|data);imports+=extra
        source+=''.join(f"EXTERN {n}:{'PROC' if n in procs else 'BYTE'}\n" for n in extra)+C.data(metadata)
        policy=C.POLICY;dependencies=metadata['required_classes'];modules=metadata.get('required_base_modules',[]);pool_abi=metadata['pool_abi']
        pool_bytes=metadata['pool_bytes'];framed=True;runtime_kernels=C.KERNELS;additional_exports=sorted(C.CONTROL)
    elif family=='normal-unsafe-class-initialization-v1':
        C=S.module('normal_unsafe_class_init','unsafe-class-init-source.py');metadata_kind='unsafe_class_init'
        metadata=C.index(summary,classes,S);S.check(members==metadata['methods'],'Unsafe registry differs from original class')
        frame_reference=C.source_frame(batch,plan,frame_overlay,metadata,S)
        procs,data=C.native_imports(metadata);extra=sorted(procs|data);imports+=extra
        source+=''.join(f"EXTERN {n}:{'PROC' if n in procs else 'BYTE'}\n" for n in extra)+C.data(metadata)
        policy=C.POLICY;dependencies=[owner['id']];modules=C.MODULES;pool_abi=1;pool_bytes=48;framed=True;runtime_kernels=C.KERNELS
    elif family=='normal-object-notification-v1':
        C=S.module('normal_object_notification_generation','object-notification-source.py');metadata_kind='object_notification'
        metadata=C.index(summary,classes,S);S.check(members==metadata['methods'],'Object notification registry differs from original declarations')
        source+='EXTERN boom_monitor_notify:PROC\nEXTERN boom_monitor_notify_all:PROC\nEXTERN boom_heap_ptr:BYTE\n'+C.data()
        imports+=['boom_monitor_notify','boom_monitor_notify_all','boom_heap_ptr']
        policy=C.POLICY;dependencies=[owner['id']];modules=[];pool_abi=1;pool_bytes=32;runtime_kernels=C.KERNELS
    elif family=='normal-finalization-policy-v1':
        C=S.module('normal_finalization_policy_generation','finalization-policy-source.py');metadata_kind='finalization_policy'
        metadata=C.index(summary,classes,S);S.check(members==metadata['methods'],'Finalization policy registry differs from original declaration')
        source+=C.data();policy=C.POLICY;dependencies=[owner['id']];modules=[];pool_abi=1;pool_bytes=32;runtime_kernels=C.KERNELS
    elif family=='normal-windows-startup-v1':
        C=S.module('normal_windows_startup_generation','windows-startup-source.py');metadata_kind='windows_startup'
        metadata=C.index(summary,classes,S);S.check(members==metadata['methods'],'Windows startup registry differs from original declaration')
        source+='EXTERN boom_windows_error_mode:PROC\n'+C.data();imports+=['boom_windows_error_mode']
        policy=C.POLICY;dependencies=[owner['id']];modules=[];pool_abi=1;pool_bytes=32;runtime_kernels=C.KERNELS
    elif family=='normal-signal-control-v1':
        C=S.module('normal_signal_control_generation','normal-signal-control-source.py');metadata_kind='normal_signal_control'
        metadata=C.index(summary,classes,S)
        S.check(members==metadata['methods'],'Signal control registry differs from original declarations')
        metadata_source,metadata_imports=C.data(metadata);kernel_override,services=C.kernel(S)
        extra=(metadata_imports|services)-set(imports);imports+=sorted(extra)
        source+=''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))+metadata_source
        policy=C.POLICY;dependencies=metadata['required_class_ids'];modules=['properties'];pool_abi=1;pool_bytes=256;runtime_kernels=C.KERNELS
        additional_exports=sorted(C.exports(members)-{rule['pool'],rule['service']}-{
            f"boom_m{m['method']}{suffix}" for m in members for suffix in ('','_native')})
    elif family=='normal-thread-priority-v1':
        C=S.module('normal_thread_priority_generation','normal-thread-priority-source.py');metadata_kind='normal_thread_priority'
        metadata=C.index(summary,classes,S)
        S.check(members==metadata['methods'],'Thread priority registry differs from original declaration')
        metadata_source,metadata_imports=C.data(metadata);kernel_override,services=C.kernel(S)
        extra=(metadata_imports|services)-set(imports);imports+=sorted(extra)
        source+=''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))+metadata_source
        policy=C.POLICY;dependencies=sorted(metadata[k] for k in ('thread_class','holder_class','virtual_class'))
        modules=[];pool_abi=1;pool_bytes=80;runtime_kernels=C.KERNELS
        additional_exports=sorted(C.exports(members)-{rule['pool'],rule['service']}-{
            f"boom_m{m['method']}{suffix}" for m in members for suffix in ('','_native')})
    elif family=='normal-thread-start-v1':
        C=S.module('normal_thread_start_generation','normal-thread-start-source.py');metadata_kind='normal_thread_start'
        metadata=C.index(summary,classes,S)
        S.check(members==metadata['methods'],'Thread start registry differs from original declaration')
        metadata_source,metadata_imports=C.data(metadata);kernel_override,services=C.kernel()
        extra=(metadata_imports|services)-set(imports);imports+=sorted(extra)
        source+=''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))+metadata_source
        policy=C.POLICY;dependencies=sorted(metadata[k] for k in ('thread_class','holder_class','virtual_class','throwable_class','runnable_class'))
        modules=[];pool_abi=1;pool_bytes=256;runtime_kernels=C.KERNELS
        additional_exports=sorted(C.exports(members)-{rule['pool'],rule['service']}-{
            f"boom_m{m['method']}{suffix}" for m in members for suffix in ('','_native')})
    elif family=='normal-access-context-v1':
        C=S.module('normal_access_generation','normal-access-source.py');metadata_kind='normal_access'
        S.check(frame_overlay is not None,'Normal access capture requires the verified source native frame overlay')
        F=S.module('normal_access_frame_overlay','native-frame-overlay.py');frame_overlay=Path(frame_overlay).resolve()
        proof=F.verify(frame_overlay,batch,plan);S.check(S.read(frame_overlay.with_name('verification.json'))==proof,'Normal access frame overlay receipt differs')
        frame_reference=dict(manifest=S.artifact(frame_overlay),verification=S.artifact(frame_overlay.with_name('verification.json')))
        metadata=C.index(summary,classes,S.read(frame_overlay),S)
        S.check(members==metadata['methods'],'Normal access native registry differs from original declarations')
        metadata_source,metadata_imports=C.data(metadata);kernel_override,services=C.kernel()
        extra=(metadata_imports|services)-set(imports);imports+=sorted(extra)
        source+=''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))+metadata_source
        policy=C.POLICY;dependencies=sorted([owner['id'],metadata['context_class'],metadata['thread_class'],metadata['domain_class'],names['bootstrap','java/lang/Class']])
        modules=['class_literals'];pool_abi=2;pool_bytes=192;runtime_kernels=C.KERNELS
        additional_exports=['boom_provider_access_bind_domain','boom_provider_access_domain_roots','boom_provider_access_domain_root_count','boom_provider_access_domain_bound']
    elif family=='normal-thread-primitives-v1':
        C=S.module('normal_thread_primitives_generation','normal-thread-source.py');metadata=C.index(summary,classes,S);metadata_kind='normal_thread'
        S.check(members==metadata['methods'],'Thread primitive registry differs from original declarations')
        data,data_imports=C.data(metadata);services={'boom_thread_native_register','boom_thread_native_dispatch','boom_thread_native_bind'}
        extra=(data_imports|services)-set(imports);imports+=sorted(extra)
        source+=''.join(f"EXTERN {n}:{'QWORD' if n.startswith('__imp_') else 'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))+data
        policy=dict(normal_source_layouts=True,original_native_inventory=20,registered_table_slots=18,executable_slots=5,
            canonical_target_addresses_from_IAT=True,platform_threads_only=True,Java_constructors=False,Java_thread_start=False,virtual_threads=False,VM_id_address_atomics=False)
        dependencies=sorted([metadata['thread_class'],metadata['virtual_base_class']]);modules=[];pool_abi=1;pool_bytes=80;runtime_kernels=C.KERNELS
        additional_exports=['boom_provider_thread_bind','boom_provider_thread_registry']
    elif family=='normal-signal-lookup-v1':
        C=S.module('normal_signal_lookup_generation','signal-lookup-source.py');metadata=C.index(summary,classes,S);metadata_kind='signal_lookup'
        S.check(members==[metadata['lookup']],'Signal lookup registry differs from original declarations')
        services={'boom_heap_contains','boom_object_check'};data_imports={'boom_heap_ptr','boom_java_string_literal_pool'}
        extra=(services|data_imports)-set(imports);imports+=sorted(extra)
        source+=''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))+C.data()
        policy=dict(normal_source_layouts=True,platform='Windows',case_sensitive=True,unknown_signal=-1,
            handler_installation=False,signal_raise=False,Java_signal_dispatch=False)
        dependencies=sorted([owner['id'],names['bootstrap','java/lang/String']]);modules=['class_literals'];pool_abi=1;pool_bytes=32;runtime_kernels=C.KERNELS
    elif family=='normal-scoped-memory-registration-v1':
        C=S.module('normal_scoped_registration_generation','scoped-memory-source.py');metadata=C.index(summary,classes,S);metadata_kind='scoped_memory'
        S.check(members==[metadata['registration']],'Scoped registration registry differs from original declarations')
        services={'boom_scoped_native_register','__imp_boom_scoped_close_unavailable'};imports+=sorted(services)
        source+=''.join(f"EXTERN {n}:{'QWORD' if n.startswith('__imp_') else 'PROC'}\n" for n in sorted(services))+C.data()
        policy=dict(original_native_inventory=True,registered_entries=1,close_target='explicit_UnsatisfiedLinkError',target_address_policy='canonical_runtime_export_from_IAT',close_scope_implemented=False,thread_handshake_implemented=False)
        dependencies=[owner['id']];modules=[];pool_abi=1;runtime_kernels=C.KERNELS
    elif family=='normal-throwable-v1':
        C=S.module('normal_throwable_generation','normal-throwable-source.py');metadata=C.index(summary,classes);metadata_kind='normal_throwable'
        S.check(members==C.contracts(summary,classes),'Throwable registry differs from original declarations')
        S.check(frame_overlay is not None,'Normal Throwable requires a verified native frame overlay')
        F=S.module('normal_throwable_generation_frames','native-frame-overlay.py');frame_overlay=Path(frame_overlay).resolve()
        proof=F.verify(frame_overlay,batch,plan);S.check(S.read(frame_overlay.with_name('verification.json'))==proof,'Throwable native frame overlay receipt differs')
        frame_reference=dict(manifest=S.artifact(frame_overlay),verification=S.artifact(frame_overlay.with_name('verification.json')))
        data,data_imports=C.data(metadata)
        services={'boom_object_check','boom_type_assignable','boom_array_new','boom_trace_head','boom_heap_contains','boom_trace_enter','boom_trace_leave'}
        extra=(data_imports|services|{f"boom_trace_method{m['method']}" for m in members})-set(imports);imports+=sorted(extra)
        source+=''.join(f"EXTERN {n}:{'PROC' if n in services else 'BYTE'}\n" for n in sorted(extra))+data
        policy=dict(normal_source_layouts=True,trace_pool_abi=3,max_backtrace_frames=128,backtrace_OOM_suppressed=True,
            Java_StackTraceElement_materialization=False,implicit_exception_factory=False,stack_roots=False,automatic_gc=False)
        dependencies=[owner['id']];modules=[];pool_abi=1;pool_bytes=64;framed=True;runtime_kernels=C.KERNELS
    elif family=='normal-file-bootstrap-v1':
        C=S.module('normal_file_bootstrap_generation','file-bootstrap-source.py')
        S.check(members==C.contracts(summary,classes,S),'File bootstrap registry differs from original declarations')
        metadata=C.index(summary,classes,S);metadata_kind='file_bootstrap';metadata_source,metadata_imports=C.data(metadata)
        service_imports={'boom_stream_fields_init','boom_fd_service'}
        extra=(service_imports|metadata_imports)-set(imports);imports+=sorted(extra)
        source+=''.join(f"EXTERN {name}:{'PROC' if name in service_imports else 'BYTE'}\n" for name in sorted(extra))+metadata_source
        policy=dict(normal_source_layouts=True,source_field_registration=True,standard_handles='Windows_GetStdHandle',append='Windows_false',byte_order='native_DWORD_memory_probe',file_IO_natives=False)
        dependencies=sorted(c['id'] for c in owners.values());modules=[];pool_abi=1;pool_bytes=48;runtime_kernels=C.KERNELS
    elif family=='normal-constructor-invocation-v1':
        C=S.module('constructor_invocation_generation','constructor-invocation-source.py');metadata=C.index(summary,classes);metadata_kind='invocation'
        S.check(members==C.contracts(summary,classes,S),'Invocation registry differs from original declarations')
        S.check(frame_overlay is not None,'Constructor invocation requires a verified native frame overlay')
        F=S.module('constructor_invocation_frames','native-frame-overlay.py');frame_overlay=Path(frame_overlay).resolve()
        proof=F.verify(frame_overlay,batch,plan);S.check(S.read(frame_overlay.with_name('verification.json'))==proof,'Invocation frame overlay receipt differs')
        frame_reference=dict(manifest=S.artifact(frame_overlay),verification=S.artifact(frame_overlay.with_name('verification.json')))
        kernel_override,kernel_imports=C.kernel_text(S.ROOT);metadata_source,metadata_imports=C.data(metadata)
        extra=(kernel_imports|metadata_imports|{'boom_trace_enter','boom_trace_leave','boom_trace_pool'}|
               {f"boom_trace_method{m['method']}" for m in members})-set(imports)
        imports+=sorted(extra);procs=kernel_imports|{'boom_trace_enter','boom_trace_leave'}
        source+=''.join(f"EXTERN {name}:{'PROC' if name in procs else 'BYTE'}\n" for name in sorted(extra))+metadata_source
        policy=dict(normal_source_layouts=True,source_constructor_bodies=True,selected_diagnostic_upcalls=True,
            exception_wrapping_complete=False,dynamic_redefinition=False)
        dependencies=sorted({c['id'] for c in owners.values()}|{metadata['constructor_class'],names['bootstrap','java/lang/Class']})
        modules=['class_literals'];pool_abi=1;pool_bytes=96;framed=True;additional_exports=sorted(C.HELPERS)
        runtime_kernels=['classes32.asm','java_classes.asm','objects.asm','heap.asm','runtime_types.asm','runtime_type_index.asm','frames.asm']
    elif family=='class-flags-v1':
        C=S.module('class_flags_generation_source','class-flags-source.py');metadata=C.index(summary,classes);metadata_kind='flags'
        imports+=['boom_java_class_typeid','boom_java_class_pool']
        source+='EXTERN boom_java_class_typeid:PROC\nEXTERN boom_java_class_pool:BYTE\n'+C.data(metadata)
        policy=dict(original_class_flags=True,reflection_inner_class_modifiers=True,arrays_raw_flags_zero=True,dynamic_redefinition=False)
        dependencies=sorted(c['id'] for c in owners.values());modules=['class_literals'];pool_abi=1
        runtime_kernels=['classes32.asm','java_classes.asm']
    elif family=='normal-constructors-v1':
        C=S.module('constructor_provider_generation_source','constructor-provider-source.py')
        metadata=C.index(summary,classes);metadata_kind='constructors';metadata_source,metadata_imports=C.data(metadata)
        service_imports={'boom_heap_alloc','boom_object_new','boom_java_class_typeid','boom_java_class_load'}
        extra=(metadata_imports|service_imports)-set(imports);imports+=sorted(extra)
        source+=''.join(f"EXTERN {name}:{'PROC' if name in service_imports else 'BYTE'}\n" for name in sorted(extra))
        source+=metadata_source
        policy=dict(normal_source_layouts=True,metadata_from_original_classes=True,nonmoving_heap_abi=1,dynamic_redefinition=False)
        dependencies=[owner['id'],metadata['constructor_class'],metadata['string_class']];modules=['class_literals'];pool_abi=1;pool_bytes=160
        runtime_kernels=['classes32.asm','java_classes.asm','objects.asm','heap.asm']
    elif family=='cds-no-archive-v1':
        imports+=['boom_java_class_typeid','boom_java_class_pool'];policy=dict(shared_archive_mapped=False,dumping_archive=False,dumping_class_list=False)
        dependencies=[owner['id'],names['bootstrap','java/lang/Class'],names['bootstrap','java/lang/Object']];modules=['class_literals'];pool_abi=2
        runtime_kernels=['classes32.asm','java_classes.asm']
        source+='EXTERN boom_java_class_typeid:PROC\nEXTERN boom_java_class_pool:BYTE\n.const\nALIGN 8\nPUBLIC boom_provider_cds_pool\nboom_provider_cds_pool DWORD 043445350h,2,0,0\n QWORD OFFSET boom_java_class_pool,0\n'
    elif family=='object-identity-v1':
        imports+=['boom_heap_contains','boom_runtime_type','boom_identity_hash','boom_heap_ptr','boom_runtime_type_map']
        policy=dict(nonmoving_heap_abi=1,moving_heap=False,identity_algorithm='pointer_mix32_v1')
        dependencies=[c['id'] for c in sorted(owners.values(),key=lambda c:c['id'])];modules=[];pool_abi=1
        runtime_kernels=['classes32.asm','heap.asm','runtime_types.asm','runtime_type_index.asm','identity_hash.asm']
        source+='EXTERN boom_heap_contains:PROC\nEXTERN boom_runtime_type:PROC\nEXTERN boom_identity_hash:PROC\nEXTERN boom_heap_ptr:BYTE\nEXTERN boom_runtime_type_map:BYTE\n.const\nALIGN 8\nPUBLIC boom_provider_identity_pool\nboom_provider_identity_pool DWORD 04A494448h,1,1,0\n QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map\n'
    else:raise ValueError('Provider family generator is not implemented')
    template=(S.ROOT/'native/providers/native-wrapper.asm.tpl').read_text(encoding='utf-8')
    for m in members:
        if framed:
            R=S.module('invocation_traced_source_adapter','verify-batch-frames.py')
            source+=f".code\nPUBLIC boom_m{m['method']}\nPUBLIC boom_m{m['method']}_native\n"+R.native_adapter(m['method'],m['class_id'],rule['pool'],rule['service'],m['operation'])[len('.code\n'):]
        else:source+=template.format(**m,pool=rule['pool'],service=rule['service'])
    source+=(kernel_override if kernel_override is not None else (S.ROOT/rule['kernel']).read_text(encoding='utf-8'))+'\nEND\n'
    output.mkdir(parents=True);path=output/'provider.asm';path.write_text(source,encoding='utf-8',newline='\n')
    result=dict(schema=1,kind='assembly_runtime_provider_pack',family=family,base=identity,methods=members,
        native_methods=len(members),owner_source=owner,owner_sources=sorted(owners.values(),key=lambda c:c['id']),context_bytes=32,policy=policy,
        required_class_ids=dependencies,required_base_modules=modules,pool_symbol=rule['pool'],service_symbol=rule['service'],pool_abi=pool_abi,pool_bytes=pool_bytes,
        exports=([rule['pool']] if rule['pool'] not in imports else [])+[rule['service']]+[f"boom_m{m['method']}{suffix}" for m in members for suffix in ('','_native')]+additional_exports,
        imports=imports,
        assembly=S.artifact(path),kernel_sha256=S.digest(S.ROOT/rule['kernel'])['sha256'],tool_sources=S.tools_identity(),
        runtime_kernel_sha256={'native/runtime/'+n:S.digest(S.ROOT/'native/runtime'/n)['sha256'] for n in runtime_kernels},
        java_codegen_rerun=False,base_Java_ASM_and_COFF_modified=False,leaf_guest_services=family not in ('normal-constructors-v1','normal-constructor-invocation-v1','normal-access-context-v1','normal-thread-start-v1','normal-signal-control-v1','normal-unsafe-class-initialization-v1'),all_family_natives_implemented=False,
        assembled=False,linked=False,executed=False,game_started=False,world_created=False,elapsed_ms=round((time.monotonic()-started)*1000))
    if family in framed_services.FAMILIES:
        record=output/(metadata_kind+'.json');S.write(record,metadata);result[metadata_kind+'_metadata']=S.artifact(record)
        result.update(native_entries_traced=True,native_java_upcalls=metadata_kind in ('winnt_filesystem','object_wait','native_library','library_name','windows_canonical','windows_file_queries'),leaf_guest_services=False,
                      all_native_frames=False,frame_overlay=frame_reference,allowed_foreign_imports=sorted(C.FOREIGN))
        if metadata_kind in ('object_wait','boot_unnamed','reference_referent','native_library','library_name','windows_canonical','windows_file_queries'):
            result.update(required_java_methods=metadata.get('required_java_methods',[]),required_provider_families=metadata.get('required_provider_families',[]))
    elif metadata_kind=='unsafe_class_init':
        S.write(output/'unsafe-class-init.json',metadata);result['unsafe_class_init_metadata']=S.artifact(output/'unsafe-class-init.json')
        result.update(native_entries_traced=True,native_java_upcalls=True,all_native_frames=False,frame_overlay=frame_reference)
    elif metadata_kind=='object_notification':
        S.write(output/'object-notification.json',metadata);result['object_notification_metadata']=S.artifact(output/'object-notification.json')
        result['all_native_frames']=False
    elif metadata_kind=='finalization_policy':
        S.write(output/'finalization-policy.json',metadata);result['finalization_policy_metadata']=S.artifact(output/'finalization-policy.json')
        result['all_native_frames']=False
    elif metadata_kind=='windows_startup':
        S.write(output/'windows-startup.json',metadata);result['windows_startup_metadata']=S.artifact(output/'windows-startup.json')
    elif metadata_kind=='normal_signal_control':
        S.write(output/'normal-signal-control.json',metadata);result['normal_signal_control_metadata']=S.artifact(output/'normal-signal-control.json')
        result['required_provider_families']=['normal-thread-primitives-v1','normal-thread-start-v1'];result['all_native_frames']=False
        result['allowed_foreign_imports']=sorted(C.FOREIGN)
        result['required_java_methods']=sorted(m['method'] for m in metadata['upcalls']);result['required_source_contracts']=[]
    elif metadata_kind=='normal_thread_priority':
        S.write(output/'normal-thread-priority.json',metadata);result['normal_thread_priority_metadata']=S.artifact(output/'normal-thread-priority.json')
        result['required_provider_families']=['normal-thread-primitives-v1'];result['all_native_frames']=False
    elif metadata_kind=='normal_thread_start':
        S.write(output/'normal-thread-start.json',metadata);result['normal_thread_start_metadata']=S.artifact(output/'normal-thread-start.json')
        result['required_provider_families']=['normal-thread-primitives-v1','normal-thread-priority-v1'];result['all_native_frames']=False
        result['allowed_foreign_imports']=sorted(C.FOREIGN)
        result['required_java_methods']=sorted(m['method'] for m in metadata['upcalls'] if m['name']!='runWith')
        result['required_source_contracts']=[metadata['run_contract']['label']]
    elif metadata_kind=='normal_access':
        S.write(output/'normal-access.json',metadata);result['normal_access_metadata']=S.artifact(output/'normal-access.json')
        result['frame_overlay']=frame_reference;result['all_native_frames']=False;result['required_provider_families']=['normal-thread-primitives-v1']
    elif metadata_kind=='normal_thread':
        S.write(output/'normal-thread.json',metadata);result['normal_thread_metadata']=S.artifact(output/'normal-thread.json')
    elif metadata_kind=='signal_lookup':
        S.write(output/'signal-lookup.json',metadata);result['signal_lookup_metadata']=S.artifact(output/'signal-lookup.json')
    elif metadata_kind=='scoped_memory':
        S.write(output/'scoped-memory.json',metadata);result['scoped_memory_metadata']=S.artifact(output/'scoped-memory.json')
    elif metadata_kind=='normal_throwable':
        S.write(output/'normal-throwable.json',metadata);result['normal_throwable_metadata']=S.artifact(output/'normal-throwable.json')
        result['native_entries_traced']=True;result['all_native_frames']=False;result['frame_overlay']=frame_reference
    elif metadata_kind=='file_bootstrap':
        S.write(output/'file-bootstrap.json',metadata);result['file_bootstrap_metadata']=S.artifact(output/'file-bootstrap.json')
    elif metadata_kind=='invocation':
        S.write(output/'constructor-invocation.json',metadata);result['constructor_invocation_metadata']=S.artifact(output/'constructor-invocation.json')
        result['native_java_upcalls']=True;result['all_native_frames']=False;result['native_entries_traced']=True;result['frame_overlay']=frame_reference
        result['required_provider_families']=['normal-constructors-v1'];result['constructor_records']=len(metadata['records']);result['exception_wrapping_complete']=False
        result['kernel_sources']={'native/providers/'+n:S.digest(S.ROOT/'native/providers'/n)['sha256'] for n in C.KERNELS}
    elif metadata_kind=='constructors':
        S.write(output/'constructors.json',metadata);result['constructor_metadata']=S.artifact(output/'constructors.json')
        result['native_java_upcalls']=True;result['all_native_frames']=False
        result['constructor_records']=len(metadata['records']);result['unavailable_constructor_records']=sum(r['unavailable'] for r in metadata['records'])
    elif metadata_kind=='flags':
        S.write(output/'class-flags.json',metadata);result['class_flags_metadata']=S.artifact(output/'class-flags.json')
        result['provided_types']=metadata['provided_types'];result['type_capacity']=metadata['type_capacity']
    S.write(output/'prepared.json',result);return result


def seal(output,assembler):
    output=Path(output).resolve();m=S.read(output/'prepared.json')
    S.check(m['tool_sources']==S.tools_identity(),'Provider tool changed during build')
    identity,_,_=S.base(m['base']['batch'],m['base']['plan']);S.check(identity==m['base'],'Provider base changed during build')
    S.checked(m['assembly'])
    services=S.module('seal_framed_service_metadata','framed-runtime-service.py')
    if m['family'] in services.FAMILIES:S.checked(m[services.FAMILIES[m['family']][1]+'_metadata'])
    if 'constructor_metadata' in m:S.checked(m['constructor_metadata'])
    if 'class_flags_metadata' in m:S.checked(m['class_flags_metadata'])
    if 'constructor_invocation_metadata' in m:S.checked(m['constructor_invocation_metadata'])
    if 'file_bootstrap_metadata' in m:S.checked(m['file_bootstrap_metadata'])
    if 'scoped_memory_metadata' in m:S.checked(m['scoped_memory_metadata'])
    if 'normal_throwable_metadata' in m:S.checked(m['normal_throwable_metadata'])
    if 'signal_lookup_metadata' in m:S.checked(m['signal_lookup_metadata'])
    if 'normal_thread_metadata' in m:S.checked(m['normal_thread_metadata'])
    if 'normal_access_metadata' in m:S.checked(m['normal_access_metadata'])
    if 'normal_thread_start_metadata' in m:S.checked(m['normal_thread_start_metadata'])
    if 'normal_thread_priority_metadata' in m:S.checked(m['normal_thread_priority_metadata'])
    if 'normal_signal_control_metadata' in m:S.checked(m['normal_signal_control_metadata'])
    if 'windows_startup_metadata' in m:S.checked(m['windows_startup_metadata'])
    if 'finalization_policy_metadata' in m:S.checked(m['finalization_policy_metadata'])
    if 'object_notification_metadata' in m:S.checked(m['object_notification_metadata'])
    if 'unsafe_class_init_metadata' in m:S.checked(m['unsafe_class_init_metadata'])
    m['object']=S.artifact(output/'provider.obj');m['assembler']=dict(path=str(Path(assembler).resolve()),digest=S.digest(assembler))
    m['assembled']=True;S.write(output/'provider.json',m);return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path);p.add_argument('--plan',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--family',default='cds-no-archive-v1');p.add_argument('--seal',action='store_true');p.add_argument('--assembler',type=Path);p.add_argument('--frame-overlay',type=Path)
    a=p.parse_args();m=seal(a.output,a.assembler) if a.seal else prepare(a.batch,a.plan,a.output,a.family,a.frame_overlay)
    print(json.dumps(dict(provider=str(a.output/'provider.json'),family=m['family'],native_methods=m['native_methods'],java_codegen_rerun=False,game_started=False)))
