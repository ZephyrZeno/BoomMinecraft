param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256)
$ErrorActionPreference='Stop';$root=(Resolve-Path -LiteralPath $Directory).Path
$allowed=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.boom/diagnostic-startup'))+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw 'VM bootstrap execution must stay in isolated project diagnostics'}
$proofPath=Join-Path $root 'selection-verification.json';$proof=Get-Content -LiteralPath $proofPath -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $AcceptedVerificationSha256 -or -not $proof.verified -or -not $proof.diagnostic_only -or $proof.source_closure_complete){throw 'Accepted original-constructor source proof differs'}
if(Test-Path -LiteralPath (Join-Path $root 'execution.json')){throw 'A completed VM bootstrap execution is immutable'}
$config=Join-Path $root 'vm-thread-bootstrap.json';$m=Get-Content -LiteralPath $config -Raw|ConvertFrom-Json
$configHash=(Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash.ToLowerInvariant()
$imageHash=(Get-FileHash -LiteralPath $m.image -Algorithm SHA256).Hash.ToLowerInvariant()
$d=Get-Content -LiteralPath (Join-Path $root 'diagnostic.json') -Raw|ConvertFrom-Json
if($m.runtime -ne $d.global_provider_identity.runtime_dll -or (Get-FileHash -LiteralPath $m.runtime -Algorithm SHA256).Hash.ToLowerInvariant() -ne $d.global_provider_identity.runtime_sha256){throw 'VM bootstrap runtime/source proof differs'}
function Assert-Inputs {foreach($r in $m.inputs){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('VM bootstrap input changed: '+$r.path)}}}
Assert-Inputs
Add-Type -Path (Join-Path $PSScriptRoot '../tests/host/NormalVmThreadBootstrapProbe.cs')
$v=[BoomNormalVmThreadBootstrapProbe]::Run($config)
Assert-Inputs
if((Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash.ToLowerInvariant() -ne $configHash -or (Get-FileHash -LiteralPath $m.image -Algorithm SHA256).Hash.ToLowerInvariant() -ne $imageHash){throw 'VM bootstrap configuration/image changed'}
$fault=$null
if($v[4] -eq 2){$rows=@($d.rows|Where-Object{$_.id -eq $v[5]});if($rows.Count -ne 1){throw 'VM bootstrap source stop does not exist'};$fault=$rows[0]}
if($v[4] -notin @(0,2)){throw 'VM bootstrap stop publication did not complete'}
$completed=$v[0] -eq 0 -and $v[4] -eq 0 -and $v[10] -eq 2 -and $v[11] -eq 1 -and (-not $m.continue_System_phase1 -or $v[18] -eq 1)
$result=[ordered]@{diagnostic_only=$true;scope='normal_VM_primordial_thread_with_untouched_original_constructors';completed_requested_entries=$completed;
context_kind=$v[0];context_pc=$v[1];context_method=$v[2];context_depth=$v[3];record_state=$v[4];first_row=$v[5];caller_pc=$v[6];caller_method=$v[7];caller_depth=$v[8];
initialized_prerequisite_classes=$v[9];bootstrap_state=$v[10];original_constructor_field_assertions_passed=($v[11] -eq 1);live_objects=$v[12];heap_cleanup_completed=($v[13] -eq 1);
held_monitor_acquisitions_at_stop=$v[14];monitor_registry_lock_at_stop=$v[15];registry_cleanup_completed=($v[16] -eq 1);owned_process_teardown_required=($v[13] -eq 0);
fault=$fault;source_configuration=$config;source_configuration_sha256=$configHash;source_verification_sha256=$AcceptedVerificationSha256;image_sha256=$imageHash;
VM_binding_configuration_fixture=$true;fake_Thread_field_state=$false;original_main_Thread_and_two_ThreadGroup_and_ACC_constructors_completed=($v[11] -eq 1);
original_System_phase1_called=($v[17] -eq 1);original_System_phase1_completed=($v[18] -eq 1);
constructor_specialization=$false;constructor_branches_removed=$false;Java_thread_start_or_exit_executed=$false;source_closure_complete=$false;full_VM_bootstrap=$false;game_started=$false;world_created=$false}
$json=$result|ConvertTo-Json -Depth 14;[IO.File]::WriteAllText((Join-Path $root 'execution.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
