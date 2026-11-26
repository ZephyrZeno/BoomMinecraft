param([Parameter(Mandatory=$true)][string]$RuntimeDirectory,[switch]$IntegratedRuntime)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtime=(Resolve-Path -LiteralPath $RuntimeDirectory).Path
$metadata=Get-Content -LiteralPath (Join-Path $runtime 'runtime.json') -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath (Join-Path $runtime 'boom-runtime.dll') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $metadata.sha256){throw 'Runtime changed'}
foreach($name in @('native/runtime/monitors.asm','native/runtime/heap.asm')){if((Get-FileHash -LiteralPath (Join-Path $project $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $metadata.sources.$name){throw 'Monitor ABI source changed'}}
$root=Join-Path $project ('.boom/monitor-abort-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText((Join-Path $project '.boom/current-monitor-abort-test.txt'),$root)
$source=Join-Path $project 'native/runtime/monitor_abort.asm';$hash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
if($IntegratedRuntime){
    if($metadata.sources.'native/runtime/monitor_abort.asm' -ne $hash.ToLowerInvariant()){throw 'Runtime lacks the current monitor teardown source'}
    $dll=Join-Path $runtime 'boom-runtime.dll'
}else{
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:/SOFTWARE/Microsoft/Windows Kits/Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$obj=Join-Path $root 'monitor-abort.obj';$dll=Join-Path $root 'monitor-abort-probe.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$obj" $source *> (Join-Path $root 'assembler.log')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath (Join-Path $root 'assembler.log') -Tail 15;throw 'Monitor abort assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_monitor_abort_owned "/OUT:$dll" $obj (Join-Path $runtime 'boom-runtime.lib') (Join-Path $sdk.FullName 'um/x64/kernel32.lib') (Join-Path $sdk.FullName 'um/x64/synchronization.lib') *> (Join-Path $root 'link.log')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath (Join-Path $root 'link.log') -Tail 12;throw 'Monitor abort link failed'}
}
Add-Type -Path (Join-Path $project 'tests/host/MonitorAbortProbe.cs');[BoomMonitorAbortProbe]::Run((Join-Path $runtime 'boom-runtime.dll'),$dll)
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $hash){throw 'Abort kernel changed during verification'}
$r=[ordered]@{passed=$true;scope='assembly_controlled_monitor_teardown_kernel_only';runtime_language='assembly';current_OS_owner_only=$true;recursive_acquisitions_counted=$true;real_contender_woken=$true;ordinary_Throwable_and_live_Java_frame_rejected=$true;unauthorized_stop_rejected=$true;unsupported_wait_metadata_rejected=$true;malformed_accounting_no_partial_release=$true;Context32_and_VM_plan_preserved=$true;idle_nodes_reclaimed_by_actual_heap_collection=$true;monitor_and_heap_cleanup_completed=$true;Java_thread_boundary_integrated=$false;VM_stop_authorization_helper_integrated=$false;assembly_runtime_DLL_rebuilt=$false;game_started=$false;world_created=$false;source_sha256=$hash.ToLowerInvariant();host_sha256=(Get-FileHash -LiteralPath (Join-Path $project 'tests/host/MonitorAbortProbe.cs') -Algorithm SHA256).Hash.ToLowerInvariant();script_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();runtime_sha256=$metadata.sha256;run_directory=$root}
$r['integrated_assembly_runtime_exports']=[bool]$IntegratedRuntime
$r['separate_adapter_built']= -not $IntegratedRuntime
$json=$r|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $project '.boom/latest-monitor-abort-test.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
