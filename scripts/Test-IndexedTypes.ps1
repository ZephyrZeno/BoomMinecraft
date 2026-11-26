param([string]$Runtime='.boom/assembly-runtime-v87-final')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/indexed-type-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
Add-Type -Path (Join-Path $project 'tests/host/RuntimeTypeProbe.cs')
[BoomRuntimeTypeProbe]::AbiAndFailure((Join-Path $runtimePath 'boom-runtime.dll'))
Add-Type -Path (Join-Path $project 'tests/host/IndexedTypeProbe.cs')
$counts=[BoomIndexedTypeProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'))
$result=[ordered]@{passed=$true;scope='assembly_ABI2_index_and_field_address_stress_with_synthetic_metadata';runtime_language='assembly';runtime_sha256=(Get-FileHash (Join-Path $runtimePath 'boom-runtime.dll')).Hash.ToLowerInvariant();rows=$counts[0];type_capacity=$counts[1];native_queries=$counts[2];hash_slots=$counts[3];workers=$counts[4];legacy_ABI1_guards=$true;pending_errors_preserved=$true;pending_Throwable_type_and_ordered_catch=$true;duplicate_tags_rejected=$true;field_reference_prefix_guards=$true;lookup_guest_allocations=0;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $project '.boom/latest-indexed-type-test.txt'),$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
