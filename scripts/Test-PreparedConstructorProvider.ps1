param([Parameter(Mandatory=$true)][string]$Source,[string]$Runtime='.boom/assembly-runtime-v109-frames-a')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$sourcePath=(Resolve-Path -LiteralPath $Source).Path;$s=Get-Content $sourcePath -Raw|ConvertFrom-Json
$image=(Resolve-Path -LiteralPath $s.prepared_image).Path
if(-not $image.StartsWith((Join-Path $project '.boom/constructor-provider-tests/'),[StringComparison]::OrdinalIgnoreCase)){throw 'Prepared image must be a project constructor fixture'}
if((Get-FileHash (Join-Path $image 'selection-verification.json') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $s.prepared_image_verification_sha256){throw 'Prepared source image proof changed'}
$proof=Get-Content (Join-Path $image 'selection-verification.json') -Raw|ConvertFrom-Json
if(-not $proof.verified -or -not $proof.diagnostic_only -or $proof.source_closure_complete){throw 'Prepared source selection scope differs'}
$root=Join-Path $project ('.boom/constructor-provider-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory("$root/reference")|Out-Null
Copy-Item -LiteralPath $sourcePath -Destination "$root/source.json"
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/NormalConstructorsReference.java') > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/javac.log" -Tail 12;throw 'Prepared constructor oracle compilation failed'}
$names=[string[]]@($s.cases|ForEach-Object{$_.name});$classpath=@($s.oracle_classpath) -join [IO.Path]::PathSeparator
$javaArgs=@('--add-opens=java.base/java.lang.reflect=ALL-UNNAMED',('-Dboom.oracle.classpath='+$classpath),'-cp',"$root/reference",'NormalConstructorsReference')+@($names)
$argumentFile=Join-Path $root 'oracle-args.txt'
[IO.File]::WriteAllLines($argumentFile,[string[]]@($javaArgs|ForEach-Object{'"'+$_.Replace('\','/').Replace('"','\"')+'"'}),[Text.UTF8Encoding]::new($false))
& D:/Dev/Java/jdk-21/bin/java.exe ("@"+$argumentFile) > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/oracle.err" -Tail 12;throw 'Prepared constructor oracle failed'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-constructor-oracle.py') "$root/source.json" "$root/oracle.tsv" > "$root/oracle-verification.json"
if($LASTEXITCODE -ne 0){throw 'Prepared constructor JVM comparison failed'}
Add-Type -Path (Join-Path $project 'tests/host/NormalConstructorProviderProbe.cs')
$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$v=[BoomNormalConstructorProviderProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $image 'diagnostic-image.dll'),"$root/source.json")
$result=[ordered]@{passed=$true;batch=$s.batch;scope='original_JDK_and_one_vanilla_application_constructor_metadata_with_original_Java_getters';cases=$v[0];constructor_objects_checked=$v[1];signature_cases=$v[2];annotation_cases=$v[3];parameter_annotation_cases=$v[4];cold_target_classes_preserved=$v[5];error_checks=$v[6];workers=$v[7];parallel_calls=$v[8];original_Constructor_getters=7;fixture_named_modules=@($s.fixture_modules|Where-Object{$null -ne $_.name}).Count;fixture_unnamed_modules=@($s.fixture_modules|Where-Object{$null -eq $_.name}).Count;fixture_loaders=@($s.fixture_loaders).Count;full_module_bootstrap=$false;application_constructor_or_initializer_executed=$false;source_image=$image;source_configuration="$root/source.json";JVM_oracle='counts_descriptors_modifiers_signatures_annotation_bytes_exceptions';Java_codegen_rerun=$false;diagnostic_image=$true;all_native_frames=$false;automatic_gc=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
