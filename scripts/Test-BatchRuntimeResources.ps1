param([Parameter(Mandatory=$true)][string]$Directory,[string]$Runtime='.boom/assembly-runtime-v103')
$ErrorActionPreference='Stop';$dir=(Resolve-Path -LiteralPath $Directory).Path;$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$closure=Get-Content (Join-Path $dir 'closure.json') -Raw|ConvertFrom-Json;$proof=Get-Content (Join-Path $dir 'selection-verification.json') -Raw|ConvertFrom-Json
if(-not $proof.verified -or -not $proof.diagnostic_only -or -not $closure.selected_Runtime_resource_natives){throw 'Runtime probe requires a verified diagnostic image containing the actual source native module'}
$summary=Get-Content (Join-Path $closure.batch 'summary.json') -Raw|ConvertFrom-Json;$m=$summary.runtime_resources
$root=Join-Path (Split-Path $PSScriptRoot -Parent) ('.boom/normal-runtime-resource-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe -c 'import json,sys,zipfile;from pathlib import Path;s=json.loads(Path(sys.argv[1]).read_text());z=zipfile.ZipFile(s["runtime_resources"]["index"]["path"]);a=list(map(json.loads,z.read("methods.jsonl").splitlines()));print(json.dumps(["boom_m"+str(m["method"]) for m in a]))' (Join-Path $closure.batch 'summary.json') > "$root/native-names.json"
if($LASTEXITCODE -ne 0){throw 'Runtime probe source address inspection failed'}
$names=[string[]](Get-Content "$root/native-names.json" -Raw|ConvertFrom-Json)
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -d "$root/reference" java/reference/NormalRuntimeResourcesReference.java > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'Runtime JVM oracle compilation failed'}
Add-Type -Path tests/host/NormalRuntimeResourcesProbe.cs
$v=[BoomNormalRuntimeResourcesProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $dir 'diagnostic-image.dll'),$m.class_id,$names,'D:/Dev/Java/jdk-21/bin/java.exe',(Join-Path $root 'reference'))
$result=[ordered]@{passed=$true;fixture_only=$false;diagnostic_image=$true;source_closure_complete=$false;scope='original_Runtime_initializer_private_constructor_singleton_and_four_normal_layout_resource_native_entries';
batch=$closure.batch;source_image=$dir;source_Runtime_initialized=$true;source_Runtime_constructor_executed=$true;getRuntime_Java_getter_executed_by_probe=$false;native_methods=4;source_native_declarations=$m.source_native_declarations;
cold_init_workers=$v[0];parallel_query_calls=$v[1];JVM_affinity_cases=$v[2];error_checks=$v[3];quiescent_fixture_objects_collected=$v[4];heap_capacity=$v[5];occupied_block_bytes=$v[6];
memory_allocation_fixtures=$true;JVM_memory_exact_sizes_compared=$false;memory_semantics='fixed_arena_capacity_minus_occupied_block_spans';automatic_gc=$false;
System_boot_phases_completed=$false;game_multicore_optimization_complete=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
