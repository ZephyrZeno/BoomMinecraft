param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v87-final')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/batch-system-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-batch-system-probe.py') $Batch --plan $Plan --output $root > "$root/prepare.log"
if($LASTEXITCODE -ne 0){throw 'System source closure preparation failed'}
$closure=Get-Content "$root/closure.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $root 'initialization-closure.obj';$dll=Join-Path $root 'System-closure.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" "$root/initialization-closure.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 20;throw 'System closure assembly failed'}
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
$lines+=@($closure.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"')
$lines+=@($closure.exports|Sort-Object -Unique|ForEach-Object{'/EXPORT:'+$_});[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 20;throw 'System closure link failed'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-initialization-closure.py') $root --output "$root/selection-verification.json" > "$root/selection-verification.log"
if($LASTEXITCODE -ne 0){throw 'System source provenance verification failed'}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/SystemArrayCopyReference.java')
if($LASTEXITCODE -ne 0){throw 'System arraycopy oracle compilation failed'}
& "$java/java.exe" -cp "$root/reference" SystemArrayCopyReference > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'System arraycopy JVM oracle failed'}
Add-Type -Path (Join-Path $project 'tests/host/BatchSystemProbe.cs')
$methods=@{};foreach($property in $closure.selected_native_methods.PSObject.Properties){$methods[$property.Value.name]='boom_m'+$property.Value.method}
$c=[BoomBatchSystemProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$closure.system_class,$closure.object_class,$methods.registerNatives,$methods.currentTimeMillis,$methods.nanoTime,$methods.arraycopy)
$result=[ordered]@{passed=$true;scope='original_System_clinit_generated_source_native_registration_and_services';runtime_language='assembly';batch=$closure.batch;source_classes=@($closure.selected_classes).Count;source_Java_methods=@($closure.selected_methods.PSObject.Properties).Count;source_native_methods=@($closure.selected_native_methods.PSObject.Properties).Count;registered_native_methods=3;initial_registration_null=$true;source_System_clinit_executed=$true;arraycopy_JVM_cases=$c[0];clock_calls=$c[1];parallel_arraycopy_calls=$c[2];workers=$c[3];quiescent_collected_arrays=$c[4];pending_context_and_unregistered_guards=$true;arraycopy_guest_allocations=0;System_boot_phases_completed=$false;String_class_initialization_executed=$false;Java_exception_materialization_verified=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 6;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
