param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v95-final')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/batch-java-class-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-batch-java-classes-probe.py') $Batch --plan $Plan --output $root > "$root/prepare.log"
if($LASTEXITCODE -ne 0){throw 'Source Class closure preparation failed'}
$closure=Get-Content "$root/closure.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10;$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $root 'initialization-closure.obj';$dll=Join-Path $root 'java-classes-closure.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" "$root/initialization-closure.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 15;throw 'Class closure assembly failed'}
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
$lines+=@($closure.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"')
$lines+=@($closure.exports|Sort-Object -Unique|ForEach-Object{'/EXPORT:'+$_});[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 15;throw 'Class closure link failed'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-initialization-closure.py') $root --output "$root/selection-verification.json" > "$root/selection-verification.log"
if($LASTEXITCODE -ne 0){throw 'Source Class provenance verification failed'}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/JavaClassReference.java')
if($LASTEXITCODE -ne 0){throw 'Class oracle compilation failed'}
& "$java/java.exe" -cp "$root/reference" JavaClassReference "$root/oracle.tsv" > "$root/oracle.out" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'Class JVM oracle failed'}
Add-Type -Path (Join-Path $project 'tests/host/JavaClassProbe.cs')
$c=[BoomJavaClassProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$closure.Class_source_shape.module_type,$closure.Class_getters.getComponentType,$closure.Class_getters.getClassLoader0,$closure.Class_getters.getModule,$closure.Class_getters.getName)
if($c[0] -ne $closure.source_types){throw 'Class type execution coverage differs'}
$result=[ordered]@{passed=$true;scope='production_source_Class_mirrors_core_queries_and_original_Java_getters';runtime_language='assembly';batch=$closure.batch;mirrored_source_types=$c[0];core_queries=$c[1];JVM_assignability_cases=$c[2];workers=$c[3];error_checks=$c[4];unrooted_objects_collected=$c[5];rooted_objects_after_collection=$c[6];original_Java_getter_calls=$c[7];original_Class_getName_calls=$c[8];Class_name_error_checks=$c[9];canonical_Class_names=$c[10];Class_name_source_literal_aliases=$c[11];collected_root_regions=3;root_region_cells=$c[12];root_region_error_checks=$c[13];root_snapshot_guest_allocations=0;warm_Class_name_guest_allocations=0;selected_Java_methods=@($closure.selected_methods.PSObject.Properties).Count;VM_prepared_loader_and_module_shapes=$true;loader_module_constructors_executed=$false;source_Class_clinit_executed=$false;Class_native_registration_complete=$false;module_bootstrap_completed=$false;System_boot_phases_completed=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 6;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
