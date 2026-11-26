param([Parameter(Mandatory=$true)][string]$Batch,[string]$Runtime='.boom/assembly-runtime-v98-final')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/concat-thunk-fixtures/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe scripts/prepare-concat-thunk-fixture.py $Batch --output $root > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/prepare.err" -Tail 12;throw 'Source concat thunk fixture preparation failed'}
$m=Get-Content -LiteralPath "$root/fixture.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10;$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $root 'fixture.obj';$dll=Join-Path $root 'fixture.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" "$root/fixture.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/assembler.log" -Tail 10;throw 'Concat fixture assembly failed'}
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
$lines+=@($m.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"');$lines+=@($m.exports|Sort-Object -Unique|ForEach-Object{'/EXPORT:'+$_})
[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/link.log" -Tail 12;throw 'Concat fixture link failed'}
& D:/Dev/Python312/python.exe scripts/verify-concat-thunk-fixture.py $root > "$root/verification.log"
if($LASTEXITCODE -ne 0){throw 'Concat source function/data verification failed'}
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -encoding UTF-8 -d "$root/reference" java/reference/JavaConcatReference.java > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'Concat source oracle javac failed'}
& D:/Dev/Java/jdk-21/bin/java.exe -cp "$root/reference" JavaConcatReference "$root/cases.bin" "$root/oracle.bin" > "$root/oracle.out" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/oracle.err" -Tail 10;throw 'Concat source oracle failed'}
Add-Type -Path tests/host/JavaConcatProbe.cs
$v=[BoomJavaConcatProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$true)
$result=[ordered]@{passed=$true;fixture_only=$true;scope='actual_generated_source_thunks_under_VM_prepared_BSM_fixture';batch=$m.batch;source_thunks=@($m.selected_sites).Count;
JVM_cases=$v[0];parallel_calls=$v[1];workers=8;error_checks=$v[2];quiescent_collected=$v[3];OOM_collected=$v[4];normal_input_String_objects=$v[5];live_objects=$v[6];
original_bootstrap_initialization_executed=$false;original_Java_conversions_executed=$false;bootstrap_gate_failure_verified=$true;automatic_gc=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
