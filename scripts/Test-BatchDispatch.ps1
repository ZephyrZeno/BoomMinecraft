param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v87-final',[switch]$AutomaticClosure)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/batch-dispatch-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$prepareArgs=@($Batch,'--plan',$Plan,'--output',$root);if($AutomaticClosure){$prepareArgs+='--automatic-closure'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-batch-dispatch-probe.py') @prepareArgs > "$root/prepare.log"
if($LASTEXITCODE -ne 0){throw 'Original dispatch closure preparation failed'}
$closure=Get-Content "$root/closure.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$stem=if($AutomaticClosure){'initialization-closure'}else{'dispatch-closure'}
$object=Join-Path $root "$stem.obj";$dll=Join-Path $root 'dispatch-closure.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" "$root/$stem.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 15;throw 'Dispatch closure assembly failed'}
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
$lines+=@($closure.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"')
$lines+=@($closure.exports|ForEach-Object{'/EXPORT:'+$_});[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 15;throw 'Dispatch closure link failed'}
if($AutomaticClosure){
    & D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-initialization-closure.py') $root --output "$root/selection-verification.json" > "$root/selection-verification.log"
    if($LASTEXITCODE -ne 0){throw 'Automatic source dispatch closure verification failed'}
}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/BufferDispatchReference.java')
if($LASTEXITCODE -ne 0){throw 'Buffer oracle compilation failed'}
& "$java/java.exe" -cp "$root/reference" BufferDispatchReference > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'Buffer JVM oracle failed'}
Add-Type -Path (Join-Path $project 'tests/host/BatchDispatchProbe.cs')
$counts=[BoomBatchDispatchProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$closure.getters.isDirect,$closure.buffer_class,$closure.object_class,$closure.object_equals)
$result=[ordered]@{passed=$true;scope='selected_original_ByteBuffer_isDirect_dispatch_table_and_ASM_kernel_guards';runtime_language='assembly';batch=$closure.batch;source_receiver_classes=$counts[0];positive_getter_calls=$counts[1];workers=$counts[2];kernel_error_checks=$counts[3];array_Object_equals_calls=$counts[4];selected_source_methods=@($closure.selected_method_origins.PSObject.Properties).Count;selected_shared_tables=$closure.selected_table_count;selected_receiver_rows=$closure.selected_receiver_rows;selected_MASM_copied_exactly=$true;guest_allocations_during_getters=0;Java_constructors_executed=$false;class_initialization_executed=$false;interface_dispatch_execution_verified=$false;System_boot_phases_completed=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$result.automatic_dependency_selection=[bool]$AutomaticClosure
$json=$result|ConvertTo-Json -Depth 6;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
