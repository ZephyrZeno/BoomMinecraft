"""Owned development prefix with source-verified unregistered native candidates."""
import argparse
import hashlib
import importlib.util
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


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('native_canonical_probe_io','runtime-provider-source.py')


def checked(record):
    path=Path(record['path']).resolve();expected=record['digest'];actual=S.digest(path)
    S.check(set(expected)<={'size','sha1','sha256'} and all(actual[k]==expected[k] for k in ('size','sha256')),
            'Sealed prefix input changed: '+str(path))
    if 'sha1' in expected:
        with path.open('rb') as stream:S.check(hashlib.file_digest(stream,'sha1').hexdigest()==expected['sha1'],'Legacy SHA1 differs: '+str(path))
    return path


def remove_stops(raw,rows,context_rows,targets):
    target='boom_diagnostic_stop_context' if context_rows else 'boom_diagnostic_stop'
    newline=b'\r\n' if raw.count(b'\r\n')==raw.count(b'\n') else b'\n'
    S.check(newline==b'\r\n' or b'\r' not in raw,'Unsupported mixed diagnostic source line endings')
    spans=[]
    for row in rows:
        name=row['symbol']
        fragment=(f'PUBLIC {name}\n{name} PROC\n lea rdx,boom_diagnostic_row{row["id"]}\n'
                  f' lea r8,boom_diagnostic_pool\n jmp {target}\n{name} ENDP\n').encode().replace(b'\n',newline)
        S.check(raw.count(fragment)==1,'Expected one exact PUBLIC and complete fail-only PROC: '+name)
        begin=raw.index(fragment);spans.append((begin,begin+len(fragment),row,fragment))
    spans.sort();cursor=0;parts=[];proof=[]
    for begin,end,row,fragment in spans:
        S.check(cursor<=begin,'Overlapping native stop ranges')
        parts.append(raw[cursor:begin]);proof.append(dict(symbol=row['symbol'],row=row['id'],begin=begin,end=end,
            removed_sha256=hashlib.sha256(fragment).hexdigest(),preceding_unchanged_bytes=begin-cursor,
            preceding_unchanged_sha256=hashlib.sha256(raw[cursor:begin]).hexdigest()));cursor=end
    parts.append(raw[cursor:]);remaining=b''.join(parts)
    B=module('native_canonical_original_spans','batch-source.py')
    old,new=B.procedure_spans(raw),B.procedure_spans(remaining)
    S.check(set(old)-set(new)==targets and not set(new)-set(old),'Unexpected procedure removal/addition')
    hashes=hashlib.sha256()
    for name,(begin,end) in old.items():
        if name in targets:continue
        a,b=new[name];S.check(raw[begin:end]==remaining[a:b],'Non-target diagnostic procedure changed: '+name)
        hashes.update(name.encode()+b'\0'+hashlib.sha256(raw[begin:end]).digest())
    rowdata_end=raw.index(b'PUBLIC boom_diagnostic_stop'+newline)
    S.check(remaining[:rowdata_end]==raw[:rowdata_end],'Original diagnostic row data changed')
    return remaining,dict(only_removed_PUBLIC_and_complete_PROCs=proof,other_procedures=len(new),
        unchanged_procedure_inventory_sha256=hashes.hexdigest(),all_complement_source_bytes_preserved=True,
        original_rowdata_prefix_bytes=rowdata_end,original_rowdata_prefix_sha256=hashlib.sha256(raw[:rowdata_end]).hexdigest(),
        final_unchanged_bytes=len(raw)-cursor,final_unchanged_sha256=hashlib.sha256(raw[cursor:]).hexdigest(),
        original_bytes=len(raw),remaining_bytes=len(remaining),diagnostic_row_data_modified=False)


