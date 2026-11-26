param([string]$Runtime='.boom/assembly-runtime-v98-final',[string]$Image='.boom/batch-property-probes/0cdf676d41a44fe2b91f6cdbf67d66ad/properties-closure.dll')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/java-concat-kernel-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe scripts/prepare-concat-kernel-cases.py --output $root > "$root/prepare.log"
if($LASTEXITCODE -ne 0){throw 'Concat case preparation failed'}
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -encoding UTF-8 -d "$root/reference" java/reference/JavaConcatReference.java > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/javac.log" -Tail 12;throw 'Concat oracle compilation failed'}
& D:/Dev/Java/jdk-21/bin/java.exe -cp "$root/reference" JavaConcatReference "$root/cases.bin" "$root/oracle.bin" > "$root/oracle.out" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/oracle.err" -Tail 12;throw 'Concat JVM oracle failed'}
Add-Type -Path tests/host/JavaConcatProbe.cs
$c=[BoomJavaConcatProbe]::Run((Join-Path (Resolve-Path -LiteralPath $Runtime).Path 'boom-runtime.dll'),(Resolve-Path -LiteralPath $Image).Path,$root)
$result=[ordered]@{passed=$true;fixture_only=$true;scope='normal_layout_concat_kernel_not_source_bootstrap_execution';JVM_cases=$c[0];parallel_calls=$c[1];workers=8;error_checks=$c[2];
quiescent_collected=$c[3];OOM_collected=$c[4];input_String_objects=$c[5];live_objects=$c[6];longer_than_65535_characters=$true;
original_Java_conversions_executed=$false;bootstrap_initialization_executed=$false;automatic_gc=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $project '.boom/latest-concat-kernel-v98.txt'),$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
