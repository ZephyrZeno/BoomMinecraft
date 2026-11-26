param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string[]]$ClassRoot,[string[]]$Entry,[string]$ReceiverClass,
[string]$Runtime='.boom/assembly-runtime-v109-frames-a',[string]$ResumeDirectory,[string]$OutputDirectory,[string]$SeedDiagnosticDirectory,[string]$SeedResultFile,[ValidateRange(1,128)][int]$MaxRounds=32,[ValidateRange(32,512)][int]$HeapMB=128,
[string[]]$ProviderPack,[string[]]$ProviderFamily=@('cds-no-archive-v1','object-identity-v1','normal-constructors-v1','class-flags-v1','normal-constructor-invocation-v1','normal-file-bootstrap-v1','normal-scoped-memory-registration-v1','normal-throwable-v1','normal-signal-lookup-v1','normal-thread-primitives-v1','normal-access-context-v1'),[switch]$AllowAdditionalClassRoots,[switch]$AllowDifferentEntries,
[string]$SourceSelectionDirectory,[ValidateRange(1,65536)][int]$MaxPreselectedMethods=16384,
[switch]$ParallelAssembly,[ValidateRange(1,8)][int]$AssemblyWorkers=8,[ValidateRange(1,1024)][int]$AssemblyCodeMiB=8)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path;$batchPath=(Resolve-Path -LiteralPath $Batch).Path;$planPath=(Resolve-Path -LiteralPath $Plan).Path
if($ResumeDirectory -and $OutputDirectory){throw 'Resume and fresh output directories are mutually exclusive'}
if($SeedDiagnosticDirectory -and $SeedResultFile){throw 'Choose a seed directory or a completed-prefix result file'}
if($ResumeDirectory -and ($SeedDiagnosticDirectory -or $SeedResultFile)){throw 'Seed and resume are mutually exclusive'}
if($ResumeDirectory -and $SourceSelectionDirectory){throw 'Source preselection requires a fresh diagnostic directory'}
if($SourceSelectionDirectory){$SourceSelectionDirectory=(Resolve-Path -LiteralPath $SourceSelectionDirectory).Path}
$previousSeedResult=if($SeedResultFile){(Resolve-Path -LiteralPath $SeedResultFile).Path}elseif($SeedDiagnosticDirectory){(Resolve-Path -LiteralPath (Join-Path $SeedDiagnosticDirectory 'result.json')).Path}else{$null}
$root=if($ResumeDirectory){(Resolve-Path -LiteralPath $ResumeDirectory).Path}elseif($OutputDirectory){[IO.Path]::GetFullPath($OutputDirectory)}else{Join-Path $project ('.boom/diagnostic-startup/'+[guid]::NewGuid().ToString('N'))}
$allowed=[IO.Path]::GetFullPath((Join-Path $project '.boom/diagnostic-startup'))+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw 'Resumed diagnostics must stay inside this project diagnostic directory'}
if($OutputDirectory -and (Test-Path -LiteralPath $root)){throw 'Fresh diagnostics require a new output directory'}
[IO.Directory]::CreateDirectory($root)|Out-Null
if($ResumeDirectory -and -not $ProviderPack.Count -and (Test-Path -LiteralPath (Join-Path $root 'result.json'))){
    $previousResult=Get-Content -LiteralPath (Join-Path $root 'result.json') -Raw|ConvertFrom-Json
    $ProviderPack=@($previousResult.runtime_provider_packs|Where-Object{$_})
}elseif($ResumeDirectory -and -not $ProviderPack.Count){
    $lastPrepared=Get-ChildItem -LiteralPath $root -Directory -Filter 'round-*'|Sort-Object Name|Select-Object -Last 1
    if(-not $lastPrepared -or -not (Test-Path -LiteralPath (Join-Path $lastPrepared.FullName 'execution.json'))){throw 'Interrupted diagnostics require a completed, verified round before resume'}
    $preparedManifest=Get-Content -LiteralPath (Join-Path $lastPrepared.FullName 'closure.json') -Raw|ConvertFrom-Json
    $ProviderPack=@($preparedManifest.runtime_provider_packs|ForEach-Object{$_.manifest.path})
}elseif(-not $ProviderPack.Count -and (Get-Content -LiteralPath (Join-Path $batchPath 'summary.json') -Raw|ConvertFrom-Json).schema -eq 23){
    $nativeFrames=$null
    if(@($ProviderFamily|Where-Object{$_ -in @('normal-constructor-invocation-v1','normal-throwable-v1','normal-access-context-v1')}).Count){
        $frameOutput=@(& (Join-Path $PSScriptRoot 'Build-NativeFrameOverlay.ps1') -Batch $batchPath -Plan $planPath)
        if(-not $?){throw 'Automatic native frame data build failed'}
        [IO.File]::WriteAllLines((Join-Path $root 'native-frame-overlay.log'),[string[]]$frameOutput,[Text.UTF8Encoding]::new($false))
        $nativeFrames=[string]$frameOutput[$frameOutput.Count-1]
    }
    foreach($family in $ProviderFamily){
        $providerArgs=@{Batch=$batchPath;Plan=$planPath;Family=$family}
        if($family -in @('normal-constructor-invocation-v1','normal-throwable-v1','normal-access-context-v1')){$providerArgs.FrameOverlay=$nativeFrames}
        $buildOutput=@(& (Join-Path $PSScriptRoot 'Build-RuntimeProviderPack.ps1') @providerArgs)
        if(-not $?){throw 'Automatic assembly runtime provider build failed'}
        [IO.File]::WriteAllLines((Join-Path $root ('provider-'+$family+'.log')),[string[]]$buildOutput,[Text.UTF8Encoding]::new($false))
        $ProviderPack+=([string]$buildOutput[$buildOutput.Count-1])
    }
}
$ProviderPack=@($ProviderPack|ForEach-Object{(Resolve-Path -LiteralPath $_).Path})
$providerIdentity=@($ProviderPack|ForEach-Object{[ordered]@{path=$_;sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant();verification_sha256=(Get-FileHash -LiteralPath (Join-Path (Split-Path $_ -Parent) 'verification.json') -Algorithm SHA256).Hash.ToLowerInvariant()}})
$admittedClasses=[Collections.Generic.HashSet[int]]::new();$admitted=[Collections.Generic.HashSet[int]]::new();$rounds=[Collections.Generic.List[object]]::new();$profile=Join-Path $root 'profile.json';$stopReason='round_limit'
$sourceHash=(Get-FileHash -LiteralPath (Join-Path $batchPath 'summary.json') -Algorithm SHA256).Hash.ToLowerInvariant()
$seedEvidence=$null;$runtimeFailure=$null;$preselections=[Collections.Generic.List[object]]::new()
if($previousSeedResult){
    $seedFile=Join-Path $root 'seed.json'
    $seedArgs=@((Join-Path $PSScriptRoot 'seed-diagnostic-profile.py'),$batchPath,'--previous',$previousSeedResult,'--output',$seedFile)
    foreach($r in $ClassRoot){$seedArgs+=@('--class-root',$r)};foreach($r in $Entry){$seedArgs+=@('--entry',$r)}
    if($AllowAdditionalClassRoots){$seedArgs+='--allow-additional-class-roots'}
    if($AllowDifferentEntries){$seedArgs+='--allow-different-entries'}
    & D:/Dev/Python312/python.exe @seedArgs > (Join-Path $root 'seed.log')
    if($LASTEXITCODE -ne 0){throw 'Executed Java selection seed source verification failed'}
    $seed=Get-Content -LiteralPath $seedFile -Raw|ConvertFrom-Json
    foreach($id_ in $seed.admitted_classes){$null=$admittedClasses.Add([int]$id_)}
    foreach($id_ in $seed.admitted_methods){$null=$admitted.Add([int]$id_)}
    $seedEvidence=[ordered]@{path=$seedFile;sha256=(Get-FileHash -LiteralPath $seedFile -Algorithm SHA256).Hash.ToLowerInvariant();admitted_Java_methods=$admitted.Count;native_implementations_added=0}
}
function Add-ReachedJavaClass([string]$Round){
    $args_=@((Join-Path $PSScriptRoot 'update-diagnostic-profile.py'),$batchPath,'--execution',(Join-Path $Round 'execution.json'),'--admitted',$profile,'--output',(Join-Path $Round 'admission.json'))
    & D:/Dev/Python312/python.exe @args_ > (Join-Path $Round 'admission.log')
    if($LASTEXITCODE -ne 0){throw 'Reached Java target source verification failed'}
    $next=Get-Content -LiteralPath (Join-Path $Round 'admission.json') -Raw|ConvertFrom-Json;$before=$admitted.Count+$admittedClasses.Count
    foreach($id_ in $next.admitted_classes){$null=$admittedClasses.Add([int]$id_)}
    foreach($id_ in $next.admitted_methods){$null=$admitted.Add([int]$id_)}
    if(($admitted.Count+$admittedClasses.Count) -le $before){throw 'Diagnostic execution repeated already selected Java targets'}
}
$firstRound=0
if($ResumeDirectory){
    $prior=$null
    if(Test-Path -LiteralPath (Join-Path $root 'result.json')){
        $prior=Get-Content -LiteralPath (Join-Path $root 'result.json') -Raw|ConvertFrom-Json
        foreach($preselection in $prior.source_only_preselections){$preselections.Add($preselection)}
        if((@($prior.runtime_provider_packs) -join "`n") -ne (@($ProviderPack) -join "`n")){throw 'Resumed runtime providers differ; start a fresh diagnostic with a source-verified seed'}
        if($ProviderPack.Count -and (($prior.runtime_provider_identity|ConvertTo-Json -Depth 5 -Compress) -ne ($providerIdentity|ConvertTo-Json -Depth 5 -Compress))){throw 'Resumed runtime provider contents changed'}
    }
    $old=Get-Content -LiteralPath $profile -Raw|ConvertFrom-Json
    if($old.source_batch_summary_sha256 -ne $sourceHash){throw 'Resumed diagnostic batch differs'}
    foreach($id_ in $old.admitted_classes){$null=$admittedClasses.Add([int]$id_)}
    $seedFile=Join-Path $root 'seed.json'
    if(Test-Path -LiteralPath $seedFile){$seed=Get-Content -LiteralPath $seedFile -Raw|ConvertFrom-Json;if($seed.source_batch_summary_sha256 -ne $sourceHash){throw 'Resumed initialization seed source differs'};$seedEvidence=[ordered]@{path=$seedFile;sha256=(Get-FileHash -LiteralPath $seedFile -Algorithm SHA256).Hash.ToLowerInvariant();admitted_Java_methods=@($seed.admitted_methods).Count;native_implementations_added=0}}
    foreach($id_ in $old.admitted_methods){$null=$admitted.Add([int]$id_)}
    foreach($r in (Get-ChildItem -LiteralPath $root -Directory -Filter 'round-*'|Sort-Object Name)){
        if(-not (Test-Path -LiteralPath (Join-Path $r.FullName 'execution.json'))){throw 'Resumed round has no completed execution'}
        $m_=Get-Content -LiteralPath (Join-Path $r.FullName 'closure.json') -Raw|ConvertFrom-Json
        $proof_=Get-Content -LiteralPath (Join-Path $r.FullName 'selection-verification.json') -Raw|ConvertFrom-Json
        if(-not $proof_.verified -or -not $proof_.diagnostic_only -or $proof_.source_closure_complete){throw 'Resumed round lacks a diagnostic source verification'}
        if($m_.source_batch_summary_sha256 -ne $sourceHash){throw 'Resumed round source differs'}
        if(-not $prior){
            $roundProviderIdentity=@($m_.runtime_provider_packs|ForEach-Object{[ordered]@{path=$_.manifest.path;sha256=$_.manifest.digest.sha256;verification_sha256=$_.verification.digest.sha256}})
            if(($roundProviderIdentity|ConvertTo-Json -Depth 5 -Compress) -ne ($providerIdentity|ConvertTo-Json -Depth 5 -Compress)){throw 'Interrupted round provider identities changed'}
            $diagnosticIdentity=(Get-Content -LiteralPath (Join-Path $r.FullName 'diagnostic.json') -Raw|ConvertFrom-Json).global_provider_identity
            if($diagnosticIdentity.runtime_sha256 -ne (Get-FileHash -LiteralPath (Join-Path $runtimePath 'boom-runtime.dll') -Algorithm SHA256).Hash.ToLowerInvariant()){throw 'Interrupted round runtime changed'}
        }
        $expectedClasses=@($m_.requested_class_roots|ForEach-Object{$_.loader+':'+$_.name})
        $expectedEntries=@($m_.requested_method_roots|ForEach-Object{$_.loader+':'+$_.owner+':'+$_.name+':'+$_.descriptor})
        if(($expectedClasses -join "`n") -ne (@($ClassRoot) -join "`n") -or ($expectedEntries -join "`n") -ne (@($Entry) -join "`n")){throw 'Resumed diagnostic roots differ'}
        $e_=Get-Content -LiteralPath (Join-Path $r.FullName 'execution.json') -Raw|ConvertFrom-Json
        $rounds.Add([ordered]@{directory=$r.FullName;execution=$e_});$firstRound++
    }
    $last=$rounds[$rounds.Count-1]
    if($last.execution.completed_requested_entries){$stopReason='requested_entries_completed_diagnostic_only';$firstRound=$MaxRounds}
    elseif($last.execution.fault -and $last.execution.fault.category -in @(1,5)){Add-ReachedJavaClass $last.directory}
    elseif($last.execution.fault){$stopReason='requires_semantic_implementation';$firstRound=$MaxRounds}
    else{$stopReason='runtime_failure_without_diagnostic_stop';$firstRound=$MaxRounds}
}
for($i=$firstRound;$i -lt $MaxRounds;$i++){
    $profileValue=[ordered]@{source_batch_summary_sha256=$sourceHash;admitted_classes=@($admittedClasses|Sort-Object);admitted_methods=@($admitted|Sort-Object);diagnostic_only=$true}
    [IO.File]::WriteAllText($profile,($profileValue|ConvertTo-Json -Depth 3),[Text.UTF8Encoding]::new($false))
    $round=Join-Path $root ('round-'+$i.ToString('D3'))
    $buildProfile=$profile
    if($SourceSelectionDirectory){
        $buildProfile=Join-Path $root ('source-only-profile-'+$i.ToString('D3')+'.json')
        & D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'preselect-diagnostic-java.py') $batchPath --selection $SourceSelectionDirectory --profile $profile --output $buildProfile --max-extra-methods $MaxPreselectedMethods > (Join-Path $root ('source-only-profile-'+$i+'.log'))
        if($LASTEXITCODE -ne 0){throw 'Source-only generated Java preselection failed'}
        $preselections.Add([ordered]@{path=$buildProfile;sha256=(Get-FileHash -LiteralPath $buildProfile -Algorithm SHA256).Hash.ToLowerInvariant();extra_methods_previously_executed=$false;native_implementations_added=0})
    }
    $parallelArgs=@{}
    if($ParallelAssembly){$parallelArgs=@{ParallelAssembly=$true;AssemblyWorkers=$AssemblyWorkers;AssemblyCodeMiB=$AssemblyCodeMiB}}
    & (Join-Path $PSScriptRoot 'Build-DiagnosticClosure.ps1') -Batch $batchPath -Plan $planPath -Output $round -ClassRoot $ClassRoot -Entry $Entry -ReceiverClass $ReceiverClass -AdmitProfile $buildProfile -Runtime $runtimePath -ProviderPack $ProviderPack @parallelArgs > (Join-Path $root ('build-'+$i+'.log'))
    if(-not $?){throw 'Diagnostic image preparation failed'}
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=(Get-Process -Id $PID).Path;$start.WorkingDirectory=$round;$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($a in @('-NoProfile','-File',(Join-Path $PSScriptRoot 'Run-DiagnosticImage.ps1'),'-Directory',$round,'-Runtime',$runtimePath,'-HeapMB',"$HeapMB")){$start.ArgumentList.Add($a)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start
    try{
        if(-not $process.Start()){throw 'Cannot start isolated diagnostic execution'}
        $out_=$process.StandardOutput.ReadToEndAsync();$err_=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit(45000)){$process.Kill($true);throw 'Owned diagnostic execution exceeded 45 seconds'}
        [IO.File]::WriteAllText((Join-Path $round 'execution.out.log'),$out_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $round 'execution.err.log'),$err_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
        if($process.ExitCode -ne 0){
            $runtimeFailure=[ordered]@{directory=$round;exit_code=$process.ExitCode;stderr=(Join-Path $round 'execution.err.log');
                stderr_sha256=(Get-FileHash -LiteralPath (Join-Path $round 'execution.err.log') -Algorithm SHA256).Hash.ToLowerInvariant();
                execution_record_published=$false;game_started=$false}
            $stopReason='diagnostic_child_failure';break
        }
    }finally{$process.Dispose()}
    $execution=Get-Content -LiteralPath (Join-Path $round 'execution.json') -Raw|ConvertFrom-Json;$rounds.Add([ordered]@{directory=$round;execution=$execution})
    if($execution.completed_requested_entries){$stopReason='requested_entries_completed_diagnostic_only';break}
    if(-not $execution.fault){$stopReason='runtime_failure_without_diagnostic_stop';break}
    if($execution.fault.category -notin @(1,5)){$stopReason='requires_semantic_implementation';break}
    Add-ReachedJavaClass $round
}
$result=[ordered]@{schema=1;diagnostic_only=$true;batch=$batchPath;plan=$planPath;source_batch_summary_sha256=$sourceHash;runtime=$runtimePath;
class_roots=@($ClassRoot);entries=@($Entry);fixture_only=[bool]$ReceiverClass;admitted_classes=@($admittedClasses|Sort-Object);admitted_methods=@($admitted|Sort-Object);seed_evidence=$seedEvidence;rounds=$rounds.ToArray();stop_reason=$stopReason;
runtime_provider_packs=@($ProviderPack);runtime_provider_identity=$providerIdentity;base_Java_codegen_rerun=$false;selected_diagnostic_Java_reassembled=$true;
source_only_preselections=$preselections.ToArray();
runtime_failure=$runtimeFailure;
source_closure_complete=$false;native_implementations_added=0;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
if($rounds.Count -gt 0 -and $rounds[$rounds.Count-1].execution.fault -and $rounds[$rounds.Count-1].execution.fault.category -notin @(1,5)){
    $needed=[ordered]@{diagnostic_only=$true;scope='first_executed_unavailable_dependency';batch=$batchPath;source_batch_summary_sha256=$sourceHash;fault=$rounds[$rounds.Count-1].execution.fault;game_started=$false}
    [IO.File]::WriteAllText((Join-Path $root 'compatibility-needed.json'),($needed|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
}
$json=$result|ConvertTo-Json -Depth 16;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