def entry_export(path,name):
    raw=Path(path).read_bytes();pe=struct.unpack_from('<I',raw,60)[0];optional=pe+24
    count=struct.unpack_from('<H',raw,pe+6)[0];section_start=optional+struct.unpack_from('<H',raw,pe+20)[0]
    regions=[]
    for i in range(count):
        at=section_start+i*40;rva,size,position=struct.unpack_from('<III',raw,at+12);regions.append((rva,size,position))
    def offset(rva,size):
        for base,length,position in regions:
            if base<=rva and rva+size<=base+length:return position+rva-base
        raise ValueError('PE export RVA outside raw section')
    export_rva,export_size=struct.unpack_from('<II',raw,optional+112);at=offset(export_rva,40)
    functions,names,addresses,strings,ordinals=struct.unpack_from('<IIIII',raw,at+20)
    found=[]
    for i in range(names):
        rva=struct.unpack_from('<I',raw,offset(strings+i*4,4))[0];begin=offset(rva,1);end=raw.find(b'\0',begin,begin+1024)
        S.check(end>=begin,'Unterminated PE export name')
        if raw[begin:end].decode('ascii')==name:
            ordinal=struct.unpack_from('<H',raw,offset(ordinals+i*2,2))[0];S.check(ordinal<functions,'Invalid entry export ordinal')
            address=struct.unpack_from('<I',raw,offset(addresses+ordinal*4,4))[0]
            S.check(not export_rva<=address<export_rva+export_size,'Process entry is a forwarded export');found.append(address)
    entry=struct.unpack_from('<I',raw,optional+16)[0]
    S.check(found==[entry] and entry!=0,'Native AddressOfEntryPoint is not the original process entry export')
    return entry


def conflicting_public_definitions(path,wanted):
    """Read actual retained COFF definitions without allocating its full symbol set."""
    raw=Path(path).read_bytes()
    S.check(len(raw)>=20,'Truncated retained COFF')
    machine,sections,_,offset,count,optional,_=struct.unpack_from('<HHIIIHH',raw)
    S.check(machine==0x8664 and optional==0 and offset>=20+40*sections and offset+18*count+4<=len(raw),
            'Invalid retained AMD64 COFF symbol table')
    strings=offset+18*count;length=struct.unpack_from('<I',raw,strings)[0]
    S.check(length>=4 and strings+length<=len(raw),'Invalid retained COFF string table')
    names={};short={name.encode():name for name in wanted if len(name)<=8}
    for name in wanted:
        encoded=name.encode()+b'\0';begin=strings+4
        while (at:=raw.find(encoded,begin,strings+length))>=0:
            if at==strings+4 or raw[at-1]==0:names[at-strings]=name
            begin=at+1
    found=set();i=0
    while i<count:
        name,_,section,_,storage,aux=struct.unpack_from('<8sIhHBB',raw,offset+i*18)
        S.check(section<=sections and i+1+aux<=count,'Invalid retained COFF symbol entry')
        if storage==2 and section>0:
            actual=names.get(struct.unpack_from('<I',name,4)[0]) if name[:4]==b'\0'*4 else short.get(name.rstrip(b'\0'))
            if actual is not None:found.add(actual)
        i+=1+aux
    return found


