param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/system-signal-monitor-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-system-signal-monitor-test.py') --directory $Directory --accepted-verification-sha256 $AcceptedVerificationSha256 --output "$root/source.json" > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 14;throw 'System signal monitor source preparation failed'}
$m=Get-Content -LiteralPath "$root/source.json" -Raw|ConvertFrom-Json
function Assert-Inputs {foreach($r in $m.inputs){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('System monitor input changed: '+$r.path)}}}
Assert-Inputs
Add-Type -Path (Join-Path $project 'tests/host/SystemSignalMonitorProbe.cs')
$v=[BoomSystemSignalMonitorProbe]::Run("$root/source.json")
Assert-Inputs
$result=[ordered]@{passed=$true;scope='original_System_path_canonical_Signal_Class_static_monitor_contention_and_release_before_explicit_handle0_native_frontier';original_Java_executed=$true;requested_entry='java/lang/System.initPhase1()V';canonical_Class_waiters=$v[0];monitor_class=$v[1];monitor_method=$v[2];stop_caller_method=$v[3];stop_caller_pc=$v[4];Signal_initializer_completed=$true;prepared_receiver_or_Thread_objects=$false;System_phase1_completed=$false;full_VM_bootstrap=$false;game_started=$false;world_created=$false;source_configuration="$root/source.json";run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
