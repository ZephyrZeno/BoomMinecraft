param(
    [Parameter(Mandatory=$true)][string]$Batch,
    [Parameter(Mandatory=$true)][string]$Plan,
    [Parameter(Mandatory=$true)][string]$IR,
    [string]$Runtime='.boom/assembly-runtime-v97-final',
    [string]$FixtureImage
)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$fixture=[bool]$FixtureImage
$folder=if($fixture){'java-property-kernel-probes'}else{'batch-property-probes'}
$root=Join-Path $project ('.boom/'+$folder+'/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
$receipt=Get-Content -LiteralPath (Join-Path $runtimePath 'runtime.json') -Raw|ConvertFrom-Json
foreach($name in @('native/runtime/system_properties.asm','native/runtime/vm_properties.asm','native/runtime/java_properties.asm')){
    if($receipt.sources.$name -ne (Get-FileHash -LiteralPath (Join-Path $project $name)).Hash.ToLowerInvariant()){throw "Property runtime source changed: $name"}
}
$prepare=@((Join-Path $PSScriptRoot 'prepare-batch-properties-probe.py'),$Batch,'--plan',$Plan,'--ir',$IR,'--output',$root)
if($fixture){$prepare+='--fixture'}
& D:/Dev/Python312/python.exe @prepare > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/prepare.err" -Tail 18;throw 'Property source preparation failed'}
$closure=$null
if($fixture){$dll=(Resolve-Path -LiteralPath $FixtureImage).Path}else{
    $closure=Get-Content -LiteralPath "$root/closure.json" -Raw|ConvertFrom-Json
    $vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
    $version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
    $bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
    $sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
    $sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
    $object=Join-Path $root 'initialization-closure.obj';$dll=Join-Path $root 'properties-closure.dll'
    & (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" "$root/initialization-closure.asm" > "$root/assembler.log" 2>&1
    if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/assembler.log" -Tail 14;throw 'Property source closure assembly failed'}
    $lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
    $lines+=@($closure.objects|ForEach-Object{'"'+$_+'"'})
    $lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"')
    $lines+=@($closure.exports|Sort-Object -Unique|ForEach-Object{'/EXPORT:'+$_})
    [IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
    & (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
    if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/link.log" -Tail 14;throw 'Property source closure link failed'}
    & D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-initialization-closure.py') $root --output "$root/selection-verification.json" > "$root/selection-verification.log"
    if($LASTEXITCODE -ne 0){throw 'Property source closure verification failed'}
}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/subset/dev/boom/properties/RawReference.java') > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'Property JVM oracle compilation failed'}
$start=[Diagnostics.ProcessStartInfo]::new();$start.FileName="$java/java.exe";$start.WorkingDirectory=$project
$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
foreach($argument in @('--add-opens','java.base/jdk.internal.util=ALL-UNNAMED','-cp',"$root/reference",'dev.boom.properties.RawReference',"$root/platform-oracle.bin")){$start.ArgumentList.Add($argument)}
foreach($name in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$start.Environment.Remove($name)|Out-Null}
$process=[Diagnostics.Process]::new();$process.StartInfo=$start
try{
    if(-not $process.Start()){throw 'Property JVM oracle start failed'}
    $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(30000)){throw 'Property JVM oracle timed out'}
    [IO.File]::WriteAllText("$root/oracle.out",$stdout.GetAwaiter().GetResult())
    [IO.File]::WriteAllText("$root/oracle.err",$stderr.GetAwaiter().GetResult())
    if($process.ExitCode -ne 0){throw 'Property JVM oracle execution failed'}
}finally{if(-not $process.HasExited){$process.Kill($true);$process.WaitForExit()};$process.Dispose()}
Add-Type -Path (Join-Path $project 'tests/host/JavaPropertiesProbe.cs')
if($fixture){$counts=[BoomJavaPropertiesProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root)}else{
    $entries=$closure.property_entries
    $counts=[BoomJavaPropertiesProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$entries.platformProperties,$entries.vmProperties,$entries.'<init>',$entries.propDefault)
}
$result=[ordered]@{passed=$true;fixture_only=$fixture;scope=$(if($fixture){'normal_source_layout_property_kernel_fixture'}else{'production_original_Raw_constructor_getter_and_property_natives'});
    batch=[IO.Path]::GetFullPath($Batch);runtime_language='assembly';platform_JVM_comparisons=$counts[0];VM_pairs=$counts[1];parallel_calls=$counts[2];workers=8;
    original_Java_calls=$counts[3];error_checks=$counts[4];UTF16_copy_cases=$counts[5];cold_OOM_collected=$counts[6];warm_OOM_collected=$counts[7];property_root_cells=$counts[8];live_objects=$counts[9];
    original_Raw_constructor_executed=(-not $fixture);Raw_class_preparation_executed=(-not $fixture);normal_source_String_and_array=$true;snapshot_clone_isolation=$true;OOM_retry_after_quiescent_GC=$true;
    String_constructors_executed=$false;String_class_initialization_executed=$false;System_boot_phases_completed=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false))
if($fixture){[IO.File]::WriteAllText((Join-Path $project '.boom/latest-properties-kernel-v97.txt'),$root,[Text.UTF8Encoding]::new($false))}
Write-Output $json