def validate_report(observed,code,rows,targets):
    S.check(code==observed['exit_code'] and code in (0,70,86),'Owned native exit/report differs')
    S.check(observed['phase1_called']==observed['phase1_returned']==observed['phase2_called']==1,
            'Original main thread did not complete Phase1 and enter Phase2')
    S.check(observed['bootstrap_state']==2 and observed['cleanup']==7 and
            observed['cleanup_error']==observed['held']==observed['registry_lock']==observed['worker_failure']==0 and
            observed['worker_context']==[0,0,0,0] and observed['context_map_drops']==0,
            'Original bootstrap/monitor/worker/cleanup invariant failed')
    S.check(observed['source_exit_returns']==observed['worker_starts']==observed['run_dispatch_calls']==
            observed['worker_records_reaped']==observed['priority_applications']==2 and observed['source_run_returns']==0,
            'Original two-worker lifecycle differs')
    ref,wait,signal=observed['reference'],observed['object_wait'],observed['signal']
    S.check(ref['opened']==ref['stopped']==ref['closed']==1 and ref['final_state']==6 and
            ref['owner_error']==ref['boundary_error']==0 and ref['tokens_issued']==ref['tokens_consumed'],
            'Original Reference domain did not close normally')
    S.check(wait['opened']==wait['stopped']==wait['closed']==1 and wait['owner_error']==0 and
            wait['interrupts']+wait['cancellations']+wait['normal']<=wait['waits'],'Original Object.wait domain did not close normally')
    S.check(signal['opened']==signal['closed']==signal['attached']==signal['exited']==signal['detached']==1 and
            signal['failure']==signal['native_error']==0,'Original Signal worker did not close normally')
    by_id={row['id']:row for row in rows}
    first=by_id.get(observed['first_row']) if observed['first_row'] else None
    main=by_id.get(observed['main_source_row']) if observed['main_source_row'] else None
    if observed['record_state']==2:S.check(first is not None,'Unknown original first-process row')
    else:S.check(observed['record_state']==0 and first is None,'Incomplete source diagnostic publication')
    if observed['main_source_row']:
        S.check(main is not None and observed['main_kind']==45057,'Unknown main source row or non-diagnostic main context')
    fault=main or first
    S.check(not fault or fault['symbol'] not in targets,'A replaced native fail-only stop was reached again')
    if code==86:S.check(observed['kind']==45057 and observed['record_state']==2 and fault is not None,'Unidentified native source stop')
    elif code==0:S.check(observed['phase2_returned']==1 and observed['VM_level_after']==2,'Normal exit without original Phase2 success')
    else:S.check(observed['main_kind']!=0,'Module rejection has no original main context')
    return first,main,fault


