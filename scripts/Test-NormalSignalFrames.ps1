param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256,[Parameter(Mandatory=$true)][string]$Runtime)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/normal-signal-frame-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-normal-signal-frames-test.py') --directory $Directory --accepted-verification-sha256 $AcceptedVerificationSha256 --runtime $Runtime --output "$root/source.json" > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 14;throw 'Normal signal frame source preparation failed'}
$m=Get-Content -LiteralPath "$root/source.json" -Raw|ConvertFrom-Json
function Assert-Inputs {foreach($r in $m.inputs){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('Normal signal frame input changed: '+$r.path)}}}
Assert-Inputs
foreach($name in @('boom-runtime.dll','boom-runtime.lib')){Copy-Item -LiteralPath (Join-Path (Split-Path $m.runtime -Parent) $name) -Destination (Join-Path $root $name);if((Get-FileHash -LiteralPath (Join-Path $root $name)).Hash -ne (Get-FileHash -LiteralPath (Join-Path (Split-Path $m.runtime -Parent) $name)).Hash){throw 'Signal test runtime copy changed'}}
& (Join-Path $PSScriptRoot 'Build-SignalControlProbe.ps1') -Output $root > "$root/callback-build.log" 2>&1
if(-not $?){Get-Content "$root/callback-build.log" -Tail 14;throw 'Signal callback fixture build failed'}
Add-Type -Path (Join-Path $project 'tests/host/NormalSignalFramesProbe.cs')
$v=[BoomNormalSignalFramesProbe]::Run("$root/source.json","$root/signal-control-probe.dll")
Assert-Inputs
$result=[ordered]@{passed=$true;scope='signal_native_transport_binding_and_queries_with_normal_TracePool3_metadata_and_legacy_TracePool2_fixture';normal_source_frame_methods=$v[0];accepted_trace_pool_versions=$v[1];error_checks=$v[2];assembly_callbacks=$v[3];workers=$v[4];parallel_native_queries=$v[5];source_native_entries_executed=$false;source_Java_executed=$false;copied_source_TracePool_metadata=$true;assembly_callback_fixtures=$true;original_Signal_dispatch_executed=$false;Java_thread_lifecycle_complete=$false;game_started=$false;world_created=$false;source_configuration="$root/source.json";run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
