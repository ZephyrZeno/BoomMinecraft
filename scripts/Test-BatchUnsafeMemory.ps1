param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v107')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/unsafe-memory-probes/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory((Split-Path $root -Parent))|Out-Null
& D:/Dev/Python312/python.exe scripts/prepare-unsafe-memory-probe.py $Batch --plan $Plan --output $root > ($root+'.prepare.log') 2> ($root+'.prepare.err')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath ($root+'.prepare.err') -Tail 12;throw 'Typed memory source fixture preparation failed'}
$source=Get-Content -LiteralPath (Join-Path $root 'source.json') -Raw|ConvertFrom-Json
$image=Join-Path $root 'image'
& D:/Dev/Python312/python.exe scripts/prepare-unsafe-memory-image.py --source "$root/source.json" --output $image --runtime (Join-Path $runtimePath 'boom-runtime.dll') > "$root/selection.log" 2> "$root/selection.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/selection.err" -Tail 12;throw 'Typed memory source selection failed'}
& scripts/Build-DiagnosticClosure.ps1 -Batch $Batch -Plan $Plan -Output $image -Runtime $runtimePath -PreparedSelection > "$root/build.log" 2>&1
if(-not $?){Get-Content -LiteralPath "$root/build.log" -Tail 14;throw 'Typed memory source image build failed'}
$proof=Get-Content -LiteralPath (Join-Path $image 'selection-verification.json') -Raw|ConvertFrom-Json
if(-not $proof.verified -or -not $proof.diagnostic_only -or $proof.source_Unsafe_memory_natives -ne 42){throw 'Typed memory fixture lacks independent source selection proof'}
& D:/Dev/Java/jdk-21/bin/javac.exe -source 21 -target 21 -proc:none --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -d "$root/reference" java/reference/NormalUnsafeMemoryReference.java > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/javac.log" -Tail 8;throw 'Typed memory JVM oracle compile failed'}
& D:/Dev/Java/jdk-21/bin/java.exe --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp "$root/reference" NormalUnsafeMemoryReference "$root/vectors.tsv" > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/oracle.err" -Tail 12;throw 'Typed memory JVM oracle failed'}
$oracle=@{};foreach($line in (Get-Content -LiteralPath "$root/oracle.err")){if($line -match '^([a-z_]+)\s+(\d+)$'){$oracle[$Matches[1]]=[long]$Matches[2]}}
if($oracle.atomic_cases -ne 324 -or $oracle.unaligned_plain_cases -ne 1 -or $oracle.boolean_nonzero_read_cases -ne 1){throw 'Typed memory JVM oracle coverage differs'}
Add-Type -Path tests/host/NormalUnsafeMemoryProbe.cs
$v=[BoomNormalUnsafeMemoryProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $image 'diagnostic-image.dll'),
    (Join-Path $root 'fields.tsv'),(Join-Path $root 'methods.tsv'),(Join-Path $root 'oracle.tsv'),
    $source.unsafe_class,$source.unsafe_singleton,$source.atomic_class,$source.atomic_value_field,$source.object_class,$source.reference_array,
    $source.loader_roots,$source.module_roots,[string[]]$source.entry_symbols)
if($v[1] -ne $source.scalar_vectors -or $v[4] -ne 354 -or $v[5] -ne 22 -or $v[6] -ne 24576 -or $v[7] -ne 128 -or $v[8] -ne 4096 -or $v[11] -ne 42){throw 'Typed memory source execution coverage differs'}
$result=[ordered]@{passed=$true;scope='source_Unsafe_typed_heap_access_and_original_AtomicInteger_methods';
batch=$source.batch;source_image=$image;run_directory=$root;native_methods=$v[11];cold_init_workers=$v[0];
scalar_vectors=$v[1];sequential_native_calls=$v[2];JVM_signaling_NaN_variations=$v[3];atomic_cases=$v[4];plain_view_cases=$v[5];
successful_contended_atomic_operations=$v[6];SC_litmus_rounds=$v[7];original_Java_contended_increment_calls=$v[8];error_checks=$v[9];quiescent_reference_GC_checks=$v[10];
JVM_atomic_relation_cases=$oracle.atomic_cases;JVM_unaligned_plain_cases=$oracle.unaligned_plain_cases;JVM_boolean_nonzero_read_cases=$oracle.boolean_nonzero_read_cases;
source_entry_exports_verified=$true;fixture_target_storage=$true;development_host='CSharp';game_runtime_language='assembly';
numeric_offsets_compared_with_JVM=$false;off_heap=$false;static_field_base=$false;unaligned_atomic=$false;automatic_gc=$false;
diagnostic_image=$true;source_closure_complete=$false;System_boot_phases_completed=$false;game_started=$false;world_created=$false;full_game_ready=$false}
$json=$result|ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false))
Write-Output $json