def run(state_file,baseline,candidate_specs,component_proofs,output):
    state_file,baseline,output=map(lambda p:Path(p).resolve(),(state_file,baseline,output))
    S.check(all(p.is_relative_to(ART) for p in (state_file,baseline,output)) and not output.exists(),
            'Use existing isolated inputs and a fresh development prefix directory')
    output.mkdir(parents=True);started=time.monotonic();records={}
    def remember(path):
        record=S.artifact(path);old=records.setdefault(record['path'],record)
        S.check(old==record,'Prefix input changed while sealing');return record
    def retain(record):checked(record);remember(record['path'])
    def nested(value):
        if isinstance(value,dict):
            if 'path' in value and isinstance(value.get('digest'),dict):retain(value);return
            for child in value.values():nested(child)
        elif isinstance(value,list):
            for child in value:nested(child)
    try:
        own=remember(__file__)
        for file in ('runtime-provider-source.py',
                     'batch-source.py','verify-batch-assembly.py','canonical-link-response.py',
                     'parallel-diagnostic-native-prefix-probe.py','vm-entry-source.py','Run-VmEntry.ps1'):
            remember(ROOT/'scripts'/file)
        state=S.read(state_file);remember(state_file)
        S.check(state['status']=='accepted' and state['provider_count']==26 and not state['full_VM_bootstrap'],
                'Scoped accepted 26 input state required')
        nested(state)
        native=S.read(baseline/'vm-entry.json');native_proof=S.read(checked(state['main_native_verification']))
        previous=S.read(checked(state['main_execution']));source=Path(native['baseline_directory'])
        S.check(Path(state['main_native_verification']['path']).parent==baseline and
                Path(state['main_execution']['path']).parent==baseline,'Accepted state refers to another native process')
        for file in ('vm-entry.json','verification.json','execution.json','vm-entry-status.bin','vm-entry.asm','vm-entry.obj','link.rsp','boom-vm-entry.exe'):
            remember(baseline/file)
        nested(native)
        S.check(native_proof['verified'] and native_proof['source_manifest_sha256']==S.digest(baseline/'vm-entry.json')['sha256'] and
                native_proof['executable_sha256']==S.digest(baseline/'boom-vm-entry.exe')['sha256'] and
                previous['source_verification_sha256']==S.digest(baseline/'verification.json')['sha256'],
                'Accepted baseline native proof/execution binding differs')
        source_proof=S.read(checked(state['main_source_verification']));closure=S.read(source/'closure.json')
        diagnostic=S.read(source/'diagnostic.json')
        for file in ('closure.json','diagnostic.json','selection-verification.json','initialization-closure.asm','diagnostic-stops.asm','assembly-provenance.json'):
            remember(source/file)
        S.check(source_proof['verified'] and native['accepted_source_verification_sha256']==S.digest(source/'selection-verification.json')['sha256'] and
                source_proof['closure_manifest_sha256']==S.digest(source/'closure.json')['sha256'] and
                source_proof['diagnostic_manifest_sha256']==S.digest(source/'diagnostic.json')['sha256'],
                'Sealed original full selection differs')
        units=source_proof['verified_assembly_objects']['units']
        S.check(native['reused_closure_objects']==[row['object'] for row in units] and
                [Path(row['path']).name for row in native['reassembled_objects']]==['vm-entry.obj'],
                'Baseline replaced a source part or reassembled original Java')
        for row in units:retain(row['assembly']);retain(row['object'])
        selected={row['class_id']:row for row in closure['selected_classes']}
        families={S.read(checked(p['manifest']))['family'] for i,p in enumerate(closure['runtime_provider_packs']) if i in closure['selected_runtime_provider_packs']}
        candidates=[];targets=set();definitions=set();foreign=set();methods={};tools=[]
        for index,specification in enumerate(candidate_specs):
            tool_name,path_text=specification.split(':',1)
            S.check(Path(tool_name).name==tool_name and tool_name.endswith('.py'),'Candidate verifier must name a project scripts file')
            candidate_file=Path(path_text).resolve();S.check(candidate_file.is_relative_to(ART),'Candidate escaped project artifacts')
            C=module('native_prefix_actual_candidate_'+str(index),tool_name);remember(ROOT/'scripts'/tool_name)
            proof=C.verify(candidate_file)
            S.check(proof==S.read(candidate_file.with_name('verification.json')),'Candidate independent proof differs')
            candidate=S.read(candidate_file);meta=candidate['metadata']['source'];nested(candidate)
            remember(candidate_file);remember(candidate_file.with_name('verification.json'))
            S.check(candidate['metadata']['base']['batch_summary']['digest']['sha256']==state['batch_summary_sha256'] and
                    candidate['metadata']['base']['base_verification']['digest']['sha256']==state['batch_verification_sha256'] and
                    candidate['metadata']['frame_overlay']['verification']['digest']['sha256']==state['frame_verification_sha256'],
                    'Candidate differs from accepted source/frame inputs')
            names={f"boom_m{row['method']}" for row in meta['methods']}
            S.check(names and len(names)==len(meta['methods']) and not targets&names,'Duplicate candidate native declaration')
            actual_defs,actual_imports=C.A.coff_symbols(checked(candidate['object']),C.C.FOREIGN)
            S.check(actual_defs==set(candidate['exports']) and actual_imports==set(candidate['imports']) and
                    not definitions&actual_defs,'Conflicting candidate PUBLIC definitions/imports')
            targets|=names;definitions|=actual_defs;foreign|=C.C.FOREIGN
            methods.update({f"boom_m{row['method']}":row for row in meta['methods']})
            S.check(set(meta['required_classes'])<=selected.keys(),'Candidate omitted original class states/failure roots')
            callbacks=list(meta['original_java'])
            callbacks.extend(row for key,row in meta.items() if key.startswith('original_Java_') and isinstance(row,dict) and 'code_sha256' in row)
            for row in callbacks:
                actual=closure['selected_methods'].get(str(row['method']))
                S.check(actual and actual['class_id']==row['class_id'] and actual['source_sha256']==row['class_sha256'] and
                        actual['code_sha256']==row['code_sha256'],'Candidate original Java callback is not actually selected')
            S.check(set(meta['required_provider_families'])<=families,'Candidate omitted a normal provider dependency')
            tools.append(C)
            candidates.append(dict(manifest=S.artifact(candidate_file),verification=S.artifact(candidate_file.with_name('verification.json')),
                tool=S.artifact(ROOT/'scripts'/tool_name),family=candidate['family'],source=meta,policy=candidate['metadata']['policy'],
                object=candidate['object'],exports=sorted(actual_defs),imports=sorted(actual_imports)))
        S.check(candidates and len(component_proofs)==len(candidates),'Every independent candidate needs its successful component execution proof')
        component_bindings=[];bound=set()
        for file in component_proofs:
            file=Path(file).resolve();S.check(file.is_relative_to(ART),'Component proof escaped artifacts')
            evidence=S.read(file);remember(file);S.check(evidence['verified'],'Candidate component did not pass')
            image_file=checked(evidence['images']);remember(image_file);configuration=S.read(image_file)
            bound_candidate=configuration.get('candidate',configuration.get('source_candidate'))
            S.check(bound_candidate is not None,'Successful component omitted its actual candidate binding')
            checked(bound_candidate)
            matches=[i for i,row in enumerate(candidates) if row['manifest']==bound_candidate]
            S.check(len(matches)==1 and matches[0] not in bound,'Component evidence belongs to another or duplicate candidate')
            bound.add(matches[0]);component_bindings.append(dict(candidate=bound_candidate,execution=S.artifact(file),images=S.artifact(image_file)))
        rows=[row for row in diagnostic['rows'] if row['symbol'] in targets]
        S.check(len(rows)==len(targets) and {r['symbol'] for r in rows}==targets and all(r['category']==2 and
                not r['method']['assembly_emitted'] and r['method']['code_sha256'] is None for r in rows),
                'Replacement is not exactly the requested native declaration fail-only stops')
        for row in rows:
            method=methods[row['symbol']]
            S.check(row['class_id']==method['class_id'] and row['source_sha256']==method['class_sha256'] and
                    row['method']['name']==method['name'] and row['method']['descriptor']==method['descriptor'],
                    'Candidate replaced another original declaration')
        [stop]=[row for row in units if Path(row['assembly']['path']).name=='diagnostic-stops.asm']
        original=checked(stop['assembly']).read_bytes();remaining,removal=remove_stops(original,rows,bool(closure.get('diagnostic_context_rows')),targets)
        asm,obj=output/'remaining-stops.asm',output/'remaining-stops.obj';asm.write_bytes(remaining);remember(asm)
        A=tools[0].A
        old_defs,old_imports=A.coff_symbols(checked(stop['object']))
        assembler=checked(native['tools']['assembler']);linker=checked(native['tools']['linker'])
        with (output/'remaining-stops-assembler.log').open('xb') as log:
            result=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(asm)],stdout=log,stderr=log)
        S.check(result.returncode==0,'Remaining fail-only stop assembly failed')
        remember(obj);remember(output/'remaining-stops-assembler.log')
        S.check(A.coff_symbols(obj)==(old_defs-targets,old_imports),'Remaining actual COFF changed definitions/imports beyond requested stops')
        candidate_objects=[checked(row['object']) for row in candidates]
        S.check(not definitions&(old_defs-targets),'Candidate conflicts with a remaining fail-only symbol')
        R=module('native_canonical_ordered_response','canonical-link-response.py')
        M=module('native_canonical_native_model','vm-entry-source.py')
        libraries=R.native_libraries(native['inputs'],Path(state['runtime'])/'boom-runtime.dll',winsock='normal-native-libraries-v1' in families)
        original_objects=[r['path'] for r in native['reused_closure_objects']+native['reassembled_objects']+native['original_source_objects']]
        exports=set(closure['exports'])|M.EXPORTS
        R.verify(baseline/'link.rsp',profile='native',output=baseline/'boom-vm-entry.exe',objects=original_objects,library_choices=[libraries],exports=exports)
        old_obj=Path(stop['object']['path']);S.check(original_objects.count(str(old_obj))==1,'Expected one baseline stop object')
        collision_checks=[]
        for path in original_objects:
            if Path(path)==old_obj:continue
            collision=conflicting_public_definitions(path,definitions)
            S.check(not collision,'Prototype PUBLIC collides with retained source COFF: '+str(sorted(collision)))
            collision_checks.append(dict(object=path,prototype_public_conflicts=[]))
        runtime_exports=module('native_prefix_runtime_exports','diagnostic-closure.py').pe_exports(checked(native['runtime']))
        S.check(not definitions&runtime_exports,'Prototype PUBLIC overrides an existing runtime export')
        objects=[p for old in original_objects for p in ([str(obj),*[str(p) for p in candidate_objects]] if Path(old)==old_obj else [old])]
        target=output/'boom-vm-entry.exe';lines=[*R.PREFIXES['native'],'/OUT:"'+str(target)+'"']
        lines+=['"'+str(p)+'"' for p in [*objects,*libraries]];lines+=['/EXPORT:'+s for s in sorted(exports)]
        rsp=output/'link.rsp';rsp.write_text('\n'.join(lines)+'\n',encoding='utf-8');remember(rsp)
        R.verify(rsp,profile='native',output=target,objects=objects,library_choices=[libraries],exports=exports)
        runtime=checked(native['runtime']);S.check(S.digest(runtime)['sha256']==RUNTIME_SHA,'Unexpected assembly runtime')
        shutil.copyfile(runtime,output/'boom-runtime.dll');remember(output/'boom-runtime.dll')
        S.write(output/'pre-link.json',dict(scope='unregistered_native_candidates_development_prefix',accepted26=remember(state_file),
            prototype_candidates=candidates,component_bindings=component_bindings,
            retained_COFF_public_conflict_checks=collision_checks,candidate_public_definitions=sorted(definitions),
            combined_actual_imports=sorted({name for row in candidates for name in row['imports']}-definitions),
            original_source_proof=state['main_source_verification'],old_parts=len(units),old_initialization_parts=len(units)-1,
            required_classes_actual=sorted({c for row in candidates for c in row['source']['required_classes']}),
            required_Java_actual=sorted({m for row in candidates for m in row['source']['required_java_methods']}),
            removal=removal,remaining_assembly=S.artifact(asm),remaining_object=S.artifact(obj),
            original_ordered_objects=original_objects,actual_ordered_objects=objects,libraries=[str(p) for p in libraries],
            exports_unchanged=True,full_selection_reverified=False,prototype_native_added=len(targets),inputs=list(records.values())))
        link_start=time.monotonic()
        with (output/'link.log').open('xb') as log:result=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=log)
        S.check(result.returncode==0,'Canonical development prefix link failed')
        remember(target);remember(output/'link.log')
        link_seconds=time.monotonic()-link_start
        P=module('native_canonical_owned_report','parallel-diagnostic-native-prefix-probe.py')
        old_pe,new_pe=P.pe(baseline/'boom-vm-entry.exe'),P.pe(target)
        S.check(new_pe['exports']==old_pe['exports'] and new_pe['machine']==old_pe['machine']==0x8664 and
                new_pe['subsystem']==3 and not new_pe['is_dll'] and new_pe['dll_characteristics']==old_pe['dll_characteristics'],
                'Development EXE changed exports, ABI, subsystem or native security flags')
        old_imports=M.pe(baseline/'boom-vm-entry.exe')['imports'];new_imports=M.pe(target)['imports']
        S.check(set(new_imports)==set(old_imports) and all(set(names)<=set(old_imports[dll])|foreign for dll,names in new_imports.items()) and
                all(set(names)<=set(new_imports[dll]) for dll,names in old_imports.items()),'Prototype introduced an unverified native import')
        S.check(foreign<=set().union(*(set(names) for names in new_imports.values())),
                'Expected prototype imports are absent from the actual PE')
        process_entry=entry_export(target,'boom_process_entry');entry_export(baseline/'boom-vm-entry.exe','boom_process_entry')
        S.write(output/'pe-verification.json',dict(verified=True,scope='actual_native_PE_entry_exports_dependencies_flags_and_unwind_ranges',
            image=S.artifact(target),AddressOfEntryPoint=process_entry,original_exports_unchanged=True,
            baseline_imports=old_imports,actual_imports=new_imports,prototype_allowed_foreign=sorted(foreign),
            original_runtime_imports=M.pe(runtime)['imports'],actual_runtime_imports=M.pe(output/'boom-runtime.dll')['imports'],
            exact_runtime_sha256=RUNTIME_SHA,actual_unwind_rows=new_pe['runtime_function_rows'],
            response=S.artifact(rsp),complete_canonical_response_verified=True))
        remember(output/'pe-verification.json');remember(output/'pre-link.json')
        for record in records.values():checked(record)
        R.verify(rsp,profile='native',output=target,objects=objects,library_choices=[libraries],exports=exports)
        print(json.dumps(dict(stage='linked',image=str(target),link_seconds=link_seconds)),flush=True)
        process_start=time.monotonic()
        with (output/'process.out.log').open('xb') as stdout,(output/'process.err.log').open('xb') as stderr:
            result=subprocess.run([str(target)],cwd=output,stdout=stdout,stderr=stderr,timeout=45,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        report_file=output/'vm-entry-status.bin';raw=report_file.read_bytes();observed=P.report(raw)
        for file in (report_file,output/'process.out.log',output/'process.err.log'):remember(file)
        first,main,fault=validate_report(observed,result.returncode,diagnostic['rows'],targets)
        u=lambda at:struct.unpack_from('<I',raw,at)[0]
        fs=dict(registration_state=u(384),File_path_id_cached=u(388),optional_final_path_API=u(392),File_class_id=u(396))
        S.check(fs['registration_state']==2 and fs['File_path_id_cached']==1 and fs['optional_final_path_API']<=1,
                'Original WinNT filesystem registration differs')
        for record in records.values():checked(record)
        S.check(S.artifact(__file__)==own and S.digest(output/'boom-runtime.dll')['sha256']==RUNTIME_SHA,
                'Probe source/runtime changed during execution')
        R.verify(rsp,profile='native',output=target,objects=objects,library_choices=[libraries],exports=exports)
        receipt=dict(schema=1,verified=True,scope='owned_development_native_VM_prefix_with_unregistered_native_candidates',
            accepted26=S.artifact(state_file),candidates=candidates,component_bindings=component_bindings,
            baseline_native_verification=state['main_native_verification'],baseline_execution=state['main_execution'],
            historical_full_source_proof=state['main_source_verification'],pre_link=S.artifact(output/'pre-link.json'),
            actual_PE_verification=S.artifact(output/'pe-verification.json'),
            image=S.artifact(target),runtime=S.artifact(output/'boom-runtime.dll'),response=S.artifact(rsp),report=S.artifact(report_file),
            native_process_exit_code=result.returncode,observations=observed,windows_filesystem=fs,
            first_process_fault=first,main_fault=main,fault=fault,fault_source='main_thread' if main else 'first_process_stop',
            native_stops_replaced=sorted(targets),prototype_native_added=len(targets),full_selection_reverified=False,
            original_Java_or_vtables_or_class_states_or_metadata_modified=False,original_inputs_unchanged=True,
            temporary_owned_buffer_final_counter='not_observed_in_ABI11; no_injected_observer',
            candidate_error_message_limitations=[row['policy'] for row in candidates],
            link_seconds=link_seconds,process_seconds=time.monotonic()-process_start,total_seconds=time.monotonic()-started,
            all_baseline_and_generated_inputs_outputs_post_hashed=True,sealed_inputs_and_generated_outputs=list(records.values()),
            probe_script=own,shared_provider_registered=False,formal27_accepted=False,full_VM_bootstrap=False,game_started=False,world_created=False)
        S.write(output/'execution.json',receipt);print(output/'execution.json',flush=True)
    except Exception as error:
        S.write(output/'failure.json',dict(verified=False,error=repr(error),
            full_selection_reverified=False,game_started=False,world_created=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accepted26',type=Path,required=True);parser.add_argument('--baseline-native',type=Path,required=True)
    parser.add_argument('--candidate',action='append',required=True,help='project-script.py:project-artifact/candidate.json; repeat in link order')
    parser.add_argument('--component-proof',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.accepted26,args.baseline_native,args.candidate,args.component_proof,args.output)
