"""Relink one sealed native prefix with an equivalent split COFF bundle and run it.

This offline candidate does not invoke current provider/source verifiers or
modify any sealed input. Its proof is a historical same-source prefix replay,
never complete System initialization or a Minecraft/world launch.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'
RUNTIME_SHA='572f28fac6ccf9851eca128929698c8d60c55d8b102972041f7f89a8dba05a26'


def check(value,message):
    if not value:raise ValueError(message)


def read(path):return json.loads(Path(path).read_bytes())


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),size=path.stat().st_size,sha256=sha)


def checked(record):
    current=artifact(record['path']);expected=record.get('digest',record)
    check(all(current[k]==expected[k] for k in ('size','sha256')),'Sealed artifact changed: '+record['path'])
    return Path(current['path'])


def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def patch_response(raw,original,objects,target):
    result=[];replaced=out=0
    for line in raw.splitlines(keepends=True):
        content=line.rstrip(b'\r\n');ending=line[len(content):]
        check(ending,'Link response must contain complete lines')
        if content.startswith(b'/OUT:'):
            out+=1;result.append(('/OUT:"'+str(target)+'"').encode()+ending)
        elif content==('"'+str(original)+'"').encode():
            replaced+=1;result.extend(('"'+str(p)+'"').encode()+ending for p in objects)
        else:result.append(line)
    check(replaced==out==1,'Expected exactly one original closure object and one OUT directive')
    return b''.join(result)


def response_files(raw):
    result=[]
    for line in raw.decode('utf-8').splitlines():
        if not line.startswith('"'):continue
        check(line.endswith('"'),'Unsupported original link response quoting')
        path=Path(line[1:-1]).resolve()
        check(path.suffix.lower() in ('.obj','.lib') and path.is_file(),'Unexpected native link input')
        result.append(path)
    check(len(result)==len(set(result)),'Duplicate native link input')
    return result


def pe(path):
    raw=Path(path).read_bytes();check(raw[:2]==b'MZ','Native image has no DOS header')
    offset=struct.unpack_from('<I',raw,60)[0];check(raw[offset:offset+4]==b'PE\0\0','Invalid PE header')
    machine,count,_,_,_,optional_bytes,characteristics=struct.unpack_from('<HHIIIHH',raw,offset+4)
    optional=offset+24
    check(machine==0x8664 and optional_bytes>=240 and struct.unpack_from('<H',raw,optional)[0]==0x20b,
          'Expected a native AMD64 PE32+ image')
    sections=[]
    for i in range(count):
        at=optional+optional_bytes+i*40
        name=raw[at:at+8].rstrip(b'\0').decode();vsize,rva,size,data=struct.unpack_from('<IIII',raw,at+8)
        flags=struct.unpack_from('<I',raw,at+36)[0]
        check(data+size<=len(raw),'PE section exceeds file bounds')
        sections.append((name,rva,vsize,size,data,flags))
    def at(rva,size=1):
        for _,base,_,length,data,_ in sections:
            if base<=rva and rva+size<=base+length:return data+rva-base
        raise ValueError('PE RVA is outside initialized section data')
    def string(rva):
        pos=at(rva);end=raw.find(b'\0',pos)
        check(end>=pos,'Unterminated PE string');return raw[pos:end].decode('ascii')
    imports=[];import_rva,import_size=struct.unpack_from('<II',raw,optional+120)
    if import_rva:
        check(import_size>=20,'Invalid import directory')
        for i in range(import_size//20):
            values=struct.unpack_from('<IIIII',raw,at(import_rva+i*20,20))
            if not any(values):break
            imports.append(string(values[3]).lower())
        else:raise ValueError('Unterminated import directory')
    export_rva,export_size=struct.unpack_from('<II',raw,optional+112);exports=[]
    if export_rva:
        d=at(export_rva,40);n=struct.unpack_from('<I',raw,d+24)[0];names=struct.unpack_from('<I',raw,d+32)[0]
        table=at(names,n*4)
        exports=[string(struct.unpack_from('<I',raw,table+i*4)[0]) for i in range(n)]
        check(len(exports)==len(set(exports)),'Duplicate PE export')
    exception_rva,exception_size=struct.unpack_from('<II',raw,optional+136)
    check(exception_size%12==0,'Invalid x64 runtime function table')
    previous=-1
    for i in range(exception_size//12):
        begin,end,unwind=struct.unpack_from('<III',raw,at(exception_rva+i*12,12))
        check(previous<begin<end and any(base<=begin<end<=base+length and flags&0x20000000
              for _,base,length,_,_,flags in sections),'Unsorted or non-executable runtime function range')
        at(unwind,4);previous=begin
    entry=struct.unpack_from('<I',raw,optional+16)[0]
    check(any(base<=entry<base+length and flags&0x20000000 for _,base,length,_,_,flags in sections),
          'Process entry is outside executable code')
    return dict(machine=machine,subsystem=struct.unpack_from('<H',raw,optional+68)[0],
        dll_characteristics=struct.unpack_from('<H',raw,optional+70)[0],
        executable=bool(characteristics&2),is_dll=bool(characteristics&0x2000),entry_present=bool(entry),
        imports=sorted(imports),exports=sorted(exports),runtime_function_rows=exception_size//12)


def report(raw):
    check(len(raw)==448,'Expected the complete 448-byte native report')
    u=lambda n:struct.unpack_from('<I',raw,n)[0]
    q=lambda n:struct.unpack_from('<Q',raw,n)[0]
    check(u(0)==0x52454d56 and u(4)==11,'Expected ABI11 assembly report')
    return dict(abi=11,bytes=448,exit_code=u(80),kind=u(12),pc=u(16),method=u(20),depth=u(24),
        record_state=u(28),first_row=u(32),main_source_row=u(312),bootstrap_state=u(52),
        held=q(40),registry_lock=u(48),cleanup=u(64),cleanup_error=u(68),live_objects=q(56),
        phase1_called=u(76),phase1_returned=u(272),phase2_called=u(276),phase2_returned=u(280),
        VM_level_before=u(288),VM_level_after=u(292),main_kind=u(296),main_pc=u(300),
        main_method=u(304),main_depth=u(308),context_map_drops=u(316),
        source_run_returns=q(120),source_exit_returns=q(128),worker_failure=u(136),
        worker_context=[q(n) for n in (240,248,256,264)],priority_applications=q(208),
        worker_starts=q(216),run_dispatch_calls=q(224),worker_records_reaped=q(232),
        signal=dict(opened=u(144),closed=u(148),attached=q(152),exited=q(168),detached=q(176),failure=u(184),native_error=u(200)),
        reference=dict(opened=u(320),stopped=u(324),closed=u(328),boundary_error=u(332),
            waits=q(336),normal=q(344),tokens_issued=q(352),tokens_consumed=q(360),
            monitor_releases=q(368),owner_error=u(376),final_state=u(380)),
        object_wait=dict(opened=u(400),stopped=u(404),closed=u(408),owner_error=u(412),
            waits=q(416),interrupts=q(424),cancellations=q(432),normal=q(440)))


def validate_prefix(observed,baseline,exit_code,fault):
    check(exit_code==observed['exit_code']==86 and observed['kind']==observed['main_kind']==45057,
          'Expected the sealed diagnostic source prefix, not normal game completion')
    check(observed['phase1_called']==observed['phase1_returned']==observed['phase2_called']==1 and
          observed['phase2_returned']==0 and observed['VM_level_before']==observed['VM_level_after']==1,
          'Original System phase prefix changed')
    check(observed['bootstrap_state']==2 and observed['record_state']==2 and observed['cleanup']==7 and
          observed['cleanup_error']==observed['held']==observed['registry_lock']==observed['worker_failure']==0 and
          observed['worker_context']==[0,0,0,0],'Bootstrap, worker or cleanup invariant changed')
    check(observed['source_exit_returns']==observed['worker_starts']==observed['run_dispatch_calls']==
          observed['worker_records_reaped']==observed['priority_applications']==2 and observed['source_run_returns']==0,
          'Original background thread lifecycle changed')
    check(fault['method']['id']==41548 and fault['symbol']=='boom_m41548' and
          observed['main_source_row']==fault['id'],'Expected original ClassLoader.registerNatives source stop')
    for key in observed:
        if key=='live_objects':continue
        check(observed[key]==baseline[key],'Sealed native report field differs: '+key)
    ref=observed['reference'];wait=observed['object_wait'];signal=observed['signal']
    check(ref['opened']==ref['stopped']==ref['closed']==1 and ref['final_state']==6 and
          ref['boundary_error']==ref['owner_error']==0 and ref['tokens_issued']==ref['tokens_consumed'],
          'Reference wait domain did not close normally')
    check(wait['opened']==wait['stopped']==wait['closed']==1 and wait['owner_error']==0,
          'Object wait domain did not close normally')
    check(signal['opened']==signal['closed']==signal['attached']==signal['exited']==signal['detached']==1 and
          signal['failure']==signal['native_error']==0,'Signal worker did not close normally')


def run(baseline,candidate,output):
    baseline=Path(baseline).resolve();candidate=Path(candidate).resolve();output=Path(output).resolve()
    check(baseline.is_relative_to(ART) and candidate.is_relative_to(ART) and output.is_relative_to(ART) and not output.exists(),
          'A fresh project-owned native probe directory is required')
    output.mkdir(parents=True);started=time.monotonic();own=artifact(Path(__file__))
    snapshots={}
    def remember(path):
        record=artifact(path);old=snapshots.setdefault(record['path'],record)
        check(old==record,'An input changed while capturing the sealed snapshot');return record
    try:
        native=read(baseline/'vm-entry.json');native_proof=read(baseline/'verification.json')
        previous=read(baseline/'execution.json');previous_raw=(baseline/'vm-entry-status.bin').read_bytes()
        check(native_proof['verified'] and not native_proof['managed_execution_host'] and not native_proof['game_started'] and
              native_proof['source_manifest_sha256']==artifact(baseline/'vm-entry.json')['sha256'] and
              native_proof['executable_sha256']==artifact(baseline/'boom-vm-entry.exe')['sha256'] and
              previous['source_verification_sha256']==artifact(baseline/'verification.json')['sha256'] and
              previous['native_report_sha256']==hashlib.sha256(previous_raw).hexdigest(),'Original native proof/report differs')
        old_report=report(previous_raw);validate_prefix(old_report,old_report,previous['native_process_exit_code'],previous['fault'])
        for name in ('vm-entry.json','verification.json','execution.json','vm-entry-status.bin','vm-entry.asm','vm-entry.obj','link.rsp','boom-vm-entry.exe'):
            remember(baseline/name)
        manifest=read(candidate/'assembled.json');proof=read(candidate/'equivalence.json')
        check(proof['verified'] and proof['source_byte_preservation_independently_checked'] and
              proof['manifest']==artifact(candidate/'assembled.json'),'Candidate equivalence proof differs')
        for name in ('assembled.json','equivalence.json'):remember(candidate/name)
        checked(manifest['candidate_script']);remember(manifest['candidate_script']['path'])
        frozen=Path(native['baseline_directory']).resolve()
        check(Path(manifest['source']['path']).parent==frozen and
              native['accepted_source_verification_sha256']==artifact(frozen/'selection-verification.json')['sha256'],
              'Candidate and native owner refer to different sealed source selections')
        for record in proof['inputs'].values():checked(record);remember(record['path'])
        remember(frozen/'diagnostic.json')
        objects=[]
        for unit in manifest['units']:
            checked(unit['assembly']);checked(unit['object']);remember(unit['assembly']['path']);remember(unit['object']['path'])
            objects.append(Path(unit['object']['path']).resolve())
        check(len(objects)==45,'This native prefix replay expects the accepted 45-object candidate')
        old_object=Path(manifest['monolithic_object']['path']).resolve();checked(native['link_response'])
        raw=(baseline/'link.rsp').read_bytes();original_files=response_files(raw)
        history={Path(r['path']).resolve():r for r in native['inputs']+native['reassembled_objects']}
        for path in original_files:
            check(path in history,'Original linker input is absent from the sealed native snapshot: '+str(path))
            checked(history[path]);remember(path)
        linker=checked(native['tools']['linker']);remember(linker)
        target=output/'boom-vm-entry.exe';new_rsp=patch_response(raw,old_object,objects,target)
        check(response_files(new_rsp)==[p for original in original_files for p in (objects if original==old_object else [original])],
              'New link input sequence differs beyond the closure replacement')
        (output/'link.rsp').write_bytes(new_rsp)
        # The source response is retained separately; all unchanged lines are
        # still byte-identical to it, including flags, imports and exports.
        (output/'baseline-link.rsp').write_bytes(raw)
        runtime=checked(native['runtime']);check(artifact(runtime)['sha256']==RUNTIME_SHA,'Unexpected assembly runtime')
        remember(runtime);shutil.copyfile(runtime,output/'boom-runtime.dll')
        check(artifact(output/'boom-runtime.dll')['sha256']==RUNTIME_SHA,'Runtime copy differs')
        stage=dict(stage='linking',inputs=snapshots,source_equivalence=artifact(candidate/'equivalence.json'),
            baseline= str(baseline),candidate=str(candidate),response=artifact(output/'link.rsp'),
            original_object=str(old_object),replacement_objects=[str(p) for p in objects],
            only_link_changes=['closure_object_replaced_by_45_proved_objects','output_path'],probe_script=own)
        write(output/'link-snapshot.json',stage)
        link_start=time.monotonic()
        with (output/'link.log').open('xb') as log:
            result=subprocess.run([str(linker),'@'+str(output/'link.rsp')],stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        check(result.returncode==0,'Independent split native link failed; inspect link.log')
        linked_seconds=time.monotonic()-link_start
        old_pe=pe(baseline/'boom-vm-entry.exe');new_pe=pe(target)
        check(old_pe==new_pe and new_pe['subsystem']==3 and new_pe['executable'] and not new_pe['is_dll'] and
              new_pe['dll_characteristics']&0x160==0x160,'Native PE exports/imports/security/unwind coverage changed')
        pe_summary={k:v for k,v in new_pe.items() if k!='exports'}
        pe_summary.update(export_count=len(new_pe['exports']),export_names_sha256=hashlib.sha256('\n'.join(new_pe['exports']).encode()).hexdigest())
        write(output/'pe-verification.json',dict(verified=True,scope='same_exports_imports_AMD64_entry_flags_and_sorted_unwind_ranges',
            baseline_image=artifact(baseline/'boom-vm-entry.exe'),candidate_image=artifact(target),properties=pe_summary))
        print(json.dumps(dict(stage='linked',seconds=round(linked_seconds,3),image=str(target))),flush=True)
        with (output/'process.out.log').open('xb') as out,(output/'process.err.log').open('xb') as err:
            process_start=time.monotonic()
            result=subprocess.run([str(target)],cwd=output,stdout=out,stderr=err,timeout=45,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        process_seconds=time.monotonic()-process_start
        validation_start=time.monotonic()
        raw_report=(output/'vm-entry-status.bin').read_bytes();observed=report(raw_report)
        validate_prefix(observed,old_report,result.returncode,previous['fault'])
        check((output/'link.rsp').read_bytes()==new_rsp and artifact(output/'boom-runtime.dll')['sha256']==RUNTIME_SHA,
              'Execution changed its sealed response/runtime')
        for record in snapshots.values():checked(record)
        check(artifact(Path(__file__))==own,'Native prefix probe changed during execution')
        receipt=dict(schema=1,verified=True,scope='same_source_22_input_native_assembly_prefix_after_split_COFF_link',
            source_equivalence=artifact(candidate/'equivalence.json'),baseline_native_verification=artifact(baseline/'verification.json'),
            baseline_execution=artifact(baseline/'execution.json'),link_snapshot=artifact(output/'link-snapshot.json'),
            link_response=artifact(output/'link.rsp'),image=artifact(target),runtime=artifact(output/'boom-runtime.dll'),
            pe_verification=artifact(output/'pe-verification.json'),report=artifact(output/'vm-entry-status.bin'),
            native_process_exit_code=result.returncode,observations=observed,fault=previous['fault'],
            binary_report_equal_to_baseline=raw_report==previous_raw,
            link_seconds=round(linked_seconds,6),process_seconds=round(process_seconds,6),
            post_execution_validation_seconds=round(time.monotonic()-validation_start,6),
            total_seconds=round(time.monotonic()-started,6),original_inputs_unchanged=True,
            current_provider_verifier_invoked=False,linked=True,executed=True,full_VM_bootstrap=False,
            completed_requested_entries=False,game_started=False,world_created=False)
        write(output/'execution.json',receipt)
        print(json.dumps({k:v for k,v in receipt.items() if k not in ('fault','observations')}),flush=True)
    except Exception as error:
        write(output/'failure.json',dict(failed=True,error_type=type(error).__name__,error=str(error),
            total_seconds=round(time.monotonic()-started,6),game_started=False,world_created=False))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-native',type=Path,required=True);parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);options=parser.parse_args()
    run(options.baseline_native,options.candidate,options.output)
