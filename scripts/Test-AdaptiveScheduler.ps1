param(
    [Parameter(Mandatory=$true)][string]$NumericRun,
    [Parameter(Mandatory=$true)][string]$ObjectRun,
    [string]$ObjectProgramRun,
    [int]$Count=8195
)
$ErrorActionPreference='Stop'
if($Count -lt 1024 -or $Count -gt 32768){throw 'Count must be 1024..32768.'}
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
foreach($inputRun in @($NumericRun,$ObjectRun)){if(-not (Get-Content -LiteralPath (Join-Path $inputRun 'result.json') -Raw|ConvertFrom-Json).passed){throw 'JVM differential results must pass first.'}}
if($ObjectProgramRun -and -not (Get-Content -LiteralPath (Join-Path $ObjectProgramRun 'result.json') -Raw|ConvertFrom-Json).passed){throw 'Object program JVM differential results must pass first.'}
$root=Join-Path $projectRoot ('.boom\adaptive-tests\'+[guid]::NewGuid().ToString('N'))
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\SchedulerProbe.cs')
$runtime=Join-Path $root 'boom-runtime.dll'
[BoomSchedulerProbe]::CheckPolicies($runtime,(Join-Path $root 'fpstate.dll'))
$measurements=[Collections.Generic.List[object]]::new()
$methods=@('longLoop','intObject','linkedObjects');if($ObjectProgramRun){$methods+=@('pair','graph','arrays','wide','nullField')}
foreach($method in $methods){
    $inputRun=if($method -eq 'longLoop'){$NumericRun}elseif($method -in @('intObject','linkedObjects')){$ObjectRun}else{$ObjectProgramRun}
    $manifest=Get-Content -LiteralPath (Join-Path $inputRun "$method\compilation.json") -Raw|ConvertFrom-Json
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Kernel identity mismatch.'}
    $measurements.Add([BoomSchedulerProbe]::Measure($runtime,$manifest.dll,$method,$Count,[bool]$manifest.requires_heap))
}
$report=[ordered]@{runtime_language='assembly';real_batches_only=$true;replay_and_loss_counter_checked=$true;budget_candidates=@(1,2,4,8);samples_per_candidate=2;fewer_workers_within_percent=10;small_batches_serial=$true;busy_and_reset_and_kernel_change_checked=$true;object_program_workloads=[bool]$ObjectProgramRun;native_record_executions=$Count*12*$methods.Count;measurements=@($measurements.ToArray());passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
