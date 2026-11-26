param([Parameter(Mandatory=$true)][string]$RuntimeDirectory,[string]$OutputDirectory,[switch]$IntegratedRuntime)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $OutputDirectory){$OutputDirectory=Join-Path $project ('.boom/reference-pending-tests/'+[guid]::NewGuid().ToString('N'))}
$root=[IO.Path]::GetFullPath($OutputDirectory);$allowed=[IO.Path]::GetFullPath((Join-Path $project '.boom/reference-pending-tests'))+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $root)){throw 'Use a fresh isolated pending-reference test directory'}
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText((Join-Path $project '.boom/current-reference-pending-test.txt'),$root)
$runtime=(Resolve-Path -LiteralPath $RuntimeDirectory).Path;$metadata=Get-Content -LiteralPath (Join-Path $runtime 'runtime.json') -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath (Join-Path $runtime 'boom-runtime.dll') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $metadata.sha256){throw 'Runtime changed'}
foreach($entry in $metadata.sources.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $project $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value){throw ('Runtime source changed: '+$entry.Name)}}
$source=Join-Path $project 'native/runtime/reference_pending.asm';$sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
if($IntegratedRuntime){
    if($metadata.sources.'native/runtime/reference_pending.asm' -ne $sourceHash.ToLowerInvariant()){throw 'Integrated runtime does not include the current pending-reference kernel'}
    $dll=Join-Path $runtime 'boom-runtime.dll'
}else{
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:/SOFTWARE/Microsoft/Windows Kits/Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/kernel32.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$obj=Join-Path $root 'reference-pending.obj';$dll=Join-Path $root 'reference-pending-probe.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$obj" $source *> (Join-Path $root 'assembler.log')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath (Join-Path $root 'assembler.log') -Tail 18;throw 'Pending-reference assembly failed'}
$names=@('create','publish','get','has','wait','stop','stopping','roots_begin','roots_end','destroy');$exports=@($names|ForEach-Object{'/EXPORT:boom_reference_pending_'+$_})
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT @exports "/OUT:$dll" $obj (Join-Path $runtime 'boom-runtime.lib') (Join-Path $sdk.FullName 'um/x64/kernel32.lib') *> (Join-Path $root 'link.log')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath (Join-Path $root 'link.log') -Tail 15;throw 'Pending-reference link failed'}
}
Add-Type -Path (Join-Path $project 'tests/host/ReferencePendingProbe.cs')
[BoomReferencePendingProbe]::Run((Join-Path $runtime 'boom-runtime.dll'),$dll)
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $sourceHash){throw 'Pending kernel changed during execution'}
$sources=[ordered]@{};foreach($name in @('native/runtime/reference_pending.asm','tests/host/ReferencePendingProbe.cs','scripts/Test-ReferencePending.ps1')){$sources[$name]=(Get-FileHash -LiteralPath (Join-Path $project $name) -Algorithm SHA256).Hash.ToLowerInvariant()}
$result=[ordered]@{passed=$true;scope='assembly_pending_reference_transport_kernel_only';runtime_language='assembly';integrated_assembly_runtime_exports=[bool]$IntegratedRuntime;separate_adapter_built=(-not $IntegratedRuntime);actual_empty_queue_wait_blocked=$true;publication_wake_races=128;competing_publishers=8;shutdown_woken_waiters=16;independent_pools=2;pending_batch_not_consumed_by_wait=$true;root_lease_and_owner_checked=$true;pending_head_and_child_preserved_during_actual_heap_collection=$true;unreachable_test_object_reclaimed=$true;stopped_queue_returns_aborted_status=$true;released_and_unknown_pool_rejected=$true;pool_and_heap_cleanup_completed=$true;original_Reference_wait_native_bound=$false;Java_worker_shutdown_unwind_integrated=$false;assembly_runtime_DLL_rebuilt=$false;game_started=$false;world_created=$false;runtime_sha256=$metadata.sha256;runtime_directory=$runtime;sources=$sources;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $project '.boom/latest-reference-pending-test.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
