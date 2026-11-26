param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/reflection-array-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-reflection-array-test.txt',$root)
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
$boundary='package dev.boom.reflection; public final class ArrayBoundary {public static Class<?> seed(){return int'+('[]'*255)+'.class;}}'
[IO.File]::WriteAllText((Join-Path $root ArrayBoundary.java),$boundary)
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -d (Join-Path $root classes) java/subset/dev/boom/reflection/ArrayReflection.java (Join-Path $root ArrayBoundary.java) java/reference/ArrayReflectionReference.java
if($LASTEXITCODE -ne 0){throw 'Reflection array source/reference javac failed'}
& $inputs.java.executable -Xmx128m -cp (Join-Path $root classes) ArrayReflectionReference > (Join-Path $root vectors.txt) 2> (Join-Path $root reference.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root reference.err) -Tail 12;throw 'Locked JVM reflection array oracle failed'}
if((Get-Content (Join-Path $root vectors.txt)).Count -ne 386){throw 'JVM reflection vector count changed'}
$arguments=@('compile-program')
foreach($name in @('ArrayReflection','ArrayReflection$Element','ArrayReflection$Marker','ArrayBoundary')){$arguments+=@('--class-file',(Join-Path $root "classes/dev/boom/reflection/$name.class"))}
$arguments+=@('--entry-class','dev/boom/reflection/ArrayReflection','--method','allocate','--descriptor','(Ljava/lang/Class;I[II)Ljava/lang/Object;','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--output',(Join-Path $root program),'--assemble')
& $Boom @arguments > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 18;throw 'Reflection array AOT compilation failed'}
& $Boom inspect-jdk-bridges --lock $MetadataLock --jdk-base $JdkBase --bridge-id 6 --bridge-id 16 --output (Join-Path $root bridges) > (Join-Path $root bridges.json)
if($LASTEXITCODE -ne 0){throw 'Original Class source bridge inspection failed'}
& D:/Dev/Python312/python.exe scripts/verify-reflection-arrays.py (Join-Path $root program/program.json) (Join-Path $root bridges/inspection.json) (Join-Path $root types.json) > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Independent reflection source verification failed'}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json
$names=Get-Content (Join-Path $root types.json) -Raw|ConvertFrom-Json
$owner=@($p.classes|Where-Object name -eq 'dev/boom/reflection/ArrayReflection')[0]
$field=@($owner.fields|Where-Object name -eq initialized)[0]
$missing=-1
for($i=0;$i -lt $p.reflection_arrays.rows.Count;$i++){$r=$p.reflection_arrays.rows[$i];if($null -eq $r.array_type -and -not $r.void_component -and $r.component_rank -lt 255){$missing=$i;break}}
if($missing -lt 0){throw 'Missing out-of-graph reflection descriptor boundary'}
Add-Type -Path tests/host/ReflectionArrayProbe.cs
[BoomReflectionArrayProbe]::Run($p.compilation.dll,(Join-Path $root vectors.txt),[string[]]$names,[uint32]$owner.id,[uint32]$field.index,[uint32]$missing)
& D:/Dev/Python312/python.exe scripts/make-platform-private-fixtures.py (Join-Path $root forged)
if($LASTEXITCODE -ne 0){throw 'Private reflection fixture generation failed'}
foreach($name in @('PrivateReflectNew','PrivateReflectMulti')){
    & $Boom compile-program --class-file (Join-Path $root "forged/$name.class") --entry-class "dev/boom/platform/$name" --method run --descriptor '()Ljava/lang/Object;' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root "rejected-$name") > (Join-Path $root "$name.json") 2> (Join-Path $root "$name.err")
    if($LASTEXITCODE -eq 0 -or (Get-Content (Join-Path $root "$name.err") -Raw) -notmatch 'Reflection array allocation native is private'){throw 'Application private reflection native was not rejected'}
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Reflection array compiler changed during tests'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;original_Array_newInstance_overloads_executed=2;original_Class_asSubclass_and_toString_Code_executed=$true;JVM_array_shape_and_exception_class_cases=329;JVM_asSubclass_identity_and_exception_class_cases=57;parallel_source_workers=8;parallel_source_calls=4096;parallel_raw_allocation_calls=4096;primitive_zero_initialization_and_reference_scan_prefix_checked=$true;allocated_dimensions_and_exact_array_identity_checked=$true;component_class_not_initialized=$true;rank_255_and_invalid_total_rank_checked=$true;null_negative_void_dimension_error_priority_checked=$true;pending_context_and_native_metadata_gates=$true;wrong_type_and_foreign_heap_dimensions_rejected=$true;quiescent_GC_graph_roots_checked=$true;partial_OOM_after_parent_and_first_child_checked=$true;partial_graph_reclaimed_and_allocation_recovered=$true;application_private_native_calls_rejected=2;frozen_array_type_rows=$p.reflection_arrays.rows.Count;missing_exact_array_descriptor_fails_explicitly=$true;dynamic_type_creation=$false;reflection_get_set_boxing_complete=$false;exception_messages_compared=$false;System_boot_phases_completed=$false;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-reflection-array-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
