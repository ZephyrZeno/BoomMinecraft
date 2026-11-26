param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v92-final')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/batch-stream-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-batch-streams-probe.py') $Batch --plan $Plan --output $root > "$root/prepare.log"
if($LASTEXITCODE -ne 0){throw 'Source streams closure preparation failed'}
$closure=Get-Content "$root/closure.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $root 'initialization-closure.obj';$dll=Join-Path $root 'streams-closure.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" "$root/initialization-closure.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 15;throw 'Streams closure assembly failed'}
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
$lines+=@($closure.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"')
$lines+=@($closure.exports|Sort-Object -Unique|ForEach-Object{'/EXPORT:'+$_});[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 15;throw 'Streams closure link failed'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-initialization-closure.py') $root --output "$root/selection-verification.json" > "$root/selection-verification.log"
if($LASTEXITCODE -ne 0){throw 'Source streams selection verification failed'}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/SourceStreamsReference.java')
if($LASTEXITCODE -ne 0){throw 'Source streams oracle compilation failed'}
& "$java/java.exe" --add-opens java.base/java.lang=ALL-UNNAMED -cp "$root/reference" SourceStreamsReference "$root/oracle.txt" > "$root/oracle.out" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'Source streams JVM oracle failed'}
Add-Type -Path (Join-Path $project 'tests/host/BatchStreamsProbe.cs')
$native=@{};foreach($p in $closure.selected_native_methods.PSObject.Properties){$native[$p.Value.name]='boom_m'+$p.Value.method}
$inputMethods=@{};foreach($entry in $closure.requested_method_roots){if($entry.owner -eq 'java/io/ByteArrayInputStream'){$inputMethods[$entry.name]=$entry.symbol}}
$c=[BoomBatchStreamsProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$closure.system_class,$closure.input_class,$closure.print_class,$closure.object_class,$closure.byte_array,$native.setIn0,$native.setOut0,$native.setErr0,$inputMethods.'<init>',$inputMethods.read,$inputMethods.available,$inputMethods.reset)
if($c[0] -ne $closure.receiver_shapes){throw 'Stream subtype execution coverage differs'}
$result=[ordered]@{passed=$true;scope='source_System_stream_setters_original_input_instance_methods_and_static_roots';runtime_language='assembly';batch=$closure.batch;source_receiver_shapes=$c[0];source_receiver_publications=$c[1];parallel_setter_calls=$c[2];workers=$c[3];error_checks=$c[4];overwritten_objects_collected=$c[5];cleared_graph_objects_collected=$c[6];idle_monitor_records_collected=$c[7];source_Java_methods=@($closure.selected_methods.PSObject.Properties).Count;source_native_methods=@($closure.selected_native_methods.PSObject.Properties).Count;actual_source_static_roots_updated=$true;null_before_heap_bind=$true;source_input_constructor_read_reset_executed=$true;input_class_initialization_executed=$false;output_constructors_executed=$false;file_or_console_IO_executed=$false;source_System_clinit_executed=$true;System_boot_phases_completed=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 6;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
