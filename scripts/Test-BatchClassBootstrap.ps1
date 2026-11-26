param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v99-final')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/class-bootstrap-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe scripts/prepare-class-bootstrap-probe.py $Batch --plan $Plan --output $root > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/prepare.err" -Tail 12;throw 'Original Class bootstrap source selection failed'}
$closure=Get-Content -LiteralPath "$root/closure.json" -Raw|ConvertFrom-Json;$m=Get-Content -LiteralPath "$root/bootstrap-probe.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10;$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $root 'initialization-closure.obj';$dll=Join-Path $root 'class-bootstrap-closure.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" "$root/initialization-closure.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/assembler.log" -Tail 12;throw 'Class bootstrap closure assembly failed'}
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
$lines+=@($closure.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"');$lines+=@($closure.exports|Sort-Object -Unique|ForEach-Object{'/EXPORT:'+$_})
[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/link.log" -Tail 14;throw 'Class bootstrap closure link failed'}
& D:/Dev/Python312/python.exe scripts/verify-initialization-closure.py $root --output "$root/selection-verification.json" > "$root/selection-verification.log"
if($LASTEXITCODE -ne 0){throw 'Original Class bootstrap provenance failed'}
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -encoding UTF-8 -d "$root/reference" java/reference/ClassBootstrapReference.java > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'Class bootstrap JVM oracle compile failed'}
& D:/Dev/Java/jdk-21/bin/java.exe --add-opens java.base/java.lang=ALL-UNNAMED -cp "$root/reference" ClassBootstrapReference > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/oracle.err" -Tail 12;throw 'Class bootstrap JVM oracle failed'}
$oracle=Get-Content -LiteralPath "$root/oracle.tsv"
foreach($primitive in $m.primitives){if(($primitive.name+"`ttrue`tfalse") -notin $oracle){throw 'JVM primitive/assertion oracle differs'}}
foreach($line in @("EMPTY_CLASS_ARRAY`t0","serialPersistentFields`t0","invalid_names`t7`tClassNotFoundException")){if($line -notin $oracle){throw 'JVM static array/error oracle differs'}}
Add-Type -Path tests/host/ClassBootstrapProbe.cs
$v=[BoomClassBootstrapProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$m.class_id,$m.empty_class_field,$m.serial_fields_field,$m.getName,$m.getComponentType)
$result=[ordered]@{passed=$true;fixture_only=$false;scope='original_Class_clinit_wrapper_clinits_getters_and_partial_AOT_native_binding';batch=$closure.batch;
source_Class_initialized=$true;source_wrapper_initializers=$v[3];source_Java_calls=$v[4];primitive_JVM_cases=$v[2];cold_init_workers=$v[0];parallel_calls=$v[1];error_checks=$v[5];quiescent_collected=$v[6];
registered_prelinked_Class_methods=10;full_Class_native_registration_complete=$false;primitive_names_have_normal_String_layout=$true;UTF16_name_input_shapes_checked=$true;
assertion_Java_wrapper_executed=$false;assertion_profile='frozen_default_disabled';String_class_initialization_executed=$false;String_constructors_executed=$false;
normal_Throwable_materialization_executed=$false;module_bootstrap_completed=$false;System_boot_phases_completed=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
