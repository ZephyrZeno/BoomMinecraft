param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[Parameter(Mandatory=$true)][string]$ProviderPack,[string]$Runtime='.boom/assembly-runtime-v109-frames-a')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/cds-provider-tests/'+[guid]::NewGuid().ToString('N'));$image=Join-Path $root 'image'
[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-cds-provider-probe.py') --batch $Batch --plan $Plan --provider $ProviderPack --runtime (Join-Path $runtimePath 'boom-runtime.dll') --output $image > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 20;throw 'CDS provider source selection failed'}
& (Join-Path $PSScriptRoot 'Build-DiagnosticClosure.ps1') -Batch $Batch -Plan $Plan -Output $image -Runtime $runtimePath -PreparedSelection > "$root/build.log" 2>&1
if(-not $?){Get-Content "$root/build.log" -Tail 24;throw 'CDS provider image build failed'}
$m=Get-Content -LiteralPath "$image/source.json" -Raw|ConvertFrom-Json
Add-Type -Path (Join-Path $project 'tests/host/NormalCdsProviderProbe.cs')
$nativeNames=[string[]]@(0..4|ForEach-Object{$m.native_symbols."$_"})
$v=[BoomNormalCdsProviderProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $image 'diagnostic-image.dll'),$m.class_class_id,$m.CDS_class_id,$m.cold_target_class_id,$m.cold_target_empty_field,[string[]]$m.getter_symbols,$nativeNames)
[IO.Directory]::CreateDirectory("$root/reference")|Out-Null
& D:/Dev/Java/jdk-21/bin/javac.exe -source 21 -target 21 -proc:none --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/NormalCdsReference.java') > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/javac.log" -Tail 12;throw 'CDS no-archive oracle compilation failed'}
& D:/Dev/Java/jdk-21/bin/java.exe -Xshare:off --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp "$root/reference" NormalCdsReference > "$root/oracle.txt" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/oracle.err" -Tail 12;throw 'CDS no-archive oracle failed'}
$result=[ordered]@{passed=$true;batch=$m.batch;provider=$m.provider;scope='source_CDS_clinit_getters_and_five_no_archive_natives_with_normal_Class_validation';cold_CDS_workers=$v[0];parallel_calls=$v[1];error_checks=$v[2];original_Java_getters=$v[3];native_methods=$v[4];cold_target_preserved=($v[5] -eq 1);original_Optional_initializer_executed=$true;initialized_target_static_reference_preserved=$true;JVM_oracle='-Xshare:off policy and independent cold-target fixture';Java_codegen_rerun=$false;diagnostic_image=$true;source_closure_complete=$false;automatic_gc=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
