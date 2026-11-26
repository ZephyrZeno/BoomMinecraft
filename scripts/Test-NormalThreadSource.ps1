param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/normal-thread-source-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-normal-thread-test.py') --directory $Directory --accepted-verification-sha256 $AcceptedVerificationSha256 --output "$root/source.json" > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 14;throw 'Normal Thread source preparation failed'}
$m=Get-Content -LiteralPath "$root/source.json" -Raw|ConvertFrom-Json
function Assert-Inputs {foreach($r in $m.inputs){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('Normal Thread source input changed: '+$r.path)}}}
Assert-Inputs
Add-Type -Path (Join-Path $project 'tests/host/NormalThreadSourceProbe.cs')
$v=[BoomNormalThreadSourceProbe]::Run("$root/source.json")
Assert-Inputs
$result=[ordered]@{passed=$true;scope='original_Thread_class_initialization_and_six_normal_native_entries_with_explicit_VM_preconstructor_peer_fixtures';original_Thread_initializer_executed=$true;cold_registration_workers=$v[0];parallel_registrations=$v[1];canonical_runtime_export_slots=$v[2];workers=$v[3];parallel_native_calls=$v[4];error_checks=$v[5];source_native_entries_exercised=6;VM_preconstructor_peer_fixtures=$true;original_Thread_constructors_executed=$false;Java_thread_start_or_exit_executed=$false;virtual_threads_implemented=$false;VM_id_address_atomics_executed=$false;full_VM_bootstrap=$false;game_started=$false;world_created=$false;source_configuration="$root/source.json";run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
