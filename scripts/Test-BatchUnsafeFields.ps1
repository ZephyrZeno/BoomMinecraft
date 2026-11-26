param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v107')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/unsafe-field-probes/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory((Split-Path $root -Parent))|Out-Null
& D:/Dev/Python312/python.exe scripts/prepare-unsafe-fields-probe.py $Batch --plan $Plan --output $root > ($root+'.prepare.log') 2> ($root+'.prepare.err')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath ($root+'.prepare.err') -Tail 12;throw 'Source field probe preparation failed'}
$source=Get-Content -LiteralPath (Join-Path $root 'source.json') -Raw|ConvertFrom-Json
$image=Join-Path $root 'image'
& D:/Dev/Python312/python.exe scripts/prepare-unsafe-fields-image.py --source "$root/source.json" --output $image --runtime (Join-Path $runtimePath 'boom-runtime.dll') > "$root/selection.log" 2> "$root/selection.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/selection.err" -Tail 12;throw 'Field fixture source selection failed'}
& scripts/Build-DiagnosticClosure.ps1 -Batch $Batch -Plan $Plan -Output $image -Runtime $runtimePath -PreparedSelection > "$root/build.log" 2>&1
if(-not $?){Get-Content -LiteralPath "$root/build.log" -Tail 14;throw 'Source field fixture image build failed'}
$proof=Get-Content -LiteralPath (Join-Path $image 'selection-verification.json') -Raw|ConvertFrom-Json
if(-not $proof.verified -or -not $proof.diagnostic_only -or $proof.source_Unsafe_field_natives -ne 1){throw 'Field native image lacks independent selection proof'}
& D:/Dev/Java/jdk-21/bin/javac.exe -source 21 -target 21 -proc:none --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -d "$root/reference" java/reference/NormalUnsafeFieldsReference.java > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/javac.log" -Tail 8;throw 'Field JVM oracle compile failed'}
& D:/Dev/Java/jdk-21/bin/java.exe --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp "$root/reference" NormalUnsafeFieldsReference "$root/oracle-cases.tsv" > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/oracle.err" -Tail 10;throw 'Field JVM oracle failed'}
$oracle=@{};foreach($line in (Get-Content -LiteralPath "$root/oracle.tsv")){$p=$line -split "`t";$oracle[$p[0]]=[int]$p[1]}
if($oracle.cases -ne $source.JVM_lookup_cases -or $oracle.errors -ne 3){throw 'Field JVM oracle coverage differs'}
Add-Type -Path tests/host/NormalUnsafeFieldsProbe.cs
$v=[BoomNormalUnsafeFieldsProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $image 'diagnostic-image.dll'),
    (Join-Path $root 'cases.tsv'),(Join-Path $root 'addresses.tsv'),$source.field_native,$source.unsafe_class,$source.unsafe_singleton,
    [int[]]$source.atomic_classes,[int[]]$source.atomic_value_fields,[int[]]$source.atomic_value_cells,[string[]]$source.entry_symbols,[int[]]$source.inherited_non_declaration)
if($v[1] -ne $source.bootstrap_field_cases -or $v[3] -ne $source.address_fixtures -or $v[4] -ne $source.relocated_fixtures){throw 'Actual field probe coverage differs from source fixtures'}
$result=[ordered]@{passed=$true;scope='original_Unsafe_and_atomic_initializers_source_field_lookup_opaque_cookies_and_receiver_specific_address_maps';
batch=$source.batch;source_image=$image;run_directory=$root;native_methods=1;cold_init_workers=$v[0];source_bootstrap_field_queries=$v[1];canonical_Class_cases=$v[2];
address_fixtures=$v[3];relocated_inherited_fixtures=$v[4];parallel_query_calls=$v[5];error_checks=$v[6];original_atomic_constructor_and_getter_cases=$v[7];original_atomic_initializers=$v[8];targets_kept_uninitialized_during_lookup=$v[9];fixture_name_Strings=$v[10];
JVM_declaration_and_lookup_relation_cases=$oracle.cases;JVM_error_cases=$oracle.errors;numeric_offsets_compared_with_JVM=$false;
fixture_String_inputs=$true;arbitrary_target_constructors_executed=$false;typed_Unsafe_memory_natives_provided=$false;Throwable_objects_materialized=$false;automatic_gc=$false;
fixture_only=$false;diagnostic_image=$true;source_closure_complete=$false;System_boot_phases_completed=$false;game_started=$false;world_created=$false;full_game_ready=$false}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
