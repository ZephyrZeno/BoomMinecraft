"""Decode exact native process reports; no guest execution or success inference."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'
MAGIC=0x52454d56
SOURCE_STOP=45057


def check(value,message):
    if not value:raise ValueError(message)


def report_layout(manifest):
    model=manifest['binding_model'];phase2=bool(manifest.get('system_phase2'));phase3=bool(manifest.get('system_phase3'))
    for key,value in (('system_phase2',phase2),('system_phase3',phase3)):
        if key in model:check(bool(model[key])==value,'Manifest/model '+key+' request differs')
    check(not phase3 or phase2,'System phase3 requires phase2')
    roots=bool(model.get('provider_native_root_spans'))
    check(not (model.get('unsafe_park') or model.get('file_input')) or roots,'Native owner metadata requires selected root spans')
    if phase3:shape=544,13
    elif roots:shape=512,12
    elif model.get('object_wait'):shape=448,11
    elif model.get('winnt_filesystem'):shape=400,10
    elif model.get('reference_processing'):shape=384,9
    elif model.get('phase2_context_rows'):shape=320,8
    elif phase2:shape=312,7
    else:shape=(272,6) if manifest.get('signal_control') or manifest.get('start_child') else (112,2)
    for key,value in zip(('execution_report_bytes','execution_report_abi'),shape):
        if key in manifest:check(type(manifest[key]) is int and manifest[key]==value,'Sealed execution report layout differs')
    return shape


def decode(raw,manifest,exit_code,diagnostics=None,*,filesystem_metadata=None,source_verification_sha256='',observe_source_admissions=False):
    length,abi=report_layout(manifest);model=manifest['binding_model']
    check(len(raw)==length and struct.unpack_from('<II',raw)==(MAGIC,abi),'Native process status ABI differs')
    def u(at):return struct.unpack_from('<I',raw,at)[0]
    def q(at):return struct.unpack_from('<Q',raw,at)[0]
    def boolean(at,name):
        value=u(at);check(value in (0,1),'Invalid boolean '+name);return bool(value)
    def empty(start,end,name):check(not any(raw[start:end]),'Absent '+name+' report fields are nonzero')
    check(exit_code==u(80) and exit_code in (0,70,86),'Native process exit/status differ')
    kind,state,row,boot,cleanup=u(12),u(28),u(32),u(52),u(64)
    check(state in (0,2) and u(68)==0 and u(48)==0,'Native VM cleanup/protocol failure')
    check(cleanup<=7,'Invalid native cleanup flags')
    entry=boolean(72,'entry returned');phase1_called=boolean(76,'phase1 called');child_ctor=boolean(84,'child constructor')
    rows={}
    if diagnostics is not None:
        for record in diagnostics['rows']:
            check(type(record['id']) is int and record['id'] not in rows,'Duplicate/invalid source diagnostic row');rows[record['id']]=record
    first_fault=None
    if state==2:
        check(row in rows,'Native process stopped at an unknown source row');first_fault=rows[row]
    start=bool(manifest.get('start_child'));signal=bool(manifest.get('signal_control'))
    thread_started=start and boolean(112,'child started');thread_reaped=start and boolean(116,'child reaped')
    thread_ran=start and q(120)==1;thread_exited=start and q(128)==1
    worker_failure=u(136) if start or signal else 0
    check(worker_failure in (0,2),'Native worker failure publication is incomplete')
    worker_context=dict(kind=u(240),pc=u(244),method=u(248),depth=u(252),pending_Throwable_present=q(256)!=0) if worker_failure==2 else None
    signal_open=signal and boolean(144,'signal opened');signal_close=signal and boolean(148,'signal closed')
    signal_attached=signal and q(152)==1;signal_exit=signal and q(168)==1;signal_detached=signal and q(176)==1
    signal_failure=u(184) if signal else 0
    completed=exit_code==0 and kind==0 and state==0 and boot==2 and entry and cleanup==7
    completed=completed and (not manifest.get('construct_child') or child_ctor)
    completed=completed and (not start or (thread_started and thread_reaped and thread_ran and thread_exited and worker_failure==0))
    completed=completed and (not signal or (signal_open and signal_close and signal_attached and signal_exit and signal_detached and signal_failure==0))
    reference=None
    if model.get('reference_processing'):
        reference=dict(opened=u(320),stopped=u(324),closed=u(328),boundary_error=u(332),waits_entered=q(336),normal_wait_returns=q(344),
            stop_tokens_issued=q(352),stop_tokens_consumed=q(360),owned_monitor_acquisitions_released=q(368),owner_error=u(376),final_pool_state=u(380))
        check(0<=reference['closed']<=reference['stopped']<=reference['opened']<=1 and reference['normal_wait_returns']<=reference['waits_entered'] and
            reference['stop_tokens_consumed']<=reference['stop_tokens_issued'],'Inconsistent original Reference worker observations')
        check(not reference['closed'] or (reference['final_pool_state']==6 and reference['stop_tokens_issued']==reference['stop_tokens_consumed']),
            'Reference transport closed with live stop tokens')
        completed=completed and reference['closed']==1 and reference['owner_error']==reference['boundary_error']==0
    elif length>=384:empty(320,384,'Reference')
    waiting=None
    if model.get('object_wait'):
        opened,stopped,closed,owner_error=(u(at) for at in (400,404,408,412))
        calls,interrupts,cancels,normal=(q(at) for at in (416,424,432,440))
        check(0<=closed<=stopped<=opened<=1 and interrupts+cancels+normal<=calls,'Source Object.wait0 lifecycle or result counters differ')
        waiting=dict(opened=bool(opened),stop_requested=bool(stopped),closed=bool(closed),owner_error=owner_error,
            source_wait_calls=calls,source_InterruptedException_objects=interrupts,issued_VM_cancellations=cancels,normal_wait_returns=normal)
        completed=completed and opened==stopped==closed==1 and owner_error==0
    elif length>=448:empty(400,448,'Object.wait')
    filesystem=None
    if model.get('winnt_filesystem'):
        check(filesystem_metadata is not None,'Original filesystem source metadata required')
        ready,bound,optional=u(384),u(388),u(392)
        check(ready in (0,2) and bound==int(ready==2) and optional<=bound and u(396)==filesystem_metadata['file_class'],
            'Native File.path registration differs from the source contract')
        filesystem=dict(registration_state=ready,original_File_path_id_cached=bool(bound),optional_final_path_API_available=bool(optional),
            original_File_class_id=u(396),original_path_offset=filesystem_metadata['field']['offset'])
    elif length>=400:empty(384,400,'Windows filesystem')
    phase=None;phase3=None;phase_rejected=False
    if manifest.get('system_phase2'):
        p1=boolean(272,'phase1 returned');called=boolean(276,'phase2 called');returned=boolean(280,'phase2 returned')
        code=struct.unpack_from('<i',raw,284)[0] if returned else None;before,after=u(288),u(292)
        main=dict(kind=u(296),pc=u(300),method=u(304),depth=u(308))
        check(not p1 or phase1_called,'Phase1 return has no original call')
        check(not called or (p1 and before==1),'Inconsistent main-thread System phase2 call')
        check(not returned or called,'Phase2 return has no original call')
        if not manifest.get('system_phase3'):check(not returned or main['kind']==0,'Returned phase2 has an exceptional main Context')
        success=returned and code==0 and after==2
        phase=dict(phase1_returned=p1,phase2_called=called,phase2_returned=returned,phase2_result=code,
            VM_level_before=before,VM_level_after=after,main_kind=main['kind'],main_pc=main['pc'],main_method=main['method'],main_depth=main['depth'])
        phase_success=success
        if manifest.get('system_phase3'):
            c3=boolean(512,'phase3 called');r3=boolean(516,'phase3 returned');b3,a3=u(520),u(524)
            ctx3=dict(kind=u(528),pc=u(532),method=u(536),depth=u(540))
            check(not c3 or (success and b3==2),'Phase3 call requires completed phase2 and VM level2')
            check(not r3 or (c3 and ctx3['kind']==0),'Phase3 return has no successful original call')
            if c3:check(ctx3==main,'Phase3 Context differs from latest main Context')
            else:
                check(not r3 and not any(ctx3.values()),'Uncalled phase3 published a return or Context')
                check(not returned or main['kind']==0,'Exceptional latest main Context has no phase3 call')
            phase_success=success and c3 and r3 and b3==2 and a3==4 and ctx3['kind']==0 and ctx3['depth']==0
            phase3=dict(called=c3,returned=r3,VM_level_before=b3,VM_level_after=a3,**ctx3,completed=phase_success)
        check(entry==phase_success,'Main-thread return differs from requested original System phase outcome')
        phase_rejected=p1 and main['kind']==0 and not phase_success
        if phase3 and phase3['called'] and not phase3['returned'] and phase3['kind']!=0 and state==0:
            phase_rejected=True
        completed=completed and phase_success
    owners=None;roots=bool(model.get('provider_native_root_spans'))
    if length>=512:
        if not roots:empty(448,512,'native owner')
        else:
            opened,closed,owner_error,status,active,waiters=(u(at) for at in (448,452,456,460,464,468))
            gate,handles,buffers,io_roots,snapshot=(q(at) for at in (472,480,488,496,504))
            park=bool(model.get('unsafe_park'));file_input=bool(model.get('file_input'))
            check(status in (0,0xffffffff),'Native root snapshot failed')
            check(snapshot<=1048576,'Native ASM root snapshot exceeds its private vector')
            if park:
                check(0<=closed<=opened<=1 and owner_error==0,'Native Parker lifecycle/owner error differs')
                check(active==waiters==gate==0,'Native Parker retains active owners, waiters or gate roots')
                check(opened==closed,'Native Parker teardown did not close its opened boundary')
            else:check(opened==closed==owner_error==active==waiters==gate==0,'Absent Parker metadata has nonzero observations')
            if file_input:check(handles==buffers==io_roots==0,'Native file input retains handles, buffers or owner roots')
            else:check(handles==buffers==io_roots==0,'Absent file-input metadata has nonzero observations')
            if status==0xffffffff:check(snapshot==0,'Uncalled native ASM snapshot published roots')
            completed=completed and status==0 and (not park or opened==closed==1)
            owners=dict(ASM_snapshot_status=status,ASM_snapshot_called=status!=0xffffffff,ASM_root_snapshot_nonnull=snapshot,
                snapshot_vector_bytes=8*1048576,automatic_collection_executed=False,
                park_metadata_present=park,Park_opened=opened,Park_closed=closed,owner_error=owner_error,Park_active=active,Park_waiters=waiters,
                Park_gate_roots_nonnull=gate,file_input_metadata_present=file_input,IO_live_handles=handles,IO_owned_buffers=buffers,IO_owner_roots_nonnull=io_roots)
    check(completed or (exit_code==86 and kind==SOURCE_STOP and state==2) or (phase_rejected and exit_code==70),
        'Native process failed without an identified source stop or original System phase failure')
    result=dict(scope='native_assembly_process_original_VM_bootstrap_prefix_only',diagnostic_only=True,
        completed_requested_prefix=bool(completed),completed_requested_entries=bool(completed),native_process_exit_code=exit_code,
        context_kind=kind,context_pc=u(16),context_method=u(20),context_depth=u(24),record_state=state,first_row=row,
        main_requested_entry_returned_normally=entry,bootstrap_state=boot,original_primordial_constructors_completed=boot==2,
        System_phase1_called=phase1_called,System_phase1_completed=phase['phase1_returned'] if phase else bool(manifest.get('include_System_phase1') and completed),
        original_child_Thread_constructor_completed=child_ctor,observed_child_Java_id=q(88),observed_next_Java_id=q(96),observed_main_Java_id=q(104),
        original_ThreadIdentifiers_next_observed=bool(manifest.get('construct_child') and not signal and q(88)==2 and q(96)==3),
        live_objects=q(56),held_monitor_acquisitions_at_stop=q(40),monitor_registry_lock_at_stop=u(48),cleanup_flags=cleanup,
        heap_cleanup_completed=bool(cleanup&1),registry_cleanup_completed=bool(cleanup&2),Java_frame_cleanup_completed=bool(cleanup&4),owned_process_teardown_required=not bool(cleanup&1),
        fault=first_fault,native_report_sha256=hashlib.sha256(raw).hexdigest(),source_verification_sha256=source_verification_sha256,
        compiler_generated_VM_binding_pool=True,VM_binding_configuration_fixture=False,managed_execution_host=False,jvm_fallback=False,
        Java_Thread_start_or_exit_executed=bool(thread_started or thread_exited),original_Java_Thread_start_completed=bool(thread_started),
        original_Java_Thread_run_completed=bool(thread_ran),original_Java_Thread_exit_completed=bool(thread_exited),native_child_record_reaped=bool(thread_reaped),
        worker_failure_state=worker_failure,worker_failure_context=worker_context,
        observed_original_worker_run_completions=q(120) if start or signal else 0,observed_original_worker_exit_completions=q(128) if start or signal else 0,
        observed_source_start_priority_applications=q(208) if start or signal else 0,observed_original_worker_starts=q(216) if start or signal else 0,
        observed_original_worker_run_dispatch_calls=q(224) if start or signal else 0,observed_worker_records_reaped=q(232) if start or signal else 0,
        nonnull_Runnable_task_verified=bool(manifest.get('child_task_main_thread') and completed),Runnable_task_kind='original_main_Thread_as_Runnable' if manifest.get('child_task_main_thread') else None,
        normal_signal_transport_opened=bool(signal_open),normal_signal_transport_closed=bool(signal_close),normal_signal_dispatcher_attached=bool(signal_attached),
        original_signal_dispatcher_Thread_exit_completed=bool(signal_exit),normal_signal_dispatcher_detached=bool(signal_detached),signal_worker_failure_state=signal_failure,
        observed_signal_dispatcher_Java_id=q(192) if signal else 0,original_Signal_dispatch_entered_count=q(160) if signal else 0,
        signal_transport_native_error=u(200) if signal else 0,VM_BREAK_thread_dump_complete=False,full_VM_bootstrap=False,game_started=False,world_created=False,
        execution_report_bytes=length,execution_report_abi=abi)
    if phase:result['main_System_phases']=phase
    if phase3:result['System_phase3']=phase3
    if owners:result['native_owner_snapshot']=owners
    if reference:result['reference_processing']=reference
    if waiting:result['object_wait']=waiting
    if filesystem:result['windows_filesystem']=filesystem
    if model.get('phase2_context_rows'):
        main_row=u(312);result.update(first_process_fault=first_fault,main_source_row=main_row,context_row_map_drops=u(316))
        if main_row:
            check(phase is not None and phase['main_kind']==SOURCE_STOP and state==2,'Main thread source row has no diagnostic stop')
            check(main_row in rows,'Unknown main-thread source row');result.update(fault=rows[main_row],fault_source='main_thread')
        elif first_fault:result['fault_source']='first_process_stop'
        if observe_source_admissions:
            result['source_admission_rows']=list(dict.fromkeys(r['id'] for r in (result['fault'],first_fault) if r and r['category'] in (1,5)))
    return result


def artifact(path):
    path=Path(path).resolve();raw=path.read_bytes();return dict(path=str(path),digest=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))


def checked(record):
    actual=artifact(record['path']);check(all(record['digest'].get(k)==v for k,v in actual['digest'].items()),'Report dependency changed: '+record['path'])
    return Path(actual['path'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--exit-code',type=int,required=True);parser.add_argument('--accepted-verification-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--observe-source-admissions',action='store_true');args=parser.parse_args()
    manifest_file=args.manifest.resolve();report=args.report.resolve();output=args.output.resolve()
    check(all(p.is_relative_to(ART) for p in (manifest_file,report,output)) and not output.exists(),'Fresh project report decode output required')
    proof_file=manifest_file.with_name('verification.json');proof=json.loads(proof_file.read_bytes());manifest=json.loads(manifest_file.read_bytes())
    check(artifact(proof_file)['digest']['sha256']==args.accepted_verification_sha256 and proof.get('verified') is True and
        not any(proof.get(k) for k in ('managed_execution_host','full_VM_bootstrap','game_started')) and
        artifact(manifest_file)['digest']['sha256']==proof['source_manifest_sha256'],'Explicitly accepted native entry verification differs')
    records=manifest['inputs']+[manifest[k] for k in ('executable','runtime','assembly','link_response')]+manifest.get('reassembled_objects',[])
    for record in records:checked(record)
    diagnostic_file=Path(manifest['baseline_directory'])/'diagnostic.json'
    check(any(Path(r['path']).resolve()==diagnostic_file.resolve() for r in records),'Original diagnostic table is not a sealed input')
    diagnostics=json.loads(diagnostic_file.read_bytes());metadata=None
    filesystem=manifest['binding_model'].get('winnt_filesystem')
    if filesystem:metadata=json.loads(checked(filesystem['metadata']).read_bytes())
    raw=report.read_bytes();result=decode(raw,manifest,args.exit_code,diagnostics,filesystem_metadata=metadata,
        source_verification_sha256=args.accepted_verification_sha256,observe_source_admissions=args.observe_source_admissions)
    for record in records:checked(record)
    check(hashlib.sha256(report.read_bytes()).digest()==hashlib.sha256(raw).digest(),'Native report changed during decoding')
    result['report_decoder']=artifact(Path(__file__));output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
