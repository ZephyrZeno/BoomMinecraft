param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$Runtime,[int]$HeapMB=128)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $Directory).Path;$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$m=Get-Content -LiteralPath (Join-Path $root 'closure.json') -Raw|ConvertFrom-Json
$d=Get-Content -LiteralPath (Join-Path $root 'diagnostic.json') -Raw|ConvertFrom-Json
if(-not $m.diagnostic_only -or $m.source_closure_complete -or $d.stop_kind -ne 45057){throw 'Execution requires an explicit diagnostic-only image'}
Add-Type -Path (Join-Path $PSScriptRoot '../tests/host/DiagnosticStartupHost.cs')
$classes=[string[]]@($m.requested_class_roots|ForEach-Object{'boom_class'+$_.class_id});$entries=[string[]]@($m.requested_method_roots|ForEach-Object{$_.symbol})
$layout=$null;$fixture=$false
if($m.diagnostic_receiver){$layout=$m.diagnostic_receiver.layout_symbol;$fixture=$true}
$expectedDescriptor=if($fixture){'()Z'}else{'()V'}
if(@($m.requested_method_roots|Where-Object{$_.descriptor -ne $expectedDescriptor}).Count){throw 'Unsupported diagnostic entry signature'}
$v=[BoomDiagnosticStartupHost]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $root 'diagnostic-image.dll'),$HeapMB,$classes,$entries,$layout)
$fault=$null
if($v[4] -eq 2){$fault=@($d.rows|Where-Object{$_.id -eq $v[5]});if($fault.Count -ne 1){throw 'Recorded diagnostic row does not exist'};$fault=$fault[0]}
if($v[4] -notin @(0,2)){throw 'Diagnostic record publication did not complete'}
$completed=$v[0] -eq 0 -and $v[4] -eq 0 -and $v[9] -eq $classes.Count -and $v[10] -eq $entries.Count
$result=[ordered]@{diagnostic_only=$true;fixture_only=$fixture;completed_requested_entries=$completed;entry_return=$v[12];context_kind=$v[0];context_pc=$v[1];context_method=$v[2];context_depth=$v[3];
record_state=$v[4];first_row=$v[5];caller_pc=$v[6];caller_method=$v[7];caller_depth=$v[8];initialized_class_roots=$v[9];called_method_roots=$v[10];live_objects=$v[11];
heap_cleanup_completed=($v[13] -eq 1);held_monitor_acquisitions_at_stop=$v[14];monitor_registry_lock_at_stop=$v[15];owned_process_teardown_required=($v[13] -eq 0);
fault=$fault;source_closure_complete=$false;native_implementations_added=0;game_started=$false;world_created=$false;full_game_ready=$false}
$json=$result|ConvertTo-Json -Depth 12;[IO.File]::WriteAllText((Join-Path $root 'execution.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
