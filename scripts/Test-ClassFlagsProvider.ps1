param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[Parameter(Mandatory=$true)][string[]]$ProviderPack,
[Parameter(Mandatory=$true)][string]$SeedDiagnosticDirectory,[string]$Runtime='.boom/assembly-runtime-v109-frames-a')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/class-flags-provider-tests/'+[guid]::NewGuid().ToString('N'));$image=Join-Path $root 'image';[IO.Directory]::CreateDirectory($root)|Out-Null
$arguments=@((Join-Path $PSScriptRoot 'prepare-class-flags-probe.py'),'--batch',$Batch,'--plan',$Plan,'--runtime',(Join-Path $runtimePath 'boom-runtime.dll'),'--output',$image,'--seed',(Join-Path $SeedDiagnosticDirectory 'result.json'))
foreach($pack in $ProviderPack){$arguments+=@('--provider',$pack)}
& D:/Dev/Python312/python.exe @arguments > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 20;throw 'Class flags source selection failed'}
& (Join-Path $PSScriptRoot 'Build-DiagnosticClosure.ps1') -Batch $Batch -Plan $Plan -Output $image -Runtime $runtimePath -PreparedSelection > "$root/build.log" 2>&1
if(-not $?){Get-Content "$root/build.log" -Tail 20;throw 'Class flags source image failed'}
$source=Get-Content "$image/source.json" -Raw|ConvertFrom-Json
[IO.Directory]::CreateDirectory("$root/reference")|Out-Null
& D:/Dev/Java/jdk-21/bin/javac.exe -source 21 -target 21 -proc:none --add-exports java.base/jdk.internal.reflect=ALL-UNNAMED -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/NormalClassFlagsReference.java') > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/javac.log" -Tail 12;throw 'Class flags oracle compile failed'}
$classpath=@($source.oracle_classpath) -join [IO.Path]::PathSeparator
$javaArgs=@('--add-exports=java.base/jdk.internal.reflect=ALL-UNNAMED',('-Dboom.oracle.classpath='+$classpath),'-cp',"$root/reference",'NormalClassFlagsReference')+@($source.cases|ForEach-Object{$_.name})
$argumentFile=Join-Path $root 'oracle-args.txt';[IO.File]::WriteAllLines($argumentFile,[string[]]@($javaArgs|ForEach-Object{'"'+$_.Replace('\','/').Replace('"','\"')+'"'}),[Text.UTF8Encoding]::new($false))
& D:/Dev/Java/jdk-21/bin/java.exe ("@"+$argumentFile) > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/oracle.err" -Tail 15;throw 'Class flags oracle failed'}
$lines=@(Get-Content "$root/oracle.tsv");if($lines.Count -ne $source.cases.Count){throw 'Class flags oracle case coverage differs'}
for($i=0;$i -lt $lines.Count;$i++){$row=$lines[$i].Split("`t");$case=$source.cases[$i];if($row.Count -ne 3 -or $row[0] -cne $case.name -or [int]$row[1] -ne $case.raw_flags -or [int]$row[2] -ne $case.modifiers){throw ('Class flags JVM metadata differs: '+$case.name)}}
Add-Type -Path (Join-Path $project 'tests/host/NormalClassFlagsProviderProbe.cs')
$v=[BoomNormalClassFlagsProviderProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $image 'diagnostic-image.dll'),"$image/source.json")
$result=[ordered]@{passed=$true;batch=$source.batch;scope='normal_Class_raw_access_and_reflection_modifiers_original_natives';cases=$v[0];distinct_raw_and_modifier_cases=$v[1];array_cases=$v[2];error_checks=$v[3];workers=$v[4];parallel_calls=$v[5];source_native_methods=2;JVM_oracle='both_values_per_case';warm_queries_allocate_guest_objects=$false;fixture_loaders=@($source.fixture_loaders).Count;fixture_modules=@($source.fixture_modules).Count;full_module_bootstrap=$false;target_constructors_or_initializers_executed=$false;Java_codegen_rerun=$false;diagnostic_image=$true;all_native_frames=$false;automatic_gc=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
