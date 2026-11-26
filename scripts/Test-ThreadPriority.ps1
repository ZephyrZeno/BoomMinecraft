param([string]$OutputDirectory,[string]$RuntimeDirectory)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $OutputDirectory){$OutputDirectory=Join-Path $project ('.boom/thread-priority-tests/'+[guid]::NewGuid().ToString('N'))}
$root=[IO.Path]::GetFullPath($OutputDirectory);$allowed=[IO.Path]::GetFullPath((Join-Path $project '.boom/thread-priority-tests'))+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $root)){throw 'Use a fresh isolated thread-priority directory'}
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText((Join-Path $project '.boom/current-thread-priority-test.txt'),$root)
if($RuntimeDirectory){
    $runtimeRoot=(Resolve-Path -LiteralPath $RuntimeDirectory).Path
    $metadata=Get-Content -LiteralPath (Join-Path $runtimeRoot 'runtime.json') -Raw|ConvertFrom-Json
    if((Get-FileHash -LiteralPath (Join-Path $runtimeRoot 'boom-runtime.dll') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $metadata.sha256){throw 'Existing runtime DLL changed'}
    foreach($entry in $metadata.sources.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $project $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value){throw ('Existing runtime source changed: '+$entry.Name)}}
}else{
    $runtimeRoot=$root
    & (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $runtimeRoot *> (Join-Path $root 'runtime-build.log')
    if(-not $?){throw 'Assembly runtime build failed'}
}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:/SOFTWARE/Microsoft/Windows Kits/Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/kernel32.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$obj=Join-Path $root 'thread-priority-probe.obj';$dll=Join-Path $root 'thread-priority-probe.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$obj" (Join-Path $project 'native/probe/thread_priority_probe.asm') *> (Join-Path $root 'probe-assembler.log')
if($LASTEXITCODE -ne 0){throw 'Priority test callback assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_priority_test_main /EXPORT:boom_priority_test_exit "/OUT:$dll" $obj (Join-Path $runtimeRoot 'boom-runtime.lib') (Join-Path $sdk.FullName 'um/x64/kernel32.lib') *> (Join-Path $root 'probe-link.log')
if($LASTEXITCODE -ne 0){throw 'Priority callback link failed'}
Add-Type -Path (Join-Path $project 'tests/host/ThreadPriorityProbe.cs')
[BoomThreadPriorityProbe]::Run((Join-Path $runtimeRoot 'boom-runtime.dll'),$dll)
$sources=[ordered]@{};foreach($n in @('native/runtime/thread_registry.asm','native/probe/thread_priority_probe.asm','scripts/Build-AssemblyRuntime.ps1','scripts/Test-ThreadPriority.ps1','tests/host/ThreadPriorityProbe.cs')){$sources[$n]=(Get-FileHash -LiteralPath (Join-Path $project $n) -Algorithm SHA256).Hash.ToLowerInvariant()}
$result=[ordered]@{passed=$true;scope='assembly_thread_priority_kernel_only';runtime_language='assembly';owned_OS_priority_cases=1000;external_self_priority_cases=10;external_remote_priority_cases=10;concurrent_detach_priority_calls=4000;invalid_range_cases=4;new_finished_released_source_noop_checked=$true;source_record_lifetime_protected=$true;owned_callback_and_exit_result_verified=$true;registry_cleanup_completed=$true;heap_cleanup_completed=$true;original_Thread_setPriority0_executed=$false;original_Thread_start_priority_applied=$false;game_started=$false;world_created=$false;sources=$sources;runtime_directory=$runtimeRoot;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json)
[IO.File]::WriteAllText((Join-Path $project '.boom/latest-thread-priority-test.txt'),$root);Write-Output $json
