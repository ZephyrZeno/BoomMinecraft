param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v96-final')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/batch-string-intern-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-batch-string-intern-probe.py') $Batch --plan $Plan --output $root > "$root/prepare.log"
if($LASTEXITCODE -ne 0){throw 'Intern source closure preparation failed'}
$closure=Get-Content -LiteralPath "$root/closure.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10;$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $root 'initialization-closure.obj';$dll=Join-Path $root 'string-intern-closure.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" "$root/initialization-closure.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/assembler.log" -Tail 14;throw 'Intern closure assembly failed'}
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
$lines+=@($closure.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"')
$lines+=@($closure.exports|Sort-Object -Unique|ForEach-Object{'/EXPORT:'+$_});[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/link.log" -Tail 14;throw 'Intern closure link failed'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-initialization-closure.py') $root --output "$root/selection-verification.json" > "$root/selection-verification.log"
if($LASTEXITCODE -ne 0){throw 'Intern source closure verification failed'}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/JavaStringInternReference.java') > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'Intern JVM oracle compilation failed'}
& "$java/java.exe" -cp "$root/reference" JavaStringInternReference "$root/dynamic-cases.bin" "$root/oracle.tsv" > "$root/oracle.out" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'Intern JVM oracle execution failed'}
Add-Type -Path (Join-Path $project 'tests/host/JavaStringInternProbe.cs')
$c=[BoomJavaStringInternProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$closure.intern_entries.intern,$closure.intern_entries.getName)
if($c[9] -ne 8196){throw 'JVM intern comparison incomplete'}
$result=[ordered]@{passed=$true;scope='production_source_String_intern_with_original_Class_getName_and_locked_literals';runtime_language='assembly';batch=$closure.batch;
source_native_methods=@($closure.selected_String_intern_natives.PSObject.Properties).Count;source_Java_methods=@($closure.selected_methods.PSObject.Properties).Count;
static_adoption_and_duplicate_calls=$c[0];static_factory_race_calls=$c[1];dynamic_cases=$c[2];parallel_calls=$c[3];workers=8;error_checks=$c[4];table_capacity=$c[5];quiescent_collected_objects=$c[6];canonical_dynamic_before_retry=$c[7];live_objects=$c[8];JVM_intern_hash_cases=$c[9];
intern_before_ldc_and_getName=$true;cross_coder_UTF16_identity=$true;growth_OOM_and_quiescent_recovery=$true;warm_guest_allocations=0;strong_retention=$true;weak_intern=$false;
String_constructors_executed=$false;String_class_initialization_executed=$false;Class_class_initialization_executed=$false;System_boot_phases_completed=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
