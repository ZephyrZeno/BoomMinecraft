param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,
[Parameter(Mandatory=$true)][string]$Runtime,[string]$SeedDiagnosticDirectory,[string]$SeedResultFile,
[Parameter(Mandatory=$true)][string[]]$ProviderPack,[string]$OutputDirectory,[ValidateRange(1,64)][int]$MaxRounds=8,[switch]$ContinueSystemPhase1,[switch]$NativeProcess,[switch]$ConstructChild,[switch]$StartChild,[switch]$ChildTaskMainThread,[switch]$SignalControl,[switch]$SystemPhase2,
[string]$SourceSelectionDirectory,[ValidateRange(1,65536)][int]$MaxPreselectedMethods=16384,[string[]]$PreselectPackage)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(([bool]$SeedDiagnosticDirectory) -eq ([bool]$SeedResultFile)){throw 'Specify one source seed directory or a verified prefix result file'}
$previousSeed=if($SeedResultFile){(Resolve-Path -LiteralPath $SeedResultFile).Path}else{(Resolve-Path -LiteralPath (Join-Path $SeedDiagnosticDirectory 'result.json')).Path}
$batchPath=(Resolve-Path -LiteralPath $Batch).Path;$planPath=(Resolve-Path -LiteralPath $Plan).Path;$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
if($ChildTaskMainThread){$StartChild=$true}
if($SystemPhase2){$SignalControl=$true;$NativeProcess=$true}
if($SignalControl){$ContinueSystemPhase1=$true;if(-not $NativeProcess){throw 'Signal control requires the assembly-owned native process'}}
if($StartChild){$ConstructChild=$true}
if($ConstructChild -and -not $NativeProcess){throw 'Child construction is validated through the assembly-owned native process'}
if(-not $OutputDirectory){$OutputDirectory=Join-Path $project ('.boom/diagnostic-startup/'+[guid]::NewGuid().ToString('N'))}
$root=[IO.Path]::GetFullPath($OutputDirectory);$allowed=[IO.Path]::GetFullPath((Join-Path $project '.boom/diagnostic-startup'))+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $root)){throw 'Use a fresh isolated VM thread bootstrap directory'}
[IO.Directory]::CreateDirectory($root)|Out-Null
$classes=@('java/lang/String','java/lang/System','java/lang/Class','java/lang/reflect/Method','java/lang/Thread','java/lang/ThreadGroup','java/security/AccessControlContext','jdk/internal/misc/VM')|ForEach-Object{'bootstrap:'+$_}
$entries=@('bootstrap:java/lang/ThreadGroup:<init>:()V','bootstrap:java/lang/ThreadGroup:<init>:(Ljava/lang/ThreadGroup;Ljava/lang/String;IZ)V','bootstrap:java/security/AccessControlContext:<init>:([Ljava/security/ProtectionDomain;Z)V','bootstrap:java/lang/Thread:<init>:(Ljava/lang/ThreadGroup;Ljava/lang/String;ILjava/lang/Runnable;JLjava/security/AccessControlContext;)V')
if($ConstructChild){$entries+=$(if($ChildTaskMainThread){'bootstrap:java/lang/Thread:<init>:(Ljava/lang/ThreadGroup;Ljava/lang/Runnable;Ljava/lang/String;)V'}else{'bootstrap:java/lang/Thread:<init>:(Ljava/lang/ThreadGroup;Ljava/lang/String;)V'})}
if($StartChild){$entries+='bootstrap:java/lang/Thread:start:()V'}
if($ContinueSystemPhase1){$entries+='bootstrap:java/lang/System:initPhase1:()V'}
if($SystemPhase2){$entries+='bootstrap:java/lang/System:initPhase2:(ZZ)I'}
$seedFile=Join-Path $root 'seed.json';$profile=Join-Path $root 'profile.json'
$seedArgs=@((Join-Path $PSScriptRoot 'seed-diagnostic-profile.py'),$batchPath,'--previous',$previousSeed,'--output',$seedFile,'--allow-additional-class-roots','--allow-different-entries')
foreach($c in $classes){$seedArgs+=@('--class-root',$c)};foreach($e in $entries){$seedArgs+=@('--entry',$e)}
& D:/Dev/Python312/python.exe @seedArgs > (Join-Path $root 'seed.log') 2> (Join-Path $root 'seed.err')
if($LASTEXITCODE -ne 0){throw 'Original-source VM thread selection seed failed'}
$seed=Get-Content -LiteralPath $seedFile -Raw|ConvertFrom-Json
$sourceProfiles=[Collections.Generic.List[object]]::new()
if($SourceSelectionDirectory){$SourceSelectionDirectory=(Resolve-Path -LiteralPath $SourceSelectionDirectory).Path}
if($PreselectPackage.Count -and -not $SourceSelectionDirectory){throw 'Package preselection requires a verified source selection directory'}
$methods=@($seed.admitted_methods);$admittedClasses=@($seed.admitted_classes);$rounds=[Collections.Generic.List[object]]::new();$stopReason='round_limit';$failure=$null
$sourceHash=(Get-FileHash -LiteralPath (Join-Path $batchPath 'summary.json') -Algorithm SHA256).Hash.ToLowerInvariant()
for($i=0;$i -lt $MaxRounds;$i++){
    $p=[ordered]@{source_batch_summary_sha256=$sourceHash;admitted_methods=$methods;admitted_classes=$admittedClasses}
    [IO.File]::WriteAllText($profile,($p|ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))
    $round=Join-Path $root ('round-{0:D3}' -f $i)
    $selectionProfile=$profile
    if($SourceSelectionDirectory){
        $inputProfile=Join-Path $root ('admission-input-{0:D3}.json' -f $i)
        Copy-Item -LiteralPath $profile -Destination $inputProfile
        $selectionProfile=Join-Path $root ('source-only-profile-{0:D3}.json' -f $i)
        $preselectArgs=@((Join-Path $PSScriptRoot 'preselect-diagnostic-java.py'),$batchPath,'--selection',$SourceSelectionDirectory,'--profile',$inputProfile,'--output',$selectionProfile,'--max-extra-methods',$MaxPreselectedMethods)
        foreach($package in $PreselectPackage){$preselectArgs+=@('--package',$package)}
        & D:/Dev/Python312/python.exe @preselectArgs > (Join-Path $root ('source-only-profile-'+$i+'.log'))
        if($LASTEXITCODE -ne 0){throw 'Source-only generated Java preselection failed'}
        $sourceProfiles.Add([ordered]@{path=$selectionProfile;sha256=(Get-FileHash -LiteralPath $selectionProfile -Algorithm SHA256).Hash.ToLowerInvariant()})
    }
    $prepare=@((Join-Path $PSScriptRoot 'prepare-normal-vm-thread-bootstrap.py'),'--batch',$batchPath,'--plan',$planPath,'--runtime',(Join-Path $runtimePath 'boom-runtime.dll'),'--output',$round,'--profile',$selectionProfile)
    foreach($pack in $ProviderPack){$prepare+=@('--provider-pack',(Resolve-Path -LiteralPath $pack).Path)}
    if($ContinueSystemPhase1){$prepare+='--continue-system-phase1'}
    if($SystemPhase2){$prepare+='--system-phase2'}
    if($ConstructChild){$prepare+='--construct-child'}
    if($StartChild){$prepare+='--start-child'}
    if($ChildTaskMainThread){$prepare+='--child-task-main-thread'}
    & D:/Dev/Python312/python.exe @prepare > (Join-Path $root ('prepare-'+$i+'.log')) 2> (Join-Path $root ('prepare-'+$i+'.err'))
    if($LASTEXITCODE -ne 0){throw 'Normal VM thread source preparation failed'}
    & (Join-Path $PSScriptRoot 'Build-DiagnosticClosure.ps1') -Batch $batchPath -Plan $planPath -Runtime $runtimePath -Output $round -PreparedSelection > (Join-Path $root ('build-'+$i+'.log'))
    if(-not $?){throw 'Normal VM thread independent source/COFF build failed'}
    $accepted=(Get-FileHash -LiteralPath (Join-Path $round 'selection-verification.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    if($NativeProcess){
        $nativeRoot=Join-Path $project ('.boom/vm-entry-images/'+[guid]::NewGuid().ToString('N'))
        $nativeArgs=@{Directory=$round;AcceptedVerificationSha256=$accepted;OutputDirectory=$nativeRoot;ConstructorOnly=(-not $ContinueSystemPhase1);ConstructChild=[bool]$ConstructChild}
        if($StartChild){$nativeArgs.StartChild=$true}
        if($ChildTaskMainThread){$nativeArgs.ChildTaskMainThread=$true}
        if($SignalControl){$nativeArgs.SignalControl=$true}
        if($SystemPhase2){$nativeArgs.SystemPhase2=$true}
        & (Join-Path $PSScriptRoot 'Build-VmEntry.ps1') @nativeArgs > (Join-Path $root ('native-build-'+$i+'.log'))
        if(-not $?){throw 'Native VM entry construction failed'}
        $nativeAccepted=(Get-FileHash -LiteralPath (Join-Path $nativeRoot 'verification.json') -Algorithm SHA256).Hash.ToLowerInvariant()
        & (Join-Path $PSScriptRoot 'Run-VmEntry.ps1') -Directory $nativeRoot -AcceptedVerificationSha256 $nativeAccepted -ObserveSourceAdmissions:$SystemPhase2 > (Join-Path $root ('native-run-'+$i+'.log'))
        if(-not $?){throw 'Assembly-owned VM prefix execution failed'}
        Copy-Item -LiteralPath (Join-Path $nativeRoot 'execution.json') -Destination (Join-Path $round 'execution.json')
        [IO.File]::WriteAllText((Join-Path $round 'native-execution-directory.txt'),$nativeRoot,[Text.UTF8Encoding]::new($false))
    }else{
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=(Get-Process -Id $PID).Path;$start.WorkingDirectory=$round;$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($a in @('-NoProfile','-File',(Join-Path $PSScriptRoot 'Run-NormalVmThreadBootstrap.ps1'),'-Directory',$round,'-AcceptedVerificationSha256',$accepted)){$start.ArgumentList.Add($a)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start
    try{
        if(-not $process.Start()){throw 'Cannot start owned VM thread bootstrap test process'}
        $out_=$process.StandardOutput.ReadToEndAsync();$err_=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit(45000)){$process.Kill($true);throw 'Owned VM thread source execution exceeded 45 seconds'}
        [IO.File]::WriteAllText((Join-Path $round 'execution.out.log'),$out_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $round 'execution.err.log'),$err_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
        if($process.ExitCode -ne 0){$failure=[ordered]@{directory=$round;exit_code=$process.ExitCode;execution_record_published=$false};$stopReason='execution_child_failure';break}
    }finally{$process.Dispose()}
    }
    $execution=Get-Content -LiteralPath (Join-Path $round 'execution.json') -Raw|ConvertFrom-Json
    $rounds.Add([ordered]@{directory=$round;execution=$execution})
    if($execution.completed_requested_entries){$stopReason=if($SystemPhase2){'original_System_phase2_completed'}elseif($ContinueSystemPhase1){'original_primordial_constructors_and_System_phase1_completed'}elseif($StartChild){'original_Java_thread_start_run_exit_completed'}elseif($ConstructChild){'original_primordial_and_child_constructors_completed'}else{'original_primordial_constructors_completed'};break}
    if(-not $execution.fault){$stopReason='runtime_failure_without_source_stop';break}
    if($execution.fault.category -notin @(1,5) -and -not $execution.source_admission_rows.Count){$stopReason='requires_semantic_implementation';break}
    & D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'update-diagnostic-profile.py') $batchPath --execution (Join-Path $round 'execution.json') --admitted $profile --output (Join-Path $round 'admission.json') > (Join-Path $round 'admission.log')
    if($LASTEXITCODE -ne 0){throw 'Actual VM thread Java target admission failed'}
    $next=Get-Content -LiteralPath (Join-Path $round 'admission.json') -Raw|ConvertFrom-Json
    if($next.admitted_methods.Count+$next.admitted_classes.Count -le $methods.Count+$admittedClasses.Count){throw 'VM thread execution repeated an already admitted target'}
    $methods=@($next.admitted_methods);$admittedClasses=@($next.admitted_classes)
}
$result=[ordered]@{schema=1;diagnostic_only=$true;scope='normal_VM_primordial_thread_source_constructors';batch=$batchPath;plan=$planPath;runtime=$runtimePath;source_batch_summary_sha256=$sourceHash;
class_roots=@($classes);entries=$entries;admitted_methods=$methods;admitted_classes=$admittedClasses;seed_evidence=[ordered]@{path=$seedFile;sha256=(Get-FileHash -LiteralPath $seedFile -Algorithm SHA256).Hash.ToLowerInvariant()};
runtime_provider_packs=$ProviderPack;rounds=$rounds.ToArray();stop_reason=$stopReason;runtime_failure=$failure;constructor_specialization=$false;constructor_branches_removed=$false;managed_execution_host=(-not $NativeProcess);VM_binding_configuration_fixture=(-not $NativeProcess);construct_child_requested=[bool]$ConstructChild;start_child_requested=[bool]$StartChild;nonnull_Runnable_task_requested=[bool]$ChildTaskMainThread;normal_signal_control_requested=[bool]$SignalControl;source_closure_complete=$false;full_VM_bootstrap=$false;game_started=$false;world_created=$false;run_directory=$root}
if($SystemPhase2){$result['scope']='normal_VM_primordial_thread_and_module_system_bootstrap';$result['original_System_phase2_requested']=$true}
if($SourceSelectionDirectory){$result['source_only_preselections']=$sourceProfiles.ToArray();$result['preselected_methods_counted_as_executed']=$false}
$json=$result|ConvertTo-Json -Depth 18;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
