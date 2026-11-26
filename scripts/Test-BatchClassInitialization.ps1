param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v95-final')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/class-initialization-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-class-init-probe.py') $Batch --plan $Plan --output $root > "$root/prepare.log"
if($LASTEXITCODE -ne 0){throw 'Original initialization closure preparation failed'}
$closure=Get-Content "$root/closure.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $root 'initialization-closure.obj';$dll=Join-Path $root 'initialization-closure.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" "$root/initialization-closure.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 20;throw 'Initialization closure assembly failed'}
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
$lines+=@($closure.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"')
$lines+=@($closure.exports|ForEach-Object{'/EXPORT:'+$_});[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 20;throw 'Initialization closure link failed'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-initialization-closure.py') $root --output "$root/selection-verification.json" > "$root/selection-verification.log"
if($LASTEXITCODE -ne 0){throw 'Original source closure provenance verification failed'}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/EnumInitializationReference.java')
if($LASTEXITCODE -ne 0){throw 'Enum oracle compilation failed'}
& "$java/java.exe" -cp "$root/reference" EnumInitializationReference "$root/roots.tsv" "$root/constants.tsv" "$root/constants-oracle.tsv" > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'Enum initialization JVM oracle failed'}
Add-Type -Path (Join-Path $project 'tests/host/ClassInitializationProbe.cs')
$counts=[BoomClassInitializationProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$closure.enum_methods.name,$closure.enum_methods.ordinal,$closure.enum_methods.getDeclaringClass)
$result=[ordered]@{passed=$true;scope='selected_original_JDK_enum_initialization_closure';runtime_language='assembly';batch=$closure.batch;root_classes=$counts[0];enum_instances=$counts[1];guest_allocated_bytes=$counts[2];warm_initialization_calls=$counts[3];workers=$counts[4];selected_source_classes=@($closure.selected_classes).Count;selected_source_methods=@($closure.selected_methods.PSObject.Properties).Count;class_initialization_executed=$true;Java_constructor_and_initializer_bodies=$true;initial_static_references_zero=$true;quiescent_static_and_literal_roots=$true;System_boot_phases_completed=$false;String_class_initialization_executed=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$result.original_Enum_getDeclaringClass_calls=$counts[8]
$result.source_Class_initialization_executed=$false
$result.module_bootstrap_completed=$false
$result['constant_classes']=$counts[5];$result['constant_fields_checked']=$counts[6]
$result['original_values_arrays_returned']=$counts[7]
$json=$result|ConvertTo-Json -Depth 6;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $project '.boom/latest-batch-class-initialization.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
