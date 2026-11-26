param()
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $projectRoot ('.boom\exception-runtime-tests\'+[guid]::NewGuid().ToString('N'))
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\ExceptionProbe.cs')
[BoomExceptionProbe]::Run((Join-Path $root 'boom-runtime.dll'))
$report=[ordered]@{runtime_language='assembly';context_bytes=32;handler_table_abi=1;materialized_throwable_only=$true;ordered_typed_catches=$true;half_open_ranges=$true;local_call_site_separate_from_origin=$true;rethrow_preserves_identity=$true;pending_exception_gc_root=$true;consumed_graph_reclaimed=$true;multicore_records=65560;workers=8;implicit_exception_materialization=$false;java_handler_codegen_integrated=$false;automatic_gc_safepoints=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $projectRoot '.boom\latest-exception-runtime.txt'),$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
