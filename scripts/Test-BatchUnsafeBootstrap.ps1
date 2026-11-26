param([Parameter(Mandatory=$true)][string]$Directory,[string]$Runtime='.boom/assembly-runtime-v101')
$ErrorActionPreference='Stop'
$directoryPath=(Resolve-Path -LiteralPath $Directory).Path;$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$closure=Get-Content -LiteralPath (Join-Path $directoryPath 'closure.json') -Raw|ConvertFrom-Json
$evidence=Get-Content -LiteralPath (Join-Path $directoryPath 'selection-verification.json') -Raw|ConvertFrom-Json
$execution=Get-Content -LiteralPath (Join-Path $directoryPath 'execution.json') -Raw|ConvertFrom-Json
if(-not $evidence.verified -or -not $evidence.diagnostic_only -or -not $execution.completed_requested_entries){throw 'Unsafe probe requires a verified diagnostic source image with completed requested initialization'}
$summary=Get-Content -LiteralPath (Join-Path $closure.batch 'summary.json') -Raw|ConvertFrom-Json
$module=$summary.unsafe_bootstrap
$root=Join-Path (Split-Path $PSScriptRoot -Parent) ('.boom/unsafe-bootstrap-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe scripts/prepare-unsafe-bootstrap-probe.py $directoryPath --output "$root/source.json"
if($LASTEXITCODE -ne 0){throw 'Unsafe probe metadata inspection failed'}
$m=Get-Content -LiteralPath "$root/source.json" -Raw|ConvertFrom-Json
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -encoding UTF-8 -d "$root/reference" java/reference/NormalUnsafeBootstrapReference.java > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'Unsafe JVM oracle compile failed'}
& D:/Dev/Java/jdk-21/bin/java.exe --add-opens java.base/jdk.internal.misc=ALL-UNNAMED -cp "$root/reference" NormalUnsafeBootstrapReference > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/oracle.err" -Tail 8;throw 'Unsafe JVM oracle failed'}
$oracle=@{};foreach($line in (Get-Content "$root/oracle.tsv")){$p=$line -split "`t";$oracle[$p[0]]=$p[1]}
if($oracle.ADDRESS_SIZE0 -ne '8' -or $oracle.BIG_ENDIAN -ne 'false' -or $oracle.UNALIGNED_ACCESS -ne 'true'){throw 'Unsupported JVM platform oracle'}
for($i=0;$i -lt 8;$i++){if([int]$oracle[$m.array_names[$i]] -ne $m.scales[$i]){throw 'Primitive array JVM oracle differs'}}
Add-Type -Path tests/host/NormalUnsafeBootstrapProbe.cs
$v=[BoomNormalUnsafeBootstrapProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $directoryPath 'diagnostic-image.dll'),$module.class_id,$module.constants_class_id,[string[]]$m.native_names,[int[]]$m.array_types,[int[]]$m.scales,[string[]]$m.static_names,[int[]]$m.static_values,[int]$oracle.PAGE_SIZE)
$result=[ordered]@{passed=$true;fixture_only=$false;diagnostic_image=$true;source_closure_complete=$false;scope='original_Unsafe_and_UnsafeConstants_initializers_normal_array_ABI_partial_AOT_bindings_and_fullFence';source_image=$directoryPath;batch=$closure.batch;
source_Unsafe_initialized=$true;source_UnsafeConstants_initialized=$true;native_methods=4;registered_prelinked_methods=3;cold_init_workers=$v[0];parallel_calls=$v[1];array_Class_cases=$v[2];original_static_values=$v[3];error_checks=$v[4];live_objects=$v[5];
JVM_primitive_array_cases=8;object_references_bytes=8;array_payload_base=0;cache_writeback_enabled=$false;other_Unsafe_memory_APIs_implemented=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
