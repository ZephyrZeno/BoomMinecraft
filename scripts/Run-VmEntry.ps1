param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256,[switch]$ObserveSourceAdmissions)
$ErrorActionPreference='Stop';$root=(Resolve-Path -LiteralPath $Directory).Path
$allowed=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.boom/vm-entry-images'))+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw 'Native entry execution requires isolated project output'}
$proofPath=Join-Path $root 'verification.json';$proof=Get-Content -LiteralPath $proofPath -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $AcceptedVerificationSha256 -or -not $proof.verified -or $proof.managed_execution_host -or $proof.full_VM_bootstrap -or $proof.game_started){throw 'Explicitly accepted native entry verification differs'}
$manifestPath=Join-Path $root 'vm-entry.json';$m=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $proof.source_manifest_sha256){throw 'Native entry source manifest changed'}
if((Test-Path -LiteralPath (Join-Path $root 'execution.json')) -or (Test-Path -LiteralPath (Join-Path $root 'vm-entry-status.bin'))){throw 'A native process execution record is immutable'}
$records=@($m.inputs)+@($m.executable,$m.runtime,$m.assembly,$m.link_response)+@($m.reassembled_objects)
function Assert-Inputs {foreach($r in $records){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('Native VM entry input changed: '+$r.path)}}}
Assert-Inputs
$start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$m.executable.path;$start.WorkingDirectory=$root;$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
$process=[Diagnostics.Process]::new();$process.StartInfo=$start
try{
    if(-not $process.Start()){throw 'Cannot start the owned assembly VM process'}
    $out_=$process.StandardOutput.ReadToEndAsync();$err_=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(45000)){$process.Kill($true);throw 'Owned native VM bootstrap prefix exceeded 45 seconds'}
    [IO.File]::WriteAllText((Join-Path $root 'process.out.log'),$out_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $root 'process.err.log'),$err_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
    $exitCode=$process.ExitCode
}finally{$process.Dispose()}
Assert-Inputs
$bytes=[IO.File]::ReadAllBytes((Join-Path $root 'vm-entry-status.bin'))
$contextRows=[bool]$m.binding_model.phase2_context_rows
$referenceControl=[bool]$m.binding_model.reference_processing
$winntFilesystem=[bool]$m.binding_model.winnt_filesystem
$expectedBytes=if($referenceControl){384}elseif($contextRows){320}elseif($m.system_phase2){312}elseif($m.signal_control -or $m.start_child){272}else{112};$expectedABI=if($referenceControl){9}elseif($contextRows){8}elseif($m.system_phase2){7}elseif($m.signal_control -or $m.start_child){6}else{2}
if($winntFilesystem){$expectedBytes=400;$expectedABI=10}
if($bytes.Length -ne $expectedBytes -or [BitConverter]::ToUInt32($bytes,0) -ne 0x52454d56 -or [BitConverter]::ToUInt32($bytes,4) -ne $expectedABI){throw 'Native process status ABI differs'}
function U32([int]$at){[BitConverter]::ToUInt32($bytes,$at)}
function U64([int]$at){[BitConverter]::ToUInt64($bytes,$at)}
if($exitCode -ne (U32 80) -or $exitCode -notin @(0,70,86)){throw 'Native process exit/status differ'}
$kind=U32 12;$state=U32 28;$row=U32 32;$boot=U32 52;$cleanup=U32 64;$fault=$null
if($state -eq 2){$d=Get-Content -LiteralPath (Join-Path $m.baseline_directory 'diagnostic.json') -Raw|ConvertFrom-Json;$matches=@($d.rows|Where-Object{$_.id -eq $row});if($matches.Count -ne 1){throw 'Native process stopped at an unknown source row'};$fault=$matches[0]}
if($state -notin @(0,2) -or (U32 68) -ne 0 -or (U32 48) -ne 0){throw 'Native VM cleanup/protocol failure'}
$threadStarted=$m.start_child -and (U32 112) -eq 1
$threadReaped=$m.start_child -and (U32 116) -eq 1
$threadRan=$m.start_child -and (U64 120) -eq 1
$threadExited=$m.start_child -and (U64 128) -eq 1
$workerFailure=if($m.start_child -or $m.signal_control){U32 136}else{0}
if($workerFailure -notin @(0,2)){throw 'Native worker failure publication is incomplete'}
$workerContext=if($workerFailure -eq 2){[ordered]@{kind=(U32 240);pc=(U32 244);method=(U32 248);depth=(U32 252);pending_Throwable_present=((U64 256) -ne 0)}}else{$null}
$signalOpened=$m.signal_control -and (U32 144) -eq 1
$signalClosed=$m.signal_control -and (U32 148) -eq 1
$signalAttached=$m.signal_control -and (U64 152) -eq 1
$signalExited=$m.signal_control -and (U64 168) -eq 1
$signalDetached=$m.signal_control -and (U64 176) -eq 1
$signalFailure=if($m.signal_control){U32 184}else{0}
$completed=$exitCode -eq 0 -and $kind -eq 0 -and $state -eq 0 -and $boot -eq 2 -and (U32 72) -eq 1 -and $cleanup -eq 7 -and (-not $m.construct_child -or (U32 84) -eq 1) -and (-not $m.start_child -or ($threadStarted -and $threadReaped -and $threadRan -and $threadExited -and $workerFailure -eq 0))
$completed=$completed -and (-not $m.signal_control -or ($signalOpened -and $signalClosed -and $signalAttached -and $signalExited -and $signalDetached -and $signalFailure -eq 0))
$referenceObservation=$null
if($referenceControl){
    $referenceObservation=[ordered]@{opened=(U32 320);stopped=(U32 324);closed=(U32 328);boundary_error=(U32 332);
        waits_entered=(U64 336);normal_wait_returns=(U64 344);stop_tokens_issued=(U64 352);stop_tokens_consumed=(U64 360);
        owned_monitor_acquisitions_released=(U64 368);owner_error=(U32 376);final_pool_state=(U32 380)}
    if($referenceObservation.closed -gt $referenceObservation.stopped -or $referenceObservation.stopped -gt $referenceObservation.opened -or $referenceObservation.opened -gt 1 -or $referenceObservation.normal_wait_returns -gt $referenceObservation.waits_entered -or $referenceObservation.stop_tokens_consumed -gt $referenceObservation.stop_tokens_issued){throw 'Inconsistent original Reference worker observations'}
    if($referenceObservation.closed -and ($referenceObservation.final_pool_state -ne 6 -or $referenceObservation.stop_tokens_issued -ne $referenceObservation.stop_tokens_consumed)){throw 'Reference transport closed with live stop tokens'}
    $completed=$completed -and $referenceObservation.closed -eq 1 -and $referenceObservation.owner_error -eq 0 -and $referenceObservation.boundary_error -eq 0
}
$phaseObservation=$null
$phaseRejected=$false
if($m.system_phase2){
    $phase1Returned=(U32 272) -eq 1
    $phase2Called=(U32 276) -eq 1
    $phase2Returned=(U32 280) -eq 1
    $phase2Code=if($phase2Returned){[BitConverter]::ToInt32($bytes,284)}else{$null}
    $levelBefore=U32 288
    $levelAfter=U32 292
    if((U32 272) -gt 1 -or (U32 276) -gt 1 -or (U32 280) -gt 1 -or ($phase1Returned -and (U32 76) -ne 1) -or ($phase2Called -and (-not $phase1Returned -or $levelBefore -ne 1)) -or ($phase2Returned -and (-not $phase2Called -or (U32 296) -ne 0))){throw 'Inconsistent main-thread System phase observations'}
    $phaseSuccess=$phase2Returned -and $phase2Code -eq 0 -and $levelAfter -eq 2
    if(((U32 72) -eq 1) -ne $phaseSuccess){throw 'Main-thread return differs from original System phase outcome'}
    $phaseRejected=$phase1Returned -and (U32 296) -eq 0 -and -not $phaseSuccess
    $completed=$completed -and $phaseSuccess
    $phaseObservation=[ordered]@{phase1_returned=$phase1Returned;phase2_called=$phase2Called;phase2_returned=$phase2Returned;phase2_result=$phase2Code;VM_level_before=$levelBefore;VM_level_after=$levelAfter;main_kind=(U32 296);main_pc=(U32 300);main_method=(U32 304);main_depth=(U32 308)}
}
if(-not $completed -and ($exitCode -ne 86 -or $kind -ne 45057 -or $state -ne 2) -and -not ($phaseRejected -and $exitCode -eq 70)){throw 'Native process failed without an identified source stop or module initialization failure'}
$result=[ordered]@{scope='native_assembly_process_original_VM_bootstrap_prefix_only';diagnostic_only=$true;completed_requested_prefix=$completed;completed_requested_entries=$completed;
native_process_exit_code=$exitCode;context_kind=$kind;context_pc=(U32 16);context_method=(U32 20);context_depth=(U32 24);record_state=$state;first_row=$row;
main_requested_entry_returned_normally=((U32 72) -eq 1);
bootstrap_state=$boot;original_primordial_constructors_completed=($boot -eq 2);System_phase1_called=((U32 76) -eq 1);System_phase1_completed=$(if($phaseObservation){$phaseObservation.phase1_returned}else{$m.include_System_phase1 -and $completed});
original_child_Thread_constructor_completed=((U32 84) -eq 1);
observed_child_Java_id=(U64 88);observed_next_Java_id=(U64 96);observed_main_Java_id=(U64 104);
original_ThreadIdentifiers_next_observed=($m.construct_child -and -not $m.signal_control -and (U64 88) -eq 2 -and (U64 96) -eq 3);
live_objects=(U64 56);held_monitor_acquisitions_at_stop=(U64 40);monitor_registry_lock_at_stop=(U32 48);cleanup_flags=$cleanup;
heap_cleanup_completed=(($cleanup -band 1) -ne 0);registry_cleanup_completed=(($cleanup -band 2) -ne 0);Java_frame_cleanup_completed=(($cleanup -band 4) -ne 0);owned_process_teardown_required=(($cleanup -band 1) -eq 0);
fault=$fault;native_report_sha256=(Get-FileHash -LiteralPath (Join-Path $root 'vm-entry-status.bin') -Algorithm SHA256).Hash.ToLowerInvariant();
source_verification_sha256=$AcceptedVerificationSha256;compiler_generated_VM_binding_pool=$true;VM_binding_configuration_fixture=$false;managed_execution_host=$false;jvm_fallback=$false;
Java_Thread_start_or_exit_executed=($threadStarted -or $threadExited);original_Java_Thread_start_completed=$threadStarted;original_Java_Thread_run_completed=$threadRan;original_Java_Thread_exit_completed=$threadExited;native_child_record_reaped=$threadReaped;worker_failure_state=$workerFailure;
worker_failure_context=$workerContext;
observed_original_worker_run_completions=$(if($m.start_child -or $m.signal_control){U64 120}else{0});observed_original_worker_exit_completions=$(if($m.start_child -or $m.signal_control){U64 128}else{0});
observed_source_start_priority_applications=$(if($m.start_child -or $m.signal_control){U64 208}else{0});observed_original_worker_starts=$(if($m.start_child -or $m.signal_control){U64 216}else{0});observed_original_worker_run_dispatch_calls=$(if($m.start_child -or $m.signal_control){U64 224}else{0});observed_worker_records_reaped=$(if($m.start_child -or $m.signal_control){U64 232}else{0});
nonnull_Runnable_task_verified=([bool]$m.child_task_main_thread -and $completed);Runnable_task_kind=$(if($m.child_task_main_thread){'original_main_Thread_as_Runnable'}else{$null});
normal_signal_transport_opened=$signalOpened;normal_signal_transport_closed=$signalClosed;normal_signal_dispatcher_attached=$signalAttached;original_signal_dispatcher_Thread_exit_completed=$signalExited;normal_signal_dispatcher_detached=$signalDetached;signal_worker_failure_state=$signalFailure;
observed_signal_dispatcher_Java_id=$(if($m.signal_control){U64 192}else{0});original_Signal_dispatch_entered_count=$(if($m.signal_control){U64 160}else{0});signal_transport_native_error=$(if($m.signal_control){U32 200}else{0});VM_BREAK_thread_dump_complete=$false;
full_VM_bootstrap=$false;game_started=$false;world_created=$false}
if($phaseObservation){$result['main_System_phases']=$phaseObservation}
if($referenceObservation){$result['reference_processing']=$referenceObservation}
if($winntFilesystem){
    $original=Get-Content -LiteralPath $m.binding_model.winnt_filesystem.metadata.path -Raw|ConvertFrom-Json
    $ready=U32 384;$fieldBound=U32 388;$optional=U32 392
    if($ready -notin @(0,2) -or $fieldBound -ne [int]($ready -eq 2) -or $optional -gt $fieldBound -or (U32 396) -ne $original.file_class){throw 'Native File.path registration differs from the source contract'}
    $result['windows_filesystem']=[ordered]@{registration_state=$ready;original_File_path_id_cached=[bool]$fieldBound;
        optional_final_path_API_available=[bool]$optional;original_File_class_id=(U32 396);original_path_offset=$original.field.offset}
}
if($contextRows){
    $mainRow=U32 312
    $result['first_process_fault']=$fault
    $result['main_source_row']=$mainRow
    $result['context_row_map_drops']=U32 316
    if($mainRow){
        if($phaseObservation.main_kind -ne 45057 -or $state -ne 2){throw 'Main thread source row has no diagnostic stop'}
        $mainFault=@($d.rows|Where-Object{$_.id -eq $mainRow})
        if($mainFault.Count -ne 1){throw 'Unknown main-thread source row'}
        $result['fault']=$mainFault[0]
        $result['fault_source']='main_thread'
    }elseif($fault){$result['fault_source']='first_process_stop'}
    if($ObserveSourceAdmissions){
        $eligible=[Collections.Generic.List[int]]::new()
        foreach($target in @($result['fault'],$fault)){
            if($target -and $target.category -in @(1,5) -and -not $eligible.Contains([int]$target.id)){$eligible.Add([int]$target.id)}
        }
        $result['source_admission_rows']=$eligible.ToArray()
    }
}
$json=$result|ConvertTo-Json -Depth 14;[IO.File]::WriteAllText((Join-Path $root 'execution.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
